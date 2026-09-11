// ============================================================================
// omega.ts — client della sezione OMEGA (Correct Score LAY, set-and-forget).
// Parla SOLO con le RPC owner-only (migrations/omega_bot.sql):
//   omega_activate / omega_stop / omega_update_params / get_omega_state / get_omega_trades.
// L'esecuzione vera avviene nel servizio locale Betfair/omega/omega_service.py
// (avvia_omega_service.bat): la UI scrive stato/parametri e legge lo specchio DB.
// Fonte di verità: Betfair/omega/COSTITUZIONE_OMEGA.md
// ============================================================================
import { supabase } from '@/integrations/supabase/client';
import { fmtMoney, fmtOdds, fmtPct, fmtTime } from '@/lib/format';
import { activityMeta as sharedActivityMeta, type ActivityMeta } from '@/lib/tradeStatus';
import type { ParamGroup } from '@/components/trading/ParamsSheetBase';

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
    /** v5: gli stessi campi degli aggregati, fotografati dal servizio */
    locked_pnl_open?: number;
    locked_pnl_open_today?: number;
    /** ciclo DEGRADATO: una fase è fallita (motivo). Non è "servizio morto". */
    degraded?: string | null;
    reconciling_liability?: number;
    live_now?: number;
    legs_today?: number;
    events_today?: number;
    won_today?: number;
    lost_today?: number;
    /** L-03: false = fotografia a bot FERMO (eventi/target azzerati, soldi freschi) */
    bot_running?: boolean;
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
    /** v5 H-06: P&L GIÀ BLOCCATO sulle posizioni vive (non realizzato, rischio 0) */
    locked_pnl_open?: number;
    /** bloccato sulle posizioni vive PIAZZATE OGGI (la giornata operativa) */
    locked_pnl_open_today?: number;
    /** v5 H-02: quota di open_liability che è un ordine a esito IGNOTO in verifica */
    reconciling_liability?: number;
    /** v5 H-08: partite DISTINTE con una posizione viva ADESSO (senza giorno) */
    live_now?: number;
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
    /** SOLO la giornata operativa (Rome), ts DESC — v5 M-22 */
    activity: OmegaActivityRow[];
    /** righe di attività della giornata OLTRE il limite chiesto (v5 M-22) */
    activity_more?: number;
    /** giornata a cui appartiene l'attività ('YYYY-MM-DD', Rome) */
    activity_day?: string | null;
    /** §14: obiettivo storicizzato per OGGI (null = migrazione non applicata) */
    goal_today?: number | null;
    /** true SOLO se `goal_today` è lo SNAPSHOT del giorno; false = ripiego dal control */
    goal_snapshot?: boolean;
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
    // ---- M-10: chiavi della whitelist del servizio prima senza UI --------
    /** percorso del calibratore ('' = default) */
    model_calibration_path: string;
    /** motore: 'legs' = due gambe (1T+2T) · 'single' = v1 (una gamba, kill-switch) */
    engine: 'legs' | 'single';
    /** esecuzione: 'auto' = coda flumine quando il gate passa · 'rest' = legacy */
    execution_mode: 'auto' | 'rest';
    /** TTL quasi-FOK del place PAPER via flumine (s) */
    paper_fill_ttl_s: number;
    /** kill-switch: place LIVE via coda flumine (FILL_OR_KILL) */
    omega_live_via_flumine: boolean;
    /** deadline (s) dell'esito FOK live prima della riconciliazione REST */
    live_fill_deadline_s: number;
    /** gol AGGIUNTIVI minimi fra punteggio corrente e risultato bancato */
    model_min_goal_distance: number;
    /** veto empirico HT→FT sulla gamba 2T: 'veto' | 'off' */
    model_empirical: 'veto' | 'off';
    /** minuto d'ingresso massimo entro cui applicare il veto empirico */
    model_empirical_max_minute: number;
    /** λ impliciti nell'intero mercato (scala CS + linee O/U) */
    lambda_market_grid: boolean;
    /** λ dal mercato Over/Under LIVE quando mancano fixture e quote pre-KO */
    lambda_live_fallback: boolean;
    /** a P equivalente vince il risultato più economico da coprire subito */
    select_cost_aware: boolean;
    /** ampiezza della banda di P considerata "equivalente" (× la più bassa) */
    select_p_band_ratio: number;
    /** gialli dal feed nei tassi residui (moltiplicatori per lega) */
    model_use_yellow_cards: boolean;
    /** fattore di coda su P ≤ 5 % (1 = nessuna correzione) */
    model_tail_factor: number;
    /** incertezza sui λ: cv della mistura lognormale (0 = Poisson puro) */
    model_lambda_cv: number;
    /** selezione conservativa: P = centro + k·SE */
    select_k_se: number;
    /** P di dover coprire (costo del green-up) nel ranking EV */
    select_p_hedge: number;
    /** peso del costo di copertura nel ranking EV */
    select_ev_kappa: number;
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

// ---------------------------------------------------------- attività (M-01)
// TUTTI i `kind` che il servizio Omega scrive (contratto 11/09) hanno qui una
// etichetta ITALIANA: prima 30+ kind cadevano nel fallback e mostravano la
// chiave inglese in maiuscolo, anche quelli CRITICI. I kind comuni ai tre bot
// stanno in lib/tradeStatus.ts (ACTIVITY_BASE): qui solo quelli di Omega.
const A_INFO = 'bg-sky-500/15 text-sky-300 border-sky-500/40';
const A_WARN = 'bg-amber-500/15 text-amber-300 border-amber-500/40';
const A_BAD = 'bg-red-500/15 text-red-300 border-red-500/40';
const A_GOOD = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40';
const A_CLOSE = 'bg-teal-500/15 text-teal-300 border-teal-500/40';
const A_PLAIN = 'bg-white/5 text-slate-300 border-white/10';
const A_MUTED = 'bg-white/5 text-slate-400 border-white/10';

