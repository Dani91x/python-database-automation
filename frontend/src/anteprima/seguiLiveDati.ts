// ============================================================================
// seguiLiveDati.ts - SOLO PER L'ANTEPRIMA POPOLATA di Segui live (/segui-live).
//
// Non e' importato dall'app. Dati PURI della giornata del prototipo
// (AUDIT_2026-10-01/REDESIGN/prototipo/js/s_live.js + ladder.js + data.js):
// Inter-Torino 58' 1-0 (Serie A, seguita a mano), Real Betis-Getafe 31' 0-0
// (La Liga, seguita dal runner per i bot), Bologna-Udinese in attesa.
// Il runner calcio e' in PAPER: posizione aperta su Inter (BACK 5 @ 1,52 abbinato
// prima del ribasso, LAY 5,63 @ 1,35 di uscita ancora sul book) e Under 2.5.
//
// VINCOLO: qui SOLO `import type` (nessun import a runtime). Il file e' letto
// anche da `confronto2/strumenti/canaleFinto.mjs`, che lo chiede al server Vite
// dell'anteprima (TS -> JS senza dipendenze) per mandare sui canali locali finti
// le STESSE righe che i finti del database restituiscono.
// Chiavi e tipi: quelli dei moduli veri (LiveFollow, LiveNowRow, LiveLadderRow,
// LiveOrderRow, LivePositionRow, ...), controllati da tsc.
// Orologio dell'anteprima: 2026-10-01T08:38:00Z (10:38 a Roma).
// ============================================================================
import type {
    Alert, LiveFollow, LiveLadderRow, LiveLadderSelection, LiveNowMarket, LiveNowRow,
    LiveSignalsRow, Signal,
} from '../lib/live';
import type { LiveAuditRow, LiveOrderRow, LivePositionRow, XhedgeRow } from '../lib/liveOrders';
import type { ScalperActivityRow, ScalperState } from '../lib/scalper';

// ------------------------------------------------------------------ orologio

export const ORA_MS = Date.parse('2026-10-01T08:38:00Z');
/** istante ISO `s` secondi prima di adesso */
const fa = (s: number) => new Date(ORA_MS - s * 1000).toISOString();
/** istante ISO a un'ora UTC di oggi, 'HH:MM' o 'HH:MM:SS' */
const alle = (hhmm: string) => `2026-10-01T${hhmm.length === 5 ? `${hhmm}:00` : hhmm}Z`;

// Freschezza: il database (poll/realtime) ha le righe di 3 s fa, il canale
// locale finto quelle di 1 s fa (piu' fresche: vincono, come nel vero).
export const MS_DB = ORA_MS - 3000;
export const MS_CANALE = ORA_MS - 1000;

// ------------------------------------------------------------------ id

export const EV = { inter: '34812001', betis: '34812044', bologna: '34812102' } as const;

export const MK = {
    interMo: '1.248120010', interOu25: '1.248120011', interCs: '1.248120012',
    interOu35: '1.248120013', interOu15: '1.248120016',
    betisMo: '1.248120440', betisOu25: '1.248120441', betisOu35: '1.248120443',
} as const;

export const SEL = {
    inter: 47999, torino: 48351, draw: 58805,
    betis: 60226, getafe: 60228,
    under25: 47972, over25: 47973, under35: 1222347, over35: 1222346,
    under15: 1221385, over15: 1221386,
} as const;

// ------------------------------------------------------------------ partite seguite

export const FOLLOWS: LiveFollow[] = [
    {
        event_id: EV.inter, fixture_id: 1378123, league_name: 'Serie A',
        home_name: 'Inter', away_name: 'Torino', open_date: alle('07:25'),
        status: 'STREAMING', error_detail: null, inplay: true, minute: 58,
        score_home: 1, score_away: 0, live_status: 'OPEN', score_source: 'betfair',
        updated_at: fa(3), origine: 'manuale',
    },
    {
        event_id: EV.betis, fixture_id: 1390457, league_name: 'La Liga',
        home_name: 'Real Betis', away_name: 'Getafe', open_date: alle('08:07'),
        status: 'STREAMING', error_detail: null, inplay: true, minute: 31,
        score_home: 0, score_away: 0, live_status: 'OPEN', score_source: 'betfair',
        updated_at: fa(3), origine: 'auto',
    },
    {
        event_id: EV.bologna, fixture_id: 1378127, league_name: 'Serie A',
        home_name: 'Bologna', away_name: 'Udinese', open_date: alle('08:52'),
        status: 'PENDING', error_detail: null, inplay: null, minute: null,
        score_home: null, score_away: null, live_status: null, score_source: null,
        updated_at: null, origine: 'auto',
    },
];

