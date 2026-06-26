import { describe, it, expect } from 'vitest';
import type { LadderEntry } from '@/lib/live';
import type { MarketLite, MarketState, OppConfig, Snapshot } from './types';
import {
    orderFlowImbalance,
    weightOfMoney,
    makeMomentumPressure,
    momentumPressure,
    makeValueVsModel,
    valueVsModel,
    spreadScalp,
    tickUp,
    tickDown,
    ticksBetween,
    greenBack,
    greenLay,
    phaseOf,
    clamp01,
} from './tier2_micro';

const CFG: OppConfig = { stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 };

// --------------------------------------------------------------- builders
function entry(
    back: [number, number][],
    lay: [number, number][],
    tv = 0,
    ltp: number | null = null,
): LadderEntry {
    return { back, lay, ltp, tv };
}
function snap(
    markets: MarketLite[],
    state: Record<string, MarketState>,
    minute: number | null = 30,
): Snapshot {
    return { ts: '2026-01-01T00:00:00.000Z', minute, scoreHome: 0, scoreAway: 0, markets, state };
}
function mo(selId: number, name: string, sp: number): MarketLite['selections'][number] {
    return { selection_id: selId, name, sort_priority: sp };
}

// ============================================================ tick ladder
describe('tick ladder Betfair', () => {
    it('tickUp respects bands (2.00→2.04 in two 0.02 steps)', () => {
        expect(tickUp(2.0, 2)).toBe(2.04);
    });
    it('tickDown mixes bands at boundary (2.00→1.99→1.98)', () => {
        expect(tickDown(2.0, 2)).toBe(1.98);
    });
    it('tickDown from 2.04 → 2.00 (two 0.02 steps)', () => {
        expect(tickDown(2.04, 2)).toBe(2.0);
    });
    it('tickUp from 3.00 uses 0.05 band (→3.10)', () => {
        expect(tickUp(3.0, 2)).toBe(3.1);
    });
    it('ticksBetween counts 2.00→2.10 as 5 ticks', () => {
        expect(ticksBetween(2.0, 2.1)).toBe(5);
    });
    it('ticksBetween 2.00→2.02 = 1 tick', () => {
        expect(ticksBetween(2.0, 2.02)).toBe(1);
    });
    it('tickDown returns null if it would cross 1.00', () => {
        expect(tickDown(1.01, 2)).toBeNull();
    });
});

// ============================================================ green math
describe('greening math', () => {
    it('greenBack(100,2.04,2.00)=2.0 (and greenBack(80,...)=1.6)', () => {
        expect(greenBack(100, 2.04, 2.0)).toBeCloseTo(2.0, 10);
        expect(greenBack(80, 2.04, 2.0)).toBeCloseTo(1.6, 10);
    });
    it('greenLay(100,3.00,3.10)=10/3.1', () => {
        expect(greenLay(100, 3.0, 3.1)).toBeCloseTo(10 / 3.1, 10);
    });
    it('clamp01 clamps to [0,1]', () => {
        expect(clamp01(-0.2)).toBe(0);
        expect(clamp01(1.5)).toBe(1);
        expect(clamp01(0.3)).toBe(0.3);
    });
});

describe('phaseOf', () => {
    it('maps minutes to pre/1T/2T/late', () => {
        expect(phaseOf(null)).toBe('pre');
        expect(phaseOf(0)).toBe('pre');
        expect(phaseOf(10)).toBe('1T');
        expect(phaseOf(60)).toBe('2T');
        expect(phaseOf(80)).toBe('late');
    });
});

