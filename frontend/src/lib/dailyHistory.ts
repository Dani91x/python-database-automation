// ============================================================================
// dailyHistory.ts — STORICO PER GIORNATA OPERATIVA (Omega + Safe Strategy).
//
// Client delle RPC owner-only di migrations/daily_history.sql:
//   get_omega_daily / get_safe_daily            → una riga per giornata con attività
//   get_omega_day_trades / get_safe_day_trades  → i trade di un giorno (aperture
//                                                 con le gambe di chiusura annidate)
// più le ANALITICHE PURE sulle righe giornaliere (equity per giorno, drawdown,
// serie positive/negative, riepilogo mese, profit factor, expectancy, tasso di
// centratura dell'obiettivo, griglia del calendario).
//
// La giornata operativa è la data in Europe/Rome (stessa regola del DB): ogni
// `day` è una stringa 'YYYY-MM-DD' e TUTTA l'aritmetica sui giorni qui è fatta
// su quelle stringhe (Date.UTC), mai sul fuso del browser.
//
// Regola del repo: logica money-critical = funzioni pure + test co-locati
// (dailyHistory.test.ts). Niente I/O fuori dai quattro fetcher.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import type { EquityPoint } from '@/components/trading/EquityCurve';

// ------------------------------------------------------------------- tipi
export interface DailyBreakdown {
    /** aperture PIAZZATE nel giorno con questa chiave */
    n: number;
    /** P&L totale (apertura + chiusure) delle aperture REGOLATE nel giorno */
    pnl: number;
    won: number;
    lost: number;
}

export interface DailyRow {
    /** giornata operativa 'YYYY-MM-DD' (Europe/Rome) */
    day: string;
    /** somma pnl delle righe regolate nel giorno, gambe di chiusura incluse */
    pnl_realized: number;
    /** aperture piazzate nel giorno (chiusure escluse, errori esclusi) */
    trades_placed: number;
    /** aperture regolate nel giorno */
    settled: number;
    won: number;
    lost: number;
    void: number;
    /** aperture del giorno chiuse a mercato (cash out / uscita automatica) */
    hedged_closed: number;
    /** won/(won+lost) in [0,1]; null senza esiti */
    win_rate: number | null;
    avg_win: number | null;
    avg_loss: number | null;
    best_trade: number | null;
    worst_trade: number | null;
    max_liability: number | null;
    /** somma dei P&L totali positivi (≥ 0) */
    gross_profit: number;
    /** somma dei P&L totali negativi in VALORE ASSOLUTO (≥ 0) */
    gross_loss: number;
    /** gross_profit / gross_loss; null se gross_loss = 0 */
    profit_factor: number | null;
    /** commissione scritta dal servizio o STIMATA (null = nulla di regolato) */
    commission_paid: number | null;
    /** obiettivo giornaliero (Omega); null per Safe */
    goal: number | null;
    goal_pct: number | null;
    /**
     * H-10 — true SOLO se `goal` è lo SNAPSHOT storicizzato di quel giorno.
     * false = obiettivo di RIPIEGO (quello corrente del control): giudicare
     * "centrato/mancato" su un obiettivo mai storicizzato è una bugia, perciò
     * il calendario non mostra ●/○ e lo dichiara.
     */
    goal_snapshot: boolean;
    /** Safe: per strategia (base/esatto/punta/tennis/model/manual) · Omega: per fase (ht_cs/ft_cs/scalp/none) */
    by_strategy: Record<string, DailyBreakdown>;
    by_sport: Record<string, DailyBreakdown>;
    by_origin: Record<string, DailyBreakdown>;
    first_trade_at: string | null;
    last_trade_at: string | null;
}

/** Una gamba (apertura o chiusura) come arriva dal DB: campi comuni alle due
 *  tabelle più quelli specifici opzionali. */
export interface DayTradeLeg {
    id: number;
    event_id: string;
    event_name: string | null;
    side: string;
    mode: 'paper' | 'live';
    price: number | null;
    size: number | null;
    liability: number | null;
    status: string;
    pnl: number;
    placed_at: string;
    settled_at: string | null;
    /** id dell'ordine su Betfair: null = mai arrivato a mercato */
    bet_id?: string | null;
    origin?: 'auto' | 'manual' | null;
    closes_trade_id?: number | null;
    meta: Record<string, unknown> | null;
    // Omega
    runner_name?: string | null;
    phase?: string | null;
    target?: number | null;
    // Safe
    sport?: string | null;
    strategy?: string | null;
    market_type?: string | null;
    selection_name?: string | null;
    minute_at_entry?: number | null;
    score_at_entry?: string | null;
}

export interface DayTrade extends DayTradeLeg {
    closes: DayTradeLeg[];
    /** pnl apertura + pnl delle chiusure regolate */
    total_pnl: number;
    placed_in_day: boolean;
    settled_in_day: boolean;
}
export type DayTrades = DayTrade[];

export type HistoryVariant = 'omega' | 'safe' | 'mike';
export type SafeSportFilter = 'calcio' | 'tennis' | null;

