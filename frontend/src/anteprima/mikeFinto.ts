// ============================================================================
// mikeFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /mike.
//
// Non e' importato dall'app. Il server di anteprima sostituisce con un alias
// Vite ESATTO l'import '@/components/mike/useMike' con questo file:
//   - il modulo VERO si importa con percorso RELATIVO (l'alias non lo tocca) e
//     si ri-esporta tutto (`export *`);
//   - `useMike` e' ridefinito qui e restituisce un `MikeView` (il tipo del
//     modulo vero) con le IDENTICHE chiavi e tipi, costruito come gli stati di
//     `pages/Mike.test.tsx` (CONTROL, AGGREGATES, eventi PRE/LIVE/ERROR, righe
//     con chiusure annidate, attivita') e con le funzioni VERE di `lib/mike`
//     dove la pagina le userebbe (`mergeMikeParams`, `groupMikeTrades`,
//     `groupsOfDay`, `dayResultCounts`, `romeDayStartMs`, `requestOutcome`);
//   - i comandi sono no-op asincroni: dall'anteprima non parte niente.
//
// La giornata (prototipo `s_calcio.js`, MIKE in LIVE): Bologna-Udinese
// pre-match con l'Under 3.5 abbinato e il green-up sul book, Inter-Torino 58'
// 1-0 coperta sulla linea 4.5 con una proposta d'uscita da firmare,
// Getafe-Celta in errore (linea 4.5 assente nel feed). Regolata in mattinata
// Shanghai Port-Shandong Taishan (due cicli, entrambi in utile).
// ============================================================================
import type { MikeHandlers, MikeView } from '../components/mike/useMike';
import {
    mergeMikeParams, groupMikeTrades, groupsOfDay, dayResultCounts, romeDayStartMs,
    type MikeActivity, type MikeAggregates, type MikeBook, type MikeControl, type MikeEvent,
    type MikeLeg, type MikeTrade,
} from '../lib/mike';
import { EV, KO, ORA_MS, alle, fa, nulla } from './giornataBot';

export * from '../components/mike/useMike';

// ------------------------------------------------------------------ parametri

const PARAMS = mergeMikeParams({
    stake: 10, commission_pct: 5, entry_hours_before_ko: 1, cashout_profit_pct: 5,
    daily_loss_stop: 50, pre_green_ticks: 2, cover_form: 'lay_under45', uscite_automatiche: false,
});

// ------------------------------------------------------------------ partite

function book(back: number, backSize: number, lay: number, laySize: number, inplay: boolean): MikeBook {
    return { best_back: back, back_size: backSize, best_lay: lay, lay_size: laySize, status: 'OPEN', inplay, bet_delay: inplay ? 5 : 0 };
}

function gamba(over: Partial<MikeLeg> & Pick<MikeLeg, 'role' | 'market' | 'selection' | 'side' | 'price' | 'size' | 'matched' | 'ref' | 'cycle_no'>): MikeLeg {
    return {
        avg_price: over.matched > 0 ? over.price : null, status: over.matched > 0 ? 'open' : 'pending',
        placed_at: ORA_MS / 1000 - 600, persistence: 'LAPSE', final: false, archived: false,
        ...over,
    };
}

const PUBBLICATA = { published_at: fa(1), published_ts: ORA_MS / 1000 - 1 };

/** Inter-Torino: Under 3.5 (8 EUR @1,30) portato in gioco e coperto
 *  bancando l'Under 4.5 (7,80 EUR @1,08); un ciclo pre-match gia' chiuso. */