// ============================================================ DETECTOR A
describe('orderFlowImbalance', () => {
    const M: MarketLite = {
        market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        selections: [mo(1, 'Team A', 1)],
    };

    it('FIRES on strong back-heavy imbalance → BACK signal with exact greening', () => {
        // back 80 vs lay 20 → I=0.6. entry bestBack 2.04. matched=80 (cap by liq).
        // target=tickDown(2.04,2)=2.00. gross=80*(0.04)/2.0=1.6 ; net=1.6*0.95=1.52.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.04, 80]], [[2.06, 20]]) } },
        };
        const res = orderFlowImbalance(snap([M], st), CFG);
        expect(res.length).toBe(1);
        const o = res[0];
        expect(o.tier).toBe('directional');
        expect(o.type).toBe('order_flow_imbalance');
        expect(o.legs.length).toBe(1);
        expect(o.legs[0].side).toBe('back');
        expect(o.legs[0].price).toBe(2.04);
        expect(o.legs[0].matchedStake).toBe(80);
        expect(o.profit).toBeCloseTo(1.52, 10);
        expect(o.profitPct).toBeCloseTo(1.9, 10);     // 1.52/80*100
        expect(o.confidence).toBeCloseTo(0.48, 10);   // min(0.8,0.6)*0.8
        expect(o.exitPlan).toContain('2.00');
    });

    it('does NOT fire on a balanced book (I=0)', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.0, 50]], [[2.02, 50]]) } },
        };
        expect(orderFlowImbalance(snap([M], st), CFG)).toEqual([]);
    });

    it('edge: thin liquidity caps matchedStake (30, not 100)', () => {
        // back 30 vs lay 5 → I=25/35≈0.714. matched=30 ; ratio=0.3.
        // gross=30*0.04/2.0=0.6 ; net=0.57.  conf=min(0.8,0.714..)*0.3.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.04, 30]], [[2.06, 5]]) } },
        };
        const o = orderFlowImbalance(snap([M], st), CFG)[0];
        expect(o.legs[0].matchedStake).toBe(30);
        expect(o.profit).toBeCloseTo(0.57, 10);
        expect(o.confidence).toBeCloseTo((25 / 35) * 0.3, 10);
    });

    it('edge: missing prices (empty ladder levels) → no opp', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([], []) } },
        };
        expect(orderFlowImbalance(snap([M], st), CFG)).toEqual([]);
    });

    it('edge: price<=1 entry is rejected', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[1.0, 80]], [[2.0, 20]]) } },
        };
        expect(orderFlowImbalance(snap([M], st), CFG)).toEqual([]);
    });

    it('edge: commission boundary (c=0 → profit equals gross 1.6)', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.04, 80]], [[2.06, 20]]) } },
        };
        const o = orderFlowImbalance(snap([M], st), { ...CFG, commission: 0 })[0];
        expect(o.profit).toBeCloseTo(1.6, 10);
    });
});

// ============================================================ DETECTOR B
describe('weightOfMoney', () => {
    const M: MarketLite = {
        market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        selections: [mo(1, 'Team A', 1)],
    };

    it('FIRES on top-3 steam (WoM=0.5) → BACK with exact greening', () => {
        // backVol=120, layVol=40, liq=160, wom=0.5. tv=80 → steam=min(1,2)=1.
        // entry bestBack 1.90, matched=60 (only top level >=1.90), ratio=0.6.
        // target=tickDown(1.90,2)=1.88. gross=60*0.02/1.88 ; net=*0.95.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry(
                    [[1.9, 60], [1.89, 40], [1.88, 20]],
                    [[1.91, 10], [1.92, 20], [1.93, 10]],
                    80) } },
        };
        const o = weightOfMoney(snap([M], st), CFG)[0];
        expect(o.type).toBe('weight_of_money');
        expect(o.legs[0].side).toBe('back');
        expect(o.legs[0].price).toBe(1.9);
        expect(o.legs[0].matchedStake).toBe(60);
        const gross = (60 * (1.9 - 1.88)) / 1.88;
        expect(o.profit).toBeCloseTo(gross * 0.95, 10);
        expect(o.profitPct).toBeCloseTo((gross * 0.95 / 60) * 100, 10);
        expect(o.confidence).toBeCloseTo(0.5 * 0.6 * 1, 10);
    });

    it('does NOT fire below minimum liquidity (£40 < 100)', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[1.9, 30]], [[1.91, 10]], 80) } },
        };
        expect(weightOfMoney(snap([M], st), CFG)).toEqual([]);
    });

    it('does NOT fire on balanced weight (wom=0)', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[1.9, 60]], [[1.91, 60]], 80) } },
        };
        expect(weightOfMoney(snap([M], st), CFG)).toEqual([]);
    });

    it('steamFactor shrinks confidence when tv >> liquidity', () => {
        // liq=160, tv=320 → steam=min(1,0.5)=0.5 → conf=0.5*0.6*0.5=0.15.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry(
                    [[1.9, 60], [1.89, 40], [1.88, 20]],
                    [[1.91, 10], [1.92, 20], [1.93, 10]],
                    320) } },
        };
        const o = weightOfMoney(snap([M], st), CFG)[0];
        expect(o.confidence).toBeCloseTo(0.5 * 0.6 * 0.5, 10);
    });
});

