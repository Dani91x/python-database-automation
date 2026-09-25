// Q7 / Q10 / Q12 (ordini dell'utente 25/09) — lato PAGINA. Gemello di
// `Betfair/safe_strategy/tests/test_safe_q7_q12_2026_09_25.py`: stessi numeri,
// stessi esiti, stesse parole nel valore del check.
import { describe, expect, it } from 'vitest';
import {
    buildFootballCtxFromScan,
    buildTennisCtxFromScan,
    DEFAULT_PARAMS,
    evaluateFootballAll,
    evaluateTennis,
    mergeParams,
    SELEZIONE_DATO_ASSENTE,
    SELEZIONE_H2H_ASSENTE,
    selectionCheck,
    TENNIS_PRE_ASSENTE,
} from '@/lib/safeStrategy';

type CalcioP = Parameters<typeof buildFootballCtxFromScan>[1];
type TennisP = Parameters<typeof buildTennisCtxFromScan>[1];

function calcio(over: Record<string, unknown> = {}) {
    return buildFootballCtxFromScan('ev1', {
        event_name: 'Nord FC v Sud FC', home: 'Nord FC', away: 'Sud FC',
        competition: 'Italian Serie A', open_date: null, inplay: true, mo_market_id: '1.1', mo_status: 'OPEN',
        odds: { home: { back: 1.06, lay: 1.07 }, draw: { back: 20, lay: 22 }, away: { back: 60, lay: 70 } },
        minute: 70, score_home: 2, score_away: 0, red_home: 0, red_away: 0,
        pre_ko: { home: 1.65, draw: 4.0, away: 5.5 },
        cs: { market_id: '1.2', status: 'OPEN', any_other_home: { back: 44, lay: 45 }, any_other_away: { back: 48, lay: 50 } },
        ...over,
    } as CalcioP, 50, 60);
}

function tennis(pre: unknown, over: Record<string, unknown> = {}) {
    return buildTennisCtxFromScan('tv1', {
        event_name: 'A v B', p1: 'A', p2: 'B', competition: 'ATP Rome', open_date: null,
        inplay: true, mo_market_id: '1.9', mo_status: 'OPEN',
        odds: { p1: { back: 1.05, lay: 1.06 }, p2: { back: 14, lay: 15 } },
        sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 0 },
        pre_ko: pre,
        ...over,
    } as TennisP, 60);
}

describe('Q7 — selezione aggiuntiva ESATTO «dove disponibile»', () => {
    it('acceso di default', () => {
        expect(DEFAULT_PARAMS.esatto.requireSelection).toBe(true);
    });
    it('dato del tutto assente → non blocca e lo dichiara', () => {
        const ck = selectionCheck(null, 'home', 0.12, 1.37);
        expect(ck.ok).toBe(true);
        expect(ck.value).toBe(SELEZIONE_DATO_ASSENTE);
    });
    it('manca lo scontro diretto → si giudica la sola difesa avversaria', () => {
        const h = { h2hMeetings: null, h2hBigDraws: null, conceded: { home: 3.0, away: 0.9 } };
        const buona = selectionCheck(h, 'home', 0.12, 1.37);
        expect(buona.ok).toBe(true);
        expect(buona.value).toBe(`${SELEZIONE_H2H_ASSENTE} · difesa 0,90`);
        expect(selectionCheck({ ...h, conceded: { home: 3.0, away: 1.8 } }, 'home', 0.12, 1.37).ok).toBe(false);
    });
    it('troppi 2-2/3-3 → scarta', () => {
        const h = { h2hMeetings: 10, h2hBigDraws: 4, conceded: { home: 1.0, away: 1.0 } };
        expect(selectionCheck(h, 'home', 0.12, 1.37).ok).toBe(false);
    });
});

describe('Q10 — PUNTA con le bande pre-partita della BASE', () => {
    const punta = (pre: Record<string, number>, params = DEFAULT_PARAMS) =>
        evaluateFootballAll(calcio({ pre_ko: pre }), params)[3];
    it('dentro le bande → segnale', () => {
        expect(punta({ home: 1.65, draw: 4.0, away: 5.5 }).state).toBe('signal');
    });
    it('favorita troppo forte → no, per il solo check favPre', () => {
        const ev = punta({ home: 1.3, draw: 5.0, away: 7.5 });
        expect(ev.state).toBe('no');
        expect(ev.checks.filter((c) => c.ok === false).map((c) => c.id)).toEqual(['favPre']);
    });
    it('sfavorita oltre 8 → no, per il solo check dogPre', () => {
        const ev = punta({ home: 1.45, draw: 4.5, away: 8.5 });
        expect(ev.checks.filter((c) => c.ok === false).map((c) => c.id)).toEqual(['dogPre']);
    });
    it('le bande vengono dalla sezione BASE', () => {
        const p = mergeParams({ base: { favPreMin: 1.7 } });
        expect(punta({ home: 1.65, draw: 4.0, away: 5.5 }, p).state).toBe('no');
    });
});

describe('Q12 — tennis: quota pre-partita e sfavoriti estremi', () => {
    it('leader favorito → segnale', () => {
        const ev = evaluateTennis(tennis({ p1: 1.3, p2: 3.5 }), DEFAULT_PARAMS.tennis);
        expect(ev.state).toBe('signal');
        expect(ev.checks.find((c) => c.id === 'leaderPre')?.ok).toBe(true);
    });
    it('leader sfavorito estremo → no', () => {
        const ev = evaluateTennis(tennis({ p1: 5.5, p2: 1.15 }), DEFAULT_PARAMS.tennis);
        expect(ev.state).toBe('no');
        expect(ev.checks.find((c) => c.id === 'leaderPre')?.value).toBe('pre-partita 5,50');
    });
    it('dato assente → non blocca e lo dichiara', () => {
        for (const pre of [null, { p1: 1.5 }]) {
            const ev = evaluateTennis(tennis(pre), DEFAULT_PARAMS.tennis);
            expect(ev.state).toBe('signal');
            expect(ev.checks.find((c) => c.id === 'leaderPre')?.value).toBe(TENNIS_PRE_ASSENTE);
        }
    });
    it('0 = spento', () => {
        const p = mergeParams({ tennis: { leaderPreMax: 0 } });
        const ev = evaluateTennis(tennis({ p1: 9, p2: 1.05 }), p.tennis);
        expect(ev.state).toBe('signal');
        expect(ev.checks.find((c) => c.id === 'leaderPre')).toBeUndefined();
    });
    it('vantaggio di game resta 2', () => {
        expect(DEFAULT_PARAMS.tennis.gamesLeadMin).toBe(2);
    });
});
