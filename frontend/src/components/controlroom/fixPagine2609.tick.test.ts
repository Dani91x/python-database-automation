// ============================================================================
// fixPagine2609.tick.test.ts - F-4 del test e2e FASE 3 (26/09): «tick di
// movimento» col SEGNO INVERTITO e sul prezzo sbagliato. I casi sono le 4
// posizioni misurate a video (catture 09:19-09:20Z, referto ADMIN26_FASE3 §2):
// il segno deve CONCORDARE con «chiudi ora» in € (giusto 6/6).
//
// FALSIFICAZIONE (26/09): rimettendo in `tickAFavore` il vecchio ×−1 sul lay
// (o in `quotaViva` il prezzo dello STESSO lato) i casi Omega 118 / Mike 5071 /
// Omega 119 diventano rossi.
// ============================================================================
import { describe, expect, it } from 'vitest';
import { quotaViva } from '@/components/controlroom/dettaglioRiga';
import { tickAFavore } from '@/lib/riskMath';

describe('F-4: tick a favore = stesso segno del «chiudi ora» in €', () => {
    it('Omega 118 LAY 1@55, ora B 60 / L 110: chiudi ora +0,08 € -> +1 tick', () => {
        const v = quotaViva(55, 'lay', { back: 60, lay: 110 });
        expect(v?.ora).toBe(60);
        expect(v?.tick).toBe(1);
    });
    it('Mike 5071 BACK 5@1,60, ora B 1,62 / L 1,68: chiudi ora −0,24 € -> −8 tick', () => {
        const v = quotaViva(1.6, 'back', { back: 1.62, lay: 1.68 });
        expect(v?.ora).toBe(1.68);
        expect(v?.tick).toBe(-8);
    });
    it('Omega 119 LAY 1@80, ora B 29: chiudi ora −1,76 € -> −17 tick (atteso dal referto)', () => {
        expect(quotaViva(80, 'lay', { back: 29, lay: 32 })?.tick).toBe(-17);
    });
    it('Mike 5070 BACK 5@1,51, chiusura a lay 1,55: −0,19 € -> tick negativo', () => {
        expect(quotaViva(1.51, 'back', { back: 1.53, lay: 1.55 })?.tick).toBe(-4);
    });
    it('tickAFavore (usato anche da SafeTradesTable): lay sale = +, back sale = −', () => {
        expect(tickAFavore('lay', 2.0, 2.1)).toBe(5);
        expect(tickAFavore('back', 2.0, 2.1)).toBe(-5);
        expect(tickAFavore('back', 2.0, 1.9)).toBe(10);
        expect(tickAFavore('lay', 2.0, 2.0)).toBe(0);
    });
});
