// ============================================================================
// useControlRoom.statoCanale.test.tsx - 25/09, voci 4, 6 e 14 dell'audit tempo
// reale, sul hook VERO (i moduli puri hanno i loro test: lib/statoBotCanale,
// lib/runnerCanale).
//
//  4. il CONTENUTO dei push `*_stato` (Safe, Mike, Omega) sovrapposto alla
//     riga di control: motivo del blocco / modalita' / parametri subito, non al
//     poll dei 30 s; "mai unione"; canale giu' -> database;
//  6. runner calcio e tennis dal canale (connessione, hello, account/ladder);
//  14. `scanner_stato` sottoscritto.
//
// Finti (chiavi e tipi dei produttori veri):
//  - safe_stato  Betfair/safe_strategy/bot_service.py:9310 {stats, last_cycle}
//  - mike_stato  Betfair/mike/service.py:4904 {control, aggregates, stats, published_ts}
//  - omega_stato Betfair/omega/omega_service.py:7816 {stats, last_cycle}
//  - hello       Betfair/stream/local_channel.py:353 {sport, mode}
//  - account     Betfair/stream/reconcile_worker.py:161 {available, exposure, checked_at}
//  - ladder      Betfair/stream/runner.py:718 (riga ladder, qui solo il segnale)
//  - scanner_stato Betfair/safe_strategy/service.py:1519 (payload di safe_strategy_status)
//  - righe di control: `select *` di safe_strategy_control / mike_control /
//    omega_control (lib/safeBot SafeControl, lib/mike MikeControl, lib/omega OmegaControl)
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
const statoCb = new Map<string, Set<(s: 'connected' | 'off') => void>>();
const statoCanale = new Map<string, 'connected' | 'off'>();
const hello = new Map<string, Record<string, unknown> | null>();
function spingi(sport: string, topic: string, d: unknown): void {
    for (const cb of iscritti.get(`${sport}:${topic}`) ?? []) cb(d);
}
function cambiaStato(sport: string, st: 'connected' | 'off'): void {
    statoCanale.set(sport, st);
    for (const cb of statoCb.get(sport) ?? []) cb(st);
}

vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn((sport: string) => ({
        getStatus: () => statoCanale.get(sport) ?? 'off',
        getHello: () => hello.get(sport) ?? null,
        onStatus: (cb: (s: 'connected' | 'off') => void) => {
            let s = statoCb.get(sport);
            if (!s) { s = new Set(); statoCb.set(sport, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        subscribe: (topic: string, cb: Cb) => {
            const k = `${sport}:${topic}`;
            let s = iscritti.get(k);
            if (!s) { s = new Set(); iscritti.set(k, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));
vi.mock('@/lib/safeStrategyScan', async (orig) => ({
    ...(await orig() as object),
    fetchScanRows: vi.fn(async () => []),
    fetchScanStatus: vi.fn(async () => null),
    subscribeScanRows: vi.fn(() => () => { /* nessun evento */ }),
    subscribeScanStatus: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig() as object),
    fetchOmegaState: vi.fn(async () => ({ control: null, aggregates: null, activity: [] })),
    fetchOmegaTrades: vi.fn(async () => []),
    fetchOmegaEvents: vi.fn(async () => []),
    updateOmegaParams: vi.fn(async () => ({})),
}));
vi.mock('@/lib/safeBot', async (orig) => ({
    ...(await orig() as object),
    fetchSafeState: vi.fn(async () => ({ control: null, trades: [], aggregates: null })),
    fetchRunnerState: vi.fn(async () => ({ ts: null, mode: null, ageS: null, up: false })),
}));
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    fetchMikeState: vi.fn(async () => ({ control: null, events: [], trades: [], activity: [], aggregates: null, requests: [], day_start: null, day_by: null })),
}));
vi.mock('@/lib/controlRoomProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposte: vi.fn(async () => []),
    subscribeProposte: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omegaProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposteOmega: vi.fn(async () => []),
    subscribeProposteOmega: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omegaMissions', async (orig) => ({
    ...(await orig() as object),
    fetchMissions: vi.fn(async () => ({ missions: [] })),
}));
vi.mock('@/lib/live', async (orig) => ({
    ...(await orig() as object),
    fetchLiveFollows: vi.fn(async () => []),
}));
vi.mock('@/lib/dailyHistory', async (orig) => ({
    ...(await orig() as object),
    fetchSafeDaily: vi.fn(async () => []),
}));
vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    fetchTennisFollows: vi.fn(async () => []),
    fetchTennisBotServices: vi.fn(async () => []),
    fetchTennisBotDaily: vi.fn(async () => []),
    fetchTennisBotOrdersToday: vi.fn(async () => []),
}));
vi.mock('@/lib/liveOrders', async (orig) => ({
    ...(await orig() as object),
    fetchLiveAccount: vi.fn(async () => null),
    subscribeLiveAccount: vi.fn(() => () => { /* nessuna spinta */ }),
}));
vi.mock('@/lib/scalperControlRoom', async (orig) => ({
    ...(await orig() as object),
    fetchScalperControlRoom: vi.fn(async () => ({ sessioni: [], ordini: [], lettoAt: null, servizio: null, servizioLetto: false })),
}));

