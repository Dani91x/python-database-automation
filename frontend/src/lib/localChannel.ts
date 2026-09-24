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
//
// STADIO C (18/09, raccordo) — `svegliaBot()` in coda al file importa `Bot`/
// `isBotTennis` da `lib/controlRoom` SOLO per instradare sulla porta giusta
// (routing, non logica di dominio): resta l'unica funzione di questo file che
// conosce il nome dei bot, per lo stesso motivo per cui i sei bot hanno gia'
// ciascuno il proprio `LocalSport`.
// ============================================================================
import { isBotTennis, type Bot } from '@/lib/controlRoom';

// Ogni canale ha il SUO processo e la SUA porta. Non è una duplicazione: i
// canali dei runner (calcio, tennis) ACCETTANO COMANDI ORDINE, quelli dei bot
// (mike, omega, safe) sono di SOLA LETTURA — mostrano e basta. Tenere separati
// chi comanda e chi mostra vuol dire che aggiungere uno schermo non aggiunge
// mai una via per mandare soldi.
// STADIO B (18/09, raccordo) — `scanner` (47336, topic `scan_calcio`/
// `scan_tennis`/`scanner_stato`) e `tennis_bot` (47337, topic
// `tennis_bot_stato`/`tennis_bot_posizioni`) sono lo STESSO meccanismo di
// connessione/riconnessione/ripiego, aggiunti in coda: oggi il backend non li
// scrive (porta chiusa), quindi restano in stato `off` senza errori, come i
// canali bot già esistenti prima del loro avvio.
export type LocalSport = 'calcio' | 'tennis' | 'mike' | 'omega' | 'safe' | 'scanner' | 'tennis_bot';

/** I canali di sola lettura: nessun comando viaggia su questi. */
export const CANALI_SOLA_LETTURA: readonly LocalSport[] = ['mike', 'omega', 'safe', 'scanner', 'tennis_bot'] as const;
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
const PORTS: Record<LocalSport, number> = {
    calcio: 47331, tennis: 47332,     // runner (comandi + push)
    mike: 47333, omega: 47334, safe: 47335,   // bot (solo push)
    scanner: 47336,     // scanner unico (safe_strategy_scan): scan_calcio/scan_tennis/scanner_stato
    tennis_bot: 47337,  // 4 bot tennis: tennis_bot_stato/tennis_bot_posizioni
};

const RECONNECT_MIN_MS = 1_000;   // backoff iniziale
const RECONNECT_STEP_MS = 1_000;  // incremento lineare
const RECONNECT_MAX_MS = 5_000;   // tetto backoff
export const LOCAL_REQUEST_TIMEOUT_MS = 10_000;

// C1 (24/09) - TOKEN DI SESSIONE. I canali del runner (47331/47332) accettano
// un comando 'order' SOLO da una connessione presentata col token dell'app
// (`?t=<token>`), che `desktop/preload.js` espone in sola lettura come
// `window.alphascoreCanale.token`. Fuori dall'app (browser, test) il token non
// c'e': il canale si usa per i push, gli ordini vanno sulla coda DB.
const TOKEN_RE = /^[0-9a-f]{64}$/;

/** Il token di sessione dei canali, o null fuori dall'app desktop. */
export function tokenCanale(): string | null {
    const g = globalThis as { alphascoreCanale?: { token?: unknown } };
    const t = g.alphascoreCanale?.token;
    return typeof t === 'string' && TOKEN_RE.test(t) ? t : null;
}

/** I canali che accettano comandi (tutti gli altri sono di sola lettura). */
function accettaComandi(sport: LocalSport): boolean {
    return !CANALI_SOLA_LETTURA.includes(sport);
}

/** URL del canale: col token SOLO sui canali che comandano e SOLO se c'e'. */
export function urlCanale(sport: LocalSport, token: string | null = tokenCanale()): string {
    const base = `ws://127.0.0.1:${PORTS[sport]}`;
    return token && accettaComandi(sport) ? `${base}/?t=${token}` : base;
}

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

    /**
     * C1: questo client puo' mandare comandi 'order'? Solo su un canale che
     * comanda e solo con il token dell'app. Senza, gli ordini vanno sulla coda DB.
     */
    puoComandare(): boolean {
        return accettaComandi(this.sport) && tokenCanale() !== null;
    }

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
            ws = new WS(urlCanale(this.sport));
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

// ------------------------------------------------------------------ sveglia
// STADIO C (18/09, raccordo, F6 lato pagina) — «LA SVEGLIA AI BOT DOPO OGNI
// CLIC». Il comando VERO resta la scrittura sul database: la sveglia serve
// SOLO a far leggere subito quella riga al bot invece che al prossimo giro di
// poll. Un solo messaggio, nessun dato d'ordine (`{"id","m":"sveglia",
// "p":{"motivo"}}`, protocollo di `Betfair/stream/local_channel.py`), sulla
// porta del bot giusto: Mike 47333, Omega 47334, Safe 47335, i 4 bot tennis
// insieme su 47337 (canale unico, non uno a bot). BEST-EFFORT PURO: se il
// socket non e' connesso, o la richiesta cade, NON si rilancia e NON si
// propaga un errore — il chiamante ha GIA' scritto sul database, quello e' il
// comando vero e non deve mai fallire per colpa della sveglia.
export type MotivoSveglia = 'approvazione' | 'comando';

function canaleDiBot(bot: Bot): LocalSport {
    return isBotTennis(bot) ? 'tennis_bot' : bot;
}

/**
 * Sveglia il bot giusto DOPO che la scrittura sul database e' gia' riuscita
 * (il chiamante lo garantisce: qui non si scrive mai niente). Non ritorna
 * nulla da attendere: e' fuoco-e-dimentica per costruzione, mai un secondo
 * tentativo, mai un log d'errore per una sveglia mancata.
 */
export function svegliaBot(bot: Bot, motivo: MotivoSveglia): void {
    getLocalChannel(canaleDiBot(bot)).request('sveglia', { motivo }).catch(() => {
        /* best-effort: il comando vero e' gia' scritto sul database */
    });
}

/** SOLO PER I TEST: chiude e dimentica i singleton (mai chiamare in produzione). */
export function __resetLocalChannels(): void {
    for (const c of instances.values()) c.destroy();
    instances.clear();
}
