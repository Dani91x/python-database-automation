import { describe, it, expect } from 'vitest';
import { matchedStake, fillRatio, netWin, DEFAULT_DELAY_SEC } from './fill';

describe('matchedStake — BACK side', () => {
    const back: [number, number][] = [[2.0, 50], [1.99, 100]];

    it('takes only levels with price >= target (best level)', () => {
        // target 2.0 → solo [2.0,50] qualifica (1.99 < 2.0). desired 200 → 50.
        expect(matchedStake(back, 2.0, 200, 'back')).toBe(50);
    });

    it('caps at desired stake when liquidity is larger', () => {
        // target 2.0 → disponibili 50, desired 30 → min(50,30)=30.
        expect(matchedStake(back, 2.0, 30, 'back')).toBe(30);
    });

    it('includes worse-priced-but-acceptable levels when target is lower', () => {
        // target 1.99 → 2.0 e 1.99 entrambi accettabili = 150, desired 200 → 150.
        expect(matchedStake(back, 1.99, 200, 'back')).toBe(150);
    });

    it('defaults to back side', () => {
        expect(matchedStake(back, 2.0, 200)).toBe(50);
    });
});

describe('matchedStake — LAY side', () => {
    const lay: [number, number][] = [[3.0, 40], [3.05, 60]];

    it('takes only levels with price <= target', () => {
        // target 3.0 → solo [3.0,40] (3.05 > 3.0 escluso). desired 200 → 40.
        expect(matchedStake(lay, 3.0, 200, 'lay')).toBe(40);
    });

    it('includes higher-priced-but-acceptable levels when target is higher', () => {
        // target 3.05 → 3.0 e 3.05 = 100, desired 200 → 100.
        expect(matchedStake(lay, 3.05, 200, 'lay')).toBe(100);
    });
});

describe('matchedStake — edge cases', () => {
    it('returns 0 for empty/undefined levels', () => {
        expect(matchedStake([], 2.0, 100)).toBe(0);
        expect(matchedStake(undefined, 2.0, 100)).toBe(0);
    });
    it('returns 0 for non-positive desired stake', () => {
        expect(matchedStake([[2.0, 50]], 2.0, 0)).toBe(0);
        expect(matchedStake([[2.0, 50]], 2.0, -10)).toBe(0);
    });
    it('returns 0 for invalid target price', () => {
        expect(matchedStake([[2.0, 50]], 0, 100)).toBe(0);
    });
    it('skips malformed levels (NaN/zero size)', () => {
        const lv: [number, number][] = [[2.0, 0], [2.0, 30], [NaN, 100]];
        expect(matchedStake(lv, 2.0, 200, 'back')).toBe(30);
    });
});

describe('fillRatio', () => {
    it('is matched/desired', () => {
        // back sum at target 2.0 = 50, desired 200 → 0.25.
        expect(fillRatio([[2.0, 50], [1.99, 100]], 2.0, 200, 'back')).toBe(0.25);
    });
    it('is 1 when fully fillable', () => {
        expect(fillRatio([[2.0, 500]], 2.0, 200, 'back')).toBe(1);
    });
    it('is 0 for non-positive desired', () => {
        expect(fillRatio([[2.0, 50]], 2.0, 0)).toBe(0);
    });
});

describe('netWin — Betfair commission netting', () => {
    it('charges commission only on positive profit', () => {
        // 100 * (1 - 0.05) = 95.
        expect(netWin(100, 0.05)).toBe(95);
    });
    it('leaves losses untouched', () => {
        expect(netWin(-50, 0.05)).toBe(-50);
    });
    it('zero profit → zero (no commission)', () => {
        expect(netWin(0, 0.05)).toBe(0);
    });
    it('handles other commission rates exactly', () => {
        expect(netWin(200, 0.02)).toBeCloseTo(196, 10);
    });
});

describe('delay constant', () => {
    it('models the in-play 5-8s delay (default 6)', () => {
        expect(DEFAULT_DELAY_SEC).toBe(6);
    });
});
