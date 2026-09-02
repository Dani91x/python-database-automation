// ============================================================================
// safeStrategy.test.ts — test del motore puro Safe Strategy.
// Copre: parsing punteggi, merge parametri, costruzione contesti dagli snapshot
// del data-layer, i 4 valutatori (segnale / no / n-d), stabilità punteggio e
// riconciliazione segnali (toast solo sui nuovi).
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { LiveNowRow } from '@/lib/live';
import type { TennisLiveNowRow } from '@/lib/tennis';
import {
    DEFAULT_PARAMS,
    mergeParams,
    parseScoreline,
    scoreInListOriented,
    scoreInListAnyOrder,
    stateFromChecks,
    buildFootballCtx,
    parsePreMatch1x2,
    favoriteSide,
    evaluateBase,
    evaluateEsatto,
    evaluatePunta,
    buildTennisCtx,
    evaluateTennis,
    trackScoreStability,
    reconcileSignals,
    footballCandidates,
    tennisCandidates,
    signalKey,
    type FootballMatchCtx,
    type TennisMatchCtx,
    type SignalCandidate,
} from './safeStrategy';

// ------------------------------------------------------------------ fixtures
const FOLLOW = { event_id: 'ev1', home_name: 'Nord FC', away_name: 'Sud FC' };

function liveNow(over: {
    minute?: number | null;
    sh?: number | null;
    sa?: number | null;
    inplay?: boolean;
    favBack?: number | null;
    favLay?: number | null;
    dogBack?: number | null;
    dogLay?: number | null;
    anyOtherHomeLay?: number | null;
    anyOtherAwayLay?: number | null;
    withCs?: boolean;
    moStatus?: string | null;
    csStatus?: string | null;
    redHome?: number;
    redAway?: number;
}): LiveNowRow {
    const {
        minute = 58, sh = 1, sa = 0, inplay = true,
        favBack = 1.28, favLay = 1.3, dogBack = 8.0, dogLay = 8.4,
        anyOtherHomeLay = 45, anyOtherAwayLay = 50, withCs = true,
        moStatus = 'OPEN', csStatus = 'OPEN',
        redHome, redAway,
    } = over;
    const markets = [
        {
            market_id: '1.1', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: moStatus,
            selections: [
                { selection_id: 1, name: 'Nord FC', back: favBack, lay: favLay, ltp: favBack },
                { selection_id: 2, name: 'Sud FC', back: dogBack, lay: dogLay, ltp: dogBack },
                { selection_id: 3, name: 'The Draw', back: 5.0, lay: 5.2, ltp: 5.0 },
            ],
        },
    ];
    if (withCs) {
        markets.push({
            market_id: '1.2', market_type: 'CORRECT_SCORE', market_name: 'Correct Score', status: csStatus,
            selections: [
                { selection_id: 10, name: '1 - 0', back: 3.0, lay: 3.1, ltp: 3.0 },
                { selection_id: 11, name: 'Any Other Home Win', back: 44, lay: anyOtherHomeLay, ltp: 44 },
                { selection_id: 12, name: 'Any Other Away Win', back: 48, lay: anyOtherAwayLay, ltp: 48 },
            ],
        });
    }
    const stats = redHome !== undefined && redAway !== undefined
        ? { cards: { yellow_home: 0, yellow_away: 0, red_home: redHome, red_away: redAway } }
        : undefined;
    return {
        event_id: 'ev1', inplay, minute, score_home: sh, score_away: sa,
        status: 'SecondHalf', score_source: 'ips',
        state: { markets, ...(stats ? { stats } : {}) },
        updated_at: null,
    };
}

// Nord (home) favorita 1.65, Sud (away) sfavorita 5.5 — riferimento CERTIFICATO
// pre-KO (il provider passa già il 1X2 parsato, mai il payload grezzo)
const PRE_MATCH = { home: 1.65, draw: 4.0, away: 5.5 };

