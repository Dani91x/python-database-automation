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
import { groupTradesIntoCicli, groupCicliByEvent, type PnlTradeLike, type EventGroup } from './eventGroups';

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

export interface PartitaSoldi {
    /** netto di commissione delle righe REGOLATE; `null` = nessun risultato ancora */
    netPnl: number | null;
    /** responsabilità impegnata dalle righe ancora aperte */
    liability: number;
    /** capitale investito */
    investito: number;
    /** c'è almeno una posizione ancora a mercato */
    aperta: boolean;
    /** quali bot hanno operato su questa partita, in ordine fisso */
    bots: Bot[];
}

const ORDINE_BOT: Bot[] = ['omega', 'safe', 'mike'];

/**
 * Soldi per partita, sommando i tre bot. Usa `eventGroups` così com'è — la
 * stessa matematica gamba→ciclo→partita delle tre pagine — e ci aggiunge solo
 * l'elenco dei bot coinvolti.
 */
export function soldiPerPartita(trades: readonly TradeConBot[]): Map<string, PartitaSoldi> {
    const cicli = groupTradesIntoCicli(trades);
    const eventi: EventGroup<TradeConBot>[] = groupCicliByEvent(cicli);

    const out = new Map<string, PartitaSoldi>();
    for (const ev of eventi) {
        const visti = new Set<Bot>();
        for (const c of ev.cicli) {
            visti.add(c.open.__bot);
            for (const ch of c.closes) visti.add(ch.__bot);
        }
        out.set(String(ev.event_id), {
            netPnl: ev.netPnl,
            liability: ev.liability,
            investito: ev.investito,
            aperta: ev.apertaAncora,
            bots: ORDINE_BOT.filter((b) => visti.has(b)),
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
}): GruppoCampionato[] {
    const { righe, soldi, nowMs, obiettivo, realizzato, targetServizio, etaScannerS } = args;

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
            campionato: campionato(p),
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
            soldi: s,
            target,
            avanzamento: avanzamentoPartita(s?.netPnl ?? null, target?.valore ?? null),
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

// ------------------------------------------------------------ totali di giornata

export interface TotaliGiornata {
    partite: number;
    live: number;
    pre: number;
    conPosizione: number;
    /** responsabilità impegnata adesso su tutte le partite */
    liability: number;
    /** netto delle righe regolate; `null` se non c'è ancora nessun risultato */
    netPnl: number | null;
}

export function totaliGiornata(gruppi: readonly GruppoCampionato[]): TotaliGiornata {
    let partite = 0, live = 0, pre = 0, conPosizione = 0, liability = 0;
    let net: number | null = null;

    for (const g of gruppi) {
        for (const m of g.partite) {
            partite += 1;
            if (m.stato === 'live') live += 1;
            else if (m.stato === 'pre') pre += 1;
            const s = m.soldi;
            if (!s) continue;
            if (s.aperta) conPosizione += 1;
            liability += s.liability;
            if (s.netPnl != null) net = (net ?? 0) + s.netPnl;
        }
    }
    return { partite, live, pre, conPosizione, liability, netPnl: net };
}
