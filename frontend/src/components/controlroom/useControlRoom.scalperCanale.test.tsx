// ============================================================================
// useControlRoom.scalperCanale.test.tsx - 25/09, ordine dell'utente: «lo
// scalper deve lavorare da solo su tutte le partite del feed come gli altri
// bot [...] pubblicalo sul canale come tutti gli altri».
//
// Sul hook VERO:
//  1. l'interruttore globale (`servizio` di `get_scalper_control_room`) acceso
//     senza sessioni: la riga dice acceso, con la SUA modalita' e la frase
//     dell'auto-mode (`stats.auto` scritto dal supervisore);
//  2. `scalper_sessioni` con una sessione SCONOSCIUTA -> rilettura mirata
//     subito, la sessione entra dal DATABASE;
//  3. sessione NOTA, messaggio piu' fresco -> overlay (battito, stats), eta'
//     del push 0, fonte "canale locale"; messaggio vecchio -> scartato;
//  4. `scalper_stato` -> l'interruttore dal canale (spento dall'utente altrove);
//  5. canale 47338 giu' -> 'off', eta' azzerata, si torna al database;
//  6. migrazione non applicata (nessuna chiave `servizio`): lo si dice.
//
// I finti hanno le chiavi e i tipi veri: sessione = `to_jsonb(scalper_control)`
// + le colonne della RPC (`lib/__fixtures__/scalperFinti.ts`), servizio =
// `to_jsonb(scalper_service_control)` (migrations/scalper_auto_mode_2026-09-25.sql),
// messaggio = riga + busta di `Betfair/stream/canale_bot.py`.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
const statoCb = new Map<string, Set<(s: 'connected' | 'off') => void>>();
const statoCanale = new Map<string, 'connected' | 'off'>();
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
        getStatus: () => statoCanale.get(sport) ?? 'connected',
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
    fetchScalperControlRoom: vi.fn(),
}));

import { fetchScalperControlRoom, type ScalperControlRoom, type ServizioScalper } from '@/lib/scalperControlRoom';
import { sessione } from '@/lib/__fixtures__/scalperFinti';
import { useControlRoom } from '@/components/controlroom/useControlRoom';

const mFetch = vi.mocked(fetchScalperControlRoom);

/** `to_jsonb(scalper_service_control)` con i fatti dell'auto-mode */
function servizio(over: Partial<ServizioScalper> = {}): ServizioScalper {
    return {
        id: 1, status: 'running', mode: 'paper', strategia: 'maker', stake: 25, params: {},
        stats: {
            boot_id: 'b1',
            auto: {
                acceso: true, modalita: 'paper', tetto: 2, sessioni: 0, sessioni_auto: 0,
                armate_ora: [], fermate_ora: [], motivo_blocco: null, conflitto: null,
                pnl_lordo_bot: 0, ordini_vivi: 0,
                feed: { letto: true, vivo: true, partite: 5, eta_scanner_s: 4.2, fonte: 'safe_strategy_scan' },
                giro_at: '2026-09-25T18:00:00+00:00',
            },
        },
        started_at: '2026-09-25T17:00:00+00:00', stopped_at: null,
        updated_at: '2026-09-25T18:00:00+00:00',
        ...over,
    };
}

function lettura(over: Partial<ScalperControlRoom> = {}): ScalperControlRoom {
    return { sessioni: [], ordini: [], lettoAt: null, servizio: servizio(), servizioLetto: true, ...over };
}

function busta(riga: object, pubblicatoMs: number, seq: number): Record<string, unknown> {
    return { ...riga, fonte: 'canale', _seq: seq, _pubblicato_ms: pubblicatoMs };
}

/** la riga di sessione come la pubblica il supervisore: SOLO le colonne di
 *  `scalper_control` (niente event_name/kickoff/ultima attivita' della RPC) */
function rigaSessioneCanale(over: Record<string, unknown> = {}): Record<string, unknown> {
    const s = sessione({ origine: 'auto', ...over } as never) as unknown as Record<string, unknown>;
    const out = { ...s };
    for (const k of ['event_name', 'league_name', 'kickoff', 'ultima_attivita_at', 'ultima_attivita_kind']) delete out[k];
    return out;
}

beforeEach(() => {
    iscritti.clear();
    statoCb.clear();
    statoCanale.clear();
    mFetch.mockReset().mockResolvedValue(lettura());
});

async function montato() {
    const h = renderHook(() => useControlRoom());
    await waitFor(() => expect(h.result.current.caricamento).toBe(false));
    return h;
}

