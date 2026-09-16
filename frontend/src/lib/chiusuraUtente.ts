// ============================================================================
// chiusuraUtente.ts — «SE CHIUDO IO, IL BOT DEVE SAPERLO».
//
// Ordine dell'utente del 16/09 sera, valido per TUTTI i bot tranne Mike:
//   «se chiudo io (anche fuori dall'app, direttamente su Betfair) il bot deve
//    saperlo e NON gestire posizioni che non esistono piu'».
//
// Qui NON si decide niente: si LEGGE quello che il servizio ha gia' scritto.
//   · Safe  → `meta.chiuso_dall_utente` sulle RIGHE (bot_service.py:1674,
//             `segna_chiuso_dall_utente`), che sopravvive al riavvio;
//   · Omega → `stats.eventi_chiusi_dall_utente` e la RPC
//             `omega_eventi_chiusi_dall_utente()` (migrazione 16/09).
//
// LA REGOLA DELLA CASA: «il servizio dichiara, la pagina non inventa». Se il
// marcatore non c'e', la partita NON e' chiusa dall'utente — non si deduce da
// «non ci sono piu' righe vive», che vuol dire un'altra cosa (regolata, mai
// aperta, ancora da leggere). E ASSENTE non e' ZERO: un marcatore senza istante
// resta un marcatore, ma l'istante si scrive «—», non «adesso».
// ============================================================================

/** Il marcatore che il servizio scrive: `{quando, come, event_id, …}`. */
export interface MarcatoreChiusura {
    /** ISO dell'istante in cui il bot se n'e' accorto; null = non dichiarato */
    quando: string | null;
    /**
     * COME la partita e' uscita dalle mani del bot, in CODICE (la traduzione
     * italiana vive in un posto solo, `comeLabel`):
     *   'cashout'       l'ultima riga viva chiusa a mano dalla scheda
     *   'cashout_event' cash-out globale della partita (il bottone nuovo)
     *   'fuori_app'     scoperto sulla posizione di CONTO: chiusa su Betfair
     */
    come: string | null;
    /** quello che il servizio ha allegato: non si interpreta, si mostra */
    dettaglio: Record<string, unknown>;
}

/** Riga di trade che puo' portare il marcatore (Safe, Omega). */
export interface RigaConMeta {
    event_id?: string | null;
    meta?: Record<string, unknown> | null;
}

const CHIAVE = 'chiuso_dall_utente';

function testo(v: unknown): string | null {
    if (v == null) return null;
    const s = String(v).trim();
    return s === '' ? null : s;
}

/**
 * Il marcatore di UNA riga, o `null`.
 *
 * ⚠️ Si accetta sia il marcatore come oggetto (la forma vera: il servizio
 * scrive un dict) sia `true` secco, perche' un marcatore degradato resta un
 * marcatore: fail-closed. Quello che NON si accetta e' `false`/assente, che
 * significa «non chiusa dall'utente» e basta.
 */
export function marcatoreRiga(riga: RigaConMeta | null | undefined): MarcatoreChiusura | null {
    const meta = riga?.meta;
    if (!meta || typeof meta !== 'object') return null;
    const raw = (meta as Record<string, unknown>)[CHIAVE];
    if (raw == null || raw === false) return null;
    if (raw === true) return { quando: null, come: null, dettaglio: {} };
    if (typeof raw !== 'object') return null;
    const o = raw as Record<string, unknown>;
    const dettaglio: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(o)) {
        if (k !== 'quando' && k !== 'come') dettaglio[k] = v;
    }
    return { quando: testo(o.quando), come: testo(o.come), dettaglio };
}

/** La partita e' chiusa dall'utente, e da CHE COSA lo sappiamo. */
export interface StatoChiusuraEvento {
    chiusa: boolean;
    /**
     * `servizio` = lo dichiara il servizio nel suo elenco (Omega);
     * `righe` = sta scritto nel `meta` delle righe (Safe);
     * `null` = non e' chiusa.
     */
    fonte: 'servizio' | 'righe' | null;
    marcatore: MarcatoreChiusura | null;
}

/**
 * Lo stato di UNA partita, messe insieme le due fonti.
 *
 * L'elenco del servizio VINCE quando c'e' (e' lui l'autorita'), ma se il
 * servizio non lo pubblica — Safe non lo pubblica, il marcatore vive sulle
 * righe — si guardano le righe di QUELLA partita. Mai il contrario: una riga
 * senza marcatore non cancella un evento che il servizio dichiara chiuso.
 */
