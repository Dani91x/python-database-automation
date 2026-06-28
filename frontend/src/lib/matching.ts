// ============================================================================
// matching.ts — modello FEDELE del motore di matching di Betfair Exchange.
//
// È PURO (nessuna dipendenza da React) e CONDIVISO: lo stesso identico codice che
// stima i fill nel simulatore Match Replay è quello che, una volta validato, userà
// il live per prevedere/validare gli abbinamenti. NON esegue ordini reali: in live
// l'esecuzione passa dalle API Betfair e i matched effettivi si leggono dal report
// d'ordine — questo modulo è il MODELLO di "cosa farebbe il matcher".
//
// SEMANTICA LADDER (coerente con live.ts / fill.ts):
//   - `back` = available-to-back (offerte di chi LAYA): ci si abbina BANCANDO (back).
//              ordinata best-first = prezzo DECRESCENTE (il best back è il più alto).
//   - `lay`  = available-to-lay  (offerte di chi BANCA): ci si abbina LAYANDO (lay).
//              ordinata best-first = prezzo CRESCENTE (il best lay è il più basso).
//   La `size` è in STAKE del backer (£) → si somma direttamente come stake piazzabile.
//
// MODELLO DI MATCHING (due fasi, come Betfair):
//   1. TAKER (marketable) al momento dell'invio: l'ordine consuma la liquidità
//      OPPOSTA visibile ai prezzi "buoni almeno quanto" il limite, dal migliore,
//      con PRICE IMPROVEMENT (ci si abbina ai prezzi reali dei livelli → media VWAP)
//      e FILL PARZIALE se la size è insufficiente. In-play l'invio avviene a
//      placedTs + delay (ritardo Betfair ~5s): il book usato è quello a quell'istante.
//   2. MAKER (resto a riposo): la parte non abbinata RIPOSA al prezzo limite e si
//      abbina NEL TEMPO man mano che il mercato TRATTA. Modello con dati a snapshot:
//        • QUEUE POSITION: si parte dietro la size già presente al proprio prezzo;
//        • CAP sul volume realmente tradato: il fill incrementale ≤ Δtv (non si può
//          abbinare più di quanto è davvero passato a mercato nell'intervallo);
//        • TRIGGER: si conteggia solo il volume tradato "che attraversa" il limite
//          (con `trd` per-prezzo se disponibile; altrimenti proxy via ltp/Δtv).
//   Alla SOSPENSIONE/chiusura il resto LAPSE viene annullato (default in-play),
//   PERSIST resta. Il P&L (replay-pnl) usa SOLO la parte abbinata, a quota = VWAP.
// ============================================================================

export type OrderSide = 'back' | 'lay';
export type Persistence = 'LAPSE' | 'PERSIST';
export type OrderStatus = 'PENDING' | 'OPEN' | 'MATCHED' | 'CANCELLED' | 'LAPSED';

// Confronto tra quote in virgola mobile (i tick Betfair sono discreti ma i prezzi
// possono arrivare con rumore numerico).
const PRICE_EPS = 1e-9;
const SIZE_EPS = 1e-9;

// Ritardo in-play Betfair (1–8s, ~5s calcio): default 5s.
export const DEFAULT_DELAY_MS = 5000;
// Stake minimo Betfair Exchange (GBP).
export const MIN_STAKE_GBP = 2;

// --------------------------------------------------------------- price ladder
// Scala dei tick Betfair: incremento valido per fascia di quota.
const TICK_BANDS: ReadonlyArray<readonly [number, number, number]> = [
    [1.01, 2, 0.01],
    [2, 3, 0.02],
    [3, 4, 0.05],
    [4, 6, 0.1],
    [6, 10, 0.2],
    [10, 20, 0.5],
    [20, 30, 1],
    [30, 50, 2],
    [50, 100, 5],
    [100, 1000, 10],
];

/** Arrotonda una quota al tick Betfair valido più vicino, clampata a [1.01, 1000]. */
export function roundToTick(price: number): number {
    if (!Number.isFinite(price)) return NaN;
    if (price <= 1.01) return 1.01;
    if (price >= 1000) return 1000;
    for (const [lo, hi, step] of TICK_BANDS) {
        if (price >= lo - PRICE_EPS && price < hi - PRICE_EPS) {
            const n = Math.round((price - lo) / step);
            return Math.round((lo + n * step) * 100) / 100;
        }
    }
    return Math.round(price * 100) / 100;
}