// ------------------------------------------------------------------ mercati (live_now)

type Q = [string, number, number | null, number | null, number | null]; // nome, id, back, lay, ltp

function mercato(market_id: string, market_type: string, market_name: string, q: Q[]): LiveNowMarket {
    return {
        market_id, market_type, market_name, status: 'OPEN',
        selections: q.map(([name, selection_id, back, lay, ltp]) => ({ selection_id, name, back, lay, ltp })),
    };
}

const MERCATI_INTER: LiveNowMarket[] = [
    mercato(MK.interMo, 'MATCH_ODDS', 'Match Odds', [
        ['Inter', SEL.inter, 1.38, 1.39, 1.38],
        ['Torino', SEL.torino, 11.5, 12, 11.5],
        ['The Draw', SEL.draw, 5.6, 5.7, 5.6],
    ]),
    mercato(MK.interOu25, 'OVER_UNDER_25', 'Over/Under 2.5 Goals', [
        ['Under 2.5 Goals', SEL.under25, 1.62, 1.63, 1.62],
        ['Over 2.5 Goals', SEL.over25, 2.6, 2.62, 2.62],
    ]),
    mercato(MK.interOu35, 'OVER_UNDER_35', 'Over/Under 3.5 Goals', [
        ['Under 3.5 Goals', SEL.under35, 1.22, 1.23, 1.22],
        ['Over 3.5 Goals', SEL.over35, 5.4, 5.6, 5.5],
    ]),
    mercato(MK.interCs, 'CORRECT_SCORE', 'Correct Score', [
        ['1 - 0', 2, 3.65, 3.7, 3.65],
        ['2 - 0', 5, 6.4, 6.6, 6.5],
        ['1 - 1', 3, 7.2, 7.4, 7.2],
        ['2 - 1', 6, 9.6, 10, 9.8],
        ['3 - 0', 10, 22, 23, 22],
        ['3 - 1', 11, 32, 34, 34],
        ['2 - 2', 7, 48, 55, 50],
        ['Any Other Home Win', 4506345, 30, 34, 32],
    ]),
    mercato(MK.interOu15, 'OVER_UNDER_15', 'Over/Under 1.5 Goals', [
        ['Under 1.5 Goals', SEL.under15, 2.94, 2.98, 2.96],
        ['Over 1.5 Goals', SEL.over15, 1.51, 1.52, 1.51],
    ]),
];

const MERCATI_BETIS: LiveNowMarket[] = [
    mercato(MK.betisMo, 'MATCH_ODDS', 'Match Odds', [
        ['Real Betis', SEL.betis, 2.02, 2.04, 2.04],
        ['Getafe', SEL.getafe, 5.9, 6, 5.9],
        ['The Draw', SEL.draw, 3.25, 3.3, 3.3],
    ]),
    mercato(MK.betisOu25, 'OVER_UNDER_25', 'Over/Under 2.5 Goals', [
        ['Under 2.5 Goals', SEL.under25, 1.86, 1.88, 1.87],
        ['Over 2.5 Goals', SEL.over25, 2.14, 2.16, 2.14],
    ]),
    mercato(MK.betisOu35, 'OVER_UNDER_35', 'Over/Under 3.5 Goals', [
        ['Under 3.5 Goals', SEL.under35, 1.36, 1.37, 1.36],
        ['Over 3.5 Goals', SEL.over35, 3.7, 3.8, 3.75],
    ]),
];

function riga(event_id: string, minute: number, sh: number, sa: number, markets: LiveNowMarket[],
    ms: number, cards: [number, number]): LiveNowRow {
    return {
        event_id, inplay: true, minute, score_home: sh, score_away: sa, status: 'OPEN',
        score_source: 'betfair',
        state: {
            markets, order_mode: 'PAPER', updated_ms: ms,
            stats: { cards: { yellow_home: cards[0], yellow_away: cards[1], red_home: 0, red_away: 0 } },
        },
        updated_at: new Date(ms).toISOString(),
    };
}

/** riga live_now per evento (`ms` = istante del produttore: MS_DB o MS_CANALE) */
export function liveNowDi(eventId: string, ms: number): LiveNowRow | null {
    if (eventId === EV.inter) return riga(EV.inter, 58, 1, 0, MERCATI_INTER, ms, [1, 2]);
    if (eventId === EV.betis) return riga(EV.betis, 31, 0, 0, MERCATI_BETIS, ms, [0, 1]);
    return null;
}

