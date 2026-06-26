// ============================================================================
// tier1_quasi.test.ts — test con valori NUMERICI calcolati a mano per ogni
// detector Tier 1 + i puri helper di matematica. Semantica Betfair verificata.
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { Snapshot, MarketState, MarketLite, OppConfig, SelLite } from './types';
import {
    backLayLock, layThenBackLock, ltdInsurance, dutchLayField, phaseFromMinute, clamp,
    thetaDecay, layTheDrawWithInsurance, layTheFieldCorrectScore, backToLay,
    meanReversionPostEvent, tier1Detectors,
} from './tier1_quasi';
import { runDetectors } from './engine';

const CFG: OppConfig = { stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 };

type Lvl = [number, number][];
type SelLad = Record<number, { back?: Lvl; lay?: Lvl; ltp?: number | null }>;

function mkState(market_id: string, market_type: string, sels: SelLad): MarketState {
    const ladder: Record<string, { back: Lvl; lay: Lvl; ltp: number | null; tv: number | null }> = {};
    for (const [sid, e] of Object.entries(sels)) {
        ladder[sid] = { back: e.back ?? [], lay: e.lay ?? [], ltp: e.ltp ?? null, tv: null };
    }
    return { market_id, market_type, status: 'OPEN', ladder };
}

const MO_SELS: SelLite[] = [
    { selection_id: 1, name: 'Home', sort_priority: 1 },
    { selection_id: 2, name: 'Away', sort_priority: 2 },
    { selection_id: 3, name: 'The Draw', sort_priority: 3 },
];
const moLite = (market_id = 'm1'): MarketLite => ({
    market_id, market_type: 'MATCH_ODDS', market_name: 'Match Odds', selections: MO_SELS,
});

function snap(over: Partial<Snapshot> = {}): Snapshot {
    return {
        ts: '2026-01-01T00:30:00.000Z', minute: 30, scoreHome: 0, scoreAway: 0,
        markets: [], state: {}, ...over,
    };
}

// ===================================================================== helpers
describe('pure math helpers', () => {
    it('phaseFromMinute partitions the match', () => {
        expect(phaseFromMinute(null)).toBe('pre');
        expect(phaseFromMinute(0)).toBe('pre');
        expect(phaseFromMinute(1)).toBe('1T');
        expect(phaseFromMinute(45)).toBe('1T');
        expect(phaseFromMinute(46)).toBe('2T');
        expect(phaseFromMinute(75)).toBe('2T');
        expect(phaseFromMinute(76)).toBe('late');
    });

    it('clamp bounds values', () => {
        expect(clamp(5, 0, 1)).toBe(1);
        expect(clamp(-5, 0, 1)).toBe(0);
        expect(clamp(0.3, 0, 1)).toBe(0.3);
    });

    it('backLayLock: back@3.6 lay@3.4 stake100 → gross 5.882353, net 5.588235', () => {
        const r = backLayLock(100, 3.6, 3.4, 0.05);
        expect(r.layStake).toBeCloseTo(105.882353, 5); // 100*3.6/3.4
        expect(r.gross).toBeCloseTo(5.882353, 5);       // 100*0.2/3.4
        expect(r.profit).toBeCloseTo(5.588235, 5);      // *0.95
    });

    it('backLayLock commission boundary: comm 0 → profit == gross', () => {
        const r = backLayLock(100, 3.6, 3.4, 0);
        expect(r.profit).toBeCloseTo(r.gross, 9);
        expect(r.profit).toBeCloseTo(5.882353, 5);
    });

    it('backLayLock rejects price<=1', () => {
        expect(backLayLock(100, 1.0, 3.4, 0.05)).toEqual({ layStake: 0, gross: 0, profit: 0 });
        expect(backLayLock(100, 3.4, 1.0, 0.05)).toEqual({ layStake: 0, gross: 0, profit: 0 });
        expect(backLayLock(0, 3.6, 3.4, 0.05)).toEqual({ layStake: 0, gross: 0, profit: 0 });
    });

    it('layThenBackLock: lay@1.75 back@2.02 stake100 → gross 13.366337, net 12.69802', () => {
        const r = layThenBackLock(100, 1.75, 2.02, 0.05);
        expect(r.backStake).toBeCloseTo(86.633663, 5); // 100*1.75/2.02
        expect(r.gross).toBeCloseTo(13.366337, 5);      // 100*0.27/2.02
        expect(r.profit).toBeCloseTo(12.69802, 5);
    });

    it('ltdInsurance: lay draw@3.5 stake100, back 0-0@8.0, comm5% → a≈0, b=-287.59, c=57.41', () => {
        const r = ltdInsurance(100, 3.5, 8.0, 0.05);
        expect(r.sz).toBeCloseTo(37.593985, 5);  // 250/(7*0.95)
        expect(r.a).toBeCloseTo(0, 6);            // 0-0 break-even by design
        expect(r.b).toBeCloseTo(-287.593985, 5);  // -250 - sz
        expect(r.c).toBeCloseTo(57.406015, 5);     // 95 - sz
    });

    it('dutchLayField: lay [12,20,50] liab100 comm5% → best 15.575139, worst -92.696026', () => {
        const r = dutchLayField([12, 20, 50], 100, 0.05);
        expect(r.stakes[0]).toBeCloseTo(9.090909, 5);
        expect(r.stakes[1]).toBeCloseTo(5.263158, 5);
        expect(r.stakes[2]).toBeCloseTo(2.040816, 5);
        expect(r.bestReturn).toBeCloseTo(15.575139, 5);
        expect(r.worstLiability).toBeCloseTo(-92.696026, 5);
    });
});

