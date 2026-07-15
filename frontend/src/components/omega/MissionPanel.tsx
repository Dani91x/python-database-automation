// ============================================================================
// MissionPanel — tab MISSIONE di /omega: centro di controllo PER PARTITA.
// Header di giornata (obiettivo €, target/partita suggerito, barra avanzamento)
// + lista partite di oggi: missioni ATTIVE prima (fase, minuto, punteggio LIVE,
// progresso verso il target), poi le altre con bottone ATTIVA.
// La UI legge lo specchio DB (polling 10s + realtime) e NON piazza mai nulla
// in automatico: ogni ordine parte da un click nella MissionCard.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Loader2, RefreshCw, Target, ChevronDown, ChevronRight } from 'lucide-react';
import {
    requestManual, fetchOmegaEvents,
    type OmegaEvent, type OmegaMode,
} from '@/lib/omega';
import {
    fetchMissions, activateMission, subscribeOmegaMissions,
    missionRealized, toNum,
    type MissionRow, type MissionsSummary, type MissionPhase,
} from '@/lib/omegaMissions';
import MissionCard from '@/components/omega/MissionCard';

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

function fmtEur(v: number): string {
    return `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;
}
function fmtSignedEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}
function timeLabel(iso: string | null | undefined): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

const PHASE_META: Record<MissionPhase, { label: string; cls: string }> = {
    pre: { label: 'PRE', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40' },
    '1t': { label: '1T', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
    ht: { label: 'HT', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
    '2t': { label: '2T', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
    finita: { label: 'FINITA', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/40' },
};

// pallino di stato missione (verde pulsante = attiva)
function statusDot(m: MissionRow): string {
    if (m.error) return 'bg-red-400';
    if (m.status === 'active') return 'bg-emerald-400 animate-pulse';
    if (m.status === 'paused') return 'bg-amber-400';
    return 'bg-slate-500';
}

interface Props {
    // mode paper/live dal toggle globale della pagina (control.mode)
    mode?: OmegaMode;
}

export default function MissionPanel({ mode = 'paper' }: Props) {
    const [missions, setMissions] = useState<MissionRow[]>([]);
    const [summary, setSummary] = useState<MissionsSummary>({ missions_total: 0, missions_active: 0 });
    const [events, setEvents] = useState<OmegaEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState<string | null>(null);

    const [dayGoal, setDayGoal] = useState(250);      // obiettivo di GIORNATA €
    const [onlyActive, setOnlyActive] = useState(false);
    const [expandedId, setExpandedId] = useState<string | null>(null);

    // dialog ATTIVA: target precompilato editabile
    const [activation, setActivation] = useState<{ eventId: string; name: string; kickoff: string | null } | null>(null);
    const [activationTarget, setActivationTarget] = useState(0);

    const lastErrToast = useRef(0);

    async function reload() {
        // eventi: best-effort (servizio offline → lista vuota, nessuno spam)
        const [pay, evs] = await Promise.all([
            fetchMissions(),
            fetchOmegaEvents().catch(() => null),
        ]);
        setMissions(pay.missions);
        setSummary(pay.summary);
        if (evs) setEvents(evs);
        setLoading(false);
    }

    useEffect(() => {
        // errori di refresh: max 1 toast al minuto (pattern di Omega.tsx)
        const onErr = (e: unknown) => {
            setLoading(false);
            const now = Date.now();
            if (now - lastErrToast.current > 60_000) {
                lastErrToast.current = now;
                toast.error('Aggiornamento missioni fallito', { description: String((e as Error)?.message ?? e) });
            }
        };
        reload().catch(onErr);
        const unsub = subscribeOmegaMissions(() => { reload().catch(onErr); });
        const poll = setInterval(() => { reload().catch(onErr); }, 10_000);
        return () => { unsub(); clearInterval(poll); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ---- derivati (Number(...) con fallback: mai NaN in UI) -------------
    const missionByEvent = useMemo(() => new Map(missions.map(m => [m.event_id, m])), [missions]);
    const activeMissions = useMemo(
        () => missions.filter(m => m.status === 'active')
            .sort((a, b) => String(a.kickoff ?? '').localeCompare(String(b.kickoff ?? ''))),
        [missions]);
    const otherMissions = useMemo(() => missions.filter(m => m.status !== 'active'), [missions]);
    const plainEvents = useMemo(() => events.filter(e => !missionByEvent.has(e.event_id)), [events, missionByEvent]);

    const eventsCount = events.length > 0 ? events.length : missions.length;
    const goal = toNum(dayGoal);
    // target/partita suggerito = obiettivo / n° eventi, 2 decimali
    const targetSuggested = eventsCount > 0 ? Math.round((goal / eventsCount) * 100) / 100 : goal;
    const totalRealized = missions.reduce((s, m) => s + missionRealized(m), 0);
    const goalPct = goal > 0 ? Math.max(0, Math.min(100, (totalRealized / goal) * 100)) : 0;

    // ---- azioni ----------------------------------------------------------
    async function doRefreshEvents() {
        setBusy('events');
        try {
            await requestManual('refresh_events');
            toast('Aggiornamento eventi richiesto', { description: 'Il servizio Omega deve essere in esecuzione.' });
            // attesa breve del servizio, su fetch fresco (come ManualPanel)
            const before = events.length;
            for (let i = 0; i < 8; i++) {
                await sleep(1500);
                const fresh = await fetchOmegaEvents().catch(() => null);
                if (fresh) { setEvents(fresh); if (fresh.length !== before) break; }
            }
        } catch (e) { toast.error('Richiesta fallita', { description: String((e as Error)?.message ?? e) }); }
        finally { setBusy(null); }
    }

    function openActivation(eventId: string, name: string, kickoff: string | null, presetTarget?: number) {
        setActivation({ eventId, name, kickoff });
        setActivationTarget(toNum(presetTarget, 0) > 0 ? toNum(presetTarget) : targetSuggested);
    }

    async function doActivate() {
        if (!activation) return;
        const tgt = toNum(activationTarget);
        if (tgt <= 0) { toast.error('Target non valido'); return; }
        setBusy('activate');
        try {
            await activateMission(activation.eventId, activation.name, activation.kickoff, tgt);
            toast.success('Missione attivata', { description: `${activation.name} · target ${fmtEur(tgt)}` });
            setExpandedId(activation.eventId);
            setActivation(null);
            await reload();
        } catch (e) {
            toast.error('Attivazione fallita', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(null); }
    }

    // ---- righe lista -----------------------------------------------------
    function activeRow(m: MissionRow) {
        const phase = (m.phase_now ?? 'pre') as MissionPhase;
        const meta = PHASE_META[phase] ?? PHASE_META.pre;
        const realized = missionRealized(m);
        const target = toNum(m.target);
        const pct = target > 0 ? Math.max(0, Math.min(100, (realized / target) * 100)) : 0;
        const expanded = expandedId === m.event_id;
        return (
            <div key={m.event_id} className="rounded-lg border border-white/10 bg-white/[0.02]">
                <button
                    className="w-full px-4 py-3 flex flex-wrap items-center gap-3 text-left hover:bg-white/5 transition"
                    onClick={() => setExpandedId(expanded ? null : m.event_id)}
                >
                    {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                    <span className={`w-2.5 h-2.5 rounded-full ${statusDot(m)}`} />
                    <span className="font-medium truncate max-w-[260px]" title={m.event_name ?? m.event_id}>
                        {m.event_name ?? m.event_id}
                    </span>
                    <Badge variant="outline" className={meta.cls}>{meta.label}</Badge>
                    {phase !== 'pre' && phase !== 'finita' && m.minute != null && (
                        <span className="text-xs text-slate-400 tabular-nums">{toNum(m.minute)}'</span>
                    )}
                    {/* punteggio LIVE grande */}
                    <span className="font-display font-black text-2xl tabular-nums tracking-tight">
                        {phase === 'pre' ? timeLabel(m.kickoff) : `${toNum(m.score_home)} - ${toNum(m.score_away)}`}
                    </span>
                    <span className="ml-auto flex items-center gap-3 min-w-[190px]">
                        <span className={`text-sm tabular-nums font-bold ${realized >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {fmtSignedEur(realized)}
                        </span>
                        <span className="text-xs text-slate-500 tabular-nums">/ {fmtEur(target)}</span>
                        <span className="relative h-2 w-24 rounded-full bg-black/50 border border-white/10 overflow-hidden">
                            <span
                                className="absolute inset-y-0 left-0 bg-gradient-to-r from-emerald-500 to-secondary transition-all duration-700"
                                style={{ width: `${pct}%` }}
                            />
                        </span>
                    </span>
                </button>
                {expanded && (
                    <div className="px-3 pb-3">
                        <MissionCard mission={m} mode={mode} onChanged={() => { reload().catch(() => { /* il polling riprova */ }); }} />
                    </div>
                )}
            </div>
        );
    }

    function inactiveRow(key: string, name: string, kickoff: string | null, m?: MissionRow) {
        return (
            <div key={key} className="rounded-lg border border-white/5 bg-white/[0.01] px-4 py-2.5 flex items-center gap-3">
                <span className={`w-2.5 h-2.5 rounded-full ${m ? statusDot(m) : 'bg-slate-600'}`} />
                <span className="text-sm text-slate-300 truncate max-w-[300px]" title={name}>{name}</span>
                <span className="text-xs text-slate-500 tabular-nums">{timeLabel(kickoff)}</span>
                {m && (
                    <Badge variant="outline" className={m.status === 'paused'
                        ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                        : 'bg-slate-500/15 text-slate-300 border-slate-500/40'}>
                        {m.status === 'paused' ? 'IN PAUSA' : 'CHIUSA'}
                    </Badge>
                )}
                {m && missionRealized(m) !== 0 && (
                    <span className={`text-xs tabular-nums font-bold ${missionRealized(m) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {fmtSignedEur(missionRealized(m))}
                    </span>
                )}
                <span className="ml-auto">
                    {/* niente riattivazione per le missioni CHIUSE (conservativo) */}
                    {(!m || m.status === 'paused') && (
                        <Button
                            size="sm" variant="outline"
                            onClick={() => openActivation(key, name, kickoff, m ? toNum(m.target) : undefined)}
                        >
                            <Target className="w-3.5 h-3.5 mr-1" />{m ? 'RIATTIVA' : 'ATTIVA'}
                        </Button>
                    )}
                </span>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* header giornata */}
            <Card className="glass-card border-white/10 p-5 space-y-3">
                <div className="flex flex-wrap items-end gap-4">
                    <label className="block">
                        <span className="text-xs text-slate-400">Obiettivo giornata €</span>
                        <input
                            type="number" min={0} step={10} value={dayGoal}
                            onChange={e => setDayGoal(toNum(e.target.value))}
                            className="mt-1 w-32 rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                        />
                    </label>
                    <div>
                        <div className="text-xs text-slate-400">Eventi oggi</div>
                        <div className="text-2xl font-display font-black tabular-nums">{eventsCount}</div>
                    </div>
                    <div>
                        <div className="text-xs text-slate-400">Target / partita suggerito</div>
                        <div className="text-2xl font-display font-black tabular-nums text-secondary">{fmtEur(targetSuggested)}</div>
                    </div>
                    <div>
                        <div className="text-xs text-slate-400">Missioni</div>
                        <div className="text-2xl font-display font-black tabular-nums">
                            {summary.missions_active}<span className="text-slate-500 text-lg"> / {summary.missions_total}</span>
                        </div>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                        <label className="flex items-center gap-2 text-xs text-slate-400">
                            <input type="checkbox" checked={onlyActive} onChange={e => setOnlyActive(e.target.checked)} />
                            solo attive
                        </label>
                        <Button variant="outline" size="sm" onClick={doRefreshEvents} disabled={busy === 'events'}>
                            {busy === 'events' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                            <span className="ml-1">Aggiorna eventi</span>
                        </Button>
                    </div>
                </div>
                {/* barra avanzamento giornata: Σ realized missioni / obiettivo */}
                <div>
                    <div className="flex items-center justify-between mb-1 text-sm">
                        <span className="flex items-center gap-2 text-slate-300"><Target className="w-4 h-4 text-secondary" />Avanzamento giornata</span>
                        <span className="font-display font-black tabular-nums">
                            <span className={totalRealized >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtSignedEur(totalRealized)}</span>
                            <span className="text-slate-500"> / {fmtEur(goal)}</span>
                        </span>
                    </div>
                    <div className="relative h-4 rounded-full bg-black/50 border border-white/10 overflow-hidden">
                        <div
                            className="absolute inset-y-0 left-0 bg-gradient-to-r from-emerald-500 to-secondary transition-all duration-700"
                            style={{ width: `${goalPct}%` }}
                        />
                        <div className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-white/90 tabular-nums">
                            {goalPct.toFixed(1)}%
                        </div>
                    </div>
                </div>
            </Card>

            {loading ? (
                <div className="text-center text-muted-foreground py-16">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-primary" />caricamento missioni…
                </div>
            ) : (
                <div className="space-y-2">
                    {/* missioni attive prima */}
                    {activeMissions.map(activeRow)}
                    {activeMissions.length === 0 && (
                        <div className="text-center text-sm text-muted-foreground py-6">
                            nessuna missione attiva — attiva una partita qui sotto
                        </div>
                    )}

                    {/* poi le altre (missioni in pausa/chiuse + eventi senza missione) */}
                    {!onlyActive && (
                        <>
                            {otherMissions.map(m => inactiveRow(m.event_id, m.event_name ?? m.event_id, m.kickoff, m))}
                            {plainEvents.map(ev => inactiveRow(ev.event_id, ev.name ?? ev.event_id, ev.open_date))}
                            {otherMissions.length === 0 && plainEvents.length === 0 && (
                                <div className="text-center text-xs text-muted-foreground py-4">
                                    nessun evento in cache — premi "Aggiorna eventi" (servizio locale acceso)
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}

            {/* dialog ATTIVA missione */}
            <Dialog open={!!activation} onOpenChange={o => { if (!o) setActivation(null); }}>
                <DialogContent className="glass-card border-white/10">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2"><Target className="w-5 h-5 text-secondary" />Attiva missione</DialogTitle>
                        <DialogDescription>
                            {activation?.name} · calcio d'inizio {timeLabel(activation?.kickoff)}
                        </DialogDescription>
                    </DialogHeader>
                    <label className="block">
                        <span className="text-xs text-slate-400">Target € della partita</span>
                        <input
                            type="number" min={0} step={0.5} value={activationTarget}
                            onChange={e => setActivationTarget(toNum(e.target.value))}
                            className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                        />
                        <span className="text-[11px] text-slate-500">suggerito: {fmtEur(targetSuggested)} (obiettivo / eventi di oggi)</span>
                    </label>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setActivation(null)}>Annulla</Button>
                        <Button onClick={() => void doActivate()} disabled={busy === 'activate'} className="bg-primary text-black hover:bg-primary/90">
                            {busy === 'activate' && <Loader2 className="w-4 h-4 animate-spin mr-1" />}
                            Attiva
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
