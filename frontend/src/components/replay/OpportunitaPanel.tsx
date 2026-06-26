// ============================================================================
// OpportunitaPanel — mostra, per la snapshot CORRENTE del replay, le opportunità
// rilevate dal motore (src/lib/opportunities) come CARD AMICHEVOLI pensate per
// utenti NON tecnici:
//   • badge colorato per RISCHIO (VERDE arb "Rischio ~zero", GIALLO low
//     "Rischio basso", ARANCIO directional "Direzionale");
//   • una riga di ISTRUZIONE in italiano semplice (BANCA/PUNTA … → guadagno …);
//   • profitto in £ e %, barra di confidenza;
//   • "Dettagli" espandibile: tabella gambe + spiegazione + piano d'uscita.
// Ordina gli arbitraggi per primi. Vuoto → messaggio chiaro.
// ============================================================================
import { useState } from 'react';
import { Card } from '@/components/ui/card';
import {
    ShieldCheck, TrendingUp, Gauge, ChevronDown, ChevronUp, Sparkles, AlertTriangle,
} from 'lucide-react';
import type { Opportunity, RiskTier } from '@/lib/opportunities/types';
import { formatGbp } from '@/lib/replay-pnl';

// Stile per tier di rischio (allineato al design system: emerald=primary, gold=secondary).
interface TierStyle {
    label: string;
    sub: string;
    badge: string;   // classi badge
    bar: string;     // colore barra confidenza
    ring: string;    // bordo card
    Icon: typeof ShieldCheck;
}
const TIER_STYLE: Record<RiskTier, TierStyle> = {
    arb: {
        label: 'Rischio ~zero',
        sub: 'Profitto bloccato qualunque esito',
        badge: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
        bar: 'bg-emerald-400',
        ring: 'border-emerald-500/30',
        Icon: ShieldCheck,
    },
    low: {
        label: 'Rischio basso',
        sub: 'Quasi sicuro, con rischio residuo dichiarato',
        badge: 'bg-secondary/15 text-secondary border-secondary/40',
        bar: 'bg-secondary',
        ring: 'border-secondary/30',
        Icon: Gauge,
    },
    directional: {
        label: 'Direzionale',
        sub: 'Scommessa sul movimento: profitto potenziale',
        badge: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
        bar: 'bg-orange-400',
        ring: 'border-orange-500/30',
        Icon: TrendingUp,
    },
};
const TIER_ORDER: Record<RiskTier, number> = { arb: 0, low: 1, directional: 2 };

function ConfidenceBar({ value, color }: { value: number; color: string }) {
    const pct = Math.max(0, Math.min(1, value)) * 100;
    return (
        <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">Affidabilità</span>
            <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[10px] tabular-nums text-muted-foreground shrink-0 w-8 text-right">{Math.round(pct)}%</span>
        </div>
    );
}

