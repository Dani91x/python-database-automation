// ============================================================================
// composizioneObiettivo.ts — SCOMPOSIZIONE di ciò che erode l'obiettivo di
// giornata: Omega · Safe calcio · Safe tennis · Mike · bot tennis (Scalper /
// Pro / FLB / Swing) · Manuale. SOLO soldi veri (paper su riga separata, mai
// sommato: vedi `provaPaper`).
//
// Riusa `realizzatoGiornata` (`lib/controlRoom.ts`), la stessa funzione
// certificata che calcola già `realizzatoOggi`/`soldiGiornata` in
// `useControlRoom.ts`: qui non si inventa una seconda formula di somma, si
// applica la stessa a gruppi di righe diversi (per bot invece che per sport).
//
// INVARIANTE (falsificata nel test): la somma delle righe di composizione
// (Omega auto + Safe calcio auto + Safe tennis auto + Mike auto + bot tennis
// + manuale) è uguale al realizzato LIVE totale calcolato sulle stesse righe
// tutte insieme. Se questa somma diverge, la composizione mente.
// ============================================================================
import { realizzatoGiornata, type RigaRealizzato } from './controlRoom';
import {
    groupTradesIntoCicli, isErrorRow, isSettled, type PnlTradeLike,
} from './eventGroups';

/**
 * Una riga sorgente, con le STESSE chiavi delle tabelle vere
 * (`omega_trades`/`safe_strategy_trades`/`mike_trades`): status, pnl, mode,
 * sport, origin. `origin` è opzionale: le righe che non lo portano (bot
 * tennis dedicati, che non hanno un percorso manuale) contano come 'auto'.
 *
 * ⚠️ `RigaRealizzato` (`lib/controlRoom.ts`) è FUORI PERIMETRO (di un altro
 * costruttore, F3): questo file NON lo tocca, lo ESTENDE solo a livello di
 * tipo (nessuna modifica al file altrui). `RigaComponente[]` resta
 * assegnabile ovunque serva un `RigaRealizzato[]` (è un suo sovrainsieme
 * strutturale), quindi `realizzatoGiornata` — certificata, invariata — si
 * riusa senza cast.
 */
export interface RigaComponente extends RigaRealizzato {
    origin?: string | null;
    /**
     * 24/09 - di `pnl`, la parte REGOLATA DA BETFAIR (netto di commissione) e
     * la parte STIMATA (calcolo del bot: Betfair non ha ancora regolato).
     * Assenti = riga di prima, trattata tutta come stimata (mai spacciata per
     * reale). Per una riga paper sono irrilevanti: il paper e' sempre calcolo.
     */
    pnlReale?: number | null;
    pnlStimato?: number | null;
}

/** Le due parti di una riga: se la riga non le dichiara, e' tutta stimata. */
function parti(r: RigaComponente): { reale: number | null; stimato: number | null } {
    if (r.pnlReale === undefined && r.pnlStimato === undefined) {
        const v = typeof r.pnl === 'number' && Number.isFinite(r.pnl) ? r.pnl : null;
        return { reale: null, stimato: v };
    }
    return { reale: r.pnlReale ?? null, stimato: r.pnlStimato ?? null };
}

function sommaParti(righe: readonly RigaComponente[]): { reale: number | null; stimato: number | null } {
    let reale: number | null = null;
    let stimato: number | null = null;
    for (const r of righe) {
        if (String(r.mode ?? '').toLowerCase() !== 'live') continue;
        if (!isSettled(r.status) || isErrorRow(r.status)) continue;
        const p = parti(r);
        if (p.reale != null) reale = somma(reale, p.reale);
        if (p.stimato != null) stimato = somma(stimato, p.stimato);
    }
    return { reale, stimato };
}

function eManuale(r: RigaComponente): boolean {
    return String(r.origin ?? '').toLowerCase() === 'manual';
}

function soloAuto(righe: readonly RigaComponente[]): RigaComponente[] {
    return righe.filter((r) => !eManuale(r));
}

function soloSport(righe: readonly RigaComponente[], sport: 'calcio' | 'tennis'): RigaComponente[] {
    return righe.filter((r) => String(r.sport ?? '').toLowerCase() === sport);
}

