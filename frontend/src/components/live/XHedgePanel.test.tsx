// Test COMPONENTE per XHedgePanel (jsdom + React Testing Library).
// @/lib/liveOrders è mockato: fetchXhedge NON tocca la rete. Il pannello è di sola
// lettura (nessun ordine), quindi verifichiamo rendering di riepilogo, matrice e
// suggerimento + la nota "piazza manualmente".
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import type { XhedgeRow } from '@/lib/liveOrders';

vi.mock('@/lib/liveOrders', () => ({
    fetchXhedge: vi.fn(),
}));

import { XHedgePanel } from './XHedgePanel';
import { fetchXhedge } from '@/lib/liveOrders';

const mFetch = vi.mocked(fetchXhedge);

function makeRow(overrides: Partial<XhedgeRow> = {}, mode: 'paper' | 'live' = 'paper'): XhedgeRow {
    return {
        event_id: 'evt-1',
        mode,
        updated_at: '2026-07-01T12:00:00Z',
        analysis: {
            n_positions: 3,
            summary: {
                worst: -8.5,
                best: 12.25,
                mean: 1.1,
                worst_scoreline: [2, 1],
                best_scoreline: [0, 0],
                n_scorelines: 9,
            },
            grid: [
                [0, 0, 12.25],
                [1, 0, 3.5],
                [0, 1, -2.0],
                [1, 1, -8.5],
                [2, 1, -8.5],
            ],
            suggestion: {
                actionable: true,
                scoreline: [1, 1],
                side: 'back',
                odds: 7.4,
                size: 5,
                new_worst: -3.2,
                new_best: 9.1,
                note: 'copre il caso peggiore 1-1',
            },
        },
        ...overrides,
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    mFetch.mockResolvedValue([makeRow()]);
});

afterEach(() => {
    cleanup();
});

describe('XHedgePanel', () => {
    it('mostra il riepilogo cross-market (worst/mean/best + scoreline)', async () => {
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        expect(mFetch).toHaveBeenCalledWith('evt-1');
        // worst appare nel riepilogo E nel suggerimento (worst→new_worst)
        await waitFor(() => expect(screen.getAllByText('−€8.50').length).toBeGreaterThanOrEqual(1));
        expect(screen.getByText('€12.25')).toBeInTheDocument();
        expect(screen.getByText('€1.10')).toBeInTheDocument();
        // scoreline peggiore 2-1 e migliore 0-0
        expect(screen.getByText('2-1')).toBeInTheDocument();
        expect(screen.getByText('0-0')).toBeInTheDocument();
    });

    it('renderizza la matrice P&L con le celle della griglia', async () => {
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByLabelText(/Matrice P&L/i)).toBeInTheDocument());
        // valore di una cella (0-0 = 12.25)
        expect(screen.getByText('12.25')).toBeInTheDocument();
        expect(screen.getByText('3.50')).toBeInTheDocument();
    });

    it('mostra il suggerimento BACK Correct Score con worst→new_worst e la nota manuale', async () => {
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText('BACK')).toBeInTheDocument());
        expect(screen.getAllByText(/Correct Score/).length).toBeGreaterThanOrEqual(1);
        // scoreline del suggerimento 1-1 e new_worst
        expect(screen.getByText('1-1')).toBeInTheDocument();
        expect(screen.getByText('−€3.20')).toBeInTheDocument();
        expect(screen.getByText(/Piazza manualmente sul mercato Correct Score/i)).toBeInTheDocument();
    });

    it("mostra sempre la nota 'solo analisi' (nessun ordine piazzato)", async () => {
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        await waitFor(() => expect(screen.getByText(/piazzata/i)).toBeInTheDocument());
        expect(screen.getByText(/non piazza ordini/i)).toBeInTheDocument();
    });

    it("in modalità 'off' mostra comunque l'analisi in sola lettura", async () => {
        render(<XHedgePanel eventId="evt-1" mode="off" pollMs={0} />);
        await waitFor(() => expect(screen.getAllByText('−€8.50').length).toBeGreaterThanOrEqual(1));
        expect(screen.getByText('OFF')).toBeInTheDocument();
    });

    it('preferisce la riga della modalità attiva (live vs paper)', async () => {
        const paperRow = makeRow({ analysis: { ...makeRow().analysis, summary: { ...makeRow().analysis.summary, worst: -1.0 } } }, 'paper');
        const liveRow = makeRow({ analysis: { ...makeRow().analysis, summary: { ...makeRow().analysis.summary, worst: -99.0 } } }, 'live');
        mFetch.mockResolvedValue([paperRow, liveRow]);
        render(<XHedgePanel eventId="evt-1" mode="live" pollMs={0} />);
        await waitFor(() => expect(screen.getAllByText('−€99.00').length).toBeGreaterThanOrEqual(1));
        expect(screen.queryByText('−€1.00')).not.toBeInTheDocument();
    });

    it('gestisce un suggerimento non azionabile', async () => {
        const row = makeRow();
        row.analysis.suggestion = {
            actionable: false, scoreline: null, side: null, odds: null, size: null,
            new_worst: -8.5, new_best: 12.25, note: 'nessuna gamba migliora',
        };
        mFetch.mockResolvedValue([row]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText(/Nessuna copertura utile/i)).toBeInTheDocument());
        expect(screen.queryByText('BACK')).not.toBeInTheDocument();
    });

    it('mostra un messaggio quando non ci sono righe', async () => {
        mFetch.mockResolvedValue([]);
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText(/Nessuna analisi x-hedge disponibile/i)).toBeInTheDocument());
    });

    it('mostra un errore se fetchXhedge rifiuta', async () => {
        mFetch.mockRejectedValue(new Error('boom'));
        render(<XHedgePanel eventId="evt-1" mode="paper" pollMs={0} />);
        await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument());
    });
});
