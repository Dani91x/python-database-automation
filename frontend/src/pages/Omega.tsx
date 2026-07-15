// ============================================================================
// /omega — Dashboard OMEGA: bot Correct Score LAY, set-and-forget.
// Obiettivo giornaliero → target per match → un lay per partita in finestra.
// Fonte di verità: Betfair/omega/COSTITUZIONE_OMEGA.md
// Realtime via Supabase (omega_control + omega_trades) + polling di sicurezza.
// ============================================================================
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger,
} from '@/components/ui/sheet';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import ManualPanel from '@/components/omega/ManualPanel';
import MissionPanel from '@/components/omega/MissionPanel';
import {
    ArrowLeft, Play, Square, Settings, Target, TrendingUp, Zap, ShieldAlert, Activity,
} from 'lucide-react';
import {
    activateOmega, stopOmega, updateOmegaParams, fetchOmegaState, fetchOmegaTrades,
    subscribeOmega, buildEquitySeries, OMEGA_PARAM_DEFAULTS, OMEGA_PARAM_FIELDS,
    type OmegaControl, type OmegaTrade, type OmegaParams, type OmegaMode, type OmegaStatus,
    type OmegaAggregates,
} from '@/lib/omega';

// ------------------------------------------------------------------ helpers
function fmtEur(v: number | null | undefined): string {
    const n = Number(v ?? 0);
    return `${n < 0 ? '−' : ''}€${Math.abs(n).toFixed(2)}`;
}
function fmtSignedEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}
function timeLabel(iso: string): string {
    return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

const STATUS_META: Record<OmegaStatus, { label: string; cls: string }> = {
    idle: { label: 'INATTIVO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    running: { label: 'IN CORSA', cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 animate-pulse' },
    stopping: { label: 'IN ARRESTO', cls: 'bg-amber-500/20 text-amber-300 border-amber-500/50' },
    stopped: { label: 'FERMO', cls: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
    error: { label: 'ERRORE', cls: 'bg-red-500/20 text-red-300 border-red-500/50' },
};

// KPI tile
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
        <Card className="glass-card border-white/10 p-4 flex-1 min-w-[150px]">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-slate-400">
                {icon}{label}
            </div>
            <div className={`mt-1 text-2xl md:text-3xl font-display font-black tabular-nums ${color}`}>{value}</div>
            {sub && <div className="mt-0.5 text-[11px] text-slate-500">{sub}</div>}
        </Card>
    );
}

// ------------------------------------------------------------- equity curve
function EquityCurve({ series }: { series: { t: number; v: number; iso: string }[] }) {
    if (series.length === 0) {
        return (
            <div className="text-sm text-muted-foreground py-16 text-center">
                nessun match ancora regolato — la curva compare al primo incasso
            </div>
        );
    }
    const W = 820, H = 240;
    const pad = { l: 10, r: 60, t: 18, b: 26 };
    let t0 = series[0].t;
    let t1 = series[series.length - 1].t;
    if (t1 - t0 < 60_000) { t0 -= 15 * 60_000; t1 += 15 * 60_000; }
    const vals = series.map(p => p.v).concat([0]);
    let vMin = Math.min(...vals), vMax = Math.max(...vals);
    const span = Math.max(vMax - vMin, 0.01);
    vMin -= span * 0.1; vMax += span * 0.1;
    const x = (t: number) => pad.l + ((t - t0) / (t1 - t0 || 1)) * (W - pad.l - pad.r);
    const y = (v: number) => pad.t + ((vMax - v) / (vMax - vMin)) * (H - pad.t - pad.b);

    let d = `M ${x(series[0].t)} ${y(0)}`;
    let prevV = 0;
    for (const p of series) { d += ` L ${x(p.t)} ${y(prevV)} L ${x(p.t)} ${y(p.v)}`; prevV = p.v; }
    const lastV = series[series.length - 1].v;
    const color = lastV >= 0 ? '#34d399' : '#f87171';
    const area = `${d} L ${x(t1)} ${y(0)} L ${x(series[0].t)} ${y(0)} Z`;
    const yTicks = [vMin + span * 0.1, (vMin + vMax) / 2, vMax - span * 0.1];

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label="Equity curve Omega">
            {yTicks.map((v, i) => (
                <g key={i}>
                    <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#1e293b" strokeWidth={1} />
                    <text x={W - pad.r + 6} y={y(v) + 3} fontSize={10} fill="#94a3b8" className="tabular-nums">{fmtSignedEur(v)}</text>
                </g>
            ))}
            <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} stroke="#334155" strokeWidth={1} strokeDasharray="3 3" />
            <path d={area} fill={color} opacity={0.12} />
            <path d={d} fill="none" stroke={color} strokeWidth={2.5} />
            <circle cx={x(series[series.length - 1].t)} cy={y(lastV)} r={4} fill={color} />
        </svg>
    );
}

