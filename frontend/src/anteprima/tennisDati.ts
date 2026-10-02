// ============================================================================
// tennisDati.ts - SOLO PER L'ANTEPRIMA POPOLATA di /tennis e /tennis/terminal.
//
// Non e' importato dall'app: lo legge solo tennisFinto.ts (alias Vite di
// '@/lib/tennis' in confronto2/strumenti/alias_tennis.mjs). Dati PURI della
// giornata del prototipo (AUDIT_2026-10-01/REDESIGN/prototipo/js/s_tennis.js +
// ladder.js + data.js): Sinner-Draper ATP Pechino in gioco 6-4 2-1 (Sinner al
// servizio, 40-15), Swiatek-Paolini WTA Pechino 3-3, in attesa Musetti-Fritz,
// Cobolli-Shelton, Gauff-Andreeva, Arnaldi-Etcheverry e altre.
// Il runner tennis e' in PAPER; Tennis Pro operativo su Sinner-Draper (BACK
// Sinner 5 @ 1,29 sul break point, uscita LAY 5,20 @ 1,24 sul book), Tennis
// Scalper "Concluso" (missione 1 tick pre-match riuscita), FLB e Swing spenti.
//
// Id coerenti con gli altri finti (controlRoomFinto.ts, giornataBot.ts):
// evento 34813501, Match Odds 1.248135010, selezioni 9876501/9876502.
// Chiavi e tipi: quelli di lib/tennis.ts (e LiveLadderRow / LiveOrderRow /
// LivePositionRow), controllati da tsc. Orologio: 2026-10-01T08:38:00Z
// (10:38 a Roma), lo stesso di scatta.mjs.
// ============================================================================
import type { LiveLadderRow, LiveLadderSelection } from '../lib/live';
import type { LiveOrderRow, LivePositionRow } from '../lib/liveOrders';
import type {
    TennisBotActivityRow, TennisBotControl, TennisBotKey, TennisBotStats, TennisEventMarket,
    TennisFixtureRow, TennisFollow, TennisLiveNowRow, TennisMoneylineRunner, TennisOddLevel,
    TennisPointEvent, TennisScoreState,
} from '../lib/tennis';
import { TENNIS_BOT_REGISTRY } from '../lib/tennis';

// ------------------------------------------------------------------ orologio

export const ORA_MS = Date.parse('2026-10-01T08:38:00Z');
const fa = (s: number) => new Date(ORA_MS - s * 1000).toISOString();
const alle = (hms: string) => `2026-10-01T${hms.length === 5 ? `${hms}:00` : hms}Z`;
/** il database ha le righe di 3 s fa (come seguiLiveDati.ts) */
export const MS_DB = ORA_MS - 3000;

// ------------------------------------------------------------------ prezzi Betfair

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
/** il tick Betfair valido piu' vicino sotto (o uguale a) `x` */
function tickSotto(x: number): number {
    const s = passo(x);
    return r2(Math.floor((x + 1e-9) / s) * s);
}
/** pseudo-casuale deterministico in [0,1) (stessa idea di prototipo/js/data.js) */
function rnd(k: number): number {
    const x = Math.sin(k * 999 + 7) * 10000;
    return x - Math.floor(x);
}

// ------------------------------------------------------------------ partite

interface Giocatore { nome: string; sel: number }
interface Partita {
    ev: string;
    mo: string;
    torneo: string;
    torneoId: string;
    regione: string;
    open: string;
    inplay: boolean;
    status: string;
    matched: number;
    g1: Giocatore;
    g2: Giocatore;
    /** miglior LAY (= LTP) di g1 all'istante ms; null = mercato chiuso */
    lay1: (ms: number) => number | null;
}

/** Match Odds: '1.2' + ultime 7 cifre dell'evento + '0' (come controlRoomFinto.ts) */
const mo = (ev: string) => `1.2${ev.slice(-7)}0`;
const fisso = (p: number) => () => p;

/** interpolazione a gradini su chiavi [secondi prima di ORA, prezzo] */
function percorso(chiavi: [number, number][], seme: number) {
    return (ms: number): number => {
        const s = (ORA_MS - ms) / 1000;
        const ultima = chiavi[chiavi.length - 1];
        let p = s >= chiavi[0][0] ? chiavi[0][1] : ultima[1];
        for (let i = 0; i < chiavi.length - 1; i++) {
            const [s0, p0] = chiavi[i];
            const [s1, p1] = chiavi[i + 1];
            if (s < s0 && s >= s1) {
                p = p0 + (p1 - p0) * ((s0 - s) / (s0 - s1 || 1));
                break;
            }
        }
        // rumore di +-1 tick ogni tanto (mai sull'ultimo tratto: la quota finale e' quella del board)
        const k = Math.floor(ms / 3000);
        const rumore = s > 12 && rnd(seme + k) > 0.7 ? (rnd(seme + k + 1) > 0.5 ? 1 : -1) : 0;
        let q = tickSotto(p + 1e-6);
        if (rumore > 0) q = su(q);
        if (rumore < 0) q = giu(q);
        return q;
    };
}

