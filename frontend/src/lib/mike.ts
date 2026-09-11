// ============================================================================
// mike.ts — data-layer della sezione MIKE (bot Under 3.5 / Over 4.5).
//
// Specchio 1:1 della whitelist backend Betfair/mike/config.py (PARAM_SPEC):
// ogni parametro qui ha default, passo, min/max o scelte identici. Le scritture
// passano SOLO da RPC owner-only (mike_activate / mike_stop / mike_update_params
// / mike_request); le letture da get_mike_state (control + events + trades +
// activity + aggregates) e dalle tabelle in sola lettura. UN canale realtime.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

export type MikeStatus = 'idle' | 'running' | 'stopping' | 'stopped' | 'error';
export type MikeMode = 'paper' | 'live';
export type MikeRequestKind = 'cashout' | 'flatten' | 'skip_event' | 'resume_event' | 'cancel';

export const MIKE_STATES = [
    'WATCH', 'PRE_ENTRY_PENDING', 'PRE_OPEN', 'PRE_GREEN_PENDING', 'HOLD',
    'PRE_LAST_ENTRY_PENDING', 'IDLE_LIVE', 'LIVE_UNCOVERED', 'LIVE_COVER_PENDING',
    'LIVE_COVERED', 'LIVE_CLOSING', 'FLAT', 'REENTRY_PENDING', 'REENTRY_OPEN',
    'REENTRY_GREEN_PENDING', 'SETTLING', 'SETTLED', 'ERROR', 'SKIPPED',
] as const;
export type MikeState = typeof MIKE_STATES[number];
export const MIKE_TERMINAL_STATES: readonly MikeState[] = ['SETTLED', 'ERROR', 'SKIPPED'];

export interface MikeStats {
    events_feed: number;
    events_tracked: number;
    by_state: Record<string, number>;
    trades_open: number;
    open_liability: number;
    realized_today: number;
    realized_total: number;
    scanner_age_s: number | null;
    last_cycle: string;
    dry: boolean;
    mode: string;
}

export interface MikeControl {
    id: number;
    status: MikeStatus;
    mode: MikeMode;
    params: Record<string, unknown> | null;
    stats: MikeStats | null;
    error: string | null;
    started_at: string | null;
    stopped_at: string | null;
    heartbeat_at: string | null;
    updated_at: string;
}

export interface MikeLeg {
    role: string;
    market: 'OU35' | 'OU45';
    selection: 'UNDER' | 'OVER';
    side: 'back' | 'lay';
    price: number;
    size: number;
    matched: number;
    avg_price: number | null;
    ref: string;
    status: 'pending' | 'open' | 'cancelled' | 'settled';
    placed_at: number;
    persistence: string;
    cycle_no: number;
    final: boolean;
    archived: boolean;
}

export interface MikeBook {
    best_back: number | null;
    back_size: number;
    best_lay: number | null;
    lay_size: number;
    status: string;
    inplay: boolean;
    bet_delay: number;
}

export interface MikeCashout {
    net: number;
    gross: number;
    base: number;
    complete: boolean;
    pct: number | null;
}

export interface MikeLive {
    minute: number | null;
    goals: number | null;
    inplay: boolean;
    ht: boolean;
    hazard: number | null;
    p4_market: number | null;
    p4_model: number | null;
    cashout: MikeCashout | null;
    cover_wait: Record<string, unknown> | null;
    pnl_by_total: Record<string, number>;
    books: Record<string, MikeBook>;
    feed_fresh: boolean;
}

export interface MikeDossier {
    fixture_id: number | null;
    league_id: number | null;
    lambda_home: number | null;
    lambda_away: number | null;
    rho: number | null;
    p4_pre: number | null;
    p_under35_cal: number | null;
    source: string;
}

export interface MikeEvent {
    event_id: string;
    fixture_id: number | null;
    event_name: string | null;
    competition: string | null;
    league_id: number | null;
    ko_at: string | null;
    mode: MikeMode;
    markets: Record<string, { market_id: string | null }>;
    state: MikeState;
    cycle_no: number;
    entry_price_initial: number | null;
    dossier: Partial<MikeDossier> | null;
    live: Partial<MikeLive> | null;
    positions: MikeLeg[];
    ctx: Record<string, unknown> | null;
    skipped: boolean;
    settled_pnl: number | null;
    updated_at: string;
}

