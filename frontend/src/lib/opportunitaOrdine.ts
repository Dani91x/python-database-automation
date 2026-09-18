// ============================================================================
// opportunitaOrdine.ts — ordinamento e raggruppamento PURI della colonna
// «Opportunità di modello» (Task 4, 18/09). L'utente non vuole un tetto al
// numero di schede: vuole che la sezione sia ORGANIZZATA.
//
// REGOLA DI STABILITÀ (la più importante): NESSUNA chiave di questo file
// dipende dal prezzo vivo o da un valore che cambia a ogni tick — solo da
// `id`, `eventId`, `live` (soldi veri sì/no) e da un'eventuale scadenza fissa
// (`scadeAlleMs`, quando il payload la porterà: campo opzionale, non ancora
// prodotto da nessun bot oggi). Così l'ordine cambia SOLO quando una scheda
// entra o esce dalla lista, mai perché una quota si è mossa — la scheda non
// deve mai saltare sotto il dito del trader mentre sta per cliccare.
// ============================================================================

export interface VoceOrdinabile {
    id: number;
    eventId: string | null;
    /** soldi veri (mode === 'live'); le urgenti-live vengono prima delle paper a parità di scadenza */
    live: boolean;
    /** istante (ms epoch) oltre il quale la proposta decade; null/undefined = nessuna scadenza dichiarata */
    scadeAlleMs?: number | null;
    /** istante di creazione della riga (ms epoch); null = ignoto, va in fondo a parità d'altro */
    creataAlleMs: number | null;
}

function confrontaBase(a: VoceOrdinabile, b: VoceOrdinabile): number {
    // 1) chi scade prima, prima — chi non ha scadenza va dopo chi ce l'ha
    const sa = a.scadeAlleMs ?? Number.POSITIVE_INFINITY;
    const sb = b.scadeAlleMs ?? Number.POSITIVE_INFINITY;
    if (sa !== sb) return sa - sb;

    // 2) le LIVE (soldi veri) prima delle paper, a parità di scadenza/assenza
    if (a.live !== b.live) return a.live ? -1 : 1;

    // 3) la più vecchia (creata prima) prima — un ordine di arrivo stabile
    const ca = a.creataAlleMs ?? Number.POSITIVE_INFINITY;
    const cb = b.creataAlleMs ?? Number.POSITIVE_INFINITY;
    if (ca !== cb) return ca - cb;

    // 4) pareggio assoluto: l'id, mai il caso (Array.sort non è garantito
    //    stabile in ogni motore per confronti che tornano 0 su input pari)
    return a.id - b.id;
}

/**
 * Ordina in modo stabile e deterministico. Nessuna dipendenza dal prezzo:
 * chiamarla di nuovo con lo STESSO insieme di voci (stessi id) produce
 * SEMPRE lo stesso ordine, qualunque sia il prezzo vivo nel frattempo.
 */
export function ordinaOpportunitaStabile<T extends VoceOrdinabile>(voci: readonly T[]): T[] {
    return [...voci].sort(confrontaBase);
}

export interface GruppoOpportunita<T> {
    /** null = partite/voci senza un evento noto (es. combinazioni multi-evento) */
    eventId: string | null;
    voci: T[];
}

/**
 * Raggruppa per partita PRESERVANDO l'ordine di `ordinaOpportunitaStabile`:
 * un gruppo appare nella posizione della sua voce più prioritaria (la prima
 * che si incontra scorrendo l'elenco già ordinato), le voci successive dello
 * stesso evento restano appese a quel gruppo invece di formarne uno nuovo più
 * in basso. Le combinazioni multi-evento (`eventId: null`) restano ognuna un
 * gruppo a sé: raggrupparle per "null" le fonderebbe fra loro, cosa falsa.
 */
export function raggruppaPerPartita<T extends VoceOrdinabile>(
    vociOrdinate: readonly T[],
): GruppoOpportunita<T>[] {
    const gruppi: GruppoOpportunita<T>[] = [];
    const indiceDiGruppo = new Map<string, number>();
    for (const v of vociOrdinate) {
        if (v.eventId == null) {
            gruppi.push({ eventId: null, voci: [v] });
            continue;
        }
        const i = indiceDiGruppo.get(v.eventId);
        if (i == null) {
            indiceDiGruppo.set(v.eventId, gruppi.length);
            gruppi.push({ eventId: v.eventId, voci: [v] });
        } else {
            gruppi[i].voci.push(v);
        }
    }
    return gruppi;
}

/** le due funzioni insieme: quello che la colonna chiama davvero. */
export function organizzaOpportunita<T extends VoceOrdinabile>(
    voci: readonly T[],
): GruppoOpportunita<T>[] {
    return raggruppaPerPartita(ordinaOpportunitaStabile(voci));
}
