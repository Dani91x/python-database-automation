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

// ------------------------------------------------------------- modalità riga
/**
 * CERT. 13/09 — MODALITÀ di OGNI RIGA (PAPER / LIVE), badge unico.
 *
 * Il backend ora etichetta con `mode` ogni trade, ogni riga di attività e ogni
 * richiesta, e tiene P&L e rischio separati per modalità. La UI deve dirlo su
 * OGNI riga, non solo nel banner di pagina: prima il badge compariva solo sulle
 * righe LIVE e l'ASSENZA di badge era ambigua — «riga in paper» e «riga senza
 * modalità dichiarata» erano indistinguibili, e con un control lasciato in LIVE
 * l'utente poteva credere che una tabella di soldi veri fosse una simulazione.
 * PAPER = tono neutro (nessun allarme), LIVE = tono di ALLARME (soldi veri),
 * modalità non dichiarata = si dice che non è dichiarata.
 */
export type RowMode = 'paper' | 'live';

export interface ModeMeta extends Meta { title: string }

export const MODE_META: Record<RowMode, ModeMeta> = {
    paper: {
        label: 'PAPER',
        cls: 'bg-white/5 text-slate-300 border-white/15',
        title: 'simulazione fedele: nessun denaro reale su questa riga',
    },
    live: {
        label: 'LIVE',
        cls: 'bg-red-500/15 text-red-300 border-red-500/40',
        title: 'soldi veri: questa riga è un ordine reale su Betfair',
    },
};

const MODE_UNKNOWN: ModeMeta = {
    label: 'MODALITÀ N/D',
    cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    title: 'il servizio non ha dichiarato la modalità di questa riga: non è verificabile se sia paper o live',
};

/** Modalità di una riga → etichetta/colore/tooltip. Sconosciuta = dichiarata tale. */
export function modeMeta(mode: string | null | undefined): ModeMeta {
    const k = String(mode ?? '').trim().toLowerCase();
    if (k === 'paper' || k === 'live') return MODE_META[k];
    return MODE_UNKNOWN;
}

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
/** esiti CERTI: nessun flag di riconciliazione/terminale può sovrascriverli */
const SETTLED_STATUS = new Set(['won', 'lost', 'void']);

type MetaObj = Record<string, unknown> | null | undefined;

export const RECONCILING_META: Meta = {
    label: 'IN VERIFICA SU BETFAIR',
    cls: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/40',
};

/**
 * Certificazione 12/09 — ordine APPOGGIATO sul book e NON ANCORA ABBINATO.
 *
 * Una lay di green-up appoggiata a +N tick resta sul book finche' il mercato
 * non scambia sotto il suo prezzo. Fino a quel momento **non copre niente**:
 * la posizione aperta e' ancora tutta scoperta. La riga pero' veniva salvata
 * con `status='open'`, cioe' con lo STESSO badge di una gamba abbinata, e in
 * tabella il trader vedeva una chiusura che in realta' non era avvenuta.
 * Caso vivo: Paris FC v Lyon con 30 EUR di Under abbinati e 20,25 EUR di lay
 * solo appoggiate — rischio reale 30 EUR, mostrato 9,75.
 */
export const RESTING_META: Meta = {
    label: 'APPOGGIATA · NON ABBINATA',
    // indaco: DEVE differire da 'open' (sky), che significa posizione abbinata,
    // e da 'pending' (ambra), che significa ordine ancora in corso di invio
    cls: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/40',
};

/** `meta.fill = 'paper_resting'`: ordine sul book, nessun abbinamento ancora. */
export function isRestingMeta(status: string | null | undefined, meta: MetaObj): boolean {
    if (SETTLED_STATUS.has(String(status ?? '').toLowerCase())) return false;
    const m = (meta ?? {}) as Record<string, unknown>;
    return String(m['fill'] ?? '').endsWith('resting');
}

/**
 * Riga TERMINALE: è PROVATO che nessun ordine reale esiste (FOK ucciso, paper
 * senza fill, richiesta mai creata). Non è una posizione viva e non è un
 * rischio: non va mostrata come un normale "IN CORSO" che non finisce mai.
 */
export const TERMINAL_ERROR_META: Meta = {
    label: 'ERRORE (definitivo)',
    cls: 'bg-orange-500/20 text-orange-200 border-orange-400/50',
};

