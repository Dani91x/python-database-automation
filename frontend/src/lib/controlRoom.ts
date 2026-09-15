// ============================================================================
// controlRoom.ts — LA MATEMATICA DELLA CONTROL ROOM. Pura: niente React,
// niente I/O, niente Supabase. È la parte dove si sbaglia sui soldi, quindi
// sta da sola e ha i suoi test.
//
// PERCHÉ ESISTE. La Control Room è UN FILTRO DI SCELTA davanti a quello che
// Omega, Safe e Mike già fanno. Non calcola segnali, non decide, non inventa
// numeri: prende quelli che i tre bot pubblicano e li mette in un ordine che
// un trader può leggere in due secondi. Ogni volta che qui dentro comparisse
// una formula che esiste già altrove, sarebbe una SECONDA VERITÀ — e due
// implementazioni della stessa cosa divergono sempre.
//
// REGOLE CHE NON SI TOCCANO:
//   1. Il P&L è SEMPRE il netto di commissione scritto dal servizio, preso da
//      `eventGroups.ts` (la stessa matematica delle tre pagine). Il client non
//      ricalcola mai una commissione.
//   2. `null` non è zero. Una partita senza righe regolate vale «—», non
//      «0,00 €» — che vorrebbe dire «ho chiuso in pari».
//   3. Il TARGET PER PARTITA lo calcola il SERVIZIO di Omega (`stats.target_match`).
//      Qui c'è un ripiego, e quando si usa il ripiego la pagina DEVE dirlo:
//      `MissionPanel.tsx:221-226` avverte per iscritto che avere due target
//      locali diversi fu un bug.
//   4. Un'età assente non è zero secondi: è «non lo so», e vale fail-closed.
// ============================================================================
import {
    groupTradesIntoCicli, groupCicliByEvent, isSettled, isErrorRow,
    type PnlTradeLike,
} from './eventGroups';

// ---------------------------------------------------------------- vocabolario

/** Chi ha prodotto una riga. Accanto al `mode`, MAI al posto: una partita
 *  tradata da due bot ha due provenienze e una sola modalità. */
export type Bot = 'omega' | 'safe' | 'mike';

export const BOT_LABEL: Record<Bot, string> = {
    omega: 'Omega',
    safe: 'Safe',
    mike: 'Mike',
};

/** Stato di una partita nella giornata. `chiusa` = fischio passato e non più
 *  in gioco: non è «finita» secondo Betfair (quello lo dice il settlement),
 *  è «non c'è più niente da guardare qui». */
export type StatoPartita = 'live' | 'pre' | 'chiusa';

/** Competizione di ripiego quando il feed non la pubblica. Una stringa sola,
 *  perché due varianti («», null) creerebbero due gruppi distinti per la
 *  stessa cosa. */
export const SENZA_CAMPIONATO = 'Altre competizioni';

// ------------------------------------------------------------------ freschezza

/** Soglie di età del dato, in secondi. Le stesse di `safeBot.feedFreshness`
 *  (5 s / 20 s): non se ne inventano di nuove. */
export const ETA_FRESCA_S = 5;
export const ETA_VECCHIA_S = 20;

export type Freschezza = 'fresca' | 'lenta' | 'vecchia' | 'ignota';

/**
 * Traduce un'età in un giudizio. `null`/`undefined` → `'ignota'`, che NON è
 * `'fresca'`: un'età che non sappiamo vale fail-closed, e chi consuma questo
 * valore deve trattare `'ignota'` come `'vecchia'` per ogni decisione che
 * riguarda soldi.
 */
export function freschezza(etaS: number | null | undefined): Freschezza {
    if (etaS == null || !Number.isFinite(etaS)) return 'ignota';
    if (etaS < 0) return 'ignota';
    if (etaS <= ETA_FRESCA_S) return 'fresca';
    if (etaS <= ETA_VECCHIA_S) return 'lenta';
    return 'vecchia';
}

/** Un dato su cui si può PIAZZARE. Solo `fresca` e `lenta`: mai su un'età
 *  ignota, mai su un dato vecchio. */
export function affidabilePerPiazzare(f: Freschezza): boolean {
    return f === 'fresca' || f === 'lenta';
}

