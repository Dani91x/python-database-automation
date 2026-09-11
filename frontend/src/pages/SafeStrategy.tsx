// ============================================================================
// SafeStrategy.tsx — sezione SAFE STRATEGY: radar + BOT operativo.
//
// Il radar (scanner autonomo backend) monitora TUTTI gli eventi calcio+tennis
// in-play e produce i segnali delle 4 strategie; da qui si può anche OPERARE:
//   · investire su un segnale o su un'opportunità di modello (coda 'place');
//   · seguire i trade in tabella realtime, con CASH OUT live su ogni posizione;
//   · avviare/fermare il bot in PAPER o LIVE (soldi veri dietro conferma).
//
// Regole di lettura del layout (molti segnali insieme = deve restare leggibile):
//   header sticky con stato · KPI · sport (Calcio/Tennis) · sezione
//   (Segnali / Opportunità / Monitor / Trade) · card più recenti in alto.
//
// FONTE UNICA dei dati live: il feed dello scanner già montato dal
// SafeStrategyProvider — nessun canale realtime duplicato, nessuna chiamata
// Betfair dal frontend. I parametri veri sono quelli del bot sul DB quando la
// riga di controllo esiste; altrimenti valgono quelli locali del radar.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
    Activity, ShieldAlert, TrendingUp, Signal as SignalIcon, Layers, ScrollText,
} from 'lucide-react';
import { useSafeStrategy, type FootballMonitor, type TennisMonitor } from '@/components/safestrategy/SafeStrategyProvider';
import { SignalCard } from '@/components/safestrategy/SignalCard';
import { MonitorCard } from '@/components/safestrategy/MonitorCard';
import { ParamsSheet } from '@/components/safestrategy/ParamsSheet';
import { BotParamsSheet, type ParamCorrections } from '@/components/safestrategy/BotParamsSheet';
import { OpportunityGroup, filterOpps, OPP_KIND_META, type OppKindFilter } from '@/components/safestrategy/OpportunityGroup';
import { RiskPanel } from '@/components/safestrategy/RiskPanel';
import { SafeTradesTable } from '@/components/safestrategy/SafeTradesTable';
import { useSafeBot } from '@/components/safestrategy/useSafeBot';
import { VARIANT_STYLE } from '@/components/safestrategy/variantStyles';
import { TradingHistory } from '@/components/trading/TradingHistory';
import { PageShell } from '@/components/trading/PageShell';
import { BotHeader } from '@/components/trading/BotHeader';
import { ServiceHealthChip } from '@/components/trading/ServiceHealthChip';
import { ModeToggle } from '@/components/trading/ModeToggle';
import { ModeBanner } from '@/components/trading/ModeBanner';
import { LiveConfirmDialog } from '@/components/trading/LiveConfirmDialog';
import { StatTile, KpiRow, toneOf } from '@/components/trading/StatTile';
import { DayBar } from '@/components/trading/DayBar';
import { EmptyState, SectionCard } from '@/components/trading/EmptyState';
import { EquityCard } from '@/components/trading/EquityCard';
import { ActivityFeed, type ActivityRow } from '@/components/trading/ActivityFeed';
import { safeActivityLine, safeActivityMeta } from '@/components/safestrategy/safeActivity';
import { fmtMoney } from '@/lib/format';
import { T } from '@/lib/tradeStatus';
import { toastSettlement } from '@/lib/toasts';
import { fetchSafeDaily, fetchSafeDayTrades, romeDay, dayLabel, type SafeSportFilter } from '@/lib/dailyHistory';
// stesse funzioni PURE (testate) della scheda Omega: gruppo per evento, P&L per
// posizione (apertura + chiusure), filtro GIORNATA operativa (Europe/Rome)
import { groupTradesByMatch, filterMatchesForDay, summarizeMatches } from '@/lib/omegaMatches';
import {
    buildEquitySeries, resolveSignalPlacement, safeTradeBook, feedFreshness,
    sameStrategyParams, strategyParamsOf, SCANNER_STALE_MS, groupClosingLegs, isCurrentOppRow,
    oppKind, oppKindCounts, comboLegStakes, comboIdempotencyPrefix, SAFE_OPP_KINDS,
    hedgeState, isLivePosition, isReconciling, positionOutcome, aggregatesHaveDay,
    type FeedFreshness, type SafeBotStatus, type SafeMode, type SafeOpportunity, type SafeOpportunityRow,
    type SafeSport, type SafeTrade, type SignalPlacement,
} from '@/lib/safeBot';
import type { ActiveSignal, Sport } from '@/lib/safeStrategy';
import type { CalcioScanPayload, ScanMediaFlags, TennisScanPayload } from '@/lib/safeStrategyScan';

function footballLiveLine(m: FootballMonitor): string {
    const { minute, scoreHome, scoreAway, inplay } = m.ctx;
    const min = minute !== null ? `${minute}′` : '—′';
    const score = scoreHome !== null && scoreAway !== null ? `${scoreHome}-${scoreAway}` : '?-?';
    const comp = m.payload.competition ? ` · ${m.payload.competition}` : '';
    return inplay ? `${min} · ${score}${comp}` : `pre-KO${comp}`;
}

function tennisLiveLine(m: TennisMonitor): string {
    const sets = m.ctx.sets ? `set ${m.ctx.sets.p1}-${m.ctx.sets.p2}` : 'set —';
    const games = m.ctx.games ? ` · game ${m.ctx.games.p1}-${m.ctx.games.p2}` : '';
    const comp = m.payload.competition ? ` · ${m.payload.competition}` : '';
    return m.ctx.inplay ? `${sets}${games}${comp}` : `pre-match${comp}`;
}

