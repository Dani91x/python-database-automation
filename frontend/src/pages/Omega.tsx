// ============================================================================
// /omega — Dashboard OMEGA: bot Correct Score LAY, set-and-forget.
// Obiettivo giornaliero → target per match → un lay per partita in finestra.
// Fonte di verità: Betfair/omega/COSTITUZIONE_OMEGA.md
// Realtime via Supabase (omega_control + omega_trades) + polling di sicurezza.
//
// GUSCIO CONDIVISO del design system di trading (components/trading):
//   PageShell → BotHeader (+ServiceHealthChip, ModeToggle) → ModeBanner →
//   DayBar → KpiRow → Tabs (Missione · Automatico · Manuale · Storico).
//
// REGOLA DEI NUMERI (audit 11/09 H-08): i KPI e la barra della giornata hanno
// UNA sola fonte, gli AGGREGATI dell'RPC (calcolati sul DB, origin-agnostici,
// con la stessa definizione di "giornata operativa" del servizio). Il client
// NON ricalcola operazioni/V/P dai trade caricati: contava anche le righe
// 'error', le riserve mai piazzate, le chiusure orfane e le partite vive di
// ieri, e finivano DUE numeri diversi nella stessa card. Il raggruppamento per
// partita serve alla TABELLA, non ai KPI.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import ManualPanel from '@/components/omega/ManualPanel';
import MissionPanel from '@/components/omega/MissionPanel';
import { useScanLiveFeedRows } from '@/lib/useScanLiveFeed';
import { TradingHistory } from '@/components/trading/TradingHistory';
import { MatchTradesTable } from '@/components/omega/MatchTradesTable';
import { PageShell } from '@/components/trading/PageShell';
import { BotHeader } from '@/components/trading/BotHeader';
import { ServiceHealthChip } from '@/components/trading/ServiceHealthChip';
import { ModeToggle } from '@/components/trading/ModeToggle';
import { ModeBanner } from '@/components/trading/ModeBanner';
import { LiveConfirmDialog } from '@/components/trading/LiveConfirmDialog';
import { StatTile, KpiRow, toneOf } from '@/components/trading/StatTile';
import { DayBar } from '@/components/trading/DayBar';
import { LoadingState, SectionCard } from '@/components/trading/EmptyState';
import { ActivityFeed, type ActivityRow } from '@/components/trading/ActivityFeed';
import { EquityCard } from '@/components/trading/EquityCard';
import { ParamsSheetBase, type ParamValues } from '@/components/trading/ParamsSheetBase';
import {
    groupTradesByMatch, filterMatchesForDay, summarizeMatches, romeDayOf, eventNamesFrom,
} from '@/lib/omegaMatches';
import { fmtMoney, fmtNum } from '@/lib/format';
import { T } from '@/lib/tradeStatus';
import { toastSettlement } from '@/lib/toasts';
import { SCANNER_STALE_MS } from '@/lib/safeBot';
import { fetchScanStatus, type ScanStatusRow } from '@/lib/safeStrategyScan';
import { fetchOmegaDaily, fetchOmegaDayTrades, romeDay, dayLabel } from '@/lib/dailyHistory';
import {
    TrendingUp, Zap, ShieldAlert, Activity, Lock,
} from 'lucide-react';
import {
    activateOmega, stopOmega, updateOmegaParams, fetchOmegaState, fetchOmegaTrades,
    subscribeOmega, buildEquitySeries, requestManual,
    OMEGA_PARAM_DEFAULTS, OMEGA_PARAM_GROUPS, omegaParamsPatch,
    activityMeta, activityLine, isHedging,
    type OmegaControl, type OmegaTrade, type OmegaParams, type OmegaMode, type OmegaStatus,
    type OmegaAggregates, type OmegaActivityRow,
} from '@/lib/omega';

/** quante righe di attività della giornata chiedere all'RPC (M-22) */
const ACTIVITY_PAGE = 60;
/**
 * §18: la vista di giornata non ha bisogno di tutto lo storico dei trade.
 * La finestra resta comunque larga (~6 giorni a 200 gambe/giorno) perché una
 * gamba di chiusura la cui APERTURA è fuori finestra diventerebbe una riga
 * orfana: le posizioni vive di giorni precedenti devono restare intere.
 */
const TRADES_DAY_LIMIT = 1200;
const TRADES_ALL_LIMIT = 3000;
/** §18: un burst di eventi realtime = UN reload (mai uno per evento) */
const REALTIME_DEBOUNCE_MS = 1200;

