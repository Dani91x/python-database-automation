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

// Aggiorna quote MEDIATO DAL DATABASE (come lo stream): mette una richiesta in coda
// (request_betfair_refresh) e fa polling dell'esito (get_betfair_refresh_request).
// Funziona da QUALUNQUE origine — anche dal sito online — perché NON chiama il PC
// direttamente: il worker locale (aggiorna_quote_betfair.bat) processa la coda e
// riscrive betfair_market_odds. Lo snapshot congelato non viene mai toccato.
const REFRESH_POLL_MS = 1500;
const REFRESH_TIMEOUT_MS = 60_000;

export async function refreshBetfairOdds(fixtureId: number): Promise<RefreshOddsResult> {
    const { data: reqId, error } = await supabase.rpc('request_betfair_refresh', {
        p_fixture_id: Number(fixtureId),
    });
    if (error) throw new Error(error.message);
    if (reqId == null) throw new Error('Richiesta di aggiornamento non accodata.');

    const deadline = Date.now() + REFRESH_TIMEOUT_MS;
    while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, REFRESH_POLL_MS));
        const { data: row, error: e2 } = await supabase.rpc('get_betfair_refresh_request', { p_id: reqId });
        if (e2) throw new Error(e2.message);
        const req = row as { status?: string; result?: RefreshOddsResult; error?: string } | null;
        if (!req) continue;
        if (req.status === 'done') {
            if (!req.result) throw new Error('Risposta aggiornamento incompleta (result mancante).');
            return req.result as RefreshOddsResult;
        }
        if (req.status === 'error') {
            return { ok: false, error: req.error ?? 'errore aggiornamento quote' };
        }
    }
    throw new Error('Aggiornamento quote scaduto (60s): il server quote è attivo? Avvia "aggiorna_quote_betfair.bat".');
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

// Piazza UN ordine reale MEDIATO DAL DATABASE (come lo stream): accoda l'ordine
// (request_betfair_order, IDEMPOTENTE su client_ref) e fa polling dell'esito
// (get_betfair_order_request). Funziona da QUALUNQUE origine — anche dal sito
// online — perché NON chiama il PC direttamente: il worker locale
// (aggiorna_quote_betfair.bat) processa la coda e piazza l'ordine reale.
const ORDER_POLL_MS = 1500;
const ORDER_TIMEOUT_MS = 90_000;

export async function placeBetfairOrder(payload: PlaceOrderPayload): Promise<PlaceOrderResult> {
    // chiave di idempotenza STABILE per questa chiamata: un retry dell'enqueue con
    // lo stesso client_ref NON crea un secondo ordine (vincolo UNIQUE lato DB).
    const client_ref = crypto.randomUUID();

    let reqId: number | null = null;
    let lastErr = '';
    for (let i = 0; i < 3 && reqId == null; i++) {
        const { data, error } = await supabase.rpc('request_betfair_order', { p: { ...payload, client_ref } });
        if (!error && data != null) { reqId = data as number; break; }
        lastErr = error?.message ?? 'accodamento non riuscito';
        await new Promise(r => setTimeout(r, 800));
    }
    if (reqId == null) throw new Error(`Ordine non accodato: ${lastErr}`);

    const deadline = Date.now() + ORDER_TIMEOUT_MS;
    while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, ORDER_POLL_MS));
        const { data: row, error: e2 } = await supabase.rpc('get_betfair_order_request', { p_id: reqId });
        if (e2) throw new Error(e2.message);
        const req = row as { status?: string; result?: PlaceOrderResult; error?: string } | null;
        if (!req) continue;
        if (req.status === 'done') {
            if (!req.result) throw new Error('Esito ordine incompleto (result mancante).');
            return req.result as PlaceOrderResult;
        }
        if (req.status === 'error') {
            return { ok: false, error: req.error ?? 'ordine non piazzato' };
        }
        // 'pending'/'processing' → continua il polling
    }
    // timeout: l'ordine POTREBBE essere stato piazzato → NON reinviare.
    throw new Error('Esito ordine non confermato (timeout): NON reinviare. Controlla Report e Betfair. Il server ordini è attivo (aggiorna_quote_betfair.bat)?');
}
