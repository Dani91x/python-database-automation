// ============================================================================
// tennis.ts — DATA LAYER DEDICATO ALLA SEZIONE TENNIS.
//
// Regola d'oro (richiesta esplicita utente): Tennis e Calcio sono sport diversi e
// NON devono MAI condividere dati. Questo modulo parla ESCLUSIVAMENTE con tabelle e
// RPC dedicate al tennis (`tennis_*` / `get_tennis_*` / `request_tennis_*`). Nessuna
// riga, tabella o RPC del calcio viene toccata o letta da qui.
//
// L'infrastruttura ricalca 1:1 quella del calcio (lib/betfair.ts + lib/live.ts +
// lib/liveOrders.ts + lib/scalper.ts) per riuso dei componenti, ma su storage tennis
// separato. I TIPI condivisi (forma della ladder/ordini) sono importati come type-only
// da lib/live.ts / lib/liveOrders.ts: è solo condivisione di SHAPE TypeScript, non di
// dati runtime — i reader tennis qui sotto leggono unicamente tabelle `tennis_*`.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import type { LiveLadderRow } from '@/lib/live';
import type {
    LiveOrderCommand,
    LiveOrderResult,
    LiveOrderRow,
    LivePositionRow,
} from '@/lib/liveOrders';

// ============================================================================
// 1) PARTITE DEL GIORNO (Screen 2) — mercato Tennis Betfair (eventTypeId=2)
// ============================================================================

export interface TennisOddLevel {
    price: number;
    size: number;
}

/** Una gamba (giocatore) del mercato Match Odds con profondità back/lay. */
export interface TennisMoneylineRunner {
    selection_id: number;
    name: string;
    sort_priority: number | null;
    back: TennisOddLevel[]; // best-first
    lay: TennisOddLevel[]; // best-first
    ltp: number | null;
}

/** Mercato aggiuntivo disponibile sull'evento (Set Betting, Handicap Games, ecc.). */
export interface TennisEventMarket {
    market_id: string;
    market_type: string; // MATCH_ODDS | SET_BETTING | ...
    market_name: string;
    total_matched: number | null;
}

/**
 * Riga "match del giorno" Tennis. Chiave su event_id/market_id Betfair (il tennis
 * NON ha fixture calcio): tutto è keyato sull'evento Betfair.
 */
export interface TennisFixtureRow {
    event_id: string;
    /** market_id del Match Odds (moneyline) — usato per aprire il terminal. */
    market_id: string;
    competition_id: string | null;
    /** Nome torneo/competizione (es. "ATP Wimbledon", "ITF Women ...", "Challenger ..."). */
    competition_name: string;
    /** Regione/paese se esposto da Betfair (per raggruppamento/etichetta). */
    competition_region: string | null;
    open_date: string; // ISO — orario d'inizio
    inplay: boolean;
    status: string; // OPEN | SUSPENDED | CLOSED
    player1: TennisMoneylineRunner;
    player2: TennisMoneylineRunner;
    /** Volume totale matchato sul Match Odds (EUR). */
    total_matched: number | null;
    /** Tutti i mercati dell'evento (incl. Match Odds) per lo Screen 3 / mercati extra. */
    markets: TennisEventMarket[];
    /** Timestamp cattura quote (per freschezza). */
    captured_at: string | null;
}

/**
 * get_tennis_fixtures(p_date) -> TennisFixtureRow[]
 * Match Tennis del giorno con moneyline P1/P2 (back/lay), volume, stato, mercati extra.
 */
export async function fetchTennisFixtures(date: string): Promise<TennisFixtureRow[]> {
    const { data, error } = await supabase.rpc('get_tennis_fixtures', { p_date: date });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: TennisFixtureRow[] } | TennisFixtureRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// ---------- Quote COMPLETE di un evento (tutti i mercati, back+lay N livelli) ----------
export interface TennisFullRunner {
    selection: string;
    selection_id: number | null;
    sort_priority: number | null;
    back: TennisOddLevel[];
    lay: TennisOddLevel[];
    ltp: number | null;
}
export interface TennisFullMarket {
    market_id: string;
    market: string; // nome mercato
    market_type: string;
    total_matched: number | null;
    runners: TennisFullRunner[];
}

/** get_tennis_full_odds(p_event_id) -> TennisFullMarket[] */
export async function fetchTennisFullOdds(eventId: string): Promise<TennisFullMarket[]> {
    const { data, error } = await supabase.rpc('get_tennis_full_odds', { p_event_id: eventId });
    if (error) throw new Error(error.message);
    return (Array.isArray(data) ? data : []) as TennisFullMarket[];
}