function ctxOf(over: Parameters<typeof liveNow>[0] & {
    stableSince?: number | null;
    observedSec?: number | null;
    preMatch?: { home: number; draw: number; away: number } | null;
} = {}): FootballMatchCtx {
    const { stableSince = 50, observedSec = 60, preMatch = PRE_MATCH, ...rest } = over;
    return buildFootballCtx(FOLLOW, liveNow(rest), preMatch, stableSince, observedSec);
}

// ---------------------------------------------------------------- utilities
describe('parseScoreline / liste punteggi', () => {
    it('parsa punteggi validi e rifiuta malformati', () => {
        expect(parseScoreline('2-1')).toEqual([2, 1]);
        expect(parseScoreline(' 10-0 ')).toEqual([10, 0]);
        expect(parseScoreline('2:1')).toBeNull();
        expect(parseScoreline('a-b')).toBeNull();
        expect(parseScoreline('')).toBeNull();
    });
    it('orientato vs qualsiasi ordine', () => {
        expect(scoreInListOriented(['1-0', '2-1'], 1, 0)).toBe(true);
        expect(scoreInListOriented(['1-0'], 0, 1)).toBe(false);
        expect(scoreInListAnyOrder(['1-0'], 0, 1)).toBe(true);
        expect(scoreInListAnyOrder(['1-1'], 1, 1)).toBe(true);
        expect(scoreInListAnyOrder(['2-0'], 1, 1)).toBe(false);
    });
});

describe('mergeParams', () => {
    it('input nullo/garbage → parametri di default', () => {
        expect(mergeParams(null)).toEqual(DEFAULT_PARAMS);
        expect(mergeParams('x')).toEqual(DEFAULT_PARAMS);
        expect(mergeParams({ base: { minuteMin: 'boom', scores: 42 } }).base).toEqual(DEFAULT_PARAMS.base);
    });
    it('override parziale valido preserva il resto', () => {
        const p = mergeParams({ base: { minuteMin: 50 }, tennis: { gamesLeadMin: 3 } });
        expect(p.base.minuteMin).toBe(50);
        expect(p.base.minuteMax).toBe(DEFAULT_PARAMS.base.minuteMax);
        expect(p.tennis.gamesLeadMin).toBe(3);
        expect(p.esatto).toEqual(DEFAULT_PARAMS.esatto);
    });
    it('scores: filtra i malformati, lista vuota → default', () => {
        expect(mergeParams({ base: { scores: ['1-0', 'x'] } }).base.scores).toEqual(['1-0']);
        expect(mergeParams({ base: { scores: ['bad'] } }).base.scores).toEqual(DEFAULT_PARAMS.base.scores);
    });
});

describe('stateFromChecks', () => {
    it('false vince su null, null vince su true', () => {
        expect(stateFromChecks([{ id: 'a', label: '', value: '', ok: true }])).toBe('signal');
        expect(stateFromChecks([
            { id: 'a', label: '', value: '', ok: true },
            { id: 'b', label: '', value: '', ok: null },
        ])).toBe('nd');
        expect(stateFromChecks([
            { id: 'a', label: '', value: '', ok: null },
            { id: 'b', label: '', value: '', ok: false },
        ])).toBe('no');
    });
});

