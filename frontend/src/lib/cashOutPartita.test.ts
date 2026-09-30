// ============================================================================
// cashOutPartita.test.ts - 30/09 (P12a): il cash out della partita, tabellare.
//
// Casi: Follo v Sarpsborg di oggi (-0,82), partita pareggiata (~+0,05, una
// cifra sola), gamba senza prezzo (NON CALCOLABILE), gamba PROVA (mai nel
// live), utile e perdita sullo stesso mercato (commissione sul netto del
// mercato), parita' numerica con `Betfair/mike/engine.py::cashout_value` su 4
// casi presi dai test Python (file:riga nel titolo del test).
//
// FALSIFICAZIONE (script `AUDIT_2026-09-30/ui_blocchi/falsifica_c_p12a.sh`):
// somma per riga invece che per selezione, commissione per gamba, gamba senza
// prezzo contata 0, paper sommato al live, rovescio dell'altra selezione tolto
// -> rossi.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { cashOutPartita, gambeDaOperazioni, r2, type GambaViva, type OpzioniCashOut } from './cashOutPartita';
import { PREZZO_VUOTO, type PrezzoScheda } from './schedaAlMs';
import type { OperazionePartita } from '@/components/controlroom/useControlRoom';

const NOW = 1_800_000_000_000;

function gamba(p: Partial<GambaViva> & Pick<GambaViva, 'id' | 'marketId' | 'selectionId' | 'lato' | 'abbinato' | 'prezzoMedio'>): GambaViva {
    return {
        bot: 'mike', modalita: 'live', selezione: null, aliquota: 0.05, ...p,
    };
}

type Libro = Record<string, Partial<PrezzoScheda>>;
function opz(libro: Libro, extra: Partial<OpzioniCashOut> = {}): OpzioniCashOut {
    return {
        prezzo: (m, s) => {
            const p = libro[`${m}|${s}`];
            return p ? { ...PREZZO_VUOTO, fonte: 'canale', istanteMs: NOW - 300, statoMercato: 'OPEN', ...p } : null;
        },
        nowMs: NOW,
        ...extra,
    };
}

// ------------------------------------------------ Follo v Sarpsborg (30/09)
// punta Under 3,5 5,00 @ 2,40 (OU35, sel 11) + banca Under 4,5 6,32 @ 1,76
// (copertura, OU45, sel 21). Ladder: Under 3,5 B 2,46 / L 2,56; Under 4,5
// B 1,63 / L 1,68.
const FOLLO: GambaViva[] = [
    gamba({ id: 5085, marketId: '1.35', selectionId: 11, selezione: 'Under 3.5 Goals', lato: 'back',
        abbinato: 5.0, prezzoMedio: 2.4, dueEsiti: true }),
    gamba({ id: 5094, marketId: '1.45', selectionId: 21, selezione: 'Under 4.5 Goals', lato: 'lay',
        abbinato: 6.32, prezzoMedio: 1.76, dueEsiti: true }),
];
const LIBRO_FOLLO: Libro = {
    '1.35|11': { back: 2.46, backSize: 80, lay: 2.56, laySize: 60 },
    '1.45|21': { back: 1.63, backSize: 90, lay: 1.68, laySize: 70 },
};

