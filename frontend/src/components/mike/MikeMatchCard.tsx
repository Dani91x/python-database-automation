// ============================================================================
// MikeMatchCard — scheda di UNA partita seguita da Mike.
//
// DUE REGOLE NON NEGOZIABILI (richiesta dell'utente):
//   1) la scheda NON si muove: l'ordine lo decide la pagina (KO crescente) e
//      l'ALTEZZA è stabile — ogni zona è SEMPRE montata e mostra "—" quando non
//      ha dati, così una copertura che compare non fa saltare le altre card;
//   2) ogni numero è quello del SERVIZIO: il "se chiudo ora" arriva da
//      `live.cashout.per` (netto commissione, audit M5), la liability da
//      `live.liability` (netta, M4). La UI non ricalcola nulla al lordo.
//
// Zone (in quest'ordine, sempre presenti):
//   header (partita · punteggio · fase · freschezza feed · allarmi)
//   → quadro modello (λ / P(4) / hazard / pressione + istogramma dei gol totali)
//   → quote delle due linee con size, variazione dal tick precedente e betDelay
//   → posizioni (ingresso, quota ora, Δ tick, se chiudo ora NETTO, stato)
//   → ordini sul book → P&L a fine gara per gol totali → liability/bloccato
//   → cash out (valore, % sulla soglia, riga intelligente, uscita a modello)
//   → azioni (Cash out / Flatten / Salta / Riprendi) + esito ultima richiesta
// ============================================================================
import { memo, useEffect, useRef, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';
import { countdownToOff, formatMinute } from '@/lib/matchClock';
import { ticksBetween } from '@/lib/riskMath';
import { fmtMoney, fmtNum, fmtOdds, fmtPct, fmtPctPoints, fmtTime } from '@/lib/format';
import { sideMeta, T } from '@/lib/tradeStatus';
import { MikeCashOutButton } from '@/components/mike/MikeCashOutButton';
import { useSecondTick } from '@/components/mike/useMikeClock';
import {
    activeLegs, awaitingKickoff, bookOrders, eventFlags, feedFreshness, legSelectionLabel, legStatusLabel,
    lineLabel, marketLabel, marketStatusMeta, phaseMeta, pnlByTotalCells, positionRows, requestOutcome,
    roleLabel, VOID_ALL, MIKE_AWAITING_KICKOFF_NOTE,
    MIKE_TERMINAL_STATES, type MikeBook, type MikeCashoutSmart, type MikeEvent, type MikeLossExit,
    type MikeParams, type MikeRequest, type MikeRequestKind, type PositionRow,
} from '@/lib/mike';

export interface MikeMatchCardProps {
    ev: MikeEvent;
    params: MikeParams;
    /** modalità del bot: serve alla doppia conferma del cash out in LIVE */
    mode?: 'paper' | 'live';
    busy?: boolean;
    /** feed dello scanner stantio: azioni spente con motivo */
    stale?: boolean;
    staleReason?: string;
    /** ultima richiesta della UI per questa partita (M1) */
    lastRequest?: MikeRequest | null;
    /**
     * mercati ANNULLATI di questa partita ('OU35' / 'OU45', oppure ['*'] per
     * tutta la partita): il void e' per MERCATO, non per evento.
     */
    voidedMarkets?: string[];
    /**
     * kind con una richiesta IN VOLO per questa partita, come stringa
     * ("cashout,flatten"): una stringa e non una funzione perche' la card e'
     * memoizzata e deve poter confrontare le props senza dipendere da closure.
     */
    pendingKinds?: string;
    onRequest?: (kind: MikeRequestKind, eventId: string) => void;
}

// ------------------------------------------------------------------ helpers
function pnlClass(v: number | null | undefined): string {
    if (v == null) return 'text-slate-400';
    return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300';
}

const EDGE_BY_GROUP: Record<string, string> = {
    pre: 'border-l-teal-400/70',
    live: 'border-l-violet-400/70',
    flat: 'border-l-emerald-400/70',
    done: 'border-l-white/15',
    off: 'border-l-red-400/70',
};

/** Riga "cash out intelligente": cosa sta valutando il bot adesso. */
export function smartLabel(smart: MikeCashoutSmart | null | undefined, threshold: number, base: number | null): string | null {
    if (!smart || !smart.enabled) return null;
    const parts: string[] = [];
    if (smart.floor != null && base && base > 0) parts.push(`min ${fmtMoney(smart.floor)} (${fmtPctPoints((smart.floor / base) * 100)})`);
    if (smart.near) parts.push(`a un passo dal ${threshold}%`);
    if (smart.hot) parts.push('fase calda');
    if (smart.ev_hold != null) parts.push(`aspettare vale ${fmtMoney(smart.ev_hold, { signed: true })}`);
    if (smart.trigger) parts.push(`→ chiude (${smart.trigger})`);
    return parts.length ? `intelligente: ${parts.join(' · ')}` : null;
}

/** Riga "uscita in perdita a modello": tenere vs chiudere. */
export function lossExitLabel(le: MikeLossExit | null | undefined, cashoutNet: number | null): string | null {
    if (!le) return null;
    if (le.mode === 'fixed') return `uscita ${le.window ?? ''}: regola fissa (perdita ≤ ${le.pct ?? '—'}%)`;
    if (le.missing) return `uscita ${le.window ?? ''}: modello senza dati → regola fissa`;
    const parts: string[] = [];
    if (le.ev_hold != null) parts.push(`tenere vale ${fmtMoney(le.ev_hold, { signed: true })}`);
    if (le.p4 != null) parts.push(`P(4) ${fmtPct(le.p4, 0)}`);
    if (le.premium != null) parts.push(`premio ${fmtMoney(le.premium)}`);
    if (le.threshold != null && cashoutNet != null) parts.push(cashoutNet >= le.threshold ? '→ chiude' : '→ tiene');
    if (le.beyond_cap) parts.push('(oltre il tetto: tiene)');
    return `uscita ${le.window ?? ''} a modello: ${parts.join(' · ')}`;
}

/** Riga "attesa della copertura": perché il bot non copre ancora. */
export function coverWaitLabel(wait: Record<string, unknown> | null | undefined, gainPct: number | null | undefined): string | null {
    if (!wait && gainPct == null) return null;
    const w = wait ?? {};
    const parts: string[] = [];
    if (gainPct != null) parts.push(`risparmio atteso ${fmtPctPoints(gainPct)}`);
    const hazard = Number(w.hazard);
    if (Number.isFinite(hazard)) parts.push(`hazard ${fmtPct(hazard, 1)}`);
    const p4 = Number(w.p4 ?? w.p4_market);
    if (Number.isFinite(p4)) parts.push(`P(4) mercato ${fmtPct(p4, 0)}`);
    const until = Number(w.until_min ?? w.max_min);
    if (Number.isFinite(until)) parts.push(`al massimo fino al ${until}′`);
    if (w.reason) parts.push(String(w.reason).replace(/_/g, ' '));
    return `copertura: attende quota migliore${parts.length ? ` · ${parts.join(' · ')}` : ''}`;
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

/** freccia di variazione di una quota rispetto al tick precedente */
function Move({ now, prev }: { now: number | null | undefined; prev: number | null | undefined }) {
    if (now == null || prev == null || Math.abs(now - prev) < 0.0001) {
        return <span className="text-slate-700" aria-hidden>·</span>;
    }
    // NEUTRO di proposito: verde/rosso nel design system significano
    // favorevole/sfavorevole, e una quota che sale è buona o cattiva a seconda
    // del lato della posizione. Qui conta solo la DIREZIONE.
    return now > prev
        ? <span className="text-slate-200" title="quota in salita" aria-label="in salita">▲</span>
        : <span className="text-slate-400" title="quota in discesa" aria-label="in discesa">▼</span>;
}

/**
 * Countdown al calcio d'inizio: componente FOGLIA, l'unico che tick ogni
 * secondo (il tempo non entra nelle props della card, memoizzata).
 *
 * Checklist 7 — KO passato ma la partita non è ancora `inplay` nel feed: la
 * card resta in PRE-MATCH e lo DICE ("in attesa del fischio"), invece di
 * mostrare "fra —" come se il dato fosse rotto.
 */
function KickoffCountdown({ koAt, ev }: { koAt: string | null; ev: MikeEvent }) {
    const now = useSecondTick(Boolean(koAt));
    const cd = countdownToOff(koAt, now);
    if (cd === null && awaitingKickoff(ev, now)) {
        return (
            <span className="text-amber-300" data-testid="mike-awaiting-kickoff">
                {MIKE_AWAITING_KICKOFF_NOTE}
            </span>
        );
    }
    return (
        <>
            {'fra '}
            <span className="tabular-nums text-white/90" data-testid="mike-countdown">
                {cd ?? '—'}
            </span>
        </>
    );
}

/** tile del quadro dati: altezza fissa, "—" quando il dato non c'è */
function Cell({ label, value, title, testId }: { label: string; value: ReactNode; title?: string; testId?: string }) {
    return (
        <div className="rounded-md bg-black/30 border border-white/5 px-2 py-1.5 min-h-[42px]" title={title} data-testid={testId}>
            <div className="text-slate-500 uppercase tracking-wide text-[9px] truncate">{label}</div>
            <div className="tabular-nums text-white/90 truncate">{value}</div>
        </div>
    );
}

/** distribuzione P(totale gol) 0..8: barre, la colonna dei 4 gol in rosso */
function GoalsHistogram({ model, emp }: {
    model: Record<string, number> | null | undefined;
    emp: Record<string, number> | null | undefined;
}) {
    const src = model ?? emp ?? null;
    const source = model ? 'modello' : emp ? 'empirico' : null;
    const keys = Array.from({ length: 9 }, (_, i) => i);
    const max = src ? Math.max(0.0001, ...keys.map((k) => Number(src[String(k)] ?? 0))) : 1;
    return (
        <div className="rounded-md bg-black/30 border border-white/5 px-2 py-1.5" data-testid="mike-goals-histogram">
            <div className="flex items-center justify-between text-[9px] uppercase tracking-wide text-slate-500">
                <span>P(totale gol) 0…8</span>
                <span>{source ?? 'nessun modello per questa partita'}</span>
            </div>
            <div className="flex items-end gap-1 h-10 mt-1">
                {keys.map((k) => {
                    const v = src ? Number(src[String(k)] ?? 0) : 0;
                    const h = src ? Math.max(2, Math.round((v / max) * 36)) : 2;
                    return (
                        <div key={k} className="flex-1 flex flex-col items-center justify-end" title={src ? `${k} gol: ${fmtPct(v, 1)}` : undefined}>
                            <div
                                className={`w-full rounded-t ${k === 4 ? 'bg-rose-400/80' : 'bg-teal-400/50'}`}
                                style={{ height: `${h}px` }}
                                data-testid={`mike-goals-bar-${k}`}
                            />
                            <span className={`text-[8px] ${k === 4 ? 'text-rose-300' : 'text-slate-500'}`}>{k}</span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

/** quote di UNA linea: back/lay con size, variazione dal tick precedente, betDelay */
function QuoteLine({ label, book, prev, title, testId }: {
    label: string;
    book: MikeBook | undefined;
    prev: { back: number | null; lay: number | null } | undefined;
    title?: string;
    testId?: string;
}) {
    // lo stato del mercato Betfair non arriva mai grezzo in pagina: SOSPESO e
    // CHIUSO significano "non si opera adesso" (ambra/rosso), OPEN non si dice.
    const status = marketStatusMeta(book?.status);
    return (
        <div
            className={`rounded-md bg-black/30 border px-2 py-1.5 min-h-[50px] ${status?.alarming ? 'border-amber-400/40' : 'border-white/5'}`}
            title={title}
            data-testid={testId}
        >
            <div className="flex items-center justify-between text-[9px] uppercase tracking-wide text-slate-500">
                <span>{label}</span>
                <span>
                    {book?.bet_delay ? `betDelay ${book.bet_delay} s` : ''}
                    {status && (
                        <span className={status.cls} data-testid="mike-market-status">
                            {book?.bet_delay ? ' · ' : ''}{status.label}
                        </span>
                    )}
                </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] tabular-nums">
                <span className="text-sky-300">
                    <Move now={book?.best_back ?? null} prev={prev?.back} /> {fmtOdds(book?.best_back ?? null)}
                    <span className="text-slate-500 text-[10px]"> {book ? fmtMoney(book.back_size, { decimals: 0 }) : '—'}</span>
                </span>
                <span className="text-slate-600">/</span>
                <span className="text-rose-300">
                    {fmtOdds(book?.best_lay ?? null)} <Move now={book?.best_lay ?? null} prev={prev?.lay} />
                    <span className="text-slate-500 text-[10px]"> {book ? fmtMoney(book.lay_size, { decimals: 0 }) : '—'}</span>
                </span>
            </div>
        </div>
    );
}

// ------------------------------------------------------------------ card
function MikeMatchCardBase({
    ev, params, mode = 'paper', busy, stale, staleReason, lastRequest, voidedMarkets = [],
    pendingKinds = '', onRequest,
}: MikeMatchCardProps) {
    const isPending = (kind: MikeRequestKind) => pendingKinds.split(',').includes(kind);
    const meta = phaseMeta(ev.state);
    const live = ev.live ?? {};
    const dossier = ev.dossier ?? {};
    const legs = activeLegs(ev);
    const cashout = live.cashout ?? null;
    const threshold = Number(cashout?.target_pct ?? params.cashout_profit_pct ?? 5);
    const coPct = cashout?.pct ?? null;
    const inplay = Boolean(live.inplay);
    const minuteLabel = formatMinute(live.minute ?? null);
    const terminal = MIKE_TERMINAL_STATES.includes(ev.state);
    const hasPosition = legs.some((l) => l.matched > 0);
    const cells = pnlByTotalCells(live.pnl_by_total, live.goals);
    const books = live.books ?? {};
    const rows = positionRows(ev);
    const orders = bookOrders(ev);
    const sels = ((ev.ctx as { selections?: Record<string, number> } | null)?.selections) ?? {};
    const marketIds = (ev.markets ?? {}) as Record<string, { market_id?: string | null } | undefined>;
    const barPct = coPct != null && threshold > 0 ? Math.max(0, Math.min(100, (coPct / threshold) * 100)) : 0;
    const freshness = feedFreshness(live.feed_age_s);
    const linesMissing = (live.lines_missing ?? []).filter(Boolean);
    const outcome = lastRequest ? requestOutcome(lastRequest) : null;
    const flags = eventFlags(ev);
    const voidAll = voidedMarkets.includes(VOID_ALL);
    const isVoidMarket = (market: string) => voidAll || voidedMarkets.includes(market);

    // quote del tick PRECEDENTE: la card si ri-renderizza solo quando il
    // servizio riscrive l'evento, quindi il valore letto qui è quello di prima
    const prevBooks = useRef<Record<string, { back: number | null; lay: number | null }>>({});
    const prevSnapshot = prevBooks.current;
    useEffect(() => {
        const next: Record<string, { back: number | null; lay: number | null }> = {};
        for (const [k, b] of Object.entries(books)) next[k] = { back: b?.best_back ?? null, lay: b?.best_lay ?? null };
        prevBooks.current = next;
    });

    // cash out: spento CON MOTIVO (feed stantio, linea assente, richiesta in volo)
    const cashPending = isPending('cashout');
    const cashDisabledReason = flags.flattenPending
        ? 'Chiusura manuale già in corso: il servizio sta chiudendo la posizione.'
        : busy
        ? 'Operazione in corso: attendi.'
        : stale
            ? `Feed stantio (${staleReason ?? 'scanner fermo'}): il servizio rifiuterebbe la richiesta.`
            : freshness.tone === 'stale'
                ? 'Feed di questa partita fermo: nessuna chiusura a prezzi fantasma.'
                : linesMissing.length > 0
                    ? `Linea ${linesMissing.map(lineLabel).join(', ')} assente nel feed: chiusura non calcolabile.`
                    : !hasPosition
                        ? 'Nessuna posizione aperta su questa partita.'
                        : null;

    const cashBreakdown = rows.map((r) => ({ label: r.label, value: cashout?.per?.[r.key] ?? null }));

    return (
        <Card
            className={`glass-card border-white/10 border-l-4 p-3 space-y-2.5 ${EDGE_BY_GROUP[meta.group] ?? ''}`}
            data-testid="mike-match-card"
            data-event-id={ev.event_id}
            data-state={ev.state}
        >
            {/* ------------------------------------------------- header */}
            <div className="flex items-start justify-between gap-2 flex-wrap min-h-[54px]">
                <div className="min-w-0 flex items-center gap-3">
                    {/* il punteggio è SEMPRE montato: in pre-match mostra "–" e la card non cambia altezza */}
                    <div className="flex flex-col items-center shrink-0 w-[58px]" data-testid="mike-score">
                        <span className="rounded-md bg-black/50 border border-white/15 px-2.5 py-0.5 font-display font-black text-xl tabular-nums text-white leading-tight">
                            {live.score_home != null && live.score_away != null
                                ? `${live.score_home}–${live.score_away}`
                                : '–'}
                        </span>
                        <span className="text-[10px] text-rose-300 h-[14px]">
                            {(live.red_home ?? 0) > 0 || (live.red_away ?? 0) > 0
                                ? <span title="espulsioni casa / trasferta">🟥 {live.red_home ?? 0}/{live.red_away ?? 0}</span>
                                : ''}
                        </span>
                    </div>
                    <div className="min-w-0">
                        <div className="font-heading font-bold text-sm truncate">{ev.event_name ?? ev.event_id}</div>
                        <div className="text-[11px] text-slate-400 truncate">
                            {ev.competition ?? '—'}
                            {inplay
                                ? <>
                                    {' · '}<span className="text-white/90 font-semibold">{minuteLabel ?? '—′'}</span>
                                    {live.goals != null && <> · {live.goals} gol</>}
                                    {live.ht && <span className="text-amber-300"> · intervallo</span>}
                                    {live.ht_score && <span className="text-slate-500"> · 1T {live.ht_score[0]}–{live.ht_score[1]}</span>}
                                </>
                                : terminal
                                    ? <>
                                        {' · KO '}<span className="text-white/90">{fmtTime(ev.ko_at)}</span>
                                        {live.goals != null && <> · {live.goals} gol totali</>}
                                        {' · '}<span className="text-slate-300">{meta.label.toLowerCase()}</span>
                                    </>
                                    : <>
                                        {' · KO '}<span className="text-white/90">{fmtTime(ev.ko_at)}</span>
                                        {' · '}<KickoffCountdown koAt={ev.ko_at} ev={ev} />
                                    </>}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                    <Badge variant="outline" className={`text-[10px] font-heading ${meta.cls}`} data-testid="mike-phase">
                        {meta.label}
                    </Badge>
                    <Badge variant="outline" className={`text-[10px] ${freshness.cls}`} data-testid="mike-feed-age">
                        {freshness.label}
                    </Badge>
                    <BetfairMediaButtons eventId={ev.event_id} compact />
                </div>
            </div>

            {/* ------------------------------------------------- allarmi (zona sempre presente) */}
            <div className="space-y-1 min-h-[20px]" data-testid="mike-alerts">
                {linesMissing.length > 0 && (
                    <div className="rounded-md border border-red-500/50 bg-red-500/10 px-2 py-1 text-[11px] text-red-200" role="alert" data-testid="mike-lines-missing">
                        linea {linesMissing.map(lineLabel).join(', ')} assente nel feed: nessuna copertura e nessun cash out possibile
                    </div>
                )}
                <div className="flex items-center gap-1.5 flex-wrap">
                    {flags.flattenPending && (
                        <Badge variant="outline" className="text-[9px] bg-rose-500/20 text-rose-200 border-rose-400/50 animate-pulse" data-testid="mike-flatten-pending">
                            CHIUSURA IN CORSO
                        </Badge>
                    )}
                    {voidedMarkets.length > 0 && (
                        <Badge variant="outline" className="text-[9px] bg-slate-500/20 text-slate-200 border-slate-400/50" data-testid="mike-void">
                            {voidAll
                                ? 'VOID · mercato annullato'
                                : `VOID (${voidedMarkets.map(marketLabel).join(', ')})`}
                        </Badge>
                    )}
                    {live.reconcile_pending && (
                        <Badge variant="outline" className="text-[9px] bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/40" data-testid="mike-reconcile">
                            ORDINE IN VERIFICA SU BETFAIR
                        </Badge>
                    )}
                    {flags.noReentry && (
                        <Badge variant="outline" className="text-[9px] bg-amber-500/15 text-amber-300 border-amber-500/40" data-testid="mike-no-reentry">
                            NESSUN RIENTRO
                        </Badge>
                    )}
                    {ev.mode === 'live' && (
                        <Badge variant="outline" className="text-[9px] bg-red-500/15 text-red-300 border-red-500/40">SOLDI VERI</Badge>
                    )}
                </div>
            </div>

            {/* ------------------------------------------------- quadro modello */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]" data-testid="mike-model">
                <Cell
                    label="P(4 gol) modello"
                    value={fmtPct(live.p4_model ?? dossier.p4_pre ?? null, 1)}
                    title="probabilità di esattamente 4 gol secondo il modello: è l'unico esito che perde"
                />
                <Cell label="P(4 gol) mercato" value={fmtPct(live.p4_market ?? null, 1)} title="P(4) implicita dalle due linee O/U" />
                <Cell
                    label={inplay ? 'Hazard gol 3′' : 'P(Over 4.5) modello'}
                    value={inplay
                        ? <>
                            {fmtPct(live.hazard ?? null, 1)}
                            <span className="text-slate-500 text-[9px]"> atl {fmtPct(live.hazard_atlas ?? null, 1)} · mod {fmtPct(live.hazard_model ?? null, 1)}</span>
                        </>
                        : fmtPct(live.p_over45_model ?? null, 1)}
                    title={inshoot(inplay)}
                />
                <Cell
                    label={inplay ? 'Pressione' : 'λ casa / trasferta'}
                    value={inplay
                        ? (live.pressure != null
                            ? <span data-testid="mike-pressure">×{fmtNum(live.pressure, 2)}{(live.pressure ?? 1) >= Number(params.cashout_smart_pressure_hot ?? 1.15) ? ' 🔥' : ''}</span>
                            : <span data-testid="mike-pressure">—</span>)
                        : <span data-testid="mike-lambda">{fmtNum(dossier.lambda_home ?? null, 2)} / {fmtNum(dossier.lambda_away ?? null, 2)}</span>}
                    title={inplay ? 'corner e cartellini dal feed (1,00 = neutra)' : 'gol attesi da modello'}
                />
            </div>

            <GoalsHistogram model={live.p_total_model} emp={live.p_total_emp} />

            {/* ------------------------------------------------- quote delle due linee */}
            {/* le TRE linee che Mike usa sono sempre tutte in pagina: se una
                sparisce dal feed si vede il "—" al suo posto, non una card che si
                accorcia (e il banner rosso qui sopra lo dice) */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" data-testid="mike-quotes">
                <QuoteLine
                    label="Under 3.5 back / lay"
                    book={books['OU35|UNDER']}
                    prev={prevSnapshot['OU35|UNDER']}
                    title={`Under 3.5 · market ${marketIds.OU35?.market_id ?? '—'} · selection ${sels['OU35|UNDER'] ?? '—'}`}
                    testId="mike-quote-ou35"
                />
                <QuoteLine
                    label="Over 4.5 back / lay"
                    book={books['OU45|OVER']}
                    prev={prevSnapshot['OU45|OVER']}
                    title={`Over 4.5 · market ${marketIds.OU45?.market_id ?? '—'} · selection ${sels['OU45|OVER'] ?? '—'}`}
                    testId="mike-quote-ou45"
                />
                <QuoteLine
                    label="Under 4.5 (re-ingresso)"
                    book={books['OU45|UNDER']}
                    prev={prevSnapshot['OU45|UNDER']}
                    title={`Under 4.5 · market ${marketIds.OU45?.market_id ?? '—'} · selection ${sels['OU45|UNDER'] ?? '—'} · linea del re-ingresso dopo un gol`}
                    testId="mike-quote-ou45-under"
                />
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400 min-h-[18px]" data-testid="mike-meta-line">
                <span>scambiato <span className="tabular-nums text-white/90">{live.total_matched != null ? fmtMoney(live.total_matched, { decimals: 0 }) : '—'}</span></span>
                <span>primo ingresso <span className="tabular-nums text-white/90">{fmtOdds(ev.entry_price_initial)}</span></span>
                <span>ciclo <span className="tabular-nums text-white/90">{ev.cycle_no}</span></span>
                {ev.settled_pnl != null && (
                    <span>regolato <span className={`tabular-nums font-semibold ${pnlClass(ev.settled_pnl)}`}>{fmtMoney(ev.settled_pnl, { signed: true })}</span></span>
                )}
            </div>

            {/* ------------------------------------------------- posizioni */}
            <div className="rounded-md border border-white/5 bg-black/20 overflow-x-auto min-h-[56px]" data-testid="mike-positions">
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
                        {rows.length === 0 ? (
                            <tr><td colSpan={5} className="px-2 py-2 text-slate-500">nessuna posizione aperta —</td></tr>
                        ) : rows.map((r) => {
                            const book = books[r.key];
                            const { ticks, favourable, closeAt } = positionTicks(r, book);
                            // M5: SOLO il netto del servizio. Se manca si dichiara.
                            const locked = cashout?.per?.[r.key] ?? null;
                            const gross = cashout?.per_gross?.[r.key] ?? null;
                            const decided = (cashout?.decided ?? []).includes(r.key);
                            const legsOfRow = legs.filter((l) => `${l.market}|${l.selection}` === r.key);
                            const unmatched = legsOfRow.reduce((s, l) => s + Math.max(0, Number(l.size) - Number(l.matched || 0)), 0);
                            return (
                                <tr key={r.key} className="border-t border-white/5" data-testid="mike-pos-row"
                                    title={`${r.label} · market ${marketIds[r.market]?.market_id ?? '—'} · selection ${r.selectionId ?? '—'} · ${r.roles.map(roleLabel).join(', ')}`}>
                                    <td className="px-2 py-1">
                                        <Badge variant="outline" className={`text-[9px] mr-1 ${sideMeta(r.netSide.toLowerCase()).cls}`}>{r.netSide}</Badge>
                                        <span className="font-semibold text-white/90">{r.label}</span>
                                        <span className="text-slate-500"> · {fmtMoney(r.matched)}{unmatched > 0.004 ? ` (+${fmtMoney(unmatched)} sul book)` : ''}</span>
                                        <span className="block text-[9px] text-slate-500">
                                            {r.roles.map(roleLabel).join(' · ')}
                                            {legsOfRow.some((l) => l.status === 'pending_reconcile') ? ' · IN VERIFICA' : ''}
                                            {decided ? ' · esito già deciso' : ''}
                                            {isVoidMarket(r.market)
                                                ? <span className="text-slate-300"> · VOID ({r.label})</span>
                                                : null}
                                        </span>
                                    </td>
                                    <td className="text-right tabular-nums text-white/90">{fmtOdds(r.entryPrice)}</td>
                                    <td className="text-right tabular-nums">
                                        <span className="text-sky-300">{fmtOdds(book?.best_back ?? null)}</span>
                                        <span className="text-slate-600">/</span>
                                        <span className="text-rose-300">{fmtOdds(book?.best_lay ?? null)}</span>
                                        <span className="block text-[9px] text-slate-500">
                                            {closeAt != null ? `chiudo @${fmtOdds(closeAt)}` : 'nessun prezzo per chiudere'}
                                        </span>
                                    </td>
                                    <td className="text-right"><TickDelta ticks={ticks} favourable={favourable} /></td>
                                    <td
                                        className={`text-right tabular-nums px-2 font-semibold ${pnlClass(locked)}`}
                                        data-testid="mike-pos-locked"
                                        title={locked == null
                                            ? 'il servizio non ha pubblicato il netto per questa selezione'
                                            : `lordo ${fmtMoney(gross, { signed: true })} · netto commissione dal servizio`}
                                    >
                                        {locked != null ? fmtMoney(locked, { signed: true }) : '—'}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* ------------------------------------------------- ordini sul book */}
            <div className="text-[11px] min-h-[20px]" data-testid="mike-orders">
                <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">Ordini sul book</span>
                {orders.length === 0 ? <span className="text-slate-500">—</span> : (
                    <div className="space-y-0.5 mt-0.5" data-testid="mike-pending">
                        {orders.map((l) => {
                            const book = books[`${l.market}|${l.selection}`];
                            const price = Number(l.price);
                            // una LAY appoggiata si abbina quando il best back SALE fino al suo prezzo;
                            // una BACK quando il best lay scende
                            const ref = l.side === 'lay' ? (book?.best_back ?? null) : (book?.best_lay ?? null);
                            const dist = ref != null && price > 0 ? ticksBetween(ref, price) : null;
                            const rest = Math.max(0, Number(l.size) - Number(l.matched || 0));
                            return (
                                <div key={l.ref} className="flex items-center gap-2 flex-wrap text-slate-300" data-testid="mike-order-row">
                                    <Badge variant="outline" className={`text-[9px] ${sideMeta(l.side).cls}`}>{sideMeta(l.side).label}</Badge>
                                    <span>{roleLabel(l.role)} <span className="text-slate-500">({legSelectionLabel(l)})</span></span>
                                    <span className="tabular-nums text-white/90">{fmtMoney(rest)} @ {fmtOdds(price)}</span>
                                    <span className="text-slate-500">
                                        {legStatusLabel(l)}{l.persistence === 'PERSIST' ? ' · PERSIST' : ''}
                                        {Number(l.matched) > 0 ? ` · abbinati ${fmtMoney(Number(l.matched))}` : ''}
                                    </span>
                                    <span className={`tabular-nums ${dist === null ? 'text-slate-500' : dist === 0 ? 'text-emerald-300' : 'text-amber-200/80'}`}>
                                        {dist === null ? 'distanza dal best: —' : dist === 0 ? 'al best' : `${Math.abs(dist)} tick ${dist > 0 ? 'sopra' : 'sotto'} il best`}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* ------------------------------------------------- P&L per gol totali + esposizione */}
            <div className="min-h-[46px]" data-testid="mike-pnl-by-total">
                <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">A fine gara, per gol totali</span>
                {cells.length === 0 ? <span className="text-[11px] text-slate-500">—</span> : (
                    <div className="flex items-center gap-1 flex-wrap mt-0.5">
                        {cells.map((c) => (
                            <span
                                key={c.total}
                                className={`rounded px-1.5 py-0.5 text-[10px] tabular-nums border ${c.isFour ? 'border-rose-400/60 bg-rose-500/15' : 'border-white/10 bg-black/30'} ${c.isCurrent ? 'ring-1 ring-white/50' : ''} ${pnlClass(c.value)}`}
                                data-testid={`pnl-total-${c.total}`}
                                title={c.isCurrent ? 'gol attuali' : c.isFour ? 'i 4 gol: l’unico esito che perde' : undefined}
                            >
                                {c.isLast ? `${c.total}+` : c.total}: {fmtMoney(c.value, { signed: true })}
                            </span>
                        ))}
                    </div>
                )}
                <div className="flex flex-wrap gap-x-3 text-[11px] mt-1">
                    <span className="text-slate-400">
                        {T.openLiability} <b className="text-orange-400 tabular-nums" data-testid="mike-liability">{live.liability != null ? fmtMoney(live.liability) : '—'}</b>
                    </span>
                    <span className="text-slate-400">
                        {T.lockedPnl} <b className={`tabular-nums ${pnlClass(live.locked)}`} data-testid="mike-locked">{live.locked != null ? fmtMoney(live.locked, { signed: true }) : '—'}</b>
                    </span>
                </div>
            </div>

            {/* ------------------------------------------------- cash out + azioni */}
            <div className="flex items-start justify-between gap-2 flex-wrap min-h-[64px]">
                <div className="text-[11px] min-w-0 flex-1">
                    <span className="text-slate-500 uppercase tracking-wide text-[9px] mr-1">{T.cashOut} ora</span>
                    {cashout && cashout.complete
                        ? <span className={`tabular-nums font-heading font-bold ${pnlClass(cashout.net)}`} data-testid="mike-cashout-value">
                            {fmtMoney(cashout.net, { signed: true })}
                            {coPct != null && <span className="text-slate-400 font-normal"> ({fmtPctPoints(coPct)} · soglia {fmtPctPoints(threshold)})</span>}
                        </span>
                        : <span className="text-slate-500" data-testid="mike-cashout-value">
                            {hasPosition ? 'prezzi incompleti' : 'nessuna posizione'}
                        </span>}
                    <div className="mt-1 h-1 w-full max-w-[220px] rounded bg-white/10 overflow-hidden"
                        role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(barPct)}
                        aria-label="Avanzamento verso la soglia di cash out">
                        <div
                            className={`h-full ${coPct != null && coPct >= threshold ? 'bg-emerald-400' : coPct != null && coPct > 0 ? 'bg-teal-400/70' : 'bg-red-400/70'}`}
                            style={{ width: `${barPct}%` }}
                        />
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5 min-h-[13px]" data-testid="mike-cashout-smart">
                        {smartLabel(cashout?.smart ?? null, threshold, cashout?.base ?? null) ?? ''}
                    </div>
                    <div className="text-[10px] text-amber-200/80 min-h-[13px]" data-testid="mike-loss-exit">
                        {lossExitLabel(live.loss_exit ?? null, cashout?.net ?? null) ?? ''}
                    </div>
                    <div className="text-[10px] text-teal-200/80 min-h-[13px]" data-testid="mike-cover-wait">
                        {coverWaitLabel(live.cover_wait, live.cover_gain_pct) ?? ''}
                    </div>
                    {outcome && (
                        <div
                            className={`text-[10px] mt-0.5 ${outcome.tone === 'ok' ? 'text-emerald-300' : outcome.tone === 'warn' ? 'text-amber-300' : outcome.tone === 'bad' ? 'text-red-300' : 'text-slate-400'}`}
                            data-testid="mike-request-outcome"
                            title={outcome.message || undefined}
                        >
                            {outcome.label}
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-1 flex-wrap justify-end">
                    {!terminal && hasPosition && (
                        <MikeCashOutButton
                            eventName={ev.event_name ?? ev.event_id}
                            net={cashout?.net ?? null}
                            pct={coPct}
                            targetPct={threshold}
                            base={cashout?.base ?? null}
                            complete={Boolean(cashout?.complete)}
                            disabledReason={cashDisabledReason}
                            pending={cashPending}
                            mode={mode}
                            breakdown={cashBreakdown}
                            lastOutcome={outcome?.label ?? null}
                            onCashOut={() => onRequest?.('cashout', ev.event_id)}
                        />
                    )}
                    {!terminal && orders.length > 0 && (
                        <Button
                            size="sm" variant="ghost" className="h-7 text-[11px] text-amber-200"
                            disabled={Boolean(busy) || isPending('cancel')}
                            onClick={() => onRequest?.('cancel', ev.event_id)}
                            data-testid="mike-cancel-btn"
                            title="annulla gli ordini ancora sul book (le posizioni abbinate restano)"
                        >Annulla ordini</Button>
                    )}
                    {!terminal && hasPosition && (
                        <Button
                            size="sm" variant="ghost" className="h-7 text-[11px] text-rose-200"
                            disabled={Boolean(busy) || Boolean(cashDisabledReason) || isPending('flatten')}
                            onClick={() => onRequest?.('flatten', ev.event_id)}
                            data-testid="mike-flatten-btn"
                            title="chiude tutto a mercato senza guardare la soglia di profitto"
                        >Flatten</Button>
                    )}
                    {!terminal && !hasPosition && ev.state !== 'SKIPPED' && (
                        <Button
                            size="sm" variant="ghost" className="h-7 text-[11px] text-slate-400"
                            disabled={Boolean(busy) || isPending('skip_event')}
                            onClick={() => onRequest?.('skip_event', ev.event_id)}
                            data-testid="mike-skip-btn"
                        >Salta</Button>
                    )}
                    {(ev.state === 'SKIPPED' || ev.state === 'ERROR' || flags.noReentry) && (
                        <Button
                            size="sm" variant="outline" className="h-7 text-[11px] border-teal-400/40 text-teal-200 hover:bg-teal-500/15"
                            disabled={Boolean(busy) || isPending('resume_event')}
                            onClick={() => onRequest?.('resume_event', ev.event_id)}
                            data-testid="mike-resume-btn"
                        >Riprendi</Button>
                    )}
                </div>
            </div>
        </Card>
    );
}

function inshoot(inplay: boolean): string {
    return inplay
        ? 'probabilità di un gol nei prossimi 3 minuti: MAX fra Atlante empirico e modello λ'
        : 'probabilità di Over 4.5 secondo il modello: è il costo atteso della copertura';
}

/**
 * `React.memo` con confronto ESPLICITO: la card si ri-disegna solo quando il
 * servizio riscrive l'evento (`updated_at`) o cambia qualcosa che la riguarda.
 * Il tempo NON entra fra le props: il countdown ha il suo tick foglia.
 */
export const MikeMatchCard = memo(MikeMatchCardBase, (a, b) => (
    a.ev.event_id === b.ev.event_id
    && a.ev.updated_at === b.ev.updated_at
    && a.ev.state === b.ev.state
    && a.params === b.params
    && a.mode === b.mode
    && a.busy === b.busy
    && a.stale === b.stale
    && a.staleReason === b.staleReason
    && (a.lastRequest?.id ?? null) === (b.lastRequest?.id ?? null)
    && (a.lastRequest?.status ?? null) === (b.lastRequest?.status ?? null)
    && a.pendingKinds === b.pendingKinds
    && (a.voidedMarkets ?? []).join(',') === (b.voidedMarkets ?? []).join(',')
    && a.onRequest === b.onRequest
));

export default MikeMatchCard;