// ------------------------------------------------------------- contesto calcio
describe('buildFootballCtx', () => {
    it('mappa MATCH_ODDS per nome, draw per esclusione, CS "Any Other" e pre-match', () => {
        const ctx = ctxOf();
        expect(ctx.odds?.home).toEqual({ back: 1.28, lay: 1.3 });
        expect(ctx.odds?.away).toEqual({ back: 8.0, lay: 8.4 });
        expect(ctx.odds?.draw).toEqual({ back: 5.0, lay: 5.2 });
        expect(ctx.anyOther?.home?.lay).toBe(45);
        expect(ctx.anyOther?.away?.lay).toBe(50);
        expect(ctx.preMatch).toEqual({ home: 1.65, draw: 4.0, away: 5.5 });
        expect(favoriteSide(ctx.preMatch)).toBe('home');
    });
    it('snapshot mancanti → campi null (mai inventati)', () => {
        const ctx = buildFootballCtx(FOLLOW, null, null, null, null);
        expect(ctx.odds).toBeNull();
        expect(ctx.anyOther).toBeNull();
        expect(ctx.preMatch).toBeNull();
        expect(ctx.minute).toBeNull();
        expect(ctx.inplay).toBe(false);
        expect(ctx.red).toBeNull();
    });
    it('parsePreMatch1x2: H/D/A, variante X, payload assente o incompleto', () => {
        expect(parsePreMatch1x2({ '1x2': { H: 1.65, D: 4.0, A: 5.5 } })).toEqual({ home: 1.65, draw: 4.0, away: 5.5 });
        expect(parsePreMatch1x2({ '1x2': { H: 2.0, X: 3.3, A: 3.8 } })).toEqual({ home: 2.0, draw: 3.3, away: 3.8 });
        expect(parsePreMatch1x2({})).toBeNull();
        expect(parsePreMatch1x2(null)).toBeNull();
        expect(parsePreMatch1x2({ '1x2': { H: 2.0, A: 3.8 } })).toBeNull();
    });
    it('segnala il mismatch dei nomi selezione (quote n/d per naming, non per ritardo)', () => {
        const bad = buildFootballCtx(
            { event_id: 'ev1', home_name: 'Nome Diverso', away_name: 'Sud FC' },
            liveNow({}), PRE_MATCH, 50,
        );
        expect(bad.oddsNameMismatch).toBe(true);
        expect(bad.odds?.home).toBeNull();
        expect(ctxOf().oddsNameMismatch).toBe(false);
    });
});

