// ============================================================================
// safeActivity.ts — ATTIVITÀ DEL SERVIZIO Safe Strategy, in italiano.
//
// Il servizio (Betfair/safe_strategy/bot_service.py) scrive su
// safe_strategy_activity ogni decisione che conta: salti, blocchi di rischio,
// tentativi di piazzamento, uscite, riconciliazioni, regolamenti, feed cieco.
// Prima nessun componente lo leggeva (audit H-16): il trader non sapeva
// PERCHÉ il bot non entrava.
//
// Qui c'è UNA voce per ogni `kind` che il servizio scrive davvero, con
// etichetta italiana, colore e `critical: true` quando l'utente DEVE
// accorgersene. I kind sconosciuti restano gestiti da `activityMeta` del design
// system (traduzione parola per parola), mai la chiave inglese nuda.
// ============================================================================
import { fmtMoney, fmtOdds, fmtTime } from '@/lib/format';
import { activityMeta, type ActivityMeta } from '@/lib/tradeStatus';

const NEUTRAL = 'bg-white/5 text-slate-300 border-white/10';
const INFO = 'bg-sky-500/15 text-sky-300 border-sky-500/40';
const WARN = 'bg-amber-500/15 text-amber-300 border-amber-500/40';
const BAD = 'bg-red-500/15 text-red-300 border-red-500/40';
const GOOD = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40';
const CLOSE = 'bg-teal-500/15 text-teal-300 border-teal-500/40';
const MUTED = 'bg-white/5 text-slate-400 border-white/10';

/**
 * TUTTI i kind scritti dal servizio Safe Strategy.
 * Aggiungendone uno nuovo al backend va aggiunto QUI (con test): un badge
 * grigio con una parola inglese sotto gli occhi di un trader è un bug.
 */
export const SAFE_ACTIVITY_EXTRA: Record<string, ActivityMeta> = {
    // ---- ciclo di vita
    stop: { label: 'BOT FERMATO', cls: NEUTRAL },
    error: { label: 'ERRORE DEL SERVIZIO', cls: BAD, critical: true },

    // ---- parametri
    params_invalid: { label: 'PARAMETRI NON VALIDI', cls: BAD, critical: true },
    params_clamped: { label: 'PARAMETRI CORRETTI', cls: WARN },

    // ---- piazzamento
    place: { label: 'ORDINE PIAZZATO', cls: INFO },
    place_pending: { label: 'ORDINE IN ATTESA DI ABBINAMENTO', cls: WARN },
    place_retry: { label: 'ORDINE · RITENTO', cls: WARN },
    place_exhausted: { label: 'ORDINE NON PIAZZATO (tentativi esauriti)', cls: BAD, critical: true },
    place_exception: { label: 'ORDINE A ESITO IGNOTO', cls: BAD, critical: true },
    confirm_failed: { label: 'CONFERMA ORDINE FALLITA', cls: BAD, critical: true },
    flumine_enqueue: { label: 'ORDINE IN CODA (flumine)', cls: INFO },

    // ---- non entrato
    skip: { label: 'NON ENTRATO', cls: MUTED },
    risk_block: { label: 'BLOCCATO DAL RISCHIO', cls: WARN, critical: true },
    combo_incomplete: { label: 'COMBINAZIONE INCOMPLETA', cls: BAD, critical: true },

    // ---- riconciliazione
    reconcile_error: { label: 'RICONCILIAZIONE FALLITA', cls: BAD, critical: true },
    reconciled_open: { label: 'RICONCILIATA · posizione aperta', cls: WARN },
    reconciled_free: { label: 'RICONCILIATA · nessun ordine', cls: NEUTRAL },
    reconciled_error: { label: 'RICONCILIATA · in errore', cls: BAD, critical: true },

    // ---- uscite
    exit: { label: 'USCITA ESEGUITA', cls: CLOSE },
    exit_hold: { label: 'USCITA · tengo la posizione', cls: INFO },
    exit_wait: { label: 'USCITA · attendo il prezzo', cls: WARN },
    exit_retry: { label: 'USCITA · ritento', cls: WARN },
    exit_failed: { label: 'USCITA FALLITA', cls: BAD, critical: true },
    cashout: { label: 'CASH OUT', cls: CLOSE },
    cashout_error: { label: 'CASH OUT FALLITO', cls: BAD, critical: true },
    cancel: { label: 'ORDINE ANNULLATO', cls: WARN },
    cancel_rejected: { label: 'ANNULLO RIFIUTATO', cls: BAD, critical: true },

    // ---- regolamento
    settle: { label: 'GAMBA REGOLATA', cls: NEUTRAL },
    settle_position: { label: 'POSIZIONE REGOLATA', cls: GOOD },
    settle_wait: { label: 'REGOLAMENTO · attendo Betfair', cls: MUTED },
    settle_error: { label: 'REGOLAMENTO FALLITO', cls: BAD, critical: true },
    settle_orphan_closing: { label: 'CHIUSURA ORFANA', cls: WARN, critical: true },

    // ---- feed
    market_missing: { label: 'MERCATO SPARITO DAL FEED', cls: BAD, critical: true },
    feed_blind: { label: 'FEED CIECO', cls: BAD, critical: true },
    feed_back: { label: 'FEED TORNATO', cls: GOOD },

    // ---- coda flumine (esecuzione condivisa con Omega)
    flumine_fill: { label: 'ABBINATO (flumine)', cls: GOOD },
    flumine_no_fill: { label: 'NON ABBINATO (flumine)', cls: WARN },
    flumine_cancel_timeout: { label: 'ANNULLO SENZA RISPOSTA (flumine)', cls: BAD, critical: true },
    flumine_recovered: { label: 'ORDINE RECUPERATO (flumine)', cls: WARN },
    flumine_live_freed: { label: 'LIABILITY LIBERATA (flumine)', cls: NEUTRAL },
    flumine_live_orphan: { label: 'ORDINE REALE ORFANO (flumine)', cls: BAD, critical: true },
    flumine_poll_error: { label: 'CODA NON RAGGIUNGIBILE (flumine)', cls: BAD, critical: true },
};