// =============================================================== main page
export default function SafeStrategy() {
    const { football, tennis, signals, scanStatus, params: localParams, saveParams } = useSafeStrategy();
    const bot = useSafeBot({ onError: (m) => toast.error('Bot Safe Strategy', { description: m }) });

    const [nowMs, setNowMs] = useState(() => Date.now());
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
    // tab Trade: di default SOLO la giornata operativa (+ posizioni vive di giorni
    // precedenti); "mostra tutte" = tutto il caricato (lo storico completo e' nel tab Storico)
    const [showAllTrades, setShowAllTrades] = useState(false);
    const [oppMinConfidence, setOppMinConfidence] = useState(0);
    const [oppSide, setOppSide] = useState<'all' | 'back' | 'lay'>('all');
    const [oppKindFilter, setOppKindFilter] = useState<OppKindFilter>('all');
    const notifiedRef = useRef<Set<number>>(new Set());
    // altezza REALE dell'header sticky (misurata da BotHeader): offset della TabsList
    const [navH, setNavH] = useState(52);
    // tab controllati: dallo Storico si torna al tab Trade dello sport giusto
    const [topTab, setTopTab] = useState<string>('calcio');
    const [calcioTab, setCalcioTab] = useState<string>('segnali');
    const [tennisTab, setTennisTab] = useState<string>('segnali');
    // filtro sport dello storico (null = tutti)
    const [historySport, setHistorySport] = useState<SafeSportFilter>(null);
    const fetchHistoryDaily = useCallback(
        (from: string, to: string) => fetchSafeDaily(from, to, historySport),
        [historySport],
    );
    const fetchHistoryDay = useCallback(
        (day: string) => fetchSafeDayTrades(day, historySport),
        [historySport],
    );
    // C-01: UNA sola giornata operativa, quella dichiarata dal DB (giorno di
    // PIAZZAMENTO, Europe/Rome). Senza la migrazione v2 si ricade su romeDay().
    const operatingDay = bot.operatingDay ?? romeDay();

    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 10_000);
        return () => window.clearInterval(t);
    }, []);

    // ---- parametri: quando il bot esiste, le SUE condizioni sono la fonte unica
    // e vengono riflesse anche sul radar client-side (che valuta i segnali).
    // Confronto NORMALIZZATO su entrambi i lati (mergeParams): un payload server
    // con chiavi in piu'/null non deve mai coincidere "quasi" e salvare a ogni
    // render (loop). Si salva solo se le condizioni normalizzate differiscono.
    const botStrategyParams = useMemo(() => strategyParamsOf(bot.params), [bot.params]);
    const lastSyncedRef = useRef<string | null>(null);
    useEffect(() => {
        if (!bot.available) return;
        if (sameStrategyParams(botStrategyParams, localParams)) return;
        const key = JSON.stringify(botStrategyParams);
        if (lastSyncedRef.current === key) return;
        lastSyncedRef.current = key;
        saveParams(botStrategyParams);
    }, [bot.available, botStrategyParams, localParams, saveParams]);

    // ---- toast di settlement: UNO per POSIZIONE (audit M-04)
    // `freshSettlements` porta solo le APERTURE; il P&L e l'esito sono quelli
    // della POSIZIONE (apertura + chiusure), non della singola gamba: prima
    // l'apertura di un green-up in utile appariva "PERSO" con un secondo toast.
    const closesByParent = useMemo(() => {
        const out = new Map<number, SafeTrade[]>();
        for (const t of bot.trades) {
            if (t.closes_trade_id == null) continue;
            const list = out.get(t.closes_trade_id) ?? [];
            list.push(t);
            out.set(t.closes_trade_id, list);
        }
        return out;
    }, [bot.trades]);
    const closesRef = useRef(closesByParent);
    closesRef.current = closesByParent;
    useEffect(() => {
        for (const t of bot.freshSettlements) {
            if (notifiedRef.current.has(t.id)) continue;
            notifiedRef.current.add(t.id);
            const legs = closesRef.current.get(t.id) ?? [];
            const outcome = positionOutcome(t);
            const total = outcome?.pnl
                ?? legs.reduce((sum, c) => sum + (Number(c.pnl) || 0), Number(t.pnl) || 0);
            const manual = t.origin === 'manual'
                || legs.some((c) => c.origin === 'manual' || (c.meta ?? {})['cashout'] === true);
            const label = outcome?.result === 'void' || t.status === 'void' ? 'VOID'
                : outcome?.result === 'flat' ? 'PARI'
                    : total >= 0 ? 'VINTO' : 'PERSO';
            // formato UNICO delle notifiche di regolazione (lib/toasts.ts)
            toastSettlement({
                name: t.event_name ?? t.event_id,
                pnl: Number(total),
                side: t.side,
                selection: t.selection_name,
                manual,
                statusLabel: label,
            });
        }
    }, [bot.freshSettlements]);

    // ---- esito di OGNI richiesta operativa, anche i rifiuti (audit L-07/M-21)
    const outcomeSeen = useRef<Set<number>>(new Set());
    useEffect(() => {
        for (const { request, outcome } of bot.freshOutcomes) {
            if (outcomeSeen.current.has(request.id)) continue;
            outcomeSeen.current.add(request.id);
            const what = request.kind === 'cashout' ? T.cashOut
                : request.kind === 'cancel' ? 'Annullo' : 'Ordine';
            const msg = outcome.message ?? undefined;
            if (outcome.tone === 'ok') toast.success(`${what}: eseguito`, { description: msg });
            else if (outcome.tone === 'rejected') toast.warning(`${what}: rifiutato dal servizio`, { description: msg });
            else toast.error(`${what}: errore`, { description: msg });
        }
    }, [bot.freshOutcomes]);

    // ---- indici
    const payloadByEvent = useMemo(() => {
        const out: Record<string, CalcioScanPayload | TennisScanPayload> = {};
        for (const m of football) out[m.eventId] = m.payload;
        for (const m of tennis) out[m.eventId] = m.payload;
        return out;
    }, [football, tennis]);

    // feed live dei trade (calcio E tennis): stesso payload del radar, ZERO
    // canali aggiuntivi. updated_at per evento → freschezza delle quote.
    const updatedAtByEvent = useMemo(() => {
        const out: Record<string, string | null> = {};
        for (const m of football) out[m.eventId] = m.updatedAt ?? null;
        for (const m of tennis) out[m.eventId] = m.updatedAt ?? null;
        return out;
    }, [football, tennis]);
    const scannerUpdatedAt = scanStatus?.updated_at ?? null;
    const freshnessOf = useMemo(
        () => (eventId: string): FeedFreshness | null =>
            eventId in updatedAtByEvent ? feedFreshness(updatedAtByEvent[eventId], scannerUpdatedAt, nowMs) : null,
        [updatedAtByEvent, scannerUpdatedAt, nowMs],
    );

    const tradeBySignal = useMemo(() => {
        const out: Record<string, SafeTrade> = {};
        for (const t of bot.trades) {
            // AUTO: signal_key in colonna. MANUALE da SignalCard: il servizio non salva
            // signal_key ma dedupa e conserva meta.idempotency_key = "sig:<chiave>"
            // (review 11/09 H1: prima la card perdeva il trade e un secondo click
            // creava un secondo trade)
            const idem = String((t.meta ?? {})['idempotency_key'] ?? '');
            const key = t.signal_key ?? (idem.startsWith('sig:') ? idem.slice(4) : null);
            if (!key) continue;
            const prev = out[key];
            if (!prev || t.id > prev.id) out[key] = t;
        }
        return out;
    }, [bot.trades]);

    /** minuto/punteggio correnti di un evento dal feed (contesto d'ingresso dei manuali, L1) */
    function entryContext(eventId: string): { minute?: number | null; score?: string | null } {
        const p = payloadByEvent[eventId];
        if (!p || 'sets' in p) return {};
        const c = p as CalcioScanPayload;
        const score = c.score_home != null && c.score_away != null ? `${c.score_home}-${c.score_away}` : null;
        return { minute: c.minute ?? null, score };
    }

    const mediaByEvent = useMemo<Record<string, ScanMediaFlags | null | undefined>>(() => {
        const out: Record<string, ScanMediaFlags | null | undefined> = {};
        for (const m of football) out[m.eventId] = m.payload.media;
        for (const m of tennis) out[m.eventId] = m.payload.media;
        return out;
    }, [football, tennis]);

    const bySport = useMemo(() => {
        const pick = (sport: Sport, status: ActiveSignal['status']) =>
            signals.filter((s) => s.sport === sport && s.status === status);
        return {
            calcioActive: pick('calcio', 'active'),
            calcioExpired: pick('calcio', 'expired'),
            tennisActive: pick('tennis', 'active'),
            tennisExpired: pick('tennis', 'expired'),
        };
    }, [signals]);

    const fbSorted = useMemo(
        () => [...football].sort((a, b) => {
            if (a.ctx.inplay !== b.ctx.inplay) return a.ctx.inplay ? -1 : 1;
            return (a.payload.open_date ?? '').localeCompare(b.payload.open_date ?? '');
        }),
        [football],
    );
    const tnSorted = useMemo(
        () => [...tennis].sort((a, b) => {
            if (a.ctx.inplay !== b.ctx.inplay) return a.ctx.inplay ? -1 : 1;
            return (a.payload.open_date ?? '').localeCompare(b.payload.open_date ?? '');
        }),
        [tennis],
    );

    const calcioTrades = useMemo(() => bot.trades.filter((t) => t.sport === 'calcio'), [bot.trades]);
    const tennisTrades = useMemo(() => bot.trades.filter((t) => t.sport === 'tennis'), [bot.trades]);
    // GIORNATA OPERATIVA (come Omega): posizioni piazzate oggi (Europe/Rome) + vive di
    // giorni precedenti; gli eventi con almeno una di queste restano visibili per intero
    const tradeGroups = useMemo(() => groupTradesByMatch(bot.trades), [bot.trades]);
    const todayGroups = useMemo(() => filterMatchesForDay(tradeGroups, operatingDay), [tradeGroups, operatingDay]);
    const todayEventIds = useMemo(() => new Set(todayGroups.map((g) => g.event_id)), [todayGroups]);
    const todayTradesCalcio = useMemo(() => calcioTrades.filter((t) => todayEventIds.has(t.event_id)), [calcioTrades, todayEventIds]);
    const todayTradesTennis = useMemo(() => tennisTrades.filter((t) => todayEventIds.has(t.event_id)), [tennisTrades, todayEventIds]);
    const todaySummaryCalcio = useMemo(() => summarizeMatches(todayGroups.filter((g) => g.legs[0]?.trade.sport === 'calcio')), [todayGroups]);
    const todaySummaryTennis = useMemo(() => summarizeMatches(todayGroups.filter((g) => g.legs[0]?.trade.sport === 'tennis')), [todayGroups]);
    // SOLO le opportunità di OGGI e recenti (partite in corso): il servizio non
    // cancella le righe delle partite finite in tempo reale e i giorni passati stanno
    // nello Storico. Poi per sport: 'calcio' (default per righe senza sport) e 'tennis'
    const currentOpps = useMemo(
        () => bot.opportunities.filter((r) => isCurrentOppRow(r, nowMs, operatingDay)),
        [bot.opportunities, nowMs, operatingDay],
    );
    const oppRows = useMemo(() => currentOpps.filter((r) => r.sport !== 'tennis'), [currentOpps]);
    const tennisOppRows = useMemo(() => currentOpps.filter((r) => r.sport === 'tennis'), [currentOpps]);
    const oppCountsAll = useMemo(() => oppKindCounts(currentOpps), [currentOpps]);
    // M-21: i tab contano le OPPORTUNITÀ, come il pannello Rischio (prima i tab
    // contavano gli eventi e i due numeri non coincidevano mai)
    const countOpps = (rows: SafeOpportunityRow[]) =>
        rows.reduce((n, r) => n + (Array.isArray(r.payload?.opps) ? r.payload.opps.length : 0), 0);
    const oppCountCalcio = useMemo(() => countOpps(oppRows), [oppRows]);
    const oppCountTennis = useMemo(() => countOpps(tennisOppRows), [tennisOppRows]);

    const stats = bot.control?.stats ?? {};
    const agg = bot.aggregates;
    // M-15 / L-04: "aperti" = POSIZIONI VIVE (le chiusure non contano, le
    // `hedged` complete nemmeno, quelle coperte in parte sì). Fonte unica:
    // `aggregates.open_count`; il calcolo locale è solo il fallback.
    const livePositions = useMemo(() => bot.trades.filter(isLivePosition), [bot.trades]);
    const reconcilingTrades = useMemo(
        () => bot.trades.filter((t) => t.closes_trade_id == null && isReconciling(t)),
        [bot.trades],
    );
    const partiallyHedged = useMemo(
        () => bot.trades.filter((t) => {
            if (t.closes_trade_id != null) return false;
            const h = hedgeState(t);
            return h != null && !h.complete;
        }),
        [bot.trades],
    );
    const visibleOppRows = useMemo(
        () => oppRows.filter((r) => filterOpps(r, oppMinConfidence, oppSide, oppKindFilter).length > 0),
        [oppRows, oppMinConfidence, oppSide, oppKindFilter],
    );
    const visibleTennisOppRows = useMemo(
        () => tennisOppRows.filter((r) => filterOpps(r, oppMinConfidence, oppSide, oppKindFilter).length > 0),
        [tennisOppRows, oppMinConfidence, oppSide, oppKindFilter],
    );
    const realizedToday = Number(agg?.realized_today ?? stats.realized_today ?? 0);
    const realizedTotal = Number(agg?.realized_total ?? stats.realized_total ?? 0);
    const openLiability = Number(agg?.open_liability ?? stats.open_liability ?? 0);
    const reconcilingLiability = Number(
        agg?.reconciling_liability ?? stats.reconciling_liability ?? stats.risk?.reconciling_liability ?? 0,
    );
    const openCount = agg?.open_count ?? livePositions.length;
    const dayLiability = Number(agg?.day_liability ?? stats.risk?.daily_liability ?? openLiability);
    const totalActive = bySport.calcioActive.length + bySport.tennisActive.length;
    // V/P e operazioni della GIORNATA: gli stessi numeri del pannello Rischio,
    // del tab Trade e dello Storico (C-01)
    const positionsToday = groupClosingLegs([...todayTradesCalcio, ...todayTradesTennis]).length;
    const wonToday = agg?.won_today ?? (todaySummaryCalcio.won + todaySummaryTennis.won);
    const lostToday = agg?.lost_today ?? (todaySummaryCalcio.lost + todaySummaryTennis.lost);
    const legsToday = agg?.legs_today ?? positionsToday;
    const eventsToday = agg?.events_today ?? todayEventIds.size;
    // Senza safe_strategy_bot_v2.sql la RPC non torna i contatori di giornata:
    // i numeri sopra sono STIMATI dal client sulle righe caricate. Va dichiarato
    // (prima la barra prometteva "gli stessi numeri dello Storico": falso).
    const dayFromUi = !aggregatesHaveDay(agg);
    const MIGRAZIONE_NOTA = 'stimato dal client (applica safe_strategy_bot_v2.sql)';
    const lockedToday = todaySummaryCalcio.pnl_locked != null || todaySummaryTennis.pnl_locked != null
        ? Number(todaySummaryCalcio.pnl_locked ?? 0) + Number(todaySummaryTennis.pnl_locked ?? 0)
        : null;
    // size minima Betfair realmente in uso dal servizio (H-15)
    const minStake = Number(bot.paramsEffective?.min_stake ?? 2);
    // righe di attività del servizio, pronte per ActivityFeed (H-16)
    const activityRows = useMemo<ActivityRow[]>(
        () => bot.activity.map((a) => ({
            id: a.id,
            ts: a.ts,
            kind: a.kind,
            event_name: (a.payload ?? {})['event_name'] as string | undefined ?? null,
            payload: a.payload,
        })),
        [bot.activity],
    );
    const criticalActivity = useMemo(
        () => activityRows.filter((r) => safeActivityMeta(String(r.kind)).critical).length,
        [activityRows],
    );
    // H-15: il servizio NON riallinea il DB, ma dichiara le correzioni
    // nell'attività `params_clamped` ({chiave: {stored, effective}}) e le chiavi
    // che ha davvero corretto sul DB in `params_invalid.persisted`.
    const paramCorrections = useMemo<ParamCorrections | null>(() => {
        const row = bot.activity.find((a) => a.kind === 'params_clamped');
        const c = (row?.payload ?? {})['corrections'];
        return c && typeof c === 'object' ? (c as ParamCorrections) : null;
    }, [bot.activity]);
    const paramPersisted = useMemo<string[] | null>(() => {
        const row = bot.activity.find((a) => a.kind === 'params_invalid');
        const p = (row?.payload ?? {})['persisted'];
        return Array.isArray(p) ? p.map(String) : null;
    }, [bot.activity]);
    const status: SafeBotStatus = bot.control?.status ?? 'idle';
    const running = status === 'running' || status === 'stopping';
    const mode: SafeMode = bot.mode;

    // ---- azioni
    function onToggleMode(next: SafeMode) {
        if (next === 'live') setLiveConfirmOpen(true);
        else void bot.setMode('paper');
    }
    async function applyLive() {
        await bot.setMode('live');
        setLiveConfirmOpen(false);
        toast.error('🔴 MODALITÀ LIVE — soldi veri');
    }
    /** LIVE ereditato dal control (altra sessione/tab) ma MAI confermato qui:
     *  nessun ordine con soldi veri finche' l'utente non passa dal dialog. */
    function liveNotConfirmed(): boolean {
        if (mode !== 'live' || bot.liveConfirmed) return false;
        setLiveConfirmOpen(true);
        toast.warning('Conferma la modalità LIVE prima di operare con soldi veri');
        return true;
    }

    async function placeFromSignal(signal: ActiveSignal, placement: SignalPlacement, size: number) {
        if (liveNotConfirmed()) return null;
        const id = await bot.place({
            event_id: signal.eventId,
            event_name: signal.matchLabel,
            sport: signal.sport,
            // il servizio NON deduce la modalita dal control: va dichiarata
            // esplicitamente o l'ordine finirebbe in paper anche a bot LIVE.
            mode,
            market_id: placement.market_id,
            market_type: placement.market_type,
            selection_id: placement.selection_id,
            selection_name: placement.selection_name,
            side: signal.side === 'LAY' ? 'lay' : 'back',
            price: placement.price ?? signal.entryOdds,
            size,
            strategy: signal.variant,
            signal_key: signal.key,
            // un solo trade per segnale anche dopo remount/doppio click (dedupe del servizio)
            idempotency_key: `sig:${signal.key}`,
            ...entryContext(signal.eventId),
        });
        if (id != null) toast.success('Ordine in coda', { description: `${signal.matchLabel} · ${fmtMoney(size)}` });
        return id;
    }

    /** Opportunità → coda 'place'. Modello / anomalia / tennis: una richiesta.
     *  COMBINAZIONE: una richiesta PER GAMBA (stake scalato allo stake totale
     *  scelto) con lo stesso prefisso di idempotenza e la stessa modalità, così
     *  il servizio le riconosce come un'unica operazione. */
    async function placeFromOpportunity(
        eventId: string, eventName: string | null, sport: SafeSport, o: SafeOpportunity, size: number,
    ) {
        if (liveNotConfirmed()) return null;
        const kind = oppKind(o);
        if (kind === 'combo') {
            const legs = comboLegStakes(o, size);
            if (legs.length === 0) { toast.error('Combinazione senza gambe'); return null; }
            const prefix = comboIdempotencyPrefix(eventId, o);
            let first: number | null = null;
            for (let i = 0; i < legs.length; i++) {
                const leg = legs[i];
                const id = await bot.place({
                    event_id: eventId,
                    event_name: eventName,
                    sport,
                    mode,
                    market_id: leg.market_id,
                    market_type: leg.market_type,
                    selection_id: leg.selection_id,
                    selection_name: leg.selection_name,
                    side: leg.side,
                    price: leg.price,
                    size: leg.stake,
                    strategy: 'model',
                    kind: 'combo',
                    combo: o.combo ?? null,
                    idempotency_key: `${prefix}:${i + 1}/${legs.length}`,
                    combo_leg: i + 1,
                    combo_legs: legs.length,
                    combo_total_stake: size,
                });
                if (id == null) {
                    toast.error('Combinazione interrotta', { description: `gamba ${i + 1}/${legs.length} non accodata — controlla i trade` });
                    return first;
                }
                if (first == null) first = id;
            }
            toast.success('Combinazione in coda', { description: `${eventName ?? eventId} · ${legs.length} gambe · ${fmtMoney(size)} totali` });
            return first;
        }
        const id = await bot.place({
            event_id: eventId,
            event_name: eventName,
            sport,
            mode,
            market_id: o.market_id,
            market_type: o.market_type,
            selection_id: o.selection_id,
            selection_name: o.selection_name,
            side: o.side,
            price: o.price,
            size,
            strategy: 'model',
            kind,
            ...(kind === 'anomaly' ? { rule: o.rule ?? null } : {}),
            // stessa opportunità (mercato, selezione, lato) = un solo trade
            idempotency_key: `opp:${eventId}:${o.market_id}:${o.selection_id}:${o.side}`,
            ...entryContext(eventId),
        });
        if (id != null) toast.success('Ordine in coda', { description: `${eventName ?? eventId} · ${fmtMoney(size)}` });
        return id;
    }

    /** Annulla una RISERVA non ancora abbinata (kind 'cancel'). Il servizio può
     *  RIFIUTARE ("in riconciliazione", "ordine gia' a mercato", "non
     *  annullabile: stato X"): l'esito arriva dal toast delle richieste. */
    async function cancelReserve(trade: SafeTrade) {
        if (trade.mode === 'live' && !bot.liveConfirmed) {
            setLiveConfirmOpen(true);
            toast.warning('Conferma la modalità LIVE prima di annullare un ordine reale');
            return;
        }
        const id = await bot.cancel(trade.id);
        if (id != null) toast.success('Annullo in coda', { description: trade.event_name ?? trade.event_id });
    }

    async function cashOut(trade: SafeTrade, args: { amount?: number; fraction?: number }) {
        // la chiusura usa la modalita' del TRADE: un trade live va confermato
        if (trade.mode === 'live' && !bot.liveConfirmed) {
            setLiveConfirmOpen(true);
            toast.warning('Conferma la modalità LIVE prima di chiudere una posizione con soldi veri');
            return;
        }
        if (bot.isCashOutPending(trade.id)) return;
        const id = await bot.cashout(trade.id, args);
        if (id != null) toast.success('Cash out in coda', { description: trade.event_name ?? trade.event_id });
    }

    function renderSignals(list: ActiveSignal[]) {
        if (list.length === 0) {
            return <EmptyState>Nessun segnale attivo in questo momento: il radar continua a osservare.</EmptyState>;
        }
        return (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {list.map((s) => {
                    const placement = resolveSignalPlacement(s, payloadByEvent[s.eventId]);
                    const trade = tradeBySignal[s.key] ?? null;
                    return (
                        <SignalCard
                            key={s.key}
                            signal={s}
                            nowMs={nowMs}
                            media={mediaByEvent[s.eventId]}
                            placement={placement}
                            mode={mode}
                            stake={s.side === 'LAY' ? bot.params.stake.laySize : bot.params.stake.backSize}
                            requests={bot.requests}
                            trade={trade}
                            tradeBook={trade ? safeTradeBook(trade, payloadByEvent[trade.event_id]) : null}
                            commissionPct={bot.paramsEffective?.commission_pct ?? bot.params.commission_pct}
                            minStake={minStake}
                            cashOutPending={trade ? bot.isCashOutPending(trade.id) : false}
                            freshness={freshnessOf(s.eventId)}
                            onPlace={(p, size) => placeFromSignal(s, p, size)}
                            onCashOut={cashOut}
                        />
                    );
                })}
            </div>
        );
    }

    /** filtri + card delle opportunità di uno sport (stessi filtri per calcio e tennis) */
    function renderOpportunities(rows: SafeOpportunityRow[], visible: SafeOpportunityRow[], sport: SafeSport) {
        const counts = oppKindCounts(rows);
        const total = rows.reduce((n, r) => n + (r.payload?.opps?.length ?? 0), 0);
        return (
            <>
                <div className="flex items-center gap-2 flex-wrap text-[11px]" data-testid="opp-kind-filter">
                    <span className="text-muted-foreground uppercase tracking-wide">Tipo</span>
                    <button
                        type="button"
                        onClick={() => setOppKindFilter('all')}
                        aria-pressed={oppKindFilter === 'all'}
                        className={`px-2 py-0.5 rounded-full border tabular-nums ${oppKindFilter === 'all' ? 'bg-white/15 text-white border-white/30' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                    >
                        tutte {total}
                    </button>
                    {SAFE_OPP_KINDS.map((k) => (
                        <button
                            key={k}
                            type="button"
                            onClick={() => setOppKindFilter(k)}
                            aria-pressed={oppKindFilter === k}
                            title={OPP_KIND_META[k].title}
                            className={`px-2 py-0.5 rounded-full border tabular-nums font-heading ${oppKindFilter === k ? OPP_KIND_META[k].badge : 'border-white/10 text-muted-foreground hover:text-white'}`}
                        >
                            {OPP_KIND_META[k].label.charAt(0) + OPP_KIND_META[k].label.slice(1).toLowerCase()} {counts[k]}
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-2 flex-wrap text-[11px]">
                    <span className="text-muted-foreground uppercase tracking-wide">Confidenza minima</span>
                    {[0, 0.5, 0.7, 0.85].map((c) => (
                        <button
                            key={c}
                            onClick={() => setOppMinConfidence(c)}
                            className={`px-2 py-0.5 rounded-full border tabular-nums ${oppMinConfidence === c ? 'bg-secondary/20 text-secondary border-secondary/40' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                        >
                            {c === 0 ? 'tutte' : `${Math.round(c * 100)}%`}
                        </button>
                    ))}
                    <span className="ml-3 text-muted-foreground uppercase tracking-wide">Lato</span>
                    {(['all', 'back', 'lay'] as const).map((s) => (
                        <button
                            key={s}
                            onClick={() => setOppSide(s)}
                            className={`px-2 py-0.5 rounded-full border uppercase ${oppSide === s ? 'bg-primary/20 text-primary border-primary/40' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                        >
                            {s === 'all' ? 'tutti' : s}
                        </button>
                    ))}
                </div>
                {rows.length === 0 ? (
                    <EmptyState>
                        {sport === 'tennis'
                            ? 'Nessuna opportunità tennis calcolata: il servizio le scrive quando il modello a punti ha un match in corso affidabile.'
                            : 'Nessuna opportunità calcolata: il servizio le scrive quando ha λ affidabili sul match in corso.'}
                    </EmptyState>
                ) : visible.length === 0 ? (
                    <EmptyState>
                        <span data-testid="opp-filtered-empty">
                            Nessuna opportunità supera i filtri
                            {oppMinConfidence > 0 ? ` (confidenza ≥ ${Math.round(oppMinConfidence * 100)}%` : ' ('}
                            {oppSide !== 'all' ? `${oppMinConfidence > 0 ? ', ' : ''}lato ${oppSide.toUpperCase()}` : ''}
                            {oppKindFilter !== 'all' ? `${oppMinConfidence > 0 || oppSide !== 'all' ? ', ' : ''}tipo ${OPP_KIND_META[oppKindFilter].label}` : ''}
                            ): allarga tipo, confidenza o lato per vederne {total}.
                        </span>
                    </EmptyState>
                ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        {visible.map((r) => (
                            <OpportunityGroup
                                key={r.event_id}
                                row={r}
                                mode={mode}
                                stake={bot.paramsEffective?.opps_stake ?? bot.params.opps_stake}
                                minStake={minStake}
                                requests={bot.requests}
                                minConfidence={oppMinConfidence}
                                sideFilter={oppSide}
                                kindFilter={oppKindFilter}
                                nowMs={nowMs}
                                players={sport === 'tennis' && payloadByEvent[r.event_id] && 'sets' in payloadByEvent[r.event_id]
                                    ? { p1: (payloadByEvent[r.event_id] as TennisScanPayload).p1, p2: (payloadByEvent[r.event_id] as TennisScanPayload).p2 }
                                    : null}
                                onPlace={(o, size) => placeFromOpportunity(r.event_id, r.payload?.event_name ?? null, sport, o, size)}
                            />
                        ))}
                    </div>
                )}
            </>
        );
    }

    function renderTrades(list: SafeTrade[], today: SafeTrade[], summary: ReturnType<typeof summarizeMatches>) {
        const shown = showAllTrades ? list : today;
        const positions = groupClosingLegs(shown).length;   // posizioni (le chiusure stanno sotto l'apertura)
        return (
            <div className="space-y-4">
                <EquityCard
                    series={buildEquitySeries(shown)}
                    scope={showAllTrades ? `ultime ${list.length} operazioni caricate` : `giornata ${dayLabel(operatingDay, { year: false })}`}
                    label="Equity curve Safe Strategy"
                />
                <SectionCard
                    testId="safe-trades-card"
                    icon={<Activity className="w-4 h-4 text-primary" aria-hidden />}
                    title={showAllTrades ? 'Tutte le operazioni' : 'Operazioni di oggi'}
                    count={positions}
                    note={
                        <span data-testid="safe-trades-summary">
                            · {summary.legs} posizioni oggi · {summary.won}V {summary.lost}P
                            {summary.live > 0 && ` · ${summary.live} ${T.live}`}
                            {summary.pnl_locked != null && ` · ${T.lockedPnl} ${fmtMoney(summary.pnl_locked, { signed: true })}`}
                            {summary.open_liability > 0 && ` · ${T.openLiability} ${fmtMoney(summary.open_liability)}`}
                        </span>
                    }
                    actions={
                        <>
                            <span className="text-[11px] text-slate-500">{T.operatingDay} {dayLabel(operatingDay, { year: false })} · le giornate passate sono nello Storico</span>
                            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowAllTrades((v) => !v)} data-testid="safe-trades-toggle">
                                {showAllTrades ? 'solo oggi' : 'mostra tutte'}
                            </Button>
                        </>
                    }
                >
                    <SafeTradesTable
                        trades={shown}
                        commissionPct={bot.paramsEffective?.commission_pct ?? bot.params.commission_pct}
                        liveFeed={payloadByEvent}
                        isCashOutPending={bot.isCashOutPending}
                        freshnessOf={freshnessOf}
                        requests={bot.requests}
                        onCashOut={cashOut}
                        onCancel={cancelReserve}
                        emptyText={showAllTrades
                            ? "nessun trade ancora — piazza da un segnale o da un'opportunità, oppure avvia il bot"
                            : "nessuna operazione oggi — piazza da un segnale o da un'opportunità, oppure avvia il bot (le giornate passate sono nello Storico)"}
                    />
                </SectionCard>
            </div>
        );
    }

    return (
        <PageShell
            title="Safe Strategy | Alpha Score"
            header={
                <BotHeader
                    bot="safe"
                    status={status}
                    heartbeatAt={bot.control?.heartbeat_at}
                    nowMs={nowMs}
                    statusPrefix="BOT"
                    statusTestId="bot-status"
                    running={running}
                    busy={bot.busy}
                    onStart={() => { void bot.start(); }}
                    onStop={() => { void bot.stop(); }}
                    onHeight={setNavH}
                    health={
                        <ServiceHealthChip
                            botName="Safe"
                            nowMs={nowMs}
                            feedUpdatedAt={scanStatus?.updated_at}
                            feedStaleMs={SCANNER_STALE_MS}
                            feedMissing={scanStatus === null}
                            heartbeatAt={bot.control?.heartbeat_at}
                            counts={{ calcio: scanStatus?.payload?.calcio_inplay, tennis: scanStatus?.payload?.tennis_inplay }}
                            source={scanStatus?.payload?.source}
                            streamMarkets={scanStatus?.payload?.stream_markets}
                            dry={scanStatus?.payload?.dry}
                            lastError={scanStatus?.payload?.last_error ?? null}
                        />
                    }
                    modeToggle={<ModeToggle mode={mode} onChange={onToggleMode} />}
                    params={bot.available
                        ? (
                            <BotParamsSheet
                                params={bot.params}
                                rawParams={bot.control?.params ?? null}
                                effective={bot.paramsEffective}
                                corrections={paramCorrections}
                                persisted={paramPersisted}
                                busy={bot.busy}
                                onSave={bot.saveParams}
                            />
                        )
                        : <ParamsSheet />}
                />
            }
            footer={
                <>
                    Fonte dati: scanner autonomo Betfair (feed unico). Video e statistiche si aprono sul
                    popup ufficiale Betfair col tuo account.
                </>
            }
        >
                <ModeBanner
                    mode={mode}
                    liveText={<>gli ordini piazzati da questa schermata e dal bot usano <b>soldi veri</b>.</>}
                    paperText="simulazione fedele: coda, liquidità e protezioni identiche al live, nessun denaro reale."
                    error={bot.control?.error ?? null}
                />

                {/* ---------------------------------------- giornata operativa */}
                <DayBar
                    dayLabel={dayLabel(operatingDay, { weekday: true })}
                    realized={realizedToday}
                    realizedTotal={realizedTotal}
                    matches={eventsToday}
                    operations={legsToday}
                    won={wonToday}
                    lost={lostToday}
                    live={openCount}
                    openLiability={openLiability}
                    lockedPnl={lockedToday}
                    note={dayFromUi
                        ? `giorno di PIAZZAMENTO della posizione — ${MIGRAZIONE_NOTA}: contati sulle righe caricate, non sull'intera giornata`
                        : 'giorno di PIAZZAMENTO della posizione: gli stessi numeri dei KPI, del tab Trade e dello Storico'}
                />

                {/* ------------------------------------------------------ KPI */}
                <KpiRow loading={bot.loading} tiles={6}>
                        <StatTile label="Segnali attivi" value={String(totalActive)} tone="gold" icon={<SignalIcon className="w-3.5 h-3.5" />} sub={`${bySport.calcioActive.length} calcio · ${bySport.tennisActive.length} tennis`} />
                        <StatTile
                            label="Trade aperti"
                            value={String(openCount)}
                            testId="safe-kpi-open"
                            icon={<Activity className="w-3.5 h-3.5" />}
                            sub={
                                <span data-testid="safe-open-sub">
                                    posizioni vive
                                    {reconcilingTrades.length > 0 && ` · ${reconcilingTrades.length} in verifica`}
                                    {partiallyHedged.length > 0 && ` · ${partiallyHedged.length} coperte in parte`}
                                    {` · ${legsToday} oggi`}
                                </span>
                            }
                        />
                        <StatTile label={T.pnlToday} value={fmtMoney(realizedToday, { signed: true })} tone={toneOf(realizedToday)} icon={<TrendingUp className="w-3.5 h-3.5" />} sub={<span data-testid="safe-operating-day">{T.operatingDay} {dayLabel(operatingDay, { year: false })} · Europe/Rome · {wonToday}V {lostToday}P</span>} />
                        <StatTile label={T.pnlTotal} value={fmtMoney(realizedTotal, { signed: true })} tone={toneOf(realizedTotal)} />
                        <StatTile
                            label={T.openLiability}
                            value={fmtMoney(openLiability)}
                            tone="danger"
                            testId="safe-kpi-liability"
                            icon={<ShieldAlert className="w-3.5 h-3.5" />}
                            sub={reconcilingLiability > 0
                                ? <span data-testid="safe-liability-reconciling">di cui in verifica su Betfair {fmtMoney(reconcilingLiability)}</span>
                                : undefined}
                        />
                        {lockedToday != null && (
                            <StatTile label={T.lockedPnl} value={fmtMoney(lockedToday, { signed: true })} tone="teal" testId="safe-kpi-locked" sub="posizioni chiuse a mercato oggi" />
                        )}
                        <StatTile label="Partite monitorate" value={String(football.length + tennis.length)} icon={<Layers className="w-3.5 h-3.5" />} sub={`⚽ ${football.length} · 🎾 ${tennis.length}`} />
                        <RiskPanel
                            risk={stats.risk}
                            opps={stats.opps}
                            fallbackCounts={oppCountsAll}
                            dayLiability={dayLiability}
                            openLiability={openLiability}
                            reconcilingLiability={reconcilingLiability}
                            dayLabel={dayLabel(operatingDay, { year: false })}
                            dayFromUi={dayFromUi}
                            paramDailyCap={bot.params.risk.daily_liability_cap}
                            paramLossStop={bot.params.risk.daily_loss_stop}
                        />
                </KpiRow>

                {/* --------------------------------------------- sport + sezioni */}
                <Tabs value={topTab} onValueChange={setTopTab} className="w-full">
                    <TabsList className="sticky z-30" style={{ top: navH }}>
                        <TabsTrigger value="calcio" aria-label={`Calcio (${bySport.calcioActive.length})`}>⚽ Calcio ({bySport.calcioActive.length})</TabsTrigger>
                        <TabsTrigger value="tennis" aria-label={`Tennis (${bySport.tennisActive.length})`}>🎾 Tennis ({bySport.tennisActive.length})</TabsTrigger>
                        <TabsTrigger value="storico" aria-label="Storico">📅 Storico</TabsTrigger>
                    </TabsList>

                    {/* ============================== CALCIO ============================== */}
                    <TabsContent value="calcio" className="mt-3">
                        <Tabs value={calcioTab} onValueChange={setCalcioTab} className="w-full">
                            <TabsList className="mb-3">
                                <TabsTrigger value="segnali">Segnali ({bySport.calcioActive.length})</TabsTrigger>
                                <TabsTrigger value="opportunita" title={`${oppRows.length} partite con opportunità`}>
                                    Opportunità modello ({oppCountCalcio})
                                </TabsTrigger>
                                <TabsTrigger value="monitor">Monitor ({fbSorted.length})</TabsTrigger>
                                <TabsTrigger value="trade">Trade ({groupClosingLegs(showAllTrades ? calcioTrades : todayTradesCalcio).length})</TabsTrigger>
                            </TabsList>

                            <TabsContent value="segnali" className="space-y-4">
                                {renderSignals(bySport.calcioActive)}
                                {bySport.calcioExpired.length > 0 && (
                                    <details>
                                        <summary className="text-[11px] uppercase tracking-wide text-muted-foreground font-heading font-bold cursor-pointer select-none">
                                            Storico sessione calcio ({bySport.calcioExpired.length})
                                        </summary>
                                        <div className="mt-2 grid grid-cols-1 lg:grid-cols-2 gap-3">
                                            {bySport.calcioExpired.map((s) => (
                                                <SignalCard key={s.key} signal={s} nowMs={nowMs} media={mediaByEvent[s.eventId]} />
                                            ))}
                                        </div>
                                    </details>
                                )}
                            </TabsContent>

                            <TabsContent value="opportunita" className="space-y-3">
                                {renderOpportunities(oppRows, visibleOppRows, 'calcio')}
                            </TabsContent>

                            <TabsContent value="monitor">
                                {fbSorted.length === 0 ? (
                                    <EmptyState>
                                        Nessun match di calcio in-play: lo scanner aggiunge gli eventi da solo appena vanno live.
                                    </EmptyState>
                                ) : (
                                    <div className="space-y-2">
                                        {fbSorted.map((m) => (
                                            <MonitorCard
                                                key={m.eventId}
                                                eventId={m.eventId}
                                                title={`${m.ctx.home} – ${m.ctx.away}`}
                                                liveLine={footballLiveLine(m)}
                                                inplay={m.ctx.inplay}
                                                evaluations={m.evaluations.map((evaluation) => ({ evaluation }))}
                                                dataNote={m.preMatchMissing ? 'riferimento pre-KO non catturato (scanner partito a match iniziato) — condizioni pre-match n/d' : null}
                                                media={m.payload.media}
                                            />
                                        ))}
                                    </div>
                                )}
                            </TabsContent>

                            <TabsContent value="trade">{renderTrades(calcioTrades, todayTradesCalcio, todaySummaryCalcio)}</TabsContent>
                        </Tabs>
                    </TabsContent>

                    {/* ============================== TENNIS ============================== */}
                    <TabsContent value="tennis" className="mt-3">
                        <Tabs value={tennisTab} onValueChange={setTennisTab} className="w-full">
                            <TabsList className="mb-3">
                                <TabsTrigger value="segnali">Segnali ({bySport.tennisActive.length})</TabsTrigger>
                                <TabsTrigger value="opportunita" title={`${tennisOppRows.length} match con opportunità`}>
                                    Opportunità tennis ({oppCountTennis})
                                </TabsTrigger>
                                <TabsTrigger value="monitor">Monitor ({tnSorted.length})</TabsTrigger>
                                <TabsTrigger value="trade">Trade ({groupClosingLegs(showAllTrades ? tennisTrades : todayTradesTennis).length})</TabsTrigger>
                            </TabsList>

                            <TabsContent value="opportunita" className="space-y-3">
                                {renderOpportunities(tennisOppRows, visibleTennisOppRows, 'tennis')}
                            </TabsContent>

                            <TabsContent value="segnali" className="space-y-4">
                                {renderSignals(bySport.tennisActive)}
                                {bySport.tennisExpired.length > 0 && (
                                    <details>
                                        <summary className="text-[11px] uppercase tracking-wide text-muted-foreground font-heading font-bold cursor-pointer select-none">
                                            Storico sessione tennis ({bySport.tennisExpired.length})
                                        </summary>
                                        <div className="mt-2 grid grid-cols-1 lg:grid-cols-2 gap-3">
                                            {bySport.tennisExpired.map((s) => (
                                                <SignalCard key={s.key} signal={s} nowMs={nowMs} media={mediaByEvent[s.eventId]} />
                                            ))}
                                        </div>
                                    </details>
                                )}
                            </TabsContent>

                            <TabsContent value="monitor">
                                {tnSorted.length === 0 ? (
                                    <EmptyState>
                                        Nessun match di tennis in-play: lo scanner li aggiunge da solo appena vanno live.
                                    </EmptyState>
                                ) : (
                                    <div className="space-y-2">
                                        {tnSorted.map((m) => (
                                            <MonitorCard
                                                key={m.eventId}
                                                eventId={m.eventId}
                                                title={`${m.ctx.p1} – ${m.ctx.p2}`}
                                                liveLine={tennisLiveLine(m)}
                                                inplay={m.ctx.inplay}
                                                evaluations={[{ evaluation: m.evaluation }]}
                                                media={m.payload.media}
                                            />
                                        ))}
                                    </div>
                                )}
                            </TabsContent>

                            <TabsContent value="trade">{renderTrades(tennisTrades, todayTradesTennis, todaySummaryTennis)}</TabsContent>
                        </Tabs>
                    </TabsContent>

                    {/* ============================== STORICO ============================= */}
                    <TabsContent value="storico" className="mt-3 space-y-3">
                        <div className="flex items-center gap-2 flex-wrap text-[11px]" data-testid="history-sport-filter">
                            <span className="text-muted-foreground uppercase tracking-wide">Sport</span>
                            {([['all', 'tutti'], ['calcio', '⚽ calcio'], ['tennis', '🎾 tennis']] as const).map(([k, label]) => {
                                const val: SafeSportFilter = k === 'all' ? null : k;
                                const active = historySport === val;
                                return (
                                    <button
                                        key={k}
                                        type="button"
                                        onClick={() => setHistorySport(val)}
                                        aria-pressed={active}
                                        className={`px-2 py-0.5 rounded-full border ${active ? 'bg-primary/20 text-primary border-primary/40' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                                    >
                                        {label}
                                    </button>
                                );
                            })}
                        </div>
                        <TradingHistory
                            variant="safe"
                            fetchDaily={fetchHistoryDaily}
                            fetchDayTrades={fetchHistoryDay}
                            filterKey={historySport ?? 'all'}
                            onGoLive={(t) => {
                                const sp = t.sport === 'tennis' ? 'tennis' : 'calcio';
                                setTopTab(sp);
                                if (sp === 'tennis') setTennisTab('trade'); else setCalcioTab('trade');
                            }}
                        />
                    </TabsContent>
                </Tabs>

                {/* ------------------------- attività del servizio (H-16) ------------ */}
                <SectionCard
                    className="mt-3"
                    testId="safe-activity-card"
                    icon={<ScrollText className="w-4 h-4 text-secondary" aria-hidden />}
                    title={T.activityToday.replace(' di oggi', '')}
                    count={activityRows.length}
                    note={
                        <span data-testid="safe-activity-note">
                            perché il bot è entrato o NON è entrato: salti, blocchi di rischio, uscite,
                            riconciliazioni, feed
                            {criticalActivity > 0 && (
                                <b className="text-red-300"> · {criticalActivity} da guardare</b>
                            )}
                        </span>
                    }
                >
                    <ActivityFeed
                        rows={activityRows}
                        metaOf={safeActivityMeta}
                        lineOf={(r) => safeActivityLine(r.payload)}
                        filterable
                        timeSeconds
                        testId="safe-activity"
                        emptyText="nessuna attività registrata: il servizio scrive qui ogni decisione (serve la migrazione safe_strategy_bot_v2.sql o il bot avviato)"
                    />
                </SectionCard>

                <div className="flex items-center gap-2 flex-wrap pt-2">
                    {(['base', 'esatto', 'punta', 'tennis'] as const).map((v) => (
                        <Badge key={v} variant="outline" className={`text-[10px] font-heading ${VARIANT_STYLE[v].badge}`}>
                            {VARIANT_STYLE[v].chipLabel()}
                        </Badge>
                    ))}
                </div>

            {/* conferma LIVE (soldi veri) */}
            <LiveConfirmDialog
                open={liveConfirmOpen}
                onOpenChange={setLiveConfirmOpen}
                onConfirm={() => { void applyLive(); }}
                busy={bot.busy}
                intro={<>Da questo momento gli ordini piazzati dai segnali, dalle opportunità e dal bot usano <b>denaro reale</b>.</>}
                warning="Le strategie Safe hanno vincite piccole e frequenti: una singola perdita può cancellare molte vincite. Controlla stake e liability prima di procedere."
            />
        </PageShell>
    );
}
