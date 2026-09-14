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

/**
 * CERT. 13/09 — i kind che rispondono alla domanda «perché NON è entrato?».
 * Sono le righe che il trader cerca quando BASE o PUNTA non scattano: `skip`
 * (condizione non soddisfatta, col motivo tradotto — es. `pre_ko_assente`) e
 * `risk_block` (entrata rifiutata dai cap di rischio). Il feed le espone come
 * chip rapido «solo NON ENTRATO»: prima erano in tono MUTED e il toggle «solo
 * da guardare» le eliminava, cioè la domanda più frequente non era filtrabile.
 */
export const SAFE_SKIP_KINDS: readonly string[] = ['skip', 'risk_block'];

/**
 * CERT. 13/09 — MODALITÀ dichiarata dal servizio su una riga di attività.
 * Il backend ora scrive `payload.mode` su OGNI riga: senza leggerla la stessa
 * lista mescolava decisioni prese con soldi veri e decisioni simulate.
 * Le righe scritte PRIMA della correzione non hanno il campo: si torna `null`
 * (modalità non dichiarata), non si inventa un 'paper'.
 */
export function safeActivityMode(
    payload: Record<string, unknown> | null | undefined,
): 'paper' | 'live' | null {
    const raw = (payload ?? {})['mode'];
    const k = raw != null ? String(raw).trim().toLowerCase() : '';
    return k === 'paper' || k === 'live' ? k : null;
}

/** Etichetta di un kind Safe Strategy (con fallback del design system). */
export function safeActivityMeta(kind: string): ActivityMeta {
    return activityMeta(kind, SAFE_ACTIVITY_EXTRA);
}

/**
 * Motivi tecnici del servizio → italiano.
 *
 * CONTRATTO: le chiavi sono quelle che il backend scrive DAVVERO nel payload
 * (`Betfair/safe_strategy/risk.py` R_*, i `_log_skip` di `bot_service.py`, i
 * `reason` degli `error`). Una chiave mancante = una parola inglese sotto gli
 * occhi del trader ("per_event_liability_cap", "spread_anomalo"): è un bug.
 */
