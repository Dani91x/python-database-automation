// ============================================================================
// omega.ts — client della sezione OMEGA (Correct Score LAY, set-and-forget).
// Parla SOLO con le RPC owner-only (migrations/omega_bot.sql):
//   omega_activate / omega_stop / omega_update_params / get_omega_state / get_omega_trades.
// L'esecuzione vera avviene nel servizio locale Betfair/omega/omega_service.py
// (avvia_omega_service.bat): la UI scrive stato/parametri e legge lo specchio DB.
// Fonte di verità: Betfair/omega/COSTITUZIONE_OMEGA.md
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

export type OmegaStatus = 'idle' | 'running' | 'stopping' | 'stopped' | 'error';
export type OmegaMode = 'paper' | 'live';
/** 'hedged' = posizione chiusa a mercato (cash out / green-up): il P&L e' bloccato. */
export type OmegaTradeStatus = 'pending' | 'open' | 'hedged' | 'won' | 'lost' | 'void' | 'error';

export interface OmegaStats {
    events_total?: number;
    matches_traded?: number;
    matches_traded_today?: number;
    matches_open?: number;
    realized_profit?: number;
    realized_today?: number;   // §2: P&L regolato nella GIORNATA operativa (Europe/Rome)
    open_liability?: number;
    matches_remaining?: number;
    /** §14: gambe (1T/2T) ancora piazzabili oggi e target per gamba */
    legs_remaining?: number;
    target_match?: number;
    target_leg?: number;
    goal?: number;
    goal_pct?: number;
    last_cycle?: string;
}

export interface OmegaControl {
    id: number;
    status: OmegaStatus;
    mode: OmegaMode;
    daily_goal: number;
    params: Record<string, unknown>;
    stats: OmegaStats | null;
    error: string | null;
    started_at: string | null;
    stopped_at: string | null;
    heartbeat_at: string | null;
    updated_at: string;
}

export interface OmegaTrade {
    id: number;
    event_id: string;
    event_name: string | null;
    market_id: string | null;
    selection_id: number | null;
    runner_name: string | null;
    side: string;
    mode: OmegaMode;
    origin?: 'auto' | 'manual';  // chi ha deciso il trade (badge in tabella)
    /** gamba (v2): 1T = Half Time Score, 2T = Correct Score finale; null = trade v1/manuale senza fase */
    phase?: 'ht_cs' | 'ft_cs' | 'scalp' | null;
    price: number | null;
    size: number | null;
    liability: number | null;
    target: number | null;
    minute_at_entry: number | null;
    score_at_entry: string | null;
    kickoff: string | null;
    status: OmegaTradeStatus;
    pnl: number;
    bet_id: string | null;
    placed_at: string;
    settled_at: string | null;
    /** id del trade CHIUSO da questa riga (gamba di copertura del cash out) */
    closes_trade_id?: number | null;
    meta: Record<string, unknown>;
}

export interface OmegaAggregates {
    realized_profit: number;
    /** §14: P&L delle POSIZIONI PIAZZATE nella giornata operativa (Europe/Rome) */
    realized_today?: number;
    open_liability: number;
    matches_traded: number;
    matches_traded_today?: number;
    /** §14: gambe piazzate oggi / partite distinte di oggi / esiti di oggi */
    legs_today?: number;
    events_today?: number;
    won_today?: number;
    lost_today?: number;
    matches_open: number;
    matches_won: number;
    matches_lost: number;
}

export interface OmegaActivityRow {
    id: number;
    ts: string;
    kind: string;
    payload: Record<string, unknown>;
}

export interface OmegaState {
    control: OmegaControl | null;
    aggregates: OmegaAggregates | null;
    activity: OmegaActivityRow[];
    /** §14: obiettivo storicizzato per OGGI (null = migrazione non applicata) */
    goal_today?: number | null;
}

