// ============================================================================
// safeBot.ts — client del BOT della sezione SAFE STRATEGY.
//
// Specchio esatto di lib/omega.ts (stesso pattern: la UI scrive stato/parametri
// e legge lo specchio DB, l'esecuzione vera è del servizio locale Betfair).
// Parla SOLO con le RPC owner-only della migrazione safe_strategy_bot.sql:
//   safe_activate / safe_stop / safe_update_params / get_safe_state /
//   get_safe_trades / safe_request.
//
// Tabelle lette in realtime: safe_strategy_control, safe_strategy_trades,
// safe_strategy_requests (UN canale 'safe-bot') e safe_strategy_opportunities
// (canale dedicato, come subscribeScanRows).
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import { DEFAULT_PARAMS, mergeParams, type SafeStrategyParams, type VariantId } from '@/lib/safeStrategy';
import {
    csSelection, htSelection,
    type CalcioScanPayload, type ScanCsSelection, type ScanOddsPair,
    type TennisScanPayload,
} from '@/lib/safeStrategyScan';

export type SafeBotStatus = 'idle' | 'running' | 'stopping' | 'stopped' | 'error';
export type SafeMode = 'paper' | 'live';
export type SafeSport = 'calcio' | 'tennis';
/** 'model' = opportunità dal modello (λ Poisson) · 'manual' = piazzato a mano */
export type SafeStrategyKind = 'base' | 'esatto' | 'punta' | 'tennis' | 'model' | 'manual';
export type SafeTradeStatus =
    | 'pending' | 'open' | 'hedged' | 'won' | 'lost' | 'void' | 'error';
export type SafeSide = 'back' | 'lay';

// ------------------------------------------------------------------- stato
export interface SafeStats {
    events_total?: number;
    signals_active?: number;
    trades_open?: number;
    open_liability?: number;
    realized_today?: number;
    realized_total?: number;
    last_cycle?: string;
}

export interface SafeControl {
    id: number;
    status: SafeBotStatus;
    mode: SafeMode;
    params: Record<string, unknown> | null;
    stats: SafeStats | null;
    error: string | null;
    started_at: string | null;
    stopped_at: string | null;
    heartbeat_at: string | null;
    updated_at?: string | null;
}

export interface SafeTrade {
    id: number;
    event_id: string;
    event_name: string | null;
    sport: SafeSport;
    strategy: SafeStrategyKind;
    market_id: string | null;
    market_type: string | null;
    selection_id: number | null;
    selection_name: string | null;
    side: SafeSide;
    mode: SafeMode;
    price: number | null;
    size: number | null;
    liability: number | null;
    commission: number | null;
    minute_at_entry: number | null;
    score_at_entry: string | null;
    status: SafeTradeStatus;
    pnl: number;
    bet_id: string | null;
    placed_at: string;
    settled_at: string | null;
    origin: 'auto' | 'manual';
    /** id del trade CHIUSO da questa riga (gamba di copertura del cash out) */
    closes_trade_id: number | null;
    /** chiave del segnale che ha generato il trade (join con ActiveSignal.key) */
    signal_key: string | null;
    meta: Record<string, unknown> | null;
}

export interface SafeAggregates {
    realized_today: number;
    realized_total: number;
    open_liability: number;
    open_count: number;
    won: number;
    lost: number;
}

export interface SafeState {
    control: SafeControl | null;
    trades: SafeTrade[];
    aggregates: SafeAggregates | null;
}

export type SafeRequestKind = 'place' | 'cashout' | 'cancel';
export interface SafeRequest {
    id: number;
    kind: SafeRequestKind;
    payload: Record<string, unknown> | null;
    status: 'pending' | 'processing' | 'done' | 'error';
    result: Record<string, unknown> | null;
    created_at: string;
    updated_at: string | null;
}

export interface SafePlacePayload {
    event_id: string;
    event_name?: string | null;
    sport: SafeSport;
    market_id: string;
    market_type?: string | null;
    selection_id: number;
    selection_name?: string | null;
    side: SafeSide;
    price: number;
    size: number;
    strategy: SafeStrategyKind;
    signal_key?: string | null;
}

// --------------------------------------------------- opportunità di modello
export interface SafeOpportunity {
    market_type: string;
    market_name: string | null;
    line: number | null;
    market_id: string;
    selection_id: number;
    selection_name: string | null;
    side: SafeSide;
    price: number;
    size_available: number | null;
    p_model: number;
    p_implied: number;
    edge: number;
    ev: number;
    confidence: number;
    rationale: string | null;
}