/**
 * Certificazione 12/09 — UNA regola di "in verifica su Betfair" per i tre bot.
 *
 * I tre servizi marcano la riserva a esito IGNOTO in due modi diversi:
 *   · Omega   `meta.reconciling = true` + `meta.reason='place_exception_reconciling'`
 *             (omega_service.py:1337-1341)
 *   · Safe    SOLO `meta.reason='place_exception_reconciling'` (execution.py:225)
 *   · Mike    come Safe (service.py:346-353, stesso writer condiviso)
 * Chi leggeva un solo campo dava due badge diversi per lo STESSO rischio. Qui
 * la regola è una: lo stato deve essere ancora `pending` (un esito arrivato
 * vince sempre) e basta uno dei due marcatori.
 */
export function isReconcilingMeta(status: string | null | undefined, meta: MetaObj): boolean {
    if (String(status ?? '').toLowerCase() !== 'pending') return false;
    const m = (meta ?? {}) as Record<string, unknown>;
    return m['reconciling'] === true
        || String(m['reason'] ?? '') === 'place_exception_reconciling';
}

/**
 * Riga TERMINALE: è PROVATO che nessun ordine reale esiste.
 *   · Omega  `meta.error_final` / `meta.leg_failed` / `meta.no_fill_at` / `meta.error_at`
 *   · Safe   `meta.error_final` (+ `error_at`)
 *   · Mike   NON scrive nessuno di questi flag (vedi report): per Mike la riga
 *            resta un semplice `error`, e questa funzione ritorna false.
 */
export function isTerminalErrorMeta(meta: MetaObj): boolean {
    const m = (meta ?? {}) as Record<string, unknown>;
    return Boolean(m['error_final']) || Boolean(m['leg_failed'])
        || m['no_fill_at'] != null || m['error_at'] != null;
}

/**
 * Badge di stato di una riga leggendo direttamente il `meta` del servizio:
 * la stessa posizione ha lo stesso badge nel LIVE e nello STORICO.
 */
export function statusMetaOf(
    row: { status: string | null | undefined; meta?: MetaObj },
): Meta {
    return statusMeta(row.status, {
        reconciling: isReconcilingMeta(row.status, row.meta),
        terminal: isTerminalErrorMeta(row.meta),
        resting: isRestingMeta(row.status, row.meta),
    });
}

/**
 * Stato di un trade -> etichetta + classi.
 * Precedenza: esito certo > riga terminale > riconciliazione > stato del DB.
 * Un trade che il servizio non ha ancora riconciliato NON va mostrato come se
 * fosse a posto; ma un esito già arrivato resta l'esito.
 */
export function statusMeta(
    status: string | null | undefined,
    opts: { reconciling?: boolean; terminal?: boolean; resting?: boolean } = {},
): Meta {
    const key = String(status ?? '').toLowerCase() as TradeStatus;
    const settled = SETTLED_STATUS.has(key);
    if (!settled && opts.terminal) return TERMINAL_ERROR_META;
    if (!settled && opts.reconciling) return RECONCILING_META;
    // dopo la riconciliazione: un ordine sul book non e' una posizione
    if (!settled && opts.resting) return RESTING_META;
    return STATUS_META[key] ?? unknownStatusMeta(key);
}

/**
 * CERT. 13/09 — uno stato che questa mappa non conosce NON è un errore.
 *
 * Prima il fallback era `STATUS_META.error`: bastava che il backend
 * introducesse uno stato nuovo (o lo scrivesse con un refuso) perché la
 * tabella dichiarasse «ERRORE» su posizioni perfettamente sane, e un trader
 * chiudesse in fretta una posizione che non aveva nulla che non andasse.
 * Si fa come `activityMeta`, che questo caso lo gestiva già bene: si mostra la
 * chiave così com'è e si DICHIARA che è sconosciuta, senza inventarne il senso.
 */
