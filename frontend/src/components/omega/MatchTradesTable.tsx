// ============================================================================
// MatchTradesTable.tsx — TABELLA DELLE PARTITE di Omega (§14, 11/09/2026).
//
// UNA RIGA = UNA PARTITA. Per ogni partita: la gamba del PRIMO TEMPO (lay sul
// Half Time Score) e la gamba del SECONDO TEMPO (lay sul Correct Score) con
// tutto quello che un trader deve vedere PRIMA di decidere:
//   selezione bancata · quota d'ingresso · quota LIVE adesso (+ età del feed,
//   "FEED FERMO" se il dato è vecchio) · minuto e punteggio live ·
//   P(perdita) del modello CONTRO quella del mercato · liability viva ·
//   P&L se chiudo ORA (netto della commissione FISSATA sul trade) ·
//   stato leggibile in italiano (IN CORSO / IN VERIFICA SU BETFAIR / APERTO /
//   COPERTA 40 % / CHIUSO IN GREEN-UP / CASH OUT MANUALE / VINTO / PERSO /
//   VOID / ERRORE definitivo) · badge del green-up con il suo stato reale
//   (in attesa / TENGO / fallito, ritento alle HH:MM / CIECO / residuo
//   abbandonato / fatto) · le operazioni di CHIUSURA attaccate alla gamba che
//   chiudono · il RISULTATO REALE di fine 1T e di fine 2T · il P&L della
//   partita in verde/rosso.
//
// Usata dal tab Automatico (live: punteggio dal feed + cash out) e dallo
// Storico (giorno passato: link "live" per le posizioni ancora vive).
// Nessun dato inventato: ogni valore viene dalle righe omega_trades o dal feed.
// ============================================================================
import type { ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    CashOutButton, greenPrice, fullGreenStake, partialLockedPnl, netAfterCommission,
} from '@/components/trading/CashOutButton';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { sideBadgeClass } from '@/components/safestrategy/variantStyles';
import { cappedFrom, tradeExposure, hedgeTooltip } from '@/lib/safeBot';
import { tradeExit } from '@/lib/dailyHistory';
import { fmtMoney, fmtOdds, fmtPct, fmtTime, fmtAge, ageSeconds } from '@/lib/format';
import {
    tradeModelOf, greenupBadge, greenupInfo, hedgeInfo, commissionPctOf, hasOwnCommission,
    positionInfo, terminalError, type HedgeInfo,
} from '@/lib/omega';
import { statusMeta, T } from '@/lib/tradeStatus';
import { liveScoreLabel } from '@/lib/useScanLiveFeed';
import { csSelection, htSelection, type CalcioScanPayload } from '@/lib/safeStrategyScan';
import {
    groupTradesByMatch, romeDayOf, type MatchGroup, type MatchLeg, type MatchTradeLike, type LegKind,
} from '@/lib/omegaMatches';

/** oltre questa età il dato del feed NON si usa per decidere: si dice e basta */
export const FEED_STALE_S = 20;

// ------------------------------------------------------------------ helpers
function fmtSigned(v: number | null | undefined): string {
    return fmtMoney(v ?? 0, { signed: true });
}
/** ora dell'orologio di ROMA (L-02: mai il fuso del browser) */
function timeLabel(iso: string | null | undefined): string {
    return fmtTime(iso);
}
function pctIt(v: number | null, digits = 1): string {
    return fmtPct(v, digits);
}
function pnlClass(v: number | null | undefined, muted = 'text-slate-400'): string {
    if (v == null) return muted;
    return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300';
}

export interface StatusInput {
    status: string;
    /** H-02: ordine reale a esito ignoto */
    reconciling?: boolean;
    /** M-05: riga terminale (nessun ordine reale esiste) */
    terminal?: boolean;
    /** meta.exit_kind della gamba o delle sue chiusure */
    exitKind?: string | null;
    /** meta.exit_profit: chiusura in utile (affidabile anche sul parziale) */
    exitProfit?: boolean | null;
    /** copertura letta da meta.hedge */
    hedge?: HedgeInfo | null;
}

/**
 * `exit_kind` che descrivono una vera USCITA A MERCATO senza dire nulla sul
 * segno: vocabolario chiuso del servizio (safe_strategy/exits.EXIT_KINDS) meno
 * quelli che hanno già un badge proprio (greenup/manual/profit/loss).
 */
const MARKET_EXIT_KINDS = new Set(['time', 'forced', 'red_card', 'other']);

/**
 * Stato LEGGIBILE di una gamba. Un solo posto per decidere la parola: prima
 * un pending in riconciliazione era un normalissimo "IN CORSO" e una
 * copertura parziale un "APERTO" (il trader non sapeva quanto era scoperto).
 */