// Sinner-Draper: break di Sinner nel 3o game del 2o set (~2 minuti fa), poi
// Sinner al servizio sul 40-15: la quota scende da 1,31 a 1,25.
const PERCORSO_SINNER = percorso([
    [260, 1.31], [215, 1.3], [180, 1.31], [150, 1.29], [128, 1.3], [110, 1.27],
    [85, 1.26], [50, 1.26], [25, 1.25], [0, 1.25],
], 11);
// Swiatek-Paolini: 3-3 nel primo set, Paolini al servizio 15-30
const PERCORSO_SWIATEK = percorso([[260, 1.44], [170, 1.45], [90, 1.46], [30, 1.47], [0, 1.47]], 23);

export const EV = {
    sinner: '34813501', swiatek: '34813522', musetti: '34813540', cobolli: '34813561',
    gauff: '34813580', arnaldi: '34813601',
    medvedev: '34813545', sabalenka: '34813590', deminaur: '34813566', darderi: '34813612',
    // l'evento generico di scatta.mjs (pagina 'tennis-terminal-match'): una COPIA
    // di Sinner-Draper coi nomi dell'URL di scatta, per avere anche quella popolata
    generico: '34000001',
} as const;

const KO = (min: number) => new Date(ORA_MS + min * 60e3).toISOString();
const gioc = (nome: string, sel: number): Giocatore => ({ nome, sel });

const PECHINO_ATP = { torneo: 'ATP Pechino', torneoId: '12764512', regione: 'Cina' };
const PECHINO_WTA = { torneo: 'WTA Pechino', torneoId: '12764530', regione: 'Cina' };
const TOKYO = { torneo: 'ATP Tokyo', torneoId: '12764498', regione: 'Giappone' };
const ORLEANS = { torneo: 'Challenger Orleans', torneoId: '12771044', regione: 'Francia' };

const partita = (ev: string, t: typeof PECHINO_ATP, minKo: number, inplay: boolean, matched: number,
    g1: Giocatore, g2: Giocatore, lay1: (ms: number) => number | null, marketId?: string): Partita => ({
    ev, mo: marketId ?? mo(ev), ...t, open: KO(minKo), inplay, status: 'OPEN', matched, g1, g2, lay1,
});

/** le partite di OGGI (1 ottobre), ordine del prototipo + altre del tabellone */
export const OGGI: Partita[] = [
    partita(EV.sinner, PECHINO_ATP, -42, true, 2210450, gioc('J. Sinner', 9876501), gioc('J. Draper', 9876502), PERCORSO_SINNER),
    partita(EV.swiatek, PECHINO_WTA, -12, true, 803120, gioc('I. Swiatek', 9030001), gioc('J. Paolini', 9030002), PERCORSO_SWIATEK),
    partita(EV.musetti, PECHINO_ATP, 28, false, 341800, gioc('L. Musetti', 354001), gioc('T. Fritz', 354002), fisso(2.4)),
    partita(EV.cobolli, TOKYO, 65, false, 121300, gioc('F. Cobolli', 356101), gioc('B. Shelton', 356102), fisso(2.54)),
    partita(EV.deminaur, TOKYO, 95, false, 98400, gioc('A. de Minaur', 356601), gioc('K. Nishikori', 356602), fisso(1.45)),
    partita(EV.gauff, PECHINO_WTA, 120, false, 289770, gioc('C. Gauff', 358001), gioc('M. Andreeva', 358002), fisso(1.9)),
    partita(EV.medvedev, PECHINO_ATP, 150, false, 512900, gioc('D. Medvedev', 354501), gioc('A. Rublev', 354502), fisso(1.83)),
    partita(EV.arnaldi, ORLEANS, 180, false, 22410, gioc('M. Arnaldi', 360101), gioc('T. Etcheverry', 360102), fisso(1.98)),
    partita(EV.darderi, ORLEANS, 225, false, 14880, gioc('L. Darderi', 361201), gioc('A. Mannarino', 361202), fisso(1.76)),
    partita(EV.sabalenka, PECHINO_WTA, 240, false, 655410, gioc('A. Sabalenka', 359001), gioc('E. Rybakina', 359002), fisso(1.62)),
];