export interface MikeTrade {
    id: number;
    event_id: string;
    event_name: string | null;
    strategy: string;
    role: string | null;
    cycle_no: number;
    market_type: string | null;
    selection_name: string | null;
    side: 'back' | 'lay';
    mode: MikeMode;
    price: number | null;
    size: number | null;
    liability: number | null;
    status: 'pending' | 'open' | 'hedged' | 'won' | 'lost' | 'void' | 'error';
    pnl: number;
    placed_at: string;
    settled_at: string | null;
    signal_key: string | null;
    meta: Record<string, unknown> | null;
}

export interface MikeActivity {
    id: number;
    ts: string;
    event_id: string | null;
    kind: string;
    payload: Record<string, unknown>;
}

export interface MikeAggregates {
    realized_total: number;
    realized_today: number;
    open_liability: number;
    open_count: number;
    won: number;
    lost: number;
}

export interface MikeStateView {
    control: MikeControl | null;
    events: MikeEvent[];
    trades: MikeTrade[];
    activity: MikeActivity[];
    aggregates: MikeAggregates | null;
}

// ------------------------------------------------------------- parametri
export type MikeParamGroup = 'generale' | 'pre' | 'cover' | 'cashout' | 'uscite' | 'reentry' | 'rischio';

export type MikeParamField =
    | { key: string; label: string; kind: 'number'; step: number; min: number; max: number; hint: string; group: MikeParamGroup }
    | { key: string; label: string; kind: 'bool'; hint: string; group: MikeParamGroup }
    | { key: string; label: string; kind: 'choice'; choices: readonly string[]; hint: string; group: MikeParamGroup }
    | { key: string; label: string; kind: 'text'; hint: string; group: MikeParamGroup };

export const MIKE_PARAM_GROUP_LABEL: Record<MikeParamGroup, string> = {
    generale: 'Generale', pre: 'Pre-match', cover: 'Copertura Over 4.5', cashout: 'Cash-out globale',
    uscite: 'Uscite HT / 2T', reentry: 'Re-ingresso (gol + 3.5)', rischio: 'Rischio',
};

