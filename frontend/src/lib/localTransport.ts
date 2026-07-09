// ============================================================================
// localTransport.ts — adatta il CANALE LOCALE (localChannel.ts) alle interfacce
// già usate dalla UI (LadderSource / LadderOrderApi di LadderView) con fallback
// TOTALE al path DB esistente quando il canale è giù.
//
// Regole MONEY-CRITICAL:
//  - MAI mescolare mode: i push order/position sono bucketizzati per row.mode
//    ('paper'|'live'); righe senza mode valida vengono SCARTATE.
//  - su DISCONNESSIONE ogni cache (ladder/ordini/posizioni/snapshot) è INVALIDATA:
//    mai mostrare un book congelato come vivo — si ri-delega al dbSource e la UI
//    mostra già l'età dei dati.
//  - send via WS: errore di TRASPORTO/busta → throw; esito APPLICATIVO ok:false
//    → ritornato come result con error (identico al path DB).
//  - risk rules / settings / place_submin / segnali RESTANO su path DB by design
//    (armRule/supportsFok = passthrough del dbApi).
// ============================================================================
import { useEffect, useState } from 'react';
import type { LadderSource, LadderOrderApi, LadderGreenupArgs } from '@/components/live/LadderView';
import type { LiveLadderRow } from '@/lib/live';
import {
    buildGreenupParams,
    type LiveOrderCommand, type LiveOrderMode, type LiveOrderResult,
    type LiveOrderRow, type LivePositionRow,
} from '@/lib/liveOrders';
import {
    getLocalChannel,
    type LocalChannel, type LocalSport, type LocalStatus,
} from '@/lib/localChannel';

// ---------------------------------------------------------------- store per-sport
// Cache alimentate dai push del canale: ultimo ladder per market, specchi ordini/
// posizioni per (mode, market). Vive quanto il canale; svuotata a ogni caduta.
interface SportStore {
    channel: LocalChannel;
    ladder: Map<string, LiveLadderRow>;                       // market_id → ultimo push
    orders: Map<string, Map<string, LiveOrderRow>>;           // `${mode}|${market}` → bet → riga
    positions: Map<string, Map<string, LivePositionRow>>;     // `${mode}|${market}` → sel → riga
    snapshotDone: Set<string>;                                // `${mode}|${market}` (epoch connessione)
    mode: string | null;                                      // mode attiva dal hello/now (informativa)
}

const stores = new Map<LocalSport, SportStore>();

const modeKey = (mode: string, marketId: string) => `${mode}|${marketId}`;

// chiave stabile di una riga ordine nello specchio (bet_id quando esiste).
const orderKey = (r: LiveOrderRow): string =>
    r.bet_id ?? r.client_order_ref ?? (r.id != null ? `id:${r.id}` : '');

const positionKey = (r: LivePositionRow): string => `${r.selection_id}:${r.handicap ?? 0}`;

function upsertOrder(store: SportStore, d: unknown): void {
    const r = d as LiveOrderRow | null;
    // MONEY-CRITICAL: filtro mode — righe senza mode valida o senza mercato: scartate.
    if (!r || !r.market_id || (r.mode !== 'paper' && r.mode !== 'live')) return;
    const key = orderKey(r);
    if (!key) return;
    const bucket = store.orders.get(modeKey(r.mode, r.market_id))
        ?? store.orders.set(modeKey(r.mode, r.market_id), new Map()).get(modeKey(r.mode, r.market_id))!;
    bucket.set(key, r);
}

function upsertPosition(store: SportStore, d: unknown): void {
    const r = d as LivePositionRow | null;
    if (!r || !r.market_id || (r.mode !== 'paper' && r.mode !== 'live')) return;
    const bucket = store.positions.get(modeKey(r.mode, r.market_id))
        ?? store.positions.set(modeKey(r.mode, r.market_id), new Map()).get(modeKey(r.mode, r.market_id))!;
    bucket.set(positionKey(r), r);
}

function invalidate(store: SportStore): void {
    store.ladder.clear();
    store.orders.clear();
    store.positions.clear();
    store.snapshotDone.clear();
}