/**
 * request_tennis_refresh(p_event_id) + poll get_tennis_refresh_request(p_id)
 * Aggiorna on-demand le quote Betfair di un evento tennis (runner locale).
 */
export interface TennisRefreshResult {
    status: 'done' | 'error' | 'pending';
    updated: number | null;
    error: string | null;
}
export async function refreshTennisOdds(eventId: string, timeoutMs = 60_000): Promise<TennisRefreshResult> {
    const { data: reqId, error } = await supabase.rpc('request_tennis_refresh', { p_event_id: eventId });
    if (error) throw new Error(error.message);
    const started = performance.now();
    // poll
    // eslint-disable-next-line no-constant-condition
    while (true) {
        const { data, error: pErr } = await supabase.rpc('get_tennis_refresh_request', { p_id: reqId });
        if (pErr) throw new Error(pErr.message);
        const res = data as TennisRefreshResult;
        if (res && res.status !== 'pending') return res;
        if (performance.now() - started > timeoutMs) {
            return { status: 'error', updated: null, error: 'timeout' };
        }
        await new Promise((r) => setTimeout(r, 1500));
    }
}

// ============================================================================
// 2) SEGUI LIVE TENNIS — eventi seguiti dallo stream tennis dedicato
//    Tabelle: tennis_live_follow / tennis_live_now / tennis_live_ladder /
//             tennis_live_signals  (mirror di live_* ma dedicate al tennis)
// ============================================================================

export type TennisFollowStatus = 'PENDING' | 'STREAMING' | 'CLOSED' | 'UPLOADED' | 'ERROR';

export interface TennisFollow {
    event_id: string;
    competition_name: string | null;
    player1_name: string;
    player2_name: string;
    open_date: string;
    status: TennisFollowStatus;
    error_detail: string | null;
    /** registrazione opt-in per-partita (migrations/tennis_follow_record.sql);
     *  assente/null se la migrazione non è ancora applicata = non registra */
    record?: boolean | null;
    inplay: boolean | null;
    /** stato punteggio serializzato (vedi TennisScoreState) */
    score: TennisScoreState | null;
    live_status: string | null;
    updated_at: string | null;
}

/** get_tennis_follows() -> { rows: TennisFollow[] } */
export async function fetchTennisFollows(): Promise<TennisFollow[]> {
    const { data, error } = await supabase.rpc('get_tennis_follows');
    if (error) throw new Error(error.message);
    const raw = data as { rows?: TennisFollow[] } | TennisFollow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

/**
 * Registra un evento tennis da seguire live (il runner tennis lo prenderà in carico).
 * tennis_follow_event(p_event_id, p_market_id) -> TennisFollow
 */
export async function followTennisEvent(eventId: string, marketId: string): Promise<TennisFollow> {
    const { data, error } = await supabase.rpc('tennis_follow_event', {
        p_event_id: eventId,
        p_market_id: marketId,
    });
    if (error) throw new Error(error.message);
    return data as unknown as TennisFollow;
}

/**
 * Registrazione OPT-IN per-partita: accende/spegne la registrazione del raw
 * nativo (.raw.jsonl + .score.jsonl, consumabile dai lab tennis) per un evento
 * SEGUITO. Il runner rilegge il flag periodicamente: il toggle funziona anche a
 * metà partita. tennis_set_follow_record(p_event_id, p_record) -> { record, ... }
 */
export async function setTennisFollowRecord(
    eventId: string,
    record: boolean,
): Promise<{ event_id: string; record: boolean }> {
    const { data, error } = await supabase.rpc('tennis_set_follow_record', {
        p_event_id: eventId,
        p_record: record,
    });
    if (error) throw new Error(error.message);
    return data as unknown as { event_id: string; record: boolean };
}

// ---------------------------------------------------- tennis_live_now (realtime)
export async function fetchTennisNow(eventId: string): Promise<TennisLiveNowRow | null> {
    const { data, error } = await supabase
        .from('tennis_live_now')
        .select('*')
        .eq('event_id', eventId)
        .maybeSingle();
    if (error) throw new Error(error.message);
    return (data as TennisLiveNowRow | null) ?? null;
}

// REALTIME lista partite del giorno (16/07 "non polling, canale WS"): notifica
// quando il worker scrive/aggiorna righe in tennis_markets → il chiamante ricarica
// la giornata via RPC. Richiede realtime_orders_bots.sql (publication + policy).
export function subscribeTennisMarkets(cb: () => void): () => void {
    const channel = supabase
        .channel(`tennis_markets:list:${Math.random().toString(36).slice(2, 9)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'tennis_markets' },
            () => cb(),
        )
        .subscribe();
    return () => {
        supabase.removeChannel(channel);
    };
}

// NB: nome canale UNICO per sottoscrizione (suffisso random) — stesso fix
// dell'audit #21 su subscribeLiveNow: due iscrizioni allo stesso evento (es.
// Terminal tennis + radar Safe Strategy) con lo stesso topic si contendevano
// il canale e una restava a secco. Il nome è solo un identificatore client-side.
export function subscribeTennisNow(eventId: string, cb: (row: TennisLiveNowRow | null) => void): () => void {
    const channel = supabase
        .channel(`tennis_live_now:${eventId}:${Math.random().toString(36).slice(2, 10)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'tennis_live_now', filter: `event_id=eq.${eventId}` },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as TennisLiveNowRow | null;
                cb(next);
            },
        )
        .subscribe();
    return () => {
        supabase.removeChannel(channel);
    };
}

