// ============================================================================
// statoBotCanale.test.ts - 25/09 (voce 4 e 14): il CONTENUTO dei push
// `*_stato` e `scanner_stato` sulla riga del database, "mai unione".
//
// I finti sono i messaggi VERI dei produttori (chiavi e tipi identici):
//  - omega_stato: Betfair/omega/omega_service.py:7816 {"stats", "last_cycle"},
//    `stats` costruito a :7530-7582 (qui un sottoinsieme delle stesse chiavi);
//  - safe_stato: Betfair/safe_strategy/bot_service.py:9310 {"stats",
//    "last_cycle"}, `stats` a :9071-9127 (motivo_blocco, tetto_partite,
//    partite_esposte, risk, params_effective, last_cycle...);
//  - mike_stato: Betfair/mike/service.py:4904 {"control", "aggregates",
//    "stats", "published_ts"}; `control` = riga intera di `mike_control`
//    (`db.read_control`, select *), `stats` a :2872-2918;
//  - dal 25/09 (punto 6) omega_stato e safe_stato portano anche `control` =
//    {status, mode, params, updated_at} (`_pubblica_stato(..., control)`):
//    finti in __fixtures__/statoBotCanaleFinti.json, generati dal run_once vero;
//  - scanner_stato: Betfair/safe_strategy/service.py:1519 = il `payload` di
//    `safe_strategy_status` (service.py:1797-1845).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { leggiPushStato, sovrapponiControl, statoScannerDalCanale } from './statoBotCanale';
import finti from './__fixtures__/statoBotCanaleFinti.json';

const T0 = '2026-09-25T13:00:00.000000+00:00';
const T1 = '2026-09-25T13:00:02.000000+00:00';

function statsSafe(lastCycle: string, over: Record<string, unknown> = {}): Record<string, unknown> {
    return {
        events_total: 12, signals_active: 1, trades_open: 0, open_liability: 0,
        reconciling_liability: 0, realized_today: 0.41, realized_total: 3.2,
        won_today: 1, lost_today: 0, legs_today: 1, events_today: 1, feed_blind: 0,
        motivo_blocco: null, tetto_partite: 3, partite_esposte: 0, cadenza_battito_s: 2,
        fonte_scan: 'canale', stop_ferma_solo_aperture: true, last_cycle: lastCycle,
        risk: { daily_liability: 0, daily_liability_bot: 0, daily_cap: 0, reconciling_liability: 0,
            realized_today_bot: 0.41, loss_stop_active: false, cap_solo_automatico: false, daily_loss_stop: 50 },
        opps: { model: 0, anomaly: 0, combo: 0, tennis: 0 },
        params_effective: { strategy_modes: { tennis: 'live', calcio: 'paper' } },
        ...over,
    };
}

function controlSafe(stats: Record<string, unknown>) {
    return {
        id: 1, status: 'running', mode: 'live', params: { auto_trade_tennis: true },
        stats, error: null, started_at: T0, stopped_at: null, heartbeat_at: T0,
        updated_at: T0,
    };
}

function controlMike(updatedAt: string, over: Record<string, unknown> = {}) {
    return {
        id: 1, status: 'running', mode: 'paper', params: { live_resting_enabled: false },
        stats: { last_cycle: T0, mode: 'paper' }, error: null, started_at: T0, stopped_at: null,
        heartbeat_at: T0, updated_at: updatedAt, ...over,
    };
}

