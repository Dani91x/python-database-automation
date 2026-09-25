// ============================================================================
// runnerCanale.ts - 25/09 (voce 6 dell'audit tempo reale): lo stato dei RUNNER
// (calcio 47331, tennis 47332) e il modo ordini "OFF/PAPER/LIVE" dal canale
// locale, con il database come ripiego dichiarato.
//
// Prima: la riga "Runner" e la riga "Ordini reali" della Control Room stavano
// al poll dei 30 s (`betfair_live_heartbeat` + `live_follow`, RPC
// `get_live_settings`), e l'eta' del battito era CONGELATA all'istante della
// lettura. Il runner tennis non ha nessuna riga di battito sul database.
//
// I messaggi VERI dei runner (busta `{"t": topic, "d": ...}` di
// `Betfair/stream/local_channel.py`):
//   hello  <- local_channel.py:353, a OGNI connessione:
//             d = {"sport": "calcio"|"tennis", "mode": <tetto del .env>}
//             (`set_hello(mode=...)`: runner.py:1798, tennis_runner.py:1790)
//   account<- reconcile_worker.py:161 (saldo, ~20 s anche col runner in
//             attesa di eventi, runner.py:1901 `run_account_sync_if_due`) e
//             :1039, saldo_evento.py:126: e' il BATTITO del runner calcio
//   ladder <- runner.py:718 / tennis_runner.py:1116 (mercati SEGUITI, 200 ms)
//   now    <- db.py:309 (calcio) / tennis_db.py:291 (tennis): la riga di
//             `live_now`/`tennis_live_now`. Per il calcio `state` porta
//             `order_mode` (EFFETTIVO), `order_mode_tetto`, `order_mode_scelto`
//             e `updated_ms` (runner.py:292-302)
//   board/order/position: altri push del runner (notizie di vita anch'esse)
//   battito <- 25/09 punto 6: `canale_bot.battito_runner` {ts, mode,
//             streaming}, pubblicato da `runner._pubblica_battito` DOVE si
//             scrive `betfair_live_heartbeat` (heartbeat_worker e attesa) e
//             dal runner tennis al suo giro di attesa. `mode` = lo STESSO della
//             riga del database (`heartbeat_mode()`: 'LIVE+PAPER'); `streaming`
//             = partite seguite dalla memoria del runner (null = non contabile)
//   modo_ordini <- 25/09 punto 6: `modo_ordini.stato_corrente()` + `ts`,
//             SOLO AL CAMBIO (`live_order_worker._pubblica_modo_ordini_se_cambiato`);
//             anche nell'hello (`hello.modo_ordini`) per chi si collega dopo
//
// Il battito e' un OGGETTO INTERO: se e' piu' recente della riga del
// database, `mode` e `streaming` vengono dal battito (mai meta' e meta'),
// salvo `streaming` null ("non contabile": resta il numero del database).
//
// LE REGOLE
//  - canale CONNESSO = processo vivo: il socket e' servito dal processo del
//    runner, che lo chiude morendo. L'eta' dichiarata e' quella dell'ultimo
//    messaggio ricevuto (anche l'hello della connessione);
//  - "in streaming" dal canale solo se arriva `ladder`/`now` da al piu'
//    `FLUSSO_VIVO_S`; il silenzio del canale NON toglie lo streaming letto dal
//    database (il dubbio non concede e non toglie: resta il ripiego);
//  - canale spento: la riga del database, con l'eta' ricalcolata ADESSO.
//
// Modulo PURO: nessun import di rete, nessun React.
// ============================================================================
import { runnerStateFrom, type RunnerState } from '@/lib/safeBot';
import {
    modoOrdiniEffettivo, normalizzaModoOrdini, type ModoOrdini, type StatoOrdiniReali,
} from '@/lib/interruttori';

/** entro quanti secondi un `ladder`/`now` dice "sta streammando" (`now` ogni 5 s) */
export const FLUSSO_VIVO_S = 15;
/** entro quanti secondi il modo ordini del `now` vale ancora (il runner lo rilegge ~1 s) */
export const MODO_CANALE_VALIDO_S = 15;

export type FonteRunner = 'canale' | 'database';

/** Il battito del runner sul canale (topic `battito`, 25/09 punto 6). */
export interface BattitoRunner {
    /** ms epoch del PRODUTTORE */
    ts: number;
    /** modalita' servite ('LIVE+PAPER', 'PAPER', 'OFF'); null = non dichiarata */
    mode: string | null;
    /** partite seguite dalla memoria del runner; null = non contabile */
    streaming: number | null;
}

/**
 * Legge un push `battito`. `null` = messaggio storto (senza `ts` numerico):
 * un battito senza istante non dice quando il runner era vivo.
 */
