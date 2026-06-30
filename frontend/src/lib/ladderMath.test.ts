import { describe, it, expect } from 'vitest';
import { lockedPnlAt, piqAhead } from './ladderMath';

describe('lockedPnlAt', () => {
    it('equalises: locked = L + (W-L)/p', () => {
        // W=10, L=-5, p=3 → -5 + 15/3 = 0
        expect(lockedPnlAt(3, 10, -5)).toBeCloseTo(0, 9);
        // W=20, L=-4, p=5 → -4 + 24/5 = 0.8
        expect(lockedPnlAt(5, 20, -4)).toBeCloseTo(0.8, 9);
    });
    it('returns the lose branch when price is not closable', () => {
        expect(lockedPnlAt(1, 10, -5)).toBe(-5);
        expect(lockedPnlAt(NaN, 10, -5)).toBe(-5);
        expect(lockedPnlAt(0.5, 10, -5)).toBe(-5);
    });
    it('flat position stays flat at any price', () => {
        expect(lockedPnlAt(4, 7, 7)).toBeCloseTo(7, 9);
    });
});

describe('piqAhead', () => {
    it('queue ahead = restingAvail - mySize (clamped at 0)', () => {
        expect(piqAhead(5, 80)).toBe(75);
        expect(piqAhead(10, 10)).toBe(0);   // solo tu al livello
        expect(piqAhead(10, 4)).toBe(0);    // dato incoerente → clamp 0
    });
    it('no order at the level → 0', () => {
        expect(piqAhead(0, 80)).toBe(0);
        expect(piqAhead(-3, 80)).toBe(0);
    });
    it('missing resting depth → 0 (only your size)', () => {
        expect(piqAhead(5, NaN)).toBe(0);
    });
});