/** True se la quota è già su un tick valido (entro tolleranza). */
export function isValidTick(price: number): boolean {
    return Math.abs(price - roundToTick(price)) < 1e-6;
}

// ------------------------------------------------------------------ snapshots
// Snapshot del book di UNA selezione a un istante (derivato da Frame.ladder[sid]).
export interface BookSnapshot {
    ts: number;                                            // ms epoch
    back: ReadonlyArray<readonly [number, number]>;        // available-to-back, best(alto)-first
    lay: ReadonlyArray<readonly [number, number]>;         // available-to-lay,  best(basso)-first
    ltp: number | null;                                    // last traded price
    tv: number | null;                                     // volume tradato CUMULATIVO sulla selezione
    trd?: ReadonlyArray<readonly [number, number]>;        // volume tradato CUMULATIVO per-prezzo (opz.)
    status?: string | null;                                // OPEN | SUSPENDED | CLOSED (opz.)
}

export interface Fill {
    price: number;   // quota dell'abbinamento
    size: number;    // stake abbinato (£)
    ts: number;      // istante dell'abbinamento (ms)
    taker: boolean;  // true = abbinato consumando il book (taker); false = a riposo (maker)
}

// Richiesta d'ordine (immutabile): ciò che l'utente ha piazzato.
export interface OrderRequest {
    side: OrderSide;
    limitPrice: number;     // quota limite (prezzo cliccato)
    stake: number;          // stake richiesto (£)
    placedTs: number;       // istante di piazzamento (ms)
    inPlay: boolean;        // true → si applica il ritardo
    delayMs?: number;       // override ritardo (default DEFAULT_DELAY_MS se inPlay)
    persistence?: Persistence; // default LAPSE
    cancelledTs?: number | null; // se settato, l'ordine è cancellato a questo istante (annulla il resto non abbinato)
}

// Stato risolto dell'ordine a un certo istante `uptoTs`.
export interface ResolvedOrder {
    side: OrderSide;
    limitPrice: number;
    requested: number;
    matched: number;            // stake abbinato totale
    avgPrice: number | null;    // VWAP degli abbinamenti (null se 0)
    remaining: number;          // stake non ancora abbinato (a riposo o annullato)
    fills: Fill[];
    status: OrderStatus;
    effectiveTs: number;        // istante in cui l'ordine raggiunge il matcher
}

// ------------------------------------------------------------- marketable take
/**
 * matchMarketable — porzione TAKER abbinabile ORA contro la liquidità OPPOSTA
 * visibile, dal prezzo migliore, rispettando il limite. Ritorna i fill (ai prezzi
 * reali dei livelli → price improvement) e il resto non abbinato.
 */
export function matchMarketable(
    side: OrderSide,
    limitPrice: number,
    stake: number,
    book: BookSnapshot,
): { matched: number; avgPrice: number | null; fills: Fill[]; remaining: number } {
    const fills: Fill[] = [];
    if (!(stake > 0) || !(limitPrice > 1)) return { matched: 0, avgPrice: null, fills, remaining: Math.max(0, stake) };
    // Si BANCA contro available-to-back; si LAYA contro available-to-lay.
    const levels = side === 'back' ? book.back : book.lay;
    let remaining = stake;
    let matched = 0;
    let cost = 0;
    for (const lvl of levels) {
        if (remaining <= SIZE_EPS) break;
        const price = lvl?.[0];
        const size = lvl?.[1];
        if (typeof price !== 'number' || !Number.isFinite(price)) continue;
        if (typeof size !== 'number' || !Number.isFinite(size) || size <= 0) continue;
        const ok = side === 'back'
            ? price >= limitPrice - PRICE_EPS   // banco a quota ≥ limite
            : price <= limitPrice + PRICE_EPS;  // layo a quota ≤ limite
        if (!ok) continue;
        const take = Math.min(remaining, size);
        fills.push({ price, size: take, ts: book.ts, taker: true });
        matched += take;
        cost += take * price;
        remaining -= take;
    }
    return {
        matched,
        avgPrice: matched > SIZE_EPS ? cost / matched : null,
        fills,
        remaining: Math.max(0, stake - matched),
    };
}

