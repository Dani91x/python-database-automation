// ============================================================================
// watchlistFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /watchlist.
//
// Non e' importato dall'app: alias Vite ESATTO di '@/lib/watchlist' (vedi
// AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/alias_analisi.mjs). Si
// ri-esporta TUTTO il modulo vero (percorso RELATIVO) e si ridefinisce solo la
// lettura get_watchlist, con le STESSE chiavi e gli stessi tipi del vero.
// Dati: prototipo AUDIT_2026-10-01/REDESIGN/prototipo/js/s_analisi.js (watchlist):
// Da valutare = Bologna-Udinese, Brentford-Fulham; Giocate = Napoli-Lazio (2
// ordini); Scartate = Lens-Nantes (quota bassa), piu' due per l'analisi scarti.
// Orologio dell'anteprima: 2026-10-01T08:38:00Z.
// ============================================================================
import type { SnapshotEdge, WatchlistRow, WatchlistStatus, RejectReason } from '../lib/watchlist';

export * from '../lib/watchlist';

/** id fixture (API-Football) delle partite in watchlist: usati anche da betfairFinto.ts */
export const FX = {
    bologna: 1378127, brentford: 1379240, napoli: 1378101, lens: 1381177, feyenoord: 1384215, benfica: 1385240,
} as const;

function edge(market: string, selection: string, p: number, back: number, lay: number,
    concordi: string[], aff: number): SnapshotEdge {
    const implied = 1 / back;
    return {
        market, selection, model_prob: p, best_back: back, best_lay: lay,
        implied_prob: Math.round(implied * 10000) / 10000,
        edge: Math.round((p - implied) * 10000) / 10000,
        ev_back: Math.round((p * (back - 1) * 0.95 - (1 - p)) * 1000) / 1000,
        affidabilita: aff, lift: Math.round((aff - 0.5) * 100) / 100, concordi, motori_totali: 4,
    };
}

const MERCATI_BETFAIR = [
    'MATCH_ODDS', 'OVER_UNDER_05', 'OVER_UNDER_15', 'OVER_UNDER_25', 'OVER_UNDER_35', 'OVER_UNDER_45',
    'BOTH_TEAMS_TO_SCORE', 'CORRECT_SCORE', 'HALF_TIME', 'HALF_TIME_SCORE', 'DOUBLE_CHANCE', 'DRAW_NO_BET',
    'FIRST_HALF_GOALS_05', 'FIRST_HALF_GOALS_15', 'TEAM_A_1', 'TEAM_B_1', 'ASIAN_HANDICAP', 'TOTAL_GOALS',
];

interface Partita {
    id: number; fixture: number; lega: string; leagueId: number; paese: string; casa: string; ospite: string;
    kickoff: string; stato: WatchlistStatus; follow: boolean; nTrade: number; edges: SnapshotEdge[];
    motivo?: RejectReason; notaScarto?: string; decisa?: string; strategia?: string;
}

