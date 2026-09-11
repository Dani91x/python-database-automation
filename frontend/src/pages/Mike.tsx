// ============================================================================
// /mike — sezione MIKE: bot di trading Under 3.5 / Over 4.5 (paper-first).
//
// Stesso scheletro di Safe Strategy/Omega: header sticky con stato bot e
// scanner, toggle PAPER/LIVE con conferma, sheet parametri (TUTTI), Avvia/Ferma;
// banner modalità; KPI; tab Partite (card per partita con fase, quadro,
// gambe, P&L per gol, cash-out) · Trade · Attività · Regolate.
// FONTE UNICA: feed dello scanner (ramo pre-KO O/U) letto dal servizio; qui
// nessuna chiamata Betfair. Scritture SOLO via RPC owner-only.
// ============================================================================
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
import { Activity, Layers, Play, ShieldAlert, Square, TrendingUp, Radar } from 'lucide-react';
import { sideBadgeClass } from '@/components/safestrategy/variantStyles';
import { useMike } from '@/components/mike/useMike';
import { MikeParamsSheet } from '@/components/mike/MikeParamsSheet';
import { MikeMatchCard } from '@/components/mike/MikeMatchCard';
import { fmtEurIt, fmtOddsIt, SCANNER_STALE_MS } from '@/lib/safeBot';
import { fetchScanStatus, type ScanStatusRow } from '@/lib/safeStrategyScan';
import { TradingHistory } from '@/components/trading/TradingHistory';
import { romeDay, dayLabel, fetchMikeDaily, fetchMikeDayTrades } from '@/lib/dailyHistory';
import {
    sortEvents, phaseMeta, roleLabel, MIKE_TERMINAL_STATES,
    type MikeMode, type MikeStatus, type MikeTrade, type MikeActivity,
} from '@/lib/mike';

const STATUS_META: Record<MikeStatus, { label: string; cls: string }> = {
    idle: { label: 'BOT INATTIVO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    running: { label: 'BOT IN CORSA', cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 animate-pulse' },
    stopping: { label: 'BOT IN ARRESTO', cls: 'bg-amber-500/20 text-amber-300 border-amber-500/50' },
    stopped: { label: 'BOT FERMO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    error: { label: 'BOT IN ERRORE', cls: 'bg-red-500/20 text-red-300 border-red-500/50' },
};

function timeLabel(iso: string | null | undefined): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '—'
        : d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Europe/Rome' });
}

