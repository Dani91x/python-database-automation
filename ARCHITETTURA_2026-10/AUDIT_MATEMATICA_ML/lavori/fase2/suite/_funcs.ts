// ------------------- aritmetica IDENTICA al server (dutch_variable) -------------------
// Il server calcola in Python: `round(x, 2)` arrotonda sul valore binario ESATTO e, sui
// pareggi esatti (x = j/8 con j dispari: 0.125, 0.375, ...), va al pari; `sum()` dei float
// e' compensata (Neumaier, da Python 3.12). Math.round(x*100)/100 differisce da entrambi.

/** `round(x, 2)` di Python: sul valore binario esatto, pareggi esatti al centesimo pari. */
export function pyRound2(x: number): number {
    if (!Number.isFinite(x)) return x;
    const a = Math.abs(x);
    const e = a * 8; // moltiplicare per 2^k e' esatto
    if (Number.isInteger(e) && e % 2 === 1) { // pareggio esatto: a*100 = n + 0.5
        const lo = Math.floor(a * 100);
        const n = lo % 2 === 0 ? lo : lo + 1;
        return Math.sign(x) * (n / 100);
    }
    return Number(x.toFixed(2)); // toFixed e' corretto sul valore binario esatto
}

/** `sum()` di Python sui float (3.12+): somma compensata alla Neumaier. */
function pySum(xs: readonly number[]): number {
    let acc = 0;
    let c = 0;
    for (const x of xs) {
        const t = acc + x;
        if (!Number.isFinite(t)) { acc = t; continue; }
        if (Math.abs(acc) >= Math.abs(x)) c += (acc - t) + x; else c += (x - t) + acc;
        acc = t;
    }
    return c !== 0 && Number.isFinite(c) ? acc + c : acc;
}

// [limite superiore, passo in centesimi] — scala dei tick Betfair (flumine CUTOFFS)
const TICK_CUTOFFS: ReadonlyArray<readonly [number, number]> = [
    [2, 1], [3, 2], [4, 5], [6, 10], [10, 20], [20, 50], [30, 100], [50, 200], [100, 500], [1000, 1000],
];

/** `get_nearest_price` di flumine (quanto usa il server): tick piu' vicino, mezzo tick in su. */
export function nearestTickPrice(price: number): number {
    if (price <= 1.01) return 1.01;
    if (price > 1000) return 1000;
    let stepCents = 1000;
    for (const [cutoff, st] of TICK_CUTOFFS) {
        if (price < cutoff) { stepCents = st; break; }
    }
    // aritmetica intera su price*1e8 (i pareggi tipo 2.01 -> 2.02 non dipendono dal float)
    const x = Math.round(price * 1e8);
    const k = 1e6 * stepCents;
    const n = Math.floor((2 * x + k) / (2 * k));
    return (n * stepCents) / 100;
}

export interface VariablePlanLeg { price: number; stake: number; profit: number }
export interface VariablePlan {
    legs: VariablePlanLeg[];
    total: number;
    bookPct: number;
    /** indice (in `input`) della prima gamba con stake negativo = pesi irrealizzabili; -1 = ok */
    negativeIndex: number;
}

/**
 * Stessa matematica di `dutch_variable` (Betfair/stream/trading/dutching.py): profitto
 * proporzionale al peso, k = T(1−Σ1/p)/Σ(w/p), s_i = round((T + k·w_i)/p_i, 2),
 * totale = round(Σs, 2), profitto_i = round(s_i·p_i − totale, 2). I prezzi sono portati al
 * tick come fa il server. `input` e' GIA' filtrato (quota > 1, peso > 0).
 */
export function dutchVariablePlan(
    input: readonly { price: number; weight: number }[],
    totalStake: number,
): VariablePlan {
    const prices = input.map(l => nearestTickPrice(l.price));
    const invSum = pySum(prices.map(p => 1 / p));
    const wpSum = pySum(input.map((l, i) => l.weight / prices[i]));
    const k = totalStake * (1 - invSum) / wpSum;
    const bookPct = pyRound2(invSum * 100);
    const stakes = input.map((l, i) => pyRound2((totalStake + k * l.weight) / prices[i]));
    const negativeIndex = stakes.findIndex(s => s < 0);
    if (negativeIndex >= 0) return { legs: [], total: 0, bookPct, negativeIndex };
    const total = pyRound2(pySum(stakes));
    return {
        legs: stakes.map((stake, i) => ({
            price: prices[i], stake, profit: pyRound2(stake * prices[i] - total),
        })),
        total, bookPct, negativeIndex: -1,
    };
}