export interface SafeOpportunityPayload {
    minute: number | null;
    score_home: number | null;
    score_away: number | null;
    event_name?: string | null;
    lambdas?: { home?: number; away?: number } | null;
    source?: string | null;
    opps: SafeOpportunity[];
}

export interface SafeOpportunityRow {
    event_id: string;
    sport: SafeSport;
    payload: SafeOpportunityPayload;
    updated_at: string | null;
}

/** punteggio di ordinamento delle opportunità: EV pesato dalla confidenza. */
export function oppScore(o: SafeOpportunity): number {
    const ev = Number(o.ev);
    const c = Number(o.confidence);
    return (Number.isFinite(ev) ? ev : 0) * (Number.isFinite(c) ? c : 0);
}

// -------------------------------------------------------------- parametri
// I parametri del BOT vivono sul DB (safe_strategy_control.params): è la fonte
// unica quando la riga di controllo esiste. Il radar client-side continua a
// usare i suoi parametri locali (localStorage) finché il bot non c'è.
export interface SafeBotParams extends SafeStrategyParams {
    /** cadenza del loop del servizio (s) */
    poll_interval_s: number;
    /** aliquota Betfair applicata al P&L positivo (%) */
    commission_pct: number;
    /** strategie abilitate al trading automatico */
    variants: VariantId[];
    max_open_trades: number;
    max_liability_per_trade: number;
    /** size abbinabile minima richiesta = fattore × stake */
    min_size_available_factor: number;
    /** cadenza del calcolo opportunità di modello (s) */
    opps_interval_s: number;
    auto_trade_opportunities: boolean;
    opps_min_confidence: number;
    opps_min_edge: number;
    opps_stake: number;
    /** stake di default usato dal motore e proposto dalla UI sui segnali */
    stake: {
        /** € da bancare sui segnali LAY */
        laySize: number;
        /** € da puntare sui segnali BACK */
        backSize: number;
    };
}

export const SAFE_BOT_DEFAULTS: SafeBotParams = {
    ...DEFAULT_PARAMS,
    poll_interval_s: 20,
    commission_pct: 5,
    variants: ['base', 'esatto', 'punta', 'tennis'],
    max_open_trades: 5,
    max_liability_per_trade: 50,
    min_size_available_factor: 1,
    opps_interval_s: 30,
    auto_trade_opportunities: false,
    opps_min_confidence: 0.6,
    opps_min_edge: 0.02,
    opps_stake: 5,
    stake: { laySize: 2, backSize: 2 },
};

const ALL_VARIANTS: VariantId[] = ['base', 'esatto', 'punta', 'tennis'];

function num(v: unknown, fallback: number): number {
    return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}
function bool(v: unknown, fallback: boolean): boolean {
    return typeof v === 'boolean' ? v : fallback;
}

/** merge DIFENSIVO dei parametri bot: valori mancanti/malformati → default. */
export function mergeBotParams(raw: unknown): SafeBotParams {
    const r = (raw ?? {}) as Record<string, unknown>;
    const strategies = (['base', 'esatto', 'punta', 'tennis'] as const).reduce((acc, k) => {
        acc[k] = { ...DEFAULT_PARAMS[k], ...((r[k] ?? {}) as object) } as never;
        return acc;
    }, {} as SafeStrategyParams);
    const variants = Array.isArray(r.variants)
        ? (r.variants as unknown[]).filter((v): v is VariantId => ALL_VARIANTS.includes(v as VariantId))
        : SAFE_BOT_DEFAULTS.variants;
    return {
        ...strategies,
        poll_interval_s: num(r.poll_interval_s, SAFE_BOT_DEFAULTS.poll_interval_s),
        commission_pct: num(r.commission_pct, SAFE_BOT_DEFAULTS.commission_pct),
        variants: variants.length ? variants : SAFE_BOT_DEFAULTS.variants,
        max_open_trades: num(r.max_open_trades, SAFE_BOT_DEFAULTS.max_open_trades),
        max_liability_per_trade: num(r.max_liability_per_trade, SAFE_BOT_DEFAULTS.max_liability_per_trade),
        min_size_available_factor: num(r.min_size_available_factor, SAFE_BOT_DEFAULTS.min_size_available_factor),
        opps_interval_s: num(r.opps_interval_s, SAFE_BOT_DEFAULTS.opps_interval_s),
        auto_trade_opportunities: bool(r.auto_trade_opportunities, SAFE_BOT_DEFAULTS.auto_trade_opportunities),
        opps_min_confidence: num(r.opps_min_confidence, SAFE_BOT_DEFAULTS.opps_min_confidence),
        opps_min_edge: num(r.opps_min_edge, SAFE_BOT_DEFAULTS.opps_min_edge),
        opps_stake: num(r.opps_stake, SAFE_BOT_DEFAULTS.opps_stake),
        stake: {
            laySize: num((r.stake as Record<string, unknown> | undefined)?.laySize, SAFE_BOT_DEFAULTS.stake.laySize),
            backSize: num((r.stake as Record<string, unknown> | undefined)?.backSize, SAFE_BOT_DEFAULTS.stake.backSize),
        },
    };
}

