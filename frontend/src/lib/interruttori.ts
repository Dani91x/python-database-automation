// ============================================================================
// interruttori.ts — UN INTERRUTTORE PER OGNI BOT E PER OGNI STRATEGIA.
//
// «Voglio poter attivare OGNI SINGOLO BOT direttamente dalla Control Room» e
// «devo poter attivare e spegnere tutto dalla UI, sia paper che live, in
// maniera facile e diretta, sia dalle singole schede che dalla Control Room»
// (utente, 16/09).
//
// PERCHE' STA IN `lib/` E NON DENTRO LA CONTROL ROOM: gli stessi gesti devono
// essere disponibili nelle pagine dei singoli bot. Due implementazioni dello
// stesso interruttore sono due verita', e divergono sempre: e' esattamente
// cosi' che «avvia il tennis» era arrivato ad accendere anche il calcio.
//
// LA VERITA' E' UNA SOLA, E STA NEL SERVIZIO
//
//   acceso?      Omega / Mike : `control.status = 'running'`
//                Safe <strategia> : servizio in corsa **e** la strategia sta
//                in `params.variants` (CHI PUO' APRIRE)
//   con che soldi? `control.mode` (TETTO) **e** `params.strategy_modes[x]`
//                (CON CHE SOLDI). Live solo se scritto in tutti e due.
//
// Non esiste nessun flag nuovo: si legge da dove il servizio scrive gia'.
//
// LE TRE REGOLE DI SCRITTURA
//
//  1. **Le due mappe si scrivono SEMPRE intere.** Una strategia spenta non
//     compare in `variants`; una accesa ha `strategy_modes[x]` scritto a
//     'paper' o 'live'. Mai ereditare: ai soldi veri si arriva scrivendolo.
//  2. **Si riparte SEMPRE dai parametri correnti.** Le RPC fanno
//     `coalesce(p_params, params)`: un oggetto parziale SOSTITUISCE l'intera
//     colonna. Se non li abbiamo letti non si scrive (`ParametriNonLetti`).
//  3. **Un gesto tocca solo la sua strategia.** Accendere «base» in prova non
//     deve spostare di un millimetro il tennis che sta operando con soldi
//     veri. L'unica eccezione e' dichiarata e si chiama per nome: il gesto
//     «solo tennis» della scheda tennis (`soloTennis.ts`), che e' un caso
//     PARTICOLARE di questo modello, non un percorso a parte.
// ============================================================================
import { activateOmega, stopOmega, updateOmegaParams, type OmegaParams } from '@/lib/omega';
import { activateSafe, stopSafe, updateSafeParams, type SafeBotParams } from '@/lib/safeBot';
import { activateMike, stopMike, updateMikeParams, type MikeParams } from '@/lib/mike';
import {
    activateTennisBotService, stopTennisBotService, updateTennisBotService,
    type TennisBotKey,
} from '@/lib/tennis';
import { isBotTennis, BOT_TENNIS, BOT_LABEL, type Bot, type BotTennis } from '@/lib/controlRoom';
import { svegliaBot } from '@/lib/localChannel';

export type { Bot };

export type Modalita = 'paper' | 'live';
export type SportBot = 'calcio' | 'tennis';

/** Le quattro strategie del manuale di Safe, nell'ordine del manuale. */
export const STRATEGIE_MANUALE = ['base', 'esatto', 'punta', 'tennis'] as const;
export type StrategiaSafe = (typeof STRATEGIE_MANUALE)[number];

/**
 * TUTTE le strategie che il servizio Safe conosce (`bot_service._STRATEGIES`).
 * `model` e `manual` non hanno un interruttore — non sono strategie del
 * manuale, sono le opportunita' di modello e gli ordini a mano — ma vanno
 * NOMINATE quando si scrive la mappa: una chiave assente vuol dire «eredita il
 * mode del servizio», e in live quello significa soldi veri.
 */
export const STRATEGIE_SAFE_TUTTE = ['base', 'esatto', 'punta', 'tennis', 'model', 'manual'] as const;

export type InterruttoreId =
    | 'omega' | 'mike'
    | 'safe-base' | 'safe-esatto' | 'safe-punta' | 'safe-tennis'
    | BotTennis;

export interface Interruttore {
    id: InterruttoreId;
    bot: Bot;
    /** null = l'interruttore comanda il SERVIZIO intero (Omega, Mike) */
    strategia: StrategiaSafe | null;
    sport: SportBot;
    /** come si chiama davanti al trader */
    etichetta: string;
    /** la chiave di importo di QUESTO interruttore nei parametri del servizio */
    chiaveImporto: string;
    /** chiave usata prima di B.5, per LATO: resta il ripiego dichiarato */
    chiaveImportoPerLato: string | null;
    etichettaImporto: string;
    notaImporto?: string;
}

