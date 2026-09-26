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
import {
    CashOutButton, greenPrice, hedgeSide, netAfterCommission, partialLockedPnl,
} from '@/components/trading/CashOutButton';
import { ExitBadge } from '@/components/trading/ExitBadge';
import { ModeBadge } from '@/components/trading/ModeBadge';
import { liveScoreLabel } from '@/lib/useScanLiveFeed';
import { tradeExit } from '@/lib/dailyHistory';
import { fmtMoney, fmtOdds, fmtPct, fmtTime, fmtQuotaAbbinata, DASH } from '@/lib/format';
import { statusMeta, pnlClass, pnlClassSoft, T } from '@/lib/tradeStatus';
import { positionInfo } from '@/lib/omega';
import { tickAFavore } from '@/lib/riskMath';
import type { CalcioScanPayload, TennisScanPayload } from '@/lib/safeStrategyScan';
import {
    blindSince, cappedFrom, comboIncomplete, comboLasciataAlTrader, errorFinal, exitRunState, hedgeState, isReconciling,
    lastRequestFor, marketBlocked, requestOutcome, safeTradeBook, staleReason,
    tradeCommission, tradeExposureNow, FEED_ROW_STALE_MS,
    tradeHold, holdReasonLabel, holdReasonHasP, pLoseEntry, tradeOppKind,
    groupClosingLegs, hedgeTooltip, partialHedge,
    type FeedFreshness, type SafeActivityRow, type SafeMode, type SafeRequest, type SafeTrade,
    type SafeTradeStatus, type TradeBook,
} from '@/lib/safeBot';
// reperto 17/09 — LO STATO DI USCITA (exit_wait/exit_hold/feed_blind) che il
// trader NON vedeva: fra un punto e l'altro il book si svuota per qualche
// secondo e la posizione restava «in perdita senza spiegazione».
import { latestExitActivityFor, safeActivityExitStatus } from '@/lib/safeExitStatus';
import { safeMarketLabel, safeReasonLabel } from './safeActivity';
// C.12b — stato dell'ORDINE condiviso con Omega, Mike e la Control Room
import { StatoOrdineRiga, StatoOrdineCompatto } from '@/components/trading/StatoOrdine';
import { statoOrdine } from '@/lib/statoOrdine';
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

/**
 * P&L della riga come NUMERO o `null`.
 *
 * CERT. 13/09 — il tipo dichiara `pnl: number`, ma il database restituisce
 * `null` finché la riga non è regolata: `Number(null)` è 0, e uno zero al posto
 * di «non ancora deciso» è la bugia più pericolosa della pagina (dice «non hai
 * né guadagnato né perso» su una posizione che è ancora tutta a rischio).
 */
function pnlOf(t: SafeTrade): number | null {
    const v = t.pnl;
    if (v === null || v === undefined) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}

/** `meta.exit_hold.source` del servizio (`_p_selection_wins`) → italiano. */
const HOLD_SOURCE_IT: Record<string, string> = {
    model: 'modello del servizio', market: 'quote di mercato', none: 'nessuna stima disponibile',
};