// =================================================================== thetaDecay
describe('thetaDecay', () => {
    const cur = (): Snapshot => snap({
        markets: [moLite()],
        state: { m1: mkState('m1', 'MATCH_ODDS', { 3: { back: [[3.5, 500]], lay: [[3.4, 500]] } }) },
    });
    const prev = (total = 0): Snapshot => snap({
        scoreHome: total, scoreAway: 0,
        markets: [moLite()],
        state: { m1: mkState('m1', 'MATCH_ODDS', { 3: { back: [[3.6, 500]], lay: [[3.5, 500]] } }) },
    });

    it('fires on decaying draw with no new goal', () => {
        const res = thetaDecay([prev()])(cur(), CFG);
        expect(res).toHaveLength(1);
        const o = res[0];
        expect(o.tier).toBe('low');
        expect(o.type).toBe('theta_decay');
        expect(o.profit).toBeCloseTo(2.794118, 5);     // backLayLock(100,3.5,3.4).net
        expect(o.profitPct).toBeCloseTo(2.794118, 5);
        expect(o.confidence).toBeCloseTo(0.7, 5);       // 0.3 + 0.4*1
        expect(o.legs[0]).toMatchObject({ side: 'back', price: 3.5, matchedStake: 100 });
        expect(o.legs[1].side).toBe('lay');
        expect(o.legs[1].price).toBeCloseTo(3.4, 6);
    });

    it('does NOT fire if price did not decay', () => {
        const flat = snap({
            markets: [moLite()],
            state: { m1: mkState('m1', 'MATCH_ODDS', { 3: { back: [[3.6, 500]], lay: [[3.5, 500]] } }) },
        });
        expect(thetaDecay([prev()])(flat, CFG)).toHaveLength(0);
    });

    it('does NOT fire if a goal was scored since prev', () => {
        // prev had 1 goal, current has 1 goal too? require total equality; here cur=0, prev total=1 → mismatch.
        expect(thetaDecay([prev(1)])(cur(), CFG)).toHaveLength(0);
    });

    it('does NOT fire with no history', () => {
        expect(thetaDecay([])(cur(), CFG)).toHaveLength(0);
    });

    it('thin liquidity caps matchedStake (30 of 100) → scaled profit & lower confidence', () => {
        const thin = snap({
            markets: [moLite()],
            state: { m1: mkState('m1', 'MATCH_ODDS', { 3: { back: [[3.5, 30]], lay: [[3.4, 500]] } }) },
        });
        const o = thetaDecay([prev()])(thin, CFG)[0];
        expect(o.legs[0].matchedStake).toBeCloseTo(30, 6);
        expect(o.profit).toBeCloseTo(0.838235, 5);     // backLayLock(30,3.5,3.4).net
        expect(o.confidence).toBeCloseTo(0.42, 5);      // 0.3 + 0.4*0.3
    });
});

