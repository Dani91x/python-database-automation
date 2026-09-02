// ============================================================================
// SafeStrategyProvider.tsx — plumbing dati della sezione SAFE STRATEGY.
//
// Monta le sottoscrizioni ai flussi GIÀ ESISTENTI (nessuna fonte dati nuova):
//   · calcio: get_live_follows (poll 20s) + realtime live_now (runner, ~5s)
//             + get_betfair_odds (1X2 pre-match, una volta per evento)
//   · tennis: get_tennis_follows (poll 20s) + realtime tennis_live_now (~2s)
// e per ogni aggiornamento invoca il motore PURO lib/safeStrategy.ts.
//
// Montato globalmente (App.tsx, dentro BrowserRouter): i segnali scattano anche
// quando l'utente è su un'altra schermata → toast cliccabile che porta a
// /safe-strategy. Sulla pagina stessa il toast è soppresso (i segnali sono già
// in vista). NESSUN ordine viene mai piazzato da qui: solo segnalazione.
// ============================================================================
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/useAuth';
import {
    fetchLiveFollows,
    fetchLiveNow,
    subscribeLiveNow,
    type LiveFollow,
    type LiveNowRow,
} from '@/lib/live';
import { fetchBetfairOdds } from '@/lib/betfair';
import {
    fetchTennisFollows,
    fetchTennisNow,
    subscribeTennisNow,
    type TennisFollow,
    type TennisLiveNowRow,
} from '@/lib/tennis';
import {
    DEFAULT_PARAMS,
    mergeParams,
    buildFootballCtx,
    buildTennisCtx,
    evaluateFootballAll,
    evaluateTennis,
    footballCandidates,
    tennisCandidates,
    parsePreMatch1x2,
    reconcileSignals,
    tennisScoreKey,
    trackScoreStability,
    trackTennisScoreStability,
    VARIANT_META,
    type ActiveSignal,
    type FootballMatchCtx,
    type SafeStrategyParams,
    type ScoreStability,
    type TennisScoreStability,
    type TennisMatchCtx,
    type VariantEvaluation,
} from '@/lib/safeStrategy';

const STORAGE_KEY = 'safe_strategy_params_v1';
const FOLLOWS_POLL_MS = 20_000;
/** stati follow per cui vale la pena monitorare (stessi del runner). */
const MONITORED_STATUS = new Set(['PENDING', 'STREAMING']);

// -------------------------- riferimento 1X2 pre-match CERTIFICATO (blindatura)
// La tabella betfair_market_odds NON è congelata al kickoff (bat rilanciato o
// refresh manuale in-play la sovrascrivono con quote live). Regola: il
// riferimento si cattura SOLO mentre now < open_date (prima del KO qualunque
// snapshot è pre-match per definizione), si ricattura ogni 5' fino al KO
// (closing line) e si PERSISTE in localStorage: sopravvive a riavvii dell'app
// a partita in corso. Se al KO non è mai stato catturato → resta n/d, mai
// un riferimento contaminato.
const PRE_SNAPSHOT_KEY = 'safe_strategy_prematch_v1';
const PRE_REFRESH_MS = 5 * 60 * 1000;
const PRE_RETRY_MS = 60 * 1000;
const PRE_TTL_MS = 48 * 60 * 60 * 1000;

interface PreMatchRef {
    home: number;
    draw: number;
    away: number;
    capturedAtMs: number;
}

