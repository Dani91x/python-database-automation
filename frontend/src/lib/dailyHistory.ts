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

export async function fetchSafeDaily(from: string, to: string, sport: SafeSportFilter = null): Promise<DailyRow[]> {
    const { data, error } = await supabase.rpc('get_safe_daily', { p_from: from, p_to: to, p_sport: sport });
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
    /** giornate con obiettivo definito (> 0) */
    total: number;
    /** giornate con pnl_realized ≥ goal */
    hit: number;
    /** hit/total in [0,1]; null senza giornate con obiettivo */
    rate: number | null;
}

/** Tasso di centratura dell'obiettivo giornaliero (Omega): pnl ≥ goal. */
export function goalHitRate(rows: DailyRow[]): GoalHitInfo {
    let total = 0, hit = 0;
    for (const r of rows) {
        if (r.goal == null || !(r.goal > 0)) continue;
        total += 1;
        if (r.pnl_realized >= r.goal) hit += 1;
    }
    return { total, hit, rate: total > 0 ? Math.round((hit / total) * 10000) / 10000 : null };
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

/** Mese precedente/successivo (month 1-12). */
export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
    const idx = year * 12 + (month - 1) + delta;
    return { year: Math.floor(idx / 12), month: (idx % 12 + 12) % 12 + 1 };
}

// ----------------------------------------------------------- uscite auto
export type ExitKind = 'profit' | 'loss' | 'time' | 'red_card' | 'forced' | 'manual' | 'greenup' | 'other';

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
};

export const EXIT_KIND_LABEL: Record<ExitKind, string> = {
    profit: 'Uscita: profitto',
    loss: 'Uscita: perdita',
    time: 'Uscita: tempo',
    red_card: 'Uscita: rosso',
    forced: 'Uscita: obbligatoria',
    manual: 'Cash out manuale',
    greenup: 'Green-up',
    other: 'Uscita',
};

/** Legge meta.exit_kind / meta.exit_reason (o meta.exit.{kind,reason}) di una
 *  gamba. null = nessuna uscita automatica registrata. */
export function exitInfo(meta: Record<string, unknown> | null | undefined): ExitInfo | null {
    if (!meta) return null;
    const nested = (meta.exit && typeof meta.exit === 'object') ? meta.exit as Record<string, unknown> : null;
    const rawKind = meta.exit_kind ?? nested?.kind ?? null;
    const rawReason = meta.exit_reason ?? nested?.reason ?? null;
    const kindStr = rawKind != null ? String(rawKind).trim().toLowerCase() : '';
    const reason = rawReason != null && String(rawReason).trim() !== '' ? String(rawReason) : null;
    if (!kindStr && !reason) return null;
    const kind: ExitKind = kindStr ? (EXIT_KIND_ALIASES[kindStr] ?? 'other') : 'other';
    const label = kind === 'other' && kindStr ? `Uscita: ${kindStr}` : EXIT_KIND_LABEL[kind];
    return { kind, label, reason, raw: kindStr || null };
}

/** Uscita di una posizione: prima quella sull'apertura, poi sulle chiusure. */
export function tradeExit(trade: { meta: Record<string, unknown> | null; closes?: DayTradeLeg[] }): ExitInfo | null {
    const own = exitInfo(trade.meta);
    if (own) return own;
    for (const c of trade.closes ?? []) {
        const e = exitInfo(c.meta);
        if (e) return e;
    }
    // cash out MANUALE: il servizio marca la chiusura con meta.cashout=true senza
    // exit_kind (review 11/09 L3) → "Cash out manuale", non una generica "Chiusura"
    for (const c of trade.closes ?? []) {
        if ((c.meta ?? {})['cashout'] === true && !(c.meta ?? {})['exit_kind']) {
            return { kind: 'manual', label: EXIT_KIND_LABEL.manual, reason: null, raw: 'cashout' };
        }
    }
    return null;
}
