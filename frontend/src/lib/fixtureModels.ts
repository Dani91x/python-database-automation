// ============================================================================
// Dati per-partita dei due motori, letti da fixture_predictions:
//  - Poisson  -> colonna db_json_analisi      (model 'poisson_xg_hybrid_dc')
//  - ML        -> colonna model_predictions_json (ensemble_v2)
// Solo fetch + tipi + helper. NESSUNA dipendenza da MarketFrequencyPanel.tsx.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ---------------------------------------------------------------- Poisson
export interface PoissonData {
    model?: string;
    generated_at?: string;
    league_id?: number;
    season_year?: number;
    fixture_id?: number;
    inputs?: Record<string, any>;
    markets?: Record<string, Record<string, any>>;
    coverage?: Record<string, any>;
}

// ---------------------------------------------------------------- ML
export interface MLBetSignal {
    market?: string;
    action?: string;
    model_prob?: number;
    implied_prob?: number;
    decimal_odds?: number;
    expected_value?: number;
    kelly_fraction?: number;
    kelly_stake?: number;
    edge?: number;
    confidence_grade?: string;
    gates_passed?: boolean;
}
export interface MLData {
    schema_version?: string;
    model_name?: string;
    generated_at?: string;
    run_id?: string;
    targets?: Record<string, Record<string, number>>;
    targets_raw?: Record<string, Record<string, number>>;
    targets_model_calibrated?: Record<string, Record<string, number>>;
    ensemble_agreement?: Record<string, { votes?: Record<string, string>; agreement_ratio?: number; predicted_class?: string }>;
    calibration_metrics?: Record<string, { brier?: number; ece?: number }>;
    reliability?: { alpha?: number; grade?: string; score?: number; reason?: string };
    coverage?: { features_pct?: number; matches_home?: number; matches_away?: number; detail?: string };
    bet_signals?: MLBetSignal[];
    no_bet_reasons?: { target?: string; reason?: string }[];
    targets_not_reliable?: { target?: string; reason?: string }[];
    targets_skipped?: { target?: string; reason?: string }[];
}

// JSONB torna gia' come oggetto da supabase-js, ma siamo robusti anche su stringa.
function asObj(v: any): any | null {
    if (v === null || v === undefined) return null;
    if (typeof v === 'string') {
        try { return JSON.parse(v); } catch { return null; }
    }
    if (typeof v === 'object') return v;
    return null;
}

export async function fetchPoisson(fixtureId: string): Promise<PoissonData | null> {
    const { data, error } = await supabase
        .from('fixture_predictions')
        .select('db_json_analisi')
        .eq('fixture_id', fixtureId)
        .maybeSingle();
    if (error) throw error;
    return asObj(data?.db_json_analisi);
}

export async function fetchML(fixtureId: string): Promise<MLData | null> {
    const { data, error } = await supabase
        .from('fixture_predictions')
        .select('model_predictions_json')
        .eq('fixture_id', fixtureId)
        .maybeSingle();
    if (error) throw error;
    return asObj(data?.model_predictions_json);
}

// ---------------------------------------------------------------- formato
export const pctFmt = (v: number | null | undefined, d = 1) =>
    v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`;

export const numFmt = (v: number | null | undefined, d = 2) =>
    v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d);

// palette coerente col design system
export const COL = {
    green: 'hsl(155 84% 42%)',
    amber: '#f59e0b',
    gray: '#94a3b8',
    blue: '#60a5fa',
};

// colore per selezione (1/X/2, Over/Under, Si/No, True/False)
export function colorForSelection(key: string): string {
    const k = key.toUpperCase();
    if (['H', 'TRUE', 'OVER', 'SI', 'SÌ', 'YES', '1'].includes(k)) return COL.green;
    if (['A', 'FALSE', 'UNDER', 'NO', '2'].includes(k)) return COL.amber;
    if (['D', 'X', 'DRAW', 'PARI'].includes(k)) return COL.gray;
    // chiavi composte HT/FT (es. H_A): colora in base all'esito FT (2° carattere)
    if (/^[HDA]_[HDA]$/.test(k)) {
        const ft = k[2];
        if (ft === 'H') return COL.green;
        if (ft === 'A') return COL.amber;
        return COL.gray;
    }
    return COL.blue;
}

// ---------------------------------------------------------------- label ML
export function mlTargetLabel(t: string): string {
    const k = t.replace(/^target_/, '');
    const fixed: Record<string, string> = {
        '1x2': '1X2 (FT)',
        'ft_1x2': '1X2 (FT)·alt',
        'ht_1x2': 'HT 1X2',
        'ht_ft': 'HT / FT',
        'btts': 'BTTS',
        'ht_over_0_5': 'HT Over 0.5',
        'goal_in_2h': 'Gol nel 2°T',
        'first_goal_before_30': "1° Gol < 30'",
        'clean_sheet_home': 'Clean Sheet Casa',
        'clean_sheet_away': 'Clean Sheet Trasf.',
        // target di conteggio (compaiono solo su fixture storiche via deep-link)
        'total_goals': 'Gol totali',
        'sot_total': 'Tiri in porta',
        'corners_total': "Calci d'angolo",
        'cards_total': 'Cartellini',
        'home_cards': 'Cartellini casa',
        'away_cards': 'Cartellini trasf.',
    };
    if (fixed[k]) return fixed[k];
    let m: RegExpMatchArray | null;
    if ((m = k.match(/^over_(\d)_(\d)$/))) return `Over ${m[1]}.${m[2]}`;
    if ((m = k.match(/^home_over_(\d)_(\d)$/))) return `Casa Over ${m[1]}.${m[2]}`;
    if ((m = k.match(/^away_over_(\d)_(\d)$/))) return `Trasf. Over ${m[1]}.${m[2]}`;
    return k.replace(/_/g, ' ');
}

export function mlClassLabel(k: string): string {
    const fixed: Record<string, string> = {
        H: '1 (Casa)', D: 'X (Pari)', A: '2 (Trasf.)',
        True: 'Sì / Over', False: 'No / Under',
    };
    if (fixed[k]) return fixed[k];
    if (/^[HDA]_[HDA]$/.test(k)) {
        const s: Record<string, string> = { H: '1', D: 'X', A: '2' };
        return `${s[k[0]]} / ${s[k[2]]}`;
    }
    return k;
}
