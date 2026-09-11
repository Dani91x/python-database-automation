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
import { fmtMoney, fmtOdds, fmtPct, fmtTime } from '@/lib/format';
import { sideMeta, T, type ActivityMeta } from '@/lib/tradeStatus';

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
    daily_stop?: boolean;
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
    /** `pending_reconcile` = esito IGNOTO su Betfair (C3): mai trattata come annullata */
    status: 'pending' | 'pending_reconcile' | 'open' | 'cancelled' | 'settled';
    placed_at: number;
    persistence: string;
    cycle_no: number;
    final: boolean;
    archived: boolean;
    /** ref della gamba che questa chiude (chiusure/green) */
    closes_ref?: string | null;
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

export interface MikeCashoutSmart {
    enabled: boolean;
    floor?: number;
    near?: boolean;
    hot?: boolean;
    hazard?: number | null;
    pressure?: number;
    cv_goal?: number;
    cv_later?: number;
    h_step?: number;
    ev_hold?: number;
    trigger?: string;
}

export interface MikeCashout {
    net: number;
    gross: number;
    base: number;
    complete: boolean;
    pct: number | null;
    /** P&L bloccabile NETTO per selezione ("OU35|UNDER" → €), dal servizio (M5) */
    per?: Record<string, number> | null;
    /** lo stesso valore al LORDO della commissione (solo tooltip) */
    per_gross?: Record<string, number> | null;
    /** selezioni con esito GIÀ deciso (valgono 0/1 senza prezzo, C2) */
    decided?: string[] | null;
    /** aliquota applicata dal servizio (frazione, es. 0,05) */
    commission?: number | null;
    /** soglia di chiusura automatica in punti % (parametro del servizio) */
    target_pct?: number | null;
    smart?: MikeCashoutSmart | null;
}

export interface MikeLossExit {
    mode: 'model' | 'fixed';
    window?: string;
    ev_hold?: number;
    p4?: number;
    p4_model?: number | null;
    p4_emp?: number | null;
    p4_market?: number | null;
    premium?: number;
    threshold?: number;
    sources?: string[];
    missing?: boolean;
    beyond_cap?: boolean;
    pct?: number;
}

export interface MikeLive {
    minute: number | null;
    goals: number | null;
    /** età della riga di feed di QUESTA partita in secondi (diagnostica C1/H6) */
    feed_age_s?: number | null;
    /** età dello scanner in secondi (comune a tutte le partite) */
    scanner_age_s?: number | null;
    /** linee assenti nel feed ("OU45|OVER"…): niente copertura né cash out */
    lines_missing?: string[] | null;
    feed_incomplete?: boolean;
    /** almeno un ordine con esito ignoto su Betfair (C3) */
    reconcile_pending?: boolean;
    /** liability NETTA della partita (M4) */
    liability?: number | null;
    /** P&L già bloccato sulla partita */
    locked?: number | null;
    /** il rientro è stato disabilitato (cash out manuale pre-KO, H1) */
    no_reentry?: boolean;
    total_matched?: number | null;
    p_over45_model?: number | null;
    p_total_model?: Record<string, number> | null;
    p_total_emp?: Record<string, number> | null;
    ht_score?: [number, number] | null;
    loss_exit?: MikeLossExit | null;
    score_home?: number | null;
    score_away?: number | null;
    red_home?: number;
    red_away?: number;
    pressure?: number | null;
    hazard_atlas?: number | null;
    hazard_model?: number | null;
    cover_gain_pct?: number | null;
    model_probs?: Record<string, number> | null;
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
    /** P&L NETTO commissione (H4): la somma delle righe fa `settled_pnl` */
    pnl: number;
    placed_at: string;
    settled_at: string | null;
    signal_key: string | null;
    meta: Record<string, unknown> | null;
    /** id della riga di APERTURA che questa riga chiude (H4) */
    closes_trade_id?: number | null;
    /** giorno operativo di attribuzione = piazzamento della POSIZIONE (M6) */
    day_placed_at?: string | null;
    /** 'manual' = riga nata da un comando dell'utente (cash out / flatten) */
    origin?: 'auto' | 'manual' | null;
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
    /** presenti solo con migrations/mike_bot_v2.sql applicata (fallback: undefined) */
    open_liability_rows?: number | null;
    live_now?: number | null;
    won_today?: number | null;
    lost_today?: number | null;
    cycles_today?: number | null;
    events_today?: number | null;
    reconciling?: number | null;
    day_by?: string | null;
    /**
     * Da dove viene `open_liability`: 'net_positions' = liability NETTA
     * pubblicata dal servizio (M4), 'rows_sum' = ripiego sulla somma delle
     * righe (servizio non ancora riavviato) → la UI lo DICHIARA.
     */
    liability_source?: 'net_positions' | 'rows_sum' | string | null;
    /** battito del servizio più vecchio di 60 s: il numero è stantio */
    liability_stale?: boolean | null;
    heartbeat_at?: string | null;
}