/** la copia generica per l'URL di scatta.mjs (NON e' nel tabellone del giorno) */
const GENERICA: Partita = partita(EV.generico, PECHINO_ATP, -42, true, 2210450,
    gioc('Giocatore Uno', 9876501), gioc('Giocatore Due', 9876502), PERCORSO_SINNER, '1.250000001');

/** ieri: partite gia' chiuse (mercato CLOSED, niente quote) */
const IERI: Partita[] = [
    { ...partita('34809911', PECHINO_ATP, -1440 + 30, false, 1488200, gioc('T. Fritz', 349901), gioc('F. Tiafoe', 349902), () => null), status: 'CLOSED' },
    { ...partita('34809937', PECHINO_WTA, -1440 + 95, false, 402310, gioc('J. Paolini', 349931), gioc('D. Kasatkina', 349932), () => null), status: 'CLOSED' },
    { ...partita('34809954', TOKYO, -1440 - 120, false, 233870, gioc('F. Cobolli', 349951), gioc('T. Machac', 349952), () => null), status: 'CLOSED' },
];

/** domani: tutte pre-match */
const DOMANI: Partita[] = [
    partita('34816020', TOKYO, 1440 - 60, false, 84210, gioc('C. Alcaraz', 381001), gioc('H. Hurkacz', 381002), fisso(1.29)),
    partita('34816044', PECHINO_WTA, 1440 + 15, false, 41300, gioc('J. Pegula', 381201), gioc('Q. Zheng', 381202), fisso(2.12)),
    partita('34816071', PECHINO_ATP, 1440 + 90, false, 52770, gioc('L. Musetti', 381401), gioc('A. Zverev', 381402), fisso(2.66)),
    partita('34816088', ORLEANS, 1440 + 150, false, 6120, gioc('L. Sonego', 381601), gioc('G. Mpetshi Perricard', 381602), fisso(1.95)),
];

const TUTTE: Partita[] = [...OGGI, GENERICA];
const perEvento = (ev: string) => TUTTE.find((p) => p.ev === ev) ?? null;
const perMercato = (mid: string) => TUTTE.find((p) => p.mo === mid) ?? null;

// ------------------------------------------------------------------ quote all'istante

interface Quota { back: number | null; lay: number | null; ltp: number | null }

/** quote di g1 e g2 all'istante ms: g2 dal complemento di g1 (book ~100%) */
function quote(p: Partita, ms: number): [Quota, Quota] {
    const l1 = p.lay1(ms);
    if (l1 == null) return [{ back: null, lay: null, ltp: null }, { back: null, lay: null, ltp: null }];
    const b1 = giu(l1);
    const b2 = tickSotto(1 / (1 - 1 / l1));
    return [{ back: b1, lay: l1, ltp: l1 }, { back: b2, lay: su(b2), ltp: b2 }];
}

// ------------------------------------------------------------------ 1) partite del giorno

function livelli(primo: number | null, verso: 'giu' | 'su', base: number, seme: number): TennisOddLevel[] {
    if (primo == null) return [];
    const out: TennisOddLevel[] = [];
    let p = primo;
    for (let i = 0; i < 3; i++, p = verso === 'giu' ? giu(p) : su(p)) {
        out.push({ price: p, size: r2(base * (0.4 + rnd(seme + i)) * (1 + i * 0.35)) });
    }
    return out;
}

function runnerDi(p: Partita, k: 0 | 1, q: Quota): TennisMoneylineRunner {
    const g = k === 0 ? p.g1 : p.g2;
    const base = Math.max(18, Math.min(2400, p.matched / 900)) * (k === 0 ? 1.2 : 0.6);
    return {
        selection_id: g.sel, name: g.nome, sort_priority: k + 1,
        back: livelli(q.back, 'giu', base, g.sel % 997),
        lay: livelli(q.lay, 'su', base * 0.85, (g.sel % 997) + 50),
        ltp: q.ltp,
    };
}

function mercatiDi(p: Partita): TennisEventMarket[] {
    const n = p.mo.slice(0, -1);
    return [
        { market_id: p.mo, market_type: 'MATCH_ODDS', market_name: 'Match Odds', total_matched: p.matched },
        { market_id: `${n}1`, market_type: 'SET_BETTING', market_name: 'Set Betting', total_matched: r2(p.matched * 0.11) },
        { market_id: `${n}2`, market_type: 'SET_WINNER', market_name: p.inplay ? 'Set 2 Winner' : 'Set 1 Winner', total_matched: r2(p.matched * 0.07) },
        { market_id: `${n}3`, market_type: 'GAME_HANDICAP', market_name: 'Handicap', total_matched: r2(p.matched * 0.04) },
    ];
}

