// D5 (decisioni dell'utente 25/09) — lato PAGINA. Gemello di
// `Betfair/safe_strategy/tests/test_safe_d5_2026_09_25.py`: stessi casi,
// stesse parole nel valore del check. Le righe hanno le chiavi di
// `service.build_rows` (`fixture_round`, `selection_hint` della scheda DB).
import { describe, expect, it } from 'vitest';
import {
    buildFootballCtxFromScan,
    buildTennisCtxFromScan,
    DEFAULT_PARAMS,
    evaluateBase,
    evaluateEsatto,
    evaluatePunta,
    evaluateTennis,
    mergeParams,
    SELEZIONE_H2H_NESSUNO,
    SELEZIONE_H2H_POCHI,
    selectionCheck,
} from '@/lib/safeStrategy';
import {
    isRoundFinale,
    MOTIVO_FINALE_NOME,
    MOTIVO_FINALE_ROUND,
    MOTIVO_SQUADRA_FEMMINILE,
    nomeIndicaFinale,
    squadraFemminile,
    voceVietata,
} from '@/lib/vetoCampionati';

type CalcioP = Parameters<typeof buildFootballCtxFromScan>[1];
type TennisP = Parameters<typeof buildTennisCtxFromScan>[1];

function scan(over: Record<string, unknown> = {}) {
    return buildFootballCtxFromScan('ev1', {
        event_name: 'Nord FC v Sud FC', home: 'Nord FC', away: 'Sud FC',
        competition: 'Serie A', open_date: '2026-09-02T16:00:00+00:00',
        inplay: true, mo_market_id: '1.1', mo_status: 'OPEN',
        odds: {
            home: { back: 1.28, lay: 1.3 },
            draw: { back: 5.0, lay: 5.2 },
            away: { back: 24.0, lay: 25.0 },
        },
        minute: 58, score_home: 1, score_away: 0, red_home: 0, red_away: 0,
        pre_ko: { home: 1.65, draw: 4.0, away: 5.5 },
        cs: { market_id: '1.2', status: 'OPEN', any_other_home: { back: 44, lay: 45 }, any_other_away: { back: 48, lay: 50 } },
        ...over,
    } as CalcioP, 50, 60);
}

const PUNTA = {
    minute: 70, score_home: 2, score_away: 0,
    odds: { home: { back: 1.06, lay: 1.07 }, draw: { back: 20, lay: 22 }, away: { back: 60, lay: 70 } },
};

function tre(over: Record<string, unknown> = {}) {
    return {
        base: evaluateBase(scan(over), DEFAULT_PARAMS.base),
        esatto: evaluateEsatto(scan({ minute: 49, ...over }), DEFAULT_PARAMS.esatto, 'home'),
        punta: evaluatePunta(scan({ ...PUNTA, ...over }), DEFAULT_PARAMS.punta),
    };
}

describe('D5 punto 1 — coppe ammesse, veto SOLO sulle finali', () => {
    const FINALI = ['Final', 'Finals', 'Grand Final', 'Clausura - Final', 'Clausura - Gran Final',
        'Promotion Play-offs - Finals', 'Final - Relegation', 'Promotion Play-offs - final',
        'Fase Final Filiales � Finals'];
    const NON = ['Semi-finals', 'Quarter-finals', 'Semi-finals\t', 'Regular Season - 5', '8th Finals',
        '1/2 Final', 'Elimination Finals', 'Final Round - 3', 'Finals - 11', '3rd Place Final',
        'Final - 3rd place', 'Placement matches - Final', ''];
    it('round finali riconosciuti (nomi veri del DB)', () => {
        for (const r of FINALI) expect(isRoundFinale(r)).toBe(true);
    });
    it('round non finali', () => {
        for (const r of NON) expect(isRoundFinale(r)).toBe(false);
        expect(isRoundFinale(null)).toBe(false);
    });
    it('la finale scarta le tre varianti col motivo dichiarato', () => {
        for (const ev of Object.values(tre({ fixture_round: 'Final' }))) {
            expect(ev.state).toBe('no');
            const ck = ev.checks.find((c) => c.id === 'campionato');
            expect(ck?.value).toBe(MOTIVO_FINALE_ROUND);
            expect(ev.checks.filter((c) => c.ok === false).map((c) => c.id)).toEqual(['campionato']);
        }
    });
    it('una coppa fuori dalla finale passa, la sua finale no', () => {
        expect(voceVietata('English FA Cup')).toBeNull();
        for (const ev of Object.values(tre({ competition: 'English FA Cup', fixture_round: 'Round of 16' }))) {
            expect(ev.state).toBe('signal');
        }
        expect(tre({ competition: 'English FA Cup', fixture_round: 'Final' }).base.state).toBe('no');
    });
    it('il round vince sul nome evento; il nome vale solo se il round manca', () => {
        expect(tre({ fixture_round: 'Semi-finals', event_name: 'Nord FC v Sud FC - Cup Final' }).base.state).toBe('signal');
        const ev = tre({ fixture_round: null, event_name: 'Nord FC v Sud FC - Cup Final' }).base;
        expect(ev.checks.find((c) => c.id === 'campionato')?.value).toBe(MOTIVO_FINALE_NOME);
        expect(nomeIndicaFinale('Cup Semi Final')).toBe(false);
        expect(nomeIndicaFinale('Quarter-final')).toBe(false);
        expect(nomeIndicaFinale('Finals Series')).toBe(false);
    });
    it('competizione assente: la finale resta una finale; senza finale nessun check', () => {
        expect(tre({ competition: null, fixture_round: 'Final' }).base.checks.find((c) => c.id === 'campionato')?.ok).toBe(false);
        const ev = tre({ competition: null, fixture_round: 'Regular Season - 5' }).base;
        expect(ev.checks.find((c) => c.id === 'campionato')).toBeUndefined();
    });
});

