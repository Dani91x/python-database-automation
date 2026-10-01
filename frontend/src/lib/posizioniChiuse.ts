// ============================================================================
// posizioniChiuse.ts - LE POSIZIONI GIA' CHIUSE, vinte e perse.
//
// "scheda "Posizioni chiuse": qui ci andranno tutte le posizioni VINCENTI E
// PERDENTI, filtrabili chiaramente, PNL GLOBALE DELLA POSIZIONE, pnl
// dettaglio" (utente, 14/09).
//
// DUE LIVELLI DI P&L, e la differenza e' tutto il punto:
//   - globale = quanto ha reso la POSIZIONE (il ciclo), apertura e chiusure
//     sommate. E' il numero che dice se quell'operazione e' andata bene.
//   - dettaglio = le singole righe. Su una posizione coperta l'apertura
//     vince e la copertura perde: guardare solo le righe fa sembrare un
//     green-up riuscito una sconfitta a meta'.
//
// LA REGOLA DI SEMPRE: paper e live non si sommano. Una posizione e'
// dell'una o dell'altra modalita'; la scheda ne mostra UNA alla volta.
//
// 24/09 (ordine dell'utente: "i dati sono mischiati per giornata, sono
// confusionari, il trader non capisce nulla: IL TRADER DEVE FIDARSI DI QUELLO
// CHE VEDE"). Tre cambi, tutti qui dentro e tutti testati:
//   1. GIORNATA = dal 01/10 (ordine dell'utente: «le chiusure devono essere
//      assegnate alla giornata di riferimento») il giorno della PARTITA,
//      deciso dal DATABASE per riga (`giorno_partita`/`giorno_da`); se
//      l'inizio non e' noto, il giorno di piazzamento (dichiarato). Una
//      partita di ieri sera regolata stamattina e' di IERI. Le righe ancora
//      senza il giorno del database (in memoria, non ancora rilette) restano
//      sul giorno di REGOLAMENTO come PROVVISORIE, contate e dichiarate: il
//      client non calcola mai il giorno della partita da solo.
//   2. UNA REGOLA DI RAGGRUPPAMENTO per calcio e tennis:
//      giornata -> bot -> partita -> ciclo (`raggruppaGiornata`), con il netto
//      di ogni livello e la sua FONTE (Betfair / stimato / paper).
//   3. VELOCITA': il vecchio costruttore creava un `Intl.DateTimeFormat` per
//      ogni posizione e ordinava con `localeCompare`: 240 ms su 2400 righe,
//      rifatti a ogni battito del feed. Ora gli istanti si leggono UNA volta
//      (ms) e il confronto e' numerico.
// ============================================================================
import { isSettled, isErrorRow, pnlDiRiga, fonteDiRiga, fonteDiRighe, type FontePnl } from '@/lib/eventGroups';
import type { Bot, Modo } from '@/lib/controlRoom';
import { modoDi } from '@/lib/controlRoom';
import { romeDay } from '@/lib/dailyHistory';
import { statoOrdine, type RigaOrdine } from '@/lib/statoOrdine';
import { certezzaChiusura, type RisultatoCertezzaChiusura } from '@/lib/certezzaChiusura';
import type { TennisBotOrderRow } from '@/lib/tennis';

export type Esito = 'vinta' | 'persa' | 'pari';

/** Una riga di una posizione chiusa: l'apertura o una delle sue chiusure. */
export interface RigaChiusa {
    id: number;
    bot: Bot;
    selezione: string | null;
    lato: 'back' | 'lay' | null;
    prezzo: number | null;
    size: number | null;
    /** netto di commissione; null = non regolata. 24/09: quello di Betfair
     *  (`pnl_betfair`) se c'e', altrimenti il calcolo del bot (`fontePnl`). */
    pnl: number | null;
    /** 24/09 - da dove viene `pnl`: conto Betfair, stima (calcolo del bot), simulato (D-06) */
    fontePnl?: FontePnl;
    stato: string;
    at: string;
    /** e' la gamba di copertura di un'altra riga? (false sul ripiego B13:
     *  li' il legame non esiste e nessuna riga si puo' dire "copertura") */
    chiusura: boolean;
    quale: string | null;
    /**
     * C.12b (16/09) - i campi grezzi dell'ORDINE (chiesto/abbinato/residuo/
     * prezzo medio/ultimo aggiornamento da Betfair). A leggerli e'
     * `lib/statoOrdine`, uno per tutti i bot.
     */
    ordine: RigaOrdine;
    /** 18/09 - bet_id della gamba: prova che Betfair ha accettato un ordine
     *  reale (`lib/certezzaChiusura.ts`, mai dentro `RigaOrdine`). */
    betId: string | null;
}

/**
 * 24/09 - come si sa che le righe di una posizione stanno insieme:
 *   - `catena`  = `closes_trade_id` scritto dal bot (Omega, Safe, Mike);
 *   - `ripiego` = i 4 bot tennis NON scrivono il legame ingresso-uscita
 *     (reperto B13): le loro righe si raggruppano per (bot, mercato,
 *     selezione), e la pagina lo DICHIARA sulla riga.
 */
export type Legame = 'catena' | 'ripiego';

/**
 * Da dove viene la giornata della posizione.
 *  - 'partita'     (01/10) giorno della partita, dal database;
 *  - 'piazzamento' inizio partita non noto: giorno di piazzamento (dal
 *                  database), o nessun istante di regolamento (client);
 *  - 'regolamento' riga senza il giorno del database: giornata PROVVISORIA;
 *  - 'nessuno'     nessuna data leggibile.
 */
export type GiornoDa = 'partita' | 'regolamento' | 'piazzamento' | 'nessuno';

