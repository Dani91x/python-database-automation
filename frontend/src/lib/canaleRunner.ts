// ============================================================================
// canaleRunner.ts - 23/09: i topic `now` e `position` dei RUNNER (calcio 47331,
// tennis 47332) come sovrapposizione del poll/realtime del database, per le
// pagine che finora li leggevano solo dal database (MarketWatch, e le
// posizioni dell'evento di SeguiLive).
//
// Formato dei messaggi (copiato dai produttori, busta di local_channel.py
// `{"t": topic, "d": payload}`):
//
//   now      <- Betfair/stream/db.py::update_live_now (calcio) e
//               Betfair/stream/tennis_live/tennis_db.py::update_tennis_live_now:
//               d = la STESSA riga che poi va in upsert su live_now /
//               tennis_live_now, `updated_at` = datetime.now(utc).isoformat()
//               del produttore. Il push parte PRIMA della scrittura cloud.
//   position <- db.py::upsert_live_position e tennis_db.py::upsert_tennis_position:
//               d = {mode, event_id, market_id, selection_id, handicap,
//                    matched_if_win, matched_if_lose, worst_if_win,
//                    worst_if_lose, selection_exposure, unmatched_back_exposure,
//                    unmatched_lay_exposure, net_position, updated_at}
//               (niente `id`: lo assegna il database). Chiave di upsert del
//               produttore: (mode, market_id, selection_id, handicap).
//
// Lo stesso contratto di righeCanale.ts ("overlay sul poll, mai unione"):
//  - le RIGHE esistenti le decide SOLO il blocco del database: il canale non
//    aggiunge una posizione che il database non ha, e una riga assente dal
//    blocco nuovo sparisce;
//  - il canale sovrappone le colonne di una riga nota SOLO se piu' fresco:
//    freschezza = `updated_at` del PRODUTTORE (lo stesso valore finisce nella
//    riga del database, perche' il push e la upsert portano lo stesso payload).
//    canale vs database: vince il canale solo se strettamente piu' recente; a
//    parita' vince il database. canale vs canale: vince il piu' recente, a
//    parita' l'ultimo arrivato (stesso socket, ordine conservato).
//  - canale muto: la vista e' IDENTICA al blocco del database (stesso array).
//
// Modulo PURO: nessun import di rete, nessun React.
// ============================================================================
import type { LiveOrderMode, LivePositionRow } from '@/lib/liveOrders';

/** Le colonne numeriche della posizione che il canale puo' sovrapporre. */
export const CAMPI_POSIZIONE = [
    'matched_if_win', 'matched_if_lose', 'worst_if_win', 'worst_if_lose',
    'selection_exposure', 'unmatched_back_exposure', 'unmatched_lay_exposure',
    'net_position',
] as const;
export type CampoPosizione = typeof CAMPI_POSIZIONE[number];

/**
 * Istante ISO -> microsecondi epoch (null se non leggibile). I microsecondi
 * contano: Python `isoformat()` e Postgres li scrivono entrambi, Date.parse
 * li tronca al millisecondo e due scritture nello stesso ms risulterebbero
 * pari. Senza frazione (microsecondi = 0, Python la omette) vale 0.
 */
export function istanteMicro(iso: string | null | undefined): number | null {
    if (typeof iso !== 'string' || !iso) return null;
    const m = /^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$/.exec(iso.trim());
    if (!m) return null;
    const base = Date.parse(`${m[1].replace(' ', 'T')}${m[3] ?? ''}`);
    if (!Number.isFinite(base)) return null;
    const frazione = (m[2] ?? '').slice(0, 6).padEnd(6, '0');
    return base * 1000 + Number(frazione);
}

// ------------------------------------------------------------------ now
/** Riga `now` minima (live_now calcio o tennis_live_now). */
export interface RigaNow {
    event_id: string;
    updated_at: string | null;
}

/**
 * Valida un push `now`: oggetto con `event_id` stringa non vuota. `null` =
 * non e' una riga now, si ignora. Il tipo concreto (calcio/tennis) lo decide
 * la porta da cui arriva: ogni pagina si abbona al canale del proprio sport.
 */
export function leggiPushNow<T extends RigaNow>(d: unknown): T | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    if (typeof o.event_id !== 'string' || !o.event_id) return null;
    return o as unknown as T;
}

/**
 * "Il piu' recente vince" fra la riga now che la pagina ha e una nuova
 * (dal canale o dal database). Senza `updated_at` confrontabile si accetta la
 * nuova (come prima: mai bloccarsi su un dato vecchio); a parita' vince la
 * nuova (stessa scrittura, stesso contenuto).
 */
export function nowPiuRecente<T extends RigaNow>(prev: T | null | undefined, next: T): T {
    if (!prev) return next;
    const a = istanteMicro(prev.updated_at);
    const b = istanteMicro(next.updated_at);
    if (a == null || b == null) return next;
    return b >= a ? next : prev;
}

