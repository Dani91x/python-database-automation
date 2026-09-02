// ============================================================================
// variantStyles.ts — stile visivo delle 4 strategie SAFE STRATEGY.
// Convenzione colori del repo: back = sky, lay = rose. Ogni strategia ha un
// colore FISSO così l'occhio la riconosce a colpo d'occhio anche con tanti
// segnali contemporanei.
// ============================================================================
import type { SideId, VariantId, VariantState } from '@/lib/safeStrategy';

export interface VariantStyle {
    /** etichetta breve per chip/badge */
    chipLabel: (subId?: SideId) => string;
    /** classi del badge variante */
    badge: string;
    /** classe bordo sinistro della SignalCard */
    edge: string;
}

export const VARIANT_STYLE: Record<VariantId, VariantStyle> = {
    base: {
        chipLabel: () => 'BASE',
        badge: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
        edge: 'border-l-rose-400',
    },
    esatto: {
        chipLabel: (subId) => (subId === 'away' ? 'R.E. OSPITE' : 'R.E. CASA'),
        badge: 'bg-violet-500/15 text-violet-300 border-violet-500/40',
        edge: 'border-l-violet-400',
    },
    punta: {
        chipLabel: () => 'PUNTA',
        badge: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
        edge: 'border-l-sky-400',
    },
    tennis: {
        chipLabel: () => 'TENNIS',
        badge: 'bg-secondary/15 text-secondary border-secondary/40',
        edge: 'border-l-secondary',
    },
};

/** pallino di stato per i chip delle partite monitorate. */
export function stateDotClass(state: VariantState): string {
    switch (state) {
        case 'signal':
            return 'bg-emerald-400 animate-pulse';
        case 'nd':
            return 'bg-amber-400/80';
        default:
            return 'bg-white/20';
    }
}

/** classi lato operazione (convenzione repo: back=sky, lay=rose). */
export function sideBadgeClass(side: 'BACK' | 'LAY' | null): string {
    if (side === 'BACK') return 'bg-sky-500/15 text-sky-300 border-sky-500/40';
    if (side === 'LAY') return 'bg-rose-500/15 text-rose-300 border-rose-500/40';
    return 'bg-white/5 text-muted-foreground border-white/10';
}