function getStore(sport: LocalSport): SportStore {
    let s = stores.get(sport);
    if (s) return s;
    const channel = getLocalChannel(sport);
    const store: SportStore = {
        channel,
        ladder: new Map(),
        orders: new Map(),
        positions: new Map(),
        snapshotDone: new Set(),
        mode: null,
    };
    channel.subscribe('ladder', (d) => {
        const row = d as LiveLadderRow | null;
        if (row?.market_id) store.ladder.set(row.market_id, row);
    });
    channel.subscribe('order', (d) => upsertOrder(store, d));
    channel.subscribe('position', (d) => upsertPosition(store, d));
    channel.subscribe('hello', (d) => {
        const h = d as { mode?: string } | null;
        if (h?.mode) store.mode = String(h.mode).toLowerCase();
    });
    channel.subscribe('now', (d) => {
        const m = (d as { state?: { order_mode?: string } } | null)?.state?.order_mode;
        if (m) store.mode = String(m).toLowerCase();
    });
    // caduta canale → cache INVALIDATE (mai un book congelato spacciato per vivo).
    channel.onStatus((st) => { if (st === 'off') invalidate(store); });
    stores.set(sport, store);
    return store;
}

/** SOLO PER I TEST: dimentica gli store (da usare insieme a __resetLocalChannels). */
export function __resetLocalTransport(): void {
    stores.clear();
}

// ------------------------------------------------------------- LadderSource locale
/**
 * Sorgente ladder con canale locale: fetch = ultimo push in cache (o dbSource.fetch
 * come fallback), subscribe = push 'ladder' filtrati per market_id. Se il canale è
 * OFF delega INTERAMENTE al dbSource (path DB invariato), ri-attaccandosi da solo
 * ai push quando il canale torna su.
 */
export function localLadderSource(sport: LocalSport, dbSource: LadderSource): LadderSource {
    const store = getStore(sport);
    return {
        fetch: async (marketId: string): Promise<LiveLadderRow | null> => {
            if (store.channel.getStatus() === 'connected') {
                const cached = store.ladder.get(marketId);
                if (cached) return cached;
            }
            return dbSource.fetch(marketId);
        },
        subscribe: (marketId: string, cb: (row: LiveLadderRow | null) => void): (() => void) => {
            let active = true;
            let dbUnsub: (() => void) | null = null;
            let localUnsub: (() => void) | null = null;
            const attach = (status: LocalStatus) => {
                if (!active) return;
                if (status === 'connected') {
                    // canale su: SOLO push locali (il DB non serve più a questa cadenza)
                    if (dbUnsub) { dbUnsub(); dbUnsub = null; }
                    if (!localUnsub) {
                        localUnsub = store.channel.subscribe('ladder', (d) => {
                            const row = d as LiveLadderRow | null;
                            if (row?.market_id === marketId) cb(row);
                        });
                        const cached = store.ladder.get(marketId);
                        if (cached) cb(cached); // primo frame subito (se già in cache)
                    }
                } else {
                    // canale giù: delega INTERA al dbSource (la cache è già invalidata)
                    if (localUnsub) { localUnsub(); localUnsub = null; }
                    if (!dbUnsub) dbUnsub = dbSource.subscribe(marketId, cb);
                }
            };
            attach(store.channel.getStatus());
            const offStatus = store.channel.onStatus(attach);
            return () => {
                active = false;
                offStatus();
                if (dbUnsub) dbUnsub();
                if (localUnsub) localUnsub();
            };
        },
    };
}

// ------------------------------------------------------------ LadderOrderApi locale
/**
 * API ordini con canale locale: send via richiesta WS 'order' (mappa {ok,d,e}),
 * fetchOrders/fetchPositions dalla cache push con snapshot iniziale ('snapshot' WS
 * per il calcio; dbApi per il tennis, il cui snapshot WS è vuoto by-design).
 * greenup usa la STESSA validazione del path DB (buildGreenupParams) e instrada via
 * send locale. armRule/supportsFok = passthrough al dbApi (risk rules su DB by design).
 */