// ------------------------------------------------- tennis_live_ladder (realtime)
// Reader/subscriber dedicati per la ladder tennis. Ritornano la STESSA shape della
// ladder calcio (LiveLadderRow) così il componente LadderView riusabile può montarli
// via dependency-injection, ma leggono unicamente `tennis_live_ladder`.
export async function fetchTennisLadder(marketId: string): Promise<LiveLadderRow | null> {
    const { data, error } = await supabase
        .from('tennis_live_ladder')
        .select('*')
        .eq('market_id', marketId)
        .maybeSingle();
    if (error) throw new Error(error.message);
    return (data as LiveLadderRow | null) ?? null;
}

export function subscribeTennisLadder(marketId: string, cb: (row: LiveLadderRow | null) => void): () => void {
    const channel = supabase
        .channel(`tennis_live_ladder:${marketId}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'tennis_live_ladder', filter: `market_id=eq.${marketId}` },
            (payload) => {
                const next = (payload.new && Object.keys(payload.new).length > 0
                    ? payload.new
                    : null) as LiveLadderRow | null;
                cb(next);
            },
        )
        .subscribe();
    return () => {
        supabase.removeChannel(channel);
    };
}

// ============================================================================
// 3) MATCH STATS TENNIS (Screen 3, colonna destra) — punteggio live set/game/point
//    Pubblicato dal runner tennis su tennis_live_now (campo `score`), derivato dal
//    worker punteggio (Betfair InPlayService, ~2s) → dataclass TennisScore + win-prob.
//    Mappatura: p1 = home (sortPriority 1) · p2 = away.
// ============================================================================

/** Flag di pressione derivati (TennisScore.pressures()). */
export interface TennisPressure {
    break_point: boolean;
    set_point: boolean;
    game_point: boolean;
}

export interface TennisScoreState {
    /** matchStatus IPS (es. "InPlay", "Finished"). */
    status: string | null;
    /** set vinti */
    sets: { p1: number; p2: number };
    /** game del set corrente */
    games: { p1: number; p2: number };
    /** punti del game corrente, Betfair-style ("0","15","30","40","A" o numero tie-break). */
    points: { p1: string; p2: string };
    /** 1 o 2: chi è al servizio ora (da isServing). null se ignoto. */
    server: 1 | 2 | null;
    /** true se il game corrente è un tie-break (games 6-6, punti numerici). */
    tiebreak: boolean;
    /** storico game per-set (gameSequence IPS), es. p1:["6","3"]. */
    game_sequence: { p1: string[]; p2: string[] };
    /** break di servizio subiti/conteggiati per giocatore. */
    service_breaks: { p1: number; p2: number };
    /** indice set corrente (currentSet IPS). */
    current_set: number | null;
    /** indice game corrente nel match (currentGame IPS) — granularità punto-per-punto. */
    current_game: number | null;
    /** riepilogo set compatto per display, es. "6-4 3-6 2-1". */
    set_summary: string | null;
    /** pressione derivata (break/set/game point). */
    pressure: TennisPressure;
    /** P(vittoria p1) dal modello Markov p_match (0..1), null se non calcolabile. */
    win_prob_p1: number | null;
    /** sorgente del punteggio (ips | derived). */
    source: string | null;
    updated_ms: number | null;
}

/** Un punto della cronologia punto-per-punto (derivata dai cambi di score key). */
export interface TennisPointEvent {
    ts: string;
    set_no: number | null;
    game_no: number | null;
    /** vincitore del punto: 1|2 (se derivabile). */
    winner: 1 | 2 | null;
    /** chi serviva */
    server: 1 | 2 | null;
    /** flag opzionali: 'break', 'set', 'game' (pressione al momento del punto). */
    tags?: string[];
    /** punteggio dopo il punto, compatto (es. "40-30"). */
    score_after: string | null;
}

// -------------------- tennis_live_now: stato evento (mercati + order_mode + score) ------
export interface TennisNowSelection {
    selection_id: number;
    name: string;
    back: number | null;
    lay: number | null;
    ltp: number | null;
}
export interface TennisNowMarket {
    market_id: string;
    market_type: string;
    market_name: string;
    status?: string | null; // OPEN | SUSPENDED | CLOSED
    selections: TennisNowSelection[];
}
export interface TennisLiveNowState {
    markets: TennisNowMarket[];
    order_mode?: string; // OFF | PAPER | LIVE (modalità ordini del runner tennis)
    updated_ms?: number;
}
export interface TennisLiveNowRow {
    event_id: string;
    inplay: boolean | null;
    status: string | null;
    /** mercati + order_mode (per il terminal/ladder). */
    state: TennisLiveNowState | null;
    /** punteggio live tennis (per il Match Stats). */
    score: TennisScoreState | null;
    /** ultimi punti (punto-per-punto). */
    points: TennisPointEvent[] | null;
    updated_at: string | null;
}

// ============================================================================
// 4) ORDINI LIVE TENNIS — coda comandi DEDICATA (tennis_live_order_queue)
//    Mirror di lib/liveOrders.ts ma su RPC tennis. Stessa shape comando/risultato.
// ============================================================================

/**
 * Invia un comando ordine sulla coda tennis (place/cancel/replace/greenup/...).
 * Speculare a lib/liveOrders.ts::sendLiveOrderCommand:
 *  - enqueue con RETRY 3× (stesso client_ref → idempotente su UNIQUE lato DB: assorbe blip di rete);
 *  - su esito 'error' RISOLVE { ok:false, error } (NON lancia) → il LadderView condiviso lo gestisce
 *    identico al calcio;
 *  - su TIMEOUT lancia "NON reinviare" (il comando potrebbe essere già stato eseguito lato runner).
 */
export async function sendTennisOrderCommand(
    cmd: LiveOrderCommand,
    timeoutMs = 90_000,
): Promise<LiveOrderResult> {
    const client_ref =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.round(Math.random() * 1e9)}`;

    let reqId: number | null = null;
    let lastErr = '';
    for (let i = 0; i < 3 && reqId == null; i++) {
        const { data, error } = await supabase.rpc('request_tennis_live_order', {
            p: { ...cmd, client_ref } as never,
        });
        if (!error && data != null) {
            reqId = data as number;
            break;
        }
        lastErr = error?.message ?? 'accodamento non riuscito';
        await new Promise((r) => setTimeout(r, 800));
    }
    if (reqId == null) throw new Error(`Comando tennis non accodato: ${lastErr}`);

    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1000));
        const { data, error: pErr } = await supabase.rpc('get_tennis_live_order', { p_id: reqId });
        if (pErr) throw new Error(pErr.message);
        const res = data as
            | { status?: string; result?: LiveOrderResult; error?: string }
            | null;
        if (!res) continue;
        if (res.status === 'done') {
            if (!res.result) throw new Error('Esito comando tennis incompleto (result mancante).');
            return res.result as LiveOrderResult;
        }
        if (res.status === 'error') {
            return {
                ok: false,
                action: cmd.action,
                mode: cmd.mode,
                error: res.error ?? (res.result as { error?: string } | undefined)?.error ?? 'comando non eseguito',
            } as LiveOrderResult;
        }
        // 'pending'/'processing' → continua il polling
    }
    // Timeout: il comando POTREBBE essere stato eseguito → NON reinviare.
    throw new Error('Esito comando tennis non confermato (timeout): NON reinviare, verifica la lista ordini.');
}