/**
 * Che cosa dire davvero di un prezzo, incrociando la sua età con quella dello
 * SCANNER. È la differenza fra «non lo guardiamo» e «non si muove».
 *
 *   `fresco`  il prezzo è recente: nessun dubbio
 *   `fermo`   il prezzo è vecchio **ma lo scanner è vivo**: il mercato non si
 *             muove, e quel prezzo è ancora quello corrente
 *   `vecchio` il prezzo è vecchio **e anche lo scanner** lo è: non sappiamo
 *             cosa stia facendo il mercato → fail-closed
 *   `ignoto`  manca un'età: vale come `vecchio` per ogni decisione sui soldi
 */
export type StatoQuote = 'fresco' | 'fermo' | 'vecchio' | 'ignoto';

export function statoQuote(
    etaQuoteS: number | null | undefined,
    etaScannerS: number | null | undefined,
): StatoQuote {
    const q = freschezza(etaQuoteS);
    if (q === 'ignota') return 'ignoto';
    if (q === 'fresca' || q === 'lenta') return 'fresco';
    // il prezzo è vecchio: decide lo SCANNER
    const sc = freschezza(etaScannerS);
    if (sc === 'fresca' || sc === 'lenta') return 'fermo';
    return 'vecchio';
}

/** Su un prezzo `fermo` si può ancora operare — è il prezzo corrente, solo che
 *  nessuno lo muove. Su `vecchio` e `ignoto` no. */
export function quoteAffidabili(s: StatoQuote): boolean {
    return s === 'fresco' || s === 'fermo';
}

// ------------------------------------------------------------- stato partita

/** Il minimo che serve per collocare una partita nella giornata. Lo soddisfa
 *  `CalcioScanPayload` così com'è, senza adattatori. */
export interface PartitaFeedLike {
    event_name?: string | null;
    /** calcio */
    home?: string | null;
    away?: string | null;
    /** tennis */
    p1?: string | null;
    p2?: string | null;
    competition?: string | null;
    open_date?: string | null;
    inplay?: boolean;
    minute?: number | null;
    score_home?: number | null;
    score_away?: number | null;
    /** tennis: set e game della partita in corso */
    sets?: { p1: number; p2: number } | null;
    games?: { p1: number; p2: number } | null;
    pressure_index?: number | null;
    /** disponibilita' video/statistiche dichiarata da Betfair (IPS) */
    media?: { video?: boolean | null; viz?: boolean | null } | null;
    /** mercato Match Odds: serve al pulsante che apre il terminale di trading */
    mo_market_id?: string | null;
    /**
     * Istante (ms epoch) in cui lo scanner ha LETTO le quote di questa partita.
     * È la LATENZA VERA del prezzo, e non è la stessa cosa dell'`updated_at`
     * della riga: quello dice «quando è cambiato qualcosa», questo dice
     * «quanto è vecchio il prezzo su cui sto per operare». Due fatti diversi,
     * due etichette diverse — non due verità sulla stessa cosa.
     */
    odds_ts_ms?: number | null;
}

/**
 * `live` se il mercato è in gioco; `pre` se il fischio deve ancora arrivare;
 * `chiusa` altrimenti.
 *
 * NOTA ONESTA SUL LIMITE: una partita rinviata risulta `chiusa` appena passa
 * l'orario previsto, perché il feed non pubblica un rinvio. È un ripiego
 * accettabile — `chiusa` in questa pagina vuol dire «non mostrarla in cima»,
 * non «regolata» — ma va saputo.
 */
export function statoPartita(p: PartitaFeedLike | null | undefined, nowMs: number): StatoPartita {
    if (!p) return 'chiusa';
    if (p.inplay === true) return 'live';
    const ko = koMs(p);
    if (ko != null && ko > nowMs) return 'pre';
    return 'chiusa';
}

/** Istante del fischio d'inizio in ms epoch, o `null` se il feed non lo dice. */
export function koMs(p: PartitaFeedLike | null | undefined): number | null {
    const raw = p?.open_date;
    if (!raw) return null;
    const t = Date.parse(raw);
    return Number.isFinite(t) ? t : null;
}

/** Calcio `'1-0'` · tennis `'1-0 · 4-2'` (set · game). `null` quando il
 *  punteggio non c'è: non si stampa `'0-0'` per una partita di cui non
 *  sappiamo il punteggio. */
export function punteggio(p: PartitaFeedLike | null | undefined): string | null {
    const set = p?.sets;
    if (set && typeof set.p1 === 'number' && typeof set.p2 === 'number') {
        const g = p?.games;
        const gioco = g && typeof g.p1 === 'number' && typeof g.p2 === 'number' ? ` · ${g.p1}-${g.p2}` : '';
        return `${set.p1}-${set.p2}${gioco}`;
    }
    const h = p?.score_home;
    const a = p?.score_away;
    if (typeof h !== 'number' || typeof a !== 'number') return null;
    return `${h}-${a}`;
}

