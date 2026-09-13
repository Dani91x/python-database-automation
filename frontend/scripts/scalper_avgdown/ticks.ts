// Griglia tick Betfair come ARRAY DI INDICI (1.01 → 1000): tutti i confronti di
// prezzo del motore scalper sono confronti di interi, mai float (vedi dossier §1).
import { roundToTick, tickDown, tickUp } from '../../src/lib/matching';

export const TICKS: number[] = (() => {
    const out: number[] = [];
    let p = 1.01;
    while (p < 1000) {
        out.push(p);
        const next = tickUp(p, 1);
        if (next <= p) break;
        p = next;
    }
    out.push(1000);
    return out;
})();

const IDX = new Map<string, number>(TICKS.map((p, i) => [p.toFixed(2), i]));

/** Indice del tick per una quota (arrotondata al tick valido). */
export function tickIdx(price: number): number {
    const i = IDX.get(roundToTick(price).toFixed(2));
    if (i === undefined) throw new Error(`prezzo fuori griglia: ${price}`);
    return i;
}

export { roundToTick, tickDown, tickUp };
