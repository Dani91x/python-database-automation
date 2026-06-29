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

// ---------- Aggiorna quote ON-DEMAND (chiama Betfair via runner locale) ----------
// Esito del refresh on-demand di una singola fixture (vedi Betfair/odds_refresh.py).
export interface RefreshOddsResult {
    ok: boolean;
    fixture_id?: number;
    markets?: number;       // n. mercati riscritti
    rows?: number;          // n. righe quote riscritte
    source?: string;        // refresh | fallback_match | fallback_unmatched | ...
    reason?: string;        // motivo quando ok=false
    error?: string;         // messaggio d'errore quando ok=false
    detail?: string;
}

// URL dell'endpoint locale esposto dal runner live (Betfair/stream/odds_http.py).
// Sovrascrivibile via VITE_ODDS_REFRESH_URL; default 127.0.0.1:8787.
const ODDS_REFRESH_URL: string =
    import.meta.env.VITE_ODDS_REFRESH_URL || 'http://127.0.0.1:8787/refresh-odds';

// Forza l'aggiornamento delle quote Betfair della SOLA fixture indicata, chiamando
// il runner locale che interroga le API Betfair e riscrive betfair_market_odds.
// Solleva un Error se il runner non è raggiungibile (gestire lato chiamante).
export async function refreshBetfairOdds(fixtureId: number): Promise<RefreshOddsResult> {
    let resp: Response;
    try {
        resp = await fetch(ODDS_REFRESH_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fixture_id: Number(fixtureId) }),
            // BATCH=20 mercati × REQ_DELAY=0.6s ≈ 12s + margine: 45s evita attese infinite
            // se il runner è bloccato sul lock o Betfair è lento.
            signal: AbortSignal.timeout(45_000),
        });
    } catch (e) {
        if (e instanceof DOMException && e.name === 'TimeoutError') {
            throw new Error('Aggiornamento quote scaduto (45s): runner occupato o Betfair lento. Riprova.');
        }
        throw new Error('Runner locale non raggiungibile: avvia lo stream live per aggiornare le quote.');
    }
    const data = (await resp.json().catch(() => ({}))) as RefreshOddsResult;
    if (!resp.ok) {
        return { ...data, ok: false, error: data?.error || data?.detail || `HTTP ${resp.status}` };
    }
    return data;
}

// ---------- Piazzamento ordine REALE su Betfair (soldi veri, via runner locale) ----------
export interface PlaceOrderPayload {
    fixture_id: number;
    market: string;                 // chiave canonica snapshot (es. 'btts')
    selection: string;              // es. 'Yes' | 'Over' | 'H'
    side: 'back' | 'lay';
    price: number;                  // quota richiesta (il server arrotonda al tick)
    size?: number | null;           // stake €; in alternativa usare liability (solo lay)
    liability?: number | null;
    persistence?: 'LAPSE' | 'PERSIST' | 'MARKET_ON_CLOSE';
    fill_or_kill?: boolean;
    min_fill_size?: number | null;
    max_stake?: number | null;      // cap anti-errore (digitato dall'utente)
}

// Esito reale dell'ordine (vedi Betfair/order_exec.py → PlaceExecutionReport parsato).
export interface PlaceOrderResult {
    ok: boolean;
    status?: string;                // SUCCESS | FAILURE | PROCESSED_WITH_ERRORS | TIMEOUT
    error_code?: string | null;
    instruction_status?: string | null;
    order_status?: string | null;   // EXECUTABLE (resta sul book) | EXECUTION_COMPLETE
    bet_id?: string | null;
    placed_date?: string | null;
    size_matched?: number | null;
    average_price_matched?: number | null;
    size_remaining?: number | null;
    // contesto abbinato (conferma)
    fixture_id?: number;
    market?: string;
    selection?: string;
    side?: string;
    market_id?: string;
    market_name?: string | null;
    runner?: string | null;
    selection_id?: number;
    handicap?: number;
    price?: number;
    size?: number;
    persistence?: string;
    fill_or_kill?: boolean;
    customer_order_ref?: string;
    error?: string;
    detail?: string;
}

const ORDER_PLACE_URL: string =
    import.meta.env.VITE_ORDER_PLACE_URL || 'http://127.0.0.1:8787/place-order';

// Piazza UN ordine reale su Betfair tramite il runner locale e ritorna l'esito.
// Solleva un Error se il runner non è raggiungibile (gestire lato chiamante).
export async function placeBetfairOrder(payload: PlaceOrderPayload): Promise<PlaceOrderResult> {
    let resp: Response;
    try {
        resp = await fetch(ORDER_PLACE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(30_000),
        });
    } catch (e) {
        if (e instanceof DOMException && e.name === 'TimeoutError') {
            throw new Error('Piazzamento scaduto (30s): runner occupato o Betfair lento.');
        }
        throw new Error('Runner locale non raggiungibile: avvia lo stream live per piazzare ordini.');
    }
    const data = (await resp.json().catch(() => ({}))) as PlaceOrderResult;
    if (!resp.ok) {
        return { ...data, ok: false, error: data?.error || data?.detail || `HTTP ${resp.status}` };
    }
    return data;
}