/**
 * I SEI INTERRUTTORI. Calcio: Omega, Mike, Safe base, Safe esatto, Safe punta.
 * Tennis: Safe tennis. Nella scheda calcio il tennis non compare, e viceversa.
 */
export const INTERRUTTORI: readonly Interruttore[] = [
    {
        id: 'omega', bot: 'omega', strategia: null, sport: 'calcio', etichetta: 'Omega',
        chiaveImporto: 'min_stake', chiaveImportoPerLato: null, etichettaImporto: 'stake minimo',
        // e' un MINIMO, non l'importo di lavoro: Omega dimensiona dall'obiettivo
        notaImporto: 'e’ un minimo, non l’importo di lavoro: Omega dimensiona dall’obiettivo',
    },
    {
        id: 'mike', bot: 'mike', strategia: null, sport: 'calcio', etichetta: 'Mike',
        chiaveImporto: 'stake', chiaveImportoPerLato: null, etichettaImporto: 'stake Under 3.5',
    },
    {
        id: 'safe-base', bot: 'safe', strategia: 'base', sport: 'calcio', etichetta: 'Safe base',
        chiaveImporto: 'stake.per_strategia.base', chiaveImportoPerLato: 'stake.laySize',
        etichettaImporto: 'stake base',
    },
    {
        id: 'safe-esatto', bot: 'safe', strategia: 'esatto', sport: 'calcio', etichetta: 'Safe esatto',
        chiaveImporto: 'stake.per_strategia.esatto', chiaveImportoPerLato: 'stake.laySize',
        etichettaImporto: 'stake esatto',
    },
    {
        id: 'safe-punta', bot: 'safe', strategia: 'punta', sport: 'calcio', etichetta: 'Safe punta',
        chiaveImporto: 'stake.per_strategia.punta', chiaveImportoPerLato: 'stake.backSize',
        etichettaImporto: 'stake punta',
    },
    {
        id: 'safe-tennis', bot: 'safe', strategia: 'tennis', sport: 'tennis', etichetta: 'Safe tennis',
        chiaveImporto: 'stake.per_strategia.tennis', chiaveImportoPerLato: 'stake.backSize',
        etichettaImporto: 'stake tennis',
    },
    // ── I QUATTRO BOT DEL TENNIS (17/09) ────────────────────────────────────
    // «Tutti i bot tennis finiti e in UI, INDIPENDENTI COME GLI ALTRI»
    // (utente, 17/09). Quattro SERVIZI, non quattro varianti di qualcosa:
    // `strategia: null` come Omega e Mike, quindi l'interruttore comanda il
    // bot intero e la sua modalita' e' quella della SUA riga di control
    // (`tennis_bot_service_control.mode`). Nessuno dei quattro eredita niente
    // da nessun altro, e accenderne uno non tocca gli altri tre.
    //
    // `chiaveImporto: 'stake'` e' la COLONNA `stake` della riga, non una voce
    // dentro `params`: il lettore la espone sotto quel nome e la scrittura
    // passa da `tennis_bot_service_update_params(p_stake)`, che `status` non
    // lo tocca.
    ...BOT_TENNIS.map((b): Interruttore => ({
        id: b, bot: b, strategia: null, sport: 'tennis',
        etichetta: `${BOT_LABEL[b]} tennis`,
        chiaveImporto: 'stake', chiaveImportoPerLato: null,
        etichettaImporto: 'stake',
    })),
];

/** Gli interruttori di uno sport. `null` = tutti (nessuna scheda scelta). */
export function interruttoriDiSport(sport: SportBot | null | undefined): Interruttore[] {
    return INTERRUTTORI.filter((i) => sport == null || i.sport === sport);
}

export function interruttoreDi(id: InterruttoreId): Interruttore {
    const i = INTERRUTTORI.find((x) => x.id === id);
    if (!i) throw new Error(`interruttore sconosciuto: ${id}`);
    return i;
}

// ---------------------------------------------------------------- lo stato

/** Quello che il SERVIZIO dichiara. Mai quello che il browser spera. */
export interface StatoServizio {
    inCorsa: boolean;
    modalita: Modalita | null;
    /** solo Safe: chi puo' APRIRE (`params.variants`). null = non letto */
    varianti?: string[] | null;
    /** solo Safe: con che soldi (`params.strategy_modes`). null = non letto */
    modiStrategia?: Record<string, 'paper' | 'live'> | null;
}

export interface StatoInterruttore {
    acceso: boolean;
    modalita: Modalita | null;
    /** sappiamo davvero che cosa sta facendo? Fail-closed: no = non si comanda */
    noto: boolean;
}

