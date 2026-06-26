// ADVERSARIAL counter-examples — certification probes, now asserting the FIXED
// behavior (the flaws flagged by the certification have been corrected).
import { describe, it, expect } from 'vitest';
import type { Snapshot, MarketState, MarketLite, OppConfig, SelLite } from './types';
import { backToLay, layTheFieldCorrectScore } from './tier1_quasi';

const CFG: OppConfig = { stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 };
type Lvl = [number, number][];
type SelLad = Record<number, { back?: Lvl; lay?: Lvl; ltp?: number | null }>;
function mkState(market_id: string, market_type: string, sels: SelLad): MarketState {
    const ladder: Record<string, { back: Lvl; lay: Lvl; ltp: number | null; tv: number | null }> = {};
    for (const [sid, e] of Object.entries(sels)) ladder[sid] = { back: e.back ?? [], lay: e.lay ?? [], ltp: e.ltp ?? null, tv: null };
    return { market_id, market_type, status: 'OPEN', ladder };
}
const MO_SELS: SelLite[] = [
    { selection_id: 1, name: 'Home', sort_priority: 1 },
    { selection_id: 2, name: 'Away', sort_priority: 2 },
    { selection_id: 3, name: 'The Draw', sort_priority: 3 },
];
function snap(over: Partial<Snapshot> = {}): Snapshot {
    return { ts: 't', minute: 30, scoreHome: 0, scoreAway: 0, markets: [], state: {}, ...over };
}

describe('FIXED: backToLay arb profit IS capped by lay-leg liquidity', () => {
    it('thin lay side: reports only the achievable lock (bounded by the binding lay leg)', () => {
        const s = snap({
            markets: [{ market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'MO', selections: MO_SELS }],
            state: { m1: mkState('m1', 'MATCH_ODDS', {
                1: { back: [[3.6, 500]], lay: [[3.4, 10]] }, // crossed but only £10 layable
            }) },
        });
        const o = backToLay([])(s, CFG)[0];
        // Achievable lock is bounded by the binding (lay) leg:
        // b_max = Ql*L/B = 10*3.4/3.6 = 9.444 ; profit = b_max*(B-L)/L*0.95
        const bMax = 10 * 3.4 / 3.6;
        const achievable = bMax * (3.6 - 3.4) / 3.4 * 0.95;
        expect(o.tier).toBe('arb');
        expect(achievable).toBeCloseTo(0.527778, 5);
        // The reported profit now equals the ACHIEVABLE lock, not the optimistic full-back lock.
        expect(o.profit).toBeCloseTo(0.527778, 5);
        // Back leg is resized to the lockable size; lay leg fully matched (£10).
        expect(o.legs[0].matchedStake).toBeCloseTo(9.444444, 5);
        expect(o.legs[1].matchedStake).toBeCloseTo(10, 5);
        // Honest confidence: only ~9.4% of the desired £100 stake is lockable.
        expect(o.confidence).toBeCloseTo(0.094444, 5);
    });

    it('deep lay side: full lock still fires unchanged', () => {
        const s = snap({
            markets: [{ market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'MO', selections: MO_SELS }],
            state: { m1: mkState('m1', 'MATCH_ODDS', {
                1: { back: [[3.6, 500]], lay: [[3.4, 500]] },
            }) },
        });
        const o = backToLay([])(s, CFG)[0];
        expect(o.profit).toBeCloseTo(5.588235, 5);
        expect(o.legs[0].matchedStake).toBeCloseTo(100, 5);
    });
});

describe('FIXED: dutch-lay field uses MATCHED (not desired) stakes for profit', () => {
    it('thin lay liquidity on one pick lowers bestReturn to the achievable figure', () => {
        const fieldLite: MarketLite = {
            market_id: 'm3', market_type: 'CORRECT_SCORE', market_name: 'CS',
            selections: [
                { selection_id: 20, name: '5-0' },
                { selection_id: 21, name: '0-5' },
                { selection_id: 22, name: '6-0' },
            ],
        };
        const s = snap({
            markets: [fieldLite],
            state: { m3: mkState('m3', 'CORRECT_SCORE', {
                20: { lay: [[12, 1]] },  // desired S20=9.09 but only £1 layable
                21: { lay: [[20, 500]] },
                22: { lay: [[50, 500]] },
            }) },
        });
        const o = layTheFieldCorrectScore()(s, CFG)[0];
        // sumEff = 1 + 5.263158 + 2.040816 = 8.303974 ; bestReturn = *0.95 = 7.888775
        expect(o.profit).toBeCloseTo(7.888775, 5);
        expect(o.profit).toBeLessThan(15.575139); // strictly below the full-fill figure
        expect(o.legs[0].matchedStake).toBeCloseTo(1, 6);
    });
});

describe('FIXED: crossed book on DRAW / UNDER IS detected as arb', () => {
    it('Draw crossed book → backToLay now finds the real arbitrage', () => {
        const s = snap({
            markets: [{ market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'MO', selections: MO_SELS }],
            state: { m1: mkState('m1', 'MATCH_ODDS', {
                3: { back: [[3.6, 500]], lay: [[3.4, 500]] }, // DRAW crossed → real arb
            }) },
        });
        const res = backToLay([])(s, CFG);
        expect(res).toHaveLength(1);
        expect(res[0].tier).toBe('arb');
        expect(res[0].legs[0].selectionId).toBe(3); // The Draw
        expect(res[0].profit).toBeCloseTo(5.588235, 5);
    });

    it('Under crossed book → backToLay now finds the real arbitrage', () => {
        const OU_SELS: SelLite[] = [
            { selection_id: 11, name: 'Over 2.5 Goals' },
            { selection_id: 12, name: 'Under 2.5 Goals' },
        ];
        const s = snap({
            markets: [{ market_id: 'ou', market_type: 'OVER_UNDER_25', market_name: 'O/U 2.5', selections: OU_SELS }],
            state: { ou: mkState('ou', 'OVER_UNDER_25', {
                12: { back: [[2.4, 500]], lay: [[2.2, 500]] }, // UNDER crossed
            }) },
        });
        const res = backToLay([])(s, CFG);
        expect(res).toHaveLength(1);
        expect(res[0].tier).toBe('arb');
        expect(res[0].legs[0].selectionId).toBe(12); // Under
    });
});