/**
 * LATENZA DELLE QUOTE in secondi. `null` = non lo sappiamo, fail-closed.
 *
 * ⚠️ ATTENZIONE A COSA SIGNIFICA DAVVERO — segnalato dall'utente il 14/09 su una
 * partita che mostrava «2 min». Lo scanner scrive **solo quando qualcosa
 * cambia**: quindi questo numero dice «da quanto quel prezzo non si muove»,
 * NON «da quanto non lo guardiamo». Su un mercato poco scambiato una riga ferma
 * da minuti è **corretta**: quel prezzo È il prezzo corrente.
 *
 * I due casi si distinguono solo incrociando con la vitalità del PRODUTTORE
 * (`statoQuote` qui sotto). Chiamare «vecchio» un prezzo semplicemente fermo è
 * lo stesso errore che ha fatto credere morto un runner che stava benissimo.
 */
export function latenzaQuoteS(p: PartitaFeedLike | null | undefined, nowMs: number): number | null {
    const t = p?.odds_ts_ms;
    if (typeof t !== 'number' || !Number.isFinite(t) || t <= 0) return null;
    return Math.max(0, Math.round((nowMs - t) / 1000));
}

/** Nome leggibile: `event_name`, altrimenti i due contendenti (calcio o
 *  tennis), altrimenti l'id. Non resta mai vuoto. */
export function nomePartita(p: PartitaFeedLike | null | undefined, eventId: string): string {
    const n = p?.event_name?.trim();
    if (n) return n;
    const a = p?.home?.trim() || p?.p1?.trim();
    const b = p?.away?.trim() || p?.p2?.trim();
    if (a && b) return `${a} – ${b}`;
    return eventId;
}

/** Campionato per il raggruppamento, con il ripiego unico. */
export function campionato(p: PartitaFeedLike | null | undefined): string {
    return p?.competition?.trim() || SENZA_CAMPIONATO;
}

/**
 * ARRICCHIMENTO DI UNA PARTITA — quello che il feed dello scanner NON ha.
 *
 * Verificato il 14/09 sui dati veri: il payload di `safe_strategy_scan` porta
 * `mo_market_id` e `open_date`, e basta. Niente campionato, niente loghi,
 * niente `fixture_id`. Quei dati esistono pero' gia' nel software, nella
 * tabella eventi di Omega (`get_omega_events`): 55 campionati su 55, loghi e
 * fixture su 27 su 55.
 *
 * Qui si UNISCONO, non si inventano: quello che manca resta `null` e la
 * scheda lo dichiara spegnendo il pulsante che non puo' funzionare.
 */
export interface ArricchimentoPartita {
    campionato: string | null;
    leagueId: number | null;
    homeTeamId: number | null;
    awayTeamId: number | null;
    /** serve al pulsante «Statistiche»: senza, quel pulsante non ha dove andare */
    fixtureId: number | null;
}

function numeroPositivo(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null;
}

/** Normalizza una riga di `get_omega_events` in un arricchimento. */
export function arricchimentoDa(e: {
    competition_name?: string | null;
    league_id?: number | null;
    home_team_id?: number | null;
    away_team_id?: number | null;
    fixture_id?: number | null;
} | null | undefined): ArricchimentoPartita {
    return {
        campionato: typeof e?.competition_name === 'string' && e.competition_name.trim()
            ? e.competition_name.trim() : null,
        leagueId: numeroPositivo(e?.league_id),
        homeTeamId: numeroPositivo(e?.home_team_id),
        awayTeamId: numeroPositivo(e?.away_team_id),
        fixtureId: numeroPositivo(e?.fixture_id),
    };
}

// --------------------------------------------------------- controllo del gioco

/**
 * CERT. 14/09 — il `pressure_index` è l'unico dato della catena che il
 * provider può non mandare, e la condizione «controllo del gioco» oggi NASCE
 * SPENTA per questo. La distinzione che conta: **assente ≠ zero**. Zero vuol
 * dire «gioco in equilibrio», assente vuol dire «non lo so», e una scheda di
 * segnale non può vantare un filtro che non ha girato.
 *
 * Si usa `typeof === 'number'` e NON `!= null`: un campo `undefined` passerebbe
 * il confronto con `null` e verrebbe contato come DATO PRESENTE, cioè la
 * pagina direbbe al trader l'esatto contrario del vero.
 */
