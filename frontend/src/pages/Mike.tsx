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
import { MikeEventPnlTable } from '@/components/mike/MikeEventPnlTable';
import { SectionFilter, useSectionFilter } from '@/components/trading/SectionFilter';
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
    dayResultCounts, groupMikeTrades, groupsOfDay, lockedPnlTotal, groupMikeTradesByEvent,
    MIKE_TRADES_LIMIT,
    type MikeEvent, type MikeMode, type MikeRequestKind, type MikeStatus,
} from '@/lib/mike';

const REQUEST_KINDS: MikeRequestKind[] = ['cashout', 'flatten', 'skip_event', 'resume_event', 'cancel'];

// R2 — senza `migrations/mike_history_v2.sql` le RPC dello storico rispondono
// «function trading_daily_history(...) is not unique»: un codice nudo in una
// pagina vuota. Qui l'errore diventa una riga che dice COSA FARE.
const fetchDailyReadable = withMikeHistoryError(fetchMikeDaily);
const fetchDayTradesReadable = withMikeHistoryError(fetchMikeDayTrades);

// =============================================================== main page
/** id delle sezioni della scheda Partite: entrano in localStorage, stabili. */
const SEZIONI_PARTITE = ['pre', 'live'] as const;

export default function Mike() {
    const bot = useMike({ onError: (m) => toast.error('Bot Mike', { description: m }) });
    const [nowMs, setNowMs] = useState(() => Date.now());
    const [scanStatus, setScanStatus] = useState<ScanStatusRow | null>(null);
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
    const [tab, setTab] = useState('partite');
    // filtri della scheda Partite: la scelta sopravvive al ricaricamento
    const filtro = useSectionFilter('mike.partite.nascoste', SEZIONI_PARTITE);
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
    // CERT. 13/09, difetto B3 — fail-CLOSED. Con `updated_at` non parsabile
    // `Date.parse` da' NaN, e `NaN > soglia` e' false: il feed risultava FRESCO e
    // i bottoni con soldi veri restavano tutti accesi su prezzi di chissà quando.
    // Un dato illeggibile e' un dato vecchio, non un dato buono.
    const scannerAge = useMemo(() => {
        const iso = scanStatus?.updated_at;
        if (!iso) return null;
        const ms = Date.parse(iso);
        if (!Number.isFinite(ms)) return null;
        return Math.max(0, (nowMs - ms) / 1000);
    }, [scanStatus?.updated_at, nowMs]);
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
    // P&L bloccato della giornata: somma dei `live.locked` DICHIARATI dalle
    // partite vive. `locked` assente = "niente ancora bloccato su questa
    // partita", NON zero: sommarlo come 0 faceva scrivere "+0,00 €" nella barra
    // mentre ogni card diceva "—" (audit UI 3).
    // CODE REVIEW 13/09, ALTO: le RIGHE erano filtrate per modalità, gli EVENTI
    // no. Il «P&L bloccato» della barra sommava quindi euro veri e simulati —
    // proprio il difetto che la certificazione dichiarava chiuso, ma solo a metà.
    const attiveDelMio = useMemo(
        () => active.filter((e) => String(e.mode ?? 'paper') === mode),
        [active, mode],
    );
    const locked = useMemo(() => lockedPnlTotal(attiveDelMio), [attiveDelMio]);
    const lockedPnl = locked.value;
    const dailyStop = Number(bot.params.daily_loss_stop ?? 0);
    // OPERAZIONI della giornata = CICLI (1 apertura + le sue chiusure), mai le
    // righe di database: è il numero che si legge anche nella scheda Trade e
    // nello Storico (audit UI 1).
    // ===================================================================
    // PAPER e SOLDI VERI NON SI SOMMANO MAI (certificazione 13/09)
    // ===================================================================
    // Le righe arrivano di entrambe le modalità. Finché Mike è girato solo in
    // paper è stato innocuo; al primo giorno in live «P&L oggi» e «P&L totale»
    // avrebbero sommato euro veri e simulati senza che niente lo dicesse.
    // Qui si tiene SOLO la modalità con cui il bot sta girando, e le righe
    // dell'altra si dichiarano invece di sparire in silenzio.
    const righeDelMio = useMemo(
        () => bot.trades.filter((t) => String(t.mode ?? 'paper') === mode),
        [bot.trades, mode],
    );
    const righeAltraModalita = bot.trades.length - righeDelMio.length;
    // partite ancora VIVE armate nell'ALTRA modalità: il `mode` si congela
    // all'arming, quindi riportare il toggle su paper NON ferma quelle già
    // avviate in live — continuano a operare con SOLDI VERI mentre il banner
    // della pagina dice PAPER. Il servizio lo conta, qui si grida.
    const partiteAltraModalita = Number(
        (stats as Record<string, unknown> | null)?.eventi_altra_modalita ?? 0);
    const liveAbilitato = (stats as Record<string, unknown> | null)?.live_abilitato;

    const tradeGroups = useMemo(() => groupMikeTrades(righeDelMio), [righeDelMio]);
    const dayOperations = useMemo(
        () => groupsOfDay(tradeGroups, bot.dayStartMs).length,
        [tradeGroups, bot.dayStartMs],
    );
    // I CICLI DELLA GIORNATA, una volta sola: li usano la scheda Operazioni e le
    // due schede Risultati, che sono la stessa domanda con un filtro diverso.
    const gruppiOggi = useMemo(
        () => groupsOfDay(tradeGroups, bot.dayStartMs),
        [tradeGroups, bot.dayStartMs],
    );
    // le linguette contano PARTITE, non righe: è quello che si vede aprendole
    const partiteOperate = useMemo(
        () => groupMikeTradesByEvent(gruppiOggi).length, [gruppiOggi]);
    const risultatiPre = useMemo(
        () => groupMikeTradesByEvent(gruppiOggi, 'pre'), [gruppiOggi]);
    const risultatiLive = useMemo(
        () => groupMikeTradesByEvent(gruppiOggi, 'live'), [gruppiOggi]);
    // UN SOLO numero di "operazioni di oggi" in tutta la pagina: barra giornata,
    // linguetta e riepilogo della scheda. Il DB è la fonte (non ha il tetto di
    // 500 righe della RPC); senza migrazione si ripiega sul conto dal client.
    const operationsToday = agg?.cycles_today ?? dayOperations;
    // V/P della giornata: dalla RPC v2; senza migrazione dal client (dichiarato)
    const clientCounts = useMemo(
        () => dayResultCounts(righeDelMio, bot.dayStartMs), [righeDelMio, bot.dayStartMs]);
    const countsFromClient = agg?.won_today == null && agg?.lost_today == null;
    const wonToday = agg?.won_today ?? clientCounts.won;
    const lostToday = agg?.lost_today ?? clientCounts.lost;
    // battito del servizio: oltre 45 s le `stats` sono una fotografia vecchia
    const hbMs = bot.control?.heartbeat_at ? Date.parse(bot.control.heartbeat_at) : NaN;
    const serviceAlive = Number.isFinite(hbMs) && nowMs - hbMs <= 45_000;
    const equity = useMemo(
        () => mikeEquitySeries(righeDelMio, bot.dayStartMs), [righeDelMio, bot.dayStartMs]);
    // TETTO DELLA RPC: oltre 500 righe la giornata arriva TRONCATA, e allora il
    // netto di una partita può essere parziale senza che si veda. Va detto in
    // ogni scheda che somma righe, non solo in una (audit 13/09).
    const avvisoRighe = (bot.trades.length >= MIKE_TRADES_LIMIT || righeAltraModalita > 0) ? (
        <div className="mb-2 space-y-1" data-testid="mike-avvisi-righe">
            {bot.trades.length >= MIKE_TRADES_LIMIT && (
                <p className="rounded-md border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200"
                   data-testid="mike-righe-troncate">
                    ⚠️ Arrivate {MIKE_TRADES_LIMIT} righe, il tetto della lettura: di qualche partita
                    potrebbero mancare operazioni e il suo netto essere incompleto. Lo Storico non ha
                    questo limite.
                </p>
            )}
            {righeAltraModalita > 0 && (
                <p className="rounded-md border border-sky-400/30 bg-sky-500/10 px-2 py-1 text-[11px] text-sky-200"
                   data-testid="mike-righe-altra-modalita">
                    {righeAltraModalita} {righeAltraModalita === 1 ? 'operazione' : 'operazioni'} in{' '}
                    <b>{mode === 'live' ? 'paper' : 'live'}</b> non {righeAltraModalita === 1 ? 'è elencata' : 'sono elencate'}:
                    {' '}questa pagina mostra solo la modalità con cui il bot sta girando.
                    Euro veri e simulati non si sommano mai.
                </p>
            )}
        </div>
    ) : null;

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
    // CERT. 13/09, difetti B1 e B2 — money-critical, tutti e due sul percorso
    // che manda ordini veri.
    //
    // B1: questa funzione non restituiva una Promise. I bottoni fanno
    // `await onCashOut()`, che quindi risolveva SUBITO su `undefined`: il
    // dialogo si chiudeva come se fosse andato tutto bene, il `catch` non
    // scattava mai e il messaggio «la posizione è ancora aperta, controlla su
    // Betfair» era codice irraggiungibile. Una chiusura FALLITA sembrava
    // riuscita. Ora la Promise viene restituita e l'errore RILANCIATO.
    //
    // B2: in live non confermato si usciva con un `return` silenzioso, ma
    // l'utente aveva gia' fatto i due click di conferma e il dialogo si
    // chiudeva: il bottone diceva di aver chiuso, il servizio non riceveva
    // niente. Ora si lancia, cosi' il dialogo resta aperto e lo dice.
    const onRequest = useCallback(async (kind: MikeRequestKind, eventId: string) => {
        // TUTTE le azioni che toccano la partita, non solo cash out e flatten:
        // `resume_event` in live rimette in gioco una partita con soldi veri e
        // `cancel` ritira ordini reali dal book (audit paper/live, difetto P7).
        //
        // CODE REVIEW 13/09, CRITICO: la modalità che conta è quella della
        // PARTITA, non il toggle della pagina. Il `mode` si congela all'arming:
        // una partita armata in live resta live anche col toggle su paper, e
        // il backend la esegue con soldi veri. Chiavare la conferma sul toggle
        // significava lasciar passare un ordine reale con UN SOLO clic.
        const modePartita = bot.events.find((e) => e.event_id === eventId)?.mode ?? mode;
        if ((modePartita === 'live' || mode === 'live') && !bot.liveConfirmed) {
            setLiveConfirmOpen(true);
            toast.warning('Conferma la modalità LIVE prima di operare con soldi veri');
            throw new Error('Modalità LIVE non confermata: nessun ordine è stato inviato.');
        }
        await bot.request(kind, eventId);
    }, [mode, bot.liveConfirmed, bot.request, bot.events]);

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
            /* CODE REVIEW 13/09, CRITICO: la modalità della PARTITA, non il
               toggle della pagina. Il `mode` si congela quando la partita viene
               armata: una partita in live resta live anche col toggle su paper,
               e il backend la esegue con soldi veri. Passare il toggle qui
               significava mostrare una card "paper" e bottoni senza doppia
               conferma su una posizione reale. */
            mode={(e.mode as MikeMode) ?? mode}
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

            {/* ===============================================================
                DUE ALLARMI CHE NON DEVONO MAI MANCARE (certificazione 13/09)
                ===============================================================
                1) Il `mode` si congela sulla PARTITA quando viene armata.
                   Riportare il toggle su paper NON ferma quelle già avviate in
                   live: continuano a coprirsi, chiudere e fare cash-out con
                   soldi veri mentre il banner qui sopra dice PAPER. È il modo
                   più silenzioso che c'è di perdere denaro.
                2) In live l'interruttore fisico del processo (MIKE_LIVE_ENABLED)
                   deve essere acceso, altrimenti nessun ordine parte davvero:
                   meglio saperlo prima di credere di stare operando. */}
            {partiteAltraModalita > 0 && (
                <div
                    role="alert"
                    data-testid="mike-allarme-modalita-mista"
                    className="rounded-lg border border-red-500/50 bg-red-500/15 px-3 py-2 text-sm text-red-200"
                >
                    <b>⚠️ {partiteAltraModalita}{' '}
                    {partiteAltraModalita === 1 ? 'partita sta operando' : 'partite stanno operando'}{' '}
                    in {mode === 'live' ? 'PAPER' : 'LIVE'}</b>
                    {mode !== 'live' && <> — con <b>soldi veri</b>, anche se il bot adesso è in paper.</>}
                    {' '}La modalità si fissa quando la partita viene armata e non cambia più:
                    quelle già avviate finiscono il loro ciclo con le regole di allora.
                    {mode !== 'live' && ' Per fermarle davvero serve chiuderle a mano dalle loro schede.'}
                </div>
            )}
            {mode === 'live' && liveAbilitato === false && (
                <div
                    role="alert"
                    data-testid="mike-live-non-abilitato"
                    className="rounded-lg border border-amber-400/50 bg-amber-500/15 px-3 py-2 text-sm text-amber-200"
                >
                    <b>Modalità LIVE, ma il processo NON è abilitato a piazzare ordini reali.</b>{' '}
                    L'interruttore di sicurezza <code>MIKE_LIVE_ENABLED</code> è spento: il bot
                    calcola tutto ma ogni ordine viene bloccato prima di partire. Per operare
                    davvero impostalo a <code>1</code> nel file <code>.env</code> e riavvia l'app.
                </div>
            )}

            {/* UNA semantica, dichiarata: partite = EVENTI con almeno una posizione
                piazzata oggi; operazioni = CICLI aperti oggi (1 ciclo = 1 riga di
                apertura + le sue chiusure); V/P = cicli già chiusi, la cui somma
                è il P&L realizzato di oggi. Sono numeri diversi da "Partite
                seguite" dei KPI, che conta le partite in lavorazione ADESSO. */}
            <DayBar
                dayLabel={dayLabel(operatingDay, { weekday: true })}
                realized={realizedToday}
                realizedTotal={realizedTotal}
                matches={agg?.events_today ?? active.length}
                operations={operationsToday}
                won={wonToday}
                lost={lostToday}
                live={agg?.live_now ?? sections.live.length}
                openLiability={openLiability}
                lockedPnl={lockedPnl}
                note={countsFromClient
                    ? 'partite con posizione piazzata oggi · operazioni = cicli aperti oggi · V/P stimati dal client: applica migrations/mike_bot_v2.sql'
                    : 'partite con almeno una posizione piazzata oggi · operazioni = cicli aperti oggi · V/P = cicli già chiusi, la loro somma è il realizzato'}
            />

            <KpiRow loading={bot.loading}>
                <StatTile
                    label="Partite seguite ora"
                    value={String(active.length)}
                    tone="teal"
                    icon={<Layers className="w-3.5 h-3.5" />}
                    sub={`${sections.pre.length} prima del fischio · ${sections.live.length} in gioco · ${withPosition} con posizione aperta`}
                    testId="mike-kpi-matches"
                />
                <StatTile
                    label="Posizioni aperte"
                    value={String(agg?.open_count ?? stats?.trades_open ?? 0)}
                    icon={<Activity className="w-3.5 h-3.5" />}
                    // MAI "N righe caricate": un conteggio di righe di database
                    // non è un numero da trader (audit UI 1).
                    sub={reconciling > 0
                        ? <span className="text-fuchsia-300">{reconciling} in verifica su Betfair</span>
                        : 'cicli con capitale ancora esposto'}
                />
                <StatTile
                    label={T.pnlToday}
                    value={fmtMoney(realizedToday, { signed: true })}
                    tone={toneOf(realizedToday)}
                    icon={<TrendingUp className="w-3.5 h-3.5" />}
                    // lo STOP è una soglia sul P&L della giornata: sta qui, non
                    // dentro la liability (che è il capitale esposto adesso).
                    sub={stats?.daily_stop
                        ? <span className="text-rose-300 font-semibold" data-testid="mike-daily-stop">STOP giornaliero ATTIVO · solo chiusure</span>
                        : <span data-testid="mike-pnl-today-sub">
                            {dayLabel(operatingDay, { year: false })} · Europe/Rome
                            {dailyStop > 0 && <> · stop a {fmtMoney(-dailyStop, { signed: true })}</>}
                        </span>}
                />
                <StatTile label={T.pnlTotal} value={fmtMoney(realizedTotal, { signed: true })} tone={toneOf(realizedTotal)} />
                <StatTile
                    label={T.openLiability}
                    value={fmtMoney(openLiability)}
                    tone="danger"
                    icon={<ShieldAlert className="w-3.5 h-3.5" />}
                    // UN concetto solo: quanto capitale è esposto ADESSO e DA
                    // DOVE arriva il numero (audit UI 4).
                    sub={<span data-testid="mike-liability-sub">
                        {liabilityFromRows
                            ? <span className="text-amber-300">stimata dalle righe (servizio da riavviare)</span>
                            : 'perdita peggiore sulle posizioni aperte, netta dal servizio'}
                        {reconciling > 0 ? ` · di cui ${reconciling} in verifica` : ''}
                        {liabilityStale && <span className="text-amber-300"> · dato stantio</span>}
                    </span>}
                />
                <StatTile
                    label={T.lockedPnl}
                    value={lockedPnl == null ? '—' : fmtMoney(lockedPnl, { signed: true })}
                    tone={lockedPnl == null ? 'plain' : toneOf(lockedPnl)}
                    sub={lockedPnl == null
                        ? 'nessuna partita ha ancora un risultato bloccato'
                        : `già bloccato su ${locked.known} ${locked.known === 1 ? 'partita' : 'partite'}${locked.pending > 0 ? ` · ${locked.pending} ancora da decidere` : ''}`}
                    testId="mike-kpi-locked"
                />
                <StatTile
                    label="Ultimo ciclo"
                    value={fmtTime(stats?.last_cycle, { seconds: true })}
                    tone={serviceAlive ? 'plain' : 'danger'}
                    sub={!serviceAlive
                        ? <span className="text-red-300" data-testid="mike-service-stale">servizio senza battito: riavvia l’app desktop</span>
                        : stats?.scanner_age_s != null ? `feed aggiornato ${fmtNum(stats.scanner_age_s, 0)} s fa` : 'feed: nessun dato'}
                    testId="mike-kpi-cycle"
                />
            </KpiRow>

            <Tabs value={tab} onValueChange={setTab} className="w-full">
                <TabsList className="sticky z-30" style={{ top: navH }}>
                    {/* ogni contatore è lo STESSO numero della scheda che apre:
                        Partite = seguite ora, Operazioni = PARTITE con operazioni
                        nella giornata, Risultati = partite con cicli chiusi prima
                        del fischio / in gioco. Mai conteggi di righe (audit UI 1).

                        13/09 — «Regolate» non esiste più: era una terza lista di
                        card che ripeteva le stesse partite. Adesso ogni partita
                        finisce nei Risultati della fase in cui ha operato, e in
                        ENTRAMBE se ha operato in entrambe. */}
                    <TabsTrigger value="partite" aria-label={`Partite (${active.length})`}>⚽ Partite ({active.length})</TabsTrigger>
                    <TabsTrigger value="trade" aria-label={`Operazioni (${partiteOperate})`}>📋 Operazioni ({partiteOperate})</TabsTrigger>
                    <TabsTrigger value="risultati-pre" aria-label={`Risultati Pre-Match (${risultatiPre.length})`}>⏱ Risultati Pre-Match ({risultatiPre.length})</TabsTrigger>
                    <TabsTrigger value="risultati-live" aria-label={`Risultati Live (${risultatiLive.length})`}>🔴 Risultati Live ({risultatiLive.length})</TabsTrigger>
                    <TabsTrigger value="attivita" aria-label="Attività">🧾 Attività</TabsTrigger>
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
                            {/* FILTRI (13/09, richiesta utente): con molte partite seguite la
                                sezione che interessa finiva sotto la piega. Il CONTEGGIO resta
                                visibile anche a sezione nascosta e l'ultima accesa non si spegne. */}
                            <SectionFilter
                                testId="mike-filtro-sezioni"
                                options={[
                                    { id: 'pre', label: '⏱ Pre-match', count: sections.pre.length,
                                      activeCls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' },
                                    { id: 'live', label: '🔴 Live', count: sections.live.length,
                                      activeCls: 'bg-violet-500/15 text-violet-300 border-violet-500/40' },
                                ]}
                                hidden={filtro.hidden}
                                onToggle={filtro.toggle}
                            />

                            {/* SEZIONE 1 — sempre la prima, anche vuota: l'occhio sa dove guardare */}
                            {filtro.isVisible('pre') && (
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
                            )}

                            {/* SEZIONE 2 — le partite in gioco: entrano qui al fischio d'inizio e restano */}
                            {filtro.isVisible('live') && (
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
                            )}

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
                    <MikeEventPnlTable
                        gruppi={gruppiOggi}
                        titolo="Operazioni della giornata"
                        icona={<Layers className="w-4 h-4 text-sky-300" aria-hidden />}
                        testId="mike-operazioni"
                        onApriScheda={openEventCard}
                        avviso={avvisoRighe}
                        nota={
                            <>Una riga per PARTITA col netto delle sue operazioni, commissione già tolta.
                            Clicca per aprire i cicli e gli ordini. {T.operatingDay}{' '}
                            {dayLabel(operatingDay, { weekday: true })} · {operationsToday}{' '}
                            {operationsToday === 1 ? 'ciclo' : 'cicli'} in totale.</>
                        }
                        vuoto={<>Nessuna operazione nella {T.operatingDay} ({dayLabel(operatingDay, { weekday: true })}).</>}
                    />
                    <EquityCard
                        series={equity}
                        scope={`${T.operatingDay} ${dayLabel(operatingDay, { year: false })}`}
                        emptyLabel="nessun trade ancora regolato oggi — la curva compare al primo incasso"
                        label="Equity curve di Mike"
                    />
                </TabsContent>

                <TabsContent value="risultati-pre" className="mt-3 space-y-3">
                    <MikeEventPnlTable
                        gruppi={gruppiOggi}
                        fase="pre"
                        titolo="Risultati Pre-Match"
                        icona={<span aria-hidden>⏱</span>}
                        testId="mike-risultati-pre"
                        onApriScheda={openEventCard}
                        avviso={avvisoRighe}
                        nota={
                            <>Cicli aperti e chiusi PRIMA del fischio d'inizio: ingresso sull'Under 3.5 e
                            uscita a +{String(bot.params.pre_green_ticks ?? 2)} tick. Una partita che ha
                            operato anche in gioco compare pure in «Risultati Live», con gli euro
                            dell'altra fase.</>
                        }
                        vuoto={<>Nessun ciclo pre-match chiuso nella {T.operatingDay}.</>}
                    />
                </TabsContent>

                <TabsContent value="risultati-live" className="mt-3 space-y-3">
                    <MikeEventPnlTable
                        gruppi={gruppiOggi}
                        fase="live"
                        titolo="Risultati Live"
                        icona={<span aria-hidden>🔴</span>}
                        testId="mike-risultati-live"
                        onApriScheda={openEventCard}
                        avviso={avvisoRighe}
                        nota={
                            <>Tutto quello che è successo a partita iniziata: la posizione portata in
                            gioco, l'uscita al fischio, la seconda puntata dopo un gol precoce, la
                            copertura sull'Over 4.5 e le chiusure.</>
                        }
                        vuoto={<>Nessuna operazione in gioco nella {T.operatingDay}.</>}
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