// -------------------------------------------------------- normalizzazione
function num(v: unknown, fallback = 0): number {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
}
function numOrNull(v: unknown): number | null {
    if (v == null || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}
function breakdown(v: unknown): Record<string, DailyBreakdown> {
    const out: Record<string, DailyBreakdown> = {};
    if (!v || typeof v !== 'object') return out;
    for (const [k, raw] of Object.entries(v as Record<string, unknown>)) {
        const r = (raw ?? {}) as Record<string, unknown>;
        out[k] = { n: num(r.n), pnl: num(r.pnl), won: num(r.won), lost: num(r.lost) };
    }
    return out;
}

/** Riga giornaliera DIFENSIVA: numeri sempre numeri, breakdown sempre oggetti.
 *  Una riga senza `day` valido viene scartata (ritorna null). */
export function normalizeDailyRow(raw: unknown): DailyRow | null {
    const r = (raw ?? {}) as Record<string, unknown>;
    const day = typeof r.day === 'string' ? r.day.slice(0, 10) : '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
    return {
        day,
        pnl_realized: num(r.pnl_realized),
        trades_placed: num(r.trades_placed),
        settled: num(r.settled),
        won: num(r.won),
        lost: num(r.lost),
        void: num(r.void),
        hedged_closed: num(r.hedged_closed),
        win_rate: numOrNull(r.win_rate),
        avg_win: numOrNull(r.avg_win),
        avg_loss: numOrNull(r.avg_loss),
        best_trade: numOrNull(r.best_trade),
        worst_trade: numOrNull(r.worst_trade),
        max_liability: numOrNull(r.max_liability),
        gross_profit: num(r.gross_profit),
        gross_loss: Math.abs(num(r.gross_loss)),
        profit_factor: numOrNull(r.profit_factor),
        commission_paid: numOrNull(r.commission_paid),
        goal: numOrNull(r.goal),
        goal_pct: numOrNull(r.goal_pct),
        // H-10: l'RPC senza la migrazione non manda il flag → NON storicizzato
        goal_snapshot: r.goal_snapshot === true,
        by_strategy: breakdown(r.by_strategy),
        by_sport: breakdown(r.by_sport),
        by_origin: breakdown(r.by_origin),
        first_trade_at: typeof r.first_trade_at === 'string' ? r.first_trade_at : null,
        last_trade_at: typeof r.last_trade_at === 'string' ? r.last_trade_at : null,
    };
}

export function normalizeDailyRows(raw: unknown): DailyRow[] {
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeDailyRow).filter((r): r is DailyRow => r != null)
        .sort((a, b) => a.day.localeCompare(b.day));
}

function normalizeLeg(raw: unknown): DayTradeLeg {
    const r = (raw ?? {}) as Record<string, unknown>;
    return {
        ...(r as unknown as DayTradeLeg),
        id: num(r.id),
        pnl: num(r.pnl),
        price: numOrNull(r.price),
        size: numOrNull(r.size),
        liability: numOrNull(r.liability),
        meta: (r.meta && typeof r.meta === 'object') ? r.meta as Record<string, unknown> : null,
    };
}

export function normalizeDayTrades(raw: unknown): DayTrade[] {
    if (!Array.isArray(raw)) return [];
    return raw.map((x) => {
        const r = (x ?? {}) as Record<string, unknown>;
        const closes = Array.isArray(r.closes) ? r.closes.map(normalizeLeg) : [];
        return {
            ...normalizeLeg(r),
            closes,
            total_pnl: num(r.total_pnl, num(r.pnl)),
            placed_in_day: Boolean(r.placed_in_day),
            settled_in_day: Boolean(r.settled_in_day),
        };
    });
}

// ----------------------------------------------------------------- fetch
export async function fetchOmegaDaily(from: string, to: string): Promise<DailyRow[]> {
    const { data, error } = await supabase.rpc('get_omega_daily', { p_from: from, p_to: to });
    if (error) throw new Error(error.message);
    return normalizeDailyRows(data);
}

/** Modalità con cui filtrare la giornata. `null` = TUTTE, cioè paper e live
 *  **sommati**: quasi mai quello che si vuole mostrare a un trader. */
export type SafeModeFilter = 'paper' | 'live' | null;

/**
 * La giornata di Safe dal server.
 *
 * ⚠️ `mode` non è un dettaglio. La RPC accetta `p_mode` dal 13/09 e il
 * frontend non glielo passava: il risultato sommava soldi veri e simulati in
 * un numero solo. Il 14/09 la card del tennis mostrava **+0,25 €** — che non
 * esisteva da nessuna parte: era +0,41 € di live più −0,16 € di paper.
 * Chiedere «tutte le modalità» va fatto **apposta**, non per distrazione.
 */
export async function fetchSafeDaily(
    from: string, to: string,
    sport: SafeSportFilter = null,
    mode: SafeModeFilter = null,
): Promise<DailyRow[]> {
    const { data, error } = await supabase.rpc('get_safe_daily', {
        p_from: from, p_to: to, p_sport: sport, p_mode: mode,
    });
    if (error) throw new Error(error.message);
    return normalizeDailyRows(data);
}

export async function fetchOmegaDayTrades(day: string): Promise<DayTrade[]> {
    const { data, error } = await supabase.rpc('get_omega_day_trades', { p_day: day });
    if (error) throw new Error(error.message);
    return normalizeDayTrades(data);
}

export async function fetchSafeDayTrades(day: string, sport: SafeSportFilter = null): Promise<DayTrade[]> {
    const { data, error } = await supabase.rpc('get_safe_day_trades', { p_day: day, p_sport: sport });
    if (error) throw new Error(error.message);
    return normalizeDayTrades(data);
}

export async function fetchMikeDaily(from: string, to: string): Promise<DailyRow[]> {
    const { data, error } = await supabase.rpc('get_mike_daily', { p_from: from, p_to: to });
    if (error) throw new Error(error.message);
    return normalizeDailyRows(data);
}

export async function fetchMikeDayTrades(day: string): Promise<DayTrade[]> {
    const { data, error } = await supabase.rpc('get_mike_day_trades', { p_day: day });
    if (error) throw new Error(error.message);
    return normalizeDayTrades(data);
}

// ------------------------------------------------------- giorni (stringhe)
const DAY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** 'YYYY-MM-DD' → ms UTC della mezzanotte (asse X monotono, indipendente dal fuso). */
export function dayToMs(day: string): number {
    const m = DAY_RE.exec(day);
    if (!m) return NaN;
    return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}
