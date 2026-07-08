// ============================================================================
// priceAxis.ts — scala TICK Betfair completa (1.01 → 1000) come ASSE NAVIGABILE
// (price bar stile Geeks Toy): mappa prezzo↔indice-tick e profilo di
// concentrazione del denaro per zona. Matematica PURA, testabile a unità.
//
// Le bande tick sono lo standard Betfair Exchange:
//   1.01–2    step 0.01     2–3    step 0.02     3–4    step 0.05
//   4–6       step 0.1      6–10   step 0.2      10–20  step 0.5
//   20–30     step 1        30–50  step 2        50–100 step 5
//   100–1000  step 10
// Indice 0 = 1.01 … indice TOTAL_TICKS−1 = 1000 (350 prezzi validi in tutto).
// ============================================================================

interface Band {
    lo: number;      // prezzo di partenza della banda (ESCLUSO per le bande dopo la prima)
    hi: number;      // prezzo di fine banda (INCLUSO)
    step: number;    // incremento tick nella banda
    startIdx: number; // indice del PRIMO prezzo della banda (lo+step; per la prima banda: 1.01)
    count: number;   // quanti prezzi contiene la banda
}

// Costruzione bande con indici progressivi. La prima banda parte da 1.01 incluso.
const RAW: Array<[number, number, number]> = [
    [1.00, 2, 0.01],
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

const BANDS: Band[] = (() => {
    const out: Band[] = [];
    let idx = 0;
    for (const [lo, hi, step] of RAW) {
        // prezzi della banda: lo+step, lo+2·step, …, hi (lo escluso: appartiene alla banda prima)
        const count = Math.round((hi - lo) / step);
        out.push({ lo, hi, step, startIdx: idx, count });
        idx += count;
    }
    return out;
})();

export const TOTAL_TICKS = BANDS[BANDS.length - 1].startIdx + BANDS[BANDS.length - 1].count; // 350
export const MIN_PRICE = 1.01;
export const MAX_PRICE = 1000;

// Prezzo → indice tick [0, TOTAL_TICKS). Il prezzo viene CLAMPATO al range Betfair e
// arrotondato al tick più VICINO della sua banda (robusto a prezzi rumorosi).
export function priceToIndex(price: number): number {
    if (!Number.isFinite(price)) return 0;
    const p = Math.min(MAX_PRICE, Math.max(MIN_PRICE, price));
    for (const b of BANDS) {
        if (p <= b.hi + 1e-9) {
            const off = Math.round((p - b.lo) / b.step) - 1; // -1: lo è della banda precedente
            const clamped = Math.max(0, Math.min(b.count - 1, off));
            return b.startIdx + clamped;
        }
    }
    return TOTAL_TICKS - 1;
}

// Indice tick → prezzo valido Betfair. Indici fuori range vengono clampati.
export function indexToPrice(idx: number): number {
    const i = Math.max(0, Math.min(TOTAL_TICKS - 1, Math.round(idx)));
    for (const b of BANDS) {
        if (i < b.startIdx + b.count) {
            const raw = b.lo + (i - b.startIdx + 1) * b.step;
            // normalizza il binario float (0.1+0.2…) sul passo della banda
            const decimals = b.step < 0.02 ? 2 : b.step < 1 ? 2 : 0;
            return Number(raw.toFixed(decimals));
        }
    }
    return MAX_PRICE;
}

// Finestra di `count` tick VALIDI centrata sul tick più vicino a `center`, clampata ai
// bordi della scala (1.01 / 1000) SENZA restringersi: vicino agli estremi il centro
// "scivola" (stesso contratto di ladderMath.windowAround, ma sulla scala tick PURA —
// usata dalla navigazione manuale del ladder, B11/B18).
export function tickWindow(center: number, count: number): number[] {
    const n = Math.max(1, Math.min(Math.floor(count), TOTAL_TICKS));
    let start = priceToIndex(center) - Math.floor(n / 2);
    start = Math.max(0, Math.min(start, TOTAL_TICKS - n));
    return Array.from({ length: n }, (_, i) => indexToPrice(start + i));
}

// ---- profilo di concentrazione del denaro (per la heat della price bar) ----
// Aggrega size ([prezzo, size][]) in `nZones` zone uniformi sull'asse degli INDICI tick
// (non sui prezzi: così le zone hanno la stessa granularità percettiva del ladder).
// Ritorna un array di lunghezza nZones con la SOMMA delle size per zona.
export function moneyProfile(
    sources: Array<Array<[number, number]> | undefined>,
    nZones: number,
): number[] {
    const n = Math.max(1, Math.floor(nZones));
    const zones = new Array<number>(n).fill(0);
    for (const list of sources) {
        for (const [price, size] of list ?? []) {
            if (!Number.isFinite(price) || !Number.isFinite(size) || size <= 0) continue;
            const z = Math.min(n - 1, Math.floor((priceToIndex(price) / TOTAL_TICKS) * n));
            zones[z] += size;
        }
    }
    return zones;
}
