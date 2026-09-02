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
import { fetchBetfairOdds, type BetfairOdds } from '@/lib/betfair';
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
    reconcileSignals,
    trackScoreStability,
    VARIANT_META,
    type ActiveSignal,
    type FootballMatchCtx,
    type SafeStrategyParams,
    type ScoreStability,
    type TennisMatchCtx,
    type VariantEvaluation,
} from '@/lib/safeStrategy';

const STORAGE_KEY = 'safe_strategy_params_v1';
const FOLLOWS_POLL_MS = 20_000;
/** stati follow per cui vale la pena monitorare (stessi del runner). */
const MONITORED_STATUS = new Set(['PENDING', 'STREAMING']);
/** tentativi massimi di fetch delle quote pre-match per evento (no retry infinito). */
const PRE_MATCH_MAX_ATTEMPTS = 5;

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
    const [preMap, setPreMap] = useState<Record<string, BetfairOdds>>({});
    const [stabMap, setStabMap] = useState<Record<string, ScoreStability>>({});
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
            const nextStab = trackScoreStability(curStab, next.minute, next.score_home, next.score_away);
            if (nextStab === curStab || nextStab === null) return prev;
            return { ...prev, [eventId]: nextStab };
        });
        setNowMap((prev) => ({ ...prev, [eventId]: next }));
    }, []);

    const preAttemptsRef = useRef(new Map<string, number>());
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
            for (const id of removed) {
                delete fbNowRef.current[id];
                preAttemptsRef.current.delete(id);
            }
            setNowMap((prev) => dropKeys(prev, removed));
            setStabMap((prev) => dropKeys(prev, removed));
            setPreMap((prev) => dropKeys(prev, removed));
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
    const prePendingRef = useRef(new Set<string>());
    useEffect(() => {
        for (const f of follows) {
            if (f.fixture_id == null) continue;
            if (!MONITORED_STATUS.has(f.status)) continue;
            if (f.event_id in preMap || prePendingRef.current.has(f.event_id)) continue;
            // retry limitato: dopo N fallimenti l'evento resta senza riferimento
            // pre-match (condizioni relative = n/d) invece di martellare la RPC
            if ((preAttemptsRef.current.get(f.event_id) ?? 0) >= PRE_MATCH_MAX_ATTEMPTS) continue;
            prePendingRef.current.add(f.event_id);
            fetchBetfairOdds(String(f.fixture_id))
                .then((odds) => {
                    preAttemptsRef.current.delete(f.event_id);
                    setPreMap((prev) => ({ ...prev, [f.event_id]: odds }));
                })
                .catch(() => {
                    preAttemptsRef.current.set(
                        f.event_id,
                        (preAttemptsRef.current.get(f.event_id) ?? 0) + 1,
                    );
                })
                .finally(() => prePendingRef.current.delete(f.event_id));
        }
    }, [follows, preMap]);

    // ------------------------------------------------- valutazione (motore puro)
    const derived = useMemo(() => {
        const football: FootballMonitor[] = follows
            .filter((f) => MONITORED_STATUS.has(f.status))
            .map((f) => {
                const now = nowMap[f.event_id] ?? null;
                const stab = stabMap[f.event_id] ?? null;
                const stable =
                    stab && now && `${now.score_home}-${now.score_away}` === stab.scoreKey
                        ? stab.sinceMinute
                        : null;
                const ctx = buildFootballCtx(f, now, preMap[f.event_id] ?? null, stable);
                return { follow: f, ctx, evaluations: evaluateFootballAll(ctx, params) };
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
                const ctx = buildTennisCtx(f, now);
                return { follow: f, ctx, evaluation: evaluateTennis(ctx, params.tennis) };
            });

        const candidates = [
            ...football.flatMap((m) => footballCandidates(m.ctx, m.evaluations)),
            ...tennis.flatMap((m) => tennisCandidates(m.ctx, m.evaluation)),
        ];
        return { football, tennis, candidates };
    }, [follows, tnFollows, nowMap, tnNowMap, preMap, stabMap, params]);

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
