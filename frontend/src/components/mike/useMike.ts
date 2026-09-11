// ============================================================================
// useMike — stato del BOT MIKE per la pagina /mike.
//
// Stessa architettura di Omega/Safe: realtime (UN canale) + poll di sicurezza,
// guardie di sequenza e smontaggio, LIVE confermato SOLO in questa sessione
// (mai ereditato dal control). Il bot può NON esistere ancora (migrazione non
// applicata): `available` false e la pagina resta leggibile.
//
// DUE CORREZIONI (audit H5 + richiesta "le schede non si muovono"):
//   * le notifiche realtime sono DEBOUNCED (RELOAD_DEBOUNCE_MS): con 26 partite
//     seguite arrivavano decine di eventi al secondo e la UI ricaricava tutto;
//   * il battito del servizio (`heartbeat_at` / `stats.last_cycle`) NON fa
//     ricaricare nulla: il filtro sta in `subscribeMike` (controlSignature).
// ============================================================================
import { useCallback, useEffect, useRef, useState } from 'react';
import {
    activateMike, stopMike, updateMikeParams, fetchMikeState, fetchMikeRequests, requestMike,
    subscribeMike, mergeMikeParams, detectSettledEvents, requestInFlight, MIKE_PARAM_DEFAULTS,
    romeDayStartMs,
    type MikeActivity, type MikeAggregates, type MikeControl, type MikeEvent, type MikeMode,
    type MikeParams, type MikeRequest, type MikeRequestKind, type MikeTrade,
} from '@/lib/mike';

const POLL_MS = 15_000;
/** finestra minima fra due ricariche scatenate dal realtime (richiesta: ≥ 1,5 s) */
export const RELOAD_DEBOUNCE_MS = 1_500;

export interface MikeView {
    available: boolean;
    loading: boolean;
    busy: boolean;
    error: string | null;
    control: MikeControl | null;
    events: MikeEvent[];
    trades: MikeTrade[];
    activity: MikeActivity[];
    aggregates: MikeAggregates | null;
    requests: MikeRequest[];
    /** inizio della giornata operativa (ms): dal DB (RPC v2) o mezzanotte di Roma stimata qui */
    dayStartMs: number | null;
    /** 'rpc' = day_start dal DB (mike_bot_v2); 'client' = mezzanotte di Roma stimata dal client */
    dayStartSource: 'rpc' | 'client';
    params: MikeParams;
    mode: MikeMode;
    liveConfirmed: boolean;
    reload: () => Promise<void>;
    start: () => Promise<void>;
    stop: () => Promise<void>;
    setMode: (mode: MikeMode) => Promise<void>;
    saveParams: (p: MikeParams) => Promise<void>;
    request: (kind: MikeRequestKind, eventId: string) => Promise<number | null>;
    isRequestPending: (eventId: string, kind: MikeRequestKind) => boolean;
    freshSettled: MikeEvent[];
    /** richieste chiuse dopo l'ultimo giro: la pagina ne fa un toast (M1) */
    freshOutcomes: MikeRequest[];
}

export interface MikeHandlers {
    onError?: (message: string) => void;
}

