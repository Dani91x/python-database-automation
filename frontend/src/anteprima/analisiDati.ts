// ============================================================================
// analisiDati.ts - SOLO PER L'ANTEPRIMA POPOLATA di /live-pnl, /trade-journal,
// /match-replay (e del tab «Backtest automatico» di /analytics).
//
// Non e' importato dall'app e NON ha un alias suo: i moduli che queste pagine
// leggono ('@/lib/liveOrders', '@/lib/live') hanno gia' un finto
// (liveOrdersFinto.ts, liveFeedFinto.ts, alias in alias_controlroom.mjs e
// alias_seguilive.mjs). Qui ci sono le letture MANCANTI, con la STESSA firma e
// gli STESSI tipi del vero, pronte da ri-esportare da quei finti:
//   liveOrdersFinto.ts:
//     export { fetchLiveSettled, fetchLiveJournal, fetchLivePositionsAll } from './analisiDati';
//   liveFeedFinto.ts:
//     export { fetchReplayList, fetchReplayChunked } from './analisiDati';
// (in ESM un export esplicito vince su `export *`: nessun altro cambio serve).
//
// Dati coerenti con i finti comuni (seguiLiveDati.ts, liveOrdersFinto.ts):
//  - settled LIVE di oggi = +3,20 -1,40 +6,32 = +8,12 EUR = `realized` del
//    rischio di giornata (liveOrdersFinto.ts, RISCHIO.realized 8.12), come il
//    prototipo (prototipo/js/s_live.js, live-pnl);
//  - journal: gli ordini PAPER di Inter-Torino di seguiLiveDati.ts (stessi
//    prezzi, size e request_id) + le operazioni del mattino sui mercati regolati;
//  - posizioni: le stesse di fetchLivePositionsEvent (seguiLiveDati.POSIZIONI);
//  - replay: elenco del prototipo (prototipo/js/s_analisi.js, match replay) e
//    frame GENERATI da un modello di Poisson sul punteggio (deterministici).
// Orologio dell'anteprima: 2026-10-01T08:38:00Z (10:38 a Roma).
// ============================================================================
import type { LiveJournalRow, LivePositionRow, LiveSettledRow } from '../lib/liveOrders';
import type {
    Frame, Ladder, Market, ReplayData, ReplayItem, ReplayProgress, ScoreEvent,
} from '../lib/live';
import { convertiFramesEur } from '../lib/live';
import { EV, MK, POSIZIONI, SEL } from './seguiLiveDati';

const ORA_MS = Date.parse('2026-10-01T08:38:00Z');
/** istante ISO a un'ora UTC di oggi, 'HH:MM:SS' */
const alle = (hms: string) => `2026-10-01T${hms}Z`;
const r2 = (v: number) => Math.round(v * 100) / 100;

// ------------------------------------------------------------------ mercati regolati di oggi

/** partite del mattino (Asia/Oceania), gia' finite alle 10:38 di Roma */
const EV_MATTINO = { ulsan: '34811422', shanghai: '34811501', melbourne: '34811650' } as const;
const MK_MATTINO = {
    ulsanOu35: '1.248114223', shanghaiMo: '1.248115010', shanghaiOu25: '1.248115011',
    melbourneMo: '1.248116500', melbourneOu25: '1.248116501',
} as const;

type S = [number, LiveSettledRow['mode'], string, string, string, number, number, LiveSettledRow['source'], string];
// [id, modo, evento, mercato, nome mercato, profitto, ordini, fonte, regolato alle (UTC)]
const SETTLED: S[] = [
    [701, 'live', EV_MATTINO.ulsan, MK_MATTINO.ulsanOu35, 'Over/Under 3.5 Goals', 3.2, 2, 'cleared', '06:15:04'],
    [702, 'live', EV_MATTINO.shanghai, MK_MATTINO.shanghaiOu25, 'Over/Under 2.5 Goals', -1.4, 2, 'cleared', '07:02:31'],
    [703, 'paper', EV_MATTINO.shanghai, MK_MATTINO.shanghaiMo, 'Match Odds', 2.1, 1, 'simulated', '07:02:33'],
    [704, 'live', EV_MATTINO.melbourne, MK_MATTINO.melbourneMo, 'Match Odds', 6.32, 2, 'cleared', '07:58:12'],
    [705, 'paper', EV_MATTINO.melbourne, MK_MATTINO.melbourneOu25, 'Over/Under 2.5 Goals', 1.85, 1, 'simulated', '07:58:15'],
];

