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
import {
    fetchLiveLadder, subscribeLiveLadder, type LiveLadderRow, type LiveLadderSelection,
} from '@/lib/live';
import { fetchTennisLadder, subscribeTennisLadder } from '@/lib/tennis';
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
    sorgentiAlMs.clear();
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

// ------------------------------------------------------ LadderSource "al ms"
// ORDINE DELL'UTENTE (23/09): il ladder passa dal CANALE LOCALE come via
// principale; il realtime DB (live_ladder / tennis_live_ladder) si usa SOLO se il
// canale e' assente (off) o muto (nessun push da > mutoMs). Appena il canale
// riprende a parlare si torna al canale e la sottoscrizione DB viene chiusa.
//
// Formato del push (ladder_worker di Betfair/stream/runner.py e di
// Betfair/stream/tennis_live/tennis_runner.py, busta di local_channel.py):
//   {"t": "ladder", "d": {"event_id": str, "market_id": str,
//     "market_type": str|null, "market_name": str|null, "status": str|null,
//     "ladder": {"updated_ms": int, "selections": [...]}}}
// La riga DB e' la STESSA dict + "updated_at" (_now_iso() al momento della
// scrittura) + "id" (bigserial). Il timestamp del PRODUTTORE e' ladder.updated_ms,
// identico nelle due vie per lo stesso book: e' la chiave della freschezza.

/** Chi ha consegnato l'ultima riga del mercato. */
export type LadderFonte = 'canale' | 'db';

/** 2 x LADDER_PUBLISH_SEC (Betfair/stream/config_stream.py: 2.0 s). */
export const LADDER_MUTO_MS_DEFAULT = 4_000;

// segni di vita del processo runner sul canale (lo stesso processo del ladder)
const TOPIC_VITA = ['ladder', 'now'] as const;

/** Il minimo del LocalChannel che serve alla sorgente (iniettabile nei test). */
export type CanaleLadder = Pick<LocalChannel, 'getStatus' | 'onStatus' | 'subscribe'>;

export interface DipendenzeLadderAlMs {
    canale?: CanaleLadder;          // default: getLocalChannel(sport)
    db?: LadderSource;              // default: live_ladder (calcio) / tennis_live_ladder
    mutoMs?: number;                // default: LADDER_MUTO_MS_DEFAULT
    adesso?: () => number;          // default: Date.now
}

/** LadderSource con in piu' la fonte dell'ultima riga consegnata per mercato. */
export interface LadderSourceAlMs extends LadderSource {
    fonte: (marketId: string) => LadderFonte | null;
}

const strOrNull = (v: unknown): string | null => (typeof v === 'string' ? v : null);

/**
 * Push 'ladder' del canale -> riga con la forma di `live_ladder` (LiveLadderRow).
 * Pura. null se il messaggio non e' un ladder valido (mai una riga inventata).
 * updated_at: sul DB e' l'ora della scrittura; qui l'ora del produttore
 * (ladder.updated_ms), l'unica che il push porta.
 */
export function ladderDaCanale(msg: unknown): LiveLadderRow | null {
    if (!msg || typeof msg !== 'object') return null;
    const m = msg as Record<string, unknown>;
    if (typeof m.market_id !== 'string' || !m.market_id) return null;
    if (typeof m.event_id !== 'string') return null;
    const lad = m.ladder;
    if (!lad || typeof lad !== 'object') return null;
    const { updated_ms: ms, selections } = lad as Record<string, unknown>;
    if (typeof ms !== 'number' || !Number.isFinite(ms)) return null;
    if (!Array.isArray(selections)) return null;
    return {
        event_id: m.event_id,
        market_id: m.market_id,
        market_type: strOrNull(m.market_type),
        market_name: strOrNull(m.market_name),
        status: strOrNull(m.status),
        ladder: { updated_ms: ms, selections: selections as LiveLadderSelection[] },
        updated_at: new Date(ms).toISOString(),
    };
}

