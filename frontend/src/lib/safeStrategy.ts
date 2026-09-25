// ============================================================================
// safeStrategy.ts — MOTORE PURO della sezione "SAFE STRATEGY".
//
// Quattro strategie sulla stessa idea: sfruttare lo spostamento delle quote nel
// 2° tempo/set quando chi è avanti mantiene il controllo. Questo modulo NON
// piazza ordini e NON fa I/O: valuta condizioni OGGETTIVE (minuto, punteggio,
// range quote) su snapshot già disponibili nel data-layer esistente
// (lib/live.ts per il calcio, lib/tennis.ts per il tennis) e produce segnali
// informativi. L'ingresso a mercato è SEMPRE manuale.
//
// Il "controllo del gioco" (condizione soggettiva) NON è codificato qui: resta
// giudizio umano — le condizioni non verificabili via dati sono esposte come
// `ok: null`, mai inventate.
//
// Regola del repo: logica money-critical = funzioni pure + test co-locati
// (safeStrategy.test.ts). Il provider React (components/safestrategy/) fa solo
// plumbing di sottoscrizioni e chiama queste funzioni.
// ============================================================================
import type { LiveNowRow, LiveNowSelection } from '@/lib/live';
import type { BetfairOdds } from '@/lib/betfair';
import type { TennisLiveNowRow, TennisScoreState } from '@/lib/tennis';
import type { CalcioScanPayload, ScanOddsPair, TennisScanPayload } from '@/lib/safeStrategyScan';
import { fmtMoney, fmtOdds as fmtOddsFmt } from '@/lib/format';
import {
    MOTIVO_FINALE_NOME, MOTIVO_FINALE_ROUND, MOTIVO_SQUADRA_FEMMINILE, isRoundFinale, motivoVeto,
    nomeIndicaFinale, squadraFemminile, voceVietata,
} from '@/lib/vetoCampionati';

// ---------------------------------------------------------------- tipi base
export type Sport = 'calcio' | 'tennis';
export type VariantId = 'base' | 'esatto' | 'punta' | 'tennis';
export type SideId = 'home' | 'away';

export interface OddsPair {
    back: number | null;
    lay: number | null;
    /** EUR abbinabili SUBITO al miglior prezzo back/lay (best offers dello
     *  stream); assenti quando la fonte non li espone (snapshot legacy) */
    backSize?: number | null;
    laySize?: number | null;
}

/** Esito di una singola condizione. ok=null → dato non disponibile (mai inventato). */
export interface ConditionCheck {
    id: string;
    label: string;
    /** valore osservato, formattato per la UI (es. "58′", "1.27", "n/d") */
    value: string;
    ok: boolean | null;
}

export type VariantState =
    | 'signal' // tutte le condizioni verificate e vere
    | 'nd'     // nessuna condizione falsa ma almeno un dato mancante
    | 'no';    // almeno una condizione falsa

export interface VariantEvaluation {
    variant: VariantId;
    /** per la variante "esatto" (una valutazione per lato bancabile) */
    subId?: SideId;
    state: VariantState;
    checks: ConditionCheck[];
    /** azione suggerita quando state==='signal' (es. "BANCA Empoli") */
    headline: string | null;
    side: 'BACK' | 'LAY' | null;
    /** selezione su cui operare (nome squadra/giocatore o "Altro risultato …") */
    selection: string | null;
    /** quota live della selezione da operare (se disponibile) */
    entryOdds: number | null;
    /** EUR abbinabili SUBITO a entryOdds (size al miglior prezzo sul lato da
     *  operare: lay → denaro in attesa da bancare, back → denaro da puntare);
     *  null = la fonte non espone le size */
    entrySize: number | null;
}

// ---------------------------------------------------------------- parametri
// Default operativi delle quattro strategie. Tutti modificabili dalla UI e
// persistiti in localStorage (merge difensivo in mergeParams).
export interface BaseParams {
    /** SOGLIA minuto: la strategia è attivabile DAL minuto indicato IN POI
     *  (minuto effettivo ≥ soglia). Nessun tetto: la finestra la chiudono i
     *  range quote, non il cronometro (regola utente 09/09) */
    minuteMin: number;
    /** punteggi ammessi, GOL FAVORITA per primi (es. "1-0","2-1","2-0") */
    scores: string[];
    favPreMin: number;
    favPreMax: number;
    dogPreMin: number;
    dogPreMax: number;
    /** ORDINE DELL'UTENTE 25/09 (Q1): QUOTA DI BANCA della squadra che PERDE
     *  per l'ingresso, 20–34 estremi inclusi (corso, «Entrata a mercato» @93.0:
     *  «vanno dal 20 al 34, a dir tanto»). Sostituisce la «Lettura A»
     *  (favLiveMin/favLiveMax, back live della favorita 1,20–1,34): tolta. */
    dogLayMin: number;
    dogLayMax: number;
    /** Q4 (25/09): veto dei campionati del corso (lib/vetoCampionati.ts) */
    vetoCampionati: boolean;
    /** anti-blip: il punteggio corrente deve essere osservato stabile da ≥N secondi
     *  (l'in-play service Betfair occasionalmente manda punteggi errati) */
    scoreConfirmSec: number;
    /** CERT. 14/09 - "controllo del gioco": attiva la condizione della specifica.
     *  Default OFF: e' una condizione che puo' BLOCCARE gli ingressi quando il
     *  dato non arriva, e si accende solo dopo aver misurato la copertura. */
    requireControl: boolean;
    /** soglia dell'indice di pressione (corner + cartellini), orientato sulla
     *  squadra guardata: >= soglia = comanda il gioco. */
    controlMin: number;
}
export interface EsattoParams {
    /** soglia "dal minuto in poi" (vedi BaseParams.minuteMin) */
    minuteMin: number;
    /** punteggi ammessi, in QUALSIASI orientamento (es. "1-0" vale anche 0-1) */
    scores: string[];
    /** la squadra bancata deve aver segnato al massimo N gol */
    maxGoalsLaySide: number;
    /** quota "Altro risultato Casa/Ospite" (Correct Score) per l'ingresso */
    entryMin: number;
    entryMax: number;
    /** anti-blip: punteggio osservato stabile da ≥N secondi (l'ingresso scatta
     *  appena superata la soglia minuto: un punteggio IPS errato per pochi
     *  secondi pesa di più) */
    scoreConfirmSec: number;
    /** CERT. 14/09 - "controllo del gioco": attiva la condizione della specifica.
     *  Default OFF: e' una condizione che puo' BLOCCARE gli ingressi quando il
     *  dato non arriva, e si accende solo dopo aver misurato la copertura. */
    requireControl: boolean;
    /** soglia dell'indice di pressione (corner + cartellini), orientato sulla
     *  squadra guardata: >= soglia = comanda il gioco. */
    controlMin: number;
    /** ORDINE DELL'UTENTE 16/09 — SPEC §2 riga «Selezione aggiuntiva»:
     *  «scontri diretti senza troppi 2-2/3-3, difesa avversaria solida».
     *  Default OFF come `requireControl`: il dato storico non ha copertura
     *  misurata e, acceso senza dato, BLOCCA gli ingressi (n/d). */
    requireSelection: boolean;
    /** D5 (utente 25/09): scontri diretti VERI dal DB (la lista «STORICO H2H»
     *  della Dashboard). Quota massima di scontri diretti con 4 o più gol
     *  (corso: «troppi 2-2, 3-3, 4-2, 4-1»). 0,58 = il DOPPIO della norma
     *  (29,22% delle 47.460 partite dell'atlante). Sostituisce
     *  `h2hBigDrawRateMax` (solo 2-2/3-3), deprecata e ignorata. */
    h2hManyGoalsRateMax: number;
    /** D5: sotto questo numero di scontri diretti il conto non blocca. */
    h2hMinMeetings: number;
    /** «difesa AVVERSARIA solida»: gol subiti per partita (ultime 5) dalla
     *  squadra che deve fermare la bancata. 1,37 = metà dei 2,7403 gol per
     *  partita dell'atlante, cioè «non peggio della media». */
    oppConcededMax: number;
    /** Q4 (25/09): veto dei campionati del corso, come la BASE */
    vetoCampionati: boolean;
}
export interface PuntaParams {
    /** soglia "dal minuto in poi" (vedi BaseParams.minuteMin) */
    minuteMin: number;
    /** punteggi ammessi, GOL SQUADRA IN VANTAGGIO per primi (margine 2 gol) */
    scores: string[];
    /** quota live (back) della squadra in vantaggio */
    entryMin: number;
    entryMax: number;
    /** minuti di assestamento dopo l'ultimo gol osservato */
    minMinutesAfterGoal: number;
    /** CERT. 14/09 - "controllo del gioco": attiva la condizione della specifica.
     *  Default OFF: e' una condizione che puo' BLOCCARE gli ingressi quando il
     *  dato non arriva, e si accende solo dopo aver misurato la copertura. */
    requireControl: boolean;
    /** soglia dell'indice di pressione (corner + cartellini), orientato sulla
     *  squadra guardata: >= soglia = comanda il gioco. */
    controlMin: number;
    /** Q4 (25/09): veto dei campionati del corso, come la BASE */
    vetoCampionati: boolean;
}
export interface TennisParams {
    /** vantaggio minimo in set (default: 1 set vinto) */
    setsLeadMin: number;
    /** vantaggio minimo in game nel set corrente (default: 2) */
    gamesLeadMin: number;
    /** range quota BACK del LEADER per l'ingresso (fix certificazione: il lay
     *  del perdente sta matematicamente a ~15-40 quando il leader quota
     *  1.03-1.10 — un range sul lay del perdente era impossibile; la quota
     *  d'ingresso della situazione è quella del leader, il lay del perdente
     *  resta un'alternativa operativa al suo prezzo reale) */
    backMin: number;
    backMax: number;
    /** esclude i doppi (nomi con "/") */
    excludeDoubles: boolean;
    /**
     * Esclude gli Slam MASCHILI (al meglio dei 5 set). Il manuale: «evita gli
     * Slam maschili, più rischio fisico» — e il rischio fisico (ritiro) è
     * l'unico modo di perdere TUTTO lo stake in questa strategia.
     * Senza il nome del torneo la condizione è n/d: mai un ingresso al buio.
     */
    excludeBestOf5: boolean;
    /**
     * Set già giocati al massimo. «1° set vinto + 2-3 game di vantaggio nel 2°»:
     * il vantaggio di UN set deve venire dall'UNICO set giocato. In bo3 è
     * automatico, in bo5 un 2-1 passerebbe pur avendone già perso uno.
     * 0 = controllo spento.
     */
    setsPlayedMax: number;
    /** parole chiave di competizioni da ESCLUDERE (match su competition_name,
     *  case-insensitive; es. gli Slam maschili best-of-5). Vuoto = nessun filtro. */
    excludeCompetitions: string[];
    /** anti-blip: punteggio set/game osservato stabile da ≥N secondi
     *  (il tennis si muove più veloce del calcio: default più corto) */
    scoreConfirmSec: number;
    /** Q12 + D5 (utente 25/09): «si calcola dalla QUOTA BACK DEL FAVORITO: se
     *  pre-match il favorito è < 1,20 è un super favorito e l'altro uno
     *  sfavorito estremo» → escluso se il leader è lo sfavorito estremo.
     *  Sostituisce `leaderPreMax` (deprecata). Dato assente → non blocca. 0 = spento. */
    favSuperMax: number;
}
export interface SafeStrategyParams {
    base: BaseParams;
    esatto: EsattoParams;
    punta: PuntaParams;
    tennis: TennisParams;
}

