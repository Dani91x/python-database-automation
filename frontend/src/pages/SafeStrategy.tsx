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
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
    Activity, Play, ShieldAlert, Square, TrendingUp, Signal as SignalIcon, Layers,
} from 'lucide-react';
import { useSafeStrategy, type FootballMonitor, type TennisMonitor } from '@/components/safestrategy/SafeStrategyProvider';
import { SignalCard } from '@/components/safestrategy/SignalCard';
import { MonitorCard } from '@/components/safestrategy/MonitorCard';
import { ParamsSheet } from '@/components/safestrategy/ParamsSheet';
import { BotParamsSheet } from '@/components/safestrategy/BotParamsSheet';
import { OpportunityGroup, filterOpps } from '@/components/safestrategy/OpportunityGroup';
import { SafeTradesTable } from '@/components/safestrategy/SafeTradesTable';
import { useSafeBot } from '@/components/safestrategy/useSafeBot';
import { VARIANT_STYLE } from '@/components/safestrategy/variantStyles';
import { EquityCurve } from '@/components/trading/EquityCurve';
import { TradingHistory } from '@/components/trading/TradingHistory';
import { fetchSafeDaily, fetchSafeDayTrades, romeDay, dayLabel, type SafeSportFilter } from '@/lib/dailyHistory';
import {
    buildEquitySeries, resolveSignalPlacement, safeTradeBook, feedFreshness,
    sameStrategyParams, strategyParamsOf, SCANNER_STALE_MS,
    type FeedFreshness, type SafeBotStatus, type SafeMode, type SafeOpportunity, type SafeTrade,
    type SignalPlacement,
} from '@/lib/safeBot';
import type { ActiveSignal, Sport } from '@/lib/safeStrategy';
import type { CalcioScanPayload, ScanMediaFlags, ScanStatusRow, TennisScanPayload } from '@/lib/safeStrategyScan';

const BOT_STATUS_META: Record<SafeBotStatus, { label: string; cls: string }> = {
    idle: { label: 'BOT INATTIVO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    running: { label: 'BOT IN CORSA', cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 animate-pulse' },
    stopping: { label: 'BOT IN ARRESTO', cls: 'bg-amber-500/20 text-amber-300 border-amber-500/50' },
    stopped: { label: 'BOT FERMO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    error: { label: 'BOT IN ERRORE', cls: 'bg-red-500/20 text-red-300 border-red-500/50' },
};

function fmtEurPlain(v: number | null | undefined): string {
    const n = Number(v ?? 0);
    return `${n < 0 ? '−' : ''}€${Math.abs(n).toFixed(2)}`;
}
function fmtSignedEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}

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

/** barra di stato dello scanner: l'utente deve SEMPRE sapere se il radar è vivo. */
function ScannerBar({ status, nowMs }: { status: ScanStatusRow | null; nowMs: number }) {
    const updatedMs = status?.updated_at ? Date.parse(status.updated_at) : null;
    const ageSec = updatedMs !== null ? Math.max(0, Math.round((nowMs - updatedMs) / 1000)) : null;
    const alive = ageSec !== null && ageSec * 1000 <= SCANNER_STALE_MS;
    const p = status?.payload ?? {};
    return (
        <div
            className={[
                'glass-card rounded-lg border px-3 py-1.5 flex items-center gap-2 flex-wrap text-xs',
                alive ? 'border-emerald-500/30' : 'border-red-500/40',
            ].join(' ')}
            data-testid="scanner-bar"
        >
            <span
                className={`inline-block w-2 h-2 rounded-full ${alive ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`}
                aria-hidden
            />
            <span className="font-heading font-bold text-white uppercase tracking-wide text-[10px]">
                Scanner {alive ? 'attivo' : 'non attivo'}
            </span>
            {alive ? (
                <>
                    <span className="font-mono tabular-nums text-muted-foreground">{ageSec}s fa</span>
                    <span className="text-muted-foreground">
                        ⚽ <b className="text-white font-mono tabular-nums">{p.calcio_inplay ?? 0}</b>
                        <span className="mx-1.5 text-white/20">·</span>
                        🎾 <b className="text-white font-mono tabular-nums">{p.tennis_inplay ?? 0}</b>
                    </span>
                    {p.source && (
                        <Badge
                            variant="outline"
                            className={
                                p.source === 'stream'
                                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 text-[10px]'
                                    : 'bg-amber-500/15 text-amber-300 border-amber-500/40 text-[10px]'
                            }
                            title={p.source === 'stream'
                                ? `Quote in push dalla Exchange Stream API su ${p.stream_markets ?? 0} mercati, ${p.stream_connections ?? 0} connessioni (capacità ${p.stream_capacity ?? 0})`
                                : 'Stream non in salute: quote via poll REST di fallback'}
                        >
                            {p.source === 'stream' ? `⚡ STREAM${p.stream_markets ? ` ${p.stream_markets}` : ''}` : 'REST'}
                        </Badge>
                    )}
                    {p.dry && (
                        <Badge variant="outline" className="bg-amber-500/15 text-amber-300 border-amber-500/40 text-[10px]">DRY</Badge>
                    )}
                    {p.last_error && (
                        <span className="text-[11px] text-amber-300/90" title={p.last_error}>⚠</span>
                    )}
                </>
            ) : (
                <span className="text-muted-foreground">
                    {status === null
                        ? 'nessun heartbeat: servizio scanner mai visto'
                        : `ultimo heartbeat ${ageSec}s fa — riavvia l’app desktop`}
                </span>
            )}
        </div>
    );
}