// -------------------------------------------------------------- 1 · Base
describe('evaluateBase', () => {
    it('SEGNALE: favorita 1-0 al 58′, pre-match e live in range → banca la sfavorita', () => {
        const ev = evaluateBase(ctxOf(), DEFAULT_PARAMS.base);
        expect(ev.state).toBe('signal');
        expect(ev.headline).toBe('BANCA Sud FC');
        expect(ev.side).toBe('LAY');
        expect(ev.entryOdds).toBe(8.4); // lay della sfavorita
    });
    it('NO: minuto fuori finestra', () => {
        expect(evaluateBase(ctxOf({ minute: 70 }), DEFAULT_PARAMS.base).state).toBe('no');
    });
    it('NO: favorita NON in vantaggio (0-1)', () => {
        expect(evaluateBase(ctxOf({ sh: 0, sa: 1 }), DEFAULT_PARAMS.base).state).toBe('no');
    });
    it('NO: quota live favorita fuori range', () => {
        expect(evaluateBase(ctxOf({ favBack: 1.5 }), DEFAULT_PARAMS.base).state).toBe('no');
    });
    it('NO: favorita pre-match fuori range (1.15)', () => {
        const ev = evaluateBase(ctxOf({ preMatch: { home: 1.15, draw: 6.0, away: 12.0 } }), DEFAULT_PARAMS.base);
        expect(ev.state).toBe('no');
    });
    it('N/D: pre-match mancante → mai segnale, mai falso positivo', () => {
        const ev = evaluateBase(ctxOf({ preMatch: null }), DEFAULT_PARAMS.base);
        expect(ev.state).toBe('nd');
        expect(ev.headline).toBeNull();
    });
    it('NO: non in-play', () => {
        expect(evaluateBase(ctxOf({ inplay: false }), DEFAULT_PARAMS.base).state).toBe('no');
    });
    it('NO: mercato Match Odds SOSPESO (es. post-gol) blocca il segnale', () => {
        expect(evaluateBase(ctxOf({ moStatus: 'SUSPENDED' }), DEFAULT_PARAMS.base).state).toBe('no');
    });
    it('SEGNALE con favorita in TRASFERTA: 0-1 vale come "1-0" (punteggi orientati alla favorita)', () => {
        const ev = evaluateBase(ctxOf({
            sh: 0, sa: 1,
            favBack: 8.0, favLay: 8.4,   // Nord (casa) = qui SFAVORITA
            dogBack: 1.28, dogLay: 1.3,  // Sud (trasferta) = qui FAVORITA
            preMatch: { home: 5.5, draw: 4.0, away: 1.65 },
        }), DEFAULT_PARAMS.base);
        expect(ev.state).toBe('signal');
        expect(ev.headline).toBe('BANCA Nord FC'); // si banca la squadra di casa che perde
        expect(ev.entryOdds).toBe(8.4);
    });
    it('N/D: stabilità punteggio non osservabile (anti-blip)', () => {
        expect(evaluateBase(ctxOf({ observedSec: null }), DEFAULT_PARAMS.base).state).toBe('nd');
    });
    it('NO: punteggio osservato da soli 10s → blip non ancora confermato', () => {
        expect(evaluateBase(ctxOf({ observedSec: 10 }), DEFAULT_PARAMS.base).state).toBe('no');
    });
    it('NO: rosso alla FAVORITA blocca il segnale', () => {
        expect(evaluateBase(ctxOf({ redHome: 1, redAway: 0 }), DEFAULT_PARAMS.base).state).toBe('no');
    });
    it('rosso alla SFAVORITA: nessun blocco (neutro/positivo per la strategia)', () => {
        expect(evaluateBase(ctxOf({ redHome: 0, redAway: 1 }), DEFAULT_PARAMS.base).state).toBe('signal');
    });
    it('dato cartellini non esposto dal provider → check saltato, segnale regolare', () => {
        const ev = evaluateBase(ctxOf(), DEFAULT_PARAMS.base);
        expect(ev.state).toBe('signal');
        expect(ev.checks.some((c) => c.id === 'noRedFav')).toBe(false);
    });
    it('N/D: quota LAY della sfavorita mancante → niente da bancare', () => {
        const ev = evaluateBase(ctxOf({ dogLay: null }), DEFAULT_PARAMS.base);
        expect(ev.state).toBe('nd');
        expect(ev.entryOdds).toBeNull();
    });
    it('status mercato assente (snapshot vecchi) = considerato aperto', () => {
        expect(evaluateBase(ctxOf({ moStatus: null }), DEFAULT_PARAMS.base).state).toBe('signal');
    });
});

