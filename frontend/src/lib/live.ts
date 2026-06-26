// ============================================================================
// live.ts — data layer per le sezioni "Segui Live" e "Match Replay".
// Legge esclusivamente via RPC certificate (get_live_follows / list_replays /
// get_replay) + la tabella realtime `live_now` (SELECT consentita all'utente
// autenticato). Nessuna logica di P&L qui (vedi replay-pnl.ts).
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

// ----------------------------------------------------------------- Segui Live
// Una partita attualmente seguita dallo stream Betfair (o in attesa/chiusa).
export type LiveFollowStatus = 'PENDING' | 'STREAMING' | 'CLOSED' | 'UPLOADED' | 'ERROR';

export interface LiveFollow {
    event_id: string;
    fixture_id: number | null;
    league_name: string | null;
    home_name: string;
    away_name: string;
    open_date: string;
    status: LiveFollowStatus;
    error_detail: string | null;
    inplay: boolean | null;
    minute: number | null;
    score_home: number | null;
    score_away: number | null;
    live_status: string | null;
    score_source: string | null;
    updated_at: string | null;
}

// get_live_follows -> { rows: LiveFollow[] }
export async function fetchLiveFollows(): Promise<LiveFollow[]> {
    const { data, error } = await supabase.rpc('get_live_follows');
    if (error) throw new Error(error.message);
    const raw = data as { rows?: LiveFollow[] } | LiveFollow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// ------------------------------------------------ live_now (realtime glance)
// Snapshot live "leggero" letto direttamente dalla tabella: usato dal dettaglio
// di Segui Live per mostrare le quote che si aggiornano in tempo reale.
export interface LiveNowSelection {
    selection_id: number;
    name: string;
    back: number | null;
    lay: number | null;
    ltp: number | null;
}
export interface LiveNowMarket {
    market_id: string;
    market_type: string;
    market_name: string;
    selections: LiveNowSelection[];
}
export interface LiveNowState {
    markets: LiveNowMarket[];
    updated_ms?: number;
}
export interface LiveNowRow {
    event_id: string;
    inplay: boolean | null;
    minute: number | null;
    score_home: number | null;
    score_away: number | null;
    status: string | null;
    score_source: string | null;
    state: LiveNowState | null;
    updated_at: string | null;
}

export async function fetchLiveNow(eventId: string): Promise<LiveNowRow | null> {
    const { data, error } = await supabase
        .from('live_now')
        .select('*')
        .eq('event_id', eventId)
        .maybeSingle();
    if (error) throw new Error(error.message);
    return (data as LiveNowRow | null) ?? null;
}

// Sottoscrizione realtime alla riga `live_now` di un evento. Ritorna una
// funzione di unsubscribe da invocare a smontaggio / cambio selezione.
export function subscribeLiveNow(
    eventId: string,
    cb: (row: LiveNowRow | null) => void,
): () => void {
    const channel = supabase
        .channel(`live_now:${eventId}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'live_now', filter: `event_id=eq.${eventId}` },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as LiveNowRow | null;
                cb(next);
            },
        )
        .subscribe();
    return () => { supabase.removeChannel(channel); };
}

// ---------------------------------------------------------------- Match Replay
// Voce della lista dei replay disponibili (mercati registrati di una partita).
export interface ReplayItem {
    event_id: string;
    fixture_id: number | null;
    league_id: number | null;   // per logo lega (può essere null finché il backend non lo espone)
    league_name: string | null;
    home_name: string;
    away_name: string;
    open_date: string;
    status: string;
    n_markets: number | null;
    n_snapshots: number | null;
    started_at: string | null;
    ended_at: string | null;
}

// list_replays(p_limit) -> { rows: ReplayItem[] }
export async function fetchReplayList(limit = 50): Promise<ReplayItem[]> {
    const { data, error } = await supabase.rpc('list_replays', { p_limit: limit });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: ReplayItem[] } | ReplayItem[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// --- struttura completa di un replay (get_replay) ---
export interface ReplaySelection {
    selection_id: number;
    name: string;
    sort_priority: number | null;
}
export interface Market {
    market_id: string;
    market_type: string | null;
    market_name: string | null;
    sort_priority: number | null;
    selections: ReplaySelection[];
}
// Ladder: per ogni selection_id, i livelli back/lay come [prezzo, size] (index 0 = best).
export interface LadderEntry {
    back: [number, number][];
    lay: [number, number][];
    ltp: number | null;
    tv: number | null;
}
export type Ladder = Record<string /* selection_id */, LadderEntry>;
export interface Frame {
    market_id: string;
    ts: string;
    minute: number | null;
    inplay: boolean;
    status: string;
    ladder: Ladder;
}
export interface ScoreEvent {
    ts: string;
    minute: number | null;
    score_home: number | null;
    score_away: number | null;
    event_type: string | null;
    source: string;
}
export interface ReplayEvent {
    event_id: string;
    fixture_id: number | null;
    league_name: string | null;
    home_name: string;
    away_name: string;
    open_date: string;
    status: string;
}
export interface ReplayData {
    event: ReplayEvent;
    markets: Market[];
    frames: Frame[];
    score_timeline: ScoreEvent[];
}

// get_replay(p_event_id) -> ReplayData
export async function fetchReplay(eventId: string): Promise<ReplayData> {
    const { data, error } = await supabase.rpc('get_replay', { p_event_id: eventId });
    if (error) throw new Error(error.message);
    return data as ReplayData;
}

// ----------------------------------------------------------- Live Signals (#2)
// Segnali del Motore Live (Poisson/DC pro) per una partita seguita. Decoupled da
// `live_now` (cadenza prezzi) → tabella dedicata `live_signals` (write-on-change).
export type SignalDirection = 'BACK' | 'LAY' | 'HOLD';

export interface Signal {
    market_id: string;
    market_type: string | null;
    market_name?: string | null;
    selection_id: number;
    selection_name: string | null;
    model_prob: number;          // 0..1 prob calibrata del motore
    market_back: number | null;  // best back disponibile
    market_lay: number | null;   // best lay disponibile
    fair_back: number | null;    // quota equa (1/prob) lato back
    fair_lay: number | null;     // quota equa lato lay
    edge: number | null;         // edge frazionario (es. 0.05 = +5%)
    direction: SignalDirection;
    confidence: number;          // 0..1
    kelly_stake: number;         // £ (Kelly frazionato)
}

// La colonna `signals` è un jsonb { signals: Signal[]; updated_ms: number|null }.
export interface LiveSignalsState {
    signals: Signal[];
    updated_ms: number | null;
}

export interface LiveSignalsRow {
    event_id: string;
    signals: LiveSignalsState | null;
    model_meta: Record<string, unknown> | null;
    updated_at: string | null;
}

// Snapshot iniziale dei segnali (la sottoscrizione poi aggiorna in realtime).
export async function fetchLiveSignals(eventId: string): Promise<LiveSignalsRow | null> {
    const { data, error } = await supabase
        .from('live_signals')
        .select('*')
        .eq('event_id', eventId)
        .maybeSingle();
    if (error) throw new Error(error.message);
    return (data as LiveSignalsRow | null) ?? null;
}

// Sottoscrizione realtime alla riga `live_signals` di un evento. Ritorna unsub.
export function subscribeLiveSignals(
    eventId: string,
    cb: (row: LiveSignalsRow | null) => void,
): () => void {
    const channel = supabase
        .channel(`live_signals:${eventId}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'live_signals', filter: `event_id=eq.${eventId}` },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as LiveSignalsRow | null;
                cb(next);
            },
        )
        .subscribe();
    return () => { supabase.removeChannel(channel); };
}