function StatTile({ label, value, tone, icon, sub }: {
    label: string; value: string; tone?: 'pos' | 'neg' | 'plain' | 'gold' | 'danger';
    icon?: ReactNode; sub?: ReactNode;
}) {
    const color = tone === 'pos' ? 'text-emerald-400'
        : tone === 'neg' ? 'text-red-400'
        : tone === 'gold' ? 'text-secondary'
        : tone === 'danger' ? 'text-orange-400'
        : 'text-white/90';
    return (
        <Card className="glass-card border-white/10 p-3 flex-1 min-w-[130px]">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-400">
                {icon}{label}
            </div>
            <div className={`mt-0.5 text-xl md:text-2xl font-display font-black tabular-nums ${color}`}>{value}</div>
            {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
        </Card>
    );
}

function EmptyBox({ children }: { children: ReactNode }) {
    return (
        <div className="glass-card rounded-xl border border-dashed border-white/10 p-6 text-center text-sm text-muted-foreground">
            {children}
        </div>
    );
}

// =============================================================== main page
export default function SafeStrategy() {
    const { football, tennis, signals, scanStatus, params: localParams, saveParams } = useSafeStrategy();
    const bot = useSafeBot({ onError: (m) => toast.error('Bot Safe Strategy', { description: m }) });

    const [nowMs, setNowMs] = useState(() => Date.now());
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
    const [oppMinConfidence, setOppMinConfidence] = useState(0);
    const [oppSide, setOppSide] = useState<'all' | 'back' | 'lay'>('all');
    const notifiedRef = useRef<Set<number>>(new Set());
    // altezza REALE dell'header sticky (su mobile va a capo): offset della TabsList
    const navRef = useRef<HTMLElement | null>(null);
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
    const operatingDay = romeDay();

    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 10_000);
        return () => window.clearInterval(t);
    }, []);

    useEffect(() => {
        const el = navRef.current;
        if (!el) return;
        const measure = () => setNavH(Math.round(el.getBoundingClientRect().height) || 52);
        measure();
        if (typeof ResizeObserver === 'undefined') return;
        const ro = new ResizeObserver(measure);
        ro.observe(el);
        return () => ro.disconnect();
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

    // ---- toast di settlement
    useEffect(() => {
        for (const t of bot.freshSettlements) {
            if (notifiedRef.current.has(t.id)) continue;
            notifiedRef.current.add(t.id);
            const name = t.event_name ?? t.event_id;
            const pnl = fmtSignedEur(Number(t.pnl));
            if (t.status === 'won' || (t.status === 'hedged' && Number(t.pnl) >= 0)) {
                toast.success(`💰 ${name}`, { description: `${pnl} · ${t.side.toUpperCase()} ${t.selection_name ?? ''}` });
            } else if (t.status === 'lost') {
                toast.error(`⚠️ ${name}`, { description: `${pnl} · ${t.side.toUpperCase()} ${t.selection_name ?? ''}` });
            } else {
                toast(`${name}`, { description: `${t.status.toUpperCase()} · ${pnl}` });
            }
        }
    }, [bot.freshSettlements]);

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
            if (!t.signal_key) continue;
            const prev = out[t.signal_key];
            if (!prev || t.id > prev.id) out[t.signal_key] = t;
        }
        return out;
    }, [bot.trades]);

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
    const oppRows = useMemo(
        () => bot.opportunities.filter((r) => r.sport === 'calcio'),
        [bot.opportunities],
    );

    const stats = bot.control?.stats ?? {};
    const agg = bot.aggregates;
    // "aperti" = posizioni a mercato; i pending (in coda/non abbinati) a parte
    const openTrades = bot.trades.filter((t) => t.status === 'open');
    const pendingTrades = bot.trades.filter((t) => t.status === 'pending');
    const visibleOppRows = useMemo(
        () => oppRows.filter((r) => filterOpps(r, oppMinConfidence, oppSide).length > 0),
        [oppRows, oppMinConfidence, oppSide],
    );
    const realizedToday = Number(agg?.realized_today ?? stats.realized_today ?? 0);
    const realizedTotal = Number(agg?.realized_total ?? stats.realized_total ?? 0);
    const openLiability = Number(agg?.open_liability ?? stats.open_liability ?? 0);
    const totalActive = bySport.calcioActive.length + bySport.tennisActive.length;
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
        });
        if (id != null) toast.success('Ordine in coda', { description: `${signal.matchLabel} · ${fmtEurPlain(size)}` });
        return id;
    }

    async function placeFromOpportunity(eventId: string, eventName: string | null, o: SafeOpportunity, size: number) {
        if (liveNotConfirmed()) return null;
        const id = await bot.place({
            event_id: eventId,
            event_name: eventName,
            sport: 'calcio',
            mode,
            market_id: o.market_id,
            market_type: o.market_type,
            selection_id: o.selection_id,
            selection_name: o.selection_name,
            side: o.side,
            price: o.price,
            size,
            strategy: 'model',
        });
        if (id != null) toast.success('Ordine in coda', { description: `${eventName ?? eventId} · ${fmtEurPlain(size)}` });
        return id;
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
            return <EmptyBox>Nessun segnale attivo in questo momento: il radar continua a osservare.</EmptyBox>;
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
                            commissionPct={bot.params.commission_pct}
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

    function renderTrades(list: SafeTrade[]) {
        return (
            <div className="space-y-4">
                <Card className="glass-card border-white/10 p-4">
                    <div className="flex items-center gap-2 text-sm text-slate-300 mb-2">
                        <TrendingUp className="w-4 h-4 text-primary" /> Equity curve · P&L cumulato regolato
                    </div>
                    <EquityCurve series={buildEquitySeries(list)} />
                </Card>
                <Card className="glass-card border-white/10 p-0 overflow-hidden">
                    <div className="px-4 py-2.5 border-b border-white/5 flex items-center gap-2 text-sm text-slate-300">
                        <Activity className="w-4 h-4 text-primary" /> Trade ({list.length})
                    </div>
                    <SafeTradesTable
                        trades={list}
                        commissionPct={bot.params.commission_pct}
                        liveFeed={payloadByEvent}
                        isCashOutPending={bot.isCashOutPending}
                        freshnessOf={freshnessOf}
                        onCashOut={cashOut}
                    />
                </Card>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background relative pb-16">
            <Helmet><title>Safe Strategy | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            {/* ------------------------------------------------ header sticky */}
            <nav ref={navRef} className="border-b border-white/5 bg-black/60 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-4 lg:px-6 py-2 flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3 flex-wrap">
                        <Link to="/select-sport" className="font-display font-black text-lg tracking-tighter">
                            AI <span className="text-primary">TERMINAL</span>
                        </Link>
                        <span className="flex items-center gap-2 text-sm text-secondary font-heading font-bold">
                            🛡️ SAFE STRATEGY
                        </span>
                        <Badge variant="outline" className={BOT_STATUS_META[status].cls} data-testid="bot-status">
                            {BOT_STATUS_META[status].label}
                        </Badge>
                        <ScannerBar status={scanStatus} nowMs={nowMs} />
                    </div>

                    <div className="flex items-center gap-2">
                        <div className="flex items-center rounded-lg border border-white/10 overflow-hidden text-xs font-bold">
                            <button
                                onClick={() => onToggleMode('paper')}
                                className={`px-3 py-1.5 transition ${mode === 'paper' ? 'bg-emerald-500/25 text-emerald-300' : 'text-slate-400 hover:text-white'}`}
                            >PAPER</button>
                            <button
                                onClick={() => onToggleMode('live')}
                                className={`px-3 py-1.5 transition ${mode === 'live' ? 'bg-red-500/25 text-red-300' : 'text-slate-400 hover:text-white'}`}
                            >LIVE</button>
                        </div>
                        {bot.available
                            ? <BotParamsSheet params={bot.params} rawParams={bot.control?.params ?? null} busy={bot.busy} onSave={bot.saveParams} />
                            : <ParamsSheet />}
                        {running ? (
                            <Button variant="destructive" size="sm" onClick={() => { void bot.stop(); }} disabled={bot.busy}>
                                <Square className="w-4 h-4 mr-1" />Ferma
                            </Button>
                        ) : (
                            <Button size="sm" onClick={() => { void bot.start(); }} disabled={bot.busy} className="bg-primary text-black hover:bg-primary/90">
                                <Play className="w-4 h-4 mr-1" />Avvia
                            </Button>
                        )}
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-5 relative z-10 max-w-7xl space-y-5">
                {/* modalità: sostituisce la vecchia dicitura "nessun ordine automatico" */}
                <div
                    className={[
                        'rounded-lg border px-3 py-2 text-[12px] flex items-center gap-2 flex-wrap',
                        mode === 'live' ? 'border-red-500/40 bg-red-500/10 text-red-200' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
                    ].join(' ')}
                    data-testid="mode-banner"
                >
                    {mode === 'live'
                        ? <><ShieldAlert className="w-4 h-4" aria-hidden /><b>MODALITÀ LIVE</b> — gli ordini piazzati da questa schermata e dal bot usano <b>soldi veri</b>.</>
                        : <><SignalIcon className="w-4 h-4" aria-hidden /><b>MODALITÀ PAPER</b> — simulazione fedele: coda, liquidità e protezioni identiche al live, nessun denaro reale.</>}
                    {bot.control?.error && <span className="ml-auto text-amber-300">⚠ {bot.control.error}</span>}
                </div>

                {/* ------------------------------------------------------ KPI */}
                {bot.loading ? (
                    <div className="flex flex-wrap gap-3">
                        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[74px] flex-1 min-w-[130px]" />)}
                    </div>
                ) : (
                    <div className="flex flex-wrap gap-3">
                        <StatTile label="Segnali attivi" value={String(totalActive)} tone="gold" icon={<SignalIcon className="w-3.5 h-3.5" />} sub={`${bySport.calcioActive.length} calcio · ${bySport.tennisActive.length} tennis`} />
                        <StatTile label="Trade aperti" value={String(openTrades.length)} icon={<Activity className="w-3.5 h-3.5" />} sub={`${pendingTrades.length} in corso · ${bot.trades.length} totali`} />
                        <StatTile label="P&L oggi" value={fmtSignedEur(realizedToday)} tone={realizedToday >= 0 ? 'pos' : 'neg'} icon={<TrendingUp className="w-3.5 h-3.5" />} sub={<span data-testid="safe-operating-day">giornata operativa {dayLabel(operatingDay, { year: false })} · Europe/Rome</span>} />
                        <StatTile label="P&L totale" value={fmtSignedEur(realizedTotal)} tone={realizedTotal >= 0 ? 'pos' : 'neg'} />
                        <StatTile label="Liability aperta" value={fmtEurPlain(openLiability)} tone="danger" icon={<ShieldAlert className="w-3.5 h-3.5" />} />
                        <StatTile label="Partite monitorate" value={String(football.length + tennis.length)} icon={<Layers className="w-3.5 h-3.5" />} sub={`⚽ ${football.length} · 🎾 ${tennis.length}`} />
                    </div>
                )}

                {/* --------------------------------------------- sport + sezioni */}
                <Tabs value={topTab} onValueChange={setTopTab} className="w-full">
                    <TabsList className="sticky z-30" style={{ top: navH }}>
                        <TabsTrigger value="calcio">⚽ Calcio ({bySport.calcioActive.length})</TabsTrigger>
                        <TabsTrigger value="tennis">🎾 Tennis ({bySport.tennisActive.length})</TabsTrigger>
                        <TabsTrigger value="storico">📅 Storico</TabsTrigger>
                    </TabsList>

                    {/* ============================== CALCIO ============================== */}
                    <TabsContent value="calcio" className="mt-3">
                        <Tabs value={calcioTab} onValueChange={setCalcioTab} className="w-full">
                            <TabsList className="mb-3">
                                <TabsTrigger value="segnali">Segnali ({bySport.calcioActive.length})</TabsTrigger>
                                <TabsTrigger value="opportunita">Opportunità modello ({oppRows.length})</TabsTrigger>
                                <TabsTrigger value="monitor">Monitor ({fbSorted.length})</TabsTrigger>
                                <TabsTrigger value="trade">Trade ({calcioTrades.length})</TabsTrigger>
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
                                {oppRows.length === 0 ? (
                                    <EmptyBox>
                                        Nessuna opportunità di modello calcolata: il servizio le scrive quando ha
                                        λ affidabili sul match in corso.
                                    </EmptyBox>
                                ) : visibleOppRows.length === 0 ? (
                                    <EmptyBox>
                                        <span data-testid="opp-filtered-empty">
                                            Nessuna opportunità supera i filtri
                                            {oppMinConfidence > 0 ? ` (confidenza ≥ ${Math.round(oppMinConfidence * 100)}%` : ' ('}
                                            {oppSide !== 'all' ? `${oppMinConfidence > 0 ? ', ' : ''}lato ${oppSide.toUpperCase()}` : ''}
                                            ): allarga confidenza o lato per vederne {oppRows.reduce((n, r) => n + (r.payload?.opps?.length ?? 0), 0)}.
                                        </span>
                                    </EmptyBox>
                                ) : (
                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                        {visibleOppRows.map((r) => (
                                            <OpportunityGroup
                                                key={r.event_id}
                                                row={r}
                                                mode={mode}
                                                stake={bot.params.opps_stake}
                                                requests={bot.requests}
                                                minConfidence={oppMinConfidence}
                                                sideFilter={oppSide}
                                                nowMs={nowMs}
                                                onPlace={(o, size) => placeFromOpportunity(r.event_id, r.payload?.event_name ?? null, o, size)}
                                            />
                                        ))}
                                    </div>
                                )}
                            </TabsContent>

                            <TabsContent value="monitor">
                                {fbSorted.length === 0 ? (
                                    <EmptyBox>
                                        Nessun match di calcio in-play: lo scanner aggiunge gli eventi da solo appena vanno live.
                                    </EmptyBox>
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

                            <TabsContent value="trade">{renderTrades(calcioTrades)}</TabsContent>
                        </Tabs>
                    </TabsContent>

                    {/* ============================== TENNIS ============================== */}
                    <TabsContent value="tennis" className="mt-3">
                        <Tabs value={tennisTab} onValueChange={setTennisTab} className="w-full">
                            <TabsList className="mb-3">
                                <TabsTrigger value="segnali">Segnali ({bySport.tennisActive.length})</TabsTrigger>
                                <TabsTrigger value="monitor">Monitor ({tnSorted.length})</TabsTrigger>
                                <TabsTrigger value="trade">Trade ({tennisTrades.length})</TabsTrigger>
                            </TabsList>

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
                                    <EmptyBox>
                                        Nessun match di tennis in-play: lo scanner li aggiunge da solo appena vanno live.
                                    </EmptyBox>
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

                            <TabsContent value="trade">{renderTrades(tennisTrades)}</TabsContent>
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

                <div className="flex items-center gap-2 flex-wrap pt-2">
                    {(['base', 'esatto', 'punta', 'tennis'] as const).map((v) => (
                        <Badge key={v} variant="outline" className={`text-[10px] font-heading ${VARIANT_STYLE[v].badge}`}>
                            {VARIANT_STYLE[v].chipLabel()}
                        </Badge>
                    ))}
                    <span className="text-[11px] text-muted-foreground">
                        Fonte dati: scanner autonomo Betfair (feed unico). Video e statistiche si aprono sul
                        popup ufficiale Betfair col tuo account.
                    </span>
                </div>
            </main>

            {/* conferma LIVE (soldi veri) */}
            <Dialog open={liveConfirmOpen} onOpenChange={setLiveConfirmOpen}>
                <DialogContent className="glass-card border-red-500/30">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-red-400">
                            <ShieldAlert className="w-5 h-5" />Passare a LIVE (soldi veri)?
                        </DialogTitle>
                        <DialogDescription className="space-y-2 text-sm">
                            <span className="block">Da questo momento gli ordini piazzati dai segnali, dalle opportunità e dal bot usano <b>denaro reale</b>.</span>
                            <span className="block text-orange-300">Le strategie Safe hanno vincite piccole e frequenti: una singola perdita può cancellare molte vincite. Controlla stake e liability prima di procedere.</span>
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setLiveConfirmOpen(false)}>Annulla</Button>
                        <Button variant="destructive" onClick={() => { void applyLive(); }} disabled={bot.busy}>Sì, passa a LIVE</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