function fixtureDi(p: Partita): TennisFixtureRow {
    const [q1, q2] = quote(p, MS_DB);
    return {
        event_id: p.ev, market_id: p.mo, competition_id: p.torneoId, competition_name: p.torneo,
        competition_region: p.regione, open_date: p.open, inplay: p.inplay, status: p.status,
        player1: runnerDi(p, 0, q1), player2: runnerDi(p, 1, q2),
        total_matched: p.matched, markets: mercatiDi(p),
        captured_at: p.status === 'CLOSED' ? p.open : fa(20),
    };
}

/** get_tennis_fixtures(p_date): la giornata richiesta (yyyy-MM-dd, ora di Roma) */
export function fixturesDel(giorno: string): TennisFixtureRow[] {
    if (giorno === '2026-10-01') return OGGI.map(fixtureDi);
    if (giorno === '2026-09-30') return IERI.map(fixtureDi);
    if (giorno === '2026-10-02') return DOMANI.map(fixtureDi);
    return [];
}

// ------------------------------------------------------------------ 2) punteggio e punti

/** Sinner-Draper: 6-4 2-1, Sinner al servizio sul 40-15 (game point) */
const SCORE_SINNER: TennisScoreState = {
    status: 'InPlay',
    sets: { p1: 1, p2: 0 },
    games: { p1: 2, p2: 1 },
    points: { p1: '40', p2: '15' },
    server: 1,
    tiebreak: false,
    game_sequence: { p1: ['6', '2'], p2: ['4', '1'] },
    service_breaks: { p1: 2, p2: 1 },
    current_set: 2,
    current_game: 4,
    set_summary: '6-4 2-1',
    pressure: { break_point: false, set_point: false, game_point: true },
    win_prob_p1: 0.81,
    source: 'ips',
    updated_ms: ORA_MS - 2000,
};

/** Swiatek-Paolini: 3-3 nel primo set, Paolini al servizio 15-30 */
const SCORE_SWIATEK: TennisScoreState = {
    status: 'InPlay',
    sets: { p1: 0, p2: 0 },
    games: { p1: 3, p2: 3 },
    points: { p1: '30', p2: '15' },
    server: 2,
    tiebreak: false,
    game_sequence: { p1: ['3'], p2: ['3'] },
    service_breaks: { p1: 1, p2: 1 },
    current_set: 1,
    current_game: 7,
    set_summary: '3-3',
    pressure: { break_point: false, set_point: false, game_point: false },
    win_prob_p1: 0.66,
    source: 'ips',
    updated_ms: ORA_MS - 4000,
};

// [set, game, vincitore, servizio, tag, punteggio dopo] - piu' vecchio per primo;
// i tag sono la PRESSIONE dopo il punto (come tennis_runner.point_event)
type P = [number, number, 1 | 2, 1 | 2, string[], string];
const PUNTI_SINNER: P[] = [
    // 1o set, 10o game: Sinner serve per il set sul 5-4
    [1, 10, 1, 1, [], '15-0'], [1, 10, 1, 1, [], '30-0'], [1, 10, 2, 1, [], '30-15'],
    [1, 10, 1, 1, ['set', 'game'], '40-15'], [1, 10, 1, 1, [], '0-0'],
    // 2o set: Draper tiene il servizio
    [2, 1, 2, 2, [], '0-15'], [2, 1, 2, 2, [], '0-30'], [2, 1, 1, 2, [], '15-30'],
    [2, 1, 2, 2, ['game'], '15-40'], [2, 1, 2, 2, [], '0-0'],
    // Sinner tiene a zero
    [2, 2, 1, 1, [], '15-0'], [2, 2, 1, 1, [], '30-0'], [2, 2, 1, 1, ['game'], '40-0'], [2, 2, 1, 1, [], '0-0'],
    // il break di Sinner
    [2, 3, 2, 2, [], '0-15'], [2, 3, 1, 2, [], '15-15'], [2, 3, 1, 2, [], '30-15'], [2, 3, 2, 2, [], '30-30'],
    [2, 3, 1, 2, ['break'], '40-30'], [2, 3, 2, 2, [], '40-40'], [2, 3, 1, 2, ['break'], 'A-40'],
    [2, 3, 1, 2, [], '0-0'],
    // Sinner al servizio, 40-15
    [2, 4, 1, 1, [], '15-0'], [2, 4, 2, 1, [], '15-15'], [2, 4, 1, 1, [], '30-15'], [2, 4, 1, 1, ['game'], '40-15'],
];
const PUNTI_SWIATEK: P[] = [
    [1, 6, 1, 1, [], '15-0'], [1, 6, 1, 1, [], '30-0'], [1, 6, 1, 1, ['game'], '40-0'], [1, 6, 1, 1, [], '0-0'],
    [1, 7, 1, 2, [], '15-0'], [1, 7, 2, 2, [], '15-15'], [1, 7, 1, 2, [], '30-15'],
];