export const OMEGA_ACTIVITY_EXTRA: Record<string, ActivityMeta> = {
    // ---- ingressi
    place: { label: 'PIAZZATO', cls: A_INFO },
    skip: { label: 'SALTATA', cls: A_MUTED },
    size_reduced: { label: 'IMPORTO RIDOTTO', cls: A_WARN },
    goal_stop: { label: 'STOP: OBIETTIVO RAGGIUNTO', cls: A_GOOD },
    loss_stop: { label: 'STOP-LOSS GIORNALIERO', cls: A_BAD, critical: true },
    confirm_failed: { label: 'CONFERMA FALLITA', cls: A_BAD, critical: true },
    place_reconciling: { label: 'ORDINE IN VERIFICA SU BETFAIR', cls: A_BAD, critical: true },
    place_exception: { label: 'ERRORE DI PIAZZAMENTO', cls: A_BAD, critical: true },
    manual_place: { label: 'ORDINE MANUALE', cls: A_INFO },
    manual_place_exception: { label: 'ORDINE MANUALE FALLITO', cls: A_BAD, critical: true },
    paper_fill_fallback: { label: 'PAPER: FILL DI RIPIEGO', cls: A_WARN },
    live_fok_fallback: { label: 'LIVE: FOK DI RIPIEGO (REST)', cls: A_WARN },
    // ---- coda flumine
    flumine_enqueue: { label: 'CODA: ORDINE ACCODATO', cls: A_PLAIN },
    flumine_fill: { label: 'CODA: ABBINATO', cls: A_GOOD },
    flumine_no_fill: { label: 'CODA: NON ABBINATO', cls: A_WARN },
    flumine_cancel: { label: 'CODA: ANNULLO', cls: A_WARN },
    flumine_cancel_timeout: { label: 'CODA: ANNULLO SCADUTO', cls: A_BAD, critical: true },
    flumine_recovered: { label: 'CODA: RECUPERATO', cls: A_INFO },
    flumine_live_freed: { label: 'CODA: SLOT LIVE LIBERATO', cls: A_PLAIN },
    flumine_live_orphan: { label: 'CODA: ORDINE LIVE ORFANO', cls: A_BAD, critical: true },
    flumine_poll_error: { label: 'CODA: LETTURA FALLITA', cls: A_BAD, critical: true },
    // ---- riconciliazione
    reconciled_open: { label: 'VERIFICA: POSIZIONE APERTA', cls: A_INFO },
    reconciled_free: { label: 'VERIFICA: RISERVA LIBERATA', cls: A_PLAIN },
    reconciled_error: { label: 'VERIFICA: IN ERRORE', cls: A_BAD, critical: true },
    reconciled_paper: { label: 'VERIFICA PAPER', cls: A_PLAIN },
    reconcile_error: { label: 'VERIFICA FALLITA', cls: A_BAD, critical: true },
    orphan_live_alert: { label: 'ORDINE LIVE SENZA TRADE', cls: A_BAD, critical: true },
    stale_open_alert: { label: 'POSIZIONE APERTA DA TROPPO', cls: A_BAD, critical: true },
    // ---- green-up (M-03: etichette al posto giusto)
    greenup: { label: 'GREEN-UP', cls: A_GOOD },
    greenup_hold: { label: 'GREEN-UP · TENGO', cls: A_INFO },
    greenup_wait: { label: 'GREEN-UP · attesa prezzi', cls: A_WARN },
    greenup_retry: { label: 'GREEN-UP · ritento', cls: A_WARN },
    greenup_failed: { label: 'GREEN-UP FALLITO', cls: A_BAD, critical: true },
    greenup_residual_dropped: { label: 'GREEN-UP · residuo abbandonato', cls: A_BAD, critical: true },
    greenup_blind: { label: 'GREEN-UP CIECO (senza feed)', cls: A_BAD, critical: true },
    cashout: { label: 'CASH OUT', cls: A_CLOSE },
    cashout_manual: { label: 'CASH OUT MANUALE', cls: A_CLOSE },
    cashout_error: { label: 'CASH OUT FALLITO', cls: A_BAD, critical: true },
    // ---- regolamento
    settle: { label: 'REGOLATA', cls: A_PLAIN },
    settle_hedged: { label: 'REGOLATA (coperta)', cls: A_CLOSE },
    hedged: { label: 'COPERTA', cls: A_CLOSE },
    settle_position: { label: 'POSIZIONE REGOLATA', cls: A_PLAIN },
    settle_wait: { label: 'REGOLAMENTO · attesa', cls: A_MUTED },
    settle_orphan: { label: 'REGOLAMENTO: CHIUSURA ORFANA', cls: A_WARN },
    settle_orphan_closing: { label: 'REGOLAMENTO: CHIUSURA SENZA APERTURA', cls: A_WARN },
    settle_error: { label: 'REGOLAMENTO FALLITO', cls: A_BAD, critical: true },
    // ---- modello e missioni
    model_lambda_market: { label: 'MODELLO: λ DAL MERCATO', cls: A_MUTED },
    model_lambda_live: { label: 'MODELLO: λ DA O/U LIVE', cls: A_MUTED },
    mission_error: { label: 'MISSIONE IN ERRORE', cls: A_BAD, critical: true },
    mission_scores_error: { label: 'MISSIONE: PUNTEGGI NON LETTI', cls: A_BAD, critical: true },
    // ---- ciclo
    error: { label: 'ERRORE', cls: A_BAD, critical: true },
    stop: { label: 'STOP', cls: A_PLAIN },
};