function loadPreRefs(): Record<string, PreMatchRef> {
    try {
        const raw = localStorage.getItem(PRE_SNAPSHOT_KEY);
        const obj = raw ? (JSON.parse(raw) as Record<string, unknown>) : null;
        if (!obj || typeof obj !== 'object') return {};
        const out: Record<string, PreMatchRef> = {};
        const cutoff = Date.now() - PRE_TTL_MS;
        for (const [k, v] of Object.entries(obj)) {
            const r = v as Partial<PreMatchRef> | null;
            if (
                r &&
                typeof r.home === 'number' &&
                typeof r.draw === 'number' &&
                typeof r.away === 'number' &&
                typeof r.capturedAtMs === 'number' &&
                r.capturedAtMs >= cutoff
            ) {
                out[k] = { home: r.home, draw: r.draw, away: r.away, capturedAtMs: r.capturedAtMs };
            }
        }
        return out;
    } catch {
        return {};
    }
}
function savePreRefs(refs: Record<string, PreMatchRef>): void {
    try {
        localStorage.setItem(PRE_SNAPSHOT_KEY, JSON.stringify(refs));
    } catch {
        /* storage non disponibile: il riferimento resta per la sessione */
    }
}

/** merge "il più recente vince" (stesso pattern di SeguiLive): il fetch iniziale
 *  può risolversi DOPO un push realtime più fresco — mai regredire a uno
 *  snapshot più vecchio (falserebbe anche l'ancora post-gol della Punta). */
function newerRow<T extends { updated_at: string | null }>(prev: T | null, next: T): T {
    if (!prev?.updated_at || !next.updated_at) return next;
    return Date.parse(next.updated_at) >= Date.parse(prev.updated_at) ? next : prev;
}

/** rimuove chiavi da una mappa di stato senza crearne una nuova se nulla cambia. */
function dropKeys<T>(prev: Record<string, T>, keys: string[]): Record<string, T> {
    let changed = false;
    const next = { ...prev };
    for (const k of keys) {
        if (k in next) {
            delete next[k];
            changed = true;
        }
    }
    return changed ? next : prev;
}

export interface FootballMonitor {
    follow: LiveFollow;
    ctx: FootballMatchCtx;
    evaluations: VariantEvaluation[];
    /** true = partita in-play SENZA riferimento pre-match certificato (app
     *  aperta dopo il kickoff): condizioni pre-match n/d per scelta, non per bug */
    preMatchMissing: boolean;
}
export interface TennisMonitor {
    follow: TennisFollow;
    ctx: TennisMatchCtx;
    evaluation: VariantEvaluation;
}

interface SafeStrategyValue {
    params: SafeStrategyParams;
    saveParams: (p: SafeStrategyParams) => void;
    resetParams: () => void;
    football: FootballMonitor[];
    tennis: TennisMonitor[];
    signals: ActiveSignal[];
}

const SafeStrategyContext = createContext<SafeStrategyValue | null>(null);

export function useSafeStrategy(): SafeStrategyValue {
    const ctx = useContext(SafeStrategyContext);
    if (!ctx) throw new Error('useSafeStrategy va usato dentro <SafeStrategyProvider>');
    return ctx;
}

function loadParams(): SafeStrategyParams {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return mergeParams(raw ? JSON.parse(raw) : null);
    } catch {
        return DEFAULT_PARAMS;
    }
}