function punti(lista: P[], finoA: number, passoS: number): TennisPointEvent[] {
    return lista.map(([set_no, game_no, winner, server, tags, score_after], i) => ({
        ts: new Date(finoA - (lista.length - 1 - i) * passoS * 1000).toISOString(),
        set_no, game_no, winner, server, tags, score_after,
    }));
}

// ------------------------------------------------------------------ tennis_live_now

function nowDi(p: Partita, ms: number): TennisLiveNowRow {
    const [q1, q2] = quote(p, ms);
    const sinnerLike = p.lay1 === PERCORSO_SINNER;
    const score = !p.inplay ? null : sinnerLike ? SCORE_SINNER : SCORE_SWIATEK;
    const lista = !p.inplay ? null : sinnerLike ? PUNTI_SINNER : PUNTI_SWIATEK;
    return {
        event_id: p.ev,
        inplay: p.inplay,
        status: p.status,
        state: {
            markets: [{
                market_id: p.mo, market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: p.status,
                selections: [
                    { selection_id: p.g1.sel, name: p.g1.nome, ...q1 },
                    { selection_id: p.g2.sel, name: p.g2.nome, ...q2 },
                ],
            }],
            order_mode: 'PAPER',
            updated_ms: ms,
        },
        score,
        points: lista ? punti(lista, (score?.updated_ms ?? ms), 34) : null,
        updated_at: new Date(ms).toISOString(),
    };
}

/** riga tennis_live_now dell'evento (null = non in streaming: il runner non l'ha ancora scritta) */
export function liveNowDi(eventId: string): TennisLiveNowRow | null {
    const p = perEvento(eventId);
    if (!p || !FOLLOWS.some((f) => f.event_id === eventId && f.status === 'STREAMING')) return null;
    return nowDi(p, MS_DB);
}

// ------------------------------------------------------------------ partite seguite

function follow(p: Partita, status: TennisFollow['status'], record: boolean): TennisFollow {
    const now = p.inplay ? nowDi(p, MS_DB) : null;
    return {
        event_id: p.ev, competition_name: p.torneo, player1_name: p.g1.nome, player2_name: p.g2.nome,
        open_date: p.open, status, error_detail: null, record,
        inplay: status === 'PENDING' ? null : p.inplay, score: now?.score ?? null,
        live_status: p.inplay ? 'InPlay' : null, updated_at: status === 'PENDING' ? null : fa(3),
    };
}

export const FOLLOWS: TennisFollow[] = [
    follow(OGGI[0], 'STREAMING', true),
    follow(OGGI[1], 'STREAMING', false),
    follow(OGGI[2], 'PENDING', false),
    follow(GENERICA, 'STREAMING', false),
];

// ------------------------------------------------------------------ ladder (tennis_live_ladder)

function scala(p: Partita, k: 0 | 1, q: Quota, ms: number, seme: number): LiveLadderSelection {
    const g = k === 0 ? p.g1 : p.g2;
    // volume per selezione: la favorita ha la fetta grossa; cresce col tempo (~95 EUR/s)
    const quota = k === 0 ? 0.8 : 0.2;
    const tv = r2((p.matched - Math.max(0, (ORA_MS - ms) / 1000) * 95) * quota);
    const base = Math.max(25, Math.min(1400, tv / 900));
    const back: [number, number][] = [];
    const lay: [number, number][] = [];
    if (q.back != null) {
        let x = q.back;
        for (let i = 0; i < 10 && x > 1.01; i++, x = giu(x)) back.push([x, r2(base * (0.35 + rnd(seme + i)) * (i === 0 ? 0.8 : 1 + i * 0.12))]);
    }
    if (q.lay != null) {
        let x = q.lay;
        for (let i = 0; i < 10 && x < 1000; i++, x = su(x)) lay.push([x, r2(base * (0.3 + rnd(seme + 40 + i)) * (i === 0 ? 0.7 : 1 + i * 0.1))]);
    }
    // volume per prezzo: piu' largo sopra la quota (dove stava prima del break)
    const grezzo: [number, number][] = [];
    if (q.ltp != null) {
        let x = q.ltp;
        for (let i = 0; i < 6 && x > 1.01; i++, x = giu(x)) grezzo.push([x, (7 - i) * (0.5 + rnd(seme + 80 + i))]);
        x = su(q.ltp);
        for (let i = 1; i < 12 && x < 1000; i++, x = su(x)) grezzo.push([x, (13 - i) * 0.7 * (0.5 + rnd(seme + 120 + i))]);
    }
    const somma = grezzo.reduce((a, [, v]) => a + v, 0) || 1;
    const trd = grezzo.map(([x, v]): [number, number] => [x, r2((v / somma) * tv)]).sort((a, b) => a[0] - b[0]);
    const b3 = back.slice(0, 3).reduce((a, [, v]) => a + v, 0);
    const l3 = lay.slice(0, 3).reduce((a, [, v]) => a + v, 0);
    const backPct = Math.round((b3 / (b3 + l3 || 1)) * 100);
    return {
        selection_id: g.sel, name: g.nome, ltp: q.ltp, tv,
        back, lay, trd, wom: { back_pct: backPct, lay_pct: 100 - backPct },
    };
}

