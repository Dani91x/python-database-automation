// ============================================================================
// ordiniCanale.ts - 25/09 (voce 13 dell'audit tempo reale): il topic `order`
// dei RUNNER come sovrapposizione del poll degli ordini dei pannelli fuori
// dalla Control Room (LiveTradingPanel 3 s, TerminalPositionsRail 4 s).
// Gemello di `canaleRunner.ts` (posizioni): stesse regole, altra chiave.
//
// Messaggio VERO (`{"t": "order", "d": ...}`):
//   Betfair/stream/db.py:535-552 `upsert_live_order`: d = la riga di
//   `live_trading_strategy._order_row` (engine/live_trading_strategy.py:324-347)
//   + `updated_at` (isoformat UTC, microsecondi), la STESSA che poi va in upsert
//   su `betfair_live_orders` con chiave UNICA (mode, client_order_ref). Niente
//   `id` (lo assegna il database). Il push parte PRIMA della scrittura.
//
// Regole ("overlay sul poll, mai unione"):
//  - le RIGHE le decide il poll: un ordine che il poll non ha non si aggiunge;
//  - il canale sovrappone le colonne che cambiano nella vita dell'ordine
//    (abbinato, residuo, stato...) SOLO se il suo `updated_at` e' strettamente
//    piu' recente di quello della riga del poll; fra due push vince il piu'
//    recente; mode e chiave non si toccano mai (paper e live non si mischiano);
//  - canale muto: la vista e' IDENTICA al poll (stesso array).
//
// Modulo PURO: nessun import di rete, nessun React.
// ============================================================================
import type { LiveOrderRow } from '@/lib/liveOrders';
import { istanteMicro } from '@/lib/canaleRunner';

/** le colonne che il canale puo' sovrapporre (quelle che vivono con l'ordine) */
export const CAMPI_ORDINE = [
    'bet_id', 'status', 'size_matched', 'size_remaining', 'size_cancelled',
    'size_lapsed', 'size_voided', 'average_price_matched', 'matched_at',
] as const;

export interface PushOrdine {
    chiave: string;
    valori: Partial<Pick<LiveOrderRow, typeof CAMPI_ORDINE[number]>>;
    updated_at: string;
    us: number;
}

export type SovrapposizioniOrdini = ReadonlyMap<string, PushOrdine>;

export function chiaveOrdine(mode: string, ref: string): string {
    return `${mode}|${ref}`;
}

/** `null` (si ignora) se: modo non paper/live, `client_order_ref` assente,
 *  `updated_at` non leggibile, colonne numeriche non finite. */
export function leggiPushOrdine(d: unknown): PushOrdine | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    if (o.mode !== 'paper' && o.mode !== 'live') return null;
    if (typeof o.client_order_ref !== 'string' || !o.client_order_ref) return null;
    if (typeof o.updated_at !== 'string') return null;
    const us = istanteMicro(o.updated_at);
    if (us == null) return null;
    const valori: Record<string, unknown> = {};
    for (const c of CAMPI_ORDINE) {
        if (!(c in o)) continue;
        const v = o[c];
        if (c.startsWith('size_') || c === 'average_price_matched') {
            if (typeof v !== 'number' || !Number.isFinite(v)) return null;
        }
        valori[c] = v;
    }
    return {
        chiave: chiaveOrdine(o.mode, o.client_order_ref),
        valori: valori as PushOrdine['valori'],
        updated_at: o.updated_at,
        us,
    };
}

function chiaveDiRiga(r: LiveOrderRow): string | null {
    return r.client_order_ref ? chiaveOrdine(r.mode, r.client_order_ref) : null;
}

function piuFresco(p: PushOrdine, r: LiveOrderRow): boolean {
    const t = istanteMicro(r.updated_at);
    return t == null || p.us > t;
}

/** Applica UN push; `prev` (stesso riferimento) quando si scarta. */
export function applicaPushOrdine(
    prev: SovrapposizioniOrdini, righeDb: readonly LiveOrderRow[], p: PushOrdine,
): SovrapposizioniOrdini {
    const r = righeDb.find((x) => chiaveDiRiga(x) === p.chiave);
    if (!r || !piuFresco(p, r)) return prev;
    const gia = prev.get(p.chiave);
    if (gia && !(p.us > gia.us)) return prev;
    const out = new Map(prev);
    out.set(p.chiave, p);
    return out;
}

/** Al poll nuovo: restano solo le sovrapposizioni di righe presenti e ancora
 *  piu' fresche del poll. */
export function potaOrdini(
    prev: SovrapposizioniOrdini, righeDb: readonly LiveOrderRow[],
): SovrapposizioniOrdini {
    if (prev.size === 0) return prev;
    const out = new Map<string, PushOrdine>();
    for (const r of righeDb) {
        const k = chiaveDiRiga(r);
        const p = k == null ? undefined : prev.get(k);
        if (p && piuFresco(p, r)) out.set(p.chiave, p);
    }
    return out.size === prev.size ? prev : out;
}

/** Le righe da mostrare. Senza sovrapposizioni: LO STESSO array. */
export function vistaOrdini(
    righeDb: LiveOrderRow[], sovr: SovrapposizioniOrdini,
): LiveOrderRow[] {
    if (sovr.size === 0) return righeDb;
    let cambiato = false;
    const out = righeDb.map((r) => {
        const k = chiaveDiRiga(r);
        const p = k == null ? undefined : sovr.get(k);
        if (!p || !piuFresco(p, r)) return r;
        cambiato = true;
        return { ...r, ...p.valori, updated_at: p.updated_at };
    });
    return cambiato ? out : righeDb;
}
