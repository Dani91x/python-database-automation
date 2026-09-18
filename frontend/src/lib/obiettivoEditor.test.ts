import { describe, it, expect } from 'vitest';
import { validaObiettivo, OBIETTIVO_MAX } from './obiettivoEditor';

describe('validaObiettivo', () => {
    it('accetta un intero semplice', () => {
        expect(validaObiettivo('50')).toEqual({ ok: true, valore: 50, errore: null });
    });

    it('accetta la virgola italiana', () => {
        expect(validaObiettivo('50,50')).toEqual({ ok: true, valore: 50.5, errore: null });
    });

    it('accetta il punto', () => {
        expect(validaObiettivo('50.5')).toEqual({ ok: true, valore: 50.5, errore: null });
    });

    it('rifiuta il vuoto', () => {
        const r = validaObiettivo('   ');
        expect(r.ok).toBe(false);
        expect(r.valore).toBeNull();
        expect(r.errore).toMatch(/inserisci/i);
    });

    it('rifiuta zero: l’obiettivo: valore non valido non salva', () => {
        const r = validaObiettivo('0');
        expect(r.ok).toBe(false);
        expect(r.valore).toBeNull();
        expect(r.errore).toMatch(/maggiore di zero/i);
    });

    it('rifiuta un negativo', () => {
        expect(validaObiettivo('-5').ok).toBe(false);
    });

    it('rifiuta testo non numerico', () => {
        const r = validaObiettivo('abc');
        expect(r.ok).toBe(false);
        expect(r.errore).toMatch(/due decimali/i);
    });

    it('rifiuta più di due decimali', () => {
        expect(validaObiettivo('50.999').ok).toBe(false);
    });

    it('rifiuta oltre il tetto', () => {
        const r = validaObiettivo(String(OBIETTIVO_MAX + 1));
        expect(r.ok).toBe(false);
        expect(r.errore).toMatch(/massimo/i);
    });

    it('accetta esattamente il tetto', () => {
        expect(validaObiettivo(String(OBIETTIVO_MAX)).ok).toBe(true);
    });

    // ── FALSIFICAZIONE (documentata nel referto: mutazione manuale del
    // codice sorgente `n <= 0` → `n < 0`, rieseguito, tornato rosso questo
    // test, poi ripristinato) ──────────────────────────────────────────────
    it('falsificazione: zero non deve MAI passare come valido', () => {
        expect(validaObiettivo('0').ok).toBe(false);
    });
});
