// ============================================================================
// replayFasi — le FASI della partita per il registro operazioni e il P&L del
// bot nel replay (08/10, cantiere 10: «il registro mette in fila pre-partita e
// gioco senza separarli: illeggibile»).
//
// Calcio: PRE-PARTITA / 1° TEMPO / INTERVALLO / 2° TEMPO dallo stato IPS della
// registrazione, la stessa fonte della barra e del tabellone
// (`score_timeline` ordinata, eventi discreti KickOff / FirstHalfEnd /
// SecondHalfKickOff; `punteggioAlTs` e `timelineEventMarkers` la leggono uguale).
// Tennis: PRE-PARTITA / SET 1 / SET 2 / ... dalla fase che il Replay Tennis gia'
// calcola (`tennisReplay.faseTennis`: «pre», «Set N», «In gioco»).
//
// Regole (scritte qui perche' il trader le legga):
//  * il calcio d'inizio e' il PRIMO KickOff della registrazione: Betfair
//    ri-emette «KickOff» a ogni riconnessione del feed, sempre DOPO quello vero;
//  * la fine del 1° tempo e' il primo FirstHalfEnd (o HalfTime) dopo il calcio
//    d'inizio; la ripresa e' il primo SecondHalfKickOff dopo il calcio d'inizio
//    (e dopo la fine del 1° tempo, se registrata);
//  * dopo SecondHalfEnd (recupero, regolamento) si resta nel 2° TEMPO;
//  * se la registrazione non porta il calcio d'inizio, l'inizio del gioco e' la
//    prima riga col minuto (il confine di `applicaBot.minutoDiGioco`, quello del
//    «pre-partita» delle etichette); se non porta ne' la fine del 1° tempo ne' la
//    ripresa, il gioco e' una sola fase «IN GIOCO (tempi IPS non registrati)»:
//    il minuto da solo NON distingue il recupero del 1° tempo dalla ripresa
//    (stessa regola di `safeStrategy.secondoTempoCheck`). Mai una fase inventata.
// PURA, nessuna dipendenza dalla pagina.
// ============================================================================

export interface FaseReplay {
    /** chiave stabile ('pre', '1t', 'int', '2t', 'gioco', 'set1', ...) */
    id: string;
    /** il titolo della sezione nel registro */
    nome: string;
    /** la forma breve per la riga «per fase» del riquadro P&L */
    breve: string;
    /** l'ordine delle sezioni (cronologico) */
    ordine: number;
}

export const FASE_PRE: FaseReplay = { id: 'pre', nome: 'PRE-PARTITA', breve: 'pre-partita', ordine: 0 };
export const FASE_1T: FaseReplay = { id: '1t', nome: '1° TEMPO', breve: '1T', ordine: 1 };
export const FASE_INTERVALLO: FaseReplay = { id: 'int', nome: 'INTERVALLO', breve: 'intervallo', ordine: 2 };
export const FASE_2T: FaseReplay = { id: '2t', nome: '2° TEMPO', breve: '2T', ordine: 3 };
/** calcio senza gli stati IPS dei tempi nella registrazione */
export const FASE_GIOCO_CALCIO: FaseReplay = { id: 'gioco', nome: 'IN GIOCO (tempi IPS non registrati)', breve: 'in gioco', ordine: 1 };
/** tennis in gioco senza una riga di punteggio all'istante */
export const FASE_GIOCO_TENNIS: FaseReplay = { id: 'gioco', nome: 'IN GIOCO (set non registrato)', breve: 'in gioco', ordine: 0.5 };

/** Le sezioni che il registro mostra SEMPRE (anche vuote), per sport. PURA. */
export function fasiFisse(sport: 'calcio' | 'tennis'): FaseReplay[] {
    return sport === 'tennis'
        ? [FASE_PRE, faseSet(1), faseSet(2)]
        : [FASE_PRE, FASE_1T, FASE_INTERVALLO, FASE_2T];
}

/** La fase «SET n» del tennis. PURA. */
export function faseSet(n: number): FaseReplay {
    return { id: `set${n}`, nome: `SET ${n}`, breve: `set ${n}`, ordine: n };
}

/** Una riga della cronologia IPS del calcio (le chiavi di `live.ScoreEvent`). */
export interface RigaIps {
    ts: string;
    minute: number | null;
    event_type: string | null;
}

/** Gli istanti di confine fra le fasi del calcio (ms; null = non registrato). */
export interface ConfiniCalcio {
    inizio: number | null;
    finePrimo: number | null;
    ripresa: number | null;
    /** l'inizio viene dal KickOff (true) o dalla prima riga col minuto (false) */
    inizioDaIps: boolean;
}

const norma = (t: string | null | undefined): string => String(t ?? '').toLowerCase().replace(/[^a-z]/g, '');

/** I confini delle fasi del calcio dalla cronologia IPS ORDINATA per ts. PURA. */
export function confiniCalcio(ordinate: ReadonlyArray<RigaIps>): ConfiniCalcio {
    let ko: number | null = null;
    let primoMinuto: number | null = null;
    for (const r of ordinate) {
        const ms = Date.parse(r.ts);
        if (!Number.isFinite(ms)) continue;
        if (ko == null && norma(r.event_type) === 'kickoff') ko = ms;
        if (primoMinuto == null && r.minute != null) primoMinuto = ms;
    }
    const inizio = ko ?? primoMinuto;
    let finePrimo: number | null = null;
    let ripresa: number | null = null;
    if (inizio != null) {
        for (const r of ordinate) {
            const ms = Date.parse(r.ts);
            if (!Number.isFinite(ms) || ms < inizio) continue;
            const t = norma(r.event_type);
            if (finePrimo == null && ripresa == null && (t === 'firsthalfend' || t === 'halftime')) finePrimo = ms;
            if (ripresa == null && t === 'secondhalfkickoff') ripresa = ms;
        }
    }
    return { inizio, finePrimo, ripresa, inizioDaIps: ko != null };
}

/** La fase del calcio all'istante `ms` dai confini. PURA. */
export function faseCalcioDaConfini(c: ConfiniCalcio, ms: number): FaseReplay {
    if (c.inizio == null || ms < c.inizio) return FASE_PRE;
    if (c.ripresa != null && ms >= c.ripresa) return FASE_2T;
    if (c.finePrimo != null && ms >= c.finePrimo) return FASE_INTERVALLO;
    if (c.finePrimo == null && c.ripresa == null) return FASE_GIOCO_CALCIO;
    return FASE_1T;
}

/** La fase del calcio all'istante `ms` dalla cronologia IPS ORDINATA. PURA. */
export function faseCalcioAl(ordinate: ReadonlyArray<RigaIps>, ms: number): FaseReplay {
    return faseCalcioDaConfini(confiniCalcio(ordinate), ms);
}

/** La fase del tennis dall'etichetta di `tennisReplay.faseTennis` («pre»,
 *  «Set N», «In gioco»). PURA. */
export function faseTennisDaEtichetta(etichetta: string): FaseReplay {
    if (etichetta === 'pre') return FASE_PRE;
    const m = /^Set (\d+)$/.exec(etichetta);
    if (m) return faseSet(Number(m[1]));
    return FASE_GIOCO_TENNIS;
}
