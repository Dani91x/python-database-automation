// ============================================================================
// SafeTradesTable.tsx — tabella realtime delle POSIZIONI Safe Strategy.
//
// Una riga = una POSIZIONE (l'apertura); le gambe di chiusura stanno annidate
// sotto con "↳", mai come trade a sé (un back a 4,90 accanto a un lay a 55
// confonde). Il minuto/punteggio della colonna "Live" e la quota ORA arrivano
// dal feed UNICO dello scanner, mai da Betfair.
//
// Cosa deve leggere un trader su ogni riga, senza aprire nulla:
//   quota d'ingresso → quota ORA (best del lato di chiusura) → Δ tick →
//   "se chiudo ora" NETTO della commissione DEL TRADE → stato in italiano
//   (IN CORSO / IN VERIFICA SU BETFAIR / APERTO / COPERTA x % / CHIUSO IN
//   GREEN-UP / CASH OUT MANUALE / USCITA FALLITA / SENZA FEED / VINTO / PERSO
//   / VOID / ERRORE DEFINITIVO) → P&L netto.
//
// Formati: SOLO lib/format.ts (denaro "12,50 €", quote "2,04", ore Europe/Rome).
// ============================================================================
import { Fragment } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CashOutButton, greenPrice, hedgeSide, netAfterCommission } from '@/components/trading/CashOutButton';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { lockedPnlAt } from '@/lib/ladderMath';
import { liveScoreLabel } from '@/lib/useScanLiveFeed';
import { tradeExit } from '@/lib/dailyHistory';
import { fmtMoney, fmtOdds, fmtPct, fmtTime, DASH } from '@/lib/format';
import { statusMeta, T } from '@/lib/tradeStatus';
import { ticksBetween } from '@/lib/riskMath';
import type { CalcioScanPayload, TennisScanPayload } from '@/lib/safeStrategyScan';
import {
    blindSince, cappedFrom, comboIncomplete, errorFinal, exitRunState, hedgeState, isReconciling,
    lastRequestFor, marketBlocked, requestOutcome, safeTradeBook, staleReason,
    tradeCommission, tradeExposureNow, FEED_ROW_STALE_MS,
    tradeHold, holdReasonLabel, holdReasonHasP, pLoseEntry, tradeOppKind,
    groupClosingLegs, hedgeTooltip, partialHedge,
    type FeedFreshness, type SafeRequest, type SafeTrade, type SafeTradeStatus, type TradeBook,
} from '@/lib/safeBot';
import { safeReasonLabel } from './safeActivity';
import { OPP_KIND_META } from './OpportunityGroup';
import { sideBadgeClass } from './variantStyles';

/** ALIAS storico: la percentuale della sezione è `fmtPct` di lib/format.ts
 *  ("0,4 %", DESIGN_SYSTEM.md §2). Conservato solo per i chiamanti esistenti:
 *  nel codice nuovo usa direttamente `fmtPct` / `fmtPctPoints`. */
