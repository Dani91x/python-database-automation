// ============================================================================
// ExitBadge.tsx — badge dell'USCITA AUTOMATICA di una posizione.
// Legge meta.exit_kind / meta.exit_reason scritti dal servizio sulla gamba
// (apertura o chiusura): "Uscita: profitto / perdita / tempo / rosso /
// obbligatoria". Il motivo esteso va nel tooltip. Niente meta → non renderizza.
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { exitInfo, type ExitInfo, type ExitKind } from '@/lib/dailyHistory';

const EXIT_CLS: Record<ExitKind, string> = {
    profit: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    loss: 'bg-red-500/15 text-red-300 border-red-500/40',
    time: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    red_card: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
    forced: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
    manual: 'bg-violet-500/15 text-violet-300 border-violet-500/40',
    greenup: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50',
    other: 'bg-slate-500/15 text-slate-300 border-slate-500/40',
};

export function ExitBadge({ meta, info, className = '' }: {
    meta?: Record<string, unknown> | null;
    /** già calcolato (es. tradeExit su apertura+chiusure) */
    info?: ExitInfo | null;
    className?: string;
}) {
    const e = info ?? exitInfo(meta);
    if (!e) return null;
    return (
        <Badge
            variant="outline"
            data-testid="exit-badge"
            data-exit-kind={e.kind}
            className={`px-1.5 py-0 text-[10px] whitespace-nowrap ${EXIT_CLS[e.kind]} ${className}`}
            title={e.reason ?? e.label}
        >
            {e.label}
        </Badge>
    );
}

export default ExitBadge;