export function haControlloGioco(p: PartitaFeedLike | null | undefined): boolean {
    return typeof p?.pressure_index === 'number' && Number.isFinite(p.pressure_index);
}

/** Copertura del dato di pressione su un insieme di partite: quante lo hanno
 *  e quante no. È il numero che la spia di pagina mostra al trader. */
export function coperturaControllo(
    partite: readonly (PartitaFeedLike | null | undefined)[],
): { conDato: number; senzaDato: number; totale: number; pct: number | null } {
    let conDato = 0;
    for (const p of partite) if (haControlloGioco(p)) conDato += 1;
    const totale = partite.length;
    return {
        conDato,
        senzaDato: totale - conDato,
        totale,
        pct: totale > 0 ? (conDato / totale) * 100 : null,
    };
}

// -------------------------------------------------------------------- target

export type FonteTarget = 'servizio' | 'ripiego';

export interface TargetPartita {
    valore: number;
    fonte: FonteTarget;
}

/** Sotto questa cifra un target non è un obiettivo, è un arrotondamento.
 *  Stesso spirito di `TARGET_MIN_EUR` in `MissionPanel.tsx`. */
export const TARGET_MIN_EUR = 0.5;

/**
 * Il target che UNA partita deve rendere.
 *
 * Ordine di precedenza, e non è negoziabile:
 *   1. `targetServizio` — è `stats.target_match`, lo calcola il servizio di
 *      Omega (`omega_service.py`) e la pagina lo LEGGE.
 *   2. ripiego locale `(obiettivo − realizzato) / partite utili`, **dichiarato
 *      come tale** dal campo `fonte`, così la UI può scriverlo.
 *
 * Ritorna `null` quando non c'è niente da dire: obiettivo già centrato, o
 * nessuna partita su cui spalmarlo. `null` NON è zero.
 */
export function targetPartita(args: {
    targetServizio?: number | null;
    obiettivo?: number | null;
    realizzato?: number | null;
    partiteUtili?: number | null;
}): TargetPartita | null {
    const { targetServizio, obiettivo, realizzato, partiteUtili } = args;

    if (typeof targetServizio === 'number' && Number.isFinite(targetServizio) && targetServizio > 0) {
        return { valore: targetServizio, fonte: 'servizio' };
    }

    if (typeof obiettivo !== 'number' || !Number.isFinite(obiettivo) || obiettivo <= 0) return null;
    if (typeof partiteUtili !== 'number' || !Number.isFinite(partiteUtili) || partiteUtili <= 0) return null;

    const fatto = typeof realizzato === 'number' && Number.isFinite(realizzato) ? realizzato : 0;
    const resta = obiettivo - fatto;
    if (resta <= 0) return null;                       // obiettivo centrato: nessun target da spalmare

    const quota = resta / partiteUtili;
    return { valore: Math.max(TARGET_MIN_EUR, quota), fonte: 'ripiego' };
}

/**
 * Avanzamento di una partita verso il suo target, in percentuale 0-100.
 * `null` quando manca il target o non c'è ancora un risultato — e una partita
 * IN PERDITA vale 0, non un numero negativo: la barra non va all'indietro, il
 * segno lo dice il P&L accanto.
 */
export function avanzamentoPartita(netPnl: number | null | undefined, target: number | null | undefined): number | null {
    if (typeof netPnl !== 'number' || !Number.isFinite(netPnl)) return null;
    if (typeof target !== 'number' || !Number.isFinite(target) || target <= 0) return null;
    if (netPnl <= 0) return 0;
    return Math.min(100, (netPnl / target) * 100);
}

// ------------------------------------------------- P&L per partita, tre bot

/** Una riga di trade con la sua provenienza. `MikeTrade`, `SafeTrade` e
 *  `OmegaTrade` soddisfano già `PnlTradeLike`: non serve nessun adattatore,
 *  si aggiunge solo l'etichetta di chi l'ha prodotta. */
export type TradeConBot<T extends PnlTradeLike = PnlTradeLike> = T & { __bot: Bot };

export function marca<T extends PnlTradeLike>(trades: readonly T[], bot: Bot): TradeConBot<T>[] {
    return trades.map((t) => ({ ...t, __bot: bot }));
}

