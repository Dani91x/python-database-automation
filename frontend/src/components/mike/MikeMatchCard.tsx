// ============================================================================
// MikeMatchCard — UNA card per partita seguita da Mike.
//
// Header (partita, competizione, KO/minuto+punteggio, fase), quadro della
// partita (P(4) modello vs mercato, hazard, λ, ingresso iniziale), gambe vive
// (ruolo, lato, prezzo, size, abbinato), striscia "P&L per gol totali 0..8"
// con la cella 4 in rosso, tile cash-out (valore, % vs soglia), azioni
// (Cash out / Salta / Riprendi), pulsanti video/statistiche Betfair.
// Nessun dato inventato: ogni valore viene da mike_events (servizio).
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';
import { sideBadgeClass } from '@/components/safestrategy/variantStyles';
import { fmtEurIt, fmtOddsIt } from '@/lib/safeBot';
import { countdownToOff, formatMinute } from '@/lib/matchClock';
import {
    activeLegs, cashoutPct, investedOf, legSelectionLabel, phaseMeta, roleLabel,
    MIKE_TERMINAL_STATES, type MikeEvent, type MikeParams, type MikeRequestKind,
} from '@/lib/mike';

export interface MikeMatchCardProps {
    ev: MikeEvent;
    params: MikeParams;
    nowMs: number;
    busy?: boolean;
    /** feed stantio: i bottoni con soldi si spengono */
    stale?: boolean;
    staleReason?: string;
    onRequest?: (kind: MikeRequestKind, eventId: string) => void;
    isRequestPending?: (eventId: string, kind: MikeRequestKind) => boolean;
}

function pct(v: number | null | undefined, digits = 1): string {
    if (v == null || !Number.isFinite(Number(v))) return '—';
    return `${(Number(v) * 100).toFixed(digits).replace('.', ',')}%`;
}
function num(v: number | null | undefined, digits = 2): string {
    if (v == null || !Number.isFinite(Number(v))) return '—';
    return Number(v).toFixed(digits).replace('.', ',');
}
function pnlClass(v: number | null | undefined): string {
    if (v == null) return 'text-slate-400';
    return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300';
}