const REASON_IT: Record<string, string> = {
    // CERT. 13/09 — motivi introdotti dalle guardie nuove del servizio.
    aggregati_non_leggibili:
        'numeri della giornata non leggibili dal database: nuovi ingressi sospesi '
        + '(senza quei numeri i limiti di rischio non sono verificabili)',
    control_non_verificabile:
        'il servizio non riesce a leggere il proprio stato: piazzamento rimandato '
        + '(le chiusure passano comunque)',
    control_illeggibile_da_troppo:
        'stato del servizio non leggibile da troppo tempo: si sta lavorando con '
        + 'parametri vecchi, controllare il database',
    reconcile_paper_mai_piazzata:
        'riserva simulata interrotta prima di partire: nessun ordine è mai esistito',
    combo_gamba_sotto_minimo: 'una gamba della combinazione è troppo piccola da piazzare',
    combo_totale_sotto_minimo: 'il totale della combinazione è sotto il minimo richiesto',
    combo_book_non_regge_il_minimo:
        'il mercato non ha liquidità sufficiente a reggere il minimo della combinazione',
    pre_ko_assente:
        'riferimento quote pre-partita non disponibile: BASE e PUNTA non valutabili su questa partita',
    variante_non_abilitata: 'strategia non abilitata nei parametri del bot',
    esatto_lato_gia_aperto: 'altro lato “Altro risultato” già aperto su questa partita',
    modalita_non_corrispondente:
        'la richiesta era di una modalità diversa da quella attiva: rifiutata',
    richiesta_scaduta: 'richiesta troppo vecchia: scartata invece di eseguirla in ritardo',
    place_exception_reconciling: 'ordine a esito ignoto: in verifica su Betfair',
    reconcile_ordine_assente: 'nessun ordine trovato su Betfair',
    reconcile_ordine_senza_fill: 'ordine su Betfair senza alcun abbinamento',
    reconcile_paper_senza_fill: 'paper: nessun abbinamento entro il TTL',
    reconcile_orphan_old: 'riserva orfana troppo vecchia',
    niente_da_chiudere: 'nessun prezzo opposto per chiudere',
    feed_assente: 'mercato non presente nel feed',
    feed_non_fresco: 'quote del feed non aggiornate',
    mercato_sospeso: 'mercato sospeso',
    liquidita_insufficiente: 'liquidità insufficiente',
    spread_troppo_ampio: 'spread troppo largo fra back e lay',
    // nome REALE scritto da bot_service._log_skip (prima restava in inglese)
    spread_anomalo: 'spread troppo largo fra back e lay',
    // cert. 12/09: prima anche questo caso diceva "spread troppo largo", ma con
    // meta' book mancante il rapporto non e' nemmeno calcolabile
    book_senza_lato_back: 'book senza lato back: non c’è nessuno che offra, spread non misurabile',
    // CERT. 14/09 — su un leader a 1,01-1,02 è normale che nessuno offra di
    // bancare: prima questo caso veniva etichettato «senza lato back» e mandava
    // a cercare il guasto dal lato sbagliato.
    book_senza_lato_lay: 'book senza lato lay: nessuno offre di bancare (normale su quote bassissime), spread non misurabile',
    size_minima: 'sotto la size minima Betfair',
    market_o_selezione_mancante: 'mercato o selezione non presenti nel feed',
    already_reserved: 'già riservato: nessun doppio ingresso sullo stesso segnale',
    place_exhausted: 'tentativi di piazzamento esauriti',
    // ---- rischio: le chiavi sono quelle di risk.py (R_*)
    daily_cap: 'cap di liability giornaliera raggiunto',
    daily_liability_cap: 'cap di liability giornaliera raggiunto',
    model_daily_cap: 'cap giornaliero dei trade di modello raggiunto',
    model_daily_liability_cap: 'cap giornaliero di liability dei trade di modello raggiunto',
    per_event_cap: 'cap di liability per evento raggiunto',
    per_event_liability_cap: 'cap di liability per evento raggiunto',
    per_event_max_trades: 'massimo di trade su questa partita',
    correlated: 'posizione troppo correlata a una già aperta',
    loss_stop: 'stop per perdita giornaliera attivo',
    daily_loss_stop: 'stop per perdita giornaliera attivo: nessun nuovo ingresso',
    max_open_trades: 'massimo di trade aperti raggiunto',
    max_liability_per_trade: 'liability per trade oltre il limite',
    max_liability_per_trade_superato: 'liability per trade oltre il limite',
    stato_rischio_non_leggibile: 'stato del rischio non leggibile: ingresso bloccato per prudenza',
    risk_block: 'bloccato dai limiti di rischio',
    in_riconciliazione: 'in riconciliazione',
    ordine_gia_a_mercato: 'ordine già a mercato',
    quote_non_disponibili: 'quote non disponibili (né dal feed né dal book Betfair)',
    'quote non disponibili': 'quote non disponibili (né dal feed né dal book Betfair)',
    chiusura_non_ancora_confermata: 'chiusura non ancora confermata da Betfair',
    // ---- combinazioni
    combo_incomplete: 'combinazione incompleta: una gamba non si è abbinata',
    combo_gamba_non_abbinabile: 'una gamba della combinazione non è abbinabile',
    combo_gamba_non_chiusa: 'una gamba della combinazione non si è chiusa',
    combo_riserva_incompleta: 'riserva della combinazione incompleta: annullata',
    combo_incompleta_senza_prezzi: 'combinazione incompleta: prezzi mancanti per chiudere',
    combo_solidale: 'gambe della combinazione trattate insieme',
    // ---- uscite
    exit_failed: 'chiusura a mercato fallita',
    exit_residual_exhausted: 'residuo non chiuso: tentativi esauriti',
    // ---- errori del servizio (kind 'error'): mai una chiave inglese nuda
    open_count_failed: 'conteggio delle posizioni aperte fallito',
    open_trades_failed: 'lettura delle posizioni aperte fallita',
    closing_trades_failed: 'lettura delle gambe di chiusura fallita',
    exit_candidates_failed: 'selezione delle posizioni da chiudere fallita',
    engine_failed: 'motore dei segnali in errore',
    feed_failed: 'lettura del feed fallita',
    fetch_failed: 'lettura da Betfair fallita',
    list_failed: 'elenco degli ordini Betfair non leggibile',
    market_senza_list_orders: 'mercato senza ordini su Betfair',
    opportunity_failed: 'calcolo delle opportunità fallito',
    tennis_opportunity_failed: 'calcolo delle opportunità tennis fallito',
    combos_failed: 'calcolo delle combinazioni fallito',
    anomaly_failed: 'calcolo delle anomalie fallito',
    opps_write_failed: 'scrittura delle opportunità fallita',
    opps_purge_failed: 'pulizia delle opportunità fallita',
    params_normalize_failed: 'normalizzazione dei parametri fallita',
    pending_requests_failed: 'lettura delle richieste in coda fallita',
    sync_hedge_failed: 'aggiornamento della copertura fallito',
    sync_parent_failed: 'aggiornamento della posizione aperta fallito',
    terminal_error_failed: 'chiusura della riga in errore fallita',
    traded_keys_failed: 'lettura dei segnali già tradati fallita',
    flumine_poll_failed: 'coda di esecuzione (flumine) non raggiungibile',
    cycle_exception: 'eccezione nel ciclo del servizio',
};

