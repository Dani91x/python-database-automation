// ADVERSARIAL certification tests for tier2_micro.ts.
// Goal: do NOT trust the reported `profit`. Re-derive the FULL two-leg greening
// lock from Betfair settlement primitives and assert the reported profit is
// actually realized — and EQUAL — on BOTH outcomes, net of commission.
import { describe, it, expect } from 'vitest';
import { backPnl, layPnl } from '@/lib/replay-pnl';
import type { LadderEntry } from '@/lib/live';
import type { MarketLite, MarketState, OppConfig, Snapshot } from './types';
import {
    orderFlowImbalance,
    weightOfMoney,
    makeMomentumPressure,
    makeValueVsModel,
    spreadScalp,
    tickUp,
    tickDown,
    ticksBetween,
    TARGET_TICKS,
    SCALP_TICKS,
} from './tier2_micro';

const CFG: OppConfig = { stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 };

function entry(back: [number, number][], lay: [number, number][], tv = 0): LadderEntry {
    return { back, lay, ltp: null, tv };
}
function snap(markets: MarketLite[], state: Record<string, MarketState>, minute: number | null = 30): Snapshot {
    return { ts: 't', minute, scoreHome: 0, scoreAway: 0, markets, state };
}
function mo(selId: number, name: string, sp: number) {
    return { selection_id: selId, name, sort_priority: sp };
}

// Independent settlement of a greening lock from the ENTRY leg + a target price.
// Returns {win, lose} net-of-commission P&L on the two market outcomes.
function settleLock(
    side: 'back' | 'lay',
    entryPx: number,
    matched: number,
    target: number,
    commission: number,
): { win: number; lose: number } {
    const net = (g: number) => (g > 0 ? g * (1 - commission) : g);
    if (side === 'back') {
        const layStake = (matched * entryPx) / target; // L = S*B/T
        const win = backPnl(matched, entryPx, true) + layPnl(layStake, target, true);
        const lose = backPnl(matched, entryPx, false) + layPnl(layStake, target, false);
        return { win: net(win), lose: net(lose) };
    }
    const backStake = (matched * entryPx) / target; // X = S*L/T
    const win = layPnl(matched, entryPx, true) + backPnl(backStake, target, true);
    const lose = layPnl(matched, entryPx, false) + backPnl(backStake, target, false);
    return { win: net(win), lose: net(lose) };
}

describe('ADVERSARIAL: greening lock realized equally on BOTH outcomes', () => {
    const M: MarketLite = {
        market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'MO',
        selections: [mo(1, 'Team A', 1)],
    };

    it('orderFlowImbalance BACK: reported profit == settled P&L on win AND lose', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.04, 80]], [[2.06, 20]]) } },
        };
        const o = orderFlowImbalance(snap([M], st), CFG)[0];
        const target = tickDown(o.legs[0].price, TARGET_TICKS)!;
        const { win, lose } = settleLock('back', o.legs[0].price, o.legs[0].matchedStake, target, CFG.commission);
        expect(win).toBeCloseTo(o.profit, 9);
        expect(lose).toBeCloseTo(o.profit, 9);
        expect(win).toBeCloseTo(lose, 9); // truly locked
    });

    it('orderFlowImbalance LAY: reported profit == settled P&L on win AND lose', () => {
        // lay-heavy: back 20 / lay 80 → I=-0.6 → LAY signal, entry bestLay.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.98, 20]], [[3.0, 80]]) } },
        };
        const o = orderFlowImbalance(snap([M], st), CFG)[0];
        expect(o.legs[0].side).toBe('lay');
        const target = tickUp(o.legs[0].price, TARGET_TICKS)!;
        const { win, lose } = settleLock('lay', o.legs[0].price, o.legs[0].matchedStake, target, CFG.commission);
        expect(win).toBeCloseTo(o.profit, 9);
        expect(lose).toBeCloseTo(o.profit, 9);
    });

    it('spreadScalp BACK 1-tick: reported profit == settled lock on both outcomes', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.0, 200]], [[2.02, 60]]) } },
        };
        const o = spreadScalp(snap([M], st), CFG)[0];
        const target = tickDown(o.legs[0].price, SCALP_TICKS)!;
        const { win, lose } = settleLock('back', o.legs[0].price, o.legs[0].matchedStake, target, CFG.commission);
        expect(win).toBeCloseTo(o.profit, 9);
        expect(lose).toBeCloseTo(o.profit, 9);
    });

    it('momentumPressure LAY Draw: reported profit == settled lock on both outcomes', () => {
        const MO: MarketLite = {
            market_id: 'mmo', market_type: 'MATCH_ODDS', market_name: 'MO',
            selections: [mo(21, 'A', 1), mo(22, 'B', 2), mo(23, 'The Draw', 3)],
        };
        const st: Record<string, MarketState> = {
            mmo: { market_id: 'mmo', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '23': entry([[2.98, 50]], [[3.0, 100]]) } },
        };
        const det = makeMomentumPressure(() => ({ pressure: 0.7, rising: true }));
        const o = det(snap([MO], st, 60), CFG).find((x) => x.id.startsWith('mom:draw'))!;
        const target = tickUp(o.legs[0].price, TARGET_TICKS)!;
        const { win, lose } = settleLock('lay', o.legs[0].price, o.legs[0].matchedStake, target, CFG.commission);
        expect(win).toBeCloseTo(o.profit, 9);
        expect(lose).toBeCloseTo(o.profit, 9);
    });
});

