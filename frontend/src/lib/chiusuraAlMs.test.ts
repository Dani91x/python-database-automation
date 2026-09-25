// ============================================================================
// chiusuraAlMs.test.ts - 25/09 (residui B17): il "se chiudo ora" e le gambe
// delle combo AL PREZZO DEL MS (parte pura).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    chiusuraAlPrezzo, ripiegoScanner, testoFonte, valutaComboAlMs, type DatiChiusuraAlMs,
} from './chiusuraAlMs';
import { PREZZO_VUOTO, type PrezzoScheda } from './schedaAlMs';

const NOW = 1_800_000_000_000;

function prezzo(p: Partial<PrezzoScheda>): PrezzoScheda {
    return { ...PREZZO_VUOTO, ...p };
}

describe('chiusuraAlPrezzo: stessa matematica del green-up, al prezzo di adesso', () => {
    // back 10 € a 2,00: +10 se vince, -10 se perde -> si chiude BANCANDO
    it('lay a 1,80: P&L bloccato +1,11 sui due esiti', () => {
        const c = chiusuraAlPrezzo(10, -10, 'lay', prezzo({ lay: 1.8, laySize: 50 }));
        expect(c).toEqual({ lato: 'lay', prezzo: 1.8, abbinabile: 50, bloccabile: 1.11 });
    });
    it('lay a 2,20: P&L bloccato -0,91', () => {
        const c = chiusuraAlPrezzo(10, -10, 'lay', prezzo({ lay: 2.2, laySize: 50 }));
        expect(c.bloccabile).toBe(-0.91);
    });
    it('il lato che manca non si inventa: prezzo e P&L null', () => {
        const c = chiusuraAlPrezzo(10, -10, 'lay', prezzo({ back: 1.9, backSize: 20 }));
        expect(c).toEqual({ lato: 'lay', prezzo: null, abbinabile: null, bloccabile: null });
    });
});

describe('ripiegoScanner e testoFonte', () => {
    const d: DatiChiusuraAlMs = {
        win: 10, lose: -10, marketId: '1.23', selectionId: 7, sport: 'calcio',
        istanteScannerMs: NOW - 12_000,
        scanner: { back: 1.88, backSize: 30, lay: 1.9, laySize: 50 },
    };
    it('lo scanner diventa un PrezzoScheda dichiarato', () => {
        expect(ripiegoScanner(d)).toEqual({ back: 1.88, backSize: 30, lay: 1.9, laySize: 50,
            istanteMs: NOW - 12_000, fonte: 'scanner', statoMercato: null });
        expect(ripiegoScanner({ ...d, scanner: { back: null, backSize: null, lay: null, laySize: null } })).toBeNull();
        expect(ripiegoScanner(null)).toBeNull();
    });
    it('testi esatti per le tre fonti e per il prezzo assente', () => {
        expect(testoFonte(prezzo({ lay: 1.8, istanteMs: NOW - 400, fonte: 'canale' }), NOW))
            .toBe('ladder al ms, 0,4 s fa');
        expect(testoFonte(prezzo({ lay: 1.8, istanteMs: NOW - 3000, fonte: 'db' }), NOW))
            .toBe('ladder al ms (DB, il canale tace), 3,0 s fa');
        expect(testoFonte(prezzo({ lay: 1.9, istanteMs: NOW - 12_000, fonte: 'scanner' }), NOW))
            .toBe('prezzo dello scanner, 12 s fa (il canale non porta questo mercato)');
        expect(testoFonte(prezzo({ lay: 1.9, istanteMs: null, fonte: 'scanner' }), NOW))
            .toBe('prezzo dello scanner, eta\' ignota (il canale non porta questo mercato)');
        expect(testoFonte(PREZZO_VUOTO, NOW)).toBe('prezzo non disponibile');
    });
});

describe('valutaComboAlMs: tre gambe, limite inferiore del profitto bloccato', () => {
    // ev della proposta 0,05 per euro; S = 4 + 3 + 3 = 10
    const gambe = (p1: number | null, p2: number | null, p3: number | null) => [
        { lato: 'back' as const, prezzoProposta: 2.0, size: 4, prezzoOra: p1 },
        { lato: 'back' as const, prezzoProposta: 3.0, size: 3, prezzoOra: p2 },
        { lato: 'lay' as const, prezzoProposta: 5.0, size: 3, prezzoOra: p3 },
    ];
    it('nessuna gamba contro: SI, limite = ev della proposta', () => {
        const v = valutaComboAlMs(0.05, gambe(2.0, 3.1, 4.9));
        expect(v.semaforo).toBe('SI');
        expect(v.evMinimo).toBeCloseTo(0.05, 10);
        expect(v.tick).toEqual([0, 2, -1]);
        expect(v.contro).toEqual([false, false, false]);
    });
    it('una back scesa (contro) ma limite ancora positivo: QUASI', () => {
        const v = valutaComboAlMs(0.05, gambe(1.9, 3.1, 5.0));
        // perdita massima 4 * 0,10 = 0,40 su 10 € -> 0,05 - 0,04 = 0,01
        expect(v.evMinimo).toBeCloseTo(0.01, 10);
        expect(v.semaforo).toBe('QUASI');
        expect(v.tick).toEqual([-10, 2, 0]);   // 1,01-2,00: passo 0,01
        expect(v.contro).toEqual([true, false, false]);
        expect(v.motivi).toContain('almeno una gamba si e\' mossa contro: il profitto bloccato e\' sceso');
    });
    it('una lay salita (contro) che azzera il limite: NO', () => {
        const v = valutaComboAlMs(0.05, gambe(2.0, 3.0, 5.2));
        // 3 * 0,20 = 0,60 su 10 -> 0,05 - 0,06 = -0,01
        expect(v.evMinimo).toBeCloseTo(-0.01, 10);
        expect(v.semaforo).toBe('NO');
        expect(v.contro).toEqual([false, false, true]);
    });
    it('una gamba senza prezzo di adesso: NO, nessun limite inventato', () => {
        const v = valutaComboAlMs(0.05, gambe(2.0, null, 5.0));
        expect(v.evMinimo).toBeNull();
        expect(v.semaforo).toBe('NO');
        expect(v.motivi).toContain('gamba 2: prezzo di adesso non disponibile');
    });
    it('ev della proposta assente: NO, lo dice', () => {
        const v = valutaComboAlMs(null, gambe(2.0, 3.0, 5.0));
        expect(v.evMinimo).toBeNull();
        expect(v.motivi).toContain('profitto bloccato della proposta non dichiarato dal servizio');
    });
});