export function unknownStatusMeta(status: string | null | undefined): Meta {
    const raw = String(status ?? '').trim();
    if (!raw) {
        return {
            label: 'STATO ASSENTE',
            cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
        };
    }
    return {
        label: `${raw.toUpperCase()} (stato sconosciuto)`,
        cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    };
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

// ------------------------------------------------------------------ P&L: colore
/**
 * CERT. 13/09 — IL COLORE DEL P&L, una regola sola per le tre sezioni.
 *
 * Richiesta testuale dell'utente: «su safe non si capisce un cazzo (le loss
 * sono in nero e in piccolo)». Per un trader il SEGNO del P&L è
 * l'informazione più importante della pagina: deve arrivare all'occhio prima
 * di qualunque altra cosa, e una perdita non può essere meno visibile di un
 * utile. Prima ogni sezione aveva la sua funzioncina locale (Mike in
 * MikeEventPnlTable, Omega in MatchTradesTable, Safe nessuna: espressioni
 * ternarie sparse riga per riga, che in diversi punti lasciavano la perdita in
 * `text-slate-*` — cioè grigio/nero — e per giunta in corpo più piccolo).
 *
 * Regola NON negoziabile:
 *   · positivo  → verde, GRASSETTO
 *   · negativo  → ROSSO, GRASSETTO, stessa dimensione del positivo
 *   · zero      → neutro ma stesso peso (un pari non è né un utile né una perdita)
 *   · ASSENTE   → grigio tenue e NIENTE grassetto: non c'è un numero da urlare
 *                 (e chi stampa il valore deve scrivere «—», mai «0,00 €»)
 *
 * Il grassetto sta QUI dentro apposta: è l'unico modo di garantire che nessun
 * punto della UI possa stampare una perdita in corpo leggero senza accorgersene.
 * La DIMENSIONE resta al chiamante, che però la applica alla cella — quindi è
 * la stessa per utile e perdita per costruzione.
 */
export function pnlClass(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(Number(v))) return 'text-slate-400';
    const n = Number(v);
    if (n > 0) return 'text-emerald-400 font-bold';
    if (n < 0) return 'text-red-400 font-bold';
    return 'text-slate-300 font-bold';
}

/**
 * Variante per i testi piccoli di contorno (sotto-righe, tooltip in pagina):
 * stessa regola di segno, tonalità leggermente più chiara perché su fondo
 * scuro il 400 su corpo 10px si legge peggio. Il grassetto resta.
 */
export function pnlClassSoft(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(Number(v))) return 'text-slate-400';
    const n = Number(v);
    if (n > 0) return 'text-emerald-300 font-bold';
    if (n < 0) return 'text-red-300 font-bold';
    return 'text-slate-300 font-bold';
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
    // CERT. 13/09 — etichette della BARRA DEI TOTALI della sezione Operazioni
    // (le stesse cinque parole in Omega, Safe e Mike: il trader non deve
    // tradurre a mente da una scheda all'altra).
    totOperazioni: 'Operazioni',
    totRealizzato: 'P&L realizzato',
    totAperto: 'Se chiudo ora',
    totInvestito: 'Investito',
    totLiability: 'Responsabilità',
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

/**
 * TOOLTIP UNICI: una riga che dice COSA guardare, identica nelle tre sezioni.
 *
 * Certificazione 12/09: le stesse quattro grandezze avevano sottotitoli diversi
 * in ogni pagina ("esposizione a coda", "stop giornaliero 50,00 €", niente) e
 * nessuna diceva che cosa fossero davvero. Il sottotitolo resta della sezione
 * (è un dato del bot); la SPIEGAZIONE è una sola e sta qui.
 */
