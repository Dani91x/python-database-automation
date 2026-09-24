// ============================================================================
// righeCanale.ts - C6 b (23/09): LA MAPPA PER RIGA di Omega, Safe e Mike.
//
// Prima la Control Room vedeva le righe dei bot (posizioni e proposte) SOLO dai
// blocchi RPC del giro di 30 s. I bot pubblicano pero' la STESSA riga, appena
// scritta, sul loro canale locale (F3, `Betfair/stream/canale_bot.py`):
//
//   push {"t": "<topic>", "d": <riga del database> + busta}
//   busta = {"fonte": "canale", "_seq": <int monotono del processo>,
//            "_pubblicato_ms": <int, ms epoch del produttore>}
//   topic: mike_posizioni (47333) - omega_posizioni, omega_proposta (47334) -
//          safe_posizioni_calcio, safe_posizioni_tennis, safe_proposta (47335)
//
// Questo modulo PURO (nessun import di rete, nessun React) tiene una mappa
// chiave composta (bot, id) -> voce, e la alimenta da DUE parti:
//
//  1. il BLOCCO del database (RPC/SELECT del giro, o la rilettura delle
//     proposte): dice QUALI righe esistono. Una riga assente dal blocco nuovo
//     SPARISCE, anche se il canale ne aveva parlato. Il canale non puo' mai
//     AGGIUNGERE una riga (contratto F3 par. 7: "overlay sul poll, mai unione").
//  2. il MESSAGGIO del canale: sovrappone le colonne di una riga GIA' nota,
//     SOLO se e' piu' fresco di cio' che la pagina ha gia'.
//
// LA FRESCHEZZA (le tre regole, ciascuna inchiodata da un test):
//  - canale vs database: il messaggio esce DOPO la scrittura riuscita. Una
//    lettura del database INIZIATA all'istante T vede quindi ogni riga
//    pubblicata prima di T. Il messaggio vince solo se `_pubblicato_ms > T`;
//    a parita' vince il database (F3 par. 7).
//  - database vs canale: all'arrivo di un blocco letto da T, la
//    sovrapposizione resta solo se `_pubblicato_ms > T`; altrimenti il blocco
//    la contiene gia' e la sovrapposizione si butta.
//  - canale vs canale: vince (`_pubblicato_ms`, `_seq`) maggiore in ordine
//    lessicografico. Il solo `_seq` non basta: al riavvio del processo riparte
//    da 1 e scarterebbe per sempre i messaggi nuovi. Un orologio che torna
//    indietro al massimo ritarda una riga fino al giro di 30 s successivo.
//
// PARITA': con il canale muto la mappa restituisce ESATTAMENTE le righe del
// blocco, stessi oggetti (stesso riferimento) e stesso ordine: la pagina rende
// identica a prima. Il canale e' un'accelerazione, mai l'unica fonte.
// ============================================================================
import type { Bot } from '@/lib/controlRoom';

/** Le sole chiavi che il messaggio ha in piu' della riga (`canale_bot.CHIAVI_META`). */
export const CHIAVI_BUSTA: readonly string[] = ['fonte', '_seq', '_pubblicato_ms'] as const;

/** Da dove viene quello che la pagina mostra di una riga. */
export type FonteRiga = 'locale' | 'database';

/** Un messaggio del canale gia' validato, con la busta tolta. */
export interface MessaggioRiga {
    /** la chiave della riga: `id` numerico, o (24/09) la colonna chiave
     *  dichiarata dal chiamante, es. `bot_key` di `tennis_bot_service_control` */
    id: number | string;
    /** `_pubblicato_ms` del produttore */
    ms: number;
    /** `_seq` del produttore */
    seq: number;
    /** la riga del database, senza le chiavi della busta */
    riga: Record<string, unknown>;
}

export interface VoceRiga<T> {
    bot: Bot;
    /** l'ultima riga arrivata dal database */
    db: T;
    /** istante (ms, orologio della pagina) in cui e' INIZIATA la lettura del blocco */
    dbMs: number;
    /** colonne dal canale, piu' fresche di `db`; null = nessuna sovrapposizione */
    canale: Record<string, unknown> | null;
    canaleMs: number | null;
    canaleSeq: number | null;
    /** quando la pagina ha ricevuto il messaggio che ha sovrapposto (per l'eta') */
    ricevutoMs: number | null;
}

export interface MappaRighe<T> {
    voci: ReadonlyMap<string, VoceRiga<T>>;
    /** per bot: inizio dell'ultima lettura del database applicata */
    lettoDbMs: Readonly<Partial<Record<Bot, number>>>;
}

/** La mappa vuota: la pagina appena aperta, prima di ogni lettura. */
export function mappaVuota<T>(): MappaRighe<T> {
    return { voci: new Map(), lettoDbMs: {} };
}

