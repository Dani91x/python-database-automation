// ============================================================================
// RiskPanel.tsx — pannello RISCHIO nell'header KPI della Safe Strategy.
//
// Legge control.stats.risk (liability giornaliera vs cap, stop per perdita)
// e control.stats.opps (opportunità per tipo) scritti dal servizio. Rosso
// quando lo stop giornaliero è scattato: da quel momento nessun nuovo ingresso
// automatico, e l'utente deve vederlo a colpo d'occhio.
// ============================================================================
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { SAFE_OPP_KINDS, type SafeOppCounts, type SafeOppKind, type SafeRiskStats } from '@/lib/safeBot';
import { OPP_KIND_META } from './OpportunityGroup';

function eur(v: number | null | undefined): string {
    const n = Number(v ?? 0);
    return `${n < 0 ? '−' : ''}€${Math.abs(n).toFixed(2)}`;
}

export interface RiskPanelProps {
    risk: SafeRiskStats | null | undefined;
    /** conteggi dal servizio; se assenti si usano quelli calcolati dalla UI */
    opps: SafeOppCounts | null | undefined;
    fallbackCounts?: Record<SafeOppKind, number>;
    /** cap dai parametri (fallback quando stats.risk non porta daily_cap) */
    paramDailyCap?: number;
    paramLossStop?: number;
}

export function RiskPanel({ risk, opps, fallbackCounts, paramDailyCap, paramLossStop }: RiskPanelProps) {
    const used = Number(risk?.daily_liability ?? 0);
    const cap = Number(risk?.daily_cap ?? paramDailyCap ?? 0);
    const lossStop = risk?.daily_loss_stop ?? paramLossStop ?? null;
    const stopActive = risk?.loss_stop_active === true;
    const pctUsed = cap > 0 ? Math.max(0, Math.min(100, (used / cap) * 100)) : 0;
    const barTone = stopActive || pctUsed >= 90 ? 'bg-red-500' : pctUsed >= 70 ? 'bg-amber-400' : 'bg-emerald-500';
    const counts: Record<SafeOppKind, number> = {
        model: Number(opps?.model ?? fallbackCounts?.model ?? 0),
        anomaly: Number(opps?.anomaly ?? fallbackCounts?.anomaly ?? 0),
        combo: Number(opps?.combo ?? fallbackCounts?.combo ?? 0),
        tennis: Number(opps?.tennis ?? fallbackCounts?.tennis ?? 0),
    };

    return (
        <Card
            className={`glass-card p-3 flex-1 min-w-[260px] ${stopActive ? 'border-red-500/50' : 'border-white/10'}`}
            data-testid="risk-panel"
            data-loss-stop={stopActive ? 'active' : 'off'}
        >
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-400">
                {stopActive
                    ? <ShieldAlert className="w-3.5 h-3.5 text-red-400" aria-hidden />
                    : <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" aria-hidden />}
                Rischio giornaliero
                <Badge
                    variant="outline"
                    data-testid="loss-stop"
                    className={`ml-auto text-[10px] ${stopActive ? 'bg-red-500/20 text-red-300 border-red-500/50 animate-pulse' : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'}`}
                    title={stopActive
                        ? `stop per perdita giornaliera SCATTATO${lossStop != null ? ` (soglia ${eur(lossStop)})` : ''}: nessun nuovo ingresso automatico fino alla prossima giornata operativa`
                        : `stop per perdita giornaliera non attivo${lossStop != null ? ` (scatta sotto ${eur(lossStop)})` : ''}`}
                >
                    {stopActive ? 'STOP PERDITA' : 'stop ok'}
                </Badge>
            </div>
            <div className="mt-1 flex items-baseline gap-1.5 tabular-nums" title="liability impegnata oggi rispetto al cap giornaliero dei parametri">
                <span className={`text-xl md:text-2xl font-display font-black ${stopActive ? 'text-red-400' : 'text-white/90'}`} data-testid="risk-liability">
                    {eur(used)}
                </span>
                <span className="text-[11px] text-slate-500">/ cap {cap > 0 ? eur(cap) : '—'}</span>
                {cap > 0 && <span className="ml-auto text-[11px] text-slate-400">{pctUsed.toFixed(0)}%</span>}
            </div>
            <div
                className="mt-1 h-1.5 rounded-full bg-black/50 border border-white/10 overflow-hidden"
                role="progressbar"
                aria-label="Liability giornaliera rispetto al cap"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(pctUsed)}
            >
                <div className={`h-full transition-all duration-500 ${barTone}`} style={{ width: `${pctUsed}%` }} />
            </div>
            <div className="mt-1.5 flex items-center gap-1 flex-wrap" data-testid="risk-opp-counts">
                {SAFE_OPP_KINDS.map((k) => (
                    <Badge
                        key={k}
                        variant="outline"
                        className={`px-1.5 py-0 text-[10px] font-heading tabular-nums ${OPP_KIND_META[k].badge}`}
                        title={`${OPP_KIND_META[k].title} — ${counts[k]} in questo momento`}
                    >
                        {OPP_KIND_META[k].label} {counts[k]}
                    </Badge>
                ))}
            </div>
        </Card>
    );
}

export default RiskPanel;