// ====================================================== layTheDrawWithInsurance
describe('layTheDrawWithInsurance', () => {
    const csLite: MarketLite = {
        market_id: 'm2', market_type: 'CORRECT_SCORE', market_name: 'Correct Score',
        selections: [{ selection_id: 10, name: '0-0', sort_priority: 1 }],
    };
    function build(Zb: number): Snapshot {
        return snap({
            markets: [moLite(), csLite],
            state: {
                m1: mkState('m1', 'MATCH_ODDS', { 3: { lay: [[3.5, 500]] } }),
                m2: mkState('m2', 'CORRECT_SCORE', { 10: { back: [[Zb, 500]] } }),
            },
        });
    }

    it('fires: builds the locked insurance structure', () => {
        const res = layTheDrawWithInsurance()(build(8.0), CFG);
        expect(res).toHaveLength(1);
        const o = res[0];
        expect(o.tier).toBe('low');
        expect(o.type).toBe('ltd_insurance');
        expect(o.profit).toBeCloseTo(57.406015, 5);    // ins.c
        expect(o.profitPct).toBeCloseTo(19.960795, 4);  // 57.406015/287.593985*100
        expect(o.confidence).toBeCloseTo(0.839286, 5);  // 1 - (1/3.5 - 1/8)
        expect(o.legs[0]).toMatchObject({ side: 'lay', price: 3.5, matchedStake: 100 });
        expect(o.legs[1].side).toBe('back');
        expect(o.legs[1].price).toBeCloseTo(8.0, 6);
        expect(o.legs[1].stake).toBeCloseTo(37.593985, 5);
    });

    it('does NOT fire when 0-0 back price too low (insurance costs more than gain)', () => {
        // Zb=2.0 → sz=263.16 > 95 → c<0
        expect(layTheDrawWithInsurance()(build(2.0), CFG)).toHaveLength(0);
    });

    it('does NOT fire without a correct-score market', () => {
        const noCs = snap({
            markets: [moLite()],
            state: { m1: mkState('m1', 'MATCH_ODDS', { 3: { lay: [[3.5, 500]] } }) },
        });
        expect(layTheDrawWithInsurance()(noCs, CFG)).toHaveLength(0);
    });
});

// ====================================================== layTheFieldCorrectScore
describe('layTheFieldCorrectScore', () => {
    const fieldLite: MarketLite = {
        market_id: 'm3', market_type: 'CORRECT_SCORE', market_name: 'Correct Score',
        selections: [
            { selection_id: 20, name: '5-0' },
            { selection_id: 21, name: '0-5' },
            { selection_id: 22, name: '6-0' },
            { selection_id: 23, name: '1-0' },
        ],
    };
    function build(): Snapshot {
        return snap({
            markets: [fieldLite],
            state: {
                m3: mkState('m3', 'CORRECT_SCORE', {
                    20: { lay: [[12, 500]] },
                    21: { lay: [[20, 500]] },
                    22: { lay: [[50, 500]] },
                    23: { lay: [[5, 500]] }, // sotto soglia 11 → escluso
                }),
            },
        });
    }

    it('fires: dutch-lay of 3 improbable scores', () => {
        const res = layTheFieldCorrectScore()(build(), CFG);
        expect(res).toHaveLength(1);
        const o = res[0];
        expect(o.tier).toBe('low');
        expect(o.type).toBe('lay_field_cs');
        expect(o.legs).toHaveLength(3); // 1-0 @5 escluso
        expect(o.profit).toBeCloseTo(15.575139, 5);
        expect(o.profitPct).toBeCloseTo(16.802381, 4);  // 15.575139/92.696026*100
        expect(o.confidence).toBeCloseTo(0.846667, 5);  // 1 - (1/12+1/20+1/50)
        expect(o.legs.every((l) => l.side === 'lay')).toBe(true);
    });

    it('does NOT fire with fewer than 2 improbable scores', () => {
        const one: Snapshot = snap({
            markets: [fieldLite],
            state: { m3: mkState('m3', 'CORRECT_SCORE', { 20: { lay: [[12, 500]] }, 23: { lay: [[5, 500]] } }) },
        });
        expect(layTheFieldCorrectScore()(one, CFG)).toHaveLength(0);
    });
});

