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
    groupBy?: string;          // overall|engine|market|selection|league|confidence
}

export async function fetchAnalyticsFilters(): Promise<AnalyticsFilters> {
    const { data, error } = await supabase.rpc('get_analytics_filters');
    if (error) throw new Error(error.message);
    return data as AnalyticsFilters;
}

export async function fetchAnalytics(q: AnalyticsQuery): Promise<AnalyticsResult> {
    const { data, error } = await supabase.rpc('get_analytics', {
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
        p_group_by: q.groupBy ?? 'overall',
    });
    if (error) throw new Error(error.message);
    return data as AnalyticsResult;
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