/** kind → etichetta italiana (Omega + base condivisa + traduzione a parole). */
export function activityMeta(kind: string | null | undefined): ActivityMeta {
    return sharedActivityMeta(kind, OMEGA_ACTIVITY_EXTRA);
}

/** motivi di `error` scritti dal servizio → frase italiana (payload.reason) */
export const OMEGA_ERROR_REASON: Record<string, string> = {
    greenup_attempts_exhausted: 'green-up: tentativi esauriti, posizione SCOPERTA',
    greenup_failed: 'green-up fallito',
    greenup_candidates_failed: 'green-up: nessun prezzo di chiusura utilizzabile',
    greenup_phase_failed: 'fase green-up interrotta',
    reconcile_phase_failed: 'fase di verifica interrotta',
    flumine_poll_failed: 'lettura della coda ordini interrotta',
    settle_phase_failed: 'fase di regolamento interrotta',
    results_phase_failed: 'lettura dei risultati interrotta',
    results_read_failed: 'risultati non leggibili',
    manual_failed: 'richiesta manuale fallita',
    missions_failed: 'missioni non aggiornate',
    list_events_failed: 'elenco eventi non letto',
    manual_ids_failed: 'id delle richieste manuali non letti',
    mission_ids_failed: 'id delle missioni non letti',
    traded_ids_failed: 'gambe già piazzate non lette',
    aggregates_failed: 'aggregati non calcolati',
    scan_phase_failed: 'scansione interrotta',
    cycle_exception: 'ciclo interrotto da un errore',
    place_exception_reconciling: 'piazzamento interrotto: ordine da verificare su Betfair',
};

/** etichetta della gamba dal payload (`leg`) */
function legTag(v: unknown): string | null {
    const s = String(v ?? '').trim();
    if (!s) return null;
    if (s === 'ht_cs' || s === 'ht' || s === '1t') return '1T';
    if (s === 'ft_cs' || s === 'ft' || s === '2t') return '2T';
    if (s === 'scalp') return 'SCALP';
    return s.toUpperCase();
}

/**
 * Riga di attività → testo leggibile. M-02: legge SOLO le chiavi che il
 * servizio scrive davvero (reason, attempt, max_attempts, p_lose, locked_pnl,
 * minute, score, exit_reason, price, size, side, leg, wait, next_retry_at,
 * cycles, residual). Il NOME della partita non è nel payload (solo
 * `event_id`): lo risolve il chiamante dai trade e lo passa qui.
 */
export function activityLine(row: OmegaActivityRow, eventName?: string | null): string {
    const p = (row.payload ?? {}) as Record<string, unknown>;
    const parts: string[] = [];
    const name = eventName?.trim() || (typeof p.event_id === 'string' ? p.event_id : null);
    if (name) parts.push(name);
    const leg = legTag(p.leg);
    if (leg) parts.push(leg);
    const side = typeof p.side === 'string' ? p.side.toUpperCase() : null;
    const size = Number(p.size);
    const price = Number(p.price);
    if (side && Number.isFinite(size) && Number.isFinite(price)) parts.push(`${side} ${fmtMoney(size)} @ ${fmtOdds(price)}`);
    else if (Number.isFinite(size) && Number.isFinite(price)) parts.push(`${fmtMoney(size)} @ ${fmtOdds(price)}`);
    else if (Number.isFinite(price)) parts.push(fmtOdds(price));
    else if (side) parts.push(side);
    const minute = Number(p.minute);
    const score = typeof p.score === 'string' ? p.score : null;
    if (Number.isFinite(minute) || score) {
        parts.push([Number.isFinite(minute) ? `${Math.trunc(minute)}′` : null, score].filter(Boolean).join(' · '));
    }
    const pl = Number(p.p_lose);
    if (Number.isFinite(pl)) parts.push(`P(perdita) ${fmtPct(pl)}`);
    const locked = Number(p.locked_pnl);
    if (Number.isFinite(locked)) parts.push(`${T_LOCKED} ${fmtMoney(locked, { signed: true })}`);
    const liab = Number(p.liability);
    if (Number.isFinite(liab) && !Number.isFinite(locked) && !Number.isFinite(size)) parts.push(`liability ${fmtMoney(liab)}`);
    const residual = Number(p.residual);
    if (Number.isFinite(residual) && residual > 0) parts.push(`residuo ${fmtMoney(residual)}`);
    // motivo: exit_reason (italiano dal servizio) → reason (chiave) → wait → err
    const rawReason = p.exit_reason ?? p.reason ?? p.wait ?? p.err ?? null;
    if (rawReason != null && String(rawReason).trim() !== '') {
        const key = String(rawReason).trim();
        parts.push(OMEGA_ERROR_REASON[key] ?? OMEGA_WAIT_REASON[key] ?? key);
    }
    const attempt = Number(p.attempt);
    if (Number.isFinite(attempt)) {
        const max = Number(p.max_attempts ?? p.max);
        parts.push(`tentativo ${Math.trunc(attempt)}${Number.isFinite(max) ? `/${Math.trunc(max)}` : ''}`);
    }
    const cycles = Number(p.cycles);
    if (Number.isFinite(cycles)) parts.push(`${Math.trunc(cycles)} cicli senza feed`);
    if (typeof p.next_retry_at === 'string' && p.next_retry_at) parts.push(`ritento alle ${fmtTime(p.next_retry_at)}`);
    return parts.join(' · ');
}

