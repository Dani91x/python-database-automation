// ============================================================================
// StatTile.tsx / KpiRow.tsx — KPI unici del design system.
// Misure e font sono quelli di Safe/Mike (p-3, text-xl md:text-2xl): Omega
// aveva tile piu' grandi, la riga KPI dei tre bot ora si legge allo stesso modo.
// ============================================================================
import type { ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

export type StatTone = 'pos' | 'neg' | 'plain' | 'gold' | 'danger' | 'teal';

const TONE_CLS: Record<StatTone, string> = {
    pos: 'text-emerald-400',
    neg: 'text-red-400',
    plain: 'text-white/90',
    gold: 'text-secondary',
    danger: 'text-orange-400',
    teal: 'text-teal-300',
};

/** tono automatico dal segno di un valore monetario */
export function toneOf(v: number | null | undefined): StatTone {
    return Number(v ?? 0) >= 0 ? 'pos' : 'neg';
}

export function StatTile({ label, value, tone = 'plain', icon, sub, testId }: {
    label: string;
    value: ReactNode;
    tone?: StatTone;
    icon?: ReactNode;
    sub?: ReactNode;
    testId?: string;
}) {
    return (
        <Card className="glass-card border-white/10 p-3 flex-1 min-w-[130px]" data-testid={testId ?? 'stat-tile'}>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-400">
                {icon}{label}
            </div>
            <div className={`mt-0.5 text-xl md:text-2xl font-display font-black tabular-nums ${TONE_CLS[tone]}`}>{value}</div>
            {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
        </Card>
    );
}

/** Riga di KPI: stesso gap e stesso skeleton di caricamento in tutte le pagine. */
export function KpiRow({ loading, tiles, children }: {
    loading?: boolean;
    /** numero di skeleton da mostrare durante il caricamento (default 6) */
    tiles?: number;
    children?: ReactNode;
}) {
    if (loading) {
        return (
            <div className="flex flex-wrap gap-3" data-testid="kpi-row" data-loading="1">
                {Array.from({ length: tiles ?? 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-[74px] flex-1 min-w-[130px]" />
                ))}
            </div>
        );
    }
    return <div className="flex flex-wrap gap-3" data-testid="kpi-row">{children}</div>;
}

export default StatTile;