// ------------------------------------------------------------------ ladder (live_ladder)

/** passo Betfair della fascia di prezzo che contiene `p` */
function passo(p: number): number {
    if (p < 2) return 0.01;
    if (p < 3) return 0.02;
    if (p < 4) return 0.05;
    if (p < 6) return 0.1;
    if (p < 10) return 0.2;
    if (p < 20) return 0.5;
    if (p < 30) return 1;
    if (p < 50) return 2;
    if (p < 100) return 5;
    return 10;
}
const r2 = (x: number) => Math.round(x * 100) / 100;
const su = (p: number) => r2(p + passo(p));
const giu = (p: number) => r2(p - passo(p - 1e-9));

/** pseudo-casuale deterministico in [0,1) (stessa idea di prototipo/js/data.js) */
function rnd(k: number): number {
    const x = Math.sin(k * 999 + 7) * 10000;
    return x - Math.floor(x);
}

/** volume scambiato per selezione (EUR), proporzionale al mercato */
const TV: Record<string, number> = {
    [MK.interMo]: 1843210, [MK.interOu25]: 612400, [MK.interOu35]: 288150,
    [MK.interCs]: 156820, [MK.interOu15]: 201930,
    [MK.betisMo]: 512330, [MK.betisOu25]: 174260, [MK.betisOu35]: 82410,
};

function scala(m: LiveNowMarket, k: number, seme: number): LiveLadderSelection {
    const s = m.selections[k];
    // la favorita del mercato ha la fetta piu' grossa del volume
    const pesi = m.selections.map((x) => 1 / Math.max(1.01, x.ltp ?? x.back ?? 10));
    const quota = pesi[k] / pesi.reduce((a, b) => a + b, 0);
    const tvSel = r2((TV[m.market_id] ?? 50000) * quota);
    const base = Math.max(25, Math.min(3200, tvSel / 420));
    const back: [number, number][] = [];
    const lay: [number, number][] = [];
    if (s.back != null) {
        let p = s.back;
        for (let i = 0; i < 10 && p > 1.01; i++, p = giu(p)) {
            back.push([p, r2(base * (0.35 + rnd(seme + i)) * (i === 0 ? 0.8 : 1 + i * 0.12))]);
        }
    }
    if (s.lay != null) {
        let p = s.lay;
        for (let i = 0; i < 10 && p < 1000; i++, p = su(p)) {
            lay.push([p, r2(base * (0.3 + rnd(seme + 40 + i)) * (i === 0 ? 0.7 : 1 + i * 0.1))]);
        }
    }
    // volume per prezzo attorno all'LTP (storia della partita: piu' largo sopra,
    // dove la quota stava prima del gol), somma = volume della selezione
    const trdGrezzo: [number, number][] = [];
    const ltp = s.ltp ?? s.back ?? s.lay;
    if (ltp != null) {
        let p = ltp;
        for (let i = 0; i < 7 && p > 1.01; i++, p = giu(p)) trdGrezzo.push([p, (8 - i) * (0.5 + rnd(seme + 80 + i))]);
        p = su(ltp);
        for (let i = 1; i < 14 && p < 1000; i++, p = su(p)) trdGrezzo.push([p, (15 - i) * 0.6 * (0.5 + rnd(seme + 120 + i))]);
    }
    const somma = trdGrezzo.reduce((a, [, v]) => a + v, 0) || 1;
    const trd = trdGrezzo
        .map(([p, v]): [number, number] => [p, r2((v / somma) * tvSel)])
        .sort((a, b) => a[0] - b[0]);
    const b3 = back.slice(0, 3).reduce((a, [, v]) => a + v, 0);
    const l3 = lay.slice(0, 3).reduce((a, [, v]) => a + v, 0);
    const tot = b3 + l3 || 1;
    const backPct = Math.round((b3 / tot) * 100);
    return {
        selection_id: s.selection_id, name: s.name, ltp: s.ltp, tv: tvSel,
        back, lay, trd, wom: { back_pct: backPct, lay_pct: 100 - backPct },
    };
}

const TUTTI: { eventId: string; m: LiveNowMarket }[] = [
    ...MERCATI_INTER.map((m) => ({ eventId: EV.inter, m })),
    ...MERCATI_BETIS.map((m) => ({ eventId: EV.betis, m })),
];

