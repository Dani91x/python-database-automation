// Test del DepthPanel (D31) — depth cumulata + delta flusso onesto.
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { DepthPanel } from './DepthPanel';

vi.mock('@/lib/live', () => ({
    fetchLiveLadder: vi.fn(),
    subscribeLiveLadder: vi.fn(() => () => {}),
}));

import { fetchLiveLadder, subscribeLiveLadder } from '@/lib/live';

const mFetch = vi.mocked(fetchLiveLadder);
const mSub = vi.mocked(subscribeLiveLadder);

function ladderRow(updatedMs: number, backSize: number, laySize: number) {
    return {
        event_id: 'evt1',
        market_id: '1.234',
        market_type: 'MATCH_ODDS',
        market_name: 'Match Odds',
        status: 'OPEN',
        ladder: {
            updated_ms: updatedMs,
            selections: [{
                selection_id: 1,
                name: 'Casa',
                ltp: 3.0,
                tv: 100,
                back: [[2.9, backSize], [2.88, 5]] as [number, number][],
                lay: [[3.0, laySize]] as [number, number][],
                trd: [] as [number, number][],
                wom: { back_pct: 60, lay_pct: 40 },
            }],
        },
        updated_at: new Date().toISOString(),
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    mSub.mockReturnValue(() => {});
});

describe('DepthPanel', () => {
    it('renderizza selezioni, totali per lato e ripartizione book', async () => {
        mFetch.mockResolvedValue(ladderRow(Date.now(), 100, 50) as never);
        render(<DepthPanel marketId="1.234" />);
        expect(await screen.findByText('Casa')).toBeInTheDocument();
        expect(screen.getByText('€105')).toBeInTheDocument();   // back 100+5
        expect(screen.getByText('€50')).toBeInTheDocument();    // lay
        expect(screen.getByText(/book 68% back/)).toBeInTheDocument(); // 105/155
    });

    it('storia insufficiente → delta "—" (mai inventato)', async () => {
        mFetch.mockResolvedValue(ladderRow(Date.now(), 100, 50) as never);
        render(<DepthPanel marketId="1.234" />);
        await screen.findByText('Casa');
        expect(screen.getByText('—')).toBeInTheDocument();
    });

    it('con storia sufficiente mostra il delta per lato', async () => {
        const now = Date.now();
        mFetch.mockResolvedValue(ladderRow(now - 40_000, 100, 50) as never);
        let cb: ((row: unknown) => void) | null = null;
        mSub.mockImplementation((_id: string, fn: never) => {
            cb = fn as (row: unknown) => void;
            return () => {};
        });
        render(<DepthPanel marketId="1.234" />);
        await screen.findByText('Casa');
        // nuovo sample: back 105→160 (+55), lay 50→30 (−20), finestra default 30s
        await act(async () => { cb?.(ladderRow(now, 155, 30)); });
        expect(await screen.findByText(/back \+€55/)).toBeInTheDocument();
        expect(screen.getByText(/lay −€20/)).toBeInTheDocument();
    });

    it('unsubscribe allo smontaggio', async () => {
        const unsub = vi.fn();
        mFetch.mockResolvedValue(ladderRow(Date.now(), 100, 50) as never);
        mSub.mockReturnValue(unsub);
        const { unmount } = render(<DepthPanel marketId="1.234" />);
        await screen.findByText('Casa');
        unmount();
        expect(unsub).toHaveBeenCalled();
    });

    it('book vuoto → messaggio onesto', async () => {
        mFetch.mockResolvedValue({
            ...ladderRow(Date.now(), 0, 0),
            ladder: { updated_ms: Date.now(), selections: [] },
        } as never);
        render(<DepthPanel marketId="1.234" />);
        expect(await screen.findByText('nessun book disponibile')).toBeInTheDocument();
    });
});
