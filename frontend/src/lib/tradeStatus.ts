// ============================================================================
// tradeStatus.ts — MAPPE ETICHETTE UNICHE del design system di trading.
//
// Tre sezioni (Omega, Safe Strategy, Mike) avevano tre mappe di stati, tre
// glossari e tre dizionari di attivita': sotto gli occhi di un trader lo stesso
// concetto deve avere SEMPRE la stessa parola e lo stesso colore.
//
// Contenuto:
//   - STATUS_META / statusMeta()   -> stato di un TRADE (in corso/aperto/...)
//   - BOT_STATUS_META              -> stato del BOT (inattivo/in corsa/...)
//   - sideMeta()                   -> BACK (sky) / LAY (rose)
//   - T                            -> glossario testuale unico
//   - ACTIVITY_BASE / activityMeta -> attivita' del servizio, in italiano
//
// Tutto PURO: nessun import di React, nessuna chiamata di rete.
// ============================================================================
import { fmtMoney, fmtOdds } from '@/lib/format';

// --------------------------------------------------------------- trade status
export type TradeStatus =
    | 'pending' | 'open' | 'hedged' | 'won' | 'lost' | 'void' | 'error';

export interface Meta { label: string; cls: string }

/** Stati di un trade: UNA etichetta italiana e UN colore per stato. */
export const STATUS_META: Record<TradeStatus, Meta> = {
    pending: { label: 'IN CORSO', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    open: { label: 'APERTO', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' },
    hedged: { label: 'CHIUSO', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' },
    won: { label: 'VINTO', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
    lost: { label: 'PERSO', cls: 'bg-red-500/15 text-red-300 border-red-500/40' },
    void: { label: 'VOID', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40' },
    error: { label: 'ERRORE', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/40' },
};

/**
 * Stato "extra" fuori dall'enum del DB: la riconciliazione (ordine REALE a
 * esito IGNOTO). L'etichetta è quella che usano già tutte e tre le sezioni
 * ("IN VERIFICA SU BETFAIR"): era la mappa condivisa a dire un'altra parola
 * ("DA RICONCILIARE"), cioè due nomi per lo stesso rischio.
 */
export const RECONCILING_META: Meta = {
    label: 'IN VERIFICA SU BETFAIR',
    cls: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/40',
};

/**
 * Riga TERMINALE: è PROVATO che nessun ordine reale esiste (FOK ucciso, paper
 * senza fill, richiesta mai creata). Non è una posizione viva e non è un
 * rischio: non va mostrata come un normale "IN CORSO" che non finisce mai.
 */
export const TERMINAL_ERROR_META: Meta = {
    label: 'ERRORE (definitivo)',
    cls: 'bg-orange-500/20 text-orange-200 border-orange-400/50',
};

/** esiti CERTI: nessun flag di riconciliazione/terminale può sovrascriverli */
const SETTLED_STATUS = new Set(['won', 'lost', 'void']);

/**
 * Stato di un trade -> etichetta + classi.
 * Precedenza: esito certo > riga terminale > riconciliazione > stato del DB.
 * Un trade che il servizio non ha ancora riconciliato NON va mostrato come se
 * fosse a posto; ma un esito già arrivato resta l'esito.
 */
export function statusMeta(
    status: string | null | undefined,
    opts: { reconciling?: boolean; terminal?: boolean } = {},
): Meta {
    const key = String(status ?? '').toLowerCase() as TradeStatus;
    const settled = SETTLED_STATUS.has(key);
    if (!settled && opts.terminal) return TERMINAL_ERROR_META;
    if (!settled && opts.reconciling) return RECONCILING_META;
    return STATUS_META[key] ?? STATUS_META.error;
}

// ----------------------------------------------------------------- bot status
export type BotStatus = 'idle' | 'running' | 'stopping' | 'stopped' | 'error';

/** Stato del BOT: identico nelle tre sezioni (prima erano tre mappe). */
export const BOT_STATUS_META: Record<BotStatus, Meta> = {
    idle: { label: 'INATTIVO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    running: { label: 'IN CORSA', cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 animate-pulse' },
    stopping: { label: 'IN ARRESTO', cls: 'bg-amber-500/20 text-amber-300 border-amber-500/50' },
    stopped: { label: 'FERMO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    error: { label: 'ERRORE', cls: 'bg-red-500/20 text-red-300 border-red-500/50' },
};

/** `prefix` = parola davanti ("BOT" -> "BOT IN CORSA"), per compatibilita' UI. */
export function botStatusMeta(status: string | null | undefined, prefix = ''): Meta {
    const key = String(status ?? 'idle').toLowerCase() as BotStatus;
    const m = BOT_STATUS_META[key] ?? BOT_STATUS_META.idle;
    return prefix ? { label: `${prefix} ${m.label}`, cls: m.cls } : m;
}

/**
 * Stati IN PIU' del bot scalper 1-tick (theta), che ha un ciclo di armamento
 * prima della corsa: prima la card della missione mostrava la chiave inglese in
 * maiuscolo ("ARMING", "REQUESTED") accanto a etichette italiane.
 */
export const SCALPER_STATUS_EXTRA: Record<string, Meta> = {
    requested: { label: 'RICHIESTO', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' },
    arming: { label: 'IN ARMAMENTO', cls: 'bg-amber-500/20 text-amber-300 border-amber-500/50' },
    armed: { label: 'ARMATO', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' },
};

/** Stato dello scalper in ITALIANO: gli stati propri + quelli comuni del bot. */
export function scalperStatusMeta(status: string | null | undefined): Meta {
    const key = String(status ?? 'idle').toLowerCase();
    return SCALPER_STATUS_EXTRA[key] ?? botStatusMeta(key);
}

// ------------------------------------------------------------------ lato (side)
export type TradeSide = 'back' | 'lay';

export const SIDE_META: Record<TradeSide, Meta> = {
    back: { label: 'BACK', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' },
    lay: { label: 'LAY', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/40' },
};

/** BACK = sky (punta), LAY = rose (banca). Mai altri colori. */
export function sideMeta(side: string | null | undefined): Meta {
    return String(side ?? '').toLowerCase() === 'lay' ? SIDE_META.lay : SIDE_META.back;
}

// ------------------------------------------------------------------- glossario
/**
 * GLOSSARIO UNICO: la UI deve usare SEMPRE queste parole.
 * Vietato reintrodurre "Capitale a rischio", "responsabilita'", "Cash-out",
 * o stati in inglese.
 */
export const T = {
    // esposizione e risultato
    openLiability: 'Liability aperta',
    lockedPnl: 'P&L bloccato',
    pnlToday: 'P&L oggi',
    pnlTotal: 'P&L totale',
    realizedToday: 'realizzato oggi',
    // operativita'
    cashOut: 'Cash out',
    cashOutQueued: 'Cash out in coda',
    cashOutSent: 'Cash out inviato',
    cashOutFailed: 'Cash out fallito',
    closedAtMarket: 'CHIUSO A MERCATO',
    greenUp: 'Green-up',
    // giornata
    operatingDay: 'giornata operativa',
    dayBarTitle: 'Giornata operativa',
    goalToday: 'Obiettivo di oggi',
    goalHit: 'CENTRATO',
    remaining: 'resta',
    matches: 'partite',
    operations: 'operazioni',
    live: 'vive',
    // modalita'
    modePaper: 'MODALITÀ PAPER',
    modeLive: 'MODALITÀ LIVE',
    liveConfirmTitle: 'Passare a LIVE (soldi veri)?',
    liveConfirmCancel: 'Annulla',
    liveConfirmOk: 'Sì, passa a LIVE',
    // servizio
    feedAlive: 'feed vivo',
    feedStopped: 'feed FERMO',
    feedNoData: 'feed: nessun dato',
    serviceNoBeat: 'nessun battito',
    restartApp: 'riavvia l’app desktop',
    activityToday: 'Attività del servizio di oggi',
    noActivityToday: 'nessuna attività oggi',
    saveParams: 'Salva parametri',
    resetParams: 'Default',
    start: 'Avvia',
    stop: 'Ferma',
} as const;

// -------------------------------------------------------------- attivita' bot
export interface ActivityMeta extends Meta {
    /** true = l'utente DEVE accorgersene (rosso, mai sepolto nella lista) */
    critical?: boolean;
}

const NEUTRAL = 'bg-white/5 text-slate-300 border-white/10';
const INFO = 'bg-sky-500/15 text-sky-300 border-sky-500/40';
const WARN = 'bg-amber-500/15 text-amber-300 border-amber-500/40';
const BAD = 'bg-red-500/15 text-red-300 border-red-500/40';
const GOOD = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40';
const CLOSE = 'bg-teal-500/15 text-teal-300 border-teal-500/40';
const MUTED = 'bg-white/5 text-slate-400 border-white/10';

/**
 * Attivita' comuni ai tre bot. Ogni chiave = un `kind` scritto dal servizio.
 * Le sezioni possono aggiungere kind propri passando `extra` ad activityMeta().
 */
export const ACTIVITY_BASE: Record<string, ActivityMeta> = {
    // ciclo di vita del servizio
    start: { label: 'AVVIO', cls: GOOD },
    stop: { label: 'STOP', cls: NEUTRAL },
    state: { label: 'FASE', cls: NEUTRAL },
    // ordini
    place: { label: 'ORDINE', cls: INFO },
    place_deferred: { label: 'ORDINE (betDelay)', cls: INFO },
    would_place: { label: 'ORDINE (dry)', cls: MUTED },
    cancel: { label: 'ANNULLO', cls: WARN },
    no_fill: { label: 'NON ABBINATO', cls: WARN },
    skip: { label: 'SALTO', cls: MUTED },
    // chiusure
    cashout: { label: 'CASH OUT', cls: CLOSE },
    cashout_done: { label: 'CASH OUT ESEGUITO', cls: CLOSE },
    cashout_failed: { label: 'CASH OUT FALLITO', cls: BAD, critical: true },
    greenup: { label: 'GREEN-UP', cls: GOOD },
    greenup_hold: { label: 'GREEN-UP · attesa', cls: INFO },
    greenup_wait: { label: 'GREEN-UP · conferma', cls: WARN },
    greenup_retry: { label: 'GREEN-UP · ritento', cls: WARN },
    greenup_failed: { label: 'GREEN-UP FALLITO', cls: BAD, critical: true },
    exit: { label: 'USCITA', cls: CLOSE },
    exit_hold: { label: 'USCITA · tiene', cls: INFO },
    exit_wait: { label: 'USCITA · attesa prezzi', cls: WARN },
    exit_retry: { label: 'USCITA · ritento', cls: WARN },
    exit_failed: { label: 'USCITA FALLITA', cls: BAD, critical: true },
    close_retries_exhausted: { label: 'CHIUSURA BLOCCATA', cls: BAD, critical: true },
    cover: { label: 'COPERTURA', cls: CLOSE },
    cancel_rejected: { label: 'ANNULLO RIFIUTATO', cls: BAD, critical: true },
    place_exhausted: { label: 'PIAZZAMENTO: TENTATIVI ESAURITI', cls: BAD, critical: true },
    combo_incomplete: { label: 'COMBO INCOMPLETA (posizione nuda)', cls: BAD, critical: true },
    // regolamento
    settle: { label: 'REGOLAMENTO', cls: NEUTRAL },
    settled: { label: 'REGOLATA', cls: NEUTRAL },
    settle_position: { label: 'POSIZIONE REGOLATA', cls: NEUTRAL },
    market_missing: { label: 'MERCATO SPARITO', cls: BAD, critical: true },
    // riconciliazione e configurazione
    reconcile: { label: 'RICONCILIAZIONE', cls: INFO },
    reconcile_fix: { label: 'RICONCILIAZIONE · corretto', cls: WARN },
    reconcile_failed: { label: 'RICONCILIAZIONE FALLITA', cls: BAD, critical: true },
    params_update: { label: 'PARAMETRI aggiornati', cls: NEUTRAL },
    params_clamped: { label: 'PARAMETRI clampati', cls: WARN },
    params_invalid: { label: 'PARAMETRI NON VALIDI', cls: BAD, critical: true },
    config_warn: { label: 'CONFIGURAZIONE', cls: WARN },
    // guardie
    feed_blind: { label: 'FEED CIECO', cls: BAD, critical: true },
    feed_back: { label: 'FEED TORNATO', cls: GOOD },
    daily_stop: { label: 'STOP GIORNALIERO', cls: BAD, critical: true },
    error: { label: 'ERRORE', cls: BAD, critical: true },
    armed: { label: 'ARMATA', cls: CLOSE },
    pre_cycle: { label: 'CICLO PRE', cls: GOOD },
};

/** dizionario di PAROLE per tradurre un kind mai visto prima */
const WORDS: Record<string, string> = {
    place: 'ordine', placed: 'piazzato', order: 'ordine',
    cancel: 'annullo', cancelled: 'annullato', canceled: 'annullato',
    fill: 'abbinato', filled: 'abbinato',
    retry: 'ritento', retries: 'ritenti', exhausted: 'esauriti',
    failed: 'fallito', fail: 'fallito', error: 'errore',
    pending: 'in corso', done: 'eseguito', ok: 'eseguito',
    skip: 'salto', skipped: 'saltato',
    settle: 'regolamento', settled: 'regolata',
    cashout: 'cash out', greenup: 'green-up', hedge: 'copertura', cover: 'copertura',
    exit: 'uscita', hold: 'tiene', start: 'avvio', stop: 'stop', state: 'fase',
    open: 'apertura', close: 'chiusura', closed: 'chiuso',
    reconcile: 'riconciliazione', params: 'parametri', config: 'configurazione',
    daily: 'giornaliero', loss: 'perdita', stake: 'importo', liability: 'liability',
    feed: 'feed', blind: 'cieco', stale: 'vecchio', armed: 'armata',
    warn: 'avviso', warning: 'avviso', info: 'info', wait: 'attesa',
    delayed: 'rinviato', deferred: 'rinviato', dry: 'dry',
    cycle: 'ciclo', pre: 'pre', live: 'live', manual: 'manuale', auto: 'automatico',
};

const CRITICAL_HINTS = ['fail', 'error', 'blind', 'exhaust', 'stop_loss', 'daily_stop'];

/**
 * kind -> etichetta leggibile. Se il kind non e' nel dizionario condiviso (ne'
 * negli `extra` della sezione) lo TRADUCE parola per parola: mai la chiave
 * inglese nuda in maiuscolo quando esiste una resa italiana ragionevole.
 */
export function activityMeta(
    kind: string | null | undefined,
    extra?: Record<string, ActivityMeta>,
): ActivityMeta {
    const key = String(kind ?? '').trim();
    if (!key) return { label: 'ATTIVITÀ', cls: NEUTRAL };
    const lower = key.toLowerCase();
    const hit = extra?.[key] ?? extra?.[lower] ?? ACTIVITY_BASE[lower];
    if (hit) return hit;
    const tokens = lower.split(/[_\-.\s]+/).filter(Boolean);
    const translated = tokens.map((t) => WORDS[t] ?? null);
    const known = translated.filter((t) => t !== null).length;
    const critical = CRITICAL_HINTS.some((h) => lower.includes(h));
    if (known === 0) {
        // nessuna parola riconosciuta: lo dichiariamo, non lo mascheriamo
        return { label: `${key} (kind sconosciuto)`, cls: MUTED, critical };
    }
    const label = tokens.map((t, i) => translated[i] ?? t).join(' · ').toUpperCase();
    return { label, cls: critical ? BAD : NEUTRAL, critical };
}

/**
 * Riga di testo leggibile per un payload di attivita' QUALSIASI: usa i campi
 * comuni (motivo/errore/nota/messaggio, lato, prezzo, size, P&L) con i
 * formatter unici. Serve da fallback quando la sezione non ha una `line` sua.
 */
export function activityLineGeneric(payload: Record<string, unknown> | null | undefined): string {
    const p = payload ?? {};
    const parts: string[] = [];
    const ev = p.event_name ?? p.event ?? null;
    if (ev) parts.push(String(ev));
    const sel = p.selection_name ?? p.selection ?? p.runner_name ?? null;
    const side = p.side ? String(p.side).toLowerCase() : null;
    if (sel) parts.push(`${side ? `${side} ` : ''}${String(sel)}`);
    else if (side) parts.push(side.toUpperCase());
    const size = Number(p.size);
    const price = Number(p.price);
    if (Number.isFinite(size) && Number.isFinite(price)) parts.push(`${fmtMoney(size)} @ ${fmtOdds(price)}`);
    else if (Number.isFinite(size)) parts.push(fmtMoney(size));
    else if (Number.isFinite(price)) parts.push(fmtOdds(price));
    const pnl = Number(p.pnl ?? p.locked ?? p.locked_pnl);
    if (Number.isFinite(pnl)) parts.push(fmtMoney(pnl, { signed: true }));
    const reason = p.reason ?? p.err ?? p.error ?? p.note ?? p.msg ?? p.message ?? null;
    if (reason) parts.push(String(reason));
    if (parts.length === 0) {
        const keys = Object.keys(p);
        return keys.length ? JSON.stringify(p).slice(0, 140) : '';
    }
    return parts.join(' · ');
}
