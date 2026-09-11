// ============================================================================
// MatchTradesTable.tsx — TABELLA DELLE PARTITE di Omega (§14, 11/09/2026).
//
// UNA RIGA = UNA PARTITA. Per ogni partita: la gamba del PRIMO TEMPO (lay sul
// Half Time Score) e la gamba del SECONDO TEMPO (lay sul Correct Score) con
// tutte le loro informazioni (selezione bancata, quota, stake, rischio, minuto
// e punteggio all'ingresso, P(modello), stato, P&L, motivo dell'uscita), le
// operazioni di CHIUSURA (back sulla stessa selezione: green-up / cash out)
// evidenziate sotto la gamba che chiudono, il RISULTATO REALE di fine 1T e di
// fine 2T, il P&L COMPLESSIVO della partita in verde/rosso.
//
// Usata dal tab Automatico (live: punteggio dal feed + cash out) e dallo
// Storico (giorno passato: link "live" per le posizioni ancora vive).
// Nessun dato inventato: ogni valore viene dalle righe omega_trades.
// ============================================================================
import type { ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CashOutButton } from '@/components/trading/CashOutButton';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { sideBadgeClass } from '@/components/safestrategy/variantStyles';
import { cappedFrom, tradeExposure, fmtEurIt, fmtOddsIt, hedgeTooltip } from '@/lib/safeBot';
import { tradeExit } from '@/lib/dailyHistory';
import { tradeModelOf } from '@/lib/omega';
import { liveScoreLabel } from '@/lib/useScanLiveFeed';
import { csSelection, htSelection, type CalcioScanPayload } from '@/lib/safeStrategyScan';
import {
    groupTradesByMatch, romeDayOf, type MatchGroup, type MatchLeg, type MatchTradeLike, type LegKind,
} from '@/lib/omegaMatches';

// ------------------------------------------------------------------ helpers
function fmtSigned(v: number): string {
    return fmtEurIt(v, true);
}
function timeLabel(iso: string | null | undefined): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '—'
        : d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' });
}
function pctIt(v: number | null, digits = 1): string {
    if (v == null || !Number.isFinite(v)) return '—';
    return `${(v * 100).toFixed(digits).replace('.', ',')}%`;
}
function pnlClass(v: number | null | undefined, muted = 'text-slate-400'): string {
    if (v == null) return muted;
    return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300';
}