/**
 * Motivi di USCITA del servizio → italiano.
 * Specchio di `Betfair/safe_strategy/exits._REASON_TEXT` + `_MINUTE_REASON_RE`:
 * l'attività `exit_wait` / `exit_retry` / `exit_hold` scrive il motivo TECNICO
 * (`lato_bancato_segna`), non la frase già tradotta di `meta.exit_reason`.
 */
const EXIT_REASON_IT: Record<string, string> = {
    sfavorita_pareggia: 'la squadra bancata ha pareggiato: chiusura in perdita',
    favorita_segna_ancora: 'la favorita ha segnato ancora: green-up',
    rosso_alla_favorita: 'cartellino rosso alla favorita: uscita',
    lato_bancato_segna: 'il lato bancato ha segnato: chiusura in perdita',
    favorita_subisce_gol: 'la favorita ha subito gol: chiusura in perdita',
    leader_vince_il_game: 'il leader ha vinto il game: take profit',
    leader_perde_il_game: 'il leader ha perso il game: uscita',
    due_game_persi_di_fila_e_parita: 'due game persi di fila e parità nel set: uscita obbligatoria',
    due_game_persi_di_fila: 'il giocatore puntato ha perso due game di fila: uscita',
    set_perso: 'il giocatore puntato ha perso un set: uscita',
    linea_decisa_contro: 'la linea tradata è decisa contro: chiusura in perdita',
    gol_avverso: 'gol avverso: la probabilità di perdere è salita oltre la soglia, uscita',
    rosso_avverso: 'cartellino rosso avverso: probabilità di perdere oltre la soglia, uscita',
    take_profit_modello: 'take profit del modello: profitto bloccato',
    cashout_quasi_gratis: 'posizione ormai vinta: cash out quasi gratis, liability liberata',
};
const MINUTE_REASON_RE = /^minuto_(\d+)/;

/** `meta.exit_kind` (vocabolario chiuso di `exits.EXIT_KINDS`) → italiano. */
const EXIT_KIND_IT: Record<string, string> = {
    greenup: 'green-up (profitto bloccato)',
    profit: 'presa di profitto',
    loss: 'chiusura in perdita',
    time: 'uscita a tempo',
    red_card: 'cartellino rosso',
    forced: 'uscita obbligata',
    manual: 'cash out manuale',
    other: 'altra uscita',
};
export function safeExitKindLabel(kind: string | null | undefined): string | null {
    const k = kind != null ? String(kind).trim().toLowerCase() : '';
    if (!k) return null;
    return EXIT_KIND_IT[k] ?? k.replace(/_/g, ' ');
}