/** I soldi di UNA modalità su una partita. */
export interface SoldiModo {
    /** netto di commissione delle righe REGOLATE; `null` = nessun risultato ancora */
    netPnl: number | null;
    /** responsabilità impegnata dalle righe ancora aperte */
    liability: number;
    /** capitale investito */
    investito: number;
    /** c'è almeno una posizione ancora a mercato */
    aperta: boolean;
}

const SOLDI_VUOTI: SoldiModo = { netPnl: null, liability: 0, investito: 0, aperta: false };

/**
 * I soldi di una partita, **separati per modalità e mai sommati**.
 *
 * Qui c'era un solo `netPnl` che sommava tutto. Sul tennis esistono righe
 * paper e righe live sulla STESSA partita: quel numero era la media di due
 * mondi diversi, e la scheda lo mostrava come se fosse un risultato.
 * Non esiste piu' un campo che li unisca: chi legge deve SCEGLIERE, e il
 * compilatore lo costringe.
 */
export interface PartitaSoldi {
    /** soldi veri */
    live: SoldiModo;
    /** simulazione */
    paper: SoldiModo;
    /** quali modalità hanno operato qui (per sapere che cosa mostrare) */
    modi: Modo[];
    /** quali bot hanno operato su questa partita, in ordine fisso */
    bots: Bot[];
}

export type Modo = 'live' | 'paper';

/** La modalità di una riga. Sconosciuta = **paper**: ai soldi veri si arriva
 *  solo dichiarandolo, mai per un campo vuoto (fail-closed). */
export function modoDi(t: { mode?: string | null }): Modo {
    return String(t?.mode ?? '').toLowerCase() === 'live' ? 'live' : 'paper';
}

const ORDINE_BOT: Bot[] = ['omega', 'safe', 'mike'];

/**
 * Soldi per partita, sommando i tre bot. Usa `eventGroups` così com'è — la
 * stessa matematica gamba→ciclo→partita delle tre pagine — e ci aggiunge solo
 * l'elenco dei bot coinvolti.
 */
export function soldiPerPartita(trades: readonly TradeConBot[]): Map<string, PartitaSoldi> {
    // DUE raggruppamenti sulle stesse righe, uno per modalità. Si riusa la
    // stessa funzione di aggregazione (già collaudata) invece di insegnarle
    // una dimensione in più: un ciclo apertura→chiusura vive dentro UNA
    // modalità, quindi dividere prima di raggruppare è corretto e non spezza
    // nessun ciclo.
    const perModo = (m: Modo) => {
        const righe = trades.filter((t) => modoDi(t) === m);
        const mappa = new Map<string, { soldi: SoldiModo; bots: Set<Bot> }>();
        for (const ev of groupCicliByEvent(groupTradesIntoCicli(righe))) {
            const visti = new Set<Bot>();
            for (const c of ev.cicli) {
                visti.add(c.open.__bot);
                for (const ch of c.closes) visti.add(ch.__bot);
            }
            mappa.set(String(ev.event_id), {
                soldi: {
                    netPnl: ev.netPnl, liability: ev.liability,
                    investito: ev.investito, aperta: ev.apertaAncora,
                },
                bots: visti,
            });
        }
        return mappa;
    };

    const vivi = perModo('live');
    const finti = perModo('paper');
    const out = new Map<string, PartitaSoldi>();
    for (const id of new Set([...vivi.keys(), ...finti.keys()])) {
        const l = vivi.get(id);
        const p = finti.get(id);
        const bots = new Set<Bot>([...(l?.bots ?? []), ...(p?.bots ?? [])]);
        const modi: Modo[] = [];
        if (l) modi.push('live');
        if (p) modi.push('paper');
        out.set(id, {
            live: l?.soldi ?? SOLDI_VUOTI,
            paper: p?.soldi ?? SOLDI_VUOTI,
            modi,
            bots: ORDINE_BOT.filter((b) => bots.has(b)),
        });
    }
    return out;
}

// ------------------------------------------------------- la giornata, in ordine

export type Sport = 'calcio' | 'tennis';

