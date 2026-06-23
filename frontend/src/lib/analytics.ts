// ============================================================================
// Analytics — data layer per la pagina /analytics (centro di controllo).
// Legge SOLO via RPC aggregati (get_analytics / get_analytics_filters): la
// tabella analytics_signals NON è esposta al client (RLS). Nessun dato sensibile.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

export interface AnalyticsGroup {
    grp: string;
    n: number;
    hits: number;
    hit_rate: number;     // 0..1
    avg_prob: number;     // 0..1 (prob media del motore)
    wilson_low: number;   // 0..1
    wilson_high: number;  // 0..1
    calib_gap: number;    // hit_rate - avg_prob (>0 = motore SOTTOstima)
}

export interface AnalyticsResult {
    group_by: string;
    z: number;
    groups: AnalyticsGroup[];
}

export interface AnalyticsFilters {
    engines: { value: string; n: number }[];
    markets: { value: string; n: number }[];
    leagues: { id: number; name: string | null; n: number }[];
    seasons: number[];
    total_settled: number;
}

export interface AnalyticsQuery {
    engine?: string | null;
    market?: string | null;
    selection?: string | null;
    leagueId?: number | null;
    seasonYear?: number | null;
    probMin?: number | null;   // 0..1
    probMax?: number | null;   // 0..1
    minAgree?: number | null;
    placedOnly?: boolean;
    dateFrom?: string | null;
    dateTo?: string | null;
    delayMin?: number | null;       // ritardo attuale minimo del mercato
    freqDev?: string | null;        // 'pos' | 'neg' | null
    timingMax?: number | null;      // primo gol entro il minuto X
    confBin?: number | null;        // drill: bin di confidenza (inizio %, es 60) — SOLO get_analytics_rows
    groupBy?: string;          // overall|engine|market|selection|league|confidence
}

// 1 partita del drill-down
export interface AnalyticsRow {
    engine: string;
    league_name: string | null;
    home_team: string | null;
    away_team: string | null;
    kickoff: string | null;
    market: string;
    selection: string;
    prob: number;
    hit: boolean;
    result: string | null;
    freq_baseline: number | null;
    freq_current: number | null;
    freq_deviation: number | null;
    delay_current: number | null;
    first_goal_minute: number | null;
}

export async function fetchAnalyticsFilters(): Promise<AnalyticsFilters> {
    const { data, error } = await supabase.rpc('get_analytics_filters');
    if (error) throw new Error(error.message);
    return data as AnalyticsFilters;
}

function rpcParams(q: AnalyticsQuery) {
    return {
        p_engine: q.engine ?? null,
        p_market: q.market ?? null,
        p_selection: q.selection ?? null,
        p_league_id: q.leagueId ?? null,
        p_season_year: q.seasonYear ?? null,
        p_prob_min: q.probMin ?? null,
        p_prob_max: q.probMax ?? null,
        p_min_agree: q.minAgree ?? null,
        p_placed_only: q.placedOnly ?? false,
        p_date_from: q.dateFrom ?? null,
        p_date_to: q.dateTo ?? null,
        p_delay_min: q.delayMin ?? null,
        p_freq_dev: q.freqDev ?? null,
        p_timing_max: q.timingMax ?? null,
    };
}

export async function fetchAnalytics(q: AnalyticsQuery): Promise<AnalyticsResult> {
    const { data, error } = await supabase.rpc('get_analytics', {
        ...rpcParams(q),
        p_group_by: q.groupBy ?? 'overall',
    });
    if (error) throw new Error(error.message);
    return data as AnalyticsResult;
}

export async function fetchAnalyticsRows(q: AnalyticsQuery, limit = 100): Promise<AnalyticsRow[]> {
    const { data, error } = await supabase.rpc('get_analytics_rows', {
        ...rpcParams(q),
        p_conf_bin: q.confBin ?? null,
        p_limit: limit,
        p_offset: 0,
    });
    if (error) throw new Error(error.message);
    return (data?.rows ?? []) as AnalyticsRow[];
}