export const DEFAULT_PARAMS: SafeStrategyParams = {
    base: {
        minuteMin: 55,
        scores: ['1-0', '2-1', '2-0'],
        favPreMin: 1.4,
        favPreMax: 1.8,
        dogPreMin: 4,
        dogPreMax: 8,
        // Q1 (25/09): quota di BANCA della sfavorita 20–34 (era la Lettura A)
        dogLayMin: 20,
        dogLayMax: 34,
        scoreConfirmSec: 30,
        requireControl: false,
        controlMin: 0.1,
        vetoCampionati: true,
    },
    esatto: {
        minuteMin: 48,
        scores: ['0-0', '1-0', '1-1', '2-1'],
        maxGoalsLaySide: 1,
        entryMin: 30,
        entryMax: 70,
        scoreConfirmSec: 30,
        requireControl: false,
        controlMin: 0.1,
        // Q7 (utente 25/09): «dove disponibile» → acceso (un dato assente non blocca)
        requireSelection: true,
        // D5 (25/09): scontri diretti dal DB, partite da 4+ gol
        h2hManyGoalsRateMax: 0.58,
        h2hMinMeetings: 3,
        oppConcededMax: 1.37,
        vetoCampionati: true,
    },
    punta: {
        minuteMin: 66,
        scores: ['2-0', '3-1', '3-0'],
        entryMin: 1.03,
        entryMax: 1.1,
        minMinutesAfterGoal: 3,
        requireControl: false,
        controlMin: 0.1,
        vetoCampionati: true,
    },
    tennis: {
        setsLeadMin: 1,
        gamesLeadMin: 2,
        // Q5 (25/09): quota minima d'ingresso da 1,01 a 1,02
        backMin: 1.02,
        backMax: 1.1,
        excludeDoubles: true,
        excludeBestOf5: true,
        setsPlayedMax: 1,
        // vuoto di default: il filtro per nome torneo non distingue tabellone
        // maschile/femminile (gli Slam femminili sono best-of-3 e NON da evitare)
        // — la lista la compila l'utente secondo il suo criterio.
        excludeCompetitions: [],
        scoreConfirmSec: 15,
        // Q12 + D5 (25/09): favorito pre-partita < 1,20 → l'altro è uno
        // sfavorito estremo (escluso se è il leader). 0 = spento.
        favSuperMax: 1.2,
    },
};

export const VARIANT_META: Record<VariantId, { num: string; label: string; sport: Sport; short: string }> = {
    base: { num: '1', label: 'Calcio · Base', sport: 'calcio', short: 'BASE' },
    esatto: { num: '2', label: 'Calcio · Risultato Esatto', sport: 'calcio', short: 'RIS. ESATTO' },
    punta: { num: '3', label: 'Calcio · Variante Punta', sport: 'calcio', short: 'PUNTA' },
    tennis: { num: '4', label: 'Tennis', sport: 'tennis', short: 'TENNIS' },
};

// ---------------------------------------------------------- merge parametri
function num(v: unknown, fallback: number): number {
    return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}
function bool(v: unknown, fallback: boolean): boolean {
    return typeof v === 'boolean' ? v : fallback;
}
function scoreList(v: unknown, fallback: string[]): string[] {
    if (!Array.isArray(v)) return fallback;
    const out = v.filter((s): s is string => typeof s === 'string' && parseScoreline(s) !== null);
    return out.length > 0 ? out : fallback;
}
function keywordList(v: unknown, fallback: string[]): string[] {
    if (!Array.isArray(v)) return fallback;
    return v
        .filter((s): s is string => typeof s === 'string')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
}

/**
 * Merge difensivo di parametri parziali (es. da localStorage) sui default:
 * qualsiasi campo assente/malformato torna al default. Non lancia mai.
 */
export function mergeParams(partial: unknown): SafeStrategyParams {
    const p = (partial && typeof partial === 'object' ? partial : {}) as Record<string, unknown>;
    const d = DEFAULT_PARAMS;
    const b = (p.base ?? {}) as Record<string, unknown>;
    const e = (p.esatto ?? {}) as Record<string, unknown>;
    const u = (p.punta ?? {}) as Record<string, unknown>;
    const t = (p.tennis ?? {}) as Record<string, unknown>;
    return {
        base: {
            minuteMin: num(b.minuteMin, d.base.minuteMin),
            scores: scoreList(b.scores, d.base.scores),
            favPreMin: num(b.favPreMin, d.base.favPreMin),
            favPreMax: num(b.favPreMax, d.base.favPreMax),
            dogPreMin: num(b.dogPreMin, d.base.dogPreMin),
            dogPreMax: num(b.dogPreMax, d.base.dogPreMax),
            // Q1 (25/09): favLiveMin/favLiveMax deprecate, non si leggono più
            dogLayMin: num(b.dogLayMin, d.base.dogLayMin),
            dogLayMax: num(b.dogLayMax, d.base.dogLayMax),
            scoreConfirmSec: num(b.scoreConfirmSec, d.base.scoreConfirmSec),
            requireControl: bool(b.requireControl, d.base.requireControl),
            controlMin: num(b.controlMin, d.base.controlMin),
            vetoCampionati: bool(b.vetoCampionati, d.base.vetoCampionati),
        },
        esatto: {
            minuteMin: num(e.minuteMin, d.esatto.minuteMin),
            scores: scoreList(e.scores, d.esatto.scores),
            maxGoalsLaySide: num(e.maxGoalsLaySide, d.esatto.maxGoalsLaySide),
            entryMin: num(e.entryMin, d.esatto.entryMin),
            entryMax: num(e.entryMax, d.esatto.entryMax),
            scoreConfirmSec: num(e.scoreConfirmSec, d.esatto.scoreConfirmSec),
            requireControl: bool(e.requireControl, d.esatto.requireControl),
            controlMin: num(e.controlMin, d.esatto.controlMin),
            requireSelection: bool(e.requireSelection, d.esatto.requireSelection),
            // D5 (25/09): `h2hBigDrawRateMax` deprecata, non si legge più
            h2hManyGoalsRateMax: num(e.h2hManyGoalsRateMax, d.esatto.h2hManyGoalsRateMax),
            h2hMinMeetings: num(e.h2hMinMeetings, d.esatto.h2hMinMeetings),
            oppConcededMax: num(e.oppConcededMax, d.esatto.oppConcededMax),
            vetoCampionati: bool(e.vetoCampionati, d.esatto.vetoCampionati),
        },
        punta: {
            minuteMin: num(u.minuteMin, d.punta.minuteMin),
            scores: scoreList(u.scores, d.punta.scores),
            entryMin: num(u.entryMin, d.punta.entryMin),
            entryMax: num(u.entryMax, d.punta.entryMax),
            minMinutesAfterGoal: num(u.minMinutesAfterGoal, d.punta.minMinutesAfterGoal),
            requireControl: bool(u.requireControl, d.punta.requireControl),
            controlMin: num(u.controlMin, d.punta.controlMin),
            vetoCampionati: bool(u.vetoCampionati, d.punta.vetoCampionati),
        },
        tennis: {
            setsLeadMin: num(t.setsLeadMin, d.tennis.setsLeadMin),
            gamesLeadMin: num(t.gamesLeadMin, d.tennis.gamesLeadMin),
            backMin: num(t.backMin, d.tennis.backMin),
            backMax: num(t.backMax, d.tennis.backMax),
            excludeDoubles: bool(t.excludeDoubles, d.tennis.excludeDoubles),
            excludeBestOf5: bool(t.excludeBestOf5, d.tennis.excludeBestOf5),
            setsPlayedMax: num(t.setsPlayedMax, d.tennis.setsPlayedMax),
            excludeCompetitions: keywordList(t.excludeCompetitions, d.tennis.excludeCompetitions),
            scoreConfirmSec: num(t.scoreConfirmSec, d.tennis.scoreConfirmSec),
            // D5 (25/09): `leaderPreMax` deprecata, non si legge più
            favSuperMax: num(t.favSuperMax, d.tennis.favSuperMax),
        },
    };
}

// ------------------------------------------------------------------ helpers
/** "2-1" → [2,1]; null se malformato. */
export function parseScoreline(s: string): [number, number] | null {
    const m = /^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$/.exec(s);
    if (!m) return null;
    return [Number(m[1]), Number(m[2])];
}

/** true se (a,b) compare nella lista COME ORIENTATO (primo numero = a). */
export function scoreInListOriented(scores: string[], a: number, b: number): boolean {
    return scores.some((s) => {
        const p = parseScoreline(s);
        return p !== null && p[0] === a && p[1] === b;
    });
}

