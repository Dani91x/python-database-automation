// ============================================================================
// controlRoomCatena.ts — LA CATENA DEI TEMPI, da Betfair al pixel.
//
// «Devi monitorare ogni cosa, dai dati di Betfair a quello che vedo in UI»
// (utente, 14/09). Questo file costruisce quella catena e la rende leggibile
// salto per salto, perché con un totale soltanto si vede CHE c'è un collo di
// bottiglia; con i salti si vede DOVE.
//
//   Betfair → feed → bot → decisione → ordine → risposta → fill
//                  ↘ database → schermo
//
// REGOLE:
//  1. **Un salto che non sappiamo misurare vale `null`, mai zero.** Zero
//     millisecondi è un'affermazione forte: significa «istantaneo». «Non lo so»
//     è un'altra cosa e si scrive in un altro modo.
//  2. **Nessun numero si inventa per far quadrare la catena.** Se manca un
//     istante, quel salto resta vuoto e i totali che lo attraversano pure.
//  3. Gli istanti del BOT vengono dal servizio (`meta.tempi`, `meta.esecuzione`):
//     qui non si ricalcola niente, si legge e si sottrae.
// ============================================================================

/** Un salto della catena: quanto tempo è passato, e fra cosa e cosa. */
export interface Salto {
    id: string;
    /** etichetta breve per il trader */
    nome: string;
    /** millisecondi; `null` = non misurabile */
    ms: number | null;
    /** che cosa è successo in questo tratto, in una riga */
    spiega: string;
    /** questo tratto dipende da noi o da Betfair? */
    nostro: boolean;
    /**
     * È davvero una LATENZA, cioè tempo speso a trasportare o decidere?
     *
     * ⚠️ REVIEW 15/09 — il primo tratto NON lo è. `t0_quote_ms` è l'istante
     * dell'ultimo CAMBIO di prezzo (`service.py:503`), non l'istante in cui
     * Betfair ce l'ha mandato: la differenza con `t1` dice da quanto quel
     * prezzo era fermo quando lo scanner ha scritto la riga. Su un mercato
     * poco scambiato vale minuti, e sommarla alla catena faceva sembrare
     * lentissima una pipeline che gira in millisecondi.
     *
     * Si mostra — è un'informazione utile, dice su che prezzo si è deciso —
     * ma non entra in nessun totale.
     */
    latenza: boolean;
}

/** Gli istanti che il servizio scrive sul `meta` di un trade. */
export interface TempiTrade {
    t0_quote_ms?: number | null;
    t1_feed_ms?: number | null;
    t2_letto_ms?: number | null;
    t3_deciso_ms?: number | null;
}

export interface EsecuzioneTrade {
    t4_inviato?: number | null;
    t5_risposta?: number | null;
    betfair_ms?: number | null;
    price_medio?: number | null;
    scorrimento_tick?: number | null;
    /**
     * Che strada ha preso l'ordine. Lo scrive il servizio (`execution.py`).
     *
     * ⚠️ REVIEW 15/09 — su `submin` (place-and-trim) l'intervallo misurato NON
     * è un round-trip di Betfair: è una SEQUENZA NOSTRA — parcheggio del
     * minimo a quota non abbinabile, riduzione, riprezzo e ritiro del residuo,
     * cioè tre o quattro chiamate REST più la nostra logica. Chiamarlo
     * «Betfair risponde» ed escluderlo dal totale nostro regalava alla nostra
     * catena il pezzo più lungo che abbiamo.
     */
    percorso?: string | null;
}

/** Differenza in ms fra due istanti, `null` se uno dei due manca o se il
 *  risultato sarebbe negativo (orologi diversi: meglio «non lo so» di un numero
 *  impossibile). */
export function delta(da: unknown, a: unknown): number | null {
    const x = typeof da === 'number' && Number.isFinite(da) ? da : null;
    const y = typeof a === 'number' && Number.isFinite(a) ? a : null;
    if (x == null || y == null) return null;
    const d = y - x;
    return d < 0 ? null : Math.round(d);
}

/**
 * La catena di UNA operazione, dal prezzo di Betfair al fill.
 * Sei salti; quelli che non si possono misurare restano `null` e la pagina li
 * mostra come «—», non come 0.
 */
