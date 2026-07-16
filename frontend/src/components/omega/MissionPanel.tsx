// ============================================================================
// MissionPanel — tab MISSIONE di /omega: centro di controllo PER PARTITA.
// Header di giornata (obiettivo €, target/partita suggerito, barra avanzamento)
// + lista partite di oggi: missioni ATTIVE prima (fase, minuto, punteggio LIVE,
// progresso verso il target), poi le altre con bottone ATTIVA.
// La UI legge lo specchio DB (polling 10s + realtime) e NON piazza mai nulla
// in automatico: ogni ordine parte da un click nella MissionCard.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Loader2, RefreshCw, Target, ChevronDown, ChevronRight, Trophy, BarChart3, TrendingUp } from 'lucide-react';
import {
    requestManual, fetchOmegaEvents, fetchManualRequests,
    type OmegaEvent, type OmegaMode,
} from '@/lib/omega';
import {
    fetchMissions, activateMission, followMission, subscribeOmegaMissions,
    missionRealized, toNum, splitEventName,
    type MissionRow, type MissionsSummary, type MissionPhase,
} from '@/lib/omegaMissions';
import { leagueLogo, teamLogo } from '@/lib/sportsLogos';
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
function isSameLocalDay(iso: string, ref: Date): boolean {
    const d = new Date(iso);
    return d.getFullYear() === ref.getFullYear() && d.getMonth() === ref.getMonth() && d.getDate() === ref.getDate();
}
// data breve (es. "13/07") mostrata SOLO se il kickoff non è oggi: senza data
// visibile l'utente ha attivato una missione su un evento vecchio di 3 giorni.
function dateLabel(iso: string | null | undefined): string | null {
    if (!iso) return null;
    if (isSameLocalDay(iso, new Date())) return null;
    return new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
}
// stato desunto dal solo kickoff (per gli eventi SENZA missione, dove non c'è
// fase dal servizio): pre | live (iniziata <3h fa) | finita (>3h, come il
// fallback di omega_engine.mission_phase).
type KickoffState = 'pre' | 'live' | 'finita';
function kickoffState(iso: string | null | undefined, now = Date.now()): KickoffState {
    if (!iso) return 'pre';
    const k = new Date(iso).getTime();
    if (Number.isNaN(k) || now < k) return 'pre';
    return now - k > 3 * 3600_000 ? 'finita' : 'live';
}

// logo con fallback pulito: se l'immagine non esiste (id non abbinato o 404
// API-Football) l'<img> sparisce, niente icona rotta.
function Logo({ src, size = 18, alt = '' }: { src: string; size?: number; alt?: string }) {
    const [broken, setBroken] = useState(false);
    // src può cambiare sulla stessa istanza (righe riordinate): il flag broken
    // del vecchio src non deve nascondere il logo del nuovo (review 16/07)
    useEffect(() => { setBroken(false); }, [src]);
    if (!src || broken) return null;
    return (
        <img
            src={src} alt={alt} width={size} height={size} loading="lazy"
            className="rounded-sm object-contain shrink-0"
            onError={() => setBroken(true)}
        />
    );
}