function OppCard({ opp }: { opp: Opportunity }) {
    const [open, setOpen] = useState(false);
    const st = TIER_STYLE[opp.tier];
    const Icon = st.Icon;

    return (
        <Card className={`glass-card ${st.ring} overflow-hidden`}>
            {/* header: badge rischio + profitto */}
            <div className="px-4 py-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-black uppercase tracking-wider ${st.badge}`}>
                        <Icon className="w-3.5 h-3.5" /> {st.label}
                    </span>
                    <div className="font-heading font-bold text-sm text-white mt-1.5 truncate">{opp.title}</div>
                    <div className="text-[11px] text-muted-foreground">{st.sub}</div>
                </div>
                <div className="text-right shrink-0">
                    <div className={`font-display font-black text-lg tabular-nums ${opp.profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {opp.profit >= 0 ? '+' : ''}{formatGbp(opp.profit)}
                    </div>
                    <div className="text-[11px] text-muted-foreground tabular-nums">
                        {opp.profitPct >= 0 ? '+' : ''}{opp.profitPct.toFixed(2)}%
                    </div>
                </div>
            </div>

            {/* istruzione in italiano semplice */}
            <div className="px-4 pb-2">
                <p className="text-sm text-white/90 leading-snug">{opp.instruction}</p>
            </div>

            {/* confidenza */}
            <div className="px-4 pb-3">
                <ConfidenceBar value={opp.confidence} color={st.bar} />
            </div>

            {/* toggle dettagli */}
            <button
                onClick={() => setOpen(o => !o)}
                className="w-full px-4 py-2 border-t border-white/5 flex items-center justify-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground hover:text-white hover:bg-white/[0.03] transition-colors"
            >
                {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                {open ? 'Nascondi dettagli' : 'Dettagli'}
            </button>

            {open && (
                <div className="px-4 py-3 border-t border-white/5 space-y-3 bg-black/20">
                    {/* tabella gambe */}
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead>
                                <tr className="text-[9px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left px-1 py-1 font-medium">Azione</th>
                                    <th className="text-left px-1 py-1 font-medium">Selezione</th>
                                    <th className="text-left px-1 py-1 font-medium">Mercato</th>
                                    <th className="text-right px-1 py-1 font-medium">Quota</th>
                                    <th className="text-right px-1 py-1 font-medium">Importo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {opp.legs.map((l, i) => {
                                    const back = l.side === 'back';
                                    const partial = l.matchedStake + 1e-9 < l.stake;
                                    return (
                                        <tr key={i} className="border-b border-white/5">
                                            <td className="px-1 py-1.5">
                                                <span className={`font-black text-[10px] uppercase ${back ? 'text-blue-300' : 'text-pink-300'}`}>
                                                    {back ? 'PUNTA' : 'BANCA'}
                                                </span>
                                            </td>
                                            <td className="px-1 py-1.5 text-white truncate max-w-[110px]">{l.selectionName}</td>
                                            <td className="px-1 py-1.5 text-muted-foreground truncate max-w-[110px]">{l.marketName}</td>
                                            <td className="px-1 py-1.5 text-right tabular-nums text-white/80">{l.price.toFixed(2)}</td>
                                            <td className="px-1 py-1.5 text-right tabular-nums">
                                                <span className="text-white">{formatGbp(l.matchedStake)}</span>
                                                {partial && (
                                                    <span className="block text-[9px] text-amber-400">abbinato {formatGbp(l.matchedStake)} di {formatGbp(l.stake)}</span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>

                    {/* spiegazione */}
                    <div className="flex gap-2 text-[11px] text-muted-foreground leading-relaxed">
                        <Sparkles className="w-3.5 h-3.5 shrink-0 mt-0.5 text-primary/70" />
                        <p>{opp.explanation}</p>
                    </div>

                    {/* piano d'uscita */}
                    {opp.exitPlan && (
                        <div className="flex gap-2 text-[11px] text-amber-200/80 leading-relaxed">
                            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-400/80" />
                            <p>{opp.exitPlan}</p>
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
}

export interface OpportunitaPanelProps {
    opportunities: Opportunity[];
}

export function OpportunitaPanel({ opportunities }: OpportunitaPanelProps) {
    // ordina: arb → low → directional, poi profitto decrescente.
    // (runDetectors ordina già così a monte: questo re-sort è DIFENSIVO e rende il
    //  componente indipendente dall'ordine della prop in ingresso.)
    const sorted = [...opportunities].sort((a, b) => {
        const t = TIER_ORDER[a.tier] - TIER_ORDER[b.tier];
        return t !== 0 ? t : b.profit - a.profit;
    });

    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-white/5 font-heading font-bold text-sm flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" /> Opportunità
                {sorted.length > 0 && (
                    <span className="text-muted-foreground font-normal">({sorted.length})</span>
                )}
            </div>

            {sorted.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground text-sm">
                    Nessuna opportunità in questo momento.
                </div>
            ) : (
                <div className="p-3 space-y-3">
                    {sorted.map(o => <OppCard key={o.id} opp={o} />)}
                </div>
            )}
        </Card>
    );
}
