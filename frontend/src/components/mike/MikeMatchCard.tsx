// ============================================================================
// MikeMatchCard — scheda di UNA partita seguita da Mike.
//
// Gerarchia visiva (design system Safe Strategy / Omega): PARTITA e PUNTEGGIO →
// FASE → POSIZIONI (ingresso vs quota LIVE, tick guadagnati/persi, P&L se chiudo
// ora) → ordini sul book → P&L a fine gara per gol totali (cella 4 in rosso) →
// cash-out con soglia. Convenzione colori del repo: BACK = sky, LAY = rose;
// favorevole = emerald, sfavorevole = red. Ogni selezione porta in tooltip
// market/selection_id risolti dal servizio (certificazione runner).
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';
import { sideBadgeClass } from '@/components/safestrategy/variantStyles';
import { fmtEurIt, fmtOddsIt } from '@/lib/safeBot';
import { countdownToOff, formatMinute } from '@/lib/matchClock';
import { ticksBetween } from '@/lib/riskMath';
import {
    activeLegs, cashoutPct, investedOf, legSelectionLabel, lockedIfClosed, phaseMeta, positionRows, roleLabel,
    MIKE_TERMINAL_STATES, type MikeBook, type MikeCashoutSmart, type MikeEvent, type MikeLossExit, type MikeParams,
    type MikeRequestKind, type PositionRow,
} from '@/lib/mike';

export interface MikeMatchCardProps {
    ev: MikeEvent;
    params: MikeParams;
    nowMs: number;
    busy?: boolean;
    /** feed stantio: azioni spente */
    stale?: boolean;
    staleReason?: string;
    onRequest?: (kind: MikeRequestKind, eventId: string) => void;
    isRequestPending?: (eventId: string, kind: MikeRequestKind) => boolean;
}