export async function fetchLiveSettled(fromIso?: string, toIso?: string): Promise<LiveSettledRow[]> {
    const da = fromIso ? Date.parse(fromIso) : -Infinity;
    const a = toIso ? Date.parse(toIso) : Infinity;
    return SETTLED
        .map(([id, mode, event_id, market_id, market_name, profit, orders, source, ora]): LiveSettledRow => ({
            id, mode, event_id, market_id, market_name, profit, orders, source,
            settled_at: alle(ora), updated_at: alle(ora),
        }))
        .filter((r) => Date.parse(r.settled_at) >= da && Date.parse(r.settled_at) < a);
}

// ------------------------------------------------------------------ posizioni aperte (tutte)

export async function fetchLivePositionsAll(): Promise<LivePositionRow[]> {
    return Object.values(POSIZIONI).flat().map((r) => ({ ...r }));
}

// ------------------------------------------------------------------ journal di oggi

interface J {
    id: number; ora: string; mode: LiveJournalRow['mode']; req: number | null; action: string;
    origin: LiveJournalRow['origin']; ev: string; mk: string; nome: string; sel: number;
    side: LiveJournalRow['side']; price: number; size: number; pers: string | null; bet: string | null;
    min: number | null; sh: number | null; sa: number | null; ltp: number; bb: number; bl: number;
    sig: Record<string, unknown> | null; tag: string | null; note: string | null;
}

