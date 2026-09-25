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
//  - scanner_stato: Betfair/safe_strategy/service.py:1519 = il `payload` di
//    `safe_strategy_status` (service.py:1797-1845).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { leggiPushStato, sovrapponiControl, statoScannerDalCanale } from './statoBotCanale';

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
    it('un control su omega/safe si ignora (nessun produttore lo manda)', () => {
        const p = leggiPushStato('omega', { control: { status: 'stopped' }, stats: { last_cycle: T1 } }, 1);
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