/**
 * Lo stato di UN interruttore, letto da `variants` + `strategy_modes` + il
 * `mode` del servizio. Nessun flag nuovo, nessuna deduzione: se il servizio
 * non lo dice, non lo sappiamo.
 */
export function statoInterruttore(i: Interruttore, s: StatoServizio | null | undefined): StatoInterruttore {
    if (s == null) return { acceso: false, modalita: null, noto: false };
    if (i.strategia == null) {
        return { acceso: s.inCorsa, modalita: s.modalita, noto: true };
    }
    // Safe: servizio fermo = tutte le strategie spente, e non serve sapere altro.
    if (!s.inCorsa) return { acceso: false, modalita: null, noto: true };
    // Servizio in corsa ma senza `variants`: NON lo sappiamo. Un elenco assente
    // non e' un elenco vuoto, e neanche i quattro default: quel default lo mette
    // il servizio in lettura, e finche' non lo pubblica non c'e' niente da leggere.
    if (s.varianti == null) return { acceso: false, modalita: null, noto: false };
    const acceso = s.varianti.map(String).includes(i.strategia);
    // I SOLDI VERI SI RAGGIUNGONO SOLO SCRIVENDOLO: serve il `mode` del
    // servizio in live E la voce della strategia in live. Uno solo non basta.
    const modalita: Modalita | null = s.modalita == null
        ? null
        : (s.modalita === 'live' && s.modiStrategia?.[i.strategia] === 'live' ? 'live' : 'paper');
    return { acceso, modalita, noto: true };
}

/** Quali strategie sono accese e con che soldi. `null` = spenta. */
export type Accensioni = Record<StrategiaSafe, Modalita | null>;

/** Le accensioni come sono ADESSO, dal servizio. */
export function accensioniCorrenti(s: StatoServizio | null | undefined): Accensioni {
    const out = {} as Accensioni;
    for (const nome of STRATEGIE_MANUALE) {
        const st = statoInterruttore(interruttoreDi(`safe-${nome}` as InterruttoreId), s);
        out[nome] = st.acceso ? (st.modalita ?? 'paper') : null;
    }
    return out;
}

export function nessunaAccesa(acc: Accensioni): boolean {
    return STRATEGIE_MANUALE.every((n) => acc[n] == null);
}

/**
 * La modalita' del SERVIZIO che serve a queste accensioni. Il `mode` del
 * control e' un TETTO: basta una strategia in live perche' il servizio debba
 * essere armato in live, e se nessuna lo e' il servizio torna in prova.
 */
export function modalitaServizio(acc: Accensioni): Modalita {
    return STRATEGIE_MANUALE.some((n) => acc[n] === 'live') ? 'live' : 'paper';
}

/**
 * I parametri con cui scrivere queste accensioni, a partire da quelli
 * CORRENTI. Le due mappe si scrivono INTERE; tutto il resto passa intatto.
 *
 * `altre` decide che fare delle strategie senza interruttore (`model`,
 * `manual`):
 *   · `'conserva'` (predefinito) — restano come sono: spegnere in silenzio
 *     una modalita' che l'operatore ha scelto sarebbe alterare una cosa che
 *     nessuno ha chiesto di cambiare;
 *   · `'prova'` — le porta in prova. E' il gesto «solo tennis» della scheda
 *     tennis, che l'utente ha chiesto per nome il 15/09.
 * In tutti e due i casi una voce illeggibile vale 'paper'.
 */
export function paramsAccensioni(
    correnti: Record<string, unknown>, acc: Accensioni,
    altre: 'conserva' | 'prova' = 'conserva',
): Record<string, unknown> {
    const out: Record<string, unknown> = { ...correnti };
    const precedenti = (correnti.strategy_modes && typeof correnti.strategy_modes === 'object'
        && !Array.isArray(correnti.strategy_modes))
        ? (correnti.strategy_modes as Record<string, unknown>) : {};

    // 1. CHI PUO' APRIRE. Solo le accese, nell'ordine del manuale.
    out.variants = STRATEGIE_MANUALE.filter((n) => acc[n] != null);

    // 2. CON CHE SOLDI. Mappa COMPLETA: le quattro del manuale piu' ogni altra
    //    chiave gia' presente, cosi' nessuna strategia eredita il mode del
    //    servizio. Una spenta vale 'paper': non apre, e se avesse comunque una
    //    gamba da chiudere la chiude con la modalita' della RIGA, non con questa.
    const modi: Record<string, string> = {};
    const nomi = new Set<string>([
        ...Object.keys(precedenti), ...STRATEGIE_SAFE_TUTTE,
    ]);
    for (const nome of nomi) {
        const manuale = (STRATEGIE_MANUALE as readonly string[]).includes(nome);
        if (manuale) {
            modi[nome] = acc[nome as StrategiaSafe] === 'live' ? 'live' : 'paper';
        } else if (altre === 'prova') {
            modi[nome] = 'paper';
        } else {
            modi[nome] = String(precedenti[nome] ?? '').toLowerCase() === 'live' ? 'live' : 'paper';
        }
    }
    out.strategy_modes = modi;
    return out;
}

