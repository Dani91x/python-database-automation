// ============================================================================
// useSafeBot — stato del BOT Safe Strategy per la pagina /safe-strategy.
//
// Stessa architettura di Omega: realtime (UN canale su control+trades+requests)
// + poll di sicurezza, ricarica completa a ogni notifica. Le opportunità di
// modello hanno il loro canale dedicato con aggiornamenti coalizzati.
//
// Il bot può NON esistere ancora (migrazione non applicata / servizio spento):
// in quel caso `available` resta false e la pagina continua a funzionare come
// radar in sola lettura, senza mai rompersi.
// ============================================================================
import { useCallback, useEffect, useRef, useState } from 'react';
import {
    activateSafe, stopSafe, updateSafeParams, fetchSafeState, fetchSafeTrades,
    fetchSafeRequests, requestSafe, subscribeSafeBot, fetchOpportunities,
    subscribeOpportunities, detectSettlements, mergeBotParams, cashoutInFlight, SAFE_BOT_DEFAULTS,
    type SafeAggregates, type SafeBotParams, type SafeControl, type SafeMode,
    type SafeOpportunityRow, type SafeRequest, type SafeTrade,
} from '@/lib/safeBot';

const POLL_MS = 15_000;
const OPPS_FLUSH_MS = 400;

export interface SafeBotView {
    /** true = la riga di controllo esiste (RPC raggiungibili) */
    available: boolean;
    loading: boolean;
    busy: boolean;
    error: string | null;
    control: SafeControl | null;
    trades: SafeTrade[];
    aggregates: SafeAggregates | null;
    requests: SafeRequest[];
    opportunities: SafeOpportunityRow[];
    /** parametri EFFETTIVI: server se il bot esiste, default altrimenti */
    params: SafeBotParams;
    mode: SafeMode;
    /** true = la modalita' LIVE e' stata CONFERMATA dall'utente in questa
     *  sessione. Un control gia' in live (da un'altra sessione/tab) mostra il
     *  banner ma NON autorizza piazzamenti finche' non si conferma qui. */
    liveConfirmed: boolean;
    reload: () => Promise<void>;
    start: () => Promise<void>;
    stop: () => Promise<void>;
    /** cambia modalita: a bot fermo e' una scelta locale applicata all'avvio,
     *  a bot in corsa ri-arma il servizio nella nuova modalita (safe_activate). */
    setMode: (mode: SafeMode) => Promise<void>;
    saveParams: (p: Partial<SafeBotParams>) => Promise<void>;
    place: (payload: Record<string, unknown>) => Promise<number | null>;
    cashout: (tradeId: number, args: { amount?: number; fraction?: number }) => Promise<number | null>;
    cancel: (tradeId: number) => Promise<number | null>;
    /** true = cash out gia' in volo per quel trade (richiesta locale non ancora
     *  visibile, richiesta pending/processing sul DB, gamba di chiusura scritta
     *  o meta.hedging): mai una seconda copertura sulla stessa posizione */
    isCashOutPending: (tradeId: number) => boolean;
    /** trade regolati dall'ultimo giro (per i toast di settlement) */
    freshSettlements: SafeTrade[];
}

export interface SafeBotHandlers {
    onError?: (message: string) => void;
    onInfo?: (message: string, description?: string) => void;
}