const PARTITE: Partita[] = [
    {
        id: 41, fixture: FX.bologna, lega: 'Serie A', leagueId: 135, paese: 'Italy', casa: 'Bologna', ospite: 'Udinese',
        kickoff: '2026-10-01T08:52:00Z', stato: 'DA_VALUTARE', follow: true, nTrade: 0,
        edges: [
            edge('over_2_5', 'Under', 0.561, 1.95, 1.97, ['ml', 'poisson', 'tacticai'], 0.58),
            edge('1x2', 'H', 0.574, 1.83, 1.84, ['ml', 'api'], 0.55),
            edge('btts', 'No', 0.49, 2.1, 2.12, ['poisson'], 0.47),
        ],
    },
    {
        id: 42, fixture: FX.brentford, lega: 'Premier League', leagueId: 39, paese: 'England', casa: 'Brentford', ospite: 'Fulham',
        kickoff: '2026-10-01T09:22:00Z', stato: 'DA_VALUTARE', follow: false, nTrade: 0,
        edges: [
            edge('over_2_5', 'Over', 0.548, 1.92, 1.94, ['ml', 'poisson'], 0.56),
            edge('1x2', 'H', 0.452, 2.3, 2.32, ['api', 'tacticai'], 0.51),
        ],
    },
    {
        id: 37, fixture: FX.napoli, lega: 'Serie A', leagueId: 135, paese: 'Italy', casa: 'Napoli', ospite: 'Lazio',
        kickoff: '2026-09-30T18:45:00Z', stato: 'GIOCATA', follow: false, nTrade: 2, decisa: '2026-09-30T16:12:00Z',
        strategia: 'Back Under 2.5',
        edges: [
            edge('over_2_5', 'Under', 0.553, 1.92, 1.94, ['ml', 'poisson', 'api'], 0.6),
            edge('1x2', 'H', 0.541, 1.91, 1.92, ['ml', 'api'], 0.54),
        ],
    },
    {
        id: 43, fixture: FX.lens, lega: 'Ligue 1', leagueId: 61, paese: 'France', casa: 'Lens', ospite: 'Nantes',
        kickoff: '2026-10-01T09:52:00Z', stato: 'SCARTATA', follow: false, nTrade: 0, decisa: '2026-10-01T06:40:00Z',
        motivo: 'quota_bassa', notaScarto: 'quota sotto 1,50 sul favorito',
        edges: [edge('1x2', 'H', 0.6, 1.71, 1.72, ['ml', 'api'], 0.57)],
    },
    {
        id: 39, fixture: FX.feyenoord, lega: 'Eredivisie', leagueId: 88, paese: 'Netherlands', casa: 'Feyenoord', ospite: 'AZ Alkmaar',
        kickoff: '2026-10-01T10:52:00Z', stato: 'SCARTATA', follow: false, nTrade: 0, decisa: '2026-10-01T06:41:00Z',
        motivo: 'quota_bassa',
        edges: [edge('over_2_5', 'Over', 0.58, 1.62, 1.64, ['poisson'], 0.52)],
    },
    {
        id: 40, fixture: FX.benfica, lega: 'Primeira Liga', leagueId: 94, paese: 'Portugal', casa: 'Benfica', ospite: 'Braga',
        kickoff: '2026-10-01T11:52:00Z', stato: 'SCARTATA', follow: false, nTrade: 0, decisa: '2026-10-01T06:44:00Z',
        motivo: 'edge_insufficiente', notaScarto: 'edge sotto il 2 %',
        edges: [edge('1x2', 'H', 0.62, 1.62, 1.63, ['ml', 'api'], 0.55)],
    },
];

function riga(p: Partita): WatchlistRow {
    const consigli = [...p.edges].sort((a, b) => b.edge - a.edge).filter((e) => e.edge > 0);
    return {
        id: p.id,
        fixture_id: p.fixture,
        league_id: p.leagueId,
        league_name: p.lega,
        season_year: 2026,
        country: p.paese,
        round: 'Regular Season - 6',
        home_team: p.casa,
        away_team: p.ospite,
        kickoff: p.kickoff,
        status: p.stato,
        follow_live: p.follow,
        snapshot: {
            generated_at: '2026-10-01T06:10:00Z',
            direction: null,
            betfair: null,
            full_odds_markets: MERCATI_BETFAIR,
            edges: p.edges,
        },
        consigli,
        snapshot_at: '2026-10-01T06:10:00Z',
        user_note: null,
        strategia_ipotizzata: p.strategia ?? null,
        tags: [],
        reject_reason: p.motivo ?? null,
        reject_note: p.notaScarto ?? null,
        decided_at: p.decisa ?? null,
        created_at: '2026-10-01T06:10:00Z',
        updated_at: p.decisa ?? '2026-10-01T06:10:00Z',
        n_trades: p.nTrade,
    };
}

export async function getWatchlist(status?: WatchlistStatus | null): Promise<WatchlistRow[]> {
    return PARTITE
        .filter((p) => !status || p.stato === status)
        .sort((a, b) => a.kickoff.localeCompare(b.kickoff))
        .map(riga);
}