// ------------------------------------------------------------- gli importi

/** Un importo di un interruttore, con la sua chiave vera e il suo ripiego. */
export interface CampoImporto {
    /** chiave vera nei parametri del servizio, es. 'stake.per_strategia.base' */
    chiave: string;
    etichetta: string;
    /** il valore in USO adesso: quello per strategia, o quello per lato */
    valore: number | null;
    /** quando il numero non significa «opera con tanto» */
    nota?: string;
    /** valorizzato quando l'importo NON e' ancora quello per strategia:
     *  la pagina lo deve dire, o il trader crede di avere una manopola sua */
    ereditato?: string;
}

/** Legge una chiave anche annidata ('stake.backSize') senza esplodere. */
export function leggiChiave(params: Record<string, unknown> | null | undefined, chiave: string): number | null {
    let nodo: unknown = params ?? null;
    for (const passo of chiave.split('.')) {
        if (nodo == null || typeof nodo !== 'object') return null;
        nodo = (nodo as Record<string, unknown>)[passo];
    }
    return typeof nodo === 'number' && Number.isFinite(nodo) ? nodo : null;
}

/**
 * Scrive una chiave anche annidata, **senza toccare il resto**.
 * Ritorna una copia: i parametri correnti non si mutano mai sul posto, o due
 * salvataggi in fila partirebbero da uno stato gia' sporcato dal primo.
 */
export function scriviChiave(
    params: Record<string, unknown> | null | undefined,
    chiave: string, valore: number,
): Record<string, unknown> {
    const radice: Record<string, unknown> = { ...(params ?? {}) };
    const passi = chiave.split('.');
    let nodo = radice;
    for (let i = 0; i < passi.length - 1; i += 1) {
        const k = passi[i];
        const dentro = nodo[k];
        nodo[k] = (dentro != null && typeof dentro === 'object') ? { ...(dentro as object) } : {};
        nodo = nodo[k] as Record<string, unknown>;
    }
    nodo[passi[passi.length - 1]] = valore;
    return radice;
}

/**
 * L'importo di UN interruttore. Se la chiave per strategia manca si mostra
 * quella per LATO — che e' quella che il motore usa davvero — e lo si DICE.
 */
export function importoDi(i: Interruttore, params: Record<string, unknown> | null): CampoImporto {
    const proprio = leggiChiave(params, i.chiaveImporto);
    if (proprio != null || i.chiaveImportoPerLato == null) {
        return {
            chiave: i.chiaveImporto, etichetta: i.etichettaImporto,
            valore: proprio, nota: i.notaImporto,
        };
    }
    const perLato = leggiChiave(params, i.chiaveImportoPerLato);
    const quale = i.chiaveImportoPerLato === 'stake.laySize' ? 'banca' : 'punta';
    return {
        chiave: i.chiaveImporto, etichetta: i.etichettaImporto,
        valore: perLato, nota: i.notaImporto,
        ereditato: `non ha ancora un importo suo: usa quello per lato (${quale}). `
            + 'Salvando qui diventa suo.',
    };
}

/** Gli importi di ogni interruttore, pronti per il pannello. */
export function importiInterruttori(
    interruttori: readonly Interruttore[],
    params: (bot: Bot) => Record<string, unknown> | null,
): Partial<Record<InterruttoreId, CampoImporto[]>> {
    const out: Partial<Record<InterruttoreId, CampoImporto[]>> = {};
    for (const i of interruttori) out[i.id] = [importoDi(i, params(i.bot))];
    return out;
}

// ------------------------------------------------------------------ errori

/**
 * L'obiettivo con cui riaccendere Omega quando non ne conosciamo uno.
 * NON e' un default di comodo: `omega_activate` richiede un numero, e passare
 * 0 spegnerebbe di fatto il dimensionamento.
 */
export class ObiettivoOmegaIgnoto extends Error {
    constructor() {
        super('non conosco l’obiettivo di giornata di Omega: aprilo dalla sua pagina e riprova');
        this.name = 'ObiettivoOmegaIgnoto';
    }
}

/**
 * `omega_activate` fa `coalesce(p_params, '{}'::jsonb)`: SOVRASCRIVE sempre.
 * E i tetti di rischio di Omega a ZERO significano TETTO SPENTO. Quindi: si
 * riavvia con i parametri CORRENTI, e se non li conosciamo non si avvia.
 */
