// ============================================================================
// scalper.ts — client del pannello SCALPER BOT (Segui Live).
// Parla SOLO con le RPC owner-only (migrations/scalper_bot.sql):
//   scalper_activate / scalper_stop / get_scalper_state.
// L'esecuzione vera avviene nel servizio locale scalper_service.py
// (avvia_scalper_service.bat): la UI scrive la richiesta e legge lo stato.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

export type ScalperMode = 'maker' | 'bias' | 'both';
export type ScalperStatus =
    | 'requested' | 'arming' | 'armed' | 'running'
    | 'stopping' | 'stopped' | 'done' | 'error';

export interface ScalperControl {
    event_id: string;
    status: ScalperStatus;
    mode: ScalperMode;
    dry_run: boolean;
    stake: number;
    params: Record<string, unknown>;
    bias: Record<string, 'BACK' | 'LAY'> | null;
    bias_meta: {
        consenso?: boolean;
        direzione?: string | null;
        prob_ml?: number | null;
        prob_poisson?: number | null;
        prob_mercato?: number | null;
        edge?: number | null;
        motivi?: string[];
        modalita?: string;
    } | null;
    stats: {
        orders_placed?: number; dry_quotes?: number; cycles?: number;
        scalps?: number; roundtrips?: number; scratches?: number;
        stops?: number; flattens?: number; pnl_locked?: number;
    } | null;
    error: string | null;
    requested_at: string;
    started_at: string | null;
    stopped_at: string | null;
    heartbeat_at: string | null;
}

export interface ScalperActivityRow {
    id: number;
    event_id: string;
    ts: string;
    kind: string;
    payload: Record<string, unknown>;
}

export interface ScalperState {
    control: ScalperControl | null;
    activity: ScalperActivityRow[];
}

// Parametri modificabili dalla UI, con i DEFAULT VALIDATI in backtest
// (grid 02/07/2026 — dossier §9). Whitelist speculare al servizio.
export interface ScalperParams {
    scalp_ticks: number;
    stop_ticks: number;
    min_flow: number;
    min_size: number;
    price_min: number;
    price_max: number;
    entry_stop_before_s: number;
    flatten_before_s: number;
}

export const SCALPER_PARAM_DEFAULTS: ScalperParams = {
    scalp_ticks: 1,
    stop_ticks: 1,
    min_flow: 10,
    min_size: 150,
    price_min: 1.5,
    price_max: 4.6,
    entry_stop_before_s: 420,
    flatten_before_s: 180,
};

export const SCALPER_PARAM_FIELDS: {
    key: keyof ScalperParams; label: string; step: number;
    min: number; max: number; hint: string;
}[] = [
    { key: 'scalp_ticks', label: 'Tick di profitto', step: 1, min: 1, max: 5, hint: 'target di chiusura per ciclo' },
    { key: 'stop_ticks', label: 'Tick di stop', step: 1, min: 1, max: 5, hint: 'tick avversi dopo lo scratch' },
    { key: 'min_flow', label: 'Flusso min €/lato (90s)', step: 5, min: 0, max: 500, hint: 'gate: volume stampato per lato' },
    { key: 'min_size', label: 'Size min ai best €', step: 25, min: 0, max: 2000, hint: 'liquidità minima sul touch' },
    { key: 'price_min', label: 'Quota min', step: 0.1, min: 1.01, max: 5, hint: 'sotto: code lente, rischio KO' },
    { key: 'price_max', label: 'Quota max', step: 0.1, min: 1.5, max: 20, hint: 'sopra: tick troppo larghi' },
    { key: 'entry_stop_before_s', label: 'Stop ingressi (s pre-KO)', step: 30, min: 60, max: 1800, hint: 'niente nuovi cicli sotto questa soglia' },
    { key: 'flatten_before_s', label: 'Chiusura forzata (s pre-KO)', step: 30, min: 30, max: 900, hint: 'tutto flat prima del fischio' },
];

export async function activateScalper(
    eventId: string, mode: ScalperMode, dryRun: boolean, stake: number,
    params: Partial<ScalperParams>,
): Promise<ScalperControl> {
    const { data, error } = await supabase.rpc('scalper_activate', {
        p_event_id: eventId,
        p_mode: mode,
        p_dry_run: dryRun,
        p_stake: stake,
        p_params: params as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as ScalperControl;
}

export async function stopScalper(eventId: string): Promise<ScalperControl> {
    const { data, error } = await supabase.rpc('scalper_stop', { p_event_id: eventId });
    if (error) throw new Error(error.message);
    return data as unknown as ScalperControl;
}

export async function fetchScalperState(
    eventId: string, activityLimit = 40,
): Promise<ScalperState> {
    const { data, error } = await supabase.rpc('get_scalper_state', {
        p_event_id: eventId,
        p_activity_limit: activityLimit,
    });
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as { control?: ScalperControl | null; activity?: ScalperActivityRow[] };
    return { control: d.control ?? null, activity: d.activity ?? [] };
}