// ------------------------------------------------------------- position
/** Un push `position` gia' validato. */
export interface PushPosizione {
    chiave: string;
    mode: LiveOrderMode;
    event_id: string | null;
    market_id: string;
    valori: Record<CampoPosizione, number>;
    updated_at: string;
    /** istanteMicro(updated_at) */
    us: number;
}

/** Chiave composta, la stessa della upsert del produttore. */
export function chiavePosizione(
    mode: string, marketId: string, selectionId: number, handicap: number | null | undefined,
): string {
    return `${mode}|${marketId}|${selectionId}|${Number(handicap ?? 0)}`;
}

function chiaveDiRiga(r: LivePositionRow): string {
    return chiavePosizione(r.mode, r.market_id, r.selection_id, r.handicap);
}

/**
 * Valida un push `position`. `null` (si ignora, non si indovina) se: mode non
 * paper/live (MAI mescolare i modi), mercato mancante, selezione non intera,
 * una colonna numerica non finita, `updated_at` non leggibile.
 */
export function leggiPushPosizione(d: unknown): PushPosizione | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    const mode = o.mode;
    if (mode !== 'paper' && mode !== 'live') return null;
    if (typeof o.market_id !== 'string' || !o.market_id) return null;
    const sel = o.selection_id;
    if (typeof sel !== 'number' || !Number.isInteger(sel)) return null;
    const hc = o.handicap == null ? 0 : o.handicap;
    if (typeof hc !== 'number' || !Number.isFinite(hc)) return null;
    if (typeof o.updated_at !== 'string') return null;
    const us = istanteMicro(o.updated_at);
    if (us == null) return null;
    const valori = {} as Record<CampoPosizione, number>;
    for (const c of CAMPI_POSIZIONE) {
        const v = o[c];
        if (typeof v !== 'number' || !Number.isFinite(v)) return null;
        valori[c] = v;
    }
    return {
        chiave: chiavePosizione(mode, o.market_id, sel, hc),
        mode,
        event_id: typeof o.event_id === 'string' ? o.event_id : null,
        market_id: o.market_id,
        valori,
        updated_at: o.updated_at,
        us,
    };
}

/** Sovrapposizioni del canale per chiave (vuota = canale muto). */
export type SovrapposizioniPos = ReadonlyMap<string, PushPosizione>;

/** Il canale e' piu' fresco della riga del database? (a parita': no) */
function piuFrescoDelDb(p: PushPosizione, r: LivePositionRow): boolean {
    const dbUs = istanteMicro(r.updated_at);
    // riga del database senza istante leggibile: il push del produttore ha
    // un istante vero, quindi e' la notizia piu' nuova che la pagina ha.
    return dbUs == null || p.us > dbUs;
}

/**
 * Applica UN push `position`. Ritorna `prev` (stesso riferimento: nessun
 * render) quando si scarta: riga sconosciuta al database, non piu' fresco
 * della riga del database, piu' vecchio della sovrapposizione gia' tenuta.
 */
export function applicaPushPosizione(
    prev: SovrapposizioniPos, righeDb: Iterable<LivePositionRow>, p: PushPosizione,
): SovrapposizioniPos {
    let riga: LivePositionRow | null = null;
    for (const r of righeDb) {
        if (chiaveDiRiga(r) === p.chiave) { riga = r; break; }
    }
    if (riga == null) return prev;
    if (!piuFrescoDelDb(p, riga)) return prev;
    const tenuta = prev.get(p.chiave);
    if (tenuta != null && p.us < tenuta.us) return prev;
    const out = new Map(prev);
    out.set(p.chiave, p);
    return out;
}

/**
 * All'arrivo di un blocco del database: tiene solo le sovrapposizioni di righe
 * ancora presenti e ancora piu' fresche del blocco. Stesso riferimento se non
 * cambia niente.
 */
export function potaSovrapposizioni(
    prev: SovrapposizioniPos, righeDb: Iterable<LivePositionRow>,
): SovrapposizioniPos {
    if (prev.size === 0) return prev;
    const perChiave = new Map<string, LivePositionRow>();
    for (const r of righeDb) perChiave.set(chiaveDiRiga(r), r);
    let out: Map<string, PushPosizione> | null = null;
    for (const [k, p] of prev) {
        const r = perChiave.get(k);
        if (r != null && piuFrescoDelDb(p, r)) continue;
        if (out == null) out = new Map(prev);
        out.delete(k);
    }
    return out ?? prev;
}

/**
 * Le posizioni che la pagina mostra: le righe del database, nel loro ordine,
 * con sopra le colonne del canale dove piu' fresche. Nessuna sovrapposizione
 * applicabile: LO STESSO array (parita' col solo database).
 */
export function vistaPosizioni(
    righeDb: LivePositionRow[], sovr: SovrapposizioniPos,
): LivePositionRow[] {
    if (sovr.size === 0) return righeDb;
    let cambiato = false;
    const out = righeDb.map((r) => {
        const p = sovr.get(chiaveDiRiga(r));
        if (p == null || !piuFrescoDelDb(p, r)) return r;
        cambiato = true;
        return { ...r, ...p.valori, updated_at: p.updated_at };
    });
    return cambiato ? out : righeDb;
}