// ===================================================================== backToLay
describe('backToLay', () => {
    it('TRUE ARB: crossed book (back 3.6 > lay 3.4) → guaranteed lock fires as arb', () => {
        const s = snap({
            markets: [moLite()],
            state: {
                m1: mkState('m1', 'MATCH_ODDS', {
                    1: { back: [[3.6, 500]], lay: [[3.4, 500]] }, // home crossed
                    2: { back: [[1.5, 500]], lay: [[1.6, 500]] }, // away normal
                }),
            },
        });
        const res = backToLay([])(s, CFG);
        expect(res).toHaveLength(1);
        const o = res[0];
        expect(o.tier).toBe('arb');
        expect(o.type).toBe('back_to_lay_arb');
        expect(o.profit).toBeCloseTo(5.588235, 5);     // backLayLock(100,3.6,3.4).net
        expect(o.profitPct).toBeCloseTo(5.588235, 5);
        expect(o.confidence).toBeCloseTo(1, 6);
        expect(o.legs[0]).toMatchObject({ side: 'back', price: 3.6 });
        expect(o.legs[1]).toMatchObject({ side: 'lay', price: 3.4 });
    });

    it('NO ARB: normal book (back 3.4 < lay 3.6) + no history → nothing fires', () => {
        const s = snap({
            markets: [moLite()],
            state: {
                m1: mkState('m1', 'MATCH_ODDS', {
                    1: { back: [[3.4, 500]], lay: [[3.6, 500]] },
                    2: { back: [[1.6, 500]], lay: [[1.7, 500]] },
                }),
            },
        });
        expect(backToLay([])(s, CFG)).toHaveLength(0);
    });

    it('MOMENTUM: favourite shortening 2.1→2.0 → expected back-to-lay (tier low)', () => {
        const prev = snap({
            markets: [moLite()],
            state: { m1: mkState('m1', 'MATCH_ODDS', { 1: { back: [[2.1, 500]], lay: [[2.15, 500]] } }) },
        });
        const cur = snap({
            markets: [moLite()],
            state: { m1: mkState('m1', 'MATCH_ODDS', { 1: { back: [[2.0, 500]], lay: [[2.05, 500]] } }) },
        });
        const res = backToLay([prev])(cur, CFG);
        const o = res.find((x) => x.type === 'back_to_lay');
        expect(o).toBeDefined();
        expect(o!.tier).toBe('low');
        // L = max(1.01, 2*2.0 - 2.1) = 1.9 ; backLayLock(100,2.0,1.9,0.05).net = 9.5/1.9 = 5.0
        expect(o!.profit).toBeCloseTo(5.0, 6);
        expect(o!.profitPct).toBeCloseTo(5.0, 6);
        expect(o!.legs[0]).toMatchObject({ side: 'back', price: 2.0 });
        expect(o!.legs[1].price).toBeCloseTo(1.9, 6);
    });
});

// ============================================================ meanReversionPostEvent
describe('meanReversionPostEvent', () => {
    const pre = snap({
        scoreHome: 0, scoreAway: 0,
        markets: [moLite()],
        state: { m1: mkState('m1', 'MATCH_ODDS', { 1: { back: [[2.5, 500]], lay: [[2.55, 500]] } }) },
    });
    const cur = snap({
        scoreHome: 1, scoreAway: 0,
        markets: [moLite()],
        state: { m1: mkState('m1', 'MATCH_ODDS', { 1: { back: [[1.7, 500]], lay: [[1.75, 500]] } }) },
    });

    it('fires: fade the overreaction after a home goal (lay-then-back)', () => {
        const res = meanReversionPostEvent([pre])(cur, CFG);
        expect(res).toHaveLength(1);
        const o = res[0];
        expect(o.tier).toBe('directional');
        expect(o.type).toBe('mean_reversion');
        // move = (1.7-2.5)/2.5 = -0.32 ; Bexit = 1.7 + 0.4*0.8 = 2.02
        // layThenBackLock(100,1.75,2.02,0.05).net = (100*0.27/2.02)*0.95 = 12.69802
        expect(o.profit).toBeCloseTo(12.69802, 5);
        expect(o.profitPct).toBeCloseTo(12.69802, 5);
        expect(o.confidence).toBeCloseTo(0.52, 5);      // 0.2 + 0.32
        expect(o.legs[0]).toMatchObject({ side: 'lay', price: 1.75, matchedStake: 100 });
        expect(o.legs[1].side).toBe('back');
        expect(o.legs[1].price).toBeCloseTo(2.02, 6);
    });

    it('does NOT fire without a goal (no score delta in history)', () => {
        const noGoal = snap({
            scoreHome: 0, scoreAway: 0,
            markets: [moLite()],
            state: { m1: mkState('m1', 'MATCH_ODDS', { 1: { back: [[1.7, 500]], lay: [[1.75, 500]] } }) },
        });
        expect(meanReversionPostEvent([pre])(noGoal, CFG)).toHaveLength(0);
    });

    it('does NOT fire when move below overshoot threshold', () => {
        const small = snap({
            scoreHome: 1, scoreAway: 0,
            markets: [moLite()],
            state: { m1: mkState('m1', 'MATCH_ODDS', { 1: { back: [[2.4, 500]], lay: [[2.45, 500]] } }) },
        });
        expect(meanReversionPostEvent([pre])(small, CFG)).toHaveLength(0);
    });
});

// =================================================================== engine wiring
describe('engine integration', () => {
    it('arb from backToLay survives the engine filter and ranks first', () => {
        const s = snap({
            markets: [moLite()],
            state: {
                m1: mkState('m1', 'MATCH_ODDS', {
                    1: { back: [[3.6, 500]], lay: [[3.4, 500]] },
                    2: { back: [[1.5, 500]], lay: [[1.6, 500]] },
                }),
            },
        });
        const res = runDetectors(s, tier1Detectors([]), CFG);
        expect(res.length).toBeGreaterThanOrEqual(1);
        expect(res[0].tier).toBe('arb');
        expect(res[0].type).toBe('back_to_lay_arb');
    });
});