export function leggiBattito(d: unknown): BattitoRunner | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    if (typeof o.ts !== 'number' || !Number.isFinite(o.ts)) return null;
    const mode = typeof o.mode === 'string' && o.mode.trim() ? o.mode.trim().toUpperCase() : null;
    const streaming = typeof o.streaming === 'number' && Number.isFinite(o.streaming) && o.streaming >= 0
        ? Math.floor(o.streaming) : null;
    return { ts: o.ts, mode, streaming };
}

/** Le notizie di un runner raccolte dal canale (orologio della pagina). */
export interface NotizieRunner {
    connesso: boolean;
    /** ultimo `hello` ricevuto (d del push) */
    hello: Record<string, unknown> | null;
    /** ultimo messaggio di qualunque topic, o l'istante della connessione */
    ultimoMsgMs: number | null;
    /** ultimo `ladder`/`now` */
    ultimoFlussoMs: number | null;
    /** ultimo `battito` valido (25/09 punto 6); assente = nessuno ricevuto */
    battito?: BattitoRunner | null;
}

export interface RunnerVista {
    /** null = non noto (nessuna lettura del database e canale spento) */
    runner: RunnerState | null;
    fonte: FonteRunner;
    /** eta' della notizia su cui si basa la riga; null = ignota */
    etaS: number | null;
}

export const NOTIZIE_VUOTE: NotizieRunner = {
    connesso: false, hello: null, ultimoMsgMs: null, ultimoFlussoMs: null, battito: null,
};

function etaDa(ms: number | null, nowMs: number): number | null {
    return ms == null ? null : Math.max(0, (nowMs - ms) / 1000);
}

/**
 * Lo stato del runner da mostrare. `db` = la lettura del database (null per
 * il tennis, che non ha battito su tabella, o se mai letta).
 */
export function runnerDalCanale(
    db: RunnerState | null, n: NotizieRunner, nowMs: number,
): RunnerVista {
    if (!n.connesso || n.ultimoMsgMs == null) {
        if (db == null) return { runner: null, fonte: 'database', etaS: null };
        // eta' e "vivo" ricalcolati ADESSO dalla riga letta (prima restavano
        // quelli dell'istante della lettura fino al giro dopo)
        const r = { ...db, ...runnerStateFrom({ ts: db.ts, mode: db.mode }, nowMs, db.streaming ?? null) };
        return { runner: r, fonte: 'database', etaS: r.ageS == null ? null : Math.round(r.ageS) };
    }
    const ageS = etaDa(n.ultimoMsgMs, nowMs);
    const flusso = n.ultimoFlussoMs != null && (nowMs - n.ultimoFlussoMs) / 1000 <= FLUSSO_VIVO_S;
    const modeHello = typeof n.hello?.mode === 'string' && n.hello.mode.trim()
        ? n.hello.mode.trim().toUpperCase() : null;
    const streamingDb = db?.streaming ?? null;
    // 25/09 (punto 6): il battito del runner, se piu' recente della riga del
    // database, e' la notizia intera (mode + streaming): mai meta' e meta'.
    const b = n.battito ?? null;
    const dbMs = db?.ts ? Date.parse(db.ts) : NaN;
    const battitoVince = b != null && (!Number.isFinite(dbMs) || b.ts > dbMs);
    // il database dichiara le modalita' SERVITE ('LIVE+PAPER'): se c'e',
    // vince sull'hello; il battito porta lo stesso valore, piu' fresco
    const mode = battitoVince ? (b.mode ?? modeHello) : (db?.mode ?? modeHello);
    const streamingBase = battitoVince && b.streaming != null ? b.streaming : streamingDb;
    return {
        runner: {
            ts: new Date(n.ultimoMsgMs).toISOString(),
            mode,
            ageS,
            up: true,
            streaming: flusso ? Math.max(streamingBase ?? 0, 1) : streamingBase,
        },
        fonte: 'canale',
        etaS: ageS == null ? null : Math.round(ageS),
    };
}

// ------------------------------------------------------------ modo ordini

/** Il modo ordini come lo dichiara il runner calcio nel `now`. */
export interface ModoOrdiniCanale {
    effettivo: ModoOrdini | null;
    tetto: ModoOrdini | null;
    scelto: ModoOrdini | null;
    /** `state.updated_ms` (now) o `ts` (modo_ordini) del produttore */
    ms: number;
    /**
     * true = viene dal topic `modo_ordini` (o dall'hello), che il runner
     * pubblica AD OGNI CAMBIO: vale finche' il canale resta collegato, senza
     * la scadenza dei 15 s del `now`.
     */
    alCambio?: boolean;
}

/**
 * Legge il push `modo_ordini` (o `hello.modo_ordini`) del runner calcio:
 * `modo_ordini.stato_corrente()` + `ts` (chiavi `effettivo`,
 * `tetto_ambiente`, `scelto_ui`, `motivo`, `scelto_ui_at`, `scelto_ui_da`,
 * `eta_lettura_s`, `ts`). `null` = messaggio storto o assente.
 */
