// 07/10 (decisione dell'utente) - Safe ESATTO entra SOLO nel 2o tempo.
// Gemello PAGINA di `Betfair/safe_strategy/tests/test_esatto_secondo_tempo_2026_10_07.py`:
// stessa chiave `secondHalf`, stessa etichetta, stessi esiti (vero / falso / n/d),
// nello stesso punto dell'elenco (subito dopo il check del minuto).
// Gli stati IPS sono quelli VERI della 35797769 (`statoIpsVero.testkit.ts`).
import { describe, expect, it } from 'vitest';
import {
    buildFootballCtxFromScan,
    DEFAULT_PARAMS,
    evaluateEsatto,
    evaluateFootballAll,
    SECONDO_TEMPO_STATO_ASSENTE,
} from '@/lib/safeStrategy';
import { tempoDaStatoIps } from '@/lib/faseIps';
import {
    statoIps2T,
    statoIpsIntervallo,
    statoIpsRecupero1T,
} from '@/lib/statoIpsVero.testkit';

type CalcioP = Parameters<typeof buildFootballCtxFromScan>[1];

/** Riga dello scanner con ESATTO "pronto" su ogni altro check (1-1, banca 30-70). */
function riga(over: Record<string, unknown> = {}) {
    return buildFootballCtxFromScan('35797769', {
        event_name: 'Spain v Belgium', home: 'Spain', away: 'Belgium',
        competition: 'World Cup', open_date: null, inplay: true,
        mo_market_id: '1.1', mo_status: 'OPEN',
        odds: {
            home: { back: 2.0, lay: 2.02 },
            draw: { back: 3.4, lay: 3.5 },
            away: { back: 4.0, lay: 4.2 },
        },
        minute: 48, score_home: 1, score_away: 1, red_home: 0, red_away: 0,
        pre_ko: { home: 1.65, draw: 4.0, away: 5.5 },
        cs: {
            market_id: '1.2', status: 'OPEN',
            any_other_home: { back: 30, lay: 32 }, any_other_away: { back: 40, lay: 42 },
        },
        ...over,
    } as CalcioP, 50, 60);
}

function esatto(over: Record<string, unknown> = {}) {
    return evaluateEsatto(riga(over), DEFAULT_PARAMS.esatto, 'home');
}
const check = (ev: ReturnType<typeof esatto>) => ev.checks.find((c) => c.id === 'secondHalf');