import { fetchSafeState, fetchRunnerState } from '@/lib/safeBot';
import { fetchMikeState } from '@/lib/mike';
import { fetchOmegaState } from '@/lib/omega';
import { fetchScanStatus } from '@/lib/safeStrategyScan';
import { useControlRoom } from '@/components/controlroom/useControlRoom';
import finti from '@/lib/__fixtures__/runnerCanaleFinti.json';

const T0 = '2026-09-25T13:00:00.000000+00:00';
const T1 = '2026-09-25T13:00:02.000000+00:00';

function statsSafe(lastCycle: string, over: Record<string, unknown> = {}) {
    return {
        events_total: 12, signals_active: 0, trades_open: 0, open_liability: 0,
        reconciling_liability: 0, realized_today: 0, realized_total: 0, won_today: 0, lost_today: 0,
        legs_today: 0, events_today: 0, feed_blind: 0, motivo_blocco: null, tetto_partite: 3,
        partite_esposte: 0, cadenza_battito_s: 2, fonte_scan: 'canale', stop_ferma_solo_aperture: true,
        last_cycle: lastCycle,
        risk: { daily_liability: 0, daily_liability_bot: 0, daily_cap: 0, reconciling_liability: 0,
            realized_today_bot: 0, loss_stop_active: false, cap_solo_automatico: false, daily_loss_stop: 50 },
        opps: { model: 0, anomaly: 0, combo: 0, tennis: 0 },
        params_effective: { strategy_modes: { tennis: 'live', calcio: 'paper' } },
        ...over,
    };
}

function safeState(stats: Record<string, unknown>) {
    return {
        control: {
            id: 1, status: 'running', mode: 'live', params: {}, stats, error: null,
            started_at: T0, stopped_at: null, heartbeat_at: T0, updated_at: T0,
        },
        trades: [], aggregates: null,
    };
}

function mikeControl(updatedAt: string, over: Record<string, unknown> = {}) {
    return {
        id: 1, status: 'running', mode: 'paper', params: { live_resting_enabled: false },
        stats: { last_cycle: T0, mode: 'paper', tetto_partite: 4, partite_esposte: 0, motivo_blocco: null },
        error: null, started_at: T0, stopped_at: null, heartbeat_at: T0, updated_at: updatedAt, ...over,
    };
}

