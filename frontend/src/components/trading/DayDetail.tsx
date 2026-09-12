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
import {
    dayLabel, tradeExit, summarizeDayTrades, attributionOf, WIN_LOSS_TIP,
    type DayTrade, type DayTradeLeg, type HistoryVariant, type DayAttribution,
} from '@/lib/dailyHistory';
import { MatchTradesTable } from '@/components/omega/MatchTradesTable';
import { fmtMoney, fmtOdds, fmtTime, DASH } from '@/lib/format';
import { statusMeta, statusMetaOf, TIP } from '@/lib/tradeStatus';

/**
 * §1 — un dato ASSENTE è «—», non «0,00 €». Prima `fmtEur` faceva
 * `Number(v ?? 0)`: uno stake o una liability mai scritti dal servizio
 * comparivano come uno zero perfettamente credibile.
 */
function fmtEur(v: number | null | undefined): string {
    return fmtMoney(v);
}
function fmtSignedEur(v: number): string {
    return fmtMoney(v, { signed: true });
}
/** ora dell'orologio di ROMA (mai il fuso del browser) */
function timeLabel(iso: string | null): string {
    return fmtTime(iso);
}

/** §19: nessuna mappa duplicata — lo stato lo dice `lib/tradeStatus`. */
export function statusBadge(status: string): { label: string; cls: string } {
    return statusMeta(status);
}

/**
 * Certificazione 12/09 — lo STORICO deve dire la stessa parola del LIVE.
 * Qui si passava il solo `status`: una riserva a esito IGNOTO
 * (`meta.reason='place_exception_reconciling'` / `meta.reconciling`) che nel
 * tab Trade è «IN VERIFICA SU BETFAIR» nello storico diventava un innocuo
 * «IN CORSO», e una riga terminale in errore un «ERRORE» qualsiasi.
 */
