import { describe, it, expect } from 'vitest';
import type { MarketLite, MarketState, OppConfig, SelLite, Snapshot } from './types';
import {
    correctScoreVsBTTS,
    correctScoreVsOverUnder,
    scenarioProfit,
} from './tier0_arb';

const CFG: OppConfig = { stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 };

type Level = [number, number];
function entry(back: Level[], lay: Level[] = []) {
    return { back, lay, ltp: null, tv: null };
}
function sel(id: number, name: string | null, sp?: number): SelLite {
    return { selection_id: id, name, sort_priority: sp };
}
function market(market_id: string, market_type: string, selections: SelLite[]): MarketLite {
    return { market_id, market_type, market_name: market_type, selections };
}
function state(market_id: string, market_type: string, ladder: Record<string, ReturnType<typeof entry>>): MarketState {
    return { market_id, market_type, status: 'OPEN', ladder: ladder as MarketState['ladder'] };
}
function snapshot(over: Partial<Snapshot>): Snapshot {
    return { ts: '2026-01-01T00:00:00.000Z', minute: 10, scoreHome: 0, scoreAway: 0, markets: [], state: {}, ...over };
}

// ===========================================================================
// ADVERSARIAL — NON-EXHAUSTIVE numeric CS grid breaks any "guaranteed" claim.
// The detector only requires every CS selection to PARSE as a score; it never
// verifies the grid COVERS every both-score (or every over-line) outcome.
// A real outcome whose score is not in the grid is NOT enumerated as a
// scenario, so the within-grid profit is NOT a true arbitrage.
//
// FIX (certification): cs_vs_btts / cs_vs_ou are reclassified OUT of tier:'arb'
// to tier:'low' and disclose the "score outside grid" residual risk; they NEVER
// advertise "profitto garantito qualunque esito". These tests assert the fix.
// ===========================================================================
describe('ADVERSARIAL: cs_vs_btts non-exhaustive grid', () => {
    // All selections are numeric scores -> passes the completeness guard, BUT
    // the both-score side lists ONLY 1-1. Real scores 2-2, 3-3, 2-1... are
    // both-score outcomes that are absent from the grid.
    const csSels = [sel(100, '0-0'), sel(101, '1-0'), sel(102, '0-1'), sel(103, '1-1')];
    const btSels = [sel(201, 'Yes'), sel(202, 'No')];

    const snap = snapshot({
        markets: [market('cs', 'CORRECT_SCORE', csSels), market('bt', 'BOTH_TEAMS_TO_SCORE', btSels)],
        state: {
            cs: state('cs', 'CORRECT_SCORE', {
                '100': entry([[6, 1000]]), '101': entry([[4, 1000]]),
                '102': entry([[6, 1000]]), '103': entry([[5, 1000]]),
            }),
            bt: state('bt', 'BOTH_TEAMS_TO_SCORE', { '201': entry([], [[1.9, 1000]]), '202': entry([], []) }),
        },
    });

    it('fires but is NOT tier:arb and does not claim a guarantee (FIXED)', () => {
        const res = correctScoreVsBTTS(snap, CFG);
        expect(res.length).toBe(1);
        expect(res[0].profit).toBeGreaterThan(100); // ~146.49 within-grid profit
        // FIX: reclassified out of arb → tier 'low', with disclosed residual risk.
        expect(res[0].tier).toBe('low');
        expect(res[0].instruction).not.toContain('garantito qualunque esito');
        expect(res[0].explanation.toLowerCase()).toContain('rischio');
    });

    it('an unlisted both-score outcome (e.g. real score 2-2) is a real loss the within-grid figure ignores', () => {
        const res = correctScoreVsBTTS(snap, CFG);
        const legs = res[0].legs;
        // Real score 2-2: both teams scored -> BTTS Yes (201) WINS. No CS leg in
        // the grid matches 2-2, so every CS back loses. winners = { Yes }.
        const actual = scenarioProfit(legs, new Set([201]), CFG.commission);
        // The position actually loses hundreds of pounds on that outcome — which is
        // why the opportunity is honestly NOT advertised as risk-free arbitrage.
        expect(actual).toBeLessThan(-300);
        expect(res[0].tier).not.toBe('arb');
    });
});

describe('ADVERSARIAL: cs_vs_ou non-exhaustive grid', () => {
    // Over 1.5 side lists ONLY 2-0. Real over-1.5 scores (1-1, 2-1, 3-0...) are
    // absent. Lay Over 1.5 settles on the real total, independent of the grid.
    const csSels = [sel(300, '0-0'), sel(301, '1-0'), sel(302, '0-1'), sel(303, '2-0')];
    const ouSels = [sel(401, 'Over 1.5 Goals'), sel(402, 'Under 1.5 Goals')];

    const snap = snapshot({
        markets: [market('cs', 'CORRECT_SCORE', csSels), market('ou15', 'OVER_UNDER_15', ouSels)],
        state: {
            cs: state('cs', 'CORRECT_SCORE', {
                '300': entry([[6, 1000]]), '301': entry([[4, 1000]]),
                '302': entry([[6, 1000]]), '303': entry([[5, 1000]]),
            }),
            ou15: state('ou15', 'OVER_UNDER_15', { '401': entry([], [[1.8, 1000]]), '402': entry([], []) }),
        },
    });

    it('fires as tier:low (not arb); an unlisted over-line score (e.g. real 2-1) is a real loss', () => {
        const res = correctScoreVsOverUnder(snap, CFG);
        expect(res.length).toBe(1);
        expect(res[0].profit).toBeGreaterThan(0);
        expect(res[0].tier).toBe('low'); // FIX: reclassified out of arb
        expect(res[0].instruction).not.toContain('garantito qualunque esito');
        // Real score 2-1: total 3 > 1.5 -> Over 1.5 (401) WINS. No CS leg matches
        // 2-1, so every CS back loses. winners = { Over 1.5 }.
        const actual = scenarioProfit(res[0].legs, new Set([401]), CFG.commission);
        expect(actual).toBeLessThan(0);
    });
});
