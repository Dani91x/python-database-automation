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
export type LiveOrderAction = 'place' | 'cancel' | 'replace' | 'place_submin' | 'greenup' | 'dutch' | 'cashout_all' | 'cashout_event';
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
export const LIVE_ORDER_POLL_MS = 1000;
export const LIVE_ORDER_TIMEOUT_MS = 90_000;

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

// ---------- green-up / cash-out (Fase 2) ----------
// Accoda un comando 'greenup': il worker legge le esposizioni MATCHED fresche da flumine
// (blotter.get_exposures) + il best price opposto dal book e piazza l'UNICO ordine di hedge
// che pareggia profit-se-vince/perde (fraction=1 → totale; 0<fraction<1 → cash-out parziale).
// side/price/size NON sono inviati: li deriva il runner dalle esposizioni reali → niente
// numeri stantii. MONEY-CRITICAL: idempotente (client_ref), su timeout NON reinviare.
export async function sendGreenup(args: {
    marketId: string;
    selectionId: number;
    mode: LiveOrderMode;
    handicap?: number;
    fraction?: number;             // (0,1] — default 1.0 (green-up totale)
}): Promise<LiveOrderResult> {
    const f = args.fraction;
    // fraction<=0 NON è "totale": è una richiesta priva di senso. Rifiutala lato chiamante
    // (altrimenti, omettendo params, il worker farebbe un green-up TOTALE inatteso).
    if (f != null && f <= 0) throw new Error('sendGreenup: fraction deve essere > 0');
    const params = f != null && f > 0 && f < 1 ? { fraction: Math.round(f * 1000) / 1000 } : undefined;
    return sendLiveOrderCommand({
        action: 'greenup',
        mode: args.mode,
        market_id: args.marketId,
        selection_id: args.selectionId,
        handicap: args.handicap ?? 0,
        ...(params ? { params } : {}),
    });
}

// ---------- dutching (equal/variable/target) — mirror sendGreenup ----------
// Accoda un comando 'dutch': il worker calcola gli stake a PROFITTO PAREGGIATO e piazza
// OGNI gamba. Niente side/price/size al top-level: tutto dentro params (contratto backend).
// MONEY-CRITICAL: idempotente (client_ref in sendLiveOrderCommand), su timeout NON reinviare.
//
// dutchMode v2:
//   'equal'/'variable' → stake totale fisso (totalStake, obbligatorio > 0).
//   'target'           → stake derivato dal PROFITTO OBIETTIVO (targetProfit, obbligatorio > 0);
//                        il worker risolve gli stake così che ogni gamba renda targetProfit.
// pricing: come piazzare ogni gamba — 'as_given' (usa i price passati), 'best' (best price live),
//   'in_front' (un tick davanti al best), 'nominated' (usa nominatedPrice). Default lato server.
export type DutchMode = 'equal' | 'variable' | 'target';
export type DutchPricing = 'as_given' | 'best' | 'in_front' | 'nominated';
export async function sendDutch(args: {
    marketId: string;
    mode: LiveOrderMode;
    selections: { selection_id: number; price: number; weight?: number }[];
    side: LiveOrderSide;
    dutchMode: DutchMode;
    totalStake?: number;           // obblig. per 'equal'/'variable'
    targetProfit?: number;         // obblig. per 'target'
    pricing?: DutchPricing;
    nominatedPrice?: number;       // obblig. quando pricing='nominated'
    handicap?: number;
    persistence?: LivePersistence;
}): Promise<LiveOrderResult> {
    if (!args.selections || args.selections.length < 2) {
        throw new Error('sendDutch: servono almeno 2 selezioni');
    }
    const isTarget = args.dutchMode === 'target';
    if (isTarget) {
        if (!Number.isFinite(args.targetProfit) || (args.targetProfit as number) <= 0) {
            throw new Error('sendDutch: target_profit deve essere > 0 (dutchMode target)');
        }
    } else if (!Number.isFinite(args.totalStake) || (args.totalStake as number) <= 0) {
        throw new Error('sendDutch: total_stake deve essere > 0');
    }
    if (args.pricing === 'nominated' &&
        !(Number.isFinite(args.nominatedPrice) && (args.nominatedPrice as number) > 1)) {
        throw new Error('sendDutch: nominated_price deve essere > 1 quando pricing=nominated');
    }
    return sendLiveOrderCommand({
        action: 'dutch',
        mode: args.mode,
        market_id: args.marketId,
        handicap: args.handicap ?? 0,
        params: {
            selections: args.selections,
            side: args.side,
            mode: args.dutchMode,
            ...(isTarget
                ? { target_profit: args.targetProfit }
                : { total_stake: args.totalStake }),
            ...(args.pricing ? { pricing: args.pricing } : {}),
            ...(args.pricing === 'nominated' ? { nominated_price: args.nominatedPrice } : {}),
            ...(args.persistence ? { persistence: args.persistence } : {}),
        },
    });
}