function pad2(n: number): string { return n < 10 ? `0${n}` : String(n); }
export function msToDay(ms: number): string {
    const d = new Date(ms);
    return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
}
export function addDays(day: string, n: number): string {
    return msToDay(dayToMs(day) + n * 86_400_000);
}
export function isValidDay(day: string): boolean {
    return DAY_RE.test(day) && Number.isFinite(dayToMs(day)) && msToDay(dayToMs(day)) === day;
}

/** Giornata operativa CORRENTE (Europe/Rome) come 'YYYY-MM-DD'. */
export function romeDay(now: Date = new Date()): string {
    try {
        const parts = new Intl.DateTimeFormat('en-CA', {
            timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit',
        }).formatToParts(now);
        const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
        const s = `${get('year')}-${get('month')}-${get('day')}`;
        if (DAY_RE.test(s)) return s;
    } catch { /* Intl senza timeZone (ambienti minimi): fallback sotto */ }
    return msToDay(now.getTime() + 2 * 3_600_000);
}

/** 'YYYY-MM-DD' → "10 settembre 2026" (etichette UI, senza fuso del browser). */
export function dayLabel(day: string, opts: { weekday?: boolean; year?: boolean } = {}): string {
    const ms = dayToMs(day);
    if (!Number.isFinite(ms)) return day;
    return new Intl.DateTimeFormat('it-IT', {
        timeZone: 'UTC',
        weekday: opts.weekday ? 'long' : undefined,
        day: 'numeric', month: 'long',
        year: opts.year === false ? undefined : 'numeric',
    }).format(new Date(ms));
}

export function monthLabel(year: number, month: number): string {
    return new Intl.DateTimeFormat('it-IT', { timeZone: 'UTC', month: 'long', year: 'numeric' })
        .format(new Date(Date.UTC(year, month - 1, 1)));
}

// ------------------------------------------------------------ periodi UI
export type PeriodKind = 'month' | '30d' | '90d' | 'year';
export const PERIOD_LABEL: Record<PeriodKind, string> = {
    month: 'Mese corrente', '30d': '30 giorni', '90d': '90 giorni', year: 'Anno',
};

/** Intervallo [from, to] (inclusivo) di un periodo rispetto a `today`. */
export function periodRange(kind: PeriodKind, today: string): { from: string; to: string } {
    const m = DAY_RE.exec(today);
    if (!m) throw new RangeError(`giorno non valido: ${today}`);
    const y = m[1], mo = m[2];
    switch (kind) {
        case 'month': return { from: `${y}-${mo}-01`, to: today };
        case '30d': return { from: addDays(today, -29), to: today };
        case '90d': return { from: addDays(today, -89), to: today };
        case 'year': return { from: `${y}-01-01`, to: today };
    }
}

export function filterRange(rows: DailyRow[], from: string, to: string): DailyRow[] {
    return rows.filter((r) => r.day >= from && r.day <= to);
}

// ----------------------------------------------------------- finestra max
/** giorni massimi accettati dalle RPC dello storico (`trading_daily_history`) */
export const MAX_HISTORY_DAYS = 400;

export interface ClampedRange { from: string; to: string; clamped: boolean; days: number }

/**
 * M-17 — la RPC solleva un'eccezione oltre 400 giorni: chiedere 401 giorni
 * faceva sparire TUTTO lo storico dietro un "Storico non disponibile". Il
 * client accorcia la finestra (tenendo la coda più recente) e lo DICHIARA.
 */
export function clampHistoryRange(from: string, to: string, maxDays = MAX_HISTORY_DAYS): ClampedRange {
    if (!isValidDay(from) || !isValidDay(to)) return { from, to, clamped: false, days: 0 };
    const span = Math.round((dayToMs(to) - dayToMs(from)) / 86_400_000);
    // estremi invertiti: si rimettono in ordine E si ri-clampano (prima una
    // finestra rovesciata di oltre 400 giorni tornava intatta e l'RPC alzava
    // di nuovo l'eccezione che questo clamp esiste per evitare)
    if (span < 0) {
        const r = clampHistoryRange(to, from, maxDays);
        return { ...r, clamped: true };
    }
    if (span <= maxDays) return { from, to, clamped: false, days: span + 1 };
    return { from: addDays(to, -maxDays), to, clamped: true, days: maxDays + 1 };
}

export interface HistoryWindow extends ClampedRange {
    /** true = il PERIODO del pannello performance non entra tutto in finestra */
    periodTruncated: boolean;
    /** primo giorno del periodo effettivamente caricato (null = tutto dentro) */
    periodFrom: string | null;
}

/**
 * Certificazione 12/09 — finestra di caricamento dello storico.
 *
 * Prima la finestra era `clampHistoryRange(min(mese, periodo), max(...))`: la
 * coda tenuta erano gli ultimi 400 giorni, quindi navigando il calendario
 * indietro di più di un anno il MESE MOSTRATO finiva FUORI dalla finestra e la
 * griglia diceva «nessuna operazione in gennaio 2025» — una bugia su dati che
 * esistono.
 *
 * Qui il mese visualizzato è SEMPRE dentro (sono al massimo 31 giorni); il
 * periodo del pannello viene incluso fin dove il limite lo consente e, se non
 * ci sta tutto, lo si DICHIARA (`periodTruncated`) invece di mostrare un
 * aggregato silenziosamente parziale.
 */