describe('leggiPushStato - valida il messaggio vero', () => {
    it('safe_stato: stats presi, nessun control (Safe non lo pubblica)', () => {
        const p = leggiPushStato('safe', { stats: statsSafe(T1), last_cycle: T1 }, 5);
        expect(p?.stats?.last_cycle).toBe(T1);
        expect(p?.control).toBeNull();
        expect(p?.ricevutoMs).toBe(5);
    });
    it('mike_stato: control SENZA il suo stats vecchio, stats del giro a parte', () => {
        const p = leggiPushStato('mike', {
            control: controlMike(T1), aggregates: { open_count: 0 },
            stats: { last_cycle: T1, mode: 'paper', motivo_blocco: null }, published_ts: 1758805202.0,
        }, 7);
        expect(p?.control?.status).toBe('running');
        expect(p?.control && 'stats' in p.control).toBe(false);
        expect(p?.stats?.last_cycle).toBe(T1);
    });
    // 25/09 (punto 6): Omega e Safe pubblicano `control` = {status, mode,
    // params, updated_at} della riga letta a inizio giro. Messaggi VERI in
    // __fixtures__/statoBotCanaleFinti.json (chiavi e tipi verificati da
    // Betfair/stream/tests/test_punto6_b_stato_bot_e_battito_tennis_2026_09_25.py)
    it('omega_stato / safe_stato con control: le quattro colonne della riga', () => {
        for (const bot of ['omega', 'safe'] as const) {
            const vero = finti[`${bot}_stato`];
            const p = leggiPushStato(bot, vero, 3);
            expect(p?.control).toEqual(vero.control);
            expect(Object.keys(p?.control ?? {}).sort()).toEqual(['mode', 'params', 'status', 'updated_at']);
            expect(p?.stats?.last_cycle).toBe(vero.last_cycle);
        }
    });
    it('un bot di prima (senza control): nessun control', () => {
        const p = leggiPushStato('omega', { stats: { last_cycle: T1 }, last_cycle: T1 }, 1);
        expect(p?.control).toBeNull();
    });
    it('messaggi storti: null', () => {
        expect(leggiPushStato('safe', null, 1)).toBeNull();
        expect(leggiPushStato('safe', [1], 1)).toBeNull();
        expect(leggiPushStato('safe', { stats: 'x' }, 1)).toBeNull();
    });
});

