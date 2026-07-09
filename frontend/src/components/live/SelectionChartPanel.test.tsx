// Test COMPONENTE per SelectionChartPanel (jsdom + React Testing Library).
// Mocka SOLO '@/lib/live' (pattern di LadderView.test.tsx): fetchLiveLadder →
// fixture con 2 selezioni, subscribeLiveLadder → cattura la callback e ritorna
// una spy di unsubscribe. La matematica (lib/ladderChart) resta REALE, così le
// candele sono calcolate come in produzione.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/live', () => ({
    fetchLiveLadder: vi.fn(),
    subscribeLiveLadder: vi.fn(() => () => {}),
}));

import { SelectionChartPanel } from './SelectionChartPanel';
import { fetchLiveLadder, subscribeLiveLadder, type LiveLadderRow } from '@/lib/live';

const mFetch = vi.mocked(fetchLiveLadder);
const mSub = vi.mocked(subscribeLiveLadder);

// base allineata all'inizio di un bucket da 15s (default del pannello).
const T0 = 1_700_000_010_000 - (1_700_000_010_000 % 15_000);

// fixture: riga ladder con 2 selezioni, ltp/tv parametrici (tv = cumulato EUR).
function ladderRow(updatedMs: number, ltps: [number, number], tvs: [number, number]): LiveLadderRow {
    return {
        event_id: 'evt1',
        market_id: '1.234',
        market_type: 'MATCH_ODDS',
        market_name: 'Match Odds',
        status: 'OPEN',
        ladder: {
            updated_ms: updatedMs,
            selections: [
                {
                    selection_id: 1, name: 'Casa', ltp: ltps[0], tv: tvs[0],
                    back: [[ltps[0] - 0.02, 10]] as [number, number][],
                    lay: [[ltps[0], 20]] as [number, number][],
                    trd: [] as [number, number][],
                    wom: { back_pct: 50, lay_pct: 50 },
                },
                {
                    selection_id: 2, name: 'Ospite', ltp: ltps[1], tv: tvs[1],
                    back: [[ltps[1] - 0.02, 10]] as [number, number][],
                    lay: [[ltps[1], 20]] as [number, number][],
                    trd: [] as [number, number][],
                    wom: { back_pct: 50, lay_pct: 50 },
                },
            ],
        },
        updated_at: new Date(updatedMs).toISOString(),
    };
}

// cattura della callback realtime + spy di unsubscribe.
let subCb: ((row: LiveLadderRow | null) => void) | null = null;
const unsubSpy = vi.fn();

beforeEach(() => {
    vi.clearAllMocks();
    subCb = null;
    mFetch.mockResolvedValue(ladderRow(T0, [3.0, 1.5], [100, 50]));
    mSub.mockImplementation((_marketId, cb) => {
        subCb = cb;
        return unsubSpy;
    });
});

// spinge N update realtime (updated_ms crescenti su più bucket, ltp variati)
// così bucketCandlesV produce almeno 3 candele con la selezione di default.
async function pushUpdates() {
    const updates: Array<[number, [number, number], [number, number]]> = [
        [T0 + 2_000, [3.05, 1.48], [120, 55]],
        [T0 + 6_000, [3.10, 1.47], [150, 60]],
        [T0 + 16_000, [2.95, 1.52], [180, 70]],   // 2° bucket da 15s
        [T0 + 22_000, [3.00, 1.50], [210, 80]],
        [T0 + 31_000, [3.20, 1.45], [260, 95]],   // 3° bucket
    ];
    for (const [t, ltps, tvs] of updates) {
        await act(async () => {
            subCb?.(ladderRow(t, ltps, tvs));
        });
    }
}

describe('SelectionChartPanel', () => {
    it('renderizza le selezioni del ladder nel select (default: la prima)', async () => {
        render(<SelectionChartPanel marketId="1.234" />);
        const select = await screen.findByRole('combobox');
        await waitFor(() => {
            expect(screen.getByRole('option', { name: 'Casa' })).toBeInTheDocument();
            expect(screen.getByRole('option', { name: 'Ospite' })).toBeInTheDocument();
        });
        expect((select as HTMLSelectElement).value).toBe('1'); // default = prima selezione
    });

    it('con meno di 2 candele mostra il placeholder onesto', async () => {
        render(<SelectionChartPanel marketId="1.234" />);
        await waitFor(() => expect(mFetch).toHaveBeenCalled());
        expect(await screen.findByText(/raccolgo prezzi/i)).toBeInTheDocument();
        // nessuna candela renderizzata
        expect(document.querySelectorAll('svg rect')).toHaveLength(0);
    });

    it('gli update realtime su più bucket fanno comparire le candele (svg rect)', async () => {
        const { container } = render(<SelectionChartPanel marketId="1.234" />);
        await waitFor(() => expect(mSub).toHaveBeenCalled());
        await pushUpdates();
        await waitFor(() => {
            // corpi candela + barre volume: con 3 bucket ≥ 3 rect
            expect(container.querySelectorAll('svg rect').length).toBeGreaterThanOrEqual(3);
        });
        expect(screen.queryByText(/raccolgo prezzi/i)).not.toBeInTheDocument();
    });

    it('chiama la unsubscribe allo smontaggio', async () => {
        const { unmount } = render(<SelectionChartPanel marketId="1.234" />);
        await waitFor(() => expect(mSub).toHaveBeenCalled());
        unmount();
        expect(unsubSpy).toHaveBeenCalledTimes(1);
    });

    it('il cambio timeframe non crasha e ri-bucketizza', async () => {
        const user = userEvent.setup();
        const { container } = render(<SelectionChartPanel marketId="1.234" />);
        await waitFor(() => expect(mSub).toHaveBeenCalled());
        await pushUpdates();
        await user.click(screen.getByRole('button', { name: '5s' }));
        await waitFor(() => {
            expect(container.querySelectorAll('svg rect').length).toBeGreaterThanOrEqual(3);
        });
        // a 5m tutti i campioni finiscono in 1 bucket → torna il placeholder (onesto)
        await user.click(screen.getByRole('button', { name: '5m' }));
        expect(await screen.findByText(/raccolgo prezzi/i)).toBeInTheDocument();
    });
});
