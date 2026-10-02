// ============================================================================
// storicoFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA dello Storico di /mike,
// /safe-strategy e /omega.
//
// Non e' importato dall'app. Il server di anteprima sostituisce con un alias
// Vite ESATTO l'import '@/lib/dailyHistory' con questo file: si ri-esporta
// TUTTO il modulo vero (percorso RELATIVO, che l'alias non tocca) e si
// ridefiniscono solo le LETTURE di rete dello storico usate dalle tre pagine
// (`fetchMikeDaily`, `fetchMikeDayTrades`, `fetchSafeDaily`,
// `fetchSafeDayTrades`, `fetchOmegaDaily`, `fetchOmegaDayTrades`,
// `fetchOmegaDailyPerModo`, `fetchOmegaDayTradesPerModo`), con le stesse firme.
// Le righe passano dalle normalizzazioni VERE (`normalizeDailyRows`,
// `normalizeDayTrades`): stesse chiavi e tipi di quelle che arrivano dalle RPC.
//
// Dati: una storia deterministica (generatore con seme fisso) dal 1 luglio a
// oggi, una giornata per riga; la cella di una giornata e' la somma delle sue
// operazioni (il dettaglio del giorno somma lo stesso P&L della cella). Oggi
// usa i numeri della giornata dei finti (Mike +3,50 live, Safe -2,20 paper,
// Omega +2,74 paper). Soldi veri e prova non si sommano mai: ogni moneta ha la
// sua storia.
// ============================================================================
import {
    addDays, normalizeDailyRows, normalizeDayTrades,
    type DailyPerModo, type DailyRow, type DayTrade, type SafeModeFilter, type SafeSportFilter,
} from '../lib/dailyHistory';
import { OGGI } from './giornataBot';

export * from '../lib/dailyHistory';

type Bot = 'mike' | 'safe' | 'omega';
type Moneta = 'paper' | 'live';

interface Operazione { pnl: number; strategia: string; nome: string; ora: number }

const SHANGHAI = 'Shanghai Port v Shandong Taishan';

interface Profilo {
    /** primo giorno con operazioni */
    dal: string;
    vinci: [number, number];
    perdi: [number, number];
    pVinci: number;
    nMax: number;
    obiettivo: number | null;
    strategie: string[];
    /** le operazioni regolate OGGI (le stesse dei finti della giornata; null = nessuna) */
    oggi: Operazione[] | null;
}

const PROFILI: Record<string, Profilo> = {
    'mike:calcio:live': { dal: '2026-09-17', vinci: [0.1, 4.2], perdi: [-8.6, -1.2], pVinci: 0.82, nMax: 4, obiettivo: null, strategie: ['under_entry', 'under_last'], oggi: [
        { pnl: 0.08, strategia: 'under_entry', nome: SHANGHAI, ora: 5 }, { pnl: 3.42, strategia: 'under_last', nome: SHANGHAI, ora: 5 }] },
    'mike:calcio:paper': { dal: '2026-07-20', vinci: [0.1, 4.2], perdi: [-9.5, -1.5], pVinci: 0.78, nMax: 5, obiettivo: null, strategie: ['under_entry', 'under_last'], oggi: null },
    'safe:calcio:paper': { dal: '2026-07-01', vinci: [0.6, 3.8], perdi: [-6, -1.1], pVinci: 0.74, nMax: 6, obiettivo: null, strategie: ['base', 'esatto', 'punta', 'model'], oggi: [{ pnl: -2.2, strategia: 'punta', nome: 'Feyenoord v AZ Alkmaar', ora: 7 }] },
    'safe:tennis:paper': { dal: '2026-07-10', vinci: [0.2, 1.1], perdi: [-3, -0.6], pVinci: 0.77, nMax: 3, obiettivo: null, strategie: ['tennis'], oggi: null },
    'safe:calcio:live': { dal: '2026-09-24', vinci: [0.5, 1.9], perdi: [-4, -1], pVinci: 0.7, nMax: 2, obiettivo: null, strategie: ['base'], oggi: null },
    'safe:tennis:live': { dal: '2026-09-28', vinci: [0.2, 0.5], perdi: [-1.2, -0.4], pVinci: 0.7, nMax: 1, obiettivo: null, strategie: ['tennis'], oggi: null },
    'omega:calcio:paper': { dal: '2026-07-01', vinci: [0.6, 0.95], perdi: [-24, -7], pVinci: 0.93, nMax: 8, obiettivo: 250, strategie: ['ht_cs', 'ft_cs'], oggi: [
        { pnl: 0.22, strategia: 'ht_cs', nome: 'Benfica B v Porto B', ora: 5 }, { pnl: 0.62, strategia: 'ht_cs', nome: 'Feyenoord v AZ Alkmaar', ora: 6 },
        { pnl: 0.95, strategia: 'ft_cs', nome: 'Feyenoord v AZ Alkmaar', ora: 7 }, { pnl: 0.95, strategia: 'ht_cs', nome: 'Inter v Torino', ora: 7 }] },
    'omega:calcio:live': { dal: '2026-09-25', vinci: [0.9, 0.95], perdi: [-12, -6], pVinci: 0.6, nMax: 2, obiettivo: 250, strategie: ['ht_cs', 'ft_cs'], oggi: null },
};