/** riga live_ladder del mercato (`ms` = MS_DB o MS_CANALE), null se ignoto */
export function ladderDi(marketId: string, ms: number): LiveLadderRow | null {
    const i = TUTTI.findIndex((x) => x.m.market_id === marketId);
    if (i < 0) return null;
    const { eventId, m } = TUTTI[i];
    return {
        event_id: eventId, market_id: m.market_id, market_type: m.market_type,
        market_name: m.market_name, status: m.status ?? 'OPEN',
        ladder: { updated_ms: ms, selections: m.selections.map((_, k) => scala(m, k, i * 300 + k * 37)) },
        updated_at: new Date(ms).toISOString(),
    };
}

/** tutti i mercati con ladder (per i push 'ladder' del canale finto) */
export const MERCATI_CON_LADDER: string[] = TUTTI.map((x) => x.m.market_id);

// ------------------------------------------------------------------ segnali del motore

function segnale(market_id: string, market_type: string, market_name: string, selection_id: number,
    selection_name: string, prob: number, mb: number, ml: number, direction: Signal['direction'],
    confidence: number, kelly: number): Signal {
    const fair = r2(1 / prob);
    return {
        market_id, market_type, market_name, selection_id, selection_name, model_prob: prob,
        market_back: mb, market_lay: ml, fair_back: fair, fair_lay: fair,
        edge: Math.round((prob * mb - 1) * 1000) / 1000, direction, confidence, kelly_stake: kelly,
    };
}

export const SEGNALI_INTER: LiveSignalsRow = {
    event_id: EV.inter,
    signals: {
        signals: [
            segnale(MK.interMo, 'MATCH_ODDS', 'Match Odds', SEL.inter, 'Inter', 0.752, 1.38, 1.39, 'BACK', 0.72, 4.2),
            segnale(MK.interOu25, 'OVER_UNDER_25', 'Over/Under 2.5 Goals', SEL.under25, 'Under 2.5 Goals', 0.644, 1.62, 1.63, 'BACK', 0.64, 3.1),
            segnale(MK.interMo, 'MATCH_ODDS', 'Match Odds', SEL.draw, 'The Draw', 0.168, 5.6, 5.7, 'HOLD', 0.31, 0),
        ],
        updated_ms: ORA_MS - 2000,
        commission: 0.05,
        // P(gol nei prossimi 5') 0,24: sopra la soglia ambra (0,22) del banner
        hazard: { p_next: 0.24, exp_goals_next: 0.27, horizon_min: 5, minute: 58, lam_home: 0.52, lam_away: 0.31 },
    },
    model_meta: { model: 'poisson_dc_pro', league: 'Serie A' },
    updated_at: fa(2),
};

export const SEGNALI_BETIS: LiveSignalsRow = {
    event_id: EV.betis,
    signals: {
        signals: [
            segnale(MK.betisOu25, 'OVER_UNDER_25', 'Over/Under 2.5 Goals', SEL.under25, 'Under 2.5 Goals', 0.556, 1.86, 1.88, 'BACK', 0.58, 2.4),
        ],
        updated_ms: ORA_MS - 2000,
        commission: 0.05,
        hazard: { p_next: 0.13, exp_goals_next: 0.14, horizon_min: 5, minute: 31, lam_home: 0.71, lam_away: 0.48 },
    },
    model_meta: { model: 'poisson_dc_pro', league: 'La Liga' },
    updated_at: fa(2),
};

// ------------------------------------------------------------------ avvisi

export const AVVISI: Alert[] = [
    {
        id: 811, level: 'WARN', code: 'NEW_MATCHES',
        message: '2 nuove partite agganciate dal runner per i bot.',
        event_id: null, acknowledged: false, created_at: fa(300),
    },
];

// ------------------------------------------------------------------ ordini e posizioni (PAPER)

function ordine(o: Pick<LiveOrderRow, 'id' | 'bet_id' | 'market_id' | 'selection_id' | 'side' | 'price' | 'size'
    | 'size_matched' | 'average_price_matched' | 'status' | 'persistence' | 'placed_at' | 'matched_at'>,
    request_id: number): LiveOrderRow {
    const size = o.size ?? 0;
    return {
        ...o,
        source: 'runner', client_order_ref: `ui-${o.id}`, request_id, mode: 'paper',
        event_id: EV.inter, handicap: 0, order_type: 'LIMIT',
        size_remaining: r2(size - o.size_matched), size_cancelled: 0, size_lapsed: 0, size_voided: 0,
        updated_at: o.matched_at ?? o.placed_at,
    };
}