/** SPECCHIO di Betfair/mike/config.py PARAM_SPEC (stesso ordine, stessi limiti). */
export const MIKE_PARAM_FIELDS: readonly MikeParamField[] = [
    { key: 'stake', label: 'Stake Under 3.5 (€)', kind: 'number', step: 0.5, min: 0.5, max: 500, hint: 'importo LIBERO (anche 1,23): sotto il minimo .it si usa il place-and-trim', group: 'generale' },
    { key: 'commission_pct', label: 'Commissione %', kind: 'number', step: 0.5, min: 0, max: 20, hint: 'aliquota Betfair (default 5%)', group: 'generale' },
    { key: 'max_matches', label: 'Partite max seguite', kind: 'number', step: 1, min: 1, max: 90, hint: 'tetto delle partite in finestra seguite in parallelo', group: 'generale' },
    { key: 'entry_hours_before_ko', label: 'Finestra pre-match (ore prima del KO)', kind: 'number', step: 0.25, min: 0.25, max: 12, hint: 'da quante ore prima del calcio d’inizio il bot lavora la partita', group: 'generale' },
    { key: 'catalogue_refresh_s', label: 'Refresh catalogo (s)', kind: 'number', step: 30, min: 60, max: 3600, hint: 'cadenza di scoperta delle nuove partite', group: 'generale' },
    { key: 'min_total_matched', label: 'Volume min. mercato (€)', kind: 'number', step: 100, min: 0, max: 1_000_000, hint: 'partite con meno scambiato non vengono seguite', group: 'generale' },
    { key: 'competition_filter', label: 'Filtro competizioni', kind: 'text', hint: 'elenco separato da virgole (vuoto = tutte), es. "serie a, premier"', group: 'generale' },
    { key: 'decide_min_interval_ms', label: 'Cadenza decisioni (ms)', kind: 'number', step: 100, min: 100, max: 5000, hint: 'intervallo minimo fra due decisioni sulla stessa partita', group: 'generale' },
    { key: 'feed_max_age_s', label: 'Feed: età max riga (s)', kind: 'number', step: 1, min: 3, max: 60, hint: 'riga più vecchia e scanner fermo = niente nuovi ingressi', group: 'generale' },
    { key: 'pre_enabled', label: 'Pre-match attivo', kind: 'bool', hint: 'off = nessun ingresso pre-match', group: 'pre' },
    { key: 'pre_entry_price_min', label: 'Quota Under 3.5 MIN', kind: 'number', step: 0.01, min: 1.01, max: 20, hint: 'sotto: rendimento troppo basso', group: 'pre' },
    { key: 'pre_entry_price_max', label: 'Quota Under 3.5 MAX', kind: 'number', step: 0.05, min: 1.01, max: 20, hint: 'sopra: partita troppo aperta', group: 'pre' },
    { key: 'pre_min_back_size_factor', label: 'Liquidità min. (× stake)', kind: 'number', step: 0.1, min: 0.5, max: 5, hint: '1 = la size al best deve coprire lo stake intero', group: 'pre' },
    { key: 'pre_max_spread_ticks', label: 'Spread max (tick)', kind: 'number', step: 1, min: 1, max: 20, hint: 'ore prima del KO i book sono larghi: l’uscita non paga lo spread (lay appoggiata)', group: 'pre' },
    { key: 'pre_green_ticks', label: 'Green-up a (+tick)', kind: 'number', step: 1, min: 1, max: 10, hint: '2 = lay 2 tick sotto l’ingresso, profitto spalmato su entrambi gli esiti', group: 'pre' },
    { key: 'pre_exit_mode', label: 'Chiusura pre-match', kind: 'choice', choices: ['resting', 'taker'], hint: 'resting = lay appoggiata SUBITO sul book (paper: abbinata solo se il mercato scambia sotto); taker = chiude al best quando i tick ci sono', group: 'pre' },
    { key: 'pre_entry_ttl_s', label: 'TTL ingresso non abbinato (s)', kind: 'number', step: 5, min: 5, max: 3600, hint: 'oltre: ordine ritirato', group: 'pre' },
    { key: 'pre_max_cycles', label: 'Cicli max per partita', kind: 'number', step: 1, min: 0, max: 100, hint: 'ingresso → green → ingresso…', group: 'pre' },
    { key: 'pre_reentry_cooldown_s', label: 'Pausa dopo un green (s)', kind: 'number', step: 5, min: 0, max: 3600, hint: 'attesa prima del ciclo successivo', group: 'pre' },
    { key: 'pre_last_entry_min', label: 'Ultimo ingresso (min prima del KO)', kind: 'number', step: 1, min: 1, max: 120, hint: 'in profitto chiude e rientra in PERSIST; in perdita tiene', group: 'pre' },
    { key: 'last_entry_persist', label: 'Ultimo ingresso in PERSIST', kind: 'bool', hint: 'la posizione entra in live', group: 'pre' },
    { key: 'last_entry_ticks_above', label: 'Ultimo ingresso: tick sopra il best', kind: 'number', step: 1, min: 0, max: 3, hint: '0 = taker al best', group: 'pre' },
    { key: 'cancel_unmatched_after_ko_s', label: 'Cancella residuo PERSIST dopo KO (s)', kind: 'number', step: 10, min: 0, max: 900, hint: 'evita fill su spike dopo un gol', group: 'pre' },
    { key: 'cover_enabled', label: 'Copertura attiva', kind: 'bool', hint: 'off = Under nudo in live', group: 'cover' },
    { key: 'cover_profit_factor', label: 'Fattore copertura', kind: 'number', step: 0.05, min: 1, max: 3, hint: '1.2 = se vince l’Over 4.5 il netto è +20% dello stake Under', group: 'cover' },
    { key: 'cover_policy', label: 'Quando coprire', kind: 'choice', choices: ['auto', 'immediate', 'wait'], hint: 'auto = subito o attesa secondo hazard/P(4); immediate = subito; wait = fino al minuto max', group: 'cover' },
    { key: 'cover_wait_hazard_max', label: 'Attendi se hazard 3′ ≤', kind: 'number', step: 0.01, min: 0, max: 1, hint: 'hazard = MAX fra Atlante empirico e modello λ (× pressione corner/cartellini): la fonte più prudente comanda', group: 'cover' },
    { key: 'cover_wait_max_min', label: 'Attendi al massimo fino al minuto', kind: 'number', step: 1, min: 0, max: 45, hint: 'poi si copre comunque (mai a mercato a tempo indefinito)', group: 'cover' },
    { key: 'cover_wait_p4_max', label: 'Attendi se P(4) mercato ≤', kind: 'number', step: 0.01, min: 0, max: 1, hint: 'P(esattamente 4 gol) implicita dalle due linee', group: 'cover' },
    { key: 'cover_good_price', label: 'Copri subito se Over 4.5 ≥', kind: 'number', step: 0.5, min: 1.01, max: 50, hint: 'quota già buona: aspettare non paga il rischio', group: 'cover' },
    { key: 'cover_wait_min_gain_pct', label: 'Attendi solo se risparmio atteso ≥ %', kind: 'number', step: 1, min: 0, max: 100, hint: 'quanto costerebbe di meno la copertura fra N minuti senza gol (modello)', group: 'cover' },
    { key: 'cover_wait_step_min', label: 'Orizzonte del risparmio (min)', kind: 'number', step: 1, min: 1, max: 20, hint: 'N minuti su cui si stima il risparmio', group: 'cover' },
    { key: 'cover_postgoal_delay_s', label: 'Dopo un gol attendi (s)', kind: 'number', step: 5, min: 0, max: 300, hint: 'riprezzo post-sospensione', group: 'cover' },
    { key: 'cover_max_goals', label: 'Nessuna copertura oltre (gol)', kind: 'number', step: 1, min: 0, max: 4, hint: 'con più gol la gestione passa al cash-out / HT', group: 'cover' },
    { key: 'cover_rounding', label: 'Arrotondamento (se non esatto)', kind: 'choice', choices: ['ceil', 'floor', 'nearest'], hint: 'usato solo con importi esatti OFF', group: 'cover' },
    { key: 'cover_max_overshoot_pct', label: 'Sovracopertura max %', kind: 'number', step: 5, min: 0, max: 200, hint: 'oltre: si logga cover_overshoot', group: 'cover' },
    { key: 'exact_sizes', label: 'Importi esatti al centesimo', kind: 'bool', hint: 'on = 3,61 € reali (place-and-trim); off = legalizza a 0,50', group: 'cover' },
    { key: 'cashout_profit_pct', label: 'Chiudi tutto a profitto ≥ %', kind: 'number', step: 0.5, min: 0.5, max: 50, hint: 'somma dei P&L bloccabili di Under 3.5 + Over 4.5', group: 'cashout' },
    { key: 'cashout_base', label: 'Base della %', kind: 'choice', choices: ['total', 'under'], hint: 'total = stake Under + copertura; under = solo stake Under', group: 'cashout' },
    { key: 'cashout_place_at_ticks', label: 'Chiusura N tick oltre il best', kind: 'number', step: 1, min: 0, max: 3, hint: 'fill più sicuro, P&L leggermente peggiore', group: 'cashout' },
    { key: 'close_retry_s', label: 'Riprezzo chiusura ogni (s)', kind: 'number', step: 5, min: 1, max: 600, hint: 'residuo non abbinato', group: 'cashout' },
    { key: 'close_max_attempts', label: 'Tentativi max chiusura', kind: 'number', step: 1, min: 1, max: 100, hint: 'poi resta in attesa (chiusura manuale)', group: 'cashout' },
    { key: 'ht_loss_exit_enabled', label: 'Uscita HT attiva', kind: 'bool', hint: 'a fine 1T con 2-4 gol', group: 'uscite' },
    { key: 'ht_loss_pct', label: 'HT: perdita tollerata %', kind: 'number', step: 1, min: 0, max: 100, hint: 'chiude comunque se la perdita è entro questa % del capitale', group: 'uscite' },
    { key: 'ht_loss_goals_min', label: 'HT: gol min', kind: 'number', step: 1, min: 0, max: 8, hint: '', group: 'uscite' },
    { key: 'ht_loss_goals_max', label: 'HT: gol max', kind: 'number', step: 1, min: 0, max: 8, hint: '', group: 'uscite' },
    { key: 'h2_loss_exit_enabled', label: 'Uscita 2T attiva', kind: 'bool', hint: 'stessa regola nel secondo tempo', group: 'uscite' },
    { key: 'h2_loss_pct', label: '2T: perdita tollerata %', kind: 'number', step: 1, min: 0, max: 100, hint: '', group: 'uscite' },
    { key: 'h2_loss_from_min', label: '2T: dal minuto', kind: 'number', step: 1, min: 45, max: 100, hint: '', group: 'uscite' },
    { key: 'h2_loss_to_min', label: '2T: fino al minuto', kind: 'number', step: 1, min: 45, max: 100, hint: '', group: 'uscite' },
    { key: 'reentry_enabled', label: 'Re-ingresso attivo', kind: 'bool', hint: 'dopo una chiusura in profitto, con 1 gol, sull’Under 4.5', group: 'reentry' },
    { key: 'reentry_green_ticks', label: 'Green re-ingresso (+tick)', kind: 'number', step: 1, min: 1, max: 10, hint: '', group: 'reentry' },
    { key: 'reentry_max_goals', label: 'Gol max per il re-ingresso', kind: 'number', step: 1, min: 0, max: 1, hint: '1 = linea 4.5 (unica nel feed)', group: 'reentry' },
    { key: 'reentry_until_min', label: 'Re-ingresso entro il minuto', kind: 'number', step: 1, min: 0, max: 100, hint: '', group: 'reentry' },
    { key: 'reentry_exit_until_min', label: 'Chiudi re-ingresso entro il minuto', kind: 'number', step: 1, min: 0, max: 100, hint: 'oltre: chiusura al best', group: 'reentry' },
    { key: 'reentry_price_min_over_entry', label: 'Solo se U4.5 > quota iniziale U3.5', kind: 'bool', hint: 'regola della specifica', group: 'reentry' },
    { key: 'reentry_hold_if_loss', label: 'Tieni il re-ingresso se in perdita', kind: 'bool', hint: 'off = chiude comunque al minuto limite', group: 'reentry' },
    { key: 'stream_extra_lines', label: 'Linee extra (5.5+)', kind: 'bool', hint: 'non ancora supportato dal feed', group: 'reentry' },
    { key: 'settle_confirm_s', label: 'Conferma punteggio finale (s)', kind: 'number', step: 10, min: 0, max: 600, hint: '', group: 'rischio' },
    { key: 'max_open_matches', label: 'Partite aperte max', kind: 'number', step: 1, min: 1, max: 90, hint: 'partite con posizione contemporaneamente', group: 'rischio' },
    { key: 'daily_loss_stop', label: 'Stop perdita giornaliera (€)', kind: 'number', step: 5, min: 0, max: 100_000, hint: '0 = off', group: 'rischio' },
    { key: 'max_liability_per_match', label: 'Cap capitale per partita (€)', kind: 'number', step: 5, min: 0, max: 100_000, hint: '0 = off; clamp anche dentro il motore', group: 'rischio' },
    { key: 'event_loss_cap_pct', label: 'Cap perdita per partita %', kind: 'number', step: 5, min: 0, max: 500, hint: 'oltre: chiusura forzata', group: 'rischio' },
    { key: 'skip_log_interval_s', label: 'Log skip ogni (s)', kind: 'number', step: 30, min: 10, max: 3600, hint: '', group: 'rischio' },
];

