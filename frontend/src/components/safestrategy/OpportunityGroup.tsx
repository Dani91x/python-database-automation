// ============================================================================
// OpportunityGroup.tsx — card delle OPPORTUNITÀ DI MODELLO di una partita.
//
// Il servizio calcola (λ Poisson dal feed live) la probabilità di modello di
// ogni selezione e la confronta con quella implicita nella quota: edge, EV e
// confidenza. Qui si mostrano ordinate per EV × confidenza — il numero grande
// è l'EV, perché è quello che decide — e si può investire con un click.
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { InvestAction } from './InvestAction';
import { oppScore, type SafeMode, type SafeOpportunity, type SafeOpportunityRow, type SafeRequest } from '@/lib/safeBot';
import { sideBadgeClass } from './variantStyles';

function pct(v: number | null | undefined, digits = 1): string {
    const n = Number(v);
    return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : '—';
}
function signedPct(v: number | null | undefined): string {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${n < 0 ? '−' : '+'}${(Math.abs(n) * 100).toFixed(1)}%`;
}

/** riga di opportunita' piu' vecchia di cosi' = quote/probabilita' stantie:
 *  si mostra l'eta' e si spegne "Investi" (il modello non e' piu' quello) */
export const OPP_ROW_STALE_MS = 60_000;

/** Opportunita' della riga che superano i filtri, ordinate per EV × confidenza.
 *  Esportata perche' la pagina sappia se i filtri hanno svuotato tutto. */
export function filterOpps(
    row: SafeOpportunityRow, minConfidence: number, sideFilter: 'all' | 'back' | 'lay',
): SafeOpportunity[] {
    const p = row.payload ?? { opps: [] };
    return (Array.isArray(p.opps) ? p.opps : [])
        .filter((o) => Number(o.confidence) >= minConfidence)
        .filter((o) => sideFilter === 'all' || o.side === sideFilter)
        .sort((a, b) => oppScore(b) - oppScore(a));
}

export interface OpportunityGroupProps {
    row: SafeOpportunityRow;
    mode: SafeMode;
    stake: number;
    requests: SafeRequest[];
    minConfidence: number;
    sideFilter: 'all' | 'back' | 'lay';
    /** timestamp corrente (dal chiamante) per l'eta' della riga */
    nowMs?: number;
    onPlace: (opp: SafeOpportunity, size: number) => Promise<number | null>;
}

export function OpportunityGroup({
    row, mode, stake, requests, minConfidence, sideFilter, nowMs, onPlace,
}: OpportunityGroupProps) {
    const p = row.payload ?? { opps: [] };
    const opps = filterOpps(row, minConfidence, sideFilter);

    if (opps.length === 0) return null;

    const now = nowMs ?? Date.now();
    const rowMs = row.updated_at ? Date.parse(row.updated_at) : NaN;
    const ageSec = Number.isFinite(rowMs) ? Math.max(0, Math.round((now - rowMs) / 1000)) : null;
    const stale = ageSec != null && ageSec * 1000 > OPP_ROW_STALE_MS;
    const staleMsg = stale ? `quote non aggiornate (${ageSec}s)` : undefined;

    const score = p.score_home != null && p.score_away != null ? `${p.score_home}-${p.score_away}` : '?-?';
    const lam = p.lambdas
        ? `λ ${Number(p.lambdas.home ?? 0).toFixed(2)} / ${Number(p.lambdas.away ?? 0).toFixed(2)}`
        : null;

    return (
        <div className="glass-card rounded-xl border border-white/10 p-4" data-testid="opp-group">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="font-display font-black text-base text-white truncate max-w-[280px]">
                    {p.event_name ?? row.event_id}
                </span>
                <span className="font-mono tabular-nums text-xs text-muted-foreground">
                    {p.minute != null ? `${p.minute}′` : '—′'} · {score}
                </span>
                {lam && (
                    <Badge variant="outline" className="text-[10px] bg-white/5 text-muted-foreground border-white/10 font-mono">
                        {lam}
                    </Badge>
                )}
                {p.source && (
                    <Badge variant="outline" className="text-[10px] bg-white/5 text-muted-foreground border-white/10">
                        {p.source}
                    </Badge>
                )}
                {ageSec != null && (
                    <Badge
                        variant="outline"
                        data-testid="opp-age"
                        className={`text-[10px] font-mono tabular-nums ${stale ? 'bg-red-500/15 text-red-300 border-red-500/40' : 'bg-white/5 text-muted-foreground border-white/10'}`}
                        title={staleMsg ?? 'eta’ dell’ultimo calcolo del modello'}
                    >
                        {ageSec}s fa
                    </Badge>
                )}
                <Badge variant="outline" className="ml-auto text-[10px] bg-secondary/15 text-secondary border-secondary/40 font-mono tabular-nums">
                    {opps.length} opp.
                </Badge>
            </div>

            <div className="mt-3 space-y-3">
                {opps.map((o) => (
                    <div
                        key={`${o.market_id}:${o.selection_id}:${o.side}`}
                        className="rounded-lg border border-white/10 bg-black/30 p-3"
                        data-testid="opp-row"
                    >
                        <div className="flex items-center gap-2 flex-wrap">
                            <Badge variant="outline" className={`text-[10px] font-heading font-bold ${sideBadgeClass(o.side === 'lay' ? 'LAY' : 'BACK')}`}>
                                {o.side.toUpperCase()}
                            </Badge>
                            <span className="font-bold text-white text-sm">{o.selection_name ?? `#${o.selection_id}`}</span>
                            <span className="text-[11px] text-muted-foreground">
                                {o.market_name ?? o.market_type}{o.line != null ? ` ${o.line}` : ''}
                            </span>
                            <span className="ml-auto font-mono tabular-nums text-xl font-bold text-primary">
                                @{Number(o.price).toFixed(2)}
                            </span>
                        </div>

                        <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
                            <div>
                                <div className="text-slate-500 uppercase tracking-wide text-[10px]">Modello</div>
                                <div className="tabular-nums text-white font-bold">{pct(o.p_model)}</div>
                            </div>
                            <div>
                                <div className="text-slate-500 uppercase tracking-wide text-[10px]">Implicita</div>
                                <div className="tabular-nums text-slate-300">{pct(o.p_implied)}</div>
                            </div>
                            <div>
                                <div className="text-slate-500 uppercase tracking-wide text-[10px]">Edge</div>
                                <div className={`tabular-nums font-bold ${Number(o.edge) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                                    {signedPct(o.edge)}
                                </div>
                            </div>
                            <div>
                                <div className="text-slate-500 uppercase tracking-wide text-[10px]">EV</div>
                                <div className={`tabular-nums font-bold ${Number(o.ev) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                                    {Number(o.ev).toFixed(3)}
                                </div>
                            </div>
                        </div>

                        <div className="mt-2 flex items-center gap-2">
                            <span className="text-[10px] uppercase tracking-wide text-slate-500 w-20">Confidenza</span>
                            <Progress value={Math.max(0, Math.min(100, Number(o.confidence) * 100))} className="h-1.5 flex-1" />
                            <span className="text-[11px] tabular-nums text-slate-300 w-12 text-right">{pct(o.confidence, 0)}</span>
                        </div>

                        {o.rationale && (
                            <p className="mt-2 text-[11px] text-muted-foreground italic">{o.rationale}</p>
                        )}

                        <InvestAction
                            mode={mode}
                            side={o.side}
                            price={Number(o.price)}
                            sizeAvailable={o.size_available ?? null}
                            defaultStake={stake}
                            requests={requests}
                            disabled={stale}
                            disabledReason={staleMsg}
                            onPlace={(size) => onPlace(o, size)}
                        />
                    </div>
                ))}
            </div>
        </div>
    );
}

export default OpportunityGroup;
