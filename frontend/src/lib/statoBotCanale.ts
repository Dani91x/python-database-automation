// ============================================================================
// statoBotCanale.ts - 25/09 (voce 4 dell'audit tempo reale): IL CONTENUTO del
// push `*_stato` di Omega, Safe e Mike come SOVRAPPOSIZIONE della riga di
// control letta dal database.
//
// Prima: la Control Room usava `safe_stato`/`mike_stato` SOLO come orologio
// ("quando ha parlato"), e il contenuto (stato, modalita', parametri, motivo
// del blocco, rischio) arrivava al poll dei 30 s. Solo Omega usava i suoi
// `stats`, e li sostituiva INTERI (le chiavi timbrate sul database, es.
// `fermato_all_avvio_at`, sparivano dalla vista).
//
// I messaggi VERI (copiati dai produttori, busta `{"t": topic, "d": ...}` di
// `Betfair/stream/local_channel.py`):
//   omega_stato <- Betfair/omega/omega_service.py (`_pubblica_stato`)
//                  d = {"stats": <dict>, "last_cycle": <ISO>,
//                       "control": {status, mode, params, updated_at}}
//   safe_stato  <- Betfair/safe_strategy/bot_service.py (`_pubblica_stato`)
//                  d = {"stats": <dict>, "last_cycle": <ISO>,
//                       "control": {status, mode, params, updated_at}}
//                  (`control` dal 25/09, punto 6: colonne della riga letta a
//                  inizio giro; un bot di prima non lo manda)
//   mike_stato  <- Betfair/mike/service.py:4904
//                  d = {"control": <riga mike_control letta a inizio giro>,
//                       "aggregates": <dict>, "stats": <dict>,
//                       "published_ts": <float, secondi epoch>}
// `stats` e' lo STESSO oggetto che il bot scrive subito dopo in
// `*_control.stats` (Omega/Safe: "lo schermo prima del disco"), e contiene
// `last_cycle` (ISO del giro). Mike porta la riga di control intera; dal
// 25/09 (punto 6) Omega e Safe ne portano status/mode/params/updated_at:
// modalita' e interruttori arrivano al ritmo del bot anche per loro.
//
// LE REGOLE ("overlay sul poll, mai unione", come `righeCanale.ts`):
//  1. riga di control MAI letta dal database -> nessuna vista dal canale
//     (il canale non crea lo stato di un bot che il database non ha dato);
//  2. `stats`: il push vince solo se il suo `last_cycle` e' STRETTAMENTE piu'
//     recente di quello della riga del database; la sovrapposizione e' PER
//     CHIAVE (`{...db.stats, ...push.stats}`): le chiavi che il bot aggiunge
//     solo scrivendo sul database (timbro d'avvio, `fermato_all_avvio_at`)
//     restano quelle del database;
//  3. colonne della riga (status, mode, params...): il push vince
//     solo se la SUA versione della riga (`updated_at`) e' STRETTAMENTE piu'
//     recente di quella letta dal database. A parita' vince il database: un
//     parametro appena salvato dalla pagina non torna indietro per un giro
//     del bot partito prima del salvataggio;
//  4. canale giu' -> il chiamante butta il push e torna al database.
//
// Modulo PURO: nessun import di rete, nessun React.
// ============================================================================

export type BotConStato = 'omega' | 'safe' | 'mike';

/** Un push `*_stato` gia' validato. */
export interface PushStato {
    /** `stats` del giro (oggetto), o null se il messaggio non lo porta */
    stats: Record<string, unknown> | null;
    /** la riga di control letta a inizio giro (senza `stats`): Mike intera,
     *  Omega/Safe status/mode/params/updated_at (25/09) */
    control: Record<string, unknown> | null;
    /** quando la pagina l'ha ricevuto (orologio della pagina): serve all'eta' */
    ricevutoMs: number;
}

function oggetto(v: unknown): Record<string, unknown> | null {
    return v != null && typeof v === 'object' && !Array.isArray(v)
        ? v as Record<string, unknown> : null;
}

/** ISO -> ms epoch, null se non leggibile. */
function istanteMs(v: unknown): number | null {
    if (typeof v !== 'string' || !v.trim()) return null;
    const t = Date.parse(v);
    return Number.isFinite(t) ? t : null;
}

