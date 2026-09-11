import { describe, it, expect } from 'vitest';
import {
    MINUS, DASH, fmtMoney, fmtOdds, fmtPct, fmtPctPoints, fmtNum, fmtTicks,
    fmtTime, fmtDateTime, fmtAge, ageSeconds,
} from './format';

describe('fmtMoney', () => {
    it('formato italiano: virgola decimale, simbolo dopo', () => {
        expect(fmtMoney(12.5)).toBe('12,50 €');
        expect(fmtMoney(1)).toBe('1,00 €');
        expect(fmtMoney(24.244)).toBe('24,24 €');
    });
    it('segno: meno tipografico sempre, piu solo se richiesto', () => {
        expect(fmtMoney(-12.5)).toBe('−12,50 €');
        expect(fmtMoney(-12.5)).toContain(MINUS);
        expect(fmtMoney(12.5, { signed: true })).toBe('+12,50 €');
        expect(fmtMoney(-12.5, { signed: true })).toBe('−12,50 €');
        expect(fmtMoney(0, { signed: true })).toBe('+0,00 €');
        // -0.001 arrotonda a zero: nessun meno fuorviante
        expect(fmtMoney(-0.001)).toBe('0,00 €');
    });
    it('decimali e valuta configurabili', () => {
        expect(fmtMoney(1234.5, { decimals: 0 })).toBe('1235 €');
        expect(fmtMoney(1.5, { currency: '' })).toBe('1,50');
    });
    it('dato assente = trattino lungo, mai zero', () => {
        expect(fmtMoney(null)).toBe(DASH);
        expect(fmtMoney(undefined)).toBe('—');
        expect(fmtMoney(Number.NaN)).toBe('—');
    });
});

describe('fmtOdds / fmtPct / fmtNum / fmtTicks', () => {
    it('quote a 2 decimali con la virgola', () => {
        expect(fmtOdds(2.04)).toBe('2,04');
        expect(fmtOdds(110)).toBe('110,00');
        expect(fmtOdds(null)).toBe('—');
        expect(fmtOdds(Number.NaN)).toBe('—');
    });
    it('percentuali da FRAZIONE 0-1', () => {
        expect(fmtPct(0.125)).toBe('12,5 %');
        expect(fmtPct(0.004, 1)).toBe('0,4 %');
        expect(fmtPct(0.012, 2)).toBe('1,20 %');
        expect(fmtPct(null)).toBe('—');
    });
    it('percentuali da punti percentuali', () => {
        expect(fmtPctPoints(12.5)).toBe('12,5 %');
        expect(fmtPctPoints(null)).toBe('—');
    });
    it('numeri e tick', () => {
        expect(fmtNum(3)).toBe('3');
        expect(fmtNum(1.234, 2)).toBe('1,23');
        expect(fmtNum(null, 2)).toBe('—');
        expect(fmtTicks(2)).toBe('2 tick');
        expect(fmtTicks(-8)).toBe('8 tick');
        expect(fmtTicks(null)).toBe('—');
    });
});

describe('orari Europe/Rome', () => {
    // 2026-09-11T16:05:07Z = 18:05:07 a Roma (CEST, +2)
    const ISO = '2026-09-11T16:05:07Z';
    it('fmtTime con e senza secondi', () => {
        expect(fmtTime(ISO)).toBe('18:05');
        expect(fmtTime(ISO, { seconds: true })).toBe('18:05:07');
        expect(fmtTime(null)).toBe('—');
        expect(fmtTime('non-una-data')).toBe('—');
    });
    it('fmtDateTime: giorno abbreviato + ora', () => {
        const s = fmtDateTime(ISO);
        expect(s).toMatch(/^ven 11 set · 18:05$/);
        expect(fmtDateTime(null)).toBe('—');
    });
});

describe('fmtAge / ageSeconds', () => {
    it('secondi, minuti, ore', () => {
        expect(fmtAge(3)).toBe('3 s');
        expect(fmtAge(59)).toBe('59 s');
        expect(fmtAge(120)).toBe('2 min');
        expect(fmtAge(3900)).toBe('1 h 05');
        expect(fmtAge(null)).toBe('—');
    });
    it('ageSeconds misura l eta di un iso', () => {
        const now = Date.parse('2026-09-11T16:05:07Z');
        expect(ageSeconds('2026-09-11T16:05:00Z', now)).toBe(7);
        expect(ageSeconds(null, now)).toBeNull();
        expect(ageSeconds('boh', now)).toBeNull();
        // orologi sfasati: mai eta negative
        expect(ageSeconds('2026-09-11T16:06:00Z', now)).toBe(0);
    });
});