const JOURNAL: J[] = [
    {
        id: 5210, ora: '04:21:10', mode: 'live', req: 54210, action: 'place', origin: 'manual',
        ev: EV_MATTINO.ulsan, mk: MK_MATTINO.ulsanOu35, nome: 'Over/Under 3.5 Goals', sel: SEL.under35,
        side: 'back', price: 1.38, size: 8, pers: 'LAPSE', bet: '371230117702', min: 21, sh: 0, sa: 0,
        ltp: 1.38, bb: 1.38, bl: 1.39, sig: { direction: 'under', edge: 0.024 }, tag: 'under', note: 'ritmo basso',
    },
    {
        id: 5244, ora: '05:47:02', mode: 'live', req: 54388, action: 'greenup', origin: 'manual',
        ev: EV_MATTINO.ulsan, mk: MK_MATTINO.ulsanOu35, nome: 'Over/Under 3.5 Goals', sel: SEL.under35,
        side: 'lay', price: 1.1, size: 10.04, pers: 'LAPSE', bet: '371231904410', min: 78, sh: 1, sa: 1,
        ltp: 1.1, bb: 1.09, bl: 1.1, sig: null, tag: 'green', note: null,
    },
    {
        id: 5251, ora: '05:16:40', mode: 'live', req: 54301, action: 'place', origin: 'manual',
        ev: EV_MATTINO.shanghai, mk: MK_MATTINO.shanghaiOu25, nome: 'Over/Under 2.5 Goals', sel: SEL.over25,
        side: 'back', price: 2.1, size: 10, pers: 'LAPSE', bet: '371231220931', min: 6, sh: 0, sa: 0,
        ltp: 2.1, bb: 2.1, bl: 2.12, sig: { direction: 'over', edge: 0.031 }, tag: 'scalp', note: 'entrata pulita',
    },
    {
        id: 5268, ora: '05:34:00', mode: 'paper', req: 54333, action: 'place', origin: 'risk_rule',
        ev: EV_MATTINO.shanghai, mk: MK_MATTINO.shanghaiMo, nome: 'Match Odds', sel: 1022,
        side: 'lay', price: 3.3, size: 6, pers: 'PERSIST', bet: null, min: 24, sh: 0, sa: 0,
        ltp: 3.3, bb: 3.25, bl: 3.3, sig: { direction: 'home', edge: -0.012 }, tag: null, note: null,
    },
    {
        id: 5290, ora: '06:31:12', mode: 'live', req: 54452, action: 'stop_loss', origin: 'risk_rule',
        ev: EV_MATTINO.shanghai, mk: MK_MATTINO.shanghaiOu25, nome: 'Over/Under 2.5 Goals', sel: SEL.over25,
        side: 'lay', price: 2.86, size: 7.34, pers: 'LAPSE', bet: '371232870155', min: 71, sh: 1, sa: 0,
        ltp: 2.86, bb: 2.84, bl: 2.86, sig: null, tag: 'stop', note: null,
    },
    {
        id: 5302, ora: '06:12:30', mode: 'live', req: 54420, action: 'place', origin: 'manual',
        ev: EV_MATTINO.melbourne, mk: MK_MATTINO.melbourneMo, nome: 'Match Odds', sel: 5180,
        side: 'back', price: 1.92, size: 12, pers: 'LAPSE', bet: '371232554018', min: 12, sh: 0, sa: 0,
        ltp: 1.92, bb: 1.92, bl: 1.93, sig: { direction: 'home', edge: 0.041 }, tag: null, note: null,
    },
    {
        id: 5317, ora: '07:05:44', mode: 'paper', req: 54470, action: 'place', origin: 'manual',
        ev: EV_MATTINO.melbourne, mk: MK_MATTINO.melbourneOu25, nome: 'Over/Under 2.5 Goals', sel: SEL.under25,
        side: 'back', price: 1.74, size: 5, pers: 'LAPSE', bet: null, min: 44, sh: 1, sa: 0,
        ltp: 1.74, bb: 1.74, bl: 1.75, sig: { direction: 'under', edge: 0.018 }, tag: null, note: null,
    },
    {
        id: 5329, ora: '07:20:05', mode: 'live', req: 54497, action: 'greenup', origin: 'risk_rule',
        ev: EV_MATTINO.melbourne, mk: MK_MATTINO.melbourneMo, nome: 'Match Odds', sel: 5180,
        side: 'lay', price: 1.36, size: 16.94, pers: 'LAPSE', bet: '371233309771', min: 66, sh: 1, sa: 0,
        ltp: 1.36, bb: 1.35, bl: 1.36, sig: null, tag: 'green', note: 'regola tp 2 tick',
    },
    {
        id: 5341, ora: '07:41:10', mode: 'paper', req: 55063, action: 'place', origin: 'manual',
        ev: EV.inter, mk: MK.interOu25, nome: 'Over/Under 2.5 Goals', sel: SEL.under25,
        side: 'back', price: 1.55, size: 4, pers: 'LAPSE', bet: '371245871540', min: 16, sh: 0, sa: 0,
        ltp: 1.55, bb: 1.55, bl: 1.56, sig: { direction: 'under', edge: 0.022 }, tag: null, note: null,
    },
    {
        id: 5352, ora: '07:58:02', mode: 'paper', req: 55107, action: 'place', origin: 'manual',
        ev: EV.inter, mk: MK.interMo, nome: 'Match Odds', sel: SEL.inter,
        side: 'back', price: 1.52, size: 5, pers: 'LAPSE', bet: '371245980112', min: 33, sh: 0, sa: 0,
        ltp: 1.52, bb: 1.52, bl: 1.53, sig: { direction: 'home', edge: 0.035 }, tag: 'scalp', note: null,
    },
    {
        id: 5360, ora: '08:14:02', mode: 'paper', req: 55160, action: 'place', origin: 'risk_rule',
        ev: EV.betis, mk: MK.betisMo, nome: 'Match Odds', sel: SEL.betis,
        side: 'lay', price: 2.04, size: 12, pers: 'LAPSE', bet: null, min: 7, sh: 0, sa: 0,
        ltp: 2.04, bb: 2.02, bl: 2.04, sig: { direction: 'home', edge: -0.012 }, tag: null, note: null,
    },
    {
        id: 5371, ora: '08:36:25', mode: 'paper', req: 55218, action: 'place', origin: 'manual',
        ev: EV.inter, mk: MK.interMo, nome: 'Match Odds', sel: SEL.inter,
        side: 'lay', price: 1.35, size: 5.63, pers: 'PERSIST', bet: '371246112874', min: 57, sh: 1, sa: 0,
        ltp: 1.38, bb: 1.38, bl: 1.39, sig: null, tag: 'uscita', note: 'uscita sul book a 1,35',
    },
    {
        id: 5376, ora: '08:37:12', mode: 'paper', req: 55231, action: 'cancel', origin: 'manual',
        ev: EV.betis, mk: MK.betisOu25, nome: 'Over/Under 2.5 Goals', sel: SEL.over25,
        side: 'back', price: 2.16, size: 6, pers: 'LAPSE', bet: null, min: 30, sh: 0, sa: 0,
        ltp: 2.14, bb: 2.14, bl: 2.16, sig: null, tag: null, note: null,
    },
];

