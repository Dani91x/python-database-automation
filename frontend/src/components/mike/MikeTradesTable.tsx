// ============================================================================
// MikeTradesTable — tab "Trade" di Mike (design system §7).
//
// Prima: una tabella piatta di gambe, senza chiusure, senza uscita, senza
// modalità, senza giornata. Ora: le CHIUSURE sono annidate sotto l'apertura
// (`closes_trade_id`), ogni riga porta ora di Roma, partita, ruolo/gamba, lato,
// quota, size abbinata, stato in italiano, badge dell'uscita
// (`meta.exit_kind`/`exit_reason`), P&L NETTO con lordo e commissione nel
// tooltip, e le righe LIVE sono marcate. Toggle "solo oggi / tutte": il default
// è la GIORNATA OPERATIVA (giorno di PIAZZAMENTO della posizione, M6).
// ============================================================================
import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { SectionCard, EmptyState } from '@/components/trading/EmptyState';
import { fmtMoney, fmtOdds, fmtTime } from '@/lib/format';
import { statusMeta, sideMeta, T } from '@/lib/tradeStatus';
import { exitInfo } from '@/lib/dailyHistory';
import {
    groupMikeTrades, groupsOfDay, isManualTrade, marketLabel, roleLabel, MIKE_TRADES_LIMIT,
    type MikeTrade,
} from '@/lib/mike';

function isReconciling(t: MikeTrade): boolean {
    return t.status === 'pending' && (t.meta ?? {})['reason'] === 'place_exception_reconciling';
}

function pnlCellClass(v: number | null): string {
    if (v == null) return 'text-slate-400';
    return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300';
}

function pnlTitle(t: MikeTrade): string {
    const meta = t.meta ?? {};
    const gross = Number(meta.pnl_gross);
    const comm = Number(meta.commission_paid);
    const parts: string[] = [];
    if (Number.isFinite(gross)) parts.push(`lordo ${fmtMoney(gross, { signed: true })}`);
    if (Number.isFinite(comm)) parts.push(`commissione ${fmtMoney(comm)}`);
    if (meta.commission_market) parts.push(`mercato ${String(meta.commission_market)}`);
    return parts.length ? `${parts.join(' · ')} (P&L di riga NETTO)` : 'P&L di riga NETTO commissione';
}

const SETTLED = new Set(['won', 'lost', 'void']);

/**
 * Il void e' PER MERCATO: una riga annullata dice QUALE selezione e' stata
 * annullata ("VOID (Under 3.5)"), non "partita annullata".
 */
function voidLabel(t: MikeTrade): string {
    if (t.status !== 'void') return '';
    const sel = t.selection_name ?? marketLabel(t.market_type);
    return sel ? ` (${sel})` : '';
}

/** una posizione ancora VIVA: il cash out è per evento, si opera dalla scheda */
const OPEN_TRADE_STATES = new Set(['pending', 'open', 'hedged']);

export interface MikeTradesTableProps {
    trades: MikeTrade[];
    /** inizio della giornata operativa in ms (Europe/Rome) */
    dayStartMs: number | null;
    /** da dove viene la giornata: 'client' = stimata (senza mike_bot_v2.sql) */
    dayStartSource?: 'rpc' | 'client';
    /** etichetta della giornata, per il riepilogo */
    dayLabel?: string;
    /** riepilogo dagli aggregati del DB (mai ricontato dal client) */
    summary?: {
        openCount?: number | null;
        won?: number | null;
        lost?: number | null;
        lockedPnl?: number | null;
        openLiability?: number | null;
        reconciling?: number | null;
    };
    /**
     * Porta alla SCHEDA della partita (tab Partite + scroll sulla card): in
     * Mike il cash out è per EVENTO, quindi dalla tabella si rimanda là invece
     * di duplicare un bottone che chiuderebbe cose diverse.
     */
    onOpenEvent?: (eventId: string) => void;
}