export class ParametriOmegaIgnoti extends Error {
    constructor() {
        super('non conosco i parametri di Omega: avviarlo adesso azzererebbe i suoi '
            + 'tetti di rischio (perdita giornaliera, responsabilita’ aperta, per partita). '
            + 'Apri la pagina di Omega, controlla i parametri, e riprova.');
        this.name = 'ParametriOmegaIgnoti';
    }
}

/**
 * UN CAMBIO DI MODALITA' NON ACCENDE MAI NIENTE (ordine del 16/09).
 *
 * `safe_activate` porta `status` a `'running'`: usarlo per cambiare solo la
 * modalita' di un servizio FERMO lo accenderebbe. I bot li accende l'utente,
 * con il gesto di accensione, scegliendo li' la modalita'. A servizio fermo non
 * c'e' nessuna modalita' da cambiare: non sta operando niente.
 */
export class BotFermoNonCambiaModalita extends Error {
    constructor(bot: Bot) {
        super(`${bot} e’ fermo: non si cambia la modalita’ di un bot che non sta `
            + 'operando. Accendilo scegliendo paper o soldi veri — cambiare modalita’ '
            + 'non deve mai accendere niente.');
        this.name = 'BotFermoNonCambiaModalita';
    }
}

/**
 * SCRIVERE SENZA AVER LETTO CANCELLA. Tutte le RPC fanno
 * `coalesce(p_params, params)`: conservano solo se ricevono NULL. Un oggetto —
 * anche minuscolo — SOSTITUISCE l'intera colonna.
 */
export class ParametriNonLetti extends Error {
    constructor(bot: Bot) {
        super(`non ho ancora letto i parametri di ${bot}: salvare adesso `
            + 'sostituirebbe TUTTI gli altri (modalita’ per strategia, uscite, '
            + 'tetti di rischio) con i valori predefiniti. Attendi che lo stato '
            + 'sia caricato, o ricarica la pagina.');
        this.name = 'ParametriNonLetti';
    }
}

// ------------------------------------------------------------------ comandi

export interface SorgenteInterruttori {
    /** i parametri correnti di quel bot, dalla riga di control */
    params: (bot: Bot) => Record<string, unknown> | null;
    /** quello che il servizio dichiara adesso */
    servizio: (bot: Bot) => StatoServizio | null;
    /** solo Omega: l'obiettivo del giorno vive fuori da `params` e
     *  `omega_activate` lo pretende */
    obiettivoOmega: () => number | null;
    /**
     * ⚠️ REPERTO A (18/09) — OPZIONALE. Una rilettura FRESCA della riga di
     * Safe (params + stato), ignara dello snapshot React che `params()`/
     * `servizio()` restituiscono.
     *
     * IL DIFETTO: `dopo()` (il refetch di pagina, tipicamente `vm.ricarica`)
     * viene chiamato SENZA essere atteso — verificato riga per riga: sia qui
     * sia in `comandiBot.ts` il parametro si chiama `dopo: () => void`, non
     * `Promise<void>`. Un comando su Safe risolve quindi SUBITO dopo la RPC,
     * PRIMA che il refetch completo abbia riportato lo stato nuovo. Se in
     * quella finestra l'utente clicca un'ALTRA riga di Safe (base/esatto/
     * punta/tennis condividono la stessa colonna `variants`+`strategy_modes`),
     * il secondo comando ricostruisce l'intero array da uno snapshot React
     * VECCHIO, e la strategia appena accesa dal primo clic sparisce dalla
     * scrittura — si "spegne da sola" agli occhi dell'utente.
     *
     * LA CORREZIONE: quando questa funzione c'e' (la Control Room la aggancia
     * a una lettura vera dal database, `comandiBot.ts::rileggiSafeDalDatabase`
     * -> `fetchSafeState`), i comandi su Safe la usano AL POSTO di
     * `params('safe')`/`servizio('safe')` per COMPORRE la scrittura: il
     * secondo clic legge quello che il primo ha appena scritto sul database,
     * non quello che React non ha ancora ricevuto. Se assente (le pagine dei
     * singoli bot, dove questa finestra non si e' mai presentata: una pagina
     * mostra UNA strategia alla volta, mai due comandi ravvicinati su righe
     * diverse), si ricade sullo snapshot passato — compatibilita' con chi non
     * la fornisce, comportamento identico a prima.
     */
    rileggiSafe?: () => Promise<{
        params: Record<string, unknown> | null;
        servizio: StatoServizio | null;
    }>;
}