const INTER: MikeEvent = {
    event_id: EV.inter, fixture_id: 1208833, event_name: 'Inter v Torino', competition: 'Serie A', league_id: 135,
    ko_at: KO.inter, mode: 'live',
    markets: { OU35: { market_id: '1.248120016' }, OU45: { market_id: '1.248120017' } },
    state: 'LIVE_COVERED', cycle_no: 1, entry_price_initial: 1.34,
    dossier: {
        fixture_id: 1208833, league_id: 135, lambda_home: 1.45, lambda_away: 0.92, rho: -0.08,
        p4_pre: 0.079, p_under35_cal: 0.74, p_under35_fonte: 'calibrated', source: 'api_football',
    },
    live: {
        ...PUBBLICATA,
        minute: 58, goals: 1, feed_age_s: 0, scanner_age_s: 1, inplay: true, ht: false,
        score_home: 1, score_away: 0, red_home: 0, red_away: 0, ht_score: [1, 0],
        lines_missing: [], feed_incomplete: false, reconcile_pending: false, no_reentry: false,
        liability: 8.62, locked: null, total_matched: 1843210,
        p_over45_model: 0.041, p4_market: 0.054, p4_model: 0.061,
        hazard: 0.041, hazard_atlas: 0.048, hazard_model: 0.041, pressure: 1.04,
        lambda_source: 'fixture', ko_price_under: 1.31, ko_drift_ticks: -1,
        p_total_model: { '1': 0.42, '2': 0.33, '3': 0.17, '4': 0.061, '5': 0.019 },
        cover_wait: null, cover_gain_pct: 9,
        cashout: {
            net: 0.4, gross: 0.42, base: 8, complete: true, pct: 5, target_pct: 5, commission: 0.05,
            per: { 'OU35|UNDER': 0.46, 'OU45|UNDER': -0.06 }, per_gross: { 'OU35|UNDER': 0.48, 'OU45|UNDER': -0.06 },
            decided: [],
            smart: { enabled: true, floor: 0.16, near: true, hot: false, ev_hold: 0.31, trigger: 'none' },
        },
        pnl_by_total: { '1': 1.66, '2': 1.66, '3': 1.66, '4': -8.62, '5': -0.59, '6': -0.59 },
        pnl_totale_by_total: { '1': 1.88, '2': 1.88, '3': 1.88, '4': -8.4, '5': -0.37, '6': -0.37 },
        pnl_cicli_chiusi: 0.22, cicli_chiusi: 1, investito: 8,
        cicli: [
            { ciclo: 1, stake: 10, prezzo_ingresso: 1.34, prezzo_uscita: 1.31, chiuso: true, pnl: 0.22, gambe: 2, ruoli: ['under_entry', 'under_green'] },
            { ciclo: 2, stake: 8, prezzo_ingresso: 1.3, prezzo_uscita: null, chiuso: false, pnl: null, gambe: 2, ruoli: ['under_last', 'over_cover'] },
        ],
        posizioni: [
            {
                market: 'OU35', selection: 'UNDER', lato: 'back', netto: 8, abbinato: 8, prezzo_medio: 1.3,
                se_vince: 2.28, se_perde: -8, decisa: null, chiusura_lato: 'lay', chiusura_prezzo: 1.23,
                chiusura_size: 8.46, se_chiudo_ora: 0.46, liquidita_al_prezzo: 388, eseguibile: true,
            },
            {
                market: 'OU45', selection: 'UNDER', lato: 'lay', netto: -7.8, abbinato: 7.8, prezzo_medio: 1.08,
                se_vince: 7.41, se_perde: -0.62, decisa: null, chiusura_lato: 'back', chiusura_prezzo: 1.07,
                chiusura_size: 7.87, se_chiudo_ora: -0.06, liquidita_al_prezzo: 1630, eseguibile: true,
            },
        ],
        books: {
            'OU35|UNDER': book(1.22, 412, 1.23, 388, true),
            'OU35|OVER': book(5.3, 120, 5.5, 96, true),
            'OU45|UNDER': book(1.07, 1630, 1.08, 1410, true),
            'OU45|OVER': book(13.5, 120, 14.5, 96, true),
        },
        feed_fresh: true,
    },
    positions: [
        gamba({ role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.34, size: 10, matched: 10, ref: 'under_entry-0-1', cycle_no: 0, status: 'settled', final: true, archived: true }),
        gamba({ role: 'under_green', market: 'OU35', selection: 'UNDER', side: 'lay', price: 1.31, size: 10.23, matched: 10.23, ref: 'under_green-0-2', cycle_no: 0, status: 'settled', final: true, archived: true, closes_ref: 'under_entry-0-1' }),
        gamba({ role: 'under_last', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.3, size: 8, matched: 8, ref: 'under_last-1-3', cycle_no: 1, persistence: 'PERSIST' }),
        gamba({ role: 'over_cover', market: 'OU45', selection: 'UNDER', side: 'lay', price: 1.08, size: 7.8, matched: 7.8, ref: 'over_cover-1-4', cycle_no: 1 }),
    ],
    ctx: {
        selections: { 'OU35|UNDER': 1222344, 'OU35|OVER': 1222345, 'OU45|UNDER': 1222347, 'OU45|OVER': 1222348 },
        // proposta d'uscita (interruttore "Uscite automatiche" spento): la firma e' dell'utente
        uscita_proposta: {
            chiave: 'chiusura|c1', categoria: 'chiusura', ciclo: 1, stato: 'LIVE_COVERED',
            stato_voluto: 'LIVE_CLOSING', motivo: 'uscita a modello: P(4 gol) sopra la soglia del secondo tempo',
            close_reason: 'loss_model',
            ordini: [
                { ruolo: 'under_close', mercato: 'OU35', selezione: 'UNDER', lato: 'lay', prezzo: 1.23, size: 8.46 },
                { ruolo: 'over_close', mercato: 'OU45', selezione: 'UNDER', lato: 'back', prezzo: 1.07, size: 7.87 },
            ],
            bloccabile: 0.4, urgente: false, minuto: 58, gol: 1,
            decided_at: ORA_MS / 1000 - 18, proposed_at: ORA_MS / 1000 - 18,
        },
    },
    skipped: false, settled_pnl: null, updated_at: fa(1),
};