export async function fetchTennisOrders(marketId: string, mode: string): Promise<LiveOrderRow[]> {
    const { data, error } = await supabase.rpc('get_tennis_live_orders', {
        p_market_id: marketId,
        p_mode: mode,
    });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: LiveOrderRow[] } | LiveOrderRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

export async function fetchTennisPositions(marketId: string, mode: string): Promise<LivePositionRow[]> {
    const { data, error } = await supabase.rpc('get_tennis_live_positions', {
        p_market_id: marketId,
        p_mode: mode,
    });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: LivePositionRow[] } | LivePositionRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// ------------------------------------------- ordini/posizioni: REALTIME (WS)
// Richiesta 16/07 ("non polling, canale WS"): postgres_changes su
// tennis_live_orders / tennis_live_positions filtrate per market_id. Richiede
// la migrazione realtime_orders_bots.sql (publication + policy SELECT).
// Il payload notifica il CAMBIAMENTO; il chiamante ricarica via RPC (che
// applica il filtro mode lato SQL) — pattern "notify → reload" del ladder.
export function subscribeTennisOrders(
    marketId: string, cb: () => void, onHealth?: (up: boolean) => void,
): () => void {
    // suffisso univoco (review 16/07): due subscribe sullo stesso topic sullo stesso
    // client possono affamarsi a vicenda (stesso pattern di live.ts subscribeLiveNow)
    const channel = supabase
        .channel(`tennis_live_orders:${marketId}:${Math.random().toString(36).slice(2, 9)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'tennis_live_orders', filter: `market_id=eq.${marketId}` },
            () => cb(),
        )
        .subscribe((status) => onHealth?.(status === 'SUBSCRIBED'));
    return () => {
        supabase.removeChannel(channel);
    };
}

export function subscribeTennisPositions(
    marketId: string, cb: () => void, onHealth?: (up: boolean) => void,
): () => void {
    const channel = supabase
        .channel(`tennis_live_positions:${marketId}:${Math.random().toString(36).slice(2, 9)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'tennis_live_positions', filter: `market_id=eq.${marketId}` },
            () => cb(),
        )
        .subscribe((status) => onHealth?.(status === 'SUBSCRIBED'));
    return () => {
        supabase.removeChannel(channel);
    };
}