// ---------- cash-out totale di mercato — mirror sendGreenup ----------
// Accoda 'cashout_all': il worker appiattisce OGNI selezione del mercato con esposizione
// aperta (greenup su ciascuna). fraction=1 → totale; 0<fraction<1 → parziale.
export async function sendCashoutAll(args: {
    marketId: string;
    mode: LiveOrderMode;
    fraction?: number;             // (0,1] — default 1.0 (cash-out totale)
}): Promise<LiveOrderResult> {
    const f = args.fraction;
    if (f != null && f <= 0) throw new Error('sendCashoutAll: fraction deve essere > 0');
    const params = f != null && f > 0 && f < 1 ? { fraction: Math.round(f * 1000) / 1000 } : undefined;
    return sendLiveOrderCommand({
        action: 'cashout_all',
        mode: args.mode,
        market_id: args.marketId,
        ...(params ? { params } : {}),
    });
}

// ---------- cash-out INTERO EVENTO (tutti i mercati) — mirror sendCashoutAll ----------
// Accoda 'cashout_event': il server DERIVA l'event_id dal market_id e appiattisce OGNI
// selezione con esposizione aperta su TUTTI i mercati dell'evento (non solo quello passato).
// Distinto da 'cashout_all' (un solo mercato). fraction=1 → totale; 0<fraction<1 → parziale.
export async function sendCashoutEvent(args: {
    marketId: string;
    mode: LiveOrderMode;
    fraction?: number;             // (0,1] — default 1.0 (cash-out totale dell'evento)
}): Promise<LiveOrderResult> {
    const f = args.fraction;
    if (f != null && f <= 0) throw new Error('sendCashoutEvent: fraction deve essere > 0');
    const params = f != null && f > 0 && f < 1 ? { fraction: Math.round(f * 1000) / 1000 } : undefined;
    return sendLiveOrderCommand({
        action: 'cashout_event',
        mode: args.mode,
        market_id: args.marketId,
        ...(params ? { params } : {}),
    });
}

// ---------- risk engine (offset / stop-loss / take-profit / trailing-stop / bracket) ----------
// 'bracket' = OCO (One-Cancels-Other): presa di profitto (offset) + stop-loss armati
// insieme; il primo che scatta annulla l'altro. Richiede un entry_bet_id (l'ordine di
// ingresso da sorvegliare): niente offset "nudo" senza un ingresso abbinato da coprire.
export type RiskRuleType = 'offset' | 'stop_loss' | 'take_profit' | 'trailing_stop' | 'bracket';
export type RiskRuleStatus = 'armed' | 'triggered' | 'cancelled' | 'done' | 'error';
// Momento di attivazione: 'immediate' arma subito; 'on_fill' aspetta l'abbinamento
// dell'ordine di ingresso (entry_bet_id) prima di sorvegliare (niente offset nudo).
export type RiskTiming = 'immediate' | 'on_fill';
// Comportamento al passaggio IN-PLAY del mercato: mantieni la regola, annullala,
// o ricalcola il riferimento (rebaseline) sul nuovo stato del book.
export type RiskOnInplay = 'keep' | 'cancel' | 'rebaseline';

// Parametri regola (jsonb.params lato backend): solo i campi pertinenti al rule_type.
export interface RiskRuleParams {
    offset_ticks?: number;
    offset_pct?: number;
    trigger_ticks?: number;
    trigger_pct?: number;
    trail_ticks?: number;
    trail_pct?: number;
    place_at_ticks?: number;       // dove piazzare l'ordine di uscita (tick dal riferimento)
    greening?: boolean;
    timing?: RiskTiming;           // 'immediate' | 'on_fill'
    on_inplay?: RiskOnInplay;      // 'keep' | 'cancel' | 'rebaseline'
    stop_amount?: number;
    target_amount?: number;
    persistence?: LivePersistence;
}

// Specchio di una riga regola (get_live_risk_rules → rows[]).
export interface RiskRuleRow {
    id: number;
    mode: LiveOrderMode;
    rule_type: RiskRuleType;
    market_id: string;
    selection_id: number;
    handicap: number | null;
    entry_side: LiveOrderSide;
    entry_price: number | null;
    entry_size: number | null;
    entry_bet_id?: string | null;
    params: RiskRuleParams | Record<string, unknown>;
    trail_extreme: number | null;
    status: RiskRuleStatus;
    enqueued_request_id: number | null;
    result: LiveOrderResult | Record<string, unknown> | null;
    error: string | null;
    created_at: string | null;
    triggered_at: string | null;
}