const NOMI = [
    'Roma v Lazio', 'Milan v Juventus', 'Napoli v Fiorentina', 'Atalanta v Genoa', 'Torino v Empoli',
    'Ajax v PSV', 'Porto v Braga', 'Sevilla v Valencia', 'Lyon v Lille', 'Celtic v Rangers',
    'Brighton v Wolves', 'Freiburg v Mainz', 'Sporting CP v Benfica', 'Club Brugge v Gent',
];
const NOMI_TENNIS = ['Sinner v Rune', 'Alcaraz v Ruud', 'Zverev v Fritz', 'Swiatek v Gauff', 'Musetti v Shelton'];

/** generatore deterministico (congruenziale) col seme della riga */
function generatore(seme: string): () => number {
    let s = 0;
    for (let i = 0; i < seme.length; i++) s = (s * 31 + seme.charCodeAt(i)) & 0x7fffffff;
    s = s || 7;
    return () => {
        s = (s * 1103515245 + 12345) & 0x7fffffff;
        return s / 0x7fffffff;
    };
}

const r2 = (x: number) => Math.round(x * 100) / 100;

function operazioniDel(chiave: string, p: Profilo, giorno: string, sport: 'calcio' | 'tennis'): Operazione[] {
    if (giorno < p.dal || giorno > OGGI) return [];
    const caso = generatore(`${chiave}:${giorno}`);
    if (giorno === OGGI) {
        return (p.oggi ?? []).map((o) => ({ ...o }));
    }
    if (caso() < 0.18) return [];
    const n = 1 + Math.floor(caso() * p.nMax);
    const out: Operazione[] = [];
    for (let i = 0; i < n; i++) {
        const vince = caso() < p.pVinci;
        const [a, b] = vince ? p.vinci : p.perdi;
        const nomi = sport === 'tennis' ? NOMI_TENNIS : NOMI;
        out.push({
            pnl: r2(a + (b - a) * caso()),
            strategia: p.strategie[Math.floor(caso() * p.strategie.length)],
            nome: nomi[Math.floor(caso() * nomi.length)],
            ora: 10 + Math.floor(caso() * 11),
        });
    }
    return out;
}