// TUTTE le posizioni tennis aperte (watchlist multi-evento D30 / dashboard D33).
// SOLO tabelle tennis_* (mai dati calcio). Richiede la migrazione
// tennis_live_positions_all_rpc.sql. mode omessa = entrambe.
export async function fetchTennisPositionsAll(mode?: string): Promise<LivePositionRow[]> {
    const { data, error } = await supabase.rpc('get_tennis_live_positions_all', {
        p_mode: mode ?? null,
    });
    if (error) throw new Error(error.message);
    const raw = data as { rows?: LivePositionRow[] } | LivePositionRow[] | null;
    if (Array.isArray(raw)) return raw;
    return raw?.rows ?? [];
}

// ============================================================================
// 5) BOT TENNIS — control multi-bot DEDICATO (tennis_bot_control)
//    Ogni bot è armabile/disarmabile in contemporanea per-evento.
//    Esecuzione reale nel servizio locale tennis_bot_service.py (cablaggio).
// ============================================================================

export type TennisBotKey = 'tennis_scalper' | 'tennis_pro' | 'tennis_flb' | 'tennis_swing';

export type TennisBotStatus =
    | 'idle'
    | 'requested'
    | 'arming'
    | 'armed'
    | 'running'
    | 'stopping'
    | 'stopped'
    | 'done'
    | 'error';

export interface TennisBotStats {
    orders_placed?: number;
    dry_quotes?: number;
    cycles?: number;
    scalps?: number;
    roundtrips?: number;
    scratches?: number;
    stops?: number;
    flattens?: number;
    /** ⚠️ P&L LORDO: flumine non detrae la commissione Betfair (4,5-5%) — etichettare "lordo" in UI. */
    pnl_locked?: number;
    /** ⚠️ P&L LORDO dei soli cicli regolati (validazione paper n≥40); può mancare nei bot vecchi. */
    pnl_settled?: number;
    pnl_open?: number;
    /** missione "1 tick per fase" (tennis_scalper): contatori/P&L per fase. */
    greens_prematch?: number;
    greens_inplay?: number;
    pnl_prematch?: number;
    pnl_inplay?: number;
}

export interface TennisBotControl {
    event_id: string;
    bot_key: TennisBotKey;
    status: TennisBotStatus;
    dry_run: boolean;
    stake: number;
    params: Record<string, unknown>;
    stats: TennisBotStats | null;
    error: string | null;
    requested_at: string | null;
    started_at: string | null;
    stopped_at: string | null;
    heartbeat_at: string | null;
}

export interface TennisBotActivityRow {
    id: number;
    event_id: string;
    bot_key: TennisBotKey;
    ts: string;
    kind: string;
    payload: Record<string, unknown>;
}

export interface TennisBotsState {
    controls: TennisBotControl[];
    activity: TennisBotActivityRow[];
}

