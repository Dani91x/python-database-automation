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
    // COPERTURA della registrazione (solo backtest flumine per-evento, campi
    // nuovi lato backend): assenti nei risultati vecchi e nel backtest strategie
    // → la UI non mostra nulla (difensivo).
    coverage_pct?: number | null;      // 0-100 (aggregato = MIN tra gli eventi)
    coverage_verdict?: string | null;  // COMPLETE | PARTIAL | ... (peggiore)
    // dettaglio per evento (fix 17/07): {event_id: {coverage_pct, coverage_verdict}}
    coverage_events?: Record<string, { coverage_pct?: number; coverage_verdict?: string }> | null;
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

// Singola partita (drill-down della strategia) con TUTTI i dati per certificare a occhio.
export interface StrategyBetRow {
    kickoff: string | null;
    league_name: string | null;
    home_team: string | null;
    away_team: string | null;
    market: string;
    selection: string;
    poisson_prob: number | null;
    ml_prob: number | null;
    tacticai_prob: number | null;
    api_over_line: number | null;
    n_engines_agree: number | null;
    delay_current: number | null;
    freq_deviation: number | null;
    odds: number | null;
    odds_src: string | null;
    edge: number | null;
    status: string | null;
    settled: boolean | null;
    hit: boolean | null;
    total_goals: number | null;
    goals_home: number | null;
    goals_away: number | null;
    first_goal_minute: number | null;
    pnl: number | null;
}

export async function runStrategyRows(id: string, limit = 500, offset = 0): Promise<StrategyBetRow[]> {
    const { data, error } = await supabase.rpc('run_strategy_rows', { p_id: id, p_limit: limit, p_offset: offset });
    if (error) throw new Error(error.message);
    return (data ?? []) as StrategyBetRow[];
}

// ====================== BACKTEST AUTOMATICO (flumine) =======================
// Backtest UFFICIALE via FlumineSimulation eseguito da un worker locale: la
// dashboard inserisce una richiesta (request_backtest), segue lo stato in
// realtime (live_backtest_requests) e, a DONE, carica i risultati aggregati
// (list_backtest_results). Le metriche derivano SOLO dal settlement flumine.
export type BacktestMode = 'engine' | 'sandbox';
export type BacktestStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'ERROR';

export type PersistenceType = 'LAPSE' | 'PERSIST' | 'MARKET_ON_CLOSE';

export interface BacktestRequestParams {
    event_ids: string[];
    mode: BacktestMode;
    bankroll?: number;
    min_edge?: number;             // engine: frazionario (0.05 = 5%)
    kelly_fraction?: number;       // engine: frazione di Kelly (0.25 = quarter Kelly)
    rules?: SandboxRules;          // sandbox: regola meccanica configurabile
    // --- esecuzione (realismo flumine), validi per entrambe le modalità ---
    commission_rate?: number;      // commissione Betfair (0.05 = 5% sul netto/mercato)
    persistence_type?: PersistenceType;        // sorte dell'inmatchato a fine mercato
    simulation_available_prices?: boolean;     // matcha anche contro i prezzi disponibili
    place_latency?: number;        // latenza simulata di piazzamento (secondi)
    cancel_latency?: number;       // latenza simulata di cancellazione (secondi)
}

// Sandbox = regola meccanica semplice (nessun modello). Tutti i campi opzionali:
// l'assenza di un filtro = nessun vincolo su quella dimensione.
export interface SandboxRules {
    market_type?: string | null;   // es. MATCH_ODDS, OVER_UNDER_25 (vuoto = tutti)
    side?: 'BACK' | 'LAY';         // direzione ordine
    selection_id?: number | null;  // selezione specifica (vuoto = tutte)
    entry_minute?: number | null;  // entra solo dopo questo minuto di gioco
    entry_price_max?: number | null; // entra solo se prezzo disponibile <= soglia
    stake?: number | null;         // stake fisso £
}

export interface BacktestRunRequest {
    id: string;                    // uuid
    status: BacktestStatus;
    params: BacktestRequestParams;
    created_at: string;
    updated_at: string;
    error_detail: string | null;
}

// Riga risultato grezza dall'RPC (list_backtest_results).
export interface BacktestResultRow {
    scope: string;
    grp: string;
    n_bets: number;
    n_won: number;
    hit_rate: number;              // 0..1
    roi: number;                   // frazionario
    total_pnl: number;
    max_drawdown: number;
    avg_odds: number;
    metrics: Record<string, unknown>;
    // COPERTURA registrazione per evento (backend nuovo, 17/07): % di partita
    // realmente coperta dalla registrazione e verdetto (COMPLETE/PARTIAL).
    // Opzionali: i risultati vecchi non li hanno.
    coverage_pct?: number | null;
    coverage_verdict?: string | null;
}