export function useMike(handlers: MikeHandlers = {}): MikeView {
    const [control, setControl] = useState<MikeControl | null>(null);
    const [events, setEvents] = useState<MikeEvent[]>([]);
    const [trades, setTrades] = useState<MikeTrade[]>([]);
    const [activity, setActivity] = useState<MikeActivity[]>([]);
    const [aggregates, setAggregates] = useState<MikeAggregates | null>(null);
    const [requests, setRequests] = useState<MikeRequest[]>([]);
    const [dayStartMs, setDayStartMs] = useState<number | null>(null);
    const [dayStartSource, setDayStartSource] = useState<'rpc' | 'client'>('client');
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [freshSettled, setFreshSettled] = useState<MikeEvent[]>([]);
    const [freshOutcomes, setFreshOutcomes] = useState<MikeRequest[]>([]);
    const [desiredMode, setDesiredMode] = useState<MikeMode>('paper');
    const [liveConfirmed, setLiveConfirmed] = useState(false);
    const [localReqs, setLocalReqs] = useState<Set<string>>(() => new Set());
    const modeSynced = useRef(false);
    const seenSettled = useRef<Set<string>>(new Set());
    const seenRequestState = useRef<Map<number, string>>(new Map());
    const initialized = useRef(false);
    const onErrorRef = useRef(handlers.onError);
    onErrorRef.current = handlers.onError;
    const reloadSeq = useRef(0);
    const mounted = useRef(true);
    useEffect(() => {
        mounted.current = true;
        return () => { mounted.current = false; };
    }, []);

    const reload = useCallback(async () => {
        const seq = ++reloadSeq.current;
        const firstLoad = !initialized.current;
        const state = await fetchMikeState();
        // senza mike_bot_v2.sql la RPC non espone le richieste: fallback in lettura
        let reqs = state.requests;
        if (!reqs.length) reqs = await fetchMikeRequests(50).catch(() => [] as MikeRequest[]);
        if (seq !== reloadSeq.current || !mounted.current) return;
        setControl(state.control);
        if (state.control && !modeSynced.current) {
            modeSynced.current = true;
            setDesiredMode(state.control.mode);
        }
        setEvents(state.events);
        setTrades(state.trades);
        setActivity(state.activity);
        setAggregates(state.aggregates);
        setRequests(reqs);
        // senza `mike_bot_v2.sql` la RPC non espone `day_start`: la giornata
        // operativa e' comunque la mezzanotte di Roma (certificazione dati reali)
        const dayMs = state.day_start ? Date.parse(state.day_start) : NaN;
        setDayStartMs(Number.isFinite(dayMs) ? dayMs : romeDayStartMs());
        setDayStartSource(Number.isFinite(dayMs) ? 'rpc' : 'client');
        setError(null);
        const fresh = detectSettledEvents(state.events, seenSettled.current, firstLoad);
        if (fresh.length) setFreshSettled(fresh);
        // richieste che hanno CAMBIATO stato in qualcosa di definitivo: la pagina
        // deve dire all'utente com'è finita (M1), una volta sola
        const closed: MikeRequest[] = [];
        for (const r of reqs) {
            const prev = seenRequestState.current.get(r.id);
            seenRequestState.current.set(r.id, r.status);
            if (firstLoad || prev === r.status) continue;
            if (r.status === 'done' || r.status === 'rejected' || r.status === 'error') closed.push(r);
        }
        if (closed.length) setFreshOutcomes(closed);
        if (firstLoad) initialized.current = true;
        setLoading(false);
    }, []);

    useEffect(() => {
        let lastErrAt = 0;
        let timer: number | null = null;
        let disposed = false;
        const run = () => {
            reload().catch((e: unknown) => {
                if (!mounted.current) return;
                setLoading(false);
                const msg = String((e as Error)?.message ?? e);
                setError(msg);
                const now = Date.now();
                if (now - lastErrAt > 60_000) {
                    lastErrAt = now;
                    onErrorRef.current?.(msg);
                }
            });
        };
        // DEBOUNCE: N notifiche ravvicinate = UNA ricarica (mai una per evento)
        const schedule = () => {
            if (disposed || timer !== null) return;
            timer = window.setTimeout(() => { timer = null; run(); }, RELOAD_DEBOUNCE_MS);
        };
        run();
        const unsub = subscribeMike(schedule);
        const poll = window.setInterval(run, POLL_MS);
        return () => {
            disposed = true;
            if (timer !== null) window.clearTimeout(timer);
            unsub();
            window.clearInterval(poll);
        };
    }, [reload]);

    const wrap = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
        setBusy(true);
        try {
            const out = await fn();
            await reload().catch(() => {});
            return out;
        } catch (e) {
            onErrorRef.current?.(String((e as Error)?.message ?? e));
            return null;
        } finally {
            if (mounted.current) setBusy(false);
        }
    }, [reload]);

    const running = control?.status === 'running' || control?.status === 'stopping';

    const start = useCallback(async () => { await wrap(() => activateMike(desiredMode)); }, [wrap, desiredMode]);
    const stop = useCallback(async () => { await wrap(() => stopMike()); }, [wrap]);
    const setMode = useCallback(async (next: MikeMode) => {
        setDesiredMode(next);
        setLiveConfirmed(next === 'live');
        if (running && control?.mode !== next) await wrap(() => activateMike(next));
    }, [wrap, running, control?.mode]);
    const saveParams = useCallback(async (p: MikeParams) => { await wrap(() => updateMikeParams(p)); }, [wrap]);
    const request = useCallback(async (kind: MikeRequestKind, eventId: string) => {
        const key = `${kind}:${eventId}`;
        setLocalReqs((prev) => new Set(prev).add(key));
        try {
            return await wrap(() => requestMike(kind, { event_id: eventId }));
        } finally {
            if (mounted.current) setLocalReqs((prev) => { const n = new Set(prev); n.delete(key); return n; });
        }
    }, [wrap]);
    const isRequestPending = useCallback(
        (eventId: string, kind: MikeRequestKind) => localReqs.has(`${kind}:${eventId}`) || requestInFlight(eventId, kind, requests),
        [localReqs, requests],
    );

    // IDENTITÀ STABILE dei parametri: `control` si riscrive a ogni ricarica, ma
    // se i parametri non sono cambiati l'oggetto resta lo STESSO, così le card
    // memoizzate non si ri-disegnano (e non si muovono) per nulla.
    const paramsKey = JSON.stringify(control?.params ?? null);
    const paramsRef = useRef<{ key: string; value: MikeParams }>({ key: '\u0000', value: { ...MIKE_PARAM_DEFAULTS } });
    if (paramsRef.current.key !== paramsKey) {
        paramsRef.current = {
            key: paramsKey,
            value: control?.params ? mergeMikeParams(control.params) : { ...MIKE_PARAM_DEFAULTS },
        };
    }
    const params = paramsRef.current.value;

    return {
        available: control !== null,
        loading, busy, error,
        control, events, trades, activity, aggregates, requests, dayStartMs, dayStartSource,
        params,
        mode: running ? (control?.mode ?? desiredMode) : desiredMode,
        liveConfirmed,
        reload, start, stop, setMode, saveParams, request, isRequestPending,
        freshSettled, freshOutcomes,
    };
}