/** Bologna-Udinese: Under 3.5 abbinato prima del fischio, green-up a +2 tick sul book. */
const BOLOGNA: MikeEvent = {
    event_id: EV.bologna, fixture_id: 1208840, event_name: 'Bologna v Udinese', competition: 'Serie A', league_id: 135,
    ko_at: KO.bologna, mode: 'live',
    markets: { OU35: { market_id: '1.248121023' }, OU45: { market_id: '1.248121024' } },
    state: 'PRE_OPEN', cycle_no: 0, entry_price_initial: 1.3,
    dossier: {
        fixture_id: 1208840, league_id: 135, lambda_home: 1.31, lambda_away: 0.88, rho: -0.07,
        p4_pre: 0.071, p_under35_cal: 0.79, p_under35_fonte: 'calibrated', source: 'api_football',
    },
    live: {
        ...PUBBLICATA,
        minute: null, goals: null, feed_age_s: 1, scanner_age_s: 1, inplay: false, ht: false,
        lines_missing: [], feed_incomplete: false, reconcile_pending: false,
        liability: 10, locked: null, total_matched: 284100,
        p_over45_model: 0.062, p4_market: 0.071, p4_model: 0.079, hazard: null,
        lambda_source: 'fixture',
        p_total_model: { '0': 0.11, '1': 0.24, '2': 0.27, '3': 0.19, '4': 0.1, '5': 0.05, '6': 0.04 },
        cover_wait: null,
        cashout: {
            net: 0.07, gross: 0.08, base: 10, complete: true, pct: 0.7, target_pct: 5, commission: 0.05,
            per: { 'OU35|UNDER': 0.07 }, per_gross: { 'OU35|UNDER': 0.08 }, decided: [],
        },
        pnl_by_total: { '0': 2.85, '1': 2.85, '2': 2.85, '3': 2.85, '4': -10, '5': -10 },
        investito: 10, cicli_chiusi: 0,
        posizioni: [{
            market: 'OU35', selection: 'UNDER', lato: 'back', netto: 10, abbinato: 10, prezzo_medio: 1.3,
            se_vince: 2.85, se_perde: -10, decisa: null, chiusura_lato: 'lay', chiusura_prezzo: 1.29,
            chiusura_size: 10.08, se_chiudo_ora: 0.07, liquidita_al_prezzo: 640, eseguibile: true,
        }],
        books: {
            'OU35|UNDER': book(1.28, 910, 1.29, 640, false),
            'OU35|OVER': book(4.4, 210, 4.6, 180, false),
            'OU45|UNDER': book(1.1, 2100, 1.11, 1800, false),
            'OU45|OVER': book(11, 140, 11.5, 120, false),
        },
        feed_fresh: true,
    },
    positions: [
        gamba({ role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.3, size: 10, matched: 10, ref: 'under_entry-0-1', cycle_no: 0 }),
        gamba({ role: 'under_green', market: 'OU35', selection: 'UNDER', side: 'lay', price: 1.28, size: 10.16, matched: 0, ref: 'under_green-0-2', cycle_no: 0, persistence: 'LAPSE', closes_ref: 'under_entry-0-1' }),
    ],
    ctx: { selections: { 'OU35|UNDER': 1222444, 'OU35|OVER': 1222445 } },
    skipped: false, settled_pnl: null, updated_at: fa(2),
};