describe('Follo v Sarpsborg: -0,32 e -0,50, totale -0,82', () => {
    const r = cashOutPartita(FOLLO, opz(LIBRO_FOLLO));
    it('la cifra della partita e\' la somma esatta delle due gambe', () => {
        expect(r.live.netto).toBe(-0.82);
        expect(r.live.lordo).toBe(-0.82);
        expect(r.live.commissione).toBe(0);
        expect(r.live.completo).toBe(true);
        expect(r.live.mancanti).toEqual([]);
        expect(r.live.nGambe).toBe(2);
    });
    it('scomposizione: chiudo banca 4,69 @ 2,56 (-0,32) e punta 6,82 @ 1,63 (-0,50)', () => {
        const [u35, u45] = r.live.gambe;
        expect(u35).toMatchObject({ selezione: 'Under 3.5 Goals', lato: 'back', abbinato: 5, prezzoIngresso: 2.4,
            latoChiusura: 'lay', importoChiusura: 4.69, prezzoChiusura: 2.56, pnl: -0.32, pnlLordo: -0.32,
            fontePrezzo: 'canale', liquiditaSufficiente: true, stato: 'da_chiudere', bot: ['mike'] });
        expect(u45).toMatchObject({ selezione: 'Under 4.5 Goals', lato: 'lay', abbinato: 6.32, prezzoIngresso: 1.76,
            latoChiusura: 'back', importoChiusura: 6.82, prezzoChiusura: 1.63, pnl: -0.5, stato: 'da_chiudere' });
        expect(u35.etaPrezzoS).toBeCloseTo(0.3, 5);
        expect(r.live.etaPrezziS).toBeCloseTo(0.3, 5);
    });
    it('il paper e\' vuoto e vale 0 (nessuna gamba PROVA)', () => {
        expect(r.paper.netto).toBe(0);
        expect(r.paper.nGambe).toBe(0);
    });
});

describe('partita PAREGGIATA: una cifra sola ~ +0,05, non due gambe in perdita', () => {
    // Farul: punta Under 3,5 5,00 @ 2,87 + banca 5,06 @ 2,84 sulla STESSA selezione
    const g = [
        gamba({ id: 5091, marketId: '1.9', selectionId: 5, selezione: 'Under 3.5 Goals', lato: 'back', abbinato: 5, prezzoMedio: 2.87 }),
        gamba({ id: 5092, marketId: '1.9', selectionId: 5, selezione: 'Under 3.5 Goals', lato: 'lay', abbinato: 5.06, prezzoMedio: 2.84 }),
    ];
    it('W = 9,35 - 9,31 = 0,04, L = 0,06: chiusura 0,01 @ 2,84 -> +0,05', () => {
        const r = cashOutPartita(g, opz({ '1.9|5': { back: 2.84, backSize: 30, lay: 2.9, laySize: 30 } }));
        expect(r.live.gambe).toHaveLength(1);
        expect(r.live.gambe[0]).toMatchObject({ seVince: 0.04, sePerde: 0.06, importoChiusura: 0.01, pnlLordo: 0.05 });
        expect(r.live.netto).toBe(0.05);
        expect(r.live.gambe[0].componenti.map((c) => c.id)).toEqual([5091, 5092]);
    });
    it('perfettamente piatta: vale il bloccato senza pretendere un prezzo', () => {
        const piatta = [
            gamba({ id: 1, marketId: '1.9', selectionId: 5, lato: 'back', abbinato: 10, prezzoMedio: 2.0 }),
            gamba({ id: 2, marketId: '1.9', selectionId: 5, lato: 'lay', abbinato: 10, prezzoMedio: 2.0 }),
        ];
        const r = cashOutPartita(piatta, opz({}));
        expect(r.live.gambe[0].stato).toBe('piatta');
        expect(r.live.netto).toBe(0);
        expect(r.live.completo).toBe(true);
    });
});

