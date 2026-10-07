// 07/10 sera (decisione dell'utente: "SAFE BASE SEMPRE E SOLO SECONDO TEMPO").
// Gemello PAGINA di `Betfair/safe_strategy/tests/test_base_secondo_tempo_2026_10_07.py`:
// stesso check `secondHalf` dell'ESATTO nella valutazione della BASE, subito dopo
// il minuto. Caso del reperto: all'INTERVALLO ('FirstHalfEnd') il minuto del feed
// continua a contare (fino a 56'), la soglia del 55' da sola faceva entrare la BASE.
// Stati IPS: forma vera della 35797769 (`statoIpsVero.testkit.ts`), minuto 55.
import { describe, expect, it } from 'vitest';
import {
    buildFootballCtxFromScan,
    DEFAULT_PARAMS,
    evaluateBase,
    evaluatePunta,
    SECONDO_TEMPO_STATO_ASSENTE,
} from '@/lib/safeStrategy';
import {
    statoIps2T,
    statoIpsIntervallo,
    statoIpsRecupero1T,
} from '@/lib/statoIpsVero.testkit';

type CalcioP = Parameters<typeof buildFootballCtxFromScan>[1];

/** Riga dello scanner con la BASE "pronta" su ogni altro check: favorita
 *  (pre 1,65) avanti 1-0, banca della sfavorita 25 (dentro 20-34). */
function riga(over: Record<string, unknown> = {}) {
    return buildFootballCtxFromScan('35797769', {
        event_name: 'Nord FC v Sud FC', home: 'Nord FC', away: 'Sud FC',
        competition: 'Serie A', open_date: null, inplay: true,
        mo_market_id: '1.1', mo_status: 'OPEN',
        odds: {
            home: { back: 1.28, lay: 1.3 },
            draw: { back: 5.0, lay: 5.2 },
            away: { back: 24.0, lay: 25.0 },
        },
        minute: 55, score_home: 1, score_away: 0, red_home: 0, red_away: 0,
        pre_ko: { home: 1.65, draw: 4.0, away: 5.5 },
        cs: null,
        ...over,
    } as CalcioP, 50, 60);
}

const base = (over: Record<string, unknown> = {}) => evaluateBase(riga(over), DEFAULT_PARAMS.base);
const check = (ev: ReturnType<typeof base>) => ev.checks.find((c) => c.id === 'secondHalf');

const intervallo55 = () => ({ ...statoIpsIntervallo(), timeElapsed: 55 });
const recupero55 = () => ({ ...statoIpsRecupero1T(), timeElapsed: 55, elapsedAddedTime: 10 });
const secondo55 = () => ({ ...statoIps2T(), timeElapsed: 55, elapsedRegularTime: 55 });

describe('BASE solo nel 2o tempo - check secondHalf', () => {
    it('intervallo al 55 (FirstHalfEnd): falso, nessun segnale', () => {
        const ev = base({ score_raw: intervallo55() });
        expect(check(ev)).toEqual({
            id: 'secondHalf', label: 'Solo nel 2\u00b0 tempo',
            value: 'intervallo (FirstHalfEnd)', ok: false,
        });
        expect(ev.state).toBe('no');
        expect(ev.headline).toBeNull();
    });

    it('recupero del 1T al 55 (KickOff, reg 45 +10): falso', () => {
        const ev = base({ score_raw: recupero55() });
        expect(check(ev)?.value).toBe('recupero del 1\u00b0 tempo (KickOff)');
        expect(ev.state).toBe('no');
    });

    it('2T al 55 (SecondHalfKickOff): vero, BASE pronta come prima', () => {
        const ev = base({ score_raw: secondo55() });
        expect(check(ev)?.ok).toBe(true);
        expect(ev.state).toBe('signal');
        expect(ev.entryOdds).toBe(25);
    });

    it('stato IPS assente: n/d, nessun ingresso, anche al 92', () => {
        for (const minute of [55, 92]) {
            const ev = base({ minute, score_raw: undefined });
            expect(check(ev)).toMatchObject({ value: SECONDO_TEMPO_STATO_ASSENTE, ok: null });
            expect(ev.state).toBe('nd');
        }
    });

    it('subito dopo il minuto; soglia del 55 invariata', () => {
        const ids = base({ score_raw: secondo55() }).checks.map((c) => c.id);
        expect(ids.indexOf('secondHalf')).toBe(ids.indexOf('minute') + 1);
        expect(DEFAULT_PARAMS.base.minuteMin).toBe(55);
        expect(base({ minute: 54, score_raw: { ...secondo55(), timeElapsed: 54 } }).state).toBe('no');
    });

    it('la PUNTA non porta il check', () => {
        const ev = evaluatePunta(riga({ minute: 70, score_raw: intervallo55() }), DEFAULT_PARAMS.punta, DEFAULT_PARAMS.base);
        expect(ev.checks.some((c) => c.id === 'secondHalf')).toBe(false);
    });
});