export const TIP = {
    openLiability: 'quanto è ancora a rischio ADESSO sulle posizioni vive (non è il capitale impegnato oggi)',
    lockedPnl: 'risultato GIÀ bloccato dalle coperture sulle posizioni ancora vive: non cambia più, qualunque sia l’esito',
    realizedToday: 'somma dei P&L delle posizioni PIAZZATE oggi e già regolate (fuso Europe/Rome)',
    // CERT. 13/09 — due cose che il numero da solo non dice e che cambiano
    // completamente come va letto: (1) a QUALE MODALITÀ si riferisce — il
    // backend tiene P&L e rischio separati fra paper e live, e sommare le due
    // contabilità non ha alcun senso; (2) che è già al NETTO della commissione
    // registrata su OGNI trade (quella del trade, non il parametro corrente).
    // La modalità è scritta anche nell'etichetta della tile («P&L oggi · PAPER»).
    pnlToday: 'P&L realizzato della giornata operativa di oggi (Europe/Rome), al NETTO della commissione registrata su ogni trade. Vale SOLO per la modalità scritta nell’etichetta: paper e live sono contabilità separate e non si sommano.',
    pnlTotal: 'P&L realizzato da sempre, tutte le giornate, al NETTO della commissione registrata su ogni trade. Vale SOLO per la modalità scritta nell’etichetta: paper e live sono contabilità separate e non si sommano.',
    // CERT. 12/09 (collaudo reportistica) — il testo precedente diceva «conta lo
    // stato, non il segno del P&L»: era FALSO. Tutte le fonti (trading_daily_history,
    // omega_aggregates_sql, safe_aggregates_sql, mike_aggregates_sql) contano per
    // SEGNO del P&L totale della POSIZIONE (apertura + chiusure).
    winLoss: 'V = posizioni con P&L totale positivo, P = negativo (apertura + chiusure): un ciclo greenato vale UNA posizione, non 1 vinta + 1 persa',
    goalToday: 'obiettivo di P&L realizzato per la giornata di oggi',
    matches: 'partite con almeno una posizione piazzata oggi',
    operations: 'posizioni (gambe) piazzate oggi, chiusure escluse',
    liveCount: 'posizioni ancora vive: non regolate',
    // CERT. 13/09 — barra dei totali della sezione Operazioni
    totOperazioni: 'quante POSIZIONI (aperture) rientrano in questa vista: le gambe di chiusura stanno dentro la posizione che chiudono, non si contano due volte',
    totRealizzato: 'somma dei P&L NETTI delle sole righe GIÀ REGOLATE di questa vista. Le posizioni ancora vive NON sono qui dentro: il loro valore è in «Se chiudo ora».',
    totAperto: 'quanto si bloccherebbe chiudendo ADESSO a mercato tutte le posizioni ancora vive, al netto della commissione. È una STIMA sui prezzi del feed, non un incasso.',
    totInvestito: 'capitale impegnato nelle aperture di questa vista (lo stake, non la responsabilità di una banca)',
    totLiability: 'quanto è ancora a rischio ADESSO sulle posizioni vive di questa vista',
    equity: 'P&L cumulato realizzato, un gradino per giornata: parte da 0 il primo giorno del periodo',
    feed: 'FEED dello scanner (fonte unica delle quote): da quanti secondi non si aggiorna',
    beat: 'BATTITO del servizio del bot: se manca, il bot non sta operando',
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
    place_saltato: { label: 'DUPLICATO EVITATO', cls: WARN },
    would_place: { label: 'ORDINE (dry)', cls: MUTED },
    cancel: { label: 'ANNULLO', cls: WARN },
    no_fill: { label: 'NON ABBINATO', cls: WARN },
    skip: { label: 'SALTO', cls: MUTED },
    // CERT. 14/09 — misure che il servizio scrive per SE STESSO (es. copertura
    // del dato di controllo del gioco): informative, mai un'azione sui soldi.
    diagnosi: { label: 'MISURA', cls: MUTED },
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
    feed_line_missing: { label: 'LINEA ASSENTE DAL FEED', cls: WARN },
    daily_stop: { label: 'STOP GIORNALIERO', cls: BAD, critical: true },
    goal_stop: { label: 'OBIETTIVO RAGGIUNTO: STOP', cls: GOOD },
    loss_stop: { label: 'STOP PER PERDITA', cls: BAD, critical: true },
    risk_block: { label: 'BLOCCATO DAL RISCHIO', cls: WARN },
    error: { label: 'ERRORE', cls: BAD, critical: true },
    armed: { label: 'ARMATA', cls: CLOSE },
    pre_cycle: { label: 'CICLO PRE', cls: GOOD },

    // --------------------------------------------------------------------
    // Certificazione 12/09 — kind che i tre servizi scrivono DAVVERO e che la
    // mappa condivisa non conosceva: senza questi la UI cadeva sul traduttore
    // parola-per-parola (o su "kind sconosciuto") e ogni sezione doveva
    // ripetersi il dizionario. Fonte: omega_service.py / bot_service.py +
    // execution.py / mike service.py.
    // --------------------------------------------------------------------
    // piazzamento e conferma
    place_pending: { label: 'ORDINE IN ATTESA DI CONFERMA', cls: INFO },
    place_retry: { label: 'PIAZZAMENTO · ritento', cls: WARN },
    place_reconciling: { label: 'PIAZZAMENTO: ESITO DA VERIFICARE', cls: BAD, critical: true },
    place_exception: { label: 'PIAZZAMENTO: ECCEZIONE', cls: BAD, critical: true },
    place_resting: { label: 'ORDINE A BOOK', cls: INFO },
    fill_resting: { label: 'ORDINE A BOOK ABBINATO', cls: GOOD },
    resting_live_unsupported: { label: 'ORDINE A BOOK NON SUPPORTATO IN LIVE', cls: WARN },
    confirm_failed: { label: 'CONFERMA FALLITA', cls: BAD, critical: true },
    size_reduced: { label: 'IMPORTO RIDOTTO', cls: WARN },
    size_legalized: { label: 'IMPORTO PORTATO AL MINIMO BETFAIR', cls: WARN },
    paper_fill_fallback: { label: 'PAPER: FILL DI RIPIEGO', cls: WARN },
    live_fok_fallback: { label: 'LIVE: RIPIEGO SU FOK', cls: WARN },
    // coda flumine
    flumine_enqueue: { label: 'ORDINE IN CODA (flumine)', cls: INFO },
    flumine_fill: { label: 'ABBINATO (flumine)', cls: GOOD },
    flumine_no_fill: { label: 'NON ABBINATO (flumine)', cls: WARN },
    flumine_cancel: { label: 'ANNULLO (flumine)', cls: WARN },
    flumine_cancel_timeout: { label: 'ANNULLO SCADUTO (flumine)', cls: BAD, critical: true },
    flumine_recovered: { label: 'ORDINE RECUPERATO (flumine)', cls: GOOD },
    flumine_live_freed: { label: 'RISERVA LIVE LIBERATA', cls: NEUTRAL },
    flumine_live_orphan: { label: 'ORDINE LIVE ORFANO', cls: BAD, critical: true },
    flumine_poll_error: { label: 'CODA NON LEGGIBILE (flumine)', cls: BAD, critical: true },
    // chiusure e uscite
    cashout_error: { label: 'CASH OUT: ERRORE', cls: BAD, critical: true },
    cashout_manual: { label: 'CASH OUT MANUALE', cls: CLOSE },
    cover_wait: { label: 'COPERTURA · attesa', cls: WARN },
    greenup_blind: { label: 'GREEN-UP CIECO (feed assente)', cls: BAD, critical: true },
    greenup_residual_dropped: { label: 'GREEN-UP: RESIDUO ABBANDONATO', cls: WARN },
    hedged: { label: 'CHIUSA A MERCATO', cls: CLOSE },
    // regolamento
    settle_error: { label: 'REGOLAMENTO: ERRORE', cls: BAD, critical: true },
    settle_wait: { label: 'REGOLAMENTO · attesa', cls: WARN },
    settle_hedged: { label: 'REGOLATA (coperta)', cls: NEUTRAL },
    settle_orphan: { label: 'REGOLATA ORFANA', cls: WARN },
    settle_orphan_closing: { label: 'CHIUSURA ORFANA REGOLATA', cls: WARN },
    settle_fallback: { label: 'REGOLAMENTO DI RIPIEGO', cls: WARN },
    settling_reverted: { label: 'REGOLAMENTO ANNULLATO', cls: WARN },
    // riconciliazione
    reconcile_error: { label: 'RICONCILIAZIONE: ERRORE', cls: BAD, critical: true },
    reconcile_pending: { label: 'RICONCILIAZIONE IN CORSO', cls: WARN },
    reconciled_open: { label: 'RICONCILIATA: POSIZIONE APERTA', cls: INFO },
    reconciled_free: { label: 'RICONCILIATA: NESSUN ORDINE', cls: NEUTRAL },
    reconciled_error: { label: 'RICONCILIATA: ORDINE ASSENTE', cls: WARN },
    reconciled_paper: { label: 'RICONCILIATA (paper)', cls: NEUTRAL },
    // vigilanza
    orphan_live_alert: { label: 'ORDINE LIVE ORFANO', cls: BAD, critical: true },
    stale_open_alert: { label: 'POSIZIONE APERTA DA TROPPO', cls: BAD, critical: true },
    // manuale, modello, ciclo
    manual_place: { label: 'PIAZZAMENTO MANUALE', cls: INFO },
    manual_place_exception: { label: 'PIAZZAMENTO MANUALE: ECCEZIONE', cls: BAD, critical: true },
    model_lambda_market: { label: 'MODELLO: λ DAL MERCATO', cls: NEUTRAL },
    model_lambda_live: { label: 'MODELLO: λ DA O/U LIVE', cls: NEUTRAL },
    mission_error: { label: 'MISSIONI: ERRORE', cls: BAD, critical: true },
    mission_scores_error: { label: 'MISSIONI: PUNTEGGI NON LETTI', cls: BAD, critical: true },
    resume_event: { label: 'PARTITA RIPRESA IN CARICO', cls: NEUTRAL },
    skip_event: { label: 'PARTITA SALTATA', cls: MUTED },
    schema_warn: { label: 'MIGRAZIONE MANCANTE', cls: BAD, critical: true },
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
