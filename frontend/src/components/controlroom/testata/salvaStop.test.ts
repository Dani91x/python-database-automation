// ============================================================================
// salvaStop.test.ts - 01/10: lo stop modificato dalla testata passa dalle
// STESSE RPC, con le STESSE chiavi, dei fogli parametri e del pannello del
// conto. Il client Supabase e' finto (`rpc` registra nome e argomenti) e
// risponde con righe dalle chiavi delle tabelle vere:
//  - set_live_settings -> to_jsonb(betfair_live_settings) (id, kill_switch,
//    max_exposure_per_selection, max_orders_per_min, order_poll_sec,
//    risk_poll_sec, daily_loss_limit, max_exposure_per_event,
//    max_exposure_per_league, updated_at) - migrations/betfair_live_risk_limits_v4.sql;
//  - safe/mike/omega_update_params -> to_jsonb della riga di control (id,
//    status, mode, params, stats, error, started_at, stopped_at,
//    heartbeat_at, updated_at [+ daily_goal per Omega]).
// Le funzioni di merge (mergeBotParams, toValues/fromValues, mergeMikeParams,
// omegaParamsPatch) sono quelle VERE.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

const rpc = vi.hoisted(() => vi.fn());
vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc } }));

import { leggiImporto, payloadStop, salvaStop, chiaveStopOmega, StopNonSalvabile } from './salvaStop';
import { toValues, fromValues, mergeExits } from '@/components/safestrategy/BotParamsSheet';
import { mergeBotParams } from '@/lib/safeBot';
import { mergeMikeParams } from '@/lib/mike';
import { omegaParamsPatch } from '@/lib/omega';

const RIGA_SETTINGS = {
    id: 1, kill_switch: false, max_exposure_per_selection: null, max_orders_per_min: null,
    order_poll_sec: null, risk_poll_sec: null, daily_loss_limit: null,
    max_exposure_per_event: null, max_exposure_per_league: null,
    updated_at: '2026-10-01T08:00:00+00:00',
};
function control(params: Record<string, unknown>, extra: Record<string, unknown> = {}) {
    return {
        id: 1, status: 'stopped', mode: 'paper', params, stats: null, error: null,
        started_at: null, stopped_at: null, heartbeat_at: null, updated_at: '2026-10-01T08:00:00+00:00', ...extra,
    };
}

// parametri grezzi come li scrive il DB (chiavi di produzione, con una chiave
// ignota a mergeBotParams che il salvataggio deve conservare)
const SAFE_RAW: Record<string, unknown> = {
    variants: ['base', 'tennis'],
    risk: { daily_loss_stop: -50, daily_liability_cap: 500 },
    strategy_modes: { tennis: 'live' },
    tennis_exit_approval: true,
    exits: { enabled: true },
    chiave_del_servizio_ignota: 7,
};
const MIKE_RAW: Record<string, unknown> = { daily_loss_stop: 50, max_open_matches: 10 };
const OMEGA_RAW: Record<string, unknown> = { strategy_version: 3, v3_daily_loss_cap: 300, daily_loss_cap: 0, stake: 2 };

beforeEach(() => { rpc.mockReset(); });

/**
 * R-05 (rilievi bassi 01/10): prima di scrivere lo stop di un bot si rilegge lo
 * stato del servizio. Risposte con le chiavi delle RPC vere: `get_safe_state`
 * e `get_mike_state` -> { control, trades, aggregates, activity, ... };
 * `get_omega_state` -> { control, aggregates, activity, activity_more, ... }.
 */
function statoServizio(params: Record<string, unknown>) {
    return {
        control: control(params), trades: [], aggregates: null, activity: [],
        activity_more: 0, activity_day: '2026-10-01', goal_today: null, goal_snapshot: false,
        events: [], requests: [], day_start: null, day_by: null,
    };
}