/** Getafe-Celta: la linea 4.5 manca nel feed, il bot si e' fermato su questa partita. */
const GETAFE: MikeEvent = {
    event_id: EV.getafe, fixture_id: 1210551, event_name: 'Getafe v Celta', competition: 'La Liga', league_id: 140,
    ko_at: KO.getafe, mode: 'live',
    markets: { OU35: { market_id: '1.248122603' }, OU45: { market_id: null } },
    state: 'ERROR', cycle_no: 0, entry_price_initial: null,
    dossier: { fixture_id: 1210551, league_id: 140, lambda_home: 1.12, lambda_away: 1.05, p4_pre: 0.11, source: 'api_football' },
    live: {
        ...PUBBLICATA,
        minute: null, goals: null, feed_age_s: 2, inplay: false, ht: false,
        lines_missing: ['OU45|UNDER', 'OU45|OVER'], feed_incomplete: true,
        books: { 'OU35|UNDER': book(1.36, 520, 1.37, 410, false) }, pnl_by_total: {}, feed_fresh: true,
    },
    positions: [],
    ctx: { error: 'linea Over/Under 4.5 assente nel feed: niente copertura possibile' },
    skipped: false, settled_pnl: null, updated_at: fa(38 * 60),
};

// ------------------------------------------------------------------ righe

function riga(over: Partial<MikeTrade> & Pick<MikeTrade, 'id' | 'event_id' | 'event_name' | 'role' | 'cycle_no' | 'side' | 'price' | 'size' | 'status' | 'placed_at'>): MikeTrade {
    const ou45 = over.role === 'over_cover';
    return {
        strategy: 'mike', market_type: ou45 ? 'OVER_UNDER_45' : 'OVER_UNDER_35',
        market_id: null, selection_id: null, selection_name: ou45 ? 'Under 4.5 Goals' : 'Under 3.5 Goals',
        mode: 'live', liability: null, pnl: null, settled_at: null, signal_key: null, meta: null,
        closes_trade_id: null, day_placed_at: over.placed_at, origin: 'auto',
        ...over,
    };
}

const SHANGHAI = 'Shanghai Port v Shandong Taishan';

