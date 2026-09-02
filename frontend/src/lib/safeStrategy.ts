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

// ---------------------------------------------------------------- tipi base
export type Sport = 'calcio' | 'tennis';
export type VariantId = 'base' | 'esatto' | 'punta' | 'tennis';
export type SideId = 'home' | 'away';

export interface OddsPair {
    back: number | null;
    lay: number | null;
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
}

// ---------------------------------------------------------------- parametri
// Default operativi delle quattro strategie. Tutti modificabili dalla UI e
// persistiti in localStorage (merge difensivo in mergeParams).
export interface BaseParams {
    minuteMin: number;
    minuteMax: number;
    /** punteggi ammessi, GOL FAVORITA per primi (es. "1-0","2-1","2-0") */
    scores: string[];
    favPreMin: number;
    favPreMax: number;
    dogPreMin: number;
    dogPreMax: number;
    /** quota live (back) della favorita per l'ingresso */
    favLiveMin: number;
    favLiveMax: number;
    /** anti-blip: il punteggio corrente deve essere osservato stabile da ≥N secondi
     *  (l'in-play service Betfair occasionalmente manda punteggi errati) */
    scoreConfirmSec: number;
}
export interface EsattoParams {
    minuteMin: number;
    minuteMax: number;
    /** punteggi ammessi, in QUALSIASI orientamento (es. "1-0" vale anche 0-1) */
    scores: string[];
    /** la squadra bancata deve aver segnato al massimo N gol */
    maxGoalsLaySide: number;
    /** quota "Altro risultato Casa/Ospite" (Correct Score) per l'ingresso */
    entryMin: number;
    entryMax: number;
    /** anti-blip: punteggio osservato stabile da ≥N secondi (finestra corta 48-50′:
     *  un punteggio IPS errato per pochi secondi pesa di più) */
    scoreConfirmSec: number;
}
export interface PuntaParams {
    minuteMin: number;
    minuteMax: number;
    /** punteggi ammessi, GOL SQUADRA IN VANTAGGIO per primi (margine 2 gol) */
    scores: string[];
    /** quota live (back) della squadra in vantaggio */
    entryMin: number;
    entryMax: number;
    /** minuti di assestamento dopo l'ultimo gol osservato */
    minMinutesAfterGoal: number;
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
    /** parole chiave di competizioni da ESCLUDERE (match su competition_name,
     *  case-insensitive; es. gli Slam maschili best-of-5). Vuoto = nessun filtro. */
    excludeCompetitions: string[];
    /** anti-blip: punteggio set/game osservato stabile da ≥N secondi
     *  (il tennis si muove più veloce del calcio: default più corto) */
    scoreConfirmSec: number;
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
        minuteMax: 62,
        scores: ['1-0', '2-1', '2-0'],
        favPreMin: 1.4,
        favPreMax: 1.8,
        dogPreMin: 4,
        dogPreMax: 8,
        favLiveMin: 1.2,
        favLiveMax: 1.34,
        scoreConfirmSec: 30,
    },
    esatto: {
        minuteMin: 48,
        minuteMax: 50,
        scores: ['0-0', '1-0', '1-1', '2-1'],
        maxGoalsLaySide: 1,
        entryMin: 30,
        entryMax: 70,
        scoreConfirmSec: 30,
    },
    punta: {
        minuteMin: 66,
        minuteMax: 70,
        scores: ['2-0', '3-1', '3-0'],
        entryMin: 1.03,
        entryMax: 1.1,
        minMinutesAfterGoal: 3,
    },
    tennis: {
        setsLeadMin: 1,
        gamesLeadMin: 2,
        backMin: 1.01,
        backMax: 1.1,
        excludeDoubles: true,
        // vuoto di default: il filtro per nome torneo non distingue tabellone
        // maschile/femminile (gli Slam femminili sono best-of-3 e NON da evitare)
        // — la lista la compila l'utente secondo il suo criterio.
        excludeCompetitions: [],
        scoreConfirmSec: 15,
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
            minuteMax: num(b.minuteMax, d.base.minuteMax),
            scores: scoreList(b.scores, d.base.scores),
            favPreMin: num(b.favPreMin, d.base.favPreMin),
            favPreMax: num(b.favPreMax, d.base.favPreMax),
            dogPreMin: num(b.dogPreMin, d.base.dogPreMin),
            dogPreMax: num(b.dogPreMax, d.base.dogPreMax),
            favLiveMin: num(b.favLiveMin, d.base.favLiveMin),
            favLiveMax: num(b.favLiveMax, d.base.favLiveMax),
            scoreConfirmSec: num(b.scoreConfirmSec, d.base.scoreConfirmSec),
        },
        esatto: {
            minuteMin: num(e.minuteMin, d.esatto.minuteMin),
            minuteMax: num(e.minuteMax, d.esatto.minuteMax),
            scores: scoreList(e.scores, d.esatto.scores),
            maxGoalsLaySide: num(e.maxGoalsLaySide, d.esatto.maxGoalsLaySide),
            entryMin: num(e.entryMin, d.esatto.entryMin),
            entryMax: num(e.entryMax, d.esatto.entryMax),
            scoreConfirmSec: num(e.scoreConfirmSec, d.esatto.scoreConfirmSec),
        },
        punta: {
            minuteMin: num(u.minuteMin, d.punta.minuteMin),
            minuteMax: num(u.minuteMax, d.punta.minuteMax),
            scores: scoreList(u.scores, d.punta.scores),
            entryMin: num(u.entryMin, d.punta.entryMin),
            entryMax: num(u.entryMax, d.punta.entryMax),
            minMinutesAfterGoal: num(u.minMinutesAfterGoal, d.punta.minMinutesAfterGoal),
        },
        tennis: {
            setsLeadMin: num(t.setsLeadMin, d.tennis.setsLeadMin),
            gamesLeadMin: num(t.gamesLeadMin, d.tennis.gamesLeadMin),
            backMin: num(t.backMin, d.tennis.backMin),
            backMax: num(t.backMax, d.tennis.backMax),
            excludeDoubles: bool(t.excludeDoubles, d.tennis.excludeDoubles),
            excludeCompetitions: keywordList(t.excludeCompetitions, d.tennis.excludeCompetitions),
            scoreConfirmSec: num(t.scoreConfirmSec, d.tennis.scoreConfirmSec),
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

function fmtOdds(v: number | null | undefined): string {
    return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : 'n/d';
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
    };
}

