import { describe, it, expect } from 'vitest';
import { countdownToOff, formatMinute, formatScore } from './matchClock';

const T0 = Date.parse('2026-07-08T15:00:00.000Z'); // off di riferimento
const iso = '2026-07-08T15:00:00.000Z';

describe('countdownToOff', () => {
    it('openDate mancante o invalida → null', () => {
        expect(countdownToOff(null, T0)).toBeNull();
        expect(countdownToOff(undefined, T0)).toBeNull();
        expect(countdownToOff('', T0)).toBeNull();
        expect(countdownToOff('non-una-data', T0)).toBeNull();
    });
    it('esattamente all\'off o già passata → null', () => {
        expect(countdownToOff(iso, T0)).toBeNull();          // nowMs == off
        expect(countdownToOff(iso, T0 + 1)).toBeNull();      // già partita
        expect(countdownToOff(iso, T0 + 3_600_000)).toBeNull();
    });
    it('< 1h → "MM:SS"', () => {
        expect(countdownToOff(iso, T0 - 59 * 60_000 - 59_000)).toBe('59:59'); // 59:59
        expect(countdownToOff(iso, T0 - 5 * 60_000 - 3000)).toBe('05:03');
        expect(countdownToOff(iso, T0 - 1000)).toBe('00:01');
        expect(countdownToOff(iso, T0 - 1)).toBe('00:00');   // ultimo istante, mai null
    });
    it('>= 1h → "H:MM:SS" (confine 59:59 vs 1:00:00)', () => {
        expect(countdownToOff(iso, T0 - 3_600_000)).toBe('1:00:00');          // esattamente 1h
        expect(countdownToOff(iso, T0 - 3_600_000 + 1000)).toBe('59:59');     // 1s sotto l'ora
        expect(countdownToOff(iso, T0 - (2 * 3600 + 5 * 60 + 7) * 1000)).toBe('2:05:07');
        expect(countdownToOff(iso, T0 - (23 * 3600 + 59 * 60 + 59) * 1000)).toBe('23:59:59');
    });
    it('>= 24h → "Ng NNh" (confine 23:59:59 vs 1g 00h)', () => {
        expect(countdownToOff(iso, T0 - 24 * 3_600_000)).toBe('1g 00h');      // esattamente 24h
        expect(countdownToOff(iso, T0 - (2 * 24 + 3) * 3_600_000)).toBe('2g 03h');
        expect(countdownToOff(iso, T0 - (5 * 24 + 15) * 3_600_000)).toBe('5g 15h');
    });
});

describe('formatMinute', () => {
    it('null / undefined / negativo / non finito → null', () => {
        expect(formatMinute(null)).toBeNull();
        expect(formatMinute(undefined)).toBeNull();
        expect(formatMinute(-1)).toBeNull();
        expect(formatMinute(NaN)).toBeNull();
    });
    it('minuto 0 è valido → "0\'"', () => {
        expect(formatMinute(0)).toBe("0'");
    });
    it('formatta il minuto corrente', () => {
        expect(formatMinute(63)).toBe("63'");
        expect(formatMinute(90)).toBe("90'");
    });
});

describe('formatScore', () => {
    it('uno dei due punteggi null/undefined → null', () => {
        expect(formatScore(null, 2)).toBeNull();
        expect(formatScore(1, undefined)).toBeNull();
        expect(formatScore(null, null)).toBeNull();
    });
    it('0–0 è un punteggio valido (en dash U+2013)', () => {
        expect(formatScore(0, 0)).toBe('0–0');
    });
    it('formatta "1–2" con en dash', () => {
        expect(formatScore(1, 2)).toBe('1–2');
        expect(formatScore(3, 0)).toBe('3–0');
    });
    it('punteggi non finiti → null (mai "NaN–1")', () => {
        expect(formatScore(NaN, 1)).toBeNull();
        expect(formatScore(1, Infinity)).toBeNull();
    });
});