function ladderAl(p: Partita, ms: number): LiveLadderRow {
    const [q1, q2] = quote(p, ms);
    // seme legato all'istante: il book "respira" tra un aggiornamento e l'altro
    const t = Math.floor(ms / 3000) % 97;
    return {
        event_id: p.ev, market_id: p.mo, market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: p.status,
        ladder: { updated_ms: ms, selections: [scala(p, 0, q1, ms, p.g1.sel % 991 + t), scala(p, 1, q2, ms, p.g2.sel % 991 + t)] },
        updated_at: new Date(ms).toISOString(),
    };
}

/** riga tennis_live_ladder del mercato (solo partite seguite e in streaming) */
export function ladderDi(marketId: string): LiveLadderRow | null {
    const p = perMercato(marketId);
    if (!p || !FOLLOWS.some((f) => f.event_id === p.ev && f.status === 'STREAMING')) return null;
    return ladderAl(p, MS_DB);
}

/**
 * Gli ultimi ~4 minuti del book (un aggiornamento ogni 3 s, dal piu' vecchio),
 * tutti PRIMA della riga di ladderDi: il realtime finto li consegna alla
 * sottoscrizione cosi' Chart (candele 5 s) e Depth (flusso) hanno una storia.
 */
export function storiaLadder(marketId: string): LiveLadderRow[] {
    if (!ladderDi(marketId)) return [];
    const p = perMercato(marketId)!;
    const out: LiveLadderRow[] = [];
    for (let s = 240; s >= 6; s -= 3) out.push(ladderAl(p, MS_DB - s * 1000));
    return out;
}

// ------------------------------------------------------------------ ordini e posizioni (PAPER)

function ordine(p: Partita, o: Pick<LiveOrderRow, 'id' | 'bet_id' | 'selection_id' | 'side' | 'price' | 'size'
    | 'size_matched' | 'average_price_matched' | 'status' | 'persistence' | 'placed_at' | 'matched_at'>,
    request_id: number): LiveOrderRow {
    const size = o.size ?? 0;
    return {
        ...o,
        source: 'runner', client_order_ref: `tennis-${o.id}`, request_id, mode: 'paper',
        event_id: p.ev, market_id: p.mo, handicap: 0, order_type: 'LIMIT',
        size_remaining: r2(size - o.size_matched), size_cancelled: 0, size_lapsed: 0, size_voided: 0,
        updated_at: o.matched_at ?? o.placed_at,
    };
}

function ordiniSinner(p: Partita): LiveOrderRow[] {
    const S1 = p.g1.sel;
    const S2 = p.g2.sel;
    return [
        // Tennis Pro: uscita (target 5 tick) sul book, e la gamba su Draper non abbinata
        ordine(p, { id: 7731, bet_id: '381220446151', selection_id: S1, side: 'lay', price: 1.24, size: 5.2,
            size_matched: 0, average_price_matched: 0, status: 'EXECUTABLE', persistence: 'PERSIST',
            placed_at: alle('08:33:44'), matched_at: null }, 61207),
        ordine(p, { id: 7712, bet_id: '381220311904', selection_id: S2, side: 'back', price: 5.4, size: 2,
            size_matched: 0, average_price_matched: 0, status: 'EXECUTABLE', persistence: 'PERSIST',
            placed_at: alle('08:05:12'), matched_at: null }, 61151),
        // Tennis Pro: ingresso sul break point, abbinato
        ordine(p, { id: 7730, bet_id: '381220445980', selection_id: S1, side: 'back', price: 1.29, size: 5,
            size_matched: 5, average_price_matched: 1.29, status: 'EXECUTION_COMPLETE', persistence: 'PERSIST',
            placed_at: alle('08:33:41'), matched_at: alle('08:33:42') }, 61206),
        // Tennis Scalper: il tick pre-match (ingresso e uscita)
        ordine(p, { id: 7611, bet_id: '381219870233', selection_id: S1, side: 'lay', price: 1.31, size: 5.08,
            size_matched: 5.08, average_price_matched: 1.31, status: 'EXECUTION_COMPLETE', persistence: 'LAPSE',
            placed_at: alle('07:49:51'), matched_at: alle('07:49:58') }, 61021),
        ordine(p, { id: 7610, bet_id: '381219802117', selection_id: S1, side: 'back', price: 1.33, size: 5,
            size_matched: 5, average_price_matched: 1.33, status: 'EXECUTION_COMPLETE', persistence: 'LAPSE',
            placed_at: alle('07:41:01'), matched_at: alle('07:41:03') }, 61010),
    ];
}