/** Le SOLE condizioni di strategia (base/esatto/punta/tennis) normalizzate con
 *  `mergeParams`: chiavi ignote/null sparite, default applicati. Serve a
 *  confrontare server e radar sullo stesso piano — senza normalizzazione un
 *  payload server con una chiave in piu' non coincide MAI col locale e la
 *  sincronizzazione salva a ogni render (loop). */
export function strategyParamsOf(p: unknown): SafeStrategyParams {
    const r = (p ?? {}) as Record<string, unknown>;
    return mergeParams({ base: r.base, esatto: r.esatto, punta: r.punta, tennis: r.tennis });
}

/** true = stesse condizioni di strategia (confronto normalizzato). */
export function sameStrategyParams(a: unknown, b: unknown): boolean {
    return JSON.stringify(strategyParamsOf(a)) === JSON.stringify(strategyParamsOf(b));
}

// ------------------------------------------------------ cash out in corso
/** Cash out gia' in volo per un trade: richiesta 'cashout' pending/processing
 *  con quel trade_id, gamba di chiusura non in errore gia' scritta, oppure
 *  flag meta.hedging alzato dal servizio. Un secondo cash out sullo stesso
 *  trade raddoppierebbe la copertura: la UI deve disabilitare il bottone. */
export function cashoutInFlight(
    tradeId: number,
    requests: Pick<SafeRequest, 'kind' | 'payload' | 'status'>[],
    trades: { id: number; closes_trade_id: number | null; status: string; meta: Record<string, unknown> | null }[],
): boolean {
    for (const r of requests) {
        if (r.kind !== 'cashout') continue;
        if (r.status !== 'pending' && r.status !== 'processing') continue;
        if (Number((r.payload ?? {})['trade_id']) === tradeId) return true;
    }
    for (const t of trades) {
        if (t.closes_trade_id === tradeId && t.status !== 'error') return true;
        if (t.id === tradeId && Boolean((t.meta ?? {})['hedging'])) return true;
    }
    return false;
}

// ------------------------------------------------------- freschezza feed
/** riga del feed piu' vecchia di cosi' = quote potenzialmente non aggiornate */
export const FEED_ROW_STALE_MS = 20_000;
/** heartbeat scanner piu' vecchio di cosi' = scanner considerato NON attivo */
export const SCANNER_STALE_MS = 45_000;

export interface FeedFreshness {
    /** eta' della riga del feed (s); null = riga senza timestamp */
    ageSec: number | null;
    scannerAlive: boolean;
    /** true = riga vecchia E scanner morto: i bottoni con soldi vanno spenti.
     *  Riga vecchia con scanner vivo = write-on-change (nulla e' cambiato). */
    stale: boolean;
}

export function feedFreshness(
    rowUpdatedAt: string | null | undefined,
    scannerUpdatedAt: string | null | undefined,
    nowMs: number,
): FeedFreshness {
    const rowMs = rowUpdatedAt ? Date.parse(rowUpdatedAt) : NaN;
    const ageSec = Number.isFinite(rowMs) ? Math.max(0, Math.round((nowMs - rowMs) / 1000)) : null;
    const hbMs = scannerUpdatedAt ? Date.parse(scannerUpdatedAt) : NaN;
    const scannerAlive = Number.isFinite(hbMs) && nowMs - hbMs <= SCANNER_STALE_MS;
    const rowOld = ageSec == null || ageSec * 1000 > FEED_ROW_STALE_MS;
    return { ageSec, scannerAlive, stale: rowOld && !scannerAlive };
}