// ------------------------------------------------------- traded-through volume
// Volume tradato CUMULATIVO ai prezzi che soddisfano il limite dell'ordine.
//   back limite O → si abbina se il mercato tratta a prezzo ≥ O (sale fino a O);
//   lay  limite O → si abbina se il mercato tratta a prezzo ≤ O (scende fino a O).
function cumTradedThrough(side: OrderSide, limitPrice: number, book: BookSnapshot): number {
    if (book.trd && book.trd.length > 0) {
        let sum = 0;
        for (const lvl of book.trd) {
            const price = lvl?.[0];
            const vol = lvl?.[1];
            if (typeof price !== 'number' || !Number.isFinite(price)) continue;
            if (typeof vol !== 'number' || !Number.isFinite(vol) || vol <= 0) continue;
            const through = side === 'back'
                ? price >= limitPrice - PRICE_EPS
                : price <= limitPrice + PRICE_EPS;
            if (through) sum += vol;
        }
        return sum;
    }
    return NaN; // nessun trd per-prezzo → il chiamante usa il proxy ltp/Δtv
}

// L'intervallo [prev, cur] ha tradato "attraverso" il limite? (proxy via ltp)
function ltpTouchedThrough(side: OrderSide, limitPrice: number, prev: BookSnapshot, cur: BookSnapshot): boolean {
    const a = prev.ltp, b = cur.ltp;
    const hit = (p: number | null) => p != null && Number.isFinite(p) && (
        side === 'back' ? p >= limitPrice - PRICE_EPS : p <= limitPrice + PRICE_EPS
    );
    return hit(a) || hit(b);
}

// size già in coda al nostro prezzo all'inizio del riposo: si entra DIETRO la
// liquidità presente al limite sul lato dove l'ordine fa da maker.
//   back che riposa a O → entra nella coda available-to-lay a O;
//   lay  che riposa a O → entra nella coda available-to-back a O.
function queueAheadAt(side: OrderSide, limitPrice: number, book: BookSnapshot): number {
    const levels = side === 'back' ? book.lay : book.back;
    let q = 0;
    for (const lvl of levels) {
        const price = lvl?.[0];
        const size = lvl?.[1];
        if (typeof price !== 'number' || typeof size !== 'number') continue;
        if (Math.abs(price - limitPrice) < PRICE_EPS) q += Math.max(0, size);
    }
    return q;
}

// --------------------------------------------------------------- order driver
/**
 * simulateOrder — risolve un ordine contro la sequenza di snapshot del suo mercato
 * fino all'istante `uptoTs`. È una funzione PURA e DETERMINISTICA: il risultato
 * dipende solo da (ordine, frames ≤ uptoTs) → lo scrubbing avanti/indietro della
 * timeline è coerente (si ricalcola da zero ad ogni istante).
 *
 * @param req     richiesta d'ordine
 * @param frames  snapshot della selezione ORDINATI per ts (tutti i frame del mercato)
 * @param uptoTs  istante corrente (ms): si considerano solo i frame con ts ≤ uptoTs
 */
