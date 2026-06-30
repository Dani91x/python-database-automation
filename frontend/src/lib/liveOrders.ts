// ============================================================================
// liveOrders.ts — data layer LIVE TRADING (Fase 1) per il pannello operativo.
// Mirror dello stile di betfair.ts: tutto MEDIATO DAL DATABASE (coda comandi +
// RPC SECURITY DEFINER), nessuna chiamata diretta al PC. Il worker locale nel
// runner (Betfair/stream/live_order_worker.py) processa la coda e parla con
// flumine (PAPER = SimulatedExecution, LIVE = ordini reali Betfair).
//
//   request_betfair_live_order(p jsonb) → bigint   (enqueue idempotente client_ref)
//   get_betfair_live_order(p_id bigint) → jsonb     (polling esito)
//   get_live_orders(p_market_id text)   → { rows }  (specchio ordini, sola lettura)
//   get_live_positions(p_market_id text)→ { rows }  (esposizioni/P&L, sola lettura)
//
// MONEY-CRITICAL: enqueue idempotente (client_ref UUID) → un retry NON crea un
// secondo ordine. Su timeout: NON reinviare (l'ordine potrebbe essere piazzato).
// NESSUNA UI qui.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ---------- Tipi comando (mirror betfair_live_order_requests / INTERFACES.md §4.1) ----------
export type LiveOrderMode = 'paper' | 'live';
export type LiveOrderAction = 'place' | 'cancel' | 'replace' | 'place_submin';
export type LiveOrderSide = 'back' | 'lay';
export type LiveOrderType = 'LIMIT' | 'LIMIT_ON_CLOSE' | 'MARKET_ON_CLOSE';
export type LivePersistence = 'LAPSE' | 'PERSIST' | 'MARKET_ON_CLOSE';
export type LiveTimeInForce = 'FILL_OR_KILL' | null;

export interface LiveOrderCommand {
    action: LiveOrderAction;
    mode: LiveOrderMode;
    market_id?: string;
    selection_id?: number;
    handicap?: number;
    side?: LiveOrderSide;
    order_type?: LiveOrderType;
    price?: number;                  // quota richiesta (il server arrotonda al tick)
    size?: number | null;            // stake € (back) / size (lay); alternativo a liability
    liability?: number | null;       // solo lay: size = liability/(price-1)
    persistence?: LivePersistence;
    time_in_force?: LiveTimeInForce;
    min_fill_size?: number | null;
    bet_id?: string;                 // obblig. cancel/replace
    new_price?: number;              // obblig. replace
    size_reduction?: number;         // cancel parziale / step-2 submin
    params?: Record<string, unknown>;
}

// Esito stabile scritto in betfair_live_order_requests.result (INTERFACES.md §3.3).
export interface LiveOrderResult {
    ok: boolean;
    action: string;
    mode: string;
    bet_id?: string | null;
    status?: string | null;          // OrderStatus flumine
    size_matched?: number | null;
    average_price_matched?: number | null;
    size_remaining?: number | null;
    market_id?: string | null;
    selection_id?: number | null;
    side?: string | null;
    price?: number | null;
    size?: number | null;
    customer_order_ref?: string | null;
    submin_step?: string | null;     // per action place_submin
    error?: string | null;
    detail?: string | null;
}

// ---------- Specchio ordini (mirror betfair_live_orders, INTERFACES.md §1.2) ----------
export interface LiveOrderRow {
    id: number;
    bet_id: string | null;
    client_order_ref: string | null;
    request_id: number | null;
    mode: LiveOrderMode;
    event_id: string | null;
    market_id: string;
    selection_id: number;
    handicap: number;
    side: LiveOrderSide;
    order_type: string;
    price: number | null;
    size: number | null;
    size_matched: number;
    size_remaining: number;
    size_cancelled: number;
    size_lapsed: number;
    size_voided: number;
    average_price_matched: number;
    status: string;                  // flumine OrderStatus
    persistence: string | null;
    placed_at: string | null;
    matched_at: string | null;
    updated_at: string | null;
}

// ---------- Esposizioni/P&L (mirror betfair_live_positions, INTERFACES.md §1.3) ----------
export interface LivePositionRow {
    id: number;
    mode: LiveOrderMode;
    event_id: string | null;
    market_id: string;
    selection_id: number;
    handicap: number;
    matched_if_win: number;
    matched_if_lose: number;
    worst_if_win: number;
    worst_if_lose: number;
    selection_exposure: number;
    unmatched_back_exposure: number;
    unmatched_lay_exposure: number;
    net_position: number;
    updated_at: string | null;
}

