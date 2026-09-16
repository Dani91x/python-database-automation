// ============================================================================
// zeroPerAssente.test.ts — C.12b: I TRE PUNTI CHE MOSTRAVANO «0,00» PER ASSENTE.
//
// Reperto n. 5 della MATRICE_CONSAPEVOLEZZA_ORDINI_2026-09-16 (§8a):
//   1. `PlacedOrdersPanel.tsx:38`  `res?.size_matched ?? 0` → un ordine con
//      l'esito non ancora scritto compariva come «abbinato €0.00», cioe' come
//      un ordine NON abbinato;
//   2. `TerminalPositionsRail.tsx:203` `(o.size_remaining ?? 0).toFixed(2)` →
//      un residuo ignoto diventava «0.00», cioe' «ordine tutto abbinato», su un
//      ordine che sta ancora sul book;
//   3. `TerminalPositionsRail.tsx:230` `average_price_matched || price` → il
//      prezzo CHIESTO sostituiva in silenzio il prezzo MEDIO assente: due
//      numeri diversi sotto la stessa etichetta.
//
// La regola scritta sta in `lib/format.ts:44-54` («mai "0,00 €": un dato assente
// non e' uno zero»). Questo file la fa rispettare LEGGENDO I SORGENTI, come
// `designGuard.test.ts`: un fix a mano si riapre alla prossima modifica, una
// guardia che legge i file no.
//
// FALSIFICAZIONE: rimettere uno qualsiasi dei tre pattern rende rosso il test
// corrispondente (verificato il 16/09 prima di consegnare).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const SRC = (() => {
    for (const base of [process.cwd(), join(process.cwd(), 'frontend'), join(process.cwd(), '..')]) {
        const p = join(base, 'src');
        if (existsSync(join(p, 'lib', 'format.ts'))) return p;
    }
    throw new Error('cartella src/ non trovata');
})();

function sorgente(rel: string): string {
    return readFileSync(join(SRC, rel), 'utf-8');
}

/** righe che NON sono commento (un pattern citato in un commento non e' un bug) */
function righeVive(testo: string): string[] {
    return testo.split(/\r?\n/).filter((l) => !/^\s*(\/\/|\*|\/\*|\{\/\*)/.test(l));
}

const PANEL = 'components/watchlist/PlacedOrdersPanel.tsx';
const RAIL = 'components/live/TerminalPositionsRail.tsx';

describe('1. PlacedOrdersPanel — abbinato ASSENTE non diventa zero', () => {
    const righe = righeVive(sorgente(PANEL));

    it('nessun `size_matched ?? 0`', () => {
        const colpe = righe.filter((l) => /size_matched\s*\?\?\s*0\b/.test(l));
        expect(colpe, `assente trattato come zero:\n${colpe.join('\n')}`).toEqual([]);
    });

    it('l abbinato passa dai formatter unici, non da un `toFixed` locale', () => {
        const colpe = righe.filter((l) => /toFixed\(\s*2\s*\)/.test(l));
        expect(colpe, `denaro/quote fatti a mano:\n${colpe.join('\n')}`).toEqual([]);
        expect(sorgente(PANEL)).toMatch(/from '@\/lib\/format'/);
        expect(sorgente(PANEL)).toMatch(/abbinato \{fmtMoney\(matched\)\}/);
    });

    it('la guardia riconosce il vecchio comportamento', () => {
        // se un giorno qualcuno lo rimette, questa regex lo aggancia
        expect(/size_matched\s*\?\?\s*0\b/.test('const matched = res?.size_matched ?? 0;')).toBe(true);
        expect(/size_matched\s*\?\?\s*0\b/.test('const matched = res?.size_matched ?? null;')).toBe(false);
    });
});

describe('2-3. TerminalPositionsRail — residuo e prezzo medio assenti', () => {
    const testo = sorgente(RAIL);
    const righe = righeVive(testo);

    it('nessun `size_remaining ?? 0` e nessun `size_matched.toFixed`', () => {
        const colpe = righe.filter((l) => (
            /size_remaining\s*\?\?\s*0\b/.test(l) || /size_matched\.toFixed/.test(l)
        ));
        expect(colpe, `assente trattato come zero:\n${colpe.join('\n')}`).toEqual([]);
    });

    it('il prezzo MEDIO assente non viene sostituito dal prezzo chiesto', () => {
        const colpe = righe.filter((l) => /average_price_matched\s*\|\|/.test(l));
        expect(colpe, `prezzo medio sostituito in silenzio:\n${colpe.join('\n')}`).toEqual([]);
        expect(testo).toMatch(/fmtOdds\(prezzoMedio\(o\.average_price_matched\)\)/);
        // e uno 0 da Betfair (= prezzo medio inesistente) non diventa «0,00»
        expect(testo).toMatch(/v != null && v > 1 \? v : null/);
        expect(testo).toMatch(/fmtMoney\(o\.size_remaining\)/);
        expect(testo).toMatch(/fmtMoney\(o\.size_matched\)/);
    });

    it('la guardia riconosce il vecchio comportamento', () => {
        expect(/average_price_matched\s*\|\|/.test('{o.average_price_matched || o.price || \'—\'}')).toBe(true);
        expect(/average_price_matched\s*\|\|/.test('{fmtOdds(o.average_price_matched)}')).toBe(false);
        expect(/size_remaining\s*\?\?\s*0\b/.test('{(o.size_remaining ?? 0).toFixed(2)}')).toBe(true);
    });
});

describe('la regola scritta in lib/format resta quella', () => {
    it('fmtMoney(null) e fmtOdds(null) rendono il trattino, non uno zero', async () => {
        const { fmtMoney, fmtOdds, DASH } = await import('@/lib/format');
        expect(fmtMoney(null)).toBe(DASH);
        expect(fmtMoney(undefined)).toBe(DASH);
        expect(fmtOdds(null)).toBe(DASH);
        expect(fmtMoney(0)).toBe('0,00 €');   // uno zero VERO resta uno zero
    });
});
