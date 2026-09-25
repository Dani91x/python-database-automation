// ============================================================================
// runnerCanale.test.ts - 25/09 (voce 6): runner e modo ordini dal canale.
//
// Finti = messaggi VERI dei runner:
//  - hello: Betfair/stream/local_channel.py:353 {"sport", **hello_extra};
//    hello_extra = {"mode": <LIVE_ORDER_MODE>} (runner.py:1798,
//    tennis_live/tennis_runner.py:1790);
//  - now calcio: Betfair/stream/db.py:294-309 riga di `live_now`
//    {event_id, inplay, minute, score_home, score_away, status, score_source,
//     state, updated_at}; `state` = runner.py:259-303 `build_live_state`
//    {markets, order_mode, order_mode_tetto, order_mode_scelto, updated_ms}.
//  - riga del database del battito: `lib/safeBot.fetchRunnerState` (ts, mode
//    'LIVE+PAPER' = runner.heartbeat_mode, streaming dal conteggio live_follow).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    runnerDalCanale, leggiModoDalNow, sovrapponiModoOrdini, NOTIZIE_VUOTE,
    FLUSSO_VIVO_S, MODO_CANALE_VALIDO_S, leggiBattito, leggiModoOrdiniCanale,
} from './runnerCanale';
import { statoOrdiniReali } from './interruttori';
import type { RunnerState } from './safeBot';
// 25/09 (punto 6): messaggi VERI generati dal codice Python (chiavi e tipi
// controllati da Betfair/stream/tests/test_punto6_battito_modo_ordini_2026_09_25.py)
import finti from './__fixtures__/runnerCanaleFinti.json';

const NOW = Date.parse('2026-09-25T13:00:00Z');

const DB: RunnerState = { ts: '2026-09-25T12:59:20Z', mode: 'LIVE+PAPER', ageS: 5, up: true, streaming: 0 };

function nowCalcio(state: Record<string, unknown>) {
    return {
        event_id: '34567890', inplay: true, minute: 12, score_home: 0, score_away: 0,
        status: 'OPEN', score_source: 'ips',
        state: { markets: [], ...state },
        updated_at: '2026-09-25T12:59:59.000000+00:00',
    };
}

describe('runnerDalCanale', () => {
    it('canale spento: la riga del database, eta\' ricalcolata ADESSO (non quella congelata)', () => {
        const v = runnerDalCanale(DB, NOTIZIE_VUOTE, NOW);
        expect(v.fonte).toBe('database');
        expect(v.runner?.ageS).toBe(40);
        expect(v.etaS).toBe(40);
        expect(v.runner?.mode).toBe('LIVE+PAPER');
        expect(v.runner?.streaming).toBe(0);
    });
    it('canale spento e database mai letto: non noto', () => {
        expect(runnerDalCanale(null, NOTIZIE_VUOTE, NOW)).toEqual({ runner: null, fonte: 'database', etaS: null });
    });
    it('canale collegato: vivo, eta\' dell\'ultimo messaggio, modalita\' del database', () => {
        const v = runnerDalCanale(DB, {
            connesso: true, hello: { sport: 'calcio', mode: 'LIVE' }, ultimoMsgMs: NOW - 3000, ultimoFlussoMs: null,
        }, NOW);
        expect(v.fonte).toBe('canale');
        expect(v.runner?.up).toBe(true);
        expect(v.runner?.ageS).toBe(3);
        expect(v.runner?.mode).toBe('LIVE+PAPER');
        // nessun flusso: resta lo streaming del database (il silenzio non toglie)
        expect(v.runner?.streaming).toBe(0);
    });
    it('ladder/now recenti: in streaming anche se il database dice 0', () => {
        const v = runnerDalCanale(DB, {
            connesso: true, hello: { sport: 'calcio', mode: 'LIVE' }, ultimoMsgMs: NOW - 200, ultimoFlussoMs: NOW - 200,
        }, NOW);
        expect(v.runner?.streaming).toBe(1);
    });
    it('flusso piu\' vecchio della soglia: non vale streaming', () => {
        const v = runnerDalCanale(DB, {
            connesso: true, hello: null, ultimoMsgMs: NOW - 1000, ultimoFlussoMs: NOW - (FLUSSO_VIVO_S + 1) * 1000,
        }, NOW);
        expect(v.runner?.streaming).toBe(0);
    });
    it('runner tennis (nessuna riga di database): dal solo canale, modalita\' dall\'hello', () => {
        const v = runnerDalCanale(null, {
            connesso: true, hello: { sport: 'tennis', mode: 'paper' }, ultimoMsgMs: NOW - 2000, ultimoFlussoMs: null,
        }, NOW);
        expect(v.runner?.mode).toBe('PAPER');
        expect(v.runner?.up).toBe(true);
        expect(v.runner?.streaming).toBeNull();
    });
});