describe('FAIL-CLOSED: una gamba viva senza prezzo -> nessuna cifra', () => {
    it('manca il prezzo di Under 4,5: netto null, completo false, la selezione in mancanti', () => {
        const r = cashOutPartita(FOLLO, opz({ '1.35|11': LIBRO_FOLLO['1.35|11'] }));
        expect(r.live.netto).toBeNull();
        expect(r.live.lordo).toBeNull();
        expect(r.live.completo).toBe(false);
        expect(r.live.mancanti).toEqual(['manca il prezzo di Under 4.5 Goals (punta)']);
        // la gamba che il prezzo ce l'ha resta scomposta, quella senza no
        expect(r.live.gambe[0].pnl).toBe(-0.32);
        expect(r.live.gambe[1].stato).toBe('senza_prezzo');
        expect(r.live.gambe[1].pnl).toBeNull();
    });
    it('c\'e\' il lato opposto ma non quello di chiusura: non si inventa', () => {
        const r = cashOutPartita(FOLLO, opz({ ...LIBRO_FOLLO, '1.45|21': { lay: 1.68, laySize: 50 } }));
        expect(r.live.netto).toBeNull();
    });
    it('mercato SOSPESO: adesso non si chiude, nessuna cifra', () => {
        const r = cashOutPartita(FOLLO, opz({ ...LIBRO_FOLLO, '1.35|11': { ...LIBRO_FOLLO['1.35|11'], statoMercato: 'SUSPENDED' } }));
        expect(r.live.netto).toBeNull();
        expect(r.live.mancanti).toEqual(['mercato SOSPESO per Under 3.5 Goals: adesso non si chiude']);
    });
    it('gamba abbinata senza mercato/selezione (riga storica): nessuna cifra', () => {
        const r = cashOutPartita([...FOLLO, gamba({ id: 77, marketId: null, selectionId: null, selezione: 'Over 4.5',
            lato: 'back', abbinato: 2, prezzoMedio: 5 })], opz(LIBRO_FOLLO));
        expect(r.live.netto).toBeNull();
        expect(r.live.mancanti).toEqual(['mercato/selezione non pubblicati: mike #77 (Over 4.5)']);
    });
    it('importo abbinato NON dichiarato: nessuna cifra (non e\' zero)', () => {
        const r = cashOutPartita([gamba({ id: 9, marketId: '1.9', selectionId: 5, selezione: 'X', lato: 'back',
            abbinato: null, prezzoMedio: 2 })], opz({}));
        expect(r.live.netto).toBeNull();
    });
    it('gamba NON scomponibile (sessione scalper) abbinata: nessuna cifra, col motivo', () => {
        const r = cashOutPartita([...FOLLO, gamba({ id: 3, bot: 'scalper', marketId: null, selectionId: null, lato: null,
            abbinato: 4, prezzoMedio: null, nonScomponibile: 'sessione scalper: esposizioni per selezione non pubblicate alla scheda' })],
        opz(LIBRO_FOLLO));
        expect(r.live.netto).toBeNull();
        expect(r.live.mancanti).toEqual(['scalper #3: sessione scalper: esposizioni per selezione non pubblicate alla scheda']);
    });
});

describe('solo l\'ABBINATO e\' una posizione', () => {
    it('residuo sul book (abbinato 0) non entra; parziale 2 su 5 conta 2', () => {
        const r = cashOutPartita([
            gamba({ id: 1, marketId: '1.9', selectionId: 5, selezione: 'U', lato: 'back', abbinato: 0, prezzoMedio: 2.0 }),
            gamba({ id: 2, marketId: '1.9', selectionId: 6, selezione: 'O', lato: 'back', abbinato: 2, prezzoMedio: 3.0 }),
        ], opz({ '1.9|6': { back: 2.9, lay: 3.0, laySize: 50 } }));
        expect(r.live.nGambe).toBe(1);
        expect(r.live.gambe).toHaveLength(1);
        // W 4, L -2: banca 2,00 @ 3,00 -> 0,00 / 0,00
        expect(r.live.gambe[0]).toMatchObject({ importoChiusura: 2, pnlLordo: 0 });
    });
});