function book(bb: number, bl: number): { back: [number, number][]; lay: [number, number][] } {
    return {
        back: [[bb, 412.5], [r2(bb - 0.01), 288.1], [r2(bb - 0.02), 655.4]],
        lay: [[bl, 380.2], [r2(bl + 0.01), 512.9], [r2(bl + 0.02), 240.7]],
    };
}

export async function fetchLiveJournal(args?: {
    limit?: number;
    marketId?: string;
    fromIso?: string;
    toIso?: string;
}): Promise<LiveJournalRow[]> {
    const da = args?.fromIso ? Date.parse(args.fromIso) : -Infinity;
    const a = args?.toIso ? Date.parse(args.toIso) : Infinity;
    return JOURNAL
        .map((j): LiveJournalRow => ({
            id: j.id, ts: alle(j.ora), mode: j.mode, request_id: j.req, action: j.action, origin: j.origin,
            event_id: j.ev, market_id: j.mk, market_name: j.nome, selection_id: j.sel, side: j.side,
            price: j.price, size: j.size, persistence: j.pers, bet_id: j.bet, minute: j.min,
            score_home: j.sh, score_away: j.sa, inplay: j.min != null, ltp: j.ltp, best_back: j.bb,
            best_lay: j.bl, book: book(j.bb, j.bl), signals: j.sig,
            params: j.origin === 'risk_rule' ? { regola: j.action, tick: 2 } : null,
            tag: j.tag, note: j.note,
        }))
        .filter((r) => !args?.marketId || r.market_id === args.marketId)
        .filter((r) => Date.parse(r.ts) >= da && Date.parse(r.ts) < a && Date.parse(r.ts) <= ORA_MS)
        .sort((x, y) => y.ts.localeCompare(x.ts))
        .slice(0, args?.limit ?? 200);
}

// ------------------------------------------------------------------ replay registrati

interface Registrazione {
    item: ReplayItem;
    /** gol: [minuto, 'h' | 'a'] */
    gol: [number, 'h' | 'a'][];
    /** forze (gol attesi in 90') casa / ospite */
    lh: number;
    la: number;
}

function reg(event_id: string, lega: string, leagueId: number, casa: string, ospite: string, ko: string,
    n_markets: number, n_snapshots: number, gol: [number, 'h' | 'a'][], lh: number, la: number): Registrazione {
    const koMs = Date.parse(ko);
    return {
        item: {
            event_id, fixture_id: Number(event_id.slice(-7)), league_id: leagueId, league_name: lega,
            home_name: casa, away_name: ospite, open_date: ko, status: 'CLOSED', n_markets, n_snapshots,
            started_at: new Date(koMs - 10 * 60_000).toISOString(),
            ended_at: new Date(koMs + 112 * 60_000).toISOString(),
        },
        gol, lh, la,
    };
}

const REGISTRAZIONI: Registrazione[] = [
    reg('34790012', 'Serie A', 135, 'Inter', 'Torino', '2026-09-21T18:45:00Z', 24, 18402, [[34, 'h'], [71, 'h']], 1.75, 0.85),
    reg('34775530', 'Serie A', 135, 'Napoli', 'Lazio', '2026-09-14T16:00:00Z', 22, 16120, [[52, 'h']], 1.5, 1.05),
    reg('34779012', 'Serie A', 135, 'Atalanta', 'Genoa', '2026-09-13T16:00:00Z', 21, 15288, [[8, 'h'], [40, 'a'], [63, 'h'], [88, 'h']], 1.8, 0.9),
    reg('34771904', 'Premier League', 39, 'Brentford', 'Fulham', '2026-09-13T14:00:00Z', 26, 20330, [[55, 'h']], 1.4, 1.2),
    reg('34768820', 'La Liga', 140, 'Real Betis', 'Getafe', '2026-09-07T16:15:00Z', 18, 13904, [[23, 'h'], [67, 'a']], 1.45, 0.9),
];

