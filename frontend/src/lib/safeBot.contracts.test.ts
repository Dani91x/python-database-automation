// ============================================================================
// Test dei CONTRATTI servizio ↔ UI aggiunti dopo l'indagine dell'11/09/2026:
//   R1    cash out su TUTTI i mercati del feed (Over/Under, BTTS, 1X2 1T)
//   C-02  copertura parziale: il residuo resta chiudibile
//   H-05  stato dell'uscita automatica (ritento / attesa prezzo / fallita)
//   M-04  una sola notifica per POSIZIONE regolata
//   M-15  "posizione viva": mai le chiusure, mai le hedged complete
//   L-07  esito leggibile di OGNI richiesta operativa
// più i delta del backend dell'11/09 sera: copertura IN VOLO = rischio ancora
// pieno, stop perdita col segno indifferente, combinazione incompleta, linee
// Over/Under tenute nel feed solo per una posizione di Mike (`decided`).
// Tutto PURO: nessuna rete, nessun componente.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { greenPrice, hedgeSide } from '@/components/trading/CashOutButton';
import { isUsableBlock, usableMarketBlocks, scanMarketBlocks } from './safeStrategyScan';
import {
    aggregatesHaveDay,
    holdReasonLabel, holdReasonHasP, tradeHold,
    safeTradeBook, marketBlocked, hedgeState, tradeExposureNow, exitRunState,
    isReconciling, errorFinal, blindSince, comboIncomplete, isLivePosition,
    normalizeLossStop, tradeCommission, requestOutcome, lastRequestFor,
    detectSettlements, cashoutInFlight,
    type SafeTrade,
} from './safeBot';

function trade(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'manual',
        market_id: '1.30', market_type: 'OVER_UNDER_35', selection_id: 47973, selection_name: 'Under',
        side: 'back', mode: 'paper', price: 1.38, size: 10, liability: 10, commission: 0.05,
        minute_at_entry: 60, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-11T18:00:00Z', settled_at: null, origin: 'manual',
        closes_trade_id: null, signal_key: null, meta: null,
        ...over,
    };
}

// --------------------------------------------------------------------- feed
const OU_SEL = (over: number, under: number) => ([
    { selection_id: 47972, name: 'Over', runner_status: 'ACTIVE', back: over, lay: over + 0.03, back_size: 120, lay_size: 90 },
    { selection_id: 47973, name: 'Under', runner_status: 'ACTIVE', back: under, lay: under + 0.06, back_size: 80, lay_size: 60 },
]);

/** payload REALE-LIKE dello scanner: cs + ht + i mercati a gol delle opportunità */
const GOALS_PAYLOAD = {
    media: null, event_name: 'Roma vs Lazio', home: 'Roma', away: 'Lazio',
    competition: 'Serie A', open_date: null, inplay: true,
    mo_market_id: '1.1', mo_status: 'OPEN',
    odds: {
        home: { selection_id: 11, back: 1.3, lay: 1.32, back_size: 250, lay_size: 180 },
        draw: { selection_id: 58805, back: 5, lay: 5.2 },
        away: { selection_id: 12, back: 9, lay: 9.4 },
    },
    minute: 62, score_home: 1, score_away: 0, red_home: 0, red_away: 0, pre_ko: null,
    cs: {
        market_id: '1.5', status: 'OPEN',
        selections: [{ selection_id: 77, name: 'Any Other Home Win', back: 38, lay: 42 }],
        any_other_home: null, any_other_away: null,
    },
    ht: { market_id: '1.7', status: 'OPEN', selections: [{ selection_id: 55, name: '1 - 0', back: 3, lay: 3.1 }] },
    ou: [
        { market_id: '1.20', status: 'OPEN', market_type: 'OVER_UNDER_25', line: 2.5, inplay: true, total_matched: 12000, ts_ms: 1, bet_delay: 5, selections: OU_SEL(1.8, 2.2) },
        { market_id: '1.30', status: 'OPEN', market_type: 'OVER_UNDER_35', line: 3.5, inplay: true, total_matched: 8000, selections: OU_SEL(3.4, 1.38) },
        // linea GIÀ DECISA dal punteggio: lo scanner la tiene solo per Mike
        { market_id: '1.40', status: 'OPEN', market_type: 'OVER_UNDER_45', line: 4.5, decided: true, for_mike: true, selections: OU_SEL(6.2, 1.16) },
        { market_id: '1.45', status: 'SUSPENDED', market_type: 'OVER_UNDER_55', line: 5.5, selections: OU_SEL(11, 1.05) },
    ],
    btts: {
        market_id: '1.50', status: 'OPEN', market_type: 'BOTH_TEAMS_TO_SCORE',
        selections: [
            { selection_id: 30246, name: 'Yes', runner_status: 'ACTIVE', back: 1.72, lay: 1.75, back_size: 200, lay_size: 150 },
            { selection_id: 110503, name: 'No', runner_status: 'ACTIVE', back: 2.3, lay: 2.36 },
        ],
    },
    ht_result: {
        market_id: '1.60', status: 'OPEN', market_type: 'HALF_TIME',
        selections: [
            { selection_id: 11, name: 'Roma', runner_status: 'ACTIVE', back: 2.1, lay: 2.14 },
            { selection_id: 58805, name: 'Draw', runner_status: 'ACTIVE', back: 2.6, lay: 2.7 },
        ],
    },
} as never;