// Export CSV (client-side) di un insieme di gruppi della pagella.
export function groupsToCsv(groups: AnalyticsGroup[], dim: string): string {
    const head = [dim, 'N', 'hit_rate', 'wilson_low', 'wilson_high', 'avg_prob', 'calib_gap'];
    const esc = (s: string) => `"${String(s).replace(/"/g, '""')}"`;
    const lines = [head.join(',')];
    for (const g of groups) {
        lines.push([esc(g.grp), g.n, g.hit_rate, g.wilson_low, g.wilson_high, g.avg_prob, g.calib_gap].join(','));
    }
    return lines.join('\n');
}

// ============================== LAYER DECISIONI ==============================
export interface DecisionGroup {
    grp: string;
    n: number;
    placed: number;
    rejected: number;
    no_signal: number;
    settled_placed: number;
    hits: number;
    stake: number;
    pnl: number;
    hit_rate: number | null;   // delle piazzate settlate
    roi: number | null;        // pnl/stake
    avg_edge: number | null;
    avg_odds: number | null;
    avg_prob: number | null;
}
export interface DecisionsResult { group_by: string; groups: DecisionGroup[]; }
export interface DecisionsFilters {
    logics: { value: string; n: number }[];
    statuses: { value: string; n: number }[];
    engines: { value: string; n: number }[];
    markets: { value: string; n: number }[];
    rejects: { value: string; n: number }[];
    total: number;
}
export interface DecisionsQuery {
    logic?: string | null; status?: string | null; engine?: string | null;
    market?: string | null; selection?: string | null; leagueId?: number | null;
    seasonYear?: number | null; reject?: string | null;
    dateFrom?: string | null; dateTo?: string | null; groupBy?: string;
}

export async function fetchDecisionsFilters(): Promise<DecisionsFilters> {
    const { data, error } = await supabase.rpc('get_decisions_filters');
    if (error) throw new Error(error.message);
    return data as DecisionsFilters;
}
export async function fetchDecisions(q: DecisionsQuery): Promise<DecisionsResult> {
    const { data, error } = await supabase.rpc('get_decisions', {
        p_logic: q.logic ?? null, p_status: q.status ?? null, p_engine: q.engine ?? null,
        p_market: q.market ?? null, p_selection: q.selection ?? null, p_league_id: q.leagueId ?? null,
        p_season_year: q.seasonYear ?? null, p_reject: q.reject ?? null,
        p_date_from: q.dateFrom ?? null, p_date_to: q.dateTo ?? null, p_group_by: q.groupBy ?? 'logic',
    });
    if (error) throw new Error(error.message);
    return data as DecisionsResult;
}

export const DECISIONS_GROUP_OPTIONS = [
    { value: 'logic', label: 'Per logica decisionale' },
    { value: 'engine', label: 'Per motore' },
    { value: 'market', label: 'Per mercato' },
    { value: 'reject', label: 'Per motivo scarto' },
    { value: 'status', label: 'Per stato' },
    { value: 'selection', label: 'Per selezione' },
    { value: 'league', label: 'Per lega' },
    { value: 'confidence', label: 'Per fascia confidenza' },
];

