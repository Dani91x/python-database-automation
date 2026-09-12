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
import { Loader2, RefreshCw, Target, ChevronDown, ChevronRight, Trophy, BarChart3, TrendingUp, CircleDot } from 'lucide-react';
import {
    requestManual, fetchOmegaEvents, fetchManualRequests, updateOmegaParams,
    filterEventsInWindow, eventsCacheUpdatedAt, OMEGA_DAILY_GOAL_MAX,
    type OmegaEvent, type OmegaMode,
} from '@/lib/omega';
import {
    fetchMissions, activateMission, followMission, setFollowRecord, subscribeOmegaMissions,
    missionRealized, goalProgressPct, toNum, splitEventName,
    type MissionRow, type MissionsSummary, type MissionPhase,
} from '@/lib/omegaMissions';
import { fmtMoney, fmtTime, fmtAge, ageSeconds } from '@/lib/format';
import { romeDay } from '@/lib/dailyHistory';
import { leagueLogo, teamLogo } from '@/lib/sportsLogos';
import MissionCard from '@/components/omega/MissionCard';
import { fetchScalperState, type ScalperControl } from '@/lib/scalper';
import { useScanLiveFeedRows } from '@/lib/useScanLiveFeed';

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

// formati UNICI del design system; le ORE sono sempre quelle di ROMA (M-08:
// prima erano quelle del browser e la "giornata" cambiava prima del servizio)
function fmtEur(v: number): string {
    return fmtMoney(v);
}
function fmtSignedEur(v: number): string {
    return fmtMoney(v, { signed: true });
}
function timeLabel(iso: string | null | undefined): string {
    return fmtTime(iso);
}
function isSameRomeDay(iso: string, ref: string = romeDay()): boolean {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? false : romeDay(d) === ref;
}
// data breve (es. "13/07") mostrata SOLO se il kickoff non è oggi: senza data
// visibile l'utente ha attivato una missione su un evento vecchio di 3 giorni.
function dateLabel(iso: string | null | undefined): string | null {
    if (!iso) return null;
    if (isSameRomeDay(iso)) return null;
    const d = romeDay(new Date(iso));
    return /^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d.slice(8, 10)}/${d.slice(5, 7)}` : null;
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
// idempotente, SENZA registrazione: record=false) e apre /segui-live
// PRESELEZIONATO sull'evento (?event=&from=omega); "Segui live" (opt-in 17/07)
// attiva la REGISTRAZIONE per intero della partita (follow + set_follow_record):
// solo le partite col REC acceso producono il raw e finiscono nel Match Replay.
function RowActions({ eventId, eventName, kickoff, fixtureId, recording }: {
    eventId: string;
    eventName: string;
    kickoff: string | null;
    fixtureId: number | null;
    // stato registrazione dal DB (get_omega_missions.recording); undefined =
    // ignoto (evento senza missione) → si parte da spento.
    recording?: boolean;
}) {
    const navigate = useNavigate();
    const [busyTrade, setBusyTrade] = useState(false);
    const [busyRec, setBusyRec] = useState(false);
    // override locale ottimista dopo un toggle; null = fai fede al DB
    const [recLocal, setRecLocal] = useState<boolean | null>(null);
    const recActive = recLocal ?? Boolean(recording);
    const goTrading = async () => {
        if (busyTrade) return;
        setBusyTrade(true);
        try {
            const { home, away } = splitEventName(eventName);
            // il follow richiede il kickoff (open_date NOT NULL nella RPC)
            if (!kickoff) throw new Error('orario di inizio mancante: impossibile seguire l\'evento');
            // solo follow + navigazione: la registrazione NON si attiva da qui
            await followMission(eventId, home || eventName, away, kickoff);
            navigate(`/segui-live?event=${encodeURIComponent(eventId)}&from=omega`);
        } catch (err) {
            toast.error('Apertura trading fallita', { description: String((err as Error)?.message ?? err) });
        } finally { setBusyTrade(false); }
    };
    const toggleRec = async () => {
        if (busyRec) return;
        setBusyRec(true);
        try {
            if (!recActive) {
                const { home, away } = splitEventName(eventName);
                if (!kickoff) throw new Error('orario di inizio mancante: impossibile seguire l\'evento');
                // il follow deve esistere prima del flag (idempotente se già presente)
                await followMission(eventId, home || eventName, away, kickoff);
                await setFollowRecord(eventId, true);
                setRecLocal(true);
                toast.success('Registrazione attivata', {
                    description: 'La partita viene registrata per intero e a fine gara caricata nel Match Replay.',
                });
            } else {
                await setFollowRecord(eventId, false);
                setRecLocal(false);
                toast('Registrazione disattivata', {
                    description: 'Streaming e trading proseguono; niente raw né upload nel Replay.',
                });
            }
        } catch (err) {
            toast.error('Toggle registrazione fallito', { description: String((err as Error)?.message ?? err) });
        } finally { setBusyRec(false); }
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
            <Button
                size="sm" variant="ghost"
                disabled={busyRec}
                title={recActive
                    ? 'Registrazione ATTIVA: la partita sarà caricata nel Match Replay — clic per spegnere'
                    : 'Registra la partita per intero (raw + Match Replay a fine gara)'}
                className={`h-7 px-2 text-[11px] ${recActive
                    ? 'text-red-300 hover:text-red-200'
                    : 'text-slate-300 hover:text-white'}`}
                onClick={() => void toggleRec()}
            >
                {busyRec
                    ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                    : <CircleDot className={`w-3.5 h-3.5 mr-1 ${recActive ? 'text-red-400 animate-pulse' : ''}`} />}
                {recActive ? 'REC' : 'Segui live'}
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
    /**
     * Audit 12/09 — target per partita del SERVIZIO (`stats.target_match`) e
     * partite ancora in finestra (`stats.matches_remaining`). Prima questo
     * pannello ne calcolava DUE suoi (obiettivo ÷ eventi in cache) e con la
     * cache eventi ferma mostrava «Target / partita suggerito 100,00 €», cioè
     * l'INTERO obiettivo di giornata su una sola partita, mentre il KPI in alto
     * diceva 0,17 €. null = servizio fermo → si ripiega sul calcolo locale e lo
     * si DICHIARA.
     */
    targetMatch?: number | null;
    matchesRemaining?: number | null;
}

export default function MissionPanel({ mode = 'paper', dailyGoal, targetMatch = null, matchesRemaining = null }: Props) {
    const [missions, setMissions] = useState<MissionRow[]>([]);
    const [summary, setSummary] = useState<MissionsSummary>({ missions_total: 0, missions_active: 0 });
    const [events, setEvents] = useState<OmegaEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState<string | null>(null);

    const [dayGoal, setDayGoal] = useState(dailyGoal ?? 250);  // obiettivo di GIORNATA €
    // segue il daily_goal del control quando cambia (l'edit locale resta possibile)
    useEffect(() => { if (dailyGoal != null && dailyGoal > 0) setDayGoal(dailyGoal); }, [dailyGoal]);
    // M-08: l'obiettivo modificato qui va SCRITTO sul control, altrimenti il
    // servizio continua a dividere un obiettivo diverso da quello mostrato
    const goalDirty = dailyGoal != null && toNum(dayGoal) !== toNum(dailyGoal);
    async function saveDayGoal() {
        setBusy('goal');
        try {
            await updateOmegaParams({ dailyGoal: toNum(dayGoal) });
            toast.success('Obiettivo di giornata salvato', {
                description: `il servizio userà ${fmtEur(toNum(dayGoal))} al giorno`,
            });
        } catch (e) {
            toast.error('Salvataggio obiettivo fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(null); }
    }
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

    // §18 — UN SOLO poll dello stato scalper per TUTTE le card (prima ogni card
    // aperta ne teneva uno suo a 5 s: dieci missioni = dieci RPC al secondo,
    // non sincronizzate, con l'app desktop a fare da collo di bottiglia).
    // Si interrogano solo le missioni SEGUITE e non finite: le altre non hanno
    // un bot da mostrare.
    const [scalpers, setScalpers] = useState<Record<string, ScalperControl | null>>({});
    const scalperIds = useMemo(
        () => missions.filter((m) => m.followed !== false && m.phase_now !== 'finita').map((m) => m.event_id),
        [missions],
    );
    const scalperIdsKey = scalperIds.join(',');
    useEffect(() => {
        if (scalperIds.length === 0) { setScalpers({}); return; }
        let alive = true;
        const load = async () => {
            const out: Record<string, ScalperControl | null> = {};
            // in SERIE: una raffica parallela di N RPC è esattamente il carico
            // che stiamo togliendo
            for (const id of scalperIds) {
                if (!alive) return;
                try {
                    out[id] = (await fetchScalperState(id, 0)).control ?? null;
                } catch {
                    out[id] = null;          // servizio spento: il poll riprova
                }
            }
            if (alive) setScalpers(out);
        };
        void load();
        const t = window.setInterval(() => { void load(); }, 10_000);
        return () => { alive = false; window.clearInterval(t); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [scalperIdsKey]);

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
    // orologio del pannello: serve alla FINESTRA OPERATIVA degli eventi e
    // all'età della cache (un evento "finito" va tolto anche senza un reload)
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 30_000);
        return () => window.clearInterval(t);
    }, []);
    const eventById = useMemo(() => new Map(events.map(e => [e.event_id, e])), [events]);
    /**
     * Audit 12/09 — SOLO le partite della finestra operativa (non ancora finite).
     * `get_omega_events` restituisce tutta la cache senza filtro di data: il
     * 12/09 la lista mostrava 73 partite del 09/09 marcate "FINITA" mentre il
     * contatore diceva 0. UNA definizione sola (lib/omega.eventIsOperable) per
     * la lista, per il contatore e per il menu della modalità manuale.
     */
    const windowEvents = useMemo(() => filterEventsInWindow(events, nowMs), [events, nowMs]);
    const cacheAt = useMemo(() => eventsCacheUpdatedAt(events), [events]);
    const cacheAgeS = ageSeconds(cacheAt, nowMs);
    /** true = la cache ha SOLO partite già finite: è ferma, va aggiornata */
    const cacheStale = events.length > 0 && windowEvents.length === 0;
    // stato REC per evento (anche per missioni non visibili in lista): il
    // pulsante "Segui live" delle righe-evento parte dallo stato DB se noto
    const missionByEvent = useMemo(() => new Map(missions.map(m => [m.event_id, m])), [missions]);
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
        return windowEvents.filter(e => !visible.has(e.event_id));
    }, [windowEvents, activeMissions, otherMissions]);

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

    // partite ancora OPERABILI = esattamente quelle che si vedono in lista
    // (finestra operativa): un contatore che non corrisponde alla lista sotto
    // è la prima cosa che fa perdere fiducia nella pagina.
    const liveMissionsCount = useMemo(
        () => missions.filter(m => m.status === 'active' || m.status === 'paused').length,
        [missions]);
    const eventsCount = windowEvents.length > 0 ? windowEvents.length : liveMissionsCount;
    const goal = toNum(dayGoal);
    /**
     * Audit 12/09 — il target per partita è UNO SOLO in tutta la pagina: quello
     * che il SERVIZIO sta usando (`stats.target_match` = obiettivo ÷ partite
     * ancora in finestra), lo stesso del KPI in alto. Il calcolo locale resta
     * solo come ripiego a bot fermo ed è DICHIARATO. Prima si divideva per gli
     * eventi della cache: con la cache ferma il denominatore era 0 e il
     * "suggerito" diventava l'INTERO obiettivo di giornata (100 € su UNA
     * partita) mentre il KPI diceva 0,17 €.
     */
    const targetFromService = targetMatch != null && Number.isFinite(targetMatch) && Number(targetMatch) > 0;
    const targetShown = targetFromService
        ? Number(targetMatch)
        : eventsCount > 0 ? Math.round((goal / eventsCount) * 100) / 100 : 0;
    /** partite che il SERVIZIO considera ancora da giocare (ripiego: la lista) */
    const remainingShown = matchesRemaining != null && Number.isFinite(matchesRemaining)
        ? Number(matchesRemaining) : eventsCount;
    const remainingShownLabel = () => (remainingShown > 0
        ? `${remainingShown} partite in finestra` : 'le partite in finestra');
    // Target precompilato del dialog ATTIVA (CERT. 12/09, review).
    // ``targetShown`` e' l'obiettivo diviso per TUTTE le partite in finestra:
    // con 250 EUR su ~600 partite vale 0,17 EUR, e una missione attivata senza
    // toccare il campo si chiuderebbe al primo centesimo di profitto. All'altro
    // estremo, a servizio fermo e lista vuota, il ripiego era l'INTERO obiettivo
    // su una sola partita. Si precompila quindi entro limiti sensati e si
    // dichiara da dove viene il numero.
    const TARGET_MIN_EUR = 1;
    const targetSuggested = Math.min(
        Math.max(targetShown > 0 ? targetShown : goal, TARGET_MIN_EUR),
        Math.max(goal, TARGET_MIN_EUR),
    );
    /** da dove viene il suggerimento, per dirlo all'utente sotto al campo */
    const targetSuggestedNote = targetShown > 0
        ? (targetShown < TARGET_MIN_EUR
            ? `obiettivo diviso per ${remainingShownLabel()} = ${fmtEur(targetShown)}, arrotondato al minimo di ${fmtEur(TARGET_MIN_EUR)}`
            : `obiettivo diviso per ${remainingShownLabel()}`)
        : 'nessuna stima dal servizio: e’ l’obiettivo intero, correggilo';
    // barra di giornata: SOLO le missioni di OGGI (review 16/07: le attive di
    // ieri restano in lista per essere gestite, ma il loro P&L è di ieri e non
    // deve gonfiare l'avanzamento verso l'obiettivo di oggi)
    // M-08: la GIORNATA è quella di Roma (come il servizio e la RPC), non
    // quella del browser: dopo mezzanotte le due non coincidono
    const todayStr = romeDay();
    const totalRealized = missions
        .filter(m => (m.mission_date ?? todayStr) === todayStr)
        .reduce((s, m) => s + missionRealized(m), 0);
    // CERT. 12/09 — la percentuale di avanzamento della giornata la mostra UNA
    // sola barra, quella in cima alla pagina (alimentata dalla RPC). Qui la
    // seconda barra e' stata rimossa perche' sommava il realizzato delle
    // MISSIONI mentre quella in alto somma le POSIZIONI: due percentuali
    // diverse per la stessa giornata. ``totalRealized`` resta perche' la riga
    // "Di quel totale, X" dichiara quanto arriva dalle missioni.

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

    // ---- feed live (scanner) per le missioni attive -----------------------
    // feed live dello scanner (punteggio 2s, CS/HT in stream): un canale condiviso
    // CERT. 12/09 — servono ANCHE gli `updated_at`: senza, la card non puo'
    // datare la "quota live" che mostra accanto al bottone che spende, e la
    // dichiarava live anche su un book fermo. `useScanLiveFeed` butta via quel
    // campo, `useScanLiveFeedRows` no.
    const liveRows = useScanLiveFeedRows(missions.map((m) => m.event_id));

    // ---- righe lista -----------------------------------------------------
    function activeRow(m: MissionRow) {
        const phase = (m.phase_now ?? 'pre') as MissionPhase;
        const meta = PHASE_META[phase] ?? PHASE_META.pre;
        // punteggio/minuto LIVE dal feed (2s) quando c'è, altrimenti quelli del servizio
        const lp = liveRows[m.event_id]?.payload ?? null;
        const lpAt = liveRows[m.event_id]?.updated_at ?? null;
        const liveMinute = lp?.minute ?? m.minute;
        const liveHome = lp?.score_home ?? m.score_home;
        const liveAway = lp?.score_away ?? m.score_away;
        const realized = missionRealized(m);
        const target = toNum(m.target);
        const pct = goalProgressPct(realized, target);
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
                    {phase !== 'pre' && phase !== 'finita' && liveMinute != null && (
                        <span className="text-xs text-slate-400 tabular-nums">{toNum(liveMinute)}'</span>
                    )}
                    {/* punteggio LIVE grande (feed scanner se presente) */}
                    <span className="font-display font-black text-2xl tabular-nums tracking-tight" title={lp ? 'punteggio dal feed live (2s)' : 'punteggio dal ciclo del servizio'}>
                        {phase === 'pre' ? timeLabel(m.kickoff) : `${toNum(liveHome)} - ${toNum(liveAway)}`}
                    </span>
                    {lp && phase !== 'pre' && phase !== 'finita' && (
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" title="feed live attivo" aria-hidden />
                    )}
                    <RowActions
                        eventId={m.event_id}
                        eventName={m.event_name ?? m.event_id}
                        kickoff={m.kickoff}
                        fixtureId={fixtureId}
                        recording={m.recording}
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
                        <MissionCard mission={m} mode={mode} live={lp ?? null} liveAt={lpAt} scalper={scalpers[m.event_id] ?? null} onChanged={() => { reload().catch(() => { /* il polling riprova */ }); }} />
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
                    recording={missionByEvent.get(ev.event_id)?.recording}
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
                        recording={m?.recording}
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
                    {/* M-08: l'obiettivo si SALVA sul control (prima restava
                        solo nello stato locale e il servizio non lo vedeva) */}
                    <label className="block">
                        <span className="text-xs text-slate-400">Obiettivo giornata (€)</span>
                        <span className="mt-1 flex items-center gap-1">
                            <input
                                type="number" min={0} max={OMEGA_DAILY_GOAL_MAX} step={10} value={dayGoal}
                                aria-label="Obiettivo giornata (€)"
                                onChange={e => setDayGoal(toNum(e.target.value))}
                                className="w-32 rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                            />
                            <Button
                                size="sm" variant="outline"
                                disabled={busy === 'goal' || !goalDirty}
                                onClick={saveDayGoal}
                                data-testid="mission-save-goal"
                                title="scrive l'obiettivo sul servizio (omega_control.daily_goal)"
                            >
                                {busy === 'goal' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Salva'}
                            </Button>
                        </span>
                        {goalDirty && (
                            <span className="text-[11px] text-amber-300 block" data-testid="mission-goal-dirty">
                                obiettivo non salvato: il servizio usa ancora {fmtEur(toNum(dailyGoal))}
                            </span>
                        )}
                    </label>
                    <div>
                        <div className="text-xs text-slate-400" title="partite non ancora finite presenti in cache: sono esattamente quelle elencate qui sotto">
                            Partite attivabili
                        </div>
                        <div className="text-2xl font-display font-black tabular-nums" data-testid="mission-events-count">{eventsCount}</div>
                        <div className="text-[10px] text-slate-500">
                            {cacheAgeS != null
                                ? `elenco aggiornato ${fmtAge(cacheAgeS)} fa`
                                : 'elenco senza orario di aggiornamento'}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-slate-400" title="lo stesso numero del KPI «Target / operazione» in cima alla pagina: obiettivo diviso le partite ancora in finestra">
                            Target / partita
                        </div>
                        <div className="text-2xl font-display font-black tabular-nums text-secondary" data-testid="mission-target-match">
                            {targetShown > 0 ? fmtEur(targetShown) : '—'}
                        </div>
                        <div className="text-[10px] text-slate-500" data-testid="mission-target-source">
                            {targetFromService
                                ? `dal servizio · ${remainingShown} partite rimaste`
                                : 'bot fermo: stima locale (obiettivo ÷ partite attivabili)'}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-slate-400">Missioni</div>
                        <div className="text-2xl font-display font-black tabular-nums">
                            {summary.missions_active}<span className="text-slate-500 text-lg"> / {summary.missions_total}</span>
                        </div>
                        <div className="text-[10px] text-slate-500">attive / totali</div>
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
                {/*
                    Audit 12/09 — QUI NON c'è più una seconda barra di giornata.
                    Ne esisteva una che sommava il realizzato delle MISSIONI, e
                    la barra in cima alla pagina somma le POSIZIONI della giornata
                    dalla RPC: due numeri diversi per la stessa cosa, nella stessa
                    schermata. La giornata si legge UNA volta sola, in alto.
                    Qui resta il contributo delle missioni, dichiarato per quello
                    che è.
                */}
                <div className="text-[11px] text-slate-500" data-testid="mission-day-note">
                    Avanzamento della giornata e obiettivo: nella barra in cima alla pagina (numeri della RPC).
                    Di quel totale, <b className={totalRealized >= 0 ? 'text-emerald-400' : 'text-red-400'} data-testid="mission-day-realized">{fmtSignedEur(totalRealized)}</b>
                    {' '}viene dalle missioni attivate oggi.
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
                    {/* stato vuoto CHIARO (audit 12/09): la lista non mostra più
                        le partite già finite, quindi quando non c'è nulla da
                        attivare bisogna dire PERCHÉ e da quando */}
                    {!onlyActive && plainEvents.length === 0 && (
                        <div className="text-center text-xs text-muted-foreground py-6 space-y-1" data-testid="mission-events-empty">
                            {cacheStale ? (
                                <>
                                    <div className="text-amber-300">
                                        nessuna partita nella finestra operativa: in elenco ci sono solo partite già finite
                                    </div>
                                    <div>
                                        l'elenco eventi è fermo{cacheAgeS != null ? ` da ${fmtAge(cacheAgeS)}` : ''}
                                        {cacheAt ? ` (ultimo aggiornamento ${fmtTime(cacheAt)})` : ''} —
                                        premi "Aggiorna eventi" con il servizio locale acceso (avvia_omega_service.bat)
                                    </div>
                                </>
                            ) : (
                                <div>nessun evento in cache — premi "Aggiorna eventi" (servizio locale acceso)</div>
                            )}
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
                        <span className="text-[11px] text-slate-500" data-testid="mission-target-note">suggerito: {fmtEur(targetSuggested)} ({targetSuggestedNote})</span>
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