// ------------------------------------------------------------------ helpers
function pct(v: number | null | undefined, digits = 0): string {
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

const EDGE_BY_GROUP: Record<string, string> = {
    pre: 'border-l-teal-400/70',
    live: 'border-l-violet-400/70',
    flat: 'border-l-emerald-400/70',
    done: 'border-l-white/15',
};

/** Riga "cash-out intelligente": cosa sta valutando il bot adesso. */
export function smartLabel(smart: MikeCashoutSmart | null | undefined, threshold: number, base: number | null): string | null {
    if (!smart || !smart.enabled) return null;
    const parts: string[] = [];
    if (smart.floor != null && base && base > 0) parts.push(`min ${fmtEurIt(smart.floor)} (${((smart.floor / base) * 100).toFixed(1).replace('.', ',')}%)`);
    if (smart.near) parts.push(`a un passo dal ${threshold}%`);
    if (smart.hot) parts.push('fase calda');
    if (smart.ev_hold != null) parts.push(`aspettare vale ${fmtEurIt(smart.ev_hold, true)}`);
    if (smart.trigger) parts.push(`→ chiude (${smart.trigger})`);
    return parts.length ? `intelligente: ${parts.join(' · ')}` : null;
}

/** Riga "uscita in perdita a modello": tenere vs chiudere. */
export function lossExitLabel(le: MikeLossExit | null | undefined, cashoutNet: number | null): string | null {
    if (!le) return null;
    if (le.mode === 'fixed') return `uscita ${le.window ?? ''}: regola fissa (perdita ≤ ${le.pct ?? '—'}%)`;
    if (le.missing) return `uscita ${le.window ?? ''}: modello senza dati → regola fissa`;
    const parts: string[] = [];
    if (le.ev_hold != null) parts.push(`tenere vale ${fmtEurIt(le.ev_hold, true)}`);
    if (le.p4 != null) parts.push(`P(4) ${(le.p4 * 100).toFixed(0)}%`);
    if (le.premium != null) parts.push(`premio ${fmtEurIt(le.premium)}`);
    if (le.threshold != null && cashoutNet != null) parts.push(cashoutNet >= le.threshold ? '→ chiude' : '→ tiene');
    if (le.beyond_cap) parts.push('(oltre il tetto: tiene)');
    return `uscita ${le.window ?? ''} a modello: ${parts.join(' · ')}`;
}

/** Tick guadagnati/persi rispetto all'ingresso, sul prezzo di CHIUSURA della posizione
 *  (netta back → best lay; netta lay → best back). Negativo per un back = favorevole. */
export function positionTicks(row: PositionRow, book: MikeBook | undefined): { ticks: number; favourable: boolean | null; closeAt: number | null } {
    const closeAt = row.netSide === 'BACK' ? (book?.best_lay ?? null) : (book?.best_back ?? null);
    if (row.entryPrice == null || closeAt == null) return { ticks: 0, favourable: null, closeAt };
    const t = ticksBetween(row.entryPrice, closeAt);
    const favourable = t === 0 ? null : row.netSide === 'BACK' ? t < 0 : t > 0;
    return { ticks: t, favourable, closeAt };
}

function TickDelta({ ticks, favourable }: { ticks: number; favourable: boolean | null }) {
    if (favourable === null) return <span className="text-slate-400 tabular-nums">= 0 tick</span>;
    const cls = favourable ? 'text-emerald-400' : 'text-red-400';
    const arrow = ticks < 0 ? '▼' : '▲';
    return <span className={`tabular-nums font-semibold ${cls}`}>{arrow} {Math.abs(ticks)} tick</span>;
}

// ------------------------------------------------------------------ card
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
    const books = live.books ?? {};
    const b35 = books['OU35|UNDER'];
    const b45 = books['OU45|OVER'];
    const hasScore = inplay && live.score_home != null && live.score_away != null;
    const smart = cashout?.smart ?? null;
    const smartHint = smartLabel(smart, threshold, cashout?.base ?? null);
    const lossHint = lossExitLabel(live.loss_exit ?? null, cashout?.net ?? null);
    const rows = positionRows(ev);
    const pending = legs.filter((l) => l.status === 'pending');
    const commission = Number(params.commission_pct ?? 5) / 100;
    const sels = ((ev.ctx as { selections?: Record<string, number> } | null)?.selections) ?? {};
    const marketIds = (ev.markets ?? {}) as Record<string, { market_id?: string | null } | undefined>;
    const barPct = coPct != null && threshold > 0 ? Math.max(0, Math.min(100, (coPct / threshold) * 100)) : 0;

    return (
        <Card
            className={`glass-card border-white/10 border-l-4 p-3 space-y-3 ${EDGE_BY_GROUP[meta.group] ?? ''}`}
            data-testid="mike-match-card"
            data-state={ev.state}
        >
            {/* ------------------------------------------------- header: partita · fase */}
            <div className="flex items-start justify-between gap-2 flex-wrap">
                <div className="min-w-0 flex items-center gap-3">
                    {hasScore && (
                        <div className="flex flex-col items-center shrink-0" data-testid="mike-score">
                            <span className="rounded-md bg-black/50 border border-white/15 px-2.5 py-0.5 font-display font-black text-xl tabular-nums text-white leading-tight">
                                {live.score_home}–{live.score_away}
                            </span>
                            {((live.red_home ?? 0) > 0 || (live.red_away ?? 0) > 0) && (
                                <span className="text-[10px] text-rose-300" title="espulsioni casa / trasferta">🟥 {live.red_home ?? 0}/{live.red_away ?? 0}</span>
                            )}
                        </div>
                    )}
                    <div className="min-w-0">
                        <div className="font-heading font-bold text-sm truncate">{ev.event_name ?? ev.event_id}</div>
                        <div className="text-[11px] text-slate-400 truncate">
                            {ev.competition ?? '—'}
                            {inplay
                                ? <> · <span className="text-white/90 font-semibold">{minuteLabel ?? '—′'}</span>{live.goals != null && <> · {live.goals} gol</>}{live.ht && <span className="text-amber-300"> · intervallo</span>}</>
                                : countdown ? <> · KO fra <span className="text-white/90 tabular-nums">{countdown}</span></> : ' · pre-KO'}
                        </div>
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
                    <div className="text-slate-500 uppercase tracking-wide text-[9px]">{inplay ? 'Pressione' : 'λ casa / trasferta'}</div>
                    <div className="tabular-nums text-white/90" data-testid="mike-pressure">
                        {inplay
                            ? (live.pressure != null ? `×${num(live.pressure)}${(live.pressure ?? 1) >= Number(params.cashout_smart_pressure_hot ?? 1.15) ? ' 🔥' : ''}` : '—')
                            : <>{num(dossier.lambda_home ?? null)} / {num(dossier.lambda_away ?? null)}</>}
                    </div>
                </div>
            </div>

            {/* ------------------------------------------------- quote live delle due linee */}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-300" data-testid="mike-quotes">
                <span title={`Under 3.5 · market ${marketIds.OU35?.market_id ?? '—'} · selection ${sels['OU35|UNDER'] ?? '—'}`}>
                    <span className="text-slate-500">U3.5</span>{' '}
                    <span className="text-sky-300 tabular-nums">{fmtOddsIt(b35?.best_back ?? null)}</span>
                    <span className="text-slate-600">/</span>
                    <span className="text-rose-300 tabular-nums">{fmtOddsIt(b35?.best_lay ?? null)}</span>
                </span>
                <span title={`Over 4.5 · market ${marketIds.OU45?.market_id ?? '—'} · selection ${sels['OU45|OVER'] ?? '—'}`}>
                    <span className="text-slate-500">O4.5</span>{' '}
                    <span className="text-sky-300 tabular-nums">{fmtOddsIt(b45?.best_back ?? null)}</span>
                    <span className="text-slate-600">/</span>
                    <span className="text-rose-300 tabular-nums">{fmtOddsIt(b45?.best_lay ?? null)}</span>
                </span>
                {ev.entry_price_initial != null && <span>primo ingresso <span className="tabular-nums text-white/90">{fmtOddsIt(ev.entry_price_initial)}</span></span>}
                <span>ciclo {ev.cycle_no}</span>
                {invested > 0 && <span>investito <span className="tabular-nums text-white/90">{fmtEurIt(invested)}</span></span>}
                {ev.settled_pnl != null && <span>regolato <span className={`tabular-nums font-semibold ${pnlClass(ev.settled_pnl)}`}>{fmtEurIt(ev.settled_pnl, true)}</span></span>}
            </div>

            {/* ------------------------------------------------- posizioni: ingresso vs quota live */}
            {rows.length > 0 && (
                <div className="overflow-x-auto rounded-md border border-white/5 bg-black/20" data-testid="mike-positions">
                    <table className="w-full text-[11px]">
                        <thead className="text-slate-500 uppercase tracking-wide text-[9px]">
                            <tr>
                                <th className="text-left font-normal px-2 py-1">Posizione</th>
                                <th className="text-right font-normal">Ingresso</th>
                                <th className="text-right font-normal">Quota ora</th>
                                <th className="text-right font-normal">Δ ingresso</th>
                                <th className="text-right font-normal px-2">Se chiudo ora</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r) => {
                                const book = books[r.key];
                                const { ticks, favourable, closeAt } = positionTicks(r, book);
                                const fromService = cashout?.per?.[r.key];
                                const gross = lockedIfClosed(r.w, r.l, book?.best_back, book?.best_lay);
                                const locked = fromService ?? (gross != null ? (gross > 0 ? Math.round(gross * (1 - commission) * 100) / 100 : gross) : null);
                                return (
                                    <tr key={r.key} className="border-t border-white/5" data-testid="mike-pos-row"
                                        title={`${r.label} · market ${marketIds[r.market]?.market_id ?? '—'} · selection ${r.selectionId ?? '—'} · ${r.roles.map(roleLabel).join(', ')}`}>
                                        <td className="px-2 py-1">
                                            <Badge variant="outline" className={`text-[9px] mr-1 ${sideBadgeClass(r.netSide)}`}>{r.netSide}</Badge>
                                            <span className="font-semibold text-white/90">{r.label}</span>
                                            <span className="text-slate-500"> · {fmtEurIt(r.matched)}</span>
                                        </td>
                                        <td className="text-right tabular-nums text-white/90">{fmtOddsIt(r.entryPrice)}</td>
                                        <td className="text-right tabular-nums">
                                            <span className="text-sky-300">{fmtOddsIt(book?.best_back ?? null)}</span>
                                            <span className="text-slate-600">/</span>
                                            <span className="text-rose-300">{fmtOddsIt(book?.best_lay ?? null)}</span>
                                            {closeAt != null && <span className="text-slate-500 text-[9px]"> chiudo @{fmtOddsIt(closeAt)}</span>}
                                        </td>
                                        <td className="text-right"><TickDelta ticks={ticks} favourable={favourable} /></td>
                                        <td className={`text-right tabular-nums px-2 font-semibold ${pnlClass(locked)}`} data-testid="mike-pos-locked">
                                            {locked != null ? fmtEurIt(locked, true) : '—'}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ------------------------------------------------- ordini sul book (non abbinati) */}
            {pending.length > 0 && (
                <div className="space-y-0.5 text-[11px]" data-testid="mike-pending">
                    {pending.map((l) => {
                        const book = books[`${l.market}|${l.selection}`];
                        const price = Number(l.price);
                        // una LAY appoggiata si abbina quando il best back SALE fino al suo prezzo; una BACK quando il best lay scende
                        const ref = l.side === 'lay' ? (book?.best_back ?? null) : (book?.best_lay ?? null);
                        const dist = ref != null && price > 0 ? ticksBetween(ref, price) : null;
                        const rest = Math.max(0, Number(l.size) - Number(l.matched || 0));
                        return (
                            <div key={l.ref} className="flex items-center gap-2 flex-wrap text-slate-300">
                                <Badge variant="outline" className={`text-[9px] ${sideBadgeClass(l.side.toUpperCase() as 'BACK' | 'LAY')}`}>{l.side.toUpperCase()}</Badge>
                                <span>{roleLabel(l.role)} <span className="text-slate-500">({legSelectionLabel(l)})</span></span>
                                <span className="tabular-nums text-white/90">{fmtEurIt(rest)} @ {fmtOddsIt(price)}</span>
                                <span className="text-slate-500">sul book{l.persistence === 'PERSIST' ? ' · PERSIST' : ''}{Number(l.matched) > 0 ? ` · abbinati ${fmtEurIt(Number(l.matched))}` : ''}</span>
                                {dist != null && (
                                    <span className={`tabular-nums ${dist === 0 ? 'text-emerald-300' : 'text-amber-200/80'}`}>
                                        {dist === 0 ? 'al best' : `${Math.abs(dist)} tick ${dist > 0 ? 'sopra' : 'sotto'} il best`}
                                    </span>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ------------------------------------------------- P&L per gol totali */}
            {totals.length > 0 && hasPosition && (
                <div className="flex items-center gap-1 flex-wrap" data-testid="mike-pnl-by-total">
                    <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">A fine gara, per gol totali</span>
                    {totals.map((t) => {
                        const v = Number(pnlByTotal[String(t)]);
                        const isCurrent = inplay && live.goals != null && t === Number(live.goals);
                        return (
                            <span
                                key={t}
                                className={`rounded px-1.5 py-0.5 text-[10px] tabular-nums border ${t === 4 ? 'border-rose-400/60 bg-rose-500/15' : 'border-white/10 bg-black/30'} ${isCurrent ? 'ring-1 ring-white/50' : ''} ${pnlClass(v)}`}
                                data-testid={`pnl-total-${t}`}
                                title={isCurrent ? 'gol attuali' : undefined}
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
                    <div className="text-[11px] min-w-0 flex-1">
                        <span className="text-slate-500 uppercase tracking-wide text-[9px] mr-1">Cash-out ora</span>
                        {cashout && cashout.complete
                            ? <span className={`tabular-nums font-heading font-bold ${pnlClass(cashout.net)}`} data-testid="mike-cashout-value">
                                {fmtEurIt(cashout.net, true)} {coPct != null && <span className="text-slate-400 font-normal">({coPct}% · soglia {threshold}%)</span>}
                            </span>
                            : <span className="text-slate-500">{hasPosition ? 'prezzi incompleti' : 'nessuna posizione'}</span>}
                        {cashout && cashout.complete && coPct != null && (
                            <div className="mt-1 h-1 w-full max-w-[220px] rounded bg-white/10 overflow-hidden" title={`${coPct}% della soglia ${threshold}%`}>
                                <div className={`h-full ${coPct >= threshold ? 'bg-emerald-400' : coPct > 0 ? 'bg-teal-400/70' : 'bg-red-400/70'}`} style={{ width: `${barPct}%` }} />
                            </div>
                        )}
                        {smartHint && <div className="text-[10px] text-slate-400 mt-0.5" data-testid="mike-cashout-smart">{smartHint}</div>}
                        {lossHint && <div className="text-[10px] text-amber-200/80 mt-0.5" data-testid="mike-loss-exit">{lossHint}</div>}
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
