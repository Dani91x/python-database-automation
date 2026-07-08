// ============================================================================
// TennisBotPanel — COLONNA SINISTRA del Terminal Tennis (Screen 3).
//
// Elenca TUTTI i bot tennis del registro (TENNIS_BOT_REGISTRY). Ogni bot è
// una card INDIPENDENTE: si arma/disarma da sola, con il proprio interruttore
// "Solo ARMATO (dry-run)" (default ON = nessun ordine reale), stake e parametri
// numerici (default validati, clampati a min/max/step). Più bot possono essere
// ARMATI contemporaneamente sullo stesso evento.
//
// Polling ~4s di fetchTennisBotsState(eventId): ogni control viene fuso nella
// card per bot_key → badge stato, freschezza heartbeat, tiles statistiche.
// Sotto le card: TennisBotEquityChart con l'equity aggregata + feed attività.
//
// Modello di riferimento per la UX arm/disarm: components/live/ScalperPanel.tsx.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
    Tooltip, TooltipTrigger, TooltipContent, TooltipProvider,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import {
    Bot, Power, Square, Activity, Zap, ChevronDown, ChevronRight,
    Loader2, AlertTriangle, ShieldAlert, RotateCcw, Info,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
    TENNIS_BOT_REGISTRY, TENNIS_BOT_STATUS_LABEL,
    fetchTennisBotsState, armTennisBot, disarmTennisBot,
    type TennisBotDescriptor, type TennisBotControl, type TennisBotActivityRow,
    type TennisBotKey, type TennisBotStatus,
} from '@/lib/tennis';
import { TennisBotEquityChart } from './TennisBotEquityChart';

interface Props {
    eventId: string;
    marketId: string;
}

const POLL_MS = 4000;

// stati in cui il bot è "attivo" (armato/operativo) → mostro il pulsante DISARMA
const ACTIVE_STATUSES: TennisBotStatus[] = ['requested', 'arming', 'armed', 'running', 'stopping'];

const num = (v: unknown, dflt = 0): number =>
    typeof v === 'number' && Number.isFinite(v) ? v : dflt;

// ------------------------------------------------------- accent color mapping
interface AccentStyle {
    text: string;
    border: string;
    ring: string;
    dot: string;
    softBg: string;
}
const ACCENTS: Record<TennisBotDescriptor['accent'], AccentStyle> = {
    primary: { text: 'text-primary', border: 'border-primary/30', ring: 'ring-primary/40', dot: 'bg-primary', softBg: 'bg-primary/10' },
    secondary: { text: 'text-secondary', border: 'border-secondary/30', ring: 'ring-secondary/40', dot: 'bg-secondary', softBg: 'bg-secondary/10' },
    cyan: { text: 'text-cyan-300', border: 'border-cyan-400/30', ring: 'ring-cyan-400/40', dot: 'bg-cyan-400', softBg: 'bg-cyan-400/10' },
    magenta: { text: 'text-fuchsia-300', border: 'border-fuchsia-400/30', ring: 'ring-fuchsia-400/40', dot: 'bg-fuchsia-400', softBg: 'bg-fuchsia-400/10' },
};

// ------------------------------------------------------------- status styling
function statusStyle(status: TennisBotStatus): { cls: string; pulse: boolean } {
    switch (status) {
        case 'running':
            return { cls: 'bg-emerald-500/20 text-emerald-300', pulse: true };
        case 'armed':
        case 'requested':
        case 'arming':
        case 'stopping':
            return { cls: 'bg-amber-400/20 text-amber-300', pulse: false };
        case 'error':
            return { cls: 'bg-red-500/20 text-red-300', pulse: false };
        default:
            return { cls: 'bg-white/10 text-white/50', pulse: false };
    }
}

const PHASE_LABEL: Record<TennisBotDescriptor['phase'], string> = {
    'pre-match': 'pre-match',
    'in-play': 'in-play',
    both: 'pre + in-play',
};

