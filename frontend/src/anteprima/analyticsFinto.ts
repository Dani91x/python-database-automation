// ============================================================================
// analyticsFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /analytics.
//
// Non e' importato dall'app: alias Vite ESATTO di '@/lib/analytics' (vedi
// AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/alias_analisi.mjs). Si
// ri-esporta TUTTO il modulo vero (percorso RELATIVO) e si ridefiniscono solo le
// letture della pagella motori (get_analytics_filters, get_analytics,
// get_analytics_rows) e del layer decisioni (get_decisions_filters,
// get_decisions), con le STESSE chiavi e tipi del vero.
// Dati: prototipo AUDIT_2026-10-01/REDESIGN/prototipo/js/s_analisi.js (5 fasce
// di confidenza, 48.211 segnali). Hit-rate, Wilson e scarto di calibrazione sono
// CALCOLATI da n/hits/prob media (stessa formula del backend: Wilson 95 %).
// Orologio dell'anteprima: 2026-10-01T08:38:00Z.
// ============================================================================
import type {
    AnalyticsFilters, AnalyticsGroup, AnalyticsQuery, AnalyticsResult, AnalyticsRow,
    DecisionGroup, DecisionsFilters, DecisionsQuery, DecisionsResult,
} from '../lib/analytics';

export * from '../lib/analytics';

const RIEPILOGO_AT = '2026-10-01T03:40:00Z';

/** gruppo della pagella da (n, hits, prob media): Wilson 95 % come il backend */
function gruppo(grp: string, n: number, hits: number, avgProb: number): AnalyticsGroup {
    const z = 1.96;
    const p = hits / n;
    const den = 1 + (z * z) / n;
    const centro = (p + (z * z) / (2 * n)) / den;
    const amp = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / den;
    return {
        grp, n, hits, hit_rate: p, avg_prob: avgProb,
        wilson_low: centro - amp, wilson_high: centro + amp, calib_gap: p - avgProb,
    };
}

// [gruppo, n, hit-rate, prob media] per ogni dimensione
type G = [string, number, number, number];
const PER_DIMENSIONE: Record<string, G[]> = {
    overall: [['Totale', 48211, 0.6979, 0.6992]],
    confidence: [
        ['50-60%', 12021, 0.572, 0.551], ['60-70%', 14330, 0.668, 0.649], ['70-80%', 11902, 0.724, 0.746],
        ['80-90%', 7210, 0.849, 0.841], ['90-100%', 2748, 0.891, 0.932],
    ],
    market: [
        ['1x2', 9640, 0.538, 0.561], ['over_1_5', 8420, 0.781, 0.772], ['over_2_5', 9810, 0.604, 0.588],
        ['over_3_5', 7215, 0.752, 0.769], ['btts', 6930, 0.559, 0.552], ['ht_1x2', 3480, 0.461, 0.489],
        ['first_half_over_0_5', 2716, 0.716, 0.702],
    ],
    engine: [
        ['poisson', 14220, 0.684, 0.676], ['ml', 13580, 0.712, 0.695], ['tacticai', 11940, 0.701, 0.718],
        ['api', 8471, 0.689, 0.712],
    ],
    selection: [
        ['over_2_5 / Under', 4920, 0.612, 0.594], ['over_2_5 / Over', 4890, 0.596, 0.582],
        ['1x2 / H', 5310, 0.571, 0.583], ['1x2 / D', 1820, 0.312, 0.304], ['1x2 / A', 2510, 0.551, 0.574],
        ['btts / Yes', 3620, 0.562, 0.551], ['btts / No', 3310, 0.556, 0.553],
    ],
    league: [
        ['Serie A', 8120, 0.704, 0.698], ['Premier League', 8840, 0.689, 0.701], ['La Liga', 7930, 0.711, 0.694],
        ['Bundesliga', 6420, 0.676, 0.689], ['Ligue 1', 6110, 0.702, 0.697], ['Serie B', 4870, 0.69, 0.703],
        ['Eredivisie', 3170, 0.684, 0.709], ['Primeira Liga', 2751, 0.719, 0.701],
    ],
};

export async function fetchAnalyticsFilters(): Promise<AnalyticsFilters> {
    return {
        engines: [
            { value: 'poisson', n: 14220 }, { value: 'ml', n: 13580 }, { value: 'tacticai', n: 11940 }, { value: 'api', n: 8471 },
        ],
        markets: PER_DIMENSIONE.market.map(([value, n]) => ({ value, n })),
        leagues: [
            { id: 135, name: 'Serie A', n: 8120 }, { id: 39, name: 'Premier League', n: 8840 },
            { id: 140, name: 'La Liga', n: 7930 }, { id: 78, name: 'Bundesliga', n: 6420 },
            { id: 61, name: 'Ligue 1', n: 6110 }, { id: 136, name: 'Serie B', n: 4870 },
            { id: 88, name: 'Eredivisie', n: 3170 }, { id: 94, name: 'Primeira Liga', n: 2751 },
        ],
        seasons: [2026, 2025, 2024],
        total_settled: 48211,
        fonte_dati: 'riepilogo',
        riepilogo_at: RIEPILOGO_AT,
    };
}

