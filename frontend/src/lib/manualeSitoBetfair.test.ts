import { describe, it, expect } from 'vitest';
import { leggiManualeSitoBetfair } from './manualeSitoBetfair';

const OGGI = '2026-09-18';

describe('leggiManualeSitoBetfair', () => {
    it('riga assente: "non disponibile" per SITO e APP, mai zero', () => {
        const r = leggiManualeSitoBetfair(null, OGGI);
        expect(r.pnlOggi).toBeNull();
        expect(r.fonte).toBe('non-disponibile');
        expect(r.app?.pnlOggi).toBeNull();
        expect(r.app?.fonte).toBe('non-disponibile');
        expect(r.esclusi).toBeNull();
    });

    it('colonne manual_* assenti (migrazione non applicata): nessun contributo, — dichiarato', () => {
        const r = leggiManualeSitoBetfair({}, OGGI);
        expect(r.pnlOggi).toBeNull();
        expect(r.fonte).toBe('non-disponibile');
        expect(r.app?.pnlOggi).toBeNull();
    });

    it('SITO con dati di OGGI: numero, netto e ordini letti dalla riga', () => {
        const r = leggiManualeSitoBetfair({
            manual_pnl_eur: 12.345, manual_pnl_is_net: true, manual_pnl_orders: 3,
            manual_pnl_excluded: 1, manual_pnl_day: OGGI,
        }, OGGI);
        expect(r.pnlOggi).toBeCloseTo(12.35, 2);
        expect(r.fonte).toBe('backend');
        expect(r.netto).toBe(true);
        expect(r.ordini).toBe(3);
        expect(r.esclusi).toBe(1);
    });

    it('APP con dati di OGGI: bucket separato, mai mischiato col sito', () => {
        const r = leggiManualeSitoBetfair({
            manual_pnl_eur: 12, manual_pnl_day: OGGI,
            manual_app_pnl_eur: -5.6, manual_app_pnl_is_net: false, manual_app_pnl_orders: 2,
            manual_app_pnl_day: OGGI,
        }, OGGI);
        expect(r.pnlOggi).toBe(12);
        expect(r.app?.pnlOggi).toBe(-5.6);
        expect(r.app?.netto).toBe(false);
        expect(r.app?.ordini).toBe(2);
    });

    it('giorno diverso da oggi: il numero e vecchio, non entra (— non 0)', () => {
        const r = leggiManualeSitoBetfair({
            manual_pnl_eur: 40, manual_pnl_day: '2026-09-17',
        }, OGGI);
        expect(r.pnlOggi).toBeNull();
        expect(r.fonte).toBe('non-disponibile');
    });

    it('lordo dichiarato: netto=false, mai spacciato per netto', () => {
        const r = leggiManualeSitoBetfair({
            manual_pnl_eur: 8, manual_pnl_is_net: false, manual_pnl_day: OGGI,
        }, OGGI);
        expect(r.netto).toBe(false);
    });
});