export async function fetchReplayList(limit = 50): Promise<ReplayItem[]> {
    return REGISTRAZIONI.slice(0, limit).map((r) => ({ ...r.item }));
}

// --- modello delle quote (Poisson sui gol che restano) ---

function poisson(l: number, k: number): number {
    let f = 1;
    for (let i = 2; i <= k; i++) f *= i;
    return (Math.exp(-l) * l ** k) / f;
}

/** probabilita' finali [casa, pari, ospite] dato il punteggio e i gol attesi residui */
function esito(sh: number, sa: number, lh: number, la: number): [number, number, number] {
    let h = 0; let d = 0; let a = 0;
    for (let i = 0; i <= 8; i++) {
        for (let j = 0; j <= 8; j++) {
            const p = poisson(lh, i) * poisson(la, j);
            const x = sh + i; const y = sa + j;
            if (x > y) h += p; else if (x === y) d += p; else a += p;
        }
    }
    return [h, d, a];
}

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
/** quota -> tick Betfair piu' vicino (verso il basso), con limiti 1,01..1000 */
function tick(q: number): number {
    const c = Math.min(1000, Math.max(1.01, q));
    const s = passo(c);
    return r2(Math.floor(c / s + 1e-9) * s);
}
const su = (p: number) => r2(p + passo(p));
const giu = (p: number) => r2(Math.max(1.01, p - passo(p - 1e-9)));

/** pseudo-casuale deterministico in [0,1) */
function rnd(k: number): number {
    const x = Math.sin(k * 999 + 7) * 10000;
    return x - Math.floor(x);
}

function livelli(back: number, n: number, seme: number, dir: 1 | -1): [number, number][] {
    const out: [number, number][] = [];
    let p = back;
    for (let i = 0; i < n; i++) {
        // size in GBP (registrazione storica): le converte convertiFramesEur, come il vero
        out.push([p, r2(60 + rnd(seme + i) * 900)]);
        p = dir === 1 ? su(p) : giu(p);
    }
    return out;
}

function voceLadder(prob: number, tv: number, seme: number): Ladder[string] {
    // prezzo da una probabilita' limitata a [0,75 %, 99,5 %]: a fine partita la
    // favorita resta a 1,01/1,02 e le altre a ~130/140, senza arbitraggi finti
    // (somma degli 1/back >= 1 >= somma degli 1/lay, come un book vero)
    const fair = 1 / Math.min(0.995, Math.max(0.0075, prob));
    // il book Betfair finisce a 1000: la lay non puo' superarlo
    const back = Math.min(990, tick(fair * 0.995));
    const lay = Math.min(1000, su(back));
    return { back: livelli(back, 3, seme, -1), lay: livelli(lay, 3, seme + 50, 1), ltp: back, tv: r2(tv) };
}

/** minuto di gioco a `t` minuti reali dal fischio d'inizio (intervallo di 15') */
function minutoDi(t: number): number | null {
    if (t < 0) return null;
    if (t < 45) return Math.floor(t) + 1;
    if (t < 60) return 45;
    return Math.min(95, Math.floor(t - 15) + 1);
}

