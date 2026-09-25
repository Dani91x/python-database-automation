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
import { getLiveSettings, setLiveOrderMode, type LiveSettings } from '@/lib/liveOrders';
import {
    fetchScalperControlRoom, stopScalperSessione, sessioneAttiva, modalitaSessione,
    impostaUsciteScalper,
} from '@/lib/scalperControlRoom';

export type { Bot };

export type Modalita = 'paper' | 'live';
export type SportBot = 'calcio' | 'tennis';

/** Le quattro strategie del manuale di Safe, nell'ordine del manuale. */
export const STRATEGIE_MANUALE = ['base', 'esatto', 'punta', 'tennis'] as const;
export type StrategiaSafe = (typeof STRATEGIE_MANUALE)[number];

/**
 * TUTTE le strategie che il servizio Safe conosce (`bot_service._STRATEGIES`).
 * `model` e `manual` non sono strategie del manuale — sono le opportunita' di
 * modello e gli ordini a mano — ma vanno NOMINATE quando si scrive la mappa:
 * una chiave assente, per il servizio, vale PAPER (i soldi veri si
 * raggiungono solo scrivendolo), e la mappa si scrive sempre intera.
 */
export const STRATEGIE_SAFE_TUTTE = ['base', 'esatto', 'punta', 'tennis', 'model', 'manual'] as const;

/**
 * 24/09 — «OGNI strumento che propone ingressi a mercato deve avere sia la
 * versione PAPER che LIVE, e in caso di LIVE gli ordini devono partire
 * DAVVERO» (utente). Le due voci di Safe che NON sono strategie del manuale
 * ma STRUMENTI:
 *   · `model`  = le opportunita' del modello (anche anomalie, combo, tennis)
 *     che l'utente APPROVA dalla scheda (PIAZZA);
 *   · `manual` = gli ordini che l'utente fa A MANO dalla scheda di Safe.
 * Non aprono niente da sole — non stanno in `variants` — quindi il loro
 * interruttore sceglie SOLO con che soldi: prova o soldi veri. Seguono il
 * servizio Safe: a servizio fermo non si arma niente (un cambio di modalita'
 * non accende mai niente) e non si «spengono» (per non vedere proposte ci
 * sono i rubinetti «Proponimi…» della scheda parametri).
 */
export const STRATEGIE_SOLO_MODALITA = ['model', 'manual'] as const;
export type StrategiaSoloModalita = (typeof STRATEGIE_SOLO_MODALITA)[number];

export function isSoloModalita(s: string | null | undefined): s is StrategiaSoloModalita {
    return s != null && (STRATEGIE_SOLO_MODALITA as readonly string[]).includes(s);
}

export type InterruttoreId =
    | 'omega' | 'mike' | 'scalper'
    | 'safe-base' | 'safe-esatto' | 'safe-punta' | 'safe-tennis'
    | 'safe-model' | 'safe-manual'
    | BotTennis;