// ------------------------------------------------------- parametri (whitelist)
// Speculare a Betfair/omega/omega_config.py (§7 della Costituzione).
export interface OmegaParams {
    price_min: number;
    price_max: number;
    entry_minute_min: number;
    entry_minute_max: number;
    max_events: number;
    commission_pct: number;
    min_lay_liquidity: number;
    min_stake: number;
    include_aggregate: boolean;
    stop_on_goal: boolean;
    entry_window_source: 'score' | 'clock';
    poll_interval_s: number;
    max_liability_per_match: number;
    daily_loss_cap: number;
    max_open_liability: number;
    /** OMEGA v2: due gambe per partita (1T Half Time Score, 2T Correct Score), selezione per modello */
    ht_entry_min: number;
    ht_entry_max: number;
    ft_entry_min: number;
    ft_entry_max: number;
    model_p_max_pct: number;
    // ---- GREEN-UP automatico: chiude la gamba a mercato appena il risultato
    // layato diventa raggiungibile (distanza gol / crollo della quota).
    greenup_enabled: boolean;
    /** 'auto' = il servizio decide (hold/exit per P(perdita) ed EV) · 'off' = mai */
    greenup_mode: 'auto' | 'off';
    /** distanza in gol dal risultato layato che fa scattare il green-up */
    greenup_trigger_distance: number;
    /** scatta anche se la quota lay scende sotto questa frazione dell'ingresso */
    greenup_price_trigger_ratio: number;
    /** attesa di conferma del punteggio prima di agire (s) */
    greenup_settle_delay_s: number;
    /** tiene la posizione se P(perdita) ≤ (0-1) */
    greenup_hold_max_risk: number;
    /** chiude comunque se P(perdita) ≥ (0-1) */
    greenup_risk_cap: number;
    /** margine di EV richiesto per tenere (0-1) */
    greenup_ev_margin: number;
    /** incassa a questa frazione del profitto massimo (0-1) */
    greenup_take_profit_frac: number;
    /** dal minuto: incassa comunque se in profitto */
    greenup_take_profit_minute: number;
    /** residuo non abbinato: attesa fra i tentativi (s) */
    greenup_retry_s: number;
    /** residuo non abbinato: tentativi max */
    greenup_max_attempts: number;
    /** calibrazione della P(modello): 'auto' applica la curva per famiglia, 'off' usa la grezza */
    model_calibration: 'auto' | 'off';
}

/** P del modello di un trade Omega (meta.model.{p_model_raw,calibrated}) */
export interface OmegaTradeModel {
    raw: number | null;
    calibrated: number | null;
    /** true = calibrazione applicata (calibrated ≠ raw o flag esplicito) */
    applied: boolean;
}
export function tradeModelOf(t: { meta: Record<string, unknown> | null | undefined }): OmegaTradeModel | null {
    const m = (t.meta ?? {})['model'];
    if (!m || typeof m !== 'object') return null;
    const r = m as Record<string, unknown>;
    const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    // contratto del servizio (omega_model.audit_block): p_model_raw, p_model (P usata),
    // calibrated = BOOLEANO "calibratore applicato" (review LOW-5)
    const raw = n(r.p_model_raw) ?? n(r.raw);
    const calibrated = n(r.p_model) ?? n(r.calibrated);
    if (raw == null && calibrated == null) return null;
    const applied = r.calibrated === true || r.applied === true || (raw != null && calibrated != null && Math.abs(raw - calibrated) > 1e-9);
    return { raw, calibrated, applied };
}