function posizioniSinner(p: Partita): LivePositionRow[] {
    // matched: tick pre-match (+0,08 / +0,08), verdi del Pro (+1,07) e BACK 5 @ 1,29
    // aperto (+1,45 se vince Sinner, -5 se perde) => +2,60 / -3,85.
    // Non abbinati: LAY 5,20 @ 1,24 su Sinner (resp. 1,25), BACK 2 @ 5,4 su Draper.
    const riga = (id: number, selection_id: number, v: Pick<LivePositionRow, 'matched_if_win' | 'matched_if_lose'
        | 'worst_if_win' | 'worst_if_lose' | 'selection_exposure' | 'unmatched_back_exposure'
        | 'unmatched_lay_exposure' | 'net_position'>): LivePositionRow => ({
        id, mode: 'paper', event_id: p.ev, market_id: p.mo, selection_id, handicap: 0, ...v, updated_at: alle('08:33:44'),
    });
    return [
        riga(4401, p.g1.sel, { matched_if_win: 2.6, matched_if_lose: -3.85, worst_if_win: 1.35, worst_if_lose: -3.85,
            selection_exposure: 3.85, unmatched_back_exposure: 0, unmatched_lay_exposure: 1.25, net_position: 5 }),
        riga(4402, p.g2.sel, { matched_if_win: -3.85, matched_if_lose: 2.6, worst_if_win: -3.85, worst_if_lose: 0.6,
            selection_exposure: 3.85, unmatched_back_exposure: 2, unmatched_lay_exposure: 0, net_position: 0 }),
    ];
}

/** ordini del mercato nella modalita' richiesta (get_tennis_live_orders) */
export function ordiniDi(marketId: string, mode: string): LiveOrderRow[] {
    const p = perMercato(marketId);
    if (!p || p.lay1 !== PERCORSO_SINNER || mode !== 'paper') return [];
    return ordiniSinner(p);
}

/** posizioni del mercato nella modalita' richiesta (get_tennis_live_positions) */
export function posizioniDi(marketId: string, mode: string): LivePositionRow[] {
    const p = perMercato(marketId);
    if (!p || p.lay1 !== PERCORSO_SINNER || mode !== 'paper') return [];
    return posizioniSinner(p);
}

// ------------------------------------------------------------------ bot tennis (tennis_bot_control)

/** i params come li scrive la UI all'armamento: default del registro, select bool -> boolean */
function paramsArmati(key: TennisBotKey): Record<string, unknown> {
    const d = TENNIS_BOT_REGISTRY.find((x) => x.key === key)!;
    const out: Record<string, unknown> = { ...d.defaults };
    for (const f of d.params) if (f.type === 'select' && f.bool) out[f.key] = out[f.key] === 'on';
    return out;
}

/** l'equity di Tennis Pro nel tempo: [bloccato, aperto, cicli, scalp, scratch, ordini] */
const PASSI_PRO: [number, number, number, number, number, number][] = [
    [0, 0, 0, 0, 0, 1], [0, 0.12, 1, 0, 0, 1], [0, 0.07, 1, 0, 0, 1],
    [0.29, 0.03, 2, 1, 0, 4], [0.29, 0.23, 2, 1, 0, 4], [0.29, 0.18, 2, 1, 0, 4],
    [0.71, 0.11, 3, 2, 1, 7], [1.07, 0, 3, 3, 1, 8], [1.07, 0.16, 4, 3, 1, 9],
];
export const N_PASSI = PASSI_PRO.length;

function controllo(p: Partita, bot_key: TennisBotKey, v: Pick<TennisBotControl, 'status' | 'stats'
    | 'requested_at' | 'started_at' | 'stopped_at' | 'heartbeat_at'>, params: Record<string, unknown>): TennisBotControl {
    return { event_id: p.ev, bot_key, dry_run: false, stake: 5, params, error: null, ...v };
}