function StatTile({ label, value, tone, icon, sub }: {
    label: string; value: string; tone?: 'pos' | 'neg' | 'plain' | 'gold' | 'danger' | 'teal';
    icon?: ReactNode; sub?: ReactNode;
}) {
    const color = tone === 'pos' ? 'text-emerald-400' : tone === 'neg' ? 'text-red-400'
        : tone === 'gold' ? 'text-secondary' : tone === 'danger' ? 'text-orange-400'
        : tone === 'teal' ? 'text-teal-300' : 'text-white/90';
    return (
        <Card className="glass-card border-white/10 p-3 flex-1 min-w-[130px]">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-400">{icon}{label}</div>
            <div className={`mt-0.5 text-xl md:text-2xl font-display font-black tabular-nums ${color}`}>{value}</div>
            {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
        </Card>
    );
}

function ScannerChip({ status, nowMs, botHeartbeat }: { status: ScanStatusRow | null; nowMs: number; botHeartbeat: string | null | undefined }) {
    const updMs = status?.updated_at ? Date.parse(status.updated_at) : NaN;
    const ageSec = Number.isFinite(updMs) ? Math.max(0, Math.round((nowMs - updMs) / 1000)) : null;
    const alive = ageSec !== null && ageSec * 1000 <= SCANNER_STALE_MS;
    const hbMs = botHeartbeat ? Date.parse(botHeartbeat) : NaN;
    const hbSec = Number.isFinite(hbMs) ? Math.max(0, Math.round((nowMs - hbMs) / 1000)) : null;
    const botAlive = hbSec !== null && hbSec <= 45;
    return (
        <div className={`glass-card rounded-lg border px-3 py-1.5 flex items-center gap-2 flex-wrap text-xs ${alive ? 'border-emerald-500/30' : 'border-red-500/40'}`} data-testid="mike-scanner-chip">
            <Radar className={`w-3.5 h-3.5 ${alive ? 'text-emerald-400' : 'text-red-400'}`} />
            <span>{alive ? `feed vivo (${ageSec}s)` : ageSec === null ? 'feed: nessun dato' : `feed FERMO da ${ageSec}s`}</span>
            <span className="text-slate-500">·</span>
            <span className={botAlive ? 'text-emerald-300' : 'text-slate-400'}>{botAlive ? `servizio Mike vivo (${hbSec}s)` : 'servizio Mike: nessun battito'}</span>
        </div>
    );
}

function EmptyBox({ children }: { children: ReactNode }) {
    return <div className="glass-card rounded-xl border border-dashed border-white/10 p-6 text-center text-sm text-muted-foreground">{children}</div>;
}

function tradeStatusBadge(status: MikeTrade['status']): { label: string; cls: string } {
    switch (status) {
        case 'pending': return { label: 'IN CORSO', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' };
        case 'open': return { label: 'APERTO', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' };
        case 'hedged': return { label: 'CHIUSO', cls: 'bg-teal-500/15 text-teal-300 border-teal-500/40' };
        case 'won': return { label: 'VINTO', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' };
        case 'lost': return { label: 'PERSO', cls: 'bg-red-500/15 text-red-300 border-red-500/40' };
        case 'void': return { label: 'VOID', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40' };
        default: return { label: 'ERRORE', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/40' };
    }
}

const ACTIVITY_META: Record<string, { label: string; cls: string }> = {
    armed: { label: 'ARMATA', cls: 'text-teal-300' },
    state: { label: 'FASE', cls: 'text-slate-300' },
    place: { label: 'ORDINE', cls: 'text-sky-300' },
    place_deferred: { label: 'ORDINE (betDelay)', cls: 'text-sky-300' },
    would_place: { label: 'ORDINE (dry)', cls: 'text-slate-400' },
    cancel: { label: 'ANNULLO', cls: 'text-amber-300' },
    no_fill: { label: 'NO FILL', cls: 'text-amber-300' },
    skip: { label: 'SALTO', cls: 'text-slate-400' },
    pre_cycle: { label: 'CICLO PRE', cls: 'text-emerald-300' },
    cover: { label: 'COPERTURA', cls: 'text-violet-300' },
    settled: { label: 'REGOLATA', cls: 'text-white/90' },
    settle: { label: 'REGOLAMENTO', cls: 'text-white/90' },
    error: { label: 'ERRORE', cls: 'text-red-300' },
    stop: { label: 'STOP', cls: 'text-slate-300' },
    close_retries_exhausted: { label: 'CHIUSURA BLOCCATA', cls: 'text-red-300' },
};

function activityLine(a: MikeActivity): string {
    const p = a.payload ?? {};
    switch (a.kind) {
        case 'state': return `${String(p.from ?? '')} → ${String(p.to ?? '')} · ${String(p.reason ?? '')}`;
        case 'place': case 'would_place': case 'place_deferred':
            return `${roleLabel(String(p.role ?? ''))} ${String(p.side ?? '').toUpperCase()} ${fmtEurIt(Number(p.size ?? 0))} @ ${fmtOddsIt(Number(p.price ?? 0))}${p.bet_delay != null ? ` · betDelay ${String(p.bet_delay)}s` : ''}`;
        case 'pre_cycle': return `ciclo ${String(p.cycle ?? '')}: ${fmtOddsIt(Number(p.entry))} → ${fmtOddsIt(Number(p.exit))} · bloccato ${fmtEurIt(Number(p.locked ?? 0), true)}`;
        case 'settled': return `P&L ${fmtEurIt(Number(p.pnl ?? 0), true)} · totale gol ${String(p.total ?? '?')}`;
        case 'armed': return `KO ${timeLabel(String(p.ko ?? ''))}`;
        case 'no_fill': return `${String(p.side ?? '')} voluto ${fmtOddsIt(Number(p.wanted))} · disponibile ${fmtOddsIt(Number(p.available))}`;
        default: {
            const reason = p.reason ?? p.err ?? p.note;
            return reason ? String(reason) : Object.keys(p).length ? JSON.stringify(p).slice(0, 140) : '';
        }
    }
}

// =============================================================== main page
export default function Mike() {
    const bot = useMike({ onError: (m) => toast.error('Bot Mike', { description: m }) });
    const [nowMs, setNowMs] = useState(() => Date.now());
    const [scanStatus, setScanStatus] = useState<ScanStatusRow | null>(null);
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
    const [tab, setTab] = useState('partite');
    const notifiedRef = useRef<Set<string>>(new Set());
    const navRef = useRef<HTMLElement | null>(null);
    const [navH, setNavH] = useState(52);
    const operatingDay = romeDay();

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
        const el = navRef.current;
        if (!el) return;
        const measure = () => setNavH(Math.round(el.getBoundingClientRect().height) || 52);
        measure();
        if (typeof ResizeObserver === 'undefined') return;
        const ro = new ResizeObserver(measure);
        ro.observe(el);
        return () => ro.disconnect();
    }, []);
    useEffect(() => {
        for (const e of bot.freshSettled) {
            if (notifiedRef.current.has(e.event_id)) continue;
            notifiedRef.current.add(e.event_id);
            const pnl = Number(e.settled_pnl ?? 0);
            const line = `${fmtEurIt(pnl, true)} · ${e.event_name ?? e.event_id}`;
            if (pnl > 0) toast.success(`💰 Regolata`, { description: line });
            else if (pnl < 0) toast.error(`⚠️ Regolata`, { description: line });
            else toast(`Regolata`, { description: line });
        }
    }, [bot.freshSettled]);

    const status: MikeStatus = (bot.control?.status ?? 'idle') as MikeStatus;
    const running = status === 'running' || status === 'stopping';
    const mode: MikeMode = bot.mode;
    const stats = bot.control?.stats ?? null;
    const scannerAge = scanStatus?.updated_at ? (nowMs - Date.parse(scanStatus.updated_at)) / 1000 : null;
    const feedStale = scannerAge === null || scannerAge * 1000 > SCANNER_STALE_MS;

    const events = useMemo(() => sortEvents(bot.events), [bot.events]);
    const active = useMemo(() => events.filter((e) => !MIKE_TERMINAL_STATES.includes(e.state)), [events]);
    const settledEvents = useMemo(() => events.filter((e) => e.state === 'SETTLED'), [events]);
    const withPosition = active.filter((e) => phaseMeta(e.state).group === 'live' || ['PRE_OPEN', 'PRE_GREEN_PENDING', 'HOLD', 'PRE_LAST_ENTRY_PENDING'].includes(e.state));
    const realizedToday = Number(bot.aggregates?.realized_today ?? stats?.realized_today ?? 0);
    const realizedTotal = Number(bot.aggregates?.realized_total ?? stats?.realized_total ?? 0);
    const openLiability = Number(bot.aggregates?.open_liability ?? stats?.open_liability ?? 0);

    function onToggleMode(next: MikeMode) {
        if (next === 'live') setLiveConfirmOpen(true);
        else void bot.setMode('paper');
    }
    async function applyLive() {
        await bot.setMode('live');
        setLiveConfirmOpen(false);
        toast.error('🔴 MODALITÀ LIVE — soldi veri');
    }
    function onRequest(kind: Parameters<typeof bot.request>[0], eventId: string) {
        if (kind === 'cashout' && mode === 'live' && !bot.liveConfirmed) {
            setLiveConfirmOpen(true);
            toast.warning('Conferma la modalità LIVE prima di operare con soldi veri');
            return;
        }
        void bot.request(kind, eventId);
    }

    return (
        <div className="min-h-screen bg-background relative pb-16">
            <Helmet><title>Mike | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav ref={navRef} className="border-b border-white/5 bg-black/60 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-4 lg:px-6 py-2 flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3 flex-wrap">
                        <Link to="/select-sport" className="font-display font-black text-lg tracking-tighter">
                            AI <span className="text-primary">TERMINAL</span>
                        </Link>
                        <span className="flex items-center gap-2 text-sm text-teal-300 font-heading font-bold">🎯 MIKE</span>
                        <Badge variant="outline" className={STATUS_META[status].cls} data-testid="mike-status">{STATUS_META[status].label}</Badge>
                        <ScannerChip status={scanStatus} nowMs={nowMs} botHeartbeat={bot.control?.heartbeat_at} />
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="flex items-center rounded-lg border border-white/10 overflow-hidden text-xs font-bold">
                            <button onClick={() => onToggleMode('paper')} className={`px-3 py-1.5 transition ${mode === 'paper' ? 'bg-emerald-500/25 text-emerald-300' : 'text-slate-400 hover:text-white'}`}>PAPER</button>
                            <button onClick={() => onToggleMode('live')} className={`px-3 py-1.5 transition ${mode === 'live' ? 'bg-red-500/25 text-red-300' : 'text-slate-400 hover:text-white'}`}>LIVE</button>
                        </div>
                        <MikeParamsSheet params={bot.params} busy={bot.busy || !bot.available} onSave={bot.saveParams} />
                        {running ? (
                            <Button variant="destructive" size="sm" onClick={() => { void bot.stop(); }} disabled={bot.busy}><Square className="w-4 h-4 mr-1" />Ferma</Button>
                        ) : (
                            <Button size="sm" onClick={() => { void bot.start(); }} disabled={bot.busy || !bot.available} className="bg-teal-500 text-black hover:bg-teal-400"><Play className="w-4 h-4 mr-1" />Avvia</Button>
                        )}
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-5 relative z-10 max-w-7xl space-y-5">
                <div className={`rounded-lg border px-3 py-2 text-[12px] flex items-center gap-2 flex-wrap ${mode === 'live' ? 'border-red-500/40 bg-red-500/10 text-red-200' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'}`} data-testid="mike-mode-banner">
                    {mode === 'live'
                        ? <><ShieldAlert className="w-4 h-4" aria-hidden /><b>MODALITÀ LIVE</b> — il bot piazza ordini con <b>soldi veri</b>.</>
                        : <><Activity className="w-4 h-4" aria-hidden /><b>MODALITÀ PAPER</b> — simulazione fedele: fill solo al prezzo ancora disponibile, betDelay in-play, protezioni identiche al live.</>}
                    {stats?.dry && <span className="ml-2 text-amber-300">DRY: nessun ordine (osservazione)</span>}
                    {bot.control?.error && <span className="ml-auto text-amber-300">⚠ {bot.control.error}</span>}
                    {!bot.available && !bot.loading && <span className="ml-auto text-amber-300">⚠ tabelle Mike assenti: applica migrations/mike_bot.sql</span>}
                </div>

                {bot.loading ? (
                    <div className="flex flex-wrap gap-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[74px] flex-1 min-w-[130px]" />)}</div>
                ) : (
                    <div className="flex flex-wrap gap-3">
                        <StatTile label="Partite seguite" value={String(active.length)} tone="teal" icon={<Layers className="w-3.5 h-3.5" />} sub={`${stats?.events_feed ?? 0} nel feed · ${withPosition.length} con posizione`} />
                        <StatTile label="Trade aperti" value={String(bot.aggregates?.open_count ?? stats?.trades_open ?? 0)} icon={<Activity className="w-3.5 h-3.5" />} sub={`${bot.trades.length} righe totali`} />
                        <StatTile label="P&L oggi" value={fmtEurIt(realizedToday, true)} tone={realizedToday >= 0 ? 'pos' : 'neg'} icon={<TrendingUp className="w-3.5 h-3.5" />} sub={<span>giornata operativa {dayLabel(operatingDay, { year: false })} · Europe/Rome</span>} />
                        <StatTile label="P&L totale" value={fmtEurIt(realizedTotal, true)} tone={realizedTotal >= 0 ? 'pos' : 'neg'} />
                        <StatTile label="Capitale a rischio" value={fmtEurIt(openLiability)} tone="danger" icon={<ShieldAlert className="w-3.5 h-3.5" />} sub={`stop giornaliero ${fmtEurIt(Number(bot.params.daily_loss_stop ?? 0))}`} />
                        <StatTile label="Ultimo ciclo" value={timeLabel(stats?.last_cycle)} sub={stats?.scanner_age_s != null ? `feed ${stats.scanner_age_s}s` : undefined} />
                    </div>
                )}

                <Tabs value={tab} onValueChange={setTab} className="w-full">
                    <TabsList className="sticky z-30" style={{ top: navH }}>
                        <TabsTrigger value="partite">⚽ Partite ({active.length})</TabsTrigger>
                        <TabsTrigger value="trade">📋 Trade ({bot.trades.length})</TabsTrigger>
                        <TabsTrigger value="attivita">🧾 Attività</TabsTrigger>
                        <TabsTrigger value="regolate">✅ Regolate ({settledEvents.length})</TabsTrigger>
                        <TabsTrigger value="storico">📅 Storico</TabsTrigger>
                    </TabsList>

                    <TabsContent value="partite" className="mt-3">
                        {active.length === 0 ? (
                            <EmptyBox>
                                Nessuna partita seguita. Con il bot in corsa, le partite con calcio d’inizio entro
                                {' '}{String(bot.params.entry_hours_before_ko)} ore e le linee 3.5/4.5 nel feed compaiono qui.
                            </EmptyBox>
                        ) : (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3" data-testid="mike-cards">
                                {active.map((e) => (
                                    <MikeMatchCard
                                        key={e.event_id} ev={e} params={bot.params} nowMs={nowMs} busy={bot.busy}
                                        stale={feedStale} staleReason={feedStale ? 'feed non aggiornato' : undefined}
                                        onRequest={onRequest} isRequestPending={bot.isRequestPending}
                                    />
                                ))}
                            </div>
                        )}
                    </TabsContent>

                    <TabsContent value="trade" className="mt-3">
                        {bot.trades.length === 0 ? <EmptyBox>Nessun trade ancora.</EmptyBox> : (
                            <Card className="glass-card border-white/10 overflow-x-auto">
                                <table className="w-full text-[12px]" data-testid="mike-trades-table">
                                    <thead className="text-slate-500 uppercase tracking-wide text-[10px]">
                                        <tr>
                                            <th className="text-left font-normal px-3 py-2">Ora</th><th className="text-left font-normal">Partita</th>
                                            <th className="text-left font-normal">Gamba</th><th className="text-left font-normal">Lato</th>
                                            <th className="text-right font-normal">Quota</th><th className="text-right font-normal">Size</th>
                                            <th className="text-left font-normal pl-3">Stato</th><th className="text-right font-normal px-3">P&L</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {bot.trades.map((t) => {
                                            const sb = tradeStatusBadge(t.status);
                                            return (
                                                <tr key={t.id} className="border-t border-white/5" data-testid="mike-trade-row">
                                                    <td className="px-3 py-1.5 tabular-nums text-slate-400">{timeLabel(t.placed_at)}</td>
                                                    <td className="truncate max-w-[220px]">{t.event_name ?? t.event_id}</td>
                                                    <td>{roleLabel(t.role ?? t.strategy)} <span className="text-slate-500">{t.selection_name ?? ''}</span></td>
                                                    <td><Badge variant="outline" className={`text-[9px] ${sideBadgeClass(t.side.toUpperCase() as 'BACK' | 'LAY')}`}>{t.side.toUpperCase()}</Badge></td>
                                                    <td className="text-right tabular-nums">{fmtOddsIt(t.price)}</td>
                                                    <td className="text-right tabular-nums">{fmtEurIt(t.size)}</td>
                                                    <td className="pl-3"><Badge variant="outline" className={`text-[9px] ${sb.cls}`}>{sb.label}</Badge>{t.mode === 'live' && <span className="ml-1 text-[9px] text-red-300">LIVE</span>}</td>
                                                    <td className={`text-right tabular-nums px-3 ${Number(t.pnl) > 0 ? 'text-emerald-400' : Number(t.pnl) < 0 ? 'text-red-400' : 'text-slate-400'}`}>{['won', 'lost', 'void'].includes(t.status) ? fmtEurIt(Number(t.pnl), true) : '—'}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </Card>
                        )}
                    </TabsContent>

                    <TabsContent value="attivita" className="mt-3">
                        {bot.activity.length === 0 ? <EmptyBox>Nessuna attività registrata.</EmptyBox> : (
                            <Card className="glass-card border-white/10 divide-y divide-white/5" data-testid="mike-activity">
                                {bot.activity.map((a) => {
                                    const m = ACTIVITY_META[a.kind] ?? { label: a.kind.toUpperCase(), cls: 'text-slate-300' };
                                    const evName = a.event_id ? (bot.events.find((e) => e.event_id === a.event_id)?.event_name ?? a.event_id) : '';
                                    return (
                                        <div key={a.id} className="px-3 py-1.5 text-[12px] flex items-start gap-2">
                                            <span className="tabular-nums text-slate-500 w-16 shrink-0">{timeLabel(a.ts)}</span>
                                            <span className={`font-heading font-bold text-[10px] uppercase tracking-wide w-28 shrink-0 ${m.cls}`}>{m.label}</span>
                                            <span className="text-slate-300 min-w-0 truncate">{evName && <span className="text-white/80">{evName} · </span>}{activityLine(a)}</span>
                                        </div>
                                    );
                                })}
                            </Card>
                        )}
                    </TabsContent>

                    <TabsContent value="regolate" className="mt-3">
                        {settledEvents.length === 0 ? <EmptyBox>Nessuna partita regolata nelle ultime 24 ore.</EmptyBox> : (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                {settledEvents.map((e) => (
                                    <MikeMatchCard key={e.event_id} ev={e} params={bot.params} nowMs={nowMs} />
                                ))}
                            </div>
                        )}
                    </TabsContent>

                    <TabsContent value="storico" className="mt-3">
                        <TradingHistory
                            variant="mike"
                            fetchDaily={fetchMikeDaily}
                            fetchDayTrades={fetchMikeDayTrades}
                            refreshToken={bot.trades.length}
                            onGoLive={() => setTab('partite')}
                        />
                    </TabsContent>
                </Tabs>

                <p className="text-[11px] text-muted-foreground pt-2">
                    Fonte dati: feed unico dello scanner (linee Over/Under 3.5 e 4.5 pre-match e live). Nessuna chiamata
                    Betfair da questa schermata. Paper-first: il live si attiva solo dal toggle con conferma.
                </p>
            </main>

            <Dialog open={liveConfirmOpen} onOpenChange={setLiveConfirmOpen}>
                <DialogContent className="glass-card border-red-500/30">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-red-400"><ShieldAlert className="w-5 h-5" />Passare a LIVE (soldi veri)?</DialogTitle>
                        <DialogDescription className="space-y-2 text-sm">
                            <span className="block">Da questo momento gli ordini del bot Mike usano <b>denaro reale</b>.</span>
                            <span className="block text-orange-300">La struttura Under 3.5 / Over 4.5 perde con esattamente 4 gol: il live va attivato solo dopo il GO della certificazione paper (Costituzione §0).</span>
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
