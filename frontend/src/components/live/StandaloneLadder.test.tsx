// Test COMPONENTE per StandaloneLadder (fix audit #22): il DELETE della riga
// live_now (callback null) deve DEGRADARE la modalità a 'off' (sola lettura),
// mai mantenere l'ultimo order_mode visto (un LIVE fantasma dopo la sparizione
// dello stato sarebbe una modalità operativa non più autorizzata dal runner).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';

vi.mock('@/lib/live', () => ({
    fetchLiveNow: vi.fn(),
    subscribeLiveNow: vi.fn(() => () => {}),
}));
// il ladder vero non serve: catturiamo SOLO la modalità che riceve.
vi.mock('./LadderView', () => ({
    default: (props: { orderMode?: string }) => (
        <div data-testid="ladder" data-mode={props.orderMode} />
    ),
}));
// il ramo tennis non è sotto test (workstream separato): mock inerte.
vi.mock('@/components/tennis/TennisLadderColumn', () => ({
    TennisLadderColumn: () => null,
}));

import { StandaloneLadder } from './StandaloneLadder';
import { fetchLiveNow, subscribeLiveNow } from '@/lib/live';

const mFetch = vi.mocked(fetchLiveNow);
const mSub = vi.mocked(subscribeLiveNow);

const NOW_ROW = {
    event_id: 'evt1', inplay: true, minute: 10, score_home: 0, score_away: 0,
    status: 'LIVE', score_source: null,
    state: { order_mode: 'paper', markets: [] },
    updated_at: new Date().toISOString(),
} as never;

beforeEach(() => {
    vi.clearAllMocks();
    mFetch.mockResolvedValue(NOW_ROW);
});

describe('StandaloneLadder — fix audit #22', () => {
    it('DELETE di live_now (callback null) → la modalità degrada a off', async () => {
        let cb: ((r: unknown) => void) | undefined;
        mSub.mockImplementation(((_id: string, c: (r: unknown) => void) => {
            cb = c;
            return () => {};
        }) as never);
        render(<StandaloneLadder slot={{ sport: 'calcio', eventId: 'evt1', marketId: '1.234', marketName: 'MO', eventName: 'A-B' }} />);
        // dallo snapshot iniziale la modalità è paper.
        expect((await screen.findByTestId('ladder')).dataset.mode).toBe('paper');
        // la riga sparisce (DELETE) → il callback riceve null → fail-safe 'off'.
        act(() => { cb?.(null); });
        expect(screen.getByTestId('ladder').dataset.mode).toBe('off');
    });
});