describe('ESATTO solo nel 2o tempo - check secondHalf (stati IPS veri)', () => {
    it('2T al 48 (SecondHalfKickOff): check vero e ESATTO pronto', () => {
        const ev = esatto({ score_raw: statoIps2T() });
        expect(check(ev)).toEqual({
            id: 'secondHalf', label: 'Solo nel 2° tempo',
            value: '2° tempo (SecondHalfKickOff)', ok: true,
        });
        expect(ev.state).toBe('signal');
    });

    it('recupero del 1T al 48 (KickOff, reg 45 +3): check falso, niente segnale', () => {
        const ev = esatto({ score_raw: statoIpsRecupero1T() });
        expect(check(ev)).toEqual({
            id: 'secondHalf', label: 'Solo nel 2° tempo',
            value: 'recupero del 1° tempo (KickOff)', ok: false,
        });
        expect(ev.state).toBe('no');
        expect(ev.headline).toBeNull();
    });

    it('intervallo (FirstHalfEnd, minuto 50 che continua a contare): falso', () => {
        const ev = esatto({ minute: 50, score_raw: statoIpsIntervallo() });
        expect(check(ev)?.value).toBe('intervallo (FirstHalfEnd)');
        expect(check(ev)?.ok).toBe(false);
        expect(ev.state).toBe('no');
    });

    it('stato IPS assente: n/d con le parole del bot, nessun ingresso', () => {
        const ev = esatto({ score_raw: undefined });
        expect(check(ev)).toEqual({
            id: 'secondHalf', label: 'Solo nel 2° tempo',
            value: 'n/d: stato IPS assente', ok: null,
        });
        expect(SECONDO_TEMPO_STATO_ASSENTE).toBe('n/d: stato IPS assente');
        expect(ev.state).toBe('nd');
        expect(ev.headline).toBeNull();
    });

    it('stato assente anche al 92: mai dedotto dal solo minuto (fail-closed)', () => {
        const ev = esatto({ minute: 92, score_raw: null });
        expect(check(ev)?.ok).toBeNull();
        expect(ev.state).toBe('nd');
    });

    it('stato presente ma non riconosciuto in zona ambigua: n/d', () => {
        const ev = esatto({ score_raw: { matchStatus: 'Mistero', timeElapsed: 48 } });
        expect(check(ev)).toMatchObject({ value: 'n/d: fase non riconosciuta (Mistero)', ok: null });
        expect(ev.state).toBe('nd');
    });

    it("stato 'KickOff' rimasto vecchio con minuto da 2T (88): ambiguo, n/d", () => {
        const ev = esatto({ minute: 88, score_raw: { ...statoIpsRecupero1T(), timeElapsed: 88, elapsedRegularTime: 35 } });
        expect(check(ev)?.ok).toBeNull();
        expect(ev.state).toBe('nd');
    });

    it('il check sta subito dopo quello del minuto; lo portano ESATTO e BASE (07/10), non la PUNTA', () => {
        const ev = esatto({ score_raw: statoIps2T() });
        const ids = ev.checks.map((c) => c.id);
        expect(ids.indexOf('secondHalf')).toBe(ids.indexOf('minute') + 1);
        const tutte = evaluateFootballAll(riga({ score_raw: statoIps2T() }), DEFAULT_PARAMS);
        for (const e of tutte) {
            expect(e.checks.some((c) => c.id === 'secondHalf')).toBe(e.variant === 'esatto' || e.variant === 'base');
        }
    });

    it('la soglia del minuto resta 48 (decisione: soglia invariata)', () => {
        expect(DEFAULT_PARAMS.esatto.minuteMin).toBe(48);
        expect(esatto({ minute: 47, score_raw: statoIps2T() }).state).toBe('no');
    });
});

describe('tempoDaStatoIps - gemello di atlante_v4.tempo_da_stato_ips', () => {
    // stessi casi di `test_atlante_v4_collegato_2026_09_25.py` e dei veri stati
    it('stati veri', () => {
        expect(tempoDaStatoIps(statoIpsRecupero1T(), 48)).toBe(1);
        expect(tempoDaStatoIps(statoIpsIntervallo(), 50)).toBe(1);
        expect(tempoDaStatoIps(statoIps2T(), 48)).toBe(2);
    });
    it('senza stato: minuto < 45 = 1T, >= 90 = 2T, 45-89 ambiguo, ignoto = null', () => {
        expect(tempoDaStatoIps(null, 30)).toBe(1);
        expect(tempoDaStatoIps({}, 90)).toBe(2);
        expect(tempoDaStatoIps({}, 60)).toBeNull();
        expect(tempoDaStatoIps(null, null)).toBeNull();
    });
    it("'KickOff' vecchio oltre il 60' non si crede; elapsedRegularTime decide", () => {
        expect(tempoDaStatoIps({ matchStatus: 'KickOff' }, 61)).toBeNull();
        expect(tempoDaStatoIps({ matchStatus: 'KickOff', elapsedRegularTime: 90, elapsedAddedTime: 2 }, 92)).toBe(2);
        expect(tempoDaStatoIps({ elapsedRegularTime: 45, elapsedAddedTime: 2 }, 47)).toBe(1);
        expect(tempoDaStatoIps({ elapsedRegularTime: '45', elapsedAddedTime: 2 }, '47')).toBe(1);
    });
    it('stati del 2T e dell\'intervallo con nomi alternativi', () => {
        expect(tempoDaStatoIps({ status: 'ExtraTimeFirstHalf' }, 100)).toBe(2);
        expect(tempoDaStatoIps({ matchStatus: 'Half Time' }, 50)).toBe(1);
        expect(tempoDaStatoIps({ matchStatus: 'HalfTime' }, 50)).toBe(1);
        expect(tempoDaStatoIps({ matchStatus: 'FirstHalf' }, 30)).toBe(1);
    });
});