export function localOrderApi(sport: LocalSport, dbApi: LadderOrderApi): LadderOrderApi {
    const store = getStore(sport);
    const connected = () => store.channel.getStatus() === 'connected';

    const send = async (cmd: LiveOrderCommand): Promise<LiveOrderResult> => {
        if (!connected()) return dbApi.send(cmd);
        // trasporto (timeout/caduta) → la request REIETTA e il throw risale (NON reinviare).
        // dedup server-side (fix review HIGH): client_ref univoco per comando —
        // un reinvio accidentale riceve l'esito già calcolato, MAI doppia esecuzione.
        const res = await store.channel.request('order', {
            ...(cmd as unknown as Record<string, unknown>),
            client_ref: crypto.randomUUID(),
        });
        // esito APPLICATIVO presente → RITORNATO così com'è (anche ok:false), come il path DB.
        if (res.d != null) return res.d as LiveOrderResult;
        // busta senza esito ({ok:false,e}: comando NON accettato dal server) → errore trasporto.
        throw new Error(res.e ?? 'canale locale: risposta ordine senza esito');
    };

    // snapshot iniziale per (mode, market): riempie la cache prima del primo read.
    // false = snapshot non riuscito → il chiamante ricade sul dbApi (mai lista vuota bugiarda).
    const ensureSnapshot = async (marketId: string, mode: LiveOrderMode): Promise<boolean> => {
        const key = modeKey(mode, marketId);
        if (store.snapshotDone.has(key)) return true;
        try {
            if (sport === 'calcio') {
                const res = await store.channel.request('snapshot', { market_id: marketId });
                const d = (res.d ?? {}) as { orders?: LiveOrderRow[]; positions?: LivePositionRow[] };
                for (const r of d.orders ?? []) upsertOrder(store, r);
                for (const r of d.positions ?? []) upsertPosition(store, r);
            } else {
                // tennis: snapshot WS vuoto by-design → seed iniziale dal DB (stesse RPC di prima)
                const [o, p] = await Promise.all([
                    dbApi.fetchOrders(marketId, mode),
                    dbApi.fetchPositions(marketId, mode),
                ]);
                for (const r of o) upsertOrder(store, r);
                for (const r of p) upsertPosition(store, r);
            }
            store.snapshotDone.add(key);
            return true;
        } catch {
            return false;
        }
    };

    const fetchOrders = async (marketId: string, mode: LiveOrderMode): Promise<LiveOrderRow[]> => {
        if (!connected()) return dbApi.fetchOrders(marketId, mode);
        if (!(await ensureSnapshot(marketId, mode))) return dbApi.fetchOrders(marketId, mode);
        const rows = [...(store.orders.get(modeKey(mode, marketId))?.values() ?? [])];
        // più recenti prima (stesso ordinamento delle RPC specchio)
        return rows.sort((a, b) => (b.id ?? 0) - (a.id ?? 0));
    };

    const fetchPositions = async (marketId: string, mode: LiveOrderMode): Promise<LivePositionRow[]> => {
        if (!connected()) return dbApi.fetchPositions(marketId, mode);
        if (!(await ensureSnapshot(marketId, mode))) return dbApi.fetchPositions(marketId, mode);
        return [...(store.positions.get(modeKey(mode, marketId))?.values() ?? [])];
    };

    // greenup: STESSA firma e STESSA validazione del path DB (buildGreenupParams è
    // l'unica fonte di verità — nessuna copia), instradato via send locale quando
    // connesso. Esposto SOLO se il dbApi lo espone (mai promettere ciò che non c'è).
    const greenup = dbApi.greenup
        ? async (args: LadderGreenupArgs): Promise<LiveOrderResult> => {
            if (!connected()) return dbApi.greenup!(args);
            const params = buildGreenupParams(args.fraction, args.targetPrice, args.cancelUnmatched);
            return send({
                action: 'greenup',
                mode: args.mode,
                market_id: args.marketId,
                selection_id: args.selectionId,
                handicap: args.handicap ?? 0,
                ...(Object.keys(params).length ? { params } : {}),
            });
        }
        : undefined;

    return {
        send,
        fetchOrders,
        fetchPositions,
        ...(greenup ? { greenup } : {}),
        // risk rules RESTANO su path DB by design (il canale locale non le gestisce).
        ...(dbApi.armRule ? { armRule: dbApi.armRule } : {}),
        supportsFok: dbApi.supportsFok,
    };
}

// ------------------------------------------------------------------ push 'now'
/**
 * Sottoscrive i push 'now' del canale locale (riga live_now calcio / tennis_live_now).
 * Consegna il payload grezzo: il chiamante lo tipizza e fa il merge "più recente vince".
 */
export function subscribeLocalNow(sport: LocalSport, cb: (d: unknown) => void): () => void {
    return getStore(sport).channel.subscribe('now', cb);
}

// ------------------------------------------------------------------ hook React
/** Stato reattivo del canale locale ('connected'|'off') per il chip in top bar. */
export function useLocalStatus(sport: LocalSport): LocalStatus {
    const [status, setStatus] = useState<LocalStatus>(() => getLocalChannel(sport).getStatus());
    useEffect(() => {
        const ch = getLocalChannel(sport);
        setStatus(ch.getStatus());
        return ch.onStatus(setStatus);
    }, [sport]);
    return status;
}