export function historyWindow(
    month: { from: string; to: string },
    period: { from: string; to: string },
    maxDays = MAX_HISTORY_DAYS,
): HistoryWindow {
    const valid = [month.from, month.to, period.from, period.to].every(isValidDay);
    if (!valid) {
        return { from: month.from, to: month.to, clamped: false, days: 0, periodTruncated: false, periodFrom: null };
    }
    const wantFrom = period.from < month.from ? period.from : month.from;
    const wantTo = period.to > month.to ? period.to : month.to;
    const want = clampHistoryRange(wantFrom, wantTo, maxDays);
    if (!want.clamped) {
        return { ...want, periodTruncated: false, periodFrom: null };
    }
    // non ci sta tutto: si ancora al MESE e si allarga all'indietro quanto resta
    const monthSpan = Math.round((dayToMs(month.to) - dayToMs(month.from)) / 86_400_000);
    const room = maxDays - monthSpan;
    const from = room > 0 ? addDays(month.from, -room) : month.from;
    const to = month.to;
    const days = Math.round((dayToMs(to) - dayToMs(from)) / 86_400_000) + 1;
    const periodTruncated = period.from < from || period.to > to;
    return { from, to, clamped: true, days, periodTruncated, periodFrom: periodTruncated ? from : null };
}

// ------------------------------------------------- attribuzione al giorno
/** Come il calendario attribuisce una posizione a una giornata operativa. */
export type DayAttribution = 'placed' | 'settled';

/**
 * Giornata operativa = giorno di PIAZZAMENTO per TUTTI E TRE i bot.
 * (Il commento storico diceva «Safe per regolazione»: non è più vero dal
 * `safe_strategy_bot_v2.sql`, e la funzione ha sempre ritornato 'placed'.)
 */
export function attributionOf(variant: HistoryVariant): DayAttribution {
    // Giornata operativa = giorno di PIAZZAMENTO per TUTTI i bot (Omega §14,
    // Safe `safe_strategy_bot_v2.sql`, Mike `mike_history_v2.sql`)
    void variant;
    return 'placed';
}

export interface DaySummary {
    /** posizioni che il CALENDARIO attribuisce a questo giorno (le stesse che
     *  fanno `trades_placed` e `pnl_realized` della cella) */
    attributed: DayTrade[];
    /** righe presenti nella risposta ma attribuite a un ALTRO giorno */
    others: DayTrade[];
    /**
     * Certificazione 12/09 — righe della giornata che il calendario NON conta
     * perché NON sono mai arrivate a mercato: `status='error'` e le riserve
     * `pending` senza alcun segno di piazzamento (né `bet_id`, né
     * `flumine_client_ref`, né riconciliazione). `trading_daily_history` le
     * esclude da `trades_placed`/`max_liability`; il dettaglio le contava e
     * l'11/09 Mike diceva «32 trade» in calendario e «44 trade» in testata,
     * con 12 ordini falliti dentro la «liability piazzata».
     */
    notPlaced: DayTrade[];
    /** P&L realizzato del giorno: lo stesso numero della cella del calendario */
    pnl: number;
    /**
     * Quota di `pnl` GIÀ incassata dalle coperture di posizioni ancora VIVE
     * (gambe di chiusura regolate mentre l'apertura è ancora a mercato).
     */
    realizedOnOpen: number;
    settled: number;
    won: number;
    lost: number;
    voided: number;
    /** posizioni ancora vive fra quelle attribuite */
    open: number;
    /** liability piazzata nel giorno */
    liability: number;
    /** P&L bloccato dalle coperture (null = nessuna copertura) */
    lockedPnl: number | null;
}

const DAY_SETTLED = new Set(['won', 'lost', 'void']);
const DAY_LIVE = new Set(['pending', 'open', 'hedged']);

/**
 * Certificazione 12/09 — che cosa contano DAVVERO V e P.
 *
 * `lib/tradeStatus.TIP.winLoss` dice «conta lo stato, non il segno del P&L»:
 * è FALSO: `trading_daily_history` (`trade_tot`), `omega_aggregates_sql`,
 * `safe_aggregates_sql` e `mike_aggregates_sql` contano tutte per SEGNO del
 * P&L totale della posizione. Finché quel testo non viene corretto alla
 * fonte, calendario, KPI e dettaglio usano QUESTO.
 */
export const WIN_LOSS_TIP =
    'V = posizioni con P&L totale positivo, P = negativo (apertura + chiusure): un ciclo greenato vale UNA posizione, non 1 vinta + 1 persa';

/** P&L delle sole gambe di CHIUSURA già regolate di una posizione. */
function settledClosesPnl(t: DayTrade): number {
    let s = 0;
    for (const c of t.closes ?? []) {
        if (DAY_SETTLED.has(c.status)) s += Number(c.pnl) || 0;
    }
    return s;
}

/**
 * Una riga è PIAZZATA con gli stessi criteri del DB (`is_placed` di
 * `trading_daily_history`): ordine reale, marker flumine, oppure riserva in
 * riconciliazione (esito ignoto = l'ordine può essere vivo su Betfair).
 */
export function isPlacedLeg(t: Pick<DayTrade, 'status' | 'meta'> & { bet_id?: unknown }): boolean {
    if (t.status === 'error') return false;
    if (t.status !== 'pending') return true;
    const meta = (t.meta ?? {}) as Record<string, unknown>;
    return t.bet_id != null
        || meta['flumine_client_ref'] != null
        || meta['reason'] === 'place_exception_reconciling';
}

/**
 * Esito della POSIZIONE come lo contano il DB e i KPI: per SEGNO del P&L
 * totale (apertura + chiusure regolate), con lo stato come spareggio sullo
 * zero. Stessa regola di `trading_daily_history` (`trade_tot`),
 * `omega_aggregates_sql`, `safe_aggregates_sql` e `mike_aggregates_sql`.
 * Prima il dettaglio contava lo STATO: il 10/09 la cella Omega diceva
 * «11V 2P» e il piede della stessa tabella «12V 1P».
 */