// ----------------------------------------------------------- Live Alerts (#5)
// Avvisi limiti Betfair / sistema. Banner in-app (nessuna dipendenza esterna).
export type AlertLevel = 'INFO' | 'WARN' | 'CRITICAL';

export interface Alert {
    id: number;
    level: AlertLevel;
    code: string | null;
    message: string;
    event_id: string | null;
    acknowledged: boolean;
    created_at: string;
}

// get_live_alerts() -> { rows: Alert[] } (solo non-acknowledged)
export async function fetchLiveAlerts(): Promise<Alert[]> {
    const { data, error } = await supabase.rpc('get_live_alerts');
    if (error) throw new Error(error.message);
    const raw = data as { rows?: Alert[] } | Alert[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// Sottoscrizione realtime a TUTTA la tabella live_alerts (nessun filtro evento).
// Il chiamante ricaricerà la lista degli unacked alla ricezione di un cambiamento.
export function subscribeLiveAlerts(cb: () => void): () => void {
    const channel = supabase
        .channel('live_alerts')
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'live_alerts' },
            () => { cb(); },
        )
        .subscribe();
    return () => { supabase.removeChannel(channel); };
}

// ack_alert(p_id) → segna l'avviso come gestito (sparisce dal banner).
export async function ackAlert(id: number): Promise<void> {
    const { error } = await supabase.rpc('ack_alert', { p_id: id });
    if (error) throw new Error(error.message);
}

// ----------------------------------------------------------------- etichette
export const LIVE_STATUS_LABEL: Record<LiveFollowStatus, string> = {
    PENDING: 'In attesa',
    STREAMING: 'In streaming',
    CLOSED: 'Chiusa',
    UPLOADED: 'Caricata',
    ERROR: 'Errore',
};