describe('LIVE e PROVA: due somme, mai una', () => {
    const prova = gamba({ id: 900, bot: 'safe', modalita: 'paper', marketId: '1.35', selectionId: 11,
        selezione: 'Under 3.5 Goals', lato: 'back', abbinato: 10, prezzoMedio: 2.2 });
    const r = cashOutPartita([...FOLLO, prova], opz(LIBRO_FOLLO));
    it('la gamba PROVA sulla stessa selezione NON tocca il live', () => {
        expect(r.live.netto).toBe(-0.82);
        expect(r.live.gambe.flatMap((p) => p.componenti.map((c) => c.id))).toEqual([5085, 5094]);
    });
    it('il paper ha la sua cifra: back 10 @ 2,20 chiuso banca 8,59 @ 2,56 -> -1,41', () => {
        // W 12, L -10: importo 22/2,56 = 8,59; 8,59 x 1,56 = 13,40 -> W2 = -1,40; L2 = -10 + 8,59 = -1,41
        expect(r.paper.gambe[0]).toMatchObject({ importoChiusura: 8.59, bot: ['safe'] });
        expect(r.paper.netto).toBe(r2(Math.min(12 - 13.4, -10 + 8.59)));
        expect(r.paper.netto).toBe(-1.41);
    });
    it('modalita\' NON dichiarata: il LIVE non si calcola (potrebbero essere soldi veri)', () => {
        const x = cashOutPartita([...FOLLO, { ...prova, modalita: null }], opz(LIBRO_FOLLO));
        expect(x.live.netto).toBeNull();
        expect(x.live.mancanti).toEqual(['modalita\' non dichiarata: safe #900 (Under 3.5 Goals)']);
        expect(x.paper.netto).toBe(0);
    });
});

describe('commissione per MERCATO sul netto, non per gamba', () => {
    // mercato a piu' esiti (risultato esatto): A back 10 @ 3,0 -> +2,00;
    // B back 10 @ 4,0 -> -0,91. Netto mercato 1,09 -> commissione 0,05 -> 1,04.
    // Per gamba sarebbe 2,00 x 0,95 - 0,91 = 0,99.
    const g = [
        gamba({ id: 1, bot: 'omega', marketId: '1.7', selectionId: 1, selezione: '1 - 0', lato: 'back', abbinato: 10, prezzoMedio: 3.0 }),
        gamba({ id: 2, bot: 'omega', marketId: '1.7', selectionId: 2, selezione: '2 - 1', lato: 'back', abbinato: 10, prezzoMedio: 4.0 }),
    ];
    const r = cashOutPartita(g, opz({ '1.7|1': { lay: 2.5, laySize: 100 }, '1.7|2': { lay: 4.4, laySize: 100 } }));
    it('lordo 1,09, commissione 0,05, netto 1,04', () => {
        expect(r.live.gambe.map((p) => p.pnlLordo)).toEqual([2, -0.91]);
        expect(r.live.lordo).toBe(1.09);
        expect(r.live.commissione).toBe(0.05);
        expect(r.live.netto).toBe(1.04);
        expect(r.live.perMercato).toEqual([{ marketId: '1.7', lordo: 1.09, aliquota: 0.05, commissione: 0.05, netto: 1.04 }]);
    });
    it('le righe sommano il netto (commissione ripartita sulle selezioni in utile)', () => {
        expect(r.live.gambe.map((p) => p.pnl)).toEqual([1.95, -0.91]);
        expect(r2(r.live.gambe.reduce((s, p) => s + (p.pnl ?? 0), 0))).toBe(r.live.netto);
    });
    it('aliquote diverse fra le righe: la piu\' alta, dichiarata', () => {
        const x = cashOutPartita([g[0], { ...g[1], aliquota: 0.02 }],
            opz({ '1.7|1': { lay: 2.5, laySize: 100 }, '1.7|2': { lay: 4.4, laySize: 100 } }));
        expect(x.live.commissione).toBe(0.05);
        expect(x.live.avvisi[0]).toMatch(/aliquote diverse/);
    });
});