// ============================================================ DETECTOR C
describe('momentumPressure', () => {
    const OU: MarketLite = {
        market_id: 'mou', market_type: 'OVER_UNDER_25', market_name: 'Over/Under 2.5',
        selections: [mo(10, 'Over 2.5', 1), mo(11, 'Under 2.5', 2)],
    };
    const MO: MarketLite = {
        market_id: 'mmo', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        selections: [mo(21, 'Team A', 1), mo(22, 'Team B', 2), mo(23, 'The Draw', 3)],
    };
    const st: Record<string, MarketState> = {
        mou: { market_id: 'mou', market_type: 'OVER_UNDER_25', status: 'OPEN',
            ladder: { '10': entry([[2.0, 100]], [[2.02, 50]]), '11': entry([[2.0, 100]], [[2.02, 50]]) } },
        mmo: { market_id: 'mmo', market_type: 'MATCH_ODDS', status: 'OPEN',
            ladder: { '23': entry([[2.98, 50]], [[3.0, 100]]) } },
    };
    const S = snap([OU, MO], st, 60);

    it('FIRES with rising pressure: BACK Over + LAY Draw (2 opps, exact)', () => {
        const det = makeMomentumPressure(() => ({ pressure: 0.7, rising: true }));
        const res = det(S, CFG);
        expect(res.length).toBe(2);
        const over = res.find((o) => o.id.startsWith('mom:over'))!;
        const draw = res.find((o) => o.id.startsWith('mom:draw'))!;

        // Over: entry 2.00 back, target tickDown(2.00,2)=1.98, matched 100.
        const grossOver = (100 * (2.0 - 1.98)) / 1.98;
        expect(over.legs[0].side).toBe('back');
        expect(over.profit).toBeCloseTo(grossOver * 0.95, 10);
        expect(over.confidence).toBeCloseTo(0.7, 10); // min(0.75,0.7)*1

        // Draw: entry 3.00 lay, target tickUp(3.00,2)=3.10, matched 100.
        const grossDraw = (100 * (3.1 - 3.0)) / 3.1;
        expect(draw.legs[0].side).toBe('lay');
        expect(draw.profit).toBeCloseTo(grossDraw * 0.95, 10);
        expect(draw.phase).toBe('2T');
    });

    it('does NOT fire when pressure below threshold', () => {
        const det = makeMomentumPressure(() => ({ pressure: 0.5, rising: true }));
        expect(det(S, CFG)).toEqual([]);
    });

    it('does NOT fire when not rising', () => {
        const det = makeMomentumPressure(() => ({ pressure: 0.9, rising: false }));
        expect(det(S, CFG)).toEqual([]);
    });

    it('default detector (no provider) returns []', () => {
        expect(momentumPressure(S, CFG)).toEqual([]);
    });
});