export const MIKE_PARAM_DEFAULTS: Record<string, number | boolean | string> = {
    stake: 10, commission_pct: 5, max_matches: 40, entry_hours_before_ko: 3, catalogue_refresh_s: 300,
    min_total_matched: 2000, competition_filter: '', decide_min_interval_ms: 500, feed_max_age_s: 15,
    pre_enabled: true, pre_entry_price_min: 1.3, pre_entry_price_max: 3, pre_min_back_size_factor: 1,
    pre_max_spread_ticks: 6, pre_green_ticks: 2, pre_exit_mode: 'resting', pre_entry_ttl_s: 60,
    pre_max_cycles: 10, pre_reentry_cooldown_s: 60, pre_last_entry_min: 10, last_entry_persist: true,
    last_entry_ticks_above: 0, cancel_unmatched_after_ko_s: 120,
    cover_enabled: true, cover_profit_factor: 1.2, cover_policy: 'auto', cover_wait_hazard_max: 0.06,
    cover_wait_max_min: 10, cover_wait_p4_max: 0.16, cover_good_price: 7, cover_wait_min_gain_pct: 8,
    cover_wait_step_min: 5, cover_postgoal_delay_s: 45, cover_max_goals: 2,
    cover_rounding: 'ceil', cover_max_overshoot_pct: 30, exact_sizes: true,
    cashout_profit_pct: 5, cashout_base: 'total', cashout_place_at_ticks: 0, close_retry_s: 10, close_max_attempts: 20,
    ht_loss_exit_enabled: true, ht_loss_pct: 25, ht_loss_goals_min: 2, ht_loss_goals_max: 4,
    h2_loss_exit_enabled: true, h2_loss_pct: 25, h2_loss_from_min: 46, h2_loss_to_min: 85,
    reentry_enabled: true, reentry_green_ticks: 2, reentry_max_goals: 1, reentry_until_min: 45,
    reentry_exit_until_min: 80, reentry_price_min_over_entry: true, reentry_hold_if_loss: false,
    stream_extra_lines: false,
    settle_confirm_s: 60, max_open_matches: 10, daily_loss_stop: 50, max_liability_per_match: 0,
    event_loss_cap_pct: 100, skip_log_interval_s: 300,
};

