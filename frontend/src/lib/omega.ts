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
export type OmegaTradeStatus = 'pending' | 'open' | 'won' | 'lost' | 'void' | 'error';

export interface OmegaStats {
    events_total?: number;
    matches_traded?: number;
    matches_traded_today?: number;
    matches_open?: number;
    realized_profit?: number;
    realized_today?: number;   // §2: P&L regolato nella GIORNATA operativa (Europe/Rome)
    open_liability?: number;
    matches_remaining?: number;
    target_match?: number;
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
    meta: Record<string, unknown>;
}

export interface OmegaAggregates {
    realized_profit: number;
    realized_today?: number;        // giornata operativa Europe/Rome (RPC aggiornata)
    open_liability: number;
    matches_traded: number;
    matches_traded_today?: number;
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
};

export type OmegaNumericParamKey = {
    [K in keyof OmegaParams]: OmegaParams[K] extends number ? K : never;
}[keyof OmegaParams];

export const OMEGA_PARAM_FIELDS: {
    key: OmegaNumericParamKey; label: string; step: number; min: number; max: number; hint: string;
}[] = [
    { key: 'price_min', label: 'Quota lay MIN', step: 1, min: 1.01, max: 1000, hint: 'sotto: risultato troppo probabile' },
    { key: 'price_max', label: 'Quota lay MAX', step: 5, min: 1.01, max: 1000, hint: 'sopra: profit irrisorio / liability enorme (niente 600)' },
    { key: 'entry_minute_min', label: 'Minuto ingresso MIN', step: 1, min: 0, max: 130, hint: 'piazza solo dopo questo minuto' },
    { key: 'entry_minute_max', label: 'Minuto ingresso MAX', step: 1, min: 0, max: 130, hint: 'niente ingressi dopo questo minuto' },
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
    return {
        control: d.control ?? null,
        aggregates: d.aggregates ?? null,
        activity: d.activity ?? [],
    };
}

export async function fetchOmegaTrades(limit = 500): Promise<OmegaTrade[]> {
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
    kind: 'refresh_events' | 'load_markets' | 'load_book' | 'place';
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