// Pulsanti per-partita (richiesta 16/07): "Statistiche" apre la scheda dettagliata
// della Dashboard per QUESTA partita (deep-link ?fixture=&from=omega, ritorno con
// "Torna a Omega"); "Trading" registra il follow live (RPC omega_mission_follow,
// idempotente) e apre /segui-live PRESELEZIONATO sull'evento (?event=&from=omega).
function RowActions({ eventId, eventName, kickoff, fixtureId }: {
    eventId: string;
    eventName: string;
    kickoff: string | null;
    fixtureId: number | null;
}) {
    const navigate = useNavigate();
    const [busyTrade, setBusyTrade] = useState(false);
    const goTrading = async () => {
        if (busyTrade) return;
        setBusyTrade(true);
        try {
            const { home, away } = splitEventName(eventName);
            // il follow richiede il kickoff (open_date NOT NULL nella RPC)
            if (!kickoff) throw new Error('orario di inizio mancante: impossibile seguire l\'evento');
            await followMission(eventId, home || eventName, away, kickoff);
            navigate(`/segui-live?event=${encodeURIComponent(eventId)}&from=omega`);
        } catch (err) {
            toast.error('Apertura trading fallita', { description: String((err as Error)?.message ?? err) });
        } finally { setBusyTrade(false); }
    };
    return (
        <span
            className="flex items-center gap-1 shrink-0"
            onClick={e => e.stopPropagation()}
            onKeyDown={e => e.stopPropagation()}
        >
            <span title={fixtureId == null ? 'Nessun match API-Football associato a questa partita' : 'Vai alle statistiche della partita (Dashboard)'}>
                <Button
                    size="sm" variant="ghost"
                    disabled={fixtureId == null}
                    className="h-7 px-2 text-[11px] text-slate-300 hover:text-white"
                    onClick={() => { if (fixtureId != null) navigate(`/dashboard?fixture=${fixtureId}&from=omega`); }}
                >
                    <BarChart3 className="w-3.5 h-3.5 mr-1" />Statistiche
                </Button>
            </span>
            <Button
                size="sm" variant="ghost"
                disabled={busyTrade}
                title="Apri il LIVE TRADING su questa partita"
                className="h-7 px-2 text-[11px] text-slate-300 hover:text-white"
                onClick={() => void goTrading()}
            >
                {busyTrade
                    ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                    : <TrendingUp className="w-3.5 h-3.5 mr-1" />}
                Trading
            </Button>
        </span>
    );
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
    // obiettivo € di giornata dal control (audit M8: prima era stato locale
    // scollegato da daily_goal); resta editabile localmente.
    dailyGoal?: number;
}