const msDi = (r: LiveLadderRow | null | undefined): number | null => {
    const ms = r?.ladder?.updated_ms;
    return typeof ms === 'number' && Number.isFinite(ms) ? ms : null;
};

/** true se `nuova` e' STRETTAMENTE piu' fresca di `vecchia` (updated_ms del produttore). */
export function piuFresca(nuova: LiveLadderRow | null | undefined, vecchia: LiveLadderRow | null | undefined): boolean {
    const n = msDi(nuova);
    if (n == null) return false;
    const v = msDi(vecchia);
    return v == null || n > v;
}

const DB_LADDER: Record<'calcio' | 'tennis', LadderSource> = {
    calcio: { fetch: fetchLiveLadder, subscribe: subscribeLiveLadder },
    tennis: { fetch: fetchTennisLadder, subscribe: subscribeTennisLadder },
};

function creaSorgenteLadderAlMs(sport: 'calcio' | 'tennis', dip: DipendenzeLadderAlMs): LadderSourceAlMs {
    const canale = dip.canale ?? getLocalChannel(sport);
    const db = dip.db ?? DB_LADDER[sport];
    const mutoMs = dip.mutoMs ?? LADDER_MUTO_MS_DEFAULT;
    const adesso = dip.adesso ?? Date.now;

    // riga piu' fresca nota per mercato (da canale o da DB) e chi l'ha portata
    const ultima = new Map<string, LiveLadderRow>();
    const fonti = new Map<string, LadderFonte>();
    let ultimoSegno: number | null = null;   // adesso() dell'ultimo push ricevuto

    const registra = (row: LiveLadderRow, fonte: LadderFonte): boolean => {
        if (!piuFresca(row, ultima.get(row.market_id))) return false;
        ultima.set(row.market_id, row);
        fonti.set(row.market_id, fonte);
        return true;
    };
    const canaleVivo = (): boolean => canale.getStatus() === 'connected'
        && ultimoSegno != null && adesso() - ultimoSegno <= mutoMs;

    for (const t of TOPIC_VITA) {
        canale.subscribe(t, (d) => {
            ultimoSegno = adesso();
            if (t !== 'ladder') return;
            const row = ladderDaCanale(d);
            if (row) registra(row, 'canale');
        });
    }
    // canale caduto: niente segni di vita, nessuna riga del canale tenuta per viva
    canale.onStatus((st) => {
        if (st !== 'off') return;
        ultimoSegno = null;
        for (const [mid, f] of fonti) {
            if (f === 'canale') { fonti.delete(mid); ultima.delete(mid); }
        }
    });

    const passoControllo = Math.max(250, Math.min(1_000, Math.floor(mutoMs / 4)));

    return {
        // UNA sola lettura DB al massimo: se il canale e' vivo e ha gia' il mercato
        // nessuna lettura; altrimenti una, e si restituisce la piu' fresca tra la
        // riga letta e quella arrivata nel frattempo.
        fetch: async (marketId: string): Promise<LiveLadderRow | null> => {
            const nota = ultima.get(marketId);
            if (nota && canaleVivo()) return nota;
            const letta = await db.fetch(marketId);
            if (letta && letta.market_id === marketId) registra(letta, 'db');
            const dopo = ultima.get(marketId);
            return dopo && !piuFresca(letta, dopo) ? dopo : letta;
        },
        subscribe: (marketId: string, cb: (row: LiveLadderRow | null) => void): (() => void) => {
            let attivo = true;
            let consegnatoMs: number | null = null;
            let dbUnsub: (() => void) | null = null;

            const consegna = (row: LiveLadderRow) => {
                const ms = msDi(row);
                if (ms == null || (consegnatoMs != null && ms <= consegnatoMs)) return;
                consegnatoMs = ms;
                cb(row);
            };
            // gettone della sottoscrizione DB corrente: una notifica tardiva di una
            // sottoscrizione gia' chiusa non arriva mai al componente
            let dbTok: object | null = null;
            const chiudiDb = () => {
                dbTok = null;
                if (dbUnsub) { dbUnsub(); dbUnsub = null; }
            };
            const riallinea = () => {
                if (!attivo) return;
                if (canaleVivo()) { chiudiDb(); return; }
                if (dbUnsub) return;
                const mio = {};
                dbTok = mio;
                dbUnsub = db.subscribe(marketId, (row) => {
                    if (!attivo || dbTok !== mio) return;
                    if (row == null) { cb(null); return; }   // come il path DB di sempre
                    if (row.market_id !== marketId) return;
                    registra(row, 'db');
                    consegna(row);
                });
            };

            const offLadder = canale.subscribe('ladder', (d) => {
                if (!attivo) return;
                const row = ladderDaCanale(d);
                if (row && row.market_id === marketId) consegna(row);
                riallinea();   // il canale ha parlato: si torna al canale
            });
            const offNow = canale.subscribe('now', () => { riallinea(); });
            const offStatus = canale.onStatus(() => { riallinea(); });
            const timer = setInterval(riallinea, passoControllo);

            const nota = ultima.get(marketId);
            if (nota && canaleVivo()) consegna(nota);
            riallinea();

            return () => {
                attivo = false;
                clearInterval(timer);
                offLadder();
                offNow();
                offStatus();
                chiudiDb();
            };
        },
        fonte: (marketId: string): LadderFonte | null => fonti.get(marketId) ?? null,
    };
}