describe('leggiModoDalNow', () => {
    it('legge effettivo/tetto/scelta dal `state` del now', () => {
        const m = leggiModoDalNow(nowCalcio({
            order_mode: 'PAPER', order_mode_tetto: 'LIVE', order_mode_scelto: 'PAPER', updated_ms: NOW - 1000,
        }));
        expect(m).toEqual({ effettivo: 'PAPER', tetto: 'LIVE', scelto: 'PAPER', ms: NOW - 1000 });
    });
    it('runner di prima (senza order_mode) o riga storta: null', () => {
        expect(leggiModoDalNow(nowCalcio({ updated_ms: NOW }))).toBeNull();
        expect(leggiModoDalNow({ state: null })).toBeNull();
        expect(leggiModoDalNow(nowCalcio({ order_mode: 'PAPER' }))).toBeNull();
    });
});

describe('sovrapponiModoOrdini', () => {
    const riga = {
        id: 1, kill_switch: false, max_exposure_per_selection: null, max_orders_per_min: null,
        order_poll_sec: null, risk_poll_sec: null, daily_loss_limit: null, max_exposure_per_event: null,
        max_exposure_per_league: null, updated_at: '2026-09-25T12:00:00Z',
        order_mode: 'paper', order_mode_updated_at: '2026-09-25T12:00:00Z', order_mode_updated_by: 'avvio_app',
        order_mode_boot_id: 'b1', order_mode_tetto: 'LIVE', order_mode_tetto_at: '2026-09-25T11:59:00Z',
    };
    const st = statoOrdiniReali(riga);
    const letto = NOW - 20_000;

    it('canale spento: la lettura del database, eta\' della lettura', () => {
        const v = sovrapponiModoOrdini(st, letto, { connesso: false, hello: null, modo: null }, NOW);
        expect(v.fonte).toBe('database');
        expect(v.effettivo).toBe('PAPER');
        expect(v.etaS).toBe(20);
        expect(v.daRileggere).toBe(false);
    });
    it('riga mai letta: il canale non inventa una lettura', () => {
        const v = sovrapponiModoOrdini(statoOrdiniReali(null), null, {
            connesso: true, hello: { mode: 'LIVE' },
            modo: { effettivo: 'LIVE', tetto: 'LIVE', scelto: 'LIVE', ms: NOW },
        }, NOW);
        expect(v.letto).toBe(false);
        expect(v.effettivo).toBe('OFF');
        expect(v.fonte).toBe('database');
    });
    it('now fresco: effettivo del runner; scelta diversa -> da rileggere', () => {
        const v = sovrapponiModoOrdini(st, letto, {
            connesso: true, hello: { sport: 'calcio', mode: 'LIVE' },
            modo: { effettivo: 'LIVE', tetto: 'LIVE', scelto: 'LIVE', ms: NOW - 1000 },
        }, NOW);
        expect(v.fonte).toBe('canale');
        expect(v.effettivo).toBe('LIVE');
        expect(v.etaS).toBe(1);
        expect(v.daRileggere).toBe(true);
        // la scelta (con chi/quando) resta del database finche' non si rilegge
        expect(v.scelto).toBe('PAPER');
    });
    it('now vecchio (oltre la validita\') o precedente alla lettura: resta il database', () => {
        for (const ms of [NOW - (MODO_CANALE_VALIDO_S + 1) * 1000, letto - 1]) {
            const v = sovrapponiModoOrdini(st, letto, {
                connesso: true, hello: { mode: 'LIVE' },
                modo: { effettivo: 'LIVE', tetto: 'LIVE', scelto: 'LIVE', ms },
            }, NOW);
            expect(v.fonte).toBe('database');
            expect(v.effettivo).toBe('PAPER');
            expect(v.daRileggere).toBe(false);
        }
    });
    it('tetto dall\'hello del runner collegato (il SUO .env)', () => {
        const v = sovrapponiModoOrdini(st, letto, { connesso: true, hello: { mode: 'PAPER' }, modo: null }, NOW);
        expect(v.tetto).toBe('PAPER');
        expect(v.effettivo).toBe('PAPER');
        expect(v.fonte).toBe('canale');
    });
});

