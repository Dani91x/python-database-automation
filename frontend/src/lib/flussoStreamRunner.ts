// Cantiere J2 (28/09/2026) — lo STREAM DI MERCATO del runner e' vivo?
//
// Il runner calcio (47331) e quello tennis (47332) pubblicano il topic
// `flusso_stream` a ogni battito (~10 s) con le chiavi fisse di
// `Betfair/stream/stream_muto.py::CHIAVI_CANALE`:
//   {ts, vivo, interrotto, motivo, eta_s, muto_da_s, mercati_fermi, episodi}
// `interrotto` = episodio dichiarato in corso (il runner non riceve messaggi,
// heartbeat compresi, da oltre 15 s): il ladder e Segui Live mostrano prezzi
// FERMI e il runner non li usa per aprire. Qui SOLO la lettura: nessuna soglia
// del segnale duplicata (la decide il runner). Modulo PURO.

export interface FlussoStreamRunner {
    ts: number;
    vivo: boolean | null;
    interrotto: boolean;
    motivo: string | null;
    etaS: number | null;
    mutoDaS: number | null;
    mercatiFermi: string[];
}

/** Oltre quanti secondi senza un `flusso_stream` il messaggio non dice piu'
 *  niente (il runner lo manda a ogni battito, ~10 s): 3 battiti. */
export const FLUSSO_STREAM_VALIDO_S = 30;

function num(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Legge un push `flusso_stream`. `null` = messaggio storto (senza `ts`). */
export function leggiFlussoStream(d: unknown): FlussoStreamRunner | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    const ts = num(o.ts);
    if (ts == null) return null;
    return {
        ts,
        vivo: typeof o.vivo === 'boolean' ? o.vivo : null,
        interrotto: o.interrotto === true,
        motivo: typeof o.motivo === 'string' ? o.motivo : null,
        etaS: num(o.eta_s),
        mutoDaS: num(o.muto_da_s),
        mercatiFermi: Array.isArray(o.mercati_fermi) ? o.mercati_fermi.map(String) : [],
    };
}

const MOTIVO_IT: Record<string, string> = {
    flusso_interrotto: 'nessun messaggio da Betfair, neanche heartbeat',
    stream_latente: 'Betfair in latenza (503)',
    mai_connesso: 'connessione mai riuscita',
};

export interface GiudizioFlussoStream {
    interrotto: boolean;
    /** J2 (reperto 3): il canale locale del runner non e' raggiungibile: lo
     *  stato dello stream NON e' noto (mai silenzio, mai «tutto a posto») */
    nonNoto?: boolean;
    testo: string;
}

export const TESTO_CANALE_GIU =
    'stato dello stream NON NOTO (canale locale del runner non raggiungibile): '
    + 'i prezzi mostrati potrebbero essere fermi';

/**
 * Come `giudizioFlussoStream`, ma sapendo se il CANALE LOCALE del runner e'
 * collegato. Canale giu' = «NON NOTO», sempre (anche con un vecchio episodio
 * in memoria: non si sa piu' niente).
 */
export function giudizioConCanale(
    f: FlussoStreamRunner | null, marketId: string | null, nowMs: number, canaleConnesso: boolean,
): GiudizioFlussoStream | null {
    if (!canaleConnesso) return { interrotto: false, nonNoto: true, testo: TESTO_CANALE_GIU };
    return giudizioFlussoStream(f, marketId, nowMs);
}

/**
 * Il giudizio per UN mercato (o per il runner intero con `marketId` null).
 * Interrotto se l'ultimo messaggio e' fresco, dichiara l'episodio e (con
 * `marketId`) il mercato e' fra quelli fermi o l'elenco e' vuoto.
 */
export function giudizioFlussoStream(
    f: FlussoStreamRunner | null, marketId: string | null, nowMs: number,
): GiudizioFlussoStream | null {
    if (!f || !f.interrotto) return null;
    if ((nowMs - f.ts) / 1000 > FLUSSO_STREAM_VALIDO_S) return null;
    if (marketId && f.mercatiFermi.length > 0 && !f.mercatiFermi.includes(String(marketId))) return null;
    const da = f.mutoDaS != null ? f.mutoDaS + Math.max(0, (nowMs - f.ts) / 1000) : null;
    const quanto = da == null ? '' : ` da ${Math.round(da)} s`;
    const perche = f.motivo ? ` (${MOTIVO_IT[f.motivo] ?? f.motivo})` : '';
    return {
        interrotto: true,
        testo: `FLUSSO INTERROTTO${quanto}${perche}: prezzi FERMI, non sono quelli di Betfair adesso. `
            + 'Nessuna apertura su questi prezzi; riconnessione automatica in corso.',
    };
}
