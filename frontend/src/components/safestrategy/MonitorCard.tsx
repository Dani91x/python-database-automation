// ============================================================================
// MonitorCard.tsx — riga di UNA partita monitorata da SAFE STRATEGY.
//
// Vista compatta: partita + stato live + un chip per strategia col pallino
// (verde pulsante = segnale, ambra = dato mancante, spento = condizioni non
// soddisfatte). Espandendo si vede la checklist completa condizione-per-
// condizione: l'utente capisce subito COSA manca perché scatti il segnale.
// ============================================================================
import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';
import type { SideId, VariantEvaluation } from '@/lib/safeStrategy';
import { VARIANT_STYLE, stateDotClass } from './variantStyles';

interface Props {
    eventId: string;
    marketId: string | null;
    sport: 'calcio' | 'tennis';
    title: string;
    /** riga di contesto live (es. "58′ · 1-0 · in-play" / "set 1-0 · game 3-2") */
    liveLine: string;
    inplay: boolean;
    evaluations: { evaluation: VariantEvaluation; subId?: SideId }[];
    /** nota diagnostica (es. mismatch nomi selezioni → quote n/d) */
    dataNote?: string | null;
}

function checkIcon(ok: boolean | null): { glyph: string; cls: string } {
    if (ok === true) return { glyph: '✓', cls: 'text-emerald-400' };
    if (ok === false) return { glyph: '✕', cls: 'text-rose-400' };
    return { glyph: '—', cls: 'text-amber-300/80' };
}

export function MonitorCard({ eventId, marketId, sport, title, liveLine, inplay, evaluations, dataNote }: Props) {
    const [open, setOpen] = useState(false);
    return (
        <div className="glass-card rounded-xl border border-white/10 p-3">
            <div className="flex items-center gap-3 flex-wrap">
                <div className="min-w-0">
                    <div className="font-heading font-bold text-sm text-white truncate">{title}</div>
                    <div className="text-[11px] text-muted-foreground font-mono tabular-nums">
                        {liveLine}
                        {!inplay && <span className="ml-2 uppercase">non in-play</span>}
                    </div>
                    {dataNote && (
                        <div className="text-[11px] text-amber-300/90 mt-0.5">⚠ {dataNote}</div>
                    )}
                </div>
                <div className="ml-auto flex items-center gap-1.5 flex-wrap">
                    {evaluations.map(({ evaluation }) => {
                        const style = VARIANT_STYLE[evaluation.variant];
                        const okCount = evaluation.checks.filter((c) => c.ok === true).length;
                        return (
                            <Badge
                                key={`${evaluation.variant}:${evaluation.subId ?? ''}`}
                                variant="outline"
                                className={`text-[10px] font-heading gap-1.5 ${style.badge}`}
                                title={`${okCount}/${evaluation.checks.length} condizioni soddisfatte`}
                            >
                                <span className={`inline-block w-1.5 h-1.5 rounded-full ${stateDotClass(evaluation.state)}`} />
                                {style.chipLabel(evaluation.subId)}
                                <span className="font-mono tabular-nums opacity-80">
                                    {okCount}/{evaluation.checks.length}
                                </span>
                            </Badge>
                        );
                    })}
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-white"
                        onClick={() => setOpen((v) => !v)}
                        aria-label={open ? 'Chiudi dettaglio condizioni' : 'Apri dettaglio condizioni'}
                    >
                        <ChevronDown className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`} />
                    </Button>
                </div>
            </div>

            {open && (
                <div className="mt-3 pt-3 border-t border-white/5 grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-3">
                    {evaluations.map(({ evaluation }) => {
                        const style = VARIANT_STYLE[evaluation.variant];
                        return (
                            <div key={`det:${evaluation.variant}:${evaluation.subId ?? ''}`}>
                                <div className="flex items-center gap-2 mb-1.5">
                                    <Badge variant="outline" className={`text-[10px] font-heading ${style.badge}`}>
                                        {style.chipLabel(evaluation.subId)}
                                    </Badge>
                                    {evaluation.state === 'signal' && (
                                        <span className="text-[10px] font-bold uppercase text-emerald-400">segnale attivo</span>
                                    )}
                                </div>
                                <ul className="space-y-0.5">
                                    {evaluation.checks.map((c) => {
                                        const icon = checkIcon(c.ok);
                                        return (
                                            <li key={c.id} className="flex items-center gap-2 text-xs">
                                                <span className={`w-3 text-center font-bold ${icon.cls}`}>{icon.glyph}</span>
                                                <span className="text-muted-foreground">{c.label}</span>
                                                <span className="ml-auto font-mono tabular-nums text-white/80">{c.value}</span>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </div>
                        );
                    })}
                    <div className="lg:col-span-2 pt-1">
                        <BetfairMediaButtons eventId={eventId} marketId={marketId} sport={sport} />
                    </div>
                </div>
            )}
        </div>
    );
}