const sorgentiAlMs = new Map<'calcio' | 'tennis', LadderSourceAlMs>();

/**
 * Sorgente ladder composita: canale locale al tick come via principale, realtime
 * DB solo a canale assente/muto. Senza `dip` e' un singleton per sport (stabile
 * tra i render: il componente non rifa' mai il fetch per un cambio di via).
 * Con `dip` crea un'istanza nuova (test).
 */
export function sorgenteLadderAlMs(sport: 'calcio' | 'tennis', dip?: DipendenzeLadderAlMs): LadderSourceAlMs {
    if (dip) return creaSorgenteLadderAlMs(sport, dip);
    let s = sorgentiAlMs.get(sport);
    if (!s) { s = creaSorgenteLadderAlMs(sport, {}); sorgentiAlMs.set(sport, s); }
    return s;
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

    // REALTIME (16/07 "non polling"): notifica di cambiamento per l'overlay del ladder.
    // Canale locale connesso → i push 'order'/'position' del runner notificano subito;
    // in parallelo resta attiva l'eventuale subscribe DB del dbApi (Supabase Realtime),
    // così la notifica arriva comunque quando il canale locale è giù. Il reload passa
    // da fetchOrders/fetchPositions (cache locale o DB, con fallback già gestito).
    const subscribeOrders = (
        marketId: string, cb: () => void, onHealth?: (up: boolean) => void,
    ): (() => void) => {
        const unLocal = store.channel.subscribe('order', (d) => {
            const r = d as { market_id?: string } | null;
            if (r?.market_id === marketId) cb();
        });
        // salute: canale locale connesso conta come "up" anche se il canale DB è giù
        const unDb = dbApi.subscribeOrders
            ? dbApi.subscribeOrders(marketId, cb, (up) => onHealth?.(up || connected()))
            : undefined;
        if (!dbApi.subscribeOrders) onHealth?.(connected());
        return () => { unLocal(); unDb?.(); };
    };
    const subscribePositions = (
        marketId: string, cb: () => void, onHealth?: (up: boolean) => void,
    ): (() => void) => {
        const unLocal = store.channel.subscribe('position', (d) => {
            const r = d as { market_id?: string } | null;
            if (r?.market_id === marketId) cb();
        });
        const unDb = dbApi.subscribePositions
            ? dbApi.subscribePositions(marketId, cb, (up) => onHealth?.(up || connected()))
            : undefined;
        if (!dbApi.subscribePositions) onHealth?.(connected());
        return () => { unLocal(); unDb?.(); };
    };

    return {
        send,
        fetchOrders,
        fetchPositions,
        subscribeOrders,
        subscribePositions,
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