/**
 * `market_type` Betfair → nome ITALIANO del mercato.
 * I valori sono quelli che il servizio scrive davvero (MATCH_ODDS,
 * CORRECT_SCORE, HALF_TIME, BOTH_TEAMS_TO_SCORE, OVER_UNDER[_xy], COMBO) più
 * quelli che il feed dello scanner usa per i blocchi.
 */
const MARKET_IT: Record<string, string> = {
    MATCH_ODDS: '1X2 finale',
    '1X2': '1X2 finale',
    CORRECT_SCORE: 'Risultato Esatto',
    CS: 'Risultato Esatto',
    HALF_TIME_SCORE: 'Risultato Esatto 1º tempo',
    HT_CS: 'Risultato Esatto 1º tempo',
    HALF_TIME: '1X2 primo tempo',
    HALF_TIME_RESULT: '1X2 primo tempo',
    HT_1X2: '1X2 primo tempo',
    BOTH_TEAMS_TO_SCORE: 'Gol/NoGol',
    BTTS: 'Gol/NoGol',
    OVER_UNDER: 'Over/Under',
    COMBO: 'Combinazione',
};
const OU_LINE_RE = /^OVER_UNDER_(\d)(\d)$/;

export function safeMarketLabel(
    marketType: string | null | undefined, line?: number | null,
): string | null {
    const raw = marketType != null ? String(marketType).trim() : '';
    if (!raw) return null;
    const up = raw.toUpperCase();
    const ou = OU_LINE_RE.exec(up);
    if (ou) return `Over/Under ${ou[1]}.${ou[2]}`;
    const base = MARKET_IT[up];
    if (base) {
        return up === 'OVER_UNDER' && line != null && Number.isFinite(Number(line))
            ? `Over/Under ${String(Number(line)).replace('.', ',')}`
            : base;
    }
    // tipo sconosciuto: mai la costante inglese nuda con gli underscore
    return raw.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

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
    const k = r.toLowerCase();
    if (REASON_IT[k]) return REASON_IT[k];
    if (EXIT_REASON_IT[k]) return EXIT_REASON_IT[k];
    const m = MINUTE_REASON_RE.exec(k);
    if (m) return `uscita a tempo al ${m[1]}′`;
    // frase già in italiano scritta dal servizio (meta.exit_reason, model_why):
    // si lascia intatta. Un codice tecnico sconosciuto (snake_case, tutto
    // minuscolo, senza spazi) non deve MAI arrivare all'occhio come tale.
    if (/^[a-z0-9]+(_[a-z0-9]+)+$/.test(k)) return k.replace(/_/g, ' ');
    return r;
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
    // mercato in CHIARO: "Risultato Esatto", mai "CORRECT_SCORE"
    const mkt = safeMarketLabel(txt(p.market_type), p.line as number | null) ?? txt(p.market_name);
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
    const exitKind = safeExitKindLabel(txt(p.exit_kind));
    if (exitKind) parts.push(`uscita: ${exitKind}`);
    // `exit_reason` è GIÀ la frase italiana scritta da exits.reason_text; `reason`
    // è il codice tecnico della stessa uscita. Prima vinceva il codice tecnico e
    // il trader leggeva "lato_bancato_segna" invece della spiegazione.
    const reason = safeReasonLabel(txt(p.exit_reason) ?? txt(p.reason));
    if (reason) parts.push(reason);
    const err = txt(p.err) ?? txt(p.detail) ?? txt(p.error);
    // dettaglio tecnico: utile, ma non deve mangiarsi la riga (il servizio ci
    // infila il dict completo dell'errore Supabase)
    if (err) parts.push(err.length > 120 ? `${err.slice(0, 120)}…` : err);
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
