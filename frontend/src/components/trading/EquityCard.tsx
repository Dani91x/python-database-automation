// ============================================================================
// EquityCard.tsx — card UNICA della curva di equity.
//
// Certificazione 12/09: la stessa curva aveva DUE nomi nella stessa pagina —
// «Equity curve · P&L cumulato regolato» qui e «Equity per giornata · P&L
// cumulato realizzato» nel pannello performance — e nessuna delle due diceva
// che cosa c'è sull'asse né da dove parte. Titolo, sottotitolo e legenda
// dell'asse sono ora UNO SOLO (EQUITY_TITLE / EQUITY_AXIS_NOTE), usati anche
// dal PerformancePanel.
// ============================================================================
import { TrendingUp } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { EquityCurve, type EquityPoint } from './EquityCurve';

/** titolo unico della curva: una sola parola per "realizzato" */
export const EQUITY_TITLE = 'Equity · P&L cumulato realizzato';
/** che cosa c'è sull'asse e da dove parte: identico ovunque */
export const EQUITY_AXIS_NOTE =
    'asse verticale = € realizzati sommati, si parte da 0,00 € all’inizio dell’ambito; '
    + 'asse orizzontale = tempo (primo e ultimo passo etichettati); ogni gradino è un regolamento';

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
            <div className="flex items-center gap-2 text-sm text-slate-300 mb-1" title={EQUITY_AXIS_NOTE}>
                <TrendingUp className="w-4 h-4 text-primary" aria-hidden />
                {EQUITY_TITLE}
                {scope && <span className="text-[11px] text-slate-500">· {scope}</span>}
            </div>
            <div className="text-[10px] text-slate-500 mb-2" data-testid="equity-axis-note">{EQUITY_AXIS_NOTE}</div>
            <EquityCurve series={series} emptyLabel={emptyLabel} label={label} />
        </Card>
    );
}

export default EquityCard;