function rigaGrezza(p: Profilo, giorno: string, ops: Operazione[], sport: string): Record<string, unknown> {
    const vinte = ops.filter((o) => o.pnl > 0);
    const perse = ops.filter((o) => o.pnl < 0);
    const lordoPiu = r2(vinte.reduce((s, o) => s + o.pnl, 0));
    const lordoMeno = r2(-perse.reduce((s, o) => s + o.pnl, 0));
    const tot = r2(ops.reduce((s, o) => s + o.pnl, 0));
    const perStrategia: Record<string, { n: number; pnl: number; won: number; lost: number }> = {};
    for (const o of ops) {
        const b = perStrategia[o.strategia] ??= { n: 0, pnl: 0, won: 0, lost: 0 };
        b.n += 1; b.pnl = r2(b.pnl + o.pnl);
        if (o.pnl > 0) b.won += 1; else if (o.pnl < 0) b.lost += 1;
    }
    const tutto = { n: ops.length, pnl: tot, won: vinte.length, lost: perse.length };
    return {
        day: giorno, pnl_realized: tot, trades_placed: ops.length, settled: ops.length,
        won: vinte.length, lost: perse.length, void: 0, hedged_closed: Math.floor(ops.length / 3),
        win_rate: ops.length ? vinte.length / Math.max(1, vinte.length + perse.length) : null,
        avg_win: vinte.length ? r2(lordoPiu / vinte.length) : null,
        avg_loss: perse.length ? r2(-lordoMeno / perse.length) : null,
        best_trade: ops.length ? Math.max(...ops.map((o) => o.pnl)) : null,
        worst_trade: ops.length ? Math.min(...ops.map((o) => o.pnl)) : null,
        max_liability: ops.length ? r2(Math.max(...ops.map((o) => Math.abs(o.pnl))) * 2.2) : null,
        gross_profit: lordoPiu, gross_loss: lordoMeno,
        profit_factor: lordoMeno > 0 ? r2(lordoPiu / lordoMeno) : null,
        commission_paid: r2(lordoPiu * 0.05),
        goal: p.obiettivo, goal_pct: p.obiettivo ? r2(tot / p.obiettivo * 100) : null, goal_snapshot: p.obiettivo != null,
        by_strategy: perStrategia, by_sport: { [sport]: tutto }, by_origin: { auto: tutto },
        first_trade_at: ops.length ? `${giorno}T${String(Math.min(...ops.map((o) => o.ora))).padStart(2, '0')}:05:00Z` : null,
        last_trade_at: ops.length ? `${giorno}T${String(Math.max(...ops.map((o) => o.ora))).padStart(2, '0')}:50:00Z` : null,
    };
}

function giorni(from: string, to: string): string[] {
    const out: string[] = [];
    for (let d = from, i = 0; d <= to && i < 800; d = addDays(d, 1), i++) out.push(d);
    return out;
}

function righe(bot: Bot, sport: 'calcio' | 'tennis' | null, moneta: Moneta, from: string, to: string): DailyRow[] {
    const sport_ = sport ?? 'calcio';
    const chiavi = sport == null && bot === 'safe' ? ['calcio', 'tennis'] : [sport_];
    const grezze: Record<string, unknown>[] = [];
    for (const g of giorni(from, to < OGGI ? to : OGGI)) {
        const ops: Operazione[] = [];
        let profilo: Profilo | null = null;
        for (const s of chiavi) {
            const chiave = `${bot}:${s}:${moneta}`;
            const p = PROFILI[chiave];
            if (!p) continue;
            profilo ??= p;
            ops.push(...operazioniDel(chiave, p, g, s === 'tennis' ? 'tennis' : 'calcio'));
        }
        if (profilo && ops.length) grezze.push(rigaGrezza(profilo, g, ops, sport_));
    }
    return normalizeDailyRows(grezze);
}

