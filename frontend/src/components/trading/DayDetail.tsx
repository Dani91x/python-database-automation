// ============================================================================
// DayDetail.tsx — i trade di UNA giornata operativa: aperture con le gambe di
// chiusura annidate, badge stato + uscita automatica, P&L bloccato dal cash
// out, P&L totale della posizione, link al live se ancora aperta, totali.
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Activity, ExternalLink } from 'lucide-react';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { cappedFrom } from '@/lib/safeBot';
import { dayLabel, tradeExit, type DayTrade, type DayTradeLeg, type HistoryVariant } from '@/lib/dailyHistory';
import { MatchTradesTable } from '@/components/omega/MatchTradesTable';

function fmtEur(v: number | null | undefined): string {
    const n = Number(v ?? 0);
    return `${n < 0 ? '−' : ''}€${Math.abs(n).toFixed(2)}`;
}
function fmtSignedEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}
function timeLabel(iso: string | null): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '—'
        : d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' });
}

export function statusBadge(status: string): { label: string; cls: string } {
    switch (status) {
        case 'pending': return { label: 'IN CORSO', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' };
        case 'open': return { label: 'APERTO', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' };
        case 'hedged': return { label: 'CHIUSO', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' };
        case 'won': return { label: 'VINTO', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' };
        case 'lost': return { label: 'PERSO', cls: 'bg-red-500/15 text-red-300 border-red-500/40' };
        case 'void': return { label: 'VOID', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40' };
        default: return { label: 'ERRORE', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/40' };
    }
}

const STRATEGY_LABEL: Record<string, string> = {
    base: 'BASE', esatto: 'R. ESATTO', punta: 'PUNTA', tennis: 'TENNIS', model: 'MODELLO', manual: 'MANUALE',
};
const PHASE_LABEL: Record<string, string> = { ht_cs: '1T', ft_cs: '2T', scalp: 'SCALP' };
const MIKE_ROLE_LABEL: Record<string, string> = {
    under_entry: 'INGRESSO U3.5', under_green: 'GREEN U3.5', under_last: 'ULTIMO (PERSIST)',
    over_cover: 'COPERTURA O4.5', under_close: 'CHIUSURA U3.5', over_close: 'CHIUSURA O4.5',
    reentry: 'RE-INGRESSO U4.5', reentry_green: 'GREEN RE-INGRESSO', manual_close: 'MANUALE',
};

const LIVE_STATUSES = new Set(['pending', 'open', 'hedged']);

function lockedPnl(leg: DayTradeLeg): number | null {
    const v = Number((leg.meta ?? {})['locked_pnl']);
    return Number.isFinite(v) ? v : null;
}
function selectionOf(t: DayTradeLeg): string {
    return t.selection_name ?? t.runner_name ?? '—';
}
function kindOf(t: DayTradeLeg, variant: HistoryVariant): string {
    if (variant === 'omega') return PHASE_LABEL[t.phase ?? ''] ?? '—';
    if (variant === 'mike') return MIKE_ROLE_LABEL[t.strategy ?? ''] ?? (t.strategy ?? '—');
    return STRATEGY_LABEL[t.strategy ?? ''] ?? (t.strategy ?? '—');
}

export interface DayDetailProps {
    day: string | null;
    trades: DayTrade[] | null;
    loading?: boolean;
    error?: string | null;
    variant: HistoryVariant;
    /** posizione ancora viva → "vai al live" (tab trade della pagina) */
    onGoLive?: (trade: DayTrade) => void;
}

export function DayDetail({ day, trades, loading = false, error = null, variant, onGoLive }: DayDetailProps) {
    if (!day) {
        return (
            <div className="text-sm text-muted-foreground py-6 text-center" data-testid="day-detail-empty">
                seleziona una giornata dal calendario per vedere i trade
            </div>
        );
    }
    const list = trades ?? [];
    const settled = list.filter((t) => ['won', 'lost', 'void'].includes(t.status));
    const totalPnl = settled.reduce((s, t) => s + t.total_pnl, 0);
    const openCount = list.filter((t) => LIVE_STATUSES.has(t.status)).length;
    const liability = list.reduce((s, t) => s + (t.placed_in_day ? Number(t.liability ?? 0) : 0), 0);

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="day-detail" aria-busy={loading || undefined}>
            <div className="px-4 py-2.5 border-b border-white/5 flex items-center gap-3 flex-wrap text-sm text-slate-300">
                <Activity className="w-4 h-4 text-primary" />
                <span className="font-semibold capitalize">{dayLabel(day, { weekday: true })}</span>
                <span className="text-slate-500">·</span>
                <span className="tabular-nums">{list.length} trade</span>
                {openCount > 0 && <Badge variant="outline" className="bg-sky-500/15 text-sky-300 border-sky-500/40 text-[10px]">{openCount} ancora vivi</Badge>}
                <span className="ml-auto tabular-nums">
                    <span className="text-slate-400 mr-1 text-xs">liability piazzata {fmtEur(liability)} ·</span>
                    <span className="text-slate-400 mr-1 text-xs">realizzato</span>
                    <b className={totalPnl > 0 ? 'text-emerald-400' : totalPnl < 0 ? 'text-red-400' : 'text-slate-300'} data-testid="day-total-pnl">
                        {fmtSignedEur(totalPnl)}
                    </b>
                </span>
            </div>
            {error ? (
                <div className="text-sm text-red-300 py-6 text-center" data-testid="day-detail-error">{error}</div>
            ) : loading && trades == null ? (
                <div className="text-sm text-muted-foreground py-8 text-center">caricamento…</div>
            ) : list.length === 0 ? (
                <div className="text-sm text-muted-foreground py-8 text-center" data-testid="day-detail-none">nessun trade in questa giornata</div>
            ) : variant === 'omega' ? (
                // Omega §14: UNA riga per PARTITA (gamba 1T + gamba 2T con le chiusure
                // attaccate, risultati reali, P&L della partita) — stessa tabella del live
                <MatchTradesTable
                    trades={list.flatMap((t) => [t, ...t.closes])}
                    onGoLive={onGoLive ? (t) => onGoLive(t as DayTrade) : undefined}
                    day={day}
                    emptyText="nessun trade in questa giornata"
                />
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="text-[11px] uppercase text-slate-500 bg-black/30">
                            <tr>
                                <th className="text-left px-3 py-2">Ora</th>
                                <th className="text-left px-3 py-2">Match</th>
                                <th className="text-center px-3 py-2">Strategia</th>
                                <th className="text-left px-3 py-2">Selezione</th>
                                <th className="text-center px-3 py-2">Lato</th>
                                <th className="text-right px-3 py-2">Quota</th>
                                <th className="text-right px-3 py-2">Stake</th>
                                <th className="text-right px-3 py-2">Liability</th>
                                <th className="text-center px-3 py-2">Stato</th>
                                <th className="text-center px-3 py-2" title="uscita automatica registrata dal servizio">Uscita</th>
                                <th className="text-right px-3 py-2" title="P&L totale della posizione: apertura + chiusure">P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            {list.map((t) => {
                                const b = statusBadge(t.status);
                                const exit = tradeExit(t);
                                const locked = lockedPnl(t);
                                const live = LIVE_STATUSES.has(t.status);
                                const isSettled = ['won', 'lost', 'void'].includes(t.status);
                                return [
                                    <tr key={t.id} className="border-t border-white/5 hover:bg-white/5" data-testid="day-trade-row">
                                        <td className="px-3 py-2 text-slate-400 tabular-nums">
                                            {timeLabel(t.placed_at)}
                                            {!t.placed_in_day && <span className="ml-1 text-[10px] text-slate-500" title="piazzato in un'altra giornata, regolato oggi">(prec.)</span>}
                                        </td>
                                        <td className="px-3 py-2 max-w-[220px] truncate" title={t.event_name ?? t.event_id}>
                                            {t.origin === 'manual' && (
                                                <Badge variant="outline" className="mr-1.5 px-1 py-0 text-[10px] bg-violet-500/15 text-violet-300 border-violet-500/40" title="piazzato manualmente">✋</Badge>
                                            )}
                                            {t.mode === 'live' && (
                                                <Badge variant="outline" className="mr-1.5 px-1 py-0 text-[10px] bg-red-500/15 text-red-300 border-red-500/40" title="soldi veri">LIVE</Badge>
                                            )}
                                            {t.event_name ?? t.event_id}
                                        </td>
                                        <td className="px-3 py-2 text-center text-[11px] font-heading font-bold text-slate-300">{kindOf(t, variant)}</td>
                                        <td className="px-3 py-2 max-w-[160px] truncate" title={selectionOf(t)}>{selectionOf(t)}</td>
                                        <td className={`px-3 py-2 text-center font-bold ${t.side === 'back' ? 'text-sky-300' : 'text-rose-300'}`}>{String(t.side).toUpperCase()}</td>
                                        <td className="px-3 py-2 text-right tabular-nums">{t.price != null ? t.price.toFixed(2) : '—'}</td>
                                        <td className="px-3 py-2 text-right tabular-nums">{fmtEur(t.size)}</td>
                                        <td className="px-3 py-2 text-right tabular-nums text-orange-400/90">{fmtEur(t.liability)}</td>
                                        <td className="px-3 py-2 text-center">
                                            <Badge variant="outline" className={b.cls}>{b.label}</Badge>
                                            {live && onGoLive && (
                                                <Button variant="ghost" size="sm" className="ml-1 h-6 px-1.5 text-[11px] text-sky-300" onClick={() => onGoLive(t)} data-testid="day-trade-live">
                                                    <ExternalLink className="w-3 h-3 mr-1" />live
                                                </Button>
                                            )}
                                        </td>
                                        <td className="px-3 py-2 text-center">
                                            <ExitBadge info={exit} />
                                            {locked != null && (
                                                <span className="ml-1 text-[11px] text-teal-300 tabular-nums" title="P&L bloccato dalla chiusura a mercato">
                                                    bloccato {fmtSignedEur(locked)}
                                                </span>
                                            )}
                                        </td>
                                        <td className={`px-3 py-2 text-right font-bold tabular-nums ${isSettled ? (t.total_pnl > 0 ? 'text-emerald-400' : t.total_pnl < 0 ? 'text-red-400' : 'text-slate-300') : 'text-slate-500'}`} data-testid="day-trade-pnl">
                                            {isSettled ? fmtSignedEur(t.total_pnl) : (locked != null ? `(${fmtSignedEur(locked)})` : '—')}
                                        </td>
                                    </tr>,
                                    ...t.closes.map((c) => {
                                        const cb = statusBadge(c.status);
                                        const cLocked = lockedPnl(c);
                                        return (
                                            <tr key={`c${c.id}`} className="border-t border-white/5 bg-black/20 text-[12px]" data-testid="day-close-row">
                                                <td className="px-3 py-1 text-slate-500 tabular-nums">↳ {timeLabel(c.placed_at)}</td>
                                                <td className="px-3 py-1 text-slate-400" colSpan={2}>
                                                    chiusura #{c.id} di #{t.id}
                                                    {cappedFrom({ meta: c.meta }) != null && (
                                                        <Badge variant="outline" className="ml-1 px-1 py-0 text-[10px] bg-amber-500/15 text-amber-300 border-amber-500/40" title="liquidità insufficiente: chiusura parziale">parziale</Badge>
                                                    )}
                                                </td>
                                                <td className="px-3 py-1 text-slate-400 truncate">{selectionOf(c)}</td>
                                                <td className={`px-3 py-1 text-center font-bold ${c.side === 'back' ? 'text-sky-300' : 'text-rose-300'}`}>{String(c.side).toUpperCase()}</td>
                                                <td className="px-3 py-1 text-right tabular-nums">{c.price != null ? c.price.toFixed(2) : '—'}</td>
                                                <td className="px-3 py-1 text-right tabular-nums">{fmtEur(c.size)}</td>
                                                <td className="px-3 py-1 text-right tabular-nums text-slate-500">{fmtEur(c.liability)}</td>
                                                <td className="px-3 py-1 text-center"><Badge variant="outline" className={`${cb.cls} text-[10px]`}>{cb.label}</Badge></td>
                                                <td className="px-3 py-1 text-center">
                                                    <ExitBadge meta={c.meta} />
                                                    {cLocked != null && <span className="ml-1 text-[11px] text-teal-300 tabular-nums">bloccato {fmtSignedEur(cLocked)}</span>}
                                                </td>
                                                <td className={`px-3 py-1 text-right tabular-nums ${['won', 'lost', 'void'].includes(c.status) ? (c.pnl >= 0 ? 'text-emerald-300' : 'text-red-300') : 'text-slate-500'}`}>
                                                    {['won', 'lost', 'void'].includes(c.status) ? fmtSignedEur(c.pnl) : '—'}
                                                </td>
                                            </tr>
                                        );
                                    }),
                                ];
                            })}
                        </tbody>
                        <tfoot className="text-[11px] text-slate-400 bg-black/30">
                            <tr>
                                <td className="px-3 py-2" colSpan={8}>
                                    {settled.length} regolati · {openCount} vivi · {settled.filter((t) => Number(t.total_pnl ?? t.pnl) > 0).length}V {settled.filter((t) => Number(t.total_pnl ?? t.pnl) < 0).length}P
                                </td>
                                <td className="px-3 py-2 text-right" colSpan={3}>
                                    totale realizzato <b className={totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtSignedEur(totalPnl)}</b>
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            )}
        </Card>
    );
}

export default DayDetail;
