// ============================================================================
// SignalCard.tsx — card di UN segnale SAFE STRATEGY (attivo o scaduto).
//
// Priorità assoluta: leggibilità immediata anche con molti segnali insieme.
// Gerarchia visiva: AZIONE (PUNTA/BANCA chi) → quota → partita → contesto.
// Dal 10/09 la card porta anche l'AZIONE: stake precompilato dai parametri e
// piazzamento in coda (PAPER o LIVE). Se per quel segnale esiste gia' un trade
// si mostra il suo stato e, se aperto, il CASH OUT live al posto dell'azione.
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { BetfairMediaButtons, type BetfairMediaAvailability } from '@/components/BetfairMediaButtons';
import { fmtEur, type ActiveSignal } from '@/lib/safeStrategy';
import { CashOutButton } from '@/components/trading/CashOutButton';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { fmtMoney, fmtOdds, fmtTime } from '@/lib/format';
import { T } from '@/lib/tradeStatus';

import {
    hedgeState, lastRequestFor, marketBlocked, requestOutcome,
    tradeCommission, tradeExposureNow, tradeHold, holdReasonLabel,
    staleReason, FEED_ROW_STALE_MS,
    type FeedFreshness, type SafeMode, type SafeRequest, type SafeTrade, type SignalPlacement,
    type TradeBook,
} from '@/lib/safeBot';
import { safeRowStatus } from './SafeTradesTable';
import { InvestAction } from './InvestAction';
import { VARIANT_STYLE, sideBadgeClass } from './variantStyles';

/** Riga "importo abbinabile SUBITO": la size al miglior prezzo sul lato da
 *  operare, aggiornata live con la quota. Per il LAY l'importo è la puntata da
 *  bancare (denaro in attesa) e si mostra anche la responsabilità = importo ×
 *  (quota − 1); per il BACK è la puntata. Senza size (fonte legacy) → "n/d". */
function MatchableLine({ signal }: { signal: ActiveSignal }) {
    const eur = fmtEur(signal.entrySize);
    if (eur === null) {
        return <span className="text-muted-foreground">Abbinabile subito: n/d</span>;
    }
    const liability =
        signal.side === 'LAY' && signal.entryOdds != null && signal.entrySize != null
            ? fmtEur(Math.round(signal.entrySize * (signal.entryOdds - 1) * 100) / 100)
            : null;
    return (
        <span>
            <span className="text-muted-foreground">Abbinabile subito</span>{' '}
            <span className="font-mono tabular-nums font-bold text-emerald-300">{eur}</span>
            {signal.side === 'LAY' && (
                <span className="text-muted-foreground"> da bancare{liability ? ` · ${T.openLiability} ${liability}` : ''}</span>
            )}
            {signal.side === 'BACK' && <span className="text-muted-foreground"> da puntare</span>}
        </span>
    );
}