const CLS = {
    amber: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    sky: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
    teal: 'bg-teal-500/15 text-teal-300 border-teal-500/40',
    green: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50',
    red: 'bg-red-500/15 text-red-300 border-red-500/40',
    orange: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
    // CERT. 13/09 — il VIOLA resta SOLO alla variante «Risultato Esatto»
    // (variantStyles.ts): nella stessa tabella lo stesso colore indicava due
    // cose diverse (la strategia nella colonna «Strategia», il «manuale» nelle
    // colonne «Partita» e «Stato»). Tutto ciò che è MANUALE passa al CIANO —
    // non all'indaco, già preso da «APPOGGIATA · NON ABBINATA» (RESTING_META).
    cyan: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40',
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
        // 24/09 (B25 + pulsanti) — gamba MANUALE lasciata al trader
        // (`meta.combo_lasciata_al_trader`): il servizio NON la sta chiudendo,
        // ha scritto la proposta di copertura in scheda. Dirlo «in chiusura»
        // sarebbe falso.
        if (comboLasciataAlTrader(t)) {
            return {
                label: 'COMBO INCOMPLETA: lasciata a te', cls: CLS.red, edge: 'border-l-red-500/60',
                title: 'lasciata a te: proposta di copertura in scheda. Una gamba della combinazione non si è abbinata; questa è tua e il bot non la tocca',
            };
        }
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
            return { label: 'CASH OUT MANUALE', cls: CLS.cyan, edge: 'border-l-cyan-500/60', title: hedgeTooltip(t, closes[0] ?? null) };
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
        // C.12b — un ordine solo APPOGGIATO sul book NON e' una posizione
        // aperta: non copre niente e il rischio e' ancora tutto scoperto.
        // `RESTING_META` esisteva dal 12/09 ma qui non veniva passata mai.
        const m = statusMeta(t.status, { resting: statoOrdine(t).esito === 'appoggiato' });
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

/**
 * «Se chiudo ora» NETTO di UNA posizione, con i prezzi del feed.
 *
 * Estratta dal corpo della tabella (13/09) perché serve in DUE posti: la
 * colonna della riga e il TOTALE in testa alla sezione. Due formule diverse per
 * lo stesso numero avrebbero dato due cifre diverse sullo stesso schermo — ed è
 * proprio il genere di incoerenza che fa perdere fiducia in una pagina di soldi.
 * `null` = non calcolabile (nessun prezzo nel feed): MAI uno zero.
 */
export function safeCloseNow(
    t: SafeTrade,
    payload: CalcioScanPayload | TennisScanPayload | null | undefined,
    commissionPct: number,
): number | null {
    const book = safeTradeBook(t, payload ?? null);
    const exp = tradeExposureNow(t);
    const nowPrice = greenPrice(exp.win, exp.lose, book?.back ?? null, book?.lay ?? null);
    if (nowPrice == null) return null;
    return netAfterCommission(
        partialLockedPnl(nowPrice, exp.win, exp.lose, 1),
        tradeCommission(t, commissionPct),
    );
}

/**
 * TOTALE «se chiudo ora» delle posizioni ANCORA VIVE.
 *
 * `null` quando nessuna posizione viva è valutabile: la barra dei totali scrive
 * «—». Una posizione viva senza prezzo NON contribuisce con zero — sarebbe come
 * dichiarare che chiudere quella posizione non costa e non rende niente.
 * Il conteggio `nonValutabili` dice quante sono rimaste fuori.
 */
export function safeCloseNowTotal(
    trades: readonly SafeTrade[],
    liveFeed: Record<string, CalcioScanPayload | TennisScanPayload>,
    commissionPct: number,
): { totale: number | null; valutate: number; nonValutabili: number } {
    let totale = 0, valutate = 0, nonValutabili = 0;
    for (const t of trades) {
        const hedge = hedgeState(t);
        const viva = t.status === 'open' || t.status === 'pending'
            || (t.status === 'hedged' && hedge != null && !hedge.complete);
        if (!viva) continue;
        const v = safeCloseNow(t, liveFeed[t.event_id], commissionPct);
        if (v == null) { nonValutabili += 1; continue; }
        totale += v;
        valutate += 1;
    }
    return {
        totale: valutate > 0 ? Math.round(totale * 100) / 100 : null,
        valutate,
        nonValutabili,
    };
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
    /**
     * Attività del servizio (`safe_strategy_activity`, C.xx 17/09): serve a
     * mostrare lo STATO DI USCITA (`exit_wait` / `exit_hold` / `feed_blind`)
     * dell'ultimo ciclo per quel trade — «In attesa: mercato sospeso»,
     * «Tenuta: ...», «Proposta in attesa della tua firma». Assente = nessuno
     * stato aggiuntivo (le altre attività continuano a comportarsi come oggi).
     */
    activity?: SafeActivityRow[];
    /**
     * CERT. 13/09 — modalità ATTIVA sul servizio in questo momento.
     * Serve solo a ATTENUARE le righe di un'altra modalità: una posizione LIVE
     * in una schermata PAPER (o viceversa) non è un errore, ma non è nemmeno
     * quello che l'utente sta guardando, e mescolarle senza distinzione è il
     * modo più rapido per chiudere la posizione sbagliata. Il badge di modalità
     * c'è SEMPRE su ogni riga, anche senza questa prop.
     */
    currentMode?: SafeMode;
    /** testo dello stato vuoto (la pagina distingue "oggi" da "tutte") */
    emptyText?: string;
    /** istante corrente (ms): eta' dell'ultima notizia da Betfair. Test: fisso. */
    nowMs?: number;
}

const COLS = 16;

export function SafeTradesTable({
    trades, commissionPct, liveFeed, isCashOutPending, freshnessOf, onCashOut, onCancel,
    requests = [], emptyText, currentMode, nowMs, activity = [],
}: SafeTradesTableProps) {
    const now = nowMs ?? Date.now();
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
                        // 26/09 (F-4): + = a favore (un lay guadagna se la quota sale);
                        // prima ×−1 sul lay rovesciava il segno di entrambi i lati
                        const dTicks = nowPrice != null && t.price != null && t.price > 1
                            ? tickAFavore(t.side === 'lay' ? 'lay' : 'back', t.price, nowPrice)
                            : null;
                        // CHIUSURA-01: stessa formula del servizio (stake di
                        // copertura arrotondato al centesimo, peggiore dei due
                        // esiti) e dello stesso CashOutButton della riga: il
                        // numero della colonna e quello del bottone non possono
                        // differire. `lockedPnlAt` (ideale) li faceva divergere.
                        const closeNow = safeCloseNow(t, payload, commissionPct);
                        const locked = lockedPnlOf(t);
                        const rowPnl = pnlOf(t);
                        const fresh = isLive ? (freshnessOf?.(t.event_id) ?? null) : null;
                        const stale = staleReason(fresh);
                        const blocked = isLive ? marketBlocked(book) : null;
                        const kind = tradeOppKind(t);
                        const hold = isLive ? tradeHold(t) : null;
                        const runLine = isLive ? exitRunLine(t) : null;
                        // reperto 17/09 — STATO DI USCITA dall'ultima attività del
                        // servizio per QUESTO trade (exit_wait/exit_hold/feed_blind).
                        // Si mostra solo quando non è già detto da un altro indicatore
                        // della riga (il gate a modello scrive `meta.exit_hold` insieme
                        // al log: mostrarlo due volte con parole diverse confonderebbe
                        // più di quanto spieghi), cioè:
                        //   · 'wait' e 'proposal' → sempre (oggi invisibili altrove)
                        //   · 'blind-data' (dato mancante nel feed) → sempre (diverso
                        //     dal mercato assente, che ha già `blindSince`)
                        //   · 'hold' → solo se `meta.exit_hold` non è (ancora) scritto
                        //   · 'blind-market' → solo se `blindSince` non lo dice già
                        const blindAt = isLive ? blindSince(t) : null;
                        const exitAct = isLive && activity.length ? latestExitActivityFor(t.id, activity) : null;
                        const exitStatus = exitAct ? safeActivityExitStatus(exitAct) : null;
                        const showExitStatus = !!exitStatus && (
                            exitStatus.tone === 'wait'
                            || exitStatus.tone === 'proposal'
                            || exitStatus.tone === 'blind-data'
                            || (exitStatus.tone === 'hold' && !hold)
                            || (exitStatus.tone === 'blind-market' && !blindAt)
                        );
                        const pEntry = kind ? pLoseEntry(t) : null;
                        const orphanClosing = t.closes_trade_id != null;
                        const reason = safeReasonLabel(String((t.meta ?? {})['reason'] ?? '') || null);
                        const outcome = requestOutcome(lastRequestFor(t.id, requests));
                        // CHIUSURA-06 (12/09): esito della POSIZIONE (apertura +
                        // gambe di chiusura) scritto dal servizio in
                        // `meta.position_pnl` / `meta.position_result`. La
                        // colonna P&L porta il risultato della SOLA apertura: su
                        // un cash out in perdita diceva "+2,00 €" per una
                        // posizione chiusa a −10,27 €. Il servizio lo scriveva
                        // gia', nessuno lo leggeva.
                        const posInfo = positionInfo(t.meta ?? null);
                        const canCashOut = t.status === 'open'
                            || (t.status === 'hedged' && hedge != null && !hedge.complete);
                        // CERT. 13/09 — riga di una modalità DIVERSA da quella
                        // attiva sul servizio: resta visibile (nasconderla
                        // sarebbe peggio: sono soldi o posizioni vere) ma in
                        // tono attenuato e col badge, così non si confonde con
                        // ciò che si sta operando adesso.
                        const otherMode = currentMode != null && t.mode !== currentMode;
                        // reperto 17/09 — dopo la conferma `price` porta il MEDIO abbinato
                        // (non il chiesto travestito): stessa lettura di `statoOrdine`, usata
                        // qui solo per la colonna quota d'ingresso (il resto sta in StatoOrdineRiga).
                        const ordine = statoOrdine(t);
                        const entryQuota = fmtQuotaAbbinata(ordine.prezzoMedio.valore ?? t.price, ordine.prezzoChiesto.valore ?? t.price);
                        return (
                            <Fragment key={t.id}>
                            <tr
                                className={`border-t border-white/5 border-l-2 ${st.edge} hover:bg-white/5 ${otherMode ? 'opacity-60' : ''}`}
                                data-testid="safe-trade-row"
                                data-status={st.label}
                                data-mode={t.mode}
                                data-other-mode={otherMode ? '1' : undefined}
                                title={otherMode ? `riga in ${String(t.mode).toUpperCase()}: il servizio è in ${String(currentMode).toUpperCase()}` : undefined}
                            >
                                <td className="px-3 py-2 text-slate-400 tabular-nums">{fmtTime(t.placed_at)}</td>
                                <td className="px-3 py-2 max-w-[200px] truncate" title={t.event_name ?? t.event_id}>
                                    {t.origin === 'manual' && (
                                        <Badge variant="outline" className={`mr-1.5 px-1 py-0 text-[10px] ${CLS.cyan}`} title="piazzato manualmente">✋</Badge>
                                    )}
                                    {t.event_name ?? t.event_id}
                                    {realScore && (
                                        <span className="ml-1.5 text-[10px] text-slate-400 tabular-nums" data-testid="safe-real-score" title="risultato reale della partita dal feed">
                                            ({realScore})
                                        </span>
                                    )}
                                    {/* CERT. 13/09 — MINUTO E PUNTEGGIO D'INGRESSO: il servizio
                                        li registra su ogni riga e nessuno li mostrava. Senza,
                                        una posizione aperta al 12' sullo 0-0 e una aperta al
                                        78' sul 2-2 sono indistinguibili in tabella, e sono due
                                        scommesse completamente diverse. */}
                                    {(t.minute_at_entry != null || t.score_at_entry) && (
                                        <div
                                            className="mt-0.5 text-[10px] text-slate-500 tabular-nums"
                                            data-testid="safe-entry-context"
                                            title="minuto e punteggio nel momento in cui la posizione è stata aperta"
                                        >
                                            ingresso {t.minute_at_entry != null ? `${t.minute_at_entry}′` : DASH}
                                            {t.score_at_entry ? ` · ${t.score_at_entry}` : ''}
                                        </div>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-center text-[11px] font-heading font-bold text-slate-300">
                                    {kind ? (
                                        <Badge
                                            variant="outline"
                                            data-testid="trade-kind"
                                            data-kind={kind}
                                            className={`px-1.5 py-0 text-[10px] font-heading ${OPP_KIND_META[kind].badge}`}
                                            // REPERTO 17/09 sera — riga di opportunità di MODELLO
                                            // (secondo motore, es. auto_trade_tennis per il tennis):
                                            // MAI la Strategia S delle 4 varianti del manuale
                                            // (quella e' strategy='base'|'esatto'|'punta'|'tennis').
                                            // Il tooltip lo dice per non farle confondere in tabella.
                                            title={`trade di ${STRATEGY_LABEL.model.toLowerCase()} (secondo motore) · ${OPP_KIND_META[kind].title}`}
                                        >
                                            {OPP_KIND_META[kind].label}
                                        </Badge>
                                    ) : (STRATEGY_LABEL[t.strategy] ?? t.strategy)}
                                    {/* CERT. 13/09 — modalità della RIGA, sempre e su ogni riga:
                                        PAPER neutro, LIVE rosso. L'assenza di badge non deve
                                        mai poter significare "forse paper, forse non dichiarata". */}
                                    <ModeBadge
                                        mode={t.mode}
                                        compact
                                        className="ml-1 align-middle"
                                        testId="safe-trade-mode"
                                        dimmed={otherMode}
                                        title={otherMode ? `il servizio è in ${String(currentMode).toUpperCase()}` : undefined}
                                    />
                                    {pEntry != null && (
                                        <div className="mt-0.5 text-[10px] font-normal text-slate-500 tabular-nums" data-testid="trade-p-lose-entry" title="probabilità di perdita stimata all'ingresso">
                                            P(perdita) ingresso {fmtPct(pEntry)}
                                        </div>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-[11px] text-slate-400 max-w-[140px] truncate" data-testid="safe-market" title={[t.market_type, t.market_id ? `mercato ${t.market_id}` : null, t.selection_id != null ? `selezione ${t.selection_id}` : null].filter(Boolean).join(' · ')}>
                                    {/* mercato in CHIARO: "Risultato Esatto", non "CORRECT_SCORE" */}
                                    {safeMarketLabel(t.market_type) ?? DASH}
                                </td>
                                <td className="px-3 py-2 max-w-[160px] truncate" title={t.selection_name ?? ''}>
                                    {t.selection_name ?? DASH}
                                </td>
                                <td className="px-3 py-2 text-center">
                                    <Badge variant="outline" data-testid="safe-side" className={`px-1.5 py-0 text-[10px] font-heading font-bold ${sideBadgeClass(t.side === 'back' ? 'BACK' : 'LAY')}`}>
                                        {t.side.toUpperCase()}
                                    </Badge>
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums" data-testid="safe-price-entry" title={entryQuota.title ?? undefined}>
                                    {entryQuota.diverso ? `abbinato ${entryQuota.text}` : entryQuota.text}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums" data-testid="safe-price-now">
                                    {nowPrice != null ? (
                                        <span
                                            className={stale ? 'text-amber-300' : 'text-white/90'}
                                            title={`miglior ${closeSide === 'lay' ? 'lay' : 'back'} disponibile${book?.marketId ? ` · mercato ${book.marketId}` : ''}${book?.source ? ` (feed: ${book.source})` : ''}`}
                                        >
                                            {fmtOdds(nowPrice)}
                                        </span>
                                    ) : book && !blocked && book[closeSide === 'lay' ? 'lay' : 'back'] == null ? (
                                        // reperto 17/09 — libro presente ma il lato con cui SI
                                        // CHIUDE è assente (capita per pochi secondi fra un punto
                                        // e l'altro): un trattino muto sembrava un guasto della
                                        // pagina, non una condizione del mercato reale.
                                        <span className="text-amber-300 text-[11px]" data-testid="safe-price-missing" title={`${closeSide === 'lay' ? 'lay' : 'back'} assente nel feed per questa selezione: nessuna uscita automatica possibile finché non torna`}>
                                            quota momentaneamente assente
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
                                            className={pnlClassSoft(closeNow)}
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
                                                // 'model' | 'market' | 'none' dal servizio: in chiaro
                                                hold.source ? `stima da: ${HOLD_SOURCE_IT[hold.source] ?? hold.source}` : null,
                                                hold.evHold != null ? `EV tenere: ${fmtMoney(hold.evHold, { signed: true })}` : null,
                                                hold.locked != null ? `bloccabile ora: ${fmtMoney(hold.locked, { signed: true })}` : null,
                                                hold.ts ? `aggiornato ${fmtTime(hold.ts)}` : null,
                                            ].filter(Boolean).join(' · ')}
                                        >
                                            In attesa: {holdReasonLabel(hold.reason)}
                                            {hold.pLose != null && !holdReasonHasP(hold.reason) ? `, P(perdita) ${fmtPct(hold.pLose)}` : ''}
                                        </div>
                                    )}
                                    {/* reperto 17/09 — stato di uscita dall'ultima attività
                                        del servizio: spiega le attese che oggi non dicevano
                                        niente al trader (prezzo assente dal book, mercato
                                        sospeso, feed cieco su dati diversi dal mercato,
                                        proposta di chiusura in attesa di firma). */}
                                    {showExitStatus && exitStatus && (
                                        <div
                                            className={`mt-0.5 text-[10px] whitespace-nowrap ${
                                                exitStatus.tone === 'proposal' ? 'text-fuchsia-300'
                                                    : exitStatus.tone === 'hold' ? 'text-sky-300/90'
                                                        : exitStatus.tone.startsWith('blind') ? 'text-red-300'
                                                            : 'text-amber-300'
                                            }`}
                                            data-testid="safe-exit-status"
                                            data-tone={exitStatus.tone}
                                            title={exitStatus.tooltip}
                                        >
                                            {exitStatus.text}
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
                                {/* CERT. 13/09 — il P&L della riga passa da `pnlClass()`:
                                    UNA regola di colore per le tre sezioni, e la perdita
                                    è ROSSA e in GRASSETTO come l'utile, mai in grigio.
                                    Il valore mostrato è `null` (→ «—») finché non c'è un
                                    risultato: uno «0,00 €» direbbe «chiuso in pari». */}
                                <td className={`px-3 py-2 text-right tabular-nums ${pnlClass(hedged ? (locked ?? rowPnl) : settled ? rowPnl : null)}`}>
                                    {hedged ? (
                                        <span data-testid="safe-locked-pnl" title={hedgeTooltip(t, closing)}>
                                            {fmtMoney(locked ?? rowPnl, { signed: true })} <span className="font-normal text-[10px] text-teal-300">bloccato</span>
                                        </span>
                                    ) : settled ? (
                                        <span title={`al netto della commissione del trade (${fmtPct(commission > 1 ? commission / 100 : commission)})`}>
                                            {fmtMoney(rowPnl, { signed: true })}
                                        </span>
                                    ) : DASH}
                                    {closes.length > 0 && posInfo?.pnl != null && (
                                        <div
                                            className={`mt-0.5 whitespace-nowrap text-[10px] ${pnlClassSoft(posInfo.pnl)}`}
                                            data-testid="safe-position-result"
                                            title="risultato della POSIZIONE (apertura + gambe di chiusura): il numero sopra è la sola gamba d'apertura"
                                        >
                                            posizione {posInfo.result === 'won' ? 'in utile' : posInfo.result === 'lost' ? 'in perdita' : 'in pari'}{' '}
                                            <b>{fmtMoney(posInfo.pnl, { signed: true })}</b>
                                        </div>
                                    )}
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
                            {/* C.12b (16/09) — LO STATO DELL'ORDINE, sotto la riga.
                                Prima Safe mostrava UN solo `size` (che dopo la
                                conferma e' l'ABBINATO) e nessun prezzo medio: alla
                                domanda «abbinato tutto o in parte?» la tabella non
                                sapeva rispondere. Qui ci sono chiesto, abbinato col
                                prezzo medio, residuo vivo sul book e da quanto non
                                arrivano notizie da Betfair. */}
                            <tr
                                className={`border-l-2 ${st.edge} ${otherMode ? 'opacity-60' : ''}`}
                                data-testid="safe-stato-ordine-row"
                                data-trade={t.id}
                            >
                                <td className="px-3 pb-2" />
                                <td colSpan={COLS - 1} className="px-3 pb-2">
                                    <StatoOrdineRiga riga={t} nowMs={now} testId="safe-stato-ordine" />
                                </td>
                            </tr>
                            {closes.map((c, ci) => {
                                const cb = statusMeta(c.status);
                                // "parziale": dalla chiusura (size_capped_from) o dall'apertura (residuo > 0)
                                const capped = cappedFrom(c) ?? (partial && ci === closes.length - 1 ? partial.hedged + partial.residual : null);
                                return (
                                    <tr key={c.id} className={`bg-white/[0.03] border-t border-dashed border-white/5 ${otherMode ? 'opacity-60' : ''}`} data-testid="safe-closing-row" data-closes={t.id} data-mode={c.mode}>
                                        <td className="px-3 py-1 text-slate-500 tabular-nums text-[11px]">{fmtTime(c.placed_at)}</td>
                                        <td colSpan={12} className="pl-8 pr-3 py-1 text-[11px] text-slate-300" title={hedgeTooltip(t, c)}>
                                            <span className="text-teal-300" aria-hidden>↳ </span>
                                            <b className="text-teal-200">{isGreenup ? T.greenUp : (exit?.kind === 'manual' || isManualCashout) ? T.cashOut : 'Chiusura'} di #{t.id}</b>
                                            {' · '}
                                            <Badge variant="outline" className={`px-1 py-0 text-[10px] font-heading font-bold mr-1 ${sideBadgeClass(c.side === 'back' ? 'BACK' : 'LAY')}`}>{c.side.toUpperCase()}</Badge>{' '}
                                            <span className="tabular-nums">{fmtMoney(c.size)} @{fmtOdds(c.price)}</span>
                                            {/* C.12b — anche una gamba di CHIUSURA e' un ordine:
                                                chiesto/abbinato/residuo, in forma compatta. */}
                                            <StatoOrdineCompatto riga={c} className="ml-1.5" testId="safe-chiusura-stato-ordine" />
                                            {/* anche la gamba di chiusura dichiara la sua modalità:
                                                è un ordine a sé, con soldi veri o simulati */}
                                            <ModeBadge mode={c.mode} compact className="ml-1 align-middle" testId="safe-closing-mode" dimmed={otherMode} />
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
                                        {/* CERT. 13/09 — QUESTA cella era il difetto denunciato
                                            dall'utente: «le loss sono in nero e in piccolo».
                                            Il P&L della gamba di chiusura (che su un cash out
                                            in perdita è il numero che conta) usciva in
                                            `text-slate-500` a 11px, cioè grigio e più piccolo
                                            dell'utile della riga sopra. Ora passa da
                                            `pnlClass()` come ogni altro P&L della pagina. */}
                                        <td className={`px-3 py-1 text-right text-xs tabular-nums ${pnlClass(['won', 'lost', 'void', 'hedged'].includes(c.status) ? pnlOf(c) : null)}`}>
                                            {['won', 'lost', 'void', 'hedged'].includes(c.status) ? fmtMoney(pnlOf(c), { signed: true }) : DASH}
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