export function MikeTradesTable({ trades, dayStartMs, dayStartSource = 'rpc', dayLabel, summary, onOpenEvent }: MikeTradesTableProps) {
    const [onlyToday, setOnlyToday] = useState(true);
    const groups = useMemo(() => groupMikeTrades(trades), [trades]);
    const shown = useMemo(
        () => (onlyToday ? groupsOfDay(groups, dayStartMs) : groups),
        [groups, onlyToday, dayStartMs],
    );

    const note = summary ? (
        <>
            {trades.length >= MIKE_TRADES_LIMIT && (
                <span className="text-amber-300" data-testid="mike-trades-capped">
                    mostrate le ultime {MIKE_TRADES_LIMIT} righe (tetto della RPC) ·{' '}
                </span>
            )}
            {onlyToday && (dayStartMs == null || dayStartSource === 'client') && (
                <span className="text-amber-300" data-testid="mike-trades-noday">
                    {dayStartMs == null
                        ? 'giornata operativa non dichiarata dal DB (applica migrations/mike_bot_v2.sql): mostro tutte le righe'
                        : 'giornata operativa stimata dal client (mezzanotte di Roma): applica migrations/mike_bot_v2.sql'} ·{' '}
                </span>
            )}
            posizioni aperte <b className="text-slate-200">{summary.openCount ?? 0}</b>
            {' · '}<b className="text-emerald-400">{summary.won ?? 0}V</b>{' '}
            <b className="text-red-400">{summary.lost ?? 0}P</b>
            {summary.lockedPnl != null && <> · {T.lockedPnl} <b className={summary.lockedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtMoney(summary.lockedPnl, { signed: true })}</b></>}
            {summary.openLiability != null && <> · {T.openLiability} <b className="text-orange-400">{fmtMoney(summary.openLiability)}</b></>}
            {summary.reconciling ? <> · <b className="text-fuchsia-300">{summary.reconciling} in verifica</b></> : null}
        </>
    ) : null;

    return (
        <SectionCard
            title={onlyToday ? `Trade della ${T.operatingDay}${dayLabel ? ` · ${dayLabel}` : ''}` : 'Tutti i trade caricati'}
            count={shown.length}
            note={note}
            testId="mike-trades"
            actions={
                <Button
                    type="button" size="sm" variant="outline" className="h-7 text-[11px]"
                    aria-pressed={!onlyToday}
                    onClick={() => setOnlyToday((v) => !v)}
                    data-testid="mike-trades-toggle"
                >{onlyToday ? 'mostra tutte' : 'solo oggi'}</Button>
            }
        >
            {shown.length === 0 ? (
                <div className="p-3">
                    <EmptyState>
                        Nessun trade {onlyToday ? `nella ${T.operatingDay}` : 'caricato'}. Le righe compaiono al primo
                        ordine piazzato dal bot; le chiusure stanno annidate sotto la loro apertura.
                    </EmptyState>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-[12px]" data-testid="mike-trades-table">
                        <thead className="text-slate-500 uppercase tracking-wide text-[10px]">
                            <tr>
                                <th className="text-left font-normal px-3 py-2">Ora</th>
                                <th className="text-left font-normal">Partita</th>
                                <th className="text-left font-normal">Gamba</th>
                                <th className="text-left font-normal">Lato</th>
                                <th className="text-right font-normal">Quota</th>
                                <th className="text-right font-normal">Size</th>
                                <th className="text-left font-normal pl-3">Stato</th>
                                <th className="text-left font-normal">Uscita</th>
                                <th className="text-right font-normal px-3">P&amp;L netto</th>
                            </tr>
                        </thead>
                        <tbody>
                            {shown.map((g) => {
                                const t = g.open;
                                const sb = statusMeta(t.status, { reconciling: isReconciling(t) });
                                const sd = sideMeta(t.side);
                                return [
                                    <tr key={t.id} className="border-t border-white/10" data-testid="mike-trade-row" data-trade-id={t.id}>
                                        <td className="px-3 py-1.5 tabular-nums text-slate-400">{fmtTime(t.placed_at, { seconds: true })}</td>
                                        <td className="max-w-[220px]">
                                            <span className="block truncate">{t.event_name ?? t.event_id}</span>
                                            {onOpenEvent && OPEN_TRADE_STATES.has(t.status) && (
                                                <button
                                                    type="button"
                                                    className="text-[10px] text-teal-300 hover:text-teal-200 underline decoration-dotted"
                                                    onClick={() => onOpenEvent(t.event_id)}
                                                    data-testid="mike-trade-goto-card"
                                                    data-event-id={t.event_id}
                                                    title="posizione ancora aperta: il cash out si fa dalla scheda della partita"
                                                >→ scheda partita</button>
                                            )}
                                        </td>
                                        <td>
                                            {isManualTrade(t) && <span title="deciso dall'utente" aria-label="manuale">✋ </span>}
                                            {roleLabel(t.role ?? t.strategy)}
                                            <span className="text-slate-500"> {t.selection_name ?? ''}</span>
                                            {g.orphan && <span className="ml-1 text-[9px] text-amber-300" title="chiusura senza apertura fra le righe caricate">orfana</span>}
                                        </td>
                                        <td><Badge variant="outline" className={`text-[9px] ${sd.cls}`}>{sd.label}</Badge></td>
                                        <td className="text-right tabular-nums">{fmtOdds(t.price)}</td>
                                        <td className="text-right tabular-nums">{fmtMoney(t.size)}</td>
                                        <td className="pl-3">
                                            <Badge variant="outline" className={`text-[9px] ${sb.cls}`} data-testid="mike-trade-status">
                                                {sb.label}{voidLabel(t)}
                                            </Badge>
                                            {t.mode === 'live' && <span className="ml-1 text-[9px] text-red-300 font-bold" data-testid="mike-trade-live">LIVE</span>}
                                        </td>
                                        <td><ExitBadge meta={t.meta} /></td>
                                        <td
                                            className={`text-right tabular-nums px-3 font-semibold ${pnlCellClass(g.netPnl)}`}
                                            title={pnlTitle(t)}
                                            data-testid="mike-trade-pnl"
                                        >
                                            {g.netPnl != null ? fmtMoney(g.netPnl, { signed: true }) : '—'}
                                        </td>
                                    </tr>,
                                    ...g.closes.map((c) => {
                                        const cb = statusMeta(c.status, { reconciling: isReconciling(c) });
                                        const cd = sideMeta(c.side);
                                        const info = exitInfo(c.meta);
                                        return (
                                            <tr key={`c${c.id}`} className="border-t border-white/5 bg-black/20 text-[11px]" data-testid="mike-trade-close" data-closes={t.id}>
                                                <td className="px-3 py-1 tabular-nums text-slate-500">↳ {fmtTime(c.placed_at, { seconds: true })}</td>
                                                <td className="text-slate-500 truncate max-w-[200px]">chiusura</td>
                                                <td className="text-slate-300">
                                                    {isManualTrade(c) && <span title="deciso dall'utente" aria-label="manuale">✋ </span>}
                                                    {roleLabel(c.role ?? c.strategy)}
                                                    <span className="text-slate-500"> {c.selection_name ?? ''}</span>
                                                </td>
                                                <td><Badge variant="outline" className={`text-[9px] ${cd.cls}`}>{cd.label}</Badge></td>
                                                <td className="text-right tabular-nums">{fmtOdds(c.price)}</td>
                                                <td className="text-right tabular-nums">{fmtMoney(c.size)}</td>
                                                <td className="pl-3">
                                                    <Badge variant="outline" className={`text-[9px] ${cb.cls}`} data-testid="mike-trade-status">
                                                        {cb.label}{voidLabel(c)}
                                                    </Badge>
                                                </td>
                                                <td><ExitBadge info={info} /></td>
                                                <td
                                                    className={`text-right tabular-nums px-3 ${pnlCellClass(SETTLED.has(c.status) ? Number(c.pnl) : null)}`}
                                                    title={pnlTitle(c)}
                                                >
                                                    {SETTLED.has(c.status) ? fmtMoney(Number(c.pnl), { signed: true }) : '—'}
                                                </td>
                                            </tr>
                                        );
                                    }),
                                ];
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </SectionCard>
    );
}

export default MikeTradesTable;