export function legStatusBadge(a: StatusInput): { label: string; cls: string } {
    // stato BASE dalla mappa CONDIVISA (lib/tradeStatus): una sola parola e un
    // solo colore per stato in tutte e tre le sezioni, nessuna mappa duplicata.
    // La precedenza esito certo > terminale > riconciliazione la decide lì.
    const base = statusMeta(a.status, { reconciling: a.reconciling, terminal: a.terminal });
    if (a.status !== 'hedged' && a.status !== 'pending' && a.status !== 'open') return base;
    if (a.reconciling || a.terminal) return base;
    if (a.status === 'hedged') {
        // Contratto 11/09 (seconda passata): 'greenup' lo scrive il servizio
        // SOLO per una chiusura INTEGRALE con bloccato ≥ 0. Una chiusura in
        // perdita è 'loss' e va detta in rosso: "CHIUSO IN GREEN-UP" su una
        // posizione chiusa a −22 € era una bugia verde.
        if (a.exitKind === 'greenup') {
            return { label: 'CHIUSO IN GREEN-UP', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50' };
        }
        if (a.exitKind === 'manual') {
            return { label: 'CASH OUT MANUALE', cls: 'bg-violet-500/15 text-violet-300 border-violet-500/40' };
        }
        if (a.exitKind === 'loss' || a.exitProfit === false) {
            return { label: 'CHIUSO IN PERDITA', cls: 'bg-red-500/15 text-red-300 border-red-500/40' };
        }
        if (a.exitKind === 'profit' || a.exitProfit === true) {
            return { label: 'CHIUSO IN UTILE', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' };
        }
        // glossario §3: "CHIUSO A MERCATO" SOLO quando il servizio ha davvero
        // dichiarato un'uscita a mercato; senza `exit_kind` lo stato è "CHIUSO"
        // (come in Safe: prima Omega inventava un'uscita che nessuno aveva detto)
        if (a.exitKind && MARKET_EXIT_KINDS.has(a.exitKind)) {
            return { label: T.closedAtMarket, cls: base.cls };
        }
        return base;
    }
    // pending / open: la copertura PARZIALE vince sullo stato nudo
    const h = a.hedge;
    const partial = h && !h.complete && h.hedgedSize != null && h.hedgedSize > 0
        && h.fraction != null && h.fraction < 0.999;
    if (partial) {
        const pct = fmtPct(h.fraction, 0);
        const rest = h.remainingLiability != null ? ` (restano ${fmtMoney(h.remainingLiability)})` : '';
        return { label: `COPERTA ${pct}${rest}`, cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' };
    }
    return base;
}

/** compatibilità storica (test e Storico): stato + exit_kind */
export function statusBadge(status: string, exitKind?: string | null): { label: string; cls: string } {
    return legStatusBadge({ status, exitKind });
}

const LEG_TITLE: Record<LegKind, string> = { ht: '1° TEMPO', ft: '2° TEMPO', other: 'ALTRO' };
const LEG_MARKET: Record<LegKind, string> = { ht: 'Half Time Score', ft: 'Correct Score', other: '' };

/** book LIVE della selezione della gamba (1T → Half Time Score, altrimenti CS) */
function bookFor(t: MatchTradeLike, kind: LegKind, live: CalcioScanPayload | undefined) {
    const sid = (t as { selection_id?: number | null }).selection_id;
    if (sid == null) return null;
    return kind === 'ht' ? htSelection(live ?? null, sid) : csSelection(live ?? null, sid);
}

/**
 * P&L se chiudo ORA al book disponibile, NETTO della commissione fissata sul
 * trade. null = nessun prezzo di chiusura (mercato senza controparte).
 */
export function closeNowPnl(
    exp: { win: number; lose: number },
    book: { back: number | null; lay: number | null } | null,
    commissionPct: number,
): { gross: number; net: number; price: number } | null {
    const price = greenPrice(exp.win, exp.lose, book?.back ?? null, book?.lay ?? null);
    if (price == null) return null;
    if (fullGreenStake(exp.win, exp.lose, price) <= 0) return null;
    const gross = partialLockedPnl(price, exp.win, exp.lose, 1);
    return { gross, net: netAfterCommission(gross, commissionPct), price };
}

// ------------------------------------------------------------- props
export interface MatchTradesTableProps<T extends MatchTradeLike> {
    /** righe omega_trades (aperture + chiusure, appiattite) */
    trades: T[];
    /** punteggio/book live dal feed dello scanner (vista live) */
    liveFeed?: Record<string, CalcioScanPayload>;
    /** ISO dell'ultimo aggiornamento della riga di feed, per evento */
    feedUpdatedAt?: Record<string, string | null>;
    /** orologio della pagina (età del feed); assente = adesso */
    nowMs?: number;
    /** aliquota corrente (5 = 5 %): RIPIEGO quando il trade non ne ha una sua */
    commission?: number;
    /** cash out di una gamba aperta (vista live); assente = nessun bottone */
    onCashOut?: (trade: T, args: { amount?: number; fraction?: number }) => Promise<void> | void;
    isCashOutPending?: (trade: T) => boolean;
    /** storico: posizione ancora viva → "vai al live" */
    onGoLive?: (trade: T) => void;
    /**
     * true = vista LIVE: si mostrano quota attuale, freschezza del feed e
     * "se chiudo ora". Nello Storico non ha senso (nessun feed) e direbbe
     * soltanto "FEED ASSENTE". Default: c'è un cash out → è la vista live.
     */
    liveView?: boolean;
    emptyText?: string;
    /** giornata mostrata (per marcare le partite di giorni precedenti ancora vive) */
    day?: string;
}

// ---------------------------------------------------------- freschezza feed
function FeedAge({ updatedAt, nowMs }: { updatedAt: string | null | undefined; nowMs: number }) {
    const age = ageSeconds(updatedAt ?? null, nowMs);
    if (age == null) {
        return (
            <span className="text-[10px] text-amber-300" data-testid="omega-feed-age" data-stale="1"
                title="nessuna riga di feed per questa partita: minuto, punteggio e quote non sono aggiornati">
                FEED ASSENTE
            </span>
        );
    }
    const stale = age > FEED_STALE_S;
    return (
        <span
            className={`text-[10px] ${stale ? 'text-red-300 font-semibold' : 'text-slate-500'}`}
            data-testid="omega-feed-age"
            data-stale={stale ? '1' : undefined}
            title={stale
                ? `il feed di questa partita non si aggiorna da ${fmtAge(age)}: non decidere su questi numeri`
                : `dato del feed di ${fmtAge(age)} (lo scanner scrive a ogni cambio, ~2-3 s)`}
        >
            {stale ? `FEED FERMO da ${fmtAge(age)}` : `feed ${fmtAge(age)}`}
        </span>
    );
}

// --------------------------------------------------------------- cella gamba
function LegCell<T extends MatchTradeLike>({
    leg, kind, group, live, feedAt, nowMs, commission, liveView, onCashOut, isCashOutPending, onGoLive,
}: {
    leg: MatchLeg<T> | null; kind: LegKind; group: MatchGroup<T>;
    live: CalcioScanPayload | undefined; feedAt: string | null | undefined; nowMs: number;
    commission: number; liveView: boolean;
    onCashOut?: MatchTradesTableProps<T>['onCashOut'];
    isCashOutPending?: MatchTradesTableProps<T>['isCashOutPending'];
    onGoLive?: MatchTradesTableProps<T>['onGoLive'];
}) {
    if (!leg) {
        return (
            <td className="px-3 py-2 align-top" data-testid={`omega-leg-${kind}`} data-empty="1">
                <div className="text-[11px] text-slate-600 italic" title={`nessuna operazione nel ${LEG_TITLE[kind].toLowerCase()} (${LEG_MARKET[kind]})`}>
                    {group.live ? 'in attesa della finestra' : 'non piazzata'}
                </div>
            </td>
        );
    }
    const t = leg.trade;
    const meta = (t.meta ?? {}) as Record<string, unknown>;
    const exit = tradeExit({ meta: t.meta ?? null, closes: leg.closes.map((c) => ({ meta: c.meta ?? null })) as never });
    const hedge = hedgeInfo(t.meta);
    const exitProfit = typeof meta.exit_profit === 'boolean' ? meta.exit_profit : null;
    const b = legStatusBadge({
        status: t.status, reconciling: leg.reconciling, terminal: leg.terminal,
        exitKind: exit?.kind, exitProfit, hedge,
    });
    const gBadge = greenupBadge(t.meta);
    const gInfo = greenupInfo(t.meta);
    const term = terminalError(t.meta);
    const pos = positionInfo(t.meta);
    // L-02: la commissione è quella FISSATA sulla riga; il parametro del form
    // è solo il ripiego per i trade vecchi che non l'hanno
    const commPct = commissionPctOf(t.meta, commission);
    const model = tradeModelOf({ meta: t.meta ?? null });
    // §15: fonte dei λ e costo di copertura immediata (audit del modello)
    const mm = meta['model'] as Record<string, unknown> | undefined;
    const lambdaSrc = typeof mm?.lambda_source === 'string' ? String(mm.lambda_source) : null;
    const coverCost = typeof mm?.cover_cost === 'number' ? Number(mm.cover_cost) : null;
    const empSrc = typeof mm?.empirical_source === 'string' ? String(mm.empirical_source) : null;
    const exp = tradeExposure({ side: t.side, price: t.price ?? null, size: t.size ?? null });
    const book = bookFor(t, kind, live);
    const side = t.side === 'back' ? 'BACK' : 'LAY';
    const risk = hedge?.remainingLiability != null && !hedge.complete
        ? hedge.remainingLiability
        : side === 'LAY' ? Number(t.liability ?? 0) : Number(t.size ?? 0);
    const pnl = leg.pnl;
    // P(perdita) IMPLICITA del mercato = 1/quota lay del risultato bancato
    const marketLay = book?.lay ?? null;
    const pMarket = marketLay != null && marketLay > 1 ? 1 / marketLay : null;
    const pModel = model ? (model.applied ? model.calibrated : (model.calibrated ?? model.raw)) : null;
    const modelTitle = [
        model?.applied ? `P(modello) calibrata ${pctIt(model.calibrated)} · grezza ${pctIt(model.raw)}` : 'P(modello) che il risultato bancato esca',
        pMarket != null ? `mercato: ${pctIt(pMarket)} (1/${fmtOdds(marketLay)})` : null,
        lambdaSrc ? `λ da ${lambdaSrc === 'market_grid' ? 'mercato intero (CS + O/U)' : lambdaSrc === 'live_ou' ? 'Over/Under live' : lambdaSrc === 'pre_ko_odds' ? 'quote pre-partita' : lambdaSrc}` : null,
        empSrc ? `dati storici: ${empSrc === 'minute' ? 'tabella per minuto' : '45′→finale'}` : null,
        coverCost != null ? `copertura immediata ≈ ${fmtMoney(coverCost)}` : null,
    ].filter(Boolean).join(' · ');
    // copertura PARZIALE: il residuo è chiudibile a parte (M-06)
    const residual = hedge && !hedge.complete && hedge.residualSize != null && hedge.residualSize > 0.01
        ? hedge.residualSize : null;
    const residualExp = residual != null
        ? tradeExposure({ side: t.side, price: t.price ?? null, size: residual })
        : null;
    // esposizione su cui si calcola il cash out: il RESIDUO se la posizione è
    // già coperta in parte, altrimenti tutta la posizione
    const cashExp = residualExp ?? exp;
    const closeNow = leg.live ? closeNowPnl(cashExp, book, commPct) : null;
    const feedAge = ageSeconds(feedAt ?? null, nowMs);
    const feedStale = feedAge == null || feedAge > FEED_STALE_S;
    const hasClose = leg.closes.some((c) => c.status !== 'error');
    const canCashOut = Boolean(onCashOut) && (t.status === 'open' || t.status === 'pending')
        && !leg.reconciling && !leg.terminal && t.side === 'lay'
        && (t as { selection_id?: number | null }).selection_id != null
        && (residual != null || !hasClose);
    return (
        <td className="px-3 py-2 align-top min-w-[260px]" data-testid={`omega-leg-${kind}`} data-trade={t.id}>
            <div className="space-y-1">
                {/* riga 1: lato + selezione bancata + quota + stake/rischio */}
                <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" data-testid="omega-side" className={`px-1.5 py-0 text-[10px] font-heading font-bold ${sideBadgeClass(side)}`}>{side}</Badge>
                    <span className="font-bold text-white text-[15px] tabular-nums" title={`${side === 'LAY' ? 'risultato bancato' : 'selezione'} sul ${LEG_MARKET[kind] || 'mercato'}`}>{t.runner_name ?? '—'}</span>
                    <span className="text-slate-300 tabular-nums" title="quota d'ingresso">@{fmtOdds(t.price)}</span>
                    {t.origin === 'manual' && <Badge variant="outline" className="px-1 py-0 text-[10px] bg-violet-500/15 text-violet-300 border-violet-500/40" title="operazione decisa a mano">✋</Badge>}
                    {t.mode === 'live' && <Badge variant="outline" className="px-1 py-0 text-[10px] bg-red-500/15 text-red-300 border-red-500/40" title="soldi veri">LIVE</Badge>}
                </div>
                <div className="text-[11px] text-slate-400 tabular-nums flex flex-wrap gap-x-2">
                    <span>stake <b className="text-slate-200">{fmtMoney(t.size)}</b></span>
                    <span title={side === 'LAY'
                        ? (hedge && !hedge.complete && hedge.remainingLiability != null
                            ? 'liability ANCORA VIVA dopo la copertura parziale'
                            : 'liability: quanto perdi se il risultato bancato esce')
                        : 'importo puntato'}>
                        rischio <b className="text-orange-300">{fmtMoney(risk)}</b>
                    </span>
                    {(t.minute_at_entry != null || t.score_at_entry) && (
                        <span title="minuto e punteggio al momento dell'ingresso">ingresso <b className="text-slate-200">{t.minute_at_entry != null ? `${t.minute_at_entry}′` : ''}{t.score_at_entry ? ` ${t.score_at_entry}` : ''}</b></span>
                    )}
                    {(pModel != null || pMarket != null) && (
                        <span data-testid="omega-model-p" title={modelTitle}>
                            P(perdita) <b className="text-slate-200">{pctIt(pModel)}</b>
                            <span className="text-slate-500"> · mercato </span>
                            <b className="text-slate-300">{pctIt(pMarket)}</b>
                        </span>
                    )}
                </div>
                {/* riga 2 (solo posizioni vive): quota LIVE, freschezza, chiusura ora */}
                {leg.live && liveView && (
                    <div className="text-[11px] tabular-nums flex flex-wrap gap-x-2 items-center" data-testid="omega-leg-live">
                        <span className="text-slate-400">
                            ora <b className={feedStale ? 'text-slate-500' : 'text-sky-300'} title="miglior quota LAY disponibile adesso sulla selezione bancata">
                                LAY {fmtOdds(book?.lay ?? null)}
                            </b>
                            <span className="text-slate-500"> / </span>
                            <b className={feedStale ? 'text-slate-500' : 'text-teal-300'} title="miglior quota BACK: è quella che serve per chiudere un lay">
                                BACK {fmtOdds(book?.back ?? null)}
                            </b>
                        </span>
                        <FeedAge updatedAt={feedAt} nowMs={nowMs} />
                        {closeNow ? (
                            <span data-testid="omega-close-now" title={`chiudendo adesso a ${fmtOdds(closeNow.price)}: ${fmtSigned(closeNow.gross)} lordi, commissione ${fmtPct(commPct / 100, 1)}${hasOwnCommission(t.meta) ? ' fissata sul trade' : ' dal parametro corrente'}`}>
                                <span className="text-slate-400">se chiudo ora </span>
                                <b className={pnlClass(closeNow.net)}>{fmtSigned(closeNow.net)}</b>
                                <span className="text-slate-500"> netti</span>
                            </span>
                        ) : (
                            <span className="text-slate-500" data-testid="omega-close-now" data-empty="1" title="nessun prezzo di chiusura disponibile: il mercato non offre controparte">
                                chiusura non disponibile
                            </span>
                        )}
                    </div>
                )}
                {/* riga 3: stato + P&L della gamba + green-up + uscita */}
                <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" data-testid="omega-status" className={`whitespace-nowrap px-1.5 py-0 text-[10px] ${b.cls}`} title={leg.closes.length ? hedgeTooltip({ side: t.side, price: t.price ?? null }, leg.closes[0] ? { side: leg.closes[0].side, price: leg.closes[0].price ?? null } : null) : undefined}>
                        {b.label}
                    </Badge>
                    {pnl.state === 'settled' && (
                        <b className={`tabular-nums ${pnlClass(pnl.value)}`} data-testid="omega-leg-pnl">{fmtSigned(pnl.value ?? 0)}</b>
                    )}
                    {pnl.state === 'locked' && (
                        <span className={`tabular-nums font-bold ${pnlClass(pnl.value)}`} data-testid="omega-locked-pnl" title="P&L bloccato dalla copertura: identico su ogni risultato, si incassa al fischio finale">
                            {fmtSigned(pnl.value ?? 0)} <span className="font-normal text-[10px] text-teal-300">bloccato</span>
                        </span>
                    )}
                    {pnl.state === 'partial' && (
                        <span className="text-[11px] text-amber-300 tabular-nums" data-testid="omega-leg-partial" title="copertura PARZIALE: la parte coperta è neutra, il resto vive; caso peggiore / migliore ai prezzi dei fill">
                            parziale {pnl.hedged_size != null ? `${fmtMoney(pnl.hedged_size, { currency: '' })}/${fmtMoney(t.size, { currency: '' })}` : ''} · <span className={pnlClass(pnl.value)}>{fmtSigned(pnl.value ?? 0)}</span>{pnl.best != null ? <> / <span className={pnlClass(pnl.best)}>{fmtSigned(pnl.best)}</span></> : null}
                        </span>
                    )}
                    {pnl.state === 'open' && !leg.reconciling && (
                        <span className="text-[11px] text-sky-300" data-testid="omega-leg-open" title="posizione viva: esito al fischio finale o alla chiusura a mercato">in corso</span>
                    )}
                    {/* H-04: lo stato REALE del green-up sulla riga */}
                    {gBadge && (
                        <Badge
                            variant="outline"
                            data-testid="omega-greenup-badge"
                            data-greenup-state={gBadge.state}
                            className={`whitespace-nowrap px-1.5 py-0 text-[10px] ${gBadge.cls}`}
                            title={gBadge.title}
                        >{gBadge.label}</Badge>
                    )}
                    {!(t.status === 'hedged' && exit?.kind === 'greenup') && <ExitBadge meta={t.meta ?? null} />}
                    {/* M-04: esito della POSIZIONE, non della singola gamba */}
                    {pos?.result && pos.pnl != null && (
                        <span className="text-[10px] text-slate-400" data-testid="omega-position-result"
                            title="esito della POSIZIONE (apertura + chiusure): una gamba d'apertura 'PERSA' può essere una posizione in utile">
                            posizione {pos.result === 'won' ? 'in utile' : pos.result === 'lost' ? 'in perdita' : 'in pari'}{' '}
                            <b className={pnlClass(pos.pnl)}>{fmtSigned(pos.pnl)}</b>
                        </span>
                    )}
                    {leg.live && onGoLive && (
                        <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[11px] text-sky-300" onClick={() => onGoLive(t)} data-testid="day-trade-live">
                            <ExternalLink className="w-3 h-3 mr-1" />live
                        </Button>
                    )}
                </div>
                {exit?.reason && (
                    <div className="text-[10px] text-slate-400" data-testid="omega-exit-reason" title="motivo della decisione automatica scritto dal servizio">{exit.reason}</div>
                )}
                {!exit?.reason && gInfo?.reason && (
                    <div className="text-[10px] text-slate-400" data-testid="omega-greenup-reason" title="motivo scritto dal servizio nello stato del green-up">{gInfo.reason}</div>
                )}
                {term && (
                    <div className="text-[10px] text-orange-300" data-testid="omega-terminal-error" title="riga TERMINALE: nessun ordine reale esiste (FOK ucciso, nessun fill, richiesta mai creata)">
                        {/* l'istante è meta.error_at: le righe 'error' non hanno settled_at */}
                        nessun ordine reale{term.reason ? ` · ${term.reason}` : ''}{term.at ? ` · ERRORE alle ${timeLabel(term.at)}` : ''}
                    </div>
                )}
                {/* chiusure: back sulla stessa selezione, evidenziate */}
                {leg.closes.map((c) => {
                    const cMeta = (c.meta ?? {}) as Record<string, unknown>;
                    const cExit = tradeExit({ meta: c.meta ?? null });
                    const cb = legStatusBadge({ status: c.status, exitKind: cExit?.kind });
                    const capped = cappedFrom({ meta: c.meta ?? null });
                    const settledC = ['won', 'lost', 'void'].includes(c.status);
                    // M-19: una chiusura richiesta a mano è un CASH OUT, non una
                    // generica "Chiusura" (il servizio la marca meta.cashout)
                    const isManual = cExit?.kind === 'manual' || cMeta.cashout === true;
                    const label = cExit?.kind === 'greenup' ? 'Green-up' : isManual ? 'Cash out' : 'Chiusura a mercato';
                    return (
                        <div key={c.id} className="rounded-md border-l-2 border-teal-400/70 bg-teal-500/10 px-2 py-1 text-[11px]" data-testid="omega-closing-line" data-closes={t.id} title={hedgeTooltip({ side: t.side, price: t.price ?? null }, { side: c.side, price: c.price ?? null })}>
                            <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-teal-300" aria-hidden>↳</span>
                                <b className="text-teal-200">{label}</b>
                                <Badge variant="outline" className={`px-1 py-0 text-[10px] font-heading font-bold ${sideBadgeClass(c.side === 'back' ? 'BACK' : 'LAY')}`}>{c.side.toUpperCase()}</Badge>
                                <span className="tabular-nums text-slate-200">{fmtMoney(c.size)} @{fmtOdds(c.price)}</span>
                                <span className="text-slate-500" title="ora di Roma">{timeLabel(c.placed_at)}</span>
                                <Badge variant="outline" className={`px-1 py-0 text-[10px] ${cb.cls}`}>{cb.label}</Badge>
                                {settledC && <b className={`tabular-nums ${pnlClass(Number(c.pnl))}`}>{fmtSigned(Number(c.pnl))}</b>}
                                {capped != null && (
                                    <Badge variant="outline" className="px-1 py-0 text-[10px] bg-amber-500/15 text-amber-300 border-amber-500/40" title={`liquidità insufficiente: chiusura PARZIALE (${fmtMoney(capped)} richiesti)`}>parziale</Badge>
                                )}
                            </div>
                        </div>
                    );
                })}
                {canCashOut && (
                    <div className="pt-0.5">
                        {residual != null && (
                            <div className="text-[10px] text-amber-300 mb-0.5" data-testid="omega-residual-note">
                                residuo scoperto {fmtMoney(residual)}: il cash out chiude SOLO quello
                            </div>
                        )}
                        <CashOutButton
                            compact
                            mode={(t.mode === 'live' ? 'live' : 'paper')}
                            win={cashExp.win}
                            lose={cashExp.lose}
                            bestBack={book?.back ?? null}
                            bestLay={book?.lay ?? null}
                            commission={commPct}
                            pending={isCashOutPending ? isCashOutPending(t) : false}
                            disabled={feedStale}
                            disabledReason={feedStale
                                ? 'quote non aggiornate (feed fermo): un cash out su prezzi vecchi si esegue a un prezzo che non hai visto'
                                : undefined}
                            onCashOut={(a) => onCashOut?.(t, a)}
                        />
                    </div>
                )}
            </div>
        </td>
    );
}

// ------------------------------------------------------------ cella risultato
function ResultCell({ score, leg, label }: { score: string | null; leg: MatchLeg<MatchTradeLike> | null; label: 'ht' | 'ft' }) {
    // solo una scoreline parsabile ("1 - 3"): per gli aggregati ("Any Other Home Win")
    // non si può dire se il bancato è uscito (review LOW-4) → nessuna riga
    const raw = leg?.trade.runner_name ?? null;
    const mm = raw ? /^\s*(\d+)\s*-\s*(\d+)\s*$/.exec(raw) : null;
    const laid = mm ? `${mm[1]}-${mm[2]}` : null;
    const hit = score != null && laid != null && score === laid;   // il risultato bancato È uscito
    return (
        <td className="px-3 py-2 align-top text-center" data-testid={`omega-result-${label}`}>
            {score ? (
                <div>
                    <div className={`font-display font-black text-lg tabular-nums ${hit ? 'text-red-400' : 'text-white'}`} title={label === 'ht' ? 'risultato reale al 45′' : 'risultato reale finale'}>{score}</div>
                    {leg && leg.trade.side === 'lay' && laid != null && (
                        <div className={`text-[10px] ${hit ? 'text-red-300' : 'text-emerald-300'}`}>{hit ? 'bancato USCITO' : 'bancato non uscito'}</div>
                    )}
                </div>
            ) : (
                <span className="text-slate-600" title={label === 'ht' ? 'in attesa del 45′' : 'in attesa del fischio finale'}>—</span>
            )}
        </td>
    );
}

// ----------------------------------------------------------------- tabella
export function MatchTradesTable<T extends MatchTradeLike>({
    trades, liveFeed = {}, feedUpdatedAt = {}, nowMs, commission = 5,
    onCashOut, isCashOutPending, onGoLive, liveView, emptyText, day,
}: MatchTradesTableProps<T>) {
    const groups = groupTradesByMatch(trades);
    const now = nowMs ?? Date.now();
    const isLive = liveView ?? Boolean(onCashOut);
    if (groups.length === 0) {
        return (
            <div className="text-center text-muted-foreground py-10 text-sm" data-testid="omega-matches-empty">
                {emptyText ?? 'nessuna partita ancora — avvia il bot e attendi la finestra dei match'}
            </div>
        );
    }
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="omega-matches-table">
                <thead className="text-[11px] uppercase text-slate-500 bg-black/30">
                    <tr>
                        <th className="text-left px-3 py-2" title="ora di Roma">Ora</th>
                        <th className="text-left px-3 py-2">Partita</th>
                        <th className="text-left px-3 py-2" title="lay sul Half Time Score: banca il risultato esatto al 45′">1° tempo</th>
                        <th className="text-center px-3 py-2" title="risultato REALE al 45′">Risultato 1T</th>
                        <th className="text-left px-3 py-2" title="lay sul Correct Score: banca il risultato esatto finale">2° tempo</th>
                        <th className="text-center px-3 py-2" title="risultato REALE finale">Risultato 2T</th>
                        <th className="text-right px-3 py-2" title="P&L complessivo della partita: entrambe le gambe con le loro chiusure">P&L partita</th>
                    </tr>
                </thead>
                <tbody>
                    {groups.map((g) => {
                        const live = liveFeed[g.event_id];
                        const feedAt = feedUpdatedAt[g.event_id] ?? null;
                        const liveLabel = g.live ? liveScoreLabel(live) : null;
                        const total = g.state === 'settled' ? g.pnl_settled
                            : g.state === 'partial' ? g.pnl_settled + (g.pnl_locked ?? 0)
                            : (g.pnl_locked ?? null);
                        const edge = g.state === 'settled'
                            ? (g.pnl_settled > 0 ? 'border-l-emerald-500/70' : g.pnl_settled < 0 ? 'border-l-red-500/70' : 'border-l-slate-500/50')
                            : 'border-l-sky-500/60';
                        const prevDay = day ? romeDayOf(g.placed_at) !== day : false;
                        return (
                            <tr key={g.event_id} className={`border-t border-white/5 border-l-4 ${edge} hover:bg-white/5`} data-testid="omega-match-row" data-event={g.event_id} data-state={g.state}>
                                <td className="px-3 py-2 align-top text-slate-400 tabular-nums whitespace-nowrap">
                                    <div title="ora di Roma del primo piazzamento">{timeLabel(g.placed_at)}</div>
                                    {g.kickoff && <div className="text-[10px] text-slate-600" title="calcio d'inizio (ora di Roma)">KO {timeLabel(g.kickoff)}</div>}
                                    {prevDay && <div className="text-[10px] text-amber-300/80" title="partita di una giornata precedente ancora viva">prec.</div>}
                                </td>
                                <td className="px-3 py-2 align-top max-w-[220px]">
                                    <div className="font-semibold text-white truncate" title={g.event_name ?? g.event_id}>{g.event_name ?? g.event_id}</div>
                                    <div className="text-[11px] tabular-nums">
                                        {liveLabel ? (
                                            <span className="text-emerald-300" data-testid="omega-live-score">
                                                <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1 align-middle" aria-hidden />
                                                {liveLabel}
                                            </span>
                                        ) : g.live ? (
                                            <span className="text-slate-500">in corso</span>
                                        ) : (
                                            <span className="text-slate-500">{g.n_legs} {g.n_legs === 1 ? 'operazione' : 'operazioni'} · regolata</span>
                                        )}
                                    </div>
                                    {g.live && isLive && <div><FeedAge updatedAt={feedAt} nowMs={now} /></div>}
                                </td>
                                <LegCell leg={g.ht} kind="ht" group={g} live={live} feedAt={feedAt} nowMs={now} commission={commission} liveView={isLive} onCashOut={onCashOut} isCashOutPending={isCashOutPending} onGoLive={onGoLive} />
                                <ResultCell score={g.result_ht} leg={g.ht} label="ht" />
                                <td className="px-0 py-0 align-top">
                                    <table className="w-full"><tbody><tr>
                                        <LegCell leg={g.ft} kind="ft" group={g} live={live} feedAt={feedAt} nowMs={now} commission={commission} liveView={isLive} onCashOut={onCashOut} isCashOutPending={isCashOutPending} onGoLive={onGoLive} />
                                    </tr>
                                    {g.others.map((o) => (
                                        <tr key={o.trade.id} className="border-t border-dashed border-white/10">
                                            <LegCell leg={o} kind="other" group={g} live={live} feedAt={feedAt} nowMs={now} commission={commission} liveView={isLive} onCashOut={onCashOut} isCashOutPending={isCashOutPending} onGoLive={onGoLive} />
                                        </tr>
                                    ))}
                                    </tbody></table>
                                </td>
                                <ResultCell score={g.result_ft} leg={g.ft} label="ft" />
                                <td className="px-3 py-2 align-top text-right whitespace-nowrap">
                                    {total != null ? (
                                        <div className={`font-display font-black text-xl tabular-nums ${pnlClass(total, 'text-slate-300')}`} data-testid="omega-match-pnl">{fmtSigned(total)}</div>
                                    ) : (
                                        <div className="font-display font-black text-xl text-slate-500" data-testid="omega-match-pnl">—</div>
                                    )}
                                    <div className="text-[10px] text-slate-500">
                                        {g.state === 'settled' ? 'regolato' : g.state === 'partial' ? `${g.n_decided}/${g.n_legs} decise` : g.pnl_locked != null ? 'bloccato' : 'in corso'}
                                        {g.open_liability > 0 && <span className="text-orange-300/80"> · rischio {fmtMoney(g.open_liability)}</span>}
                                        {g.reconciling_liability > 0 && (
                                            <span className="text-fuchsia-300/80" data-testid="omega-match-reconciling" title="ordine reale a esito ancora ignoto: conta nel rischio finché Betfair non risponde">
                                                {' '}· di cui {fmtMoney(g.reconciling_liability)} in verifica
                                            </span>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

export default MatchTradesTable;

/** intestazione riepilogo riusabile (n partite, gambe) */
export function matchesTitle(nMatches: number, nLegs: number): ReactNode {
    return <>{nMatches} {nMatches === 1 ? 'partita' : 'partite'} · {nLegs} {nLegs === 1 ? 'operazione' : 'operazioni'}</>;
}