export interface RigaComposizione {
    chiave: 'omega' | 'safe_calcio' | 'safe_tennis' | 'mike' | 'scalper' | 'bot_tennis' | 'manuale'
        | 'manuale_sito' | 'manuale_app' | 'altro';
    etichetta: string;
    /** P&L netto di oggi, SOLO soldi veri; null = nessuna riga (mostrare —, mai 0) */
    valore: number | null;
    /** 24/09 - di `valore`, la parte STIMATA (Betfair non ha ancora regolato);
     *  null = tutto regolato da Betfair (o nessuna riga) */
    stimato?: number | null;
}

export interface ComposizioneObiettivo {
    righe: RigaComposizione[];
    /** somma di tutte le righe (per l'invariante/il controllo, non necessariamente mostrata) */
    totale: number | null;
    /** in prova (paper), su TUTTE le fonti insieme: mai sommato al totale sopra */
    provaPaper: number | null;
    /** 24/09 - di `totale`, la parte regolata da Betfair e quella stimata
     *  (reale + stimato = totale). Facoltativi per i fixture di prima. */
    reale?: number | null;
    stimato?: number | null;
}

const ETICHETTE: Record<RigaComposizione['chiave'], string> = {
    omega: 'Omega',
    safe_calcio: 'Safe calcio',
    safe_tennis: 'Safe tennis',
    mike: 'Mike',
    // 24/09 - reale di Betfair per bet_id degli ordini della sessione
    scalper: 'Scalper calcio',
    bot_tennis: 'Bot tennis (Scalper · Pro · FLB · Swing)',
    manuale: 'Manuale (app + sito Betfair)',
    // 18/09 (raccordo) — DUE voci NUOVE, dal conto Betfair (`betfair_live_
    // account.manual_pnl_*`/`manual_app_pnl_*`, vedi `lib/manualeSitoBetfair.ts`):
    // diverse dalla riga "manuale" sopra, che e' `origin==='manual'` sulle
    // righe dei BOT (un cash-out/una gamba manuale dentro Omega/Safe/Mike).
    // Queste due sono scommesse FUORI dai bot: sul sito Betfair, e sul
    // terminale manuale (ladder) della nostra app.
    manuale_sito: 'Manuale · sito Betfair',
    manuale_app: 'Manuale · app',
    // 24/09 - ordini regolati sul conto di altri bot (non Omega/Safe/Mike/
    // tennis) e la DIFFERENZA fra il conto Betfair e le righe dei bot lette
    // dalla pagina (righe fuori dalla finestra caricata, P&L reale non ancora
    // scritto sulla riga): e' soldi veri, non si nasconde.
    altro: 'Altro sul conto Betfair',
};

function somma(a: number | null, b: number | null): number | null {
    if (a == null && b == null) return null;
    return Math.round(((a ?? 0) + (b ?? 0)) * 100) / 100;
}

/**
 * Compone la scomposizione dell'obiettivo dalle righe GIÀ lette (nessuna
 * lettura nuova: chi chiama passa gli stessi array di oggi già in memoria).
 *
 * `omega`/`mike`: solo calcio, un percorso solo (Omega e Mike non operano sul
 * tennis). `safe`: calcio + tennis mischiati (li separa qui per `sport`).
 * `tennisBot`: righe SINTETICHE, una per bot dedicato (già nette di
 * commissione, dalla RPC `get_tennis_bot_daily`): vedi
 * `useControlRoom.ts` per come vengono costruite.
 */