/** stato dei bot dell'evento al passo `i` (0..N_PASSI-1) della giornata */
export function botsAlPasso(eventId: string, i: number): { controls: TennisBotControl[]; activity: TennisBotActivityRow[] } {
    const p = perEvento(eventId);
    if (!p || p.lay1 !== PERCORSO_SINNER) return { controls: [], activity: [] };
    const [l, o, cicli, scalp, scratch, ordini] = PASSI_PRO[Math.max(0, Math.min(N_PASSI - 1, i))];
    const statsPro: TennisBotStats = {
        orders_placed: ordini, cycles: cicli, scalps: scalp, scratches: scratch, stops: 0,
        pnl_locked: l, pnl_open: o,
    };
    const statsScalper: TennisBotStats = {
        orders_placed: 2, cycles: 1, roundtrips: 1, scalps: 0, scratches: 0, stops: 0,
        pnl_locked: 0.0752, pnl_open: 0, greens_prematch: 1, greens_inplay: 0, pnl_prematch: 0.0752, pnl_inplay: 0,
    };
    const pro = controllo(p, 'tennis_pro', {
        status: 'running', stats: statsPro, requested_at: alle('07:55:41'), started_at: alle('07:56:02'),
        stopped_at: null, heartbeat_at: fa(3),
    }, {
        ...paramsArmati('tennis_pro'),
        // scritte dal runner (tennis_runner._scrivi_superficie): la mappa riconosce "pechino"
        surface: 'hard', surface_fonte: 'mappa', surface_voce: 'Pechino', surface_torneo: p.torneo,
        surface_testo: 'cemento (mappa: Pechino)',
    });
    const scalper = controllo(p, 'tennis_scalper', {
        status: 'done', stats: statsScalper, requested_at: alle('07:30:12'), started_at: alle('07:30:30'),
        stopped_at: alle('07:50:04'), heartbeat_at: alle('07:50:04'),
    }, paramsArmati('tennis_scalper'));
    let id = 90560;
    const att = (ts: string, bot_key: TennisBotKey, kind: string, payload: Record<string, unknown>): TennisBotActivityRow =>
        ({ id: id--, event_id: p.ev, bot_key, ts: alle(ts), kind, payload });
    const S1 = p.g1.sel;
    // dal piu' recente (come la RPC); le righe "future" rispetto al passo non ci sono ancora
    const tutte: [number, TennisBotActivityRow][] = [
        [8, att('08:33:41', 'tennis_pro', 'entry', { kind: 'break_point', sel: S1, side: 'BACK', price: 1.29, target: 1.24, stop: 1.32 })],
        [7, att('08:31:08', 'tennis_pro', 'exit', { outcome: 'green', kind: 'set_transition', sel: S1, locked: 0.36 })],
        [6, att('08:24:30', 'tennis_pro', 'exit', { outcome: 'green', kind: 'compressed_fav', sel: S1, locked: 0.42 })],
        [6, att('08:19:55', 'tennis_pro', 'exit', { outcome: 'scratch', kind: 'break_point', sel: S1, locked: 0 })],
        [3, att('08:05:02', 'tennis_pro', 'exit', { outcome: 'green', kind: 'break_point', sel: S1, locked: 0.29 })],
        [1, att('07:58:40', 'tennis_pro', 'entry', { kind: 'break_point', sel: S1, side: 'BACK', price: 1.36, target: 1.31, stop: 1.39 })],
        [0, att('07:56:02', 'tennis_pro', 'superficie', { superficie: 'hard', fonte: 'mappa', voce: 'Pechino', torneo: p.torneo, testo: 'cemento (mappa: Pechino)', richiesta_ignorata: null })],
        [0, att('07:56:02', 'tennis_pro', 'modalita', { modalita_bot: 'paper', modalita_esecuzione: 'PAPER', runner: 'PAPER', dry_run: false, esecuzione: 'simulata', client: 'simulato affiancato (paper_trade=True)' })],
        [0, att('07:50:04', 'tennis_scalper', 'mission', { phase: 'done' })],
        [0, att('07:49:58', 'tennis_scalper', 'mission', { phase: 'prematch', locked: 0.0752 })],
        [0, att('07:49:58', 'tennis_scalper', 'cycle', { esito: 'roundtrip', locked: 0.0752, selection_id: S1 })],
    ];
    return {
        controls: [pro, scalper],
        activity: tutte.filter(([da]) => da <= i).map(([, r]) => r),
    };
}