export function outcomeOf(status: string, totalPnl: number): 'won' | 'lost' | 'void' | null {
    if (!DAY_SETTLED.has(status)) return null;
    if (totalPnl > 0) return 'won';
    if (totalPnl < 0) return 'lost';
    return status === 'won' ? 'won' : status === 'lost' ? 'lost' : 'void';
}

/**
 * M-18/H-11 — i totali del dettaglio giornata devono coincidere con la cella
 * del calendario: si sommano SOLO le posizioni attribuite a quel giorno
 * (`placed_in_day` con l'attribuzione 'placed', `settled_in_day` con
 * 'settled'). Prima il dettaglio sommava qualunque riga regolata presente
 * nella risposta, comprese quelle che il calendario conta in un altro giorno.
 *
 * Certificazione 12/09 — tre allineamenti alla RPC (`trading_daily_history`):
 *  1. il P&L realizzato include le CHIUSURE già regolate anche quando
 *     l'apertura è ancora viva (nel dump reale del 12/09 il calendario Safe
 *     diceva −0,77 € e il dettaglio della stessa giornata +1,90 €: 2,67 € di
 *     coperture incassate che la testata non mostrava);
 *  2. V/P per SEGNO del P&L della posizione, non per stato;
 *  3. conteggio e liability escludono le righe mai arrivate a mercato.
 */
export function summarizeDayTrades(
    trades: DayTrade[] | null | undefined, attribution: DayAttribution,
): DaySummary {
    const list = trades ?? [];
    const belongs = (t: DayTrade) => (attribution === 'placed' ? t.placed_in_day : t.settled_in_day || (t.placed_in_day && !t.settled_at));
    const mine = list.filter(belongs);
    const others = list.filter((t) => !belongs(t));
    const attributed = mine.filter((t) => isPlacedLeg(t));
    const notPlaced = mine.filter((t) => !isPlacedLeg(t));
    let pnl = 0, realizedOnOpen = 0, settled = 0, won = 0, lost = 0, voided = 0, open = 0, liability = 0;
    let lockedPnl: number | null = null;
    for (const t of attributed) {
        if (DAY_SETTLED.has(t.status)) {
            const total = Number(t.total_pnl ?? t.pnl) || 0;
            pnl += total;
            settled += 1;
            const outcome = outcomeOf(t.status, total);
            if (outcome === 'won') won += 1;
            else if (outcome === 'lost') lost += 1;
            else voided += 1;
        } else if (DAY_LIVE.has(t.status)) {
            open += 1;
            // coperture già incassate su una posizione ancora viva: sono soldi
            // REALIZZATI e il calendario li conta (settled_rows della RPC)
            const cashed = settledClosesPnl(t);
            pnl += cashed;
            realizedOnOpen += cashed;
        }
        if (t.placed_in_day) liability += Number(t.liability ?? 0) || 0;
        const lk = Number((t.meta ?? {})['locked_pnl']);
        if (Number.isFinite(lk) && !DAY_SETTLED.has(t.status)) lockedPnl = (lockedPnl ?? 0) + lk;
    }
    return {
        attributed, others, notPlaced,
        pnl: Math.round(pnl * 100) / 100,
        realizedOnOpen: Math.round(realizedOnOpen * 100) / 100,
        settled, won, lost, voided, open,
        liability: Math.round(liability * 100) / 100,
        lockedPnl: lockedPnl == null ? null : Math.round(lockedPnl * 100) / 100,
    };
}

// ------------------------------------------------------------- analitiche
function sortedByDay(rows: DailyRow[]): DailyRow[] {
    return [...rows].sort((a, b) => a.day.localeCompare(b.day));
}
function r2(x: number): number { return Math.round(x * 100) / 100; }

/** Equity per giornata: cumulato del P&L realizzato, un punto per giorno. */
export function equityByDay(rows: DailyRow[]): EquityPoint[] {
    let cum = 0;
    return sortedByDay(rows).map((r) => {
        cum = r2(cum + r.pnl_realized);
        return { t: dayToMs(r.day), v: cum, iso: r.day };
    });
}

export interface DrawdownInfo {
    /** massima discesa dal picco (≥ 0) */
    maxDrawdown: number;
    /** discesa corrente dal picco (≥ 0) */
    currentDrawdown: number;
    /** picco dell'equity (cumulato massimo raggiunto, ≥ 0: si parte da 0) */
    peak: number;
    peakDay: string | null;
    /** giorno in cui si è toccato il fondo del drawdown massimo */
    troughDay: string | null;
}

/** Drawdown sull'equity per giornata (partenza da 0 = nessun trade). */
export function drawdown(rows: DailyRow[]): DrawdownInfo {
    let peak = 0, peakDay: string | null = null;
    let maxDd = 0, troughDay: string | null = null;
    let cum = 0;
    for (const r of sortedByDay(rows)) {
        cum = r2(cum + r.pnl_realized);
        if (cum > peak) { peak = cum; peakDay = r.day; }
        const dd = r2(peak - cum);
        if (dd > maxDd) { maxDd = dd; troughDay = r.day; }
    }
    return { maxDrawdown: maxDd, currentDrawdown: r2(peak - cum), peak, peakDay, troughDay };
}

export interface StreakInfo {
    /** massimo numero di giornate POSITIVE consecutive */
    bestWin: number;
    /** massimo numero di giornate NEGATIVE consecutive */
    bestLoss: number;
    /** serie in corso: >0 giornate positive, <0 negative, 0 nessuna/ultima a zero */
    current: number;
}