function fmtAgo(ms: number, nowMs: number): string {
    const s = Math.max(0, Math.round((nowMs - ms) / 1000));
    if (s < 60) return `${s}s fa`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m fa`;
    return `${Math.floor(m / 60)}h ${m % 60}m fa`;
}

interface Props {
    signal: ActiveSignal;
    /** timestamp corrente (dal chiamante, per re-render coerente della lista) */
    nowMs: number;
    /** disponibilità video/animazione Betfair per l'evento (dallo scanner) */
    media?: BetfairMediaAvailability | null;
    /** coordinate di mercato risolte dal feed (null = non piazzabile da qui) */
    placement?: SignalPlacement | null;
    mode?: SafeMode;
    stake?: number;
    requests?: SafeRequest[];
    /** trade gia' esistente per questo segnale (match su signal_key) */
    trade?: SafeTrade | null;
    tradeBook?: TradeBook | null;
    commissionPct?: number;
    /** cash out gia' in volo per il trade del segnale */
    cashOutPending?: boolean;
    /** freschezza della riga del feed dell'evento (quote stantie → azioni spente) */
    freshness?: FeedFreshness | null;
    /** size minima Betfair in uso dal servizio (params_effective.min_stake) */
    minStake?: number;
    onPlace?: (placement: SignalPlacement, size: number) => Promise<number | null>;
    onCashOut?: (trade: SafeTrade, args: { amount?: number; fraction?: number }) => Promise<void> | void;
}

export function SignalCard({
    signal, nowMs, media, placement, mode = 'paper', stake = 5, requests = [],
    trade = null, tradeBook = null, commissionPct, cashOutPending = false, freshness = null,
    minStake, onPlace, onCashOut,
}: Props) {
    const style = VARIANT_STYLE[signal.variant];
    const active = signal.status === 'active';
    const stale = staleReason(freshness);
    // stato/copertura/esito del trade: le stesse regole della tabella, in italiano
    const tradeStatus = trade ? safeRowStatus(trade) : null;
    const hedge = trade ? hedgeState(trade) : null;
    const hold = trade && ['open', 'pending'].includes(trade.status) ? tradeHold(trade) : null;
    const blocked = trade && ['open', 'pending'].includes(trade.status)
        ? marketBlocked(tradeBook)
        : null;
    const outcome = trade ? requestOutcome(lastRequestFor(trade.id, requests)) : null;
    const canCashOut = trade != null
        && (trade.status === 'open' || (trade.status === 'hedged' && hedge != null && !hedge.complete));
    const ageBadge = freshness?.ageSec != null && freshness.ageSec * 1000 > FEED_ROW_STALE_MS ? (
        <Badge
            variant="outline"
            data-testid="feed-age"
            className={`px-1 py-0 text-[10px] ${stale ? 'bg-red-500/15 text-red-300 border-red-500/40' : 'bg-white/5 text-slate-400 border-white/10'}`}
            title={stale ?? 'riga del feed non riscritta di recente (nessuna variazione)'}
        >
            feed {freshness.ageSec}s
        </Badge>
    ) : null;
    return (
        <div
            className={[
                'glass-card rounded-xl border border-white/10 border-l-4 p-4 transition-all',
                style.edge,
                active ? 'pulse-glow' : 'opacity-50',
            ].join(' ')}
        >
            <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className={`font-heading font-bold text-[10px] ${style.badge}`}>
                    {style.chipLabel(signal.subId)}
                </Badge>
                <Badge variant="outline" className={`font-heading font-bold text-[10px] ${sideBadgeClass(signal.side)}`}>
                    {signal.side ?? '—'}
                </Badge>
                <span className="ml-auto text-[11px] text-muted-foreground font-mono tabular-nums">
                    {fmtTime(signal.triggeredAtMs)} · {fmtAgo(signal.triggeredAtMs, nowMs)}
                </span>
            </div>

            <div className="mt-2 flex items-baseline gap-3 flex-wrap">
                <span className="font-display font-black text-lg md:text-xl tracking-tight text-white">
                    {signal.headline}
                </span>
                <span className="font-mono tabular-nums text-2xl font-bold text-primary">
                    {signal.entryOdds != null ? `@${fmtOdds(signal.entryOdds)}` : '@ n/d'}
                </span>
            </div>

            <div className="mt-1 text-sm">
                <MatchableLine signal={signal} />
            </div>

            <div className="mt-1 text-sm text-muted-foreground">
                {signal.matchLabel}
                <span className="mx-2 text-white/20">·</span>
                <span className="font-mono tabular-nums">{signal.contextAtTrigger}</span>
                {!active && (
                    <span className="ml-2 text-[11px] uppercase tracking-wide text-amber-300/80">
                        condizioni non più valide
                    </span>
                )}
            </div>

            <div className="mt-3">
                <BetfairMediaButtons eventId={signal.eventId} media={media} />
            </div>

            {trade ? (
                <div className="mt-3 flex items-center gap-2 flex-wrap" data-testid="signal-trade">
                    {/* stato in ITALIANO, lo stesso della tabella (audit L-07) */}
                    <Badge
                        variant="outline"
                        data-testid="signal-trade-status"
                        className={`text-[10px] font-heading font-bold ${tradeStatus?.cls ?? ''}`}
                        title={tradeStatus?.title}
                    >
                        {tradeStatus?.label}
                    </Badge>
                    <ExitBadge meta={trade.meta} />
                    <span className="text-[11px] text-muted-foreground tabular-nums">
                        {trade.side.toUpperCase()} {fmtMoney(trade.size)} @{fmtOdds(trade.price)}
                    </span>
                    {hold && (
                        <span className="text-[10px] text-sky-300/90" data-testid="signal-hold" title="il servizio tiene la posizione aperta">
                            In attesa: {holdReasonLabel(hold.reason)}
                        </span>
                    )}
                    {canCashOut && onCashOut && (
                        <CashOutButton
                            compact
                            // modalita' del TRADE (il servizio chiude con quella), non della pagina
                            mode={trade.mode}
                            {...tradeExposureNow(trade)}
                            bestBack={tradeBook?.back ?? null}
                            bestLay={tradeBook?.lay ?? null}
                            commission={tradeCommission(trade, commissionPct ?? 5)}
                            pending={cashOutPending}
                            disabled={stale != null || blocked != null}
                            disabledReason={stale ?? blocked ?? undefined}
                            residual={hedge && !hedge.complete
                                ? { remaining: hedge.remainingLiability ?? hedge.residualSize, fraction: hedge.fraction }
                                : null}
                            onCashOut={(a) => onCashOut(trade, a)}
                        />
                    )}
                    {blocked && (
                        <span className="text-[10px] text-amber-300" data-testid="signal-market-blocked">{blocked}</span>
                    )}
                    {outcome && (
                        <span
                            className={`text-[10px] ${outcome.tone === 'ok' ? 'text-emerald-300' : outcome.tone === 'pending' ? 'text-amber-300' : 'text-red-300'}`}
                            data-testid="signal-request-outcome"
                            data-tone={outcome.tone}
                            title={outcome.message ?? undefined}
                        >
                            {outcome.label}{outcome.message ? `: ${outcome.message}` : ''}
                        </span>
                    )}
                    {ageBadge}
                </div>
            ) : onPlace && active ? (
                placement ? (
                    <>
                        <InvestAction
                            mode={mode}
                            side={signal.side === 'LAY' ? 'lay' : 'back'}
                            price={placement.price ?? signal.entryOdds}
                            sizeAvailable={placement.size_available ?? signal.entrySize}
                            defaultStake={stake}
                            minStake={minStake}
                            requests={requests}
                            disabled={stale != null}
                            disabledReason={stale}
                            onPlace={(size) => onPlace(placement, size)}
                        />
                        {/* l'ingresso deve corrispondere a Betfair: mercato, selezione e
                            best price con la size abbinabile (audit L-07) */}
                        <p className="mt-1 text-[10px] text-slate-500 tabular-nums" data-testid="signal-placement">
                            mercato <b className="text-slate-400">{placement.market_type}</b> {placement.market_id}
                            {' · '}selezione {placement.selection_id}
                            {placement.price != null && <> · best {signal.side === 'LAY' ? 'lay' : 'back'} {fmtOdds(placement.price)}</>}
                            {placement.size_available != null && <> ({fmtMoney(placement.size_available)} abbinabili)</>}
                        </p>
                        {ageBadge && <div className="mt-1">{ageBadge}</div>}
                    </>
                ) : (
                    <p className="mt-3 text-[11px] text-amber-300/80" data-testid="signal-no-placement">
                        Mercato non risolvibile dal feed (id selezione mancante): piazza dal terminale live.
                    </p>
                )
            ) : null}
        </div>
    );
}
