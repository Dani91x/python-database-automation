// ============================================================================
// comboPrezzoVivo.ts — PREZZO VIVO PER GAMBA di una proposta COMBO.
//
// Oggi (18/09) le proposte di opportunità hanno UN market_id/selection_id in
// cima al payload (`PropostaOpportunitaPayload`, `lib/safeBot.ts`) e
// `prezzoVivo()` (`lib/controlRoomProposte.ts`) lo risolve su UN payload di
// evento. Le proposte COMBO in arrivo da un altro costruttore avranno invece
// `payload.legs[]` (una gamba = market_id/market_type/selection_id/side/
// price/size) e `payload.combo_id`, SENZA market/selection in cima.
//
// Questo file calcola il prezzo vivo di OGNI gamba dagli STESSI dati già in
// memoria (il feed scanner realtime, `righeFeed`/`feedPerEvento` di
// `useControlRoom.ts`): nessuna lettura nuova. Una gamba può appartenere a un
// evento diverso dalle altre (non porta un `event_id` proprio): si cerca il
// mercato fra TUTTI i payload della giornata già caricati.
//
// Tipi OPZIONALI apposta: finché la scheda combo non è su master, nessun
// consumatore esiste ancora — questo file può essere importato e testato da
// solo, senza rompere nulla di ciò che gira oggi.
// ============================================================================
import { prezzoVivo, type PrezzoVivo } from './controlRoomProposte';
import type { CalcioScanPayload, TennisScanPayload } from './safeStrategyScan';

export type LatoOrdine = 'back' | 'lay';

/** una gamba di una proposta combo — stesse chiavi del contratto dichiarato
 *  dal costruttore del backend (market_id/market_type/selection_id/side/
 *  price/size), tutte opzionali: un contratto ancora in arrivo non deve far
 *  esplodere questo file se manca un campo. */
export interface GambaCombo {
    market_id?: string | null;
    market_type?: string | null;
    selection_id?: number | null;
    side?: LatoOrdine | string | null;
    price?: number | null;
    size?: number | null;
}

type PayloadFeed = CalcioScanPayload | TennisScanPayload;

function normalizzaLato(side: GambaCombo['side']): LatoOrdine | null {
    return side === 'back' || side === 'lay' ? side : null;
}

/**
 * Prezzo vivo di UNA gamba: cerca il suo `market_id`/`selection_id` in TUTTI
 * i payload passati (uno per evento della giornata) e prende il primo che
 * risolve un prezzo. Nessun mercato trovato → `{ prezzo: null, ... }`, MAI un
 * ripiego inventato — la stessa regola di `prezzoVivo` per il caso singolo.
 */
export function prezzoVivoGamba(
    gamba: GambaCombo | null | undefined,
    payloads: readonly (PayloadFeed | null | undefined)[],
): PrezzoVivo {
    const vuoto: PrezzoVivo = { prezzo: null, abbinabile: null, statoMercato: null };
    if (!gamba) return vuoto;
    const lato = normalizzaLato(gamba.side);
    if (!lato || !gamba.market_id) return vuoto;
    for (const payload of payloads) {
        if (!payload) continue;
        const v = prezzoVivo(payload, gamba.market_id, gamba.selection_id ?? null, lato);
        if (v.prezzo != null) return v;
    }
    return vuoto;
}

/**
 * Prezzo vivo per OGNI gamba, nello stesso ordine dell'array di ingresso:
 * la scheda potrà indicizzare `prezzi[i]` per la gamba `legs[i]`.
 */
export function prezzoVivoPerGamba(
    legs: readonly GambaCombo[] | null | undefined,
    payloads: readonly (PayloadFeed | null | undefined)[],
): PrezzoVivo[] {
    if (!legs || !legs.length) return [];
    return legs.map((g) => prezzoVivoGamba(g, payloads));
}
