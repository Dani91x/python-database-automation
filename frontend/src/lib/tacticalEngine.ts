// ============================================================================
// Tactical Engine (GSG) — terzo motore INDIPENDENTE ispirato a TacticAI.
// Forze attacco/difesa INFERITE per massima verosimiglianza (Dixon-Coles) +
// simmetria casa/trasferta (Z2) + time-decay. Predizioni leakage-free.
//
// I dati sono letti dal DATABASE Supabase (colonna `tactical_engine_json` della
// tabella `fixture_predictions`), esattamente come fa il PoissonPanel con
// `db_json_analisi`. Stesso client, stesso pattern di fetch.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

export interface TEStrength {
    att: number;          // >1 = attacco sopra la media torneo
    def_factor: number;   // <1 = difesa solida (subisce meno della media)
}

export interface TEMarkets {
    home: number; draw: number; away: number;
    double_1x: number; double_12: number; double_x2: number;
    over_0_5: number; over_1_5: number; over_2_5: number; over_3_5: number;
    under_0_5: number; under_1_5: number; under_2_5: number; under_3_5: number;
    btts_yes: number; btts_no: number;
}

export interface TEFixture {
    engine_version: string;
    method: string;
    generated_at: string;
    league_name: string;
    fixture_id: number;
    season_year: number | null;
    date: string;
    status: string;
    home_name: string;
    away_name: string;
    neutral: boolean;
    exp_goals_home: number;
    exp_goals_away: number;
    lambda_home: number;
    lambda_away: number;
    markets: TEMarkets;
    markets_ht: TEMarkets | null;
    top_scores: { h: number; a: number; p: number }[];
    strength_home: TEStrength;
    strength_away: TEStrength;
    training: {
        n_matches: number; eff_matches: number; converged: boolean;
        rho: number; half_life_days: number; ridge: number;
    };
    actual: { home_goals: number; away_goals: number; outcome: string } | null;
    predicted_correct_1x2: boolean | null;
}

/** Predizione per una fixture letta dal DB, o null se il motore non l'ha prodotta
 *  (storico precedente insufficiente / squadra mai vista / colonna vuota). */
export async function fetchTacticalEngine(fixtureId: string | number): Promise<TEFixture | null> {
    const { data, error } = await supabase
        .from('fixture_predictions')
        .select('tactical_engine_json')
        .eq('fixture_id', fixtureId)
        .maybeSingle();
    if (error) throw error;
    const v = (data as any)?.tactical_engine_json;
    return v ? (typeof v === 'string' ? JSON.parse(v) : v) as TEFixture : null;
}

/** Consiglio sintetico PARLANTE, basato sui segnali piu' forti (onesto: probabilita'). */
export function buildAdvice(f: TEFixture): string {
    const m = f.markets;
    const home = f.home_name, away = f.away_name;
    const parts: string[] = [];

    const outcomes: [string, number, string][] = [
        ['1', m.home, `vittoria ${home}`],
        ['X', m.draw, 'pareggio'],
        ['2', m.away, `vittoria ${away}`],
    ];
    outcomes.sort((a, b) => b[1] - a[1]);
    const [bestKey, bestP, bestLabel] = outcomes[0];
    const conf = bestP >= 0.65 ? 'nettamente favorita' : bestP >= 0.5 ? 'favorita'
        : bestP >= 0.4 ? 'leggermente favorita' : 'esito incerto';

    if (bestKey === 'X') {
        parts.push(`Esito più probabile: pareggio (${pct(bestP)}), partita equilibrata.`);
    } else {
        const squadra = bestKey === '1' ? home : away;
        parts.push(`Esito più probabile: ${bestLabel} (${pct(bestP)}) — ${squadra} ${conf}.`);
        if (bestP < 0.55) {
            if (bestKey === '1') parts.push(`Rete di sicurezza: 1X ${pct(m.double_1x)}.`);
            else parts.push(`Rete di sicurezza: X2 ${pct(m.double_x2)}.`);
        }
    }
    if (m.over_2_5 >= 0.58) parts.push(`Tendenza gol: Over 2.5 (${pct(m.over_2_5)}), match aperto.`);
    else if (m.under_2_5 >= 0.58) parts.push(`Tendenza gol: Under 2.5 (${pct(m.under_2_5)}), match chiuso.`);
    else parts.push(`Linea gol equilibrata (Over 2.5 ${pct(m.over_2_5)}).`);

    if (m.btts_yes >= 0.55) parts.push(`Entrambe a segno: Sì (${pct(m.btts_yes)}).`);
    else if (m.btts_no >= 0.58) parts.push(`Entrambe a segno: No (${pct(m.btts_no)}).`);

    return parts.join(' ');
}

function pct(v: number): string {
    return `${Math.round(v * 100)}%`;
}
