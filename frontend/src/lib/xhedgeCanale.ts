// ============================================================================
// xhedgeCanale.ts - 25/09 (voce 12 dell'audit tempo reale): l'analisi
// cross-market (`betfair_live_xhedge`) dal canale del runner calcio (47331)
// come SOVRAPPOSIZIONE del poll di 5 s di `XHedgePanel`.
//
// Messaggio VERO: `Betfair/stream/xhedge_worker.py` (dopo l'upsert riuscito)
// -> `canale_bot.pubblica_scritte(TOPIC["betfair_live_xhedge"], res)`:
//   {"t": "betfair_live_xhedge", "d": <riga restituita dalla scrittura> + busta}
//   riga  = {id, event_id, mode, analysis, updated_at} (migrations/betfair_live_xhedge.sql)
//   busta = {fonte: "canale", _seq, _pubblicato_ms} (canale_bot.busta)
//
// Le regole, come `righeCanale.ts` / `canaleRunner.ts` ("overlay sul poll, mai
// unione"):
//  - QUALI righe esistono lo dice il poll (`get_live_xhedge`): una riga del
//    canale per (evento, modo) che il poll non ha non si mostra;
//  - il canale vince solo se il SUO `updated_at` (scritto dal worker, lo stesso
//    che finisce nella tabella) e' strettamente piu' recente; a parita' vince
//    il database; fra due messaggi del canale vince il piu' recente;
//  - la guardia "analisi fresca" del pannello (30 s su `updated_at`) resta
//    identica: il canale porta lo stesso `updated_at` del worker.
//
// Modulo PURO: nessun import di rete, nessun React.
// ============================================================================
import type { XhedgeRow } from '@/lib/liveOrders';
import { leggiMessaggioRiga } from '@/lib/righeCanale';
import { istanteMicro } from '@/lib/canaleRunner';

export const TOPIC_XHEDGE = 'betfair_live_xhedge';

/** chiave (evento, modo): la stessa dell'indice unico della tabella */
export function chiaveXhedge(r: { event_id: string; mode: string }): string {
    return `${r.event_id}|${r.mode}`;
}

/** Una riga del canale con il suo istante di ricezione (per l'eta'). */
export interface XhedgeCanale {
    riga: XhedgeRow;
    ricevutoMs: number;
}

export type SovrapposizioniXhedge = ReadonlyMap<string, XhedgeCanale>;

/**
 * Valida un push `betfair_live_xhedge`. `null` (si ignora) se: busta assente
 * o storta, evento non stringa, modo non paper/live (mai mescolare i modi),
 * analisi non oggetto, `updated_at` non leggibile.
 */
export function leggiPushXhedge(d: unknown): XhedgeRow | null {
    const msg = leggiMessaggioRiga(d);
    if (!msg) return null;
    const r = msg.riga;
    if (typeof r.event_id !== 'string' || !r.event_id) return null;
    if (r.mode !== 'paper' && r.mode !== 'live') return null;
    if (!r.analysis || typeof r.analysis !== 'object' || Array.isArray(r.analysis)) return null;
    if (typeof r.updated_at !== 'string' || istanteMicro(r.updated_at) == null) return null;
    return r as unknown as XhedgeRow;
}

/**
 * Applica UN push. Ritorna `prev` (stesso riferimento) quando si scarta:
 * riga (evento, modo) che il database non ha, non piu' recente della riga del
 * database, non piu' recente della sovrapposizione gia' tenuta.
 */
export function applicaPushXhedge(
    prev: SovrapposizioniXhedge, righeDb: readonly XhedgeRow[], push: XhedgeRow, ricevutoMs: number,
): SovrapposizioniXhedge {
    const k = chiaveXhedge(push);
    const db = righeDb.find((r) => chiaveXhedge(r) === k);
    if (!db) return prev;
    const tPush = istanteMicro(push.updated_at);
    const tDb = istanteMicro(db.updated_at);
    if (tPush == null || (tDb != null && !(tPush > tDb))) return prev;
    const gia = prev.get(k);
    if (gia) {
        const tGia = istanteMicro(gia.riga.updated_at);
        if (tGia != null && !(tPush > tGia)) return prev;
    }
    const out = new Map(prev);
    out.set(k, { riga: push, ricevutoMs });
    return out;
}

/** Al blocco nuovo del database: si tengono solo le sovrapposizioni di righe
 *  ancora presenti e ancora piu' recenti del database. */
export function potaXhedge(
    prev: SovrapposizioniXhedge, righeDb: readonly XhedgeRow[],
): SovrapposizioniXhedge {
    if (prev.size === 0) return prev;
    const out = new Map<string, XhedgeCanale>();
    for (const r of righeDb) {
        const k = chiaveXhedge(r);
        const s = prev.get(k);
        if (!s) continue;
        const tS = istanteMicro(s.riga.updated_at);
        const tDb = istanteMicro(r.updated_at);
        if (tS != null && (tDb == null || tS > tDb)) out.set(k, s);
    }
    return out.size === prev.size ? prev : out;
}

/** Le righe da mostrare: quelle del database, con sopra quelle del canale piu'
 *  recenti. Senza sovrapposizioni: LO STESSO array. */
export function vistaXhedge(
    righeDb: XhedgeRow[], sovr: SovrapposizioniXhedge,
): XhedgeRow[] {
    if (sovr.size === 0) return righeDb;
    return righeDb.map((r) => sovr.get(chiaveXhedge(r))?.riga ?? r);
}
