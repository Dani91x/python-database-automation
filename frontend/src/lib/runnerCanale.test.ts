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
    FLUSSO_VIVO_S, MODO_CANALE_VALIDO_S,
} from './runnerCanale';
import { statoOrdiniReali } from './interruttori';
import type { RunnerState } from './safeBot';

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