/** attività Omega leggibile in italiano (kind → etichetta + stile) */
export const OMEGA_ACTIVITY_META: Record<string, { label: string; cls: string }> = {
    greenup: { label: 'GREEN-UP', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
    greenup_hold: { label: 'GREEN-UP · attesa', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' },
    greenup_wait: { label: 'GREEN-UP · conferma', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    greenup_retry: { label: 'GREEN-UP · ritento', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/40' },
    place: { label: 'PIAZZATO', cls: 'bg-white/5 text-slate-300 border-white/10' },
    settle: { label: 'REGOLATO', cls: 'bg-white/5 text-slate-300 border-white/10' },
    cashout: { label: 'CASH OUT', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' },
    error: { label: 'ERRORE', cls: 'bg-red-500/15 text-red-300 border-red-500/40' },
};
export function activityMeta(kind: string): { label: string; cls: string } {
    return OMEGA_ACTIVITY_META[kind] ?? { label: kind.toUpperCase(), cls: 'bg-white/5 text-slate-300 border-white/10' };
}

/** riga di attività → testo leggibile (evento, risultato, P(perdita), motivo) */
export function activityLine(row: OmegaActivityRow): string {
    const p = row.payload ?? {};
    const parts: string[] = [];
    const ev = p.event_name ?? p.event ?? null;
    if (ev) parts.push(String(ev));
    const runner = p.runner_name ?? p.selection ?? p.score ?? null;
    if (runner) parts.push(`lay ${String(runner)}`);
    const live = p.live_score ?? p.current_score ?? null;
    const minute = p.minute ?? null;
    if (live != null || minute != null) parts.push(`${minute != null ? `${minute}′` : ''}${live != null ? `${minute != null ? ' · ' : ''}${String(live)}` : ''}`);
    const pl = Number(p.p_lose);
    if (Number.isFinite(pl)) parts.push(`P(perdita) ${(pl * 100).toFixed(1).replace('.', ',')}%`);
    const locked = Number(p.locked ?? p.locked_pnl ?? p.pnl);
    if (Number.isFinite(locked)) parts.push(`${locked < 0 ? '−' : '+'}€${Math.abs(locked).toFixed(2)}`);
    const reason = p.reason ?? p.exit_reason ?? p.message ?? null;
    if (reason) parts.push(String(reason));
    const attempt = p.attempt ?? null;
    if (attempt != null) parts.push(`tentativo ${String(attempt)}${p.max_attempts != null ? `/${String(p.max_attempts)}` : ''}`);
    return parts.join(' · ');
}

/** Etichetta della gamba di un trade (v2). */
export function phaseLabel(phase: OmegaTrade['phase'] | undefined): string {
    return phase === 'ht_cs' ? '1T' : phase === 'ft_cs' ? '2T' : phase === 'scalp' ? 'SCALP' : '—';
}

export const OMEGA_PARAM_DEFAULTS: OmegaParams = {
    price_min: 20,
    price_max: 120,
    entry_minute_min: 30,
    entry_minute_max: 60,
    max_events: 0,
    commission_pct: 5,
    min_lay_liquidity: 5,
    min_stake: 0.5,
    include_aggregate: false,
    stop_on_goal: true,
    entry_window_source: 'score',
    poll_interval_s: 20,
    max_liability_per_match: 0,
    daily_loss_cap: 0,
    max_open_liability: 0,
    ht_entry_min: 20,
    ht_entry_max: 40,
    ft_entry_min: 50,
    ft_entry_max: 80,
    model_p_max_pct: 2,
    greenup_enabled: true,
    greenup_mode: 'auto',
    greenup_trigger_distance: 1,
    greenup_price_trigger_ratio: 0.5,
    greenup_settle_delay_s: 30,
    greenup_hold_max_risk: 0.02,
    greenup_risk_cap: 0.10,
    greenup_ev_margin: 0.10,
    greenup_take_profit_frac: 0.9,
    greenup_take_profit_minute: 80,
    greenup_retry_s: 20,
    greenup_max_attempts: 15,
    model_calibration: 'auto',
};

/** campi numerici della sezione "Green-up automatico" (ordine di lettura) */
export const OMEGA_GREENUP_FIELDS: {
    key: OmegaNumericParamKey; label: string; step: number; min: number; max: number; hint: string;
}[] = [
    { key: 'greenup_trigger_distance', label: 'Scatta a distanza (gol)', step: 1, min: 0, max: 5, hint: '1 = appena manca UN gol al risultato layato (es. lay 2-1 e si va sul 2-0) si chiude a mercato' },
    { key: 'greenup_price_trigger_ratio', label: 'Scatta se la quota scende sotto (frazione)', step: 0.05, min: 0.05, max: 1, hint: '0.5 = quota lay dimezzata rispetto all’ingresso: il mercato sta convergendo sul risultato, meglio uscire' },
    { key: 'greenup_settle_delay_s', label: 'Attesa conferma punteggio (s)', step: 5, min: 0, max: 300, hint: 'VAR e correzioni: aspetta che il punteggio sia stabile prima di chiudere' },
    { key: 'greenup_hold_max_risk', label: 'Tieni se P(perdita) ≤ (0-1)', step: 0.005, min: 0, max: 1, hint: 'sotto questa probabilità di perdita il servizio TIENE (attività "GREEN-UP · attesa")' },
    { key: 'greenup_risk_cap', label: 'Chiudi comunque se P(perdita) ≥ (0-1)', step: 0.01, min: 0, max: 1, hint: 'oltre questa soglia si chiude anche con EV a favore' },
    { key: 'greenup_ev_margin', label: 'Margine EV per tenere (0-1)', step: 0.01, min: 0, max: 1, hint: 'tenere deve valere almeno questo margine rispetto al green-up immediato' },
    { key: 'greenup_take_profit_frac', label: 'Incassa a frazione del max (0-1)', step: 0.05, min: 0, max: 1, hint: '0.9 = chiude quando ha in mano il 90% del profitto massimo' },
    { key: 'greenup_take_profit_minute', label: 'Incassa comunque dal minuto', step: 1, min: 0, max: 130, hint: 'in profitto e oltre questo minuto: si chiude senza aspettare' },
    { key: 'greenup_retry_s', label: 'Residuo · attesa fra tentativi (s)', step: 5, min: 1, max: 600, hint: 'chiusura parziale (liquidità): riprova ogni tot secondi (attività "ritento")' },
    { key: 'greenup_max_attempts', label: 'Residuo · tentativi max', step: 1, min: 1, max: 100, hint: 'poi il residuo si chiude al prezzo disponibile' },
];

export type OmegaNumericParamKey = {
    [K in keyof OmegaParams]: OmegaParams[K] extends number ? K : never;
}[keyof OmegaParams];

export const OMEGA_PARAM_FIELDS: {
    key: OmegaNumericParamKey; label: string; step: number; min: number; max: number; hint: string;
}[] = [
    { key: 'price_min', label: 'Quota lay MIN', step: 1, min: 1.01, max: 1000, hint: 'sotto: risultato troppo probabile' },
    { key: 'price_max', label: 'Quota lay MAX', step: 5, min: 1.01, max: 1000, hint: 'sopra: profit irrisorio / liability enorme (niente 600)' },
    { key: 'ht_entry_min', label: 'Gamba 1T: minuto MIN', step: 1, min: 0, max: 45, hint: 'Half Time Score: ingresso dal minuto reale (feed)' },
    { key: 'ht_entry_max', label: 'Gamba 1T: minuto MAX', step: 1, min: 0, max: 45, hint: 'niente 1T dopo questo minuto' },
    { key: 'ft_entry_min', label: 'Gamba 2T: minuto MIN', step: 1, min: 45, max: 130, hint: 'Correct Score finale: ingresso nel 2T' },
    { key: 'ft_entry_max', label: 'Gamba 2T: minuto MAX', step: 1, min: 45, max: 130, hint: 'niente 2T dopo questo minuto' },
    { key: 'model_p_max_pct', label: 'P(modello) MAX %', step: 0.5, min: 0.01, max: 50, hint: 'lay solo risultati che il modello dà sotto questa probabilità' },
    { key: 'entry_minute_min', label: 'v1: minuto MIN', step: 1, min: 0, max: 130, hint: 'solo motore v1 (una gamba)' },
    { key: 'entry_minute_max', label: 'v1: minuto MAX', step: 1, min: 0, max: 130, hint: 'solo motore v1 (una gamba)' },
    { key: 'max_events', label: 'Max eventi/giorno', step: 1, min: 0, max: 1000, hint: '0 = illimitato' },
    { key: 'commission_pct', label: 'Commissione %', step: 0.5, min: 0, max: 20, hint: 'aliquota Betfair (default 5%)' },
    { key: 'min_lay_liquidity', label: 'Liquidità lay MIN €', step: 1, min: 0, max: 100000, hint: 'size minima disponibile al best' },
    { key: 'min_stake', label: 'Stake MIN €', step: 0.5, min: 0.5, max: 1000, hint: 'lay minimo .it = €0.50' },
    { key: 'poll_interval_s', label: 'Cadenza loop (s)', step: 5, min: 5, max: 600, hint: 'ogni quanto scansiona' },
    { key: 'max_liability_per_match', label: 'Cap liability/match €', step: 10, min: 0, max: 1000000, hint: '0 = OFF (set-and-forget)' },
    { key: 'daily_loss_cap', label: 'Stop-loss giornaliero €', step: 25, min: 0, max: 1000000, hint: '0 = OFF' },
    { key: 'max_open_liability', label: 'Cap liability aperta €', step: 100, min: 0, max: 10000000, hint: '0 = OFF' },
];

// --------------------------------------------------------------------- RPC
export async function activateOmega(
    mode: OmegaMode, dailyGoal: number, params: Partial<OmegaParams>,
): Promise<OmegaControl> {
    const { data, error } = await supabase.rpc('omega_activate', {
        p_mode: mode, p_daily_goal: dailyGoal, p_params: params as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as OmegaControl;
}

export async function stopOmega(): Promise<OmegaControl> {
    const { data, error } = await supabase.rpc('omega_stop', {});
    if (error) throw new Error(error.message);
    return data as unknown as OmegaControl;
}

export async function updateOmegaParams(args: {
    dailyGoal?: number; params?: Partial<OmegaParams>; mode?: OmegaMode;
}): Promise<OmegaControl> {
    const { data, error } = await supabase.rpc('omega_update_params', {
        p_daily_goal: args.dailyGoal ?? null,
        p_params: (args.params ?? null) as never,
        p_mode: args.mode ?? null,
    });
    if (error) throw new Error(error.message);
    return data as unknown as OmegaControl;
}

export async function fetchOmegaState(activityLimit = 50): Promise<OmegaState> {
    const { data, error } = await supabase.rpc('get_omega_state', { p_activity_limit: activityLimit });
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as Partial<OmegaState>;
    const g = Number(d.goal_today);
    return {
        control: d.control ?? null,
        aggregates: d.aggregates ?? null,
        activity: d.activity ?? [],
        goal_today: Number.isFinite(g) && d.goal_today != null ? g : null,
    };
}

export async function fetchOmegaTrades(limit = 2000): Promise<OmegaTrade[]> {
    const { data, error } = await supabase.rpc('get_omega_trades', { p_limit: limit });
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as OmegaTrade[];
}

// Realtime: notifica su cambi di omega_control o omega_trades. Ritorna l'unsubscribe.
export function subscribeOmega(onChange: () => void): () => void {
    const channel = supabase
        .channel('omega-live')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'omega_control' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'omega_trades' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(channel); };
}

// ------------------------------------------------------------ MODALITÀ MANUALE
export interface OmegaEventMarket {
    market_id: string;
    market_name: string | null;
    market_type: string | null;
    total_matched: number | null;
    runner_names?: Record<string, string>;
}
export interface OmegaEvent {
    event_id: string;
    name: string | null;
    open_date: string | null;
    markets: OmegaEventMarket[];
    updated_at: string;
    // enrichment 16/07 (best-effort, null = non risolto): competizione da
    // Betfair + id fixture/lega/squadre abbinati dal matcher per i loghi.
    country_code?: string | null;
    competition_id?: string | null;
    competition_name?: string | null;
    fixture_id?: number | null;
    league_id?: number | null;
    home_team_id?: number | null;
    away_team_id?: number | null;
}
export interface OmegaMarketRunner {
    selection_id: number;
    name: string;
    status?: string | null;
    lay_price: number | null;
    lay_size: number;
    back_price: number | null;
    back_size: number;
    lay_ladder?: [number, number][];
}
export interface OmegaMarketSnapshot {
    market_id: string;
    event_id: string | null;
    event_name: string | null;
    market_name: string | null;
    inplay: boolean;
    minute: number | null;
    runners: OmegaMarketRunner[];
    updated_at: string;
}
export interface OmegaManualRequest {
    id: number;
    kind: 'refresh_events' | 'load_markets' | 'load_book' | 'place' | 'cashout';
    payload: Record<string, unknown>;
    status: 'pending' | 'processing' | 'done' | 'error';
    result: Record<string, unknown> | null;
    created_at: string;
    processed_at: string | null;
}

export type OmegaSide = 'lay' | 'back';

export interface OmegaPlacePayload {
    event_id: string;
    event_name?: string | null;
    market_id: string;
    selection_id: number;
    runner_name?: string | null;
    side: OmegaSide;
    mode: OmegaMode;
    price?: number | null;
    size?: number | null;
    target?: number | null;
    commission_pct?: number;
    /** gamba della missione (tab MISSIONE): etichetta il trade per fase */
    phase?: 'ht_cs' | 'ft_cs' | 'scalp';
}

export async function requestManual(
    kind: OmegaManualRequest['kind'], payload: Record<string, unknown> = {},
): Promise<number> {
    const { data, error } = await supabase.rpc('omega_request', { p_kind: kind, p_payload: payload as never });
    if (error) throw new Error(error.message);
    return data as unknown as number;
}

export async function fetchOmegaEvents(): Promise<OmegaEvent[]> {
    const { data, error } = await supabase.rpc('get_omega_events', {});
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as OmegaEvent[];
}

export async function fetchOmegaMarket(marketId: string): Promise<OmegaMarketSnapshot | null> {
    const { data, error } = await supabase.rpc('get_omega_market', { p_market_id: marketId });
    if (error) throw new Error(error.message);
    return (data ?? null) as unknown as OmegaMarketSnapshot | null;
}

export async function fetchManualRequests(limit = 20): Promise<OmegaManualRequest[]> {
    const { data, error } = await supabase.rpc('get_omega_manual_requests', { p_limit: limit });
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as OmegaManualRequest[];
}

// Equity curve: cumulato del P&L sui trade REGOLATI, ordinati per settled_at.
export function buildEquitySeries(trades: OmegaTrade[]): { t: number; v: number; iso: string }[] {
    const settled = trades
        .filter(t => t.settled_at && (t.status === 'won' || t.status === 'lost' || t.status === 'void'))
        .sort((a, b) => new Date(a.settled_at as string).getTime() - new Date(b.settled_at as string).getTime());
    let cum = 0;
    return settled.map(t => {
        cum += Number(t.pnl) || 0;
        return { t: new Date(t.settled_at as string).getTime(), v: cum, iso: t.settled_at as string };
    });
}
