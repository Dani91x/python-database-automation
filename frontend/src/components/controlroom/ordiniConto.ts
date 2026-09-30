// ============================================================================
// ordiniConto.ts - P14 (30/09): gli ordini del CONTO fuori dai bot, per partita.
//
// Stasera su FC Vsetin l'utente ha puntato Over 3,5 e Under 4,5 dal sito:
// sul conto la partita era chiusa (rischio 0,15), Mike credeva 6,42 e il suo
// cash out non vedeva quegli ordini. Da qui la pagina li mostra per partita.
//
// Fonte: RPC `get_live_orders_account_open()` (contratto concordato 30/09):
// `{ rows: [{ bet_id, market_id, selection_id, event_id, event_name,
// market_name, selection_name, side: 'BACK'|'LAY', price_matched,
// size_matched, size_remaining, status, source, placed_at }], letto_at }`,
// solo live, solo ordini NON dei bot, solo mercati non regolati.
// Letta nel giro dei 30 s della pagina (nessun poll nuovo). Se la RPC non
// esiste ancora (migrazione non applicata) o fallisce: "non letti", MAI
// "nessun ordine".
// ============================================================================
import type { OrdineContoFuoriBot } from '@/lib/liveOrders';

export interface OrdiniContoStato {
    /** 'letti' = risposta valida della RPC; 'non-letti' = mai letti o errore */
    stato: 'letti' | 'non-letti';
    /** perche' non letti (per lo schermo) */
    motivo: string | null;
    /** istante della lettura dichiarato dalla RPC (`letto_at`) */
    lettoAt: string | null;
    /** ordini per event_id */
    perEvento: Map<string, OrdineContoFuoriBot[]>;
    /** ordini senza event_id (la RPC non ha saputo dire la partita) */
    senzaEvento: OrdineContoFuoriBot[];
}

export const ORDINI_CONTO_NON_LETTI: OrdiniContoStato = {
    stato: 'non-letti', motivo: 'non ancora letti', lettoAt: null, perEvento: new Map(), senzaEvento: [],
};

export function raggruppaOrdiniConto(righe: readonly OrdineContoFuoriBot[], lettoAt: string | null): OrdiniContoStato {
    const perEvento = new Map<string, OrdineContoFuoriBot[]>();
    const senzaEvento: OrdineContoFuoriBot[] = [];
    for (const r of righe) {
        if (r.event_id == null || r.event_id === '') { senzaEvento.push(r); continue; }
        const k = String(r.event_id);
        perEvento.set(k, [...(perEvento.get(k) ?? []), r]);
    }
    return { stato: 'letti', motivo: null, lettoAt, perEvento, senzaEvento };
}

/** Il motivo a schermo di una lettura fallita: la RPC che non c'e' ancora si dice. */
export function motivoNonLetti(errore: unknown): string {
    const m = errore instanceof Error ? errore.message : String(errore ?? '');
    if (/get_live_orders_account_open|does not exist|PGRST202|404|Could not find the function/i.test(m)) {
        return 'RPC non disponibile';
    }
    return m ? `lettura fallita: ${m.slice(0, 120)}` : 'lettura fallita';
}

/** Le partite con ordini fuori dai bot, coi loro nomi (per la testata). */
export function partiteConOrdiniFuori(s: OrdiniContoStato): { n: number; nomi: string[] } {
    const nomi: string[] = [];
    for (const [id, righe] of s.perEvento) nomi.push(righe.find((r) => r.event_name)?.event_name ?? id);
    return { n: s.perEvento.size, nomi };
}