export async function fetchAnalytics(q: AnalyticsQuery): Promise<AnalyticsResult> {
    const dim = q.groupBy ?? 'overall';
    const righe = PER_DIMENSIONE[dim] ?? PER_DIMENSIONE.overall;
    return {
        group_by: dim,
        z: 1.96,
        groups: righe.map(([grp, n, hr, prob]) => gruppo(grp, n, Math.round(n * hr), prob)),
        fonte_dati: 'riepilogo',
        riepilogo_at: RIEPILOGO_AT,
    };
}

type R = [string, string, string, string, string, string, string, number, boolean, string, number];
// [motore, lega, casa, ospite, kickoff, mercato, selezione, prob, esito, risultato, minuto 1 gol]
const PARTITE: R[] = [
    ['ml', 'Serie A', 'Inter', 'Torino', '2026-09-21T18:45:00Z', 'over_2_5', 'Over', 0.64, true, '3-1', 12],
    ['poisson', 'Premier League', 'Brentford', 'Fulham', '2026-09-20T14:00:00Z', 'over_2_5', 'Over', 0.61, false, '1-0', 55],
    ['tacticai', 'La Liga', 'Real Betis', 'Getafe', '2026-09-20T16:15:00Z', '1x2', 'H', 0.66, true, '2-0', 23],
    ['ml', 'Serie A', 'Napoli', 'Lazio', '2026-09-14T16:00:00Z', 'btts', 'Yes', 0.62, true, '2-1', 31],
    ['api', 'Bundesliga', 'Mainz', 'Freiburg', '2026-09-13T13:30:00Z', '1x2', 'H', 0.63, false, '0-0', 0],
    ['poisson', 'Serie A', 'Atalanta', 'Genoa', '2026-09-13T16:00:00Z', 'over_1_5', 'Over', 0.68, true, '3-1', 8],
    ['ml', 'Ligue 1', 'Lens', 'Nantes', '2026-09-12T19:00:00Z', 'over_2_5', 'Under', 0.65, true, '1-0', 64],
    ['tacticai', 'Eredivisie', 'Feyenoord', 'AZ Alkmaar', '2026-09-07T12:30:00Z', 'btts', 'Yes', 0.61, true, '2-2', 19],
];

export async function fetchAnalyticsRows(_q: AnalyticsQuery, limit = 100): Promise<AnalyticsRow[]> {
    return PARTITE.slice(0, limit).map(([engine, league_name, home_team, away_team, kickoff, market, selection, prob, hit, result, gol]) => ({
        engine, league_name, home_team, away_team, kickoff, market, selection, prob, hit, result,
        freq_baseline: 0.524, freq_current: 0.561, freq_deviation: 0.037, delay_current: 3,
        first_goal_minute: gol > 0 ? gol : null,
    }));
}

// ------------------------------------------------------------------ layer decisioni

type D = [string, number, number, number, number, number, number, number, number, number];
// [gruppo, n, piazzate, scartate, no_signal, settlate, vinte, stake, pnl, edge medio]
const DECISIONI: D[] = [
    ['omega_value', 1842, 412, 1206, 224, 398, 231, 4120, 186.4, 0.052],
    ['safe_ladder', 966, 288, 590, 88, 281, 214, 2880, 61.2, 0.031],
    ['mike_under', 724, 351, 302, 71, 344, 318, 3510, 47.8, 0.024],
    ['direzione_api', 410, 0, 0, 410, 0, 0, 0, 0, 0],
];

export async function fetchDecisionsFilters(): Promise<DecisionsFilters> {
    return {
        logics: DECISIONI.map(([value, n]) => ({ value, n })),
        statuses: [{ value: 'placed', n: 1051 }, { value: 'rejected', n: 2098 }, { value: 'no_signal', n: 793 }],
        engines: [{ value: 'poisson', n: 1420 }, { value: 'ml', n: 1310 }, { value: 'tacticai', n: 702 }, { value: 'api', n: 510 }],
        markets: [{ value: 'over_2_5', n: 1640 }, { value: '1x2', n: 1210 }, { value: 'btts', n: 1092 }],
        rejects: [{ value: 'quota_bassa', n: 912 }, { value: 'edge_insufficiente', n: 744 }, { value: 'liquidita', n: 442 }],
        total: 3942,
        fonte_dati: 'riepilogo',
        riepilogo_at: RIEPILOGO_AT,
    };
}

export async function fetchDecisions(q: DecisionsQuery): Promise<DecisionsResult> {
    const groups: DecisionGroup[] = DECISIONI.map(([grp, n, placed, rejected, no_signal, settled, hits, stake, pnl, edge]) => ({
        grp, n, placed, rejected, no_signal, settled_placed: settled, hits, stake, pnl,
        hit_rate: settled ? hits / settled : null,
        roi: stake ? pnl / stake : null,
        avg_edge: placed ? edge : null,
        avg_odds: placed ? 1.94 : null,
        avg_prob: placed ? 0.58 : null,
    }));
    return { group_by: q.groupBy ?? 'logic', groups, fonte_dati: 'riepilogo', riepilogo_at: RIEPILOGO_AT };
}