/**
 * CHIAVE COMPOSTA bot+id. `omega_trades`, `safe_strategy_trades`,
 * `mike_trades` (e le rispettive code delle proposte) hanno sequenze PK
 * INDIPENDENTI: sull'id nudo la riga 7 di Safe sovrascriverebbe la riga 7 di
 * Omega. E' lo stesso rischio che `OFFSET_BOT` chiude in `soldiPerPartita`.
 */
export function chiaveRiga(bot: Bot, id: number | string): string {
    return `${bot}#${String(id)}`;
}

/**
 * Valida un push del canale. `null` = non e' una riga (busta mancante o
 * storta, id non numerico): si ignora, non si indovina.
 *
 * 24/09 - `campoChiave`: per le tabelle senza `id` numerico (la riga di
 * `tennis_bot_service_control` ha per chiave `bot_key`) la chiave e' quella
 * colonna, stringa non vuota. Di serie resta `id` numerico, come prima.
 */
export function leggiMessaggioRiga(bruto: unknown, campoChiave: string = 'id'): MessaggioRiga | null {
    if (!bruto || typeof bruto !== 'object' || Array.isArray(bruto)) return null;
    const o = bruto as Record<string, unknown>;
    if (o.fonte !== 'canale') return null;
    const id = o[campoChiave];
    const ms = o._pubblicato_ms;
    const seq = o._seq;
    const chiaveValida = campoChiave === 'id'
        ? typeof id === 'number' && Number.isFinite(id)
        : typeof id === 'string' && id.trim() !== '';
    if (!chiaveValida) return null;
    if (typeof ms !== 'number' || !Number.isFinite(ms)) return null;
    if (typeof seq !== 'number' || !Number.isFinite(seq)) return null;
    const riga: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(o)) {
        if (!CHIAVI_BUSTA.includes(k)) riga[k] = v;
    }
    return { id: id as number | string, ms, seq, riga };
}

/**
 * Applica un BLOCCO del database per UN bot, letto a partire da `lettoMs`.
 *
 * - le righe del bot sono ESATTAMENTE quelle del blocco, nel suo ordine
 *   (una riga assente sparisce);
 * - una sovrapposizione del canale resta solo se piu' fresca della lettura;
 * - le righe degli altri bot non si toccano.
 *
 * L'ultimo blocco applicato vince, come prima di questo modulo: l'ordine fra
 * letture sovrapposte lo governa chi chiama (`giroCorrente` nel hook).
 *
 * 24/09 - `chiaveDi`: la colonna chiave per le righe senza `id` numerico
 * (`bot_key` degli interruttori tennis). Di serie `r.id`, come prima.
 */
export function applicaBloccoDb<T>(
    prev: MappaRighe<T>, bot: Bot, righe: readonly T[], lettoMs: number,
    chiaveDi: (r: T) => number | string = (r) => (r as unknown as { id: number }).id,
): MappaRighe<T> {
    const voci = new Map<string, VoceRiga<T>>();
    for (const [k, v] of prev.voci) {
        if (v.bot !== bot) voci.set(k, v);
    }
    for (const r of righe) {
        const k = chiaveRiga(bot, chiaveDi(r));
        const vecchia = prev.voci.get(k);
        const tieni = vecchia != null && vecchia.canale != null
            && vecchia.canaleMs != null && vecchia.canaleMs > lettoMs;
        voci.set(k, {
            bot, db: r, dbMs: lettoMs,
            canale: tieni ? vecchia.canale : null,
            canaleMs: tieni ? vecchia.canaleMs : null,
            canaleSeq: tieni ? vecchia.canaleSeq : null,
            ricevutoMs: tieni ? vecchia.ricevutoMs : null,
        });
    }
    return { voci, lettoDbMs: { ...prev.lettoDbMs, [bot]: lettoMs } };
}

/**
 * Applica UN messaggio del canale per `bot`. Ritorna `prev` (stesso
 * riferimento: nessun render) quando il messaggio si scarta:
 * - riga sconosciuta al database (il canale non aggiunge righe);
 * - non piu' fresco della lettura del database che ha portato la riga;
 * - non piu' fresco dell'ultima sovrapposizione del canale;
 * - `sportAtteso` dato e la riga dichiara un altro sport (topic sbagliato:
 *   calcio e tennis non si mischiano, fail-closed).
 */
export function applicaMessaggioCanale<T>(
    prev: MappaRighe<T>, bot: Bot, msg: MessaggioRiga, ricevutoMs: number,
    sportAtteso?: 'calcio' | 'tennis',
): MappaRighe<T> {
    if (sportAtteso != null) {
        const sp = msg.riga.sport;
        if (typeof sp === 'string' && sp.trim().toLowerCase() !== sportAtteso) return prev;
    }
    const k = chiaveRiga(bot, msg.id);
    const v = prev.voci.get(k);
    if (!v) return prev;
    if (!(msg.ms > v.dbMs)) return prev;
    if (v.canale != null && v.canaleMs != null) {
        const piuNuovo = msg.ms > v.canaleMs
            || (msg.ms === v.canaleMs && v.canaleSeq != null && msg.seq > v.canaleSeq);
        if (!piuNuovo) return prev;
    }
    const voci = new Map(prev.voci);
    voci.set(k, {
        ...v, canale: msg.riga, canaleMs: msg.ms, canaleSeq: msg.seq, ricevutoMs,
    });
    return { voci, lettoDbMs: prev.lettoDbMs };
}