const RIGHE: MikeTrade[] = [
    // regolata in mattinata: ciclo pre-match chiuso a +2 tick, poi ultimo ingresso tenuto fino alla fine (2 gol)
    riga({ id: 9001, event_id: EV.shanghai, event_name: SHANGHAI, role: 'under_entry', cycle_no: 0, side: 'back', price: 1.42, size: 10, liability: 10,
        status: 'won', pnl: 3.99, placed_at: alle('05:02'), settled_at: alle('07:31'),
        meta: { pnl_gross: 4.2, commission_paid: 0.21, pnl_fonte: 'betfair' } }),
    riga({ id: 9002, event_id: EV.shanghai, event_name: SHANGHAI, role: 'under_green', cycle_no: 0, side: 'lay', price: 1.38, size: 10.29, liability: 3.91,
        status: 'lost', pnl: -3.91, placed_at: alle('05:14'), settled_at: alle('07:31'), closes_trade_id: 9001,
        meta: { exit_kind: 'greenup', exit_reason: 'green-up a +2 tick', pnl_fonte: 'betfair' } }),
    riga({ id: 9003, event_id: EV.shanghai, event_name: SHANGHAI, role: 'under_last', cycle_no: 1, side: 'back', price: 1.36, size: 10, liability: 10,
        status: 'won', pnl: 3.42, placed_at: alle('05:33'), settled_at: alle('07:31'),
        meta: { pnl_gross: 3.6, commission_paid: 0.18, pnl_fonte: 'betfair' } }),
    // Inter-Torino: ciclo pre chiuso in green, poi ultimo ingresso in gioco e copertura
    riga({ id: 9101, event_id: EV.inter, event_name: 'Inter v Torino', role: 'under_entry', cycle_no: 0, side: 'back', price: 1.34, size: 10, liability: 10,
        status: 'open', placed_at: alle('06:40') }),
    riga({ id: 9102, event_id: EV.inter, event_name: 'Inter v Torino', role: 'under_green', cycle_no: 0, side: 'lay', price: 1.31, size: 10.23, liability: 3.17,
        status: 'open', placed_at: alle('06:55'), closes_trade_id: 9101, meta: { exit_kind: 'greenup', exit_reason: 'green-up a +2 tick' } }),
    riga({ id: 9103, event_id: EV.inter, event_name: 'Inter v Torino', role: 'under_last', cycle_no: 1, side: 'back', price: 1.3, size: 8, liability: 8,
        status: 'open', placed_at: alle('07:22') }),
    riga({ id: 9104, event_id: EV.inter, event_name: 'Inter v Torino', role: 'over_cover', cycle_no: 1, side: 'lay', price: 1.08, size: 7.8, liability: 0.62,
        status: 'open', placed_at: alle('08:12') }),
    // Bologna-Udinese: ingresso pre-match
    riga({ id: 9201, event_id: EV.bologna, event_name: 'Bologna v Udinese', role: 'under_entry', cycle_no: 0, side: 'back', price: 1.3, size: 10, liability: 10,
        status: 'open', placed_at: alle('08:31:55') }),
];

const INIZIO_GIORNATA = romeDayStartMs(ORA_MS);

const OGGI_GRUPPI = groupsOfDay(groupMikeTrades(RIGHE), INIZIO_GIORNATA);
const VP = dayResultCounts(RIGHE, INIZIO_GIORNATA);
const REALIZZATO_OGGI = Math.round(RIGHE.reduce((s, r) => s + Number(r.pnl ?? 0), 0) * 100) / 100;
const LIABILITY = 18.62;

const AGGREGATI: MikeAggregates = {
    realized_total: 64.3, realized_today: REALIZZATO_OGGI, open_liability: LIABILITY, open_count: 2,
    won: 41, lost: 9, open_liability_rows: LIABILITY, live_now: 1,
    won_today: VP.won, lost_today: VP.lost, cycles_today: OGGI_GRUPPI.length,
    events_today: new Set(OGGI_GRUPPI.map((g) => g.open.event_id)).size,
    reconciling: 0, day_by: 'placed', liability_source: 'net_positions', liability_stale: false,
    heartbeat_at: fa(1),
};

const CONTROL: MikeControl = {
    id: 1, status: 'running', mode: 'live', params: { ...PARAMS },
    stats: {
        events_feed: 41, events_tracked: 3,
        by_state: { PRE_OPEN: 1, LIVE_COVERED: 1, ERROR: 1 },
        trades_open: 2, open_liability: LIABILITY, realized_today: REALIZZATO_OGGI, realized_total: 64.3,
        scanner_age_s: 1, last_cycle: fa(1), dry: false, mode: 'live', daily_stop: false,
    },
    error: null, started_at: alle('04:58'), stopped_at: null, heartbeat_at: fa(1), updated_at: fa(1),
};