export interface ComandiInterruttori {
    accendi: (id: InterruttoreId, modalita: Modalita) => Promise<void>;
    spegni: (id: InterruttoreId) => Promise<void>;
    cambiaModalita: (id: InterruttoreId, modalita: Modalita) => Promise<void>;
    cambiaImporto: (id: InterruttoreId, chiave: string, importo: number) => Promise<void>;
    /** freno d'emergenza: ferma il SERVIZIO, non una strategia */
    fermaBot: (bot: Bot) => Promise<void>;
    /** scrive UNA configurazione completa di accensioni di Safe. Serve al gesto
     *  «solo tennis» della scheda tennis, che e' un caso particolare di questo
     *  modello e non un percorso a parte. */
    scriviAccensioni: (acc: Accensioni, opzioni?: OpzioniAccensioni) => Promise<void>;
    /**
     * Cambia la modalita' del SERVIZIO (il TETTO), senza toccare le
     * accensioni. A servizio FERMO si rifiuta: `safe_activate` lo
     * accenderebbe, e un cambio di modalita' non deve mai accendere niente.
     */
    cambiaModalitaServizio: (bot: Bot, modalita: Modalita) => Promise<void>;
}

export interface OpzioniAccensioni {
    /** che fare delle strategie senza interruttore (`model`, `manual`) */
    altre?: 'conserva' | 'prova';
    /** chiavi che il gesto AGGIUNGE (lo stake e le entrate di «solo tennis») */
    extra?: (p: Record<string, unknown>) => Record<string, unknown>;
    /**
     * Il gesto puo' far passare il servizio da fermo a in corsa? `true` solo
     * per i gesti di ACCENSIONE. Un cambio di modalita' passa `false`.
     */
    puoAccendere?: boolean;
}

/**
 * Costruisce i comandi. `dopo` viene chiamato a ogni cambiamento riuscito,
 * perche' la pagina deve rileggere lo stato dal SERVIZIO invece di fidarsi di
 * quello che credeva di aver appena fatto.
 */