export function pctIt(v: number | null, digits = 1): string {
    return fmtPct(v, digits);
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

/** Risultato REALE della partita dal feed (per le posizioni già regolate). */
export function realScoreOf(p: CalcioScanPayload | TennisScanPayload | null | undefined): string | null {
    if (!p) return null;
    if ('sets' in p) {
        const t = p as TennisScanPayload;
        return t.sets ? `set ${t.sets.p1}-${t.sets.p2}` : null;
    }
    const c = p as CalcioScanPayload;
    return c.score_home != null && c.score_away != null ? `${c.score_home}-${c.score_away}` : null;
}

const STRATEGY_LABEL: Record<string, string> = {
    base: 'BASE', esatto: 'R. ESATTO', punta: 'PUNTA', tennis: 'TENNIS',
    model: 'MODELLO', manual: 'MANUALE',
};

/** Stato di una GAMBA (etichette unificate del design system). */
export function tradeBadge(status: SafeTradeStatus): { label: string; cls: string } {
    return statusMeta(status);
}

function lockedPnlOf(t: SafeTrade): number | null {
    const v = Number((t.meta ?? {})['locked_pnl']);
    return Number.isFinite(v) ? v : null;
}

const CLS = {
    amber: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    sky: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
    teal: 'bg-teal-500/15 text-teal-300 border-teal-500/40',
    green: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50',
    red: 'bg-red-500/15 text-red-300 border-red-500/40',
    orange: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
    violet: 'bg-violet-500/15 text-violet-300 border-violet-500/40',
    fuchsia: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/40',
};

export interface RowStatus {
    label: string;
    cls: string;
    title?: string;
    /** classe del bordo sinistro della riga (esito a colpo d'occhio) */
    edge: string;
}

/**
 * Stato della POSIZIONE in italiano, in ordine di gravità: prima ciò che
 * richiede una decisione (verifica su Betfair, uscita fallita, feed assente),
 * poi l'esito. PURA e testabile: è il cuore di quello che il trader legge.
 */
export function safeRowStatus(
    t: SafeTrade,
    closes: SafeTrade[] = [],
    nowIso?: string | null,
): RowStatus {
    void nowIso;
    const err = errorFinal(t);
    if (err || t.status === 'error') {
        return {
            label: 'ERRORE DEFINITIVO', cls: CLS.orange, edge: 'border-l-orange-500/60',
            title: err?.detail
                ? `errore definitivo: ${err.detail}${err.at ? ` (${fmtTime(err.at)})` : ''}`
                : 'la gamba è in errore: nessun ordine a mercato, nessuna liability',
        };
    }
    if (isReconciling(t)) {
        return {
            label: 'IN VERIFICA SU BETFAIR', cls: CLS.fuchsia, edge: 'border-l-fuchsia-500/60',
            title: 'ordine a esito IGNOTO: potrebbe essere vivo su Betfair. Conta nella liability aperta finché il servizio non lo riconcilia.',
        };
    }
    const exit = tradeExit({ meta: t.meta, closes: closes.map((c) => ({ meta: c.meta })) as never });
    const run = exitRunState(t);
    const hedge = hedgeState(t);
    const partialPct = hedge && !hedge.complete && hedge.fraction != null ? hedge.fraction : null;
    if (comboIncomplete(t) && (t.status === 'open' || t.status === 'pending')) {
        // il profitto BLOCCATO della combinazione non esiste più: una gamba non
        // si è abbinata e il servizio sta svolgendo il resto
        return {
            label: 'COMBO INCOMPLETA: in chiusura', cls: CLS.red, edge: 'border-l-red-500/60',
            title: 'una gamba della combinazione non si è abbinata: il profitto bloccato è saltato e il servizio sta chiudendo le gambe rimaste',
        };
    }

    if (t.status === 'won' || t.status === 'lost' || t.status === 'void') {
        const m = statusMeta(t.status);
        return {
            label: m.label, cls: m.cls,
            edge: t.status === 'won' ? 'border-l-emerald-500/60'
                : t.status === 'lost' ? 'border-l-red-500/60' : 'border-l-slate-500/40',
        };
    }
    if (t.status === 'hedged') {
        if (partialPct != null) {
            return {
                label: `COPERTA ${Math.round(partialPct * 100)} %`, cls: CLS.amber, edge: 'border-l-amber-500/60',
                title: `copertura PARZIALE: restano ${fmtMoney(hedge?.remainingLiability ?? hedge?.residualSize)} da chiudere`,
            };
        }
        if (exit?.kind === 'greenup') {
            return { label: 'CHIUSO IN GREEN-UP', cls: CLS.green, edge: 'border-l-emerald-500/60', title: hedgeTooltip(t, closes[0] ?? null) };
        }
        const manual = exit?.kind === 'manual'
            || closes.some((c) => c.origin === 'manual' || (c.meta ?? {})['cashout'] === true);
        if (manual) {
            return { label: 'CASH OUT MANUALE', cls: CLS.violet, edge: 'border-l-violet-500/60', title: hedgeTooltip(t, closes[0] ?? null) };
        }
        // glossario §3: lo stato e' "CHIUSO" ("CHIUSO A MERCATO" non e' uno stato)
        const m = statusMeta('hedged');
        return { label: m.label, cls: m.cls, edge: 'border-l-teal-500/60', title: hedgeTooltip(t, closes[0] ?? null) };
    }
    if (t.status === 'open' || t.status === 'pending') {
        if (run?.state === 'failed') {
            return {
                label: 'USCITA FALLITA', cls: CLS.red, edge: 'border-l-red-500/60',
                title: [
                    "l'uscita automatica non è riuscita: la liability è ancora a rischio",
                    run.attempts != null ? `${run.attempts} tentativi` : null,
                    run.lastError ? `ultimo errore: ${run.lastError}` : null,
                ].filter(Boolean).join(' · '),
            };
        }
        const blind = blindSince(t);
        if (blind) {
            return {
                label: `SENZA FEED da ${fmtTime(blind)}`, cls: CLS.red, edge: 'border-l-red-500/60',
                title: 'posizione viva ma il mercato non è più nel feed: nessuna uscita automatica possibile',
            };
        }
        if (partialPct != null) {
            return {
                label: `COPERTA ${Math.round(partialPct * 100)} %`, cls: CLS.amber, edge: 'border-l-amber-500/60',
                title: `copertura PARZIALE: restano ${fmtMoney(hedge?.remainingLiability ?? hedge?.residualSize)} da chiudere`,
            };
        }
        const m = statusMeta(t.status);
        return { label: m.label, cls: m.cls, edge: t.status === 'open' ? 'border-l-sky-500/50' : 'border-l-amber-500/50' };
    }
    const m = statusMeta(t.status);
    return { label: m.label, cls: m.cls, edge: 'border-l-white/10' };
}

/** Riga "in corso" dell'uscita automatica: cosa sta facendo il servizio (H-05). */
export function exitRunLine(t: SafeTrade): string | null {
    const r = exitRunState(t);
    if (!r) return null;
    const at = r.nextRetryAt ? ` alle ${fmtTime(r.nextRetryAt)}` : '';
    if (r.state === 'failed') {
        return r.nextRetryAt
            ? `USCITA FALLITA, ritento${at}`
            : `USCITA FALLITA${r.attempts != null ? ` dopo ${r.attempts} tentativi` : ''}`;
    }
    if (r.state === 'retrying') return `uscita: ritento${at}${r.attempts != null ? ` (${r.attempts}°)` : ''}`;
    if (r.state === 'waiting_price') return 'uscita: in attesa di prezzo';
    return null;
}

export interface SafeTradesTableProps {
    trades: SafeTrade[];
    /** aliquota di fallback: la commissione VERA è quella del trade */
    commissionPct: number;
    /** payload live per evento: calcio E tennis (stesso feed del radar) */
    liveFeed: Record<string, CalcioScanPayload | TennisScanPayload>;
    /** cash out gia' in volo per quel trade → bottone spento */
    isCashOutPending?: (tradeId: number) => boolean;
    /** freschezza della riga del feed per evento (quote stantie → spento) */
    freshnessOf?: (eventId: string) => FeedFreshness | null;
    onCashOut: (trade: SafeTrade, args: { amount?: number; fraction?: number }) => Promise<void> | void;
    /** annulla una RISERVA pending (kind 'cancel'); assente = nessun bottone */
    onCancel?: (trade: SafeTrade) => Promise<void> | void;
    /** ultime richieste operative: esito visibile sulla riga (L-07) */
    requests?: SafeRequest[];
    /** testo dello stato vuoto (la pagina distingue "oggi" da "tutte") */
    emptyText?: string;
}

const COLS = 16;

export function SafeTradesTable({
    trades, commissionPct, liveFeed, isCashOutPending, freshnessOf, onCashOut, onCancel,
    requests = [], emptyText,
}: SafeTradesTableProps) {
    const groups = groupClosingLegs(trades);
    // oltre 200 righe caricate una chiusura può perdere la sua apertura: va
    // detto, non mascherato (audit L-04)
    const orphans = groups.filter((g) => g.trade.closes_trade_id != null).length;
    return (
        <div className="overflow-x-auto">
            {orphans > 0 && (
                <p className="px-3 py-2 text-[11px] text-amber-300/90" data-testid="safe-orphan-note">
                    {orphans} {orphans === 1 ? 'gamba di chiusura' : 'gambe di chiusura'} senza la loro apertura fra
                    le righe caricate (limite di 200): la posizione completa è nello Storico.
                </p>
            )}
            <table className="w-full text-sm">
                <thead className="text-[11px] uppercase text-slate-500 bg-black/30">
                    <tr>
                        <th className="text-left px-3 py-2" title="ora di piazzamento, orologio di Roma">Ora (Roma)</th>
                        <th className="text-left px-3 py-2">Partita</th>
                        <th className="text-center px-3 py-2">Strategia</th>
                        <th className="text-left px-3 py-2">Mercato</th>
                        <th className="text-left px-3 py-2">Selezione</th>
                        <th className="text-center px-3 py-2" title="LAY = banca · BACK = punta; la gamba di copertura ha il lato opposto">Lato</th>
                        <th className="text-right px-3 py-2" title="quota di ingresso">Quota</th>
                        <th className="text-right px-3 py-2" title="miglior quota ORA sul lato con cui si chiude (dal feed)">Quota ora</th>
                        <th className="text-right px-3 py-2" title="tick di movimento dall'ingresso: positivo = a favore">Δ tick</th>
                        <th className="text-right px-3 py-2">Stake</th>
                        <th className="text-right px-3 py-2">Liability</th>
                        <th className="text-right px-3 py-2" title="P&L che si bloccherebbe chiudendo ADESSO, al netto della commissione del trade">Se chiudo ora</th>
                        <th className="text-center px-3 py-2" title="minuto e punteggio LIVE dal feed dello scanner">Live</th>
                        <th className="text-center px-3 py-2">Stato</th>
                        <th className="text-right px-3 py-2">P&L</th>
                        <th className="text-center px-3 py-2" title="chiudi a mercato bloccando il P&L">{T.cashOut}</th>
                    </tr>
                </thead>
                <tbody>
                    {trades.length === 0 ? (
                        <tr>
                            <td colSpan={COLS} className="text-center text-muted-foreground py-10" data-testid="safe-trades-empty">
                                {emptyText ?? "nessun trade ancora — piazza da un segnale o da un'opportunità, oppure avvia il bot"}
                            </td>
                        </tr>
                    ) : groups.map(({ trade: t, closes }) => {
                        const closing = closes[0] ?? null;
                        const exit = tradeExit({ meta: t.meta, closes: closes.map((c) => ({ meta: c.meta })) as never });
                        const isGreenup = exit?.kind === 'greenup';
                        const isManualCashout = !exit && closes.some((c) => c.origin === 'manual' || (c.meta ?? {})['cashout'] === true);
                        const hedged = t.status === 'hedged';
                        const partial = partialHedge(t);
                        const hedge = hedgeState(t);
                        const st = safeRowStatus(t, closes);
                        const payload = liveFeed[t.event_id];
                        const settled = ['won', 'lost', 'void'].includes(t.status);
                        const isLive = ['pending', 'open'].includes(t.status);
                        // il punteggio live resta visibile anche sull'apertura gia' coperta
                        const live = isLive || hedged ? liveLabelOf(payload) : null;
                        const realScore = settled ? realScoreOf(payload) : null;
                        const book: TradeBook | null = safeTradeBook(t, payload);
                        const exp = tradeExposureNow(t);
                        const commission = tradeCommission(t, commissionPct);
                        // quota ORA = best del lato con cui si CHIUDE (mirror di CashOutButton)
                        const closeSide = hedgeSide(exp.win, exp.lose);
                        const nowPrice = greenPrice(exp.win, exp.lose, book?.back ?? null, book?.lay ?? null);
                        const dTicks = nowPrice != null && t.price != null && t.price > 1
                            ? ticksBetween(t.price, nowPrice) * (t.side === 'lay' ? -1 : 1)
                            : null;
                        const closeNow = nowPrice != null
                            ? netAfterCommission(lockedPnlAt(nowPrice, exp.win, exp.lose), commission)
                            : null;
                        const locked = lockedPnlOf(t);
                        const fresh = isLive ? (freshnessOf?.(t.event_id) ?? null) : null;
                        const stale = staleReason(fresh);
                        const blocked = isLive ? marketBlocked(book) : null;
                        const kind = tradeOppKind(t);
                        const hold = isLive ? tradeHold(t) : null;
                        const runLine = isLive ? exitRunLine(t) : null;
                        const pEntry = kind ? pLoseEntry(t) : null;
                        const orphanClosing = t.closes_trade_id != null;
                        const reason = safeReasonLabel(String((t.meta ?? {})['reason'] ?? '') || null);
                        const outcome = requestOutcome(lastRequestFor(t.id, requests));
                        const canCashOut = t.status === 'open'
                            || (t.status === 'hedged' && hedge != null && !hedge.complete);
                        return (
                            <Fragment key={t.id}>
                            <tr className={`border-t border-white/5 border-l-2 ${st.edge} hover:bg-white/5`} data-testid="safe-trade-row" data-status={st.label}>
                                <td className="px-3 py-2 text-slate-400 tabular-nums">{fmtTime(t.placed_at)}</td>
                                <td className="px-3 py-2 max-w-[200px] truncate" title={t.event_name ?? t.event_id}>
                                    {t.origin === 'manual' && (
                                        <Badge variant="outline" className={`mr-1.5 px-1 py-0 text-[10px] ${CLS.violet}`} title="piazzato manualmente">✋</Badge>
                                    )}
                                    {t.event_name ?? t.event_id}
                                    {realScore && (
                                        <span className="ml-1.5 text-[10px] text-slate-400 tabular-nums" data-testid="safe-real-score" title="risultato reale della partita dal feed">
                                            ({realScore})
                                        </span>
                                    )}
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
                                            P(perdita) ingresso {fmtPct(pEntry)}
                                        </div>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-[11px] text-slate-400 max-w-[140px] truncate" title={[t.market_type, t.market_id ? `mercato ${t.market_id}` : null, t.selection_id != null ? `selezione ${t.selection_id}` : null].filter(Boolean).join(' · ')}>
                                    {t.market_type ?? DASH}
                                </td>
                                <td className="px-3 py-2 max-w-[160px] truncate" title={t.selection_name ?? ''}>
                                    {t.selection_name ?? DASH}
                                </td>
                                <td className="px-3 py-2 text-center">
                                    <Badge variant="outline" data-testid="safe-side" className={`px-1.5 py-0 text-[10px] font-heading font-bold ${sideBadgeClass(t.side === 'back' ? 'BACK' : 'LAY')}`}>
                                        {t.side.toUpperCase()}
                                    </Badge>
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">{fmtOdds(t.price)}</td>
                                <td className="px-3 py-2 text-right tabular-nums" data-testid="safe-price-now">
                                    {nowPrice != null ? (
                                        <span
                                            className={stale ? 'text-amber-300' : 'text-white/90'}
                                            title={`miglior ${closeSide === 'lay' ? 'lay' : 'back'} disponibile${book?.marketId ? ` · mercato ${book.marketId}` : ''}${book?.source ? ` (feed: ${book.source})` : ''}`}
                                        >
                                            {fmtOdds(nowPrice)}
                                        </span>
                                    ) : <span className="text-slate-600">{DASH}</span>}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums" data-testid="safe-tick-delta">
                                    {dTicks != null ? (
                                        <span className={dTicks > 0 ? 'text-emerald-400' : dTicks < 0 ? 'text-red-400' : 'text-slate-400'}>
                                            {dTicks > 0 ? '+' : dTicks < 0 ? '−' : ''}{Math.abs(dTicks)}
                                        </span>
                                    ) : <span className="text-slate-600">{DASH}</span>}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(t.size)}</td>
                                <td className="px-3 py-2 text-right tabular-nums text-orange-400/90" title={hedge?.inFlight
                                    ? 'copertura IN VOLO: l’ordine non è ancora abbinato, il rischio è ancora quello pieno'
                                    : hedge?.remainingLiability != null ? `liability RESIDUA dopo la copertura: ${fmtMoney(hedge.remainingLiability)}` : undefined}>
                                    {fmtMoney(hedge?.remainingLiability ?? t.liability)}
                                    {hedge?.inFlight && (
                                        <div className="text-[10px] text-amber-300 whitespace-nowrap" data-testid="safe-hedge-inflight">
                                            rischio ancora pieno: copertura in volo
                                        </div>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums" data-testid="safe-close-now">
                                    {closeNow != null ? (
                                        <span
                                            className={closeNow >= 0 ? 'text-emerald-300' : 'text-red-300'}
                                            title={`chiudendo ora: ${fmtMoney(closeNow, { signed: true })} netto (commissione ${fmtPct(commission > 1 ? commission / 100 : commission)})`}
                                        >
                                            {fmtMoney(closeNow, { signed: true })}
                                        </span>
                                    ) : <span className="text-slate-600">{DASH}</span>}
                                </td>
                                <td className="px-3 py-2 text-center tabular-nums">
                                    {live ? (
                                        <span className={stale ? 'text-amber-300' : 'text-emerald-300'}>
                                            <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle ${stale ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'}`} aria-hidden />
                                            {live}
                                        </span>
                                    ) : <span className="text-slate-600">{DASH}</span>}
                                    {fresh?.ageSec != null && fresh.ageSec * 1000 > FEED_ROW_STALE_MS && (
                                        // riga vecchia: badge di eta' (scanner vivo = write-on-change,
                                        // nulla e' cambiato; scanner morto = quote stantie, bottoni spenti)
                                        <Badge
                                            variant="outline"
                                            data-testid="feed-age"
                                            className={`ml-1 px-1 py-0 text-[10px] ${stale ? CLS.red : 'bg-white/5 text-slate-400 border-white/10'}`}
                                            title={stale ? `${T.feedStopped}: ${stale}` : 'riga del feed non riscritta di recente (nessuna variazione)'}
                                        >
                                            {stale ? `${T.feedStopped} ${fresh.ageSec}s` : `${fresh.ageSec}s`}
                                        </Badge>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-center">
                                    <Badge
                                        variant="outline"
                                        data-testid="safe-status"
                                        className={`whitespace-nowrap ${st.cls}`}
                                        title={st.title}
                                    >
                                        {st.label}
                                    </Badge>
                                    {!(hedged && isGreenup) && <ExitBadge meta={t.meta} className="ml-1" />}
                                    {runLine && (
                                        <div className="mt-0.5 text-[10px] text-red-300 whitespace-nowrap" data-testid="safe-exit-run" title="stato dell'uscita automatica scritto dal servizio">
                                            {runLine}
                                        </div>
                                    )}
                                    {hedged && exit?.reason && (
                                        <div className="mt-0.5 text-[10px] text-slate-400 whitespace-nowrap" data-testid="safe-exit-reason" title="motivo dell'uscita scritto dal servizio">
                                            {exit.reason}
                                        </div>
                                    )}
                                    {blocked && (
                                        <div className="mt-0.5 text-[10px] text-amber-300 whitespace-nowrap" data-testid="safe-market-blocked">
                                            {blocked}
                                        </div>
                                    )}
                                    {isReconciling(t) && reason && (
                                        <div className="mt-0.5 text-[10px] text-fuchsia-300/90 whitespace-nowrap" data-testid="safe-reason">{reason}</div>
                                    )}
                                    {hold && (
                                        <div
                                            className="mt-0.5 text-[10px] text-sky-300/90 whitespace-nowrap tabular-nums"
                                            data-testid="trade-hold"
                                            title={[
                                                'il servizio tiene la posizione aperta',
                                                hold.source ? `fonte: ${hold.source}` : null,
                                                hold.evHold != null ? `EV tenere: ${fmtMoney(hold.evHold, { signed: true })}` : null,
                                                hold.locked != null ? `bloccabile ora: ${fmtMoney(hold.locked, { signed: true })}` : null,
                                                hold.ts ? `aggiornato ${fmtTime(hold.ts)}` : null,
                                            ].filter(Boolean).join(' · ')}
                                        >
                                            In attesa: {holdReasonLabel(hold.reason)}
                                            {hold.pLose != null && !holdReasonHasP(hold.reason) ? `, P(perdita) ${fmtPct(hold.pLose)}` : ''}
                                        </div>
                                    )}
                                    {outcome && (
                                        <div
                                            className={`mt-0.5 text-[10px] whitespace-nowrap ${outcome.tone === 'ok' ? 'text-emerald-300' : outcome.tone === 'pending' ? 'text-amber-300' : 'text-red-300'}`}
                                            data-testid="safe-request-outcome"
                                            data-tone={outcome.tone}
                                            title={outcome.message ?? undefined}
                                        >
                                            {outcome.label}{outcome.message ? `: ${outcome.message}` : ''}
                                        </div>
                                    )}
                                </td>
                                <td className={`px-3 py-2 text-right font-bold tabular-nums ${t.status === 'won' || (hedged && Number(locked ?? t.pnl) >= 0) ? 'text-emerald-400' : t.status === 'lost' || (hedged && Number(locked ?? t.pnl) < 0) ? 'text-red-400' : 'text-slate-400'}`}>
                                    {hedged ? (
                                        <span data-testid="safe-locked-pnl" title={hedgeTooltip(t, closing)}>
                                            {fmtMoney(locked ?? Number(t.pnl), { signed: true })} <span className="font-normal text-[10px] text-teal-300">bloccato</span>
                                        </span>
                                    ) : settled ? (
                                        <span title={`al netto della commissione del trade (${fmtPct(commission > 1 ? commission / 100 : commission)})`}>
                                            {fmtMoney(Number(t.pnl), { signed: true })}
                                        </span>
                                    ) : DASH}
                                </td>
                                <td className="px-3 py-2 text-center">
                                    {orphanClosing ? (
                                        <span className="text-[11px] text-slate-400" title="gamba di copertura del cash out">chiude #{t.closes_trade_id}</span>
                                    ) : canCashOut ? (
                                        <CashOutButton
                                            compact
                                            // modalita' del TRADE: il servizio chiude con quella,
                                            // non con la modalita' corrente della pagina
                                            mode={t.mode}
                                            win={exp.win}
                                            lose={exp.lose}
                                            bestBack={book?.back ?? null}
                                            bestLay={book?.lay ?? null}
                                            commission={commission}
                                            pending={isCashOutPending?.(t.id) ?? false}
                                            disabled={stale != null || blocked != null}
                                            disabledReason={stale ?? blocked ?? undefined}
                                            residual={hedge && !hedge.complete && !hedge.inFlight
                                                ? { remaining: hedge.remainingLiability ?? hedge.residualSize, fraction: hedge.fraction }
                                                : null}
                                            onCashOut={(a) => onCashOut(t, a)}
                                        />
                                    ) : t.status === 'pending' && onCancel ? (
                                        <Button
                                            type="button"
                                            variant="outline"
                                            size="sm"
                                            className="h-7 px-2 text-[11px] border-white/15"
                                            data-testid="safe-cancel"
                                            title="annulla la riserva non ancora abbinata (il servizio rifiuta se l'ordine è già a mercato o in riconciliazione)"
                                            disabled={isReconciling(t)}
                                            onClick={() => { void onCancel(t); }}
                                        >
                                            Annulla
                                        </Button>
                                    ) : hedged ? (
                                        <span className="text-[11px] text-teal-300" title="posizione chiusa a mercato: P&L bloccato">coperto</span>
                                    ) : <span className="text-slate-600">{DASH}</span>}
                                </td>
                            </tr>
                            {closes.map((c, ci) => {
                                const cb = statusMeta(c.status);
                                // "parziale": dalla chiusura (size_capped_from) o dall'apertura (residuo > 0)
                                const capped = cappedFrom(c) ?? (partial && ci === closes.length - 1 ? partial.hedged + partial.residual : null);
                                return (
                                    <tr key={c.id} className="bg-white/[0.03] border-t border-dashed border-white/5" data-testid="safe-closing-row" data-closes={t.id}>
                                        <td className="px-3 py-1 text-slate-500 tabular-nums text-[11px]">{fmtTime(c.placed_at)}</td>
                                        <td colSpan={12} className="pl-8 pr-3 py-1 text-[11px] text-slate-300" title={hedgeTooltip(t, c)}>
                                            <span className="text-teal-300" aria-hidden>↳ </span>
                                            <b className="text-teal-200">{isGreenup ? T.greenUp : (exit?.kind === 'manual' || isManualCashout) ? T.cashOut : 'Chiusura'} di #{t.id}</b>
                                            {' · '}
                                            <Badge variant="outline" className={`px-1 py-0 text-[10px] font-heading font-bold mr-1 ${sideBadgeClass(c.side === 'back' ? 'BACK' : 'LAY')}`}>{c.side.toUpperCase()}</Badge>{' '}
                                            <span className="tabular-nums">{fmtMoney(c.size)} @{fmtOdds(c.price)}</span>
                                            {c.selection_name && c.selection_name !== t.selection_name && <span className="text-slate-500"> · {c.selection_name}</span>}
                                            {c.commission != null && (
                                                <span className="text-slate-500" title="aliquota applicata a QUESTA chiusura (non il parametro corrente)">
                                                    {' '}· commissione {fmtPct(Number(c.commission) > 1 ? Number(c.commission) / 100 : Number(c.commission))}
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-3 py-1 text-center">
                                            <Badge variant="outline" className={`px-1.5 py-0 text-[10px] ${cb.cls}`}>{cb.label}</Badge>
                                            <ExitBadge meta={c.meta} className="ml-1" />
                                        </td>
                                        <td className="px-3 py-1 text-right text-[11px] text-slate-500 tabular-nums">
                                            {['won', 'lost', 'void', 'hedged'].includes(c.status) ? fmtMoney(Number(c.pnl), { signed: true }) : DASH}
                                        </td>
                                        <td className="px-3 py-1 text-center">
                                            <span className="text-[11px] text-slate-400" title="gamba di copertura del cash out">
                                                chiude #{t.id}
                                                {capped != null && (
                                                    <Badge
                                                        variant="outline"
                                                        data-testid="cashout-capped"
                                                        className={`ml-1 px-1 py-0 text-[10px] ${CLS.amber}`}
                                                        title={cappedFrom(c) != null
                                                            ? `liquidità insufficiente: richiesti ${fmtMoney(capped)}, abbinati ${fmtMoney(c.size)} — chiusura PARZIALE`
                                                            : `copertura PARZIALE: coperti ${fmtMoney(partial?.hedged)} di ${fmtMoney(partial?.size)} di stake, residuo ${fmtMoney(partial?.residual)} ancora vivo`}
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
