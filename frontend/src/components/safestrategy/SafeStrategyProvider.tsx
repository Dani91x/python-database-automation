// ============================================================================
// SafeStrategyProvider.tsx — plumbing dati della sezione SAFE STRATEGY.
//
// FONTE UNICA: lo SCANNER AUTONOMO backend (Betfair/safe_strategy → tabella
// safe_strategy_scan + heartbeat safe_strategy_status). Nessuna iscrizione
// manuale: lo scanner monitora TUTTI gli eventi calcio+tennis in-play del
// momento e questo provider li valuta col motore PURO certificato
// (lib/safeStrategy.ts). Richiede migrations/safe_strategy_scan.sql.
//
// Efficienza (uso a piena potenza, tante schede aperte):
//   · UN solo canale realtime per la tabella scan (mai N canali per evento);
//   · aggiornamenti COALIZZATI (flush ogni 400ms): decine di righe live non
//     scatenano decine di re-render al secondo;
//   · merge "più recente vince" su updated_at (fetch iniziale vs realtime).
//
// Montato globalmente (App.tsx): i segnali nuovi emettono un toast cliccabile
// verso /safe-strategy da qualunque schermata. NESSUN ordine parte da qui.
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
    fetchScanRows,
    fetchScanStatus,
    subscribeScanRows,
    subscribeScanStatus,
    type CalcioScanPayload,
    type ScanRow,
    type ScanStatusRow,
    type TennisScanPayload,
} from '@/lib/safeStrategyScan';
import {
    DEFAULT_PARAMS,
    mergeParams,
    buildFootballCtxFromScan,
    buildTennisCtxFromScan,
    evaluateFootballAll,
    evaluateTennis,
    footballCandidates,
    tennisCandidates,
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
/** poll di backup (il realtime è la via primaria) */
const BACKUP_POLL_MS = 30_000;
/** flush coalizzato degli aggiornamenti realtime */
const FLUSH_MS = 400;

export interface FootballMonitor {
    eventId: string;
    payload: CalcioScanPayload;
    ctx: FootballMatchCtx;
    evaluations: VariantEvaluation[];
    /** true = in-play SENZA riferimento pre-KO catturato dallo scanner
     *  (scanner partito a match iniziato): condizioni pre-match n/d per scelta */
    preMatchMissing: boolean;
}
export interface TennisMonitor {
    eventId: string;
    payload: TennisScanPayload;
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
    /** heartbeat dello scanner backend (null = mai visto) */
    scanStatus: ScanStatusRow | null;
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

function newerRow(prev: ScanRow | null, next: ScanRow): ScanRow {
    if (!prev?.updated_at || !next.updated_at) return next;
    return Date.parse(next.updated_at) >= Date.parse(prev.updated_at) ? next : prev;
}

export function SafeStrategyProvider({ children }: { children: ReactNode }) {
    const { user } = useAuth();
    const userId = user?.id ?? null;
    const navigate = useNavigate();
    const location = useLocation();

    const [params, setParams] = useState<SafeStrategyParams>(loadParams);
    const [rowsMap, setRowsMap] = useState<Record<string, ScanRow>>({});
    const [scanStatus, setScanStatus] = useState<ScanStatusRow | null>(null);
    const [stabMap, setStabMap] = useState<Record<string, ScoreStability>>({});
    const [tnStabMap, setTnStabMap] = useState<Record<string, TennisScoreStability>>({});
    const [signals, setSignals] = useState<ActiveSignal[]>([]);

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

    // -------------------------------------------- applicazione righe (coalizzata)
    // ref con l'ultima riga ACCETTATA per evento (per il confronto updated_at
    // fuori dai setState) + buffer degli eventi realtime in attesa di flush.
    const rowsRef = useRef<Record<string, ScanRow>>({});
    const pendingUpsertRef = useRef(new Map<string, ScanRow>());
    const pendingDeleteRef = useRef(new Set<string>());
    const flushTimerRef = useRef<number | null>(null);

    const applyRows = useCallback((upserts: ScanRow[], deletes: string[]) => {
        const accepted: ScanRow[] = [];
        for (const row of upserts) {
            const cur = rowsRef.current[row.event_id] ?? null;
            const next = newerRow(cur, row);
            if (next === cur) continue;
            rowsRef.current[row.event_id] = next;
            accepted.push(next);
        }
        for (const id of deletes) delete rowsRef.current[id];
        if (accepted.length === 0 && deletes.length === 0) return;

        // tracker stabilità punteggio (anti-blip): alimentati SOLO dalle righe accettate
        const nowMs = Date.now();
        setStabMap((prev) => {
            let next = prev;
            for (const row of accepted) {
                if (row.sport !== 'calcio') continue;
                const p = row.payload as CalcioScanPayload;
                const cur = next[row.event_id] ?? null;
                const upd = trackScoreStability(cur, p.minute, p.score_home, p.score_away, nowMs);
                if (upd !== cur && upd !== null) next = { ...next, [row.event_id]: upd };
            }
            for (const id of deletes) {
                if (id in next) {
                    next = { ...next };
                    delete next[id];
                }
            }
            return next;
        });
        setTnStabMap((prev) => {
            let next = prev;
            for (const row of accepted) {
                if (row.sport !== 'tennis') continue;
                const p = row.payload as TennisScanPayload;
                const cur = next[row.event_id] ?? null;
                const upd = trackTennisScoreStability(cur, tennisScoreKey(p.sets, p.games), nowMs);
                if (upd !== cur && upd !== null) next = { ...next, [row.event_id]: upd };
            }
            for (const id of deletes) {
                if (id in next) {
                    next = { ...next };
                    delete next[id];
                }
            }
            return next;
        });
        setRowsMap((prev) => {
            const next = { ...prev };
            for (const row of accepted) next[row.event_id] = row;
            for (const id of deletes) delete next[id];
            return next;
        });
    }, []);

    const scheduleFlush = useCallback(() => {
        if (flushTimerRef.current !== null) return;
        flushTimerRef.current = window.setTimeout(() => {
            flushTimerRef.current = null;
            const upserts = [...pendingUpsertRef.current.values()];
            const deletes = [...pendingDeleteRef.current];
            pendingUpsertRef.current.clear();
            pendingDeleteRef.current.clear();
            applyRows(upserts, deletes);
        }, FLUSH_MS);
    }, [applyRows]);

    // ------------------------------------------------ fetch iniziale + realtime
    useEffect(() => {
        if (!userId) {
            rowsRef.current = {};
            setRowsMap({});
            setScanStatus(null);
            return;
        }
        let alive = true;
        const load = () => {
            fetchScanRows()
                .then((rows) => {
                    if (!alive) return;
                    // il fetch è lo stato COMPLETO: le righe assenti sono sparite
                    const present = new Set(rows.map((r) => r.event_id));
                    const gone = Object.keys(rowsRef.current).filter((id) => !present.has(id));
                    applyRows(rows, gone);
                })
                .catch(() => {
                    /* migrazione non applicata o rete: si ritenta al prossimo giro */
                });
            fetchScanStatus()
                .then((s) => {
                    if (alive) setScanStatus(s);
                })
                .catch(() => {});
        };
        load();
        const poll = window.setInterval(load, BACKUP_POLL_MS);
        const offRows = subscribeScanRows((ev) => {
            if (ev.type === 'upsert') {
                pendingUpsertRef.current.set(ev.row.event_id, ev.row);
                pendingDeleteRef.current.delete(ev.row.event_id);
            } else {
                pendingDeleteRef.current.add(ev.eventId);
                pendingUpsertRef.current.delete(ev.eventId);
            }
            scheduleFlush();
        });
        const offStatus = subscribeScanStatus((row) => {
            if (row) setScanStatus(row);
        });
        return () => {
            alive = false;
            window.clearInterval(poll);
            offRows();
            offStatus();
            if (flushTimerRef.current !== null) {
                window.clearTimeout(flushTimerRef.current);
                flushTimerRef.current = null;
            }
        };
    }, [userId, applyRows, scheduleFlush]);

    // ------------------------------------------------- valutazione (motore puro)
    const derived = useMemo(() => {
        const nowMs = Date.now();
        const football: FootballMonitor[] = [];
        const tennis: TennisMonitor[] = [];
        for (const row of Object.values(rowsMap)) {
            if (row.sport === 'calcio') {
                const p = row.payload as CalcioScanPayload;
                const stab = stabMap[row.event_id] ?? null;
                const stable =
                    stab && `${p.score_home}-${p.score_away}` === stab.scoreKey ? stab : null;
                const ctx = buildFootballCtxFromScan(
                    row.event_id,
                    p,
                    stable?.sinceMinute ?? null,
                    stable ? (nowMs - stable.sinceMs) / 1000 : null,
                );
                football.push({
                    eventId: row.event_id,
                    payload: p,
                    ctx,
                    evaluations: evaluateFootballAll(ctx, params),
                    preMatchMissing: ctx.inplay && ctx.preMatch === null,
                });
            } else {
                const p = row.payload as TennisScanPayload;
                const stab = tnStabMap[row.event_id] ?? null;
                const key = tennisScoreKey(p.sets ?? null, p.games ?? null);
                const observed =
                    stab && key && stab.scoreKey === key ? (nowMs - stab.sinceMs) / 1000 : null;
                const ctx = buildTennisCtxFromScan(row.event_id, p, observed);
                tennis.push({
                    eventId: row.event_id,
                    payload: p,
                    ctx,
                    evaluation: evaluateTennis(ctx, params.tennis),
                });
            }
        }
        const candidates = [
            ...football.flatMap((m) => footballCandidates(m.ctx, m.evaluations)),
            ...tennis.flatMap((m) => tennisCandidates(m.ctx, m.evaluation)),
        ];
        return { football, tennis, candidates };
    }, [rowsMap, stabMap, tnStabMap, params]);

    // ------------------------------------------- riconciliazione segnali + toast
    const signalsRef = useRef<ActiveSignal[]>([]);
    useEffect(() => {
        const { next, fresh } = reconcileSignals(signalsRef.current, derived.candidates, Date.now());
        signalsRef.current = next;
        setSignals(next);
        if (fresh.length === 0) return;
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
            scanStatus,
        }),
        [params, saveParams, resetParams, derived.football, derived.tennis, signals, scanStatus],
    );

    return <SafeStrategyContext.Provider value={value}>{children}</SafeStrategyContext.Provider>;
}