/** ordini PAPER per mercato: Inter MO (abbinato + uscita sul book) e Under 2.5 */
export const ORDINI: Record<string, LiveOrderRow[]> = {
    [MK.interMo]: [
        ordine({
            id: 9134, bet_id: '371246112874', market_id: MK.interMo, selection_id: SEL.inter,
            side: 'lay', price: 1.35, size: 5.63, size_matched: 0, average_price_matched: 0,
            status: 'EXECUTABLE', persistence: 'PERSIST', placed_at: fa(95), matched_at: null,
        }, 55218),
        ordine({
            id: 9101, bet_id: '371245980112', market_id: MK.interMo, selection_id: SEL.inter,
            side: 'back', price: 1.52, size: 5, size_matched: 5, average_price_matched: 1.52,
            status: 'EXECUTION_COMPLETE', persistence: 'LAPSE', placed_at: alle('07:58:02'), matched_at: alle('07:58:03'),
        }, 55107),
    ],
    [MK.interOu25]: [
        ordine({
            id: 9088, bet_id: '371245871540', market_id: MK.interOu25, selection_id: SEL.under25,
            side: 'back', price: 1.55, size: 4, size_matched: 4, average_price_matched: 1.55,
            status: 'EXECUTION_COMPLETE', persistence: 'LAPSE', placed_at: alle('07:41:10'), matched_at: alle('07:41:12'),
        }, 55063),
    ],
};

function posizione(p: Pick<LivePositionRow, 'id' | 'market_id' | 'selection_id' | 'matched_if_win' | 'matched_if_lose'
    | 'worst_if_win' | 'worst_if_lose' | 'selection_exposure' | 'unmatched_lay_exposure' | 'net_position' | 'updated_at'>): LivePositionRow {
    return { ...p, mode: 'paper', event_id: EV.inter, handicap: 0, unmatched_back_exposure: 0 };
}

/** posizioni PAPER per mercato (specchio betfair_live_positions) */
export const POSIZIONI: Record<string, LivePositionRow[]> = {
    // BACK 5 @ 1,52 abbinato: +2,60 se vince, -5,00 se perde; LAY 5,63 @ 1,35 sul book
    // (responsabilita' 1,97): nel caso peggiore il "se vince" scende a +0,63.
    [MK.interMo]: [posizione({
        id: 3301, market_id: MK.interMo, selection_id: SEL.inter,
        matched_if_win: 2.6, matched_if_lose: -5, worst_if_win: 0.63, worst_if_lose: -5,
        selection_exposure: 5, unmatched_lay_exposure: 1.97, net_position: 5, updated_at: fa(95),
    })],
    [MK.interOu25]: [posizione({
        id: 3288, market_id: MK.interOu25, selection_id: SEL.under25,
        matched_if_win: 2.2, matched_if_lose: -4, worst_if_win: 2.2, worst_if_lose: -4,
        selection_exposure: 4, unmatched_lay_exposure: 0, net_position: 4, updated_at: alle('07:41:12'),
    })],
};

// ------------------------------------------------------------------ x-hedge dell'evento

function xhedgeInter(): XhedgeRow {
    // P&L per risultato finale (casa 1..4, ospite 0..3; si parte dall'1-0):
    // BACK Inter 5 @ 1,52 + BACK Under 2.5 4 @ 1,55
    const grid: Array<[number, number, number]> = [];
    for (let h = 1; h <= 4; h++) {
        for (let a = 0; a <= 3; a++) {
            const mo = h > a ? 2.6 : -5;
            const ou = h + a <= 2 ? 2.2 : -4;
            grid.push([h, a, r2(mo + ou)]);
        }
    }
    const per = [...grid].sort((x, y) => x[2] - y[2]);
    const media = r2(grid.reduce((s, g) => s + g[2], 0) / grid.length);
    return {
        event_id: EV.inter, mode: 'paper', updated_at: fa(4),
        analysis: {
            n_positions: 2, ignored_orders: 0, cs_market_id: MK.interCs,
            summary: {
                worst: per[0][2], best: per[per.length - 1][2], mean: media,
                worst_scoreline: [per[0][0], per[0][1]],
                best_scoreline: [per[per.length - 1][0], per[per.length - 1][1]],
                n_scorelines: grid.length,
            },
            grid,
            suggestion: null,
        },
    };
}
export const XHEDGE: Record<string, XhedgeRow[]> = { [EV.inter]: [xhedgeInter()] };

