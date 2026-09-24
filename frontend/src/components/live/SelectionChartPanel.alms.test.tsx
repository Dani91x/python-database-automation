// ============================================================================
// SelectionChartPanel.alms.test.tsx - fix B33 punto 1 (24/09): il pannello
// Chart era rimasto sulla "vecchia via" (fetchLiveLadder/subscribeLiveLadder
// diretti, DB sempre) in SeguiLive.tsx (calcio) e TennisTerminal.tsx (tennis,
// TENNIS_LADDER_SOURCE). Ora entrambe le pagine iniettano sorgenteLadderAlMs:
// canale locale al ms come via principale, DB come ripiego SOLO a canale
// assente/muto, e l'indicatore "Aggiornato: HH:MM:SS (canale|DB)" dichiarato
// (stesso pattern di LadderView, vedi ladderAlMs.view.test.tsx).
//
// Qui si prova il PANNELLO con una sorgente "al ms" iniettata via dependency
// injection (creaSorgenteLadderAlMs con un CanaleLadder finto in-memory: nessun
// WebSocket vero, nessuna rete). Falsificato: senza `ladderSource` il pannello
// userebbe il default DB (fetchLiveLadder/subscribeLiveLadder mockati vuoti)
// e non vedrebbe MAI la riga del canale.
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';

vi.mock('@/lib/live', () => ({
    fetchLiveLadder: vi.fn(),
    subscribeLiveLadder: vi.fn(() => () => {}),
}));

import { SelectionChartPanel } from './SelectionChartPanel';
import type { LadderSource } from './LadderView';
import { fetchLiveLadder, subscribeLiveLadder, type LiveLadderRow } from '@/lib/live';
import { sorgenteLadderAlMs, __resetLocalTransport } from '@/lib/localTransport';

const mDbFetch = vi.mocked(fetchLiveLadder);
const mDbSub = vi.mocked(subscribeLiveLadder);

const MID = '1.234';

// canale finto in-memory: nessun WebSocket, stessa interfaccia di CanaleLadder
// (getStatus/onStatus/subscribe) di localTransport.ts.
class CanaleFinto {
    private stato: 'connected' | 'off' = 'off';
    private topic = new Map<string, Set<(d: unknown) => void>>();
    private statusSub = new Set<(s: 'connected' | 'off') => void>();
    getStatus(): 'connected' | 'off' { return this.stato; }
    onStatus(cb: (s: 'connected' | 'off') => void): () => void {
        this.statusSub.add(cb);
        return () => this.statusSub.delete(cb);
    }
    subscribe(topic: string, cb: (d: unknown) => void): () => void {
        const set = this.topic.get(topic) ?? new Set();
        this.topic.set(topic, set);
        set.add(cb);
        return () => set.delete(cb);
    }
    connetti(): void { this.stato = 'connected'; this.statusSub.forEach(f => f('connected')); }
    spegni(): void { this.stato = 'off'; this.statusSub.forEach(f => f('off')); }
    pubblica(topic: string, d: unknown): void {
        (this.topic.get(topic) ?? new Set()).forEach(f => f(d));
    }
}

function rigaCanale(updatedMs: number, ltp: number): unknown {
    return {
        event_id: 'evt1', market_id: MID, market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        status: 'OPEN',
        ladder: {
            updated_ms: updatedMs,
            selections: [
                { selection_id: 1, name: 'Casa', ltp, tv: 1000,
                    back: [[ltp - 0.02, 10]], lay: [[ltp, 20]], trd: [], wom: { back_pct: 50, lay_pct: 50 } },
                { selection_id: 2, name: 'Ospite', ltp: 1.5, tv: 500,
                    back: [[1.48, 10]], lay: [[1.5, 20]], trd: [], wom: { back_pct: 50, lay_pct: 50 } },
            ],
        },
    };
}

let ora = 1_000_000;
const adesso = () => ora;

beforeEach(() => {
    vi.clearAllMocks();
    ora = 1_000_000;
    mDbFetch.mockResolvedValue(null);
    mDbSub.mockImplementation(() => () => {});
});
afterEach(() => {
    __resetLocalTransport();
});

describe('SelectionChartPanel con sorgenteLadderAlMs (fix B33 punto 1)', () => {
    it('mostra "Aggiornato ... (canale)" quando il canale pubblica, non il DB (mai chiamato)', async () => {
        const canale = new CanaleFinto();
        const db: LadderSource = { fetch: mDbFetch, subscribe: mDbSub };
        const source = sorgenteLadderAlMs('calcio', { canale, db, adesso });

        canale.connetti();
        render(<SelectionChartPanel marketId={MID} ladderSource={source} />);
        act(() => { canale.pubblica('ladder', rigaCanale(1_758_621_600_000, 3.1)); });

        // connesso ma senza push al montaggio = muto: il DB si apre come ripiego
        // (stesso comportamento di ladderAlMs.view.test.tsx) e si chiude non
        // appena il canale parla -- qui si prova che vince il canale, non il DB.
        expect(await screen.findByText(/Aggiornato: .*\(canale\)/)).toBeInTheDocument();
    });

    it('canale assente: legge il DB e dichiara la fonte "(DB)"', async () => {
        const canale = new CanaleFinto(); // resta 'off': mai connesso
        const rigaDb: LiveLadderRow = {
            event_id: 'evt1', market_id: MID, market_type: 'MATCH_ODDS', market_name: 'Match Odds',
            status: 'OPEN',
            ladder: {
                updated_ms: 1_758_621_600_000,
                selections: [
                    { selection_id: 1, name: 'Casa', ltp: 2.9, tv: 1000,
                        back: [[2.88, 10]], lay: [[2.9, 20]], trd: [], wom: { back_pct: 50, lay_pct: 50 } },
                    { selection_id: 2, name: 'Ospite', ltp: 1.5, tv: 500,
                        back: [[1.48, 10]], lay: [[1.5, 20]], trd: [], wom: { back_pct: 50, lay_pct: 50 } },
                ],
            },
            updated_at: new Date(1_758_621_600_000).toISOString(),
        };
        mDbFetch.mockResolvedValue(rigaDb);
        const db: LadderSource = { fetch: mDbFetch, subscribe: mDbSub };
        const source = sorgenteLadderAlMs('calcio', { canale, db, adesso });

        render(<SelectionChartPanel marketId={MID} ladderSource={source} />);

        expect(await screen.findByText(/Aggiornato: .*\(DB\)/)).toBeInTheDocument();
        await waitFor(() => expect(mDbSub).toHaveBeenCalled());
    });

    it('FALSIFICAZIONE: senza ladderSource iniettato (default DB) non compare mai "(canale)"', async () => {
        // stesso identico canale, MAI passato al pannello: prova che il default
        // (fetchLiveLadder/subscribeLiveLadder mockati vuoti) non vede la riga.
        render(<SelectionChartPanel marketId={MID} />);
        await waitFor(() => expect(mDbFetch).toHaveBeenCalled());
        expect(screen.queryByText(/\(canale\)/)).not.toBeInTheDocument();
        // nessun indicatore "Aggiornato" del tutto: fetch/subscribe di default
        // ritornano null/nessuna riga, quindi updated_ms resta assente.
        expect(screen.queryByText(/Aggiornato:/)).not.toBeInTheDocument();
    });
});