/** Etichetta di un kind Safe Strategy (con fallback del design system). */
export function safeActivityMeta(kind: string): ActivityMeta {
    return activityMeta(kind, SAFE_ACTIVITY_EXTRA);
}

/** motivi tecnici del servizio → italiano (quelli che finiscono nel payload) */
const REASON_IT: Record<string, string> = {
    place_exception_reconciling: 'ordine a esito ignoto: in verifica su Betfair',
    reconcile_ordine_assente: 'nessun ordine trovato su Betfair',
    reconcile_paper_senza_fill: 'paper: nessun abbinamento entro il TTL',
    reconcile_orphan_old: 'riserva orfana troppo vecchia',
    niente_da_chiudere: 'nessun prezzo opposto per chiudere',
    feed_assente: 'mercato non presente nel feed',
    feed_non_fresco: 'quote del feed non aggiornate',
    mercato_sospeso: 'mercato sospeso',
    liquidita_insufficiente: 'liquidità insufficiente',
    spread_troppo_ampio: 'spread troppo ampio',
    size_minima: 'sotto la size minima Betfair',
    daily_cap: 'cap di liability giornaliera raggiunto',
    daily_liability_cap: 'cap di liability giornaliera raggiunto',
    model_daily_cap: 'cap giornaliero dei trade di modello raggiunto',
    per_event_cap: 'cap di liability per evento raggiunto',
    per_event_max_trades: 'massimo di trade su questa partita',
    correlated: 'posizione troppo correlata a una già aperta',
    loss_stop: 'stop per perdita giornaliera attivo',
    max_open_trades: 'massimo di trade aperti raggiunto',
    max_liability_per_trade: 'liability per trade oltre il limite',
    in_riconciliazione: 'in riconciliazione',
    ordine_gia_a_mercato: 'ordine già a mercato',
    quote_non_disponibili: 'quote non disponibili (né dal feed né dal book Betfair)',
    'quote non disponibili': 'quote non disponibili (né dal feed né dal book Betfair)',
    combo_incomplete: 'combinazione incompleta: una gamba non si è abbinata',
};

/** sorgente delle quote usata dal servizio per chiudere */
export function safeSourceLabel(source: string | null | undefined): string | null {
    const s = source != null ? String(source).trim().toLowerCase() : '';
    if (s === 'feed') return 'quote dal feed dello scanner';
    if (s === 'rest') return 'quote dal book Betfair';
    return null;
}