describe('sovrapponiControl - mai unione, vince solo il piu\' recente', () => {
    it('riga mai letta: il canale non crea lo stato', () => {
        const p = leggiPushStato('safe', { stats: statsSafe(T1), last_cycle: T1 }, 1);
        expect(sovrapponiControl(null, p)).toEqual({ control: null, daCanale: false });
    });
    it('senza push: STESSO oggetto del database', () => {
        const db = controlSafe(statsSafe(T0));
        const v = sovrapponiControl(db, null);
        expect(v.control).toBe(db);
        expect(v.daCanale).toBe(false);
    });
    it('giro piu\' recente: stats dal canale, per chiave (il timbro del database resta)', () => {
        const db = controlSafe({ ...statsSafe(T0, { motivo_blocco: null }), fermato_all_avvio_at: T0, app_boot_id: 'b1' });
        const p = leggiPushStato('safe', {
            stats: statsSafe(T1, { motivo_blocco: 'tetto partite raggiunto', tetto_partite: 3, partite_esposte: 3 }),
            last_cycle: T1,
        }, 1);
        const v = sovrapponiControl(db, p);
        expect(v.daCanale).toBe(true);
        const st = v.control?.stats as Record<string, unknown>;
        expect(st.motivo_blocco).toBe('tetto partite raggiunto');
        expect(st.partite_esposte).toBe(3);
        expect(st.fermato_all_avvio_at).toBe(T0);
        expect(st.app_boot_id).toBe('b1');
        // le colonne della riga restano del database (Safe non le pubblica)
        expect(v.control?.mode).toBe('live');
        expect(v.control?.status).toBe('running');
    });
    it('giro NON piu\' recente (pari o vecchio): vince il database, stesso oggetto', () => {
        const db = controlSafe(statsSafe(T1));
        for (const t of [T1, T0]) {
            const p = leggiPushStato('safe', { stats: statsSafe(t, { motivo_blocco: 'x' }), last_cycle: t }, 1);
            const v = sovrapponiControl(db, p);
            expect(v.control).toBe(db);
            expect(v.daCanale).toBe(false);
        }
    });
    it('Mike: status/mode/params dal canale SOLO con una versione della riga piu\' nuova', () => {
        const db = controlMike(T0);
        const nuova = leggiPushStato('mike', {
            control: controlMike(T1, { status: 'stopped', mode: 'live', params: { live_resting_enabled: true } }),
            aggregates: {}, stats: { last_cycle: T0, mode: 'live' }, published_ts: 1.0,
        }, 1);
        const v = sovrapponiControl(db, nuova);
        expect(v.control?.status).toBe('stopped');
        expect(v.control?.mode).toBe('live');
        expect((v.control?.params as Record<string, unknown>).live_resting_enabled).toBe(true);
        expect(v.daCanale).toBe(true);
    });
    it('Mike: versione della riga PARI -> vince il database (un salvataggio della pagina non torna indietro)', () => {
        const db = controlMike(T1, { params: { live_resting_enabled: true } });
        const vecchia = leggiPushStato('mike', {
            control: controlMike(T1, { params: { live_resting_enabled: false } }),
            aggregates: {}, stats: { last_cycle: T0 }, published_ts: 1.0,
        }, 1);
        const v = sovrapponiControl(db, vecchia);
        expect((v.control?.params as Record<string, unknown>).live_resting_enabled).toBe(true);
        expect(v.control).toBe(db);
    });

    // 25/09 (punto 6) - Omega e Safe
    function rigaOmega(updatedAt: string, over: Record<string, unknown> = {}) {
        // colonne di omega_control (riga_control dei test Python): daily_goal fuori da params
        return {
            id: 1, status: 'running', mode: 'paper', daily_goal: 250,
            params: { stake_lay: 1.0, engine: 'single', greenup_mode: 'off' },
            stats: { last_cycle: T0, realized_today: 1.5, fermato_all_avvio_at: T0 }, error: null,
            started_at: T0, stopped_at: null, heartbeat_at: T0, updated_at: updatedAt, created_at: T0,
            ...over,
        };
    }
    it('Omega: modalita\' e parametri dal push con una versione della riga piu\' nuova', () => {
        const db = rigaOmega(T0);
        const v = sovrapponiControl(db, leggiPushStato('omega', finti.omega_stato, 1));
        expect(v.daCanale).toBe(true);
        expect(v.control?.mode).toBe('live');
        expect(v.control?.updated_at).toBe(finti.omega_stato.control.updated_at);
        // le colonne che il push non porta restano del database
        expect(v.control?.daily_goal).toBe(250);
        expect(v.control?.started_at).toBe(T0);
    });
    it('mai unione: i params del push SOSTITUISCONO quelli del database (non si fondono)', () => {
        const db = rigaOmega(T0);
        const v = sovrapponiControl(db, leggiPushStato('omega', finti.omega_stato, 1));
        expect(v.control?.params).toEqual(finti.omega_stato.control.params);
        expect(v.control?.params).not.toHaveProperty('greenup_mode');
    });
    it('Omega/Safe: versione della riga PARI o piu\' vecchia -> vince il database, stesso oggetto', () => {
        const t = finti.omega_stato.control.updated_at;
        for (const dbAt of [t, '2026-09-25T13:00:09.000000+00:00']) {
            const db = rigaOmega(dbAt, { stats: { last_cycle: '2026-09-25T13:00:09.000000+00:00' } });
            const v = sovrapponiControl(db, leggiPushStato('omega', finti.omega_stato, 1));
            expect(v.control).toBe(db);
            expect(v.control?.mode).toBe('paper');
            expect(v.daCanale).toBe(false);
        }
        const dbSafe = { ...controlSafe(statsSafe('2026-09-25T13:00:09.000000+00:00')), mode: 'paper', updated_at: t };
        const w = sovrapponiControl(dbSafe, leggiPushStato('safe', finti.safe_stato, 1));
        expect(w.control).toBe(dbSafe);
    });
    it('Safe: modalita\' dal push; control senza updated_at leggibile non vince mai', () => {
        const db = { ...controlSafe(statsSafe(T0)), mode: 'paper' };
        const v = sovrapponiControl(db, leggiPushStato('safe', finti.safe_stato, 1));
        expect(v.control?.mode).toBe('live');
        expect(v.control?.params).toEqual(finti.safe_stato.control.params);
        const senzaVersione = { ...finti.safe_stato, control: { ...finti.safe_stato.control, updated_at: null } };
        const w = sovrapponiControl(db, leggiPushStato('safe', senzaVersione, 1));
        expect(w.control?.mode).toBe('paper');
    });
});

describe('statoScannerDalCanale - scanner_stato sulla riga letta', () => {
    const riga = { id: 'scanner', payload: { source: 'stream', calcio_inplay: 3 }, updated_at: '2026-09-25T13:00:00Z' };
    const tDb = Date.parse(riga.updated_at);
    it('riga mai letta: nulla', () => {
        expect(statoScannerDalCanale(null, { source: 'stream' }, tDb + 1000)).toBeNull();
    });
    it('ricezione piu\' recente: payload del canale ed eta\' dalla ricezione', () => {
        const v = statoScannerDalCanale(riga, { source: 'stream', calcio_inplay: 4 }, tDb + 10_000);
        expect(v?.payload).toEqual({ source: 'stream', calcio_inplay: 4 });
        expect(v?.updated_at).toBe(new Date(tDb + 10_000).toISOString());
    });
    it('ricezione non piu\' recente o messaggio storto: stessa riga', () => {
        expect(statoScannerDalCanale(riga, { source: 'x' }, tDb)).toBe(riga);
        expect(statoScannerDalCanale(riga, 'x', tDb + 5)).toBe(riga);
    });
});
