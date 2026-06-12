// ============================================================================
// Frequenze Mercati — tipi, catalogo mercati e accesso RPC
// La matematica vive in Postgres (RPC get_market_frequency): il client
// riceve la serie pronta e si limita al rendering.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ---------- Tipi (specchiano l'output jsonb della RPC) ----------
export interface FrequencyPoint {
    idx: number;
    fid: number;
    date: string;
    home: string;
    away: string;
    out: 0 | 1;
    mm5: number | null;
    mm10: number | null;
    mm15: number | null;
    z: number | null; // z-score MM10 vs baseline, normalizzato su se_mm10
}

export interface FrequencyMeta {
    league_id: number;
    market: string;
    selection: string;
    line: number | null;
    mode: 'last_n' | 'season' | 'all';
    season_year: number | null;
    n_requested: number | null;
    n_scope: number;      // partite settlate nell'intervallo
    n_effective: number;  // esiti validi della serie (denominatore reale)
    baseline: number | null;
    std: number | null;
    se_mm5: number | null;
    se_mm10: number | null;
    se_mm15: number | null;
    ht_coverage_pct: number | null;
    date_from: string | null;
    date_to: string | null;
}

export interface FrequencySeries {
    meta: FrequencyMeta;
    points: FrequencyPoint[];
}

export interface LeagueSeason {
    season_year: number;
    n_settled: number;
    ht_coverage_pct: number;
}

// ---------- Catalogo mercati (solo lato PUNTA, banca esclusa) ----------
export interface SelectionDef { value: string; label: string }
export interface MarketDef {
    id: string;
    label: string;
    group: 'ft' | 'ht';
    selections: SelectionDef[];
    lines?: number[];       // solo Under/Over
    defaultLine?: number;
}

const exactFtScores = [
    '0-0', '0-1', '0-2', '0-3',
    '1-0', '1-1', '1-2', '1-3',
    '2-0', '2-1', '2-2', '2-3',
    '3-0', '3-1', '3-2', '3-3',
];
const exactHtScores = ['0-0', '0-1', '0-2', '1-0', '1-1', '1-2', '2-0', '2-1', '2-2'];
const htFtCombos = ['1-1', '1-X', '1-2', 'X-1', 'X-X', 'X-2', '2-1', '2-X', '2-2'];

export const MARKETS: MarketDef[] = [
    {
        id: '1x2', label: 'Esito Finale 1X2', group: 'ft',
        selections: [{ value: '1', label: '1' }, { value: 'X', label: 'X' }, { value: '2', label: '2' }],
    },
    {
        id: 'dc', label: 'Doppia Chance', group: 'ft',
        selections: [{ value: '1X', label: '1X' }, { value: 'X2', label: 'X2' }, { value: '12', label: '12' }],
    },
    {
        id: 'dnb', label: 'Draw No Bet', group: 'ft',
        selections: [{ value: '1', label: '1' }, { value: '2', label: '2' }],
    },
    {
        id: 'ou_ft', label: 'Under/Over', group: 'ft',
        selections: [{ value: 'over', label: 'Over' }, { value: 'under', label: 'Under' }],
        lines: [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5], defaultLine: 2.5,
    },
    {
        id: 'btts', label: 'Entrambe Segnano (GG/NG)', group: 'ft',
        selections: [{ value: 'yes', label: 'Si (GG)' }, { value: 'no', label: 'No (NG)' }],
    },
    {
        id: 'home_scores', label: 'Squadra Casa segna', group: 'ft',
        selections: [{ value: 'yes', label: 'Si' }, { value: 'no', label: 'No' }],
    },
    {
        id: 'away_scores', label: 'Squadra Trasferta segna', group: 'ft',
        selections: [{ value: 'yes', label: 'Si' }, { value: 'no', label: 'No' }],
    },
    {
        id: 'exact_ft', label: 'Risultato Esatto', group: 'ft',
        selections: [
            ...exactFtScores.map(s => ({ value: s, label: s })),
            { value: 'other_home', label: 'Altro Casa' },
            { value: 'other_away', label: 'Altro Trasf.' },
            { value: 'other_draw', label: 'Altro Pari' },
        ],
    },
    {
        id: '1x2_ht', label: 'Primo Tempo 1X2', group: 'ht',
        selections: [{ value: '1', label: '1' }, { value: 'X', label: 'X' }, { value: '2', label: '2' }],
    },
    {
        id: 'ou_ht', label: 'Under/Over Primo Tempo', group: 'ht',
        selections: [{ value: 'over', label: 'Over' }, { value: 'under', label: 'Under' }],
        lines: [0.5, 1.5, 2.5], defaultLine: 1.5,
    },
    {
        id: 'exact_ht', label: 'Risultato Esatto 1°T', group: 'ht',
        selections: [
            ...exactHtScores.map(s => ({ value: s, label: s })),
            { value: 'other', label: 'Altro' },
        ],
    },
    {
        id: 'ht_ft', label: 'Parziale/Finale', group: 'ht',
        selections: htFtCombos.map(s => ({ value: s, label: s.replace('-', '/') })),
    },
];

// Soglie del gate informativo HT (vedi report ricognizione: 100% campionati, 35% FA Cup)
export const HT_WARN_THRESHOLD = 90;  // sotto: badge ben visibile
export const HT_HARD_THRESHOLD = 50;  // sotto: mercato disabilitato con messaggio

export function formatSeason(year: number): string {
    return `${year}/${String((year + 1) % 100).padStart(2, '0')}`;
}

// ---------- Chiamate RPC ----------
export interface FrequencyParams {
    leagueId: number;
    market: string;
    selection: string;
    line?: number | null;
    mode: 'last_n' | 'season' | 'all';
    lastN?: number;
    seasonYear?: number | null;
}

export async function fetchMarketFrequency(p: FrequencyParams): Promise<FrequencySeries> {
    const { data, error } = await supabase.rpc('get_market_frequency', {
        p_league_id: p.leagueId,
        p_market: p.market,
        p_selection: p.selection,
        p_line: p.line ?? null,
        p_mode: p.mode,
        p_last_n: p.mode === 'last_n' ? (p.lastN ?? 300) : null,
        p_season_year: p.mode === 'season' ? (p.seasonYear ?? null) : null,
    });
    if (error) throw new Error(error.message);
    return data as FrequencySeries;
}

export async function fetchLeagueSeasons(leagueId: number): Promise<LeagueSeason[]> {
    const { data, error } = await supabase.rpc('get_league_seasons', { p_league_id: leagueId });
    if (error) throw new Error(error.message);
    return (data ?? []) as LeagueSeason[];
}