describe('D5 punto 2 — Bolivia ammessa', () => {
    it('passa', () => {
        expect(voceVietata('Bolivian Primera Division')).toBeNull();
        expect(tre({ competition: 'Bolivian Primera Division' }).base.state).toBe('signal');
    });
});

describe('D5 punto 4 — femminile dai nomi squadra', () => {
    it('i nomi dell\'utente scartano anche in un campionato lecito', () => {
        for (const [h, a] of [['Arsenal (W)', 'Chelsea (W)'], ['Nord FC', 'Chelsea Women'],
            ['Juventus Femminile', 'Nord FC'], ['Glasgow City Ladies', 'Nord FC'],
            ['Wolfsburg Frauen', 'Nord FC'], ['Real Madrid Femenino', 'Nord FC'], ['Nord FC', 'Santa Fe W']]) {
            const ev = tre({ home: h, away: a }).base;
            expect(ev.state).toBe('no');
            expect(ev.checks.find((c) => c.id === 'campionato')?.value).toBe(MOTIVO_SQUADRA_FEMMINILE);
        }
    });
    it('nomi maschili non scattano', () => {
        for (const n of ['W Connection', 'Wolverhampton Wanderers', 'Wrexham', 'Womersley United', 'Frauenfeld', '', null]) {
            expect(squadraFemminile(n)).toBe(false);
        }
    });
});