export interface PartitaGiornata {
    event_id: string;
    sport: Sport;
    nome: string;
    campionato: string;
    koMs: number | null;
    stato: StatoPartita;
    minuto: number | null;
    punteggio: string | null;
    /** il dato di pressione c'è su questa partita? (assente ≠ zero) */
    controlloDisponibile: boolean;
    etaFeedS: number | null;
    freschezza: Freschezza;
    /** da quanto quel prezzo non si muove (≠ «da quanto non lo guardiamo») */
    latenzaQuoteS: number | null;
    freschezzaQuote: Freschezza;
    /** il giudizio vero, incrociato con la vitalità dello scanner */
    statoQuote: StatoQuote;
    /** video/statistiche Betfair: il pulsante esiste già, qui passa solo il dato */
    media: { video: boolean | null; viz: boolean | null } | null;
    /** loghi e `fixture_id` dalla tabella eventi di Omega; `null` = non
     *  arricchita, e la scheda lo dichiara invece di mostrare pulsanti morti */
    extra: ArricchimentoPartita | null;
    /** Match Odds, per aprire il terminale di trading su QUESTA partita */
    marketId: string | null;
    soldi: PartitaSoldi | null;
    target: TargetPartita | null;
    avanzamento: number | null;
}

export interface GruppoCampionato {
    campionato: string;
    /** il fischio più vicino del gruppo: è l'ordine in cui i campionati si leggono */
    primoKoMs: number | null;
    partite: PartitaGiornata[];
}

/** `live` prima di `pre`, `pre` prima di `chiusa`. Dentro lo stesso stato
 *  comanda l'orologio. */
const PESO_STATO: Record<StatoPartita, number> = { live: 0, pre: 1, chiusa: 2 };

/**
 * Costruisce la giornata: partite raggruppate per campionato, i campionati in
 * ordine di primo fischio, e dentro ogni campionato **ordine cronologico**.
 *
 * Le partite senza fischio noto vanno in fondo al loro gruppo: non si inventa
 * un orario per farle stare in ordine.
 */
export function costruisciGiornata(args: {
    righe: readonly { event_id: string; sport?: Sport; payload: PartitaFeedLike | null; updated_at?: string | null }[];
    soldi: Map<string, PartitaSoldi>;
    nowMs: number;
    obiettivo?: number | null;
    realizzato?: number | null;
    targetServizio?: number | null;
    /** età dello SCANNER: serve a distinguere «prezzo fermo» da «prezzo vecchio» */
    etaScannerS?: number | null;
    /** campionato/loghi/fixture per event_id, dalla tabella eventi di Omega.
     *  Facoltativo: senza, la pagina funziona e lo dichiara. */
    arricchimento?: Map<string, ArricchimentoPartita>;
}): GruppoCampionato[] {
    const { righe, soldi, nowMs, obiettivo, realizzato, targetServizio, etaScannerS } = args;
    const extra = args.arricchimento ?? new Map<string, ArricchimentoPartita>();

    // Le partite UTILI per spalmare l'obiettivo sono quelle su cui si può
    // ancora operare: le chiuse non possono più rendere niente, e contarle
    // abbasserebbe il target di tutte le altre mentendo.
    const utili = righe.filter((r) => statoPartita(r.payload, nowMs) !== 'chiusa').length;
    const target = targetPartita({ targetServizio, obiettivo, realizzato, partiteUtili: utili });

    const partite: PartitaGiornata[] = righe.map((r) => {
        const p = r.payload;
        const s = soldi.get(String(r.event_id)) ?? null;
        const eta = etaSecondi(r.updated_at, nowMs);
        const lat = latenzaQuoteS(p, nowMs);
        return {
            event_id: String(r.event_id),
            sport: r.sport ?? 'calcio',
            nome: nomePartita(p, String(r.event_id)),
            // il nome del campionato lo sa Omega, non il feed: si preferisce
            // quello vero e si ripiega sul feed solo se manca.
            campionato: extra.get(String(r.event_id))?.campionato ?? campionato(p),
            extra: extra.get(String(r.event_id)) ?? null,
            koMs: koMs(p),
            stato: statoPartita(p, nowMs),
            minuto: typeof p?.minute === 'number' ? p.minute : null,
            punteggio: punteggio(p),
            controlloDisponibile: haControlloGioco(p),
            etaFeedS: eta,
            freschezza: freschezza(eta),
            latenzaQuoteS: lat,
            freschezzaQuote: freschezza(lat),
            statoQuote: statoQuote(lat, etaScannerS ?? null),
            media: p?.media ? { video: p.media.video ?? null, viz: p.media.viz ?? null } : null,
            marketId: p?.mo_market_id ?? null,
            soldi: s,
            target,
            // il target di giornata si insegue con i SOLDI VERI: una vincita
            // simulata non deve riempire la barra di un pixel.
            avanzamento: avanzamentoPartita(s?.live.netPnl ?? null, target?.valore ?? null),
        };
    });

    const gruppi = new Map<string, PartitaGiornata[]>();
    for (const m of partite) {
        const arr = gruppi.get(m.campionato);
        if (arr) arr.push(m);
        else gruppi.set(m.campionato, [m]);
    }

    const out: GruppoCampionato[] = [];
    for (const [nome, elenco] of gruppi) {
        elenco.sort(confrontaPartite);
        out.push({ campionato: nome, primoKoMs: primoKo(elenco), partite: elenco });
    }

    out.sort((a, b) => {
        if (a.primoKoMs == null && b.primoKoMs == null) return a.campionato.localeCompare(b.campionato, 'it');
        if (a.primoKoMs == null) return 1;
        if (b.primoKoMs == null) return -1;
        if (a.primoKoMs !== b.primoKoMs) return a.primoKoMs - b.primoKoMs;
        return a.campionato.localeCompare(b.campionato, 'it');
    });
    return out;
}

