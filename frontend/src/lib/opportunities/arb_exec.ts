// ============================================================================
// arb_exec.ts — validazione dell'ESEGUIBILITÀ REALE di un arbitraggio sotto il
// ritardo Betfair, col motore di matching condiviso (matching.ts).
//
// Un arbitraggio è "garantito" solo se riesci a piazzare TUTTE le gambe ai prezzi
// mostrati. In-play c'è il ritardo (~8s) e le gambe stanno su mercati diversi: puoi
// riempirne una e mancarne un'altra, restando con una posizione aperta non coperta.
// Qui ogni gamba viene RI-SIMULATA come ordine taker col ritardo in-play: se anche
// una sola gamba non si abbina per (quasi) l'intero matchedStake richiesto contro il
// book che esiste DOPO il ritardo, l'arb NON è affidabile e va nascosto.
//
// Pre-match (inPlay=false → delay 0): il book usato è quello corrente → un arb reale
// passa sempre. Il filtro morde solo in-play, dove serve.
// ============================================================================
import { simulateOrder, DEFAULT_DELAY_MS, type BookSnapshot } from '@/lib/matching';
import type { Opportunity } from './types';

// Fornisce la sequenza di snapshot del book (ordinata per ts) per una selezione.
export type SnapsProvider = (marketId: string, selectionId: number) => BookSnapshot[];

/**
 * arbExecutableUnderDelay — true se OGNI gamba dell'arb si abbinerebbe per l'intero
 * `matchedStake` richiesto al book disponibile dopo il ritardo in-play.
 *
 * @param tolerance frazione minima accettata del matched richiesto (0.99 = ammette
 *                  solo il rumore numerico; sotto, la gamba è considerata non eseguibile).
 */
export function arbExecutableUnderDelay(
    opp: Opportunity,
    getSnaps: SnapsProvider,
    placedMs: number,
    inPlay: boolean,
    delayMs: number = DEFAULT_DELAY_MS,
    tolerance = 0.99,
): boolean {
    if (opp.legs.length === 0) return false;
    const effectiveTs = placedMs + (inPlay ? delayMs : 0);
    for (const l of opp.legs) {
        const required = l.matchedStake;
        if (!(required > 0)) return false;
        const snaps = getSnaps(l.marketId, l.selectionId);
        if (!snaps || snaps.length === 0) return false;
        const res = simulateOrder(
            { side: l.side, limitPrice: l.price, stake: required, placedTs: placedMs, inPlay, delayMs },
            snaps,
            effectiveTs + 1, // includi il frame attivo all'istante d'invio (post-ritardo)
        );
        if (res.matched < required * tolerance) return false;
    }
    return true;
}