export function downloadCsv(filename: string, csv: string): void {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------- etichette
export const ENGINE_LABEL: Record<string, string> = {
    poisson: 'Poisson', ml: 'ML', api: 'API', tacticai: 'Tactics',
};

export const MARKET_LABEL: Record<string, string> = {
    '1x2': 'Esito Finale (1X2)',
    ht_1x2: 'Esito 1° Tempo',
    over_1_5: 'Over/Under 1.5',
    over_2_5: 'Over/Under 2.5',
    over_3_5: 'Over/Under 3.5',
    btts: 'Gol/No Gol (BTTS)',
    first_half_over_0_5: 'Gol 1° Tempo (0.5)',
};

export const GROUP_BY_OPTIONS = [
    { value: 'overall', label: 'Totale' },
    { value: 'confidence', label: 'Per fascia di confidenza' },
    { value: 'market', label: 'Per mercato' },
    { value: 'selection', label: 'Per selezione' },
    { value: 'engine', label: 'Per motore' },
    { value: 'league', label: 'Per lega' },
];

export const pct = (v: number | null | undefined, d = 1) =>
    v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`;

// ============================== MOTORE STRATEGIE =============================
// Backtest parametrico (backtest_strategy) + storage virtuale (strategies).
// Le chiavi di StrategyFilters sono snake_case: vengono salvate AS-IS nel JSON
// e lette da run_strategy lato DB (unica mappatura filtri→RPC, certificata).
export interface StrategyFilters {
    date_from?: string | null;
    date_to?: string | null;
    market?: string | null;
    selection?: string | null;
    leagues?: number[] | null;
    direction?: 'back' | 'lay';
    odds_source?: 'betfair_book' | 'betfair' | 'book';
    commission?: number;          // 0..1 (default 0.05)
    min_odds?: number | null;
    max_odds?: number | null;
    poisson_min?: number | null;  // 0..1
    ml_min?: number | null;
    tacticai_min?: number | null;
    api_over?: boolean;
    n_engines_min?: number | null;
    min_edge?: number | null;
    delay_eq?: number | null;
    delay_min?: number | null;
    freq_dir?: 'below' | 'above' | null;
    ml_clean?: boolean;
    status?: string | null;       // PLACED|REJECTED|NO_SIGNAL
    group_by?: string;            // market_league|market|league|overall|month
}

export interface BacktestRow {
    grp: string;
    n: number;
    n_settled: number;
    n_hit: number;
    hit_rate: number | null;
    wilson_low: number | null;
    wilson_high: number | null;
    n_priced: number;
    n_unpriced: number;
    profit: number | null;
    turnover: number | null;
    roi: number | null;
    roi_low: number | null;
    roi_high: number | null;
    avg_odds: number | null;
}

export interface Strategy {
    id: string;
    name: string;
    filters: StrategyFilters;
    created_at: string;
    updated_at: string;
}

function backtestParams(f: StrategyFilters) {
    const num = (v: number | null | undefined) => (v === undefined ? null : v);
    return {
        p_date_from: f.date_from ?? null,
        p_date_to: f.date_to ?? null,
        p_market: f.market ?? null,
        p_selection: f.selection ?? null,
        p_leagues: f.leagues && f.leagues.length ? f.leagues : null,
        p_direction: f.direction ?? 'back',
        p_odds_source: f.odds_source ?? 'betfair_book',
        p_commission: f.commission ?? 0.05,
        p_min_odds: num(f.min_odds),
        p_max_odds: num(f.max_odds),
        p_poisson_min: num(f.poisson_min),
        p_ml_min: num(f.ml_min),
        p_tacticai_min: num(f.tacticai_min),
        p_api_over: f.api_over ?? false,
        p_n_engines_min: num(f.n_engines_min),
        p_min_edge: num(f.min_edge),
        p_delay_eq: num(f.delay_eq),
        p_delay_min: num(f.delay_min),
        p_freq_dir: f.freq_dir ?? null,
        p_ml_clean: f.ml_clean ?? false,
        p_status: f.status ?? null,
        p_group_by: f.group_by ?? 'market_league',
    };
}

export async function fetchBacktest(f: StrategyFilters): Promise<BacktestRow[]> {
    const { data, error } = await supabase.rpc('backtest_strategy', backtestParams(f));
    if (error) throw new Error(error.message);
    return (data ?? []) as BacktestRow[];
}

export async function listStrategies(): Promise<Strategy[]> {
    const { data, error } = await supabase.rpc('list_strategies');
    if (error) throw new Error(error.message);
    return (data ?? []) as Strategy[];
}

export async function saveStrategy(name: string, filters: StrategyFilters): Promise<string> {
    const { data, error } = await supabase.rpc('save_strategy', { p_name: name, p_filters: filters });
    if (error) throw new Error(error.message);
    return data as string;
}

export async function deleteStrategy(id: string): Promise<void> {
    const { error } = await supabase.rpc('delete_strategy', { p_id: id });
    if (error) throw new Error(error.message);
}

export async function runStrategy(id: string, groupBy?: string): Promise<BacktestRow[]> {
    const { data, error } = await supabase.rpc('run_strategy', { p_id: id, p_group_by: groupBy ?? null });
    if (error) throw new Error(error.message);
    return (data ?? []) as BacktestRow[];
}

export const STRATEGY_GROUP_OPTIONS = [
    { value: 'market_league', label: 'Per mercato × lega' },
    { value: 'market', label: 'Per mercato' },
    { value: 'league', label: 'Per lega' },
    { value: 'month', label: 'Per mese' },
    { value: 'overall', label: 'Totale' },
];
