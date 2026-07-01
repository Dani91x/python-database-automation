// ============================================================================
// riskMath.ts — matematica PURA per le ANTEPRIME UI del risk engine (offset /
// stop-loss / take-profit / trailing). Nessun I/O, nessun React: solo aritmetica
// sul ladder Betfair (tick non lineari). Il server resta AUTORITATIVO: qui
// calcoliamo solo i prezzi mostrati all'utente prima di armare una regola.
//
// Ladder Betfair (incrementi per banda):
//   1.01–2 .01 | 2–3 .02 | 3–4 .05 | 4–6 .1 | 6–10 .2 | 10–20 .5 |
//   20–30 1 | 30–50 2 | 50–100 5 | 100–1000 10
// ============================================================================

// Bande [min inclusivo, max esclusivo (tranne l'ultima), step].
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

export const MIN_PRICE = 1.01;
export const MAX_PRICE = 1000;

// round a 2 decimali stabile (evita 0.30000000000000004 sul ladder).
function r2(x: number): number {
    return Math.round(x * 100) / 100;
}

// Ladder completo materializzato UNA volta: [1.01 … 1000]. Indici contigui →
// muoversi di N tick = spostarsi di N posizioni (anche a cavallo tra bande).
const PRICES: number[] = (() => {
    const out: number[] = [];
    for (const [lo, hi, step] of TICK_BANDS) {
        // per ogni banda emetti lo, lo+step, … < hi; hi lo emette la banda successiva
        // (o, per l'ultima, lo aggiungiamo esplicitamente in coda).
        const steps = Math.round((hi - lo) / step);
        for (let k = 0; k < steps; k++) out.push(r2(lo + k * step));
    }
    out.push(MAX_PRICE); // 1000 (estremo superiore, non coperto dai loop < hi)
    return out;
})();

// Indice del tick valido più vicino a `price` (ricerca binaria; sceglie il più
// vicino, a parità il più basso). Clampa a [MIN_PRICE, MAX_PRICE].
function nearestTickIndex(price: number): number {
    if (!Number.isFinite(price) || price <= MIN_PRICE) return 0;
    if (price >= MAX_PRICE) return PRICES.length - 1;
    let lo = 0, hi = PRICES.length - 1;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (PRICES[mid] < price) lo = mid + 1; else hi = mid;
    }
    // PRICES[lo] è il primo >= price: confronta col precedente e prendi il più vicino.
    if (lo > 0 && (price - PRICES[lo - 1]) <= (PRICES[lo] - price)) return lo - 1;
    return lo;
}

// Snap: prezzo valido più vicino sul ladder Betfair.
export function nearestTick(price: number): number {
    return PRICES[nearestTickIndex(price)];
}

// Prezzo spostato di `n` tick da `price` (n>0 = SALE, n<0 = SCENDE). `price` viene
// prima snappato al tick valido. Clampa agli estremi del ladder.
export function ticksAway(price: number, n: number): number {
    const idx = nearestTickIndex(price);
    const target = Math.min(PRICES.length - 1, Math.max(0, idx + Math.trunc(n)));
    return PRICES[target];
}

// Prezzo TARGET di un ordine offset (presa di profitto):
//   BACK entrato a P → si chiude LAY a un prezzo PIÙ BASSO (ticks giù).
//   LAY  entrato a P → si chiude BACK a un prezzo PIÙ ALTO (ticks su).
// `ticks` è la distanza in tick (magnitudine ≥ 0).
export function offsetTargetPrice(entrySide: 'back' | 'lay', entryPrice: number, ticks: number): number {
    const t = Math.abs(Math.trunc(ticks));
    return entrySide === 'back' ? ticksAway(entryPrice, -t) : ticksAway(entryPrice, +t);
}

// Prezzo di TRIGGER di uno stop-loss (movimento avverso):
//   BACK entrato a P → perdi se il prezzo SALE (ticks su).
//   LAY  entrato a P → perdi se il prezzo SCENDE (ticks giù).
export function stopTriggerPrice(entrySide: 'back' | 'lay', entryPrice: number, ticks: number): number {
    const t = Math.abs(Math.trunc(ticks));
    return entrySide === 'back' ? ticksAway(entryPrice, +t) : ticksAway(entryPrice, -t);
}

// Book percentage (overround) = Σ(1/quota)·100. <100 arbitraggio a favore del backer,
// >100 margine del banco. Ignora quote non valide (≤1). Ritorna 0 su input vuoto.
export function bookPercentage(prices: number[]): number {
    if (!Array.isArray(prices) || prices.length === 0) return 0;
    let sum = 0;
    for (const p of prices) {
        if (Number.isFinite(p) && p > 1) sum += 1 / p;
    }
    return r2(sum * 100);
}