export interface PosizioneChiusa {
    /** id della riga di APERTURA: identifica la posizione (con il bot) */
    id: number;
    eventId: string;
    partita: string;
    sport: 'calcio' | 'tennis';
    modo: Modo;
    bot: Bot;
    /** P&L della posizione INTERA: apertura + coperture */
    pnlGlobale: number;
    /**
     * 24/09 - da dove viene `pnlGlobale`: `conto` solo se TUTTE le gambe
     * regolate hanno il netto di Betfair; altrimenti `stima` o `simulato` (D-06).
     * Opzionale nel tipo per i fixture scritti prima.
     */
    fontePnl?: FontePnl;
    /** 24/09 - di `pnlGlobale`, la parte regolata da Betfair e quella stimata
     *  (solo soldi veri; paper = entrambe null). Opzionali per i fixture di prima. */
    pnlReale?: number | null;
    pnlStimato?: number | null;
    /** vinta / persa / pari, dal P&L globale */
    esito: Esito;
    /** le righe che la compongono, in ordine di tempo */
    righe: RigaChiusa[];
    /** quando si e' chiusa (l'ultima riga regolata) */
    chiusaAt: string;
    /** quando e' stata PIAZZATA l'apertura (ISO); '' se il dato manca */
    piazzataAt: string;
    /**
     * GIORNATA della posizione: 'YYYY-MM-DD' nel fuso Europe/Rome.
     *
     * 24/09 - e' il giorno di REGOLAMENTO (l'ultima gamba regolata: l'istante
     * di Betfair `pnl_betfair_settled_at` se c'e', altrimenti `settled_at` del
     * bot), la stessa regola della barra di giornata e del conto Betfair.
     * Senza nessun istante di regolamento si ripiega sul piazzamento
     * dell'apertura (`giornoDa = 'piazzamento'`, la scheda lo dice).
     * '' solo quando non c'e' proprio nessuna data.
     */
    giorno: string;
    giornoDa?: GiornoDa;
    /**
     * 01/10 - true = `giorno` viene dal DATABASE (giorno della partita, o il
     * suo ripiego dichiarato); false/assente = calcolato qui dal regolamento,
     * provvisorio finche' il database non lo conferma.
     */
    giornoConfermato?: boolean;
    /**
     * 23/09 - true = la riga e' una GAMBA DI CHIUSURA la cui apertura NON e'
     * fra le righe lette (paginazione, giorno diverso, riga cancellata). Il
     * suo P&L e' quello della sola gamba, non il netto del ciclo: lo si
     * DICHIARA invece di spacciarlo per un'operazione completa.
     */
    orfana: boolean;
    /** 24/09 - vedi `Legame`. Assente = `catena` (fixture di prima). */
    legame?: Legame;
    /** 24/09 - mercato e selezione dell'APERTURA, in chiaro quando si sa */
    mercato?: string | null;
    selezione?: string | null;
    lato?: 'back' | 'lay' | null;
    /** 24/09 - origine dell'apertura ('auto' | 'manual'), per la controprova con la barra */
    origine?: string | null;
}

/**
 * La giornata (Europe/Rome) di un istante ISO. '' se non c'e' o non e'
 * leggibile: mai una data inventata.
 */
export function giornataDi(iso: string | null | undefined): string {
    if (!iso) return '';
    const ms = Date.parse(iso);
    if (!Number.isFinite(ms)) return '';
    // 24/09 - VELOCITA': il fuso di Roma ha scarti di ORE intere (UTC+1/+2),
    // quindi la mezzanotte di Roma cade sempre all'inizio di un'ora UTC e
    // tutti gli istanti della stessa ora UTC hanno la stessa giornata. Si
    // chiede al formattatore UNA volta per ora, non una per riga.
    const ora = Math.floor(ms / 3_600_000);
    const noto = giornoPerOra.get(ora);
    if (noto !== undefined) return noto;
    const g = romeDay(new Date(ora * 3_600_000));
    if (giornoPerOra.size > 20_000) giornoPerOra.clear();
    giornoPerOra.set(ora, g);
    return g;
}
const giornoPerOra = new Map<number, string>();

export interface TradeChiudibile {
    id: number;
    event_id?: string | null;
    event_name?: string | null;
    sport?: string | null;
    mode?: string | null;
    status?: string | null;
    pnl?: number | null;
    /** 24/09 - netto regolato da Betfair (null/assente = non ancora: stimato) */
    pnl_betfair?: number | null;
    pnl_betfair_settled_at?: string | null;
    side?: string | null;
    price?: number | null;
    size?: number | null;
    selection_name?: string | null;
    /** Omega porta il nome della selezione qui, non in `selection_name` */
    runner_name?: string | null;
    /** Safe / Mike: tipo di mercato; Omega: `phase` */
    market_type?: string | null;
    phase?: string | null;
    market_id?: string | null;
    selection_id?: number | string | null;
    origin?: string | null;
    placed_at?: string | null;
    settled_at?: string | null;
    closes_trade_id?: number | null;
    strategy?: string | null;
    // C.12b - colonne della migrazione `trades_consapevolezza_ordine_2026-09-16`
    // (assenti finche' non e' applicata) e il `meta`.
    size_requested?: number | null;
    size_matched?: number | null;
    size_remaining?: number | null;
    avg_price_matched?: number | null;
    betfair_updated_at?: string | null;
    /** 18/09 - presente = un ordine reale e' stato accettato da Betfair */
    bet_id?: string | null;
    meta?: Record<string, unknown> | null;
    /** 01/10 (contratto SQL) - giorno della partita 'YYYY-MM-DD' (Roma); null = inizio non noto */
    giorno_partita?: string | null;
    /** 01/10 (contratto SQL) - 'partita' | 'piazzamento' (inizio non noto) */
    giorno_da?: string | null;
    /** 01/10 (contratto SQL) - la riga appartiene alla giornata chiesta */
    in_day?: boolean | null;
    __bot: Bot;
    /** 24/09 - marcatore del CLIENT (come `__bot`): la riga non porta il
     *  legame ingresso-uscita (i 4 bot tennis, B13). */
    __senzaLegame?: boolean;
}

/** Mezzo centesimo: sotto questa soglia un IMPORTO (abbinato, residuo) non
 *  esiste. NON decide piu' l'esito (C-05, sotto). */
export const SOGLIA_PARI = 0.005;

