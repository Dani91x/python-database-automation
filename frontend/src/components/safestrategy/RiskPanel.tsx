// ============================================================================
// RiskPanel.tsx — pannello RISCHIO nella riga KPI della Safe Strategy.
//
// UNA sola fonte per i numeri della giornata: `control.stats.risk` del servizio
// e, quando manca (bot fermo / migrazione non applicata), gli `aggregates`
// della RPC — che usano lo STESSO giorno di PIAZZAMENTO dei KPI, del tab Trade
// e dello storico (audit C-01). Prima il pannello poteva mostrare un numero
// diverso dai KPI per la stessa giornata.
//
// Rosso quando lo stop giornaliero è scattato: da quel momento nessun nuovo
// ingresso automatico, e l'utente deve vederlo a colpo d'occhio.
// ============================================================================
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { fmtMoney, fmtPctPoints } from '@/lib/format';
import { T } from '@/lib/tradeStatus';
import { normalizeLossStop, SAFE_OPP_KINDS, type SafeOppCounts, type SafeOppKind, type SafeRiskStats } from '@/lib/safeBot';
import { OPP_KIND_META } from './OpportunityGroup';

export interface RiskPanelProps {
    risk: SafeRiskStats | null | undefined;
    /** conteggi dal servizio; se assenti si usano quelli calcolati dalla UI */
    opps: SafeOppCounts | null | undefined;
    fallbackCounts?: Record<SafeOppKind, number>;
    /** cap dai parametri (fallback quando stats.risk non porta daily_cap) */
    paramDailyCap?: number;
    paramLossStop?: number;
    /** capitale IMPEGNATO oggi (base dei cap): aggregates.day_liability */
    dayLiability?: number | null;
    /** rischio VIVO adesso (liability delle posizioni aperte) */
    openLiability?: number | null;
    /** di cui in VERIFICA su Betfair (riserve a esito ignoto): H-03 */
    reconcilingLiability?: number | null;
    /** etichetta della giornata operativa: lo stesso giorno dei KPI (C-01) */
    dayLabel?: string;
    /** true = i conteggi mostrati sono quelli calcolati dalla UI (stessi dei tab) */
    countsFromUi?: boolean;
    /** true = senza `safe_strategy_bot_v2.sql` l'impegnato di giornata NON viene
     *  dal servizio: e' STIMATO dal client sulle righe caricate. Va detto, mai
     *  mostrato come se fosse il numero del servizio. */
    dayFromUi?: boolean;
}