export function SafeStrategyProvider({ children }: { children: ReactNode }) {
    const { user } = useAuth();
    const userId = user?.id ?? null;
    const navigate = useNavigate();
    const location = useLocation();

    const [params, setParams] = useState<SafeStrategyParams>(loadParams);
    const [follows, setFollows] = useState<LiveFollow[]>([]);
    const [tnFollows, setTnFollows] = useState<TennisFollow[]>([]);
    const [nowMap, setNowMap] = useState<Record<string, LiveNowRow | null>>({});
    const [tnNowMap, setTnNowMap] = useState<Record<string, TennisLiveNowRow | null>>({});
    const [preRefs, setPreRefs] = useState<Record<string, PreMatchRef>>(loadPreRefs);
    const [stabMap, setStabMap] = useState<Record<string, ScoreStability>>({});
    const [tnStabMap, setTnStabMap] = useState<Record<string, TennisScoreStability>>({});
    const [signals, setSignals] = useState<ActiveSignal[]>([]);

    // path corrente in ref: il toast decide al momento dello scatto, senza
    // riagganciare gli effetti dati alla route.
    const pathRef = useRef(location.pathname);
    useEffect(() => {
        pathRef.current = location.pathname;
    }, [location.pathname]);

    const saveParams = useCallback((p: SafeStrategyParams) => {
        const merged = mergeParams(p);
        setParams(merged);
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
        } catch {
            /* storage non disponibile: i parametri restano per la sessione */
        }
    }, []);
    const resetParams = useCallback(() => saveParams(DEFAULT_PARAMS), [saveParams]);

    // ------------------------------------------------------ poll liste follow
    useEffect(() => {
        if (!userId) {
            setFollows([]);
            setTnFollows([]);
            return;
        }
        let alive = true;
        const load = async () => {
            try {
                const rows = await fetchLiveFollows();
                if (alive) setFollows(rows);
            } catch {
                /* transitorio: si ritenta al prossimo giro */
            }
            try {
                const rows = await fetchTennisFollows();
                if (alive) setTnFollows(rows);
            } catch {
                /* idem */
            }
        };
        void load();
        const t = window.setInterval(load, FOLLOWS_POLL_MS);
        return () => {
            alive = false;
            window.clearInterval(t);
        };
    }, [userId]);

    // ------------------------------------------- snapshot live_now (calcio)
    // ref con l'ultimo snapshot ACCETTATO per evento: consente il confronto
    // updated_at fuori dai setState (unico writer: handleFootballNow).
    const fbNowRef = useRef<Record<string, LiveNowRow>>({});
    const handleFootballNow = useCallback((eventId: string, row: LiveNowRow | null) => {
        if (!row) return; // payload vuoto: nessuna informazione nuova
        const cur = fbNowRef.current[eventId] ?? null;
        const next = newerRow(cur, row);
        if (next === cur) return; // snapshot più vecchio di quello già mostrato
        fbNowRef.current[eventId] = next;
        setStabMap((prev) => {
            const curStab = prev[eventId] ?? null;
            const nextStab = trackScoreStability(curStab, next.minute, next.score_home, next.score_away, Date.now());
            if (nextStab === curStab || nextStab === null) return prev;
            return { ...prev, [eventId]: nextStab };
        });
        setNowMap((prev) => ({ ...prev, [eventId]: next }));
    }, []);

    const preBusyRef = useRef(new Set<string>());
    const preLastTryRef = useRef(new Map<string, number>());
    const fbSubsRef = useRef(new Map<string, () => void>());
    useEffect(() => {
        const wanted = new Set(
            follows.filter((f) => MONITORED_STATUS.has(f.status)).map((f) => f.event_id),
        );
        const removed: string[] = [];
        for (const [id, off] of fbSubsRef.current) {
            if (!wanted.has(id)) {
                off();
                fbSubsRef.current.delete(id);
                removed.push(id);
            }
        }
        if (removed.length > 0) {
            // pruning: gli eventi usciti dal monitoraggio non servono più in memoria
            // (preRefs resta: è persistito con TTL 48h e serve se il follow riappare)
            for (const id of removed) {
                delete fbNowRef.current[id];
                preLastTryRef.current.delete(id);
            }
            setNowMap((prev) => dropKeys(prev, removed));
            setStabMap((prev) => dropKeys(prev, removed));
        }
        for (const id of wanted) {
            if (fbSubsRef.current.has(id)) continue;
            fbSubsRef.current.set(id, subscribeLiveNow(id, (row) => handleFootballNow(id, row)));
            // il realtime notifica solo i CAMBI futuri → fetch immediato (pattern live.ts)
            void fetchLiveNow(id)
                .then((row) => handleFootballNow(id, row))
                .catch(() => {});
        }
    }, [follows, handleFootballNow]);

    // -------------------------------------- snapshot tennis_live_now (tennis)
    const tnNowRef = useRef<Record<string, TennisLiveNowRow>>({});
    const handleTennisNow = useCallback((eventId: string, row: TennisLiveNowRow | null) => {
        if (!row) return; // payload vuoto: nessuna informazione nuova
        const cur = tnNowRef.current[eventId] ?? null;
        const next = newerRow(cur, row);
        if (next === cur) return; // snapshot più vecchio di quello già mostrato
        tnNowRef.current[eventId] = next;
        setTnStabMap((prev) => {
            const curStab = prev[eventId] ?? null;
            const key = tennisScoreKey(next.score?.sets ?? null, next.score?.games ?? null);
            const nextStab = trackTennisScoreStability(curStab, key, Date.now());
            if (nextStab === curStab || nextStab === null) return prev;
            return { ...prev, [eventId]: nextStab };
        });
        setTnNowMap((prev) => ({ ...prev, [eventId]: next }));
    }, []);

    const tnSubsRef = useRef(new Map<string, () => void>());
    useEffect(() => {
        const wanted = new Set(
            tnFollows.filter((f) => MONITORED_STATUS.has(f.status)).map((f) => f.event_id),
        );
        const removed: string[] = [];
        for (const [id, off] of tnSubsRef.current) {
            if (!wanted.has(id)) {
                off();
                tnSubsRef.current.delete(id);
                removed.push(id);
            }
        }
        if (removed.length > 0) {
            for (const id of removed) delete tnNowRef.current[id];
            setTnNowMap((prev) => dropKeys(prev, removed));
            setTnStabMap((prev) => dropKeys(prev, removed));
        }
        for (const id of wanted) {
            if (tnSubsRef.current.has(id)) continue;
            tnSubsRef.current.set(id, subscribeTennisNow(id, (row) => handleTennisNow(id, row)));
            void fetchTennisNow(id)
                .then((row) => handleTennisNow(id, row))
                .catch(() => {});
        }
    }, [tnFollows, handleTennisNow]);

    // cleanup totale a smontaggio
    useEffect(
        () => () => {
            for (const off of fbSubsRef.current.values()) off();
            fbSubsRef.current.clear();
            for (const off of tnSubsRef.current.values()) off();
            tnSubsRef.current.clear();
        },
        [],
    );

    // --------------------------- 1X2 pre-match (riferimento favorita, 1 fetch)
    useEffect(() => {
        const nowMs = Date.now();
        for (const f of follows) {
            if (f.fixture_id == null) continue;
            if (!MONITORED_STATUS.has(f.status)) continue;
            const ko = Date.parse(f.open_date);
            // REGOLA DI CERTIFICAZIONE: cattura SOLO prima del kickoff — dopo,
            // la tabella quote può essere stata sovrascritta con valori in-play.
            if (!Number.isFinite(ko) || nowMs >= ko) continue;
            const ref = preRefs[f.event_id];
            if (ref && nowMs - ref.capturedAtMs < PRE_REFRESH_MS) continue; // ricattura ogni 5' → closing line
            if (preBusyRef.current.has(f.event_id)) continue;
            if (nowMs - (preLastTryRef.current.get(f.event_id) ?? 0) < PRE_RETRY_MS) continue;
            preBusyRef.current.add(f.event_id);
            preLastTryRef.current.set(f.event_id, nowMs);
            fetchBetfairOdds(String(f.fixture_id))
                .then((odds) => {
                    const parsed = parsePreMatch1x2(odds);
                    if (!parsed) return;
                    // ricontrollo al ritorno: se nel frattempo è scattato il KO, scarta
                    if (Date.now() >= ko) return;
                    setPreRefs((prev) => {
                        const next = { ...prev, [f.event_id]: { ...parsed, capturedAtMs: Date.now() } };
                        savePreRefs(next);
                        return next;
                    });
                })
                .catch(() => {
                    /* si ritenta non prima di PRE_RETRY_MS */
                })
                .finally(() => preBusyRef.current.delete(f.event_id));
        }
    }, [follows, preRefs]);

    // ------------------------------------------------- valutazione (motore puro)
    const derived = useMemo(() => {
        const nowMs = Date.now();
        const football: FootballMonitor[] = follows
            .filter((f) => MONITORED_STATUS.has(f.status))
            .map((f) => {
                const now = nowMap[f.event_id] ?? null;
                const stab = stabMap[f.event_id] ?? null;
                const stable =
                    stab && now && `${now.score_home}-${now.score_away}` === stab.scoreKey
                        ? stab
                        : null;
                const ref = preRefs[f.event_id] ?? null;
                const ctx = buildFootballCtx(
                    f,
                    now,
                    ref ? { home: ref.home, draw: ref.draw, away: ref.away } : null,
                    stable?.sinceMinute ?? null,
                    stable ? (nowMs - stable.sinceMs) / 1000 : null,
                );
                return {
                    follow: f,
                    ctx,
                    evaluations: evaluateFootballAll(ctx, params),
                    preMatchMissing: ctx.inplay && ref === null,
                };
            });

        const tennis: TennisMonitor[] = tnFollows
            .filter((f) => MONITORED_STATUS.has(f.status))
            .map((f) => {
                // fallback: se tennis_live_now non è ancora arrivato, il punteggio
                // della riga follow (stesso runner) evita un buco di dati.
                const now =
                    tnNowMap[f.event_id] ??
                    (f.score
                        ? ({
                              event_id: f.event_id,
                              inplay: f.inplay,
                              status: f.live_status,
                              state: null,
                              score: f.score,
                              points: null,
                              updated_at: f.updated_at,
                          } satisfies TennisLiveNowRow)
                        : null);
                const stab = tnStabMap[f.event_id] ?? null;
                const key = tennisScoreKey(now?.score?.sets ?? null, now?.score?.games ?? null);
                const observed =
                    stab && key && stab.scoreKey === key ? (nowMs - stab.sinceMs) / 1000 : null;
                const ctx = buildTennisCtx(f, now, observed);
                return { follow: f, ctx, evaluation: evaluateTennis(ctx, params.tennis) };
            });

        const candidates = [
            ...football.flatMap((m) => footballCandidates(m.ctx, m.evaluations)),
            ...tennis.flatMap((m) => tennisCandidates(m.ctx, m.evaluation)),
        ];
        return { football, tennis, candidates };
    }, [follows, tnFollows, nowMap, tnNowMap, preRefs, stabMap, tnStabMap, params]);

    // ------------------------------------------- riconciliazione segnali + toast
    const signalsRef = useRef<ActiveSignal[]>([]);
    useEffect(() => {
        const { next, fresh } = reconcileSignals(signalsRef.current, derived.candidates, Date.now());
        signalsRef.current = next;
        setSignals(next);
        if (fresh.length === 0) return;
        // sulla pagina Safe Strategy i segnali sono già in vista: niente toast
        if (pathRef.current === '/safe-strategy') return;
        for (const s of fresh) {
            const meta = VARIANT_META[s.variant];
            toast.warning(`🛡️ ${meta.short} — ${s.headline}`, {
                description: `${s.matchLabel} · ${s.contextAtTrigger}${
                    s.entryOdds != null ? ` · @${s.entryOdds.toFixed(2)}` : ''
                }`,
                duration: 20_000,
                action: { label: 'Apri', onClick: () => navigate('/safe-strategy') },
            });
        }
    }, [derived.candidates, navigate]);

    const value = useMemo<SafeStrategyValue>(
        () => ({
            params,
            saveParams,
            resetParams,
            football: derived.football,
            tennis: derived.tennis,
            signals,
        }),
        [params, saveParams, resetParams, derived.football, derived.tennis, signals],
    );

    return <SafeStrategyContext.Provider value={value}>{children}</SafeStrategyContext.Provider>;
}