/** true se {a,b} compare nella lista in QUALSIASI orientamento. */
export function scoreInListAnyOrder(scores: string[], a: number, b: number): boolean {
    return scores.some((s) => {
        const p = parseScoreline(s);
        return p !== null && ((p[0] === a && p[1] === b) || (p[0] === b && p[1] === a));
    });
}

function inRange(v: number, min: number, max: number): boolean {
    return v >= min && v <= max;
}

// Formati: UN SOLO formato in tutta la sezione (DESIGN_SYSTEM.md §2) — quota con
// la VIRGOLA decimale, denaro con il simbolo DOPO il numero. Il valore assente
// della checklist resta "n/d" (convenzione del radar, coerente su tutti i check).
function fmtOdds(v: number | null | undefined): string {
    return typeof v === 'number' && Number.isFinite(v) ? fmtOddsFmt(v) : 'n/d';
}

/** importo EUR abbinabile, compatto (es. "152 €", "41,26 €"); null → assente. */
export function fmtEur(v: number | null | undefined): string | null {
    if (typeof v !== 'number' || !Number.isFinite(v)) return null;
    return fmtMoney(v, { decimals: Number.isInteger(v) ? 0 : 2 });
}

/** quota + size abbinabile per la checklist (es. "8,40 · 120 € abbinabili"). */
function fmtOddsWithSize(odds: number | null | undefined, size: number | null | undefined): string {
    const eur = fmtEur(size);
    return eur === null ? fmtOdds(odds) : `${fmtOdds(odds)} · ${eur} abbinabili`;
}

function sizeOrNull(v: number | null | undefined): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function fmtMinute(minute: number | null): string {
    return minute === null ? 'n/d' : `${minute}′`;
}

/** stato aggregato dalle condizioni: false vince su null, null vince su true. */
export function stateFromChecks(checks: ConditionCheck[]): VariantState {
    if (checks.some((c) => c.ok === false)) return 'no';
    if (checks.some((c) => c.ok === null)) return 'nd';
    return 'signal';
}

// ------------------------------------------------------- contesto CALCIO
export interface FootballMatchCtx {
    eventId: string;
    home: string;
    away: string;
    inplay: boolean;
    minute: number | null;
    scoreHome: number | null;
    scoreAway: number | null;
    /** MATCH_ODDS live (null = mercato non disponibile nello snapshot) */
    odds: { home: OddsPair | null; draw: OddsPair | null; away: OddsPair | null } | null;
    /** "Altro risultato Casa/Ospite" dal CORRECT_SCORE live */
    anyOther: { home: OddsPair | null; away: OddsPair | null } | null;
    /** 1X2 pre-match (riferimento favorita/sfavorita); null = non disponibile */
    preMatch: { home: number; draw: number; away: number } | null;
    /** market_id del MATCH_ODDS live (per deep-link Betfair); null se assente */
    matchOddsMarketId: string | null;
    /** MATCH_ODDS tradabile: true=OPEN, false=SUSPENDED/CLOSED, null=assente.
     *  Fondamentale: Base/Punta scattano spesso post-gol, quando il mercato è
     *  sospeso e le quote dell'ultimo snapshot NON sono ottenibili. */
    matchOddsOpen: boolean | null;
    /** CORRECT_SCORE tradabile (stessa semantica). */
    correctScoreOpen: boolean | null;
    /** true se il MATCH_ODDS c'è ma i nomi delle selezioni NON coincidono coi
     *  nomi squadra del follow: quote n/d per mismatch di naming, non per dati
     *  in ritardo — la UI lo segnala così l'utente sa cosa sta succedendo. */
    oddsNameMismatch: boolean;
    /** minuto in cui il punteggio CORRENTE è stato osservato per la prima volta
     *  (per la regola "attendi N minuti dopo il gol" della Variante Punta);
     *  null = non ancora osservabile */
    scoreStableSinceMinute: number | null;
    /** secondi da cui il punteggio CORRENTE è osservato ininterrottamente
     *  (anti-blip: l'IPS Betfair occasionalmente manda punteggi errati) */
    scoreObservedSec: number | null;
    /** cartellini rossi live (da live_now.state.stats); null = dato non esposto
     *  dal provider punteggio corrente — in tal caso il check viene SALTATO,
     *  non bloccato (il dato manca per il provider, non per la partita) */
    red: { home: number; away: number } | null;
    /** CERT. 14/09 - indice di "controllo del gioco" orientato sulla squadra di
     *  CASA, in [-1, 1] (negativo = preme l'ospite). Lo calcola lo SCANNER e
     *  viaggia nel payload: questo motore e quello del bot leggono lo stesso
     *  numero, altrimenti la pagina mostrerebbe un segnale che il bot non
     *  prende. null = dato non disponibile (mai zero). */
    pressureIndex: number | null;
    /** SPEC §2 «Selezione aggiuntiva» (16/09): scontri diretti e gol subiti,
     *  calcolati dallo SCANNER e pubblicati nella riga (come pressureIndex).
     *  null = dato non disponibile, e non diventa mai uno zero. */
    selectionHint: SelectionHint | null;
    /** Q4 (25/09): nome Betfair della competizione (riga dello scanner), per il
     *  veto dei campionati del corso. Assente/null = veto non applicabile
     *  (come i cartellini: l'assenza del dato non è la lista nera). */
    competition?: string | null;
    /** D5 (25/09): nome dell'evento Betfair (riserva per riconoscere una
     *  FINALE quando il round della fixture manca). */
    eventName?: string | null;
    /** D5 (25/09): round API-Football della fixture abbinata («Final»,
     *  «Semi-finals», «Regular Season - 5»), pubblicato dallo scanner. */
    fixtureRound?: string | null;
}

/** I numeri della «Selezione aggiuntiva» come li scrive lo scanner
 *  (`safe_strategy/selezione.py`, `hint_da_scheda`): D5 (25/09) fonte DB,
 *  `fixture_predictions.raw_json` (la riga della Dashboard). null = dato assente. */
export interface SelectionHint {
    fonte?: string;
    fixtureId?: number | null;
    h2hMeetings: number | null;
    /** scontri diretti con 4 o più gol a fine partita */
    h2hManyGoals: number | null;
    conceded: { home: number | null; away: number | null } | null;
    /** % «Attacco»/«Difesa» del CONFRONTO DIRETTO della Dashboard (solo nota) */
    forze?: {
        att: { home: number | null; away: number | null } | null;
        def: { home: number | null; away: number | null } | null;
    } | null;
}

/** Estrae il 1X2 pre-match dal payload di get_betfair_odds ({"1x2": {H,D,A|X}}). */
export function parsePreMatch1x2(preMatch: BetfairOdds | null): { home: number; draw: number; away: number } | null {
    const x2 = preMatch?.['1x2'] ?? null;
    const pmH = x2 && typeof x2.H === 'number' ? x2.H : null;
    const pmD = x2 && typeof x2.D === 'number' ? x2.D : x2 && typeof x2.X === 'number' ? x2.X : null;
    const pmA = x2 && typeof x2.A === 'number' ? x2.A : null;
    return pmH !== null && pmD !== null && pmA !== null ? { home: pmH, draw: pmD, away: pmA } : null;
}

function norm(s: string | null | undefined): string {
    return (s ?? '').trim().toLowerCase();
}

function pairOf(sel: LiveNowSelection | undefined): OddsPair | null {
    if (!sel) return null;
    return { back: sel.back ?? null, lay: sel.lay ?? null };
}

/** status assente (snapshot vecchi) = considerato aperto; altrimenti solo OPEN. */
function marketOpen(status: string | null | undefined): boolean {
    return status == null || status === 'OPEN';
}

/**
 * Costruisce il contesto calcio dagli snapshot del data-layer esistente.
 * `now` = riga live_now (runner, ~5s) · `preMatch` = 1X2 CERTIFICATO pre-KO
 * (il provider lo cattura solo prima del kickoff: mai quote contaminate in-play).
 */
export function buildFootballCtx(
    follow: { event_id: string; home_name: string; away_name: string },
    now: LiveNowRow | null,
    preMatch: { home: number; draw: number; away: number } | null,
    scoreStableSinceMinute: number | null,
    scoreObservedSec: number | null,
): FootballMatchCtx {
    const markets = now?.state?.markets ?? [];
    const mo = markets.find((m) => m.market_type === 'MATCH_ODDS');
    const cs = markets.find((m) => m.market_type === 'CORRECT_SCORE');

    let odds: FootballMatchCtx['odds'] = null;
    let oddsNameMismatch = false;
    if (mo) {
        const homeSel = mo.selections.find((s) => norm(s.name) === norm(follow.home_name));
        const awaySel = mo.selections.find((s) => norm(s.name) === norm(follow.away_name));
        const drawSel =
            mo.selections.find((s) => norm(s.name) === 'the draw') ??
            mo.selections.find((s) => s !== homeSel && s !== awaySel);
        odds = { home: pairOf(homeSel), draw: pairOf(drawSel), away: pairOf(awaySel) };
        oddsNameMismatch = !homeSel || !awaySel;
    }

    let anyOther: FootballMatchCtx['anyOther'] = null;
    if (cs) {
        const anyHome = cs.selections.find((s) => /any other/i.test(s.name) && /home/i.test(s.name));
        const anyAway = cs.selections.find((s) => /any other/i.test(s.name) && /away/i.test(s.name));
        anyOther = { home: pairOf(anyHome), away: pairOf(anyAway) };
    }

    // rossi live: presenti solo se il provider punteggio li espone
    const cards = now?.state?.stats?.cards ?? null;
    const redH = typeof cards?.red_home === 'number' ? cards.red_home : null;
    const redA = typeof cards?.red_away === 'number' ? cards.red_away : null;

    return {
        eventId: follow.event_id,
        home: follow.home_name,
        away: follow.away_name,
        inplay: now?.inplay === true,
        minute: now?.minute ?? null,
        scoreHome: now?.score_home ?? null,
        scoreAway: now?.score_away ?? null,
        odds,
        anyOther,
        preMatch,
        matchOddsMarketId: mo?.market_id ?? null,
        matchOddsOpen: mo ? marketOpen(mo.status) : null,
        correctScoreOpen: cs ? marketOpen(cs.status) : null,
        oddsNameMismatch,
        scoreStableSinceMinute,
        scoreObservedSec,
        red: redH !== null && redA !== null ? { home: redH, away: redA } : null,
        // l'indice di controllo lo pubblica lo SCANNER: da live_now non c'e',
        // e un dato assente resta assente (il check diventa "n/d", non falso).
        pressureIndex: null,
        // stessa ragione: la «selezione aggiuntiva» la pubblica lo SCANNER;
        // da live_now non c'è, e un dato assente resta assente.
        selectionHint: null,
    };
}

