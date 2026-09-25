// ============================================================================
// XHedgePanel.canale.test.tsx - 25/09 (voce 12): l'analisi cross-market dal
// canale del runner calcio (47331, topic `betfair_live_xhedge`) sovrapposta al
// poll di 5 s, "mai unione". Include i test del modulo puro lib/xhedgeCanale.
//
// Finto = messaggio VERO: Betfair/stream/xhedge_worker.py (dopo l'upsert)
// -> canale_bot.pubblica_scritte: riga restituita dalla scrittura
// {id, event_id, mode, analysis, updated_at} (migrations/betfair_live_xhedge.sql)
// + busta {fonte: "canale", _seq, _pubblicato_ms} (canale_bot.busta).
// `analysis` con le chiavi di trading/xhedge.compute_xhedge (n_positions,
// summary, grid, suggestion, ignored_orders), come il test storico del pannello.
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, act } from '@testing-library/react';
import type { XhedgeRow } from '@/lib/liveOrders';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
function spingi(topic: string, d: unknown) { for (const cb of iscritti.get(topic) ?? []) cb(d); }

vi.mock('@/lib/liveOrders', () => ({
    fetchXhedge: vi.fn(),
    sendLiveOrderCommand: vi.fn(),
    fetchRiskRules: vi.fn(async () => []),
    requestRiskRule: vi.fn(),
    cancelRiskRule: vi.fn(),
    shouldResetLiveConfirm: (isLive: boolean, ok: boolean) => isLive === true && ok === true,
}));
vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn(() => ({
        getStatus: () => 'connected' as const,
        getHello: () => null,
        onStatus: () => () => { /* nessun cambio */ },
        subscribe: (topic: string, cb: Cb) => {
            let s = iscritti.get(topic);
            if (!s) { s = new Set(); iscritti.set(topic, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));

import { XHedgePanel } from './XHedgePanel';
import { fetchXhedge } from '@/lib/liveOrders';
import {
    applicaPushXhedge, leggiPushXhedge, potaXhedge, vistaXhedge,
} from '@/lib/xhedgeCanale';

const mFetch = vi.mocked(fetchXhedge);

function riga(updatedAt: string, worst: number, over: Partial<XhedgeRow> = {}): XhedgeRow {
    return {
        event_id: 'evt-1', mode: 'paper', updated_at: updatedAt,
        analysis: {
            n_positions: 2, ignored_orders: 0,
            summary: { worst, best: 12.25, mean: 1.1, worst_scoreline: [1, 1], best_scoreline: [0, 0], n_scorelines: 4 },
            grid: [[0, 0, 12.25], [1, 1, worst]],
            suggestion: {
                actionable: false, scoreline: null, side: null, odds: null, size: null,
                new_worst: worst, new_best: 12.25, note: 'nessuna copertura migliora il peggiore',
            },
        },
        ...over,
    };
}
function messaggio(r: XhedgeRow, seq = 1): Record<string, unknown> {
    return { id: 41, ...r, fonte: 'canale', _seq: seq, _pubblicato_ms: Date.parse(r.updated_at) + 3 };
}

const T0 = '2026-09-25T13:00:00.100000+00:00';
const T1 = '2026-09-25T13:00:05.200000+00:00';

beforeEach(() => {
    vi.clearAllMocks();
    iscritti.clear();
});
afterEach(() => cleanup());

describe('lib/xhedgeCanale - modulo puro', () => {
    it('valida il messaggio vero; busta assente o modo sconosciuto: null', () => {
        expect(leggiPushXhedge(messaggio(riga(T1, -3)))?.analysis.summary?.worst).toBe(-3);
        expect(leggiPushXhedge(riga(T1, -3))).toBeNull();                       // senza busta
        expect(leggiPushXhedge(messaggio(riga(T1, -3, { mode: 'off' as never })))).toBeNull();
    });
    it('mai unione: una riga che il database non ha non entra', () => {
        const p = leggiPushXhedge(messaggio(riga(T1, -3)))!;
        const vuota = new Map();
        expect(applicaPushXhedge(vuota, [], p, 1)).toBe(vuota);
    });
    it('vince solo un updated_at piu\' recente; al blocco nuovo si pota', () => {
        const db = [riga(T0, -8.5)];
        const nuova = leggiPushXhedge(messaggio(riga(T1, -3)))!;
        const vecchia = leggiPushXhedge(messaggio(riga(T0, -1)))!;
        const vuota = new Map();
        expect(applicaPushXhedge(vuota, db, vecchia, 1)).toBe(vuota);
        const s = applicaPushXhedge(vuota, db, nuova, 1);
        expect(vistaXhedge(db, s)[0].analysis.summary?.worst).toBe(-3);
        // il database raggiunge il canale: la sovrapposizione cade
        const dbNuovo = [riga(T1, -3)];
        expect(potaXhedge(s, dbNuovo).size).toBe(0);
        // canale muto: stesso array del database
        expect(vistaXhedge(db, new Map())).toBe(db);
    });
});

describe('XHedgePanel - canale 47331 sul poll', () => {
    it('una riga piu\' recente dal canale sostituisce quella del poll, fonte dichiarata', async () => {
        mFetch.mockResolvedValue([riga(T0, -8.5)]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByTestId('xhedge-fonte').textContent).toMatch(/fonte db/));
        expect(screen.getAllByText(/\u2212\u20ac8\.50/).length).toBeGreaterThan(0);
        act(() => spingi('betfair_live_xhedge', messaggio(riga(T1, -3))));
        await waitFor(() => expect(screen.getByTestId('xhedge-fonte').textContent).toMatch(/fonte canale/));
        expect(screen.getAllByText(/\u2212\u20ac3\.00/).length).toBeGreaterThan(0);
        // il poll e' spento (pollMs 0): nessuna lettura in piu'
        expect(mFetch).toHaveBeenCalledTimes(1);
    });

    it('riga di un altro evento o di un evento che il poll non ha: ignorata', async () => {
        mFetch.mockResolvedValue([riga(T0, -8.5)]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByTestId('xhedge-fonte')).toBeTruthy());
        act(() => spingi('betfair_live_xhedge', messaggio(riga(T1, -3, { event_id: 'evt-2' }))));
        act(() => spingi('betfair_live_xhedge', messaggio(riga(T1, -2, { mode: 'live' }))));
        await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
        expect(screen.getByTestId('xhedge-fonte').textContent).toMatch(/fonte db/);
        expect(screen.getAllByText(/\u2212\u20ac8\.50/).length).toBeGreaterThan(0);
    });

    it('mai unione: con il poll vuoto il canale non fa comparire un\'analisi', async () => {
        mFetch.mockResolvedValue([]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText(/Nessuna analisi x-hedge/)).toBeTruthy());
        act(() => spingi('betfair_live_xhedge', messaggio(riga(T1, -3))));
        await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
        expect(screen.getByText(/Nessuna analisi x-hedge/)).toBeTruthy();
        expect(screen.queryByTestId('xhedge-fonte')).toBeNull();
    });
});