export function componiObiettivo(input: {
    omega: readonly RigaComponente[];
    safe: readonly RigaComponente[];
    mike: readonly RigaComponente[];
    tennisBot: readonly RigaComponente[];
    /**
     * 18/09 (raccordo) — le DUE voci manuali fuori dai bot (sito Betfair /
     * app), gia' tradotte in righe sintetiche da `useControlRoom.ts` (una
     * riga per bucket, dallo stesso `lib/manualeSitoBetfair.ts`). Opzionali:
     * finche' il chiamante non le passa (o la migrazione non e' applicata),
     * si comportano come array vuoti — comportamento IDENTICO a ieri.
     */
    manualeSito?: readonly RigaComponente[];
    manualeApp?: readonly RigaComponente[];
    /**
     * 24/09 - "Altro sul conto Betfair": righe sintetiche (altri bot + la
     * differenza fra il conto e le righe dei bot lette). Facoltativo: assente
     * = voce vuota, comportamento di prima.
     */
    altro?: readonly RigaComponente[];
    /**
     * 24/09 - lo SCALPER CALCIO: righe sintetiche (una per partita) col reale
     * di Betfair regolato oggi. Facoltativo: assente = voce vuota, come prima.
     */
    scalper?: readonly RigaComponente[];
}): ComposizioneObiettivo {
    const omegaAuto = soloAuto(input.omega);
    const safeCalcioAuto = soloAuto(soloSport(input.safe, 'calcio'));
    const safeTennisAuto = soloAuto(soloSport(input.safe, 'tennis'));
    const mikeAuto = soloAuto(input.mike);
    const tennisBot = input.tennisBot; // nessun percorso manuale per i 4 bot dedicati
    const manuale = [...input.omega, ...input.safe, ...input.mike].filter(eManuale);
    const manualeSito = input.manualeSito ?? [];
    const manualeApp = input.manualeApp ?? [];
    const altro = input.altro ?? [];
    const scalper = input.scalper ?? [];

    const voce = (chiave: RigaComposizione['chiave'], righeVoce: readonly RigaComponente[]): RigaComposizione => ({
        chiave,
        etichetta: ETICHETTE[chiave],
        valore: realizzatoGiornata(righeVoce).live,
        stimato: sommaParti(righeVoce).stimato,
    });

    const righe: RigaComposizione[] = [
        voce('omega', omegaAuto),
        voce('safe_calcio', safeCalcioAuto),
        voce('safe_tennis', safeTennisAuto),
        voce('mike', mikeAuto),
        voce('scalper', scalper),
        voce('bot_tennis', tennisBot),
        voce('manuale', manuale),
        voce('manuale_sito', manualeSito),
        voce('manuale_app', manualeApp),
        voce('altro', altro),
    ];

    const totale = righe.reduce<number | null>((acc, r) => somma(acc, r.valore), null);

    const tutteLeRighe = [
        ...input.omega, ...input.safe, ...input.mike, ...input.tennisBot,
        ...manualeSito, ...manualeApp, ...altro, ...scalper,
    ];
    const provaPaper = realizzatoGiornata(tutteLeRighe).paper;
    const { reale, stimato } = sommaParti(tutteLeRighe);

    return { righe, totale, provaPaper, reale, stimato };
}

// ============================================================================
// 24/09 - IL P&L REALE DI OGGI DEL CONTO (ordini dell'utente 9 e 10)
//
// Il runner (`Betfair/stream/reconcile_worker.py::_sync_manual_pnl`) legge da
// Betfair i regolati di OGGI (giorno di Roma, `settledDate`) di TUTTO il
// conto e scrive `betfair_live_account.pnl_reale_oggi` (+ lo pubblica sul
// canale 47331, topic `account`): netto (profit - commissione del mercato),
// per voce, e i bet_id contati. Qui lo si LEGGE (mai ricalcolato) e si
// compongono le righe della barra:
//   * reale  = quello del conto, per voce;
//   * stimato = le operazioni gia' chiuse dal bot ma non ancora regolate da
//     Betfair (calcolo del bot), SEMPRE dichiarate.
// Il paper non passa mai di qui: resta il calcolo, sulla sua riga separata.
// ============================================================================

// 25/09 - 'scalper': gli ordini dello specchio dello scalper calcio
// (`source='scalper'`, reconcile_worker._fonte_di). Un runner di prima non la
// scrive: `fontiDichiarate` dice quali voci il conto ha DAVVERO scritto.
export type FonteReale = 'omega' | 'safe_calcio' | 'safe_tennis' | 'mike' | 'bot_tennis'
    | 'manuale_app' | 'manuale_sito' | 'altri_bot' | 'scalper';

export const FONTI_REALI: readonly FonteReale[] = [
    'omega', 'safe_calcio', 'safe_tennis', 'mike', 'bot_tennis',
    'manuale_app', 'manuale_sito', 'altri_bot', 'scalper',
];