beforeEach(() => {
    iscritti.clear();
    statoCb.clear();
    statoCanale.clear();
    hello.clear();
    for (const s of ['omega', 'safe', 'mike']) statoCanale.set(s, 'connected');
    vi.mocked(fetchSafeState).mockResolvedValue(safeState(statsSafe(T0)) as never);
    vi.mocked(fetchMikeState).mockResolvedValue({
        control: mikeControl(T0), events: [], trades: [], activity: [], aggregates: null,
        requests: [], day_start: null, day_by: null,
    } as never);
    vi.mocked(fetchOmegaState).mockResolvedValue({ control: null, aggregates: null, activity: [] } as never);
    vi.mocked(fetchRunnerState).mockResolvedValue({ ts: null, mode: null, ageS: null, up: false });
    vi.mocked(fetchScanStatus).mockResolvedValue(null);
});

async function montato() {
    const h = renderHook(() => useControlRoom());
    await waitFor(() => expect(h.result.current.caricamento).toBe(false));
    return h;
}
const bot = (h: { result: { current: ReturnType<typeof useControlRoom> } }, b: string) =>
    h.result.current.bots.find((x) => x.bot === b)!;

describe('voce 4 - lo STATO dei bot dal push *_stato', () => {
    it('Safe: un giro piu\' recente porta subito il motivo del blocco, fonte canale', async () => {
        const h = await montato();
        await waitFor(() => expect(bot(h, 'safe').stato).toBe('running'));
        expect(bot(h, 'safe').fonteStato).toBe('database');
        expect(bot(h, 'safe').motivoBlocco).toBeNull();
        act(() => spingi('safe', 'safe_stato', {
            stats: statsSafe(T1, { motivo_blocco: 'tetto partite raggiunto', partite_esposte: 3 }),
            last_cycle: T1,
        }));
        await waitFor(() => expect(bot(h, 'safe').motivoBlocco).toBe('tetto partite raggiunto'));
        expect(bot(h, 'safe').partiteEsposte).toBe(3);
        expect(bot(h, 'safe').fonteStato).toBe('canale');
        // la modalita' e' una colonna che Safe non pubblica: resta del database
        expect(bot(h, 'safe').modalita).toBe('live');
    });

    it('Safe: i modi per strategia (params_effective) arrivano dal push', async () => {
        const h = await montato();
        await waitFor(() => expect(bot(h, 'safe').modiStrategia).toEqual({ tennis: 'live', calcio: 'paper' }));
        act(() => spingi('safe', 'safe_stato', {
            stats: statsSafe(T1, { params_effective: { strategy_modes: { tennis: 'paper', calcio: 'paper' } } }),
            last_cycle: T1,
        }));
        await waitFor(() => expect(bot(h, 'safe').modiStrategia).toEqual({ tennis: 'paper', calcio: 'paper' }));
    });

    it('Safe: un giro NON piu\' recente della riga letta non cambia niente', async () => {
        const h = await montato();
        await waitFor(() => expect(bot(h, 'safe').stato).toBe('running'));
        act(() => spingi('safe', 'safe_stato', {
            stats: statsSafe(T0, { motivo_blocco: 'vecchio' }), last_cycle: T0,
        }));
        await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
        expect(bot(h, 'safe').motivoBlocco).toBeNull();
        expect(bot(h, 'safe').fonteStato).toBe('database');
    });

    it('mai unione: un push per un bot la cui riga non e\' mai stata letta non crea lo stato', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ control: null, trades: [], aggregates: null } as never);
        const h = await montato();
        act(() => spingi('safe', 'safe_stato', { stats: statsSafe(T1, { motivo_blocco: 'x' }), last_cycle: T1 }));
        await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
        expect(bot(h, 'safe').stato).toBeNull();
        expect(bot(h, 'safe').motivoBlocco).toBeNull();
    });

    it('Mike: modalita\' e interruttori dal push con una versione della riga piu\' nuova', async () => {
        const h = await montato();
        await waitFor(() => expect(bot(h, 'mike').modalita).toBe('paper'));
        act(() => spingi('mike', 'mike_stato', {
            control: mikeControl(T1, { mode: 'live', params: { live_resting_enabled: true } }),
            aggregates: { open_count: 0 },
            stats: { last_cycle: T1, mode: 'live', tetto_partite: 4, partite_esposte: 1, motivo_blocco: null },
            published_ts: 1758805202.0,
        }));
        await waitFor(() => expect(bot(h, 'mike').modalita).toBe('live'));
        expect(bot(h, 'mike').params).toMatchObject({ live_resting_enabled: true });
        expect(h.result.current.mikeRestingLive).toBe(true);
        expect(bot(h, 'mike').partiteEsposte).toBe(1);
        expect(bot(h, 'mike').fonteStato).toBe('canale');
    });

    it('canale giu\': il push si butta e si torna al database', async () => {
        const h = await montato();
        await waitFor(() => expect(bot(h, 'safe').stato).toBe('running'));
        act(() => spingi('safe', 'safe_stato', {
            stats: statsSafe(T1, { motivo_blocco: 'dal canale' }), last_cycle: T1,
        }));
        await waitFor(() => expect(bot(h, 'safe').motivoBlocco).toBe('dal canale'));
        act(() => cambiaStato('safe', 'off'));
        await waitFor(() => expect(bot(h, 'safe').motivoBlocco).toBeNull());
        expect(bot(h, 'safe').fonteStato).toBe('database');
    });

    it('Omega: il realizzato di testata dal push, per chiave (il timbro del database resta)', async () => {
        vi.mocked(fetchOmegaState).mockResolvedValue({
            control: {
                id: 1, status: 'running', mode: 'paper', daily_goal: 10, params: {},
                stats: { last_cycle: T0, realized_today: 1.5, fermato_all_avvio_at: T0 },
                error: null, started_at: T0, stopped_at: null, heartbeat_at: T0, updated_at: T0,
            },
            aggregates: null, activity: [],
        } as never);
        statoCanale.set('omega', 'connected');
        const h = await montato();
        await waitFor(() => expect(h.result.current.realizzato).toBe(1.5));
        act(() => spingi('omega', 'omega_stato', {
            stats: { last_cycle: T1, realized_today: 2.25, bot_running: true }, last_cycle: T1,
        }));
        await waitFor(() => expect(h.result.current.realizzato).toBe(2.25));
        expect(bot(h, 'omega').fermatoAllAvvioAt).toBe(T0);
        expect(bot(h, 'omega').fonteStato).toBe('canale');
    });
});