// --- schema parametri per-bot (UI: rende gli input generici) -----------------
export interface TennisBotParamField {
    key: string;
    label: string;
    step: number;
    min: number;
    max: number;
    hint: string;
    /** campo a SCELTA (stringa/bool) invece che numerico: la UI rende una <select>.
     *  I default rispecchiano ESATTAMENTE i default del bot Python (nessun cambio
     *  di comportamento finché l'utente non sceglie). */
    type?: 'number' | 'select';
    options?: { value: string; label: string }[];
    /** true = inviare come boolean ('on'→true, 'off'→false). */
    bool?: boolean;
}

export interface TennisBotDescriptor {
    key: TennisBotKey;
    name: string;
    short: string;
    /** pre-match, in-play o entrambi (badge informativo). */
    phase: 'pre-match' | 'in-play' | 'both';
    accent: 'primary' | 'secondary' | 'cyan' | 'magenta';
    defaultStake: number;
    /** parametri modificabili con i loro default validati (numerici o select). */
    params: TennisBotParamField[];
    defaults: Record<string, number | string>;
}

// NB: default validati in backtest (dossier tennis_scalper). Rifiniti dopo la lettura
// diretta dei bot Python — vedi tennis_bot_service.py per la whitelist speculare.
export const TENNIS_BOT_REGISTRY: TennisBotDescriptor[] = [
    {
        key: 'tennis_scalper',
        name: 'Tennis Scalper',
        short: 'Missione tick pre-match: 1 tick di profitto prima del via, poi stop. Maker micro-scalp sul favorito (gamba in-play OFF: bocciata dal backtest di validazione).',
        phase: 'both',
        accent: 'primary',
        defaultStake: 5,
        params: [
            { key: 'scalp_ticks', label: 'Tick profitto', step: 1, min: 1, max: 5, hint: 'target chiusura per ciclo' },
            { key: 'stop_ticks', label: 'Tick stop', step: 1, min: 1, max: 8, hint: 'tick avversi che innescano lo stop (preset validato: 3)' },
            { key: 'signal_ticks', label: 'Tick segnale', step: 1, min: 1, max: 10, hint: 'ampiezza deviazione per entrare' },
            { key: 'min_flow', label: 'Flusso min €/lato', step: 1, min: 0, max: 500, hint: 'gate volume stampato (preset validato: 2)' },
            { key: 'min_size', label: 'Size min ai best €', step: 1, min: 0, max: 2000, hint: 'liquidità minima sul touch' },
            { key: 'price_min', label: 'Quota min', step: 0.1, min: 1.01, max: 5, hint: 'sotto: code lente' },
            { key: 'price_max', label: 'Quota max', step: 0.1, min: 1.5, max: 20, hint: 'sopra: tick larghi' },
            { key: 'one_tick_per_phase', label: 'Missione 1 tick/fase', step: 0, min: 0, max: 0, type: 'select', bool: true,
              options: [{ value: 'on', label: 'on' }, { value: 'off', label: 'off' }],
              hint: '1 tick di profitto pre-match, poi stop automatico (stato "Concluso"). off = scalping continuo' },
            { key: 'inplay_tick_enabled', label: 'Gamba in-play (sperimentale)', step: 0, min: 0, max: 0, type: 'select', bool: true,
              options: [{ value: 'off', label: 'off' }, { value: 'on', label: 'on' }],
              hint: '⚠️ BOCCIATA dal backtest di validazione (1 verde/34 match, coda −13€/ciclo): tenere OFF salvo test su match ultra-liquidi' },
            { key: 'runner_filter', label: 'Runner operato', step: 0, min: 0, max: 0, type: 'select',
              options: [{ value: 'favorite', label: 'solo favorito' }, { value: 'all', label: 'entrambi' }],
              hint: 'favorito = best-back più basso al momento della quotazione; evita la doppia esposizione correlata sui 2 runner' },
        ],
        // preset live TENNIS_PARAMS (run_tennis_scalper.py) — la UI VINCE sul
        // setdefault del runner: questi default DEVONO restare allineati al preset.
        defaults: {
            scalp_ticks: 1,
            stop_ticks: 3,
            signal_ticks: 1,
            min_flow: 2,
            min_size: 5,
            price_min: 1.2,
            price_max: 6,
            one_tick_per_phase: 'on',
            inplay_tick_enabled: 'off',
            runner_filter: 'favorite',
        },
    },
    {
        key: 'tennis_pro',
        name: 'Tennis Pro',
        short: 'Direzionale score-driven: break point, serving-for-set, doppio break, favorito compresso.',
        phase: 'in-play',
        accent: 'secondary',
        defaultStake: 5,
        params: [
            { key: 'bp_target_ticks', label: 'Break: tick target', step: 1, min: 2, max: 40, hint: 'obiettivo su break point' },
            { key: 'bp_stop_ticks', label: 'Break: tick stop', step: 1, min: 1, max: 30, hint: 'stop su break point' },
            { key: 'fade_target_ticks', label: 'Fade: tick target', step: 1, min: 2, max: 40, hint: 'obiettivo fade over-reaction' },
            { key: 'min_matched', label: 'Matched min €', step: 5000, min: 0, max: 500000, hint: 'liquidità minima mercato' },
            { key: 'price_max', label: 'Quota max', step: 0.1, min: 1.1, max: 10, hint: 'non entrare sopra questa quota' },
            // fix audit #9: il bot Python distingue ("grass","fast") vs il resto (clay/hard/WTA):
            // le opzioni devono coprire TUTTE le chiavi su cui la logica si biforca.
            { key: 'surface', label: 'Superficie', step: 0, min: 0, max: 0, type: 'select',
              options: [
                  { value: 'hard', label: 'hard' },
                  { value: 'clay', label: 'clay' },
                  { value: 'grass', label: 'grass' },
                  { value: 'fast', label: 'Veloce/indoor' },
                  { value: 'wta', label: 'WTA' },
              ],
              hint: 'ATTENZIONE: su grass/veloce il bot BACKa chi serve sui break point e DISATTIVA serving-for-set / doppio break / favorito compresso (attivi su clay/hard/WTA). Imposta la superficie reale del match.' },
            // fix audit #9: hint VERITIERI — trend FLIPPA i setup di dominio in
            // trend-following (BACK del dominante), non è un filtro expected-rate.
            { key: 'trend', label: 'Trend-following', step: 0, min: 0, max: 0, type: 'select', bool: true,
              options: [{ value: 'off', label: 'off' }, { value: 'on', label: 'on' }],
              hint: 'FLIPPA i setup di dominio (serving-for-set, doppio break, set transition, favorito compresso) da LAY di reversione a BACK trend-following: cavalca il dominante invece di puntare sul rientro' },
            // fix audit #9: adapt sceglie la DIREZIONE dal regime di prezzo (Kaufman ER),
            // non riduce lo stake dopo perdite.
            { key: 'adapt', label: 'Direzione adattiva', step: 0, min: 0, max: 0, type: 'select', bool: true,
              options: [{ value: 'off', label: 'off' }, { value: 'on', label: 'on' }],
              hint: 'sceglie la DIREZIONE dei setup di dominio dal regime di prezzo live (Efficiency Ratio di Kaufman): trend → BACK del dominante, range → LAY, regime neutro → nessun ingresso. Con on ignora il flag trend' },
            { key: 'maker', label: 'Ingresso maker', step: 0, min: 0, max: 0, type: 'select', bool: true,
              options: [{ value: 'off', label: 'off' }, { value: 'on', label: 'on' }],
              hint: 'entra passivo a maker_offset tick dal best (fill non garantito)' },
        ],
        defaults: { bp_target_ticks: 5, bp_stop_ticks: 3, fade_target_ticks: 4, min_matched: 50000, price_max: 3.6,
            surface: 'grass', trend: 'off', adapt: 'off', maker: 'off' },
    },
    {
        key: 'tennis_flb',
        name: 'Tennis FLB',
        short: 'Lay del favorito estremo (favourite-longshot bias), liability minima, exit green/hold/hybrid.',
        phase: 'in-play',
        accent: 'cyan',
        defaultStake: 5,
        params: [
            { key: 'lay_max', label: 'Lay max (quota)', step: 0.01, min: 1.01, max: 1.5, hint: 'lay solo sotto questa quota' },
            { key: 'green_ticks', label: 'Tick green', step: 1, min: 1, max: 20, hint: 'green a questo profitto' },
            { key: 'green_frac', label: 'Frazione green', step: 0.1, min: 0.1, max: 1, hint: 'quota di posizione da chiudere' },
            { key: 'rearm_mult', label: 'Rearm mult', step: 0.05, min: 1, max: 2, hint: 'riarmo dopo movimento' },
            { key: 'min_matched', label: 'Matched min €', step: 5000, min: 0, max: 500000, hint: 'liquidità minima mercato' },
            { key: 'exit_mode', label: 'Uscita', step: 0, min: 0, max: 0, type: 'select',
              options: [{ value: 'hybrid', label: 'hybrid' }, { value: 'hold', label: 'hold' }, { value: 'green', label: 'green' }],
              hint: 'hold = preset col miglior backtest (direzionale, locked può restare <0); hybrid = green parziale' },
        ],
        defaults: { lay_max: 1.1, green_ticks: 8, green_frac: 0.5, rearm_mult: 1.1, min_matched: 10000,
            exit_mode: 'hybrid' },
    },
    {
        key: 'tennis_swing',
        name: 'Tennis Swing',
        short: 'Maker fade degli estremi del favorito: z-score robusto + Efficiency-Ratio + RSI.',
        phase: 'in-play',
        accent: 'magenta',
        defaultStake: 5,
        params: [
            { key: 'N', label: 'Finestra N', step: 5, min: 10, max: 120, hint: 'lookback tick-index' },
            { key: 'zin', label: 'Z ingresso', step: 0.1, min: 1, max: 4, hint: 'soglia z per entrare' },
            { key: 'er_max', label: 'ER max', step: 0.05, min: 0.1, max: 0.9, hint: 'gate regime (Efficiency Ratio)' },
            { key: 'stop_ticks', label: 'Tick stop', step: 1, min: 2, max: 30, hint: 'stop di protezione' },
            { key: 'tmax', label: 'T max (s)', step: 10, min: 20, max: 300, hint: 'time-stop posizione' },
        ],
        defaults: { N: 40, zin: 2.0, er_max: 0.4, stop_ticks: 8, tmax: 90 },
    },
];