export interface MikeStateView {
    control: MikeControl | null;
    events: MikeEvent[];
    trades: MikeTrade[];
    activity: MikeActivity[];
    aggregates: MikeAggregates | null;
    /** richieste della UI con esito (M1): assenti senza mike_bot_v2.sql */
    requests: MikeRequest[];
    /** inizio della giornata operativa (Europe/Rome) dichiarato dal DB */
    day_start: string | null;
    /** criterio di attribuzione della giornata: 'placed' (piazzamento) */
    day_by: string | null;
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
    { key: 'entry_hours_before_ko', label: 'Finestra pre-match (ore prima del KO)', kind: 'number', step: 0.25, min: 0.25, max: 12, hint: 'da quante ore prima del calcio d’inizio il bot lavora la partita', group: 'generale' },
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
    { key: 'cashout_smart_enabled', label: 'Cash-out intelligente', kind: 'bool', hint: 'chiude prima della soglia se tenere non vale il rischio (punteggio, hazard, pressione, valore atteso)', group: 'cashout' },
    { key: 'cashout_smart_min_pct', label: 'Profitto minimo per chiudere prima (%)', kind: 'number', step: 0.5, min: 0, max: 50, hint: 'mai sotto questo profitto, qualunque sia il rischio', group: 'cashout' },
    { key: 'cashout_smart_tolerance_pct', label: '"A un passo" dalla soglia = entro (punti %)', kind: 'number', step: 0.5, min: 0, max: 50, hint: 'es. soglia 5 e tolleranza 2 → da 3% in su si può chiudere se la fase è calda', group: 'cashout' },
    { key: 'cashout_smart_hazard_hot', label: 'Fase calda: hazard gol 3′ ≥', kind: 'number', step: 0.01, min: 0, max: 1, hint: 'Atlante + modello + pressione', group: 'cashout' },
    { key: 'cashout_smart_pressure_hot', label: 'Fase calda: pressione ≥', kind: 'number', step: 0.05, min: 1, max: 1.25, hint: 'corner e cartellini dal feed (1,00 = neutra, max 1,25)', group: 'cashout' },
    { key: 'cashout_smart_goals_hot', label: 'Punteggio caldo: gol ≥', kind: 'number', step: 1, min: 0, max: 8, hint: 'con 3 gol il prossimo è il 4°: chiude appena sopra il profitto minimo', group: 'cashout' },
    { key: 'cashout_smart_ev_margin_pct', label: 'Chiudi se aspettare vale meno di (punti %)', kind: 'number', step: 0.5, min: 0, max: 50, hint: 'valore atteso dell\'attesa (modello) sotto il valore attuale di questo margine', group: 'cashout' },
    { key: 'close_retry_s', label: 'Riprezzo chiusura ogni (s)', kind: 'number', step: 5, min: 1, max: 600, hint: 'residuo non abbinato', group: 'cashout' },
    { key: 'close_max_attempts', label: 'Tentativi max chiusura', kind: 'number', step: 1, min: 1, max: 100, hint: 'poi resta in attesa (chiusura manuale)', group: 'cashout' },
    { key: 'ht_loss_exit_enabled', label: 'Uscita HT attiva', kind: 'bool', hint: 'a fine 1T con 2-4 gol', group: 'uscite' },
    { key: 'ht_loss_pct', label: 'HT: perdita tollerata %', kind: 'number', step: 1, min: 0, max: 100, hint: 'chiude comunque se la perdita è entro questa % del capitale', group: 'uscite' },
    { key: 'loss_exit_mode', label: 'Decisione di uscita', kind: 'choice', choices: ['model', 'fixed'], hint: 'model = chiudi se il valore certo batte il valore atteso a fine gara meno il premio al rischio sui 4 gol; fixed = solo la regola "perdita ≤ %"', group: 'uscite' },
    { key: 'loss_exit_risk_premium_pct', label: 'Premio al rischio (% capitale × P(4))', kind: 'number', step: 5, min: 0, max: 300, hint: 'più alto = esce prima quando i 4 gol sono probabili', group: 'uscite' },
    { key: 'loss_exit_p4_prudent', label: 'P(4) prudente (max modello/mercato)', kind: 'bool', hint: 'usa la stima più pessimista fra modello, tabella HT→FT e mercato', group: 'uscite' },
    { key: 'loss_exit_max_pct', label: 'Non cristallizzare oltre (%)', kind: 'number', step: 5, min: 0, max: 100, hint: '0 = spento: decide solo il modello', group: 'uscite' },
    { key: 'loss_exit_emp_min_n', label: 'Casi minimi tabella HT→FT', kind: 'number', step: 10, min: 20, max: 5000, hint: 'sotto, l\'empirico non parla', group: 'uscite' },
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
    { key: 'reentry_exit_until_min', label: 'Chiusura forzata del re-ingresso al minuto', kind: 'number', step: 1, min: 0, max: 100, hint: '0 = mai: la lay a +N tick resta sul book fino a fine gara', group: 'reentry' },
    { key: 'reentry_price_min_over_entry', label: 'Solo se U4.5 > quota iniziale U3.5', kind: 'bool', hint: 'regola della specifica', group: 'reentry' },
    { key: 'reentry_hold_if_loss', label: 'Tieni il re-ingresso se in perdita', kind: 'bool', hint: 'vale solo con una chiusura forzata impostata', group: 'reentry' },
    { key: 'settle_confirm_s', label: 'Conferma punteggio finale (s)', kind: 'number', step: 10, min: 0, max: 600, hint: '', group: 'rischio' },
    { key: 'max_open_matches', label: 'Partite aperte max', kind: 'number', step: 1, min: 1, max: 90, hint: 'partite con posizione contemporaneamente', group: 'rischio' },
    { key: 'daily_loss_stop', label: 'Stop perdita giornaliera (€)', kind: 'number', step: 5, min: 0, max: 100_000, hint: '0 = off', group: 'rischio' },
    { key: 'max_liability_per_match', label: 'Cap capitale per partita (€)', kind: 'number', step: 5, min: 0, max: 100_000, hint: '0 = off; clamp anche dentro il motore', group: 'rischio' },
    { key: 'event_loss_cap_pct', label: 'Cap perdita per partita %', kind: 'number', step: 5, min: 0, max: 500, hint: 'oltre: chiusura forzata', group: 'rischio' },
    { key: 'skip_log_interval_s', label: 'Log skip ogni (s)', kind: 'number', step: 30, min: 10, max: 3600, hint: '', group: 'rischio' },
];

