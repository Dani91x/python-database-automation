// ============================================================================
// scanEventBuffer.ts — riduzione PURA di una RAFFICA di eventi realtime dello
// scanner in UN solo aggiornamento (Task 6, 18/09: "un commit per frame, non
// uno per messaggio").
//
// Questa funzione è ESATTAMENTE la stessa logica che oggi vive dentro il
// callback di `subscribeScanRows` in `useControlRoom.ts` (upsert per
// event_id, rimozione su `delete`), estratta per essere applicata a un LOTTO
// di eventi in un colpo solo invece che a uno alla volta: stesso risultato
// finale, un solo `setState` invece di N. Nessuna lettura nuova, nessuna
// perdita di eventi: il lotto si applica IN ORDINE di arrivo.
// ============================================================================

export interface ScanRowLike { event_id: string }
export type ScanRowEvent<R extends ScanRowLike> =
    | { type: 'upsert'; row: R }
    | { type: 'delete'; eventId: string };

/** Applica UN evento a una lista (stessa semantica di prima: upsert in
 *  posizione, o append se nuovo; delete filtra via). */
export function applicaEventoScan<R extends ScanRowLike>(
    lista: readonly R[], ev: ScanRowEvent<R>,
): R[] {
    if (ev.type === 'delete') return lista.filter((r) => r.event_id !== ev.eventId);
    const i = lista.findIndex((r) => r.event_id === ev.row.event_id);
    if (i < 0) return [...lista, ev.row];
    const next = lista.slice();
    next[i] = ev.row;
    return next;
}

/** Applica un LOTTO di eventi, in ordine, con UNA sola riduzione: il
 *  risultato è identico ad applicarli uno a uno, ma il chiamante fa UN solo
 *  `setState` invece di uno per evento. */
export function applicaLottoScan<R extends ScanRowLike>(
    lista: readonly R[], lotto: readonly ScanRowEvent<R>[],
): R[] {
    return lotto.reduce<R[]>((acc, ev) => applicaEventoScan(acc, ev), [...lista]);
}