/**
 * C-05 (01/10, rilievi bassi) - L'ESITO con la STESSA regola del database
 * (storico: `total_pnl > 0` vinta, `< 0` persa, `= 0` pari): ZERO ESATTO AL
 * CENTESIMO. Le cifre sono gia' arrotondate al centesimo (`pnlGlobale`, netto
 * tennis), quindi per loro e' lo zero esatto; un valore con piu' decimali si
 * porta prima al centesimo (simmetrico: -0,005 e' -0,01 come +0,005 e' +0,01),
 * cosi' un residuo di calcolo in virgola mobile (5e-17) non diventa una vinta.
 * Prima: soglia di +/-0,005 (mezzo centesimo, non lo zero del database).
 */
export function esitoDi(pnl: number): Esito {
    const c = Math.sign(pnl) * Math.round(Math.abs(pnl) * 100);
    if (c > 0) return 'vinta';
    if (c < 0) return 'persa';
    return 'pari';
}

/** lo stato di regolamento dal segno al centesimo (stessa regola di `esitoDi`) */
export function statoDaNetto(netto: number): 'won' | 'lost' | 'void' {
    const e = esitoDi(netto);
    return e === 'vinta' ? 'won' : e === 'persa' ? 'lost' : 'void';
}

function testo(v: unknown): string | null {
    return typeof v === 'string' && v.trim() ? v.trim() : null;
}
function numero(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
function cent(n: number): number {
    return Math.round(n * 100) / 100;
}
function msDi(iso: string | null): number {
    if (!iso) return NaN;
    return Date.parse(iso);
}
function ePaper(r: { mode?: string | null }): boolean {
    return String(r.mode ?? '').trim().toLowerCase() === 'paper';
}

/**
 * L'istante di REGOLAMENTO di una gamba: quello di Betfair se il netto di
 * Betfair c'e' (mai per una riga paper), altrimenti quello del bot. E' la
 * stessa scelta della barra (`righeGiornataPerCiclo`): la giornata del reale
 * e' quella di Betfair.
 */
export function regolataAlle(r: TradeChiudibile): string | null {
    if (!ePaper(r) && numero(r.pnl_betfair) != null) {
        return testo(r.pnl_betfair_settled_at) ?? testo(r.settled_at);
    }
    return testo(r.settled_at);
}

const FASE_OMEGA: Record<string, string> = {
    ht_cs: 'Risultato esatto 1T',
    ft_cs: 'Risultato esatto',
    scalp: 'Scalp',
};

/** Il mercato in chiaro: tipo di mercato, fase di Omega, o l'id Betfair. */
function mercatoDi(r: TradeChiudibile): string | null {
    const tipo = testo(r.market_type);
    if (tipo) return tipo;
    const fase = testo(r.phase);
    if (fase) return FASE_OMEGA[fase] ?? fase;
    const mid = testo(r.market_id);
    return mid ? `mercato ${mid}` : null;
}

/** La selezione in chiaro: nome (Safe/Mike), runner (Omega), o l'id. */
function selezioneDi(r: TradeChiudibile): string | null {
    const nome = testo(r.selection_name) ?? testo(r.runner_name);
    if (nome) return nome;
    const sid = r.selection_id;
    return sid == null || sid === '' ? null : `selezione #${String(sid)}`;
}

function latoDi(side: unknown): 'back' | 'lay' | null {
    return side === 'lay' ? 'lay' : side === 'back' ? 'back' : null;
}

/**
 * La chiave di una riga: bot + id, mai l'id da solo.
 *
 * REVIEW 14/09, CRITICO - gli id vengono da tabelle DIVERSE (`omega_trades`,
 * `safe_strategy_trades`, `mike_trades`, `tennis_live_orders`), ognuna con la
 * sua sequenza. Il trade #288 di Safe e il #288 di Omega sono righe diverse.
 */
export function chiaveRiga(bot: Bot, id: unknown): string {
    return `${bot}:${String(id)}`;
}

function rigaChiusa(r: TradeChiudibile, chiusura: boolean): RigaChiusa {
    return {
        id: r.id, bot: r.__bot,
        selezione: selezioneDi(r),
        lato: latoDi(r.side),
        prezzo: numero(r.price), size: numero(r.size),
        pnl: pnlDiRiga(r), fontePnl: fonteDiRiga(r), stato: String(r.status ?? ''),
        at: regolataAlle(r) ?? testo(r.placed_at) ?? '',
        chiusura,
        quale: testo(r.strategy),
        betId: testo(r.bet_id),
        ordine: {
            status: String(r.status ?? ''), side: r.side ?? null,
            price: numero(r.price), size: numero(r.size),
            size_requested: numero(r.size_requested),
            size_matched: numero(r.size_matched),
            size_remaining: numero(r.size_remaining),
            avg_price_matched: numero(r.avg_price_matched),
            betfair_updated_at: testo(r.betfair_updated_at),
            meta: r.meta ?? null,
        },
    };
}

const GIORNO_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * 01/10 - il giorno della posizione secondo il DATABASE (contratto SQL del
 * giorno partita), dalla prima riga che lo porta (l'apertura per prima).
 * `null` = nessuna riga porta il dato: la giornata resta provvisoria.
 * Nessun giorno partita e' calcolato qui: con 'piazzamento' il database
 * dichiara che l'inizio non e' noto e vale il giorno di piazzamento
 * dell'apertura, la stessa regola del database.
 */
export function giornoDalDatabase(
    righe: readonly TradeChiudibile[], piazzataAt: string,
): { giorno: string; da: 'partita' | 'piazzamento' } | null {
    for (const r of righe) {
        const gp = typeof r.giorno_partita === 'string' ? r.giorno_partita.slice(0, 10) : '';
        if (GIORNO_RE.test(gp) && r.giorno_da !== 'piazzamento') return { giorno: gp, da: 'partita' };
        if (r.giorno_da === 'piazzamento') {
            const g = giornataDi(piazzataAt || testo(r.placed_at));
            if (g) return { giorno: g, da: 'piazzamento' };
        }
    }
    return null;
}

/** Le chiavi del contratto del 01/10 che la memoria eredita dalla lettura del database. */
const CHIAVI_GIORNO = ['giorno_partita', 'giorno_da', 'in_day'] as const;

/** La riga porta il giorno del database? (contratto del 01/10: `giorno_da` o `in_day` valorizzati) */
export function haGiornoDb(r: object): boolean {
    const x = r as { giorno_da?: unknown; in_day?: unknown };
    return x.giorno_da === 'partita' || x.giorno_da === 'piazzamento' || typeof x.in_day === 'boolean';
}

/**
 * La posizione da un'apertura (o dalla prima riga di un ripiego B13) e da
 * TUTTE le sue gambe. `null` = non ancora chiusa.
 */
function costruisci(
    a: TradeChiudibile, gambe: readonly TradeChiudibile[], legame: Legame, orfana: boolean,
): PosizioneChiusa | null {
    if (!isSettled(String(a.status ?? ''))) return null;   // non ancora conclusa

    // UNA GAMBA ANCORA VIVA = POSIZIONE NON CHIUSA. Sommare solo le righe
    // regolate darebbe un P&L parziale mostrato come definitivo.
    // ECCEZIONE (18/09, certezza di chiusura): una gamba `cancelled` non andra'
    // mai a won/lost/void - e' morta senza aver portato rischio; prima faceva
    // sparire l'INTERA posizione per sempre. Le gambe `error` sono gia' fuori.
    for (const g of gambe) {
        const s = String(g.status ?? '').toLowerCase();
        if (!isSettled(s) && s !== 'cancelled') return null;
    }

    const tutte = [a, ...gambe];
    const live = !ePaper(a);
    // il P&L globale somma TUTTE le gambe regolate: su un green-up l'apertura
    // vince e la copertura perde, e solo la somma dice il vero. Di ogni gamba
    // il netto di BETFAIR se c'e', altrimenti il calcolo del bot.
    let globale = 0;
    let reale: number | null = null;
    let stimato: number | null = null;
    let regMs = NaN;
    let regIso: string | null = null;
    const regolate: TradeChiudibile[] = [];
    for (const r of tutte) {
        if (!isSettled(String(r.status ?? ''))) continue;
        regolate.push(r);
        const v = pnlDiRiga(r) ?? 0;
        globale += v;
        if (live) {
            if (numero(r.pnl_betfair) != null) reale = (reale ?? 0) + v;
            else stimato = (stimato ?? 0) + v;
        }
        const iso = regolataAlle(r);
        const ms = msDi(iso);
        if (Number.isFinite(ms) && !(ms <= regMs)) { regMs = ms; regIso = iso; }
    }
    globale = cent(globale);
    const fontePnl = fonteDiRighe(regolate) ?? 'stima';

    const conMs = tutte.map((r) => {
        const riga = rigaChiusa(r, legame === 'catena' && numero(r.closes_trade_id) != null);
        return { riga, ms: msDi(riga.at || null) };
    });
    conMs.sort((x, y) => (Number.isFinite(x.ms) ? x.ms : 0) - (Number.isFinite(y.ms) ? y.ms : 0));
    const righe = conMs.map((x) => x.riga);

    let chiusaMs = NaN;
    let chiusaAt = '';
    for (const x of conMs) {
        if (Number.isFinite(x.ms) && !(x.ms <= chiusaMs)) { chiusaMs = x.ms; chiusaAt = x.riga.at; }
    }
    const piazzataAt = testo(a.placed_at) ?? '';

    // LA GIORNATA (01/10) = quella del DATABASE (giorno della partita, o il
    // piazzamento se l'inizio non e' noto). Senza il dato del database: il
    // regolamento, PROVVISORIO e dichiarato; senza regolamento, il piazzamento.
    let giorno = '';
    let giornoDa: GiornoDa = 'nessuno';
    let giornoConfermato = false;
    const db = giornoDalDatabase(tutte, piazzataAt);
    if (db) {
        giorno = db.giorno;
        giornoDa = db.da;
        giornoConfermato = true;
    } else {
        giorno = regIso ? giornataDi(regIso) : '';
        giornoDa = giorno ? 'regolamento' : 'nessuno';
        if (!giorno) {
            giorno = giornataDi(piazzataAt);
            if (giorno) giornoDa = 'piazzamento';
        }
    }

    const nomeTennis = String(a.sport ?? '').toLowerCase() === 'tennis';
    return {
        id: a.id,
        eventId: String(a.event_id ?? ''),
        partita: testo(a.event_name) ?? `evento ${a.event_id ?? '?'}`,
        sport: nomeTennis ? 'tennis' : 'calcio',
        modo: modoDi(a),
        bot: a.__bot,
        pnlGlobale: globale,
        fontePnl,
        pnlReale: reale == null ? null : cent(reale),
        pnlStimato: stimato == null ? null : cent(stimato),
        esito: esitoDi(globale),
        righe,
        chiusaAt,
        piazzataAt,
        giorno,
        giornoDa,
        giornoConfermato,
        orfana,
        legame,
        mercato: mercatoDi(a),
        selezione: selezioneDi(a),
        lato: latoDi(a.side),
        origine: testo(a.origin),
    };
}

/**
 * Costruisce le posizioni chiuse dalle righe grezze dei bot.
 *
 * Una POSIZIONE e' un'apertura (`closes_trade_id` vuoto) piu' TUTTE le gambe
 * della sua catena (A <- B <- C). Le coperture non sono posizioni proprie, ma
 * il loro P&L entra INTERAMENTE nel globale, perche' sono soldi veri.
 *
 * Entra solo cio' che e' DEFINITIVO: una posizione con una gamba ancora viva
 * non e' "chiusa".
 *
 * Le righe `__senzaLegame` (bot tennis, B13) si raggruppano per (bot,
 * modalita', mercato, selezione): e' il RIPIEGO dichiarato (`legame`).
 */
export function posizioniChiuse(trades: readonly TradeChiudibile[]): PosizioneChiusa[] {
    // indice di TUTTE le righe vere, per riconoscere le coperture orfane
    const perChiave = new Map<string, TradeChiudibile>();
    const vere: TradeChiudibile[] = [];
    const senzaLegame = new Map<string, TradeChiudibile[]>();
    for (const t of trades) {
        if (isErrorRow(String(t.status ?? ''))) continue;   // mai andata a mercato
        if (t.__senzaLegame) {
            const k = [t.__bot, modoDi(t), testo(t.market_id) ?? `ev:${t.event_id ?? ''}`,
                String(t.selection_id ?? '')].join('|');
            const l = senzaLegame.get(k);
            if (l) l.push(t); else senzaLegame.set(k, [t]);
            continue;
        }
        vere.push(t);
        perChiave.set(chiaveRiga(t.__bot, t.id), t);
    }

    const coperture = new Map<string, TradeChiudibile[]>();
    const aperture: { t: TradeChiudibile; orfana: boolean }[] = [];
    for (const t of vere) {
        const chiude = numero(t.closes_trade_id);
        if (chiude == null) { aperture.push({ t, orfana: false }); continue; }
        const padre = chiaveRiga(t.__bot, chiude);
        if (!perChiave.has(padre)) {
            // COPERTURA ORFANA - il trade che chiudeva non e' fra le righe
            // lette. I suoi euro sono veri: una posizione a se', marcata.
            aperture.push({ t, orfana: true });
            continue;
        }
        const lista = coperture.get(padre);
        if (lista) lista.push(t); else coperture.set(padre, [t]);
    }

    /** Tutte le gambe di una posizione, seguendo la catena fino in fondo. */
    const gambeDi = (radice: TradeChiudibile): TradeChiudibile[] => {
        const fuori: TradeChiudibile[] = [];
        const coda = [radice];
        const visti = new Set<string>([chiaveRiga(radice.__bot, radice.id)]);
        for (let i = 0; i < coda.length; i++) {
            const nodo = coda[i];
            for (const g of coperture.get(chiaveRiga(nodo.__bot, nodo.id)) ?? []) {
                const k = chiaveRiga(g.__bot, g.id);
                if (visti.has(k)) continue;      // difesa contro un ciclo nei dati
                visti.add(k);
                fuori.push(g);
                coda.push(g);
            }
        }
        return fuori;
    };

    const out: PosizioneChiusa[] = [];
    for (const { t, orfana } of aperture) {
        const p = costruisci(t, gambeDi(t), 'catena', orfana);
        if (p) out.push(p);
    }
    for (const gruppo of senzaLegame.values()) {
        const ordinato = gruppo.slice().sort((x, y) => x.id - y.id);
        const p = costruisci(ordinato[0], ordinato.slice(1), 'ripiego', false);
        if (p) out.push(p);
    }

    // le piu' recenti in cima: su un banco si guarda l'ultima cosa successa
    const ms = new Map<PosizioneChiusa, number>();
    for (const p of out) { const v = msDi(p.chiusaAt || null); ms.set(p, Number.isFinite(v) ? v : 0); }
    return out.sort((x, y) => (ms.get(y) as number) - (ms.get(x) as number));
}

// ============================================================================
// 24/09 - I 4 BOT TENNIS: la traduzione di una riga di `tennis_live_orders`
// nel contratto delle altre (UNA sola, usata dalla pagina e dallo storico).
// ============================================================================

/**
 * Il P&L NETTO di un ordine tennis: il netto di Betfair quando c'e' (mai per
 * una riga paper), altrimenti `pnl - commission` (il `pnl` della tabella e'
 * LORDO). `null` = non ancora regolato.
 */
export function nettoOrdineTennis(o: Pick<TennisBotOrderRow, 'mode' | 'pnl' | 'commission' | 'pnl_betfair'>): number | null {
    const reale = o.pnl_betfair;
    if (String(o.mode ?? '').toLowerCase() !== 'paper'
        && typeof reale === 'number' && Number.isFinite(reale)) return reale;
    const lordo = o.pnl;
    if (typeof lordo !== 'number' || !Number.isFinite(lordo)) return null;
    const comm = o.commission;
    const c = typeof comm === 'number' && Number.isFinite(comm) ? comm : 0;
    return Math.round((lordo - c) * 100) / 100;
}

/**
 * Un ordine REGOLATO di un bot tennis come riga chiudibile. `null` = non
 * entra (non e' di un bot tennis, e' in errore, non e' regolato, o il suo P&L
 * non e' ancora noto: "0,00" sarebbe uno zero travestito da pareggio).
 *
 * DUE TRADUZIONI OBBLIGATE, nessuna inventata:
 *  1. LO STATO. `status` e' lo stato flumine (`EXECUTION_COMPLETE` = abbinato
 *     tutto, non regolato): il regolamento lo dichiara `settled_at`, l'esito
 *     lo dice il segno del netto.
 *  2. IL P&L. `pnl` e' LORDO: si usa `nettoOrdineTennis`.
 * La riga porta `__senzaLegame`: il servizio non scrive quale ordine chiude
 * quale (B13), quindi si raggruppa per (bot, mercato, selezione).
 */
export function rigaDaOrdineTennis(
    o: TennisBotOrderRow, nomePartita: string | null, isBot: (b: string) => boolean,
): TradeChiudibile | null {
    const bot = o.source;
    if (bot == null || !isBot(String(bot))) return null;
    if (isErrorRow(o.status)) return null;
    if (o.settled_at == null) return null;
    const netto = nettoOrdineTennis(o);
    if (netto == null) return null;
    // 01/10 (contratto SQL): il giorno della partita, se la lettura lo porta
    const extra = o as unknown as Record<string, unknown>;
    const giornoDb: Partial<TradeChiudibile> = {};
    for (const c of CHIAVI_GIORNO) {
        if (c in extra) (giornoDb as Record<string, unknown>)[c] = extra[c];
    }
    return {
        ...giornoDb,
        id: o.id,
        event_id: String(o.event_id ?? ''),
        event_name: nomePartita,
        sport: 'tennis',
        mode: o.mode,
        status: statoDaNetto(netto),
        pnl: netto,
        pnl_betfair: o.pnl_betfair ?? null,
        pnl_betfair_settled_at: o.pnl_betfair_settled_at ?? null,
        side: o.side,
        price: o.price ?? null,
        size: o.size ?? null,
        // `tennis_live_orders` porta il `selection_id`, non il nome
        selection_name: null,
        market_id: o.market_id ?? null,
        selection_id: o.selection_id ?? null,
        placed_at: o.placed_at ?? null,
        settled_at: o.settled_at,
        closes_trade_id: null,
        strategy: null,
        size_requested: o.size ?? null,
        size_matched: o.size_matched ?? null,
        size_remaining: o.size_remaining ?? null,
        avg_price_matched: o.average_price_matched ?? null,
        betfair_updated_at: o.updated_at ?? null,
        bet_id: o.bet_id ?? null,
        meta: null,
        __bot: bot as Bot,
        __senzaLegame: true,
    };
}

/**
 * Unisce le righe in memoria (canali + lettura dei 30 s) con quelle lette per
 * una giornata dal database. Chiave bot+id; vince la MEMORIA (e' piu'
 * fresca). Serve a completare le catene: una chiusura "orfana" in memoria
 * ritrova la sua apertura letta dalla giornata.
 */
export function unisciRighe(
    memoria: readonly TradeChiudibile[], giornata: readonly TradeChiudibile[],
): TradeChiudibile[] {
    if (!giornata.length) return memoria as TradeChiudibile[];
    // 01/10: la riga in memoria vince (piu' fresca) ma EREDITA il giorno della
    // partita dalla stessa riga letta dal database (la memoria non lo porta)
    const dalDb = new Map<string, TradeChiudibile>();
    for (const r of giornata) dalDb.set(chiaveRiga(r.__bot, r.id), r);
    const viste = new Set<string>();
    const out: TradeChiudibile[] = [];
    for (const r of memoria) {
        const k = chiaveRiga(r.__bot, r.id);
        viste.add(k);
        const d = dalDb.get(k);
        if (d && !haGiornoDb(r) && haGiornoDb(d)) {
            const conGiorno: TradeChiudibile = { ...r };
            for (const c of CHIAVI_GIORNO) {
                if (c in d) (conGiorno as unknown as Record<string, unknown>)[c] = (d as unknown as Record<string, unknown>)[c];
            }
            out.push(conGiorno);
        } else out.push(r);
    }
    for (const r of giornata) {
        const k = chiaveRiga(r.__bot, r.id);
        if (viste.has(k)) continue;
        viste.add(k);
        out.push(r);
    }
    return out;
}

// ============================================================================
// FILTRI E RIEPILOGO
// ============================================================================

export interface FiltroChiuse {
    esito?: Esito | 'tutte';
    sport?: 'calcio' | 'tennis' | 'tutti';
    modo?: Modo | 'tutte';
    bot?: Bot | 'tutti';
    /**
     * GIORNATA da mostrare, 'YYYY-MM-DD' (Europe/Rome), giorno della partita
     * (01/10; vedi `GiornoDa` per i ripieghi). `undefined` / `null` / '' =
     * nessun filtro di giornata.
     */
    giorno?: string | null;
    /** 24/09 - 'betfair' = solo posizioni col netto TUTTO regolato da Betfair */
    fonte?: 'tutte' | 'betfair';
}

export function filtraChiuse(
    righe: readonly PosizioneChiusa[], f: FiltroChiuse,
): PosizioneChiusa[] {
    const giorno = typeof f.giorno === 'string' && f.giorno.trim() ? f.giorno.trim() : null;
    return righe.filter((p) => {
        if (f.esito && f.esito !== 'tutte' && p.esito !== f.esito) return false;
        if (f.sport && f.sport !== 'tutti' && p.sport !== f.sport) return false;
        if (f.modo && f.modo !== 'tutte' && p.modo !== f.modo) return false;
        if (f.bot && f.bot !== 'tutti' && p.bot !== f.bot) return false;
        if (f.fonte === 'betfair' && p.fontePnl !== 'conto') return false;
        // una posizione SENZA giornata leggibile non e' "di oggi": lo dice la
        // scheda con un avviso, invece di finire nel totale del giorno
        if (giorno && p.giorno !== giorno) return false;
        return true;
    });
}

/**
 * 26/09 (F-1, e2e fase 3) - IL P&L «OGGI» DI UN BOT nella plancia, con la
 * STESSA fonte e la STESSA regola della scheda Posizioni chiuse: posizioni
 * chiuse, UNA modalita', netto (`pnlGlobale`). Prima Omega/Mike/Safe avevano
 * `null` («oggi —») mentre le Chiuse della stessa pagina dicevano +0,95 /
 * +0,79 €. `strategia` (Safe) = quella dell'APERTURA del ciclo. `null` =
 * nessuna posizione chiusa: «—», mai uno zero inventato.
 *
 * 01/10 (rilievi bassi, punto 1) - la giornata e' `p.giorno`, cioe' quella
 * della scheda: giorno della PARTITA quando la riga porta il dato del database
 * (`posizioniDellaGiornata` in `lib/chiuseGiornata`), altrimenti il giorno di
 * REGOLAMENTO, provvisorio (`giornoConfermato` false). `escluse` = le posizioni
 * che la scheda toglie dal giorno (partite di altri giorni): fuori anche qui.
 */
export function pnlChiuseDelGiorno(
    posizioni: readonly PosizioneChiusa[],
    f: {
        giorno: string; bot: Bot; modo: Modo; strategia?: string | null;
        escluse?: ReadonlySet<PosizioneChiusa>;
    },
): number | null {
    let tot: number | null = null;
    for (const p of chiuseDelBot(posizioni, f)) tot = cent((tot ?? 0) + p.pnlGlobale);
    return tot;
}

/** Le posizioni chiuse di un bot nel giorno: la base di `pnlChiuseDelGiorno`. */
export function chiuseDelBot(
    posizioni: readonly PosizioneChiusa[],
    f: {
        giorno: string; bot: Bot; modo: Modo; strategia?: string | null;
        escluse?: ReadonlySet<PosizioneChiusa>;
    },
): PosizioneChiusa[] {
    const out: PosizioneChiusa[] = [];
    for (const p of filtraChiuse(posizioni, { giorno: f.giorno, bot: f.bot, modo: f.modo })) {
        if (f.escluse?.has(p)) continue;
        if (f.strategia != null) {
            const apertura = p.righe.find((r) => !r.chiusura && String(r.id) === String(p.id));
            if ((apertura?.quale ?? null) !== f.strategia) continue;
        }
        out.push(p);
    }
    return out;
}

/** giorno di REGOLAMENTO (Roma) di una riga: quello del conto per il reale */
function giornoRegolamentoRiga(r: RigaChiusa): string {
    return giornataDi(r.at || null);
}

export interface ControprovaRegolato {
    /** somma dei netti delle gambe regolate nel giorno (conto Betfair + stima) */
    totale: number | null;
    reale: number | null;
    stimato: number | null;
}

/**
 * B-12 (01/10) - LA CONTROPROVA CON LA BARRA sullo STESSO perimetro della
 * barra: le gambe SOLDI VERI regolate nel giorno (giorno di REGOLAMENTO del
 * conto Betfair, la stessa regola di `righeGiornataPerCiclo`), qualunque sia
 * il giorno della loro partita. Di ogni gamba il netto di Betfair se c'e',
 * altrimenti la stima (come la barra). Le posizioni a cavallo della
 * mezzanotte si elencano a parte (`aCavalloDellaMezzanotte`).
 */
export function regolatoNelGiorno(posizioni: readonly PosizioneChiusa[], giorno: string): ControprovaRegolato {
    let reale: number | null = null;
    let stimato: number | null = null;
    for (const p of posizioni) {
        if (p.modo !== 'live') continue;
        for (const r of p.righe) {
            if (r.pnl == null || !isSettled(r.stato)) continue;
            if (giornoRegolamentoRiga(r) !== giorno) continue;
            if (r.fontePnl === 'conto') reale = cent((reale ?? 0) + r.pnl);
            else stimato = cent((stimato ?? 0) + r.pnl);
        }
    }
    const totale = reale == null && stimato == null ? null : cent((reale ?? 0) + (stimato ?? 0));
    return { totale, reale, stimato };
}

export interface ACavallo {
    p: PosizioneChiusa;
    /** giorno di regolamento dell'ultima gamba */
    regolata: string;
}

/**
 * B-12 (01/10) - le posizioni il cui giorno della partita (confermato dal
 * database) e' diverso dal giorno in cui si sono regolate, e che toccano la
 * giornata `giorno` da uno dei due lati: si ELENCANO, mai sommate in silenzio.
 */
export function aCavalloDellaMezzanotte(posizioni: readonly PosizioneChiusa[], giorno: string): ACavallo[] {
    const out: ACavallo[] = [];
    for (const p of posizioni) {
        if (!p.giornoConfermato) continue;
        const regolata = giornataDi(p.chiusaAt || null);
        if (!regolata || regolata === p.giorno) continue;
        if (p.giorno !== giorno && regolata !== giorno) continue;
        out.push({ p, regolata });
    }
    return out;
}

/**
 * Quante posizioni chiuse restano FUORI dalla giornata mostrata (e quante non
 * hanno proprio una data): la scheda lo dice invece di farle sparire.
 */
export function fuoriGiornata(
    righe: readonly PosizioneChiusa[], giorno: string,
): { altriGiorni: number; senzaData: number } {
    let altriGiorni = 0, senzaData = 0;
    for (const p of righe) {
        if (!p.giorno) { senzaData += 1; continue; }
        if (p.giorno !== giorno) altriGiorni += 1;
    }
    return { altriGiorni, senzaData };
}

export interface RiepilogoChiuse {
    n: number;
    vinte: number;
    perse: number;
    pari: number;
    /** somma dei P&L globali; `null` se non c'e' nessuna posizione */
    totale: number | null;
    /** vinte su vinte+perse; `null` senza esiti */
    percentualeVinte: number | null;
    /** 24/09 - di `totale`, la parte regolata da Betfair e quella stimata
     *  (soldi veri). Paper: entrambe null. */
    reale?: number | null;
    stimato?: number | null;
    /** quante posizioni sono orfane / a ripiego B13 (si dichiarano) */
    orfane?: number;
    ripiego?: number;
}

/** Il riepilogo di un insieme di posizioni GIA' filtrate: quello che si vede
 *  in alto deve descrivere quello che si vede sotto, non tutto il resto. */
export function riepilogoChiuse(righe: readonly PosizioneChiusa[]): RiepilogoChiuse {
    let vinte = 0, perse = 0, pari = 0, totale = 0, orfane = 0, ripiego = 0;
    let reale: number | null = null;
    let stimato: number | null = null;
    for (const p of righe) {
        if (p.esito === 'vinta') vinte += 1;
        else if (p.esito === 'persa') perse += 1;
        else pari += 1;
        totale += p.pnlGlobale;
        if (p.pnlReale != null) reale = (reale ?? 0) + p.pnlReale;
        if (p.pnlStimato != null) stimato = (stimato ?? 0) + p.pnlStimato;
        if (p.orfana) orfane += 1;
        if (p.legame === 'ripiego') ripiego += 1;
    }
    const conEsito = vinte + perse;
    return {
        n: righe.length, vinte, perse, pari,
        totale: righe.length ? cent(totale) : null,
        percentualeVinte: conEsito > 0 ? vinte / conEsito : null,
        reale: reale == null ? null : cent(reale),
        stimato: stimato == null ? null : cent(stimato),
        orfane, ripiego,
    };
}

// ============================================================================
// 24/09 - LA REGOLA DI RAGGRUPPAMENTO, una per calcio e tennis:
//   giornata (della partita dal 01/10, Roma) -> bot -> partita -> ciclo
// Ogni livello porta il suo netto e la sua composizione (reale / stimato), e
// la somma dei livelli e' IDENTICA al totale della giornata (testato).
// Safe si divide per sport ("Safe calcio" / "Safe tennis"), come le voci della
// barra di giornata.
// ============================================================================

export interface GruppoPartita {
    chiave: string;
    eventId: string;
    partita: string;
    sport: 'calcio' | 'tennis';
    cicli: PosizioneChiusa[];
    riepilogo: RiepilogoChiuse;
}

export interface GruppoBot {
    /** 'omega' | 'safe_calcio' | 'safe_tennis' | 'mike' | chiave del bot tennis */
    chiave: string;
    bot: Bot;
    sport: 'calcio' | 'tennis' | null;
    partite: GruppoPartita[];
    riepilogo: RiepilogoChiuse;
}

export interface GiornataChiuse {
    giorno: string;
    bots: GruppoBot[];
    riepilogo: RiepilogoChiuse;
}

const ORDINE_GRUPPI = [
    'omega', 'safe_calcio', 'mike', 'safe_tennis',
    'tennis_scalper', 'tennis_pro', 'tennis_flb', 'tennis_swing',
];

export function chiaveGruppoBot(p: Pick<PosizioneChiusa, 'bot' | 'sport'>): string {
    return p.bot === 'safe' ? `safe_${p.sport}` : p.bot;
}

/**
 * Raggruppa posizioni GIA' filtrate (una giornata, una modalita').
 * Bot nell'ordine fisso; partite e cicli dal piu' recente.
 */
export function raggruppaGiornata(giorno: string, posizioni: readonly PosizioneChiusa[]): GiornataChiuse {
    const perBot = new Map<string, Map<string, PosizioneChiusa[]>>();
    for (const p of posizioni) {
        const kb = chiaveGruppoBot(p);
        let partite = perBot.get(kb);
        if (!partite) { partite = new Map(); perBot.set(kb, partite); }
        const kp = p.eventId || `senza-evento:${p.partita}`;
        const l = partite.get(kp);
        if (l) l.push(p); else partite.set(kp, [p]);
    }
    const bots: GruppoBot[] = [];
    for (const [kb, partite] of perBot) {
        const gruppi: GruppoPartita[] = [];
        for (const [kp, cicli] of partite) {
            const primo = cicli[0];
            gruppi.push({
                chiave: kp, eventId: primo.eventId, partita: primo.partita, sport: primo.sport,
                cicli, riepilogo: riepilogoChiuse(cicli),
            });
        }
        // le posizioni arrivano gia' dalla piu' recente: la partita con il
        // ciclo piu' recente sta in cima
        const tutte = gruppi.flatMap((g) => g.cicli);
        const primo = tutte[0];
        bots.push({
            chiave: kb, bot: primo.bot,
            sport: primo.bot === 'safe' ? primo.sport : null,
            partite: gruppi, riepilogo: riepilogoChiuse(tutte),
        });
    }
    const pos = (k: string) => { const i = ORDINE_GRUPPI.indexOf(k); return i < 0 ? 99 : i; };
    bots.sort((a, b) => pos(a.chiave) - pos(b.chiave));
    return { giorno, bots, riepilogo: riepilogoChiuse(posizioni) };
}

// ============================================================================
// 18/09 - CERTEZZA DI CHIUSURA di una posizione della scheda.
//
// Il GIUDIZIO non vive qui: e' `lib/certezzaChiusura.ts`, lo stesso della
// striscia di esito delle schede di uscita.
// ============================================================================

/** L'apertura di una posizione: la riga con l'id della posizione. */
function aperturaDi(p: PosizioneChiusa): RigaChiusa | null {
    return p.righe.find((r) => r.id === p.id) ?? p.righe[0] ?? null;
}

function statoMorto(stato: string): boolean {
    return String(stato).toLowerCase() === 'cancelled';
}

/**
 * Il giudizio "effettivamente chiusa" di UNA posizione. `regolataDalMercato`
 * si RICAVA dagli stati delle righe: non e' un `true` cablato.
 */
export function certezzaDiPosizione(p: PosizioneChiusa): RisultatoCertezzaChiusura {
    const a = aperturaDi(p);
    const chiusure = p.righe.filter((r) => r !== a);
    const regolata = a != null && isSettled(a.stato)
        && chiusure.every((r) => isSettled(r.stato) || statoMorto(r.stato));
    return certezzaChiusura({
        apertura: a?.ordine ?? {},
        chiusure: chiusure.map((r) => r.ordine),
        regolataDalMercato: regolata,
        modo: p.modo,
    });
}

/** Quante gambe di chiusura sono state ANNULLATE. */
export function gambeAnnullate(p: PosizioneChiusa): number {
    const a = aperturaDi(p);
    return p.righe.filter((r) => r !== a && statoMorto(r.stato)).length;
}

export interface SintesiPosizione {
    ingresso: { lato: 'back' | 'lay' | null; prezzo: number | null; stake: number | null; at: string };
    /** quota media PESATA sull'abbinato e stake abbinato delle gambe di
     *  chiusura; `null` = nessuna gamba ha abbinato qualcosa (mai zero) */
    chiusura: { prezzoMedio: number | null; stake: number | null; at: string } | null;
}

/**
 * Ingresso e chiusura in una riga: quota, stake ABBINATO, ora. I numeri sono
 * quelli di `statoOrdine`; solo se mancano si ripiega su `size`/`price` - e
 * solo per righe REGOLATE, dove portano l'abbinato.
 */
export function sintesiPosizione(p: PosizioneChiusa): SintesiPosizione {
    const abbinatoDi = (r: RigaChiusa): { stake: number | null; prezzo: number | null } => {
        const s = statoOrdine(r.ordine);
        const regolata = isSettled(r.stato);
        return {
            stake: s.abbinato.valore ?? (regolata ? r.size : null),
            prezzo: s.prezzoMedio.valore ?? (regolata ? r.prezzo : null),
        };
    };
    const a = aperturaDi(p);
    const ing = a ? abbinatoDi(a) : { stake: null, prezzo: null };
    let stake = 0, pesato = 0, ultimo = '';
    for (const r of p.righe) {
        if (r === a || statoMorto(r.stato)) continue;
        const g = abbinatoDi(r);
        if (g.stake == null || g.stake <= 0 || g.prezzo == null) continue;
        stake += g.stake;
        pesato += g.stake * g.prezzo;
        if (r.at > ultimo) ultimo = r.at;
    }
    return {
        ingresso: { lato: a?.lato ?? null, prezzo: ing.prezzo, stake: ing.stake, at: p.piazzataAt },
        chiusura: stake > 0
            ? { prezzoMedio: pesato / stake, stake: Math.round(stake * 100) / 100, at: ultimo }
            : null,
    };
}