// ---------- enqueue + polling (mirror placeBetfairOrder) ----------
const LIVE_ORDER_POLL_MS = 1000;
const LIVE_ORDER_TIMEOUT_MS = 90_000;

// Invia UN comando live MEDIATO DAL DATABASE: accoda (request_betfair_live_order,
// IDEMPOTENTE su client_ref UUID) e fa polling dell'esito (get_betfair_live_order).
// Funziona da QUALUNQUE origine — anche dal sito online — perché NON chiama il PC
// direttamente: il worker locale processa la coda. Su timeout: throw "NON reinviare".
export async function sendLiveOrderCommand(cmd: LiveOrderCommand): Promise<LiveOrderResult> {
    // chiave di idempotenza STABILE: un retry dell'enqueue con lo stesso client_ref
    // NON crea un secondo comando (vincolo UNIQUE lato DB).
    const client_ref = crypto.randomUUID();

    let reqId: number | null = null;
    let lastErr = '';
    for (let i = 0; i < 3 && reqId == null; i++) {
        const { data, error } = await supabase.rpc('request_betfair_live_order', { p: { ...cmd, client_ref } });
        if (!error && data != null) { reqId = data as number; break; }
        lastErr = error?.message ?? 'accodamento non riuscito';
        await new Promise(r => setTimeout(r, 800));
    }
    if (reqId == null) throw new Error(`Comando non accodato: ${lastErr}`);

    const deadline = Date.now() + LIVE_ORDER_TIMEOUT_MS;
    while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, LIVE_ORDER_POLL_MS));
        const { data: row, error: e2 } = await supabase.rpc('get_betfair_live_order', { p_id: reqId });
        if (e2) throw new Error(e2.message);
        const req = row as { status?: string; result?: LiveOrderResult; error?: string } | null;
        if (!req) continue;
        if (req.status === 'done') {
            if (!req.result) throw new Error('Esito comando incompleto (result mancante).');
            return req.result as LiveOrderResult;
        }
        if (req.status === 'error') {
            return { ok: false, action: cmd.action, mode: cmd.mode, error: req.error ?? 'comando non eseguito' };
        }
        // 'pending'/'processing' → continua il polling
    }
    // timeout: il comando POTREBBE essere stato eseguito → NON reinviare.
    throw new Error('Esito comando non confermato (timeout): NON reinviare. Controlla la lista ordini. Il runner è attivo in modalità PAPER/LIVE?');
}

// ---------- letture per i pannelli (mirror get_live_follows) ----------
export async function fetchLiveOrders(marketId: string): Promise<LiveOrderRow[]> {
    const { data, error } = await supabase.rpc('get_live_orders', { p_market_id: marketId });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: LiveOrderRow[] } | LiveOrderRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

export async function fetchLivePositions(marketId: string): Promise<LivePositionRow[]> {
    const { data, error } = await supabase.rpc('get_live_positions', { p_market_id: marketId });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: LivePositionRow[] } | LivePositionRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// ---------- helper di legalizzazione .it (informativi: il server è autoritativo) ----------
// Specchio delle regole min_stake_rules backend, SOLO per feedback live in UI.
export function layLiabilityFromSize(size: number, price: number): number {
    if (!Number.isFinite(size) || !Number.isFinite(price) || price <= 1) return 0;
    return Math.round(size * (price - 1) * 100) / 100;
}
export function laySizeFromLiability(liability: number, price: number): number {
    if (!Number.isFinite(liability) || !Number.isFinite(price) || price <= 1) return 0;
    return Math.round((liability / (price - 1)) * 100) / 100;
}

// ---------- conferma LIVE one-shot ----------
// MONEY-CRITICAL: la spunta "Confermo ordine REALE" NON deve diventare una conferma
// permanente per la sessione. Dopo OGNI comando LIVE andato a buon fine va resettata,
// così ogni nuovo ordine LIVE richiede una nuova conferma esplicita. In PAPER (isLive
// false) non c'è conferma da resettare. Su esito negativo la spunta resta (l'invio
// non è andato a buon fine: l'utente può ritentare senza ri-confermare).
export function shouldResetLiveConfirm(isLive: boolean, ok: boolean): boolean {
    return isLive === true && ok === true;
}

// ---------- etichette IT ----------
export const LIVE_ORDER_STATUS_LABEL: Record<string, string> = {
    PENDING: 'In invio',
    EXECUTABLE: 'Sul book',
    EXECUTION_COMPLETE: 'Completato',
    EXPIRED: 'Scaduto',
    VIOLATION: 'Rifiutato',
};