describe('leggiImporto - euro al centesimo, negativo = perdita massima', () => {
    it('-40, −40,5, 40 sono la stessa perdita; 3 decimali rifiutati', () => {
        expect(leggiImporto('-40', 'mike')).toEqual({ ok: true, perdita: 40 });
        expect(leggiImporto('−40,5', 'mike')).toEqual({ ok: true, perdita: 40.5 });
        expect(leggiImporto('40', 'omega')).toEqual({ ok: true, perdita: 40 });
        expect(leggiImporto('-40,555', 'mike').ok).toBe(false);
        expect(leggiImporto('abc', 'mike').ok).toBe(false);
    });
    it('conto: vuoto = spento, 0 rifiutato (regola di LiveControlsPanel); bot: 0 = spento, vuoto rifiutato', () => {
        expect(leggiImporto('', 'conto')).toEqual({ ok: true, perdita: null });
        expect(leggiImporto('0', 'conto').ok).toBe(false);
        expect(leggiImporto('0', 'safe')).toEqual({ ok: true, perdita: null });
        expect(leggiImporto('', 'safe').ok).toBe(false);
    });
    it('oltre il tetto del foglio (Mike 100000) rifiutato', () => {
        expect(leggiImporto('-100001', 'mike').ok).toBe(false);
    });
    // R-04 (review 01/10): i punti delle migliaia della forma it-IT
    it('R-04: «12.500,00» (migliaia + virgola decimale) = 12500; «-1.234.567,5» = 1234567,5', () => {
        expect(leggiImporto('-12.500,00', 'safe')).toEqual({ ok: true, perdita: 12500 });
        expect(leggiImporto('12.500,5', 'conto')).toEqual({ ok: true, perdita: 12500.5 });
        expect(leggiImporto('−12.500,00 €', 'omega')).toEqual({ ok: true, perdita: 12500 });
        // letto come 1234567,5 e rifiutato per il TETTO (1.000.000), non come «non valido»
        expect(leggiImporto('-1.234.567,5', 'conto')).toEqual({ ok: false, errore: expect.stringMatching(/oltre il massimo/) });
        expect(leggiImporto('-999.999,99', 'conto')).toEqual({ ok: true, perdita: 999999.99 });
    });
    it('R-04: «12.500» senza virgola = 12500 SOLO con esattamente 3 cifre dopo ogni punto', () => {
        expect(leggiImporto('-12.500', 'safe')).toEqual({ ok: true, perdita: 12500 });
        expect(leggiImporto('1.000', 'omega')).toEqual({ ok: true, perdita: 1000 });
        // il punto decimale di prima resta com'era: 1 o 2 cifre = centesimi
        expect(leggiImporto('-12.50', 'safe')).toEqual({ ok: true, perdita: 12.5 });
        expect(leggiImporto('-12.5', 'safe')).toEqual({ ok: true, perdita: 12.5 });
        // forme non di migliaia: rifiutate come prima
        expect(leggiImporto('-12.5000', 'safe').ok).toBe(false);
        expect(leggiImporto('-1.2,50', 'safe').ok).toBe(false);
        expect(leggiImporto('-12,500', 'safe').ok).toBe(false);
        expect(leggiImporto('-12.500.0', 'safe').ok).toBe(false);
    });
});

describe('payloadStop - lo STESSO payload del foglio del proprietario', () => {
    it('Safe: identico a BotParamsSheet.save con il solo stop cambiato (chiavi ignote conservate)', () => {
        const atteso = (() => {
            const p = mergeBotParams(SAFE_RAW);
            const v = toValues(p, mergeExits(SAFE_RAW.exits), SAFE_RAW);
            v['risk.daily_loss_stop'] = -40;
            // R-06 (01/10): anche il foglio, ora, lascia ASSENTE la chiave
            // `risk.max_open_trades` assente nel database: nessuna eccezione qui.
            return fromValues(v, p.variants, SAFE_RAW);
        })();
        const payload = payloadStop('safe', 40, SAFE_RAW);
        expect(payload).toEqual(atteso);
        expect((payload.risk as Record<string, unknown>).daily_loss_stop).toBe(-40);
        expect('max_open_trades' in (payload.risk as Record<string, unknown>)).toBe(false);
        expect(payload.chiave_del_servizio_ignota).toBe(7);
        expect(payload.strategy_modes).toEqual({ tennis: 'live' });
    });
    it('Safe: identico al foglio anche con il tetto delle posizioni nel database (5 e 0)', () => {
        for (const n of [5, 0]) {
            const raw: Record<string, unknown> = { ...SAFE_RAW, risk: { daily_loss_stop: -50, max_open_trades: n } };
            const p = mergeBotParams(raw);
            const v = toValues(p, mergeExits(raw.exits), raw);
            v['risk.daily_loss_stop'] = -40;
            const payload = payloadStop('safe', 40, raw);
            expect(payload).toEqual(fromValues(v, p.variants, raw));
            expect((payload.risk as Record<string, unknown>).max_open_trades).toBe(n);
        }
    });
    it('Mike: mergeMikeParams del foglio con daily_loss_stop positivo', () => {
        expect(payloadStop('mike', 40, MIKE_RAW)).toEqual(mergeMikeParams({ ...mergeMikeParams(MIKE_RAW), daily_loss_stop: 40 }));
    });
    it('Omega: omegaParamsPatch con la chiave del motore in uso (v3 -> v3_daily_loss_cap; v2 -> daily_loss_cap)', () => {
        expect(payloadStop('omega', 120, OMEGA_RAW)).toEqual(omegaParamsPatch(OMEGA_RAW, { v3_daily_loss_cap: 120 }));
        const v2 = { ...OMEGA_RAW, strategy_version: 2 };
        expect(chiaveStopOmega(v2)).toBe('daily_loss_cap');
        expect(payloadStop('omega', 120, v2).daily_loss_cap).toBe(120);
        expect(payloadStop('omega', 120, v2).v3_daily_loss_cap).toBe(300);
    });
    it('0 / spento: Safe 0, Mike 0, Omega 0 (la convenzione "0 = OFF" dei fogli)', () => {
        expect(((payloadStop('safe', null, SAFE_RAW).risk) as Record<string, unknown>).daily_loss_stop).toBe(0);
        expect(payloadStop('mike', null, MIKE_RAW).daily_loss_stop).toBe(0);
        expect(payloadStop('omega', null, OMEGA_RAW).v3_daily_loss_cap).toBe(0);
    });
    it('CANCELLO: parametri non letti (null o {}) -> rifiuta, mai i predefiniti al posto dei veri', () => {
        expect(() => payloadStop('safe', 40, null)).toThrow(StopNonSalvabile);
        expect(() => payloadStop('mike', 40, {})).toThrow(StopNonSalvabile);
        expect(() => payloadStop('omega', 40, null)).toThrow(StopNonSalvabile);
    });
});

