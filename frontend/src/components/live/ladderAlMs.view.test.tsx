// ============================================================================
// ladderAlMs.view.test.tsx - GridView / LadderView con la sorgente "al ms"
// (ordine utente 23/09): i prezzi a schermo arrivano dal canale locale al tick;
// canale muto > N s -> si vede il DB; canale che riprende -> di nuovo il canale;
// un push piu' vecchio di quello mostrato non cambia lo schermo.
// Canale = LocalChannel VERO su WebSocket finto; push con le chiavi del
// ladder_worker di Betfair/stream/runner.py dentro la busta {"t","d"}.
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: {
        rpc: vi.fn(async () => ({ data: null, error: null })),
        from: vi.fn(),
        channel: vi.fn(),
        removeChannel: vi.fn(),
    },
}));

import { GridView } from './GridView';
import { LadderView, type LadderSource, type LadderOrderApi } from './LadderView';
import type { LiveLadderRow } from '@/lib/live';
import type { LiveOrderResult, LiveOrderRow, LivePositionRow } from '@/lib/liveOrders';
import { __resetLocalChannels } from '@/lib/localChannel';
import { sorgenteLadderAlMs, __resetLocalTransport } from '@/lib/localTransport';

class MockWebSocket {
    static instances: MockWebSocket[] = [];
    url: string;
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    constructor(url: string) { this.url = url; MockWebSocket.instances.push(this); }
    send(): void { /* nessuna richiesta */ }
    close(): void { /* serverClose() */ }
    serverOpen(): void { this.onopen?.(); }
    serverMessage(obj: unknown): void { this.onmessage?.({ data: JSON.stringify(obj) }); }
    serverClose(): void { this.onclose?.(); }
}
const ws47331 = () => {
    const w = [...MockWebSocket.instances].reverse().find((x) => x.url.endsWith(':47331'));
    if (!w) throw new Error('nessun socket 47331');
    return w;
};

const MID = '1.234567890';
// riga come nel ladder_worker (event_id, market_id, market_type, market_name, status, ladder)
function rigaRunner(updatedMs: number, bestBack: number): Omit<LiveLadderRow, 'updated_at'> {
    return {
        event_id: '34567890', market_id: MID, market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        status: 'OPEN',
        ladder: {
            updated_ms: updatedMs,
            selections: [
                {
                    selection_id: 47972, name: 'Casa', ltp: 2.9, tv: 1234.5,
                    back: [[bestBack, 10.5], [1.2, 5.0], [1.1, 3.0]], lay: [[40, 20.0], [42, 8.0], [44, 4.0]],
                    trd: [[2.9, 100.0]], wom: { back_pct: 40.0, lay_pct: 60.0 },
                },
            ],
        },
    };
}
const rigaDb = (ms: number, bb: number): LiveLadderRow & { id: number } =>
    ({ id: 17, ...rigaRunner(ms, bb), updated_at: '2026-09-23T10:00:00.123456+00:00' });

const ORDER_API: LadderOrderApi = {
    send: vi.fn(async () => ({ ok: true, action: 'place', mode: 'paper' } as LiveOrderResult)),
    fetchOrders: vi.fn(async () => [] as LiveOrderRow[]),
    fetchPositions: vi.fn(async () => [] as LivePositionRow[]),
};

function dbFinto(iniziale: LiveLadderRow | null) {
    const cbs: Array<(r: LiveLadderRow | null) => void> = [];
    const unsub = vi.fn();
    const db: LadderSource = {
        fetch: vi.fn(async () => iniziale),
        subscribe: vi.fn((_m: string, cb: (r: LiveLadderRow | null) => void) => { cbs.push(cb); return unsub; }),
    };
    return { db, unsub, emetti: (r: LiveLadderRow | null) => cbs[cbs.length - 1]?.(r) };
}

let ora = 5_000_000;
const adesso = () => ora;
// cella prezzo della griglia: title "BACK <stake> @ <prezzo> ..." (cellTitle di GridView)
const cellaBack = (p: string) => screen.queryByTitle(new RegExp(`^BACK .*@ ${p.replace('.', '\\.')}(\\D|$)`));

beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    ora = 5_000_000;
    localStorage.clear();
});
afterEach(() => {
    __resetLocalTransport();
    __resetLocalChannels();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe('GridView con sorgenteLadderAlMs', () => {
    it('canale che pubblica: i prezzi del canale sono a schermo entro il tick; muto > N: DB; riprende: canale', async () => {
        const { db, unsub, emetti } = dbFinto(rigaDb(100, 2.5));
        const src = sorgenteLadderAlMs('calcio', { db, adesso, mutoMs: 4_000 });
        const ws = ws47331();
        act(() => { ws.serverOpen(); });
        render(<GridView marketId={MID} orderMode="paper" ladderSource={src} orderApi={ORDER_API} />);
        expect(await screen.findByText('Casa')).toBeInTheDocument();
        expect(cellaBack('2.50')).toBeInTheDocument();          // fetch iniziale (DB, una volta)
        expect(db.fetch).toHaveBeenCalledTimes(1);

        // tick del canale: a schermo SUBITO, senza attese
        act(() => { ws.serverMessage({ t: 'ladder', d: rigaRunner(200, 3.1) }); });
        expect(cellaBack('3.10')).toBeInTheDocument();
        // connesso ma ancora senza push al montaggio = muto: il DB era aperto e il
        // primo tick del canale lo ha chiuso
        expect(db.subscribe).toHaveBeenCalledTimes(1);
        expect(unsub).toHaveBeenCalledTimes(1);

        // canale muto entro N: resta il canale
        act(() => { ora += 3_999; vi.advanceTimersByTime(1_000); });
        expect(db.subscribe).toHaveBeenCalledTimes(1);
        // canale muto oltre N: si apre il realtime DB e si vede il DB
        act(() => { ora += 2; vi.advanceTimersByTime(1_000); });
        expect(db.subscribe).toHaveBeenCalledTimes(2);
        act(() => { emetti(rigaDb(300, 3.3)); });
        expect(cellaBack('3.30')).toBeInTheDocument();

        // il canale riprende: si torna al canale e il DB si chiude
        act(() => { ws.serverMessage({ t: 'ladder', d: rigaRunner(400, 3.5) }); });
        expect(cellaBack('3.50')).toBeInTheDocument();
        expect(unsub).toHaveBeenCalledTimes(2);
        expect(db.fetch).toHaveBeenCalledTimes(1);               // nessuna lettura DB in piu'
    });

    it('push piu\' vecchio di quello mostrato: lo schermo non cambia', async () => {
        const { db } = dbFinto(null);
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = ws47331();
        act(() => { ws.serverOpen(); });
        render(<GridView marketId={MID} orderMode="paper" ladderSource={src} orderApi={ORDER_API} />);
        act(() => { ws.serverMessage({ t: 'ladder', d: rigaRunner(500, 3.1) }); });
        expect(await screen.findByText('Casa')).toBeInTheDocument();
        expect(cellaBack('3.10')).toBeInTheDocument();
        act(() => { ws.serverMessage({ t: 'ladder', d: rigaRunner(499, 7.4) }); });
        expect(cellaBack('7.40')).toBeNull();
        expect(cellaBack('3.10')).toBeInTheDocument();
    });
});

describe('LadderView con sorgenteLadderAlMs: indicatore "Aggiornato" gia\' esistente', () => {
    it('il testo dichiara la fonte della riga a schermo (canale / DB)', async () => {
        const { db, emetti } = dbFinto(null);
        const src = sorgenteLadderAlMs('calcio', { db, adesso, mutoMs: 4_000 });
        const ws = ws47331();
        act(() => { ws.serverOpen(); });
        render(<LadderView marketId={MID} orderMode="off" ladderSource={src} orderApi={ORDER_API} />);
        act(() => { ws.serverMessage({ t: 'ladder', d: rigaRunner(1_758_621_600_000, 3.1) }); });
        expect(await screen.findByText(/Aggiornato: .*\(canale\)/)).toBeInTheDocument();
        act(() => { ora += 4_001; vi.advanceTimersByTime(1_000); });
        act(() => { emetti(rigaDb(1_758_621_601_000, 3.3)); });
        expect(await screen.findByText(/Aggiornato: .*\(DB\)/)).toBeInTheDocument();
    });
});