// -------------------------------------------------- 2 · Risultato Esatto
describe('evaluateEsatto', () => {
    it('SEGNALE lato Casa: 49′, 1-0, Casa con 1 gol, "Any Other Home" a 45', () => {
        const ev = evaluateEsatto(ctxOf({ minute: 49 }), DEFAULT_PARAMS.esatto, 'home');
        expect(ev.state).toBe('signal');
        expect(ev.headline).toContain('Altro risultato Casa');
        expect(ev.entryOdds).toBe(45);
    });
    it('NO: lato con troppi gol (2-1, lato Casa ha 2 gol)', () => {
        const ev = evaluateEsatto(ctxOf({ minute: 49, sh: 2, sa: 1 }), DEFAULT_PARAMS.esatto, 'home');
        expect(ev.state).toBe('no');
        // ...ma il lato Ospite (1 gol) resta valido
        const evAway = evaluateEsatto(ctxOf({ minute: 49, sh: 2, sa: 1, anyOtherAwayLay: 50 }), DEFAULT_PARAMS.esatto, 'away');
        expect(evAway.state).toBe('signal');
    });
    it('NO: punteggio non in lista (3-0)', () => {
        expect(evaluateEsatto(ctxOf({ minute: 49, sh: 3, sa: 0 }), DEFAULT_PARAMS.esatto, 'away').state).toBe('no');
    });
    it('NO: quota fuori range (quota 20)', () => {
        expect(evaluateEsatto(ctxOf({ minute: 49, anyOtherHomeLay: 20 }), DEFAULT_PARAMS.esatto, 'home').state).toBe('no');
    });
    it('N/D: mercato Correct Score assente', () => {
        expect(evaluateEsatto(ctxOf({ minute: 49, withCs: false }), DEFAULT_PARAMS.esatto, 'home').state).toBe('nd');
    });
    it('N/D: lay "Altro risultato" mancante → MAI il back come sostituto', () => {
        const ev = evaluateEsatto(ctxOf({ minute: 49, anyOtherHomeLay: null }), DEFAULT_PARAMS.esatto, 'home');
        expect(ev.state).toBe('nd');
        expect(ev.entryOdds).toBeNull();
    });
    it('NO: mercato Correct Score SOSPESO blocca il segnale', () => {
        expect(evaluateEsatto(ctxOf({ minute: 49, csStatus: 'SUSPENDED' }), DEFAULT_PARAMS.esatto, 'home').state).toBe('no');
    });
    it('NO: punteggio osservato da soli 10s → blip non confermato (anti-blip)', () => {
        expect(evaluateEsatto(ctxOf({ minute: 49, observedSec: 10 }), DEFAULT_PARAMS.esatto, 'home').state).toBe('no');
    });
    it('N/D: stabilità punteggio non osservabile', () => {
        expect(evaluateEsatto(ctxOf({ minute: 49, observedSec: null }), DEFAULT_PARAMS.esatto, 'home').state).toBe('nd');
    });
});

// ------------------------------------------------------ 3 · Variante Punta
describe('evaluatePunta', () => {
    const scenario = { minute: 68, sh: 2, sa: 0, favBack: 1.06, stableSince: 63 };
    it('SEGNALE: 68′, 2-0, favorita avanti, back 1.06, gol assestato da 5′', () => {
        const ev = evaluatePunta(ctxOf(scenario), DEFAULT_PARAMS.punta);
        expect(ev.state).toBe('signal');
        expect(ev.headline).toBe('PUNTA Nord FC');
        expect(ev.side).toBe('BACK');
        expect(ev.entryOdds).toBe(1.06);
    });
    it('NO: gol troppo recente (osservato da 1′)', () => {
        expect(evaluatePunta(ctxOf({ ...scenario, stableSince: 67 }), DEFAULT_PARAMS.punta).state).toBe('no');
    });
    it('N/D: stabilità punteggio non ancora osservabile', () => {
        expect(evaluatePunta(ctxOf({ ...scenario, stableSince: null }), DEFAULT_PARAMS.punta).state).toBe('nd');
    });
    it('NO: in vantaggio c’è la SFAVORITA', () => {
        // Sud (away, sfavorita) avanti 0-2: score in lista come 2-0 ma leader ≠ favorita
        const ev = evaluatePunta(ctxOf({ ...scenario, sh: 0, sa: 2, dogBack: 1.06 }), DEFAULT_PARAMS.punta);
        expect(ev.state).toBe('no');
    });
    it('NO: margine di un solo gol (2-1)', () => {
        expect(evaluatePunta(ctxOf({ ...scenario, sh: 2, sa: 1 }), DEFAULT_PARAMS.punta).state).toBe('no');
    });
    it('NO: mercato SOSPESO blocca il segnale (scenario post-gol tipico)', () => {
        expect(evaluatePunta(ctxOf({ ...scenario, moStatus: 'SUSPENDED' }), DEFAULT_PARAMS.punta).state).toBe('no');
    });
    it('NO: rosso a CHI SI PUNTA blocca il segnale', () => {
        expect(evaluatePunta(ctxOf({ ...scenario, redHome: 1, redAway: 0 }), DEFAULT_PARAMS.punta).state).toBe('no');
    });
    it('rosso a chi PERDE: nessun blocco', () => {
        expect(evaluatePunta(ctxOf({ ...scenario, redHome: 0, redAway: 1 }), DEFAULT_PARAMS.punta).state).toBe('signal');
    });
    it('dato cartellini non esposto → check saltato, segnale regolare', () => {
        const ev = evaluatePunta(ctxOf(scenario), DEFAULT_PARAMS.punta);
        expect(ev.state).toBe('signal');
        expect(ev.checks.some((c) => c.id === 'noRedLead')).toBe(false);
    });
    it('SEGNALE con favorita in TRASFERTA: 0-2 vale come "2-0"', () => {
        const ev = evaluatePunta(ctxOf({
            minute: 68, sh: 0, sa: 2, stableSince: 63,
            dogBack: 1.06, // Sud (trasferta) = favorita in vantaggio
            preMatch: { home: 5.5, draw: 4.0, away: 1.65 },
        }), DEFAULT_PARAMS.punta);
        expect(ev.state).toBe('signal');
        expect(ev.headline).toBe('PUNTA Sud FC');
    });
});

