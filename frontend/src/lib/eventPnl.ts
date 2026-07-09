// ============================================================================
// eventPnl.ts — matematica PURA di MTM ed esposizione per EVENTO (D30/D33).
// Nessun I/O, nessun React: stessa aritmetica di lockedPnlAt/greenup
// (trading/greenup.py lato backend). MONEY-CRITICAL: prezzi mancanti o invalidi
// NON producono mai un numero inventato → null / conteggio `unpriced` che la UI
// DEVE mostrare.
// ============================================================================
import type { LivePositionRow } from '@/lib/liveOrders';

// Sotto questa soglia due P&L sono considerati uguali (centesimo di euro).
const FLAT_EPS = 0.01;

/**
 * MTM di UNA posizione: P&L bloccato se si greenasse ORA al prezzo opposto.
 *   locked = L + (W − L) / p   con p = best_lay se W>L (chiudo layando),
 *                                   p = best_back se W<L (chiudo backando).
 * |W−L| < 0.01 → posizione già piatta → (W+L)/2 (nessun prezzo necessario).
 * Prezzo necessario mancante/invalido (null, <=1, non finito) → null: MAI inventare.
 */
export function positionMtm(
    w: number,
    l: number,
    bestBack: number | null,
    bestLay: number | null,
): number | null {
    if (!Number.isFinite(w) || !Number.isFinite(l)) return null;
    if (Math.abs(w - l) < FLAT_EPS) return (w + l) / 2; // piatta: P&L già bloccato
    const p = w > l ? bestLay : bestBack;
    if (p == null || !Number.isFinite(p) || p <= 1) return null;
    return l + (w - l) / p; // identica a lockedPnlAt(p, w, l)
}

/**
 * MTM aggregato per evento: somma dei positionMtm delle posizioni valutabili.
 * priceMap: selection_id → { back, lay } (da live_now.state o dal book).
 * Ritorna { mtm, priced, unpriced }: `unpriced` = n. posizioni NON valutabili
 * (prezzo mancante) — la UI DEVE mostrarlo, mai nasconderlo.
 * Posizioni piatte-zero (|W| e |L| < 0.01, cioè nessuna posizione) sono ignorate.
 */
export function eventMtm(
    positions: ReadonlyArray<LivePositionRow>,
    priceMap: ReadonlyMap<number, { back: number | null; lay: number | null }>,
): { mtm: number; priced: number; unpriced: number } {
    let mtm = 0;
    let priced = 0;
    let unpriced = 0;
    for (const pos of positions) {
        const w = pos.matched_if_win;
        const l = pos.matched_if_lose;
        // nessuna posizione reale su questa selezione → ignora (né priced né unpriced).
        if (Math.abs(w) < FLAT_EPS && Math.abs(l) < FLAT_EPS) continue;
        const px = priceMap.get(pos.selection_id);
        const v = positionMtm(w, l, px?.back ?? null, px?.lay ?? null);
        if (v == null) {
            unpriced += 1;
        } else {
            mtm += v;
            priced += 1;
        }
    }
    return { mtm, priced, unpriced };
}

/**
 * Esposizione worst-case aggregata dell'evento (upper bound ONESTO):
 * Σ selection_exposure delle righe. Valori non finiti → 0 (mai NaN in UI).
 */
export function eventExposure(positions: ReadonlyArray<LivePositionRow>): number {
    let tot = 0;
    for (const pos of positions) {
        const e = pos.selection_exposure;
        if (Number.isFinite(e)) tot += e;
    }
    return tot;
}