export function statusBadge(status: string, exitKind?: string | null): { label: string; cls: string } {
    if (status === 'hedged' && exitKind === 'greenup') {
        return { label: 'CHIUSO IN GREEN-UP', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50' };
    }
    switch (status) {
        case 'pending': return { label: 'IN CORSO', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' };
        case 'open': return { label: 'APERTO', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' };
        case 'hedged': return { label: 'CHIUSO A MERCATO', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' };
        case 'won': return { label: 'VINTO', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' };
        case 'lost': return { label: 'PERSO', cls: 'bg-red-500/15 text-red-300 border-red-500/40' };
        case 'void': return { label: 'VOID', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40' };
        default: return { label: 'ERRORE', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/40' };
    }
}

const LEG_TITLE: Record<LegKind, string> = { ht: '1° TEMPO', ft: '2° TEMPO', other: 'ALTRO' };
const LEG_MARKET: Record<LegKind, string> = { ht: 'Half Time Score', ft: 'Correct Score', other: '' };

/** book LIVE della selezione della gamba (1T → Half Time Score, altrimenti CS) */
function bookFor(t: MatchTradeLike, kind: LegKind, live: CalcioScanPayload | undefined) {
    const sid = (t as { selection_id?: number | null }).selection_id;
    if (sid == null) return null;
    return kind === 'ht' ? htSelection(live ?? null, sid) : csSelection(live ?? null, sid);
}

// ------------------------------------------------------------- props
export interface MatchTradesTableProps<T extends MatchTradeLike> {
    /** righe omega_trades (aperture + chiusure, appiattite) */
    trades: T[];
    /** punteggio/book live dal feed dello scanner (vista live) */
    liveFeed?: Record<string, CalcioScanPayload>;
    /** aliquota (5 = 5%) per il calcolatore del cash out */
    commission?: number;
    /** cash out di una gamba aperta (vista live); assente = nessun bottone */
    onCashOut?: (trade: T, args: { amount?: number; fraction?: number }) => Promise<void> | void;
    isCashOutPending?: (trade: T) => boolean;
    /** storico: posizione ancora viva → "vai al live" */
    onGoLive?: (trade: T) => void;
    emptyText?: string;
    /** giornata mostrata (per marcare le partite di giorni precedenti ancora vive) */
    day?: string;
}

// --------------------------------------------------------------- cella gamba
function LegCell<T extends MatchTradeLike>({ leg, kind, group, live, commission, onCashOut, isCashOutPending, onGoLive }: {
    leg: MatchLeg<T> | null; kind: LegKind; group: MatchGroup<T>;
    live: CalcioScanPayload | undefined; commission: number;
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
    const exit = tradeExit({ meta: t.meta ?? null, closes: leg.closes.map((c) => ({ meta: c.meta ?? null })) as never });
    const b = statusBadge(t.status, exit?.kind);
    const model = tradeModelOf({ meta: t.meta ?? null });
    // §15: fonte dei λ e costo di copertura immediata (audit del modello)
    const mm = ((t.meta ?? {}) as Record<string, unknown>)['model'] as Record<string, unknown> | undefined;
    const lambdaSrc = typeof mm?.lambda_source === 'string' ? String(mm.lambda_source) : null;
    const coverCost = typeof mm?.cover_cost === 'number' ? Number(mm.cover_cost) : null;
    const empSrc = typeof mm?.empirical_source === 'string' ? String(mm.empirical_source) : null;
    const modelTitle = [
        model?.applied ? `P(modello) calibrata ${pctIt(model.calibrated)} · grezza ${pctIt(model.raw)}` : 'P(modello) che il risultato bancato esca',
        lambdaSrc ? `λ da ${lambdaSrc === 'market_grid' ? 'mercato intero (CS + O/U)' : lambdaSrc === 'live_ou' ? 'Over/Under live' : lambdaSrc === 'pre_ko_odds' ? 'quote pre-partita' : lambdaSrc}` : null,
        empSrc ? `dati storici: ${empSrc === 'minute' ? 'tabella per minuto' : '45′→finale'}` : null,
        coverCost != null ? `copertura immediata ≈ ${fmtEurIt(coverCost)}` : null,
    ].filter(Boolean).join(' · ');
    const exp = tradeExposure({ side: t.side, price: t.price ?? null, size: t.size ?? null });
    const book = bookFor(t, kind, live);
    const side = t.side === 'back' ? 'BACK' : 'LAY';
    const risk = side === 'LAY' ? Number(t.liability ?? 0) : Number(t.size ?? 0);
    const pnl = leg.pnl;
    const canCashOut = Boolean(onCashOut) && t.status === 'open' && t.side === 'lay'
        && (t as { selection_id?: number | null }).selection_id != null && leg.closes.length === 0;
    return (
        <td className="px-3 py-2 align-top min-w-[260px]" data-testid={`omega-leg-${kind}`} data-trade={t.id}>
            <div className="space-y-1">
                {/* riga 1: lato + selezione bancata + quota + stake/rischio */}
                <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" data-testid="omega-side" className={`px-1.5 py-0 text-[10px] font-heading font-bold ${sideBadgeClass(side)}`}>{side}</Badge>
                    <span className="font-bold text-white text-[15px] tabular-nums" title={`${side === 'LAY' ? 'risultato bancato' : 'selezione'} sul ${LEG_MARKET[kind] || 'mercato'}`}>{t.runner_name ?? '—'}</span>
                    <span className="text-slate-300 tabular-nums">@{fmtOddsIt(t.price)}</span>
                    {t.origin === 'manual' && <Badge variant="outline" className="px-1 py-0 text-[10px] bg-violet-500/15 text-violet-300 border-violet-500/40" title="operazione decisa a mano">✋</Badge>}
                    {t.mode === 'live' && <Badge variant="outline" className="px-1 py-0 text-[10px] bg-red-500/15 text-red-300 border-red-500/40" title="soldi veri">LIVE</Badge>}
                </div>
                <div className="text-[11px] text-slate-400 tabular-nums flex flex-wrap gap-x-2">
                    <span>stake <b className="text-slate-200">{fmtEurIt(t.size)}</b></span>
                    <span title={side === 'LAY' ? 'liability: quanto perdi se il risultato bancato esce' : 'importo puntato'}>rischio <b className="text-orange-300">{fmtEurIt(risk)}</b></span>
                    {(t.minute_at_entry != null || t.score_at_entry) && (
                        <span title="minuto e punteggio al momento dell'ingresso">ingresso <b className="text-slate-200">{t.minute_at_entry != null ? `${t.minute_at_entry}′` : ''}{t.score_at_entry ? ` ${t.score_at_entry}` : ''}</b></span>
                    )}
                    {model && (
                        <span data-testid="omega-model-p" title={modelTitle}>
                            P <b className="text-slate-200">{pctIt(model.applied ? model.calibrated : (model.calibrated ?? model.raw))}</b>
                        </span>
                    )}
                </div>
                {/* riga 3: stato + P&L della gamba + uscita */}
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
                            parziale {pnl.hedged_size != null ? `${pnl.hedged_size.toFixed(2)}/${Number(t.size ?? 0).toFixed(2)}` : ''} · <span className={pnlClass(pnl.value)}>{fmtSigned(pnl.value ?? 0)}</span>{pnl.best != null ? <> / <span className={pnlClass(pnl.best)}>{fmtSigned(pnl.best)}</span></> : null}
                        </span>
                    )}
                    {pnl.state === 'open' && (
                        <span className="text-[11px] text-sky-300" data-testid="omega-leg-open" title="posizione viva: esito al fischio finale o alla chiusura a mercato">in corso</span>
                    )}
                    {!(t.status === 'hedged' && exit?.kind === 'greenup') && <ExitBadge meta={t.meta ?? null} />}
                    {leg.live && onGoLive && (
                        <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[11px] text-sky-300" onClick={() => onGoLive(t)} data-testid="day-trade-live">
                            <ExternalLink className="w-3 h-3 mr-1" />live
                        </Button>
                    )}
                </div>
                {exit?.reason && (
                    <div className="text-[10px] text-slate-400" data-testid="omega-exit-reason" title="motivo della decisione automatica scritto dal servizio">{exit.reason}</div>
                )}
                {/* chiusure: back sulla stessa selezione, evidenziate */}
                {leg.closes.map((c) => {
                    const cb = statusBadge(c.status);
                    const capped = cappedFrom({ meta: c.meta ?? null });
                    const cExit = tradeExit({ meta: c.meta ?? null });
                    const settledC = ['won', 'lost', 'void'].includes(c.status);
                    return (
                        <div key={c.id} className="rounded-md border-l-2 border-teal-400/70 bg-teal-500/10 px-2 py-1 text-[11px]" data-testid="omega-closing-line" data-closes={t.id} title={hedgeTooltip({ side: t.side, price: t.price ?? null }, { side: c.side, price: c.price ?? null })}>
                            <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-teal-300" aria-hidden>↳</span>
                                <b className="text-teal-200">{cExit?.kind === 'greenup' ? 'Green-up' : cExit?.kind === 'manual' ? 'Cash out' : 'Chiusura'}</b>
                                <Badge variant="outline" className={`px-1 py-0 text-[10px] font-heading font-bold ${sideBadgeClass(c.side === 'back' ? 'BACK' : 'LAY')}`}>{c.side.toUpperCase()}</Badge>
                                <span className="tabular-nums text-slate-200">{fmtEurIt(c.size)} @{fmtOddsIt(c.price)}</span>
                                <span className="text-slate-500">{timeLabel(c.placed_at)}</span>
                                <Badge variant="outline" className={`px-1 py-0 text-[10px] ${cb.cls}`}>{cb.label}</Badge>
                                {settledC && <b className={`tabular-nums ${pnlClass(Number(c.pnl))}`}>{fmtSigned(Number(c.pnl))}</b>}
                                {capped != null && (
                                    <Badge variant="outline" className="px-1 py-0 text-[10px] bg-amber-500/15 text-amber-300 border-amber-500/40" title="liquidità insufficiente: chiusura PARZIALE rispetto allo stake richiesto">parziale</Badge>
                                )}
                            </div>
                        </div>
                    );
                })}
                {canCashOut && (
                    <div className="pt-0.5">
                        <CashOutButton
                            compact
                            mode={(t.mode === 'live' ? 'live' : 'paper')}
                            win={exp.win}
                            lose={exp.lose}
                            bestBack={book?.back ?? null}
                            bestLay={book?.lay ?? null}
                            commission={commission}
                            pending={isCashOutPending ? isCashOutPending(t) : false}
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
    trades, liveFeed = {}, commission = 5, onCashOut, isCashOutPending, onGoLive, emptyText, day,
}: MatchTradesTableProps<T>) {
    const groups = groupTradesByMatch(trades);
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
                        <th className="text-left px-3 py-2">Ora</th>
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
                                    <div>{timeLabel(g.placed_at)}</div>
                                    {g.kickoff && <div className="text-[10px] text-slate-600" title="calcio d'inizio">KO {timeLabel(g.kickoff)}</div>}
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
                                </td>
                                <LegCell leg={g.ht} kind="ht" group={g} live={live} commission={commission} onCashOut={onCashOut} isCashOutPending={isCashOutPending} onGoLive={onGoLive} />
                                <ResultCell score={g.result_ht} leg={g.ht} label="ht" />
                                <td className="px-0 py-0 align-top">
                                    <table className="w-full"><tbody><tr>
                                        <LegCell leg={g.ft} kind="ft" group={g} live={live} commission={commission} onCashOut={onCashOut} isCashOutPending={isCashOutPending} onGoLive={onGoLive} />
                                    </tr>
                                    {g.others.map((o) => (
                                        <tr key={o.trade.id} className="border-t border-dashed border-white/10">
                                            <LegCell leg={o} kind="other" group={g} live={live} commission={commission} onCashOut={onCashOut} isCashOutPending={isCashOutPending} onGoLive={onGoLive} />
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
                                        {g.open_liability > 0 && <span className="text-orange-300/80"> · rischio {fmtEurIt(g.open_liability)}</span>}
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