/** favorita dal 1X2 pre-match; null se pari o dato mancante. */
export function favoriteSide(preMatch: FootballMatchCtx['preMatch']): SideId | null {
    if (!preMatch) return null;
    if (preMatch.home === preMatch.away) return null;
    return preMatch.home < preMatch.away ? 'home' : 'away';
}

function leaderSide(scoreHome: number, scoreAway: number): SideId | null {
    if (scoreHome === scoreAway) return null;
    return scoreHome > scoreAway ? 'home' : 'away';
}

// ------------------------------------------------- valutatori CALCIO
function minuteCheck(id: string, minute: number | null, min: number, max: number): ConditionCheck {
    return {
        id,
        label: `Minuto ${min}–${max}′`,
        value: fmtMinute(minute),
        ok: minute === null ? null : inRange(minute, min, max),
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

/** 1 · Calcio Base — banca (lay) la squadra che perde sul mercato 1X2. */
export function evaluateBase(ctx: FootballMatchCtx, params: BaseParams): VariantEvaluation {
    const checks: ConditionCheck[] = [];
    const sh = ctx.scoreHome;
    const sa = ctx.scoreAway;
    const fav = favoriteSide(ctx.preMatch);
    const lead = sh !== null && sa !== null ? leaderSide(sh, sa) : null;

    checks.push({ id: 'inplay', label: 'Partita in-play', value: ctx.inplay ? 'sì' : 'no', ok: ctx.inplay ? true : false });
    checks.push(minuteCheck('minute', ctx.minute, params.minuteMin, params.minuteMax));

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
    if (ctx.preMatch === null || fav === null) {
        checks.push({ id: 'favPre', label: `Favorita pre-match ${params.favPreMin}–${params.favPreMax}`, value: 'n/d', ok: null });
        checks.push({ id: 'dogPre', label: `Sfavorita pre-match ${params.dogPreMin}–${params.dogPreMax}`, value: 'n/d', ok: null });
    } else {
        const favPre = fav === 'home' ? ctx.preMatch.home : ctx.preMatch.away;
        const dogPre = fav === 'home' ? ctx.preMatch.away : ctx.preMatch.home;
        checks.push({
            id: 'favPre',
            label: `Favorita pre-match ${params.favPreMin}–${params.favPreMax}`,
            value: fmtOdds(favPre),
            ok: inRange(favPre, params.favPreMin, params.favPreMax),
        });
        checks.push({
            id: 'dogPre',
            label: `Sfavorita pre-match ${params.dogPreMin}–${params.dogPreMax}`,
            value: fmtOdds(dogPre),
            ok: inRange(dogPre, params.dogPreMin, params.dogPreMax),
        });
    }

    // quota live (back) della favorita — valida solo a mercato aperto
    checks.push(marketOpenCheck('Mercato Match Odds aperto', ctx.matchOddsOpen));
    const favLive = fav === null || ctx.odds === null ? null : (fav === 'home' ? ctx.odds.home : ctx.odds.away)?.back ?? null;
    checks.push({
        id: 'favLive',
        label: `Quota live favorita ${params.favLiveMin}–${params.favLiveMax}`,
        value: fmtOdds(favLive),
        ok: favLive === null ? null : inRange(favLive, params.favLiveMin, params.favLiveMax),
    });

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
    const dogLay = dog === null || ctx.odds === null ? null : (dog === 'home' ? ctx.odds.home : ctx.odds.away)?.lay ?? null;
    // senza un prezzo LAY reale della sfavorita non c'è nulla da bancare
    checks.push({
        id: 'dogLay',
        label: 'Quota banca sfavorita disponibile',
        value: fmtOdds(dogLay),
        ok: dogLay === null ? null : true,
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
    };
}

/** 2 · Calcio Risultato Esatto — banca "Altro risultato Casa/Ospite" (un lato). */
export function evaluateEsatto(ctx: FootballMatchCtx, params: EsattoParams, side: SideId): VariantEvaluation {
    const checks: ConditionCheck[] = [];
    const sh = ctx.scoreHome;
    const sa = ctx.scoreAway;
    const sideName = side === 'home' ? ctx.home : ctx.away;
    const sideLabel = side === 'home' ? 'Casa' : 'Ospite';

    checks.push({ id: 'inplay', label: 'Partita in-play', value: ctx.inplay ? 'sì' : 'no', ok: ctx.inplay ? true : false });
    checks.push(minuteCheck('minute', ctx.minute, params.minuteMin, params.minuteMax));

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

    // anti-blip: con una finestra di soli 3 minuti un punteggio IPS errato per
    // pochi secondi può falsare l'ingresso — stessa guardia certificata della Base
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
        value: fmtOdds(entry),
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
    };
}

/** 3 · Calcio Variante Punta — punta (back) la squadra avanti di 2 gol. */
export function evaluatePunta(ctx: FootballMatchCtx, params: PuntaParams): VariantEvaluation {
    const checks: ConditionCheck[] = [];
    const sh = ctx.scoreHome;
    const sa = ctx.scoreAway;
    const lead = sh !== null && sa !== null ? leaderSide(sh, sa) : null;
    const fav = favoriteSide(ctx.preMatch);

    checks.push({ id: 'inplay', label: 'Partita in-play', value: ctx.inplay ? 'sì' : 'no', ok: ctx.inplay ? true : false });
    checks.push(minuteCheck('minute', ctx.minute, params.minuteMin, params.minuteMax));

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
    const leadBack = lead === null || ctx.odds === null ? null : (lead === 'home' ? ctx.odds.home : ctx.odds.away)?.back ?? null;
    checks.push({
        id: 'entry',
        label: `Quota live ${params.entryMin}–${params.entryMax}`,
        value: fmtOdds(leadBack),
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
    };
}

/** Valuta tutte le varianti calcio su un contesto (base, esatto×2, punta). */
export function evaluateFootballAll(ctx: FootballMatchCtx, params: SafeStrategyParams): VariantEvaluation[] {
    return [
        evaluateBase(ctx, params.base),
        evaluateEsatto(ctx, params.esatto, 'home'),
        evaluateEsatto(ctx, params.esatto, 'away'),
        evaluatePunta(ctx, params.punta),
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
        value: `back ${fmtOdds(leadBack)}${trailLay !== null ? ` · lay perdente ${fmtOdds(trailLay)}` : ''}`,
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
    entryOdds: number | null;
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
    entryOdds: number | null;
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
            next.push({ ...existing, entryOdds: c.entryOdds, headline: c.headline });
        } else if (existing && existing.status === 'expired') {
            // stessa situazione tornata valida: riattiva senza nuovo toast
            next.push({ ...existing, status: 'active', expiredAtMs: null, entryOdds: c.entryOdds });
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
            entryOdds: ev.entryOdds,
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
            entryOdds: ev.entryOdds,
            contextAtTrigger: `${situation}${ctx.games ? ` · game ${ctx.games.p1}-${ctx.games.p2}` : ''}`,
        },
    ];
}