export function safeReasonLabel(reason: string | null | undefined): string | null {
    const r = reason != null ? String(reason).trim() : '';
    if (!r) return null;
    return REASON_IT[r.toLowerCase()] ?? r;
}

/** Riga di testo di UN'attività Safe Strategy: partita, selezione, numeri e
 *  motivo, tutto in italiano e coi formatter unici. */
export function safeActivityLine(payload: Record<string, unknown> | null | undefined): string {
    const p = payload ?? {};
    const parts: string[] = [];
    const txt = (v: unknown) => (v != null && String(v).trim() !== '' ? String(v).trim() : null);
    const ev = txt(p.event_name) ?? txt(p.event_id);
    if (ev) parts.push(ev);
    const sel = txt(p.selection_name) ?? txt(p.selection);
    const side = txt(p.side);
    if (sel) parts.push(`${side ? `${side.toUpperCase()} ` : ''}${sel}`);
    else if (side) parts.push(side.toUpperCase());
    const mkt = txt(p.market_type) ?? txt(p.market_name);
    if (mkt) parts.push(mkt);
    const size = Number(p.size);
    const price = Number(p.price);
    if (Number.isFinite(size) && Number.isFinite(price)) parts.push(`${fmtMoney(size)} @ ${fmtOdds(price)}`);
    else if (Number.isFinite(size)) parts.push(fmtMoney(size));
    else if (Number.isFinite(price)) parts.push(fmtOdds(price));
    const pnl = Number(p.pnl ?? p.locked_pnl ?? p.position_pnl);
    if (Number.isFinite(pnl)) parts.push(fmtMoney(pnl, { signed: true }));
    const liab = Number(p.liability);
    if (Number.isFinite(liab) && liab > 0) parts.push(`liability ${fmtMoney(liab)}`);
    const exitKind = txt(p.exit_kind);
    if (exitKind) parts.push(`uscita: ${exitKind}`);
    const reason = safeReasonLabel(txt(p.reason) ?? txt(p.exit_reason));
    if (reason) parts.push(reason);
    const err = txt(p.err) ?? txt(p.detail) ?? txt(p.error);
    if (err) parts.push(err);
    const attempts = Number(p.attempts);
    if (Number.isFinite(attempts) && attempts > 0) parts.push(`${attempts}° tentativo`);
    const next = txt(p.next_retry_at);
    if (next) parts.push(`ritento alle ${fmtTime(next)}`);
    const src = safeSourceLabel(txt(p.source));
    if (src) parts.push(src);
    // combo_incomplete: quali gambe restano da svolgere
    const pending = Array.isArray(p.pending_ids) ? (p.pending_ids as unknown[]) : null;
    if (pending && pending.length) parts.push(`gambe in sospeso ${pending.map((x) => `#${x}`).join(' ')}`);
    // market_missing: quante volte di fila il mercato è mancato
    const fails = Number(p.fails);
    if (Number.isFinite(fails) && fails > 0) parts.push(`${fails} volte di fila senza mercato`);
    // params_clamped: la correzione, chiave per chiave (salvato → in uso)
    const corr = p.corrections && typeof p.corrections === 'object'
        ? (p.corrections as Record<string, { stored?: unknown; effective?: unknown }>)
        : null;
    if (corr) {
        const bits = Object.entries(corr)
            .map(([k, v]) => `${k}: salvato ${String(v?.stored)} → in uso ${String(v?.effective)}`);
        if (bits.length) parts.push(bits.join(' · '));
    }
    // params_invalid: chiavi corrette DAVVERO sul DB
    const persisted = Array.isArray(p.persisted) ? (p.persisted as unknown[]) : null;
    if (persisted && persisted.length) parts.push(`corrette sul database: ${persisted.join(', ')}`);
    const trade = Number(p.trade_id);
    if (Number.isFinite(trade)) parts.push(`#${trade}`);
    if (parts.length === 0) {
        const keys = Object.keys(p);
        return keys.length ? JSON.stringify(p).slice(0, 140) : '';
    }
    return parts.join(' · ');
}

export default SAFE_ACTIVITY_EXTRA;