describe('salvaStop - RPC vere, chiavi vere, cifra dal database', () => {
    it('conto: set_live_settings({ p: { daily_loss_limit } }) e SOLO quella chiave; ritorna la cifra della riga', async () => {
        rpc.mockResolvedValueOnce({ data: { ...RIGA_SETTINGS, daily_loss_limit: 35 }, error: null });
        const v = await salvaStop('conto', 40, null);
        expect(rpc).toHaveBeenCalledWith('set_live_settings', { p: { daily_loss_limit: 40 } });
        expect(v).toBe(35);
    });
    it('conto spento: daily_loss_limit null; la riga del DB vale null -> null', async () => {
        rpc.mockResolvedValueOnce({ data: RIGA_SETTINGS, error: null });
        expect(await salvaStop('conto', null, null)).toBeNull();
        expect(rpc).toHaveBeenCalledWith('set_live_settings', { p: { daily_loss_limit: null } });
    });
    it('conto: digitato SPENTO ma la riga del DB dice 25 -> vale 25 (la riga, mai il digitato)', async () => {
        rpc.mockResolvedValueOnce({ data: { ...RIGA_SETTINGS, daily_loss_limit: 25 }, error: null });
        expect(await salvaStop('conto', null, null)).toBe(25);
    });
    // R-05: la scrittura e' la SECONDA chiamata (la prima rilegge lo stato)
    it('Safe: safe_update_params({ p_params }) col payload del foglio; ritorna |risk.daily_loss_stop| della riga', async () => {
        rpc.mockResolvedValueOnce({ data: statoServizio(SAFE_RAW), error: null });
        rpc.mockResolvedValueOnce({ data: control({ ...SAFE_RAW, risk: { daily_loss_stop: -45 } }), error: null });
        const v = await salvaStop('safe', 40, SAFE_RAW);
        expect(rpc.mock.calls[0][0]).toBe('get_safe_state');
        expect(rpc.mock.calls[1][0]).toBe('safe_update_params');
        expect(rpc.mock.calls[1][1]).toEqual({ p_params: payloadStop('safe', 40, SAFE_RAW) });
        // la cifra e' quella RESTITUITA (45), non quella digitata (40)
        expect(v).toBe(45);
    });
    it('Mike: mike_update_params({ p_params, p_mode: null }): la modalita\' non si tocca', async () => {
        rpc.mockResolvedValueOnce({ data: statoServizio(MIKE_RAW), error: null });
        rpc.mockResolvedValueOnce({ data: control({ ...MIKE_RAW, daily_loss_stop: 35 }), error: null });
        expect(await salvaStop('mike', 40, MIKE_RAW)).toBe(35);
        expect(rpc.mock.calls[0][0]).toBe('get_mike_state');
        expect(rpc.mock.calls[1][0]).toBe('mike_update_params');
        expect(rpc.mock.calls[1][1]).toEqual({ p_params: payloadStop('mike', 40, MIKE_RAW), p_mode: null });
    });
    it('Omega: omega_update_params con p_daily_goal null (obiettivo intatto) e p_mode null', async () => {
        rpc.mockResolvedValueOnce({ data: statoServizio(OMEGA_RAW), error: null });
        rpc.mockResolvedValueOnce({ data: control({ ...OMEGA_RAW, v3_daily_loss_cap: 110 }, { daily_goal: 250 }), error: null });
        expect(await salvaStop('omega', 120, OMEGA_RAW)).toBe(110);
        expect(rpc.mock.calls[0][0]).toBe('get_omega_state');
        expect(rpc).toHaveBeenCalledWith('omega_update_params', {
            p_daily_goal: null, p_params: payloadStop('omega', 120, OMEGA_RAW), p_mode: null,
        });
    });
    it('errore della RPC: si propaga (il componente lo scrive), nessun esito inventato', async () => {
        rpc.mockResolvedValueOnce({ data: null, error: { message: 'non autorizzato (owner-only)' } });
        await expect(salvaStop('conto', 40, null)).rejects.toThrow(/owner-only/);
    });
    it('parametri non letti: nessuna RPC parte', async () => {
        await expect(salvaStop('mike', 40, null)).rejects.toThrow(StopNonSalvabile);
        expect(rpc).not.toHaveBeenCalled();
    });
});

