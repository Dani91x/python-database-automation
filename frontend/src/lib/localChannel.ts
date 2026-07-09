// ============================================================================
// localChannel.ts — client WebSocket del CANALE LOCALE UI(desktop) ↔ runner.
//
// Controparte browser di Betfair/stream/local_channel.py: quando l'app desktop
// gira sullo stesso PC del runner, ladder/now/ordini/posizioni arrivano PUSHATI
// da 127.0.0.1 (latenza ~0) e i comandi ordine viaggiano via WS invece che via
// coda DB. PURO trasporto: NESSUN import supabase, nessuna logica di dominio
// (il fallback DB vive in localTransport.ts).
//
// Protocollo (JSON, un messaggio per riga — speculare al server):
//   push  server→client : {"t": topic, "d": payload}   topic: hello|ladder|now|order|position|board
//   req   client→server : {"id": n, "m": "order"|"snapshot", "p": {...}}
//   res   server→client : {"id": n, "ok": bool, "d": {...}, "e"?: "msg"}
//
// MONEY-CRITICAL: su timeout/caduta con richieste pendenti l'esito è IGNOTO →
// il reject dice esplicitamente "NON reinviare" (l'ordine potrebbe essere stato
// eseguito). Il canale NON ritenta mai una richiesta da solo.
// ============================================================================

export type LocalSport = 'calcio' | 'tennis';
export type LocalStatus = 'connected' | 'off';

/** Ultimo hello ricevuto dal server ({sport, mode, ...}). */
export interface LocalHello {
    sport?: string;
    mode?: string;
    [k: string]: unknown;
}

/** Busta di risposta a una richiesta (id già consumato). d/e dipendono dal metodo. */
export interface LocalResponse {
    ok: boolean;
    d?: unknown;
    e?: string;
}

// porte fisse del runner (vedi local_channel.py: calcio 47331 · tennis 47332).
const PORTS: Record<LocalSport, number> = { calcio: 47331, tennis: 47332 };

const RECONNECT_MIN_MS = 1_000;   // backoff iniziale
const RECONNECT_STEP_MS = 1_000;  // incremento lineare
const RECONNECT_MAX_MS = 5_000;   // tetto backoff
export const LOCAL_REQUEST_TIMEOUT_MS = 10_000;

type TopicCallback = (d: unknown) => void;

interface PendingRequest {
    resolve: (res: LocalResponse) => void;
    reject: (err: Error) => void;
    timer: ReturnType<typeof setTimeout>;
}

export class LocalChannel {
    readonly sport: LocalSport;

    private ws: WebSocket | null = null;
    private status: LocalStatus = 'off';
    private hello: LocalHello | null = null;
    private nextId = 1;
    private backoffMs = RECONNECT_MIN_MS;
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private destroyed = false;
    private readonly pending = new Map<number, PendingRequest>();
    private readonly topics = new Map<string, Set<TopicCallback>>();
    private readonly statusCbs = new Set<(s: LocalStatus) => void>();

    constructor(sport: LocalSport) {
        this.sport = sport;
        this.connect();
    }

    // ------------------------------------------------------------- stato
    getStatus(): LocalStatus { return this.status; }

    /** Ultimo {"t":"hello"} ricevuto (null se mai connesso / dopo una caduta). */
    getHello(): LocalHello | null { return this.hello; }

    /** Notifica i cambi di stato ('connected'|'off'). Ritorna l'unsubscribe. */
    onStatus(cb: (s: LocalStatus) => void): () => void {
        this.statusCbs.add(cb);
        return () => { this.statusCbs.delete(cb); };
    }

    // --------------------------------------------------------------- push
    /** Sottoscrive un topic di push ('hello'|'ladder'|'now'|'order'|'position'|'board'). */
    subscribe(topic: string, cb: TopicCallback): () => void {
        let set = this.topics.get(topic);
        if (!set) { set = new Set(); this.topics.set(topic, set); }
        set.add(cb);
        return () => { set.delete(cb); };
    }