export type MikeParams = Record<string, number | boolean | string>;

/** merge DIFENSIVO: chiavi ignote scartate, tipi sbagliati → default, numeri clampati. */
export function mergeMikeParams(raw: unknown): MikeParams {
    const r = (raw ?? {}) as Record<string, unknown>;
    const out: MikeParams = { ...MIKE_PARAM_DEFAULTS };
    for (const f of MIKE_PARAM_FIELDS) {
        const v = r[f.key];
        if (v === undefined || v === null) continue;
        if (f.kind === 'number') {
            const n = typeof v === 'number' ? v : Number(v);
            if (Number.isFinite(n)) out[f.key] = Math.min(f.max, Math.max(f.min, n));
        } else if (f.kind === 'bool') {
            if (typeof v === 'boolean') out[f.key] = v;
            else if (typeof v === 'string') out[f.key] = ['1', 'true', 'yes', 'on'].includes(v.toLowerCase());
        } else if (f.kind === 'choice') {
            if (typeof v === 'string' && f.choices.includes(v)) out[f.key] = v;
        } else if (typeof v === 'string') {
            out[f.key] = v.trim();
        }
    }
    return out;
}

// -------------------------------------------------------------- fasi / UI
export interface PhaseMeta { label: string; cls: string; dot: string; group: 'pre' | 'live' | 'flat' | 'done' | 'off' }