// ------------------------------------------------------------------ registro del runner

export const AUDIT: LiveAuditRow[] = [
    { id: 70412, ts: fa(95), mode: 'paper', action: 'place', market_id: MK.interMo, selection_id: SEL.inter, side: 'lay', price: 1.35, size: 5.63, status: 'EXECUTABLE', error: null, request_id: 55218, detail: { persistence: 'PERSIST' } },
    { id: 70391, ts: alle('07:58:03'), mode: 'paper', action: 'place', market_id: MK.interMo, selection_id: SEL.inter, side: 'back', price: 1.52, size: 5, status: 'EXECUTION_COMPLETE', error: null, request_id: 55107, detail: { persistence: 'LAPSE' } },
    { id: 70355, ts: alle('07:41:12'), mode: 'paper', action: 'place', market_id: MK.interOu25, selection_id: SEL.under25, side: 'back', price: 1.55, size: 4, status: 'EXECUTION_COMPLETE', error: null, request_id: 55063, detail: { persistence: 'LAPSE' } },
];

// ------------------------------------------------------------------ scalper

const HABITAT_RIGHE = [
    { market_id: '1.248121300', event: 'Brentford v Fulham', ko: '2026-10-01 09:22', tv: 402770, depth: 1240, spread: 1, osc: 0.42, score: 78, verdict: 'GO \u2705' },
    { market_id: '1.248121900', event: 'Atalanta v Genoa', ko: '2026-10-01 10:22', tv: 211480, depth: 880, spread: 1, osc: 0.38, score: 71, verdict: 'GO \u2705' },
    { market_id: '1.248122150', event: 'Feyenoord v AZ Alkmaar', ko: '2026-10-01 10:52', tv: 77310, depth: 310, spread: 2.6, osc: 0.21, score: 47, verdict: 'forse' },
    { market_id: '1.248121770', event: 'Lens v Nantes', ko: '2026-10-01 09:52', tv: 98640, depth: 140, spread: 1.8, osc: 0.12, score: 34, verdict: 'NO' },
    { market_id: '1.248122620', event: 'Napoli v Lazio', ko: '2026-10-01 12:52', tv: 690420, depth: 2940, spread: 1, osc: 0.33, score: 54, verdict: 'CON BIAS o NO (elite)' },
];

const ATTIVITA_HABITAT: ScalperActivityRow = {
    id: 66120, event_id: 'habitat', ts: fa(482), kind: 'habitat_scan',
    payload: { rows: HABITAT_RIGHE, n: HABITAT_RIGHE.length },
};

/** stato dello scalper per evento ('habitat' = ultimo scan delle partite adatte) */
export function scalperDi(eventId: string): ScalperState {
    if (eventId === 'habitat') return { control: null, activity: [ATTIVITA_HABITAT] };
    if (eventId !== EV.inter) return { control: null, activity: [] };
    // ultima sessione pre-match su Inter-Torino: completata al calcio d'inizio
    return {
        control: {
            event_id: EV.inter, status: 'done', mode: 'maker', dry_run: true, stake: 25,
            params: {
                scalp_ticks: 1, stop_ticks: 1, min_flow: 10, min_size: 300, price_min: 1.5, price_max: 4.6,
                entry_stop_before_s: 420, flatten_before_s: 180, event_profit_target: 1, event_loss_cap: 1.5,
                one_green_per_phase: true, sniper_mode: true, sniper_stake: 10,
            },
            bias: null, bias_meta: null,
            stats: {
                orders_placed: 14, dry_quotes: 14, cycles: 5, scalps: 3, roundtrips: 0, scratches: 1,
                stops: 1, flattens: 0, pnl_locked: 0.71, pnl_settled: 0.71,
                greens_prematch: 1, greens_inplay: 0, pnl_prematch: 0.71, pnl_inplay: 0,
            },
            error: null,
            requested_at: alle('06:31:40'), started_at: alle('06:31:44'),
            stopped_at: alle('07:22:00'), heartbeat_at: alle('07:22:00'),
        },
        activity: [
            { id: 66101, event_id: EV.inter, ts: alle('07:22:00'), kind: 'done', payload: { reason: 'flatten_before_ko' } },
            { id: 66094, event_id: EV.inter, ts: alle('07:09:02'), kind: 'cycle', payload: { side: 'BACK', ticks: 1 } },
            { id: 66090, event_id: EV.inter, ts: alle('07:08:40'), kind: 'scratch', payload: { reason: 'flow' } },
        ],
    };
}