// ============================================================================
// Card di un singolo bot — form di armamento + stato fuso dal control.
// ============================================================================
interface CardProps {
    descriptor: TennisBotDescriptor;
    control: TennisBotControl | null;
    busy: boolean;
    nowTs: number;
    onArm: (botKey: TennisBotKey, dryRun: boolean, stake: number, params: Record<string, number>) => void;
    onDisarm: (botKey: TennisBotKey) => void;
}

function TennisBotCard({ descriptor, control, busy, nowTs, onArm, onDisarm }: CardProps) {
    const accent = ACCENTS[descriptor.accent];
    const [dryRun, setDryRun] = useState(true);
    const [stake, setStake] = useState<number>(descriptor.defaultStake);
    const [params, setParams] = useState<Record<string, number>>({ ...descriptor.defaults });
    const [showParams, setShowParams] = useState(false);

    const active = !!control && ACTIVE_STATUSES.includes(control.status);
    const status = control?.status ?? 'idle';
    const st = statusStyle(status);
    const stats = control?.stats ?? null;

    // freschezza heartbeat: "agg. Xs fa", rossa se >30s quando OPERATIVO
    const heartbeat = useMemo(() => {
        if (!control?.heartbeat_at) return null;
        const ageMs = nowTs - new Date(control.heartbeat_at).getTime();
        const secs = Math.max(0, Math.round(ageMs / 1000));
        const stale = control.status === 'running' && secs > 30;
        return { secs, stale };
    }, [control?.heartbeat_at, control?.status, nowTs]);

    const clamp = (f: TennisBotDescriptor['params'][number], v: number) =>
        Math.min(f.max, Math.max(f.min, v));

    const handleToggle = () => {
        if (active) {
            onDisarm(descriptor.key);
        } else {
            onArm(descriptor.key, dryRun, stake, params);
        }
    };

    return (
        <div
            className={cn(
                'rounded-xl border bg-white/[0.04] p-3 space-y-3 transition',
                active ? cn(accent.border, 'ring-1', accent.ring) : 'border-white/10',
            )}
        >
            {/* intestazione: nome + fase + stato */}
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <span className={cn('h-2 w-2 rounded-full', accent.dot)} />
                        <span className={cn('font-display font-black text-sm tracking-tight text-white')}>
                            {descriptor.name}
                        </span>
                        <span className={cn('rounded px-1.5 py-0.5 text-[9px] font-bold uppercase', accent.softBg, accent.text)}>
                            {PHASE_LABEL[descriptor.phase]}
                        </span>
                    </div>
                    <p className="mt-1 text-[11px] leading-tight text-white/45">{descriptor.short}</p>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                    <Badge className={cn('border-transparent font-bold', st.cls)}>
                        <span className="flex items-center gap-1">
                            {st.pulse && <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 animate-pulse" />}
                            {TENNIS_BOT_STATUS_LABEL[status]}
                        </span>
                    </Badge>
                    {active && control?.dry_run && (
                        <span className="text-[9px] font-bold uppercase text-amber-300">dry-run</span>
                    )}
                    {heartbeat && active && (
                        <span className={cn('text-[9px] font-mono', heartbeat.stale ? 'text-red-300 font-bold' : 'text-white/35')}>
                            agg. {heartbeat.secs}s fa
                        </span>
                    )}
                </div>
            </div>

            {control?.error && (
                <div className="flex items-center gap-1.5 rounded-md bg-red-500/10 px-2 py-1 text-[11px] text-red-300">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {control.error}
                </div>
            )}

            {/* riga controlli: stake + solo-armato + toggle ARMA/DISARMA */}
            <div className="flex items-center gap-2 flex-wrap">
                <label className="flex items-center gap-1.5 text-[11px] text-white/50">
                    <span>Stake €</span>
                    <Input
                        type="number"
                        min={1}
                        max={500}
                        step={1}
                        value={stake}
                        disabled={active || busy}
                        onChange={(e) => setStake(Math.max(1, Math.min(500, Number(e.target.value) || 1)))}
                        className="h-8 w-20 bg-white/5 border-white/10 text-white text-xs"
                    />
                </label>
                <label className={cn('flex items-center gap-1.5 text-[11px] cursor-pointer select-none', active && 'opacity-60')}>
                    <Checkbox
                        checked={dryRun}
                        disabled={active || busy}
                        onCheckedChange={(v) => setDryRun(v === true)}
                    />
                    <span className={dryRun ? 'text-amber-300 font-semibold' : 'text-white/55'}>
                        Solo ARMATO (dry-run)
                    </span>
                </label>
                {!dryRun && !active && (
                    <span className="flex items-center gap-1 text-[10px] font-bold text-red-300">
                        <ShieldAlert className="h-3.5 w-3.5" /> ORDINI REALI
                    </span>
                )}
            </div>

            {/* parametri espandibili */}
            <div className="rounded-lg border border-white/10 bg-black/20">
                <button
                    type="button"
                    onClick={() => setShowParams((s) => !s)}
                    className="flex w-full items-center justify-between px-2 py-1.5 text-[11px] font-bold text-white/60 hover:text-white/80"
                >
                    <span className="flex items-center gap-1.5">
                        {showParams ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                        Parametri
                        <span className="text-white/30 font-normal">({descriptor.params.length})</span>
                    </span>
                    {!active && (
                        <span
                            role="button"
                            tabIndex={0}
                            onClick={(e) => {
                                e.stopPropagation();
                                setParams({ ...descriptor.defaults });
                            }}
                            className="flex items-center gap-1 text-[10px] text-white/40 hover:text-white/70"
                        >
                            <RotateCcw className="h-3 w-3" /> default
                        </span>
                    )}
                </button>
                {showParams && (
                    <div className="grid grid-cols-2 gap-2 px-2 pb-2">
                        {descriptor.params.map((f) => (
                            <TooltipProvider key={f.key} delayDuration={200}>
                                <div className="space-y-0.5">
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <label className="flex items-center gap-1 text-[10px] text-white/45 cursor-help">
                                                {f.label}
                                                <Info className="h-2.5 w-2.5 text-white/25" />
                                            </label>
                                        </TooltipTrigger>
                                        <TooltipContent side="top" className="max-w-[220px] text-[11px]">
                                            {f.hint}
                                        </TooltipContent>
                                    </Tooltip>
                                    <Input
                                        type="number"
                                        step={f.step}
                                        min={f.min}
                                        max={f.max}
                                        value={params[f.key] ?? descriptor.defaults[f.key]}
                                        disabled={active || busy}
                                        onChange={(e) => {
                                            const raw = Number(e.target.value);
                                            if (!Number.isFinite(raw)) return;
                                            setParams((p) => ({ ...p, [f.key]: raw }));
                                        }}
                                        onBlur={(e) => {
                                            const raw = Number(e.target.value);
                                            const v = Number.isFinite(raw) ? clamp(f, raw) : descriptor.defaults[f.key];
                                            setParams((p) => ({ ...p, [f.key]: v }));
                                        }}
                                        className="h-7 bg-white/5 border-white/10 text-white text-xs"
                                    />
                                </div>
                            </TooltipProvider>
                        ))}
                    </div>
                )}
            </div>

            {/* statistiche live (visibili quando c'è un control con stats) */}
            {active && (
                <div className="grid grid-cols-3 gap-1.5 text-center">
                    {[
                        { l: 'Cicli', v: num(stats?.cycles) },
                        { l: 'Scalp', v: num(stats?.scalps) + num(stats?.roundtrips) },
                        { l: 'Scratch', v: num(stats?.scratches) },
                        { l: 'Stop', v: num(stats?.stops) },
                        { l: 'P&L bloccato €', v: num(stats?.pnl_locked).toFixed(2), accent: true },
                        { l: 'P&L aperto €', v: num(stats?.pnl_open).toFixed(2) },
                    ].map((s, i) => (
                        <div key={i} className="rounded-md border border-white/10 bg-white/[0.03] px-1 py-1">
                            <div className="text-[8px] uppercase tracking-wide text-white/35">{s.l}</div>
                            <div className={cn('text-xs font-black', s.accent ? accent.text : 'text-white')}>{s.v}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* toggle ARMA / DISARMA — grande e inequivocabile */}
            <Button
                onClick={handleToggle}
                disabled={busy || control?.status === 'stopping'}
                className={cn(
                    'w-full font-black transition',
                    active
                        ? 'bg-red-600 hover:bg-red-500 text-white'
                        : 'bg-emerald-600 hover:bg-emerald-500 text-white',
                )}
            >
                {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                ) : active ? (
                    <>
                        <Square className="h-4 w-4 mr-2" /> DISARMA
                    </>
                ) : (
                    <>
                        <Power className="h-4 w-4 mr-2" /> ARMA {dryRun ? '(dry-run)' : 'ORDINI REALI'}
                    </>
                )}
            </Button>
        </div>
    );
}

// ============================================================================
// Pannello: elenco card + chart + feed attività, con polling.
// ============================================================================
export function TennisBotPanel({ eventId, marketId }: Props) {
    const [controls, setControls] = useState<TennisBotControl[]>([]);
    const [activity, setActivity] = useState<TennisBotActivityRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [busyBots, setBusyBots] = useState<Record<string, boolean>>({});
    const [nowTs, setNowTs] = useState<number>(Date.now());
    const inflight = useRef<Set<string>>(new Set());

    // marketId è parte del contratto (evento/mercato del terminal) — riservato
    // ad usi futuri (es. deep-link blotter). Riferito qui per evitare unused.
    void marketId;

    const refresh = useCallback(async () => {
        try {
            const s = await fetchTennisBotsState(eventId);
            setControls(s.controls);
            setActivity(s.activity);
        } catch {
            /* transitorio: il polling riprova */
        } finally {
            setLoading(false);
        }
    }, [eventId]);

    useEffect(() => {
        setLoading(true);
        void refresh();
        const t = setInterval(() => void refresh(), POLL_MS);
        return () => clearInterval(t);
    }, [refresh]);

    // clock 1s per la freschezza "agg. Xs fa"
    useEffect(() => {
        const t = setInterval(() => setNowTs(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    const controlByKey = useMemo(() => {
        const m = new Map<TennisBotKey, TennisBotControl>();
        for (const c of controls) m.set(c.bot_key, c);
        return m;
    }, [controls]);

    const setBusy = (botKey: string, v: boolean) =>
        setBusyBots((prev) => ({ ...prev, [botKey]: v }));

    const handleArm = useCallback(
        async (botKey: TennisBotKey, dryRun: boolean, stake: number, params: Record<string, number>) => {
            if (inflight.current.has(botKey)) return;
            const desc = TENNIS_BOT_REGISTRY.find((d) => d.key === botKey);
            // Gate money-critical: armare un bot con ORDINI REALI attiva un agente autonomo
            // che piazza scommesse vere non presidiato → conferma esplicita (come il 1-click LIVE del ladder).
            if (!dryRun) {
                const ok = window.confirm(
                    `⚠️ ARMARE "${desc?.name ?? botKey}" CON ORDINI REALI?\n\n` +
                        `Il bot piazzerà scommesse REALI su Betfair in autonomia (stake €${stake}).\n` +
                        `Assicurati che il runner sia in modalità LIVE. Confermi?`,
                );
                if (!ok) return;
            }
            inflight.current.add(botKey);
            setBusy(botKey, true);
            try {
                const ctrl = await armTennisBot(eventId, botKey, dryRun, stake, params);
                // merge ottimistico immediato
                setControls((prev) => {
                    const rest = prev.filter((c) => c.bot_key !== botKey);
                    return [...rest, ctrl];
                });
                toast.success(
                    `${desc?.name ?? botKey} ARMATO${dryRun ? ' (dry-run · nessun ordine)' : ' · ORDINI REALI'}`,
                );
                void refresh();
            } catch (e) {
                toast.error(`Armamento fallito: ${e instanceof Error ? e.message : String(e)}`);
            } finally {
                inflight.current.delete(botKey);
                setBusy(botKey, false);
            }
        },
        [eventId, refresh],
    );

    const handleDisarm = useCallback(
        async (botKey: TennisBotKey) => {
            if (inflight.current.has(botKey)) return;
            inflight.current.add(botKey);
            setBusy(botKey, true);
            const desc = TENNIS_BOT_REGISTRY.find((d) => d.key === botKey);
            try {
                const ctrl = await disarmTennisBot(eventId, botKey);
                setControls((prev) => {
                    const rest = prev.filter((c) => c.bot_key !== botKey);
                    return [...rest, ctrl];
                });
                toast.success(`${desc?.name ?? botKey} disarmato — chiusura flat`);
                void refresh();
            } catch (e) {
                toast.error(`Disarmo fallito: ${e instanceof Error ? e.message : String(e)}`);
            } finally {
                inflight.current.delete(botKey);
                setBusy(botKey, false);
            }
        },
        [eventId, refresh],
    );

    const armedCount = useMemo(
        () => controls.filter((c) => ACTIVE_STATUSES.includes(c.status)).length,
        [controls],
    );

    return (
        <div className="space-y-3">
            {/* intestazione colonna */}
            <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                    <Bot className="h-5 w-5 text-primary" />
                    <span className="font-display font-black text-white tracking-tight">Bot Tennis</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                    {armedCount > 0 ? (
                        <Badge className="bg-emerald-500/20 text-emerald-300 border-transparent font-bold">
                            <Zap className="h-3 w-3 mr-1" /> {armedCount} armat{armedCount === 1 ? 'o' : 'i'}
                        </Badge>
                    ) : (
                        <span className="text-white/35">nessun bot armato</span>
                    )}
                </div>
            </div>

            {loading && controls.length === 0 ? (
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 flex items-center gap-2 text-white/50 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" /> Caricamento bot…
                </div>
            ) : (
                <div className="space-y-2.5">
                    {TENNIS_BOT_REGISTRY.map((desc) => (
                        <TennisBotCard
                            key={desc.key}
                            descriptor={desc}
                            control={controlByKey.get(desc.key) ?? null}
                            busy={!!busyBots[desc.key]}
                            nowTs={nowTs}
                            onArm={handleArm}
                            onDisarm={handleDisarm}
                        />
                    ))}
                </div>
            )}

            {/* equity/PnL aggregato */}
            <TennisBotEquityChart controls={controls} />

            {/* feed attività compatto (debug veloce) */}
            <div className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-2">
                <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-white/50" />
                    <span className="font-display font-black text-sm text-white tracking-tight">Attività</span>
                </div>
                <div className="max-h-44 overflow-y-auto rounded-lg border border-white/10 bg-black/30 p-2 space-y-1">
                    {activity.length === 0 ? (
                        <div className="text-[11px] text-white/35">Nessuna attività ancora…</div>
                    ) : (
                        activity.map((a) => {
                            const desc = TENNIS_BOT_REGISTRY.find((d) => d.key === a.bot_key);
                            const acc = desc ? ACCENTS[desc.accent] : ACCENTS.primary;
                            return (
                                <div key={a.id} className="text-[10px] font-mono leading-tight">
                                    <span className="text-white/30">
                                        {new Date(a.ts).toLocaleTimeString('it-IT', { hour12: false })}
                                    </span>{' '}
                                    <span className={cn('font-bold', acc.text)}>{desc?.short ? desc.name : a.bot_key}</span>{' '}
                                    <span
                                        className={cn(
                                            a.kind === 'error'
                                                ? 'text-red-300 font-bold'
                                                : a.kind === 'cycle' || a.kind === 'scalp'
                                                    ? 'text-emerald-300 font-bold'
                                                    : a.kind === 'stop'
                                                        ? 'text-amber-300'
                                                        : 'text-white/60',
                                        )}
                                    >
                                        {a.kind}
                                    </span>{' '}
                                    <span className="text-white/45">{JSON.stringify(a.payload)}</span>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>
        </div>
    );
}