export function catenaOperazione(
    tempi: TempiTrade | null | undefined,
    esecuzione: EsecuzioneTrade | null | undefined,
    t6FillMs?: number | null,
): Salto[] {
    const t = tempi ?? {};
    const e = esecuzione ?? {};
    const submin = String(e.percorso ?? '').toLowerCase() === 'submin';
    return [
        {
            // NON è una latenza: vedi `Salto.latenza`.
            id: 'eta_prezzo', nome: 'prezzo già fermo da', ms: delta(t.t0_quote_ms, t.t1_feed_ms),
            spiega: 'da quanto quel prezzo non cambiava quando lo scanner ha scritto la riga — '
                + 'non è un ritardo, è l’età del prezzo su cui si è deciso',
            nostro: true, latenza: false,
        },
        {
            id: 'lettura', nome: 'feed → bot', ms: delta(t.t1_feed_ms, t.t2_letto_ms),
            spiega: 'quanto la riga è rimasta sul database prima che il bot la leggesse',
            nostro: true, latenza: true,
        },
        {
            id: 'decisione', nome: 'bot → decisione', ms: delta(t.t2_letto_ms, t.t3_deciso_ms),
            spiega: 'quanto ci ha messo il bot a decidere, avendo il dato in mano',
            nostro: true, latenza: true,
        },
        {
            id: 'invio', nome: 'decisione → invio', ms: delta(t.t3_deciso_ms, e.t4_inviato),
            spiega: 'dalla decisione alla chiamata a Betfair', nostro: true, latenza: true,
        },
        submin ? {
            // place-and-trim: NON è un round-trip, è una sequenza nostra
            id: 'betfair', nome: 'place-and-trim (3-4 chiamate)',
            ms: typeof e.betfair_ms === 'number' ? Math.round(e.betfair_ms) : delta(e.t4_inviato, e.t5_risposta),
            spiega: 'sequenza NOSTRA sotto-minimo: parcheggio, taglio, riprezzo e '
                + 'ritiro del residuo — dentro ci sono anche i round-trip di Betfair',
            nostro: true, latenza: true,
        } : {
            id: 'betfair', nome: 'Betfair risponde',
            ms: typeof e.betfair_ms === 'number' ? Math.round(e.betfair_ms) : delta(e.t4_inviato, e.t5_risposta),
            spiega: 'l’unico tratto che non dipende da noi', nostro: false, latenza: true,
        },
        {
            id: 'fill', nome: 'risposta → fill', ms: delta(e.t5_risposta, t6FillMs),
            spiega: 'dalla risposta all’abbinamento confermato', nostro: true, latenza: true,
        },
    ];
}

/** Totale della catena: `null` se anche un solo salto manca — un totale
 *  parziale spacciato per totale è peggio di nessun totale.
 *
 *  I tratti che NON sono latenze (l'età del prezzo) restano fuori: sommarli
 *  farebbe sembrare lenta una pipeline che gira in millisecondi. */
export function totaleCatena(salti: readonly Salto[]): number | null {
    let somma = 0;
    for (const s of salti) {
        if (!s.latenza) continue;
        if (s.ms == null) return null;
        somma += s.ms;
    }
    return somma;
}

/** Quanto della catena dipende da NOI (tutto tranne Betfair). `null` se manca
 *  un pezzo nostro. */
export function totaleNostro(salti: readonly Salto[]): number | null {
    let somma = 0;
    for (const s of salti) {
        if (!s.nostro || !s.latenza) continue;
        if (s.ms == null) return null;
        somma += s.ms;
    }
    return somma;
}

/** Il salto più lento fra quelli misurati: è il collo di bottiglia.
 *  `null` se non c'è niente di misurato. */
export function colloDiBottiglia(salti: readonly Salto[]): Salto | null {
    let peggio: Salto | null = null;
    for (const s of salti) {
        // l'età del prezzo non è un collo di bottiglia: non è tempo nostro
        if (!s.latenza) continue;
        if (s.ms == null) continue;
        if (peggio == null || s.ms > (peggio.ms as number)) peggio = s;
    }
    return peggio;
}

// ------------------------------------------------- la catena fino allo schermo

export interface CatenaSchermo {
    /** età della riga del feed che stiamo mostrando (ms) */
    feedMs: number | null;
    /** età dell'ultimo messaggio spinto dal bot sul canale locale (ms) */
    pushMs: number | null;
    /** età dell'ultima lettura completa dal database (ms) */
    letturaMs: number | null;
    /** il più vecchio dei tre: è l'età REALE di quello che il trader vede */
    schermoMs: number | null;
}

/**
 * Quanto è vecchio quello che il trader sta guardando **adesso**.
 *
 * Si prende il PEGGIORE dei tre canali, non il migliore: la pagina è vecchia
 * quanto il suo pezzo più vecchio. Mostrare il minimo sarebbe la stessa bugia
 * di un semaforo verde acceso da un solo sensore su tre.
 */
export function catenaSchermo(args: {
    feedMs?: number | null;
    pushMs?: number | null;
    letturaMs?: number | null;
}): CatenaSchermo {
    const val = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.round(v) : null);
    const feedMs = val(args.feedMs);
    const pushMs = val(args.pushMs);
    const letturaMs = val(args.letturaMs);
    const noti = [feedMs, pushMs, letturaMs].filter((v): v is number => v != null);
    return { feedMs, pushMs, letturaMs, schermoMs: noti.length ? Math.max(...noti) : null };
}

/** Formato breve: sotto il secondo in millisecondi, sopra in secondi. Un numero
 *  assente è `—`, mai `0 ms`. */
export function fmtMs(ms: number | null | undefined): string {
    if (typeof ms !== 'number' || !Number.isFinite(ms)) return '—';
    if (ms < 1000) return `${Math.round(ms)} ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
    return `${Math.round(ms / 60_000)} min`;
}