/** Serie per giornata: pnl > 0 = positiva, < 0 = negativa, = 0 = neutra (interrompe). */
export function streaks(rows: DailyRow[]): StreakInfo {
    let bestWin = 0, bestLoss = 0, cur = 0;
    for (const r of sortedByDay(rows)) {
        if (r.pnl_realized > 0) cur = cur > 0 ? cur + 1 : 1;
        else if (r.pnl_realized < 0) cur = cur < 0 ? cur - 1 : -1;
        else cur = 0;
        if (cur > bestWin) bestWin = cur;
        if (-cur > bestLoss) bestLoss = -cur;
    }
    return { bestWin, bestLoss, current: cur };
}

/** Profit factor aggregato = Σ gross_profit / Σ gross_loss; null senza perdite. */
export function profitFactor(rows: DailyRow[]): number | null {
    let gp = 0, gl = 0;
    for (const r of rows) { gp += r.gross_profit; gl += Math.abs(r.gross_loss); }
    if (gl <= 0) return null;
    return Math.round((gp / gl) * 1000) / 1000;
}

/** Expectancy = P&L realizzato / aperture regolate; null senza regolati. */
export function expectancy(rows: DailyRow[]): number | null {
    let pnl = 0, n = 0;
    for (const r of rows) { pnl += r.pnl_realized; n += r.settled; }
    if (n <= 0) return null;
    return r2(pnl / n);
}

export interface GoalHitInfo {
    /** giornate con obiettivo STORICIZZATO (> 0 e `goal_snapshot`) */
    total: number;
    /** giornate con pnl_realized ≥ goal */
    hit: number;
    /** hit/total in [0,1]; null senza giornate giudicabili */
    rate: number | null;
    /** H-10: giornate con un obiettivo di RIPIEGO, escluse dal conteggio */
    notHistorized: number;
}

/**
 * Tasso di centratura dell'obiettivo giornaliero (Omega): pnl ≥ goal.
 * H-10 — solo le giornate con obiettivo STORICIZZATO (`goal_snapshot`): usare
 * l'obiettivo corrente per giudicare il passato produce numeri inventati.
 */
export function goalHitRate(rows: DailyRow[]): GoalHitInfo {
    let total = 0, hit = 0, notHistorized = 0;
    for (const r of rows) {
        if (r.goal == null || !(r.goal > 0)) continue;
        if (!r.goal_snapshot) { notHistorized += 1; continue; }
        total += 1;
        if (r.pnl_realized >= r.goal) hit += 1;
    }
    return {
        total, hit, notHistorized,
        rate: total > 0 ? Math.round((hit / total) * 10000) / 10000 : null,
    };
}

export interface MonthSummary {
    year: number;
    month: number;
    pnl: number;
    /** giornate con attività */
    days: number;
    positiveDays: number;
    negativeDays: number;
    tradesPlaced: number;
    settled: number;
    won: number;
    lost: number;
    winRate: number | null;
    bestDay: DailyRow | null;
    worstDay: DailyRow | null;
    goalHit: GoalHitInfo;
}

/** Riepilogo di un mese (month 1-12) dalle righe giornaliere. */
export function monthSummary(rows: DailyRow[], year: number, month: number): MonthSummary {
    if (!Number.isInteger(month) || month < 1 || month > 12) {
        throw new RangeError(`mese non valido: ${month} (atteso 1-12)`);
    }
    const prefix = `${year}-${pad2(month)}-`;
    const inMonth = rows.filter((r) => r.day.startsWith(prefix));
    let pnl = 0, pos = 0, neg = 0, placed = 0, settled = 0, won = 0, lost = 0;
    let best: DailyRow | null = null, worst: DailyRow | null = null;
    for (const r of inMonth) {
        pnl += r.pnl_realized;
        if (r.pnl_realized > 0) pos += 1; else if (r.pnl_realized < 0) neg += 1;
        placed += r.trades_placed; settled += r.settled; won += r.won; lost += r.lost;
        if (!best || r.pnl_realized > best.pnl_realized) best = r;
        if (!worst || r.pnl_realized < worst.pnl_realized) worst = r;
    }
    return {
        year, month, pnl: r2(pnl), days: inMonth.length, positiveDays: pos, negativeDays: neg,
        tradesPlaced: placed, settled, won, lost,
        winRate: won + lost > 0 ? Math.round((won / (won + lost)) * 10000) / 10000 : null,
        bestDay: best, worstDay: worst, goalHit: goalHitRate(inMonth),
    };
}

export interface PeriodSummary {
    pnl: number;
    days: number;
    positiveDays: number;
    negativeDays: number;
    tradesPlaced: number;
    settled: number;
    won: number;
    lost: number;
    void: number;
    hedgedClosed: number;
    winRate: number | null;
    profitFactor: number | null;
    expectancy: number | null;
    drawdown: DrawdownInfo;
    streaks: StreakInfo;
    goalHit: GoalHitInfo;
    bestDay: DailyRow | null;
    worstDay: DailyRow | null;
    /** null se nessuna riga ha una commissione */
    commission: number | null;
    maxLiability: number | null;
    from: string | null;
    to: string | null;
}