// ------------------------------------------------------------------ attivita'

const ATTIVITA: MikeActivity[] = [
    { id: 512, ts: fa(18), event_id: EV.inter, kind: 'uscita_proposta', payload: {
        motivo: 'uscita a modello', bloccabile: 0.4,
        ordini: [
            { ruolo: 'under_close', mercato: 'OU35', selezione: 'UNDER', lato: 'lay', prezzo: 1.23 },
            { ruolo: 'over_close', mercato: 'OU45', selezione: 'UNDER', lato: 'back', prezzo: 1.07 },
        ] } },
    { id: 511, ts: alle('08:31:58'), event_id: EV.bologna, kind: 'place_resting', payload: { role: 'under_green', side: 'lay', selection: 'UNDER', size: 10.16, price: 1.28 } },
    { id: 510, ts: alle('08:31:55'), event_id: EV.bologna, kind: 'place', payload: { role: 'under_entry', side: 'back', selection: 'UNDER', size: 10, price: 1.3, mode: 'live' } },
    { id: 509, ts: alle('08:12:10'), event_id: EV.inter, kind: 'cover', payload: { side: 'lay', selection: 'UNDER', size: 7.8, price: 1.08, x: 1.2, minute: 37 } },
    { id: 508, ts: alle('08:00:12'), event_id: EV.getafe, kind: 'feed_line_missing', payload: { markets: ['OU45|UNDER', 'OU45|OVER'], state: 'WATCH' } },
    { id: 507, ts: alle('08:00:13'), event_id: EV.getafe, kind: 'state', payload: { from: 'WATCH', to: 'ERROR', reason: 'feed_line_missing' } },
    { id: 506, ts: alle('07:52:40'), event_id: EV.bologna, kind: 'armed', payload: { ko: KO.bologna } },
    { id: 505, ts: alle('07:31:02'), event_id: EV.shanghai, kind: 'settled', payload: { pnl: 3.5 } },
    { id: 504, ts: alle('07:22:05'), event_id: EV.inter, kind: 'place', payload: { role: 'under_last', side: 'back', selection: 'UNDER', size: 8, price: 1.3, mode: 'live' } },
    { id: 503, ts: alle('06:55:30'), event_id: EV.inter, kind: 'pre_cycle', payload: { cycle: 0, entry: 1.34, exit: 1.31, locked: 0.22 } },
    { id: 502, ts: alle('06:25:00'), event_id: EV.inter, kind: 'armed', payload: { ko: KO.inter } },
    { id: 501, ts: alle('05:14:20'), event_id: EV.shanghai, kind: 'pre_cycle', payload: { cycle: 0, entry: 1.42, exit: 1.38, locked: 0.08 } },
];

// ------------------------------------------------------------------ vista

/** UNA vista per tutta la vita della pagina: stessi oggetti a ogni render,
 *  come un hook vero che non riceve aggiornamenti. */
let VISTA: MikeView | null = null;

function vista(): MikeView {
    return {
        available: true, loading: false, busy: false, error: null,
        control: CONTROL,
        events: [INTER, BOLOGNA, GETAFE],
        trades: RIGHE,
        activity: [...ATTIVITA].sort((a, b) => b.ts.localeCompare(a.ts)),
        aggregates: AGGREGATI,
        requests: [],
        arretratiProva: null,
        canaleLocale: 'connected',
        dayStartMs: INIZIO_GIORNATA,
        dayStartSource: 'rpc',
        params: PARAMS,
        mode: 'live',
        liveConfirmed: false,
        reload: nulla, start: nulla, stop: nulla,
        setMode: nulla, saveParams: nulla,
        request: async () => null,
        isRequestPending: () => false,
        freshSettled: [],
        freshOutcomes: [],
    };
}

export function useMike(_handlers: MikeHandlers = {}): MikeView {
    VISTA ??= vista();
    return VISTA;
}