// ---------------------------------------------------------------- 4 · Tennis
const TENNIS_FOLLOW = { event_id: 'tv1', player1_name: 'Rossi M.', player2_name: 'Bianchi L.' };

function tennisNow(over: {
    sets?: { p1: number; p2: number } | null;
    games?: { p1: number; p2: number } | null;
    inplay?: boolean;
    p1Back?: number | null;
    p2Lay?: number | null;
    moStatus?: string | null;
}): TennisLiveNowRow {
    const { sets = { p1: 1, p2: 0 }, games = { p1: 3, p2: 0 }, inplay = true, p1Back = 1.03, p2Lay = 15, moStatus = 'OPEN' } = over;
    return {
        event_id: 'tv1', inplay, status: 'OPEN',
        state: {
            markets: [{
                market_id: '1.9', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: moStatus,
                selections: [
                    { selection_id: 1, name: 'Rossi M.', back: p1Back, lay: p1Back !== null ? p1Back + 0.01 : null, ltp: p1Back },
                    { selection_id: 2, name: 'Bianchi L.', back: p2Lay !== null ? p2Lay - 1 : null, lay: p2Lay, ltp: p2Lay },
                ],
            }],
        },
        score: (sets === null && games === null) ? null : {
            status: 'InPlay', sets: sets ?? { p1: 0, p2: 0 }, games: games ?? { p1: 0, p2: 0 },
            points: { p1: '0', p2: '0' }, server: 1, tiebreak: false,
            game_sequence: { p1: [], p2: [] }, service_breaks: { p1: 0, p2: 0 },
            current_set: 2, current_game: null, set_summary: null,
            pressure: { break_point: false, set_point: false, game_point: false },
            win_prob_p1: null, source: 'ips', updated_ms: null,
        },
        points: null, updated_at: null,
    };
}

function tennisCtx(over: Parameters<typeof tennisNow>[0] = {}, observedSec: number | null = 60): TennisMatchCtx {
    return buildTennisCtx(TENNIS_FOLLOW, tennisNow(over), observedSec);
}