function generaReplay(r: Registrazione): ReplayData {
    const { item, gol, lh, la } = r;
    const id = item.event_id;
    const mo = `1.${id.slice(2)}0`;
    const ou = `1.${id.slice(2)}1`;
    const S = { h: 101, d: 58805, a: 102, under: SEL.under25, over: SEL.over25 };
    const markets: Market[] = [
        {
            market_id: mo, market_type: 'MATCH_ODDS', market_name: 'Match Odds', sort_priority: 1,
            selections: [
                { selection_id: S.h, name: item.home_name, sort_priority: 1 },
                { selection_id: S.a, name: item.away_name, sort_priority: 2 },
                { selection_id: S.d, name: 'The Draw', sort_priority: 3 },
            ],
        },
        {
            market_id: ou, market_type: 'OVER_UNDER_25', market_name: 'Over/Under 2.5 Goals', sort_priority: 2,
            selections: [
                { selection_id: S.under, name: 'Under 2.5 Goals', sort_priority: 1 },
                { selection_id: S.over, name: 'Over 2.5 Goals', sort_priority: 2 },
            ],
        },
    ];
    const koMs = Date.parse(item.open_date);
    const frames: Frame[] = [];
    const score: ScoreEvent[] = [{
        ts: item.open_date, minute: 0, score_home: 0, score_away: 0, event_type: 'KickOff', source: 'betfair',
    }];
    // pre-match ogni 60 s (10'), poi in-play ogni 30 s fino al 95'
    const istanti: number[] = [];
    for (let t = -10; t < 0; t += 1) istanti.push(t);
    for (let t = 0; t <= 110; t += 0.5) istanti.push(t);
    let tvBase = 180000;
    istanti.forEach((t, k) => {
        const minuto = minutoDi(t);
        const giocati = minuto ?? 0;
        const sh = gol.filter(([m, s]) => s === 'h' && m <= giocati).length;
        const sa = gol.filter(([m, s]) => s === 'a' && m <= giocati).length;
        const resto = Math.max(0.01, (90 - Math.min(90, giocati)) / 90);
        const [ph, pd, pa] = esito(sh, sa, lh * resto, la * resto);
        const restanti = 2 - (sh + sa); // gol che mancano per l'Under 2.5
        let pUnder = 0;
        if (restanti >= 0) for (let i = 0; i <= restanti; i++) pUnder += poisson((lh + la) * resto, i);
        pUnder = Math.min(0.995, Math.max(0.005, pUnder));
        tvBase += 900 + rnd(k) * 1400;
        const ts = new Date(koMs + t * 60_000).toISOString();
        const inplay = t >= 0;
        frames.push({
            market_id: mo, ts, minute: minuto, inplay, status: 'OPEN',
            ladder: {
                [String(S.h)]: voceLadder(ph, tvBase * 0.55, k * 7 + 1),
                [String(S.a)]: voceLadder(pa, tvBase * 0.18, k * 7 + 2),
                [String(S.d)]: voceLadder(pd, tvBase * 0.27, k * 7 + 3),
            },
        });
        frames.push({
            market_id: ou, ts, minute: minuto, inplay, status: 'OPEN',
            ladder: {
                [String(S.under)]: voceLadder(pUnder, tvBase * 0.21, k * 7 + 4),
                [String(S.over)]: voceLadder(1 - pUnder, tvBase * 0.19, k * 7 + 5),
            },
        });
    });
    // il feed punteggio emette un aggiornamento al minuto (come get_scores) e un
    // evento 'Goal' a ogni rete: la pagina legge il minuto da qui
    for (let t = 0.2; t <= 110; t += 1) {
        const m = minutoDi(t);
        if (m == null || (t >= 45 && t < 60)) continue;
        const sh = gol.filter(([g, s]) => s === 'h' && g < m).length;
        const sa = gol.filter(([g, s]) => s === 'a' && g < m).length;
        score.push({
            ts: new Date(koMs + t * 60_000).toISOString(), minute: m, score_home: sh, score_away: sa,
            event_type: null, source: 'betfair',
        });
    }
    let h = 0; let a = 0;
    for (const [m, s] of gol) {
        if (s === 'h') h += 1; else a += 1;
        const t = m <= 45 ? m - 0.5 : m + 14.5;
        score.push({
            ts: new Date(koMs + t * 60_000).toISOString(), minute: m, score_home: h, score_away: a,
            event_type: 'Goal', source: 'betfair',
        });
    }
    score.sort((x, y) => x.ts.localeCompare(y.ts));
    return {
        event: {
            event_id: id, fixture_id: item.fixture_id, league_name: item.league_name,
            home_name: item.home_name, away_name: item.away_name, open_date: item.open_date, status: item.status,
        },
        markets,
        // la registrazione e' storica (GBP): stessa conversione alla fonte del vero
        frames: convertiFramesEur(frames),
        score_timeline: score,
    };
}

export async function fetchReplayChunked(
    eventId: string,
    onProgress?: (p: ReplayProgress) => void,
): Promise<ReplayData> {
    const r = REGISTRAZIONI.find((x) => x.item.event_id === eventId);
    if (!r) throw new Error(`replay ${eventId} non registrato`);
    const data = generaReplay(r);
    onProgress?.({ done: 1, total: 1, frames: data.frames.length });
    return data;
}