// ------------------------------------------------ 25/09 punto 6: battito
describe('leggiBattito (topic `battito`, canale_bot.battito_runner)', () => {
    it('il messaggio vero: ts, mode, streaming', () => {
        expect(leggiBattito(finti.battito)).toEqual({ ts: finti.battito.ts, mode: 'LIVE+PAPER', streaming: 2 });
    });
    it('senza ts numerico non e\' un battito', () => {
        const senzaTs: Record<string, unknown> = { ...finti.battito };
        delete senzaTs.ts;
        expect(leggiBattito(senzaTs)).toBeNull();
        expect(leggiBattito({ ...finti.battito, ts: 'ieri' })).toBeNull();
        expect(leggiBattito(null)).toBeNull();
    });
    it('streaming null (non contabile) resta null, mai zero inventato', () => {
        expect(leggiBattito({ ...finti.battito, streaming: null })?.streaming).toBeNull();
    });
});

describe('runnerDalCanale con il battito', () => {
    const conn = { connesso: true, hello: { sport: 'calcio', mode: 'LIVE' }, ultimoFlussoMs: null };
    it('battito piu\' recente della riga del database: mode e streaming dal battito (oggetto intero)', () => {
        const b = leggiBattito(finti.battito)!;               // ts = NOW - 2 s, streaming 2
        const v = runnerDalCanale({ ...DB, mode: 'PAPER', streaming: 0 }, {
            ...conn, ultimoMsgMs: NOW - 2000, battito: b,
        }, NOW);
        expect(v.fonte).toBe('canale');
        expect(v.runner?.mode).toBe('LIVE+PAPER');
        expect(v.runner?.streaming).toBe(2);
        expect(v.etaS).toBe(2);
    });
    it('battito piu\' vecchio della riga del database: resta tutto il database', () => {
        const b = { ...leggiBattito(finti.battito)!, ts: Date.parse(DB.ts!) - 1000 };
        const v = runnerDalCanale({ ...DB, mode: 'PAPER', streaming: 0 }, {
            ...conn, ultimoMsgMs: NOW - 1000, battito: b,
        }, NOW);
        expect(v.runner?.mode).toBe('PAPER');
        expect(v.runner?.streaming).toBe(0);
    });
    it('battito con streaming non contabile: resta il numero del database', () => {
        const b = { ...leggiBattito(finti.battito)!, streaming: null };
        const v = runnerDalCanale({ ...DB, streaming: 3 }, { ...conn, ultimoMsgMs: NOW, battito: b }, NOW);
        expect(v.runner?.streaming).toBe(3);
        expect(v.runner?.mode).toBe('LIVE+PAPER');
    });
    it('runner tennis in attesa (nessuna riga di database): mode e streaming dal battito', () => {
        const v = runnerDalCanale(null, {
            connesso: true, hello: { sport: 'tennis', mode: 'LIVE' }, ultimoFlussoMs: null,
            ultimoMsgMs: NOW, battito: { ts: NOW, mode: 'PAPER', streaming: 0 },
        }, NOW);
        expect(v.runner?.mode).toBe('PAPER');
        expect(v.runner?.streaming).toBe(0);
        expect(v.etaS).toBe(0);
    });
    it('canale spento: il battito ricevuto prima non conta', () => {
        const v = runnerDalCanale(DB, { ...NOTIZIE_VUOTE, battito: leggiBattito(finti.battito) }, NOW);
        expect(v.fonte).toBe('database');
        expect(v.runner?.streaming).toBe(0);
    });
});