/** get_tennis_bots_state(p_event_id, p_activity_limit) -> TennisBotsState */
export async function fetchTennisBotsState(eventId: string, activityLimit = 60): Promise<TennisBotsState> {
    const { data, error } = await supabase.rpc('get_tennis_bots_state', {
        p_event_id: eventId,
        p_activity_limit: activityLimit,
    });
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as { controls?: TennisBotControl[]; activity?: TennisBotActivityRow[] };
    return { controls: d.controls ?? [], activity: d.activity ?? [] };
}

// REALTIME bot (richiesta 16/07 "non polling, canale WS"): postgres_changes su
// tennis_bot_control + tennis_bot_activity per l'evento → il pannello ricarica
// lo stato via RPC alla notifica. Richiede realtime_orders_bots.sql.
export function subscribeTennisBots(eventId: string, cb: () => void): () => void {
    const channel = supabase
        .channel(`tennis_bots:${eventId}:${Math.random().toString(36).slice(2, 9)}`)
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'tennis_bot_control', filter: `event_id=eq.${eventId}` },
            () => cb(),
        )
        .on(
            'postgres_changes',
            { event: '*', schema: 'public', table: 'tennis_bot_activity', filter: `event_id=eq.${eventId}` },
            () => cb(),
        )
        .subscribe();
    return () => {
        supabase.removeChannel(channel);
    };
}