    // ----------------------------------------------------------- richieste
    /**
     * Invia una richiesta {id,m,p} e risolve con la busta {ok,d,e}. Reietta SOLO
     * per problemi di TRASPORTO (non connesso / timeout / caduta): l'esito
     * applicativo (anche negativo) arriva sempre come resolve.
     */
    request(method: string, params: Record<string, unknown>): Promise<LocalResponse> {
        return new Promise<LocalResponse>((resolve, reject) => {
            const ws = this.ws;
            if (this.status !== 'connected' || !ws) {
                reject(new Error('canale locale non connesso'));
                return;
            }
            const id = this.nextId++;
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(
                    `canale locale: nessuna risposta in ${LOCAL_REQUEST_TIMEOUT_MS / 1000}s — `
                    + 'se era un ordine NON reinviare: controlla la lista ordini.',
                ));
            }, LOCAL_REQUEST_TIMEOUT_MS);
            this.pending.set(id, { resolve, reject, timer });
            try {
                ws.send(JSON.stringify({ id, m: method, p: params }));
            } catch (err) {
                clearTimeout(timer);
                this.pending.delete(id);
                reject(err instanceof Error ? err : new Error('invio sul canale locale fallito'));
            }
        });
    }

    // ----------------------------------------------------------- lifecycle
    /** Chiude definitivamente (test/teardown): niente reconnect successivi. */
    destroy(): void {
        this.destroyed = true;
        if (this.reconnectTimer != null) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
        const ws = this.ws;
        this.ws = null;
        try { ws?.close(); } catch { /* già chiuso */ }
        this.failPending();
        this.hello = null;
        this.setStatus('off');
    }

    private connect(): void {
        if (this.destroyed) return;
        // ambienti senza WebSocket (SSR/test non stubbati): resta 'off' senza retry-loop.
        const WS = typeof WebSocket !== 'undefined' ? WebSocket : undefined;
        if (!WS) return;

        let ws: WebSocket;
        try {
            ws = new WS(`ws://127.0.0.1:${PORTS[this.sport]}`);
        } catch {
            this.scheduleReconnect();
            return;
        }
        this.ws = ws;
        ws.onopen = () => {
            if (this.ws !== ws) return;
            this.backoffMs = RECONNECT_MIN_MS; // connessione riuscita → backoff azzerato
            this.setStatus('connected');
        };
        ws.onmessage = (ev: MessageEvent) => {
            if (this.ws !== ws) return;
            this.handleMessage(typeof ev.data === 'string' ? ev.data : '');
        };
        const onDrop = () => { this.dropConnection(ws); };
        ws.onclose = onDrop;
        ws.onerror = onDrop;
    }

    /** Caduta della connessione: pendenti reiettate (esito IGNOTO), hello invalidato, reconnect. */
    private dropConnection(ws: WebSocket): void {
        if (this.ws !== ws) return; // onerror+onclose: gestisci una volta sola
        this.ws = null;
        try { ws.close(); } catch { /* best-effort */ }
        this.failPending();
        this.hello = null;
        this.setStatus('off');
        this.scheduleReconnect();
    }

    private failPending(): void {
        for (const [, p] of this.pending) {
            clearTimeout(p.timer);
            p.reject(new Error(
                'canale locale caduto: esito NON confermato — se era un ordine NON reinviare, controlla la lista ordini.',
            ));
        }
        this.pending.clear();
    }

    private scheduleReconnect(): void {
        if (this.destroyed || this.reconnectTimer != null) return;
        const delay = this.backoffMs;
        this.backoffMs = Math.min(this.backoffMs + RECONNECT_STEP_MS, RECONNECT_MAX_MS);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, delay);
    }

    private setStatus(s: LocalStatus): void {
        if (this.status === s) return;
        this.status = s;
        for (const cb of this.statusCbs) {
            try { cb(s); } catch { /* callback esterna: mai rompere il canale */ }
        }
    }

    private handleMessage(raw: string): void {
        let msg: Record<string, unknown>;
        try {
            msg = JSON.parse(raw) as Record<string, unknown>;
        } catch {
            return; // messaggio malformato: ignora
        }
        // risposta a una richiesta ({id,ok,d,e})
        if (typeof msg.id === 'number') {
            const p = this.pending.get(msg.id);
            if (!p) return; // risposta tardiva dopo timeout: ignora
            this.pending.delete(msg.id);
            clearTimeout(p.timer);
            p.resolve({ ok: msg.ok === true, d: msg.d, e: typeof msg.e === 'string' ? msg.e : undefined });
            return;
        }
        // push ({t,d})
        const topic = typeof msg.t === 'string' ? msg.t : null;
        if (!topic) return;
        if (topic === 'hello') {
            this.hello = (msg.d && typeof msg.d === 'object' ? msg.d : {}) as LocalHello;
        }
        const set = this.topics.get(topic);
        if (!set) return;
        for (const cb of set) {
            try { cb(msg.d); } catch { /* callback esterna: mai rompere il canale */ }
        }
    }
}

// ------------------------------------------------------------------ singleton
const instances = new Map<LocalSport, LocalChannel>();

/** Client singleton per sport (crea e connette al primo accesso). */
export function getLocalChannel(sport: LocalSport): LocalChannel {
    let c = instances.get(sport);
    if (!c) {
        c = new LocalChannel(sport);
        instances.set(sport, c);
    }
    return c;
}

/** SOLO PER I TEST: chiude e dimentica i singleton (mai chiamare in produzione). */
export function __resetLocalChannels(): void {
    for (const c of instances.values()) c.destroy();
    instances.clear();
}
