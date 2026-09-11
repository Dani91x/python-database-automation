// ============================================================================
// SafeTradesTable.tsx — tabella realtime dei trade SAFE STRATEGY.
//
// Stessa griglia della tabella Omega (Ora/Match/…/Stato/P&L) più le colonne
// proprie della sezione (strategia, mercato, selezione, lato) e il CASH OUT
// live su ogni posizione aperta. Il minuto/punteggio della colonna "Live"
// arriva dal feed unico dello scanner (useScanLiveFeed), mai da Betfair.
// L'USCITA AUTOMATICA (meta.exit_kind / exit_reason scritti dal servizio) e'
// mostrata come badge accanto allo stato, sia sull'apertura sia sulla chiusura.
// ============================================================================
import { Fragment } from 'react';
import { Badge } from '@/components/ui/badge';
import { CashOutButton } from '@/components/trading/CashOutButton';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { liveScoreLabel } from '@/lib/useScanLiveFeed';
import { tradeExit } from '@/lib/dailyHistory';
import type { CalcioScanPayload, TennisScanPayload } from '@/lib/safeStrategyScan';
import {
    cappedFrom, safeTradeBook, tradeExposure, staleReason, FEED_ROW_STALE_MS,
    tradeHold, holdReasonLabel, holdReasonHasP, pLoseEntry, tradeOppKind,
    groupClosingLegs, fmtEurIt, fmtOddsIt, hedgeTooltip, partialHedge,
    type FeedFreshness, type SafeTrade, type SafeTradeStatus,
} from '@/lib/safeBot';
import { OPP_KIND_META } from './OpportunityGroup';
import { sideBadgeClass } from './variantStyles';

/** "0,4%" — percentuale in formato italiano (virgola) */
export function pctIt(v: number | null, digits = 1): string {
    if (v == null || !Number.isFinite(v)) return '—';
    return `${(v * 100).toFixed(digits).replace('.', ',')}%`;
}

/** "52′ · 1-0" (calcio) oppure "set 1-0 · game 3-2" (tennis) dal feed. */
export function liveLabelOf(p: CalcioScanPayload | TennisScanPayload | null | undefined): string | null {
    if (!p) return null;
    if ('sets' in p) {
        const t = p as TennisScanPayload;
        if (!t.sets) return null;
        const games = t.games ? ` · game ${t.games.p1}-${t.games.p2}` : '';
        return `set ${t.sets.p1}-${t.sets.p2}${games}`;
    }
    return liveScoreLabel(p as CalcioScanPayload);
}