// ============================================================ DETECTOR D
describe('valueVsModel', () => {
    const M: MarketLite = {
        market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        selections: [mo(1, 'Team A', 1)],
    };
    const st: Record<string, MarketState> = {
        m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
            ladder: { '1': entry([[2.5, 100]], [[2.6, 80]]) } },
    };
    const S = snap([M], st);

    it('FIRES on positive back edge (p=0.45) with exact EV', () => {
        // backEdge = 0.45*1.5*0.95 - 0.55 = 0.09125 ; EV = 0.09125*100 = 9.125.
        const det = makeValueVsModel(() => 0.45);
        const o = det(S, CFG)[0];
        expect(o.type).toBe('value_vs_model');
        expect(o.legs[0].side).toBe('back');
        expect(o.legs[0].matchedStake).toBe(100);
        expect(o.profit).toBeCloseTo(9.125, 10);
        expect(o.profitPct).toBeCloseTo(9.125, 10);
        expect(o.confidence).toBeCloseTo(0.09125, 10); // min(0.7,0.09125)*1
    });

    it('does NOT fire when edge below threshold (p=0.40)', () => {
        // backEdge = 0.4*1.5*0.95 - 0.6 = -0.03 ; layEdge = 0.6*0.95 - 0.4*1.6 = -0.07.
        const det = makeValueVsModel(() => 0.4);
        expect(det(S, CFG)).toEqual([]);
    });

    it('default detector (no provider) returns []', () => {
        expect(valueVsModel(S, CFG)).toEqual([]);
    });

    it('ignores invalid model probabilities (null / out of (0,1))', () => {
        expect(makeValueVsModel(() => null)(S, CFG)).toEqual([]);
        expect(makeValueVsModel(() => 0)(S, CFG)).toEqual([]);
        expect(makeValueVsModel(() => 1)(S, CFG)).toEqual([]);
    });
});

// ============================================================ DETECTOR E
describe('spreadScalp', () => {
    const M: MarketLite = {
        market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        selections: [mo(1, 'Team A', 1)],
    };

    it('FIRES on tight spread + imbalance → 1-tick scalp (exact)', () => {
        // bb=2.00(200), bl=2.02(60). spread=1 tick. liq=60. I=140/260≈0.5385.
        // entry 2.00 back, matched 100, target tickDown(2.00,1)=1.99.
        // gross=100*0.01/1.99 ; net=*0.95.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.0, 200]], [[2.02, 60]]) } },
        };
        const o = spreadScalp(snap([M], st), CFG)[0];
        expect(o.type).toBe('spread_scalp');
        expect(o.legs[0].side).toBe('back');
        expect(o.legs[0].price).toBe(2.0);
        expect(o.legs[0].matchedStake).toBe(100);
        const gross = (100 * (2.0 - 1.99)) / 1.99;
        expect(o.profit).toBeCloseTo(gross * 0.95, 10);
        expect(o.confidence).toBeCloseTo((140 / 260) * 1, 10); // min(0.6,0.538)*1
        expect(o.instruction).toContain('fill NON garantito');
    });

    it('does NOT fire when the spread is too wide (5 ticks)', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.0, 200]], [[2.1, 60]]) } },
        };
        expect(spreadScalp(snap([M], st), CFG)).toEqual([]);
    });

    it('does NOT fire when liquidity below minimum (£30 < 50)', () => {
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.0, 30]], [[2.02, 30]]) } },
        };
        expect(spreadScalp(snap([M], st), CFG)).toEqual([]);
    });

    it('edge: thin top-of-book caps matchedStake', () => {
        // bb size 60 → matched=min(60,100)=60. lay 60 too (liq ok). I=0 though → no fire.
        // Make back-heavy: bb 80, bl 55 → I=25/135≈0.185 < 0.3 → no fire.
        const st: Record<string, MarketState> = {
            m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN',
                ladder: { '1': entry([[2.0, 80]], [[2.02, 55]]) } },
        };
        expect(spreadScalp(snap([M], st), CFG)).toEqual([]);
    });
});