describe('safeTradeBook — TUTTI i mercati del feed (audit R1)', () => {
    it('Over/Under: la linea giusta per market_id, non una qualunque', () => {
        // gli stessi selection_id compaiono su OGNI linea: solo il market_id le
        // distingue — prezzare la linea sbagliata sarebbe un errore di soldi
        expect(safeTradeBook(
            { market_id: '1.30', market_type: 'OVER_UNDER_35', selection_id: 47973, selection_name: 'Under' },
            GOALS_PAYLOAD,
        )).toMatchObject({ back: 1.38, lay: 1.44, marketId: '1.30', status: 'OPEN', source: 'ou' });
        expect(safeTradeBook(
            { market_id: '1.20', market_type: 'OVER_UNDER_25', selection_id: 47972, selection_name: 'Over' },
            GOALS_PAYLOAD,
        )).toMatchObject({ back: 1.8, marketId: '1.20' });
    });

    it('Over/Under senza market_id sulla riga: risolve dalla LINEA del market_type', () => {
        expect(safeTradeBook(
            { market_id: null, market_type: 'OVER_UNDER_25', selection_id: 47973, selection_name: 'Under' },
            GOALS_PAYLOAD,
        )).toMatchObject({ back: 2.2, marketId: '1.20' });
    });

    it('Gol/NoGol (BTTS) e 1X2 primo tempo: prezzati come gli altri', () => {
        expect(safeTradeBook(
            { market_id: '1.50', market_type: 'BOTH_TEAMS_TO_SCORE', selection_id: 30246, selection_name: 'Yes' },
            GOALS_PAYLOAD,
        )).toMatchObject({ back: 1.72, lay: 1.75, source: 'btts' });
        expect(safeTradeBook(
            { market_id: '1.60', market_type: 'HALF_TIME', selection_id: 58805, selection_name: 'Draw' },
            GOALS_PAYLOAD,
        )).toMatchObject({ back: 2.6, lay: 2.7, source: 'ht_result' });
    });

    it('size abbinabili e stato del mercato tornano insieme al prezzo', () => {
        expect(safeTradeBook(
            { market_id: '1.20', market_type: 'OVER_UNDER_25', selection_id: 47972, selection_name: 'Over' },
            GOALS_PAYLOAD,
        )).toMatchObject({ backSize: 120, laySize: 90, runnerStatus: 'ACTIVE' });
    });

    it('selezione per NOME quando la riga non porta l id', () => {
        expect(safeTradeBook(
            { market_id: '1.50', market_type: 'BOTH_TEAMS_TO_SCORE', selection_id: null, selection_name: 'No' },
            GOALS_PAYLOAD,
        )).toMatchObject({ back: 2.3 });
    });

    it('Correct Score / Half Time Score / Match Odds continuano a funzionare', () => {
        expect(safeTradeBook({ market_id: '1.5', market_type: 'CORRECT_SCORE', selection_id: 77, selection_name: null }, GOALS_PAYLOAD))
            .toMatchObject({ back: 38, lay: 42 });
        expect(safeTradeBook({ market_id: '1.7', market_type: 'HALF_TIME_SCORE', selection_id: 55, selection_name: null }, GOALS_PAYLOAD))
            .toMatchObject({ back: 3, lay: 3.1 });
        expect(safeTradeBook({ market_id: '1.1', market_type: 'MATCH_ODDS', selection_id: 11, selection_name: 'Roma' }, GOALS_PAYLOAD))
            .toMatchObject({ back: 1.3, lay: 1.32, source: 'match_odds' });
    });

    it('linea O/U GIÀ DECISA (nel feed solo per una posizione Mike): nessun prezzo', () => {
        // l esito è aritmetico: quella quota non è un prezzo di uscita reale
        expect(safeTradeBook(
            { market_id: '1.40', market_type: 'OVER_UNDER_45', selection_id: 47972, selection_name: 'Over' },
            GOALS_PAYLOAD,
        )).toBeNull();
        expect(safeTradeBook(
            { market_id: null, market_type: 'OVER_UNDER_45', selection_id: 47972, selection_name: 'Over' },
            GOALS_PAYLOAD,
        )).toBeNull();
    });

    it('mercato SOSPESO: il prezzo c è, ma marketBlocked lo dichiara', () => {
        const b = safeTradeBook(
            { market_id: '1.45', market_type: 'OVER_UNDER_55', selection_id: 47973, selection_name: 'Under' },
            GOALS_PAYLOAD,
        );
        expect(b).toMatchObject({ status: 'SUSPENDED' });
        expect(marketBlocked(b)).toBe('mercato sospeso');
        expect(marketBlocked(null)).toBeNull();
        expect(marketBlocked({ back: 1, lay: 2, status: 'OPEN' })).toBeNull();
        expect(marketBlocked({ back: 1, lay: 2, status: 'OPEN', runnerStatus: 'REMOVED' })).toBe('selezione rimossa');
        expect(marketBlocked({ back: 1, lay: 2, status: 'CLOSED' })).toBe('mercato chiuso');
    });

    it('senza market_id e con la selezione in PIÙ blocchi non indovina', () => {
        // 47973 ("Under") esiste su tutte le linee: ambiguo → niente prezzo
        expect(safeTradeBook(
            { market_id: null, market_type: 'MERCATO_IGNOTO', selection_id: 47973, selection_name: 'Under' },
            GOALS_PAYLOAD,
        )).toBeNull();
    });

    it('senza market_id e con la selezione in UN solo blocco: la usa', () => {
        expect(safeTradeBook(
            { market_id: null, market_type: 'MERCATO_IGNOTO', selection_id: 30246, selection_name: 'Yes' },
            GOALS_PAYLOAD,
        )).toMatchObject({ back: 1.72, source: 'btts' });
    });

    it('feed assente o mercato non nel feed → null (cash out spento, mai indovinato)', () => {
        expect(safeTradeBook({ market_id: '1.30', market_type: 'OVER_UNDER_35', selection_id: 47973, selection_name: 'Under' }, null)).toBeNull();
        expect(safeTradeBook({ market_id: '9.99', market_type: 'ASIAN_HANDICAP', selection_id: 1, selection_name: 'x' }, GOALS_PAYLOAD)).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// R1 (certificazione 11/09 sera) — il CASH OUT su ogni mercato del feed non
// basta che trovi il book: deve chiudere sul LATO OPPOSTO all'apertura, al
// prezzo di quel lato, con la size abbinabile di quel lato. Un lato sbagliato
// qui non e' un errore di stile: raddoppia la posizione invece di chiuderla.
// ---------------------------------------------------------------------------
describe('R1 — chiusura sul LATO OPPOSTO, mercato per mercato', () => {
    /** i sei mercati che il feed dello scanner espone, con il book atteso */
    const MERCATI = [
        { nome: 'Match Odds',        market_id: '1.1',  market_type: 'MATCH_ODDS',           selection_id: 11,     selection_name: 'Roma',  back: 1.3,  lay: 1.32, backSize: 250, laySize: 180 },
        { nome: 'Correct Score',     market_id: '1.5',  market_type: 'CORRECT_SCORE',        selection_id: 77,     selection_name: null,    back: 38,   lay: 42,   backSize: null, laySize: null },
        { nome: 'Half Time Score',   market_id: '1.7',  market_type: 'HALF_TIME_SCORE',      selection_id: 55,     selection_name: null,    back: 3,    lay: 3.1,  backSize: null, laySize: null },
        { nome: 'O/U 2.5',           market_id: '1.20', market_type: 'OVER_UNDER_25',        selection_id: 47972,  selection_name: 'Over',  back: 1.8,  lay: 1.83, backSize: 120, laySize: 90 },
        { nome: 'O/U 3.5',           market_id: '1.30', market_type: 'OVER_UNDER_35',        selection_id: 47973,  selection_name: 'Under', back: 1.38, lay: 1.44, backSize: 80,  laySize: 60 },
        { nome: 'Gol/NoGol (BTTS)',  market_id: '1.50', market_type: 'BOTH_TEAMS_TO_SCORE',  selection_id: 30246,  selection_name: 'Yes',   back: 1.72, lay: 1.75, backSize: 200, laySize: 150 },
        { nome: '1X2 primo tempo',   market_id: '1.60', market_type: 'HALF_TIME',            selection_id: 11,     selection_name: 'Roma',  back: 2.1,  lay: 2.14, backSize: null, laySize: null },
    ] as const;

    it.each(MERCATI)('$nome: un LAY aperto si chiude in BACK al best BACK', (m) => {
        // LAY 10 @m.lay: vince +10, perde -10*(lay-1) -> hedgeSide = back
        const t = trade({
            market_id: m.market_id, market_type: m.market_type,
            selection_id: m.selection_id, selection_name: m.selection_name,
            side: 'lay', price: m.lay, size: 10, liability: 10 * (m.lay - 1),
        });
        const book = safeTradeBook(t, GOALS_PAYLOAD);
        expect(book, `${m.nome}: il feed deve dare il book`).not.toBeNull();
        const exp = tradeExposureNow(t);
        expect(hedgeSide(exp.win, exp.lose)).toBe('back');
        expect(greenPrice(exp.win, exp.lose, book!.back, book!.lay)).toBe(m.back);
        expect(book!.backSize).toBe(m.backSize);
    });

    it.each(MERCATI)('$nome: un BACK aperto si chiude in LAY al best LAY', (m) => {
        const t = trade({
            market_id: m.market_id, market_type: m.market_type,
            selection_id: m.selection_id, selection_name: m.selection_name,
            side: 'back', price: m.back, size: 10, liability: 10,
        });
        const book = safeTradeBook(t, GOALS_PAYLOAD);
        expect(book, `${m.nome}: il feed deve dare il book`).not.toBeNull();
        const exp = tradeExposureNow(t);
        expect(hedgeSide(exp.win, exp.lose)).toBe('lay');
        expect(greenPrice(exp.win, exp.lose, book!.back, book!.lay)).toBeCloseTo(m.lay, 6);
        expect(book!.laySize).toBe(m.laySize);
    });

    it('ogni linea Over/Under ha il SUO prezzo: mai quello di una linea vicina', () => {
        // 47973 ("Under") esiste su OGNI linea: se il market_id non filtrasse,
        // la 3.5 verrebbe chiusa al prezzo della 2.5 (soldi veri, quota diversa)
        const per_linea = (mid: string, mt: string) => safeTradeBook(
            { market_id: mid, market_type: mt, selection_id: 47973, selection_name: 'Under' },
            GOALS_PAYLOAD,
        );
        expect(per_linea('1.20', 'OVER_UNDER_25')).toMatchObject({ back: 2.2, marketId: '1.20' });
        expect(per_linea('1.30', 'OVER_UNDER_35')).toMatchObject({ back: 1.38, marketId: '1.30' });
        expect(per_linea('1.45', 'OVER_UNDER_55')).toMatchObject({ back: 1.05, marketId: '1.45' });
        // i lay con la tolleranza del binario (il fixture li costruisce sommando)
        expect(per_linea('1.20', 'OVER_UNDER_25')!.lay).toBeCloseTo(2.26, 6);
        expect(per_linea('1.30', 'OVER_UNDER_35')!.lay).toBeCloseTo(1.44, 6);
        expect(per_linea('1.45', 'OVER_UNDER_55')!.lay).toBeCloseTo(1.11, 6);
    });

    it('`for_mike` da solo NON spegne il cash out (spegnerlo sarebbe R1 di nuovo)', () => {
        // il marcatore dice solo "questa linea sta nel feed anche per Mike":
        // se la linea e' viva, e' un mercato di chiusura legittimo per Safe.
        const payload = {
            ...(GOALS_PAYLOAD as never as Record<string, unknown>),
            ou: [{
                market_id: '1.31', status: 'OPEN', market_type: 'OVER_UNDER_45', line: 4.5,
                for_mike: true,
                selections: [
                    { selection_id: 47972, name: 'Over', runner_status: 'ACTIVE', back: 6.2, lay: 6.4, back_size: 30, lay_size: 20 },
                    { selection_id: 47973, name: 'Under', runner_status: 'ACTIVE', back: 1.16, lay: 1.18, back_size: 500, lay_size: 400 },
                ],
            }],
        } as never;
        expect(isUsableBlock({ status: 'OPEN', for_mike: true } as never)).toBe(true);
        expect(isUsableBlock({ status: 'OPEN', decided: true, for_mike: true } as never)).toBe(false);
        expect(safeTradeBook(
            { market_id: '1.31', market_type: 'OVER_UNDER_45', selection_id: 47973, selection_name: 'Under' },
            payload,
        )).toMatchObject({ back: 1.16, lay: 1.18, source: 'ou' });
    });

    it('i blocchi DECISI sono fuori dai blocchi utilizzabili, non solo dal pricing', () => {
        const tutti = scanMarketBlocks(GOALS_PAYLOAD);
        const usabili = usableMarketBlocks(GOALS_PAYLOAD);
        expect(tutti.length - usabili.length).toBe(1);                 // la sola 4.5 `decided`
        expect(usabili.some((b) => b.market_id === '1.40')).toBe(false);
        expect(tutti.some((b) => b.market_id === '1.40')).toBe(true);
    });
});

// ---------------------------------------------------------------------------
// Motivo di ATTESA: il contratto vero sono le FRASI del servizio, non codici
// brevi. Questi sono i testi LETTERALI prodotti da exits.decide_time_exit /
// bot_service._write_model_hold: se il backend li cambia, qui diventa rosso.
// ---------------------------------------------------------------------------
describe('exit_hold: le frasi REALI del servizio arrivano in italiano', () => {
    const REALI = [
        'margine ampio: P(perdita)=0.4%, tengo fino al settlement',
        'rischio alto: P(perdita)=15.0% >= 10%, esco',
        'profitto bloccato +1,20 €: esco',
        'tenere non rende: EV(tengo)=+1,50 € vs bloccato -0,20 €, P(perdita)=6.0%, esco',
        'EV(tengo)=+1,50 € > bloccato -0,20 €, P(perdita)=6.0%: tengo',
        'P(perdita) non stimabile e chiusura in perdita: tengo',
        'modello: tengo',
        'modello: nessuna regola attiva, tengo',
    ];

    it('nessuna frase viene mangiata dalla mappa: si mostra cosi come e', () => {
        for (const frase of REALI) {
            expect(holdReasonLabel(frase)).toBe(frase);
            // sono gia in italiano: nessuna parola inglese nuda sotto gli occhi
            expect(frase).not.toMatch(/(hold|exit|wide|margin|risk cap|locked)/i);
        }
    });

    it('le frasi che portano gia la P(perdita) non la fanno accodare due volte', () => {
        const conP = REALI.filter((r) => /P\(perdita\)/.test(r));
        expect(conP.length).toBeGreaterThan(0);
        for (const frase of conP) expect(holdReasonHasP(frase)).toBe(true);
        expect(holdReasonHasP('modello: tengo')).toBe(false);
        expect(holdReasonHasP(null)).toBe(false);
    });

    it('motivo assente = "in attesa" (mai una cella muta)', () => {
        expect(holdReasonLabel(null)).toBe('in attesa');
        expect(holdReasonLabel('')).toBe('in attesa');
    });

    it('tradeHold legge la forma esatta di meta.exit_hold del servizio', () => {
        // le chiavi sono quelle di bot_service.HOLD_KEY
        expect(tradeHold({ meta: { exit_hold: {
            reason: REALI[0], p_lose: 0.004, source: 'model',
            locked: -4.0, ev_hold: 1.5, ts: '2026-09-11T20:00:00Z',
        } } })).toEqual({
            reason: REALI[0], pLose: 0.004, source: 'model',
            locked: -4, evHold: 1.5, ts: '2026-09-11T20:00:00Z',
        });
        expect(tradeHold({ meta: null })).toBeNull();
        expect(tradeHold({ meta: { exit_hold: 'non un oggetto' } })).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// Migrazione v2 assente: la UI deve SAPERE che i numeri di giornata sono suoi
// (stimati sulle righe caricate) e non del servizio.
// ---------------------------------------------------------------------------
describe('aggregatesHaveDay — riconosce la RPC vecchia', () => {
    const V1 = {
        realized_today: 2.85, realized_total: 40,
        open_liability: 116.64, open_count: 1, won: 1, lost: 0,
    };

    it('i soli sei campi della v1 = NESSUN contatore di giornata', () => {
        expect(aggregatesHaveDay(V1)).toBe(false);
        expect(aggregatesHaveDay(null)).toBe(false);
        expect(aggregatesHaveDay(undefined)).toBe(false);
    });

    it('basta UNO dei campi v2 per fidarsi del servizio', () => {
        expect(aggregatesHaveDay({ ...V1, won_today: 0 })).toBe(true);
        expect(aggregatesHaveDay({ ...V1, lost_today: 0 })).toBe(true);
        expect(aggregatesHaveDay({ ...V1, legs_today: 0 })).toBe(true);
        expect(aggregatesHaveDay({ ...V1, events_today: 0 })).toBe(true);
        expect(aggregatesHaveDay({ ...V1, day_liability: 0 })).toBe(true);
    });

    it('zero e un valore, non un campo assente (mai confonderli)', () => {
        // won_today: 0 significa "il servizio dice zero", non "non lo so"
        expect(aggregatesHaveDay({ ...V1, won_today: 0, lost_today: 0 })).toBe(true);
        expect(aggregatesHaveDay({ ...V1, operating_day: '2026-09-11' })).toBe(false);
    });
});

describe('copertura, esposizione e stato letti dal meta', () => {
    it('hedgeState: meta.hedge con fraction < 1 = copertura PARZIALE ancora viva', () => {
        expect(hedgeState({ size: 10, meta: { hedge: { fraction: 0.4, remaining_liability: 117, hedged_size: 4, residual_size: 6, complete: false } } }))
            .toEqual({ fraction: 0.4, remainingLiability: 117, hedgedSize: 4, residualSize: 6, complete: false, inFlight: false });
    });

    it('hedgeState: copertura COMPLETA e confermata', () => {
        expect(hedgeState({ size: 10, meta: { hedge: { fraction: 1, remaining_liability: 0, complete: true } } }))
            .toMatchObject({ complete: true, inFlight: false, remainingLiability: 0 });
        expect(hedgeState({ size: 10, meta: null })).toBeNull();
    });

    // contratto backend 11/09: mentre la chiusura è IN VOLO remaining_liability
    // è la liability PIENA — il rischio scende solo a copertura CONFERMATA
    it('hedgeState: chiusura IN VOLO = rischio ancora pieno, mai "completa"', () => {
        expect(hedgeState({ size: 10, meta: { hedging: true, hedge: { fraction: 1, remaining_liability: 195, complete: true } } }))
            .toMatchObject({ inFlight: true, complete: false, remainingLiability: 195 });
        expect(hedgeState({ size: 10, meta: { closing_status: 'pending' } })).toMatchObject({ inFlight: true, complete: false });
        expect(hedgeState({ size: 10, meta: { hedge_pending_ids: [11] } })).toMatchObject({ inFlight: true });
    });

    it('hedgeState: percorso REST/paper senza meta.hedge (hedged_size/residual_size)', () => {
        expect(hedgeState({ size: 10, meta: { hedged_size: 6, residual_size: 4 } }))
            .toMatchObject({ fraction: 0.6, hedgedSize: 6, residualSize: 4, complete: false });
    });

    it('C-02: dopo una chiusura CONFERMATA parziale il residuo resta chiudibile', () => {
        const apertura = trade({ id: 9, meta: { hedge: { fraction: 0.4, complete: false, remaining_liability: 117 } } });
        const chiusuraConfermata = trade({ id: 10, closes_trade_id: 9, status: 'open' });
        expect(cashoutInFlight(9, [], [apertura, chiusuraConfermata])).toBe(false);
        // …ma finché l ordine di copertura è pending il bottone resta spento
        expect(cashoutInFlight(9, [], [apertura, trade({ id: 11, closes_trade_id: 9, status: 'pending' })])).toBe(true);
    });

    it('tradeExposureNow: usa if_win/if_lose del servizio (esposizione RESIDUA)', () => {
        const t = { side: 'lay', price: 40, size: 5, meta: { if_win: -80, if_lose: 2.5 } };
        expect(tradeExposureNow(t)).toEqual({ win: -80, lose: 2.5 });
        // senza meta: esposizione dell ordine di apertura (lay 5 @40)
        expect(tradeExposureNow({ ...t, meta: null })).toEqual({ win: -195, lose: 5 });
    });

    it('H-05 exitRunState: ritento / attesa prezzo / fallita definitivamente', () => {
        expect(exitRunState({ meta: null })).toBeNull();
        expect(exitRunState({ meta: { exit: { state: 'retrying', attempts: 2, next_retry_at: '2026-09-11T18:07:00Z' } } }))
            .toMatchObject({ state: 'retrying', attempts: 2, nextRetryAt: '2026-09-11T18:07:00Z' });
        expect(exitRunState({ meta: { exit: { state: 'waiting_price', wait_attempts: 4 } } }))
            .toMatchObject({ state: 'waiting_price', waitAttempts: 4 });
        expect(exitRunState({ meta: { exit: { state: 'failed', attempts: 3, last_error: 'INSUFFICIENT_FUNDS' } } }))
            .toMatchObject({ state: 'failed', lastError: 'INSUFFICIENT_FUNDS' });
    });

    it('isReconciling / errorFinal / blindSince / comboIncomplete', () => {
        expect(isReconciling({ status: 'pending', meta: { reason: 'place_exception_reconciling' } })).toBe(true);
        expect(isReconciling({ status: 'open', meta: { reason: 'place_exception_reconciling' } })).toBe(false);
        expect(isReconciling({ status: 'pending', meta: null })).toBe(false);
        expect(errorFinal({ meta: { error_final: true, error_at: 'x', last_error: 'boom' } })).toEqual({ at: 'x', detail: 'boom' });
        expect(errorFinal({ meta: null })).toBeNull();
        expect(blindSince({ meta: { blind_since: '2026-09-11T18:00:00Z' } })).toBe('2026-09-11T18:00:00Z');
        expect(blindSince({ meta: { market_missing_since: 'z' } })).toBe('z');
        expect(blindSince({ meta: null })).toBeNull();
        expect(comboIncomplete({ meta: { combo_incomplete: true } })).toBe(true);
        expect(comboIncomplete({ meta: null })).toBe(false);
    });

    it('M-15 isLivePosition: chiusure e hedged complete NON sono posizioni vive', () => {
        const base = { status: 'open', size: 10, meta: null as Record<string, unknown> | null, closes_trade_id: null as number | null };
        expect(isLivePosition(base)).toBe(true);
        expect(isLivePosition({ ...base, closes_trade_id: 9 })).toBe(false);
        expect(isLivePosition({ ...base, status: 'hedged', meta: { hedge: { fraction: 1, complete: true } } })).toBe(false);
        expect(isLivePosition({ ...base, status: 'hedged', meta: { hedge: { fraction: 0.4, complete: false } } })).toBe(true);
        expect(isLivePosition({ ...base, status: 'pending' })).toBe(true);
        expect(isLivePosition({ ...base, status: 'pending', meta: { error_final: true } })).toBe(false);
        expect(isLivePosition({ ...base, status: 'won' })).toBe(false);
    });

    it('normalizeLossStop: il segno non conta, 50 e −50 sono lo stesso stop', () => {
        expect(normalizeLossStop(50)).toBe(-50);
        expect(normalizeLossStop(-50)).toBe(-50);
        expect(normalizeLossStop(0)).toBe(0);
        expect(normalizeLossStop(null)).toBeNull();
        expect(normalizeLossStop('x' as never)).toBeNull();
    });

    it('L-02 tradeCommission: quella del TRADE, non il parametro corrente', () => {
        expect(tradeCommission({ commission: 0.02 }, 5)).toBe(0.02);
        expect(tradeCommission({ commission: null }, 5)).toBe(5);
        expect(tradeCommission(null, 5)).toBe(5);
    });
});

describe('L-07 — esito leggibile di OGNI richiesta operativa', () => {
    const req = (over: Record<string, unknown>) => ({
        id: 1, kind: 'cashout' as const, payload: { trade_id: 9 },
        status: 'done' as const, result: null, created_at: 'x', updated_at: null, ...over,
    });

    it('eseguito / rifiutato / errore / in coda, sempre con un messaggio', () => {
        expect(requestOutcome(req({ result: { ok: true, message: 'chiusura inviata' } })))
            .toMatchObject({ tone: 'ok', label: 'eseguito', message: 'chiusura inviata', settled: true, tradeId: 9 });
        expect(requestOutcome(req({ status: 'rejected', result: { rejected: true, message: 'in riconciliazione' } })))
            .toMatchObject({ tone: 'rejected', label: 'rifiutato', message: 'in riconciliazione' });
        expect(requestOutcome(req({ status: 'error', result: { error: 'boom' } })))
            .toMatchObject({ tone: 'error', message: 'boom' });
        expect(requestOutcome(req({ status: 'pending', result: null })))
            .toMatchObject({ tone: 'pending', settled: false });
        expect(requestOutcome(null)).toBeNull();
    });

    it('rifiuto dichiarato solo dentro result (stato "done")', () => {
        expect(requestOutcome(req({ result: { status: 'rejected', message: 'ordine gia a mercato' } })))
            .toMatchObject({ tone: 'rejected', message: 'ordine gia a mercato' });
    });

    it('dice da dove venivano le quote usate per chiudere', () => {
        expect(requestOutcome(req({ result: { message: 'chiuso', source: 'rest' } })))
            .toMatchObject({ source: 'rest', sourceLabel: 'quote dal book Betfair', message: 'chiuso (quote dal book Betfair)' });
        expect(requestOutcome(req({ result: { message: 'chiuso', source: 'feed' } })))
            .toMatchObject({ sourceLabel: 'quote dal feed dello scanner' });
        expect(requestOutcome(req({ status: 'rejected', result: { message: 'quote non disponibili' } })))
            .toMatchObject({ tone: 'rejected', message: 'quote non disponibili' });
    });

    it('lastRequestFor: la più recente per quel trade, filtrabile per tipo', () => {
        const rs = [
            req({ id: 1, kind: 'place' }),
            req({ id: 2, kind: 'cashout' }),
            req({ id: 3, kind: 'cashout', payload: { trade_id: 10 } }),
            req({ id: 4, kind: 'cancel' }),
        ];
        expect(lastRequestFor(9, rs as never)?.id).toBe(4);
        expect(lastRequestFor(9, rs as never, 'cashout')?.id).toBe(2);
        expect(lastRequestFor(77, rs as never)).toBeNull();
    });
});

describe('M-04 — UNA sola notifica per POSIZIONE regolata', () => {
    it('le gambe di CHIUSURA non generano una seconda notifica', () => {
        const rows = [
            trade({ id: 70, status: 'hedged', settled_at: 't', pnl: -22.1 }),
            trade({ id: 71, status: 'hedged', settled_at: 't', pnl: 24, closes_trade_id: 70 }),
        ];
        expect(detectSettlements(rows, new Set<number>(), true)).toEqual([]);   // primo carico: silenzio
        const seen = new Set<number>();
        expect(detectSettlements(rows, seen, false).map((t) => t.id)).toEqual([70]);
        expect(detectSettlements(rows, seen, false)).toEqual([]);               // mai due volte
    });
});
