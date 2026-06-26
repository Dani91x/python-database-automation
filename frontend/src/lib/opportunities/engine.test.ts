import { describe, it, expect } from 'vitest';
import { runDetectors, DEFAULT_OPP_CONFIG, TIER_ORDER, opportunitySignature } from './engine';
import type { Detector, Opportunity, Snapshot, RiskTier, Leg } from './types';

// Il gate "specchio della realtà" del motore richiede mercato OPEN + controparte
// reale su ogni gamba: la snapshot espone m1 OPEN (le gambe di default usano m1 e
// hanno matchedStake>0), così questi test isolano filtro/ordinamento/dedup.
const snap: Snapshot = {
    ts: '2026-01-01T00:00:00.000Z',
    minute: 1, scoreHome: 0, scoreAway: 0,
    markets: [],
    state: { m1: { market_id: 'm1', market_type: 'MATCH_ODDS', status: 'OPEN', ladder: {} } },
};

function leg(over: Partial<Leg> = {}): Leg {
    return {
        marketId: 'm1', marketName: 'Match Odds', selectionId: 1, selectionName: 'A',
        side: 'back', price: 2.0, stake: 100, matchedStake: 100, ...over,
    };
}

function opp(over: Partial<Opportunity> = {}): Opportunity {
    return {
        id: 'x', tier: 'arb' as RiskTier, type: 'cross_market', title: 't',
        instruction: 'i', legs: [leg()], profit: 1, profitPct: 1, confidence: 1,
        explanation: 'e', phase: 'p', ...over,
    };
}

describe('opportunitySignature', () => {
    it('is order-independent on legs', () => {
        const a = opp({ legs: [leg({ selectionId: 1 }), leg({ selectionId: 2 })] });
        const b = opp({ legs: [leg({ selectionId: 2 }), leg({ selectionId: 1 })] });
        expect(opportunitySignature(a)).toBe(opportunitySignature(b));
    });
    it('differs by type', () => {
        expect(opportunitySignature(opp({ type: 'a' })))
            .not.toBe(opportunitySignature(opp({ type: 'b' })));
    });
});

describe('runDetectors — filtering', () => {
    it('drops arb below minProfitPct, keeps arb at/above', () => {
        const d: Detector = () => [
            opp({ id: 'lo', type: 'arb_lo', profitPct: 0.3, profit: 9 }),
            opp({ id: 'hi', type: 'arb_hi', profitPct: 1.0, profit: 10 }),
        ];
        const res = runDetectors(snap, [d], DEFAULT_OPP_CONFIG);
        expect(res.map((o) => o.id)).toEqual(['hi']);
    });

    it('keeps low/directional regardless of profitPct', () => {
        const d: Detector = () => [
            opp({ id: 'low', tier: 'low', type: 'value', profitPct: 0.01, profit: 5 }),
            opp({ id: 'dir', tier: 'directional', type: 'momentum', profitPct: 0.0, profit: 7 }),
        ];
        const res = runDetectors(snap, [d], DEFAULT_OPP_CONFIG);
        expect(res.map((o) => o.id).sort()).toEqual(['dir', 'low']);
    });
});

describe('runDetectors — ordering', () => {
    it('sorts by tier (arb>low>directional) then profit desc', () => {
        const d: Detector = () => [
            opp({ id: 'dir', tier: 'directional', type: 'm', profitPct: 9, profit: 20 }),
            opp({ id: 'low', tier: 'low', type: 'v', profitPct: 9, profit: 5 }),
            opp({ id: 'arb1', tier: 'arb', type: 'a1', profitPct: 1, profit: 10 }),
            opp({ id: 'arb2', tier: 'arb', type: 'a2', profitPct: 1, profit: 30 }),
        ];
        const res = runDetectors(snap, [d], DEFAULT_OPP_CONFIG);
        expect(res.map((o) => o.id)).toEqual(['arb2', 'arb1', 'low', 'dir']);
    });
});

describe('runDetectors — dedupe', () => {
    it('removes duplicates by type+legs signature, keeping best (first after sort)', () => {
        const dA: Detector = () => [opp({ id: 'first', type: 'dup', profitPct: 1, profit: 10 })];
        const dB: Detector = () => [opp({ id: 'second', type: 'dup', profitPct: 1, profit: 10 })];
        const res = runDetectors(snap, [dA, dB], DEFAULT_OPP_CONFIG);
        expect(res.length).toBe(1);
        expect(res[0].id).toBe('first');
    });
});

describe('config + constants', () => {
    it('DEFAULT_OPP_CONFIG matches the contract', () => {
        expect(DEFAULT_OPP_CONFIG).toEqual({ stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 });
    });
    it('TIER_ORDER ranks arb>low>directional', () => {
        expect(TIER_ORDER.arb).toBeLessThan(TIER_ORDER.low);
        expect(TIER_ORDER.low).toBeLessThan(TIER_ORDER.directional);
    });
});