describe('evaluateTennis', () => {
    it('SEGNALE: set 1-0 + 3-0, back leader 1.03 (range 1.01-1.10)', () => {
        const ev = evaluateTennis(tennisCtx(), DEFAULT_PARAMS.tennis);
        expect(ev.state).toBe('signal');
        expect(ev.headline).toBe('PUNTA Rossi M.');
        expect(ev.side).toBe('BACK');
        expect(ev.entryOdds).toBe(1.03);
    });
    it('SEGNALE: back leader 1.08 — col vecchio range lay impossibile sarebbe stato bloccato', () => {
        const ev = evaluateTennis(tennisCtx({ p1Back: 1.08 }), DEFAULT_PARAMS.tennis);
        expect(ev.state).toBe('signal');
        expect(ev.entryOdds).toBe(1.08);
    });
    it('NO: back leader fuori range (1.15)', () => {
        expect(evaluateTennis(tennisCtx({ p1Back: 1.15 }), DEFAULT_PARAMS.tennis).state).toBe('no');
    });
    it('N/D: back leader non disponibile', () => {
        expect(evaluateTennis(tennisCtx({ p1Back: null }), DEFAULT_PARAMS.tennis).state).toBe('nd');
    });
    it('NO: punteggio osservato da soli 5s → blip non confermato (anti-blip)', () => {
        expect(evaluateTennis(tennisCtx({}, 5), DEFAULT_PARAMS.tennis).state).toBe('no');
    });
    it('N/D: stabilità punteggio non osservabile', () => {
        expect(evaluateTennis(tennisCtx({}, null), DEFAULT_PARAMS.tennis).state).toBe('nd');
    });
    it('filtro competizioni: esclusa → NO; altra → segnale; ignota → N/D', () => {
        const params = { ...DEFAULT_PARAMS.tennis, excludeCompetitions: ['wimbledon'] };
        const at = (comp: string | null) =>
            evaluateTennis(
                buildTennisCtx({ ...TENNIS_FOLLOW, competition_name: comp }, tennisNow({}), 60),
                params,
            ).state;
        expect(at('ATP Wimbledon')).toBe('no');
        expect(at('ATP Rome')).toBe('signal');
        expect(at(null)).toBe('nd');
        // lista vuota (default) → check assente, nessun blocco
        const ev = evaluateTennis(tennisCtx(), DEFAULT_PARAMS.tennis);
        expect(ev.checks.some((c) => c.id === 'competition')).toBe(false);
    });
    it('NO: solo 1 game di vantaggio nel set corrente', () => {
        expect(evaluateTennis(tennisCtx({ games: { p1: 2, p2: 1 } }), DEFAULT_PARAMS.tennis).state).toBe('no');
    });
    it('NO: vantaggio game del giocatore SBAGLIATO (sotto nei set)', () => {
        expect(evaluateTennis(tennisCtx({ games: { p1: 0, p2: 3 } }), DEFAULT_PARAMS.tennis).state).toBe('no');
    });
    it('NO: set in parità', () => {
        expect(evaluateTennis(tennisCtx({ sets: { p1: 1, p2: 1 } }), DEFAULT_PARAMS.tennis).state).toBe('no');
    });
    it('NO: doppio escluso (nomi con "/")', () => {
        const ctx = buildTennisCtx(
            { event_id: 'tv1', player1_name: 'Rossi/Verdi', player2_name: 'Bianchi/Neri' },
            tennisNow({}),
            60,
        );
        expect(evaluateTennis(ctx, DEFAULT_PARAMS.tennis).state).toBe('no');
    });
    it('N/D: punteggio non disponibile', () => {
        const ctx = buildTennisCtx(TENNIS_FOLLOW, tennisNow({ sets: null, games: null }), 60);
        expect(evaluateTennis(ctx, DEFAULT_PARAMS.tennis).state).toBe('nd');
    });
    it('NO: mercato SOSPESO blocca il segnale', () => {
        expect(evaluateTennis(tennisCtx({ moStatus: 'SUSPENDED' }), DEFAULT_PARAMS.tennis).state).toBe('no');
    });
});

