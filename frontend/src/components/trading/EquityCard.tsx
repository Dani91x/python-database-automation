// ============================================================================
// EquityCard.tsx — card UNICA della curva di equity.
// Titolo e sottotitolo identici in tutte le sezioni ("giornata …" / "tutte …"),
// e una sola implementazione del grafico (EquityCurve): la copia SVG che viveva
// dentro Omega.tsx è stata rimossa.
// ============================================================================
import { TrendingUp } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { EquityCurve, type EquityPoint } from './EquityCurve';

export function EquityCard({ series, scope, emptyLabel, label = 'Equity curve', testId = 'equity-card' }: {
    series: EquityPoint[];
    /** ambito della curva: "giornata 10 settembre" o "tutte le partite caricate" */
    scope?: string;
    emptyLabel?: string;
    /** aria-label del grafico */
    label?: string;
    testId?: string;
}) {
    return (
        <Card className="glass-card border-white/10 p-4" data-testid={testId}>
            <div className="flex items-center gap-2 text-sm text-slate-300 mb-2">
                <TrendingUp className="w-4 h-4 text-primary" aria-hidden />
                Equity curve · P&amp;L cumulato regolato
                {scope && <span className="text-[11px] text-slate-500">· {scope}</span>}
            </div>
            <EquityCurve series={series} emptyLabel={emptyLabel} label={label} />
        </Card>
    );
}

export default EquityCard;