describe('ADVERSARIAL: valueVsModel LAY branch (untested in suite)', () => {
    const M: MarketLite = {
        market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'MO',
        selections: [mo(1, 'Team A', 1)],
    };
    it('fires on a +EV LAY and EV matches hand derivation', () => {
        // p=0.30, oLay=1.5: layEdge=(0.7)*0.95 - 0.3*0.5 = 0.665-0.15 = 0.515.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[1.45, 100]], [[1.5, 100]]) } },
        };
        const det = makeValueVsModel(() => 0.3);
        const o = det(snap([M], st), CFG)[0];
        expect(o.legs[0].side).toBe('lay');
        expect(o.legs[0].price).toBe(1.5);
        expect(o.profit).toBeCloseTo(51.5, 9); // 0.515*100
        expect(o.profitPct).toBeCloseTo(51.5, 9);
    });

    it('EV sign check: independent Monte-Carlo-free expectation equals reported', () => {
        // Verify layEdge formula against backPnl/layPnl expectation directly.
        const p = 0.3, O = 1.5, c = 0.05, S = 100;
        const net = (g: number) => (g > 0 ? g * (1 - c) : g);
        // selection wins prob p; lose prob (1-p). Lay: win=loss, lose=gain.
        const evLay = p * net(layPnl(S, O, true)) + (1 - p) * net(layPnl(S, O, false));
        expect(evLay).toBeCloseTo(51.5, 9);
    });
});

describe('ADVERSARIAL: tick ladder band-boundary stress', () => {
    it('downtick at every band lower edge uses the LOWER band step', () => {
        expect(tickDown(2.0, 1)).toBe(1.99);  // 0.01
        expect(tickDown(3.0, 1)).toBe(2.98);  // 0.02
        expect(tickDown(4.0, 1)).toBe(3.95);  // 0.05
        expect(tickDown(6.0, 1)).toBe(5.9);   // 0.1
        expect(tickDown(10.0, 1)).toBe(9.8);  // 0.2
    });
    it('uptick at every band lower edge uses the upper band step', () => {
        expect(tickUp(2.0, 1)).toBe(2.02);
        expect(tickUp(3.0, 1)).toBe(3.05);
        expect(tickUp(4.0, 1)).toBe(4.1);
        expect(tickUp(6.0, 1)).toBe(6.2);
    });
    it('ticksBetween returns null for non-ladder high (2.01 invalid)', () => {
        expect(ticksBetween(2.0, 2.01)).toBeNull();
    });
    it('ticksBetween spans a band boundary correctly (2.98→3.05 = 2)', () => {
        expect(ticksBetween(2.98, 3.05)).toBe(2);
    });
});

describe('ADVERSARIAL: matchedStake aggregates multiple qualifying levels', () => {
    const M: MarketLite = {
        market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'MO',
        selections: [mo(1, 'Team A', 1)],
    };
    it('OFI back at lower bestBack aggregates deeper >= price levels for fill', () => {
        // bestBack 2.04 with two levels >= 2.04 (2.06 also qualifies as it is a
        // better back price). matched should sum 30+40=70 (capped 100).
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.04, 30], [2.06, 40]], [[2.1, 5]]) } },
        };
        const o = orderFlowImbalance(snap([M], st), CFG)[0];
        // back-heavy (70 vs 5) → I large → fires. matched = 70.
        expect(o.legs[0].matchedStake).toBe(70);
    });
});

describe('ADVERSARIAL: momentumPressure missing Over/Draw selection', () => {
    it('OVER_UNDER with no Over selection yields no opp', () => {
        const OU: MarketLite = {
            market_id: 'mou', market_type: 'OVER_UNDER_25', market_name: 'OU',
            selections: [mo(11, 'Under 2.5', 2)],
        };
        const st: Record<string, MarketState> = {
            mou: { market_id: 'mou', market_type: 'OVER_UNDER_25', status: 'OPEN',
                ladder: { '11': entry([[2.0, 100]], [[2.02, 50]]) } },
        };
        const det = makeMomentumPressure(() => ({ pressure: 0.9, rising: true }));
        expect(det(snap([OU], st, 60), CFG)).toEqual([]);
    });
});
