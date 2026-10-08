// ============================================================================
// fusoOrarioUTC.test.ts - guardia: sotto vitest il fuso orario e' SEMPRE UTC.
// (vitest.config.ts imposta process.env.TZ = 'UTC' prima di avviare i worker.)
// Se qualcuno toglie quella riga, questo test e' rosso su ogni PC fuori da UTC,
// e con lui le istantanee del DOM che stampano un orario locale
// (es. LadderView.botReplay.test.tsx, "Aggiornato: 16:13:20").
// ============================================================================
import { describe, it, expect } from 'vitest';

describe('fuso orario dei test', () => {
    it("process.env.TZ e' UTC", () => {
        expect(process.env.TZ).toBe('UTC');
    });

    it('Date lavora in UTC: offset 0 in estate e in inverno', () => {
        expect(new Date(Date.UTC(2026, 6, 1, 12, 0, 0)).getTimezoneOffset()).toBe(0);
        expect(new Date(Date.UTC(2026, 0, 1, 12, 0, 0)).getTimezoneOffset()).toBe(0);
    });

    it("toLocaleTimeString('it') stampa l'ora UTC, la stessa dell'istantanea del ladder", () => {
        // 16:13:20 UTC = l'orario scritto nell'istantanea di LadderView.botReplay.test.tsx
        expect(new Date(Date.UTC(2026, 9, 8, 16, 13, 20)).toLocaleTimeString('it')).toBe('16:13:20');
    });
});