function confrontaPartite(a: PartitaGiornata, b: PartitaGiornata): number {
    const ps = PESO_STATO[a.stato] - PESO_STATO[b.stato];
    if (ps !== 0) return ps;
    if (a.koMs == null && b.koMs == null) return a.nome.localeCompare(b.nome, 'it');
    if (a.koMs == null) return 1;                       // senza orario: in fondo
    if (b.koMs == null) return -1;
    if (a.koMs !== b.koMs) return a.koMs - b.koMs;
    return a.nome.localeCompare(b.nome, 'it');
}

function primoKo(elenco: readonly PartitaGiornata[]): number | null {
    let min: number | null = null;
    for (const m of elenco) {
        if (m.koMs == null) continue;
        if (min == null || m.koMs < min) min = m.koMs;
    }
    return min;
}

/** Età in secondi di un istante ISO, o `null` se l'istante non c'è o non si
 *  legge. Non si restituisce mai `0` per «non lo so». */
export function etaSecondi(iso: string | null | undefined, nowMs: number): number | null {
    if (!iso) return null;
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return null;
    return Math.max(0, Math.round((nowMs - t) / 1000));
}

// ------------------------------------------- il realizzato, diviso come serve

export type Sport2 = 'calcio' | 'tennis' | 'ignoto';

/** Una riga di trade con quello che serve per dividere il realizzato. */
export interface RigaRealizzato {
    status: string;
    pnl?: number | null;
    mode?: string | null;
    sport?: string | null;
}

export interface Realizzato {
    /** somma dei NETTI delle righe REGOLATE; null = nessun risultato ancora */
    totale: number | null;
    live: number | null;
    paper: number | null;
    perSport: Record<Sport2, number | null>;
    /** quante righe regolate hanno prodotto questi numeri */
    righe: number;
    /**
     * Quante hanno chiuso in positivo e quante in negativo.
     *
     * ⚠️ REVIEW 15/09 — nella barra di giornata il P&L veniva dalle righe dei
     * TRE bot e i contatori «operazioni / V / P» da `get_safe_daily`, che
     * legge la sola tabella di Safe. Le operazioni di Omega e Mike non erano
     * assenti: valevano ZERO dentro un totale presentato come quello della
     * giornata. Contando qui, numeri e contatori nascono dalle stesse righe e
     * non possono più divergere.
     *
     * Una riga a P&L esattamente zero non è né vinta né persa.
     */
    vinte: number;
    perse: number;
}

function somma(a: number | null, b: number): number { return (a ?? 0) + b; }

/**
 * IL REALIZZATO DELLA GIORNATA, diviso per modalità e per sport.
 *
 * Due regole, e sono la stessa cosa detta due volte:
 *  · **soldi veri e simulati non si sommano MAI** in un numero solo. Un totale
 *    che li mescola è la bugia più costosa che una pagina di trading possa dire;
 *  · **si divide anche per sport**, perché oggi il tennis è in live e il calcio
 *    in paper: senza la divisione «quanto ho guadagnato col tennis» non ha
 *    risposta.
 *
 * Una riga NON regolata non vale zero: non entra. `null` significa «nessun
 * risultato ancora», che è diverso da «ho chiuso in pari».
 */
