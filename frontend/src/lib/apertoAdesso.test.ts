// ============================================================================
// apertoAdesso.test.ts - W_G/P6 (30/09): «aperto adesso» = SOMMA PER PARTITA
// del cash out LIVE (matematica di `cashOutPartita`), mai per riga; partite non
// calcolabili contate a parte, mai sommate in silenzio; paper mai dentro.
// Righe finte con la forma di `OperazionePartita` (come CashOutGlobale.test).
// Fatti del 30/09 (progetto §0/§5): Follo -0,82 (Mike, due gambe); Farul
// PAREGGIATA (punta Under 3,5 5,00 @2,87 + banca green 5,06 @2,84 abbinata).
// ============================================================================
import { describe, expect, it } from 'vitest';
import { apertoAdesso } from './apertoAdesso';
import type { OperazionePerCashOut } from './cashOutPartita';
import { PREZZO_VUOTO, type PrezzoScheda } from './schedaAlMs';

type Op = OperazionePerCashOut;
const ordine = (side: string, price: number, size: number) => ({
    status: 'open', side, price, size, size_requested: size, size_matched: size,
    size_remaining: 0, avg_price_matched: price, betfair_updated_at: null, meta: null,
});
function op(p: Partial<Op> & Pick<Op, 'id' | 'bot'>): Op {
    return {
        selezione: null, lato: 'back', modalita: 'live', marketId: null, selectionId: null,
        ordine: ordine('back', 2, 5), chiusureOrdini: [], chiusura: { alMs: { aliquota: 0.05 } },
        ...p,
    } as Op;
}
const FOLLO: Op[] = [
    op({ id: 5085, bot: 'mike', selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.35', selectionId: 11,
        ordine: ordine('back', 2.4, 5) }),
    op({ id: 5094, bot: 'mike', selezione: 'Under 4.5 Goals', lato: 'lay', marketId: '1.45', selectionId: 21,
        ordine: ordine('lay', 1.76, 6.32) }),
];
const FARUL: Op[] = [
    op({ id: 5091, bot: 'mike', selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.91', selectionId: 31,
        ordine: ordine('back', 2.87, 5),
        chiusureOrdini: [ordine('lay', 2.84, 5.06)],
        chiusureGambe: [{ id: 5092, marketId: '1.91', selectionId: 31 }] }),
];
const LIBRO: Record<string, Partial<PrezzoScheda>> = {
    '1.35|11': { back: 2.46, backSize: 80, lay: 2.56, laySize: 60 },
    '1.45|21': { back: 1.63, backSize: 90, lay: 1.68, laySize: 70 },
    '1.91|31': { back: 2.8, backSize: 90, lay: 2.9, laySize: 70 },
};
const prezzo = (libro: Record<string, Partial<PrezzoScheda>>) =>
    (_e: string, m: string, s: number): PrezzoScheda | null => {
        const p = libro[`${m}|${s}`];
        return p ? { ...PREZZO_VUOTO, fonte: 'scanner', istanteMs: 1, statoMercato: 'OPEN', ...p } : null;
    };

describe('apertoAdesso - somma PER PARTITA del cash out LIVE', () => {
    it('Follo -0,82 (due gambe di Mike, una partita)', () => {
        const a = apertoAdesso({ operazioni: new Map([['E1', FOLLO]]), prezzo: prezzo(LIBRO), nowMs: 2 });
        expect(a).toEqual({ netto: -0.82, partite: 1, nonCalcolabili: 0,
            perBot: { mike: { netto: -0.82, partite: 1, nonCalcolabili: 0 } },
            etaPrezziS: 0.001, calcolatoAlMs: 2 });
    });

    it('Farul PAREGGIATA: la chiusura abbinata netta la punta (quasi 0), non la si conta aperta', () => {
        const a = apertoAdesso({ operazioni: new Map([['E3', FARUL]]), prezzo: prezzo(LIBRO), nowMs: 2 });
        expect(a.partite).toBe(1);
        expect(Math.abs(a.netto as number)).toBeLessThan(0.1);
        // pareggiata in utile su entrambi gli esiti: >= 0. La sola punta (per RIGA,
        // senza la chiusura che la netta) darebbe una perdita (~ -0,05)
        expect(a.netto as number).toBeGreaterThanOrEqual(0);
    });

    it('partita NON calcolabile (manca un prezzo): contata a parte, fuori dalla somma', () => {
        const senza = { ...LIBRO };
        delete senza['1.45|21'];
        const a = apertoAdesso({
            operazioni: new Map([['E1', FOLLO], ['E3', FARUL]]), prezzo: prezzo(senza), nowMs: 2,
        });
        expect(a.nonCalcolabili).toBe(1);
        expect(a.partite).toBe(1);
        expect(Math.abs(a.netto as number)).toBeLessThan(0.1);   // solo Farul
    });

    it('solo paper: nessuna partita LIVE, cifra null', () => {
        const a = apertoAdesso({
            operazioni: new Map([['E1', FOLLO.map((o) => ({ ...o, modalita: 'paper' as const }))]]),
            prezzo: prezzo(LIBRO), nowMs: 2,
        });
        expect(a).toEqual({ netto: null, partite: 0, nonCalcolabili: 0, perBot: {}, etaPrezziS: null, calcolatoAlMs: 2 });
    });

    it('R2-2: eta\' dei prezzi = il prezzo PIU\' VECCHIO fra le partite calcolabili, all\'istante del calcolo', () => {
        const libro = { ...LIBRO, '1.35|11': { ...LIBRO['1.35|11'], istanteMs: 0 }, '1.45|21': { ...LIBRO['1.45|21'], istanteMs: 20_000 } };
        const a = apertoAdesso({ operazioni: new Map([['E1', FOLLO]]), prezzo: prezzo(libro), nowMs: 30_000 });
        expect(a.netto).toBe(-0.82);
        expect(a.etaPrezziS).toBe(30);
        expect(a.calcolatoAlMs).toBe(30_000);
    });
});
