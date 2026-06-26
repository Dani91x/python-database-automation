// ============================================================================
// engine.ts — orchestratore dei detector.
// runDetectors: concatena gli output, filtra le ARB sotto soglia, ordina per
// tier (arb > low > directional) e profitto decrescente, dedup per type+legs.
// ============================================================================
import type { Detector, Opportunity, OppConfig, RiskTier, Snapshot, Leg } from './types';

// Config di default del motore.
export const DEFAULT_OPP_CONFIG: OppConfig = {
    stake: 100,
    minProfitPct: 0.5,
    commission: 0.05,
    delaySec: 6,
};

// Ordine di priorità dei tier (più basso = più in alto in lista).
export const TIER_ORDER: Record<RiskTier, number> = {
    arb: 0,
    low: 1,
    directional: 2,
};

// Firma canonica di una gamba (per dedup): mercato|selezione|lato|prezzo.
function legSig(l: Leg): string {
    return `${l.marketId}:${l.selectionId}:${l.side}:${l.price}`;
}

// Firma canonica di un'opportunità: type + gambe ordinate (indipendente
// dall'ordine in cui il detector le ha emesse).
export function opportunitySignature(o: Opportunity): string {
    const legs = o.legs.map(legSig).sort();
    return `${o.type}|${legs.join('|')}`;
}

/**
 * runDetectors — esegue i detector e produce la lista finale ordinata e deduplicata.
 *
 * 1. concat di tutti gli output
 * 2. filtro: per tier 'arb' tieni solo profitPct >= minProfitPct (gli altri tier
 *    passano: low/directional non sono arbitraggi garantiti)
 * 3. ordina per tier (arb>low>directional), poi profit desc
 * 4. dedup per (type + firma gambe), tenendo la PRIMA occorrenza (già la migliore
 *    dopo l'ordinamento)
 */
export function runDetectors(
    snap: Snapshot,
    detectors: Detector[],
    cfg: OppConfig = DEFAULT_OPP_CONFIG,
): Opportunity[] {
    const all: Opportunity[] = [];
    for (const det of detectors) {
        const res = det(snap, cfg);
        if (res && res.length) all.push(...res);
    }

    const filtered = all.filter((o) =>
        o.tier === 'arb' ? o.profitPct >= cfg.minProfitPct : true,
    );

    filtered.sort((a, b) => {
        const t = TIER_ORDER[a.tier] - TIER_ORDER[b.tier];
        if (t !== 0) return t;
        return b.profit - a.profit;
    });

    const seen = new Set<string>();
    const out: Opportunity[] = [];
    for (const o of filtered) {
        const sig = opportunitySignature(o);
        if (seen.has(sig)) continue;
        seen.add(sig);
        out.push(o);
    }
    return out;
}
