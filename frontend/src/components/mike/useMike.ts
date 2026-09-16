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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    activateMike, stopMike, updateMikeParams, fetchMikeState, fetchMikeRequests, requestMike,
    subscribeMike, mergeMikeParams, detectSettledEvents, requestInFlight, MIKE_PARAM_DEFAULTS,
    romeDayStartMs, fondiEventiLocali, MIKE_TERMINAL_STATES,
    type MikeEventoSpinto, type MikeState,
    type MikeActivity, type MikeAggregates, type MikeControl, type MikeEvent, type MikeMode,
    type MikeParams, type MikeRequest, type MikeRequestKind, type MikeTrade,
} from '@/lib/mike';
import { getLocalChannel, type LocalStatus } from '@/lib/localChannel';
import { creaInterruttori } from '@/lib/interruttori';

/** stati in cui una partita non cambia piu': una scheda spinta in uno di questi
 *  e non piu' restituita dal database e' una card fantasma, e va potata. */
const TERMINALI = new Set<MikeState>(MIKE_TERMINAL_STATES);

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
    /**
     * Stato del canale locale (app desktop): 'connected' = quote, P&L e stato
     * arrivano PUSHATI da 127.0.0.1 a ogni giro del bot, senza passare dal
     * database. 'off' = si legge dal database come sempre — piu' lento di
     * qualche secondo, mai meno vero.
     */
    canaleLocale: LocalStatus;
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
    // schede spinte dal canale locale, per event_id. Sovrappongono quelle del
    // database campo per campo (vedi `fondiEventiLocali`): non le sostituiscono,
    // quindi se il socket cade non sparisce niente.
    const [spinti, setSpinti] = useState<Map<string, MikeEventoSpinto>>(() => new Map());
    const [statsSpinte, setStatsSpinte] = useState<Record<string, unknown> | null>(null);
    const [aggSpinti, setAggSpinti] = useState<Record<string, unknown> | null>(null);
    const [canaleLocale, setCanaleLocale] = useState<LocalStatus>('off');
    // cassetto dei push in arrivo, svuotato una volta per lotto (vedi sotto)
    const inArrivo = useRef<Map<string, MikeEventoSpinto>>(new Map());
    const svuota = useRef<number | null>(null);
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
    /**
     * ⚠️ 16/09 — UN CAMBIO DI MODALITA' NON ACCENDE MAI NIENTE.
     *
     * Qui si chiamava `activateMike(next)`: `mike_activate` porta `status` a
     * 'running', quindi cambiare modalita' era anche un modo di ACCENDERE il
     * bot — e i bot li accende l'utente, con il gesto di accensione. Adesso si
     * passa dal comando CONDIVISO (`lib/interruttori.ts`), lo stesso che usa la
     * Control Room, che scrive con `mike_update_params(p_params, p_mode)`: il
     * `status` non lo tocca proprio.
     */
    const setMode = useCallback(async (next: MikeMode) => {
        setDesiredMode(next);
        setLiveConfirmed(next === 'live');
        if (running && control?.mode !== next) {
            await wrap(async () => {
                await creaInterruttori({
                    params: () => (control?.params ?? null) as Record<string, unknown> | null,
                    servizio: () => ({ inCorsa: running, modalita: control?.mode ?? null }),
                    obiettivoOmega: () => null,
                }, () => {}).cambiaModalita('mike', next);
                return null;
            });
        }
    }, [wrap, running, control]);
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
    // ---- CANALE LOCALE (desktop): le schede arrivano PUSHATE, a ogni giro ----
    // Il database resta la verita' durevole e continua a essere letto come
    // prima: questo e' solo un'accelerazione. Fuori dall'app desktop il socket
    // non si connette mai, `canaleLocale` resta 'off' e non cambia nulla.
    useEffect(() => {
        const ch = getLocalChannel('mike');
        setCanaleLocale(ch.getStatus());
        const offStato = ch.onStatus((st) => {
            setCanaleLocale(st);
            // caduto il socket si BUTTANO le schede spinte: meglio i numeri del
            // database, che sono veri anche se vecchi, che una foto congelata
            // di cui non sappiamo piu' l'eta'.
            if (st !== 'connected') {
                setSpinti(new Map());
                setStatsSpinte(null);
                setAggSpinti(null);
                inArrivo.current = new Map();
            }
        });
        // I push arrivano UNO PER PARTITA a ogni giro del bot (1 s). Scrivere lo
        // stato a ogni messaggio vorrebbe dire, con 30 partite, 30 re-render
        // della pagina al secondo: ogni `onmessage` e' un task separato del
        // browser e React non li unisce da solo. Si accumulano in un cassetto e
        // si svuota una volta sola — 250 ms sono sotto la soglia percettiva e
        // portano i risvegli da 30/s a 4/s.
        const offEvento = ch.subscribe('mike_event', (d) => {
            const row = d as MikeEventoSpinto | null;
            const eid = row && typeof row === 'object' ? String(row.event_id ?? '') : '';
            if (!eid) return;
            inArrivo.current.set(eid, row as MikeEventoSpinto);
            if (svuota.current != null) return;
            svuota.current = window.setTimeout(() => {
                svuota.current = null;
                const lotto = inArrivo.current;
                inArrivo.current = new Map();
                setSpinti((prev) => {
                    const next = new Map(prev);
                    for (const [k, v] of lotto) next.set(k, v);
                    return next;
                });
            }, 250);
        });
        // i NUMERI DI TESTATA (P&L, liability, KPI): senza questo il servizio li
        // pubblicava e nessuno li ascoltava, e il commento nel codice prometteva
        // un aggiornamento che non avveniva.
        const offStatoBot = ch.subscribe('mike_stato', (d) => {
            const msg = d as { stats?: unknown; aggregates?: unknown } | null;
            if (!msg || typeof msg !== 'object') return;
            if (msg.stats && typeof msg.stats === 'object') {
                setStatsSpinte(msg.stats as Record<string, unknown>);
            }
            if (msg.aggregates && typeof msg.aggregates === 'object') {
                setAggSpinti(msg.aggregates as Record<string, unknown>);
            }
        });
        return () => {
            offStato(); offEvento(); offStatoBot();
            if (svuota.current != null) window.clearTimeout(svuota.current);
        };
    }, []);

    const params = paramsRef.current.value;
    // POTATURA (M3): una scheda spinta che il database non restituisce piu'
    // resterebbe appesa in pagina per sempre come card fantasma — il servizio
    // tiene 48 ore di storia, la RPC ne mostra 24. Si tengono solo le partite
    // che il database conosce ancora, piu' quelle appena nate che il database
    // non ha ancora scritto (`state` fra quelli operativi, non terminali).
    const spintiVivi = useMemo(() => {
        if (!spinti.size) return spinti;
        const noti = new Set(events.map((e) => String(e.event_id)));
        const out = new Map<string, MikeEventoSpinto>();
        for (const [eid, p] of spinti) {
            const st = String((p as { state?: unknown }).state ?? '');
            if (noti.has(eid) || !TERMINALI.has(st as MikeState)) out.set(eid, p);
        }
        return out;
    }, [events, spinti]);
    const eventiVisibili = useMemo(() => fondiEventiLocali(events, spintiVivi), [events, spintiVivi]);
    // i numeri di testata: stessa regola di sovrapposizione, campo per campo.
    // Solo `stats` e `aggregates`; modalita', stato e parametri restano del
    // database. Se il socket cade tornano null e si vedono di nuovo i numeri
    // del database: piu' vecchi di qualche secondo, mai assenti.
    const controlVisibile = useMemo(
        () => (control && statsSpinte
            ? ({ ...control, stats: { ...(control.stats ?? {}), ...statsSpinte } } as MikeControl)
            : control),
        [control, statsSpinte]);
    const aggregatiVisibili = useMemo(
        () => (aggregates && aggSpinti
            ? ({ ...aggregates, ...aggSpinti } as MikeAggregates)
            : aggregates),
        [aggregates, aggSpinti]);

    return {
        available: control !== null,
        loading, busy, error,
        control: controlVisibile, events: eventiVisibili, trades, activity,
        aggregates: aggregatiVisibili, requests,
        dayStartMs, dayStartSource, canaleLocale,
        params,
        mode: running ? (control?.mode ?? desiredMode) : desiredMode,
        liveConfirmed,
        reload, start, stop, setMode, saveParams, request, isRequestPending,
        freshSettled, freshOutcomes,
    };
}