// -------------------------------------------------------------- trade badge
function tradeBadge(status: OmegaTrade['status']): { label: string; cls: string } {
    switch (status) {
        case 'pending': return { label: 'IN CORSO', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' };
        case 'open': return { label: 'APERTO', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' };
        case 'won': return { label: 'VINTO', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' };
        case 'lost': return { label: 'PERSO', cls: 'bg-red-500/15 text-red-300 border-red-500/40' };
        case 'void': return { label: 'VOID', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40' };
        default: return { label: 'ERRORE', cls: 'bg-orange-500/15 text-orange-300 border-orange-500/40' };
    }
}

// =============================================================== main page
export default function Omega() {
    const [control, setControl] = useState<OmegaControl | null>(null);
    const [aggregates, setAggregates] = useState<OmegaAggregates | null>(null);
    const [trades, setTrades] = useState<OmegaTrade[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    // form inputs
    const [goalInput, setGoalInput] = useState(250);
    const [params, setParams] = useState<OmegaParams>(OMEGA_PARAM_DEFAULTS);
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);

    const seenSettled = useRef<Set<number>>(new Set());
    const initialized = useRef(false);

    const status: OmegaStatus = control?.status ?? 'idle';
    const mode: OmegaMode = control?.mode ?? 'paper';
    const stats = control?.stats ?? {};

    async function reload() {
        const firstLoad = !initialized.current;
        const [st, tr] = await Promise.all([fetchOmegaState(60), fetchOmegaTrades(500)]);
        setControl(st.control);
        setAggregates(st.aggregates);
        setTrades(tr);
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
            const name = t.event_name || t.event_id;
            // distingue i trade decisi a mano da quelli del bot (trasparenza)
            const tag = t.origin === 'manual' ? '✋ ' : '';
            if (t.status === 'won') {
                toast.success(`💰 ${tag}${name}`, { description: `Incassato ${fmtSignedEur(Number(t.pnl))} · ${t.side === 'back' ? 'back' : 'lay'} ${t.runner_name}` });
            } else if (t.status === 'lost') {
                toast.error(`⚠️ ${tag}${name}`, { description: `Perso ${fmtSignedEur(Number(t.pnl))} · ${t.side === 'back' ? 'back' : 'lay'} ${t.runner_name}` });
            } else {
                toast(`${tag}${name}`, { description: `Match VOID · P&L €0` });
            }
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
        const unsub = subscribeOmega(() => { reload().catch(onReloadError); });
        const poll = setInterval(() => { reload().catch(onReloadError); }, 15_000);
        return () => { unsub(); clearInterval(poll); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ---- azioni
    async function handleStart() {
        setBusy(true);
        try {
            await activateOmega(mode, goalInput, params);
            toast.success('Omega avviato', { description: `Obiettivo ${fmtEur(goalInput)}/giorno · modalità ${mode.toUpperCase()}` });
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

    async function handleSaveParams() {
        setBusy(true);
        try {
            await updateOmegaParams({ dailyGoal: goalInput, params });
            toast.success('Parametri aggiornati');
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
                next === 'live' ? '🔴 MODALITÀ LIVE — soldi veri' : '🟢 Modalità PAPER (simulazione)',
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
    // I numeri "soldi" vengono dagli AGGREGATI freschi (RPC, calcolati sul DB e
    // ORIGIN-AGNOSTICI: includono i trade manuali anche a bot automatico fermo).
    // Fallback alla fotografia stats se l'RPC non li fornisse.
    // §2: obiettivo/barra sono della GIORNATA operativa (realized_today); il
    // cumulato storico resta visibile come sottotitolo del KPI.
    const realizedTotal = Number(aggregates?.realized_profit ?? stats.realized_profit ?? 0);
    const realized = Number(aggregates?.realized_today ?? stats.realized_today ?? realizedTotal);
    const goal = Number(control?.daily_goal ?? stats.goal ?? goalInput ?? 250);
    const goalPct = goal > 0 ? Math.max(0, Math.min(100, (realized / goal) * 100)) : 0;
    const openLiability = Number(aggregates?.open_liability ?? stats.open_liability ?? 0);
    const matchesTraded = Number(aggregates?.matches_traded ?? stats.matches_traded ?? trades.length);
    const equity = useMemo(() => buildEquitySeries(trades), [trades]);
    const running = status === 'running' || status === 'stopping';

    return (
        <div className="min-h-screen bg-background text-foreground relative">
            <Helmet><title>Omega | Correct Score Bot</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-20" />

            {/* top bar */}
            <nav className="border-b border-white/5 bg-black/60 backdrop-blur-xl sticky top-0 z-40">
                <div className="container mx-auto px-4 h-16 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                        <Link to="/select-sport"><Button variant="ghost" size="sm"><ArrowLeft className="w-4 h-4 mr-1" />Menu</Button></Link>
                        <div className="font-display font-black text-2xl tracking-tighter flex items-center gap-2">
                            <span className="text-primary text-3xl leading-none">Ω</span>
                            <span>OMEGA</span>
                        </div>
                        <Badge variant="outline" className={STATUS_META[status].cls}>{STATUS_META[status].label}</Badge>
                    </div>
                    <div className="flex items-center gap-2">
                        {/* mode toggle */}
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
                        <ParamsSheet
                            params={params} setParams={setParams}
                            goal={goalInput} setGoal={setGoalInput}
                            onSave={handleSaveParams} busy={busy}
                        />
                        {running ? (
                            <Button variant="destructive" size="sm" onClick={handleStop} disabled={busy}>
                                <Square className="w-4 h-4 mr-1" />Ferma
                            </Button>
                        ) : (
                            <Button size="sm" onClick={handleStart} disabled={busy} className="bg-primary text-black hover:bg-primary/90">
                                <Play className="w-4 h-4 mr-1" />Avvia
                            </Button>
                        )}
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 py-6 relative z-10 space-y-6">
                {loading ? (
                    <div className="text-center text-muted-foreground py-24">
                        <Activity className="w-6 h-6 animate-spin mx-auto mb-3 text-primary" />caricamento Omega…
                    </div>
                ) : (
                    <Tabs defaultValue="mission" className="w-full">
                        <TabsList className="mb-4">
                            <TabsTrigger value="mission">🎯 Missione</TabsTrigger>
                            <TabsTrigger value="auto">⚙️ Automatico</TabsTrigger>
                            <TabsTrigger value="manual">✋ Manuale</TabsTrigger>
                        </TabsList>
                        <TabsContent value="mission">
                            {/* mode paper/live dal toggle globale in alto (control.mode) */}
                            <MissionPanel mode={mode} />
                        </TabsContent>
                        <TabsContent value="auto" className="space-y-6">
                        {/* barra obiettivo */}
                        <Card className="glass-card border-white/10 p-5">
                            <div className="flex items-end justify-between mb-2">
                                <div className="flex items-center gap-2 text-sm text-slate-300">
                                    <Target className="w-4 h-4 text-secondary" /> Obiettivo giornaliero
                                </div>
                                <div className="font-display font-black text-2xl tabular-nums">
                                    <span className={realized >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtSignedEur(realized)}</span>
                                    <span className="text-slate-500 text-lg"> / {fmtEur(goal)}</span>
                                </div>
                            </div>
                            <div className="relative h-5 rounded-full bg-black/50 border border-white/10 overflow-hidden">
                                <div
                                    className="absolute inset-y-0 left-0 bg-gradient-to-r from-emerald-500 to-secondary transition-all duration-700"
                                    style={{ width: `${goalPct}%` }}
                                />
                                <div className="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-white/90 tabular-nums">
                                    {goalPct.toFixed(1)}%
                                </div>
                            </div>
                        </Card>

                        {/* KPI */}
                        <div className="flex flex-wrap gap-3">
                            <StatTile label="P&L oggi" value={fmtSignedEur(realized)} tone={realized >= 0 ? 'pos' : 'neg'} icon={<TrendingUp className="w-3.5 h-3.5" />} sub={`totale storico ${fmtSignedEur(realizedTotal)}`} />
                            <StatTile label="Target / match" value={fmtEur(stats.target_match)} tone="gold" icon={<Zap className="w-3.5 h-3.5" />} sub={`${stats.matches_remaining ?? '—'} match rimasti`} />
                            <StatTile label="Eventi oggi" value={String(stats.events_total ?? '—')} icon={<Activity className="w-3.5 h-3.5" />} />
                            <StatTile label="Match piazzati" value={String(matchesTraded)} sub={`${trades.filter(t => t.status === 'won').length}V · ${trades.filter(t => t.status === 'lost').length}P · ${aggregates?.matches_open ?? stats.matches_open ?? 0} aperti`} />
                            <StatTile label="Liability aperta" value={fmtEur(openLiability)} tone="danger" icon={<ShieldAlert className="w-3.5 h-3.5" />} sub="esposizione a coda" />
                        </div>

                        {/* equity curve */}
                        <Card className="glass-card border-white/10 p-5">
                            <div className="flex items-center gap-2 text-sm text-slate-300 mb-3">
                                <TrendingUp className="w-4 h-4 text-primary" /> Equity curve · P&L cumulato regolato
                            </div>
                            <EquityCurve series={equity} />
                        </Card>

                        {/* lista trade live */}
                        <Card className="glass-card border-white/10 p-0 overflow-hidden">
                            <div className="px-5 py-3 border-b border-white/5 flex items-center gap-2 text-sm text-slate-300">
                                <Activity className="w-4 h-4 text-primary" /> Trade piazzati ({trades.length})
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead className="text-[11px] uppercase text-slate-500 bg-black/30">
                                        <tr>
                                            <th className="text-left px-4 py-2">Ora</th>
                                            <th className="text-left px-4 py-2">Match</th>
                                            <th className="text-center px-4 py-2">Lay</th>
                                            <th className="text-right px-4 py-2">Quota</th>
                                            <th className="text-right px-4 py-2">Stake</th>
                                            <th className="text-right px-4 py-2">Liability</th>
                                            <th className="text-center px-4 py-2">Min</th>
                                            <th className="text-center px-4 py-2">Stato</th>
                                            <th className="text-right px-4 py-2">P&L</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {trades.length === 0 ? (
                                            <tr><td colSpan={9} className="text-center text-muted-foreground py-10">nessun trade ancora — avvia il bot e attendi la finestra dei match</td></tr>
                                        ) : trades.map(t => {
                                            const b = tradeBadge(t.status);
                                            return (
                                                <tr key={t.id} className="border-t border-white/5 hover:bg-white/5">
                                                    <td className="px-4 py-2 text-slate-400 tabular-nums">{timeLabel(t.placed_at)}</td>
                                                    <td className="px-4 py-2 max-w-[240px] truncate" title={t.event_name ?? t.event_id}>
                                                        {t.origin === 'manual' && (
                                                            <Badge variant="outline" className="mr-1.5 px-1 py-0 text-[10px] bg-violet-500/15 text-violet-300 border-violet-500/40" title="trade piazzato manualmente">✋</Badge>
                                                        )}
                                                        {t.event_name ?? t.event_id}
                                                    </td>
                                                    <td className={`px-4 py-2 text-center font-bold ${t.side === 'back' ? 'text-sky-300' : 'text-rose-300'}`}>{t.runner_name ?? '—'}</td>
                                                    <td className="px-4 py-2 text-right tabular-nums">{t.price?.toFixed(2) ?? '—'}</td>
                                                    <td className="px-4 py-2 text-right tabular-nums">{fmtEur(t.size)}</td>
                                                    <td className="px-4 py-2 text-right tabular-nums text-orange-400/90">{fmtEur(t.liability)}</td>
                                                    <td className="px-4 py-2 text-center text-slate-400 tabular-nums">{t.minute_at_entry ?? '—'}'</td>
                                                    <td className="px-4 py-2 text-center"><Badge variant="outline" className={b.cls}>{b.label}</Badge></td>
                                                    <td className={`px-4 py-2 text-right font-bold tabular-nums ${t.status === 'won' ? 'text-emerald-400' : t.status === 'lost' ? 'text-red-400' : 'text-slate-400'}`}>
                                                        {['won', 'lost', 'void'].includes(t.status) ? fmtSignedEur(Number(t.pnl)) : '—'}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </Card>
                        </TabsContent>
                        <TabsContent value="manual">
                            <ManualPanel />
                        </TabsContent>
                    </Tabs>
                )}
            </main>

            {/* conferma LIVE (soldi veri) */}
            <Dialog open={liveConfirmOpen} onOpenChange={setLiveConfirmOpen}>
                <DialogContent className="glass-card border-red-500/30">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-red-400"><ShieldAlert className="w-5 h-5" />Passare a LIVE (soldi veri)?</DialogTitle>
                        <DialogDescription className="space-y-2 text-sm">
                            <span className="block">Omega inizierà a piazzare <b>lay reali</b> sul Correct Score con denaro vero.</span>
                            <span className="block text-orange-300">Ricorda §9 della Costituzione: profit piccolo ~98%, ma perdita grande ~1–2% (coda pesante). La liability aperta può essere ingente.</span>
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setLiveConfirmOpen(false)}>Annulla</Button>
                        <Button variant="destructive" onClick={() => applyMode('live')} disabled={busy}>Sì, passa a LIVE</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

// --------------------------------------------------------- pannello parametri
function ParamsSheet({ params, setParams, goal, setGoal, onSave, busy }: {
    params: OmegaParams; setParams: (p: OmegaParams) => void;
    goal: number; setGoal: (n: number) => void;
    onSave: () => void; busy: boolean;
}) {
    return (
        <Sheet>
            <SheetTrigger asChild>
                <Button variant="outline" size="sm"><Settings className="w-4 h-4 mr-1" />Parametri</Button>
            </SheetTrigger>
            <SheetContent className="glass-card border-white/10 w-full sm:max-w-md overflow-y-auto">
                <SheetHeader>
                    <SheetTitle className="font-display flex items-center gap-2"><span className="text-primary text-xl">Ω</span> Parametri Omega</SheetTitle>
                    <SheetDescription>Tutto configurabile. Salva per applicare a caldo (§7 Costituzione).</SheetDescription>
                </SheetHeader>

                <div className="mt-5 space-y-4">
                    <label className="block">
                        <span className="text-xs text-slate-400">Obiettivo giornaliero €</span>
                        <input
                            type="number" value={goal} min={0} step={10}
                            onChange={e => setGoal(Number(e.target.value))}
                            className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                        />
                    </label>

                    {OMEGA_PARAM_FIELDS.map(f => (
                        <label key={f.key} className="block">
                            <span className="text-xs text-slate-400">{f.label}</span>
                            <input
                                type="number" step={f.step} min={f.min} max={f.max}
                                value={Number((params as unknown as Record<string, number>)[f.key])}
                                onChange={e => setParams({ ...params, [f.key]: Number(e.target.value) })}
                                className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                            />
                            <span className="text-[11px] text-slate-500">{f.hint}</span>
                        </label>
                    ))}

                    <label className="block">
                        <span className="text-xs text-slate-400">Sorgente minuto</span>
                        <select
                            value={params.entry_window_source}
                            onChange={e => setParams({ ...params, entry_window_source: e.target.value as 'score' | 'clock' })}
                            className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm"
                        >
                            <option value="score">score (feed live)</option>
                            <option value="clock">clock (orario KO)</option>
                        </select>
                    </label>

                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={params.include_aggregate}
                            onChange={e => setParams({ ...params, include_aggregate: e.target.checked })} />
                        Includi risultati aggregati ("Any Other …")
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={params.stop_on_goal}
                            onChange={e => setParams({ ...params, stop_on_goal: e.target.checked })} />
                        Stop nuovi ingressi a obiettivo raggiunto
                    </label>

                    <Button onClick={onSave} disabled={busy} className="w-full bg-primary text-black hover:bg-primary/90">
                        Salva parametri
                    </Button>
                    <p className="text-[11px] text-slate-500 pb-6">
                        I tre cap (liability/match, stop-loss, liability aperta) sono <b>OFF di default</b>:
                        Omega è set-and-forget. Mettili &gt; 0 per attivarli.
                    </p>
                </div>
            </SheetContent>
        </Sheet>
    );
}
