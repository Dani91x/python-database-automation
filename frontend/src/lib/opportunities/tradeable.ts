// ============================================================================
// tradeable.ts — "SPECCHIO DELLA REALTÀ": un'opportunità esiste SOLO se è
// davvero eseguibile contro il book registrato in quell'istante.
//
// Regola (confermata money-critical):
//   1) il MERCATO dev'essere OPEN (non SUSPENDED/CLOSED): durante una sospensione
//      — tipica dopo un gol/cartellino o a fine gara — i prezzi mostrati NON sono
//      abbinabili e le bet possono essere annullate;
//   2) dev'essere PLAUSIBILE PIAZZARE a quei prezzi: ci deve essere CONTROPARTE
//      reale (size > 0) su OGNI gamba mostrata → niente "abbinato £0";
//   3) per i segnali direzionali serve un MERCATO VERO A DUE LATI (best back E
//      best lay con size reale e spread di probabilità sano): un libro "back 5 /
//      lay 1000" non è un prezzo con consenso, è liquidità ritirata / quota
//      fantasma e NON va trattato come operabile.
//
// Queste funzioni sono PURE e condivise da engine.ts (gate centrale) e dai
// singoli detector (gate alla sorgente). Nessuna dipendenza da React.
// ============================================================================
import type { Opportunity, Snapshot, MarketState, Leg } from './types';

// Tolleranza numerica per "size/stake realmente > 0".
export const EXEC_EPS = 1e-6;

// Spread MASSIMO sulla probabilità implicita (1/bestBack − 1/bestLay) perché una
// selezione sia un MERCATO REALE a due lati. I mercati veri stanno ben sotto 0.03;
// 0.10 (10 punti percentuali) è generoso ma taglia i libri degeneri tipo
// back 5 / lay 1000 (gap ≈ 0.20). NON è una soglia di "size": è un test di
// VALIDITÀ del mercato (esiste un prezzo di consenso a due lati?).
export const MAX_PROB_SPREAD = 0.10;

// Tipi di opportunità le cui gambe si piazzano SIMULTANEAMENTE (struttura bloccata):
// per queste l'ingresso richiede TUTTE le gambe contestualmente.
const MULTI_LEG_ENTRY_TYPES = new Set(['ltd_insurance', 'lay_field_cs']);

// Il mercato è operabile adesso? (status OPEN). SUSPENDED/CLOSED → no.
export function isMarketOpen(st: MarketState | undefined): boolean {
    return !!st && (st.status ?? '').toUpperCase() === 'OPEN';
}

// Miglior prezzo con size REALE (> 0): ignora i livelli fantasma a size 0.
// I livelli sono ordinati con index 0 = best, ma il best potrebbe avere size 0
// (book in aggiornamento) → si scorre fino al primo con controparte vera.
function bestSizedPrice(
    levels: ReadonlyArray<readonly [number, number]> | undefined,
): number | null {
    if (!levels) return null;
    for (const lvl of levels) {
        const price = lvl?.[0];
        const size = lvl?.[1];
        if (typeof price === 'number' && price > 1 && typeof size === 'number' && size > 0) {
            return price;
        }
    }
    return null;
}

export interface RealBook {
    bestBack: number;
    bestLay: number;
}

/**
 * tradeableSelection — la selezione è un MERCATO REALE a due lati su cui è
 * plausibile operare ORA? Richiede:
 *   - mercato OPEN;
 *   - best back E best lay entrambi con size reale;
 *   - book NON incrociato (bestLay > bestBack: il caso incrociato è un arbitraggio
 *     gestito a parte dai detector tier0/back-to-lay);
 *   - spread di probabilità entro MAX_PROB_SPREAD (esiste un prezzo di consenso).
 * Ritorna il book reale {bestBack,bestLay} o null se non operabile.
 */
export function tradeableSelection(
    st: MarketState | undefined,
    selId: number,
    maxProbSpread = MAX_PROB_SPREAD,
): RealBook | null {
    if (!isMarketOpen(st)) return null;
    const e = st!.ladder?.[String(selId)];
    const bb = bestSizedPrice(e?.back);
    const bl = bestSizedPrice(e?.lay);
    if (bb == null || bl == null) return null;
    if (!(bl > bb)) return null; // incrociato/anomalo: non è un libro a due lati "normale"
    if ((1 / bb) - (1 / bl) > maxProbSpread) return null; // spread di prob. troppo largo → non reale
    return { bestBack: bb, bestLay: bl };
}

/**
 * entryLegs — gambe d'INGRESSO (azione da piazzare ORA) di un'opportunità:
 *  - tier 'arb': tutte (il lock richiede tutte le bet contestualmente);
 *  - strutture simultanee (ltd_insurance / lay_field_cs): tutte;
 *  - altrimenti: solo la prima (l'azione immediata; l'uscita è un piano futuro).
 * Condiviso tra il gate del motore e l'harness di validazione (unica fonte).
 */
export function entryLegs(o: Opportunity): Leg[] {
    if (o.tier === 'arb' || MULTI_LEG_ENTRY_TYPES.has(o.type)) return o.legs;
    return o.legs.length > 0 ? [o.legs[0]] : [];
}

/**
 * isExecutableNow — l'opportunità è uno SPECCHIO della realtà eseguibile adesso?
 *   - OGNI mercato referenziato da una gamba dev'essere OPEN;
 *   - OGNI gamba mostrata dev'essere realmente abbinabile (matchedStake > 0):
 *     nessuna gamba "abbinato £0" senza controparte.
 * Una gamba di uscita PROIETTATA inclusa in `legs[]` (es. il lay di un back-to-lay)
 * viene inclusa nel controllo: se non c'è controparte a quel prezzo ORA, il
 * profitto promesso non è reale → l'opportunità non si mostra.
 */
export function isExecutableNow(snap: Snapshot, o: Opportunity): boolean {
    if (o.legs.length === 0) return false;
    for (const l of o.legs) {
        if (!isMarketOpen(snap.state[l.marketId])) return false;
        if (!(l.matchedStake > EXEC_EPS)) return false;
    }
    return true;
}
