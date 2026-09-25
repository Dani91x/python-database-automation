// Q4 (ordine dell'utente 25/09) — veto dei campionati del corso, lato PAGINA.
// Gemello di `Betfair/safe_strategy/tests/test_safe_q1_q4_q5_2026_09_25.py`:
// stessi nomi, stessi esiti. La parità della LISTA la verifica il test Python
// che legge `vetoCampionati.ts`; qui si verifica il COMPORTAMENTO del motore.
import { describe, expect, it } from 'vitest';
import {
    buildFootballCtxFromScan,
    DEFAULT_PARAMS,
    evaluateBase,
    evaluateEsatto,
    evaluatePunta,
    mergeParams,
} from '@/lib/safeStrategy';
import { voceVietata } from '@/lib/vetoCampionati';

function scan(competition: string | null, over: Record<string, unknown> = {}) {
    return buildFootballCtxFromScan('ev1', {
        event_name: 'Nord FC v Sud FC', home: 'Nord FC', away: 'Sud FC',
        competition, open_date: '2026-09-02T16:00:00+00:00',
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
    } as Parameters<typeof buildFootballCtxFromScan>[1], 50, 60);
}

const PUNTA = {
    minute: 70, score_home: 2, score_away: 0,
    odds: { home: { back: 1.06, lay: 1.07 }, draw: { back: 20, lay: 22 }, away: { back: 60, lay: 70 } },
};

function treVarianti(competition: string | null, params = DEFAULT_PARAMS) {
    return {
        base: evaluateBase(scan(competition), params.base),
        esatto: evaluateEsatto(scan(competition, { minute: 49 }), params.esatto, 'home'),
        punta: evaluatePunta(scan(competition, PUNTA), params.punta),
    };
}

const VIETATI: Record<string, string> = {
    'Friendlies Women': 'veto campionato: calcio femminile (corso)',
    'Club Friendlies': 'veto campionato: amichevoli (corso)',
    'English FA Cup': 'veto campionato: coppe (corso)',
    'DFB Pokal': 'veto campionato: coppe (corso)',
    'Taça de Portugal': 'veto campionato: coppe (corso)',
    'UEFA Champions League': 'veto campionato: coppe (corso)',
    'German Bundesliga 2': 'veto campionato: Bundesliga 2 (corso)',
    '2. Bundesliga': 'veto campionato: Bundesliga 2 (corso)',
    'German Bundesliga': 'veto campionato: Bundesliga (corso)',
    'Dutch Eerste Divisie': 'veto campionato: Eerste Divisie (serie B olandese) (corso)',
    'Keuken Kampioen Divisie': 'veto campionato: Eerste Divisie (serie B olandese) (corso)',
    'Dutch Eredivisie': 'veto campionato: Eredivisie (corso)',
    'Bolivian Primera Division': 'veto campionato: campionato boliviano (corso)',
};

const LECITI = ['Italian Serie A', 'Italian Serie B', 'English Premier League', 'Spanish La Liga',
    'French Ligue 1', 'Austrian Bundesliga', 'German 3. Liga', 'Japanese J League', 'Cupertino League'];

describe('Q4 — veto dei campionati del corso (gemello del bot)', () => {
    for (const [nome, motivo] of Object.entries(VIETATI)) {
        it(`${nome} → scartata sulle tre varianti col motivo dichiarato`, () => {
            for (const ev of Object.values(treVarianti(nome))) {
                expect(ev.state).toBe('no');
                const ck = ev.checks.find((c) => c.id === 'campionato');
                expect(ck?.ok).toBe(false);
                expect(ck?.value).toBe(motivo);
                expect(ev.checks.filter((c) => c.ok === false).map((c) => c.id)).toEqual(['campionato']);
            }
        });
    }
    for (const nome of LECITI) {
        it(`${nome} → passa`, () => {
            expect(voceVietata(nome)).toBeNull();
            for (const ev of Object.values(treVarianti(nome))) expect(ev.state).toBe('signal');
        });
    }
    it('competizione assente → veto non applicabile (nessun check)', () => {
        for (const ev of Object.values(treVarianti(null))) {
            expect(ev.state).toBe('signal');
            expect(ev.checks.find((c) => c.id === 'campionato')).toBeUndefined();
        }
    });
    it('veto spento dai parametri → nessun check', () => {
        const p = mergeParams({ base: { vetoCampionati: false }, esatto: { vetoCampionati: false }, punta: { vetoCampionati: false } });
        for (const ev of Object.values(treVarianti('German Bundesliga', p))) expect(ev.state).toBe('signal');
    });
    it('acceso di default', () => {
        expect(DEFAULT_PARAMS.base.vetoCampionati).toBe(true);
        expect(DEFAULT_PARAMS.esatto.vetoCampionati).toBe(true);
        expect(DEFAULT_PARAMS.punta.vetoCampionati).toBe(true);
    });
});

describe('Q5 — tennis quota minima 1,02', () => {
    it('default 1.02', () => {
        expect(DEFAULT_PARAMS.tennis.backMin).toBe(1.02);
    });
});