export function RiskPanel({
    risk, opps, fallbackCounts, paramDailyCap, paramLossStop,
    dayLiability, openLiability, reconcilingLiability, dayLabel, countsFromUi, dayFromUi,
}: RiskPanelProps) {
    // "impegnato oggi" = capitale usato nella giornata (base dei cap di rischio);
    // "rischio aperto" = quello ancora a mercato ADESSO. Sono due cose diverse:
    // mescolarle faceva leggere un numero per un altro (contratto backend 11/09).
    const used = Number(risk?.daily_liability ?? dayLiability ?? 0);
    const open = openLiability == null ? null : Number(openLiability);
    const cap = Number(risk?.daily_cap ?? paramDailyCap ?? 0);
    // il servizio legge lo stop in valore assoluto: 50 e −50 sono −50 €
    const lossStop = normalizeLossStop(risk?.daily_loss_stop ?? paramLossStop ?? null);
    const stopActive = risk?.loss_stop_active === true;
    const reconciling = Number(risk?.reconciling_liability ?? reconcilingLiability ?? 0);
    const pctUsed = cap > 0 ? Math.max(0, Math.min(100, (used / cap) * 100)) : 0;
    const barTone = stopActive || pctUsed >= 90 ? 'bg-red-500' : pctUsed >= 70 ? 'bg-amber-400' : 'bg-emerald-500';
    // M-21: se il servizio non pubblica i conteggi si usano quelli della UI —
    // gli STESSI che contano i tab, così i due numeri non divergono mai
    const counts: Record<SafeOppKind, number> = {
        model: Number(opps?.model ?? fallbackCounts?.model ?? 0),
        anomaly: Number(opps?.anomaly ?? fallbackCounts?.anomaly ?? 0),
        combo: Number(opps?.combo ?? fallbackCounts?.combo ?? 0),
        tennis: Number(opps?.tennis ?? fallbackCounts?.tennis ?? 0),
    };
    const oppSource = opps == null || countsFromUi ? 'calcolate da questa schermata' : 'pubblicate dal servizio';

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
                        ? `stop per perdita giornaliera SCATTATO${lossStop != null ? ` (soglia ${fmtMoney(lossStop)})` : ''}: nessun nuovo ingresso automatico fino alla prossima giornata operativa`
                        : `stop per perdita giornaliera non attivo${lossStop != null ? ` (scatta sotto ${fmtMoney(lossStop)})` : ''}`}
                >
                    {stopActive ? 'STOP PERDITA' : 'stop ok'}
                </Badge>
            </div>
            <div className="mt-1 flex items-baseline gap-1.5 tabular-nums" title={`capitale IMPEGNATO nella ${T.operatingDay}${dayLabel ? ` (${dayLabel})` : ''} rispetto al cap giornaliero: e' la base dei cap di rischio, non il rischio ancora vivo`}>
                <span className={`text-xl md:text-2xl font-display font-black ${stopActive ? 'text-red-400' : 'text-white/90'}`} data-testid="risk-liability">
                    {fmtMoney(used)}
                </span>
                <span className="text-[11px] text-slate-500">impegnato oggi / cap {cap > 0 ? fmtMoney(cap) : '—'}</span>
                {cap > 0 && <span className="ml-auto text-[11px] text-slate-400">{fmtPctPoints(pctUsed, 0)}</span>}
            </div>
            {open != null && (
                <div className="text-[10px] text-orange-300/90" data-testid="risk-open-liability" title={`${T.openLiability}: quello che e' ancora a rischio ADESSO sulle posizioni vive`}>
                    rischio aperto ora <b>{fmtMoney(open)}</b>
                </div>
            )}
            {dayLabel && (
                <div className="text-[10px] text-slate-500" data-testid="risk-day">
                    {T.operatingDay} {dayLabel} · Europe/Rome
                </div>
            )}
            {dayFromUi && (
                <div
                    className="text-[10px] text-amber-300/90"
                    data-testid="risk-day-estimated"
                    title="la RPC vecchia non torna i contatori di giornata: l'impegnato e' sommato sulle righe caricate da questa schermata, non su tutta la giornata operativa"
                >
                    ⚠ impegnato stimato dal client (applica safe_strategy_bot_v2.sql)
                </div>
            )}
            {reconciling > 0 && (
                <div className="text-[10px] text-fuchsia-300/90" data-testid="risk-reconciling" title="riserve a esito IGNOTO: l'ordine potrebbe essere vivo su Betfair, la liability va considerata impegnata">
                    di cui in verifica su Betfair <b>{fmtMoney(reconciling)}</b>
                </div>
            )}
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
            <div className="mt-1.5 flex items-center gap-1 flex-wrap" data-testid="risk-opp-counts" data-source={opps == null || countsFromUi ? 'ui' : 'service'}>
                {SAFE_OPP_KINDS.map((k) => (
                    <Badge
                        key={k}
                        variant="outline"
                        className={`px-1.5 py-0 text-[10px] font-heading tabular-nums ${OPP_KIND_META[k].badge}`}
                        title={`${OPP_KIND_META[k].title} — ${counts[k]} in questo momento (${oppSource})`}
                    >
                        {OPP_KIND_META[k].label} {counts[k]}
                    </Badge>
                ))}
            </div>
        </Card>
    );
}

export default RiskPanel;
