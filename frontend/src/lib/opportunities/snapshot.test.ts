import { describe, it, expect } from 'vitest';
import { buildSnapshots } from './snapshot';
import type { ReplayData, Frame, LadderEntry } from '@/lib/live';

function entry(ltp: number): LadderEntry {
    return { back: [[ltp, 100]], lay: [[ltp + 0.02, 100]], ltp, tv: 0 };
}

// ts base: 2026-01-01T00:00:00Z = 0 reference; useremo offset secondi.
const T0 = '2026-01-01T00:00:00.000Z';
const T15 = '2026-01-01T00:00:15.000Z';
const T20 = '2026-01-01T00:00:20.000Z';

function frame(ts: string, ladderLtp: number, minute: number): Frame {
    const ladder = { '1': entry(ladderLtp) };
    return { market_id: 'm1', ts, minute, inplay: true, status: 'OPEN', ladder };
}

const replay: ReplayData = {
    event: {
        event_id: 'e1', fixture_id: null, league_name: null,
        home_name: 'A', away_name: 'B', open_date: T0, status: 'OPEN',
    },
    markets: [
        {
            market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
            sort_priority: 1,
            selections: [
                { selection_id: 1, name: 'Team A', sort_priority: 1 },
                { selection_id: 2, name: 'Team B', sort_priority: 2 },
                { selection_id: 3, name: 'The Draw', sort_priority: 3 },
            ],
        },
    ],
    frames: [
        frame(T0, 2.0, 1),
        frame(T15, 1.5, 16),
    ],
    score_timeline: [
        { ts: T0, minute: 1, score_home: 0, score_away: 0, event_type: null, source: 'x' },
        { ts: T20, minute: 21, score_home: 1, score_away: 0, event_type: 'GOAL', source: 'x' },
    ],
};

describe('buildSnapshots', () => {
    const snaps = buildSnapshots(replay, 10000);

    it('produces one snapshot per 10s bucket from t0 to tEnd (0,10,20s → 3)', () => {
        expect(snaps.length).toBe(3);
    });

    it('bucket 0: carries the first frame (ltp 2.0), score 0-0', () => {
        const s = snaps[0];
        expect(s.state['m1'].ladder['1'].ltp).toBe(2.0);
        expect(s.scoreHome).toBe(0);
        expect(s.scoreAway).toBe(0);
    });

    it('bucket 10s: carry-forward still first frame (frame@15s not yet), score 0-0', () => {
        const s = snaps[1];
        expect(s.state['m1'].ladder['1'].ltp).toBe(2.0);
        expect(s.scoreHome).toBe(0);
    });

    it('bucket 20s: latest frame is frame@15s (ltp 1.5), score 1-0 (goal@20s)', () => {
        const s = snaps[2];
        expect(s.state['m1'].ladder['1'].ltp).toBe(1.5);
        expect(s.scoreHome).toBe(1);
        expect(s.scoreAway).toBe(0);
    });

    it('includes the full markets list in every snapshot', () => {
        expect(snaps[0].markets.length).toBe(1);
        expect(snaps[0].markets[0].market_id).toBe('m1');
        expect(snaps[0].markets[0].selections.length).toBe(3);
    });

    it('carries the latest frame minute', () => {
        expect(snaps[2].minute).toBe(16);
    });

    it('returns [] for empty replay', () => {
        const empty: ReplayData = { ...replay, frames: [], score_timeline: [] };
        expect(buildSnapshots(empty, 10000)).toEqual([]);
    });
});
