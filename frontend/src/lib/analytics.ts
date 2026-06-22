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