// -------------------------------------------- 25/09 punto 6: modo_ordini
describe('leggiModoOrdiniCanale (topic `modo_ordini` e hello.modo_ordini)', () => {
    it('il messaggio vero', () => {
        expect(leggiModoOrdiniCanale(finti.modo_ordini)).toEqual({
            effettivo: 'PAPER', tetto: 'LIVE', scelto: 'PAPER', ms: finti.modo_ordini.ts, alCambio: true,
        });
        expect(leggiModoOrdiniCanale(finti.hello.modo_ordini)?.effettivo).toBe('PAPER');
    });
    it('senza ts o senza effettivo: null', () => {
        const senzaTs: Record<string, unknown> = { ...finti.modo_ordini };
        delete senzaTs.ts;
        expect(leggiModoOrdiniCanale(senzaTs)).toBeNull();
        expect(leggiModoOrdiniCanale({ ...finti.modo_ordini, effettivo: 'boh' })).toBeNull();
        expect(leggiModoOrdiniCanale(undefined)).toBeNull();
    });
});

describe('sovrapponiModoOrdini con il modo al cambio', () => {
    const riga = {
        id: 1, kill_switch: false, max_exposure_per_selection: null, max_orders_per_min: null,
        order_poll_sec: null, risk_poll_sec: null, daily_loss_limit: null, max_exposure_per_event: null,
        max_exposure_per_league: null, updated_at: '2026-09-25T12:00:00Z',
        order_mode: 'paper', order_mode_updated_at: '2026-09-25T12:00:00Z', order_mode_updated_by: 'avvio_app',
        order_mode_boot_id: 'b1', order_mode_tetto: 'LIVE', order_mode_tetto_at: '2026-09-25T11:59:00Z',
    };
    const st = statoOrdiniReali(riga);
    const letto = NOW - 20_000;
    const hello = { sport: 'calcio', mode: 'LIVE' };

    it('senza partite (nessun now): il cambio del runner vale subito e chiede la rilettura', () => {
        const m = leggiModoOrdiniCanale(finti.modo_ordini_live)!;       // ts = NOW - 1 s
        const v = sovrapponiModoOrdini(st, letto, { connesso: true, hello, modo: null, modoAlCambio: m }, NOW);
        expect(v.fonte).toBe('canale');
        expect(v.effettivo).toBe('LIVE');
        expect(v.etaS).toBe(1);
        expect(v.daRileggere).toBe(true);
        expect(v.scelto).toBe('PAPER');        // chi/quando restano del database
    });
    it('al cambio NON scade dopo 15 s: vale finche\' il canale e\' collegato', () => {
        const m = { ...leggiModoOrdiniCanale(finti.modo_ordini_live)!, ms: NOW - 600_000 };
        const v = sovrapponiModoOrdini(st, NOW - 700_000, { connesso: true, hello, modo: null, modoAlCambio: m }, NOW);
        expect(v.fonte).toBe('canale');
        expect(v.effettivo).toBe('LIVE');
        expect(v.etaS).toBe(600);
    });
    it('lettura piu\' recente del cambio: effettivo del runner (e\' quello che applica), nessuna rilettura', () => {
        const m = { ...leggiModoOrdiniCanale(finti.modo_ordini_live)!, ms: letto - 5000 };
        const v = sovrapponiModoOrdini(st, letto, { connesso: true, hello, modo: null, modoAlCambio: m }, NOW);
        expect(v.effettivo).toBe('LIVE');
        expect(v.daRileggere).toBe(false);
    });
    it('mai unione: fra now e modo_ordini vince il piu\' recente, intero', () => {
        const alCambio = { ...leggiModoOrdiniCanale(finti.modo_ordini)!, ms: NOW - 3000 };   // PAPER
        const dalNow = { effettivo: 'LIVE' as const, tetto: 'LIVE' as const, scelto: 'LIVE' as const, ms: NOW - 1000 };
        const v = sovrapponiModoOrdini(st, letto, { connesso: true, hello, modo: dalNow, modoAlCambio: alCambio }, NOW);
        expect(v.effettivo).toBe('LIVE');
        expect(v.etaS).toBe(1);
        const w = sovrapponiModoOrdini(st, letto, {
            connesso: true, hello, modo: { ...dalNow, ms: NOW - 5000 }, modoAlCambio: alCambio,
        }, NOW);
        expect(w.effettivo).toBe('PAPER');
        expect(w.etaS).toBe(3);
    });
    it('canale scollegato: il modo al cambio non vale piu\'', () => {
        const m = leggiModoOrdiniCanale(finti.modo_ordini_live)!;
        const v = sovrapponiModoOrdini(st, letto, { connesso: false, hello: null, modo: null, modoAlCambio: m }, NOW);
        expect(v.fonte).toBe('database');
        expect(v.effettivo).toBe('PAPER');
    });
});