/** La riga che la pagina mostra: quella del database, con sopra le colonne
 *  del canale se piu' fresche. Senza sovrapposizione: LO STESSO oggetto. */
export function vistaVoce<T>(v: VoceRiga<T>): T {
    if (v.canale == null) return v.db;
    return { ...v.db, ...v.canale } as T;
}

/** Le righe di un bot, nell'ordine del blocco del database. */
export function righeDi<T>(m: MappaRighe<T>, bot: Bot): T[] {
    const out: T[] = [];
    for (const v of m.voci.values()) {
        if (v.bot === bot) out.push(vistaVoce(v));
    }
    return out;
}

/** Eta' e fonte di UNA riga: ricezione del messaggio del canale se la
 *  sovrappone, altrimenti inizio della lettura del database. `null` = riga
 *  sconosciuta. */
export function etaRiga<T>(
    m: MappaRighe<T>, bot: Bot, id: number | string, nowMs: number,
): { fonte: FonteRiga; etaS: number } | null {
    const v = m.voci.get(chiaveRiga(bot, id));
    if (!v) return null;
    const at = v.canale != null && v.ricevutoMs != null ? v.ricevutoMs : v.dbMs;
    return {
        fonte: v.canale != null ? 'locale' : 'database',
        etaS: Math.max(0, Math.round((nowMs - at) / 1000)),
    };
}

/**
 * Per UN bot, su una o piu' mappe: l'ultima notizia del canale ACCETTATA
 * (ricezione) e l'ultima lettura del database. Serve all'indicatore di pagina
 * "righe: canale locale / database", come `fonteScan` per lo scanner.
 */
export function ultimeNotizie(
    mappe: readonly MappaRighe<unknown>[], bot: Bot,
): { canaleMs: number | null; dbMs: number | null } {
    let canaleMs: number | null = null;
    let dbMs: number | null = null;
    for (const m of mappe) {
        const d = m.lettoDbMs[bot];
        if (d != null && (dbMs == null || d > dbMs)) dbMs = d;
        for (const v of m.voci.values()) {
            if (v.bot !== bot || v.canale == null || v.ricevutoMs == null) continue;
            if (canaleMs == null || v.ricevutoMs > canaleMs) canaleMs = v.ricevutoMs;
        }
    }
    return { canaleMs, dbMs };
}

// ---------------------------------------------------------------------------
// 24/09 - QUANDO UN MESSAGGIO DEL CANALE CHIEDE UNA RILETTURA DEL DATABASE
// (decisione dell'utente: "righe nuove dei bot in Control Room subito, non al
// poll dei 30 s"). Il canale continua a NON aggiungere righe: dice solo alla
// pagina che il blocco del database di quel bot e' vecchio, e la pagina lo
// rilegge subito (`lib/rilettureMirate.ts`, anti-tempesta 2 s per bot).
// ---------------------------------------------------------------------------

/**
 * Stati TERMINALI di una riga di posizione/ordine: regolata (`won`/`lost`/
 * `void` dei tre bot calcio, `lib/eventGroups.SETTLED_STATES`), annullata o
 * decaduta (anche gli stati flumine di `tennis_live_orders`), in errore.
 * Una riga con `settled_at` valorizzato e' terminale qualunque sia lo stato.
 * `EXECUTION_COMPLETE` NON e' terminale: abbinato tutto, la posizione e' viva.
 */
const STATI_TERMINALI: ReadonlySet<string> = new Set([
    'won', 'lost', 'void', 'voided', 'cancelled', 'canceled', 'closed', 'error',
    'lapsed', 'expired',
]);

export function rigaTerminale(riga: unknown): boolean {
    if (!riga || typeof riga !== 'object') return false;
    const o = riga as Record<string, unknown>;
    if (typeof o.settled_at === 'string' && o.settled_at.trim() !== '') return true;
    return STATI_TERMINALI.has(String(o.status ?? '').trim().toLowerCase());
}

/**
 * Il messaggio chiede una rilettura del blocco del database di `bot`?
 * - riga SCONOSCIUTA alla mappa: si' (e' una posizione nuova: la porta il
 *   database, non il canale);
 * - riga nota che DIVENTA terminale col messaggio (prima non lo era): si'
 *   (una posizione chiusa: il blocco del database la dice chiusa, e con lei
 *   le righe collegate);
 * - altrimenti no: basta la sovrapposizione.
 */
export function serveRilettura<T>(m: MappaRighe<T>, bot: Bot, msg: MessaggioRiga): boolean {
    const v = m.voci.get(chiaveRiga(bot, msg.id));
    if (!v) return true;
    return rigaTerminale(msg.riga) && !rigaTerminale(vistaVoce(v));
}