/** motivo (tooltip) per cui i bottoni con soldi sono spenti su un feed stantio */
export function staleReason(f: FeedFreshness | null | undefined): string | undefined {
    if (!f?.stale) return undefined;
    return `quote non aggiornate (${f.ageSec != null ? `${f.ageSec}s` : 'n/d'})`;
}

// -------------------------------------------------------------------- RPC
export async function activateSafe(mode: SafeMode, params?: Partial<SafeBotParams>): Promise<SafeControl> {
    const { data, error } = await supabase.rpc('safe_activate', {
        p_mode: mode, p_params: (params ?? null) as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as SafeControl;
}

export async function stopSafe(): Promise<SafeControl> {
    const { data, error } = await supabase.rpc('safe_stop', {});
    if (error) throw new Error(error.message);
    return data as unknown as SafeControl;
}

export async function updateSafeParams(params: Partial<SafeBotParams>): Promise<SafeControl> {
    const { data, error } = await supabase.rpc('safe_update_params', { p_params: params as never });
    if (error) throw new Error(error.message);
    return data as unknown as SafeControl;
}

export async function fetchSafeState(): Promise<SafeState> {
    const { data, error } = await supabase.rpc('get_safe_state', {});
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as Partial<SafeState>;
    return {
        control: d.control ?? null,
        trades: Array.isArray(d.trades) ? d.trades : [],
        aggregates: d.aggregates ?? null,
    };
}

export async function fetchSafeTrades(limit = 300): Promise<SafeTrade[]> {
    const { data, error } = await supabase.rpc('get_safe_trades', { p_limit: limit });
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as SafeTrade[];
}

/** Accoda una richiesta operativa al servizio (place / cashout / cancel). */
export async function requestSafe(
    kind: SafeRequestKind, payload: Record<string, unknown> = {},
): Promise<number> {
    const { data, error } = await supabase.rpc('safe_request', {
        p_kind: kind, p_payload: payload as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as number;
}

/** Ultime richieste (feedback pending/done/error sui bottoni "Investi"). */
export async function fetchSafeRequests(limit = 30): Promise<SafeRequest[]> {
    const { data, error } = await supabase
        .from('safe_strategy_requests')
        .select('*')
        .order('id', { ascending: false })
        .limit(limit);
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as SafeRequest[];
}

// --------------------------------------------------------------- realtime
/** UN solo canale per control + trades + requests (mai N canali). */
export function subscribeSafeBot(onChange: () => void): () => void {
    const channel = supabase
        .channel('safe-bot')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'safe_strategy_control' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'safe_strategy_trades' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'safe_strategy_requests' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(channel); };
}

export async function fetchOpportunities(): Promise<SafeOpportunityRow[]> {
    const { data, error } = await supabase.from('safe_strategy_opportunities').select('*');
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as SafeOpportunityRow[];
}

export type SafeOppEvent =
    | { type: 'upsert'; row: SafeOpportunityRow }
    | { type: 'delete'; eventId: string };

export function subscribeOpportunities(cb: (ev: SafeOppEvent) => void): () => void {
    const channel = supabase
        .channel(`safe_strategy_opportunities:${Math.random().toString(36).slice(2, 10)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'safe_strategy_opportunities' },
            (payload) => {
                if (payload.eventType === 'DELETE') {
                    const old = payload.old as { event_id?: string } | null;
                    if (old?.event_id) cb({ type: 'delete', eventId: old.event_id });
                    return;
                }
                const next = payload.new as SafeOpportunityRow | null;
                if (next && next.event_id) cb({ type: 'upsert', row: next });
            },
        )
        .subscribe();
    return () => { void supabase.removeChannel(channel); };
}

// ------------------------------------------------------------- matematica
/** Equity curve: cumulato del P&L sui trade REGOLATI, ordinati per settled_at.
 *  (stessa funzione di omega.ts, generica sul tipo di trade) */
export function buildEquitySeries(
    trades: { settled_at: string | null; status: string; pnl: number }[],
): { t: number; v: number; iso: string }[] {
    const settled = trades
        .filter((t) => t.settled_at && ['won', 'lost', 'void', 'hedged'].includes(t.status))
        .sort((a, b) => new Date(a.settled_at as string).getTime() - new Date(b.settled_at as string).getTime());
    let cum = 0;
    return settled.map((t) => {
        cum += Number(t.pnl) || 0;
        return { t: new Date(t.settled_at as string).getTime(), v: cum, iso: t.settled_at as string };
    });
}

/** Trade regolati NUOVI rispetto a `seen` (che viene aggiornato in place).
 *  Al primo caricamento memorizza lo storico e ritorna [] (niente toast). */
export function detectSettlements(
    trades: SafeTrade[], seen: Set<number>, firstLoad: boolean,
): SafeTrade[] {
    const settled = trades.filter(
        (t) => t.settled_at && ['won', 'lost', 'void', 'hedged'].includes(t.status),
    );
    if (firstLoad) {
        settled.forEach((t) => seen.add(t.id));
        return [];
    }
    const fresh: SafeTrade[] = [];
    for (const t of settled) {
        if (seen.has(t.id)) continue;
        seen.add(t.id);
        fresh.push(t);
    }
    return fresh;
}

export interface TradeExposure {
    /** P&L se la SELEZIONE vince */
    win: number;
    /** P&L se la SELEZIONE perde */
    lose: number;
}

/** Esposizione di un trade sulla SUA selezione (arrotondata ai centesimi):
 *    LAY  €S @L → vince: −S×(L−1) · perde: +S
 *    BACK €S @B → vince: +S×(B−1) · perde: −S
 *  Prezzo/size non validi → {0,0} (nessuna esposizione mostrabile). */
export function tradeExposure(
    trade: { side: string | null; price: number | null; size: number | null },
): TradeExposure {
    const price = Number(trade.price);
    const size = Number(trade.size);
    if (!Number.isFinite(price) || price <= 1 || !Number.isFinite(size) || size <= 0) {
        return { win: 0, lose: 0 };
    }
    const r2 = (x: number) => Math.round(x * 100) / 100;
    if (trade.side === 'lay') return { win: r2(-size * (price - 1)), lose: r2(size) };
    return { win: r2(size * (price - 1)), lose: r2(-size) };
}

/** Cash out limitato dalla liquidità: la gamba di chiusura è stata ridotta.
 *  Il servizio scrive meta.size_capped_from (stake richiesto) sulla riga di
 *  chiusura → la UI deve dire "parziale", mai far credere a un green pieno. */
export function cappedFrom(trade: { meta: Record<string, unknown> | null }): number | null {
    const v = Number((trade.meta ?? {})['size_capped_from']);
    return Number.isFinite(v) && v > 0 ? v : null;
}

// ------------------------------------------------------------ book LIVE
/** Ruolo Match Odds di un NOME selezione dentro il payload dello scanner.
 *  Calcio: casa / pareggio / ospite · Tennis: p1 / p2. null = nome ignoto. */
function moRole(
    payload: CalcioScanPayload | TennisScanPayload, name: string,
): ScanOddsPair | null {
    const n = norm(name);
    if (!n) return null;
    const o = payload.odds as Record<string, ScanOddsPair | null> | null;
    if (!o) return null;
    if ('home' in payload) {
        const p = payload as CalcioScanPayload;
        if (n === norm(p.home)) return o.home ?? null;
        if (n === norm(p.away)) return o.away ?? null;
        if (n === 'the draw' || n === 'draw' || n === 'pareggio') return o.draw ?? null;
        return null;
    }
    const p = payload as TennisScanPayload;
    if (n === norm(p.p1)) return o.p1 ?? null;
    if (n === norm(p.p2)) return o.p2 ?? null;
    return null;
}

/** Runner Match Odds (id + prezzi) di una selezione: prima l'override
 *  `mo_selections` se lo scanner lo pubblica, poi `odds.<lato>.selection_id`
 *  che e' quello che il feed odierno espone per calcio e tennis. */
function moRunner(
    payload: CalcioScanPayload | TennisScanPayload,
    by: { name?: string | null; selectionId?: number | null },
): ScanCsSelection | null {
    const sels = payload.mo_selections;
    if (Array.isArray(sels)) {
        const hit = sels.find((s) =>
            (by.selectionId != null && Number(s.selection_id) === Number(by.selectionId))
            || (by.name != null && norm(s.name) === norm(by.name)));
        if (hit) return hit;
    }
    if (by.name != null) {
        const pair = moRole(payload, by.name);
        if (pair) return { ...pair, selection_id: Number(pair.selection_id ?? 0), name: by.name };
    }
    if (by.selectionId != null) {
        const o = payload.odds as Record<string, ScanOddsPair | null> | null;
        for (const pair of Object.values(o ?? {})) {
            if (pair && Number(pair.selection_id) === Number(by.selectionId)) {
                return { ...pair, selection_id: Number(by.selectionId), name: null };
            }
        }
    }
    return null;
}

/** Miglior back/lay della selezione di un trade dal feed dello scanner.
 *  Copre i mercati che il feed espone: Correct Score, Half Time Score e
 *  Match Odds (calcio e tennis, id da `odds.<lato>.selection_id`).
 *  null = book non disponibile → il cash out resta disabilitato. */
export function safeTradeBook(
    trade: { market_type: string | null; selection_id: number | null; selection_name: string | null },
    payload: CalcioScanPayload | TennisScanPayload | null | undefined,
): { back: number | null; lay: number | null } | null {
    if (!payload) return null;
    const type = (trade.market_type ?? '').toUpperCase();
    if (trade.selection_id != null && 'cs' in payload) {
        const p = payload as CalcioScanPayload;
        if (type.includes('HALF_TIME_SCORE') || type === 'HT_CS') {
            const s = htSelection(p, trade.selection_id);
            if (s) return { back: s.back ?? null, lay: s.lay ?? null };
        }
        if (type.includes('CORRECT_SCORE') || type === 'CS') {
            const s = csSelection(p, trade.selection_id);
            if (s) return { back: s.back ?? null, lay: s.lay ?? null };
        }
    }
    if (type.includes('MATCH_ODDS') || type === '1X2') {
        const r = moRunner(payload, { name: trade.selection_name, selectionId: trade.selection_id });
        if (r) return { back: r.back ?? null, lay: r.lay ?? null };
    }
    return null;
}

// -------------------------------------------------- risoluzione mercato segnale
/** Coordinate di mercato con cui piazzare un segnale del radar. */
export interface SignalPlacement {
    market_id: string;
    market_type: string;
    selection_id: number;
    selection_name: string | null;
    /** best price e size ABBINABILE sul lato da operare (live) */
    price: number | null;
    size_available: number | null;
}

function norm(s: string | null | undefined): string {
    return (s ?? '').trim().toLowerCase();
}

/** Risolve market_id/selection_id di un segnale usando il feed dello scanner.
 *  · variante 'esatto' → Correct Score, selezione "Any Other Home/Away Win"
 *  · base / punta / tennis → Match Odds, id dal lato corrispondente al NOME
 *  null = il feed non espone ancora l'id: la UI mostra l'azione disabilitata,
 *  mai indovina. */
export function resolveSignalPlacement(
    signal: {
        variant: string; subId?: string; side: 'BACK' | 'LAY' | null; selection?: string | null;
    },
    payload: CalcioScanPayload | TennisScanPayload | null | undefined,
): SignalPlacement | null {
    if (!payload) return null;
    const lay = signal.side === 'LAY';
    const pick = (sel: ScanCsSelection, marketId: string, type: string): SignalPlacement | null => {
        const selectionId = Number(sel.selection_id);
        if (!Number.isFinite(selectionId) || selectionId <= 0) return null;
        return {
            market_id: marketId,
            market_type: type,
            selection_id: selectionId,
            selection_name: sel.name ?? null,
            price: (lay ? sel.lay : sel.back) ?? null,
            size_available: (lay ? sel.lay_size : sel.back_size) ?? null,
        };
    };

    if (signal.variant === 'esatto') {
        const cs = (payload as CalcioScanPayload).cs;
        const sels = cs?.selections;
        if (!cs?.market_id || !Array.isArray(sels)) return null;
        const want = signal.subId === 'away' ? /any other away/i : /any other home/i;
        const byName = signal.selection
            ? sels.find((s) => norm(s.name) === norm(signal.selection))
            : undefined;
        const sel = byName ?? sels.find((s) => want.test(s.name ?? ''));
        return sel ? pick(sel, cs.market_id, 'CORRECT_SCORE') : null;
    }

    const marketId = payload.mo_market_id;
    if (!marketId || !signal.selection) return null;
    const runner = moRunner(payload, { name: signal.selection });
    return runner ? pick(runner, marketId, 'MATCH_ODDS') : null;
}