describe('voce 6 - i runner dal canale', () => {
    it('runner calcio collegato: vivo dal canale con l\'eta\' dell\'ultimo messaggio', async () => {
        statoCanale.set('calcio', 'connected');
        hello.set('calcio', { sport: 'calcio', mode: 'LIVE' });
        const h = await montato();
        act(() => spingi('calcio', 'account', { available: 100, exposure: 0, checked_at: T1 }));
        await waitFor(() => expect(h.result.current.fonteRunner.fonte).toBe('canale'), { timeout: 3000 });
        expect(h.result.current.runner?.up).toBe(true);
        expect(h.result.current.runner?.mode).toBe('LIVE');
    });

    it('ladder dal canale = in streaming', async () => {
        statoCanale.set('calcio', 'connected');
        const h = await montato();
        act(() => spingi('calcio', 'ladder', { market_id: '1.2', ladder: {} }));
        await waitFor(() => expect(h.result.current.runner?.streaming).toBe(1), { timeout: 3000 });
    });

    it('canale spento: la riga del database (ripiego), fonte "database"', async () => {
        vi.mocked(fetchRunnerState).mockResolvedValue({
            ts: new Date(Date.now() - 5000).toISOString(), mode: 'LIVE+PAPER', ageS: 5, up: true, streaming: 0,
        });
        const h = await montato();
        await waitFor(() => expect(h.result.current.runner?.mode).toBe('LIVE+PAPER'));
        expect(h.result.current.fonteRunner.fonte).toBe('database');
        expect(h.result.current.runnerTennis).toBeNull();
    });

    // 25/09 (punto 6): topic `battito` {ts, mode, streaming}
    // (canale_bot.battito_runner, runner._pubblica_battito); messaggio vero in
    // lib/__fixtures__/runnerCanaleFinti.json
    it('battito del runner calcio: l\'eta\' torna a zero a ogni battito, mode e streaming dal battito', async () => {
        statoCanale.set('calcio', 'connected');
        hello.set('calcio', { sport: 'calcio', mode: 'LIVE' });
        vi.mocked(fetchRunnerState).mockResolvedValue({
            ts: new Date(Date.now() - 60_000).toISOString(), mode: 'LIVE+PAPER', ageS: 60, up: true, streaming: 0,
        });
        const h = await montato();
        // si lascia invecchiare l'ultima notizia (l'hello della connessione)
        await waitFor(() => expect(h.result.current.fonteRunner.etaS ?? 0).toBeGreaterThanOrEqual(1), { timeout: 3000 });
        act(() => spingi('calcio', 'battito', { ...finti.battito, ts: Date.now() }));
        await waitFor(() => expect(h.result.current.fonteRunner.etaS).toBe(0), { timeout: 3000 });
        expect(h.result.current.fonteRunner.fonte).toBe('canale');
        expect(h.result.current.runner?.streaming).toBe(2);
        expect(h.result.current.runner?.mode).toBe('LIVE+PAPER');
        // di nuovo vecchio, di nuovo un battito: di nuovo zero
        await waitFor(() => expect(h.result.current.fonteRunner.etaS ?? 0).toBeGreaterThanOrEqual(1), { timeout: 3000 });
        act(() => spingi('calcio', 'battito', { ...finti.battito, ts: Date.now(), streaming: 1 }));
        await waitFor(() => expect(h.result.current.fonteRunner.etaS).toBe(0), { timeout: 3000 });
        expect(h.result.current.runner?.streaming).toBe(1);
    }, 10_000);

    it('battito storto (senza ts): non e\' una notizia di vita', async () => {
        statoCanale.set('calcio', 'connected');
        const h = await montato();
        await waitFor(() => expect(h.result.current.fonteRunner.etaS ?? 0).toBeGreaterThanOrEqual(1), { timeout: 3000 });
        const storto: Record<string, unknown> = { ...finti.battito };
        delete storto.ts;
        act(() => spingi('calcio', 'battito', storto));
        await act(async () => { await new Promise((r) => setTimeout(r, 1200)); });
        expect(h.result.current.fonteRunner.etaS ?? 0).toBeGreaterThanOrEqual(1);
        expect(h.result.current.runner?.streaming ?? null).not.toBe(2);
    }, 10_000);

    it('runner tennis collegato: noto dal solo canale 47332', async () => {
        statoCanale.set('tennis', 'connected');
        hello.set('tennis', { sport: 'tennis', mode: 'PAPER' });
        const h = await montato();
        await waitFor(() => expect(h.result.current.runnerTennis?.up).toBe(true), { timeout: 3000 });
        expect(h.result.current.runnerTennis?.mode).toBe('PAPER');
        expect(h.result.current.fonteRunnerTennis.fonte).toBe('canale');
    });
});

describe('voce 14 - scanner_stato sottoscritto', () => {
    it('lo stato dello scanner si aggiorna dal canale, fonte dichiarata', async () => {
        const letto = new Date(Date.now() - 60_000).toISOString();
        vi.mocked(fetchScanStatus).mockResolvedValue({
            id: 'scanner', payload: { source: 'stream' } as never, updated_at: letto,
        });
        const h = await montato();
        await waitFor(() => expect(h.result.current.feedSorgente).toBe('stream'));
        expect(h.result.current.fonteStatoScanner).toBe('database');
        const vecchiaEta = h.result.current.feedEtaS;
        act(() => spingi('scanner', 'scanner_stato', { source: 'stream+rest', calcio_inplay: 2 }));
        await waitFor(() => expect(h.result.current.feedSorgente).toBe('stream+rest'));
        expect(h.result.current.fonteStatoScanner).toBe('canale');
        expect(h.result.current.feedEtaS ?? 99).toBeLessThan(vecchiaEta ?? 0);
    });
});