export default function MissionPanel({ mode = 'paper', dailyGoal }: Props) {
    const [missions, setMissions] = useState<MissionRow[]>([]);
    const [summary, setSummary] = useState<MissionsSummary>({ missions_total: 0, missions_active: 0 });
    const [events, setEvents] = useState<OmegaEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState<string | null>(null);

    const [dayGoal, setDayGoal] = useState(dailyGoal ?? 250);  // obiettivo di GIORNATA €
    // segue il daily_goal del control quando cambia (l'edit locale resta possibile)
    useEffect(() => { if (dailyGoal != null && dailyGoal > 0) setDayGoal(dailyGoal); }, [dailyGoal]);
    const [onlyActive, setOnlyActive] = useState(false);
    // le missioni ATTIVE nascono ESPANSE (16/07: l'utente non trovava posizioni
    // né pulsanti — erano dietro un click invisibile); qui si tiene solo chi
    // ha volutamente RICHIUSO la scheda.
    const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

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
        // realtime su missions+trades: le raffiche (fill+settle ravvicinati)
        // vengono coalizzate in UNA reload ogni 400ms (review 16/07)
        let pending: number | undefined;
        const unsub = subscribeOmegaMissions(() => {
            if (pending !== undefined) return;
            pending = window.setTimeout(() => { pending = undefined; reload().catch(onErr); }, 400);
        });
        const poll = setInterval(() => { reload().catch(onErr); }, 10_000);
        return () => { unsub(); if (pending !== undefined) clearTimeout(pending); clearInterval(poll); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ---- notifiche live (16/07: "non vedo niente di quello che fa il bot") --
    // Confronta lo stato precedente delle missioni: GOL (punteggio cambiato) e
    // gambe REGOLATE (n_settled aumentato) → toast immediato. Solo display.
    const prevMissions = useRef<Map<string, MissionRow>>(new Map());
    useEffect(() => {
        const prev = prevMissions.current;
        const LEG_LABEL: Record<string, string> = { ht_cs: 'Gamba 1T', ft_cs: 'Gamba 2T', scalp: 'Scalp' };
        for (const m of missions) {
            const p = prev.get(m.event_id);
            if (!p) continue;
            if (m.score_home != null && m.score_away != null && p.score_home != null && p.score_away != null
                && (m.score_home !== p.score_home || m.score_away !== p.score_away)) {
                toast(`⚽ GOL — ${m.event_name ?? m.event_id}`, {
                    description: `${m.score_home} - ${m.score_away}${m.minute != null ? ` (${m.minute}')` : ''}`,
                    duration: 10_000,
                });
            }
            for (const k of ['ht_cs', 'ft_cs', 'scalp'] as const) {
                const legNow = m.legs?.[k];
                const legPrev = p.legs?.[k];
                if (legNow && toNum(legNow.n_settled) > toNum(legPrev?.n_settled)) {
                    const delta = toNum(legNow.realized) - toNum(legPrev?.realized);
                    const msg = `${LEG_LABEL[k]} regolata: ${fmtSignedEur(delta)}`;
                    if (delta >= 0) toast.success(msg, { description: m.event_name ?? m.event_id, duration: 12_000 });
                    else toast.error(msg, { description: m.event_name ?? m.event_id, duration: 12_000 });
                }
            }
        }
        prevMissions.current = new Map(missions.map(m => [m.event_id, m]));
    }, [missions]);

    // ---- derivati (Number(...) con fallback: mai NaN in UI) -------------
    const eventById = useMemo(() => new Map(events.map(e => [e.event_id, e])), [events]);
    const activeMissions = useMemo(
        () => missions.filter(m => m.status === 'active')
            .sort((a, b) => String(a.kickoff ?? '').localeCompare(String(b.kickoff ?? ''))),
        [missions]);
    // in pausa sempre visibili; le CHIUSE solo se hanno avuto attività reale
    // (trade o P&L): una missione attivata per sbaglio e auto-chiusa a zero
    // (es. evento stantio) non deve restare in lista come rumore.
    const otherMissions = useMemo(() => missions.filter(m => {
        if (m.status === 'active') return false;
        if (m.status === 'paused') return true;
        const legs = m.legs ?? {};
        const hasTrades = Object.values(legs).some(l => toNum(l?.n_open) > 0 || toNum(l?.n_settled) > 0);
        return hasTrades || missionRealized(m) !== 0;
    }), [missions]);
    // un evento sparisce dalla lista SOLO se la sua missione è visibile sopra:
    // una chiusa-a-zero nascosta deve far RIapparire l'evento tra gli attivabili
    // (review 16/07: prima il match svaniva dal pannello per il resto del giorno)
    const plainEvents = useMemo(() => {
        const visible = new Set([...activeMissions, ...otherMissions].map(m => m.event_id));
        return events.filter(e => !visible.has(e.event_id));
    }, [events, activeMissions, otherMissions]);

    // gruppi per COMPETIZIONE, ordinati per primo kickoff; dentro, per orario.
    // Le partite già FINITE (kickoff >3h fa) scendono in coda al proprio gruppo.
    const eventGroups = useMemo(() => {
        const by = new Map<string, { name: string; leagueId: number | null; events: OmegaEvent[] }>();
        for (const ev of plainEvents) {
            const key = ev.competition_name?.trim() || 'Altre competizioni';
            let g = by.get(key);
            if (!g) { g = { name: key, leagueId: null, events: [] }; by.set(key, g); }
            if (g.leagueId == null && ev.league_id != null) g.leagueId = toNum(ev.league_id);
            g.events.push(ev);
        }
        const groups = [...by.values()];
        for (const g of groups) {
            g.events.sort((a, b) => {
                const fa = kickoffState(a.open_date) === 'finita' ? 1 : 0;
                const fb = kickoffState(b.open_date) === 'finita' ? 1 : 0;
                if (fa !== fb) return fa - fb;
                return String(a.open_date ?? '').localeCompare(String(b.open_date ?? ''));
            });
        }
        groups.sort((a, b) => {
            // "Altre competizioni" sempre in fondo; le altre per primo kickoff
            if (a.name === 'Altre competizioni') return 1;
            if (b.name === 'Altre competizioni') return -1;
            const ka = a.events.find(e => kickoffState(e.open_date) !== 'finita')?.open_date ?? a.events[0]?.open_date ?? '';
            const kb = b.events.find(e => kickoffState(e.open_date) !== 'finita')?.open_date ?? b.events[0]?.open_date ?? '';
            return String(ka).localeCompare(String(kb));
        });
        return groups;
    }, [plainEvents]);

    // per il target/partita contano solo gli eventi ANCORA OPERABILI (pre o
    // live): dividere l'obiettivo per partite già finite gonfiava il denominatore.
    // Fallback (review 16/07): solo le missioni ancora vive, non tutte.
    const operableEvents = useMemo(
        () => events.filter(e => kickoffState(e.open_date) !== 'finita').length,
        [events]);
    const liveMissionsCount = useMemo(
        () => missions.filter(m => m.status === 'active' || m.status === 'paused').length,
        [missions]);
    const eventsCount = operableEvents > 0 ? operableEvents : liveMissionsCount;
    const goal = toNum(dayGoal);
    // target/partita suggerito = obiettivo / n° eventi, 2 decimali
    const targetSuggested = eventsCount > 0 ? Math.round((goal / eventsCount) * 100) / 100 : goal;
    // barra di giornata: SOLO le missioni di OGGI (review 16/07: le attive di
    // ieri restano in lista per essere gestite, ma il loro P&L è di ieri e non
    // deve gonfiare l'avanzamento verso l'obiettivo di oggi)
    const todayStr = new Date().toLocaleDateString('sv-SE');  // YYYY-MM-DD locale
    const totalRealized = missions
        .filter(m => (m.mission_date ?? todayStr) === todayStr)
        .reduce((s, m) => s + missionRealized(m), 0);
    const goalPct = goal > 0 ? Math.max(0, Math.min(100, (totalRealized / goal) * 100)) : 0;

    // ---- azioni ----------------------------------------------------------
    async function doRefreshEvents() {
        setBusy('events');
        try {
            const reqId = await requestManual('refresh_events');
            // polla la RICHIESTA (non la lunghezza della lista: 62→62 eventi non
            // cambia il count e prima sembrava "non succede nulla"). Finestra 50
            // richieste e 45s (review 16/07: con enrichment il refresh può
            // superare i 20s, e altre richieste possono spingere la nostra
            // fuori dalle ultime 10 → falso "servizio non risponde").
            let settled = false;
            for (let i = 0; i < 45 && !settled; i++) {
                await sleep(1000);
                const reqs = await fetchManualRequests(50).catch(() => null);
                const r = reqs?.find(x => x.id === reqId);
                if (!r || (r.status !== 'done' && r.status !== 'error')) continue;
                settled = true;
                if (r.status === 'error') {
                    toast.error('Aggiornamento eventi fallito', {
                        description: String((r.result as { err?: string } | null)?.err ?? 'errore nel servizio Omega'),
                    });
                } else {
                    const fresh = await fetchOmegaEvents().catch(() => null);
                    if (fresh) setEvents(fresh);
                    const n = toNum((r.result as { events?: number } | null)?.events, fresh?.length ?? 0);
                    toast.success(`Eventi aggiornati: ${n} partite di oggi`);
                }
            }
            if (!settled) {
                // il refresh potrebbe comunque essere andato a buon fine più
                // tardi: si ricarica la lista prima di allarmare l'utente
                const fresh = await fetchOmegaEvents().catch(() => null);
                if (fresh) setEvents(fresh);
                toast.warning('Il servizio Omega non ha ancora risposto', {
                    description: 'Se l’app desktop è aperta la lista si aggiornerà da sola; altrimenti avvia il servizio (avvia_omega_service.bat).',
                });
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
            setCollapsedIds(prev => { const next = new Set(prev); next.delete(activation.eventId); return next; });
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
        const expanded = !collapsedIds.has(m.event_id);
        // riepilogo posizioni SEMPRE visibile anche a scheda richiusa
        const legsObj = m.legs ?? {};
        const nOpen = Object.values(legsObj).reduce((s, l) => s + toNum(l?.n_open), 0);
        const nSettled = Object.values(legsObj).reduce((s, l) => s + toNum(l?.n_settled), 0);
        // fixture API-Football per il deep-link Statistiche: dall'evento in cache
        // o, in fallback, dal consulente dati delle suggestion (può mancare)
        const fixtureId = eventById.get(m.event_id)?.fixture_id
            ?? m.suggestion_ht?.advisor?.matched_fixture_id
            ?? m.suggestion_ft?.advisor?.matched_fixture_id
            ?? null;
        const toggleExpanded = () => setCollapsedIds(prev => {
            const next = new Set(prev);
            if (expanded) next.add(m.event_id); else next.delete(m.event_id);
            return next;
        });
        return (
            <div key={m.event_id} className="rounded-lg border border-white/10 bg-white/[0.02]">
                {/* header cliccabile: div role="button" (non <button>) perché contiene
                    i veri <Button> Statistiche/Trading — bottoni annidati = HTML invalido */}
                <div
                    role="button"
                    tabIndex={0}
                    className="w-full px-4 py-3 flex flex-wrap items-center gap-3 text-left hover:bg-white/5 transition cursor-pointer"
                    onClick={toggleExpanded}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpanded(); } }}
                >
                    {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                    <span className={`w-2.5 h-2.5 rounded-full ${statusDot(m)}`} />
                    <Logo src={teamLogo(eventById.get(m.event_id)?.home_team_id)} alt="" />
                    <span className="font-medium truncate max-w-[260px]" title={m.event_name ?? m.event_id}>
                        {m.event_name ?? m.event_id}
                    </span>
                    <Logo src={teamLogo(eventById.get(m.event_id)?.away_team_id)} alt="" />
                    {dateLabel(m.kickoff) && (
                        <Badge variant="outline" className="bg-red-500/15 text-red-300 border-red-500/40">{dateLabel(m.kickoff)}</Badge>
                    )}
                    <Badge variant="outline" className={meta.cls}>{meta.label}</Badge>
                    {phase !== 'pre' && phase !== 'finita' && m.minute != null && (
                        <span className="text-xs text-slate-400 tabular-nums">{toNum(m.minute)}'</span>
                    )}
                    {/* punteggio LIVE grande */}
                    <span className="font-display font-black text-2xl tabular-nums tracking-tight">
                        {phase === 'pre' ? timeLabel(m.kickoff) : `${toNum(m.score_home)} - ${toNum(m.score_away)}`}
                    </span>
                    <RowActions
                        eventId={m.event_id}
                        eventName={m.event_name ?? m.event_id}
                        kickoff={m.kickoff}
                        fixtureId={fixtureId}
                    />
                    <span className="ml-auto flex items-center gap-3 min-w-[190px]">
                        {/* posizioni SEMPRE in vista, anche a scheda richiusa */}
                        {(nOpen > 0 || nSettled > 0) && (
                            <span className="text-[11px] text-slate-400 tabular-nums whitespace-nowrap">
                                {nOpen > 0 && <span className="text-sky-300">{nOpen} apert{nOpen === 1 ? 'a' : 'e'}</span>}
                                {nOpen > 0 && nSettled > 0 && ' · '}
                                {nSettled > 0 && <span>{nSettled} regolat{nSettled === 1 ? 'a' : 'e'}</span>}
                            </span>
                        )}
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
                </div>
                {expanded && (
                    <div className="px-3 pb-3">
                        <MissionCard mission={m} mode={mode} onChanged={() => { reload().catch(() => { /* il polling riprova */ }); }} />
                    </div>
                )}
            </div>
        );
    }

    // riga di un evento SENZA missione: loghi squadre, orario, stato (pre/live/
    // finita). ATTIVA solo se la partita non è già finita.
    function eventRow(ev: OmegaEvent) {
        const state = kickoffState(ev.open_date);
        const { home, away } = splitEventName(ev.name);
        const dLabel = dateLabel(ev.open_date);
        return (
            <div
                key={ev.event_id}
                className={`rounded-lg border border-white/5 bg-white/[0.01] px-4 py-2.5 flex items-center gap-3 ${state === 'finita' ? 'opacity-50' : ''}`}
            >
                <span className="flex items-center gap-2 min-w-0 flex-1">
                    <Logo src={teamLogo(ev.home_team_id)} alt={home} />
                    <span className="text-sm text-slate-200 truncate" title={ev.name ?? ev.event_id}>{home || (ev.name ?? ev.event_id)}</span>
                    {away && <span className="text-[11px] text-slate-500 shrink-0">v</span>}
                    {away && <span className="text-sm text-slate-200 truncate" title={away}>{away}</span>}
                    <Logo src={teamLogo(ev.away_team_id)} alt={away} />
                </span>
                {dLabel && (
                    <Badge variant="outline" className="bg-red-500/15 text-red-300 border-red-500/40">{dLabel}</Badge>
                )}
                {state === 'live' && (
                    <Badge variant="outline" className="bg-emerald-500/15 text-emerald-300 border-emerald-500/40">LIVE</Badge>
                )}
                {state === 'finita' && (
                    <Badge variant="outline" className="bg-slate-500/15 text-slate-400 border-slate-500/40">FINITA</Badge>
                )}
                <span className="text-sm font-display font-bold tabular-nums text-slate-300 w-12 text-right">
                    {timeLabel(ev.open_date)}
                </span>
                <RowActions
                    eventId={ev.event_id}
                    eventName={ev.name ?? ev.event_id}
                    kickoff={ev.open_date}
                    fixtureId={ev.fixture_id ?? null}
                />
                <span className="w-24 text-right">
                    {state !== 'finita' && (
                        <Button
                            size="sm" variant="outline"
                            onClick={() => openActivation(ev.event_id, ev.name ?? ev.event_id, ev.open_date)}
                        >
                            <Target className="w-3.5 h-3.5 mr-1" />ATTIVA
                        </Button>
                    )}
                </span>
            </div>
        );
    }

    function inactiveRow(key: string, name: string, kickoff: string | null, m?: MissionRow) {
        return (
            <div key={key} className="rounded-lg border border-white/5 bg-white/[0.01] px-4 py-2.5 flex items-center gap-3">
                <span className={`w-2.5 h-2.5 rounded-full ${m ? statusDot(m) : 'bg-slate-600'}`} />
                <span className="text-sm text-slate-300 truncate max-w-[300px]" title={name}>{name}</span>
                {dateLabel(kickoff) && (
                    <Badge variant="outline" className="bg-red-500/15 text-red-300 border-red-500/40">{dateLabel(kickoff)}</Badge>
                )}
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
                <span className="ml-auto flex items-center gap-1">
                    <RowActions
                        eventId={key}
                        eventName={name}
                        kickoff={kickoff}
                        fixtureId={eventById.get(key)?.fixture_id
                            ?? m?.suggestion_ht?.advisor?.matched_fixture_id
                            ?? m?.suggestion_ft?.advisor?.matched_fixture_id
                            ?? null}
                    />
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

                    {/* poi le missioni in pausa/chiuse */}
                    {!onlyActive && otherMissions.map(m => inactiveRow(m.event_id, m.event_name ?? m.event_id, m.kickoff, m))}

                    {/* infine gli eventi senza missione, raggruppati per COMPETIZIONE
                        e ordinati per orario (le partite finite in coda, attenuate) */}
                    {!onlyActive && eventGroups.map(g => (
                        <div key={g.name} className="space-y-1.5">
                            <div className="flex items-center gap-2 pt-3 pb-0.5 px-1">
                                {g.leagueId != null
                                    ? <Logo src={leagueLogo(g.leagueId)} size={20} alt={g.name} />
                                    : <Trophy className="w-4 h-4 text-slate-500" />}
                                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{g.name}</span>
                                <span className="text-[11px] text-slate-600 tabular-nums">({g.events.length})</span>
                                <span className="flex-1 border-t border-white/5" />
                            </div>
                            {g.events.map(eventRow)}
                        </div>
                    ))}
                    {!onlyActive && otherMissions.length === 0 && plainEvents.length === 0 && (
                        <div className="text-center text-xs text-muted-foreground py-4">
                            nessun evento in cache — premi "Aggiorna eventi" (servizio locale acceso)
                        </div>
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