function fmtEur(v: number | null | undefined): string {
    const n = Number(v ?? 0);
    return `${n < 0 ? '−' : ''}€${Math.abs(n).toFixed(2)}`;
}
function fmtSignedEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}
function timeLabel(iso: string): string {
    return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

const STRATEGY_LABEL: Record<string, string> = {
    base: 'BASE', esatto: 'R. ESATTO', punta: 'PUNTA', tennis: 'TENNIS',
    model: 'MODELLO', manual: 'MANUALE',
};

export function tradeBadge(status: SafeTradeStatus): { label: string; cls: string } {
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

function lockedPnlOf(t: SafeTrade): number | null {
    const v = Number((t.meta ?? {})['locked_pnl']);
    return Number.isFinite(v) ? v : null;
}

export interface SafeTradesTableProps {
    trades: SafeTrade[];
    commissionPct: number;
    /** payload live per evento: calcio E tennis (stesso feed del radar) */
    liveFeed: Record<string, CalcioScanPayload | TennisScanPayload>;
    /** cash out gia' in volo per quel trade → bottone spento */
    isCashOutPending?: (tradeId: number) => boolean;
    /** freschezza della riga del feed per evento (quote stantie → spento) */
    freshnessOf?: (eventId: string) => FeedFreshness | null;
    onCashOut: (trade: SafeTrade, args: { amount?: number; fraction?: number }) => Promise<void> | void;
    /** testo dello stato vuoto (la pagina distingue "oggi" da "tutte") */
    emptyText?: string;
}

export function SafeTradesTable({
    trades, commissionPct, liveFeed, isCashOutPending, freshnessOf, onCashOut, emptyText,
}: SafeTradesTableProps) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead className="text-[11px] uppercase text-slate-500 bg-black/30">
                    <tr>
                        <th className="text-left px-3 py-2">Ora</th>
                        <th className="text-left px-3 py-2">Match</th>
                        <th className="text-center px-3 py-2">Strategia</th>
                        <th className="text-left px-3 py-2">Mercato</th>
                        <th className="text-left px-3 py-2">Selezione</th>
                        <th className="text-center px-3 py-2" title="LAY = banca · BACK = punta; la gamba di copertura ha il lato opposto">Lato</th>
                        <th className="text-right px-3 py-2">Quota</th>
                        <th className="text-right px-3 py-2">Stake</th>
                        <th className="text-right px-3 py-2">Liability</th>
                        <th className="text-center px-3 py-2" title="minuto e punteggio LIVE dal feed dello scanner">Live</th>
                        <th className="text-center px-3 py-2">Stato</th>
                        <th className="text-right px-3 py-2">P&L</th>
                        <th className="text-center px-3 py-2" title="chiudi a mercato bloccando il P&L">Cash out</th>
                    </tr>
                </thead>
                <tbody>
                    {trades.length === 0 ? (
                        <tr>
                            <td colSpan={13} className="text-center text-muted-foreground py-10" data-testid="safe-trades-empty">
                                {emptyText ?? "nessun trade ancora — piazza da un segnale o da un'opportunità, oppure avvia il bot"}
                            </td>
                        </tr>
                    ) : groupClosingLegs(trades).map(({ trade: t, closes }) => {
                        const closing = closes[0] ?? null;
                        const exit = tradeExit({ meta: t.meta, closes: closes.map((c) => ({ meta: c.meta })) as never });
                        const isGreenup = exit?.kind === 'greenup';
                        // cash out MANUALE: il servizio marca solo meta.cashout=true (nessun exit_kind)
                        const isManualCashout = !exit && closes.some((c) => c.origin === 'manual' || (c.meta ?? {})['cashout'] === true);
                        const hedged = t.status === 'hedged';
                        const partial = partialHedge(t);
                        const b = hedged && isGreenup
                            ? { label: 'CHIUSO IN GREEN-UP', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50' }
                            : tradeBadge(t.status);
                        const payload = liveFeed[t.event_id];
                        const isLive = ['pending', 'open'].includes(t.status);
                        // il punteggio live resta visibile anche sull'apertura gia' coperta
                        const live = isLive || hedged ? liveLabelOf(payload) : null;
                        const book = safeTradeBook(t, payload);
                        const exp = tradeExposure(t);
                        const locked = lockedPnlOf(t);
                        const fresh = isLive ? (freshnessOf?.(t.event_id) ?? null) : null;
                        const stale = staleReason(fresh);
                        const kind = tradeOppKind(t);
                        const hold = isLive ? tradeHold(t) : null;
                        const pEntry = kind ? pLoseEntry(t) : null;
                        const orphanClosing = t.closes_trade_id != null;
                        return (
                            <Fragment key={t.id}>
                            <tr className="border-t border-white/5 hover:bg-white/5" data-testid="safe-trade-row">
                                <td className="px-3 py-2 text-slate-400 tabular-nums">{timeLabel(t.placed_at)}</td>
                                <td className="px-3 py-2 max-w-[200px] truncate" title={t.event_name ?? t.event_id}>
                                    {t.origin === 'manual' && (
                                        <Badge variant="outline" className="mr-1.5 px-1 py-0 text-[10px] bg-violet-500/15 text-violet-300 border-violet-500/40" title="piazzato manualmente">✋</Badge>
                                    )}
                                    {t.event_name ?? t.event_id}
                                </td>
                                <td className="px-3 py-2 text-center text-[11px] font-heading font-bold text-slate-300">
                                    {kind ? (
                                        <Badge
                                            variant="outline"
                                            data-testid="trade-kind"
                                            data-kind={kind}
                                            className={`px-1.5 py-0 text-[10px] font-heading ${OPP_KIND_META[kind].badge}`}
                                            title={`trade di ${STRATEGY_LABEL.model.toLowerCase()} · ${OPP_KIND_META[kind].title}`}
                                        >
                                            {OPP_KIND_META[kind].label}
                                        </Badge>
                                    ) : (STRATEGY_LABEL[t.strategy] ?? t.strategy)}
                                    {pEntry != null && (
                                        <div className="mt-0.5 text-[10px] font-normal text-slate-500 tabular-nums" data-testid="trade-p-lose-entry" title="probabilità di perdita stimata all'ingresso">
                                            P(perdita) ingresso {pctIt(pEntry)}
                                        </div>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-[11px] text-slate-400 max-w-[140px] truncate" title={t.market_type ?? ''}>
                                    {t.market_type ?? '—'}
                                </td>
                                <td className="px-3 py-2 max-w-[160px] truncate" title={t.selection_name ?? ''}>
                                    {t.selection_name ?? '—'}
                                </td>
                                <td className="px-3 py-2 text-center">
                                    <Badge variant="outline" data-testid="safe-side" className={`px-1.5 py-0 text-[10px] font-heading font-bold ${sideBadgeClass(t.side === 'back' ? 'BACK' : 'LAY')}`}>
                                        {t.side.toUpperCase()}
                                    </Badge>
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">{t.price?.toFixed(2) ?? '—'}</td>
                                <td className="px-3 py-2 text-right tabular-nums">{fmtEur(t.size)}</td>
                                <td className="px-3 py-2 text-right tabular-nums text-orange-400/90">{fmtEur(t.liability)}</td>
                                <td className="px-3 py-2 text-center tabular-nums">
                                    {live ? (
                                        <span className={stale ? 'text-amber-300' : 'text-emerald-300'}>
                                            <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle ${stale ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'}`} aria-hidden />
                                            {live}
                                        </span>
                                    ) : <span className="text-slate-600">—</span>}
                                    {fresh?.ageSec != null && fresh.ageSec * 1000 > FEED_ROW_STALE_MS && (
                                        // riga vecchia: badge di eta' (scanner vivo = write-on-change,
                                        // nulla e' cambiato; scanner morto = quote stantie, bottoni spenti)
                                        <Badge
                                            variant="outline"
                                            data-testid="feed-age"
                                            className={`ml-1 px-1 py-0 text-[10px] ${stale ? 'bg-red-500/15 text-red-300 border-red-500/40' : 'bg-white/5 text-slate-400 border-white/10'}`}
                                            title={stale ? stale : 'riga del feed non riscritta di recente (nessuna variazione)'}
                                        >
                                            {fresh.ageSec}s
                                        </Badge>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-center">
                                    <Badge
                                        variant="outline"
                                        data-testid="safe-status"
                                        className={`whitespace-nowrap ${b.cls}`}
                                        title={hedged ? hedgeTooltip(t, closing) : undefined}
                                    >
                                        {b.label}
                                    </Badge>
                                    {!(hedged && isGreenup) && <ExitBadge meta={t.meta} className="ml-1" />}
                                    {hedged && exit?.reason && (
                                        <div className="mt-0.5 text-[10px] text-slate-400 whitespace-nowrap" data-testid="safe-exit-reason" title="motivo dell'uscita scritto dal servizio">
                                            {exit.reason}
                                        </div>
                                    )}
                                    {hold && (
                                        <div
                                            className="mt-0.5 text-[10px] text-sky-300/90 whitespace-nowrap tabular-nums"
                                            data-testid="trade-hold"
                                            title={[
                                                'il servizio tiene la posizione aperta',
                                                hold.source ? `fonte: ${hold.source}` : null,
                                                hold.evHold != null ? `EV tenere: ${fmtSignedEur(hold.evHold)}` : null,
                                                hold.locked != null ? `bloccabile ora: ${fmtSignedEur(hold.locked)}` : null,
                                                hold.ts ? `aggiornato ${timeLabel(hold.ts)}` : null,
                                            ].filter(Boolean).join(' · ')}
                                        >
                                            In attesa: {holdReasonLabel(hold.reason)}
                                            {hold.pLose != null && !holdReasonHasP(hold.reason) ? `, P(perdita) ${pctIt(hold.pLose)}` : ''}
                                        </div>
                                    )}
                                </td>
                                <td className={`px-3 py-2 text-right font-bold tabular-nums ${t.status === 'won' || (hedged && Number(locked ?? t.pnl) >= 0) ? 'text-emerald-400' : t.status === 'lost' || (hedged && Number(locked ?? t.pnl) < 0) ? 'text-red-400' : 'text-slate-400'}`}>
                                    {hedged ? (
                                        <span data-testid="safe-locked-pnl" title={hedgeTooltip(t, closing)}>
                                            {fmtEurIt(locked ?? Number(t.pnl), true)} <span className="font-normal text-[10px] text-teal-300">bloccato</span>
                                        </span>
                                    ) : ['won', 'lost', 'void'].includes(t.status) ? fmtSignedEur(Number(t.pnl)) : '—'}
                                </td>
                                <td className="px-3 py-2 text-center">
                                    {orphanClosing ? (
                                        <span className="text-[11px] text-slate-400" title="gamba di copertura del cash out">chiude #{t.closes_trade_id}</span>
                                    ) : t.status === 'open' ? (
                                        <CashOutButton
                                            compact
                                            // modalita' del TRADE: il servizio chiude con quella,
                                            // non con la modalita' corrente della pagina
                                            mode={t.mode}
                                            win={exp.win}
                                            lose={exp.lose}
                                            bestBack={book?.back ?? null}
                                            bestLay={book?.lay ?? null}
                                            commission={commissionPct}
                                            pending={isCashOutPending?.(t.id) ?? false}
                                            disabled={stale != null}
                                            disabledReason={stale}
                                            onCashOut={(a) => onCashOut(t, a)}
                                        />
                                    ) : hedged ? (
                                        <span className="text-[11px] text-teal-300" title="posizione chiusa a mercato: P&L bloccato">coperto</span>
                                    ) : <span className="text-slate-600">—</span>}
                                </td>
                            </tr>
                            {closes.map((c, ci) => {
                                const cb = tradeBadge(c.status);
                                // "parziale": dalla chiusura (size_capped_from) o dall'apertura (residuo > 0)
                                const capped = cappedFrom(c) ?? (partial && ci === closes.length - 1 ? partial.hedged + partial.residual : null);
                                return (
                                    <tr key={c.id} className="bg-white/[0.03] border-t border-dashed border-white/5" data-testid="safe-closing-row" data-closes={t.id}>
                                        <td className="px-3 py-1 text-slate-500 tabular-nums text-[11px]">{timeLabel(c.placed_at)}</td>
                                        <td colSpan={8} className="pl-8 pr-3 py-1 text-[11px] text-slate-300" title={hedgeTooltip(t, c)}>
                                            <span className="text-teal-300" aria-hidden>↳ </span>
                                            <b className="text-teal-200">{isGreenup ? 'Green-up' : (exit?.kind === 'manual' || isManualCashout) ? 'Cash out' : 'Chiusura'} di #{t.id}</b>
                                            {' · '}
                                            <Badge variant="outline" className={`px-1 py-0 text-[10px] font-heading font-bold mr-1 ${sideBadgeClass(c.side === 'back' ? 'BACK' : 'LAY')}`}>{c.side.toUpperCase()}</Badge>{' '}
                                            <span className="tabular-nums">{fmtEurIt(c.size)} @{fmtOddsIt(c.price)}</span>
                                            {c.selection_name && c.selection_name !== t.selection_name && <span className="text-slate-500"> · {c.selection_name}</span>}
                                        </td>
                                        <td className="px-3 py-1 text-center text-slate-600">—</td>
                                        <td className="px-3 py-1 text-center">
                                            <Badge variant="outline" className={`px-1.5 py-0 text-[10px] ${cb.cls}`}>{cb.label}</Badge>
                                            <ExitBadge meta={c.meta} className="ml-1" />
                                        </td>
                                        <td className="px-3 py-1 text-right text-[11px] text-slate-500 tabular-nums">
                                            {['won', 'lost', 'void', 'hedged'].includes(c.status) ? fmtSignedEur(Number(c.pnl)) : '—'}
                                        </td>
                                        <td className="px-3 py-1 text-center">
                                            <span className="text-[11px] text-slate-400" title="gamba di copertura del cash out">
                                                chiude #{t.id}
                                                {capped != null && (
                                                    <Badge
                                                        variant="outline"
                                                        data-testid="cashout-capped"
                                                        className="ml-1 px-1 py-0 text-[10px] bg-amber-500/15 text-amber-300 border-amber-500/40"
                                                        title={cappedFrom(c) != null
                                                            ? `liquidità insufficiente: richiesti €${capped.toFixed(2)}, abbinati €${Number(c.size ?? 0).toFixed(2)} — chiusura PARZIALE`
                                                            : `copertura PARZIALE: coperti €${partial?.hedged.toFixed(2)} di €${partial?.size.toFixed(2)} di stake, residuo €${partial?.residual.toFixed(2)} ancora vivo`}
                                                    >
                                                        parziale
                                                    </Badge>
                                                )}
                                            </span>
                                        </td>
                                    </tr>
                                );
                            })}
                            </Fragment>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

export default SafeTradesTable;