// =============================================================== main page
export default function Omega() {
    const [control, setControl] = useState<OmegaControl | null>(null);
    const [aggregates, setAggregates] = useState<OmegaAggregates | null>(null);
    const [trades, setTrades] = useState<OmegaTrade[]>([]);
    // attività del servizio (green-up, attese, ritenti…) dall'RPC di stato
    const [activity, setActivity] = useState<OmegaActivityRow[]>([]);
    const [activityMore, setActivityMore] = useState(0);
    // giornata a cui l'RPC ha filtrato l'attività (null = RPC senza v5)
    const [activityDay, setActivityDay] = useState<string | null>(null);
    const [activityLimit, setActivityLimit] = useState(ACTIVITY_PAGE);
    // §14: obiettivo storicizzato di OGGI (RPC) e filtro della tabella partite
    const [goalToday, setGoalToday] = useState<number | null>(null);
    const [goalSnapshot, setGoalSnapshot] = useState(false);
    const [showAllMatches, setShowAllMatches] = useState(false);
    // minuto/punteggio/quote LIVE dal feed dello scanner, con la FRESCHEZZA di
    // ogni riga: su un feed fermo non si decide un cash out
    const eventIds = useMemo(() => [...new Set(trades.map((t) => t.event_id))], [trades]);
    const liveRows = useScanLiveFeedRows(eventIds);
    const liveFeed = useMemo(() => {
        const out: Record<string, NonNullable<typeof liveRows[string]>['payload']> = {};
        for (const [id, r] of Object.entries(liveRows)) out[id] = r.payload;
        return out;
    }, [liveRows]);
    const feedUpdatedAt = useMemo(() => {
        const out: Record<string, string | null> = {};
        for (const [id, r] of Object.entries(liveRows)) out[id] = r.updated_at;
        return out;
    }, [liveRows]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    // salute del servizio: il feed dello scanner (fonte unica) + il battito Omega
    const [scanStatus, setScanStatus] = useState<ScanStatusRow | null>(null);
    const [nowMs, setNowMs] = useState(() => Date.now());
    const [navH, setNavH] = useState(52);

    // form inputs
    const [goalInput, setGoalInput] = useState(250);
    const [params, setParams] = useState<OmegaParams>(OMEGA_PARAM_DEFAULTS);
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
    // tab attivo (controllato: dallo Storico si torna all'Automatico sul trade vivo)
    const [tab, setTab] = useState<string>('mission');

    const seenSettled = useRef<Set<number>>(new Set());
    const initialized = useRef(false);
    // H-07: i parametri COME LI HA IL SERVIZIO: il "Salva" manda questi più le
    // modifiche dell'utente, mai i default della UI sopra i valori del servizio
    const serverParams = useRef<Record<string, unknown>>({});
    // limiti correnti (ref: le usa anche il reload del realtime)
    const limits = useRef({ trades: TRADES_DAY_LIMIT, activity: ACTIVITY_PAGE });
    limits.current = {
        trades: showAllMatches ? TRADES_ALL_LIMIT : TRADES_DAY_LIMIT,
        activity: activityLimit,
    };

    const status: OmegaStatus = control?.status ?? 'idle';
    const mode: OmegaMode = control?.mode ?? 'paper';
    const stats = control?.stats ?? {};

    async function reload() {
        const firstLoad = !initialized.current;
        const [st, tr] = await Promise.all([
            fetchOmegaState(limits.current.activity),
            fetchOmegaTrades(limits.current.trades),
        ]);
        setControl(st.control);
        setAggregates(st.aggregates);
        setTrades(tr);
        setActivity(Array.isArray(st.activity) ? st.activity : []);
        setActivityMore(Number(st.activity_more) || 0);
        setActivityDay(st.activity_day ?? null);
        setGoalToday(st.goal_today ?? null);
        setGoalSnapshot(st.goal_snapshot === true);
        if (st.control) {
            serverParams.current = (st.control.params ?? {}) as Record<string, unknown>;
        }
        if (st.control && firstLoad) {
            // sincronizza i form solo al primo caricamento (non sovrascrivere l'editing)
            setGoalInput(Number(st.control.daily_goal) || 250);
            setParams({ ...OMEGA_PARAM_DEFAULTS, ...(st.control.params as Partial<OmegaParams>) });
        }
        // popup incassi: al primo load NON notifica lo storico, solo i NUOVI settlement
        detectSettlements(tr, firstLoad);
        if (firstLoad) initialized.current = true;
        setLoading(false);
    }

    function detectSettlements(tr: OmegaTrade[], firstLoad: boolean) {
        const settled = tr.filter(t => t.settled_at && ['won', 'lost', 'void'].includes(t.status));
        if (firstLoad) {
            // primo caricamento: memorizza lo storico come "già visto", nessun toast
            settled.forEach(t => seenSettled.current.add(t.id));
            return;
        }
        for (const t of settled) {
            if (seenSettled.current.has(t.id)) continue;
            seenSettled.current.add(t.id);
            // M-04: il toast racconta l'esito della POSIZIONE quando il servizio
            // lo ha scritto (una gamba d'apertura "persa" può essere una
            // posizione in utile: prima arrivava un "⚠️ perso" falso + doppione)
            const posPnl = Number((t.meta as Record<string, unknown> | null)?.position_pnl);
            const posId = (t.meta as Record<string, unknown> | null)?.position_id;
            if (Number.isFinite(posPnl) && posId != null && t.closes_trade_id != null) {
                continue;   // la chiusura non notifica: lo fa l'apertura con il totale
            }
            // formato UNICO delle notifiche di regolazione (lib/toasts.ts):
            // i trade decisi a mano restano distinguibili da quelli del bot
            toastSettlement({
                name: t.event_name || t.event_id,
                pnl: t.status === 'void' ? 0 : (Number.isFinite(posPnl) ? posPnl : Number(t.pnl)),
                side: t.side,
                selection: t.runner_name,
                manual: t.origin === 'manual',
                statusLabel: 'Match VOID',
            });
        }
    }

    useEffect(() => {
        reload().catch(e => { toast.error('Errore caricamento Omega', { description: String(e?.message ?? e) }); setLoading(false); });
        // errori dei reload periodici: non silenziarli del tutto (dashboard
        // money-critical) ma nemmeno spammare — al massimo un toast al minuto.
        let lastErrToast = 0;
        const onReloadError = (e: unknown) => {
            const now = Date.now();
            if (now - lastErrToast > 60_000) {
                lastErrToast = now;
                toast.error('Aggiornamento dati Omega fallito', { description: String((e as Error)?.message ?? e) });
            }
        };
        // §18: il realtime di omega_trades arriva a raffiche (una riga per
        // gamba, per chiusura, per settlement): senza debounce ogni raffica
        // faceva N ricariche da migliaia di righe.
        let debounce: number | undefined;
        const unsub = subscribeOmega(() => {
            if (debounce !== undefined) return;
            debounce = window.setTimeout(() => {
                debounce = undefined;
                reload().catch(onReloadError);
            }, REALTIME_DEBOUNCE_MS);
        });
        const poll = setInterval(() => { reload().catch(onReloadError); }, 15_000);
        return () => {
            unsub(); clearInterval(poll);
            if (debounce !== undefined) window.clearTimeout(debounce);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // "mostra tutte" / "carica altre attività": si ricarica con il limite nuovo
    const reloadRef = useRef(reload);
    reloadRef.current = reload;
    useEffect(() => {
        if (!initialized.current) return;
        reloadRef.current().catch(() => { /* il polling riprova */ });
    }, [showAllMatches, activityLimit]);

    // orologio unico della pagina (età del feed e del battito)
    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 5_000);
        return () => window.clearInterval(t);
    }, []);

    // stato del feed dello scanner: nessuna chiamata Betfair, solo lo specchio DB
    useEffect(() => {
        let alive = true;
        const load = () => { fetchScanStatus().then((s) => { if (alive) setScanStatus(s); }).catch(() => {}); };
        load();
        const t = window.setInterval(load, 15_000);
        return () => { alive = false; window.clearInterval(t); };
    }, []);

    // ---- azioni
    async function handleStart() {
        setBusy(true);
        try {
            await activateOmega(mode, goalInput, omegaParamsPatch(serverParams.current, params as unknown as Record<string, unknown>) as Partial<OmegaParams>);
            toast.success('Omega avviato', { description: `Obiettivo ${fmtMoney(goalInput)}/giorno · modalità ${mode.toUpperCase()}` });
            await reload();
        } catch (e) {
            toast.error('Avvio fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(false); }
    }

    async function handleStop() {
        setBusy(true);
        try {
            await stopOmega();
            toast('Omega in arresto…');
            await reload();
        } catch (e) {
            toast.error('Stop fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(false); }
    }

    // Cash out di una gamba aperta: accoda la richiesta al servizio Omega
    // (kind 'cashout'), che piazza l'ordine di copertura e scrive il trade
    // 'hedged' + la riga di chiusura con closes_trade_id.
    // Un secondo cash out sullo stesso trade raddoppierebbe la copertura: si
    // tiene traccia delle richieste in volo per trade_id (ref = guardia
    // sincrona anti doppio click, stato = bottone spento al render).
    const cashoutInFlightRef = useRef<Set<number>>(new Set());
    const [cashoutPending, setCashoutPending] = useState<Set<number>>(() => new Set());
    function isCashOutPending(t: OmegaTrade): boolean {
        if (cashoutPending.has(t.id) || cashoutInFlightRef.current.has(t.id)) return true;
        if (isHedging(t.meta)) return true;
        // gamba di chiusura 'pending' = copertura in volo; una chiusura già
        // ABBINATA su una posizione con residuo NON blocca la chiusura del
        // residuo (M-06: prima il residuo restava inchiudibile dalla UI)
        return trades.some((x) => x.closes_trade_id === t.id && x.status === 'pending');
    }
    async function handleCashOut(t: OmegaTrade, args: { amount?: number; fraction?: number }) {
        if (isCashOutPending(t)) return;
        cashoutInFlightRef.current.add(t.id);
        setCashoutPending((prev) => new Set(prev).add(t.id));
        try {
            await requestManual('cashout', { trade_id: t.id, ...args });
            toast.success(T.cashOutSent, {
                description: `${t.event_name ?? t.event_id} · ${t.runner_name ?? ''}`.trim(),
            });
            await reload();
        } catch (e) {
            toast.error(T.cashOutFailed, { description: String((e as Error)?.message ?? e) });
        } finally {
            cashoutInFlightRef.current.delete(t.id);
            setCashoutPending((prev) => { const n = new Set(prev); n.delete(t.id); return n; });
        }
    }

    async function handleSaveParams(next: ParamValues) {
        setBusy(true);
        try {
            const goal = Number(next.__daily_goal);
            const draft = { ...next } as Record<string, unknown>;
            delete draft.__daily_goal;
            // H-07: patch sui parametri del SERVIZIO, non l'oggetto della UI
            const payload = omegaParamsPatch(serverParams.current, draft);
            setParams((p) => ({ ...p, ...(draft as Partial<OmegaParams>) }));
            if (Number.isFinite(goal) && goal >= 0) setGoalInput(goal);
            await updateOmegaParams({
                dailyGoal: Number.isFinite(goal) && goal >= 0 ? goal : undefined,
                params: payload as Partial<OmegaParams>,
            });
            toast.success('Parametri aggiornati', {
                description: `${Object.keys(payload).length} chiavi inviate al servizio`,
            });
            await reload();
        } catch (e) {
            toast.error('Salvataggio fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(false); }
    }

    async function applyMode(next: OmegaMode) {
        setBusy(true);
        try {
            await updateOmegaParams({ mode: next });
            toast[next === 'live' ? 'error' : 'success'](
                next === 'live' ? `🔴 ${T.modeLive} — soldi veri` : '🟢 Modalità PAPER (simulazione)',
            );
            await reload();
        } catch (e) {
            toast.error('Cambio modalità fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(false); setLiveConfirmOpen(false); }
    }

    function onToggleMode(next: OmegaMode) {
        if (next === 'live') setLiveConfirmOpen(true);
        else applyMode('paper');
    }

    // ---- derivati
    // H-08: TUTTI i numeri "soldi e contatori" vengono dagli AGGREGATI dell'RPC
    // (una sola fonte). `stats` è la fotografia del servizio: la si usa solo
    // dove l'RPC non ha il dato (target per gamba/partita) e, a bot FERMO, i
    // contatori di scansione sono dichiarati stantii (L-03).
    const agg = aggregates;
    const realizedTotal = Number(agg?.realized_profit ?? stats.realized_profit ?? 0);
    const realized = Number(agg?.realized_today ?? stats.realized_today ?? 0);
    // obiettivo di OGGI: snapshot storicizzato se c'è, altrimenti quello corrente
    const goal = Number(goalToday ?? control?.daily_goal ?? stats.goal ?? goalInput ?? 250);
    const operatingDay = romeDay();
    const openLiability = Number(agg?.open_liability ?? stats.open_liability ?? 0);
    const matchesTraded = Number(agg?.matches_traded ?? stats.matches_traded ?? 0);
    const legsToday = agg?.legs_today ?? stats.legs_today ?? null;
    const eventsToday = agg?.events_today ?? stats.events_today ?? null;
    const wonToday = agg?.won_today ?? stats.won_today ?? null;
    const lostToday = agg?.lost_today ?? stats.lost_today ?? null;
    const liveNow = agg?.live_now ?? stats.live_now ?? agg?.matches_open ?? null;
    const running = status === 'running' || status === 'stopping';
    // L-03: a bot fermo "Eventi oggi"/"Target" sono la fotografia dell'ultimo
    // ciclo: si dice, non si spaccia per un dato vivo
    const statsFresh = stats.bot_running !== false && running;
    // §14: partite (una riga = una partita) della giornata + vive di giorni precedenti
    const allMatches = useMemo(() => groupTradesByMatch(trades), [trades]);
    /**
     * Certificazione 11/09 — SENZA `omega_models_v5.sql` l'RPC non manda
     * `locked_pnl_open` né `reconciling_liability`, e l'intera riga KPI
     * «P&L bloccato» + «In verifica su Betfair» spariva: proprio i due numeri
     * che dicono quanto si è già perso e quanto è a esito ignoto.
     *
     * Ripiego: si calcolano dalle righe CARICATE (le stesse `meta` che legge
     * la RPC — `locked_pnl` a copertura completa, `liability` dei pending in
     * riconciliazione). È una STIMA perché la finestra dei trade è limitata,
     * e la UI lo dichiara: mai un numero senza provenienza.
     */
    const clientFallback = useMemo(() => summarizeMatches(allMatches), [allMatches]);
    const lockedFromRpc = agg?.locked_pnl_open ?? stats.locked_pnl_open ?? null;
    const reconcilingFromRpc = agg?.reconciling_liability ?? stats.reconciling_liability ?? null;
    /** true = i due numeri sono STIMATI dal client (migrazione v5 non applicata) */
    const lockedEstimated = lockedFromRpc == null;
    const lockedOpen = lockedFromRpc ?? clientFallback.pnl_locked ?? 0;
    // bloccato della GIORNATA (le posizioni piazzate oggi): è quello che
    // appartiene alla barra della giornata; il totale resta nel KPI
    const lockedToday = agg?.locked_pnl_open_today ?? stats.locked_pnl_open_today ?? null;
    const reconcilingLiab = Number(reconcilingFromRpc ?? clientFallback.reconciling_liability ?? 0);
    const todayMatches = useMemo(() => filterMatchesForDay(allMatches, operatingDay), [allMatches, operatingDay]);
    const shownMatches = showAllMatches ? allMatches : todayMatches;
    // riepilogo della TABELLA (quante righe sto guardando), non dei soldi: i
    // numeri di giornata restano quelli della RPC
    const shownSummary = useMemo(() => summarizeMatches(shownMatches), [shownMatches]);
    const shownTrades = useMemo(() => {
        if (showAllMatches) return trades;
        const ids = new Set(shownMatches.map((g) => g.event_id));
        return trades.filter((t) => ids.has(t.event_id));
    }, [trades, shownMatches, showAllMatches]);
    // equity della VISTA: la giornata (default) o tutto il caricato con "mostra tutte"
    const equity = useMemo(() => buildEquitySeries(shownTrades), [shownTrades]);
    // M-01/M-02: il nome della partita non è nel payload dell'attività (solo
    // event_id): lo risolviamo dai trade
    const eventNames = useMemo(() => eventNamesFrom(trades), [trades]);
    // l'RPC v5 manda SOLO la giornata; senza la migrazione si filtra qui
    const todayActivity = useMemo(
        () => activity.filter((a) => !a.ts || romeDayOf(a.ts) === operatingDay),
        [activity, operatingDay],
    );
    const activityRows: ActivityRow[] = useMemo(() => todayActivity.map((a) => {
        const evId = String((a.payload ?? {}).event_id ?? '');
        const name = eventNames[evId] ?? null;
        return { id: a.id, ts: a.ts, kind: String(a.kind), event_name: name, line: activityLine(a, name) };
    }), [todayActivity, eventNames]);

    // valori del pannello parametri: obiettivo + tutte le chiavi della whitelist
    const paramValues: ParamValues = useMemo(() => ({
        __daily_goal: goalInput,
        ...(params as unknown as Record<string, number | boolean | string>),
    }), [params, goalInput]);

    return (
        <PageShell
            title="Omega | Correct Score Bot"
            header={
                <BotHeader
                    bot="omega"
                    status={status}
                    running={running}
                    busy={busy}
                    onStart={handleStart}
                    onStop={handleStop}
                    onHeight={setNavH}
                    // certificazione 11/09: `status='running'` è quello che il DB
                    // DICHIARA. Senza battito il badge lo dice in faccia invece
                    // di lasciare "IN CORSA" su un servizio spento da ore.
                    heartbeatAt={control?.heartbeat_at}
                    nowMs={nowMs}
                    health={
                        <ServiceHealthChip
                            botName="Omega"
                            nowMs={nowMs}
                            feedUpdatedAt={scanStatus?.updated_at}
                            feedStaleMs={SCANNER_STALE_MS}
                            feedMissing={scanStatus === null}
                            heartbeatAt={control?.heartbeat_at}
                            counts={{ calcio: scanStatus?.payload?.calcio_inplay, tennis: scanStatus?.payload?.tennis_inplay }}
                            source={scanStatus?.payload?.source}
                            streamMarkets={scanStatus?.payload?.stream_markets}
                            dry={scanStatus?.payload?.dry}
                            lastError={scanStatus?.payload?.last_error ?? null}
                            // ciclo degradato: il servizio gira ma una fase è
                            // fallita (avviso ambra, non "servizio morto")
                            degraded={stats.degraded ?? null}
                        />
                    }
                    modeToggle={<ModeToggle mode={mode} onChange={onToggleMode} />}
                    params={
                        <ParamsSheetBase
                            title="Parametri Omega"
                            symbol={<span className="text-primary text-xl" aria-hidden>Ω</span>}
                            description="Limiti e unità sono quelli della whitelist del servizio: un valore fuori range viene clampato e dichiarato. «Salva parametri» invia i valori del servizio più le TUE modifiche, non i default della UI."
                            groups={OMEGA_PARAM_GROUPS_UI}
                            values={paramValues}
                            onSave={handleSaveParams}
                            onReset={() => ({ __daily_goal: 250, ...(OMEGA_PARAM_DEFAULTS as unknown as Record<string, number | boolean | string>) })}
                            busy={busy}
                            triggerTestId="omega-params-trigger"
                            footer={<>I tre cap (liability/partita, stop-loss, liability aperta) sono <b>OFF di default</b>: Omega è set-and-forget. Mettili &gt; 0 per attivarli.</>}
                        />
                    }
                />
            }
        >
            {loading ? (
                <LoadingState label="caricamento Omega…" />
            ) : (
                <>
                    <ModeBanner
                        mode={mode}
                        liveText={<>Omega piazza <b>lay reali</b> sul Correct Score con <b>soldi veri</b>.</>}
                        paperText="simulazione fedele: coda, liquidità, betDelay e protezioni identiche al live, nessun denaro reale."
                        error={control?.error ?? null}
                    />

                    {/* giornata operativa: ogni giornata riparte da 0 (era sepolta nel tab Automatico) */}
                    <DayBar
                        testId="omega-daily-mission"
                        ids={{ line: 'omega-mission-line', day: 'omega-operating-day', remaining: 'omega-remaining', goalHit: 'omega-goal-hit', counts: 'omega-today-legs' }}
                        dayLabel={dayLabel(operatingDay, { weekday: true })}
                        realized={realized}
                        goal={goal}
                        matches={eventsToday}
                        operations={legsToday}
                        won={wonToday}
                        lost={lostToday}
                        live={liveNow}
                        openLiability={openLiability}
                        lockedPnl={lockedToday ?? lockedOpen}
                        note={goalSnapshot
                            ? 'numeri dalla RPC (giornata Europe/Rome): il realizzato riparte da zero ogni giorno e conta SOLO le posizioni piazzate oggi'
                            : 'obiettivo non ancora storicizzato per oggi: è quello corrente del servizio'}
                    />

                    <KpiRow tiles={5}>
                        <StatTile label={T.pnlToday} value={fmtMoney(realized, { signed: true })} tone={toneOf(realized)} icon={<TrendingUp className="w-3.5 h-3.5" />} sub={`totale storico ${fmtMoney(realizedTotal, { signed: true })}`} testId="omega-kpi-pnl" />
                        <StatTile
                            label="Target / operazione"
                            value={fmtMoney(stats.target_leg ?? stats.target_match)}
                            tone="gold"
                            icon={<Zap className="w-3.5 h-3.5" />}
                            sub={statsFresh
                                ? `${stats.legs_remaining ?? '—'} operazioni · ${stats.matches_remaining ?? '—'} partite rimaste · ${fmtMoney(stats.target_match)}/partita`
                                : 'bot fermo: nessun target in corso'}
                            testId="omega-kpi-target"
                        />
                        <StatTile
                            label="Eventi in finestra"
                            value={statsFresh ? String(stats.events_total ?? '—') : '—'}
                            icon={<Activity className="w-3.5 h-3.5" />}
                            sub={statsFresh ? 'ultimo ciclo dello scanner' : 'disponibile a bot avviato'}
                            testId="omega-kpi-events"
                        />
                        <StatTile
                            label="Operazioni oggi"
                            value={legsToday != null ? fmtNum(legsToday) : '—'}
                            sub={`${wonToday ?? 0}V · ${lostToday ?? 0}P · ${liveNow ?? 0} partite vive · storico ${fmtNum(matchesTraded)}`}
                            testId="omega-kpi-legs"
                        />
                        <StatTile
                            label={T.openLiability}
                            value={fmtMoney(openLiability)}
                            tone="danger"
                            icon={<ShieldAlert className="w-3.5 h-3.5" />}
                            sub={reconcilingLiab > 0
                                ? `di cui ${fmtMoney(reconcilingLiab)} in verifica su Betfair`
                                : 'esposizione a coda (copertura completa = rischio 0)'}
                            testId="omega-kpi-liability"
                        />
                    </KpiRow>
                    {/* la riga c'è SEMPRE: senza la v5 i due numeri sono stimati
                        dalle righe caricate e la UI lo dichiara (mai nascondere
                        quanto si è già perso e quanto è a esito ignoto) */}
                    <KpiRow tiles={2}>
                        <StatTile
                            label={T.lockedPnl}
                            value={fmtMoney(lockedOpen, { signed: true })}
                            tone={toneOf(lockedOpen)}
                            icon={<Lock className="w-3.5 h-3.5" />}
                            sub={lockedEstimated
                                ? 'stimato dal client dalle righe caricate (applica omega_models_v5.sql per il valore dal DB)'
                                : lockedToday != null
                                    ? `di oggi ${fmtMoney(lockedToday, { signed: true })} · già bloccato sulle posizioni vive: non cambia più`
                                    : 'già bloccato sulle posizioni vive: non cambia più, si incassa al fischio finale'}
                            testId="omega-kpi-locked"
                        />
                        <StatTile
                            label="In verifica su Betfair"
                            value={fmtMoney(reconcilingLiab)}
                            tone={reconcilingLiab > 0 ? 'danger' : 'plain'}
                            sub={lockedEstimated
                                ? 'stimato dal client (applica omega_models_v5.sql)'
                                : reconcilingLiab > 0
                                    ? 'ordini reali a esito ancora ignoto: contano nella liability'
                                    : 'nessun ordine in sospeso'}
                            testId="omega-kpi-reconciling"
                        />
                    </KpiRow>

                    <Tabs value={tab} onValueChange={setTab} className="w-full">
                        <TabsList className="sticky z-30" style={{ top: navH }}>
                            <TabsTrigger value="mission" aria-label="Missione">🎯 Missione</TabsTrigger>
                            <TabsTrigger value="auto" aria-label="Automatico">⚙️ Automatico</TabsTrigger>
                            <TabsTrigger value="manual" aria-label="Manuale">✋ Manuale</TabsTrigger>
                            <TabsTrigger value="storico" aria-label="Storico">📅 Storico</TabsTrigger>
                        </TabsList>

                        <TabsContent value="mission" className="mt-3">
                            {/* mode paper/live dal toggle globale in alto (control.mode) */}
                            <MissionPanel mode={mode} dailyGoal={goal} />
                        </TabsContent>

                        <TabsContent value="auto" className="mt-3 space-y-5">
                            <EquityCard
                                series={equity}
                                scope={showAllMatches ? 'tutte le partite caricate' : `giornata ${dayLabel(operatingDay, { year: false })}`}
                                emptyLabel="nessun match ancora regolato — la curva compare al primo incasso"
                                label="Equity curve Omega"
                            />

                            {/* partite: UNA riga per partita (1T + 2T, risultati reali, P&L) */}
                            <SectionCard
                                testId="omega-matches-card"
                                icon={<Activity className="w-4 h-4 text-primary" aria-hidden />}
                                title={showAllMatches ? 'Tutte le partite' : 'Partite di oggi'}
                                count={shownMatches.length}
                                note={
                                    // H-08: gli stessi numeri della barra e dei KPI (RPC)
                                    <span data-testid="omega-matches-summary">
                                        · {legsToday ?? shownSummary.legs} operazioni oggi · {wonToday ?? 0}V {lostToday ?? 0}P
                                        {lockedOpen != null && lockedOpen !== 0 && ` · ${T.lockedPnl} ${fmtMoney(lockedOpen, { signed: true })}`}
                                        {openLiability > 0 && ` · ${T.openLiability} ${fmtMoney(openLiability)}`}
                                    </span>
                                }
                                actions={
                                    <>
                                        <span className="text-[11px] text-slate-500">ogni riga: gamba 1° tempo + gamba 2° tempo, quote live, risultati reali, P&amp;L della partita</span>
                                        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowAllMatches((v) => !v)} data-testid="omega-matches-toggle">
                                            {showAllMatches ? 'solo oggi' : 'mostra tutte'}
                                        </Button>
                                    </>
                                }
                            >
                                <MatchTradesTable
                                    trades={shownTrades}
                                    liveFeed={liveFeed}
                                    feedUpdatedAt={feedUpdatedAt}
                                    nowMs={nowMs}
                                    liveView
                                    commission={params.commission_pct}
                                    onCashOut={handleCashOut}
                                    isCashOutPending={isCashOutPending}
                                    day={operatingDay}
                                    emptyText={showAllMatches ? 'nessun trade ancora — avvia il bot e attendi la finestra dei match' : 'nessuna partita oggi — avvia il bot e attendi la finestra dei match (le giornate passate sono nello Storico)'}
                                />
                            </SectionCard>

                            {/* attività del servizio: green-up, attese, conferme, ritenti */}
                            <SectionCard
                                testId="omega-activity"
                                icon={<Zap className="w-4 h-4 text-primary" aria-hidden />}
                                title={T.activityToday}
                                count={activityRows.length}
                                actions={
                                    <>
                                        <span className="text-[11px] text-slate-500">
                                            ogni passo del servizio: ingressi, coda ordini, verifiche, green-up, regolamenti
                                            {activityDay ? ` · giornata ${dayLabel(activityDay, { year: false })}` : ' · filtro di giornata lato client (migrazione v5 non applicata)'}
                                        </span>
                                        {activityMore > 0 && (
                                            <Button
                                                variant="ghost" size="sm" className="h-7 text-xs"
                                                onClick={() => setActivityLimit((n) => n + 120)}
                                                disabled={busy}
                                                data-testid="omega-activity-more"
                                            >
                                                carica altre ({activityMore})
                                            </Button>
                                        )}
                                    </>
                                }
                            >
                                <ActivityFeed
                                    rows={activityRows}
                                    metaOf={(k) => activityMeta(k)}
                                    filterable
                                    rowTestId="omega-activity-row"
                                />
                            </SectionCard>
                        </TabsContent>

                        <TabsContent value="manual" className="mt-3">
                            <ManualPanel />
                        </TabsContent>

                        <TabsContent value="storico" className="mt-3">
                            <TradingHistory
                                variant="omega"
                                fetchDaily={fetchOmegaDaily}
                                fetchDayTrades={fetchOmegaDayTrades}
                                onGoLive={() => setTab('auto')}
                            />
                        </TabsContent>
                    </Tabs>
                </>
            )}

            {/* conferma LIVE (soldi veri) */}
            <LiveConfirmDialog
                open={liveConfirmOpen}
                onOpenChange={setLiveConfirmOpen}
                onConfirm={() => applyMode('live')}
                busy={busy}
                intro={<>Omega inizierà a piazzare <b>lay reali</b> sul Correct Score con denaro vero.</>}
                warning="Ricorda §9 della Costituzione: profit piccolo ~98%, ma perdita grande ~1–2% (coda pesante). La liability aperta può essere ingente."
            />
        </PageShell>
    );
}

// obiettivo giornaliero in cima al pannello (non è un `params` della whitelist:
// viaggia sulla colonna dedicata `omega_control.daily_goal`)
const OMEGA_PARAM_GROUPS_UI = [
    {
        label: 'Obiettivo',
        note: 'quanto deve produrre la giornata: il servizio ne ricava il target per partita e per gamba.',
        fields: [{
            key: '__daily_goal', label: 'Obiettivo giornaliero (€)', type: 'number' as const,
            min: 0, max: 1000000, step: 10,
            hint: 'storicizzato a fine giornata: lo Storico giudica "centrato" solo sull’obiettivo di QUEL giorno',
        }],
    },
    ...OMEGA_PARAM_GROUPS,
];