export function MikeMatchCard({ ev, params, nowMs, busy, stale, staleReason, onRequest, isRequestPending }: MikeMatchCardProps) {
    const meta = phaseMeta(ev.state);
    const live = ev.live ?? {};
    const dossier = ev.dossier ?? {};
    const legs = activeLegs(ev);
    const invested = investedOf(ev);
    const cashout = live.cashout ?? null;
    const coPct = cashout ? cashoutPct(cashout.net, cashout.base) : null;
    const threshold = Number(params.cashout_profit_pct ?? 5);
    const inplay = Boolean(live.inplay);
    const minuteLabel = formatMinute(live.minute ?? null);
    const countdown = !inplay ? countdownToOff(ev.ko_at, nowMs) : null;
    const terminal = MIKE_TERMINAL_STATES.includes(ev.state);
    const hasPosition = legs.some((l) => l.matched > 0);
    const pnlByTotal = live.pnl_by_total ?? {};
    const totals = Object.keys(pnlByTotal).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    const cashoutDisabled = Boolean(busy) || Boolean(stale) || !hasPosition
        || (isRequestPending?.(ev.event_id, 'cashout') ?? false);
    const b35 = live.books?.['OU35|UNDER'];
    const b45 = live.books?.['OU45|OVER'];

    return (
        <Card
            className={`glass-card border-white/10 p-3 space-y-3 ${meta.group === 'live' ? 'border-l-2 border-l-teal-400/60' : ''}`}
            data-testid="mike-match-card"
            data-state={ev.state}
        >
            {/* ------------------------------------------------- header */}
            <div className="flex items-start justify-between gap-2 flex-wrap">
                <div className="min-w-0">
                    <div className="font-heading font-bold text-sm truncate">{ev.event_name ?? ev.event_id}</div>
                    <div className="text-[11px] text-slate-400 truncate">
                        {ev.competition ?? '—'}
                        {inplay
                            ? <> · <span className="text-white/90">{minuteLabel ?? '—′'}</span>{live.goals != null && <> · {live.goals} gol</>}{live.ht && ' · intervallo'}</>
                            : countdown ? <> · KO fra <span className="text-white/90 tabular-nums">{countdown}</span></> : ' · pre-KO'}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant="outline" className={`text-[10px] font-heading ${meta.cls}`} data-testid="mike-phase">
                        {meta.label}
                    </Badge>
                    <BetfairMediaButtons eventId={ev.event_id} compact />
                </div>
            </div>

            {/* ------------------------------------------------- quadro partita */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                <div className="rounded-md bg-black/30 border border-white/5 px-2 py-1.5">
                    <div className="text-slate-500 uppercase tracking-wide text-[9px]">P(4 gol) modello</div>
                    <div className="tabular-nums text-white/90">{pct(live.p4_model ?? dossier.p4_pre ?? null)}</div>
                </div>
                <div className="rounded-md bg-black/30 border border-white/5 px-2 py-1.5">
                    <div className="text-slate-500 uppercase tracking-wide text-[9px]">P(4 gol) mercato</div>
                    <div className="tabular-nums text-white/90">{pct(live.p4_market ?? null)}</div>
                </div>
                <div className="rounded-md bg-black/30 border border-white/5 px-2 py-1.5">
                    <div className="text-slate-500 uppercase tracking-wide text-[9px]">Hazard gol 3′</div>
                    <div className="tabular-nums text-white/90">{inplay ? pct(live.hazard ?? null) : '—'}</div>
                </div>
                <div className="rounded-md bg-black/30 border border-white/5 px-2 py-1.5">
                    <div className="text-slate-500 uppercase tracking-wide text-[9px]">λ casa / trasferta</div>
                    <div className="tabular-nums text-white/90">{num(dossier.lambda_home ?? null)} / {num(dossier.lambda_away ?? null)}</div>
                </div>
            </div>

            {/* ------------------------------------------------- book + posizione */}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-300">
                <span>U3.5 <span className="text-sky-300 tabular-nums">{fmtOddsIt(b35?.best_back ?? null)}</span>/<span className="text-rose-300 tabular-nums">{fmtOddsIt(b35?.best_lay ?? null)}</span></span>
                <span>O4.5 <span className="text-sky-300 tabular-nums">{fmtOddsIt(b45?.best_back ?? null)}</span>/<span className="text-rose-300 tabular-nums">{fmtOddsIt(b45?.best_lay ?? null)}</span></span>
                {ev.entry_price_initial != null && <span>ingresso iniziale <span className="tabular-nums text-white/90">{fmtOddsIt(ev.entry_price_initial)}</span></span>}
                <span>ciclo {ev.cycle_no}</span>
                {invested > 0 && <span>investito <span className="tabular-nums text-white/90">{fmtEurIt(invested)}</span></span>}
                {ev.settled_pnl != null && <span>regolato <span className={`tabular-nums ${pnlClass(ev.settled_pnl)}`}>{fmtEurIt(ev.settled_pnl, true)}</span></span>}
            </div>

            {legs.length > 0 && (
                <div className="overflow-x-auto">
                    <table className="w-full text-[11px]">
                        <thead className="text-slate-500 uppercase tracking-wide text-[9px]">
                            <tr><th className="text-left font-normal">Gamba</th><th className="text-left font-normal">Lato</th><th className="text-right font-normal">Quota</th><th className="text-right font-normal">Size</th><th className="text-right font-normal">Abbinato</th><th className="text-left font-normal pl-2">Stato</th></tr>
                        </thead>
                        <tbody>
                            {legs.map((l) => (
                                <tr key={l.ref} className="border-t border-white/5" data-testid="mike-leg">
                                    <td className="py-1">{roleLabel(l.role)} <span className="text-slate-500">({legSelectionLabel(l)})</span></td>
                                    <td><Badge variant="outline" className={`text-[9px] ${sideBadgeClass(l.side.toUpperCase() as 'BACK' | 'LAY')}`}>{l.side.toUpperCase()}</Badge></td>
                                    <td className="text-right tabular-nums">{fmtOddsIt(l.avg_price ?? l.price)}</td>
                                    <td className="text-right tabular-nums">{fmtEurIt(l.size)}</td>
                                    <td className="text-right tabular-nums">{fmtEurIt(l.matched)}</td>
                                    <td className="pl-2 text-slate-400">{l.status}{l.persistence === 'PERSIST' ? ' · PERSIST' : ''}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ------------------------------------------------- P&L per gol totali */}
            {totals.length > 0 && hasPosition && (
                <div className="flex items-center gap-1 flex-wrap" data-testid="mike-pnl-by-total">
                    <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">P&L a fine gara per gol totali</span>
                    {totals.map((t) => {
                        const v = Number(pnlByTotal[String(t)]);
                        return (
                            <span
                                key={t}
                                className={`rounded px-1.5 py-0.5 text-[10px] tabular-nums border ${t === 4 ? 'border-rose-400/60 bg-rose-500/15' : 'border-white/10 bg-black/30'} ${pnlClass(v)}`}
                                data-testid={`pnl-total-${t}`}
                            >
                                {t === totals[totals.length - 1] ? `${t}+` : t}: {fmtEurIt(v, true)}
                            </span>
                        );
                    })}
                </div>
            )}

            {/* ------------------------------------------------- cash-out + azioni */}
            {!terminal && (
                <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="text-[11px]">
                        <span className="text-slate-500 uppercase tracking-wide text-[9px] mr-1">Cash-out ora</span>
                        {cashout && cashout.complete
                            ? <span className={`tabular-nums font-heading font-bold ${pnlClass(cashout.net)}`} data-testid="mike-cashout-value">
                                {fmtEurIt(cashout.net, true)} {coPct != null && <span className="text-slate-400 font-normal">({coPct}% · soglia {threshold}%)</span>}
                            </span>
                            : <span className="text-slate-500">{hasPosition ? 'prezzi incompleti' : 'nessuna posizione'}</span>}
                    </div>
                    <div className="flex items-center gap-1">
                        {hasPosition && (
                            <Button
                                size="sm" variant="outline"
                                className="h-7 text-[11px] border-rose-400/40 text-rose-200 hover:bg-rose-500/15"
                                disabled={cashoutDisabled}
                                title={staleReason}
                                onClick={() => onRequest?.('cashout', ev.event_id)}
                                data-testid="mike-cashout-btn"
                            >Cash out</Button>
                        )}
                        {ev.state === 'SKIPPED' ? null : !hasPosition && (
                            <Button
                                size="sm" variant="ghost" className="h-7 text-[11px] text-slate-400"
                                disabled={Boolean(busy) || (isRequestPending?.(ev.event_id, 'skip_event') ?? false)}
                                onClick={() => onRequest?.('skip_event', ev.event_id)}
                                data-testid="mike-skip-btn"
                            >Salta</Button>
                        )}
                    </div>
                </div>
            )}
            {ev.state === 'SKIPPED' && (
                <div className="flex justify-end">
                    <Button
                        size="sm" variant="ghost" className="h-7 text-[11px] text-teal-300"
                        disabled={Boolean(busy) || (isRequestPending?.(ev.event_id, 'resume_event') ?? false)}
                        onClick={() => onRequest?.('resume_event', ev.event_id)}
                        data-testid="mike-resume-btn"
                    >Riprendi</Button>
                </div>
            )}
        </Card>
    );
}