// R-06 (rilievi bassi 01/10): il confronto dei predefiniti frontend/Python ha
// trovato UNA differenza che sovrascrive un valore vero: `risk.max_open_trades`
// di Safe (frontend 0 = nessun tetto; Python assente = tetto del bot, 20).
// FALSIFICAZIONE: togliendo la correzione in `payloadStop` i due test diventano
// rossi (il payload porta `risk.max_open_trades: 0`).
describe('R-06: salvare lo stop di Safe non tocca il tetto delle posizioni aperte', () => {
    it('chiave ASSENTE nel database: resta assente (il servizio usa il tetto del bot)', () => {
        const p = payloadStop('safe', 40, SAFE_RAW) as { risk: Record<string, unknown> };
        expect('max_open_trades' in p.risk).toBe(false);
        expect(p.risk.daily_loss_stop).toBe(-40);
        expect(p.risk.daily_liability_cap).toBe(500);
    });
    it('chiave PRESENTE (5): resta 5, mai 0 (= nessun tetto)', () => {
        const raw = { ...SAFE_RAW, risk: { daily_loss_stop: -50, max_open_trades: 5 } };
        const p = payloadStop('safe', 40, raw) as { risk: Record<string, unknown> };
        expect(p.risk.max_open_trades).toBe(5);
        // e la riga letta non viene toccata
        expect((raw.risk as Record<string, unknown>).daily_loss_stop).toBe(-50);
    });
});

// R-05 (rilievi bassi 01/10). FALSIFICAZIONE: componendo il payload su `raw`
// (i parametri della pagina) invece che sulla riga riletta, il primo test
// diventa rosso; togliendo la rilettura, rossi anche gli altri due.
describe('R-05: prima di scrivere si RILEGGONO i parametri del bot', () => {
    it('Mike: un foglio ha cambiato max_open_matches (10 -> 12) dopo la lettura della pagina: il 12 resta', async () => {
        const nelDb = { ...MIKE_RAW, max_open_matches: 12 };
        rpc.mockResolvedValueOnce({ data: statoServizio(nelDb), error: null });
        rpc.mockResolvedValueOnce({ data: control({ ...nelDb, daily_loss_stop: 40 }), error: null });
        await salvaStop('mike', 40, MIKE_RAW);   // la pagina ha ancora 10
        const scritto = rpc.mock.calls[1][1].p_params as Record<string, unknown>;
        expect(scritto.max_open_matches).toBe(12);
        expect(scritto.daily_loss_stop).toBe(40);
        expect(scritto).toEqual(payloadStop('mike', 40, nelDb));
    });
    it('Safe: una strategia aggiunta nel frattempo (punta) non si perde', async () => {
        const nelDb = { ...SAFE_RAW, variants: ['base', 'tennis', 'punta'] };
        rpc.mockResolvedValueOnce({ data: statoServizio(nelDb), error: null });
        rpc.mockResolvedValueOnce({ data: control({ ...nelDb, risk: { daily_loss_stop: -40 } }), error: null });
        await salvaStop('safe', 40, SAFE_RAW);
        const scritto = rpc.mock.calls[1][1].p_params as Record<string, unknown>;
        expect(scritto.variants).toEqual(['base', 'tennis', 'punta']);
    });
    it('rilettura FALLITA o VUOTA: niente scrittura, e il motivo si legge', async () => {
        rpc.mockResolvedValueOnce({ data: null, error: { message: 'rete giu' } });
        await expect(salvaStop('omega', 120, OMEGA_RAW)).rejects.toThrow(/non riletti prima di salvare \(rete giu\)/);
        expect(rpc).toHaveBeenCalledTimes(1);
        rpc.mockReset();
        rpc.mockResolvedValueOnce({ data: statoServizio({}), error: null });
        await expect(salvaStop('safe', 40, SAFE_RAW)).rejects.toThrow(StopNonSalvabile);
        expect(rpc).toHaveBeenCalledTimes(1);
        expect(rpc.mock.calls[0][0]).toBe('get_safe_state');
    });
});