// entry_price è OBBLIGATORIO per offset/stop_loss/trailing_stop (contratto backend):
// serve un riferimento per calcolare target/trigger. take_profit può basarsi su P&L
// (target_amount). ECCEZIONE: con entry_bet_id o timing 'on_fill' il server deriva il
// riferimento dall'ABBINAMENTO reale dell'ordine di ingresso → entry_price non richiesto.
const RISK_RULE_ENTRY_PRICE_REQUIRED: ReadonlySet<RiskRuleType> = new Set<RiskRuleType>([
    'offset', 'stop_loss', 'trailing_stop',
]);

// Arma una regola di rischio (request_live_risk_rule → bigint id). MONEY-CRITICAL:
// client_ref UUID idempotente → un retry dell'enqueue NON crea una seconda regola.
// Ritorna l'id della regola armata.
export async function requestRiskRule(args: {
    mode: LiveOrderMode;
    ruleType: RiskRuleType;
    marketId: string;
    selectionId: number;
    handicap?: number;
    entrySide: LiveOrderSide;
    entryPrice?: number;
    entrySize?: number;
    entryBetId?: string;           // ordine di ingresso da sorvegliare (on_fill/bracket)
    params: RiskRuleParams;
}): Promise<number> {
    const timing = args.params?.timing;
    const hasEntryBet = typeof args.entryBetId === 'string' && args.entryBetId.length > 0;
    // no offset "nudo": bracket e timing 'on_fill' devono sorvegliare un ordine di ingresso.
    if ((args.ruleType === 'bracket' || timing === 'on_fill') && !hasEntryBet) {
        throw new Error(`requestRiskRule: entry_bet_id obbligatorio per '${args.ruleType}'/timing on_fill (no offset nudo)`);
    }
    // entry_price richiesto solo se il riferimento NON è derivato dall'ordine di ingresso.
    const derivesFromFill = hasEntryBet || timing === 'on_fill';
    if (RISK_RULE_ENTRY_PRICE_REQUIRED.has(args.ruleType) && !derivesFromFill &&
        !(args.entryPrice != null && Number.isFinite(args.entryPrice))) {
        throw new Error(`requestRiskRule: entry_price obbligatorio per rule_type '${args.ruleType}'`);
    }
    // chiave di idempotenza STABILE (come sendLiveOrderCommand): retry senza duplicare.
    const client_ref = crypto.randomUUID();
    const p = {
        client_ref,
        mode: args.mode,
        rule_type: args.ruleType,
        market_id: args.marketId,
        selection_id: args.selectionId,
        handicap: args.handicap ?? 0,
        entry_side: args.entrySide,
        ...(hasEntryBet ? { entry_bet_id: args.entryBetId } : {}),
        ...(args.entryPrice != null ? { entry_price: args.entryPrice } : {}),
        ...(args.entrySize != null ? { entry_size: args.entrySize } : {}),
        params: args.params,
    };

    let ruleId: number | null = null;
    let lastErr = '';
    for (let i = 0; i < 3 && ruleId == null; i++) {
        const { data, error } = await supabase.rpc('request_live_risk_rule', { p });
        if (!error && data != null) { ruleId = Number(data); break; }
        lastErr = error?.message ?? 'accodamento regola non riuscito';
        await new Promise(r => setTimeout(r, 800));
    }
    if (ruleId == null) throw new Error(`Regola non armata: ${lastErr}`);
    return ruleId;
}

// Annulla una regola armata (cancel_live_risk_rule → row). Ritorna la riga aggiornata.
export async function cancelRiskRule(id: number): Promise<RiskRuleRow | null> {
    const { data, error } = await supabase.rpc('cancel_live_risk_rule', { p_id: id });
    if (error) throw new Error(error.message);
    return (data as RiskRuleRow | null) ?? null;
}

// Legge le regole di un mercato (get_live_risk_rules → { rows }). Sola lettura.
export async function fetchRiskRules(marketId: string): Promise<RiskRuleRow[]> {
    const { data, error } = await supabase.rpc('get_live_risk_rules', { p_market_id: marketId });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: RiskRuleRow[] } | RiskRuleRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
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