// ---------------------------------------------- contesti dallo SCANNER autonomo
function numOrNull(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
function scanPair(x: ScanOddsPair | null | undefined): OddsPair | null {
    if (!x) return null;
    return {
        back: numOrNull(x.back),
        lay: numOrNull(x.lay),
        backSize: numOrNull(x.back_size),
        laySize: numOrNull(x.lay_size),
    };
}
/** stato mercato dallo scanner: null = non ancora interrogato (ignoto). */
function scanMarketOpen(status: string | null | undefined): boolean | null {
    return status == null ? null : status === 'OPEN';
}

/** Contesto calcio dalla riga dello scanner autonomo (payload JSONB difensivo). */
export function buildFootballCtxFromScan(
    eventId: string,
    p: CalcioScanPayload,
    scoreStableSinceMinute: number | null,
    scoreObservedSec: number | null,
): FootballMatchCtx {
    const redH = numOrNull(p.red_home);
    const redA = numOrNull(p.red_away);
    return {
        eventId,
        home: p.home ?? p.event_name ?? '—',
        away: p.away ?? '—',
        inplay: p.inplay === true,
        minute: numOrNull(p.minute),
        scoreHome: numOrNull(p.score_home),
        scoreAway: numOrNull(p.score_away),
        odds: p.odds
            ? { home: scanPair(p.odds.home), draw: scanPair(p.odds.draw), away: scanPair(p.odds.away) }
            : null,
        anyOther: p.cs
            ? { home: scanPair(p.cs.any_other_home), away: scanPair(p.cs.any_other_away) }
            : null,
        preMatch:
            p.pre_ko &&
            numOrNull(p.pre_ko.home) !== null &&
            numOrNull(p.pre_ko.draw) !== null &&
            numOrNull(p.pre_ko.away) !== null
                ? { home: p.pre_ko.home, draw: p.pre_ko.draw, away: p.pre_ko.away }
                : null,
        matchOddsMarketId: p.mo_market_id ?? null,
        matchOddsOpen: scanMarketOpen(p.mo_status),
        correctScoreOpen: p.cs ? scanMarketOpen(p.cs.status) : null,
        oddsNameMismatch: false, // nomi e selezioni vengono dallo STESSO catalogo
        red: redH !== null && redA !== null ? { home: redH, away: redA } : null,
        competition: p.competition?.trim() || null,
        eventName: p.event_name ?? null,
        fixtureRound: typeof p.fixture_round === 'string' ? p.fixture_round.trim() || null : null,
        pressureIndex: numOrNull(p.pressure_index),
        selectionHint: p.selection_hint
            ? {
                  fonte: p.selection_hint.fonte,
                  fixtureId: numOrNull(p.selection_hint.fixture_id),
                  h2hMeetings: numOrNull(p.selection_hint.h2h_meetings),
                  h2hManyGoals: numOrNull(p.selection_hint.h2h_many_goals),
                  conceded: p.selection_hint.conceded
                      ? {
                            home: numOrNull(p.selection_hint.conceded.home),
                            away: numOrNull(p.selection_hint.conceded.away),
                        }
                      : null,
                  forze: p.selection_hint.forze ?? null,
              }
            : null,
        scoreStableSinceMinute,
        scoreObservedSec,
    };
}

/** Contesto tennis dalla riga dello scanner autonomo. */
export function buildTennisCtxFromScan(
    eventId: string,
    p: TennisScanPayload,
    scoreObservedSec: number | null,
): TennisMatchCtx {
    const sets =
        p.sets && numOrNull(p.sets.p1) !== null && numOrNull(p.sets.p2) !== null
            ? { p1: p.sets.p1, p2: p.sets.p2 }
            : null;
    const games =
        p.games && numOrNull(p.games.p1) !== null && numOrNull(p.games.p2) !== null
            ? { p1: p.games.p1, p2: p.games.p2 }
            : null;
    return {
        eventId,
        p1: p.p1 ?? p.event_name ?? '—',
        p2: p.p2 ?? '—',
        inplay: p.inplay === true,
        sets,
        games,
        odds: p.odds ? { p1: scanPair(p.odds.p1), p2: scanPair(p.odds.p2) } : null,
        matchOddsMarketId: p.mo_market_id ?? null,
        matchOddsOpen: scanMarketOpen(p.mo_status),
        oddsNameMismatch: false,
        competition: p.competition?.trim() || null,
        scoreObservedSec,
        preMatch: tennisPreMatch(p.pre_ko),
    };
}

/** Q12 (25/09): coppia pre-partita completa e sensata (quote > 1), altrimenti
 *  null. Gemello di `engine._tennis_pre_match`. */
function tennisPreMatch(pre: TennisScanPayload['pre_ko']): { p1: number; p2: number } | null {
    if (!pre) return null;
    const p1 = numOrNull(pre.p1);
    const p2 = numOrNull(pre.p2);
    if (p1 === null || p2 === null || p1 <= 1 || p2 <= 1) return null;
    return { p1, p2 };
}

/** favorita dal 1X2 pre-match; null se pari o dato mancante. */
export function favoriteSide(preMatch: FootballMatchCtx['preMatch']): SideId | null {
    if (!preMatch) return null;
    if (preMatch.home === preMatch.away) return null;
    return preMatch.home < preMatch.away ? 'home' : 'away';
}

/**
 * Al meglio di quanti set — gemello di ``engine.detect_best_of`` (stesse parole
 * chiave, stesso ordine di valutazione). 5 se sono già stati giocati ≥3 set, o
 * se è uno Slam senza un marcatore femminile/juniores/qualificazioni.
 */
const BO5_KEYWORDS = ['australian open', 'roland garros', 'french open', 'wimbledon', 'us open'];
const BO3_MARKERS = ['women', 'wta', 'ladies', 'girl', 'boy', 'junior',
    'wheelchair', 'qualif', 'mixed', 'legend', 'doubles'];

export function detectBestOf(competition: string | null, setsPlayed: number): number {
    if (setsPlayed >= 3) return 5;
    const comp = (competition ?? '').toLowerCase();
    if (comp && BO5_KEYWORDS.some((k) => comp.includes(k))) {
        if (!BO3_MARKERS.some((m) => comp.includes(m))) return 5;
    }
    return 3;
}

function leaderSide(scoreHome: number, scoreAway: number): SideId | null {
    if (scoreHome === scoreAway) return null;
    return scoreHome > scoreAway ? 'home' : 'away';
}

// ------------------------------------------------- valutatori CALCIO
/** SOGLIA minuto: vera dal minuto indicato IN POI (minuto ≥ soglia), mai un
 *  intervallo chiuso — con un range fisso (es. 48–50′) quasi nessun segnale
 *  passerebbe; il tetto reale lo mettono i range quote delle strategie. */
function minuteCheck(id: string, minute: number | null, fromMinute: number): ConditionCheck {
    return {
        id,
        label: `Dal minuto ${fromMinute}′ in poi`,
        value: fmtMinute(minute),
        ok: minute === null ? null : minute >= fromMinute,
    };
}

/** mercato tradabile ora (post-gol i mercati restano sospesi per secondi:
 *  in quella finestra le quote dell'ultimo snapshot NON sono ottenibili). */
function marketOpenCheck(label: string, open: boolean | null): ConditionCheck {
    return {
        id: 'marketOpen',
        label,
        value: open === null ? 'n/d' : open ? 'aperto' : 'sospeso',
        ok: open,
    };
}

/**
 * CERT. 14/09 - check «controllo del gioco» per una squadra ('home'/'away').
 *
 * `deveAvere = true`  -> la squadra DEVE dominare (BASE e PUNTA: la favorita
 *                        protetta deve avere il controllo).
 * `deveAvere = false` -> la squadra NON deve dominare (RISULTATO ESATTO: la
 *                        condizione e' INVERTITA, la bancata non deve comandare
 *                        il gioco, altrimenti e' piu' probabile che segni
 *                        ancora — ed e' proprio il gol che fa perdere).
 *
 * `idx` e' orientato sulla squadra di CASA: positivo = preme la casa.
 * Dato assente -> `ok: null`: nessun segnale su un dato che non c'e'.
 * Gemello esatto di `engine.control_check` (Python): i due motori devono dire
 * la stessa cosa sulla stessa riga.
 */
export function controlCheck(
    idx: number | null,
    lato: SideId | null,
    deveAvere: boolean,
    soglia: number,
): ConditionCheck {
    const label = deveAvere ? 'Controllo del gioco alla favorita' : 'La bancata NON ha il controllo';
    if (idx === null || (lato !== 'home' && lato !== 'away')) {
        return { id: 'control', label, value: 'n/d', ok: null };
    }
    const proprio = lato === 'home' ? idx : -idx;
    const ok = deveAvere ? proprio >= soglia : proprio <= soglia;
    const verso = proprio > 0 ? 'preme' : proprio < 0 ? 'subisce' : 'equilibrio';
    return { id: 'control', label, value: `${verso} (${proprio.toFixed(2)})`, ok };
}

/** 1 · Calcio Base — banca (lay) la squadra che perde sul mercato 1X2. */
/**
 * Q4 (ordine dell'utente 25/09) — VETO dei campionati del corso, con le
 * decisioni D5 dello stesso giorno. Gemello di `engine.campionato_check`
 * (Python), stesso ordine: 1) competizione in lista (coppe e Bolivia NON più
 * in lista); 2) nome di una SQUADRA femminile; 3) FINALE (dal round della
 * fixture; solo se il round manca, dal nome evento). null = nessun check:
 * veto spento, oppure competizione assente e nessuna regola 2-3 scatta.
 */
export function campionatoCheck(
    competition: string | null | undefined,
    attivo: boolean,
    extra: { home?: string | null; away?: string | null; fixtureRound?: string | null; eventName?: string | null } = {},
): ConditionCheck | null {
    if (!attivo) return null;
    const label = 'Campionato non vietato dal corso';
    if (competition != null) {
        const voce = voceVietata(competition);
        if (voce !== null) return { id: 'campionato', label, value: motivoVeto(voce), ok: false };
    }
    if (squadraFemminile(extra.home) || squadraFemminile(extra.away)) {
        return { id: 'campionato', label, value: MOTIVO_SQUADRA_FEMMINILE, ok: false };
    }
    if (extra.fixtureRound != null) {
        if (isRoundFinale(extra.fixtureRound)) {
            return { id: 'campionato', label, value: MOTIVO_FINALE_ROUND, ok: false };
        }
    } else if (nomeIndicaFinale(extra.eventName)) {
        return { id: 'campionato', label, value: MOTIVO_FINALE_NOME, ok: false };
    }
    if (competition == null) return null;
    return { id: 'campionato', label, value: competition, ok: true };
}

/** `campionatoCheck` con tutti i dati della riga (un solo punto). */
function campionatoCtx(ctx: FootballMatchCtx, attivo: boolean): ConditionCheck | null {
    return campionatoCheck(ctx.competition, attivo, {
        home: ctx.home, away: ctx.away, fixtureRound: ctx.fixtureRound ?? null, eventName: ctx.eventName ?? null,
    });
}

/** Bande pre-partita favorita/sfavorita dalla sezione `base` dei parametri.
 *  UNA sola implementazione per BASE e PUNTA (Q10, 25/09). Gemello di
 *  `engine.pre_bands_checks`. */
export function preBandsChecks(
    preMatch: FootballMatchCtx['preMatch'],
    fav: SideId | null,
    bande: Pick<BaseParams, 'favPreMin' | 'favPreMax' | 'dogPreMin' | 'dogPreMax'>,
): ConditionCheck[] {
    const favLabel = `Favorita pre-match ${bande.favPreMin}–${bande.favPreMax}`;
    const dogLabel = `Sfavorita pre-match ${bande.dogPreMin}–${bande.dogPreMax}`;
    if (preMatch === null || fav === null) {
        return [
            { id: 'favPre', label: favLabel, value: 'n/d', ok: null },
            { id: 'dogPre', label: dogLabel, value: 'n/d', ok: null },
        ];
    }
    const favPre = fav === 'home' ? preMatch.home : preMatch.away;
    const dogPre = fav === 'home' ? preMatch.away : preMatch.home;
    return [
        { id: 'favPre', label: favLabel, value: fmtOdds(favPre), ok: inRange(favPre, bande.favPreMin, bande.favPreMax) },
        { id: 'dogPre', label: dogLabel, value: fmtOdds(dogPre), ok: inRange(dogPre, bande.dogPreMin, bande.dogPreMax) },
    ];
}

export function evaluateBase(ctx: FootballMatchCtx, params: BaseParams): VariantEvaluation {
    const checks: ConditionCheck[] = [];
    const sh = ctx.scoreHome;
    const sa = ctx.scoreAway;
    const fav = favoriteSide(ctx.preMatch);
    const lead = sh !== null && sa !== null ? leaderSide(sh, sa) : null;

    checks.push({ id: 'inplay', label: 'Partita in-play', value: ctx.inplay ? 'sì' : 'no', ok: ctx.inplay ? true : false });
    const veto = campionatoCtx(ctx, params.vetoCampionati);
    if (veto !== null) checks.push(veto);
    checks.push(minuteCheck('minute', ctx.minute, params.minuteMin));
    // BASE: "la favorita deve avere il controllo del gioco" (specifica).
    if (params.requireControl) {
        checks.push(controlCheck(ctx.pressureIndex, fav, true, params.controlMin));
    }

    // punteggio: la FAVORITA deve essere in vantaggio con uno dei punteggi ammessi
    if (sh === null || sa === null) {
        checks.push({ id: 'score', label: `Favorita avanti ${params.scores.join(' · ')}`, value: 'n/d', ok: null });
    } else if (fav === null) {
        checks.push({
            id: 'score',
            label: `Favorita avanti ${params.scores.join(' · ')}`,
            value: `${sh}-${sa} (favorita n/d)`,
            ok: null,
        });
    } else {
        const favGoals = fav === 'home' ? sh : sa;
        const dogGoals = fav === 'home' ? sa : sh;
        checks.push({
            id: 'score',
            label: `Favorita avanti ${params.scores.join(' · ')}`,
            value: `${sh}-${sa}`,
            ok: lead === fav && scoreInListOriented(params.scores, favGoals, dogGoals),
        });
    }

    // quote pre-match favorita / sfavorita
    checks.push(...preBandsChecks(ctx.preMatch, fav, params));

    // quote live valide solo a mercato aperto. Q1 (25/09): il filtro sul back
    // live della FAVORITA («Lettura A», 1,20–1,34) è TOLTO; la banda d'ingresso
    // è la quota di BANCA della sfavorita, nel check `dogLay` qui sotto.
    checks.push(marketOpenCheck('Mercato Match Odds aperto', ctx.matchOddsOpen));

    // anti-blip: il punteggio deve essere osservato stabile da almeno N secondi
    // (l'in-play service Betfair a volte manda punteggi errati per qualche tick)
    checks.push({
        id: 'scoreConfirmed',
        label: `Punteggio stabile da ≥${params.scoreConfirmSec}s`,
        value: ctx.scoreObservedSec === null ? 'n/d' : `${Math.floor(ctx.scoreObservedSec)}s`,
        ok: ctx.scoreObservedSec === null ? null : ctx.scoreObservedSec >= params.scoreConfirmSec,
    });

    // rosso alla favorita = "mezzo gol subito" → niente ingresso. Il check è
    // ENFORCED solo quando il dato cartellini c'è (provider Betfair in-play);
    // se il provider non lo espone il check si SALTA: l'assenza del DATO non è
    // l'assenza di rossi, e non blocchiamo la partita per un limite del fallback.
    if (ctx.red !== null && fav !== null) {
        const redFav = fav === 'home' ? ctx.red.home : ctx.red.away;
        checks.push({
            id: 'noRedFav',
            label: 'Nessun rosso alla favorita',
            value: redFav === 0 ? 'nessuno' : `${redFav} rosso/i`,
            ok: redFav === 0,
        });
    }

    const dog: SideId | null = fav === null ? null : fav === 'home' ? 'away' : 'home';
    const dogName = dog === null ? null : dog === 'home' ? ctx.home : ctx.away;
    const dogPair = dog === null || ctx.odds === null ? null : dog === 'home' ? ctx.odds.home : ctx.odds.away;
    const dogLay = dogPair?.lay ?? null;
    // Q1 (25/09): si banca la perdente solo se la sua QUOTA DI BANCA sta nella
    // banda del corso, 20–34 estremi inclusi. Senza un prezzo LAY reale non
    // c'è nulla da bancare: n/d, mai un ingresso al buio.
    checks.push({
        id: 'dogLay',
        label: `Quota banca sfavorita ${params.dogLayMin}–${params.dogLayMax}`,
        value: fmtOddsWithSize(dogLay, dogPair?.laySize),
        ok: dogLay === null ? null : inRange(dogLay, params.dogLayMin, params.dogLayMax),
    });

    const state = stateFromChecks(checks);
    return {
        variant: 'base',
        state,
        checks,
        headline: state === 'signal' && dogName ? `BANCA ${dogName}` : null,
        side: 'LAY',
        selection: dogName,
        entryOdds: dogLay,
        entrySize: dogLay === null ? null : sizeOrNull(dogPair?.laySize),
    };
}

/** 2 · Calcio Risultato Esatto — banca "Altro risultato Casa/Ospite" (un lato). */
/**
 * SPEC §2 riga «Selezione aggiuntiva» — scontri diretti senza troppe partite
 * da 4+ gol e difesa AVVERSARIA solida. Gemello esatto di
 * `engine.selection_check` (Python): i due motori devono dire la stessa cosa
 * sulla stessa riga. D5 (utente 25/09): dati VERI dal DB (la riga della
 * Dashboard); «troppi 2-2, 3-3, 4-2, 4-1» → partite con 4 o più gol; sotto
 * `minMeetings` scontri il conto non blocca; forze attacco/difesa solo nota.
 * «Avversaria» è la difesa della squadra OPPOSTA a quella bancata.
 */
export function selectionCheck(
    hint: SelectionHint | null,
    laidSide: SideId,
    rateMax: number,
    concededMax: number,
    minMeetings = 3,
): ConditionCheck {
    const label = `Scontri diretti con max ${Math.round(rateMax * 100)}% di partite da ≥4 gol e difesa avversaria entro ${fmtOdds(concededMax)} gol subiti`;
    // Q7 (utente 25/09): «dove disponibile». Ogni parte si giudica per conto
    // suo; una parte SENZA dato non blocca e lo dichiara (prima: n/d → blocco).
    const opponent: SideId = laidSide === 'home' ? 'away' : 'home';
    let meetings = hint ? hint.h2hMeetings : null;
    const many = hint ? hint.h2hManyGoals : null;
    const conceded = hint && hint.conceded ? hint.conceded[opponent] : null;
    const forze = forzeTesto(hint ? hint.forze : null);
    let h2hOk: boolean | null = null;
    let difOk: boolean | null = null;
    const parti: string[] = [];
    if (meetings !== null && many !== null && meetings >= 0 && many >= 0) {
        if (meetings === 0) {
            parti.push(SELEZIONE_H2H_NESSUNO);
        } else {
            let testo = `h2h: ${Math.trunc(meetings)} partite, ${Math.trunc(many)} con ≥4 gol`;
            if (meetings < minMeetings) {
                testo += SELEZIONE_H2H_POCHI;
            } else {
                h2hOk = many / meetings <= rateMax;
            }
            parti.push(testo);
        }
    } else {
        meetings = null;
        parti.push(SELEZIONE_H2H_ASSENTE);
    }
    if (conceded !== null) {
        difOk = conceded <= concededMax;
        parti.push(`difesa avversaria ${fmtOdds(conceded)} gol subiti`);
    } else {
        parti.push(SELEZIONE_DIFESA_ASSENTE);
    }
    if (forze !== null) parti.push(forze);
    if (meetings === null && conceded === null && forze === null) {
        return { id: 'h2hDifesa', label, value: SELEZIONE_DATO_ASSENTE, ok: true };
    }
    return { id: 'h2hDifesa', label, value: parti.join(' · '), ok: h2hOk !== false && difOk !== false };
}

/** «forze att 45-55 · def 60-40» (gemello di `engine._forze_testo`). */
function forzeTesto(forze: SelectionHint['forze'] | null | undefined): string | null {
    if (!forze) return null;
    const parti: string[] = [];
    for (const chiave of ['att', 'def'] as const) {
        const blk = forze[chiave];
        if (!blk) return null;
        const casa = numOrNull(blk.home);
        const ospite = numOrNull(blk.away);
        if (casa === null || ospite === null) return null;
        parti.push(`${chiave} ${casa.toFixed(0)}-${ospite.toFixed(0)}`);
    }
    return `forze ${parti[0]} · ${parti[1]}`;
}

// Q7 (25/09): le parole con cui il check DICHIARA un dato assente (non blocca).
// Identiche a quelle del motore del bot (`engine.SELEZIONE_*`).
export const SELEZIONE_DATO_ASSENTE = 'dato assente (non blocca)';
export const SELEZIONE_H2H_ASSENTE = 'scontri diretti: dato assente';
export const SELEZIONE_H2H_NESSUNO = 'h2h: nessuno scontro diretto nel DB (non blocca)';
export const SELEZIONE_H2H_POCHI = ' (troppo pochi: non blocca)';
export const SELEZIONE_DIFESA_ASSENTE = 'difesa: dato assente';
export const TENNIS_PRE_ASSENTE = 'pre-partita: dato assente (non blocca)';

/** D5 punto 7 (utente 25/09): favorito pre-partita < soglia e leader = l'altro
 *  → sfavorito estremo, escluso. Gemello di `engine.tennis_sfavorito_estremo_check`. */
export function tennisSfavoritoEstremoCheck(
    pre: { p1: number; p2: number },
    leader: 1 | 2,
    favSuperMax: number,
    label: string,
): ConditionCheck {
    if (pre.p1 === pre.p2) {
        return { id: 'leaderPre', label, value: `nessun favorito pre-partita (${fmtOdds(pre.p1)})`, ok: true };
    }
    const fav: 1 | 2 = pre.p1 < pre.p2 ? 1 : 2;
    const qFav = fav === 1 ? pre.p1 : pre.p2;
    if (qFav < favSuperMax && leader !== fav) {
        return { id: 'leaderPre', label, value: `favorito pre-match ${fmtOdds(qFav)} → sfavorito estremo: escluso`, ok: false };
    }
    const chi = leader === fav ? 'si punta il favorito' : 'favorito non super';
    return { id: 'leaderPre', label, value: `favorito pre-match ${fmtOdds(qFav)} (${chi})`, ok: true };
}

export function evaluateEsatto(ctx: FootballMatchCtx, params: EsattoParams, side: SideId): VariantEvaluation {
    const checks: ConditionCheck[] = [];
    const sh = ctx.scoreHome;
    const sa = ctx.scoreAway;
    const sideName = side === 'home' ? ctx.home : ctx.away;
    const sideLabel = side === 'home' ? 'Casa' : 'Ospite';

    checks.push({ id: 'inplay', label: 'Partita in-play', value: ctx.inplay ? 'sì' : 'no', ok: ctx.inplay ? true : false });
    const veto = campionatoCtx(ctx, params.vetoCampionati);
    if (veto !== null) checks.push(veto);
    checks.push(minuteCheck('minute', ctx.minute, params.minuteMin));
    // RISULTATO ESATTO: condizione INVERTITA rispetto a BASE e PUNTA — la
    // squadra BANCATA non deve avere il controllo. Se comanda il gioco e' piu'
    // probabile che segni ancora, ed e' proprio il gol che fa perdere.
    if (params.requireControl) {
        checks.push(controlCheck(ctx.pressureIndex, side, false, params.controlMin));
    }
    // SPEC §2 «Selezione aggiuntiva» (ordine dell'utente 16/09): filtro di
    // SELEZIONE DELLA PARTITA, si accende dai parametri come requireControl.
    if (params.requireSelection) {
        checks.push(selectionCheck(ctx.selectionHint, side, params.h2hManyGoalsRateMax, params.oppConcededMax, params.h2hMinMeetings));
    }

    if (sh === null || sa === null) {
        checks.push({ id: 'score', label: `Punteggio ${params.scores.join(' · ')}`, value: 'n/d', ok: null });
        checks.push({ id: 'sideGoals', label: `${sideLabel} con max ${params.maxGoalsLaySide} gol`, value: 'n/d', ok: null });
    } else {
        checks.push({
            id: 'score',
            label: `Punteggio ${params.scores.join(' · ')}`,
            value: `${sh}-${sa}`,
            ok: scoreInListAnyOrder(params.scores, sh, sa),
        });
        const sideGoals = side === 'home' ? sh : sa;
        checks.push({
            id: 'sideGoals',
            label: `${sideLabel} con max ${params.maxGoalsLaySide} gol`,
            value: `${sideGoals} gol`,
            ok: sideGoals <= params.maxGoalsLaySide,
        });
    }

    // anti-blip: l'ingresso scatta appena superata la soglia minuto, quindi un
    // punteggio IPS errato per pochi secondi può falsare l'ingresso — stessa
    // guardia certificata della Base
    checks.push({
        id: 'scoreConfirmed',
        label: `Punteggio stabile da ≥${params.scoreConfirmSec}s`,
        value: ctx.scoreObservedSec === null ? 'n/d' : `${Math.floor(ctx.scoreObservedSec)}s`,
        ok: ctx.scoreObservedSec === null ? null : ctx.scoreObservedSec >= params.scoreConfirmSec,
    });

    // quota "Altro risultato" (Correct Score) — si BANCA: quota di riferimento =
    // SOLO il lay (mai il back come sostituto: su questi mercati lo spread è
    // ampio e un prezzo back non è ottenibile bancando)
    checks.push(marketOpenCheck('Mercato Risultato Esatto aperto', ctx.correctScoreOpen));
    const pair = ctx.anyOther === null ? null : side === 'home' ? ctx.anyOther.home : ctx.anyOther.away;
    const entry = pair?.lay ?? null;
    checks.push({
        id: 'entry',
        label: `Quota "Altro risultato ${sideLabel}" ${params.entryMin}–${params.entryMax}`,
        value: fmtOddsWithSize(entry, pair?.laySize),
        ok: entry === null ? null : inRange(entry, params.entryMin, params.entryMax),
    });

    const state = stateFromChecks(checks);
    return {
        variant: 'esatto',
        subId: side,
        state,
        checks,
        headline: state === 'signal' ? `BANCA Altro risultato ${sideLabel} (${sideName})` : null,
        side: 'LAY',
        selection: `Altro risultato ${sideLabel}`,
        entryOdds: entry,
        entrySize: entry === null ? null : sizeOrNull(pair?.laySize),
    };
}

/** 3 · Calcio Variante Punta — punta (back) la squadra avanti di 2 gol.
 *  Q10 (utente 25/09): stesse bande pre-partita della BASE, lette dalla sezione
 *  `base` dei parametri (`bandePre`); senza, i default del motore. */
export function evaluatePunta(ctx: FootballMatchCtx, params: PuntaParams, bandePre?: BaseParams): VariantEvaluation {
    const checks: ConditionCheck[] = [];
    const sh = ctx.scoreHome;
    const sa = ctx.scoreAway;
    const lead = sh !== null && sa !== null ? leaderSide(sh, sa) : null;
    const fav = favoriteSide(ctx.preMatch);

    checks.push({ id: 'inplay', label: 'Partita in-play', value: ctx.inplay ? 'sì' : 'no', ok: ctx.inplay ? true : false });
    const veto = campionatoCtx(ctx, params.vetoCampionati);
    if (veto !== null) checks.push(veto);
    checks.push(minuteCheck('minute', ctx.minute, params.minuteMin));
    // PUNTA: "la favorita deve continuare a spingere" (specifica). Stessa
    // semantica della BASE: la squadra PROTETTA deve avere il controllo.
    if (params.requireControl) {
        checks.push(controlCheck(ctx.pressureIndex, fav, true, params.controlMin));
    }

    if (sh === null || sa === null) {
        checks.push({ id: 'score', label: `In vantaggio ${params.scores.join(' · ')}`, value: 'n/d', ok: null });
    } else {
        const a = Math.max(sh, sa);
        const b = Math.min(sh, sa);
        checks.push({
            id: 'score',
            label: `In vantaggio ${params.scores.join(' · ')}`,
            value: `${sh}-${sa}`,
            ok: lead !== null && scoreInListOriented(params.scores, a, b),
        });
    }

    // chi è avanti deve essere la favorita pre-match (se il riferimento c'è)
    if (lead === null) {
        checks.push({
            id: 'leadFav',
            label: 'In vantaggio c’è la favorita',
            value: sh !== null && sa !== null ? 'pareggio' : 'n/d',
            ok: sh !== null && sa !== null ? false : null,
        });
    } else if (fav === null) {
        checks.push({ id: 'leadFav', label: 'In vantaggio c’è la favorita', value: 'favorita n/d', ok: null });
    } else {
        checks.push({
            id: 'leadFav',
            label: 'In vantaggio c’è la favorita',
            value: lead === 'home' ? ctx.home : ctx.away,
            ok: lead === fav,
        });
    }

    // Q10 (25/09): bande pre-partita della BASE (stessa funzione, stessi numeri)
    checks.push(...preBandsChecks(ctx.preMatch, fav, bandePre ?? DEFAULT_PARAMS.base));

    // rosso a CHI SI PUNTA (la squadra in vantaggio): un back a quota 1.03-1.10
    // con la squadra in 10 è il worst-case della strategia → niente ingresso.
    // Come nella Base: enforced solo quando il dato cartellini è esposto.
    if (ctx.red !== null && lead !== null) {
        const redLead = lead === 'home' ? ctx.red.home : ctx.red.away;
        checks.push({
            id: 'noRedLead',
            label: 'Nessun rosso a chi si punta',
            value: redLead === 0 ? 'nessuno' : `${redLead} rosso/i`,
            ok: redLead === 0,
        });
    }

    // quota live (back) della squadra in vantaggio — valida solo a mercato aperto
    checks.push(marketOpenCheck('Mercato Match Odds aperto', ctx.matchOddsOpen));
    const leadPair = lead === null || ctx.odds === null ? null : lead === 'home' ? ctx.odds.home : ctx.odds.away;
    const leadBack = leadPair?.back ?? null;
    checks.push({
        id: 'entry',
        label: `Quota live ${params.entryMin}–${params.entryMax}`,
        value: fmtOddsWithSize(leadBack, leadPair?.backSize),
        ok: leadBack === null ? null : inRange(leadBack, params.entryMin, params.entryMax),
    });

    // assestamento post-gol: dal momento in cui ABBIAMO OSSERVATO il punteggio
    // corrente devono essere passati almeno N minuti (stima conservativa: se
    // l'app è aperta a metà partita, il timer parte dall'osservazione).
    const since = ctx.scoreStableSinceMinute;
    const elapsed = since !== null && ctx.minute !== null ? ctx.minute - since : null;
    checks.push({
        id: 'settled',
        label: `Almeno ${params.minMinutesAfterGoal}′ dopo l'ultimo gol`,
        value: elapsed === null ? 'n/d' : `${elapsed}′`,
        ok: elapsed === null ? null : elapsed >= params.minMinutesAfterGoal,
    });

    const state = stateFromChecks(checks);
    const leadName = lead === null ? null : lead === 'home' ? ctx.home : ctx.away;
    return {
        variant: 'punta',
        state,
        checks,
        headline: state === 'signal' && leadName ? `PUNTA ${leadName}` : null,
        side: 'BACK',
        selection: leadName,
        entryOdds: leadBack,
        entrySize: leadBack === null ? null : sizeOrNull(leadPair?.backSize),
    };
}

/** Valuta tutte le varianti calcio su un contesto (base, esatto×2, punta). */
export function evaluateFootballAll(ctx: FootballMatchCtx, params: SafeStrategyParams): VariantEvaluation[] {
    return [
        evaluateBase(ctx, params.base),
        evaluateEsatto(ctx, params.esatto, 'home'),
        evaluateEsatto(ctx, params.esatto, 'away'),
        evaluatePunta(ctx, params.punta, params.base),
    ];
}

// ------------------------------------------------- contesto e valutatore TENNIS
export interface TennisMatchCtx {
    eventId: string;
    p1: string;
    p2: string;
    inplay: boolean;
    sets: { p1: number; p2: number } | null;
    /** game del SET CORRENTE */
    games: { p1: number; p2: number } | null;
    /** MATCH_ODDS live */
    odds: { p1: OddsPair | null; p2: OddsPair | null } | null;
    /** market_id del MATCH_ODDS live (per deep-link Betfair); null se assente */
    matchOddsMarketId: string | null;
    /** MATCH_ODDS tradabile: true=OPEN, false=SUSPENDED/CLOSED, null=assente. */
    matchOddsOpen: boolean | null;
    /** true se il MATCH_ODDS c'è ma i nomi giocatore non coincidono (naming). */
    oddsNameMismatch: boolean;
    /** nome torneo/competizione (per il filtro esclusioni); null = ignoto */
    competition: string | null;
    /** secondi da cui set+game correnti sono osservati stabili (anti-blip) */
    scoreObservedSec: number | null;
    /** Q12 (25/09): quota PRE-PARTITA congelata (back) dei due giocatori, dallo
     *  scanner. Assente = dato non disponibile (non blocca). */
    preMatch?: { p1: number; p2: number } | null;
}

/** chiave compatta della situazione set+game (per il tracker di stabilità). */
export function tennisScoreKey(
    sets: { p1: number; p2: number } | null,
    games: { p1: number; p2: number } | null,
): string | null {
    if (!sets || !games) return null;
    return `s${sets.p1}-${sets.p2}·g${games.p1}-${games.p2}`;
}

export interface TennisScoreStability {
    scoreKey: string;
    sinceMs: number;
}

/** tracker di stabilità set+game: a ogni cambio la finestra riparte. PURO. */
export function trackTennisScoreStability(
    prev: TennisScoreStability | null,
    key: string | null,
    nowMs: number,
): TennisScoreStability | null {
    if (key === null) return prev;
    if (prev !== null && prev.scoreKey === key) return prev;
    return { scoreKey: key, sinceMs: nowMs };
}

/**
 * Costruisce il contesto tennis da tennis_live_now (runner tennis, ~2s).
 * Mappatura repo: p1 = sortPriority 1 (home) · p2 = away.
 */
export function buildTennisCtx(
    follow: { event_id: string; player1_name: string; player2_name: string; competition_name?: string | null },
    now: TennisLiveNowRow | null,
    scoreObservedSec: number | null,
): TennisMatchCtx {
    const score: TennisScoreState | null = now?.score ?? null;
    const mo = now?.state?.markets?.find((m) => m.market_type === 'MATCH_ODDS');
    let odds: TennisMatchCtx['odds'] = null;
    let oddsNameMismatch = false;
    if (mo) {
        const s1 = mo.selections.find((s) => norm(s.name) === norm(follow.player1_name));
        const s2 = mo.selections.find((s) => norm(s.name) === norm(follow.player2_name));
        odds = { p1: pairOf(s1), p2: pairOf(s2) };
        oddsNameMismatch = !s1 || !s2;
    }
    return {
        eventId: follow.event_id,
        p1: follow.player1_name,
        p2: follow.player2_name,
        inplay: now?.inplay === true,
        sets: score?.sets ?? null,
        games: score?.games ?? null,
        odds,
        matchOddsMarketId: mo?.market_id ?? null,
        matchOddsOpen: mo ? marketOpen(mo.status) : null,
        oddsNameMismatch,
        competition: follow.competition_name?.trim() || null,
        scoreObservedSec,
    };
}

/** 4 · Tennis — punta chi è avanti (o banca chi è sotto), stessa logica. */
export function evaluateTennis(ctx: TennisMatchCtx, params: TennisParams): VariantEvaluation {
    const checks: ConditionCheck[] = [];
    const isDoubles = ctx.p1.includes('/') || ctx.p2.includes('/');

    checks.push({ id: 'inplay', label: 'Match in-play', value: ctx.inplay ? 'sì' : 'no', ok: ctx.inplay ? true : false });

    if (params.excludeDoubles) {
        checks.push({ id: 'singles', label: 'Singolare (no doppio)', value: isDoubles ? 'doppio' : 'singolare', ok: !isDoubles });
    }

    // filtro competizioni escluse (es. Slam maschili best-of-5): enforced solo
    // se la lista è compilata; senza nome torneo il check resta n/d
    if (params.excludeCompetitions.length > 0) {
        if (ctx.competition === null) {
            checks.push({ id: 'competition', label: 'Competizione non esclusa', value: 'n/d', ok: null });
        } else {
            const compLower = ctx.competition.toLowerCase();
            const hit = params.excludeCompetitions.find((k) => compLower.includes(k));
            checks.push({
                id: 'competition',
                label: 'Competizione non esclusa',
                value: hit ? `esclusa ("${hit}")` : ctx.competition,
                ok: !hit,
            });
        }
    }

    // leader per SET
    let leader: 1 | 2 | null = null;
    if (ctx.sets === null) {
        checks.push({ id: 'sets', label: `Vantaggio di ${params.setsLeadMin}+ set`, value: 'n/d', ok: null });
    } else {
        const diff = ctx.sets.p1 - ctx.sets.p2;
        leader = diff > 0 ? 1 : diff < 0 ? 2 : null;
        checks.push({
            id: 'sets',
            label: `Vantaggio di ${params.setsLeadMin}+ set`,
            value: `${ctx.sets.p1}-${ctx.sets.p2}`,
            ok: Math.abs(diff) >= params.setsLeadMin,
        });
    }

    // Q12 + D5 (25/09): «sfavoriti estremi» esclusi. Quota back PRE-PARTITA
    // del FAVORITO sotto `favSuperMax` (stretto) → l'altro è uno sfavorito
    // estremo: escluso se è il leader. Dato assente → NON blocca (lo dichiara).
    const favSuperMax = typeof params.favSuperMax === 'number' && Number.isFinite(params.favSuperMax) ? params.favSuperMax : 0;
    if (favSuperMax > 0 && leader !== null) {
        const preLabel = `Leader non sfavorito estremo (favorito pre-partita ≥${fmtOdds(favSuperMax)})`;
        const pre = ctx.preMatch ?? null;
        if (pre === null) {
            checks.push({ id: 'leaderPre', label: preLabel, value: TENNIS_PRE_ASSENTE, ok: true });
        } else {
            checks.push(tennisSfavoritoEstremoCheck(pre, leader, favSuperMax, preLabel));
        }
    }

    // vantaggio game nel set corrente, dello STESSO giocatore avanti nei set
    if (ctx.games === null || leader === null) {
        checks.push({
            id: 'games',
            label: `${params.gamesLeadMin}+ game di vantaggio nel set corrente`,
            value: ctx.games === null ? 'n/d' : `${ctx.games.p1}-${ctx.games.p2}`,
            ok: ctx.games !== null && leader === null && ctx.sets !== null ? false : null,
        });
    } else {
        const gLead = leader === 1 ? ctx.games.p1 - ctx.games.p2 : ctx.games.p2 - ctx.games.p1;
        checks.push({
            id: 'games',
            label: `${params.gamesLeadMin}+ game di vantaggio nel set corrente`,
            value: `${ctx.games.p1}-${ctx.games.p2}`,
            ok: gLead >= params.gamesLeadMin,
        });
    }

    // CERT. 14/09 — FORMATO DEL MATCH, gemello di ``engine.detect_best_of``.
    // Il manuale chiede di evitare gli Slam maschili; il filtro non esisteva
    // all'ingresso, né qui né nel motore Python.
    if (params.excludeBestOf5) {
        if (ctx.competition === null) {
            checks.push({ id: 'bestOf', label: 'Al meglio dei 3 set', value: 'n/d', ok: null });
        } else {
            const played = ctx.sets === null ? 0 : ctx.sets.p1 + ctx.sets.p2;
            const bo = detectBestOf(ctx.competition, played);
            checks.push({
                id: 'bestOf',
                label: 'Al meglio dei 3 set',
                value: `al meglio dei ${bo}`,
                ok: bo !== 5,
            });
        }
    }

    // «1° set vinto»: il vantaggio di UN set deve venire dall'UNICO set giocato
    if (params.setsPlayedMax > 0) {
        const played = ctx.sets === null ? null : ctx.sets.p1 + ctx.sets.p2;
        checks.push({
            id: 'setsPlayed',
            label: `Set già giocati ≤${params.setsPlayedMax}`,
            value: played === null ? 'n/d' : String(played),
            ok: played === null ? null : played <= params.setsPlayedMax,
        });
    }

    // anti-blip: set+game osservati stabili da ≥N secondi
    checks.push({
        id: 'scoreConfirmed',
        label: `Punteggio stabile da ≥${params.scoreConfirmSec}s`,
        value: ctx.scoreObservedSec === null ? 'n/d' : `${Math.floor(ctx.scoreObservedSec)}s`,
        ok: ctx.scoreObservedSec === null ? null : ctx.scoreObservedSec >= params.scoreConfirmSec,
    });

    // quota d'ingresso = BACK del LEADER nel range (fix certificazione: quando
    // il leader quota 1.03-1.10 il lay del perdente sta a ~15-40 — un range sul
    // lay del perdente era matematicamente impossibile). Il lay del perdente al
    // suo prezzo REALE resta l'alternativa operativa equivalente: lo mostriamo
    // come informazione, la quota che decide è quella del leader.
    checks.push(marketOpenCheck('Mercato Match Odds aperto', ctx.matchOddsOpen));
    const leadPair = leader === null || ctx.odds === null ? null : leader === 1 ? ctx.odds.p1 : ctx.odds.p2;
    const trailPair = leader === null || ctx.odds === null ? null : leader === 1 ? ctx.odds.p2 : ctx.odds.p1;
    const leadBack = leadPair?.back ?? null;
    const trailLay = trailPair?.lay ?? null;
    checks.push({
        id: 'odds',
        label: `Quota back leader ${params.backMin}–${params.backMax}`,
        value: `back ${fmtOddsWithSize(leadBack, leadPair?.backSize)}${
            trailLay !== null ? ` · lay perdente ${fmtOddsWithSize(trailLay, trailPair?.laySize)}` : ''
        }`,
        ok: leadBack === null ? null : inRange(leadBack, params.backMin, params.backMax),
    });

    const state = stateFromChecks(checks);
    const leadName = leader === null ? null : leader === 1 ? ctx.p1 : ctx.p2;
    return {
        variant: 'tennis',
        state,
        checks,
        headline: state === 'signal' && leadName ? `PUNTA ${leadName}` : null,
        side: 'BACK',
        selection: leadName,
        entryOdds: leadBack,
        entrySize: leadBack === null ? null : sizeOrNull(leadPair?.backSize),
    };
}

// ------------------------------------------------- stabilità punteggio (Punta)
export interface ScoreStability {
    /** chiave del punteggio osservato (es. "2-0") */
    scoreKey: string;
    /** minuto della PRIMA osservazione di questo punteggio */
    sinceMinute: number;
    /** timestamp (ms) della PRIMA osservazione — per l'anti-blip in secondi */
    sinceMs: number;
}

/**
 * Aggiorna il tracker di stabilità punteggio di un evento: al cambio punteggio
 * il timer riparte (minuto corrente + timestamp corrente). Ritorna il record
 * aggiornato (o null se i dati non bastano). PURO: il chiamante conserva la
 * mappa per-evento e passa `nowMs` (testabilità).
 */
export function trackScoreStability(
    prev: ScoreStability | null,
    minute: number | null,
    scoreHome: number | null,
    scoreAway: number | null,
    nowMs: number,
): ScoreStability | null {
    if (minute === null || scoreHome === null || scoreAway === null) return prev;
    const key = `${scoreHome}-${scoreAway}`;
    if (prev !== null && prev.scoreKey === key) {
        // stesso punteggio: la prima osservazione resta (mai in avanti)
        return prev.sinceMinute <= minute ? prev : { ...prev, sinceMinute: minute };
    }
    return { scoreKey: key, sinceMinute: minute, sinceMs: nowMs };
}

// ---------------------------------------------------------- segnali attivi
export interface ActiveSignal {
    key: string;
    sport: Sport;
    variant: VariantId;
    subId?: SideId;
    eventId: string;
    matchLabel: string;
    headline: string;
    side: 'BACK' | 'LAY' | null;
    /** nome della selezione su cui operare (serve a risolvere l'id di mercato) */
    selection?: string | null;
    entryOdds: number | null;
    /** EUR abbinabili SUBITO a entryOdds (aggiornati live come la quota) */
    entrySize: number | null;
    /** contesto al momento dello scatto (es. "58′ · 1-0") */
    contextAtTrigger: string;
    triggeredAtMs: number;
    status: 'active' | 'expired';
    expiredAtMs: number | null;
}

export interface SignalCandidate {
    key: string;
    sport: Sport;
    variant: VariantId;
    subId?: SideId;
    eventId: string;
    matchLabel: string;
    headline: string;
    side: 'BACK' | 'LAY' | null;
    /** nome della selezione su cui operare (serve a risolvere l'id di mercato) */
    selection?: string | null;
    entryOdds: number | null;
    entrySize: number | null;
    contextAtTrigger: string;
}

/** chiave stabile del segnale: evento + variante(+lato) + situazione punteggio. */
export function signalKey(
    eventId: string,
    variant: VariantId,
    subId: SideId | undefined,
    situation: string,
): string {
    return `${eventId}:${variant}${subId ? `:${subId}` : ''}:${situation}`;
}

const SIGNAL_HISTORY_MAX = 50;

/**
 * Riconcilia i segnali correnti coi candidati del ciclo di valutazione:
 *  - candidato nuovo → segnale attivo (ritornato anche in `fresh` per il toast);
 *  - candidato già attivo → aggiorna quota live;
 *  - attivo non più candidato → passa a 'expired' (resta nello storico sessione).
 * Storico limitato a SIGNAL_HISTORY_MAX (i più recenti). PURO.
 */
export function reconcileSignals(
    prev: ActiveSignal[],
    candidates: SignalCandidate[],
    nowMs: number,
): { next: ActiveSignal[]; fresh: ActiveSignal[] } {
    const byKey = new Map(prev.map((s) => [s.key, s]));
    const candidateKeys = new Set(candidates.map((c) => c.key));
    const fresh: ActiveSignal[] = [];
    const next: ActiveSignal[] = [];

    for (const c of candidates) {
        const existing = byKey.get(c.key);
        if (existing && existing.status === 'active') {
            next.push({ ...existing, entryOdds: c.entryOdds, entrySize: c.entrySize, headline: c.headline });
        } else if (existing && existing.status === 'expired') {
            // stessa situazione tornata valida: riattiva senza nuovo toast
            next.push({
                ...existing,
                status: 'active',
                expiredAtMs: null,
                entryOdds: c.entryOdds,
                entrySize: c.entrySize,
            });
        } else {
            const created: ActiveSignal = { ...c, triggeredAtMs: nowMs, status: 'active', expiredAtMs: null };
            next.push(created);
            fresh.push(created);
        }
    }
    for (const s of prev) {
        if (candidateKeys.has(s.key)) continue;
        if (s.status === 'active') next.push({ ...s, status: 'expired', expiredAtMs: nowMs });
        else next.push(s);
    }

    next.sort((a, b) => b.triggeredAtMs - a.triggeredAtMs);
    return { next: next.slice(0, SIGNAL_HISTORY_MAX), fresh };
}

/** Estrae i candidati-segnale dalle valutazioni di un match calcio. */
export function footballCandidates(
    ctx: FootballMatchCtx,
    evaluations: VariantEvaluation[],
): SignalCandidate[] {
    const out: SignalCandidate[] = [];
    const situation = `${ctx.scoreHome ?? '?'}-${ctx.scoreAway ?? '?'}`;
    for (const ev of evaluations) {
        if (ev.state !== 'signal' || !ev.headline) continue;
        out.push({
            key: signalKey(ctx.eventId, ev.variant, ev.subId, situation),
            sport: 'calcio',
            variant: ev.variant,
            subId: ev.subId,
            eventId: ctx.eventId,
            matchLabel: `${ctx.home} – ${ctx.away}`,
            headline: ev.headline,
            side: ev.side,
            selection: ev.selection ?? null,
            entryOdds: ev.entryOdds,
            entrySize: ev.entrySize,
            contextAtTrigger: `${fmtMinute(ctx.minute)} · ${situation}`,
        });
    }
    return out;
}

/** Estrae il candidato-segnale dalla valutazione di un match tennis. */
export function tennisCandidates(ctx: TennisMatchCtx, ev: VariantEvaluation): SignalCandidate[] {
    if (ev.state !== 'signal' || !ev.headline) return [];
    const situation = ctx.sets ? `set ${ctx.sets.p1}-${ctx.sets.p2}` : 'set ?';
    return [
        {
            key: signalKey(ctx.eventId, 'tennis', undefined, situation),
            sport: 'tennis',
            variant: 'tennis',
            eventId: ctx.eventId,
            matchLabel: `${ctx.p1} – ${ctx.p2}`,
            headline: ev.headline,
            side: ev.side,
            selection: ev.selection ?? null,
            entryOdds: ev.entryOdds,
            entrySize: ev.entrySize,
            contextAtTrigger: `${situation}${ctx.games ? ` · game ${ctx.games.p1}-${ctx.games.p2}` : ''}`,
        },
    ];
}