export const MIKE_PARAM_DEFAULTS: Record<string, number | boolean | string> = {
    stake: 10, commission_pct: 5, entry_hours_before_ko: 3,
    competition_filter: '', decide_min_interval_ms: 500, feed_max_age_s: 15,
    pre_enabled: true, pre_entry_price_min: 1.3, pre_entry_price_max: 3, pre_min_back_size_factor: 1,
    pre_max_spread_ticks: 6, pre_green_ticks: 2, pre_exit_mode: 'resting', pre_entry_ttl_s: 60,
    pre_max_cycles: 10, pre_reentry_cooldown_s: 60, pre_last_entry_min: 10, last_entry_persist: true,
    last_entry_ticks_above: 0, cancel_unmatched_after_ko_s: 120,
    cover_enabled: true, cover_profit_factor: 1.2, cover_policy: 'auto', cover_wait_hazard_max: 0.06,
    cover_wait_max_min: 10, cover_wait_p4_max: 0.16, cover_good_price: 7, cover_wait_min_gain_pct: 8,
    cover_wait_step_min: 5, cover_postgoal_delay_s: 45, cover_max_goals: 2,
    cover_rounding: 'ceil', cover_max_overshoot_pct: 30, exact_sizes: true,
    cashout_profit_pct: 5, cashout_base: 'total', cashout_place_at_ticks: 0, close_retry_s: 10, close_max_attempts: 20,
    cashout_smart_enabled: true, cashout_smart_min_pct: 2, cashout_smart_tolerance_pct: 2, cashout_smart_hazard_hot: 0.1,
    cashout_smart_pressure_hot: 1.15, cashout_smart_goals_hot: 3, cashout_smart_ev_margin_pct: 1,
    loss_exit_mode: 'model', loss_exit_risk_premium_pct: 50, loss_exit_p4_prudent: true, loss_exit_max_pct: 0, loss_exit_emp_min_n: 200,
    ht_loss_exit_enabled: true, ht_loss_pct: 25, ht_loss_goals_min: 2, ht_loss_goals_max: 4,
    h2_loss_exit_enabled: true, h2_loss_pct: 25, h2_loss_from_min: 46, h2_loss_to_min: 85,
    reentry_enabled: true, reentry_green_ticks: 2, reentry_max_goals: 1, reentry_until_min: 45,
    reentry_exit_until_min: 0, reentry_price_min_over_entry: true, reentry_hold_if_loss: false,
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

/**
 * ORDINE STABILE delle card (richiesta dell'utente: "le schede non devono
 * muoversi"). L'ordinamento usa SOLO dati che non cambiano durante la partita:
 * calcio d'inizio crescente e, a pari KO, `event_id`. MAI la fase o lo stato:
 * la fase cambia a ogni ciclo del servizio e faceva saltare le schede di posto.
 */
export function sortEvents(events: readonly MikeEvent[]): MikeEvent[] {
    return [...events].sort(compareByKickoff);
}

function compareByKickoff(a: MikeEvent, b: MikeEvent): number {
    const ka = a.ko_at ? Date.parse(a.ko_at) : Number.POSITIVE_INFINITY;
    const kb = b.ko_at ? Date.parse(b.ko_at) : Number.POSITIVE_INFINITY;
    const na = Number.isFinite(ka) ? ka : Number.POSITIVE_INFINITY;
    const nb = Number.isFinite(kb) ? kb : Number.POSITIVE_INFINITY;
    if (na !== nb) return na - nb;
    return a.event_id < b.event_id ? -1 : a.event_id > b.event_id ? 1 : 0;
}

export type MikeSection = 'pre' | 'live' | 'fix';

/**
 * Una partita è LIVE solo dal fischio d'inizio (`live.inplay`) e NON torna
 * indietro: `sticky` conserva gli event_id già visti in gioco, così un buco di
 * feed non fa rimbalzare la card dalla sezione LIVE a quella PRE-MATCH.
 */
export function isEventLive(ev: MikeEvent, sticky?: ReadonlySet<string>): boolean {
    if (ev.live?.inplay === true) return true;
    return Boolean(sticky?.has(ev.event_id));
}

/** aggiorna in place la memoria "è già andata in gioco" (usata dalla pagina) */
export function rememberLive(events: readonly MikeEvent[], sticky: Set<string>): Set<string> {
    for (const e of events) if (e.live?.inplay === true) sticky.add(e.event_id);
    return sticky;
}

/** partita da SISTEMARE a mano: ERROR o SKIPPED (H6: prima erano invisibili) */
export function needsAttention(ev: MikeEvent): boolean {
    return ev.state === 'ERROR' || ev.state === 'SKIPPED' || ev.skipped === true;
}

export interface MikeSections {
    /** non in gioco, per calcio d'inizio crescente */
    pre: MikeEvent[];
    /** in gioco, per calcio d'inizio crescente */
    live: MikeEvent[];
    /** ERROR / SKIPPED: azioni manuali (Riprendi) */
    fix: MikeEvent[];
    /** regolate (SETTLED) della giornata */
    settled: MikeEvent[];
}

/**
 * Tre sezioni FISSE nello stesso ordine (PRE-MATCH · LIVE · DA SISTEMARE) più le
 * regolate. Dentro ogni sezione l'ordine è quello stabile di `sortEvents`.
 */
export function splitMikeEvents(events: readonly MikeEvent[], sticky?: ReadonlySet<string>): MikeSections {
    const pre: MikeEvent[] = []; const live: MikeEvent[] = [];
    const fix: MikeEvent[] = []; const settled: MikeEvent[] = [];
    for (const e of events) {
        if (e.state === 'SETTLED' || e.state === 'SETTLING') { settled.push(e); continue; }
        if (needsAttention(e)) { fix.push(e); continue; }
        if (isEventLive(e, sticky)) live.push(e); else pre.push(e);
    }
    return {
        pre: pre.sort(compareByKickoff), live: live.sort(compareByKickoff),
        fix: fix.sort(compareByKickoff), settled: settled.sort(compareByKickoff),
    };
}

// --------------------------------------------------------- freschezza feed
export type FeedTone = 'ok' | 'warn' | 'stale' | 'unknown';

export interface FeedFreshness { tone: FeedTone; label: string; cls: string }

/** Freschezza del feed PER PARTITA: ≤5 s verde, ≤20 s ambra, oltre "FEED FERMO". */
export function feedFreshness(ageS: number | null | undefined): FeedFreshness {
    const n = ageS == null ? null : Number(ageS);
    if (n === null || !Number.isFinite(n)) {
        return { tone: 'unknown', label: 'FEED: NESSUN DATO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' };
    }
    if (n <= 5) return { tone: 'ok', label: `feed ${Math.round(n)} s`, cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' };
    if (n <= 20) return { tone: 'warn', label: `feed ${Math.round(n)} s`, cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' };
    return { tone: 'stale', label: `FEED FERMO (${Math.round(n)} s)`, cls: 'bg-red-500/15 text-red-300 border-red-500/40' };
}

// ------------------------------------------------- stato del mercato Betfair
export interface MarketStatusMeta { label: string; cls: string; alarming: boolean }

/**
 * `books[...].status` arriva GREZZO da Betfair (OPEN / SUSPENDED / CLOSED /
 * INACTIVE): in una card italiana non ci va mai un codice inglese, e SOSPESO o
 * CHIUSO significano "non puoi operare adesso" → ambra/rosso, non grigio.
 */
export const MIKE_MARKET_STATUS: Record<string, MarketStatusMeta> = {
    OPEN: { label: 'APERTO', cls: 'text-slate-500', alarming: false },
    SUSPENDED: { label: 'SOSPESO', cls: 'text-amber-300 font-semibold', alarming: true },
    CLOSED: { label: 'CHIUSO', cls: 'text-red-300 font-semibold', alarming: true },
    INACTIVE: { label: 'NON ATTIVO', cls: 'text-red-300 font-semibold', alarming: true },
};

export function marketStatusMeta(status: string | null | undefined): MarketStatusMeta | null {
    const s = String(status ?? '').trim().toUpperCase();
    if (!s || s === 'OPEN') return null;              // normale: non si dice nulla
    return MIKE_MARKET_STATUS[s]
        ?? { label: s.replace(/_/g, ' '), cls: 'text-amber-300 font-semibold', alarming: true };
}

// ------------------------------------------------- pre-match / attesa fischio
/**
 * Calcio d'inizio PASSATO ma la partita non è ancora `inplay` nel feed: la card
 * resta in PRE-MATCH (checklist 7) e deve dirlo, altrimenti mostra "fra —" e
 * sembra rotta. Gli stati terminali non aspettano nessun fischio.
 */
export function awaitingKickoff(ev: MikeEvent, nowMs: number): boolean {
    if (ev.live?.inplay === true) return false;
    if (MIKE_TERMINAL_STATES.includes(ev.state)) return false;
    const ko = ev.ko_at ? Date.parse(ev.ko_at) : NaN;
    return Number.isFinite(ko) && nowMs >= ko;
}

export const MIKE_AWAITING_KICKOFF_NOTE = 'in attesa del fischio';

// ------------------------------------------------------------ storico (RPC)
/**
 * Errore delle RPC dello STORICO tradotto in una riga che dice COSA FARE.
 * Senza `mike_history_v2.sql` il DB risponde
 * «function public.trading_daily_history(...) is not unique» (42725): un codice
 * nudo in una pagina vuota. Vedi audit R2.
 */
export const MIKE_HISTORY_MIGRATION_HINT = 'storico Mike: applica migrations/mike_history_v2.sql';

export function mikeHistoryErrorMessage(raw: unknown): string {
    const msg = String((raw as Error)?.message ?? raw ?? '').trim();
    const low = msg.toLowerCase();
    const broken = low.includes('is not unique')
        || low.includes('not unique')
        || low.includes('does not exist')
        || low.includes('could not find the function')
        || low.includes('tabella non ammessa')
        || low.includes('attribuzione non valida');
    if (broken) return `${MIKE_HISTORY_MIGRATION_HINT} (${msg || 'RPC assente'})`;
    return msg || 'storico Mike non disponibile';
}

/** avvolge un fetch dello storico: l'errore che arriva alla UI è LEGGIBILE. */
export function withMikeHistoryError<A extends unknown[], R>(
    fn: (...args: A) => Promise<R>,
): (...args: A) => Promise<R> {
    return async (...args: A) => {
        try {
            return await fn(...args);
        } catch (e) {
            throw new Error(mikeHistoryErrorMessage(e));
        }
    };
}

// ------------------------------------------------- stato del contesto (ctx)
export interface MikeEventFlags {
    /** chiusura manuale ARMATA: il servizio sta chiudendo (ctx.flatten_pending) */
    flattenPending: boolean;
    /** rientro disabilitato: solo "Riprendi" lo riabilita (ctx.no_reentry) */
    noReentry: boolean;
}

/**
 * Bandiere della partita dal `ctx` scritto dal servizio, con ripiego su `live`
 * (il servizio pubblica `no_reentry` in entrambi). Un flatten armato NON è uno
 * stato dell'enum: senza questo la UI mostrerebbe "Cash out" cliccabile mentre
 * la chiusura è già in corso.
 */
export function eventFlags(ev: MikeEvent): MikeEventFlags {
    const ctx = (ev.ctx ?? {}) as Record<string, unknown>;
    return {
        flattenPending: ctx.flatten_pending === true,
        noReentry: ctx.no_reentry === true || ev.live?.no_reentry === true,
    };
}

/** etichetta italiana di un MERCATO ("OU35" / "OVER_UNDER_35" → "linea 3.5") */
export function marketLabel(key: string | null | undefined): string {
    const k = String(key ?? '').toUpperCase();
    if (k === 'OU35' || k === 'OVER_UNDER_35') return 'linea 3.5';
    if (k === 'OU45' || k === 'OVER_UNDER_45') return 'linea 4.5';
    return k || '—';
}

/** codice mercato normalizzato ("OVER_UNDER_35" → "OU35") */
export function marketCode(key: string | null | undefined): string {
    const k = String(key ?? '').toUpperCase();
    if (k === 'OVER_UNDER_35') return 'OU35';
    if (k === 'OVER_UNDER_45') return 'OU45';
    return k;
}

/** mercato annullato su TUTTA la partita (payload senza elenco) */
export const VOID_ALL = '*';

/**
 * Mercati ANNULLATI di una partita. Il void ora è PER MERCATO: si legge
 * dall'attività `settled` (`voided: ['OU35']`) e, in ripiego, dalle righe
 * `void` con `meta.void_reason`. `['*']` = annullata tutta la partita.
 * Serve a non marchiare "VOID" una partita in cui solo una linea è saltata.
 */
export function voidedMarketsOf(
    eventId: string,
    activity: readonly MikeActivity[],
    trades: readonly MikeTrade[],
): string[] {
    const out = new Set<string>();
    for (const a of activity) {
        if (a.kind !== 'settled' || String(a.event_id ?? '') !== eventId) continue;
        const p = a.payload ?? {};
        if (p.void !== true) continue;
        const list = Array.isArray(p.voided) ? p.voided : [];
        if (list.length === 0) out.add(VOID_ALL);
        else for (const m of list) out.add(marketCode(String(m)));
    }
    for (const t of trades) {
        if (t.event_id !== eventId || t.status !== 'void') continue;
        if (!(t.meta ?? {})['void_reason']) continue;
        out.add(marketCode(t.market_type));
    }
    if (out.has(VOID_ALL) && out.size > 1) out.delete(VOID_ALL);
    return [...out];
}

/** riga nata da un comando dell'utente (cash out / flatten manuale) */
export function isManualTrade(t: MikeTrade): boolean {
    return t.origin === 'manual' || t.role === 'manual_close'
        || (t.meta ?? {})['exit_kind'] === 'manual';
}

/** tetto di righe della RPC get_mike_state (migrations/mike_bot_v2.sql) */
export const MIKE_TRADES_LIMIT = 500;

/** etichetta italiana di una linea del feed ("OU45|OVER" → "Over 4.5") */
export function lineLabel(key: string): string {
    const [market, selection] = String(key).split('|');
    const line = market === 'OU35' ? '3.5' : market === 'OU45' ? '4.5' : market;
    return `${selection === 'UNDER' ? 'Under' : selection === 'OVER' ? 'Over' : selection} ${line}`;
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

/** Esposizione netta di una selezione dalle gambe abbinate (stessa matematica di engine.exposure):
 *  W = P&L se la selezione vince, L = P&L se perde. */
export function selectionExposure(legs: readonly MikeLeg[], market: string, selection: string): { w: number; l: number } {
    let w = 0; let l = 0;
    for (const leg of legs) {
        if (leg.archived || leg.market !== market || leg.selection !== selection || !(leg.matched > 0)) continue;
        const p = Number(leg.avg_price ?? leg.price);
        const m = Number(leg.matched);
        if (leg.side === 'back') { w += m * (p - 1); l -= m; } else { w -= m * (p - 1); l += m; }
    }
    return { w: Math.round(w * 100) / 100, l: Math.round(l * 100) / 100 };
}

/** P&L LORDO bloccato chiudendo ORA la selezione con un full green (stessa formula di compute_greenup:
 *  posizione netta back → LAY al best lay: L + (W−L)/lay; netta lay → BACK al best back: W + (L−W)/back). */
export function lockedIfClosed(w: number, l: number, bestBack: number | null | undefined, bestLay: number | null | undefined): number | null {
    if (Math.abs(w - l) < 0.005) return Math.round(Math.min(w, l) * 100) / 100;
    if (w > l) {
        if (!bestLay || bestLay <= 1) return null;
        return Math.round((l + (w - l) / bestLay) * 100) / 100;
    }
    if (!bestBack || bestBack <= 1) return null;
    return Math.round((w + (l - w) / bestBack) * 100) / 100;
}

export interface PositionRow {
    key: string;              // "OU35|UNDER"
    market: string;
    selection: string;
    label: string;            // "Under 3.5"
    selectionId: number | null;
    netSide: 'BACK' | 'LAY';
    /** prezzo medio d'ingresso della posizione netta */
    entryPrice: number | null;
    /** euro abbinati sul lato netto */
    matched: number;
    w: number;
    l: number;
    roles: string[];
}

/** Posizioni aperte per selezione (gambe abbinate non archiviate), con prezzo medio d'ingresso. */
export function positionRows(ev: MikeEvent): PositionRow[] {
    const legs = activeLegs(ev).filter((l) => l.matched > 0);
    const keys = Array.from(new Set(legs.map((l) => `${l.market}|${l.selection}`)));
    const sels = ((ev.ctx as { selections?: Record<string, number> } | null)?.selections) ?? {};
    const out: PositionRow[] = [];
    for (const key of keys) {
        const [market, selection] = key.split('|');
        const mine = legs.filter((l) => l.market === market && l.selection === selection);
        const { w, l } = selectionExposure(mine, market, selection);
        if (Math.abs(w - l) < 0.005) continue;             // gia' piatta (green completato)
        const netSide: 'BACK' | 'LAY' = w > l ? 'BACK' : 'LAY';
        const side = netSide === 'BACK' ? 'back' : 'lay';
        const sameSide = mine.filter((x) => x.side === side);
        const matched = sameSide.reduce((s, x) => s + Number(x.matched), 0);
        const wsum = sameSide.reduce((s, x) => s + Number(x.matched) * Number(x.avg_price ?? x.price), 0);
        out.push({
            key, market, selection, label: `${selection === 'UNDER' ? 'Under' : 'Over'} ${market === 'OU35' ? '3.5' : '4.5'}`,
            selectionId: sels[key] ?? null, netSide, entryPrice: matched > 0 ? Math.round((wsum / matched) * 100) / 100 : null,
            matched: Math.round(matched * 100) / 100, w, l, roles: Array.from(new Set(mine.map((x) => x.role))),
        });
    }
    return out;
}

export function legSelectionLabel(l: MikeLeg): string {
    const line = l.market === 'OU35' ? '3.5' : '4.5';
    return `${l.selection === 'UNDER' ? 'Under' : 'Over'} ${line}`;
}

/** gambe ancora sul book (non abbinate del tutto): ordini VIVI, mai posizioni */
export function bookOrders(ev: MikeEvent): MikeLeg[] {
    return (ev.positions ?? []).filter(
        (l) => !l.archived && (l.status === 'pending' || l.status === 'pending_reconcile')
            && Number(l.size) - Number(l.matched || 0) > 0.004,
    );
}

/** stato italiano di UNA gamba (la riga di posizione non deve mai essere muta) */
export function legStatusLabel(l: MikeLeg): string {
    if (l.status === 'pending_reconcile') return 'IN VERIFICA';
    if (l.status === 'pending') return l.matched > 0 ? 'SUL BOOK (parziale)' : 'SUL BOOK';
    if (l.status === 'open') return 'ABBINATA';
    if (l.status === 'cancelled') return 'ANNULLATA';
    return 'REGOLATA';
}

// ------------------------------------------------------- P&L per gol totali
export interface PnlTotalCell {
    total: number;
    value: number;
    /** i 4 gol: l'unico esito che perde (Costituzione §1) */
    isFour: boolean;
    /** gol attuali della partita */
    isCurrent: boolean;
    /** ultima cella: "8+" */
    isLast: boolean;
}

/** celle "a fine gara per gol totali" 0..N, ordinate, con il 4 e l'attuale marcati. */
export function pnlByTotalCells(
    pnlByTotal: Record<string, number> | null | undefined,
    goals: number | null | undefined,
): PnlTotalCell[] {
    const src = pnlByTotal ?? {};
    const totals = Object.keys(src).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    const g = goals == null ? null : Number(goals);
    return totals.map((t, i) => ({
        total: t,
        value: Number(src[String(t)]),
        isFour: t === 4,
        isCurrent: g !== null && Number.isFinite(g) && t === g,
        isLast: i === totals.length - 1,
    }));
}

// ------------------------------------------------------------ attività bot
/** TUTTI i kind scritti dal servizio Mike (COSTITUZIONE §8 + audit L5). */
export const MIKE_ACTIVITY_KINDS = [
    'armed', 'state', 'place', 'place_pending', 'place_deferred', 'place_resting', 'fill_resting',
    'cancel', 'skip', 'no_fill', 'would_place', 'size_legalized', 'pre_cycle', 'cover',
    'close_retries_exhausted', 'settled', 'settle_fallback', 'settling_reverted', 'daily_stop',
    'stop', 'skip_event', 'resume_event', 'reconcile_pending', 'reconcile_fix',
    'resting_live_unsupported', 'feed_line_missing', 'config_warn', 'schema_warn', 'error',
] as const;

/** kind specifici di Mike che si aggiungono ad ACTIVITY_BASE (design system §6). */
export const MIKE_ACTIVITY_EXTRA: Record<string, ActivityMeta> = {
    armed: { label: 'ARMATA', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' },
    pre_cycle: { label: 'CICLO PRE', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
    place_pending: { label: 'ORDINE IN CORSO', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    place_resting: { label: 'ORDINE APPOGGIATO', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' },
    fill_resting: { label: 'APPOGGIATA ABBINATA', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
    size_legalized: { label: 'IMPORTO LEGALIZZATO', cls: 'bg-white/5 text-slate-300 border-white/10' },
    settle_fallback: { label: 'REGOLAMENTO DA FEED', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    settling_reverted: { label: 'REGOLAMENTO ANNULLATO', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    skip_event: { label: 'PARTITA SALTATA (utente)', cls: 'bg-white/5 text-slate-400 border-white/10' },
    resume_event: { label: 'PARTITA RIPRESA (utente)', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' },
    reconcile_pending: { label: 'ORDINE IN VERIFICA', cls: 'bg-red-500/15 text-red-300 border-red-500/40', critical: true },
    reconcile_fix: { label: 'RICONCILIAZIONE · corretto', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    resting_live_unsupported: { label: 'APPOGGIATA NON SUPPORTATA IN LIVE', cls: 'bg-red-500/15 text-red-300 border-red-500/40', critical: true },
    feed_line_missing: { label: 'LINEA ASSENTE NEL FEED', cls: 'bg-red-500/15 text-red-300 border-red-500/40', critical: true },
    schema_warn: { label: 'SCHEMA DB', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    cover: { label: 'COPERTURA OVER 4.5', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' },
    skip: { label: 'SALTO', cls: 'bg-white/5 text-slate-400 border-white/10' },
};

/**
 * Riga leggibile di UNA attività, in ITALIANO, con i formatter unici.
 * Copre tutti i kind di MIKE_ACTIVITY_KINDS; per un kind mai visto ricade sui
 * campi comuni del payload (motivo/errore/nota) e mai su JSON nudo se evitabile.
 */
export function mikeActivityLine(kind: string, payload: Record<string, unknown> | null | undefined): string {
    const p = payload ?? {};
    const n = (k: string) => Number(p[k]);
    const money = (k: string, signed = false) => fmtMoney(n(k), { signed });
    const odds = (k: string) => fmtOdds(n(k));
    const role = () => roleLabel(p.role == null ? null : String(p.role));
    const side = () => sideMeta(p.side == null ? '' : String(p.side)).label;
    switch (kind) {
        case 'armed':
            return `partita armata · KO ${fmtTime(p.ko == null ? null : String(p.ko))}`;
        case 'state':
            return `${String(p.from ?? '—')} → ${String(p.to ?? '—')}${p.reason ? ` · ${reasonLabel(p.reason)}` : ''}`;
        case 'place':
            return `${role()} ${side()} ${money('size')} @ ${odds('price')}${p.mode === 'live' ? ' · LIVE' : ''}${p.note ? ` · ${reasonLabel(p.note)}` : ''}`;
        case 'place_pending':
            return `${role() !== '—' ? role() : String(p.leg ?? '')} in attesa di conferma${p.note ? ` · ${reasonLabel(p.note)}` : ''}`;
        case 'place_deferred':
            return `${role()} ${money('size')} @ ${odds('price')} · rinviato per betDelay ${String(p.bet_delay ?? '?')} s`;
        case 'place_resting':
            return `${role()} appoggiata sul book ${money('size')} @ ${odds('price')}`;
        case 'fill_resting':
            return `${role()} appoggiata ABBINATA ${money('size')} @ ${odds('price')}${Number.isFinite(n('best_back')) ? ` · best back ${odds('best_back')}` : ''}`;
        case 'would_place':
            return `(dry) ${role()} ${side()} ${money('size')} @ ${odds('price')}`;
        case 'cancel':
            return `${role()} annullato${p.by ? ` · ${String(p.by)}` : ''}`;
        case 'skip':
            return `${reasonLabel(p.reason)}${p.leg ? ` · ${String(p.leg)}` : ''}`;
        case 'no_fill':
            return `${role()} ${side()} non abbinato · voluto ${odds('wanted')} · disponibile ${odds('available')}${p.reason ? ` · ${reasonLabel(p.reason)}` : ''}`;
        case 'size_legalized':
            return `${role()} importo ${money('from')} → ${money('to')}`;
        case 'pre_cycle':
            return `ciclo ${String(p.cycle ?? '?')}: ${odds('entry')} → ${odds('exit')} · ${T.lockedPnl} ${money('locked', true)}`;
        case 'cover':
            return `copertura Over 4.5 ${money('size')} @ ${odds('price')} · ${String(p.x ?? '?')}× · minuto ${String(p.minute ?? '?')}${Number.isFinite(n('overshoot_pct')) ? ` · sovracopertura ${fmtPct(n('overshoot_pct') / 100)}` : ''}`;
        case 'close_retries_exhausted':
            return `chiusura bloccata dopo ${String(p.value ?? '?')} tentativi: serve una chiusura manuale`;
        case 'settled':
            if (p.void === true) {
                // il void ora è PER MERCATO: si dice QUALE linea è stata annullata
                const voided = Array.isArray(p.voided) ? p.voided.map((m) => marketLabel(String(m))) : [];
                const which = voided.length ? voided.join(', ') : 'tutta la partita';
                return `mercato annullato (${which}) · P&L ${fmtMoney(Number(p.pnl ?? 0), { signed: true })}`;
            }
            return `totale gol ${String(p.total ?? '?')} · P&L ${fmtMoney(Number(p.net ?? p.pnl ?? 0), { signed: true })}`;
        case 'settle_fallback':
            return `regolamento dal feed (${reasonLabel(p.reason)}) · totale gol ${String(p.total_from_feed ?? '?')}`;
        case 'settling_reverted':
            return `regolamento annullato → ${String(p.to ?? '—')} · ${reasonLabel(p.reason)}`;
        case 'daily_stop':
            return `stop giornaliero: P&L ${fmtMoney(Number(p.day_pnl ?? 0), { signed: true })} (regolato ${fmtMoney(Number(p.realized_today ?? 0), { signed: true })} · bloccato ${fmtMoney(Number(p.locked_open ?? 0), { signed: true })}) · soglia ${fmtMoney(Number(p.stop ?? 0))}`;
        case 'stop':
            return 'servizio fermato';
        case 'skip_event':
            return `partita saltata${p.by ? ` da ${String(p.by)}` : ''}`;
        case 'resume_event':
            return `partita ripresa${p.by ? ` da ${String(p.by)}` : ''}${p.to ? ` → ${String(p.to)}` : ''}${p.no_reentry === false ? ' · rientro riabilitato' : ''}`;
        case 'reconcile_pending':
            return `ordine con esito ignoto su Betfair${p.leg ? ` (${String(p.leg)})` : ''}${p.legs ? ` · ${String(p.legs)} gambe` : ''}${p.reason ? ` · ${reasonLabel(p.reason)}` : ''}${p.action ? ` · ${reasonLabel(p.action)}` : ''}`;
        case 'reconcile_fix':
            return `${String(p.leg ?? '')} · ${reasonLabel(p.action)}${p.status ? ` · stato ${String(p.status)}` : ''}${Number.isFinite(n('size')) ? ` · ${money('size')}` : ''}${Number.isFinite(n('price')) ? ` @ ${odds('price')}` : ''}`;
        case 'resting_live_unsupported':
            return `lay appoggiata non supportata in live (${role()}): si chiude al best${p.reason ? ` · ${reasonLabel(p.reason)}` : ''}`;
        case 'feed_line_missing':
            return `linee assenti nel feed: ${[...(Array.isArray(p.markets) ? p.markets : []), ...(Array.isArray(p.selections) ? p.selections : [])].map((x) => lineLabel(String(x))).join(', ') || reasonLabel(p.reason)} · stato ${String(p.state ?? '—')}`;
        case 'config_warn':
            return `${String(p.message ?? '')} (finestra ${String(p.entry_hours_before_ko ?? '?')} h · scanner ${String(p.scanner_pre_ko_hours ?? '?')} h)`;
        case 'schema_warn':
            return `${reasonLabel(p.reason)}${p.err ? ` · ${String(p.err)}` : ''}`;
        case 'error':
            return `${reasonLabel(p.reason)}${p.leg ? ` · ${String(p.leg)}` : ''}${p.err ? ` · ${String(p.err)}` : ''}`;
        default: {
            const reason = p.reason ?? p.err ?? p.note ?? p.message ?? p.msg;
            if (reason) return reasonLabel(reason);
            return Object.keys(p).length ? JSON.stringify(p).slice(0, 140) : '';
        }
    }
}

/** motivi del backend (snake_case) → italiano leggibile */
export const MIKE_REASON_LABEL: Record<string, string> = {
    feed_stantio: 'feed stantio', feed_assente: 'linea assente nel feed',
    mercato_annullato: 'mercato annullato', prezzo_assente: 'prezzo assente',
    liquidita_insufficiente: 'liquidità insufficiente', fuori_finestra: 'fuori finestra pre-match',
    quota_fuori_range: 'quota fuori range', spread_troppo_largo: 'spread troppo largo',
    stop_giornaliero: 'stop giornaliero attivo', cap_partita: 'cap di capitale per partita',
    cap_perdita: 'cap di perdita per partita', no_reentry: 'rientro disabilitato',
    reserve_failed: 'riserva fallita', requests_failed: 'lettura richieste fallita',
    events_failed: 'lettura partite fallita', event_cycle: 'ciclo della partita',
    settle_timeout: 'regolamento in timeout', settle_rows_failed: 'scrittura righe di regolamento',
    settle_update_failed: 'aggiornamento regolamento', cycle_exception: 'eccezione nel ciclo',
    riga_ricostruita: 'riga ricostruita', riga_orfana: 'riga orfana', confermata: 'confermata',
    mai_piazzata: 'mai piazzata', cancelled_by_user: 'annullata dall’utente',
    cancelled_manual: 'annullata (chiusura manuale)', cancelled_by_engine: 'annullata dal motore',
    pending_stale: 'ordine scaduto', place_exception_reconciling: 'esito ignoto: in verifica',
};

export function reasonLabel(raw: unknown): string {
    const s = raw == null ? '' : String(raw).trim();
    if (!s) return '';
    return MIKE_REASON_LABEL[s] ?? s.replace(/_/g, ' ');
}

// ------------------------------------------------ esito richieste della UI
export const MIKE_REQUEST_KIND_LABEL: Record<MikeRequestKind, string> = {
    cashout: 'Cash out', flatten: 'Flatten', skip_event: 'Salta partita',
    resume_event: 'Riprendi partita', cancel: 'Annulla ordini',
};

/** `result.code` del servizio → messaggio italiano (M1: mai un codice nudo). */
export const MIKE_REQUEST_CODE_MESSAGE: Record<string, string> = {
    ok: 'eseguito',
    evento_non_seguito: 'la partita non è più seguita dal bot',
    stato_terminale: 'partita già chiusa',
    posizione_aperta: 'c’è ancora una posizione aperta',
    stato_non_riprendibile: 'in questo stato non si può riprendere',
    feed_assente: 'linea assente nel feed',
    snapshot_assente: 'nessuno snapshot del mercato',
    niente_da_chiudere: 'niente da chiudere',
    feed_stantio: 'feed stantio',
    kind_non_valido: 'comando non valido',
    errore_interno: 'errore interno del servizio',
    processing_stale: 'richiesta rimasta in lavorazione',
};

export type MikeOutcomeTone = 'ok' | 'pending' | 'warn' | 'bad';

export interface MikeRequestOutcome {
    id: number;
    kind: MikeRequestKind;
    kindLabel: string;
    tone: MikeOutcomeTone;
    /** riga pronta per la card: "Cash out rifiutato: feed stantio" */
    label: string;
    /** messaggio del servizio (o la resa italiana del codice) */
    message: string;
    eventId: string | null;
    at: string | null;
    /** netto stimato di chiusura pubblicato dal servizio (`result.cashout_net`) */
    net?: number | null;
    /** true = chiusura ARMATA (ordini annullati, chiusura guidata dall'engine) */
    armed?: boolean;
}

/** Esito di UNA richiesta, in italiano, pronto per toast e riga nella card (M1). */
export function requestOutcome(r: MikeRequest): MikeRequestOutcome {
    const kindLabel = MIKE_REQUEST_KIND_LABEL[r.kind] ?? String(r.kind);
    const code = String(r.result?.code ?? '');
    const fromCode = code ? (MIKE_REQUEST_CODE_MESSAGE[code] ?? code.replace(/_/g, ' ')) : '';
    const message = String(r.result?.message ?? '').trim() || fromCode;
    const eventId = r.payload?.event_id != null ? String(r.payload.event_id) : null;
    const at = r.updated_at ?? r.created_at ?? null;
    const base = { id: r.id, kind: r.kind, kindLabel, message, eventId, at };
    if (r.status === 'pending' || r.status === 'processing') {
        return { ...base, tone: 'pending', label: `${kindLabel} in corso…`, message: message || 'inviato al servizio' };
    }
    if (r.status === 'rejected') return { ...base, tone: 'warn', label: `${kindLabel} rifiutato: ${message || '—'}` };
    if (r.status === 'error') return { ...base, tone: 'bad', label: `${kindLabel} in errore: ${message || '—'}` };
    const warn = r.result?.warning === 'reconcile' ? ' · ordini in verifica' : '';
    // CHIUSURA ARMATA (`phase:'armed'`): gli ordini sul book sono stati annullati
    // e la chiusura la guida l'engine nei cicli successivi. La riga si scrive con
    // i CAMPI del risultato (importi in formato italiano), non con il messaggio
    // grezzo del servizio ("0.47 EUR"), che resta disponibile come dettaglio.
    if (r.result?.phase === 'armed') {
        const net = Number(r.result?.cashout_net);
        const cancelled = Number(r.result?.cancelled);
        const parts: string[] = [];
        if (Number.isFinite(cancelled) && cancelled > 0) {
            parts.push(`annullati ${cancelled} ordini sul book`);
        }
        parts.push('chiusura in corso');
        if (Number.isFinite(net)) parts.push(`netto stimato ${fmtMoney(net, { signed: true })}`);
        if (r.result?.complete === false) parts.push('prezzi incompleti su una selezione');
        return {
            ...base,
            tone: 'ok',
            armed: true,
            net: Number.isFinite(net) ? net : null,
            label: `${kindLabel} armato: ${parts.join(' · ')}${warn}`,
        };
    }
    return { ...base, tone: 'ok', label: `${kindLabel} eseguito${message && code !== 'ok' ? `: ${message}` : ''}${warn}` };
}

/** ultima richiesta (per evento, eventualmente per kind): la più recente per id. */
export function lastRequestFor(
    eventId: string, requests: readonly MikeRequest[], kind?: MikeRequestKind,
): MikeRequest | null {
    let best: MikeRequest | null = null;
    for (const r of requests) {
        if (String(r.payload?.event_id ?? '') !== eventId) continue;
        if (kind && r.kind !== kind) continue;
        if (!best || Number(r.id) > Number(best.id)) best = r;
    }
    return best;
}

// --------------------------------------------- trade: chiusure sotto l'apertura
export interface MikeTradeGroup {
    open: MikeTrade;
    /** chiusure/green che riferiscono questa apertura (`closes_trade_id`) */
    closes: MikeTrade[];
    /** P&L NETTO del ciclo: apertura + chiusure regolate */
    netPnl: number | null;
    /** true = chiusura senza apertura nota (riga orfana: mai nascosta) */
    orphan: boolean;
}

const SETTLED_TRADE_STATES = new Set(['won', 'lost', 'void']);

/** giorno operativo di attribuzione della riga (ms): piazzamento della POSIZIONE. */
export function tradeDayMs(t: MikeTrade): number {
    const iso = t.day_placed_at ?? t.placed_at;
    const ms = iso ? Date.parse(iso) : NaN;
    return Number.isFinite(ms) ? ms : 0;
}

/**
 * Righe di `mike_trades` → gruppi con le CHIUSURE ANNIDATE sotto l'apertura
 * (design §7 / audit H4). Le aperture sono ordinate dalla più recente; le
 * chiusure dalla più vecchia (ordine in cui sono avvenute). Una chiusura la cui
 * apertura non è nel set diventa un gruppo a sé, dichiarato orfano.
 */
export function groupMikeTrades(trades: readonly MikeTrade[]): MikeTradeGroup[] {
    const byId = new Map<number, MikeTrade>();
    for (const t of trades) byId.set(Number(t.id), t);
    const closesOf = new Map<number, MikeTrade[]>();
    const opens: MikeTrade[] = [];
    const orphans: MikeTrade[] = [];
    for (const t of trades) {
        const parent = t.closes_trade_id == null ? null : Number(t.closes_trade_id);
        if (parent == null) { opens.push(t); continue; }
        if (!byId.has(parent)) { orphans.push(t); continue; }
        const arr = closesOf.get(parent) ?? [];
        arr.push(t);
        closesOf.set(parent, arr);
    }
    const mk = (open: MikeTrade, orphan: boolean): MikeTradeGroup => {
        const closes = (closesOf.get(Number(open.id)) ?? [])
            .slice().sort((a, b) => Date.parse(a.placed_at) - Date.parse(b.placed_at));
        const rows = [open, ...closes].filter((r) => SETTLED_TRADE_STATES.has(r.status));
        const netPnl = rows.length
            ? Math.round(rows.reduce((s, r) => s + Number(r.pnl ?? 0), 0) * 100) / 100
            : null;
        return { open, closes, netPnl, orphan };
    };
    const groups = [
        ...opens.map((o) => mk(o, false)),
        ...orphans.map((o) => mk(o, true)),
    ];
    return groups.sort((a, b) => Date.parse(b.open.placed_at) - Date.parse(a.open.placed_at));
}

/**
 * Mezzanotte di OGGI a Roma in ms (ripiego quando la RPC non espone `day_start`,
 * cioe' senza `mike_bot_v2.sql`): la giornata operativa resta quella di
 * piazzamento anche senza migrazione, invece di "tutte le righe".
 */
export function romeDayStartMs(now: number = Date.now()): number {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(now));
    const get = (t: string) => Number(parts.find((x) => x.type === t)?.value ?? 0);
    // ms trascorsi dalla mezzanotte di Roma (ora locale di Roma dell'istante `now`)
    const sinceMidnight = ((get('hour') * 60 + get('minute')) * 60 + get('second')) * 1000 + (now % 1000);
    return now - sinceMidnight;
}

/**
 * V/P della giornata operativa calcolati dal client (ripiego senza `won_today`/
 * `lost_today` della RPC v2): posizioni = righe di APERTURA piazzate nel giorno,
 * esito dal P&L NETTO della posizione (apertura + chiusure).
 */
export function dayResultCounts(trades: readonly MikeTrade[], dayStartMs: number | null): { won: number; lost: number } {
    const groups = groupsOfDay(groupMikeTrades(trades), dayStartMs);
    let won = 0, lost = 0;
    for (const g of groups) {
        if (g.netPnl == null) continue;
        if (g.netPnl > 0) won += 1; else if (g.netPnl < 0) lost += 1;
    }
    return { won, lost };
}

/** solo i gruppi della giornata operativa (per il toggle "solo oggi / tutte"). */
export function groupsOfDay(groups: readonly MikeTradeGroup[], dayStartMs: number | null): MikeTradeGroup[] {
    if (dayStartMs == null || !Number.isFinite(dayStartMs)) return [...groups];
    return groups.filter((g) => tradeDayMs(g.open) >= dayStartMs);
}

export interface MikeEquityPoint { t: number; v: number; iso: string }

/**
 * Curva di equity dai trade REGOLATI (design §11: Mike non ne aveva una).
 * Gradini sul momento di regolamento, P&L NETTO cumulato.
 */
export function mikeEquitySeries(trades: readonly MikeTrade[], dayStartMs?: number | null): MikeEquityPoint[] {
    const rows = trades
        .filter((t) => SETTLED_TRADE_STATES.has(t.status))
        .filter((t) => dayStartMs == null || tradeDayMs(t) >= dayStartMs)
        .map((t) => ({ iso: t.settled_at ?? t.placed_at, pnl: Number(t.pnl ?? 0) }))
        .filter((r) => Boolean(r.iso) && Number.isFinite(Date.parse(String(r.iso))))
        .sort((a, b) => Date.parse(String(a.iso)) - Date.parse(String(b.iso)));
    let cum = 0;
    return rows.map((r) => {
        cum = Math.round((cum + r.pnl) * 100) / 100;
        return { t: Date.parse(String(r.iso)), v: cum, iso: String(r.iso) };
    });
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
        // le tre chiavi sotto arrivano solo con mike_bot_v2.sql: senza migrazione
        // la UI resta funzionante (requests lette a parte, giornata dal client)
        requests: Array.isArray(d.requests) ? d.requests : [],
        day_start: d.day_start ?? null,
        day_by: d.day_by ?? null,
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

export interface MikeRequestResult {
    code?: string;
    message?: string;
    ok?: boolean;
    phase?: string;
    cancelled?: number;
    legs?: number;
    cashout_net?: number;
    warning?: string;
    [k: string]: unknown;
}

export interface MikeRequest {
    id: number; kind: MikeRequestKind; payload: Record<string, unknown>;
    /** 'rejected' = rifiuto ATTESO (feed stantio, niente da chiudere…), non un errore */
    status: 'pending' | 'processing' | 'done' | 'rejected' | 'error';
    result: MikeRequestResult | null;
    created_at: string;
    updated_at?: string | null;
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
/**
 * Firma del control che IGNORA il battito: `heartbeat_at`, `updated_at` e i
 * campi di `stats` che cambiano a ogni ciclo senza dire nulla di nuovo
 * (`last_cycle`, `scanner_age_s`). Un battito non deve far ricaricare la UI
 * (audit H5): con 26 partite seguite erano decine di reload al minuto.
 */
export function controlSignature(row: Record<string, unknown> | null | undefined): string {
    if (!row) return '';
    const { heartbeat_at: _h, updated_at: _u, stats, ...rest } = row as Record<string, unknown>;
    const st = (stats ?? null) as Record<string, unknown> | null;
    let statsSig = '';
    if (st) {
        const { last_cycle: _lc, scanner_age_s: _sa, ...restStats } = st;
        statsSig = JSON.stringify(restStats);
    }
    return `${JSON.stringify(rest)}|${statsSig}`;
}

/** true = questa notifica realtime NON cambia nulla di utile (solo battito). */
export function isHeartbeatOnlyChange(
    table: string, row: Record<string, unknown> | null | undefined, lastSignature: string | null,
): boolean {
    if (table !== 'mike_control') return false;
    const sig = controlSignature(row);
    return sig !== '' && sig === lastSignature;
}

/**
 * Tabelle che il servizio Mike SCRIVE e che la pagina legge: la sottoscrizione
 * realtime deve coprirle tutte (senza `mike_activity` il tab Attività si
 * aggiornava solo al poll da 15 s o per rimbalzo di un'altra tabella).
 */
export const MIKE_REALTIME_TABLES = [
    'mike_control', 'mike_events', 'mike_trades', 'mike_activity', 'mike_requests',
] as const;

/** UN canale per control + events + trades + activity + requests (mai N canali). */
export function subscribeMike(onChange: (table?: string) => void): () => void {
    let lastControlSig: string | null = null;
    const handle = (table: string) => (payload: { new?: unknown }) => {
        if (table === 'mike_control') {
            const row = (payload?.new ?? null) as Record<string, unknown> | null;
            if (isHeartbeatOnlyChange(table, row, lastControlSig)) return;
            lastControlSig = controlSignature(row);
        }
        onChange(table);
    };
    let channel = supabase.channel('mike-live');
    for (const table of MIKE_REALTIME_TABLES) {
        channel = channel.on('postgres_changes', { event: '*', schema: 'public', table }, handle(table));
    }
    channel.subscribe();
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