/** Tutti i KPI di un insieme di giornate (pannello performance). */
export function summarizeRows(rows: DailyRow[]): PeriodSummary {
    const sorted = sortedByDay(rows);
    let pnl = 0, pos = 0, neg = 0, placed = 0, settled = 0, won = 0, lost = 0, vd = 0, hedged = 0;
    let best: DailyRow | null = null, worst: DailyRow | null = null;
    let commission: number | null = null;
    let maxLiab: number | null = null;
    for (const r of sorted) {
        pnl += r.pnl_realized;
        if (r.pnl_realized > 0) pos += 1; else if (r.pnl_realized < 0) neg += 1;
        placed += r.trades_placed; settled += r.settled; won += r.won; lost += r.lost;
        vd += r.void; hedged += r.hedged_closed;
        if (!best || r.pnl_realized > best.pnl_realized) best = r;
        if (!worst || r.pnl_realized < worst.pnl_realized) worst = r;
        if (r.commission_paid != null) commission = r2((commission ?? 0) + r.commission_paid);
        if (r.max_liability != null && (maxLiab == null || r.max_liability > maxLiab)) maxLiab = r.max_liability;
    }
    return {
        pnl: r2(pnl), days: sorted.length, positiveDays: pos, negativeDays: neg,
        tradesPlaced: placed, settled, won, lost, void: vd, hedgedClosed: hedged,
        winRate: won + lost > 0 ? Math.round((won / (won + lost)) * 10000) / 10000 : null,
        profitFactor: profitFactor(sorted),
        expectancy: expectancy(sorted),
        drawdown: drawdown(sorted),
        streaks: streaks(sorted),
        goalHit: goalHitRate(sorted),
        bestDay: best, worstDay: worst,
        commission, maxLiability: maxLiab,
        from: sorted[0]?.day ?? null,
        to: sorted[sorted.length - 1]?.day ?? null,
    };
}

/** Breakdown aggregato su più giornate per una dimensione (strategia/sport/origine). */
export function aggregateBreakdown(
    rows: DailyRow[], dim: 'by_strategy' | 'by_sport' | 'by_origin',
): Record<string, DailyBreakdown> {
    const out: Record<string, DailyBreakdown> = {};
    for (const r of rows) {
        for (const [k, b] of Object.entries(r[dim] ?? {})) {
            const cur = out[k] ?? { n: 0, pnl: 0, won: 0, lost: 0 };
            out[k] = { n: cur.n + b.n, pnl: r2(cur.pnl + b.pnl), won: cur.won + b.won, lost: cur.lost + b.lost };
        }
    }
    return out;
}

// --------------------------------------------------------------- calendario
export interface CalendarCell {
    day: string;
    /** giorno del mese 1-31 */
    dom: number;
    inMonth: boolean;
    row: DailyRow | null;
    /** 0 = lunedì … 6 = domenica */
    dow: number;
}

/** Griglia del mese (month 1-12): settimane lun→dom, celle fuori mese incluse
 *  (inMonth=false) per completare la prima e l'ultima settimana. */
export function calendarGrid(year: number, month: number, rows: DailyRow[]): CalendarCell[][] {
    if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
        throw new RangeError(`mese non valido: ${year}-${month} (atteso 1-12)`);
    }
    const byDay = new Map<string, DailyRow>();
    for (const r of rows) byDay.set(r.day, r);
    const first = Date.UTC(year, month - 1, 1);
    const firstDow = (new Date(first).getUTCDay() + 6) % 7; // lun=0
    const start = first - firstDow * 86_400_000;
    const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const totalCells = Math.ceil((firstDow + daysInMonth) / 7) * 7;
    const weeks: CalendarCell[][] = [];
    for (let i = 0; i < totalCells; i += 1) {
        const ms = start + i * 86_400_000;
        const d = new Date(ms);
        const day = msToDay(ms);
        const cell: CalendarCell = {
            day,
            dom: d.getUTCDate(),
            inMonth: d.getUTCMonth() === month - 1 && d.getUTCFullYear() === year,
            row: byDay.get(day) ?? null,
            dow: i % 7,
        };
        if (i % 7 === 0) weeks.push([]);
        weeks[weeks.length - 1].push(cell);
    }
    return weeks;
}

/**
 * Estremi della GRIGLIA del mese (lunedì della prima settimana → domenica
 * dell'ultima), non del solo mese.
 *
 * Certificazione 12/09 — il calendario disegna anche le celle di coda del mese
 * precedente e di testa del successivo (`calendar-day-outside`) e su ognuna
 * dichiarava «nessuna operazione». Quelle giornate però non erano MAI dentro
 * la finestra caricata (che partiva dal 1° del mese): un'affermazione su dati
 * mai chiesti. Caricando la griglia intera (al massimo 12 giorni in più su
 * 400) ogni cella mostrata è una cella letta davvero.
 */
export function calendarGridBounds(year: number, month: number): { from: string; to: string } {
    if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
        throw new RangeError(`mese non valido: ${year}-${month} (atteso 1-12)`);
    }
    const firstMs = Date.UTC(year, month - 1, 1);
    const lastMs = Date.UTC(year, month, 0);
    const firstDow = (new Date(firstMs).getUTCDay() + 6) % 7;   // lun = 0
    const lastDow = (new Date(lastMs).getUTCDay() + 6) % 7;
    return { from: msToDay(firstMs - firstDow * 86_400_000), to: msToDay(lastMs + (6 - lastDow) * 86_400_000) };
}

/** Mese precedente/successivo (month 1-12). */
export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
    const idx = year * 12 + (month - 1) + delta;
    return { year: Math.floor(idx / 12), month: (idx % 12 + 12) % 12 + 1 };
}

// ----------------------------------------------------------- uscite auto
export type ExitKind = 'profit' | 'loss' | 'time' | 'red_card' | 'forced' | 'manual' | 'greenup' | 'model' | 'other';

export interface ExitInfo {
    kind: ExitKind;
    /** "Uscita: profitto" … */
    label: string;
    /** motivo esteso scritto dal servizio (tooltip) */
    reason: string | null;
    /** valore grezzo di meta.exit_kind (per i kind 'other') */
    raw: string | null;
}

