import { describe, it, expect } from 'vitest';
import {
    lockedPnlAt, piqAhead, windowAround, flashDir, stepStake, nextPreset,
    STAKE_MIN, STAKE_STEP,
} from './ladderMath';

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

describe('windowAround', () => {
    const asc = Array.from({ length: 100 }, (_, i) => 2 + i * 0.02); // 2.00 … 3.98
    it('list shorter than maxRows → returned whole (copy)', () => {
        const short = [1.5, 1.6, 1.7];
        const w = windowAround(short, 1.6, 10);
        expect(w).toEqual(short);
        expect(w).not.toBe(short); // copia, non alias
    });
    it('centers the window on the nearest tick', () => {
        const w = windowAround(asc, 3.0, 11);
        expect(w).toHaveLength(11);
        expect(w[5]).toBeCloseTo(3.0, 9); // centro esatto in mezzo
    });
    it('clamps at the LOW edge without shrinking', () => {
        const w = windowAround(asc, 2.0, 11);
        expect(w).toHaveLength(11);
        expect(w[0]).toBeCloseTo(2.0, 9);
    });
    it('clamps at the HIGH edge without shrinking', () => {
        const w = windowAround(asc, 99, 11);
        expect(w).toHaveLength(11);
        expect(w[10]).toBeCloseTo(3.98, 9);
    });
    it('non-finite center falls back to the middle', () => {
        const w = windowAround(asc, NaN, 11);
        expect(w).toHaveLength(11);
    });
    it('empty / invalid inputs → empty', () => {
        expect(windowAround([], 2, 10)).toEqual([]);
        expect(windowAround(asc, 2, 0)).toEqual([]);
    });
});

describe('flashDir', () => {
    it('detects increase/decrease above the noise threshold', () => {
        expect(flashDir(10, 20)).toBe('up');
        expect(flashDir(20, 10)).toBe('down');
    });
    it('sub-threshold noise and first-sight produce no flash', () => {
        expect(flashDir(10, 10.3)).toBeNull();
        expect(flashDir(undefined, 50)).toBeNull();
        expect(flashDir(NaN, 50)).toBeNull();
        expect(flashDir(10, NaN)).toBeNull();
    });
});

describe('stepStake / nextPreset', () => {
    it('steps by 0.50€ with a hard floor at 0.50€', () => {
        expect(stepStake(5, 1)).toBe(5.5);
        expect(stepStake(5, -1)).toBe(4.5);
        expect(stepStake(0.5, -1)).toBe(STAKE_MIN);
        expect(stepStake(0.7, -1)).toBe(STAKE_MIN); // clamp, non negativo
    });
    it('invalid current stake restarts from the floor', () => {
        expect(stepStake(NaN, 1)).toBe(STAKE_MIN + STAKE_STEP);
        expect(stepStake(0, 1)).toBe(STAKE_MIN + STAKE_STEP);
    });
    it('rounds to cents', () => {
        expect(stepStake(1.111, 1)).toBe(1.61);
    });
    it('nextPreset cycles and restarts from the first when off-preset', () => {
        const presets = [2, 5, 10, 25];
        expect(nextPreset(presets, 2)).toBe(5);
        expect(nextPreset(presets, 25)).toBe(2);   // ciclico
        expect(nextPreset(presets, 7.5)).toBe(2);  // non-preset → riparte
        expect(nextPreset([], 7)).toBe(7);         // lista vuota → invariato
    });
});