const T_LOCKED = 'bloccato';

/** motivi di attesa del green-up scritti dal servizio (payload.wait) */
export const OMEGA_WAIT_REASON: Record<string, string> = {
    prezzi_non_disponibili: 'prezzi di chiusura non disponibili',
    prezzo_opposto_non_disponibile: 'prezzo opposto non disponibile',
    assestamento: 'attende l’assestamento del mercato dopo il gol',
};

// ======================================================= META di una gamba
// Tutto quello che il servizio scrive su `omega_trades.meta` e che il trader
// DEVE poter leggere sulla riga: stato del green-up (H-04), copertura parziale
// (M-06), verifica su Betfair (H-02), commissione fissata (L-02), esito della
// POSIZIONE (M-04), riga terminale in errore (M-05). Tutte funzioni PURE.
type Meta = Record<string, unknown> | null | undefined;

function metaObj(meta: Meta): Record<string, unknown> {
    return (meta ?? {}) as Record<string, unknown>;
}
function nOrNull(v: unknown): number | null {
    if (v === null || v === undefined || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}
function sOrNull(v: unknown): string | null {
    if (typeof v !== 'string') return null;
    const s = v.trim();
    return s === '' ? null : s;
}
function sub(meta: Meta, key: string): Record<string, unknown> | null {
    const v = metaObj(meta)[key];
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

// ------------------------------------------------------------------- H-02
/** true = ordine REALE a esito IGNOTO ancora in verifica su Betfair. */
export function isReconciling(meta: Meta): boolean {
    const m = metaObj(meta);
    return m.reconciling === true || m.reconciling === 'true'
        || m.reason === 'place_exception_reconciling';
}
/** da quando è in verifica (ISO) */
export function reconcilingSince(meta: Meta): string | null {
    return sOrNull(metaObj(meta).reconciling_since);
}

// ------------------------------------------------------------------- M-05
/**
 * Riga TERMINALE in errore: nessun ordine reale esiste (o è morto).
 * L'ISTANTE dell'errore è `meta.error_at` (contratto 11/09: le righe
 * `status='error'` NON hanno più `settled_at`), con ripiego su `no_fill_at`.
 */
export function terminalError(meta: Meta): { reason: string | null; at: string | null } | null {
    const m = metaObj(meta);
    const isTerm = m.error_final === true || m.leg_failed === true
        || m.no_fill_at != null || m.error_at != null;
    if (!isTerm) return null;
    return { reason: sOrNull(m.reason), at: sOrNull(m.error_at) ?? sOrNull(m.no_fill_at) };
}

/** Istante dell'errore (`meta.error_at`): l'ordinamento e l'etichetta
 *  "ERRORE alle HH:MM" non possono usare `settled_at`, che non c'è più. */
export function errorAt(meta: Meta): string | null {
    const m = metaObj(meta);
    return sOrNull(m.error_at) ?? sOrNull(m.no_fill_at);
}
/** allarme "aperta da troppo tempo" già emesso dal servizio (ISO) */
export function staleOpenAlerted(meta: Meta): string | null {
    return sOrNull(metaObj(meta).stale_open_alerted);
}

// ------------------------------------------------------------------- L-02
/**
 * Commissione da usare per i calcoli della RIGA: quella FISSATA sul trade
 * (`meta.commission`, una FRAZIONE) e non il parametro corrente del form —
 * cambiare il campo "Commissione %" non deve riscrivere il P&L di un trade
 * piazzato ieri. Ritorna PUNTI percentuali (5 = 5 %).
 */
export function commissionPctOf(meta: Meta, fallbackPct = 5): number {
    const raw = nOrNull(metaObj(meta).commission);
    if (raw == null || raw < 0) return fallbackPct;
    // il servizio scrive una frazione (0.05); un valore > 1 è già in punti
    return raw <= 1 ? raw * 100 : raw;
}
/** true = la commissione viene dalla riga (non dal form) */
export function hasOwnCommission(meta: Meta): boolean {
    return nOrNull(metaObj(meta).commission) != null;
}

// ------------------------------------------------------------------- M-04
export type PositionResult = 'won' | 'lost' | 'flat';
export interface PositionInfo { id: number | null; pnl: number | null; result: PositionResult | null }
/** Esito della POSIZIONE (apertura + chiusure), non della singola gamba. */
export function positionInfo(meta: Meta): PositionInfo | null {
    const m = metaObj(meta);
    const id = nOrNull(m.position_id);
    const pnl = nOrNull(m.position_pnl);
    const raw = sOrNull(m.position_result);
    const result: PositionResult | null = raw === 'won' || raw === 'lost' || raw === 'flat' ? raw : null;
    if (id == null && pnl == null && result == null) return null;
    return { id, pnl, result };
}

// ------------------------------------------------------------------- M-06
export interface HedgeInfo {
    /** frazione di stake già coperta (0-1); null = ignota */
    fraction: number | null;
    /**
     * Liability ANCORA A RISCHIO. Contratto 11/09 (seconda passata): resta la
     * liability PIENA finché una chiusura è in volo (`hedging = true`) e vale 0
     * solo a copertura COMPLETA confermata. Non è "liability × (1 − frazione)":
     * fino al fill l'esposizione è intera.
     */
    remainingLiability: number | null;
    hedgedSize: number | null;
    /** stake d'apertura, se il servizio lo ripete nel blocco (può mancare) */
    size: number | null;
    residualSize: number | null;
    complete: boolean;
    /** istante del blocco, se presente (può mancare) */
    at: string | null;
}
/** `meta.hedge` scritto dal servizio; fallback su hedged_size/residual_size. */
export function hedgeInfo(meta: Meta): HedgeInfo | null {
    const h = sub(meta, 'hedge');
    const m = metaObj(meta);
    if (h) {
        return {
            fraction: nOrNull(h.fraction),
            remainingLiability: nOrNull(h.remaining_liability),
            hedgedSize: nOrNull(h.hedged_size),
            size: nOrNull(h.size),
            residualSize: nOrNull(h.residual_size),
            complete: h.complete === true,
            at: sOrNull(h.at),
        };
    }
    const hedged = nOrNull(m.hedged_size);
    if (hedged == null || hedged <= 0) return null;
    const size = nOrNull(m.size);
    const residual = nOrNull(m.residual_size);
    return {
        fraction: size != null && size > 0 ? Math.min(1, hedged / size) : null,
        remainingLiability: null,
        hedgedSize: hedged,
        size,
        residualSize: residual,
        complete: nOrNull(m.locked_pnl) != null && (residual == null || residual <= 0.01),
        at: null,
    };
}
/** true = copertura IN CORSO (il servizio sta chiudendo): niente doppio cash out */
export function isHedging(meta: Meta): boolean {
    return metaObj(meta).hedging === true;
}

// ------------------------------------------------------------------- H-04
export type GreenupState = 'pending' | 'done' | 'hold' | 'failed' | 'blind' | 'residual_dropped';
const GREENUP_STATES: GreenupState[] = ['pending', 'done', 'hold', 'failed', 'blind', 'residual_dropped'];

export interface GreenupInfo {
    state: GreenupState | null;
    reason: string | null;
    at: string | null;
    attempts: number | null;
    nextRetryAt: string | null;
    pLose: number | null;
    ev: number | null;
    /** 'goal' | 'price' | 'take_profit' (motivo dello scatto) */
    trigger: string | null;
}
/** `meta.greenup` (stato unico del green-up sulla riga). */
export function greenupInfo(meta: Meta): GreenupInfo | null {
    const g = sub(meta, 'greenup');
    if (!g) return null;
    const raw = sOrNull(g.state);
    const state = raw && (GREENUP_STATES as string[]).includes(raw) ? (raw as GreenupState) : null;
    const info: GreenupInfo = {
        state,
        reason: sOrNull(g.reason) ?? sOrNull(g.note) ?? sOrNull(g.why),
        at: sOrNull(g.at),
        attempts: nOrNull(g.attempts) ?? nOrNull(g.rounds),
        nextRetryAt: sOrNull(g.next_retry_at),
        pLose: nOrNull(g.p_lose),
        ev: nOrNull(g.ev),
        trigger: sOrNull(g.trigger),
    };
    if (info.state == null && info.reason == null && info.attempts == null) return null;
    return info;
}

export interface GreenupHold {
    trigger: string | null;
    reason: string | null;
    pLose: number | null;
    lockedPnl: number | null;
    evHold: number | null;
    minute: number | null;
    score: string | null;
    laidScore: string | null;
    ts: string | null;
}
/** `meta.greenup_hold`: la decisione "TENGO" con i suoi numeri. */
export function greenupHold(meta: Meta): GreenupHold | null {
    const h = sub(meta, 'greenup_hold');
    if (!h) return null;
    return {
        trigger: sOrNull(h.trigger),
        reason: sOrNull(h.reason),
        pLose: nOrNull(h.p_lose),
        lockedPnl: nOrNull(h.locked_pnl),
        evHold: nOrNull(h.ev_hold),
        minute: nOrNull(h.minute),
        score: sOrNull(h.score),
        laidScore: sOrNull(h.laid_score),
        ts: sOrNull(h.ts),
    };
}

export interface GreenupBadge { state: GreenupState; label: string; cls: string; title: string }

const GREENUP_BADGE_CLS: Record<GreenupState, string> = {
    pending: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    done: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50',
    hold: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
    failed: 'bg-red-500/15 text-red-300 border-red-500/40',
    blind: 'bg-red-500/20 text-red-200 border-red-400/50',
    residual_dropped: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
};

/**
 * Badge del green-up per la riga della partita (H-04): "in attesa", "TENGO"
 * con P(perdita) ed EV, "fallito, ritento alle HH:MM", "CIECO (senza feed)",
 * "residuo abbandonato", "fatto". Prima nessuno di questi stati era visibile:
 * una posizione cieca o scoperta si leggeva come un normale "APERTO".
 */
export function greenupBadge(meta: Meta): GreenupBadge | null {
    const g = greenupInfo(meta);
    if (!g?.state) return null;
    const hold = greenupHold(meta);
    const pLose = g.pLose ?? hold?.pLose ?? null;
    const ev = g.ev ?? hold?.evHold ?? null;
    let label: string;
    switch (g.state) {
        case 'pending':
            label = 'GREEN-UP in attesa';
            break;
        case 'hold': {
            const bits = [
                pLose != null ? `P(perdita) ${fmtPct(pLose)}` : null,
                ev != null ? `EV ${fmtMoney(ev, { signed: true })}` : null,
            ].filter(Boolean).join(' · ');
            label = bits ? `TENGO · ${bits}` : 'TENGO';
            break;
        }
        case 'failed':
            label = g.nextRetryAt
                ? `GREEN-UP fallito, ritento alle ${fmtTime(g.nextRetryAt)}`
                : 'GREEN-UP FALLITO';
            break;
        case 'blind':
            label = 'GREEN-UP CIECO (senza feed)';
            break;
        case 'residual_dropped':
            label = 'residuo abbandonato';
            break;
        case 'done':
        default:
            label = 'GREEN-UP fatto';
    }
    const title = [
        g.reason ?? hold?.reason ?? null,
        g.attempts != null ? `tentativi ${g.attempts}` : null,
        g.at ? `aggiornato alle ${fmtTime(g.at)}` : null,
    ].filter(Boolean).join(' · ') || label;
    return { state: g.state, label, cls: GREENUP_BADGE_CLS[g.state], title };
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
    greenup_risk_cap: 0.15,
    greenup_ev_margin: 0.10,
    greenup_take_profit_frac: 0.9,
    greenup_take_profit_minute: 80,
    greenup_retry_s: 20,
    greenup_max_attempts: 15,
    // H-07: il SERVIZIO ha 'off' e 0.15 (Betfair/omega/omega_config.py). Il
    // default della UI non deve MAI riaccendere il calibratore né abbassare il
    // cap di rischio con un "Salva" involontario.
    model_calibration: 'off',
    model_calibration_path: '',
    engine: 'legs',
    execution_mode: 'auto',
    paper_fill_ttl_s: 45,
    omega_live_via_flumine: true,
    live_fill_deadline_s: 20,
    model_min_goal_distance: 2,
    model_empirical: 'veto',
    model_empirical_max_minute: 60,
    lambda_market_grid: true,
    lambda_live_fallback: true,
    select_cost_aware: true,
    select_p_band_ratio: 2,
    model_use_yellow_cards: true,
    model_tail_factor: 1.3,
    model_lambda_cv: 0.30,
    select_k_se: 0,
    select_p_hedge: 0.5,
    select_ev_kappa: 1,
};

export type OmegaNumericParamKey = {
    [K in keyof OmegaParams]: OmegaParams[K] extends number ? K : never;
}[keyof OmegaParams];

// ------------------------------------------------ pannello parametri (M-09/M-10)
// SPEC UNICA per ParamsSheetBase. min/max/step sono quelli VERI della whitelist
// del servizio (Betfair/omega/omega_config.py `_SPEC`): prima la UI dichiarava
// limiti diversi (`greenup_ev_margin` "0-1" mentre è in EURO fino a 1000,
// `greenup_max_attempts` min 1 mentre il servizio ammette 0, `settle_delay_s`
// max 300 vs 600…) e un valore "valido" per la UI veniva clampato in silenzio
// dal servizio. Tutte le chiavi della whitelist hanno una UI: 19 parametri
// (motore, λ, ranking, esecuzione) prima non erano raggiungibili (M-10).
export const OMEGA_PARAM_GROUPS: ParamGroup[] = [
    {
        label: 'Selezione e finestre',
        note: 'quali risultati bancare e in quale minuto: la parte che decide QUANTE gambe entrano.',
        fields: [
            { key: 'engine', label: 'Motore', type: 'select', hint: 'v2 = due gambe per partita con selezione per probabilità', options: [
                { value: 'legs', label: 'due gambe (1T Half Time Score + 2T Correct Score)' },
                { value: 'single', label: 'v1: una gamba sul Correct Score (kill-switch)' },
            ] },
            { key: 'price_min', label: 'Quota lay MIN', type: 'number', step: 1, min: 1.01, max: 1000, hint: 'sotto: risultato troppo probabile' },
            { key: 'price_max', label: 'Quota lay MAX', type: 'number', step: 5, min: 1.01, max: 1000, hint: 'sopra: profitto irrisorio e liability enorme' },
            { key: 'ht_entry_min', label: 'Gamba 1T: minuto MIN', type: 'number', step: 1, min: 0, max: 45, hint: 'Half Time Score: ingresso dal minuto reale del feed' },
            { key: 'ht_entry_max', label: 'Gamba 1T: minuto MAX', type: 'number', step: 1, min: 0, max: 45, hint: 'niente 1T dopo questo minuto' },
            { key: 'ft_entry_min', label: 'Gamba 2T: minuto MIN', type: 'number', step: 1, min: 45, max: 130, hint: 'Correct Score finale: ingresso nel 2T' },
            { key: 'ft_entry_max', label: 'Gamba 2T: minuto MAX', type: 'number', step: 1, min: 45, max: 130, hint: 'niente 2T dopo questo minuto' },
            { key: 'model_p_max_pct', label: 'P(modello) MAX (punti %)', type: 'number', step: 0.5, min: 0.01, max: 50, hint: 'si banca solo sotto questa probabilità; il valore è in PUNTI percentuali (2 = 2 %)' },
            { key: 'model_min_goal_distance', label: 'Distanza minima dal punteggio (gol)', type: 'number', step: 1, min: 1, max: 5, hint: 'gol AGGIUNTIVI che servirebbero perché il risultato bancato esca' },
            { key: 'max_events', label: 'Max eventi al giorno', type: 'number', step: 1, min: 0, max: 1000, hint: '0 = illimitato' },
            { key: 'min_lay_liquidity', label: 'Liquidità lay MIN (€)', type: 'number', step: 1, min: 0, max: 100000, hint: 'importo minimo disponibile al best lay' },
            { key: 'min_stake', label: 'Stake MIN (€)', type: 'number', step: 0.5, min: 0.5, max: 1000, hint: 'lay minimo Betfair .it = 0,50 €' },
            { key: 'include_aggregate', label: 'Includi i risultati aggregati ("Any Other …")', type: 'boolean' },
            { key: 'entry_window_source', label: 'Sorgente del minuto', type: 'select', options: [
                { value: 'score', label: 'score (minuto e punteggio dal feed live)' },
                { value: 'clock', label: 'clock (orario del calcio d’inizio)' },
            ] },
        ],
    },
    {
        label: 'Motore v1 (una gamba)',
        note: 'usati SOLO con motore "v1": il motore a due gambe ignora questi due minuti.',
        fields: [
            { key: 'entry_minute_min', label: 'v1: minuto MIN', type: 'number', step: 1, min: 0, max: 130 },
            { key: 'entry_minute_max', label: 'v1: minuto MAX', type: 'number', step: 1, min: 0, max: 130 },
        ],
    },
    {
        label: 'Modello e probabilità',
        note: 'come si stima la P del risultato bancato: λ, coda, veto empirico, ranking.',
        fields: [
            { key: 'model_calibration', label: 'Calibrazione P(modello)', type: 'select', hint: 'il calibratore condiviso è addestrato sulla Safe Strategy: su Omega resta OFF finché non esiste una famiglia sua', options: [
                { value: 'off', label: 'off (probabilità grezza del modello) — default del servizio' },
                { value: 'auto', label: 'auto (curva per famiglia di risultati)' },
            ] },
            { key: 'model_calibration_path', label: 'Percorso del calibratore', type: 'text', hint: 'vuoto = percorso di default' },
            { key: 'model_empirical', label: 'Veto empirico HT→FT (gamba 2T)', type: 'select', options: [
                { value: 'veto', label: 'veto (P = la più alta fra modello e dati storici)' },
                { value: 'off', label: 'off (solo modello)' },
            ] },
            { key: 'model_empirical_max_minute', label: 'Veto empirico: minuto massimo', type: 'number', step: 1, min: 45, max: 90 },
            { key: 'model_tail_factor', label: 'Fattore di coda su P ≤ 5 %', type: 'number', step: 0.1, min: 0.5, max: 5, hint: '1 = nessuna correzione; banco 11/09: 1,3' },
            { key: 'model_lambda_cv', label: 'Incertezza sui λ (cv)', type: 'number', step: 0.05, min: 0, max: 1, hint: '0 = Poisson puro; 0,30 = coda osservata sui dati' },
            { key: 'model_use_yellow_cards', label: 'Usa i cartellini gialli del feed', type: 'boolean' },
            { key: 'lambda_market_grid', label: 'λ impliciti nell’intero mercato (CS + Over/Under)', type: 'boolean' },
            { key: 'lambda_live_fallback', label: 'λ dall’Over/Under LIVE se mancano fixture e quote pre-KO', type: 'boolean' },
            { key: 'select_cost_aware', label: 'A pari probabilità scegli il risultato più economico da coprire', type: 'boolean' },
            { key: 'select_p_band_ratio', label: 'Banda di probabilità equivalente (× la più bassa)', type: 'number', step: 0.5, min: 1, max: 10 },
            { key: 'select_k_se', label: 'Selezione conservativa: k × SE', type: 'number', step: 0.1, min: 0, max: 3, hint: '0 = solo il centro (raccomandato finché il banco non misura la SE)' },
            { key: 'select_p_hedge', label: 'P di dover coprire (ranking EV)', type: 'number', step: 0.05, min: 0, max: 1 },
            { key: 'select_ev_kappa', label: 'Peso del costo di copertura (ranking EV)', type: 'number', step: 0.1, min: 0, max: 5 },
        ],
    },
    {
        label: 'Green-up automatico',
        note: 'la scommessa diventa un TRADE: il servizio chiude a mercato appena il risultato bancato diventa raggiungibile, oppure TIENE se il modello dice che uscire butta valore. Ogni passo compare in "Attività del servizio" e come badge sulla riga della partita.',
        fields: [
            { key: 'greenup_enabled', label: 'Green-up automatico attivo', type: 'boolean' },
            { key: 'greenup_mode', label: 'Modalità green-up', type: 'select', options: [
                { value: 'auto', label: 'auto (tiene o chiude per P(perdita) ed EV)' },
                { value: 'off', label: 'off (nessun green-up)' },
            ] },
            { key: 'greenup_trigger_distance', label: 'Scatta a distanza (gol)', type: 'number', step: 1, min: 0, max: 3, hint: '1 = appena manca UN gol al risultato bancato si valuta la chiusura' },
            { key: 'greenup_price_trigger_ratio', label: 'Scatta se la quota scende sotto (frazione dell’ingresso)', type: 'number', step: 0.05, min: 0.05, max: 1, hint: '0,5 = quota lay dimezzata: il mercato sta convergendo sul risultato' },
            { key: 'greenup_settle_delay_s', label: 'Attesa assestamento dopo il gol (s)', type: 'number', step: 5, min: 0, max: 600, hint: 'VAR e correzioni: si aspetta che il mercato si riallinei' },
            { key: 'greenup_hold_max_risk', label: 'TIENI se P(perdita) ≤ (frazione 0-1)', type: 'number', step: 0.005, min: 0, max: 1, hint: 'sotto questa probabilità di perdita il servizio TIENE (attività "GREEN-UP · TENGO")' },
            { key: 'greenup_risk_cap', label: 'ESCI comunque se P(perdita) ≥ (frazione 0-1)', type: 'number', step: 0.01, min: 0, max: 1, hint: 'oltre questa soglia si chiude anche con EV a favore (default del servizio 0,15)' },
            { key: 'greenup_ev_margin', label: 'Margine EV per tenere (€)', type: 'number', step: 0.5, min: 0, max: 1000, hint: 'in EURO, non una frazione: tenere deve valere almeno questo margine rispetto al green-up immediato' },
            { key: 'greenup_take_profit_frac', label: 'Incassa a frazione del massimo (0,1-1)', type: 'number', step: 0.05, min: 0.1, max: 1, hint: '0,9 = si chiude con il 90 % del profitto massimo in mano' },
            { key: 'greenup_take_profit_minute', label: 'Incassa comunque dal minuto', type: 'number', step: 1, min: 0, max: 130 },
            { key: 'greenup_retry_s', label: 'Residuo: attesa fra i tentativi (s)', type: 'number', step: 5, min: 2, max: 600 },
            { key: 'greenup_max_attempts', label: 'Residuo: tentativi massimi', type: 'number', step: 1, min: 0, max: 100, hint: '0 = nessun ritentativo' },
        ],
    },
    {
        label: 'Protezioni e cap',
        note: 'i tre cap sono OFF di default (Omega è set-and-forget): mettili > 0 per attivarli.',
        fields: [
            { key: 'commission_pct', label: 'Commissione %', type: 'number', step: 0.5, min: 0, max: 20, hint: 'aliquota Betfair (5 % di default). Sui trade già piazzati vale quella FISSATA sulla riga, non questa.' },
            { key: 'max_liability_per_match', label: 'Cap liability per partita (€)', type: 'number', step: 10, min: 0, max: 1000000, hint: '0 = OFF' },
            { key: 'daily_loss_cap', label: 'Stop-loss giornaliero (€)', type: 'number', step: 25, min: 0, max: 1000000, hint: '0 = OFF' },
            { key: 'max_open_liability', label: 'Cap liability aperta (€)', type: 'number', step: 100, min: 0, max: 10000000, hint: '0 = OFF' },
            { key: 'stop_on_goal', label: 'Stop ai nuovi ingressi a obiettivo raggiunto', type: 'boolean' },
        ],
    },
    {
        label: 'Esecuzione',
        note: 'come vengono mandati gli ordini. In PAPER la coda replica il live (betDelay, liquidità, FOK).',
        fields: [
            { key: 'poll_interval_s', label: 'Cadenza del ciclo (s)', type: 'number', step: 5, min: 5, max: 600 },
            { key: 'execution_mode', label: 'Percorso di esecuzione', type: 'select', options: [
                { value: 'auto', label: 'auto (coda flumine quando il gate passa)' },
                { value: 'rest', label: 'rest (percorso legacy)' },
            ] },
            { key: 'paper_fill_ttl_s', label: 'PAPER: TTL quasi-FOK (s)', type: 'number', step: 5, min: 5, max: 600 },
            { key: 'omega_live_via_flumine', label: 'LIVE via coda flumine (FILL_OR_KILL)', type: 'boolean' },
            { key: 'live_fill_deadline_s', label: 'LIVE: scadenza dell’esito FOK (s)', type: 'number', step: 5, min: 5, max: 300 },
        ],
    },
];

/** tutte le chiavi che hanno una UI (i test verificano che coprano la whitelist) */
export const OMEGA_PARAM_KEYS: string[] = OMEGA_PARAM_GROUPS.flatMap((g) => g.fields.map((f) => f.key));

/**
 * H-07 — cosa mandare a `omega_update_params`: l'oggetto LETTO DAL CONTROL più
 * SOLO le chiavi che l'utente ha davvero cambiato. Un default della UI diverso
 * da quello del servizio (è capitato con `model_calibration` e
 * `greenup_risk_cap`) non deve poter sovrascrivere il valore vivo del servizio
 * con un "Salva" fatto per cambiare altro.
 */
export function omegaParamsPatch(
    serverParams: Record<string, unknown> | null | undefined,
    draft: Record<string, unknown>,
): Record<string, unknown> {
    const server = (serverParams ?? {}) as Record<string, unknown>;
    const out: Record<string, unknown> = { ...server };
    const same = (a: unknown, b: unknown) => {
        if (typeof a === 'boolean' || typeof b === 'boolean') return Boolean(a) === Boolean(b);
        const na = Number(a), nb = Number(b);
        if (Number.isFinite(na) && Number.isFinite(nb) && a !== '' && b !== '' && a != null && b != null) return na === nb;
        return String(a ?? '') === String(b ?? '');
    };
    for (const [k, v] of Object.entries(draft)) {
        if (Object.prototype.hasOwnProperty.call(server, k)) {
            if (!same(server[k], v)) out[k] = v;
            continue;
        }
        // chiave che il servizio non ha ancora nel suo oggetto: si manda SOLO se
        // l'utente l'ha portata fuori dal default della UI, altrimenti sarebbe
        // un default della UI scritto sopra quello del servizio
        const def = (OMEGA_PARAM_DEFAULTS as unknown as Record<string, unknown>)[k];
        if (def === undefined || !same(def, v)) out[k] = v;
    }
    return out;
}

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
    const more = Number(d.activity_more);
    return {
        control: d.control ?? null,
        aggregates: d.aggregates ?? null,
        activity: d.activity ?? [],
        activity_more: Number.isFinite(more) && more > 0 ? Math.trunc(more) : 0,
        activity_day: typeof d.activity_day === 'string' ? d.activity_day.slice(0, 10) : null,
        goal_today: Number.isFinite(g) && d.goal_today != null ? g : null,
        // v5 assente (migrazione non applicata) → NON è uno snapshot storicizzato
        goal_snapshot: d.goal_snapshot === true,
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
