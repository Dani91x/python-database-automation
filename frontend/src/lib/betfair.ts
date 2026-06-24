// ============================================================================
// Match Betfair — accesso alle partite Betfair del giorno e alle loro quote.
// I dati arrivano da engine_signals (riempita dal report Betfair, aggiorna_report.bat)
// via due RPC SECURITY DEFINER. Il match Betfair<->fixture e' gia' fatto a monte.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// Stessa forma della query fixture_predictions usata da MatchesList (così la lista
// le renderizza identiche, solo filtrate).
export interface BetfairFixtureRow {
    fixture_id: number;
    fixture_date: string;
    home_team_name: string | null;
    away_team_name: string | null;
    home_team_id: number | null;
    away_team_id: number | null;
    league_name: string | null;
    league_id: number | null;
    status: string | null;
}

export async function fetchBetfairFixtures(date: string): Promise<BetfairFixtureRow[]> {
    const { data, error } = await supabase.rpc('get_betfair_fixtures', { p_date: date });
    if (error) throw new Error(error.message);
    return (data ?? []) as BetfairFixtureRow[];
}

// Quote Betfair per mercato canonico: { "1x2": {"H":1.2,...}, "over_2_5": {"Over":..,"Under":..}, ... }
export type BetfairOdds = Record<string, Record<string, number>>;

export async function fetchBetfairOdds(fixtureId: string): Promise<BetfairOdds> {
    const { data, error } = await supabase.rpc('get_betfair_odds', { p_fixture_id: Number(fixtureId) });
    if (error) throw new Error(error.message);
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {};
    return data as BetfairOdds;
}

// ---------- Quote COMPLETE (tutti i mercati, back+lay 3 livelli) ----------
export interface OddLevel { price: number; size: number }
export interface BetfairRunner { selection: string; sort_priority: number | null; back: OddLevel[]; lay: OddLevel[] }
export interface BetfairMarket { market: string; runners: BetfairRunner[] }

export async function fetchBetfairFullOdds(fixtureId: string): Promise<BetfairMarket[]> {
    const { data, error } = await supabase.rpc('get_betfair_full_odds', { p_fixture_id: Number(fixtureId) });
    if (error) throw new Error(error.message);
    return (Array.isArray(data) ? data : []) as BetfairMarket[];
}

// back/lay per i 7 mercati canonici del cruscotto Direzione: { market: { selection: {back[],lay[]} } }
export type DirectionOdds = Record<string, Record<string, { back: OddLevel[]; lay: OddLevel[] }>>;

export async function fetchBetfairDirectionOdds(fixtureId: string): Promise<DirectionOdds> {
    const { data, error } = await supabase.rpc('get_betfair_direction_odds', { p_fixture_id: Number(fixtureId) });
    if (error) throw new Error(error.message);
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {};
    return data as DirectionOdds;
}