export function simulateOrder(req: OrderRequest, frames: ReadonlyArray<BookSnapshot>, uptoTs: number): ResolvedOrder {
    const persistence: Persistence = req.persistence ?? 'LAPSE';
    const delayMs = req.inPlay ? (req.delayMs ?? DEFAULT_DELAY_MS) : 0;
    const effectiveTs = req.placedTs + delayMs;
    const cancelledTs = req.cancelledTs ?? null;

    const base: ResolvedOrder = {
        side: req.side,
        limitPrice: req.limitPrice,
        requested: req.stake,
        matched: 0,
        avgPrice: null,
        remaining: req.stake,
        fills: [],
        status: 'PENDING',
        effectiveTs,
    };
    if (!(req.stake > 0) || !(req.limitPrice > 1)) return { ...base, remaining: 0, status: 'CANCELLED' };
    // ordine non ancora arrivato al matcher
    if (uptoTs < effectiveTs - PRICE_EPS) return base;

    // book all'istante di invio = ultimo snapshot con ts ≤ effectiveTs
    let takeIdx = -1;
    for (let i = 0; i < frames.length; i++) {
        if (frames[i].ts <= effectiveTs + PRICE_EPS) takeIdx = i; else break;
    }
    if (takeIdx < 0) {
        // nessuno snapshot ancora disponibile all'invio → niente da abbinare (resta pending/open)
        return { ...base, status: 'OPEN' };
    }

    const fills: Fill[] = [];
    let matched = 0;
    let cost = 0;

    // --- FASE 1: TAKER al book di invio ---
    const takeBook = frames[takeIdx];
    const taker = matchMarketable(req.side, req.limitPrice, req.stake, takeBook);
    for (const f of taker.fills) { fills.push(f); matched += f.size; cost += f.size * f.price; }
    let remaining = Math.max(0, req.stake - matched);

    // posizione in coda al momento del riposo (sul book di invio)
    let queueAhead = remaining > SIZE_EPS ? queueAheadAt(req.side, req.limitPrice, takeBook) : 0;

    // --- FASE 2: MAKER, il resto riposa e si abbina nel tempo ---
    // baseline del volume tradato-attraverso al book di invio (per misurare gli incrementi)
    let prevThrough = remaining > SIZE_EPS ? cumTradedThrough(req.side, req.limitPrice, takeBook) : NaN;
    let prevBook = takeBook;
    let status: OrderStatus = remaining > SIZE_EPS ? 'OPEN' : 'MATCHED';

    for (let i = takeIdx + 1; i < frames.length; i++) {
        const cur = frames[i];
        if (cur.ts > uptoTs + PRICE_EPS) break;

        // cancellazione utente: il resto non abbinato sparisce
        if (cancelledTs != null && cur.ts >= cancelledTs - PRICE_EPS && remaining > SIZE_EPS) {
            status = matched > SIZE_EPS ? 'OPEN' : 'CANCELLED';
            remaining = 0;
            break;
        }

        if (remaining <= SIZE_EPS) { status = 'MATCHED'; break; }

        // sospensione/chiusura: LAPSE annulla il resto, PERSIST lo mantiene
        const st = (cur.status ?? '').toUpperCase();
        if ((st === 'SUSPENDED' || st === 'CLOSED') && persistence === 'LAPSE') {
            status = matched > SIZE_EPS ? 'OPEN' : 'LAPSED';
            remaining = 0;
            break;
        }

        // volume tradato-attraverso nell'intervallo (prevBook → cur]
        let tradedThrough: number;
        const curThrough = cumTradedThrough(req.side, req.limitPrice, cur);
        if (Number.isFinite(curThrough)) {
            // dato esatto per-prezzo (trd): incremento del cumulato attraverso il limite.
            // se il trd compare solo ora, la baseline è 0 (cumulato precedente sconosciuto → prudente).
            const baseline = Number.isFinite(prevThrough) ? prevThrough : 0;
            tradedThrough = Math.max(0, curThrough - baseline);
        } else {
            // proxy: Δtv del mercato, contato solo se l'ltp ha attraversato il limite
            const dtv = Math.max(0, (cur.tv ?? 0) - (prevBook.tv ?? 0));
            tradedThrough = ltpTouchedThrough(req.side, req.limitPrice, prevBook, cur) ? dtv : 0;
        }

        if (tradedThrough > SIZE_EPS) {
            // prima si smaltisce la coda davanti a noi, poi si riempie il nostro ordine
            let consume = tradedThrough;
            const fromQueue = Math.min(queueAhead, consume);
            queueAhead -= fromQueue;
            consume -= fromQueue;
            const fill = Math.min(consume, remaining);
            if (fill > SIZE_EPS) {
                // a riposo si ottiene il PROPRIO prezzo limite (si è il maker)
                fills.push({ price: req.limitPrice, size: fill, ts: cur.ts, taker: false });
                matched += fill;
                cost += fill * req.limitPrice;
                remaining -= fill;
            }
        }

        if (Number.isFinite(curThrough)) prevThrough = curThrough;
        prevBook = cur;
        if (remaining <= SIZE_EPS) { status = 'MATCHED'; break; }
    }

    return {
        side: req.side,
        limitPrice: req.limitPrice,
        requested: req.stake,
        matched,
        avgPrice: matched > SIZE_EPS ? cost / matched : null,
        remaining: Math.max(0, remaining),
        fills,
        status,
        effectiveTs,
    };
}