// ------------------------------------------------------- stabilità punteggio
describe('trackScoreStability', () => {
    it('primo avvistamento → parte da minuto e timestamp correnti', () => {
        expect(trackScoreStability(null, 58, 1, 0, 1000)).toEqual({ scoreKey: '1-0', sinceMinute: 58, sinceMs: 1000 });
    });
    it('stesso punteggio → conserva la prima osservazione (minuto e timestamp)', () => {
        const prev = { scoreKey: '1-0', sinceMinute: 58, sinceMs: 1000 };
        expect(trackScoreStability(prev, 63, 1, 0, 9000)).toBe(prev);
    });
    it('gol → il timer riparte (minuto e timestamp)', () => {
        const prev = { scoreKey: '1-0', sinceMinute: 58, sinceMs: 1000 };
        expect(trackScoreStability(prev, 66, 2, 0, 9000)).toEqual({ scoreKey: '2-0', sinceMinute: 66, sinceMs: 9000 });
    });
    it('dati mancanti → non tocca lo stato', () => {
        const prev = { scoreKey: '1-0', sinceMinute: 58, sinceMs: 1000 };
        expect(trackScoreStability(prev, null, 1, 0, 2000)).toBe(prev);
        expect(trackScoreStability(prev, 60, null, 0, 2000)).toBe(prev);
    });
});

// ------------------------------------------------------- riconciliazione segnali
function candidate(key: string, odds = 8.4): SignalCandidate {
    return {
        key, sport: 'calcio', variant: 'base', eventId: 'ev1',
        matchLabel: 'Nord FC – Sud FC', headline: 'BANCA Sud FC', side: 'LAY',
        entryOdds: odds, contextAtTrigger: '58′ · 1-0',
    };
}

describe('reconcileSignals', () => {
    it('candidato nuovo → attivo + fresh (per il toast)', () => {
        const { next, fresh } = reconcileSignals([], [candidate('k1')], 1000);
        expect(next).toHaveLength(1);
        expect(next[0].status).toBe('active');
        expect(fresh).toHaveLength(1);
    });
    it('candidato già attivo → aggiorna la quota, NESSUN nuovo toast', () => {
        const first = reconcileSignals([], [candidate('k1', 8.4)], 1000).next;
        const { next, fresh } = reconcileSignals(first, [candidate('k1', 8.8)], 2000);
        expect(fresh).toHaveLength(0);
        expect(next[0].entryOdds).toBe(8.8);
        expect(next[0].triggeredAtMs).toBe(1000);
    });
    it('candidato sparito → expired ma resta nello storico', () => {
        const first = reconcileSignals([], [candidate('k1')], 1000).next;
        const { next, fresh } = reconcileSignals(first, [], 2000);
        expect(fresh).toHaveLength(0);
        expect(next[0].status).toBe('expired');
        expect(next[0].expiredAtMs).toBe(2000);
    });
    it('situazione tornata valida → riattiva senza nuovo toast', () => {
        const s1 = reconcileSignals([], [candidate('k1')], 1000).next;
        const s2 = reconcileSignals(s1, [], 2000).next;
        const { next, fresh } = reconcileSignals(s2, [candidate('k1')], 3000);
        expect(fresh).toHaveLength(0);
        expect(next[0].status).toBe('active');
    });
});

// ---------------------------------------------------------- estrazione candidati
describe('footballCandidates / tennisCandidates', () => {
    it('calcio: solo le valutazioni in stato signal, chiave con punteggio', () => {
        const ctx = ctxOf();
        const evs = [
            evaluateBase(ctx, DEFAULT_PARAMS.base),                       // signal (58′ 1-0)
            evaluateEsatto(ctx, DEFAULT_PARAMS.esatto, 'home'),           // no (minuto 58)
        ];
        const cands = footballCandidates(ctx, evs);
        expect(cands).toHaveLength(1);
        expect(cands[0].key).toBe(signalKey('ev1', 'base', undefined, '1-0'));
    });
    it('tennis: chiave con punteggio set (un segnale per set)', () => {
        const ctx = tennisCtx();
        const cands = tennisCandidates(ctx, evaluateTennis(ctx, DEFAULT_PARAMS.tennis));
        expect(cands).toHaveLength(1);
        expect(cands[0].key).toBe(signalKey('tv1', 'tennis', undefined, 'set 1-0'));
        expect(cands[0].contextAtTrigger).toBe('set 1-0 · game 3-0');
    });
});