describe('D5 punti 5-6 — scontri diretti dal DB e forze della Dashboard', () => {
    const hint = (m: number | null, x: number | null, casa = 0.8, fuori = 1.6) => ({
        fonte: 'fixture_predictions.raw_json', fixtureId: 555, h2hMeetings: m, h2hManyGoals: x,
        conceded: { home: casa, away: fuori },
        forze: { att: { home: 45, away: 55 }, def: { home: 60, away: 40 } },
    });
    it('default 0,58 / minimo 3; la chiave vecchia è ignorata', () => {
        expect(DEFAULT_PARAMS.esatto.h2hManyGoalsRateMax).toBe(0.58);
        expect(DEFAULT_PARAMS.esatto.h2hMinMeetings).toBe(3);
        const p = mergeParams({ esatto: { h2hBigDrawRateMax: 0.01 } as Record<string, unknown> });
        expect(p.esatto.h2hManyGoalsRateMax).toBe(0.58);
    });
    it('nota dichiarata e verdetto (difesa avversaria = ospite)', () => {
        const ck = selectionCheck(hint(4, 2), 'home', 0.58, 1.37, 3);
        expect(ck.ok).toBe(false);
        expect(ck.value).toBe('h2h: 4 partite, 2 con ≥4 gol · difesa avversaria 1,60 gol subiti · forze att 45-55 · def 60-40');
        expect(selectionCheck(hint(4, 2), 'away', 0.58, 1.37, 3).ok).toBe(true);
    });
    it('troppe partite da tanti gol → scarta; bordo 58% incluso', () => {
        expect(selectionCheck(hint(4, 3, 0.8, 0.4), 'home', 0.58, 1.37, 3).ok).toBe(false);
        expect(selectionCheck(hint(50, 29, 0.8, 0.4), 'home', 0.58, 1.37, 3).ok).toBe(true);
        expect(selectionCheck(hint(50, 30, 0.8, 0.4), 'home', 0.58, 1.37, 3).ok).toBe(false);
    });
    it('pochi scontri o nessuno: non blocca e lo dice', () => {
        const pochi = selectionCheck(hint(2, 2, 0.8, 0.4), 'home', 0.58, 1.37, 3);
        expect(pochi.ok).toBe(true);
        expect(pochi.value).toContain('h2h: 2 partite, 2 con ≥4 gol' + SELEZIONE_H2H_POCHI);
        const nessuno = selectionCheck(hint(0, 0, 0.8, 0.4), 'home', 0.58, 1.37, 3);
        expect(nessuno.ok).toBe(true);
        expect(nessuno.value.startsWith(SELEZIONE_H2H_NESSUNO)).toBe(true);
    });
    it('la riga dello scanner arriva al motore (chiavi di build_rows)', () => {
        const ctx = scan({
            minute: 49, fixture_round: 'Regular Season - 5',
            selection_hint: {
                fonte: 'fixture_predictions.raw_json', fixture_id: 555, h2h_meetings: 10,
                h2h_many_goals: 7, conceded: { home: 1.0, away: 1.0 },
                forze: { att: { home: 45, away: 55 }, def: { home: 60, away: 40 } },
            },
        });
        expect(ctx.fixtureRound).toBe('Regular Season - 5');
        const ev = evaluateEsatto(ctx, DEFAULT_PARAMS.esatto, 'home');
        const ck = ev.checks.find((c) => c.id === 'h2hDifesa');
        expect(ck?.ok).toBe(false);
        expect(ck?.value.startsWith('h2h: 10 partite, 7 con ≥4 gol')).toBe(true);
    });
});

describe('D5 punto 7 — tennis: super favorito < 1,20', () => {
    function tennis(pre: unknown, leaderP2 = false) {
        return buildTennisCtxFromScan('tv1', {
            event_name: 'A v B', p1: 'A', p2: 'B', competition: 'ATP Rome', open_date: null,
            inplay: true, mo_market_id: '1.9', mo_status: 'OPEN',
            odds: leaderP2
                ? { p1: { back: 15, lay: 16 }, p2: { back: 1.05, lay: 1.06 } }
                : { p1: { back: 1.05, lay: 1.06 }, p2: { back: 14, lay: 15 } },
            sets: leaderP2 ? { p1: 0, p2: 1 } : { p1: 1, p2: 0 },
            games: leaderP2 ? { p1: 0, p2: 3 } : { p1: 3, p2: 0 },
            pre_ko: pre,
        } as TennisP, 60);
    }
    const lp = (pre: unknown, leaderP2 = false, par = DEFAULT_PARAMS.tennis) =>
        evaluateTennis(tennis(pre, leaderP2), par).checks.find((c) => c.id === 'leaderPre');
    it('default 1,20', () => {
        expect(DEFAULT_PARAMS.tennis.favSuperMax).toBe(1.2);
    });
    it('leader sfavorito estremo → escluso, con la nota', () => {
        expect(lp({ p1: 8, p2: 1.12 })?.value).toBe('favorito pre-match 1,12 → sfavorito estremo: escluso');
        expect(lp({ p1: 8, p2: 1.12 })?.ok).toBe(false);
    });
    it('bordo stretto: 1,20 non è super favorito', () => {
        expect(lp({ p1: 4.8, p2: 1.2 })?.ok).toBe(true);
    });
    it('si punta il super favorito → si entra', () => {
        expect(lp({ p1: 1.1, p2: 8 })?.ok).toBe(true);
        expect(lp({ p1: 8, p2: 1.1 }, true)?.ok).toBe(true);
        expect(lp({ p1: 1.1, p2: 8 }, true)?.ok).toBe(false);
    });
    it('quote pari → nessun favorito', () => {
        expect(lp({ p1: 1.9, p2: 1.9 })?.value).toContain('nessun favorito');
    });
    it('0 = spento; la chiave vecchia leaderPreMax è ignorata', () => {
        expect(lp({ p1: 8, p2: 1.05 }, false, mergeParams({ tennis: { favSuperMax: 0 } }).tennis)).toBeUndefined();
        const p = mergeParams({ tennis: { leaderPreMax: 1.01 } as Record<string, unknown> });
        expect(p.tennis.favSuperMax).toBe(1.2);
    });
});
