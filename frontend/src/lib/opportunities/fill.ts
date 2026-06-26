// ============================================================================
// fill.ts — modello di RIEMPIMENTO REALISTICO + netting commissioni + delay.
//
// PRINCIPIO ANTI-OVERFITTING: su Betfair NON puoi assumere il fill completo.
// Lo stake realmente piazzabile ORA è limitato dalla LIQUIDITÀ disponibile
// ai livelli del book che sono "buoni almeno quanto" il prezzo target.
//
// SEMANTICA LATO/LADDER (coerente con live.ts):
//   - per PUNTARE (back) una selezione prendi il denaro "disponibile per bancare"
//     => livelli `ladder.back`. Accetti il tuo prezzo o MEGLIO: per chi banca
//     "meglio" = quota PIÙ ALTA, quindi i livelli con price >= target.
//   - per LAYARE una selezione prendi il denaro "disponibile per layare"
//     => livelli `ladder.lay`. Per chi laya "meglio" = quota PIÙ BASSA, quindi
//     i livelli con price <= target.
//
//   La `size` ai livelli è espressa in STAKE del backer (£), quindi la sommiamo
//   direttamente come stake piazzabile.
// ============================================================================

export type FillSide = 'back' | 'lay';

// Tolleranza per confronti tra quote in virgola mobile (le quote Betfair hanno
// tick discreti, ma i prezzi possono arrivare con rumore numerico).
const PRICE_EPS = 1e-9;

// Ritardo in-play Betfair (5-8s): default 6s. Le bet piazzate "ora" si matchano
// contro il book con questo ritardo → riduce la certezza del fill teorico.
export const DEFAULT_DELAY_SEC = 6;

/**
 * matchedStake — stake REALISTICAMENTE piazzabile ORA per uno stake desiderato
 * a un prezzo target, dati i livelli del book.
 *
 * = somma delle `size` dei livelli "buoni almeno quanto" il target
 *     (back: price >= target ; lay: price <= target)
 *   limitata (cap) allo stake desiderato.
 *
 * @param levels  livelli [[price,size]...] (back per side='back', lay per side='lay')
 * @param targetPrice prezzo minimo accettabile (back) / massimo accettabile (lay)
 * @param desiredStake stake che si vorrebbe piazzare (£)
 * @param side 'back' | 'lay' (default 'back')
 */
export function matchedStake(
    levels: ReadonlyArray<readonly [number, number]> | undefined,
    targetPrice: number,
    desiredStake: number,
    side: FillSide = 'back',
): number {
    if (!levels || levels.length === 0) return 0;
    if (!Number.isFinite(desiredStake) || desiredStake <= 0) return 0;
    if (!Number.isFinite(targetPrice) || targetPrice <= 0) return 0;

    let available = 0;
    for (const lvl of levels) {
        const price = lvl?.[0];
        const size = lvl?.[1];
        if (typeof price !== 'number' || !Number.isFinite(price)) continue;
        if (typeof size !== 'number' || !Number.isFinite(size) || size <= 0) continue;
        const good = side === 'back'
            ? price >= targetPrice - PRICE_EPS
            : price <= targetPrice + PRICE_EPS;
        if (good) available += size;
    }
    return Math.min(available, desiredStake);
}

/**
 * fillRatio — frazione [0..1] dello stake desiderato che si riesce a piazzare.
 * Utile per stimare la confidence di un'opportunità (liquidità sufficiente?).
 */
export function fillRatio(
    levels: ReadonlyArray<readonly [number, number]> | undefined,
    targetPrice: number,
    desiredStake: number,
    side: FillSide = 'back',
): number {
    if (!Number.isFinite(desiredStake) || desiredStake <= 0) return 0;
    return matchedStake(levels, targetPrice, desiredStake, side) / desiredStake;
}

/**
 * netWin — netting commissioni Betfair.
 * Betfair preleva la commissione SOLO sulle vincite NETTE di mercato:
 *   profitto > 0 → profitto * (1 - commission)
 *   profitto <= 0 → invariato (nessuna commissione sulle perdite).
 */
export function netWin(grossProfit: number, commission: number): number {
    return grossProfit > 0 ? grossProfit * (1 - commission) : grossProfit;
}