/** tennis_bot_arm(...) -> TennisBotControl */
export async function armTennisBot(
    eventId: string,
    botKey: TennisBotKey,
    dryRun: boolean,
    stake: number,
    params: Record<string, number | string | boolean>,
): Promise<TennisBotControl> {
    const { data, error } = await supabase.rpc('tennis_bot_arm', {
        p_event_id: eventId,
        p_bot_key: botKey,
        p_dry_run: dryRun,
        p_stake: stake,
        p_params: params as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as TennisBotControl;
}

/** tennis_bot_disarm(...) -> TennisBotControl */
export async function disarmTennisBot(eventId: string, botKey: TennisBotKey): Promise<TennisBotControl> {
    const { data, error } = await supabase.rpc('tennis_bot_disarm', {
        p_event_id: eventId,
        p_bot_key: botKey,
    });
    if (error) throw new Error(error.message);
    return data as unknown as TennisBotControl;
}

// ----------------------------------------------------------------- etichette
export const TENNIS_FOLLOW_STATUS_LABEL: Record<TennisFollowStatus, string> = {
    PENDING: 'In attesa',
    STREAMING: 'In streaming',
    CLOSED: 'Chiusa',
    UPLOADED: 'Caricata',
    ERROR: 'Errore',
};

export const TENNIS_BOT_STATUS_LABEL: Record<TennisBotStatus, string> = {
    idle: 'Inattivo',
    requested: 'Richiesto',
    arming: 'Armamento…',
    armed: 'Armato',
    running: 'Operativo',
    stopping: 'Arresto…',
    stopped: 'Fermato',
    done: 'Concluso',
    error: 'Errore',
};
