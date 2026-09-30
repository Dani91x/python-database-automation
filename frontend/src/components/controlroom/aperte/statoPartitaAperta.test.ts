// ============================================================================
// statoPartitaAperta.test.ts - P15 (30/09): i fatti di oggi (progetto par. 0).
// Righe nella forma di `OperazionePartita` (useControlRoom) con l'ordine come
// `RigaOrdine` (lib/statoOrdine: status, side, price, size, size_requested,
// size_matched, size_remaining, avg_price_matched, betfair_updated_at, meta).
//   Follo: punta Under 3,5 5,00 @ 2,40 (5085) + banca Under 4,5 6,32 @ 1,76
//          (5094, copertura): con 4 gol esatti perdono entrambe -> -9,80
//   Farul: punta Under 3,5 5,00 @ 2,87 (5091) + banca green 5,06 @ 2,84 (5092,
//          chiusura sulla stessa selezione): pareggiata (+0,04 / +0,06)
// ============================================================================
import { describe, it, expect } from 'vitest';
import { statoPartitaAperta } from './statoPartitaAperta';
import { dueEsitiPartita, type OperazionePerCashOut } from '@/lib/cashOutPartita';

function ordine(side: 'back' | 'lay', price: number, size: number, matched = size) {
    return {
        status: 'open', side, price, size, size_requested: size, size_matched: matched,
        size_remaining: Math.round((size - matched) * 100) / 100, avg_price_matched: matched > 0 ? price : null,
        betfair_updated_at: null, meta: null,
    };
}

function op(over: Partial<OperazionePerCashOut> & { id: number }): OperazionePerCashOut {
    return {
        bot: 'mike', selezione: null, lato: 'back', modalita: 'live', marketId: null, selectionId: null,
        ordine: ordine('back', 2, 5), chiusureOrdini: [], chiusura: null, ...over,
    };
}

const DUE = (m: string) => m === '1.OU35' || m === '1.OU45';

const FOLLO = [
    op({ id: 5085, selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.OU35', selectionId: 35,
        ordine: ordine('back', 2.40, 5.00) }),
    op({ id: 5094, selezione: 'Under 4.5 Goals', lato: 'lay', marketId: '1.OU45', selectionId: 45,
        ordine: ordine('lay', 1.76, 6.32) }),
];

const FARUL = [
    op({ id: 5091, selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.OU35', selectionId: 35,
        ordine: ordine('back', 2.87, 5.00),
        chiusureOrdini: [ordine('lay', 2.84, 5.06)],
        chiusureGambe: [{ id: 5092, marketId: '1.OU35', selectionId: 35 }] }),
];
// punta e banca uguali alla stessa quota: ogni esito vale esattamente 0
const PARI = [
    op({ id: 5201, selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.OU35', selectionId: 35,
        ordine: ordine('back', 2.00, 5.00),
        chiusureOrdini: [ordine('lay', 2.00, 5.00)],
        chiusureGambe: [{ id: 5202, marketId: '1.OU35', selectionId: 35 }] }),
];

describe('statoPartitaAperta - i fatti del 30/09', () => {
    it('Follo: A RISCHIO, caso peggiore -9,80 (4 gol esatti)', () => {
        const r = statoPartitaAperta(FOLLO, { chiusa: false, dueEsiti: DUE });
        expect(r.stato).toBe('A RISCHIO');
        expect(r.casoPeggiore).toBe(-9.8);
        // fmtMoney: meno tipografico, virgola, euro (DESIGN_SYSTEM §1, mai toFixed)
        expect(r.dettaglio).toMatch(/caso peggiore −9,80 €/);
    });
    it('Farul: IN VERDE (ogni esito guadagna: caso peggiore > 0)', () => {
        const r = statoPartitaAperta(FARUL, { chiusa: false, dueEsiti: DUE });
        expect(r.stato).toBe('IN VERDE');
        expect(r.casoPeggiore).toBeGreaterThan(0);
    });
    it('caso peggiore esattamente 0: PAREGGIATA (nessuno perde, nessuno guadagna)', () => {
        // due gambe che si annullano al centesimo: punta e banca uguali sulla stessa selezione
        const r = statoPartitaAperta(PARI, { chiusa: false, dueEsiti: DUE });
        expect(r.stato).toBe('PAREGGIATA');
        expect(r.casoPeggiore).toBe(0);
    });
    it('partita chiusa col bot non ancora regolato: DA REGOLARE', () => {
        expect(statoPartitaAperta(FOLLO, { chiusa: true, dueEsiti: DUE }).stato).toBe('DA REGOLARE');
    });
    it('manca un dato (chiusura abbinata senza mercato): NON CALCOLABILE e lo dice', () => {
        const senza = [op({ ...FARUL[0], id: 5091, chiusureGambe: undefined })];
        const r = statoPartitaAperta(senza, { chiusa: false, dueEsiti: DUE });
        expect(r.stato).toBe('NON CALCOLABILE');
        expect(r.casoPeggiore).toBeNull();
        expect(r.dettaglio).toMatch(/mercato\/selezione non pubblicati/);
    });
    it('le gambe PROVA non entrano nello stato LIVE', () => {
        const r = statoPartitaAperta([...FOLLO.map((o) => ({ ...o, modalita: 'paper' as const })), ...FARUL],
            { chiusa: false, dueEsiti: DUE });
        expect(r.stato).toBe('IN VERDE');
    });
    it('nessun abbinato LIVE: NON CALCOLABILE (non "pareggiata")', () => {
        const r = statoPartitaAperta([op({ id: 1, marketId: '1.OU35', selectionId: 35, ordine: ordine('back', 2, 5, 0) })],
            { chiusa: false, dueEsiti: DUE });
        expect(r.stato).toBe('NON CALCOLABILE');
    });

    it('R2-4 tennis: back su P1 e su P2 nel Match Odds (due esiti) = coperta, NON «A RISCHIO −20»', () => {
        const tennis = [
            op({ id: 7001, bot: 'safe', selezione: 'Sinner', lato: 'back', marketId: '1.MO', selectionId: 1,
                ordine: ordine('back', 2.00, 10.00) }),
            op({ id: 7002, bot: 'safe', selezione: 'Alcaraz', lato: 'back', marketId: '1.MO', selectionId: 2,
                ordine: ordine('back', 2.00, 10.00) }),
        ];
        // come la pagina: `dueEsitiPartita('tennis', moMarketId, dueEsitiMike(...))`
        const r = statoPartitaAperta(tennis, { chiusa: false, dueEsiti: dueEsitiPartita('tennis', '1.MO', undefined) });
        expect(r.stato).toBe('PAREGGIATA');
        expect(r.casoPeggiore).toBe(0);
        // senza la regola dei due esiti lo stesso caso conterebbe «nessuno vince»
        expect(statoPartitaAperta(tennis, { chiusa: false }).stato).toBe('A RISCHIO');
    });
});