export function useSafeBot(handlers: SafeBotHandlers = {}): SafeBotView {
    const [control, setControl] = useState<SafeControl | null>(null);
    const [trades, setTrades] = useState<SafeTrade[]>([]);
    const [aggregates, setAggregates] = useState<SafeAggregates | null>(null);
    const [requests, setRequests] = useState<SafeRequest[]>([]);
    const [opportunities, setOpportunities] = useState<SafeOpportunityRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [freshSettlements, setFreshSettlements] = useState<SafeTrade[]>([]);
    // modalita scelta dall'utente: a bot fermo vive solo qui, all'avvio va in safe_activate
    const [desiredMode, setDesiredMode] = useState<SafeMode>('paper');
    const modeSynced = useRef(false);
    // LIVE confermato in QUESTA sessione (mai ereditato dal control)
    const [liveConfirmed, setLiveConfirmed] = useState(false);
    // cash out in volo per trade_id (richiesta partita ma non ancora nel DB)
    const [localCashouts, setLocalCashouts] = useState<Set<number>>(() => new Set());

    const seenSettled = useRef<Set<number>>(new Set());
    const initialized = useRef(false);
    const onErrorRef = useRef(handlers.onError);
    onErrorRef.current = handlers.onError;
    // guardie del reload: sequenza (risultati fuori ordine ignorati) e smontaggio
    const reloadSeq = useRef(0);
    const mounted = useRef(true);
    useEffect(() => {
        mounted.current = true;
        return () => { mounted.current = false; };
    }, []);

    const reload = useCallback(async () => {
        const seq = ++reloadSeq.current;
        const firstLoad = !initialized.current;
        const [state, reqs] = await Promise.all([
            fetchSafeState(),
            fetchSafeRequests(30).catch(() => [] as SafeRequest[]),
        ]);
        // get_safe_state porta gia i trade; se la RPC non li includesse si
        // ricade sulla lista dedicata (contratto piu' permissivo, mai vuota).
        let rows = state.trades;
        if (rows.length === 0) rows = await fetchSafeTrades(300).catch(() => [] as SafeTrade[]);
        // un reload piu' recente ha gia' vinto, o il componente non c'e' piu'
        if (seq !== reloadSeq.current || !mounted.current) return;
        setControl(state.control);
        if (state.control && !modeSynced.current) {
            // la modalita' del control si RIFLETTE (banner), non si eredita
            // come autorizzazione: liveConfirmed resta false finche' l'utente
            // non conferma in questa sessione.
            modeSynced.current = true;
            setDesiredMode(state.control.mode);
        }
        setAggregates(state.aggregates);
        setTrades(rows);
        setRequests(reqs);
        setError(null);
        const fresh = detectSettlements(rows, seenSettled.current, firstLoad);
        if (fresh.length) setFreshSettlements(fresh);
        if (firstLoad) initialized.current = true;
        setLoading(false);
    }, []);

    useEffect(() => {
        let lastErrAt = 0;
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
        run();
        const unsub = subscribeSafeBot(run);
        const poll = window.setInterval(run, POLL_MS);
        return () => { unsub(); window.clearInterval(poll); };
    }, [reload]);

    // ------------------------------------------------- opportunità di modello
    useEffect(() => {
        let alive = true;
        const pending = new Map<string, SafeOpportunityRow | null>();
        let timer: number | undefined;
        const flush = () => {
            timer = undefined;
            if (!alive) return;
            setOpportunities((prev) => {
                const byId = new Map(prev.map((r) => [r.event_id, r]));
                for (const [id, row] of pending) {
                    if (row === null) byId.delete(id); else byId.set(id, row);
                }
                pending.clear();
                return [...byId.values()];
            });
        };
        const schedule = () => { if (timer === undefined) timer = window.setTimeout(flush, OPPS_FLUSH_MS); };
        fetchOpportunities()
            .then((rows) => { if (alive) setOpportunities(rows); })
            .catch(() => { /* tabella/migrazione assenti: sezione vuota */ });
        const unsub = subscribeOpportunities((ev) => {
            if (ev.type === 'upsert') pending.set(ev.row.event_id, ev.row);
            else pending.set(ev.eventId, null);
            schedule();
        });
        return () => { alive = false; unsub(); if (timer !== undefined) window.clearTimeout(timer); };
    }, []);

    // -------------------------------------------------------------- comandi
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

    const start = useCallback(async () => {
        await wrap(() => activateSafe(desiredMode));
    }, [wrap, desiredMode]);
    const stop = useCallback(async () => { await wrap(() => stopSafe()); }, [wrap]);
    const setMode = useCallback(async (next: SafeMode) => {
        setDesiredMode(next);
        setLiveConfirmed(next === 'live');
        // a bot fermo non c'e' nulla da riscrivere sul DB: la modalita viaggia
        // con safe_activate al prossimo avvio (nessuna RPC "solo modalita").
        // A bot in corsa GIA' nella modalita' richiesta (conferma di un LIVE
        // ereditato) non si ri-arma nulla: e' solo la conferma locale.
        if (running && control?.mode !== next) await wrap(() => activateSafe(next));
    }, [wrap, running, control?.mode]);
    const saveParams = useCallback(async (p: Partial<SafeBotParams>) => {
        await wrap(() => updateSafeParams(p));
    }, [wrap]);
    const place = useCallback(
        (payload: Record<string, unknown>) => wrap(() => requestSafe('place', payload)),
        [wrap],
    );
    const cashout = useCallback(
        async (tradeId: number, args: { amount?: number; fraction?: number }) => {
            setLocalCashouts((prev) => new Set(prev).add(tradeId));
            try {
                return await wrap(() => requestSafe('cashout', { trade_id: tradeId, ...args }));
            } finally {
                if (mounted.current) {
                    setLocalCashouts((prev) => { const n = new Set(prev); n.delete(tradeId); return n; });
                }
            }
        },
        [wrap],
    );
    const cancel = useCallback(
        (tradeId: number) => wrap(() => requestSafe('cancel', { trade_id: tradeId })),
        [wrap],
    );
    const isCashOutPending = useCallback(
        (tradeId: number) => localCashouts.has(tradeId) || cashoutInFlight(tradeId, requests, trades),
        [localCashouts, requests, trades],
    );

    const params = control?.params ? mergeBotParams(control.params) : SAFE_BOT_DEFAULTS;

    return {
        available: control !== null,
        loading, busy, error,
        control, trades, aggregates, requests, opportunities,
        params,
        mode: running ? (control?.mode ?? desiredMode) : desiredMode,
        liveConfirmed,
        reload, start, stop, setMode, saveParams, place, cashout, cancel,
        isCashOutPending,
        freshSettlements,
    };
}
