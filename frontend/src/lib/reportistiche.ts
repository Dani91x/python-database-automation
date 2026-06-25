// ============================================================================
// Reportistiche — data layer per la sezione /analytics → "Reportistiche".
// Report "Direzioni": come performano nel tempo i migliori segnali della tab
// Direzione. Legge SOLO via RPC aggregati certificati (get_direction_report /
// get_direction_report_matches) — analytics_signals non è esposta al client.
// Math certificata da _certify_direction_report.py (oracolo == RPC, 0 mismatch).
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

export interface DirReportKpi {
    n: number;
    hits: number;
    hit_rate: number | null;       // 0..1, null se n=0
    avg_prob: number | null;
    calib_gap: number | null;      // hit_rate - avg_prob
    wilson_low: number | null;
    wilson_high: number | null;
    good_n: number;
    good_hits: number;
    good_hit_rate: number | null;
}
export interface DirDaily {
    giorno: string;                // YYYY-MM-DD (fuso Europe/Rome)
    n: number; hits: number;
    hit_rate: number | null;
    avg_prob: number | null;
    good_n: number;
    good_hit_rate: number | null;
}
export interface DirByMarket {
    market: string;
    n: number; hits: number;
    hit_rate: number | null;
    avg_prob: number | null;
    good_n: number;
    good_hit_rate: number | null;
}
export interface DirByMarketDay {
    market: string; giorno: string;
    n: number; hit_rate: number | null;
}
export interface DirByLeague {
    league_id: number | null;
    league_name: string | null;
    n: number; hits: number;
    hit_rate: number | null;
    avg_prob: number | null;
    good_n: number;
    good_hit_rate: number | null;
}
export interface DirLeagueOpt { id: number | null; name: string | null; n: number; }
export interface DirReportMeta {
    from: string; to: string;
    league_id: number | null;
    market: string | null;
    only_good: boolean;
    generated_at: string;
    leagues: DirLeagueOpt[];
}
export interface DirReport {
    meta: DirReportMeta;
    kpi: DirReportKpi;
    daily: DirDaily[];
    by_market: DirByMarket[];
    by_market_day: DirByMarketDay[];
    by_league: DirByLeague[];
}
export interface DirMatchRow {
    fixture_id: number;
    giorno: string;
    league_id: number | null;
    league_name: string | null;
    home_team: string | null;
    away_team: string | null;
    goals_home: number | null;
    goals_away: number | null;
    dir_tot: number; dir_ok: number;
    good_tot: number; good_ok: number;
}

export interface DirReportQuery {
    from: string;                  // YYYY-MM-DD
    to: string;                    // YYYY-MM-DD
    leagueId?: number | null;
    market?: string | null;
    onlyGood?: boolean;
    betfairOnly?: boolean;         // solo partite presenti su Betfair (engine_signals)
}

function rpcParams(q: DirReportQuery) {
    return {
        p_from: q.from,
        p_to: q.to,
        p_league_id: q.leagueId ?? null,
        p_market: q.market ?? null,
        p_only_good: q.onlyGood ?? false,
        p_betfair_only: q.betfairOnly ?? false,
    };
}

export async function fetchDirReport(q: DirReportQuery): Promise<DirReport> {
    const { data, error } = await supabase.rpc('get_direction_report', rpcParams(q));
    if (error) throw new Error(error.message);
    return data as DirReport;
}

export interface DirMatchesPage { rows: DirMatchRow[]; total: number; }
export async function fetchDirMatches(q: DirReportQuery, limit = 500, offset = 0): Promise<DirMatchesPage> {
    const { data, error } = await supabase.rpc('get_direction_report_matches', {
        ...rpcParams(q),
        p_limit: limit,
        p_offset: offset,
    });
    if (error) throw new Error(error.message);
    // la RPC ritorna { total, offset, limit, rows }; difesa anche se tornasse un array nudo
    const raw = data as DirMatchRow[] | { rows?: DirMatchRow[]; total?: number } | null;
    if (Array.isArray(raw)) return { rows: raw, total: raw.length };
    return { rows: raw?.rows ?? [], total: raw?.total ?? 0 };
}

// drill fine: le 7 direzioni di UNA partita con esito ✓/✗
export interface DirFixtureRow {
    market: string;
    selection: string;
    prob: number | null;
    n_engines_agree: number | null;
    hit: boolean | null;
}
export interface DirFixtureDetail {
    fixture_id: number;
    home_team: string | null;
    away_team: string | null;
    league_name: string | null;
    giorno: string | null;
    goals_home: number | null;
    goals_away: number | null;
    rows: DirFixtureRow[];
}
export async function fetchDirFixture(fixtureId: number): Promise<DirFixtureDetail | null> {
    const { data, error } = await supabase.rpc('get_direction_report_fixture', { p_fixture_id: fixtureId });
    if (error) throw new Error(error.message);
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    return data as DirFixtureDetail;
}

// ----------------------------------------------------------------- etichette
// Riusa le stesse etichette mercato del resto di /analytics (coerenza).
export const DIR_MARKET_LABEL: Record<string, string> = {
    '1x2': 'Esito Finale (1X2)',
    ht_1x2: 'Esito 1° Tempo',
    over_1_5: 'Over/Under 1.5',
    over_2_5: 'Over/Under 2.5',
    over_3_5: 'Over/Under 3.5',
    btts: 'Gol/No Gol (BTTS)',
    first_half_over_0_5: 'Gol 1° Tempo (0.5)',
};
export const DIR_MARKET_SHORT: Record<string, string> = {
    '1x2': '1X2', ht_1x2: 'HT 1X2', over_1_5: 'Over 1.5', over_2_5: 'Over 2.5',
    over_3_5: 'Over 3.5', btts: 'BTTS', first_half_over_0_5: '1°T Over 0.5',
};
export const DIR_MARKETS = ['1x2', 'ht_1x2', 'over_1_5', 'over_2_5', 'over_3_5', 'btts', 'first_half_over_0_5'];

// Catalogo report disponibili nella sezione "Reportistiche" (estendibile).
export const REPORTS = [
    { id: 'direzioni', label: 'Direzioni', desc: 'Performance dei segnali direzione nel tempo' },
] as const;
export type ReportId = typeof REPORTS[number]['id'];
