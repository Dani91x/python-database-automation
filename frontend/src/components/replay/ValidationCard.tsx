// ============================================================================
// ValidationCard — card "Validazione" (collassabile) che mostra il Report
// dell'harness (src/lib/opportunities/validate.ts) per la partita caricata:
// quante opportunità sono state trovate, quanti ARBITRAGGI sono risultati
// realmente ESEGUIBILI (liquidità presente + prezzo che regge per il ritardo
// in-play), la % media e la ripartizione per fase. Dà all'utente la prova che
// il motore è stato validato su dati reali.
// ============================================================================
import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { BadgeCheck, ChevronDown, ChevronUp } from 'lucide-react';
import type { Report } from '@/lib/opportunities/validate';

const PHASE_LABEL: Record<string, string> = {
    pre: 'Pre-partita',
    '1T': '1° tempo',
    '2T': '2° tempo',
    late: 'Finale',
};

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
    return (
        <div className="rounded-lg bg-black/30 border border-white/5 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
            <div className={`font-display font-black text-lg tabular-nums ${accent ?? 'text-white'}`}>{value}</div>
        </div>
    );
}

export function ValidationCard({ report }: { report: Report }) {
    const [open, setOpen] = useState(false);

    const arbExecPct = report.arb.total > 0
        ? Math.round((report.arb.executable / report.arb.total) * 100)
        : 0;

    const phases = Object.entries(report.arb.executableByPhase)
        .sort((a, b) => b[1] - a[1]);

    return (
        <Card className="glass-card border-primary/20 overflow-hidden">
            <button
                onClick={() => setOpen(o => !o)}
                className="w-full px-4 py-3 flex items-center justify-between gap-2 hover:bg-white/[0.03] transition-colors"
            >
                <span className="flex items-center gap-2 font-heading font-bold text-sm">
                    <BadgeCheck className="w-4 h-4 text-primary" /> Validazione su dati reali
                </span>
                <span className="flex items-center gap-2">
                    <span className={`text-[11px] tabular-nums ${report.arb.executable > 0 ? 'text-emerald-300' : 'text-muted-foreground'}`}>
                        {report.arb.executable} arb eseguibili
                    </span>
                    {open ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                </span>
            </button>

            {open && (
                <div className="px-4 pb-4 pt-1 space-y-3 border-t border-white/5">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        <Stat label="Snapshot analizzati" value={String(report.totalSnapshots)} />
                        <Stat label="Opportunità totali" value={String(report.totalOpportunities)} />
                        <Stat label="Arbitraggi eseguibili" value={`${report.arb.executable}/${report.arb.total}`} accent="text-emerald-400" />
                        <Stat label="% media (arb)" value={`${report.arb.avgProfitPct.toFixed(2)}%`} accent="text-emerald-400" />
                    </div>

                    {/* riepilogo eseguibili vs teoriche */}
                    <div className="text-[11px] text-muted-foreground leading-relaxed">
                        Su <strong className="text-white">{report.totalOpportunities}</strong> opportunità rilevate,
                        {' '}<strong className="text-emerald-300">{report.executable}</strong> sono risultate
                        ESEGUIBILI (liquidità sufficiente e prezzo che regge il ritardo in-play di {report.delaySec}s),
                        {' '}<strong className="text-white">{report.theoretical}</strong> solo teoriche.
                        {report.arb.total > 0 && (
                            <> Arbitraggi eseguibili: <strong className="text-emerald-300">{arbExecPct}%</strong> del totale.</>
                        )}
                    </div>

                    {/* arbitraggi eseguibili per fase */}
                    {phases.length > 0 && (
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                                Arbitraggi eseguibili per fase
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {phases.map(([ph, n]) => (
                                    <span key={ph} className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-[11px]">
                                        <span className="text-muted-foreground">{PHASE_LABEL[ph] ?? ph}</span>
                                        <span className="font-bold tabular-nums text-emerald-300">{n}</span>
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* distribuzione profitto */}
                    {report.profit.count > 0 && (
                        <div className="text-[11px] text-muted-foreground">
                            Profitto (£): min {report.profit.min.toFixed(2)} · mediana {report.profit.median.toFixed(2)} · max {report.profit.max.toFixed(2)}
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
}
