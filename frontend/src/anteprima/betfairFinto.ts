// ============================================================================
// betfairFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA (/dashboard «Match Betfair»,
// /watchlist ordini piazzati).
//
// Non e' importato dall'app: alias Vite ESATTO di '@/lib/betfair' (vedi
// AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/alias_analisi.mjs). Si
// ri-esporta TUTTO il modulo vero (percorso RELATIVO) e si ridefiniscono solo due
// letture: get_betfair_fixtures (partite Betfair di oggi) e get_betfair_orders
// (ordini reali piazzati per fixture), con le STESSE chiavi e tipi del vero.
// Le scritture (placeBetfairOrder, refreshBetfairOdds) restano quelle vere.
// Dati: il palinsesto calcio del prototipo (AUDIT_2026-10-01/REDESIGN/prototipo/js/data.js).
// Orologio dell'anteprima: 2026-10-01T08:38:00Z (10:38 a Roma).
// ============================================================================
import type { BetfairFixtureRow, PlacedOrder } from '../lib/betfair';
import { FX } from './watchlistFinto';

export * from '../lib/betfair';

type P = [number, string, string, string, number, number, string, number];
// [fixture, ora UTC, casa, ospite, id casa, id ospite, lega, id lega]
const PALINSESTO: P[] = [
    [1378123, '07:25', 'Inter', 'Torino', 505, 503, 'Serie A', 135],
    [1390457, '08:07', 'Real Betis', 'Getafe', 543, 546, 'La Liga', 140],
    [FX.bologna, '08:52', 'Bologna', 'Udinese', 500, 494, 'Serie A', 135],
    [FX.brentford, '09:22', 'Brentford', 'Fulham', 55, 36, 'Premier League', 39],
    [FX.lens, '09:52', 'Lens', 'Nantes', 116, 83, 'Ligue 1', 61],
    [1378190, '10:22', 'Atalanta', 'Genoa', 499, 495, 'Serie A', 135],
    [FX.feyenoord, '10:52', 'Feyenoord', 'AZ Alkmaar', 209, 201, 'Eredivisie', 88],
    [FX.benfica, '11:52', 'Benfica', 'Braga', 211, 217, 'Primeira Liga', 94],
    [1378262, '12:52', 'Napoli', 'Lazio', 492, 487, 'Serie A', 135],
    [1379301, '14:00', 'Arsenal', 'Newcastle', 42, 34, 'Premier League', 39],
    [1390512, '16:30', 'Sevilla', 'Valencia', 536, 532, 'La Liga', 140],
    [1382044, '17:45', 'Bayer Leverkusen', 'Mainz', 168, 164, 'Bundesliga', 78],
];

export async function fetchBetfairFixtures(date: string): Promise<BetfairFixtureRow[]> {
    if (date !== '2026-10-01') return [];
    return PALINSESTO.map(([fixture_id, ora, casa, ospite, hid, aid, lega, lid]) => ({
        fixture_id,
        fixture_date: `2026-10-01T${ora}:00+00:00`,
        home_team_name: casa,
        away_team_name: ospite,
        home_team_id: hid,
        away_team_id: aid,
        league_name: lega,
        league_id: lid,
        status: 'ok',
    }));
}

/** ordini reali piazzati dalla watchlist: Napoli-Lazio (giocata, 2 ordini) */
const ORDINI: Record<number, PlacedOrder[]> = {
    [FX.napoli]: [
        {
            id: 912, market: 'over_2_5', selection: 'Under', side: 'back', price: 1.92, size: 10, liability: null,
            persistence: 'LAPSE', fill_or_kill: false, status: 'done',
            result: {
                ok: true, status: 'SUCCESS', error_code: null, instruction_status: 'SUCCESS',
                order_status: 'EXECUTION_COMPLETE', bet_id: '3.2211904', placed_date: '2026-09-30T16:14:08Z',
                size_matched: 10, average_price_matched: 1.92, size_remaining: 0,
                fixture_id: FX.napoli, market: 'over_2_5', selection: 'Under', side: 'back',
                market_id: '1.247990412', market_name: 'Over/Under 2.5 Goals', runner: 'Under 2.5 Goals',
            },
            error: null, requested_at: '2026-09-30T16:14:06Z', processed_at: '2026-09-30T16:14:08Z',
        },
        {
            id: 913, market: '1x2', selection: 'H', side: 'back', price: 1.95, size: 5, liability: null,
            persistence: 'LAPSE', fill_or_kill: false, status: 'done',
            result: {
                ok: true, status: 'SUCCESS', error_code: null, instruction_status: 'SUCCESS',
                order_status: 'EXECUTABLE', bet_id: '3.2211931', placed_date: '2026-09-30T16:15:40Z',
                size_matched: 3.2, average_price_matched: 1.95, size_remaining: 1.8,
                fixture_id: FX.napoli, market: '1x2', selection: 'H', side: 'back',
                market_id: '1.247990410', market_name: 'Match Odds', runner: 'Napoli',
            },
            error: null, requested_at: '2026-09-30T16:15:38Z', processed_at: '2026-09-30T16:15:40Z',
        },
    ],
};

export async function fetchBetfairOrders(fixtureId: number): Promise<PlacedOrder[]> {
    return (ORDINI[fixtureId] ?? []).map((o) => ({ ...o }));
}