export interface PnlRealeOggi {
    /** giorno di Roma YYYY-MM-DD */
    day: string;
    /** netto dell'intero conto, regolato oggi */
    netto: number;
    ordini: number;
    per_fonte: Record<FonteReale, { netto: number; ordini: number }>;
    /** i bet_id gia' contati nel reale: la pagina non li conta anche come stimati */
    bet_ids: string[];
    /** ordini senza commissione di mercato leggibile (non nel reale) */
    senza_commissione: number;
    /** ordini con un ref ma senza una nostra riga (contati nel sito) */
    sospetti_sito: number;
    letto_at: string | null;
    /** 25/09 - le voci che il conto ha scritto davvero (le altre valgono 0
     *  perche' ASSENTI, non perche' zero: es. 'scalper' da un runner di prima) */
    fontiDichiarate?: FonteReale[];
}

function finito(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/**
 * Legge il P&L reale dal valore GREZZO (colonna JSONB o messaggio del
 * canale). `null` = non disponibile: forma sbagliata, o giorno diverso da
 * OGGI (un totale di ieri non e' il totale di oggi, mai mostrato come tale).
 */
export function leggiPnlRealeOggi(grezzo: unknown, oggi: string): PnlRealeOggi | null {
    if (!grezzo || typeof grezzo !== 'object') return null;
    const g = grezzo as Record<string, unknown>;
    if (typeof g.day !== 'string' || g.day !== oggi) return null;
    const netto = finito(g.netto);
    if (netto == null) return null;
    const pf = (g.per_fonte && typeof g.per_fonte === 'object') ? g.per_fonte as Record<string, unknown> : null;
    if (!pf) return null;
    const per_fonte = {} as Record<FonteReale, { netto: number; ordini: number }>;
    for (const f of FONTI_REALI) {
        const v = pf[f] as Record<string, unknown> | undefined;
        per_fonte[f] = { netto: finito(v?.netto) ?? 0, ordini: finito(v?.ordini) ?? 0 };
    }
    const ids = Array.isArray(g.bet_ids) ? g.bet_ids.map((x) => String(x)) : [];
    return {
        day: g.day,
        netto,
        ordini: finito(g.ordini) ?? 0,
        per_fonte,
        bet_ids: ids,
        senza_commissione: finito(g.senza_commissione) ?? 0,
        sospetti_sito: finito(g.sospetti_sito) ?? 0,
        letto_at: typeof g.letto_at === 'string' ? g.letto_at : null,
        fontiDichiarate: FONTI_REALI.filter((f) => pf[f] != null && typeof pf[f] === 'object'),
    };
}

/** Fra la riga del database e il messaggio del canale vince il PIU' RECENTE
 *  (`letto_at`); a pari o illeggibile, quello del canale (arriva per primo). */
export function pnlRealePiuRecente(db: PnlRealeOggi | null, canale: PnlRealeOggi | null): PnlRealeOggi | null {
    if (!db) return canale;
    if (!canale) return db;
    const a = Date.parse(db.letto_at ?? '');
    const b = Date.parse(canale.letto_at ?? '');
    if (Number.isFinite(a) && Number.isFinite(b) && a > b) return db;
    return canale;
}

/** Una riga di trade con il P&L reale (chiavi delle tabelle vere). */
export interface RigaTradeReale extends RigaTradeCiclo {
    pnl_betfair?: number | null;
    pnl_betfair_settled_at?: string | null;
    settled_at?: string | null;
    bet_id?: string | null;
}

/**
 * 24/09 - LE OPERAZIONI DI OGGI PER LA BARRA, con reale e stimato separati.
 *
 * Un ciclo (apertura + chiusure) entra con:
 *   * reale   = somma delle gambe con `pnl_betfair` REGOLATE OGGI da Betfair
 *     (`pnl_betfair_settled_at` nel giorno di Roma): la giornata e' quella
 *     del regolamento, come nel conto;
 *   * stimato = somma delle gambe regolate dal bot (won/lost/void) ma senza
 *     `pnl_betfair`, il cui bet_id NON e' fra quelli gia' contati dal conto
 *     (`regolatiBetfair`), chiuse oggi (`settled_at` del bot, o in mancanza il
 *     piazzamento dell'apertura).
 * PAPER: netto del ciclo CHIUSO, giornata del REGOLAMENTO della sua ultima
 * gamba (26/09, F-2: la stessa regola delle Posizioni chiuse), tutto stimato
 * per definizione.
 */
export function righeGiornataPerCiclo<T extends RigaTradeReale>(
    trades: readonly T[],
    opts: {
        oggi: string;
        /** giorno di Roma di un istante ISO ('' se illeggibile) */
        giornoDi: (iso: string | null | undefined) => string;
        sport?: string;
        regolatiBetfair?: ReadonlySet<string> | null;
    },
): RigaComponente[] {
    const out: RigaComponente[] = [];
    const vere = trades.filter((t) => !isErrorRow(t.status));
    const delGiorno = (iso: string | null | undefined) => !!iso && opts.giornoDi(iso) === opts.oggi;
    for (const c of groupTradesIntoCicli(vere)) {
        const a = c.open;
        const sport = opts.sport ?? a.sport ?? null;
        if (String(a.mode ?? '').toLowerCase() === 'paper') {
            // 26/09 (F-2, e2e fase 3) - anche il PAPER per giorno di REGOLAMENTO,
            // con la regola delle Posizioni chiuse (`posizioniChiuse.ts`): il
            // ciclo entra quando e' CHIUSO (nessuna gamba viva) e la sua ultima
            // gamba regolata (`settled_at`) e' di oggi. Prima contava il giorno
            // di PIAZZAMENTO: il #341 (piazzato il 24, regolato il 26) era nelle
            // Chiuse di oggi e assente dalla barra, «due verita' sullo stesso denaro».
            let viva = false;
            let ultima: string | null = null;
            let ultimaMs = NaN;
            for (const g of [a, ...c.closes]) {
                const s = String(g.status ?? '').toLowerCase();
                if (!isSettled(s)) { if (s !== 'cancelled') viva = true; continue; }
                const ms = g.settled_at ? Date.parse(g.settled_at) : NaN;
                if (Number.isFinite(ms) && !(ms <= ultimaMs)) { ultimaMs = ms; ultima = g.settled_at ?? null; }
            }
            // senza nessun istante di regolamento: il piazzamento, come fanno le Chiuse
            if (viva || !isSettled(a.status) || !delGiorno(ultima ?? a.placed_at)) continue;
            const netto = c.netPnl;
            out.push({
                status: netto == null ? a.status : netto > 0 ? 'won' : netto < 0 ? 'lost' : 'void',
                pnl: netto, mode: a.mode ?? null, sport, origin: a.origin ?? null,
            });
            continue;
        }
        let reale: number | null = null;
        let stimato: number | null = null;
        for (const g of [a, ...c.closes]) {
            const b = finito(g.pnl_betfair);
            if (b != null) {
                if (delGiorno(g.pnl_betfair_settled_at ?? g.settled_at)) reale = somma(reale, b);
                continue;
            }
            if (!isSettled(g.status)) continue;
            if (g.bet_id && opts.regolatiBetfair?.has(String(g.bet_id))) continue;
            if (!delGiorno(g.settled_at ?? a.placed_at)) continue;
            const v = finito(g.pnl);
            if (v != null) stimato = somma(stimato, v);
        }
        if (reale == null && stimato == null) continue;
        const netto = somma(reale, stimato) as number;
        out.push({
            status: netto > 0 ? 'won' : netto < 0 ? 'lost' : 'void',
            pnl: netto, mode: a.mode ?? null, sport, origin: a.origin ?? null,
            pnlReale: reale, pnlStimato: stimato,
        });
    }
    return out;
}

/** Una riga sintetica LIVE (voce del conto): reale e/o stimato dichiarati. */
export function rigaSintetica(
    reale: number | null, stimato: number | null, extra: { sport?: string; origin?: string },
): RigaComponente | null {
    if (reale == null && stimato == null) return null;
    const v = somma(reale, stimato) as number;
    return {
        status: v > 0 ? 'won' : v < 0 ? 'lost' : 'void', pnl: v, mode: 'live',
        sport: extra.sport ?? null, origin: extra.origin ?? 'auto',
        pnlReale: reale, pnlStimato: stimato,
    };
}

/**
 * La DIFFERENZA fra il conto e le righe dei tre bot lette dalla pagina: il
 * reale di Omega+Safe+Mike secondo il conto meno il reale che le righe
 * caricate portano. Diversa da zero quando una riga regolata oggi e' fuori
 * dalla finestra letta o il suo `pnl_betfair` non e' ancora scritto: sono
 * soldi veri, vanno in "Altro sul conto" invece di sparire.
 */
export function differenzaContoRighe(reale: PnlRealeOggi, righeBot: readonly RigaComponente[]): number {
    const conto = reale.per_fonte.omega.netto + reale.per_fonte.safe_calcio.netto
        + reale.per_fonte.safe_tennis.netto + reale.per_fonte.mike.netto;
    let righe = 0;
    for (const r of righeBot) {
        if (String(r.mode ?? '').toLowerCase() !== 'live') continue;
        righe += finito(r.pnlReale) ?? 0;
    }
    return Math.round((conto - righe) * 100) / 100;
}

// ============================================================================
// 23/09 - LE RIGHE DELLA BARRA SONO OPERAZIONI (CICLI), NON GAMBE.
//
// Bug segnalato dall'utente (Safe tennis, live): un cash out e' DUE righe in
// `safe_strategy_trades` - l'apertura (back 3,00 @1,15, won, +0,45) e la gamba
// di chiusura (lay 3,17 @1,08, lost, -0,25, `closes_trade_id` = apertura,
// `origin = 'manual'` perche' il cash out lo chiede la dashboard,
// `Betfair/safe_strategy/bot_service.py:2684`). Contate per GAMBA:
//   - i contatori della barra dicevano '1 vinta + 1 persa' per UN'operazione
//     vinta di +0,20;
//   - la composizione metteva +0,45 sotto 'Safe tennis' e -0,25 sotto
//     'Manuale': la riga del bot mostrava l'apertura INTERA;
//   - la giornata era quella del piazzamento di OGNI gamba, non dell'apertura
//     (una chiusura dopo mezzanotte finiva nel giorno dopo).
// Qui ogni ciclo diventa UNA riga, con il NETTO (apertura + tutte le gambe
// regolate), l'esito dal SEGNO del netto e modalita'/sport/origine/giornata
// dell'APERTURA: la stessa regola di `safe_aggregates_sql` e di
// `trading_daily_history` (esito del ciclo per segno del totale, giornata =
// piazzamento dell'apertura) e di `posizioniChiuse.ts`.
//
// La somma dei netti e' IDENTICA alla somma delle gambe regolate dello stesso
// insieme: il totale non cambia, cambia a chi e a quale giorno si attribuisce.
// Una chiusura ORFANA (apertura fuori dalle righe lette) resta una riga sua,
// con i propri campi: i suoi euro sono veri e non si nascondono.
// ============================================================================

/** La riga sorgente minima: le STESSE chiavi di `omega_trades`/
 *  `safe_strategy_trades`/`mike_trades`. */
export interface RigaTradeCiclo extends PnlTradeLike {
    sport?: string | null;
    origin?: string | null;
}

export function righeRealizzatoPerCiclo<T extends RigaTradeCiclo>(
    trades: readonly T[],
    opts: {
        /** la giornata: si giudica sul piazzamento dell'APERTURA del ciclo */
        delGiorno: (placedAt: string | null | undefined) => boolean;
        /** sport fisso per i bot di un solo sport (Omega, Mike: calcio) */
        sport?: string;
    },
): RigaComponente[] {
    const out: RigaComponente[] = [];
    // `error` = mai andata a mercato: fuori prima di raggruppare
    const vere = trades.filter((t) => !isErrorRow(t.status));
    for (const c of groupTradesIntoCicli(vere)) {
        const a = c.open;
        if (!opts.delGiorno(a.placed_at)) continue;
        const netto = c.netPnl;
        out.push({
            // nessuna gamba regolata: resta lo stato dell'apertura, che non e'
            // regolato e `realizzatoGiornata` salta (mai uno zero inventato)
            status: netto == null ? a.status : netto > 0 ? 'won' : netto < 0 ? 'lost' : 'void',
            pnl: netto,
            mode: a.mode ?? null,
            sport: opts.sport ?? a.sport ?? null,
            origin: a.origin ?? null,
        });
    }
    return out;
}
