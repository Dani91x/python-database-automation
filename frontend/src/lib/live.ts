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

// Sottoscrizione realtime alla riga `live_follow` di un evento (stato
// PENDING→STREAMING→CLOSED/ERROR). Fix 17/07 "Trading = streaming immediato":
// la pagina Segui Live reagisce al cambio di stato APPENA il runner aggancia,
// invece di aspettare il poll di backup (15s). Pattern identico a
// subscribeBacktestRequest (analytics.ts). NB: il realtime notifica solo i
// CAMBI futuri → il chiamante DEVE fare anche un fetch immediato (follow già
// STREAMING all'arrivo). Richiede la migrazione live_follow_realtime.sql
// (policy SELECT authenticated + publication): senza, semplicemente non arriva
// alcun evento e resta attivo il poll di backup (nessuna regressione).
export function subscribeLiveFollowEvent(
    eventId: string,
    cb: (row: LiveFollow | null) => void,
): () => void {
    const channel = supabase
        .channel(`live_follow:${eventId}:${Math.random().toString(36).slice(2, 10)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'live_follow', filter: `event_id=eq.${eventId}` },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as LiveFollow | null;
                cb(next);
            },
        )
        .subscribe();
    return () => { supabase.removeChannel(channel); };
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
    status?: string | null;   // OPEN | SUSPENDED | CLOSED (per il badge/banner)
    selections: LiveNowSelection[];
}
/** statistiche live scritte dal runner (score_worker: state["stats"] = snap.stats).
 *  Presenti quando il provider punteggio le espone (Betfair in-play); possono
 *  mancare del tutto col fallback — i consumer devono tollerarne l'assenza. */
export interface LiveNowStats {
    cards?: {
        yellow_home?: number | null;
        yellow_away?: number | null;
        red_home?: number | null;
        red_away?: number | null;
    } | null;
}
export interface LiveNowState {
    markets: LiveNowMarket[];
    order_mode?: string;       // OFF | PAPER | LIVE — modalità ordini del runner (per il badge del pannello Live Trading)
    updated_ms?: number;
    stats?: LiveNowStats | null;
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
// Fix audit #21: il nome del canale è UNICO per sottoscrizione (suffisso random) —
// due iscrizioni allo stesso evento (es. due slot multi-ladder) con lo stesso topic
// si contendevano il canale e una restava a secco. Il nome è solo un identificatore
// client-side: nessun altro codice dipende dalla stringa del topic.
export function subscribeLiveNow(
    eventId: string,
    cb: (row: LiveNowRow | null) => void,
): () => void {
    const channel = supabase
        .channel(`live_now:${eventId}:${Math.random().toString(36).slice(2, 10)}`)
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
    // volume tradato per-prezzo [prezzo, volume] (cumulativo). Presente solo nelle
    // registrazioni recenti (recorder full-depth) → abilita i fill maker tick-perfetti.
    trd?: [number, number][];
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
    // dict grezzo del provider (get_scores): contiene i conteggi corner/cartellini
    // per derivare gli eventi quando non sono presenti come event_type discreti.
    payload?: any;
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

// get_replay(p_event_id) -> ReplayData (chiamata UNICA: usata solo come fallback
// finché la migrazione live_stream_rpc_chunked.sql non è applicata — sugli eventi
// grandi muore col timeout del ruolo API ~8s).
export async function fetchReplay(eventId: string): Promise<ReplayData> {
    const { data, error } = await supabase.rpc('get_replay', { p_event_id: eventId });
    if (error) throw new Error(error.message);
    return data as ReplayData;
}

// --- caricamento a FINESTRE TEMPORALI (fix timeout eventi grandi) ---
// get_replay_meta -> anagrafica + catalogo + score_timeline + estremi temporali.
export interface ReplayMeta {
    event: ReplayEvent;
    markets: Market[];
    score_timeline: ScoreEvent[];
    ts_min: string | null;
    ts_max: string | null;
    inplay_from_ts: string | null;
}

export interface ReplayProgress {
    done: number;      // finestre completate
    total: number;     // finestre totali
    frames: number;    // frame accumulati finora
}

// Budget di frame del replay: bucket adattivo per restarci dentro.
const REPLAY_TARGET_FRAMES = 9000;   // in-play (granularità fine)
const REPLAY_TARGET_PRE = 2500;      // pre-match (granularità grossa)
const WINDOW_MS = 10 * 60_000;       // finestra di fetch: 10 minuti
// p_max_rows per finestra: DEVE superare il budget teorico di frame di una
// finestra (WINDOW_MS/bucket × mercati) — se il server tronca, il client lo
// rileva (n === max) e DIMEZZA la finestra: mai un troncamento silenzioso.
const FRAMES_PER_CALL = 10000;       // = clamp massimo di p_max_rows lato SQL
// pre-match caricato al massimo per queste ore prima del kickoff: un follow
// armato giorni prima non deve generare centinaia di finestre vuote.
const PRE_MATCH_MAX_MS = 4 * 3600_000;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// Errore PostgREST "funzione non trovata" (migrazione non ancora applicata).
const isMissingFunction = (e: { code?: string; message?: string } | null): boolean =>
    !!e && (e.code === 'PGRST202' || /get_replay_meta|schema cache/i.test(e.message ?? ''));

async function fetchReplayFramesWindow(
    eventId: string, fromMs: number, toMs: number, bucketSec: number,
): Promise<Frame[]> {
    const fromIso = new Date(fromMs).toISOString();
    const toIso = new Date(toMs).toISOString();
    const call = async () => supabase.rpc('get_replay_frames', {
        p_event_id: eventId,
        p_from_ts: fromIso,
        p_to_ts: toIso,
        p_bucket_sec: bucketSec,
        p_max_rows: FRAMES_PER_CALL,
    });
    let { data, error } = await call();
    if (error) {
        // un retry per errori transitori (rete/timeout): finestra piccola, costa poco
        await new Promise(r => setTimeout(r, 800));
        ({ data, error } = await call());
        if (error) throw new Error(`finestra ${fromIso}–${toIso}: ${error.message}`);
    }
    const raw = data as { frames?: Frame[] } | null;
    const frames = raw?.frames ?? [];
    // finestra TRONCATA dal LIMIT server (il taglio avviene per market_id → interi
    // mercati spariti in silenzio): dimezza la finestra e riprova ricorsivamente.
    if (frames.length >= FRAMES_PER_CALL && toMs - fromMs > 30_000) {
        const mid = fromMs + Math.floor((toMs - fromMs) / 2);
        const [a, b] = [
            await fetchReplayFramesWindow(eventId, fromMs, mid, bucketSec),
            await fetchReplayFramesWindow(eventId, mid, toMs, bucketSec),
        ];
        return [...a, ...b];
    }
    return frames;
}

// Carica un replay a finestre temporali con progresso. Se le RPC chunked non
// esistono ancora sul DB, ripiega in automatico sulla vecchia get_replay.
export async function fetchReplayChunked(
    eventId: string,
    onProgress?: (p: ReplayProgress) => void,
): Promise<ReplayData> {
    const { data, error } = await supabase.rpc('get_replay_meta', { p_event_id: eventId });
    if (error) {
        if (isMissingFunction(error)) return fetchReplay(eventId); // fallback pre-migrazione
        throw new Error(error.message);
    }
    const meta = data as ReplayMeta;
    const base: ReplayData = {
        event: meta.event,
        markets: meta.markets ?? [],
        frames: [],
        score_timeline: meta.score_timeline ?? [],
    };
    if (!meta.ts_min || !meta.ts_max) return base; // nessuno snapshot registrato

    let tsMin = new Date(meta.ts_min).getTime();
    const tsMax = new Date(meta.ts_max).getTime();
    const inplayFrom = meta.inplay_from_ts ? new Date(meta.inplay_from_ts).getTime() : tsMin;
    const nMkts = Math.max(1, base.markets.length);

    // pre-match cappato alle ultime PRE_MATCH_MAX_MS ore prima del kickoff:
    // registrazioni armate con giorni d'anticipo non generano finestre inutili.
    if (inplayFrom - tsMin > PRE_MATCH_MAX_MS) tsMin = inplayFrom - PRE_MATCH_MAX_MS;

    // bucket adattivi: pre-match grossolano, in-play fine (indipendenti tra loro,
    // così 2h di pre-match non degradano la granularità della partita).
    const preSpanSec = Math.max(0, (Math.min(inplayFrom, tsMax) - tsMin) / 1000);
    const inSpanSec = Math.max(0, (tsMax - Math.max(inplayFrom, tsMin)) / 1000);
    const bucketPre = clamp(Math.ceil((preSpanSec * nMkts) / REPLAY_TARGET_PRE), 30, 300);
    const bucketIn = clamp(Math.ceil((inSpanSec * nMkts) / REPLAY_TARGET_FRAMES), 2, 60);

    // pianifica le finestre [from, to) con il bucket della fase corrispondente
    const windows: { from: number; to: number; bucket: number }[] = [];
    const pushWindows = (from: number, to: number, bucket: number) => {
        for (let t = from; t < to; t += WINDOW_MS) {
            windows.push({ from: t, to: Math.min(t + WINDOW_MS, to), bucket });
        }
    };
    const endExclusive = tsMax + 1000; // p_to_ts esclusivo: includi l'ultimo frame
    if (inplayFrom > tsMin) {
        pushWindows(tsMin, Math.min(inplayFrom, endExclusive), bucketPre);
        pushWindows(inplayFrom, endExclusive, bucketIn);
    } else {
        pushWindows(tsMin, endExclusive, bucketIn);
    }

    const frames: Frame[] = [];
    for (let i = 0; i < windows.length; i++) {
        const w = windows[i];
        const part = await fetchReplayFramesWindow(eventId, w.from, w.to, w.bucket);
        frames.push(...part);
        onProgress?.({ done: i + 1, total: windows.length, frames: frames.length });
    }
    return { ...base, frames };
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

// F40: hazard gol imminente dal modello (λ residui calibrati + CDF tempi-gol).
// Presente SOLO in-play; deriva da minuto/punteggio/cartellini (NON tiri live).
export interface GoalHazardState {
    p_next: number;          // P(≥1 gol nei prossimi horizon_min minuti), 0..1
    exp_goals_next: number;  // gol attesi nell'orizzonte
    horizon_min: number;     // ampiezza orizzonte (default 5')
    minute: number;          // minuto a cui è stato calcolato
    lam_home: number;
    lam_away: number;
}

// La colonna `signals` è un jsonb { signals: Signal[]; updated_ms; commission; hazard }.
export interface LiveSignalsState {
    signals: Signal[];
    updated_ms: number | null;
    // F38: commissione con cui il motore ha calcolato EV/Kelly (assente nelle righe
    // scritte prima del deploy: il frontend ricade sul default 5% del motore).
    commission?: number | null;
    // F40: assente pre-match o nelle righe scritte prima del deploy.
    hazard?: GoalHazardState | null;
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

// ------------------------------------------------------------- Live Ladder
// Ladder LIVE per-mercato (Betting Toolkit / Bet Angel / Geeks Toy), SOLA LETTURA.
// Pubblicata dal runner (ladder_worker) sulla tabella realtime `live_ladder` in
// modalità write-on-change, costruita dai soli dati dello stream già sottoscritto.
// La pagina ladder sottoscrive QUESTA tabella filtrando per market_id (come live_now).
export interface LiveLadderSelection {
    selection_id: number;
    name: string | null;
    ltp: number | null;
    tv: number | null;                 // volume tradato totale sulla selezione (EUR)
    back: [number, number][];          // disponibile al BACK [prezzo, size] (best first)
    lay: [number, number][];           // disponibile al LAY  [prezzo, size] (best first)
    trd: [number, number][];           // volume tradato per-prezzo [prezzo, volume] (full)
    wom: { back_pct: number; lay_pct: number }; // weight of money vicino al best (~3 livelli)
}
export interface LiveLadderState {
    updated_ms: number | null;
    selections: LiveLadderSelection[];
}
export interface LiveLadderRow {
    event_id: string;
    market_id: string;
    market_type: string | null;
    market_name: string | null;
    status: string | null;             // OPEN | SUSPENDED | CLOSED (per banda/banner)
    ladder: LiveLadderState | null;
    updated_at: string | null;
}

// Snapshot iniziale della ladder di un mercato (la sottoscrizione aggiorna poi in realtime).
export async function fetchLiveLadder(marketId: string): Promise<LiveLadderRow | null> {
    const { data, error } = await supabase
        .from('live_ladder')
        .select('*')
        .eq('market_id', marketId)
        .maybeSingle();
    if (error) throw new Error(error.message);
    return (data as LiveLadderRow | null) ?? null;
}

// Sottoscrizione realtime alla riga `live_ladder` di un mercato (filtro per market_id,
// come subscribeLiveNow). Ritorna una funzione di unsubscribe da invocare a smontaggio /
// cambio mercato.
export function subscribeLiveLadder(
    marketId: string,
    cb: (row: LiveLadderRow | null) => void,
): () => void {
    const channel = supabase
        .channel(`live_ladder:${marketId}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'live_ladder', filter: `market_id=eq.${marketId}` },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as LiveLadderRow | null;
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