export function statoChiusuraEvento(args: {
    eventId: string | null | undefined;
    righe?: readonly RigaConMeta[] | null;
    /** event_id dichiarati chiusi dal servizio (Omega: `stats`/RPC) */
    eventiDalServizio?: readonly string[] | null;
}): StatoChiusuraEvento {
    const eid = testo(args.eventId);
    if (!eid) return { chiusa: false, fonte: null, marcatore: null };

    const dichiarati = args.eventiDalServizio;
    if (dichiarati && dichiarati.some((x) => testo(x) === eid)) {
        // il servizio lo dichiara: si cerca comunque il dettaglio sulle righe,
        // ma la sua assenza non smentisce il servizio
        const m = (args.righe ?? []).filter((r) => testo(r?.event_id) === eid)
            .map(marcatoreRiga).find((x): x is MarcatoreChiusura => x != null) ?? null;
        return { chiusa: true, fonte: 'servizio', marcatore: m };
    }

    for (const r of args.righe ?? []) {
        if (testo(r?.event_id) !== eid) continue;
        const m = marcatoreRiga(r);
        if (m) return { chiusa: true, fonte: 'righe', marcatore: m };
    }
    return { chiusa: false, fonte: null, marcatore: null };
}

/** Gli event_id chiusi dall'utente secondo le RIGHE (indice per la pagina). */
export function eventiChiusiDalleRighe(
    righe: readonly RigaConMeta[] | null | undefined,
): Map<string, MarcatoreChiusura> {
    const out = new Map<string, MarcatoreChiusura>();
    for (const r of righe ?? []) {
        const eid = testo(r?.event_id);
        if (!eid || out.has(eid)) continue;
        const m = marcatoreRiga(r);
        if (m) out.set(eid, m);
    }
    return out;
}

/** `come` → italiano. UNA sola tabella: due traduzioni della stessa cosa prima
 *  o poi dicono due cose diverse. */
const COME_IT: Record<string, string> = {
    cashout: 'hai chiuso a mano l’ultima posizione viva',
    cashout_event: 'hai fatto il cash out globale della partita',
    fuori_app: 'la posizione e’ stata chiusa fuori dall’app, direttamente su Betfair',
};

export function comeLabel(come: string | null | undefined): string | null {
    const k = testo(come)?.toLowerCase() ?? null;
    if (!k) return null;
    return COME_IT[k] ?? k.replace(/_/g, ' ');
}

// --------------------------------------------------------------- i payload
//
// I due gesti nuovi viaggiano sulla CODA che esiste gia' (`safe_request`), con
// i kind aggiunti dalla migrazione del 16/09. Il payload lo valida anche la
// RPC (`payload % senza event_id`), ma un payload sbagliato non deve nemmeno
// partire: qui si rompe subito e in italiano, non dopo un giro sul database.

export class EventoMancante extends Error {
    constructor(gesto: string) {
        super(`${gesto}: manca l’identificativo della partita, la richiesta non parte`);
        this.name = 'EventoMancante';
    }
}

/** Payload di `safe_request('cashout_event', …)` — SOLO `event_id`: quali
 *  righe chiudere lo decide il servizio leggendo le SUE tabelle. */
export function payloadCashoutEvento(eventId: string | null | undefined): { event_id: string } {
    const eid = testo(eventId);
    if (!eid) throw new EventoMancante('cash out globale');
    return { event_id: eid };
}

/** Payload di `safe_request('riprendi_evento', …)`. */
export function payloadRiprendiEvento(eventId: string | null | undefined): { event_id: string } {
    const eid = testo(eventId);
    if (!eid) throw new EventoMancante('riprendi');
    return { event_id: eid };
}

/**
 * PERCHE' il bottone e' spento, in italiano. `null` = si puo' premere.
 *
 * Regola della casa: **un pulsante spento dice PERCHE'**. E il caso piu'
 * probabile oggi e' che la migrazione del 16/09 non sia applicata: la RPC
 * `safe_request` ha ancora il CHECK vecchio e RIFIUTA i due kind nuovi. Non si
 * nasconde: l'errore del servizio si mostra com'e'.
 */
export function motivoCashoutSpento(args: {
    eventId: string | null | undefined;
    /** ci sono posizioni del bot ancora vive su questa partita? */
    posizioniVive: number;
    chiusa: boolean;
    inCorso?: boolean;
}): string | null {
    if (!testo(args.eventId)) return 'partita senza identificativo: non si puo’ chiedere niente al servizio';
    if (args.inCorso) return 'richiesta gia’ in corso: si aspetta la risposta del servizio';
    if (args.chiusa) return 'partita gia’ chiusa da te: non c’e’ altro da chiudere';
    if (args.posizioniVive <= 0) return 'nessuna posizione viva del bot su questa partita';
    return null;
}

/** `null` = si puo' premere «Riprendi». */
export function motivoRiprendiSpento(args: {
    eventId: string | null | undefined;
    chiusa: boolean;
    inCorso?: boolean;
}): string | null {
    if (!testo(args.eventId)) return 'partita senza identificativo: non si puo’ chiedere niente al servizio';
    if (args.inCorso) return 'richiesta gia’ in corso: si aspetta la risposta del servizio';
    if (!args.chiusa) return 'la partita non e’ marcata come chiusa da te: non c’e’ niente da riprendere';
    return null;
}