export function creaInterruttori(
    sorgente: SorgenteInterruttori, dopo: () => void,
): ComandiInterruttori {
    const paramsLetti = (bot: Bot): Record<string, unknown> => {
        const correnti = sorgente.params(bot);
        if (correnti == null || Object.keys(correnti).length === 0) throw new ParametriNonLetti(bot);
        return correnti;
    };

    /**
     * ⚠️ REPERTO A (18/09) — LA CORREZIONE ALLA RADICE.
     *
     * Una lettura di Safe (params + stato) FRESCA quanto lo permette
     * `sorgente.rileggiSafe` (se il chiamante l'ha agganciata; altrimenti lo
     * snapshot passato, comportamento identico a prima). Ogni comando su Safe
     * che COMPONE una scrittura (`conCambio`, `scriviSafe`, il cambio del
     * `mode` del servizio) passa da qui invece di leggere `sorgente.params
     * ('safe')`/`sorgente.servizio('safe')` direttamente: e' l'UNICO punto che
     * decide "qual e' lo stato di Safe adesso", cosi' i due letture (quella
     * che sceglie CHI e' acceso e quella che sceglie CON CHE PARAMETRI si
     * scrive) non possono mai vedere due istantanee diverse nello stesso
     * comando.
     */
    const statoSafeFresco = async (): Promise<{ correnti: Record<string, unknown>; servizio: StatoServizio | null }> => {
        const fresco = sorgente.rileggiSafe
            ? await sorgente.rileggiSafe()
            : { params: sorgente.params('safe'), servizio: sorgente.servizio('safe') };
        if (fresco.params == null || Object.keys(fresco.params).length === 0) {
            throw new ParametriNonLetti('safe');
        }
        return { correnti: fresco.params, servizio: fresco.servizio };
    };

    /** Come sopra, ma solo lo STATO (per i gesti che non compongono `params`,
     *  es. il gate di `cambiaModalitaServizio`): non pretende che i parametri
     *  siano stati letti, perche' non li scrive. */
    const servizioSafeFresco = async (): Promise<StatoServizio | null> => {
        if (sorgente.rileggiSafe) return (await sorgente.rileggiSafe()).servizio;
        return sorgente.servizio('safe');
    };

    /**
     * Scrive UNA configurazione di accensioni su Safe. Tre casi, e uno solo
     * per ciascuno:
     *   · nessuna accesa      -> `safe_stop`. NON si scrive `variants: []`:
     *     il servizio (`normalize_variants`) legge la lista vuota come «usa il
     *     default», cioe' TUTTE E QUATTRO ACCESE. Spegnere l'ultima strategia
     *     scrivendo una lista vuota le riaccenderebbe tutte.
     *   · il servizio deve cambiare modalita' (o e' fermo) -> `safe_activate`
     *     con i parametri espliciti: e' l'unico modo di armare il `mode`.
     *   · gia' in corsa nella modalita' giusta -> `safe_update_params`, che non
     *     azzera `started_at` ne' interrompe niente.
     *
     * `frescoGia'` e' un'ottimizzazione facoltativa: quando il chiamante
     * (`conCambio`) ha GIA' fatto la lettura fresca per costruire `acc`, la
     * passa qui per evitare un secondo giro di rete — la firma pubblica
     * (`scriviAccensioni: (acc, opzioni?) => Promise<void>`, usata da
     * `soloTennis.ts`/`comandiBot.ts`) resta identica: e' un parametro in piu',
     * facoltativo, non visibile a chi chiama con la forma vecchia.
     */
    const scriviSafe = async (
        acc: Accensioni, opzioni: OpzioniAccensioni = {},
        frescoGia?: { correnti: Record<string, unknown>; servizio: StatoServizio | null },
    ) => {
        const { altre = 'conserva', extra, puoAccendere = true } = opzioni;
        const { correnti, servizio: s } = frescoGia ?? await statoSafeFresco();
        if (nessunaAccesa(acc)) {
            await stopSafe();
            svegliaBot('safe', 'comando'); // STADIO C — DOPO la scrittura, mai prima
            dopo();
            return;
        }
        const params = extra
            ? extra(paramsAccensioni(correnti, acc, altre))
            : paramsAccensioni(correnti, acc, altre);
        const voluta = modalitaServizio(acc);
        if (s?.inCorsa && s.modalita === voluta) {
            await updateSafeParams(params as Partial<SafeBotParams>);
        } else {
            // `safe_activate` porta `status` a 'running'. A servizio GIA' in
            // corsa non accende niente (riarma solo il `mode`); a servizio
            // FERMO lo accenderebbe, e un cambio di modalita' non deve mai
            // farlo: i bot li accende l'utente.
            if (!s?.inCorsa && !puoAccendere) throw new BotFermoNonCambiaModalita('safe');
            await activateSafe(voluta, params as Partial<SafeBotParams>);
        }
        svegliaBot('safe', 'comando'); // STADIO C — DOPO la scrittura, mai prima
        dopo();
    };

    /**
     * Le accensioni di ADESSO (lettura FRESCA, non lo snapshot React) con UNA
     * strategia cambiata: il resto non si tocca. Ritorna anche la lettura
     * fresca stessa, cosi' `accendi`/`spegni`/`cambiaModalita` la passano a
     * `scriviSafe` senza rileggere una seconda volta.
     */
    const conCambio = async (strategia: StrategiaSafe, valore: Modalita | null) => {
        const fresco = await statoSafeFresco();
        const acc: Accensioni = { ...accensioniCorrenti(fresco.servizio), [strategia]: valore };
        return { acc, fresco };
    };

    const avviaBot = async (bot: Bot, modalita: Modalita) => {
        // I quattro bot tennis: `stake` e `params` a null CONSERVANO quelli
        // gia' scritti (la RPC fa `coalesce`). La modalita' invece si scrive
        // sempre, ed e' quella che l'utente ha appena scelto col pulsante.
        if (isBotTennis(bot)) {
            await activateTennisBotService(bot as TennisBotKey, modalita);
            svegliaBot(bot, 'comando'); dopo(); return;
        }
        if (bot === 'mike') { await activateMike(modalita); svegliaBot(bot, 'comando'); dopo(); return; }
        const obiettivo = sorgente.obiettivoOmega();
        if (obiettivo == null) throw new ObiettivoOmegaIgnoto();
        const correnti = sorgente.params('omega');
        if (correnti == null || Object.keys(correnti).length === 0) throw new ParametriOmegaIgnoti();
        await activateOmega(modalita, obiettivo, correnti as Partial<OmegaParams>);
        svegliaBot(bot, 'comando');
        dopo();
    };

    const fermaBot = async (bot: Bot) => {
        // ⚠️ L'ORDINE CONTA, e l'`else` finale non e' piu' «per forza Omega»:
        // con i quattro bot tennis nel modello, un `else` distratto fermerebbe
        // OMEGA al posto dello Scalper. Ogni bot ha il suo ramo, per nome.
        if (isBotTennis(bot)) await stopTennisBotService(bot as TennisBotKey);
        else if (bot === 'safe') await stopSafe();
        else if (bot === 'mike') await stopMike();
        else await stopOmega();
        svegliaBot(bot, 'comando'); // STADIO C — DOPO la scrittura, mai prima
        dopo();
    };

    const accendi = async (id: InterruttoreId, modalita: Modalita) => {
        const i = interruttoreDi(id);
        if (i.strategia == null) return avviaBot(i.bot, modalita);
        const { acc, fresco } = await conCambio(i.strategia, modalita);
        await scriviSafe(acc, {}, fresco);
    };

    const spegni = async (id: InterruttoreId) => {
        const i = interruttoreDi(id);
        if (i.strategia == null) return fermaBot(i.bot);
        const { acc, fresco } = await conCambio(i.strategia, null);
        await scriviSafe(acc, {}, fresco);
    };

    const cambiaModalita = async (id: InterruttoreId, modalita: Modalita) => {
        const i = interruttoreDi(id);
        if (i.strategia != null) {
            const { acc, fresco } = await conCambio(i.strategia, modalita);
            await scriviSafe(acc, { puoAccendere: false }, fresco);
            return;
        }
        // `update_params` di Omega e Mike accetta il mode e NON tocca `status`:
        // e' il solo modo di cambiare modalita' senza accendere niente.
        await cambiaModalitaServizio(i.bot, modalita);
    };

    const cambiaImporto = async (id: InterruttoreId, chiave: string, importo: number) => {
        const i = interruttoreDi(id);
        // TENNIS — lo stake e' una COLONNA della riga di control, non una voce
        // di `params`: si scrive da sola, e `status` non lo tocca nessuno. Una
        // chiave diversa da 'stake' finirebbe dentro `params`, e li' si riparte
        // comunque dai parametri correnti.
        if (isBotTennis(i.bot)) {
            const k = i.bot as TennisBotKey;
            if (chiave === 'stake') await updateTennisBotService(k, { stake: importo });
            else {
                await updateTennisBotService(k, {
                    params: scriviChiave(paramsLetti(i.bot), chiave, importo),
                });
            }
            svegliaBot(i.bot, 'comando'); dopo(); return;
        }
        if (i.bot === 'safe') {
            // ⚠️ REPERTO A — anche un cambio d'importo su Safe compone da uno
            // snapshot: due cambi ravvicinati su due stake DIVERSI (es. base
            // poi esatto) devono vedersi a vicenda, non solo le accensioni.
            const { correnti } = await statoSafeFresco();
            const nuovi = scriviChiave(correnti, chiave, importo);
            await updateSafeParams(nuovi as Partial<SafeBotParams>);
            svegliaBot('safe', 'comando'); dopo(); return;
        }
        // si riparte SEMPRE dai parametri correnti: mandare la sola chiave
        // cambiata cancellerebbe tutto il resto.
        const nuovi = scriviChiave(paramsLetti(i.bot), chiave, importo);
        if (i.bot === 'mike') await updateMikeParams(nuovi as MikeParams);
        else await updateOmegaParams({ params: nuovi as Partial<OmegaParams> });
        svegliaBot(i.bot, 'comando');
        dopo();
    };

    /**
     * Il TETTO del servizio, senza toccare chi e' acceso. Per Safe l'unico modo
     * di scrivere `control.mode` e' `safe_activate`, che accende: quindi a
     * servizio fermo ci si rifiuta. Per Omega e Mike si passa da
     * `X_update_params(p_mode)`, che il `status` non lo tocca proprio.
     */
    const cambiaModalitaServizio = async (bot: Bot, modalita: Modalita) => {
        // TENNIS — `tennis_bot_service_activate` porterebbe `status` a
        // 'running': un cambio di modalita' non accende MAI niente, quindi
        // passa dalla gemella che `status` non lo tocca.
        if (isBotTennis(bot)) {
            await updateTennisBotService(bot as TennisBotKey, { mode: modalita });
            svegliaBot(bot, 'comando'); dopo(); return;
        }
        if (bot === 'omega') {
            await updateOmegaParams({ mode: modalita });
            svegliaBot(bot, 'comando'); dopo(); return;
        }
        if (bot === 'mike') {
            await updateMikeParams(paramsLetti('mike') as MikeParams, modalita);
            svegliaBot(bot, 'comando'); dopo(); return;
        }
        // ⚠️ REPERTO A — lettura FRESCA anche qui: un `inCorsa` letto da uno
        // snapshot vecchio potrebbe rifiutare un comando appena diventato
        // legittimo (o il contrario) nella stessa finestra di razza.
        const s = await servizioSafeFresco();
        if (!s?.inCorsa) throw new BotFermoNonCambiaModalita('safe');
        // niente `p_params`: `safe_activate` fa `coalesce(p_params, params)` e li
        // CONSERVA. Qui si cambia solo il tetto, non la configurazione.
        await activateSafe(modalita);
        svegliaBot('safe', 'comando');
        dopo();
    };

    return {
        accendi, spegni, cambiaModalita, cambiaImporto, fermaBot,
        scriviAccensioni: scriviSafe, cambiaModalitaServizio,
    };
}