// ---------- cross-market hedge (x-hedge) per EVENTO ----------
// Analisi P&L per-scoreline sull'INTERO evento (tutti i mercati correlati): quanto si
// vince/perde in ogni possibile risultato dato lo stato attuale delle esposizioni, più
// un eventuale suggerimento di copertura (una gamba che migliora il caso peggiore).
// Sola lettura: get_live_xhedge(p_event_id) → { rows: XhedgeRow[] }.
export interface XhedgeSuggestion {
    actionable: boolean;
    scoreline: [number, number] | null;
    side: 'back' | null;
    odds: number | null;
    size: number | null;
    new_worst: number;
    new_best: number;
    note: string;
}
export interface XhedgeAnalysis {
    n_positions: number;
    /** Ordini matched NON modellabili (es. "Any Other" del Correct Score) esclusi dalla
     *  griglia: > 0 ⟹ la matrice è INCOMPLETA e la UI DEVE avvisare (esposizione reale
     *  assente dai P&L mostrati). Campo assente nelle analisi pre-fix → trattare come 0. */
    ignored_orders?: number;
    summary: {
        worst: number;
        best: number;
        mean: number;
        worst_scoreline: [number, number];
        best_scoreline: [number, number];
        n_scorelines: number;
    };
    grid: Array<[number, number, number]>;   // [home, away, pnl]
    suggestion: XhedgeSuggestion | null;
}
export interface XhedgeRow {
    event_id: string;
    mode: LiveOrderMode;
    analysis: XhedgeAnalysis;
    updated_at: string;
}

// Legge l'analisi x-hedge dell'evento (get_live_xhedge → { rows }). Sola lettura.
export async function fetchXhedge(eventId: string): Promise<XhedgeRow[]> {
    const { data, error } = await supabase.rpc('get_live_xhedge', { p_event_id: eventId });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: XhedgeRow[] } | XhedgeRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// ---------- impostazioni globali runner + kill-switch (Fase 6 controlli) ----------
// Riga singleton (id=1) di configurazione LIVE del runner. kill_switch globale mediato
// dal DB: quando ON il runner NON processa alcun ordine (protezione money-critical
// valida da QUALUNQUE origine, anche dal sito online). I cap e le velocità di poll
// sono i limiti operativi; le velocità si applicano al RIAVVIO del runner.
export interface LiveSettings {
    id: number;
    kill_switch: boolean;
    max_exposure_per_selection: number | null;
    max_orders_per_min: number | null;
    order_poll_sec: number | null;
    risk_poll_sec: number | null;
    updated_at: string;
}

// Riga di audit (mirror get_live_audit → { rows }): traccia di ogni evento del runner
// (ordini, errori, kill-switch, cambi impostazioni) per il pannello di controllo.
export interface LiveAuditRow {
    id: number;
    ts: string;
    mode: string | null;
    action: string | null;
    market_id: string | null;
    selection_id: number | null;
    side: string | null;
    price: number | null;
    size: number | null;
    status: string | null;
    error: string | null;
    request_id: number | null;
    detail: unknown;
}

// Legge le impostazioni globali (get_live_settings → riga singleton). Sola lettura.
export async function getLiveSettings(): Promise<LiveSettings | null> {
    const { data, error } = await supabase.rpc('get_live_settings', {});
    if (error) throw new Error(error.message);
    return (data as LiveSettings | null) ?? null;
}

// Attiva/disattiva il kill-switch GLOBALE (set_live_kill_switch → riga aggiornata).
// MONEY-CRITICAL: ON = il runner smette di processare ordini. Ritorna lo stato nuovo.
export async function setKillSwitch(on: boolean): Promise<LiveSettings | null> {
    const { data, error } = await supabase.rpc('set_live_kill_switch', { p_on: on });
    if (error) throw new Error(error.message);
    return (data as LiveSettings | null) ?? null;
}

// Aggiorna un sottoinsieme delle impostazioni (set_live_settings → riga aggiornata).
// Accetta qualunque subset dei campi editabili; i campi omessi restano invariati.
export async function setLiveSettings(
    patch: Partial<Pick<LiveSettings,
        'kill_switch' | 'max_exposure_per_selection' | 'max_orders_per_min' | 'order_poll_sec' | 'risk_poll_sec'>>,
): Promise<LiveSettings | null> {
    const { data, error } = await supabase.rpc('set_live_settings', { p: patch });
    if (error) throw new Error(error.message);
    return (data as LiveSettings | null) ?? null;
}

// Legge gli ultimi eventi di audit (get_live_audit → { rows }). Sola lettura.
export async function fetchLiveAudit(limit = 100): Promise<LiveAuditRow[]> {
    const { data, error } = await supabase.rpc('get_live_audit', { p_limit: limit });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: LiveAuditRow[] } | null;
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