function operazioniGiorno(bot: Bot, sport: 'calcio' | 'tennis' | null, moneta: Moneta, giorno: string): DayTrade[] {
    const chiavi = sport == null && bot === 'safe' ? ['calcio', 'tennis'] : [sport ?? 'calcio'];
    const grezze: Record<string, unknown>[] = [];
    let id = 50_000;
    for (const s of chiavi) {
        const chiave = `${bot}:${s}:${moneta}`;
        const p = PROFILI[chiave];
        if (!p) continue;
        for (const o of operazioniDel(chiave, p, giorno, s === 'tennis' ? 'tennis' : 'calcio')) {
            id += 1;
            const ora = `${giorno}T${String(o.ora).padStart(2, '0')}:10:00Z`;
            const fine = `${giorno}T${String(Math.min(23, o.ora + 2)).padStart(2, '0')}:00:00Z`;
            const lay = bot === 'omega' || o.strategia === 'base' || o.strategia === 'esatto';
            const prezzo = bot === 'omega' ? 18 : bot === 'mike' ? 1.36 : lay ? 4.2 : 1.3;
            const stake = bot === 'omega' ? 1 : bot === 'mike' ? 10 : 2;
            grezze.push({
                id, event_id: `3480${id}`, event_name: o.nome, side: lay ? 'lay' : 'back', mode: moneta,
                price: prezzo, size: stake, liability: lay ? r2((prezzo - 1) * stake) : stake,
                status: o.pnl >= 0 ? 'won' : 'lost', pnl: o.pnl, placed_at: ora, settled_at: fine,
                bet_id: `${moneta}-${id}`, origin: 'auto', closes_trade_id: null, meta: {},
                phase: bot === 'omega' ? o.strategia : null, runner_name: bot === 'omega' ? '2 - 1' : null,
                sport: bot === 'safe' ? s : null, strategy: bot === 'safe' ? o.strategia : null,
                market_type: bot === 'omega' ? 'CORRECT_SCORE' : bot === 'mike' ? 'OVER_UNDER_35' : 'MATCH_ODDS',
                selection_name: bot === 'mike' ? 'Under 3.5 Goals' : bot === 'safe' ? 'The Draw' : null,
                closes: [], total_pnl: o.pnl, placed_in_day: true, settled_in_day: true,
                in_day: true, giorno_partita: giorno, giorno_da: 'partita',
            });
        }
    }
    return normalizeDayTrades(grezze);
}

const monetaDi = (m: SafeModeFilter, dflt: Moneta): Moneta => m ?? dflt;

// ------------------------------------------------------------------ Mike (live)

export async function fetchMikeDaily(from: string, to: string, mode: SafeModeFilter = null): Promise<DailyRow[]> {
    return righe('mike', 'calcio', monetaDi(mode, 'live'), from, to);
}

export async function fetchMikeDayTrades(day: string, mode: SafeModeFilter = null): Promise<DayTrade[]> {
    return operazioniGiorno('mike', 'calcio', monetaDi(mode, 'live'), day);
}

// ------------------------------------------------------------------ Safe (paper)

export async function fetchSafeDaily(
    from: string, to: string, sport: SafeSportFilter = null, mode: SafeModeFilter = null,
): Promise<DailyRow[]> {
    return righe('safe', sport, monetaDi(mode, 'paper'), from, to);
}

export async function fetchSafeDayTrades(
    day: string, sport: SafeSportFilter = null, mode: SafeModeFilter = null,
): Promise<DayTrade[]> {
    return operazioniGiorno('safe', sport, monetaDi(mode, 'paper'), day);
}

// ------------------------------------------------------------------ Omega (paper)

export async function fetchOmegaDaily(from: string, to: string): Promise<DailyRow[]> {
    return righe('omega', 'calcio', 'paper', from, to);
}

export async function fetchOmegaDayTrades(day: string): Promise<DayTrade[]> {
    return operazioniGiorno('omega', 'calcio', 'paper', day);
}

export async function fetchOmegaDailyPerModo(from: string, to: string, mode: 'paper' | 'live'): Promise<DailyPerModo> {
    return { rows: righe('omega', 'calcio', mode, from, to), modoAttendibile: true };
}

export async function fetchOmegaDayTradesPerModo(
    day: string, mode: 'paper' | 'live',
): Promise<{ trades: DayTrade[]; modoAttendibile: boolean }> {
    return { trades: operazioniGiorno('omega', 'calcio', mode, day), modoAttendibile: true };
}