export interface Interruttore {
    id: InterruttoreId;
    bot: Bot;
    /** null = l'interruttore comanda il SERVIZIO intero (Omega, Mike) */
    strategia: StrategiaSafe | StrategiaSoloModalita | null;
    sport: SportBot;
    /** come si chiama davanti al trader */
    etichetta: string;
    /** che cosa comanda, in parole: compare accanto all'etichetta e nella
     *  conferma dei soldi veri. Serve dove il nome da solo non basta. */
    descrizione?: string;
    /** la chiave di importo di QUESTO interruttore nei parametri del servizio.
     *  `null` = questo interruttore non ha un importo suo (model/manual: lo
     *  stake lo decide la proposta o la scheda, non l'interruttore). */
    chiaveImporto: string | null;
    /** chiave usata prima di B.5, per LATO: resta il ripiego dichiarato */
    chiaveImportoPerLato: string | null;
    etichettaImporto: string;
    notaImporto?: string;
    /**
     * 24/09 - presente = questo bot NON si accende da qui: si ARMA PER
     * PARTITA (lo scalper calcio, una riga `scalper_control` per evento). La
     * riga mostra stato e modalita' delle sue sessioni e offre solo FERMA;
     * al posto di "avvia" dice questa frase. Accendere da qui vorrebbe dire
     * scegliere le partite al posto dell'utente (strategia) o un interruttore
     * globale che il supervisore non legge: decisione del coordinatore.
     */
    armoPerPartita?: string;
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
    // -- 24/09 - LO SCALPER CALCIO ("in Control Room come tutti gli altri
    // bot", utente). Si arma PER PARTITA: acceso = almeno una sessione
    // attiva, modalita' = quella dichiarata dalle sessioni (`dry_run`), FERMA
    // = stop di tutte le sessioni attive (force-flat, `scalper_stop_sessione`).
    // Nessun importo qui: lo stake e' della sessione, scelto all'armo.
    {
        id: 'scalper', bot: 'scalper', strategia: null, sport: 'calcio',
        etichetta: 'Scalper calcio',
        descrizione: 'si arma per partita da Segui Live; da qui stato, modalita\u2019 e stop delle sessioni',
        chiaveImporto: null, chiaveImportoPerLato: null, etichettaImporto: '',
        armoPerPartita: 'si arma per partita da Segui Live (stake e prova/soldi veri si scelgono li\u2019)',
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
    // ── 24/09 — I DUE STRUMENTI DI SAFE CHE PROPONGONO INGRESSI ─────────────
    // Solo la MODALITA': si accendono in prova o con soldi veri insieme al
    // servizio Safe, con la stessa doppia conferma di ogni altra riga. Stanno
    // nella scheda calcio: dalla scheda tennis il gesto «solo tennis» li porta
    // comunque in prova (`paramsAccensioni(..., 'prova')`, ordine del 15/09).
    {
        id: 'safe-model', bot: 'safe', strategia: 'model', sport: 'calcio',
        etichetta: 'Safe modello',
        descrizione: 'opportunità del modello che approvo',
        chiaveImporto: null, chiaveImportoPerLato: null, etichettaImporto: '',
    },
    {
        id: 'safe-manual', bot: 'safe', strategia: 'manual', sport: 'calcio',
        etichetta: 'Safe a mano',
        descrizione: 'ordini a mano dalla scheda',
        chiaveImporto: null, chiaveImportoPerLato: null, etichettaImporto: '',
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
    // 24/09 — model/manual: accese col servizio, e la modalita' si dichiara
    // SEMPRE (anche a servizio fermo: le richieste della scheda il servizio le
    // esegue anche da fermo). Stessa regola del servizio
    // (`modalita_di_strategia`): tetto del servizio in live E voce scritta
    // 'live'. Con il servizio in live e la mappa non letta non lo sappiamo.
    if (isSoloModalita(i.strategia)) {
        // Servizio in corsa ma senza `variants`: come per le quattro, NON lo
        // sappiamo — e il comando riscrive `variants`, quindi non si comanda.
        if (s.inCorsa && s.varianti == null) return { acceso: false, modalita: null, noto: false };
        if (s.modalita == null) return { acceso: s.inCorsa, modalita: null, noto: true };
        if (s.modalita !== 'live') return { acceso: s.inCorsa, modalita: 'paper', noto: true };
        if (s.modiStrategia == null) return { acceso: false, modalita: null, noto: false };
        return {
            acceso: s.inCorsa,
            modalita: s.modiStrategia[i.strategia] === 'live' ? 'live' : 'paper',
            noto: true,
        };
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
 * 24/09 — la modalita' del SERVIZIO che serve a una mappa `strategy_modes`
 * GIA' COMPOSTA (da `paramsAccensioni`, quindi intera): basta una voce 'live'
 * — una strategia accesa in live, oppure `model`/`manual` scritti 'live' —
 * perche' il tetto debba essere armato in live. Le strategie spente valgono
 * gia' 'paper' nella mappa composta, quindi non la alzano.
 */
export function modalitaServizioDaParams(params: Record<string, unknown>): Modalita {
    const modi = params.strategy_modes;
    if (modi == null || typeof modi !== 'object' || Array.isArray(modi)) return 'paper';
    // solo le chiavi che il servizio conosce (`_STRATEGIES`): una chiave
    // estranea il servizio la scarta, e non deve poter armare il tetto.
    const m = modi as Record<string, unknown>;
    return STRATEGIE_SAFE_TUTTE.some((n) => String(m[n] ?? '').toLowerCase() === 'live')
        ? 'live' : 'paper';
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
    // model/manual non hanno un importo loro: chi chiede il loro importo sta
    // sbagliando interruttore (`importiInterruttori` li salta), mai inventarlo
    if (i.chiaveImporto == null) throw new Error(`${i.id} non ha un importo suo`);
    const chiave = i.chiaveImporto;
    const proprio = leggiChiave(params, chiave);
    if (proprio != null || i.chiaveImportoPerLato == null) {
        return {
            chiave, etichetta: i.etichettaImporto,
            valore: proprio, nota: i.notaImporto,
        };
    }
    const perLato = leggiChiave(params, i.chiaveImportoPerLato);
    const quale = i.chiaveImportoPerLato === 'stake.laySize' ? 'banca' : 'punta';
    return {
        chiave, etichetta: i.etichettaImporto,
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
    for (const i of interruttori) {
        // model/manual: nessun campo importo (lo stake lo decide la proposta
        // o la scheda), mai uno inventato
        out[i.id] = i.chiaveImporto == null ? [] : [importoDi(i, params(i.bot))];
    }
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
 * 24/09 — model/manual seguono il servizio Safe: a servizio FERMO non si
 * arma niente. Accenderli vorrebbe dire accendere Safe, e Safe si accende
 * scegliendo una delle sue strategie (una lista di varianti vuota, per il
 * servizio, vuol dire «tutte e quattro»: non la si scrive mai per sbaglio).
 */
export class SafeFermoPerStrumento extends Error {
    constructor(etichetta: string) {
        super(`Safe è fermo: «${etichetta}» segue il servizio Safe. Accendi prima una `
            + 'strategia di Safe (base, esatto, punta o tennis), poi scegli qui '
            + 'prova o soldi veri.');
        this.name = 'SafeFermoPerStrumento';
    }
}

/**
 * 24/09 — model/manual non si «spengono»: non aprono niente da soli, scelgono
 * solo con che soldi. Il gesto sicuro e' «passa a prova»; per non vedere piu'
 * le proposte ci sono i rubinetti «Proponimi…» della scheda parametri.
 */
export class StrumentoSenzaSpegnimento extends Error {
    constructor(etichetta: string) {
        super(`«${etichetta}» non si spegne da qui: sceglie solo con che soldi `
            + 'opera. Usa «passa a prova» per non mandare ordini reali; per non '
            + 'ricevere proposte usa i rubinetti «Proponimi…» nei parametri di Safe.');
        this.name = 'StrumentoSenzaSpegnimento';
    }
}

/**
 * 24/09 - LO SCALPER CALCIO SI ARMA PER PARTITA. Accenderlo, cambiargli la
 * modalita' o lo stake da qui vorrebbe dire scegliere la partita al posto
 * dell'utente: non si fa, e il gesto lo DICE invece di fingere.
 */
export class ScalperSiArmaPerPartita extends Error {
    constructor(gesto: string) {
        super(`lo Scalper calcio non si ${gesto} da qui: si arma PER PARTITA da Segui Live `
            + '(partita, stake, prova o soldi veri). Da qui si vedono le sue sessioni e si fermano.');
        this.name = 'ScalperSiArmaPerPartita';
    }
}

/**
 * 24/09 - FERMA sullo scalper: non tutte le sessioni si sono fermate. Il
 * freno le prova TUTTE e poi dice quali hanno mancato (e perche').
 */
export class ScalperNonTutteFermate extends Error {
    constructor(mancate: { eventId: string; motivo: string }[]) {
        super(`${mancate.length === 1 ? 'una sessione dello Scalper NON si e\u2019 fermata'
            : `${mancate.length} sessioni dello Scalper NON si sono fermate`}: `
            + mancate.map((m) => `${m.eventId} (${m.motivo})`).join('; '));
        this.name = 'ScalperNonTutteFermate';
    }
}

/**
 * Ferma TUTTE le sessioni attive dello scalper, una alla volta, ripartendo da
 * una lettura FRESCA del database (mai dallo snapshot della pagina: una
 * sessione armata un secondo fa deve fermarsi anche lei). Ogni stop porta la
 * firma della sessione (`requested_at`) e la sua modalita': la RPC rifiuta
 * una sessione riarmata nel frattempo. Le prova tutte, poi dice quali no.
 */
export async function fermaTutteLeSessioniScalper(): Promise<number> {
    const { sessioni } = await fetchScalperControlRoom();
    const mancate: { eventId: string; motivo: string }[] = [];
    let fermate = 0;
    for (const s of sessioni) {
        if (!sessioneAttiva(s)) continue;
        const m = modalitaSessione(s);
        if (m == null) {
            mancate.push({ eventId: s.event_id, motivo: 'modalita\u2019 non dichiarata' });
            continue;
        }
        try {
            await stopScalperSessione(s.event_id, s.requested_at, m);
            fermate += 1;
        } catch (e) {
            mancate.push({ eventId: s.event_id, motivo: e instanceof Error ? e.message : String(e) });
        }
    }
    if (mancate.length) throw new ScalperNonTutteFermate(mancate);
    return fermate;
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
    /**
     * 25/09 — «Uscite automatiche» di QUESTO interruttore (acceso = il bot
     * esegue da solo le uscite della strategia; spento = diventano proposte
     * nella scheda). Facoltativo: chi non lo fornisce (pagine dei singoli bot,
     * finti dei test vecchi) non mostra il pulsante. Vedi `paramsConUscite`.
     */
    cambiaUscite?: (id: InterruttoreId, automatiche: boolean) => Promise<void>;
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
        // 24/09 — il TETTO si calcola dalla mappa COMPOSTA, non dalle sole
        // quattro accensioni: se `model`/`manual` sono scritti 'live' (e
        // `altre` li ha conservati) il servizio deve restare armato in live,
        // o riportarlo in paper li spegnerebbe in silenzio. Con 'prova' la
        // mappa li porta a paper e il risultato e' identico a prima.
        const voluta: Modalita = modalitaServizio(acc) === 'live' ? 'live'
            : modalitaServizioDaParams(params);
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

    /**
     * 24/09 — model/manual: si scrive SOLO la loro voce di `strategy_modes`,
     * ripartendo dalla lettura FRESCA. Le quattro accensioni restano quelle di
     * adesso (`paramsAccensioni` con `'conserva'` riscrive la mappa INTERA, le
     * altre voci con il loro valore attuale), poi si sovrascrive la voce di
     * questo strumento. Il tetto si ricalcola dalla mappa composta: in live
     * lo si arma con `safe_activate` (a servizio GIA' in corsa, quindi non
     * accende niente), tornando in prova lo si abbassa solo se nessun'altra
     * voce e' in live. A servizio fermo si rifiuta: un cambio di modalita'
     * non accende mai niente.
     */
    const scriviSoloModalita = async (i: Interruttore, strumento: StrategiaSoloModalita, modalita: Modalita) => {
        const { correnti, servizio: s } = await statoSafeFresco();
        if (!s?.inCorsa) throw new SafeFermoPerStrumento(i.etichetta);
        // Chi e' acceso DEVE essere noto: `variants` riscritto da uno stato
        // ignoto spegnerebbe (o, vuoto, riaccenderebbe TUTTE) le strategie.
        const acc = accensioniCorrenti(s);
        if (s.varianti == null || nessunaAccesa(acc)) throw new ParametriNonLetti('safe');
        const composti = paramsAccensioni(correnti, acc, 'conserva');
        const params: Record<string, unknown> = {
            ...composti,
            strategy_modes: {
                ...(composti.strategy_modes as Record<string, string>),
                [strumento]: modalita,
            },
        };
        const voluta = modalitaServizioDaParams(params);
        if (s.modalita === voluta) {
            await updateSafeParams(params as Partial<SafeBotParams>);
        } else {
            await activateSafe(voluta, params as Partial<SafeBotParams>);
        }
        svegliaBot('safe', 'comando'); // STADIO C — DOPO la scrittura, mai prima
        dopo();
    };

    const avviaBot = async (bot: Bot, modalita: Modalita) => {
        // 24/09 - lo scalper calcio si arma per partita: da qui mai
        if (bot === 'scalper') throw new ScalperSiArmaPerPartita('accende');
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
        else if (bot === 'scalper') {
            // tutte le sessioni attive, con la guardia d'identita'. Anche se
            // qualcuna manca, la pagina si rilegge (le altre sono ferme).
            try { await fermaTutteLeSessioniScalper(); } finally { dopo(); }
            return;
        }
        else if (bot === 'safe') await stopSafe();
        else if (bot === 'mike') await stopMike();
        else await stopOmega();
        svegliaBot(bot, 'comando'); // STADIO C — DOPO la scrittura, mai prima
        dopo();
    };

    const accendi = async (id: InterruttoreId, modalita: Modalita) => {
        const i = interruttoreDi(id);
        if (i.strategia == null) return avviaBot(i.bot, modalita);
        if (isSoloModalita(i.strategia)) return scriviSoloModalita(i, i.strategia, modalita);
        const { acc, fresco } = await conCambio(i.strategia, modalita);
        await scriviSafe(acc, {}, fresco);
    };

    const spegni = async (id: InterruttoreId) => {
        const i = interruttoreDi(id);
        if (i.strategia == null) return fermaBot(i.bot);
        if (isSoloModalita(i.strategia)) throw new StrumentoSenzaSpegnimento(i.etichetta);
        const { acc, fresco } = await conCambio(i.strategia, null);
        await scriviSafe(acc, {}, fresco);
    };

    const cambiaModalita = async (id: InterruttoreId, modalita: Modalita) => {
        const i = interruttoreDi(id);
        // la sessione legge `dry_run` una volta, all'armo: cambiarlo a sessione
        // in corsa non cambierebbe niente di vero
        if (i.bot === 'scalper') throw new ScalperSiArmaPerPartita('cambia di modalita\u2019');
        if (isSoloModalita(i.strategia)) return scriviSoloModalita(i, i.strategia, modalita);
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
        if (i.bot === 'scalper') throw new ScalperSiArmaPerPartita('cambia di stake');
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
        if (bot === 'scalper') throw new ScalperSiArmaPerPartita('cambia di modalita\u2019');
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

    /**
     * 25/09 — «Uscite automatiche» per singolo bot/strategia. Si riparte
     * SEMPRE dai parametri correnti (le RPC sostituiscono l'intera colonna):
     * `paramsConUscite` tocca UNA chiave e basta. Lo scalper non ha una riga di
     * servizio: la scelta va su TUTTE le sessioni attive (RPC dedicata).
     */
    const cambiaUscite = async (id: InterruttoreId, automatiche: boolean) => {
        const i = interruttoreDi(id);
        if (isBotTennis(i.bot)) throw new UsciteNonGestiteQui(i.etichetta);
        if (i.bot === 'scalper') {
            await impostaUsciteScalper(automatiche);
            dopo(); return;
        }
        if (i.bot === 'safe') {
            const { correnti } = await statoSafeFresco();
            await updateSafeParams(paramsConUscite(i, correnti, automatiche) as Partial<SafeBotParams>);
            svegliaBot('safe', 'comando'); dopo(); return;
        }
        const nuovi = paramsConUscite(i, paramsLetti(i.bot), automatiche);
        if (i.bot === 'mike') await updateMikeParams(nuovi as MikeParams);
        else await updateOmegaParams({ params: nuovi as Partial<OmegaParams> });
        svegliaBot(i.bot, 'comando');
        dopo();
    };

    return {
        accendi, spegni, cambiaModalita, cambiaImporto, fermaBot,
        scriviAccensioni: scriviSafe, cambiaModalitaServizio, cambiaUscite,
    };
}

// ============================================================================
// 25/09 — USCITE AUTOMATICHE / MANUALI, PER SINGOLO BOT.
//
// «Tutti i bot (in live e in paper) DEVONO AVERE L'ABILITAZIONE per le uscite
// automatiche e per l'operatività totalmente automatica; se disattivo il
// pulsante (TUTTO DEVE ESSERE IN UI PER SINGOLO BOT), le uscite le gestisco io
// manualmente tramite l'apposita scheda» (utente, 25/09).
//
// DOVE VIVE L'INTERRUTTORE (una chiave per servizio, letta a caldo a ogni giro,
// identica in prova e con soldi veri; nessuna tabella nuova):
//   Omega   `params.uscite_protezione`  'automatico' | 'avvisa_e_proponi' (24/09)
//   Mike    `params.uscite_automatiche` bool (Betfair/mike/config.py)
//   Safe    `params.uscite_automatiche` = { base, esatto, punta, tennis, model }
//           (bool per strategia; tennis ripiega su `tennis_exit_approval`)
//   Scalper `scalper_control.params.uscite_automatiche` di ogni sessione attiva
// Cambia solo CHI esegue l'uscita, mai QUANDO o COME la strategia la decide.
// ============================================================================

/** Lo stato delle uscite di UNA riga. `automatiche: null` = non si sa (parametri
 *  non letti, o sessioni dello scalper in stati diversi): non si comanda. */
export interface StatoUscite {
    automatiche: boolean | null;
    /** una frase in piu' (es. «nessuna sessione attiva») */
    nota?: string;
    /** posizioni aperte di questa riga e da quanti minuti la piu' vecchia */
    aperte?: number | null;
    daMin?: number | null;
}

/** Le strategie di Safe che hanno uscite decise dal bot (`bot_service.STRATEGIE_CON_USCITE`). */
export const STRATEGIE_SAFE_CON_USCITE = ['base', 'esatto', 'punta', 'tennis', 'model'] as const;

export class UsciteNonGestiteQui extends Error {
    constructor(etichetta: string) {
        super(`${etichetta}: le uscite di questo bot non si comandano da questo interruttore`);
        this.name = 'UsciteNonGestiteQui';
    }
}

/** Safe: stessa regola del servizio (`normalize_uscite_automatiche`). Solo un
 *  booleano vero conta; altrimenti il comportamento di oggi. */
export function usciteSafeDi(params: Record<string, unknown> | null | undefined, strategia: string): boolean {
    const mappa = params?.uscite_automatiche;
    const v = mappa != null && typeof mappa === 'object' && !Array.isArray(mappa)
        ? (mappa as Record<string, unknown>)[strategia] : undefined;
    if (typeof v === 'boolean') return v;
    if (strategia === 'tennis') return params?.tennis_exit_approval !== true;
    return true;
}

/** Mike: stessa coercizione di `config._coerce` per un bool. Assente = true. */
function usciteMikeDi(params: Record<string, unknown>): boolean {
    const v = params.uscite_automatiche;
    if (v === undefined || v === null) return true;
    if (typeof v === 'boolean') return v;
    if (typeof v === 'string') return ['1', 'true', 'yes', 'on'].includes(v.trim().toLowerCase());
    return Boolean(v);
}

/**
 * Le uscite di UNA riga, lette dai parametri del SUO servizio. `null` = la riga
 * non ha un interruttore delle uscite qui (Safe «a mano», bot tennis: altro
 * perimetro). Parametri non letti = `automatiche: null` (fail-closed).
 */
export function statoUscite(i: Interruttore, params: Record<string, unknown> | null | undefined): StatoUscite | null {
    if (isBotTennis(i.bot)) return null;
    if (i.bot === 'safe' && (i.strategia == null || !(STRATEGIE_SAFE_CON_USCITE as readonly string[]).includes(i.strategia))) {
        return null;
    }
    if (i.bot === 'scalper') {
        // lo scalper espone l'aggregato delle sessioni attive (`usciteSessioniScalper`)
        const v = params?.uscite_automatiche;
        if (typeof v === 'boolean') return { automatiche: v };
        return { automatiche: null, nota: typeof params?.uscite_nota === 'string' ? params.uscite_nota : 'sessioni non lette' };
    }
    if (params == null || Object.keys(params).length === 0) return { automatiche: null };
    if (i.bot === 'omega') {
        return { automatiche: String(params.uscite_protezione ?? '').trim().toLowerCase() === 'automatico' };
    }
    if (i.bot === 'mike') return { automatiche: usciteMikeDi(params) };
    return { automatiche: usciteSafeDi(params, String(i.strategia)) };
}

/** Le uscite di ogni interruttore di un elenco (come `importiInterruttori`). */
export function usciteInterruttori(
    lista: readonly Interruttore[],
    paramsDi: (bot: Bot) => Record<string, unknown> | null,
): Partial<Record<InterruttoreId, StatoUscite>> {
    const out: Partial<Record<InterruttoreId, StatoUscite>> = {};
    for (const i of lista) {
        const st = statoUscite(i, paramsDi(i.bot));
        if (st != null) out[i.id] = st;
    }
    return out;
}

/**
 * I parametri da SCRIVERE per portare le uscite di `i` a `automatiche`,
 * partendo da quelli correnti: una chiave sola cambia, tutto il resto resta.
 * Safe tennis scrive anche il cancelletto storico `tennis_exit_approval`
 * (una sola verità: la scheda parametri lo mostra ancora).
 */
export function paramsConUscite(
    i: Interruttore, correnti: Record<string, unknown>, automatiche: boolean,
): Record<string, unknown> {
    if (i.bot === 'omega') {
        return { ...correnti, uscite_protezione: automatiche ? 'automatico' : 'avvisa_e_proponi' };
    }
    if (i.bot === 'mike') return { ...correnti, uscite_automatiche: automatiche };
    if (i.bot === 'safe' && i.strategia != null
        && (STRATEGIE_SAFE_CON_USCITE as readonly string[]).includes(i.strategia)) {
        const prima = correnti.uscite_automatiche;
        const mappa = prima != null && typeof prima === 'object' && !Array.isArray(prima)
            ? { ...(prima as Record<string, unknown>) } : {};
        mappa[i.strategia] = automatiche;
        const out: Record<string, unknown> = { ...correnti, uscite_automatiche: mappa };
        if (i.strategia === 'tennis') out.tennis_exit_approval = !automatiche;
        return out;
    }
    throw new UsciteNonGestiteQui(i.etichetta);
}

/**
 * «uscite: manuali, N posizioni aperte da X min»: aggiunge a ogni riga quante
 * posizioni APERTE ha il suo bot (per Safe: della sua strategia, dalla
 * `gamba` dichiarata dalla riga) e da quanti minuti c'e' la piu' vecchia.
 * Puro: le posizioni sono quelle che la pagina ha gia' (`vm.posizioni`).
 */
export function conPosizioniAperte(
    uscite: Partial<Record<InterruttoreId, StatoUscite>>,
    posizioni: readonly { bot: Bot; piazzataAt: string; gamba?: string | null }[],
    nowMs: number,
): Partial<Record<InterruttoreId, StatoUscite>> {
    const out: Partial<Record<InterruttoreId, StatoUscite>> = {};
    for (const [id, st] of Object.entries(uscite) as [InterruttoreId, StatoUscite][]) {
        const i = interruttoreDi(id);
        const mie = posizioni.filter((p) => p.bot === i.bot
            && (i.strategia == null || String(p.gamba ?? '').trim().toLowerCase() === i.strategia));
        let piuVecchia: number | null = null;
        for (const p of mie) {
            const t = Date.parse(p.piazzataAt);
            if (Number.isFinite(t) && (piuVecchia == null || t < piuVecchia)) piuVecchia = t;
        }
        out[id] = {
            ...st,
            aperte: mie.length,
            daMin: piuVecchia == null ? null : Math.max(0, Math.floor((nowMs - piuVecchia) / 60_000)),
        };
    }
    return out;
}

/**
 * Lo scalper: l'aggregato delle sessioni ATTIVE (`scalper_control.params`).
 * Tutte d'accordo -> quel valore; nessuna attiva -> `true` con la nota (le
 * sessioni nuove nascono con le uscite automatiche); discordi -> `null`.
 * Ritorna i "params" della riga scalper per `statoUscite`.
 */
export function usciteSessioniScalper(
    sessioni: readonly { status: string; params: Record<string, unknown> | null }[],
): Record<string, unknown> {
    const attive = sessioni.filter((s) => sessioneAttiva(s));
    if (attive.length === 0) {
        return { uscite_automatiche: true, uscite_nota: 'nessuna sessione attiva: le nuove nascono con le uscite automatiche' };
    }
    const valori = new Set(attive.map((s) => (s.params?.uscite_automatiche === false ? false : true)));
    if (valori.size === 1) return { uscite_automatiche: [...valori][0] };
    return { uscite_automatiche: null, uscite_nota: 'sessioni con scelte diverse' };
}

// ============================================================================
// ORDINI REALI (24/09) - "devo operare dalla UI, non dal codice".
//
// Prima `LIVE_ORDER_MODE` (OFF/PAPER/LIVE) viveva SOLO nel .env: era il gate
// del trading manuale dal ladder E il freno di Safe/Mike/Omega sugli ordini
// reali. Adesso la scelta sta nella riga di controllo `betfair_live_settings`
// (la stessa del kill-switch) e si cambia da qui.
//
// LA REGOLA E' UNA, ED E' QUELLA DEL RUNNER (`Betfair/stream/modo_ordini.py`):
//   effettivo = il PIU' RESTRITTIVO fra il tetto del .env e la scelta dalla UI
//   (OFF < PAPER < LIVE); scelta assente o illeggibile -> OFF.
// Qui la si RIPETE solo per mostrarla: chi decide e' il runner, che pubblica
// lo stesso valore in `live_now.state.order_mode` (il badge di MarketWatch).
// ============================================================================
export type ModoOrdini = 'OFF' | 'PAPER' | 'LIVE';
export const MODI_ORDINI: readonly ModoOrdini[] = ['OFF', 'PAPER', 'LIVE'];
const RANGO_MODO: Record<ModoOrdini, number> = { OFF: 0, PAPER: 1, LIVE: 2 };

/** 'live' / ' Paper ' -> 'LIVE' / 'PAPER'. Qualunque altra cosa -> null. */
export function normalizzaModoOrdini(v: unknown): ModoOrdini | null {
    if (typeof v !== 'string') return null;
    const m = v.trim().toUpperCase();
    return (MODI_ORDINI as readonly string[]).includes(m) ? (m as ModoOrdini) : null;
}

/** La regola del runner: il piu' restrittivo; uno dei due illeggibile -> OFF. */
export function modoOrdiniEffettivo(tetto: unknown, scelto: unknown): ModoOrdini {
    const t = normalizzaModoOrdini(tetto);
    const s = normalizzaModoOrdini(scelto);
    if (t == null || s == null) return 'OFF';
    return RANGO_MODO[t] <= RANGO_MODO[s] ? t : s;
}

export interface StatoOrdiniReali {
    /** la riga e' stata letta */
    letto: boolean;
    /** riga letta ma senza `order_mode`: la migrazione non e' applicata */
    migrazioneMancante: boolean;
    scelto: ModoOrdini | null;
    /** tetto dichiarato dal runner al suo avvio; null = mai dichiarato */
    tetto: ModoOrdini | null;
    effettivo: ModoOrdini;
    /** la UI chiede piu' di quanto il tetto consenta */
    limitatoDalTetto: boolean;
    cambiatoDa: string | null;
    cambiatoAlle: string | null;
    tettoAlle: string | null;
}

export function statoOrdiniReali(s: LiveSettings | null | undefined): StatoOrdiniReali {
    const letto = s != null;
    const migrazioneMancante = letto && !('order_mode' in (s as object));
    const scelto = letto ? normalizzaModoOrdini(s?.order_mode) : null;
    const tetto = letto ? normalizzaModoOrdini(s?.order_mode_tetto) : null;
    return {
        letto,
        migrazioneMancante,
        scelto,
        tetto,
        effettivo: modoOrdiniEffettivo(tetto, scelto),
        limitatoDalTetto: scelto != null && tetto != null && RANGO_MODO[scelto] > RANGO_MODO[tetto],
        cambiatoDa: s?.order_mode_updated_by ?? null,
        cambiatoAlle: s?.order_mode_updated_at ?? null,
        tettoAlle: s?.order_mode_tetto_at ?? null,
    };
}

/** Il gesto: scrive la scelta (RPC `set_live_order_mode`). La doppia conferma
 *  per LIVE la fa il componente, come per i bot. */
export async function scegliModoOrdini(m: ModoOrdini): Promise<LiveSettings | null> {
    return setLiveOrderMode(m.toLowerCase() as 'off' | 'paper' | 'live');
}

/** La lettura (RPC `get_live_settings`, owner-only). */
export async function leggiModoOrdini(): Promise<LiveSettings | null> {
    return getLiveSettings();
}