// request_backtest(p_params jsonb) -> uuid (id richiesta)
export async function requestBacktest(params: BacktestRequestParams): Promise<string> {
    const { data, error } = await supabase.rpc('request_backtest', { p_params: params });
    if (error) throw new Error(error.message);
    return data as string;
}

// list_backtest_runs() -> { rows: BacktestRunRequest[] }
export async function fetchBacktestRuns(): Promise<BacktestRunRequest[]> {
    const { data, error } = await supabase.rpc('list_backtest_runs');
    if (error) throw new Error(error.message);
    const raw = data as { rows?: BacktestRunRequest[] } | BacktestRunRequest[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// list_backtest_results(p_request_id) -> { rows: BacktestResultRow[] }, mappate
// sulla forma BacktestRow così che il componente <BacktestResults> le renderizzi.
export async function fetchBacktestResults(requestId: string): Promise<BacktestRow[]> {
    const { data, error } = await supabase.rpc('list_backtest_results', { p_request_id: requestId });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: BacktestResultRow[] } | BacktestResultRow[] | null;
    const rows = Array.isArray(raw) ? raw : (raw?.rows ?? []);
    return rows.map(mapResultToBacktestRow);
}

// Adatta una ResultRow flumine alla forma BacktestRow attesa da <BacktestResults>.
// Campi non disponibili dal settlement flumine (Wilson/CI/no-quota) → null/0.
function mapResultToBacktestRow(r: BacktestResultRow): BacktestRow {
    return {
        grp: r.scope && r.scope !== r.grp ? `${r.scope} · ${r.grp}` : r.grp,
        n: r.n_bets,
        n_settled: r.n_bets,        // flumine settla ogni ordine simulato
        n_hit: r.n_won,
        hit_rate: r.hit_rate ?? null,
        wilson_low: null,
        wilson_high: null,
        n_priced: r.n_bets,
        n_unpriced: 0,
        profit: r.total_pnl ?? null,
        turnover: r.roi ? (r.total_pnl ?? 0) / r.roi : null,  // turnover ≈ pnl/roi
        roi: r.roi ?? null,
        roi_low: null,
        roi_high: null,
        avg_odds: r.avg_odds ?? null,
        // copertura registrazione: il backend la scrive dentro il jsonb `metrics`
        // (contratto 17/07); accettiamo anche il livello riga per compatibilità.
        // Difensivo: risultati vecchi → undefined → nessun badge in UI.
        coverage_pct: typeof r.coverage_pct === 'number' ? r.coverage_pct
            : typeof (r.metrics as Record<string, unknown> | null)?.coverage_pct === 'number'
                ? (r.metrics as Record<string, unknown>).coverage_pct as number : undefined,
        coverage_verdict: typeof r.coverage_verdict === 'string' ? r.coverage_verdict
            : typeof (r.metrics as Record<string, unknown> | null)?.coverage_verdict === 'string'
                ? (r.metrics as Record<string, unknown>).coverage_verdict as string : undefined,
        coverage_events: (() => {
            const ev = (r.metrics as Record<string, unknown> | null)?.coverage_events;
            return ev && typeof ev === 'object' && !Array.isArray(ev)
                ? ev as Record<string, { coverage_pct?: number; coverage_verdict?: string }>
                : undefined;
        })(),
    };
}

// Sottoscrizione realtime alla riga di richiesta (stato PENDING→RUNNING→DONE/ERROR).
export function subscribeBacktestRequest(
    id: string,
    cb: (row: BacktestRunRequest | null) => void,
): () => void {
    const channel = supabase
        .channel(`live_backtest_requests:${id}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'live_backtest_requests', filter: `id=eq.${id}` },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as BacktestRunRequest | null;
                cb(next);
            },
        )
        .subscribe();
    return () => { supabase.removeChannel(channel); };
}

export const BACKTEST_STATUS_LABEL: Record<BacktestStatus, string> = {
    PENDING: 'In coda',
    RUNNING: 'In esecuzione',
    DONE: 'Completato',
    ERROR: 'Errore',
};

export const STRATEGY_GROUP_OPTIONS = [
    { value: 'market_league', label: 'Per mercato × lega' },
    { value: 'market', label: 'Per mercato' },
    { value: 'league', label: 'Per lega' },
    { value: 'month', label: 'Per mese' },
    { value: 'overall', label: 'Totale' },
];
