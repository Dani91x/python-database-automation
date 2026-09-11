// ============================================================================
// /mike — sezione MIKE: bot di trading Under 3.5 / Over 4.5 (paper-first).
//
// GUSCIO CONDIVISO del design system di trading (components/trading):
//   PageShell → BotHeader (+ServiceHealthChip, ModeToggle) → ModeBanner →
//   DayBar → KpiRow → Tabs (Partite · Trade · Attività · Regolate · Storico).
// Formati e etichette da lib/format.ts + lib/tradeStatus.ts: nessun formatter
// locale, nessuna mappa di stati duplicata.
//
// SCHEDE FERME (richiesta dell'utente): il tab Partite ha DUE sezioni fisse,
// sempre nello stesso ordine — «⏱ PRE-MATCH» e «🔴 LIVE» — più «⚠️ DA
// SISTEMARE» in fondo per ERROR/SKIPPED (audit H6: prima erano invisibili e
// "Riprendi" era irraggiungibile). Dentro ogni sezione l'ordine è per calcio
// d'inizio crescente e NON dipende dalla fase: una partita passa a LIVE solo al
// fischio d'inizio e non torna più indietro (memoria sticky). Le card sono
// memoizzate su `updated_at`, il tempo non entra nelle loro props (il countdown
// ha un tick foglia) e le ricariche del realtime sono debounced.
//
// FONTE UNICA: feed dello scanner (ramo pre-KO O/U) letto dal servizio; qui
// nessuna chiamata Betfair. Scritture SOLO via RPC owner-only.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Activity, Layers, ShieldAlert, TrendingUp, Zap } from 'lucide-react';
import { useMike } from '@/components/mike/useMike';
import { MikeParamsSheet } from '@/components/mike/MikeParamsSheet';
import { MikeMatchCard } from '@/components/mike/MikeMatchCard';
import { MikeTradesTable } from '@/components/mike/MikeTradesTable';
import { SCANNER_STALE_MS } from '@/lib/safeBot';
import { fetchScanStatus, type ScanStatusRow } from '@/lib/safeStrategyScan';
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
import { fmtMoney, fmtNum, fmtTime } from '@/lib/format';
import { activityMeta, T } from '@/lib/tradeStatus';
import { toastSettlement } from '@/lib/toasts';
import { romeDay, dayLabel, fetchMikeDaily, fetchMikeDayTrades } from '@/lib/dailyHistory';
import {
    splitMikeEvents, rememberLive, lastRequestFor, requestOutcome, mikeActivityLine,
    mikeEquitySeries, activeLegs, voidedMarketsOf, withMikeHistoryError, MIKE_ACTIVITY_EXTRA,
    dayResultCounts,
    type MikeEvent, type MikeMode, type MikeRequestKind, type MikeStatus,
} from '@/lib/mike';

const REQUEST_KINDS: MikeRequestKind[] = ['cashout', 'flatten', 'skip_event', 'resume_event', 'cancel'];

// R2 — senza `migrations/mike_history_v2.sql` le RPC dello storico rispondono
// «function trading_daily_history(...) is not unique»: un codice nudo in una
// pagina vuota. Qui l'errore diventa una riga che dice COSA FARE.
const fetchDailyReadable = withMikeHistoryError(fetchMikeDaily);
const fetchDayTradesReadable = withMikeHistoryError(fetchMikeDayTrades);