function statusBadgeOf(leg: DayTradeLeg): { label: string; cls: string } {
    return statusMetaOf({ status: leg.status, meta: leg.meta });
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
/** P&L già incassato dalle gambe di chiusura REGOLATE di una posizione. */
function cashedOf(t: DayTrade): number {
    let s = 0;
    for (const c of t.closes ?? []) {
        if (['won', 'lost', 'void'].includes(c.status)) s += Number(c.pnl) || 0;
    }
    return Math.round(s * 100) / 100;
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
    /**
     * H-11/M-18: come il CALENDARIO attribuisce una posizione al giorno.
     * Per TUTTI E TRE i bot è il giorno di PIAZZAMENTO (Europe/Rome).
     * Assente = dedotta dalla variante (`attributionOf`).
     */
    attribution?: DayAttribution;
    /** posizione ancora viva → "vai al live" (tab trade della pagina) */
    onGoLive?: (trade: DayTrade) => void;
}

export function DayDetail({ day, trades, loading = false, error = null, variant, attribution, onGoLive }: DayDetailProps) {
    if (!day) {
        return (
            <div className="text-sm text-muted-foreground py-6 text-center" data-testid="day-detail-empty">
                seleziona una giornata dal calendario per vedere i trade
            </div>
        );
    }
    const list = trades ?? [];
    const attr = attribution ?? attributionOf(variant);
    // H-11/M-18: i totali sono quelli della CELLA del calendario — solo le
    // posizioni che il calendario attribuisce a questa giornata.
    const day0 = summarizeDayTrades(list, attr);
    const settled = day0.attributed.filter((t) => ['won', 'lost', 'void'].includes(t.status));
    const totalPnl = day0.pnl;
    const openCount = day0.open;
    const liability = day0.liability;
    const otherDays = day0.others.length;
    // le righe MAI arrivate a mercato restano visibili (un ordine fallito è
    // un'informazione), ma fuori dai conteggi: il calendario non le conta
    const rowsShown = [...day0.attributed, ...day0.notPlaced];
    const notPlaced = day0.notPlaced.length;
    /**
     * Certificazione 12/09 — finché i trade della giornata non sono arrivati
     * la testata NON deve dichiarare «0 trade · liability piazzata 0,00 € ·
     * realizzato +0,00 €»: sono tre affermazioni false su una pagina di
     * trading (il dump lo mostrava accanto a un dettaglio con 6 posizioni).
     */
    const noData = trades == null;

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid="day-detail" aria-busy={loading || undefined}>
            <div className="px-4 py-2.5 border-b border-white/5 flex items-center gap-3 flex-wrap text-sm text-slate-300">
                <Activity className="w-4 h-4 text-primary" />
                <span className="font-semibold capitalize">{dayLabel(day, { weekday: true })}</span>
                <span className="text-slate-500">·</span>
                <span className="tabular-nums" data-testid="day-count">
                    {noData ? 'caricamento…' : `${day0.attributed.length} trade`}
                </span>
                {!noData && openCount > 0 && <Badge variant="outline" className="bg-sky-500/15 text-sky-300 border-sky-500/40 text-[10px]">{openCount} ancora vivi</Badge>}
                {!noData && notPlaced > 0 && (
                    <span className="text-[11px] text-slate-500" data-testid="day-not-placed" title="ordini mai arrivati a mercato (errore o riserva senza esito): il calendario non li conta fra i trade piazzati né nella liability">
                        + {notPlaced} non piazzati (fuori dai totali)
                    </span>
                )}
                {!noData && otherDays > 0 && (
                    <span className="text-[11px] text-slate-500" data-testid="day-other-days" title={attr === 'placed'
                        ? 'righe regolate oggi ma PIAZZATE in un altro giorno: il calendario le conta là, quindi non entrano in questi totali'
                        : 'righe piazzate oggi ma regolate in un altro giorno: il calendario le conta là'}>
                        + {otherDays} di altre giornate (fuori dai totali)
                    </span>
                )}
                <span className="ml-auto tabular-nums">
                    <span
                        className="text-slate-400 mr-1 text-xs"
                        title="capitale IMPEGNATO dalle posizioni piazzate in questa giornata (non è quello ancora a rischio adesso)"
                    >
                        liability piazzata {noData ? DASH : fmtEur(liability)} ·
                    </span>
                    <span className="text-slate-400 mr-1 text-xs" title={TIP.realizedToday}>realizzato</span>
                    <b className={noData ? 'text-slate-500' : totalPnl > 0 ? 'text-emerald-400' : totalPnl < 0 ? 'text-red-400' : 'text-slate-300'} data-testid="day-total-pnl">
                        {noData ? DASH : fmtSignedEur(totalPnl)}
                    </b>
                    {!noData && day0.realizedOnOpen !== 0 && (
                        <span
                            className="ml-1 text-[11px] text-slate-500"
                            data-testid="day-realized-on-open"
                            title="P&L già incassato dalle coperture di posizioni ancora VIVE: è realizzato e il calendario lo conta, ma l’apertura non è ancora regolata"
                        >
                            (di cui {fmtSignedEur(day0.realizedOnOpen)} da coperture su posizioni vive)
                        </span>
                    )}
                </span>
            </div>
            {error ? (
                <div className="text-sm text-red-300 py-6 text-center" data-testid="day-detail-error">{error}</div>
            ) : noData ? (
                <div className="text-sm text-muted-foreground py-8 text-center" data-testid="day-detail-loading" role="status">caricamento…</div>
            ) : rowsShown.length === 0 ? (
                <div className="text-sm text-muted-foreground py-8 text-center" data-testid="day-detail-none">
                    nessun trade in questa giornata
                    {otherDays > 0 && (
                        <>: le {otherDays} righe di questa risposta sono {attr === 'placed' ? 'state piazzate' : 'state regolate'} in
                        un’altra giornata e il calendario le conta là</>
                    )}
                </div>
            ) : variant === 'omega' ? (
                // Omega §14: UNA riga per PARTITA (gamba 1T + gamba 2T con le chiusure
                // attaccate, risultati reali, P&L della partita) — stessa tabella del live
                // §3: la tabella mostra SOLO le posizioni che il calendario
                // attribuisce a questa giornata — le altre sono già dichiarate
                // dalla nota «+N di altre giornate (fuori dai totali)». Prima
                // entravano nella tabella ma non nei totali di testata, senza
                // alcun segno che le distinguesse: le somme a mano non tornavano.
                <MatchTradesTable
                    trades={rowsShown.flatMap((t) => [t, ...t.closes])}
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
                            {/* §3: righe = SOLO le posizioni attribuite a questa
                                giornata, le stesse che fanno i totali di testata e
                                del piede. Le altre restano dichiarate dalla nota
                                «+N di altre giornate (fuori dai totali)». */}
                            {rowsShown.map((t) => {
                                const b = statusBadgeOf(t);
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
                                        <td className="px-3 py-2 text-right tabular-nums">{fmtOdds(t.price)}</td>
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
                                            {isSettled
                                                ? fmtSignedEur(t.total_pnl)
                                                : cashedOf(t) !== 0
                                                    // la copertura è già regolata: quei soldi sono
                                                    // incassati e il calendario li conta già
                                                    ? <span title="già incassato dalle coperture regolate; l’apertura è ancora viva">{fmtSignedEur(cashedOf(t))}</span>
                                                    : (locked != null ? `(${fmtSignedEur(locked)})` : '—')}
                                        </td>
                                    </tr>,
                                    ...t.closes.map((c) => {
                                        const cb = statusBadgeOf(c);
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
                                                <td className="px-3 py-1 text-right tabular-nums">{fmtOdds(c.price)}</td>
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
                                    {/* Certificazione 12/09 — V/P per SEGNO del P&L TOTALE della
                                        posizione (apertura + chiusure), con lo stato come spareggio
                                        sullo zero: la stessa regola di `trading_daily_history` e dei
                                        tre `*_aggregates_sql`. Contando lo STATO il piede diceva
                                        «12V 1P» dove la cella del calendario diceva «11V 2P». */}
                                    {settled.length} regolati · {openCount} vivi ·{' '}
                                    <span title={WIN_LOSS_TIP}>{day0.won}V {day0.lost}P</span>
                                    {day0.voided > 0 ? ` · ${day0.voided} void` : ''}
                                    {notPlaced > 0 ? ` · ${notPlaced} non piazzati (fuori dai totali)` : ''}
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