/**
 * Valida un push `*_stato`. `null` = non e' uno stato (si ignora, non si
 * indovina): payload non oggetto, oppure ne' `stats` ne' `control` oggetti.
 * Il `control` si accetta da Mike (riga intera) e, dal 25/09 (punto 6), da
 * Omega e Safe (status/mode/params/updated_at). Senza `updated_at` leggibile
 * `sovrapponiControl` non lo applica mai.
 */
export function leggiPushStato(bot: BotConStato, d: unknown, ricevutoMs: number): PushStato | null {
    const o = oggetto(d);
    if (!o) return null;
    const stats = oggetto(o.stats);
    let control: Record<string, unknown> | null = null;
    // 25/09 (punto 6): anche Omega e Safe pubblicano `control` (le colonne
    // status/mode/params/updated_at della riga letta a inizio giro); vale per
    // tutti la stessa regola 3 (versione della riga strettamente piu' nuova).
    void bot;
    const c = oggetto(o.control);
    if (c) {
        // lo `stats` dentro la riga (Mike) e' quello del giro PRIMA: vale `o.stats`
        const { stats: _vecchie, ...resto } = c;
        void _vecchie;
        control = resto;
    }
    if (!stats && !control) return null;
    return { stats, control, ricevutoMs };
}

/** Le chiavi della riga di control che interessano la vista. */
interface ControlLike {
    stats?: unknown;
    updated_at?: string | null;
}

export interface VistaControl<C> {
    /** la riga da mostrare: STESSO oggetto del database se il canale non vince */
    control: C | null;
    /** true se almeno una parte viene dal canale */
    daCanale: boolean;
}

/**
 * La riga di control da mostrare: quella del database, con sopra le parti del
 * push piu' fresche (regole in testa al file). Senza push o con il push non
 * piu' fresco: LO STESSO oggetto del database (nessun render in piu').
 */
export function sovrapponiControl<C extends ControlLike>(
    db: C | null | undefined, push: PushStato | null | undefined,
): VistaControl<C> {
    if (db == null) return { control: null, daCanale: false };
    if (push == null) return { control: db, daCanale: false };
    let out: C = db;
    let daCanale = false;

    // colonne della riga: versione della riga strettamente piu' nuova
    if (push.control) {
        const tPush = istanteMs(push.control.updated_at);
        const tDb = istanteMs(db.updated_at);
        if (tPush != null && (tDb == null || tPush > tDb)) {
            out = { ...out, ...push.control } as C;
            daCanale = true;
        }
    }

    // stats: giro strettamente piu' recente, sovrapposizione per chiave
    if (push.stats) {
        const dbStats = oggetto(db.stats);
        const tPush = istanteMs(push.stats.last_cycle);
        const tDb = istanteMs(dbStats?.last_cycle);
        if (tPush != null && (tDb == null || tPush > tDb)) {
            out = { ...out, stats: { ...(dbStats ?? {}), ...push.stats } } as C;
            daCanale = true;
        }
    }
    return { control: out, daCanale };
}

// ------------------------------------------------ 25/09 (voce 14): scanner

/** La riga `safe_strategy_status` come la legge la pagina (id, payload, updated_at). */
interface RigaStatoScanner {
    id: string;
    payload: unknown;
    updated_at: string | null;
}

/**
 * Il push `scanner_stato` (47336) sulla riga di stato gia' letta.
 *
 * Messaggio VERO: `Betfair/safe_strategy/service.py:1519` pubblica `payload`,
 * lo STESSO dict che un istante dopo va in `safe_strategy_status.payload`
 * (`db.py:182`, con `updated_at` = ora della scrittura). Il push non porta un
 * istante suo: l'eta' e' quella della RICEZIONE (canale locale, ms).
 *  - riga mai letta: `prev` invariato (mai unione);
 *  - push non oggetto: `prev` invariato;
 *  - ricezione non piu' recente della riga: `prev` invariato.
 * Ritorna `prev` (stesso riferimento) quando scarta.
 */
export function statoScannerDalCanale<R extends RigaStatoScanner>(
    prev: R | null, d: unknown, ricevutoMs: number,
): R | null {
    if (prev == null) return prev;
    if (d == null || typeof d !== 'object' || Array.isArray(d)) return prev;
    const tDb = istanteMs(prev.updated_at);
    if (tDb != null && !(ricevutoMs > tDb)) return prev;
    return { ...prev, payload: d, updated_at: new Date(ricevutoMs).toISOString() };
}