// =============================================================== main page
export default function Mike() {
    const bot = useMike({ onError: (m) => toast.error('Bot Mike', { description: m }) });
    const [nowMs, setNowMs] = useState(() => Date.now());
    const [scanStatus, setScanStatus] = useState<ScanStatusRow | null>(null);
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
    const [tab, setTab] = useState('partite');
    const notifiedRef = useRef<Set<string>>(new Set());
    const notifiedReqRef = useRef<Set<number>>(new Set());
    // memoria "è già andata in gioco": una card non torna mai in PRE-MATCH
    const liveSeen = useRef<Set<string>>(new Set());
    const [navH, setNavH] = useState(52);
    const operatingDay = romeDay();

    // `nowMs` serve SOLO all'intestazione (salute del servizio): 5 s, e non
    // entra nelle props delle card (il countdown ha il suo tick da 1 s).
    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 5_000);
        return () => window.clearInterval(t);
    }, []);
    useEffect(() => {
        let alive = true;
        const load = () => { fetchScanStatus().then((s) => { if (alive) setScanStatus(s); }).catch(() => {}); };
        load();
        const t = window.setInterval(load, 15_000);
        return () => { alive = false; window.clearInterval(t); };
    }, []);
    useEffect(() => {
        for (const e of bot.freshSettled) {
            if (notifiedRef.current.has(e.event_id)) continue;
            notifiedRef.current.add(e.event_id);
            toastSettlement({ name: e.event_name ?? e.event_id, pnl: Number(e.settled_pnl ?? 0) });
        }
    }, [bot.freshSettled]);
    // M1 — l'esito di OGNI richiesta della UI diventa un toast, una volta sola
    useEffect(() => {
        for (const r of bot.freshOutcomes) {
            if (notifiedReqRef.current.has(r.id)) continue;
            notifiedReqRef.current.add(r.id);
            const o = requestOutcome(r);
            const name = bot.events.find((e) => e.event_id === o.eventId)?.event_name ?? o.eventId ?? 'Mike';
            if (o.tone === 'ok') toast.success(o.label, { description: name });
            else if (o.tone === 'warn') toast.warning(o.label, { description: name });
            else toast.error(o.label, { description: name });
        }
    }, [bot.freshOutcomes, bot.events]);

    const status: MikeStatus = (bot.control?.status ?? 'idle') as MikeStatus;
    const running = status === 'running' || status === 'stopping';
    const mode: MikeMode = bot.mode;
    const stats = bot.control?.stats ?? null;
    const scannerAge = scanStatus?.updated_at ? (nowMs - Date.parse(scanStatus.updated_at)) / 1000 : null;
    const feedStale = scannerAge === null || scannerAge * 1000 > SCANNER_STALE_MS;

    rememberLive(bot.events, liveSeen.current);
    const sections = useMemo(
        () => splitMikeEvents(bot.events, liveSeen.current),
        [bot.events],
    );
    const active = useMemo(
        () => [...sections.pre, ...sections.live, ...sections.fix],
        [sections],
    );
    const withPosition = useMemo(
        () => active.filter((e) => activeLegs(e).some((l) => l.matched > 0)).length,
        [active],
    );

    const agg = bot.aggregates;
    const realizedToday = Number(agg?.realized_today ?? stats?.realized_today ?? 0);
    const realizedTotal = Number(agg?.realized_total ?? stats?.realized_total ?? 0);
    const openLiability = Number(agg?.open_liability ?? stats?.open_liability ?? 0);
    const reconciling = Number(agg?.reconciling ?? 0);
    // la liability puo' essere la NETTA del servizio o il ripiego sulle righe:
    // un trader deve sapere quale dei due sta leggendo (e se e' stantia)
    const liabilityFromRows = agg?.liability_source === 'rows_sum';
    const liabilityStale = agg?.liability_stale === true;
    // P&L bloccato della giornata: somma dei `live.locked` delle partite vive
    const lockedPnl = useMemo(
        () => Math.round(active.reduce((s, e) => s + Number(e.live?.locked ?? 0), 0) * 100) / 100,
        [active],
    );
    // V/P della giornata: dalla RPC v2; senza migrazione dal client (dichiarato)
    const clientCounts = useMemo(() => dayResultCounts(bot.trades, bot.dayStartMs), [bot.trades, bot.dayStartMs]);
    const countsFromClient = agg?.won_today == null && agg?.lost_today == null;
    const wonToday = agg?.won_today ?? clientCounts.won;
    const lostToday = agg?.lost_today ?? clientCounts.lost;
    // battito del servizio: oltre 45 s le `stats` sono una fotografia vecchia
    const hbMs = bot.control?.heartbeat_at ? Date.parse(bot.control.heartbeat_at) : NaN;
    const serviceAlive = Number.isFinite(hbMs) && nowMs - hbMs <= 45_000;
    const equity = useMemo(() => mikeEquitySeries(bot.trades, bot.dayStartMs), [bot.trades, bot.dayStartMs]);

    const activityRows: ActivityRow[] = useMemo(
        () => bot.activity.map((a) => {
            const name = a.event_id
                ? (bot.events.find((e) => e.event_id === a.event_id)?.event_name ?? a.event_id)
                : null;
            return {
                id: a.id,
                ts: a.ts,
                kind: a.kind,
                event_name: name,
                line: [name, mikeActivityLine(a.kind, a.payload)].filter(Boolean).join(' · '),
            };
        }),
        [bot.activity, bot.events],
    );

    function onToggleMode(next: MikeMode) {
        if (next === 'live') setLiveConfirmOpen(true);
        else void bot.setMode('paper');
    }
    async function applyLive() {
        await bot.setMode('live');
        setLiveConfirmOpen(false);
        toast.error(`🔴 ${T.modeLive} — soldi veri`);
    }
    const onRequest = useCallback((kind: MikeRequestKind, eventId: string) => {
        if ((kind === 'cashout' || kind === 'flatten') && mode === 'live' && !bot.liveConfirmed) {
            setLiveConfirmOpen(true);
            toast.warning('Conferma la modalità LIVE prima di operare con soldi veri');
            return;
        }
        void bot.request(kind, eventId);
    }, [mode, bot.liveConfirmed, bot.request]);

    const pendingKindsOf = useCallback(
        (eventId: string) => REQUEST_KINDS.filter((k) => bot.isRequestPending(eventId, k)).join(','),
        [bot.isRequestPending],
    );

    // dalla tabella Trade alla SCHEDA della partita: il cash out di Mike è per
    // EVENTO, quindi la riga rimanda alla card invece di duplicare il bottone.
    const openEventCard = useCallback((eventId: string) => {
        setTab('partite');
        window.setTimeout(() => {
            const el = document.querySelector<HTMLElement>(`[data-testid="mike-match-card"][data-event-id="${eventId}"]`);
            if (!el) return;
            // `scrollIntoView` non esiste in jsdom (e su qualche webview vecchia):
            // lo scroll è un vezzo, l'evidenziazione è quello che conta.
            if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'center' });
            el.classList.add('ring-2', 'ring-teal-400/70');
            window.setTimeout(() => el.classList.remove('ring-2', 'ring-teal-400/70'), 2_000);
        }, 60);
    }, []);

    const voidedOf = useCallback(
        (eventId: string) => voidedMarketsOf(eventId, bot.activity, bot.trades),
        [bot.activity, bot.trades],
    );

    const renderCard = (e: MikeEvent) => (
        <MikeMatchCard
            key={e.event_id}
            ev={e}
            params={bot.params}
            mode={mode}
            busy={bot.busy}
            stale={feedStale}
            staleReason={feedStale ? 'scanner fermo' : undefined}
            lastRequest={lastRequestFor(e.event_id, bot.requests)}
            voidedMarkets={voidedOf(e.event_id)}
            pendingKinds={pendingKindsOf(e.event_id)}
            onRequest={onRequest}
        />
    );

    return (
        <PageShell
            title="Mike | Alpha Score"
            header={
                <BotHeader
                    bot="mike"
                    status={status}
                    heartbeatAt={bot.control?.heartbeat_at}
                    nowMs={nowMs}
                    statusPrefix="BOT"
                    statusTestId="mike-status"
                    running={running}
                    busy={bot.busy}
                    startDisabled={!bot.available}
                    onStart={() => { void bot.start(); }}
                    onStop={() => { void bot.stop(); }}
                    onHeight={setNavH}
                    health={
                        <ServiceHealthChip
                            botName="Mike"
                            nowMs={nowMs}
                            feedUpdatedAt={scanStatus?.updated_at}
                            feedStaleMs={SCANNER_STALE_MS}
                            feedMissing={scanStatus === null}
                            heartbeatAt={bot.control?.heartbeat_at}
                            counts={{ calcio: scanStatus?.payload?.calcio_inplay, tennis: scanStatus?.payload?.tennis_inplay }}
                            source={scanStatus?.payload?.source}
                            streamMarkets={scanStatus?.payload?.stream_markets}
                            dry={stats?.dry}
                            lastError={scanStatus?.payload?.last_error ?? null}
                        />
                    }
                    modeToggle={<ModeToggle mode={mode} onChange={onToggleMode} />}
                    params={<MikeParamsSheet params={bot.params} busy={bot.busy || !bot.available} onSave={bot.saveParams} />}
                />
            }
            footer="Fonte dati: feed unico dello scanner (linee Over/Under 3.5 e 4.5 pre-match e live). Nessuna chiamata Betfair da questa schermata. Paper-first: il live si attiva solo dal toggle con conferma."
        >
            <ModeBanner
                mode={mode}
                testId="mike-mode-banner"
                liveText={<>il bot piazza ordini con <b>soldi veri</b>.</>}
                paperText="simulazione fedele: fill solo al prezzo ancora disponibile, betDelay in-play, protezioni identiche al live."
                dry={stats?.dry}
                error={bot.control?.error ?? null}
                migrationWarning={!bot.available && !bot.loading ? 'tabelle Mike assenti: applica migrations/mike_bot.sql' : null}
            />

            <DayBar
                dayLabel={dayLabel(operatingDay, { weekday: true })}
                realized={realizedToday}
                realizedTotal={realizedTotal}
                matches={agg?.events_today ?? active.length}
                operations={agg?.cycles_today ?? bot.trades.length}
                won={wonToday}
                lost={lostToday}
                live={agg?.live_now ?? sections.live.length}
                openLiability={openLiability}
                lockedPnl={lockedPnl}
                note={countsFromClient
                    ? 'conta le partite PIAZZATE oggi (Europe/Rome) · V/P stimati dal client: applica migrations/mike_bot_v2.sql'
                    : 'conta le partite PIAZZATE oggi (giorno di piazzamento, Europe/Rome)'}
            />

            <KpiRow loading={bot.loading}>
                <StatTile
                    label="Partite seguite"
                    value={String(active.length)}
                    tone="teal"
                    icon={<Layers className="w-3.5 h-3.5" />}
                    sub={`${sections.pre.length} pre-match · ${sections.live.length} live · ${withPosition} con posizione`}
                    testId="mike-kpi-matches"
                />
                <StatTile
                    label="Posizioni aperte"
                    value={String(agg?.open_count ?? stats?.trades_open ?? 0)}
                    icon={<Activity className="w-3.5 h-3.5" />}
                    sub={reconciling > 0 ? <span className="text-fuchsia-300">{reconciling} in verifica su Betfair</span> : `${bot.trades.length} righe caricate`}
                />
                <StatTile
                    label={T.pnlToday}
                    value={fmtMoney(realizedToday, { signed: true })}
                    tone={toneOf(realizedToday)}
                    icon={<TrendingUp className="w-3.5 h-3.5" />}
                    sub={<span>{T.operatingDay} {dayLabel(operatingDay, { year: false })} · Europe/Rome</span>}
                />
                <StatTile label={T.pnlTotal} value={fmtMoney(realizedTotal, { signed: true })} tone={toneOf(realizedTotal)} />
                <StatTile
                    label={T.openLiability}
                    value={fmtMoney(openLiability)}
                    tone="danger"
                    icon={<ShieldAlert className="w-3.5 h-3.5" />}
                    sub={stats?.daily_stop
                        ? <span className="text-rose-300 font-semibold" data-testid="mike-daily-stop">STOP giornaliero ATTIVO · solo chiusure</span>
                        : <span data-testid="mike-liability-sub">
                            {liabilityFromRows
                                ? <span className="text-amber-300">stimata dalle righe</span>
                                : <>stop giornaliero {fmtMoney(Number(bot.params.daily_loss_stop ?? 0))}</>}
                            {reconciling > 0 ? ` · di cui ${reconciling} in verifica` : ''}
                            {liabilityStale && <span className="text-amber-300"> · dato stantio</span>}
                        </span>}
                />
                <StatTile
                    label={T.lockedPnl}
                    value={fmtMoney(lockedPnl, { signed: true })}
                    tone={toneOf(lockedPnl)}
                    sub="già bloccato sulle partite vive"
                    testId="mike-kpi-locked"
                />
                <StatTile
                    label="Ultimo ciclo"
                    value={fmtTime(stats?.last_cycle, { seconds: true })}
                    tone={serviceAlive ? 'plain' : 'danger'}
                    sub={!serviceAlive
                        ? <span className="text-red-300" data-testid="mike-service-stale">servizio senza battito: riavvia l’app desktop</span>
                        : stats?.scanner_age_s != null ? `feed ${fmtNum(stats.scanner_age_s, 0)} s` : 'feed: nessun dato'}
                    testId="mike-kpi-cycle"
                />
            </KpiRow>

            <Tabs value={tab} onValueChange={setTab} className="w-full">
                <TabsList className="sticky z-30" style={{ top: navH }}>
                    <TabsTrigger value="partite" aria-label={`Partite (${active.length})`}>⚽ Partite ({active.length})</TabsTrigger>
                    <TabsTrigger value="trade" aria-label={`Trade (${bot.trades.length})`}>📋 Trade ({bot.trades.length})</TabsTrigger>
                    <TabsTrigger value="attivita" aria-label="Attività">🧾 Attività</TabsTrigger>
                    <TabsTrigger value="regolate" aria-label={`Regolate (${sections.settled.length})`}>✅ Regolate ({sections.settled.length})</TabsTrigger>
                    <TabsTrigger value="storico" aria-label="Storico">📅 Storico</TabsTrigger>
                </TabsList>

                <TabsContent value="partite" className="mt-3 space-y-4">
                    {active.length === 0 ? (
                        <EmptyState>
                            Nessuna partita seguita. Con il bot in corsa, le partite con calcio d’inizio entro
                            {' '}{String(bot.params.entry_hours_before_ko)} ore e le linee 3.5/4.5 nel feed compaiono qui.
                        </EmptyState>
                    ) : (
                        <div className="space-y-4" data-testid="mike-cards">
                            {/* SEZIONE 1 — sempre la prima, anche vuota: l'occhio sa dove guardare */}
                            <section data-testid="mike-section-pre">
                                <h2 className="text-[11px] uppercase tracking-wide text-teal-300 font-heading font-bold mb-1.5">
                                    ⏱ PRE-MATCH ({sections.pre.length})
                                    <span className="text-slate-500 font-normal normal-case"> · per calcio d’inizio</span>
                                </h2>
                                {sections.pre.length === 0
                                    ? <EmptyState testId="mike-pre-empty">Nessuna partita in attesa del calcio d’inizio.</EmptyState>
                                    : <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start" data-testid="mike-cards-pre">
                                        {sections.pre.map(renderCard)}
                                    </div>}
                            </section>

                            {/* SEZIONE 2 — le partite in gioco: entrano qui al fischio d'inizio e restano */}
                            <section data-testid="mike-section-live">
                                <h2 className="text-[11px] uppercase tracking-wide text-violet-300 font-heading font-bold mb-1.5">
                                    🔴 LIVE ({sections.live.length})
                                    <span className="text-slate-500 font-normal normal-case"> · in gioco</span>
                                </h2>
                                {sections.live.length === 0
                                    ? <EmptyState testId="mike-live-empty">Nessuna partita in gioco in questo momento.</EmptyState>
                                    : <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start" data-testid="mike-cards-live">
                                        {sections.live.map(renderCard)}
                                    </div>}
                            </section>

                            {/* SEZIONE 3 — ERROR/SKIPPED: prima invisibili, "Riprendi" irraggiungibile (H6) */}
                            {sections.fix.length > 0 && (
                                <section data-testid="mike-section-fix">
                                    <h2 className="text-[11px] uppercase tracking-wide text-red-300 font-heading font-bold mb-1.5">
                                        ⚠️ DA SISTEMARE ({sections.fix.length})
                                        <span className="text-slate-500 font-normal normal-case"> · partite in errore o saltate: serve una mano</span>
                                    </h2>
                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start" data-testid="mike-cards-fix">
                                        {sections.fix.map(renderCard)}
                                    </div>
                                </section>
                            )}
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="trade" className="mt-3 space-y-3">
                    <MikeTradesTable
                        trades={bot.trades}
                        dayStartMs={bot.dayStartMs}
                        dayStartSource={bot.dayStartSource}
                        dayLabel={dayLabel(operatingDay, { weekday: true })}
                        summary={{
                            openCount: agg?.open_count ?? stats?.trades_open ?? 0,
                            won: wonToday ?? agg?.won ?? 0,
                            lost: lostToday ?? agg?.lost ?? 0,
                            lockedPnl,
                            openLiability,
                            reconciling,
                        }}
                        onOpenEvent={openEventCard}
                    />
                    <EquityCard
                        series={equity}
                        scope={`${T.operatingDay} ${dayLabel(operatingDay, { year: false })}`}
                        emptyLabel="nessun trade ancora regolato oggi — la curva compare al primo incasso"
                        label="Equity curve di Mike"
                    />
                </TabsContent>

                <TabsContent value="attivita" className="mt-3">
                    <SectionCard
                        icon={<Zap className="w-4 h-4 text-teal-300" aria-hidden />}
                        title="Attività del servizio"
                        count={activityRows.length}
                        note={`${T.operatingDay} · ora di Roma`}
                        testId="mike-activity"
                    >
                        <ActivityFeed
                            rows={activityRows}
                            metaOf={(k) => activityMeta(k, MIKE_ACTIVITY_EXTRA)}
                            filterable
                            timeSeconds
                            maxHeightCls="max-h-[32rem]"
                            emptyText="Nessuna attività registrata."
                            rowTestId="mike-activity-row"
                        />
                    </SectionCard>
                </TabsContent>

                <TabsContent value="regolate" className="mt-3">
                    {sections.settled.length === 0 ? (
                        <EmptyState>Nessuna partita regolata nella {T.operatingDay}.</EmptyState>
                    ) : (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start" data-testid="mike-cards-settled">
                            {sections.settled.map((e) => (
                                <MikeMatchCard
                                    key={e.event_id} ev={e} params={bot.params} mode={mode}
                                    voidedMarkets={voidedOf(e.event_id)}
                                />
                            ))}
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="storico" className="mt-3">
                    <TradingHistory
                        variant="mike"
                        fetchDaily={fetchDailyReadable}
                        fetchDayTrades={fetchDayTradesReadable}
                        refreshToken={bot.trades.length}
                        onGoLive={() => setTab('partite')}
                    />
                </TabsContent>
            </Tabs>

            <LiveConfirmDialog
                open={liveConfirmOpen}
                onOpenChange={setLiveConfirmOpen}
                onConfirm={() => { void applyLive(); }}
                busy={bot.busy}
                intro={<>Da questo momento gli ordini del bot Mike usano <b>denaro reale</b>.</>}
                warning="La struttura Under 3.5 / Over 4.5 perde con esattamente 4 gol: il live va attivato solo dopo il GO della certificazione paper (Costituzione §0)."
            />
        </PageShell>
    );
}