export function realizzatoGiornata(righe: readonly RigaRealizzato[]): Realizzato {
    const out: Realizzato = {
        totale: null, live: null, paper: null,
        perSport: { calcio: null, tennis: null, ignoto: null },
        righe: 0, vinte: 0, perse: 0,
    };
    for (const r of righe) {
        if (!isSettled(r.status) || isErrorRow(r.status)) continue;
        const v = r.pnl;
        if (typeof v !== 'number' || !Number.isFinite(v)) continue;
        out.righe += 1;
        if (v > 0) out.vinte += 1; else if (v < 0) out.perse += 1;
        out.totale = somma(out.totale, v);
        const m = String(r.mode ?? '').toLowerCase();
        if (m === 'live') out.live = somma(out.live, v);
        else if (m === 'paper') out.paper = somma(out.paper, v);
        const sp = String(r.sport ?? '').toLowerCase();
        const chiave: Sport2 = sp === 'tennis' ? 'tennis' : sp === 'calcio' ? 'calcio' : 'ignoto';
        out.perSport[chiave] = somma(out.perSport[chiave], v);
    }
    // arrotondamento al centesimo una volta sola, alla fine
    const r2 = (x: number | null) => (x == null ? null : Math.round(x * 100) / 100);
    out.totale = r2(out.totale); out.live = r2(out.live); out.paper = r2(out.paper);
    for (const k of Object.keys(out.perSport) as Sport2[]) out.perSport[k] = r2(out.perSport[k]);
    return out;
}

// ------------------------------------------------------------ totali di giornata

export interface TotaliGiornata {
    /**
     * I soldi sono stati letti?
     *
     * ⚠️ REVIEW 15/09 — `liability` e i conteggi partivano da 0 e non c'era
     * modo, guardando il risultato, di distinguere «nessuna posizione aperta»
     * da «non ho letto i trade». La testata stampava «Esposizione 0,00 €» e
     * «0 / 0» anche durante il caricamento o dopo una lettura fallita: sul
     * numero più pericoloso della pagina, un'assenza travestita da sicurezza.
     *
     * Quando è `false` la pagina scrive «—», non uno zero.
     */
    letti: boolean;
    partite: number;
    /** partite IN GIOCO adesso (nome storico: non è la modalità) */
    live: number;
    pre: number;
    /** partite con almeno una posizione aperta, in QUALSIASI modalità */
    conPosizione: number;
    /** partite con una posizione aperta con SOLDI VERI */
    conPosizioneLive: number;

    /** responsabilità impegnata adesso con SOLDI VERI */
    liability: number;
    /** responsabilità impegnata adesso in PROVA. Mai sommata alla precedente. */
    liabilityPaper: number;
    /** netto delle righe regolate con SOLDI VERI; `null` = nessun risultato */
    netPnl: number | null;
    /** netto delle righe regolate in PROVA. Mai sommato al precedente. */
    netPnlPaper: number | null;
}

/**
 * I totali della colonna partite, **per modalità**.
 *
 * `liability` e `netPnl` sono i SOLDI VERI. Prima erano un unico numero che
 * sommava paper e live: l'esposizione dichiarata comprendeva denaro che non
 * esiste, e su un banco reale è il numero più pericoloso della pagina.
 */
export function totaliGiornata(
    gruppi: readonly GruppoCampionato[],
    /** i trade dei tre bot sono stati letti almeno una volta? */
    letti = true,
): TotaliGiornata {
    let partite = 0, live = 0, pre = 0, conPosizione = 0, conPosizioneLive = 0;
    let liability = 0, liabilityPaper = 0;
    let net: number | null = null;
    let netPaper: number | null = null;

    for (const g of gruppi) {
        for (const m of g.partite) {
            partite += 1;
            if (m.stato === 'live') live += 1;
            else if (m.stato === 'pre') pre += 1;
            const s = m.soldi;
            if (!s) continue;
            if (s.live.aperta || s.paper.aperta) conPosizione += 1;
            if (s.live.aperta) conPosizioneLive += 1;
            liability += s.live.liability;
            liabilityPaper += s.paper.liability;
            if (s.live.netPnl != null) net = (net ?? 0) + s.live.netPnl;
            if (s.paper.netPnl != null) netPaper = (netPaper ?? 0) + s.paper.netPnl;
        }
    }
    const r2 = (x: number | null) => (x == null ? null : Math.round(x * 100) / 100);
    return {
        letti,
        partite, live, pre, conPosizione, conPosizioneLive,
        liability: Math.round(liability * 100) / 100,
        liabilityPaper: Math.round(liabilityPaper * 100) / 100,
        netPnl: r2(net), netPnlPaper: r2(netPaper),
    };
}