describe('la riga Scalper calcio con l\'interruttore globale', () => {
    it('acceso senza sessioni: acceso, in prova, con la frase dell\'auto-mode', async () => {
        const { result } = await montato();
        const sc = () => result.current.bots.find((b) => b.bot === 'scalper')!;
        await waitFor(() => expect(sc().stato).toBe('running'));
        expect(sc().inCorsa).toBe(true);
        expect(sc().modalita).toBe('paper');
        expect(sc().tettoPartite).toBe(2);
        expect(sc().nota).toMatch(/^auto-mode: nessuna sessione - tetto 2 - feed calcio: 5 partite, scanner 4 s fa \(safe_strategy_scan\) - 0 ordini vivi - nessuna sessione viva - dal database, letto \d+ s fa$/);
        // lo stake delle partite nuove e' nei "params" della riga (campo importo)
        expect(sc().params).toMatchObject({ stake: 25, uscite_automatiche: true });
    });

    it('migrazione non applicata (nessuna chiave servizio): lo dice, la card resta', async () => {
        mFetch.mockResolvedValue({ sessioni: [], ordini: [], lettoAt: null, servizio: null, servizioLetto: false });
        const { result } = await montato();
        const sc = () => result.current.bots.find((b) => b.bot === 'scalper')!;
        await waitFor(() => expect(sc().nota).toContain('auto-mode non disponibile'));
        expect(sc().inCorsa).toBe(false);
    });
});

describe('il canale 47338', () => {
    it('sessione SCONOSCIUTA -> rilettura subito, la sessione entra dal database', async () => {
        const { result } = await montato();
        const prima = mFetch.mock.calls.length;
        mFetch.mockResolvedValue(lettura({ sessioni: [sessione({ event_id: '35800001', origine: 'auto' })] }));
        act(() => {
            spingi('scalper', 'scalper_sessioni',
                busta(rigaSessioneCanale({ event_id: '35800001', status: 'requested' }), Date.now() + 1_000, 1));
        });
        expect(mFetch.mock.calls.length).toBe(prima + 1);   // subito, non al giro dei 30 s
        const sc = () => result.current.bots.find((b) => b.bot === 'scalper')!;
        await waitFor(() => expect(sc().nota).toContain('1 sessione viva (1 prova)'));
    });

    it('sessione NOTA: overlay piu\' fresco (stats, battito), fonte canale; vecchio scartato', async () => {
        mFetch.mockResolvedValue(lettura({ sessioni: [sessione({ event_id: '35800001', origine: 'auto' })] }));
        const { result } = await montato();
        const sc = () => result.current.bots.find((b) => b.bot === 'scalper')!;
        await waitFor(() => expect(sc().nota).toContain('1 sessione viva'));
        const letture = mFetch.mock.calls.length;
        act(() => {
            spingi('scalper', 'scalper_sessioni', busta(rigaSessioneCanale({
                event_id: '35800001', heartbeat_at: '2026-09-25T18:00:05+00:00',
                stats: { cycles: 3, pnl_locked: 0.9, ordini_vivi: 2 },
            }), Date.now() + 1_000, 7));
        });
        expect(mFetch.mock.calls.length).toBe(letture);      // nessuna rilettura: basta l'overlay
        expect(sc().etaPushS).toBe(0);
        expect(sc().battitoAt).toBe('2026-09-25T18:00:05+00:00');
        expect(sc().nota).toContain('dal canale locale, 0 s fa');
        // un messaggio piu' VECCHIO della lettura non passa
        act(() => {
            spingi('scalper', 'scalper_sessioni', busta(rigaSessioneCanale({
                event_id: '35800001', heartbeat_at: '2026-09-25T17:00:00+00:00',
            }), Date.now() - 600_000, 99));
        });
        expect(sc().battitoAt).toBe('2026-09-25T18:00:05+00:00');
    });

    it('la sessione si FERMA sul canale -> rilettura mirata (ordini e P&L dal database)', async () => {
        mFetch.mockResolvedValue(lettura({ sessioni: [sessione({ event_id: '35800001', origine: 'auto' })] }));
        await montato();
        const prima = mFetch.mock.calls.length;
        act(() => {
            spingi('scalper', 'scalper_sessioni', busta(rigaSessioneCanale({
                event_id: '35800001', status: 'stopped',
            }), Date.now() + 1_000, 8));
        });
        expect(mFetch.mock.calls.length).toBe(prima + 1);
    });

    it('scalper_stato: l\'interruttore spento altrove arriva dal canale', async () => {
        const { result } = await montato();
        const sc = () => result.current.bots.find((b) => b.bot === 'scalper')!;
        await waitFor(() => expect(sc().inCorsa).toBe(true));
        act(() => {
            spingi('scalper', 'scalper_stato',
                busta(servizio({ status: 'stopped', stats: null }), Date.now() + 1_000, 3));
        });
        expect(sc().inCorsa).toBe(false);
        expect(sc().stato).toBe('stopped');
    });

    it('canale giu\': off, eta\' azzerata, si torna al database', async () => {
        mFetch.mockResolvedValue(lettura({ sessioni: [sessione({ event_id: '35800001' })] }));
        const { result } = await montato();
        const sc = () => result.current.bots.find((b) => b.bot === 'scalper')!;
        await waitFor(() => expect(sc().nota).toContain('1 sessione viva'));
        act(() => {
            spingi('scalper', 'scalper_sessioni', busta(rigaSessioneCanale({
                event_id: '35800001', heartbeat_at: '2026-09-25T18:00:05+00:00',
            }), Date.now() + 1_000, 7));
        });
        expect(sc().canale).toBe('connected');
        act(() => { cambiaStato('scalper', 'off'); });
        expect(sc().canale).toBe('off');
        expect(sc().etaPushS).toBeNull();
        expect(sc().battitoAt).toBe(sessione().heartbeat_at);
        expect(sc().nota).toContain('dal database');
    });
});