export const MIKE_PHASE_META: Record<MikeState, PhaseMeta> = {
    WATCH: { label: 'IN ATTESA', cls: 'bg-teal-500/15 text-teal-200 border-teal-400/40', dot: 'bg-teal-400', group: 'pre' },
    PRE_ENTRY_PENDING: { label: 'INGRESSO…', cls: 'bg-teal-500/20 text-teal-200 border-teal-400/50 animate-pulse', dot: 'bg-teal-400 animate-pulse', group: 'pre' },
    PRE_OPEN: { label: 'UNDER APERTO (PRE)', cls: 'bg-teal-500/25 text-teal-100 border-teal-300/60', dot: 'bg-teal-300', group: 'pre' },
    PRE_GREEN_PENDING: { label: 'GREEN-UP…', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50 animate-pulse', dot: 'bg-emerald-400 animate-pulse', group: 'pre' },
    HOLD: { label: 'HOLD → LIVE', cls: 'bg-amber-500/20 text-amber-200 border-amber-400/50', dot: 'bg-amber-400', group: 'pre' },
    PRE_LAST_ENTRY_PENDING: { label: 'ULTIMO INGRESSO (PERSIST)', cls: 'bg-teal-500/25 text-teal-100 border-teal-300/60', dot: 'bg-teal-300', group: 'pre' },
    IDLE_LIVE: { label: 'LIVE · NESSUNA POSIZIONE', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40', dot: 'bg-white/30', group: 'live' },
    LIVE_UNCOVERED: { label: 'LIVE · SCOPERTO', cls: 'bg-sky-500/20 text-sky-200 border-sky-400/50', dot: 'bg-sky-400', group: 'live' },
    LIVE_COVER_PENDING: { label: 'COPERTURA…', cls: 'bg-violet-500/20 text-violet-200 border-violet-400/50 animate-pulse', dot: 'bg-violet-400 animate-pulse', group: 'live' },
    LIVE_COVERED: { label: 'LIVE · COPERTO', cls: 'bg-violet-500/25 text-violet-100 border-violet-300/60', dot: 'bg-violet-300', group: 'live' },
    LIVE_CLOSING: { label: 'CHIUSURA…', cls: 'bg-rose-500/20 text-rose-200 border-rose-400/50 animate-pulse', dot: 'bg-rose-400 animate-pulse', group: 'live' },
    FLAT: { label: 'FLAT', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50', dot: 'bg-emerald-400', group: 'flat' },
    REENTRY_PENDING: { label: 'RE-INGRESSO…', cls: 'bg-teal-500/20 text-teal-200 border-teal-400/50 animate-pulse', dot: 'bg-teal-400 animate-pulse', group: 'live' },
    REENTRY_OPEN: { label: 'RE-INGRESSO U4.5', cls: 'bg-teal-500/25 text-teal-100 border-teal-300/60', dot: 'bg-teal-300', group: 'live' },
    REENTRY_GREEN_PENDING: { label: 'GREEN RE-INGRESSO…', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50 animate-pulse', dot: 'bg-emerald-400 animate-pulse', group: 'live' },
    SETTLING: { label: 'REGOLAMENTO…', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40', dot: 'bg-white/30', group: 'done' },
    SETTLED: { label: 'REGOLATA', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40', dot: 'bg-white/30', group: 'done' },
    ERROR: { label: 'ERRORE', cls: 'bg-red-500/20 text-red-300 border-red-500/50', dot: 'bg-red-500', group: 'off' },
    SKIPPED: { label: 'SALTATA', cls: 'bg-slate-600/30 text-slate-400 border-slate-500/40', dot: 'bg-white/20', group: 'off' },
};

export function phaseMeta(state: string | null | undefined): PhaseMeta {
    return MIKE_PHASE_META[(state ?? 'WATCH') as MikeState] ?? MIKE_PHASE_META.WATCH;
}

/** ordine delle card: live con posizione, poi live, poi pre-match per KO, poi chiuse */
export function phaseRank(state: string | null | undefined): number {
    const g = phaseMeta(state).group;
    return g === 'live' ? 0 : g === 'flat' ? 1 : g === 'pre' ? 2 : g === 'done' ? 3 : 4;
}

export function sortEvents(events: readonly MikeEvent[]): MikeEvent[] {
    return [...events].sort((a, b) => {
        const r = phaseRank(a.state) - phaseRank(b.state);
        if (r !== 0) return r;
        const ka = a.ko_at ? Date.parse(a.ko_at) : Infinity;
        const kb = b.ko_at ? Date.parse(b.ko_at) : Infinity;
        return ka - kb;
    });
}

/** % del valore di cash-out rispetto alla base (null se base ≤ 0) */
export function cashoutPct(value: number | null | undefined, base: number | null | undefined): number | null {
    if (value == null || base == null) return null;
    const v = Number(value), b = Number(base);
    if (!Number.isFinite(v) || !Number.isFinite(b) || b <= 0) return null;
    return Math.round((v / b) * 1000) / 10;
}

/** gambe VIVE (non archiviate) con capitale a rischio */
export function activeLegs(ev: MikeEvent): MikeLeg[] {
    return (ev.positions ?? []).filter((l) => !l.archived && (l.matched > 0 || l.status === 'pending'));
}

export function investedOf(ev: MikeEvent): number {
    const roles = new Set(['under_entry', 'under_last', 'over_cover', 'reentry']);
    return activeLegs(ev).filter((l) => l.side === 'back' && roles.has(l.role)).reduce((s, l) => s + Number(l.matched || 0), 0);
}

export const MIKE_ROLE_LABEL: Record<string, string> = {
    under_entry: 'Ingresso Under 3.5', under_green: 'Green-up Under 3.5', under_last: 'Ultimo ingresso (PERSIST)',
    over_cover: 'Copertura Over 4.5', under_close: 'Chiusura Under 3.5', over_close: 'Chiusura Over 4.5',
    reentry: 'Re-ingresso Under 4.5', reentry_green: 'Green re-ingresso', manual_close: 'Chiusura manuale',
};

export function roleLabel(role: string | null | undefined): string {
    return (role && MIKE_ROLE_LABEL[role]) || role || '—';
}

export function legSelectionLabel(l: MikeLeg): string {
    const line = l.market === 'OU35' ? '3.5' : '4.5';
    return `${l.selection === 'UNDER' ? 'Under' : 'Over'} ${line}`;
}

// -------------------------------------------------------------------- RPC
export async function activateMike(mode: MikeMode, params?: MikeParams): Promise<MikeControl> {
    const { data, error } = await supabase.rpc('mike_activate', { p_mode: mode, p_params: (params ?? null) as never });
    if (error) throw new Error(error.message);
    return data as unknown as MikeControl;
}

export async function stopMike(): Promise<MikeControl> {
    const { data, error } = await supabase.rpc('mike_stop', {});
    if (error) throw new Error(error.message);
    return data as unknown as MikeControl;
}

export async function updateMikeParams(params: MikeParams, mode?: MikeMode): Promise<MikeControl> {
    const { data, error } = await supabase.rpc('mike_update_params', {
        p_params: params as never, p_mode: (mode ?? null) as never,
    });
    if (error) throw new Error(error.message);
    return data as unknown as MikeControl;
}

export async function fetchMikeState(): Promise<MikeStateView> {
    const { data, error } = await supabase.rpc('get_mike_state', {});
    if (error) throw new Error(error.message);
    const d = (data ?? {}) as Partial<MikeStateView>;
    return {
        control: d.control ?? null,
        events: Array.isArray(d.events) ? d.events : [],
        trades: Array.isArray(d.trades) ? d.trades : [],
        activity: Array.isArray(d.activity) ? d.activity : [],
        aggregates: d.aggregates ?? null,
    };
}

export async function fetchMikeTrades(limit = 300): Promise<MikeTrade[]> {
    const { data, error } = await supabase.rpc('get_mike_trades', { p_limit: limit });
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as MikeTrade[];
}

export async function requestMike(kind: MikeRequestKind, payload: Record<string, unknown>): Promise<number> {
    const { data, error } = await supabase.rpc('mike_request', { p_kind: kind, p_payload: payload as never });
    if (error) throw new Error(error.message);
    return data as unknown as number;
}

export interface MikeRequest {
    id: number; kind: MikeRequestKind; payload: Record<string, unknown>;
    status: 'pending' | 'processing' | 'done' | 'error'; result: Record<string, unknown> | null;
    created_at: string;
}

export async function fetchMikeRequests(limit = 30): Promise<MikeRequest[]> {
    const { data, error } = await supabase.from('mike_requests').select('*').order('id', { ascending: false }).limit(limit);
    if (error) throw new Error(error.message);
    return (data ?? []) as unknown as MikeRequest[];
}

/** richiesta in volo per (evento, kind): mai un doppio comando */
export function requestInFlight(eventId: string, kind: MikeRequestKind, requests: readonly MikeRequest[]): boolean {
    return requests.some((r) => r.kind === kind && (r.status === 'pending' || r.status === 'processing')
        && String(r.payload?.event_id ?? '') === eventId);
}

// --------------------------------------------------------------- realtime
/** UN canale per control + events + trades + requests (mai N canali). */
export function subscribeMike(onChange: () => void): () => void {
    const channel = supabase
        .channel('mike-live')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'mike_control' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'mike_events' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'mike_trades' }, onChange)
        .on('postgres_changes', { event: '*', schema: 'public', table: 'mike_requests' }, onChange)
        .subscribe();
    return () => { void supabase.removeChannel(channel); };
}

// ------------------------------------------------------------ settlement
/** eventi regolati NUOVI rispetto a `seen` (aggiornato in place); al primo giro solo memorizza. */
export function detectSettledEvents(events: readonly MikeEvent[], seen: Set<string>, firstLoad: boolean): MikeEvent[] {
    const fresh: MikeEvent[] = [];
    for (const e of events) {
        if (e.state !== 'SETTLED') continue;
        if (seen.has(e.event_id)) continue;
        seen.add(e.event_id);
        if (!firstLoad) fresh.push(e);
    }
    return fresh;
}