describe('liquidita\' al miglior prezzo', () => {
    it('meno dell\'importo di chiusura: la cifra resta, con l\'avviso «caso migliore»', () => {
        const r = cashOutPartita(FOLLO, opz({ ...LIBRO_FOLLO, '1.35|11': { back: 2.46, lay: 2.56, laySize: 3 } }));
        expect(r.live.netto).toBe(-0.82);
        expect(r.live.liquiditaInsufficiente).toBe(true);
        expect(r.live.gambe[0].liquiditaSufficiente).toBe(false);
        expect(r.live.avvisi.some((a) => /liquidita' insufficiente.*Under 3.5 Goals.*caso migliore/.test(a))).toBe(true);
    });
    it('eta\' ignota di un prezzo: dichiarata', () => {
        const o = opz(LIBRO_FOLLO);
        const r = cashOutPartita(FOLLO, { ...o, prezzo: (m, s) => {
            const p = o.prezzo(m, s);
            return p && s === 21 ? { ...p, istanteMs: null } : p;
        } });
        expect(r.live.etaIgnota).toBe(true);
        expect(r.live.netto).toBe(-0.82);
    });
});

// ===================================================================
// PARITA' con Betfair/mike/engine.py::cashout_value (commissione 0,05)
// ===================================================================
describe('parita\' numerica con engine.cashout_value (test Python, sola lettura)', () => {
    it('test_mike_engine.py:167-180 - back Under 3,5 20 @ 1,50, lay 1,40: net 1,36; senza libro incompleto', () => {
        // Python: w,l = (10, -20); locked = -20 + 30/1,40; net = locked * 0,95 (approx 0,02)
        // engine esatto: size 21,43 -> esiti 1,43 / 1,43 -> gross 1,43, net round(1,3585) = 1,36
        const g = [gamba({ id: 'e1', marketId: 'OU35', selectionId: 1, selezione: 'Under 3.5', lato: 'back', abbinato: 20, prezzoMedio: 1.5 })];
        const r = cashOutPartita(g, opz({ 'OU35|1': { back: 1.39, lay: 1.4, laySize: 100 } }));
        expect(r.live.lordo).toBe(1.43);
        expect(r.live.netto).toBe(1.36);
        expect(r.live.completo).toBe(true);
        const r2x = cashOutPartita(g, opz({}));
        expect(r2x.live.completo).toBe(false);
        expect(r2x.live.netto).toBeNull();
    });
    it('test_mike_engine_cert_2026_09_12.py:178-187 - Under 3,5 + Over 4,5 (un mercato ciascuno): net 1,31', () => {
        // engine: OU35 banca 22,90 @ 1,31 -> 2,90; OU45 Over banca 2,56 @ 12,5 -> -1,44;
        // net = round(2,90 x 0,95 - 1,44) = 1,31
        const g = [
            gamba({ id: 'e1', marketId: 'OU35', selectionId: 1, selezione: 'Under 3.5', lato: 'back', abbinato: 20, prezzoMedio: 1.5, dueEsiti: true }),
            gamba({ id: 'c1', marketId: 'OU45', selectionId: 2, selezione: 'Over 4.5', lato: 'back', abbinato: 4, prezzoMedio: 8.0, dueEsiti: true }),
        ];
        const r = cashOutPartita(g, opz({ 'OU35|1': { back: 1.3, lay: 1.31, laySize: 100 }, 'OU45|2': { back: 12.0, lay: 12.5, laySize: 100 } }));
        expect(r.live.gambe.map((p) => [p.importoChiusura, p.pnlLordo])).toEqual([[22.9, 2.9], [2.56, -1.44]]);
        expect(r.live.netto).toBe(1.31);
    });
    it('test_mike_engine_cert_2026_09_12.py:164-174 - Over 4,5 + Under 4,5 sullo STESSO mercato: una chiave, net 1,81', () => {
        // engine P5: exposure(UNDER) = (0, 18) -> chiave OVER (18, 0), banca 1,91 @ 9,4
        // -> esiti 1,96 / 1,91 -> gross 1,91 -> net round(1,91 x 0,95) = 1,81
        const g = [
            gamba({ id: 'c1', marketId: 'OU45', selectionId: 2, selezione: 'Over 4.5', lato: 'back', abbinato: 4, prezzoMedio: 8.0, dueEsiti: true }),
            gamba({ id: 'r1', marketId: 'OU45', selectionId: 1, selezione: 'Under 4.5', lato: 'back', abbinato: 10, prezzoMedio: 1.4, dueEsiti: true }),
        ];
        const r = cashOutPartita(g, opz({ 'OU45|2': { back: 9.0, lay: 9.4, laySize: 100 }, 'OU45|1': { back: 1.3, lay: 1.32, laySize: 100 } }));
        expect(r.live.gambe).toHaveLength(1);
        expect(r.live.gambe[0]).toMatchObject({ selectionId: 2, seVince: 18, sePerde: 0, latoChiusura: 'lay',
            importoChiusura: 1.91, prezzoChiusura: 9.4, pnlLordo: 1.91 });
        expect(r.live.netto).toBe(1.81);
    });
    it('test_mike_engine_cert_2026_09_12.py:303-316 - Under 3,5 gia\' PERSA (4 gol, linea potata): completo, net -8,75', () => {
        // engine C2: Under 3,5 decisa = -20 senza prezzo; Over banca 15,84 @ 2,02 -> 11,84;
        // net = -20 + 11,84 x 0,95 = -8,752 -> -8,75
        const g = [
            gamba({ id: 'e1', marketId: 'OU35', selectionId: 1, selezione: 'Under 3.5', lato: 'back', abbinato: 20, prezzoMedio: 1.5 }),
            gamba({ id: 'c1', marketId: 'OU45', selectionId: 2, selezione: 'Over 4.5', lato: 'back', abbinato: 4, prezzoMedio: 8.0 }),
        ];
        const r = cashOutPartita(g, opz({ 'OU45|2': { back: 2.0, lay: 2.02, laySize: 100 } }, {
            esitoDeciso: (m, s) => (m === 'OU35' && s === 1 ? false : null),
        }));
        expect(r.live.completo).toBe(true);
        expect(r.live.gambe[0]).toMatchObject({ stato: 'decisa', pnlLordo: -20 });
        expect(r.live.gambe[1]).toMatchObject({ importoChiusura: 15.84, pnlLordo: 11.84 });
        expect(r.live.netto).toBe(-8.75);
    });
});

// ===================================================================
// DALLE RIGHE DELLA SCHEDA (OperazionePartita VERA, stesse chiavi)
// ===================================================================
function op(p: Partial<OperazionePartita> & Pick<OperazionePartita, 'id' | 'bot'>): OperazionePartita {
    return {
        selezione: null, lato: 'back', prezzo: 2, size: 5, stato: 'open', pnl: null, modalita: 'live',
        at: '2026-09-30T14:00:00.000Z', quale: null,
        ordine: { status: 'open', side: 'back', price: 2, size: 5, size_requested: 5, size_matched: 5,
            size_remaining: 0, avg_price_matched: 2, betfair_updated_at: null, meta: null },
        dettaglio: null, marketId: null, selectionId: null, liability: null, vivo: null, etaQuoteS: null,
        chiusura: null, chiusureOrdini: [], eventId: '35001', chiudeId: null,
        ...p,
    };
}
const ordine = (side: 'back' | 'lay', price: number, chiesto: number, abbinato: number | null, status = 'open'): OperazionePartita['ordine'] => ({
    status, side, price, size: chiesto, size_requested: chiesto, size_matched: abbinato,
    size_remaining: abbinato == null ? null : Math.max(0, chiesto - abbinato),
    avg_price_matched: abbinato ? price : null, betfair_updated_at: null, meta: null,
});
const alMs = (aliquota: number): OperazionePartita['chiusura'] => ({
    lato: 'lay', prezzo: null, abbinabile: null, bloccabile: null,
    alMs: { win: 0, lose: 0, marketId: null, selectionId: null, sport: 'calcio', istanteScannerMs: null,
        scanner: { back: null, backSize: null, lay: null, laySize: null }, aliquota },
});

describe('gambeDaOperazioni: le righe della scheda di TUTTI i bot', () => {
    // Follo: la punta Under 3,5 con due tentativi di green-up MAI abbinati
    // (righe `error`, ritirate da Mike) + la banca Under 4,5 di copertura
    const follo: OperazionePartita[] = [
        op({ id: 5085, bot: 'mike', selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.35', selectionId: 11,
            ordine: ordine('back', 2.4, 5, 5), chiusura: alMs(0.05),
            chiusureOrdini: [ordine('lay', 2.36, 5.08, 0, 'error'), ordine('lay', 2.36, 5.08, null, 'error')] }),
        op({ id: 5094, bot: 'mike', selezione: 'Under 4.5 Goals', lato: 'lay', marketId: '1.45', selectionId: 21,
            ordine: ordine('lay', 1.76, 6.32, 6.32), chiusura: alMs(0.05) }),
    ];
    it('Follo: i tentativi mai abbinati non contano, cifra -0,82', () => {
        const g = gambeDaOperazioni(follo);
        expect(g.map((x) => x.id)).toEqual([5085, 5094]);
        expect(cashOutPartita(g, opz(LIBRO_FOLLO)).live.netto).toBe(-0.82);
    });
    it('Farul: la chiusura (green) con i SUOI id netta l\'apertura: +0,05', () => {
        const farul = op({ id: 5091, bot: 'mike', selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.9', selectionId: 5,
            ordine: ordine('back', 2.87, 5, 5), chiusura: alMs(0.05),
            chiusureOrdini: [ordine('lay', 2.84, 5.06, 5.06)] });
        const conId = { ...farul, chiusureGambe: [{ id: 5092, marketId: '1.9', selectionId: 5 }] };
        const r = cashOutPartita(gambeDaOperazioni([conId]), opz({ '1.9|5': { back: 2.84, lay: 2.9, laySize: 30 } }));
        expect(r.live.netto).toBe(0.05);
        expect(r.live.gambe[0].componenti.map((c) => c.id)).toEqual([5091, 5092]);
    });
    it('Farul SENZA gli id della chiusura (oggi la pagina non li porta): NON calcolabile, lo dice', () => {
        const farul = op({ id: 5091, bot: 'mike', selezione: 'Under 3.5 Goals', lato: 'back', marketId: '1.9', selectionId: 5,
            ordine: ordine('back', 2.87, 5, 5), chiusureOrdini: [ordine('lay', 2.84, 5.06, 5.06)] });
        const r = cashOutPartita(gambeDaOperazioni([farul]), opz({ '1.9|5': { back: 2.84, lay: 2.9, laySize: 30 } }));
        expect(r.live.netto).toBeNull();
        expect(r.live.mancanti).toEqual(['mercato/selezione non pubblicati: mike #5091/chiusura 1 (selezione ignota)']);
    });
    it('riga REGOLATA fuori; parziale conta l\'abbinato; PROVA nella sua somma; scalper dichiarato', () => {
        const g = gambeDaOperazioni([
            op({ id: 1, bot: 'safe', marketId: '1.9', selectionId: 5, ordine: ordine('back', 2, 5, 5, 'won') }),
            op({ id: 2, bot: 'omega', marketId: '1.7', selectionId: 1, ordine: ordine('back', 3, 5, 2, 'pending') }),
            op({ id: 3, bot: 'safe', modalita: 'paper', marketId: '1.9', selectionId: 5, ordine: ordine('back', 2, 5, 5) }),
            op({ id: 4, bot: 'scalper', lato: null, ordine: { ...ordine('back', 2, 5, 5), side: null } }),
        ]);
        expect(g.map((x) => x.id)).toEqual([2, 3, 4]);
        expect(g[0].abbinato).toBe(2);
        expect(g[1].modalita).toBe('paper');
        expect(g[2].nonScomponibile).toMatch(/scalper/);
    });
    it('aliquota dalla riga (P11: chiusura.alMs.aliquota) e mercato a due esiti dal chiamante', () => {
        const g = gambeDaOperazioni(follo, { dueEsiti: (m) => m === '1.45' });
        expect(g.map((x) => [x.aliquota, x.dueEsiti])).toEqual([[0.05, false], [0.05, true]]);
    });
});

describe('r2: il centesimo come Betfair', () => {
    it('meta\' centesimo e segni', () => {
        expect(r2(0.145)).toBe(0.15);
        expect(r2(-0.5066)).toBe(-0.51);
        expect(r2(0.0025)).toBe(0);
        expect(r2(7.3164)).toBe(7.32);
        expect(r2(-4.8032)).toBe(-4.8);
    });
});