const EXIT_KIND_ALIASES: Record<string, ExitKind> = {
    profit: 'profit', take_profit: 'profit', tp: 'profit', profitto: 'profit', green: 'profit',
    greenup: 'greenup', green_up: 'greenup', 'green-up': 'greenup', greenup_auto: 'greenup', greenup_forced: 'greenup',
    loss: 'loss', stop_loss: 'loss', sl: 'loss', perdita: 'loss', red: 'loss',
    time: 'time', timeout: 'time', minute: 'time', clock: 'time', tempo: 'time', minuto: 'time',
    red_card: 'red_card', redcard: 'red_card', rosso: 'red_card', card: 'red_card',
    forced: 'forced', mandatory: 'forced', obbligatoria: 'forced', must: 'forced', settle: 'forced',
    lost_game: 'forced', two_lost: 'forced',
    manual: 'manual', cashout: 'manual', user: 'manual',
    // certificazione 12/09: Safe scrive in `meta.exit.kind` il vocabolario
    // della REGOLA (safe_strategy/exits.py), non quello della UI: `model` è
    // l'uscita decisa dal modello e prima finiva in "Uscita" generica
    model: 'model', modello: 'model',
    other: 'other', altro: 'other',
};

export const EXIT_KIND_LABEL: Record<ExitKind, string> = {
    profit: 'Uscita: profitto',
    loss: 'Uscita: perdita',
    time: 'Uscita: tempo',
    red_card: 'Uscita: rosso',
    forced: 'Uscita: obbligatoria',
    manual: 'Cash out manuale',
    greenup: 'Green-up',
    model: 'Uscita: modello',
    other: 'Uscita',
};

/**
 * Certificazione 12/09 — il MOTIVO dell'uscita in italiano.
 *
 * Omega e Safe scrivono `meta.exit_reason` già tradotto; Mike ci mette la
 * chiave tecnica grezza (`mike/service.py:204` = `close_reason` o il `role`
 * della gamba), e il tooltip del badge mostrava «under_green» a un trader.
 * Qui la chiave tecnica diventa una frase; qualunque testo non in tabella
 * passa invariato (Omega/Safe sono già in italiano).
 */
const EXIT_REASON_TEXT: Record<string, string> = {
    // Mike — ruolo della gamba
    under_entry: 'ingresso Under 3.5',
    under_green: 'green-up sull’Under 3.5',
    under_last: 'ultimo ingresso (ordine che resta a book)',
    under_close: 'chiusura dell’Under 3.5',
    over_cover: 'copertura con l’Over 4.5',
    over_close: 'chiusura dell’Over 4.5',
    reentry: 're-ingresso sull’Under 4.5',
    reentry_green: 'green-up del re-ingresso',
    manual_close: 'chiusura manuale',
    // Mike — motivo
    manual: 'richiesta manuale dell’operatore',
    profit: 'profitto raggiunto',
    loss_cap: 'tetto di perdita raggiunto',
    reentry_time: 'finestra del re-ingresso scaduta',
    overshoot: 'prezzo oltre la soglia',
    liquidita: 'liquidità insufficiente',
    pending_stale: 'riserva rimasta senza esito',
};

/** Motivo dell'uscita in italiano; un testo già in chiaro passa invariato. */
export function exitReasonText(reason: string | null | undefined): string | null {
    if (reason == null) return null;
    const s = String(reason).trim();
    if (s === '') return null;
    return EXIT_REASON_TEXT[s.toLowerCase()] ?? s;
}

/** Legge meta.exit_kind / meta.exit_reason (o meta.exit.{kind,reason}) di una
 *  gamba. null = nessuna uscita automatica registrata. */
export function exitInfo(meta: Record<string, unknown> | null | undefined): ExitInfo | null {
    if (!meta) return null;
    const nested = (meta.exit && typeof meta.exit === 'object') ? meta.exit as Record<string, unknown> : null;
    const rawKind = meta.exit_kind ?? nested?.kind ?? null;
    const rawReason = meta.exit_reason ?? nested?.reason ?? null;
    const kindStr = rawKind != null ? String(rawKind).trim().toLowerCase() : '';
    const reason = exitReasonText(rawReason == null ? null : String(rawReason));
    if (!kindStr && !reason) return null;
    const kind: ExitKind = kindStr ? (EXIT_KIND_ALIASES[kindStr] ?? 'other') : 'other';
    // 'other' è un valore LEGITTIMO del vocabolario: etichetta italiana, non la chiave nuda
    const label = kind === 'other' && kindStr && !(kindStr in EXIT_KIND_ALIASES) ? `Uscita: ${kindStr}` : EXIT_KIND_LABEL[kind];
    return { kind, label, reason, raw: kindStr || null };
}

/**
 * Uscita di una posizione: prima quella sull'apertura, poi sulle chiusure.
 *
 * Certificazione 12/09 — una gamba di chiusura in ERRORE (ordine annullato o
 * mai piazzato) NON è un'uscita avvenuta: nel dump reale di Mike del 12/09 tre
 * posizioni regolate a mercato mostravano il badge «Green-up» mentre la gamba
 * di green-up era `status='error'` (`meta.reason='cancelled_by_engine'`). Il
 * trader leggeva un green-up che non c'è mai stato.
 */
export function tradeExit(trade: { meta: Record<string, unknown> | null; closes?: DayTradeLeg[] }): ExitInfo | null {
    const own = exitInfo(trade.meta);
    if (own) return own;
    const real = (trade.closes ?? []).filter((c) => c.status !== 'error');
    for (const c of real) {
        const e = exitInfo(c.meta);
        if (e) return e;
    }
    // cash out MANUALE: il servizio marca la chiusura con meta.cashout=true senza
    // exit_kind (review 11/09 L3) → "Cash out manuale", non una generica "Chiusura"
    for (const c of real) {
        if ((c.meta ?? {})['cashout'] === true && !(c.meta ?? {})['exit_kind']) {
            return { kind: 'manual', label: EXIT_KIND_LABEL.manual, reason: null, raw: 'cashout' };
        }
    }
    return null;
}