export function leggiModoOrdiniCanale(d: unknown): ModoOrdiniCanale | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    if (typeof o.ts !== 'number' || !Number.isFinite(o.ts)) return null;
    const effettivo = normalizzaModoOrdini(o.effettivo);
    if (effettivo == null) return null;
    return {
        effettivo,
        tetto: normalizzaModoOrdini(o.tetto_ambiente),
        scelto: normalizzaModoOrdini(o.scelto_ui),
        ms: o.ts,
        alCambio: true,
    };
}

/**
 * Legge il modo ordini da un push `now` del runner calcio. `null` = il
 * messaggio non lo porta (runner di prima del 24/09, riga storta).
 */
export function leggiModoDalNow(d: unknown): ModoOrdiniCanale | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const st = (d as { state?: unknown }).state;
    if (!st || typeof st !== 'object' || Array.isArray(st)) return null;
    const s = st as Record<string, unknown>;
    const ms = s.updated_ms;
    if (typeof ms !== 'number' || !Number.isFinite(ms)) return null;
    const effettivo = normalizzaModoOrdini(s.order_mode);
    if (effettivo == null) return null;
    return {
        effettivo,
        tetto: normalizzaModoOrdini(s.order_mode_tetto),
        scelto: normalizzaModoOrdini(s.order_mode_scelto),
        ms,
    };
}

export interface StatoOrdiniVista extends StatoOrdiniReali {
    fonte: FonteRunner;
    /** eta' della notizia mostrata; null = ignota */
    etaS: number | null;
    /**
     * true = il runner dichiara una SCELTA diversa da quella letta dal
     * database: la riga e' vecchia, il chiamante la rilegge subito.
     */
    daRileggere: boolean;
}

/**
 * La riga "Ordini reali" da mostrare: la lettura del database (`st`) con
 * sopra cio' che il runner dichiara sul canale, "mai unione":
 *  - riga mai letta: nessuna sovrapposizione (il canale non inventa una lettura);
 *  - tetto: quello dell'hello del runner collegato (e' il SUO .env);
 *  - effettivo: quello del `now` se fresco (`MODO_CANALE_VALIDO_S`) e piu'
 *    recente della lettura; e' il modo che il worker APPLICA;
 *  - scelta: resta del database (porta chi/quando); se il runner ne dichiara
 *    un'altra, `daRileggere`.
 */
export function sovrapponiModoOrdini(
    st: StatoOrdiniReali, lettoMs: number | null,
    canale: {
        connesso: boolean; hello: Record<string, unknown> | null; modo: ModoOrdiniCanale | null;
        /** 25/09 (punto 6): l'ultimo `modo_ordini` (topic o hello), al cambio */
        modoAlCambio?: ModoOrdiniCanale | null;
    },
    nowMs: number,
): StatoOrdiniVista {
    const etaDb = lettoMs == null ? null : Math.max(0, Math.round((nowMs - lettoMs) / 1000));
    const base: StatoOrdiniVista = { ...st, fonte: 'database', etaS: etaDb, daRileggere: false };
    if (!st.letto || st.migrazioneMancante || !canale.connesso) return base;
    const tettoHello = normalizzaModoOrdini(canale.hello?.mode);
    const mNow = canale.modo;
    const nowValido = mNow != null && (nowMs - mNow.ms) / 1000 <= MODO_CANALE_VALIDO_S
        && (lettoMs == null || mNow.ms > lettoMs);
    // il `modo_ordini` al cambio vale finche' il canale e' collegato (il runner
    // ne manda uno nuovo a OGNI cambio, anche lettura scaduta -> OFF): e' il
    // modo che il worker APPLICA, anche se la lettura della pagina e' piu' recente
    const mCambio = canale.modoAlCambio ?? null;
    // UN oggetto intero, il piu' recente fra i due validi: mai unione
    let m: ModoOrdiniCanale | null = nowValido ? mNow : null;
    if (mCambio != null && (m == null || mCambio.ms >= m.ms)) m = mCambio;
    const tetto = tettoHello ?? (m != null ? m.tetto : null) ?? st.tetto;
    if (m == null && tetto === st.tetto) return base;
    const effettivo = m != null && m.effettivo != null ? m.effettivo : modoOrdiniEffettivo(tetto, st.scelto);
    return {
        ...st,
        tetto,
        effettivo,
        limitatoDalTetto: st.scelto != null && tetto != null
            && modoOrdiniEffettivo(tetto, st.scelto) !== st.scelto,
        fonte: 'canale',
        etaS: m != null ? Math.max(0, Math.round((nowMs - m.ms) / 1000)) : etaDb,
        // si rilegge solo se la notizia del runner e' PIU' RECENTE della lettura
        // (una lettura piu' nuova e diversa = scelta appena fatta: il runner la
        // dira' al prossimo giro, niente rilettura a vuoto)
        daRileggere: m != null && m.scelto != null && m.scelto !== st.scelto
            && (lettoMs == null || m.ms > lettoMs),
    };
}
