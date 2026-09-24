// ============================================================================
// useControlRoom.righeNuove.test.tsx - 24/09, decisione dell'utente: "righe
// nuove dei bot in Control Room subito, non al poll dei 30 s; bot tennis dal
// loro canale".
//
// Sul hook VERO (i moduli puri hanno i loro test: `lib/rilettureMirate.test.ts`,
// `lib/righeCanale.rilettura.test.ts`):
//  1. id SCONOSCIUTO sul canale di un bot -> rilettura del blocco di QUEL bot
//     subito (non al giro dei 30 s), la riga compare DAL DATABASE;
//  2. id NOTO -> nessuna rilettura (basta l'overlay);
//  3. raffica di righe nuove -> al massimo UNA rilettura per bot ogni 2 s;
//  4. riga che diventa terminale -> una rilettura mirata;
//  5. 4 bot tennis dal canale 47337: `tennis_bot_posizioni` (riga vera di
//     `tennis_live_orders`) e `tennis_bot_stato` (riga vera di
//     `tennis_bot_service_control`), overlay sul poll con eta' e fonte;
//  6. ripiego: canale 47337 giu' -> 'off', eta' del push azzerata, restano i
//     numeri del database.
//
// I finti hanno le chiavi e i tipi delle tabelle vere (`migrations/
// tennis_orders.sql`, `tennis_bot_pnl_2026-09-17.sql`,
// `pnl_betfair_reale_2026-09-24.sql`, `tennis_bot_service_control_2026-09-17.sql`);
// il messaggio e' riga + busta di `Betfair/stream/canale_bot.py`.
//
// FALSIFICAZIONE (esito nel referto): senza `rilettore.current?.chiedi` in
// `suRigaPosizione` il gruppo 1 e il gruppo 5 diventano rossi; senza
// l'anti-tempesta (minimo 0) diventa rosso il gruppo 3; con il topic tennis
// sbagliato diventa rosso il gruppo 5.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { OmegaTrade } from '@/lib/omega';
import type { TennisBotOrderRow, TennisBotServiceRow } from '@/lib/tennis';

// ------------------------------------------------------ canale controllabile
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

import { fetchOmegaTrades } from '@/lib/omega';
import { fetchMikeState } from '@/lib/mike';
import { fetchSafeState } from '@/lib/safeBot';
import { fetchTennisBotOrdersToday, fetchTennisBotServices } from '@/lib/tennis';
import { useControlRoom } from '@/components/controlroom/useControlRoom';

// ------------------------------------------------------------------- finti

function rigaOmega(id: number, over: Partial<OmegaTrade> = {}): OmegaTrade & { commission: number | null } {
    return {
        id, event_id: '34567890', event_name: 'Inter v Milan',
        market_id: '1.234567890', selection_id: 1, runner_name: '1 - 0',
        side: 'lay', mode: 'paper', origin: 'auto', phase: 'ft_cs',
        price: 8.4, size: 1, liability: 7.4, commission: null, target: null,
        minute_at_entry: 12, score_at_entry: '0-0', kickoff: '2026-09-24T18:45:00+00:00',
        status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-24T19:00:00+00:00', settled_at: null,
        closes_trade_id: null, meta: {},
        ...over,
    };
}

/** riga di `tennis_live_orders` come la porta `get_tennis_bot_orders_today`
 *  (`to_jsonb(o.*)`: TUTTE le colonne) e come la pubblica il runner */
function rigaTennis(id: number, over: Partial<TennisBotOrderRow> & Record<string, unknown> = {}): TennisBotOrderRow {
    return {
        id, bet_id: '345678901234', client_order_ref: `tsc-35794049-${id}`, request_id: null,
        mode: 'paper', source: 'tennis_scalper', event_id: '35794049',
        market_id: '1.245678901', selection_id: 10838543, handicap: 0,
        side: 'back', order_type: 'LIMIT', price: 1.85, size: 2,
        size_matched: 2, size_remaining: 0, size_cancelled: 0, size_lapsed: 0, size_voided: 0,
        average_price_matched: 1.85, status: 'EXECUTION_COMPLETE', persistence: 'LAPSE',
        placed_at: '2026-09-24T14:00:00.123456+00:00', matched_at: '2026-09-24T14:00:00.923456+00:00',
        updated_at: '2026-09-24T14:00:01.654321+00:00',
        pnl: null, commission: null, settled_at: null,
        pnl_betfair: null, pnl_betfair_settled_at: null,
        ...({ commissione_betfair: null } as Record<string, unknown>),
        ...over,
    } as TennisBotOrderRow;
}

/** riga di `tennis_bot_service_control` (select *) */
function rigaServizio(over: Partial<TennisBotServiceRow> = {}): TennisBotServiceRow {
    return {
        bot_key: 'tennis_scalper', status: 'stopped', mode: 'paper', stake: 2,
        params: {}, stats: { cadenza_battito_s: 15, partite_esposte: 0, stop_ferma_solo_aperture: true, motivo_blocco: null },
        error: null, started_at: null, stopped_at: null,
        heartbeat_at: '2026-09-24T14:00:00+00:00', updated_at: '2026-09-24T14:00:00+00:00',
        ...over,
    };
}

/** busta di `canale_bot.busta` */
function busta(riga: object, pubblicatoMs: number, seq: number): Record<string, unknown> {
    return { ...riga, fonte: 'canale', _seq: seq, _pubblicato_ms: pubblicatoMs };
}

beforeEach(() => {
    iscritti.clear();
    statoCb.clear();
    statoCanale.clear();
    vi.mocked(fetchOmegaTrades).mockReset().mockResolvedValue([]);
    vi.mocked(fetchSafeState).mockReset().mockResolvedValue({ control: null, trades: [], aggregates: null } as never);
    vi.mocked(fetchMikeState).mockReset().mockResolvedValue({ control: null, events: [], trades: [], activity: [], aggregates: null, requests: [], day_start: null, day_by: null } as never);
    vi.mocked(fetchTennisBotOrdersToday).mockReset().mockResolvedValue([]);
    vi.mocked(fetchTennisBotServices).mockReset().mockResolvedValue([]);
});

async function montato() {
    const h = renderHook(() => useControlRoom());
    await waitFor(() => expect(h.result.current.caricamento).toBe(false));
    return h;
}

// ============================================================ 1) id sconosciuto

describe('riga NUOVA dal canale: rilettura mirata subito', () => {
    it('Omega: id sconosciuto -> fetchOmegaTrades subito, la riga compare dal database', async () => {
        const { result } = await montato();
        expect(result.current.posizioni).toHaveLength(0);
        const prima = vi.mocked(fetchOmegaTrades).mock.calls.length;
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(8)]);
        act(() => { spingi('omega', 'omega_posizioni', busta(rigaOmega(8), Date.now() + 1_000, 1)); });
        // subito: nessuna attesa dei 30 s
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima + 1);
        await waitFor(() => expect(result.current.posizioni.map((p) => p.id)).toEqual([8]));
        // la riga e' entrata dal DATABASE (fonte dichiarata)
        expect(result.current.etaRiga('omega', 8)?.fonte).toBe('database');
    });

    it('Safe e Mike: la rilettura e\' quella del LORO blocco', async () => {
        await montato();
        const safePrima = vi.mocked(fetchSafeState).mock.calls.length;
        const mikePrima = vi.mocked(fetchMikeState).mock.calls.length;
        const omegaPrima = vi.mocked(fetchOmegaTrades).mock.calls.length;
        act(() => {
            spingi('safe', 'safe_posizioni_tennis', busta({ id: 3, sport: 'tennis', status: 'open' }, Date.now() + 1_000, 1));
            spingi('mike', 'mike_posizioni', busta({ id: 4, status: 'open' }, Date.now() + 1_000, 1));
        });
        expect(vi.mocked(fetchSafeState).mock.calls.length).toBe(safePrima + 1);
        expect(vi.mocked(fetchMikeState).mock.calls.length).toBe(mikePrima + 1);
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(omegaPrima);
    });

    it('riga sul topic dello sport sbagliato: nessuna rilettura (fail-closed)', async () => {
        await montato();
        const prima = vi.mocked(fetchSafeState).mock.calls.length;
        act(() => { spingi('safe', 'safe_posizioni_calcio', busta({ id: 3, sport: 'tennis', status: 'open' }, Date.now() + 1_000, 1)); });
        expect(vi.mocked(fetchSafeState).mock.calls.length).toBe(prima);
    });
});

// ================================================================= 2) id noto

describe('riga NOTA: nessuna rilettura', () => {
    it('solo overlay, nessuna chiamata al database', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(7)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(1));
        const prima = vi.mocked(fetchOmegaTrades).mock.calls.length;
        act(() => { spingi('omega', 'omega_posizioni', busta(rigaOmega(7, { price: 6.2 }), Date.now() + 1_000, 3)); });
        expect(result.current.posizioni[0].prezzo).toBe(6.2);
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima);
    });
});

// =========================================================== 3) anti-tempesta

describe('anti-tempesta: al massimo una rilettura per bot ogni 2 s', () => {
    it('50 righe nuove in un colpo: una lettura subito, una sola allo scadere dei 2 s', async () => {
        await montato();
        const prima = vi.mocked(fetchOmegaTrades).mock.calls.length;
        act(() => {
            for (let i = 0; i < 50; i += 1) {
                spingi('omega', 'omega_posizioni', busta(rigaOmega(100 + i), Date.now() + 1_000, i + 1));
            }
        });
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima + 1);
        await waitFor(
            () => expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima + 2),
            { timeout: 3_500 },
        );
        await new Promise((r) => setTimeout(r, 600));
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima + 2);
    }, 10_000);

    it('la stessa riga sconosciuta ripetuta chiede UNA rilettura sola', async () => {
        await montato();
        const prima = vi.mocked(fetchOmegaTrades).mock.calls.length;
        act(() => {
            for (let i = 0; i < 5; i += 1) {
                spingi('omega', 'omega_posizioni', busta(rigaOmega(9), Date.now() + 1_000, i + 1));
            }
        });
        await new Promise((r) => setTimeout(r, 2_300));
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima + 1);
    }, 10_000);
});

// ===================================================== 4) riga che si chiude

describe('riga che DIVENTA terminale: una rilettura mirata', () => {
    it('Omega regolata dal canale -> rilettura', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([rigaOmega(7)]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(1));
        const prima = vi.mocked(fetchOmegaTrades).mock.calls.length;
        act(() => {
            spingi('omega', 'omega_posizioni',
                busta(rigaOmega(7, { status: 'won', pnl: 0.95, settled_at: '2026-09-24T20:40:00+00:00' }), Date.now() + 1_000, 4));
        });
        expect(vi.mocked(fetchOmegaTrades).mock.calls.length).toBe(prima + 1);
        expect(result.current.posizioni).toHaveLength(0);
    });
});

// ============================================== 5) i 4 bot tennis dal 47337

describe('bot tennis dal canale 47337', () => {
    it('sottoscrive i due topic sul canale tennis_bot (sola lettura)', async () => {
        await montato();
        expect(iscritti.get('tennis_bot:tennis_bot_stato')?.size ?? 0).toBeGreaterThan(0);
        expect(iscritti.get('tennis_bot:tennis_bot_posizioni')?.size ?? 0).toBeGreaterThan(0);
    });

    it('riga d\'ordine NUOVA di un bot: rilettura mirata, poi la posizione c\'e\'', async () => {
        const { result } = await montato();
        const prima = vi.mocked(fetchTennisBotOrdersToday).mock.calls.length;
        vi.mocked(fetchTennisBotOrdersToday).mockResolvedValue([rigaTennis(4812)]);
        act(() => { spingi('tennis_bot', 'tennis_bot_posizioni', busta(rigaTennis(4812), Date.now() + 1_000, 1)); });
        expect(vi.mocked(fetchTennisBotOrdersToday).mock.calls.length).toBe(prima + 1);
        await waitFor(() => expect(result.current.posizioni.map((p) => `${p.bot}#${p.id}`)).toEqual(['tennis_scalper#4812']));
    });

    it('riga d\'ordine NOTA: overlay dal canale (fonte locale), nessuna rilettura', async () => {
        vi.mocked(fetchTennisBotOrdersToday).mockResolvedValue([rigaTennis(4812, { size_matched: 1, size_remaining: 1 })]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(1));
        expect(result.current.fonteRighe.tennis.fonte).toBe('database');
        const prima = vi.mocked(fetchTennisBotOrdersToday).mock.calls.length;
        act(() => {
            spingi('tennis_bot', 'tennis_bot_posizioni',
                busta(rigaTennis(4812, { price: 1.9, size_matched: 2, size_remaining: 0 }), Date.now() + 1_000, 2));
        });
        expect(vi.mocked(fetchTennisBotOrdersToday).mock.calls.length).toBe(prima);
        expect(result.current.posizioni[0].prezzo).toBe(1.9);
        expect(result.current.fonteRighe.tennis.fonte).toBe('locale');
        expect(result.current.etaRiga('tennis_scalper', 4812)?.fonte).toBe('locale');
    });

    it('ordine manuale o source sconosciuto: ignorato', async () => {
        const { result } = await montato();
        const prima = vi.mocked(fetchTennisBotOrdersToday).mock.calls.length;
        act(() => {
            spingi('tennis_bot', 'tennis_bot_posizioni', busta(rigaTennis(1, { source: 'runner' }), Date.now() + 1_000, 1));
            spingi('tennis_bot', 'tennis_bot_posizioni', busta({ ...rigaTennis(2), source: 'manual' }, Date.now() + 1_000, 2));
        });
        expect(vi.mocked(fetchTennisBotOrdersToday).mock.calls.length).toBe(prima);
        expect(result.current.posizioni).toHaveLength(0);
    });

    it('paper e live restano separati: il mode e\' quello della riga', async () => {
        vi.mocked(fetchTennisBotOrdersToday).mockResolvedValue([
            rigaTennis(1, { mode: 'paper', size_matched: 1 }), rigaTennis(2, { mode: 'live', size_matched: 1 }),
        ]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.posizioni).toHaveLength(2));
        const modo = (id: number) => result.current.posizioni.find((p) => p.id === id)?.modalita;
        expect(modo(1)).toBe('paper');
        expect(modo(2)).toBe('live');
    });

    it('tennis_bot_stato: lo stato del bot dal canale, piu\' fresco del poll, con l\'eta\' del push', async () => {
        vi.mocked(fetchTennisBotServices).mockResolvedValue([rigaServizio()]);
        const { result } = await montato();
        const scalper = () => result.current.bots.find((b) => b.bot === 'tennis_scalper')!;
        await waitFor(() => expect(scalper().stato).toBe('stopped'));
        expect(scalper().canale).toBe('connected');
        expect(scalper().etaPushS).toBeNull();
        act(() => {
            spingi('tennis_bot', 'tennis_bot_stato',
                busta(rigaServizio({ status: 'running', mode: 'live', heartbeat_at: '2026-09-24T14:00:15+00:00' }), Date.now() + 1_000, 5));
        });
        expect(scalper().stato).toBe('running');
        expect(scalper().modalita).toBe('live');
        expect(scalper().etaPushS).toBe(0);
        // un messaggio piu' vecchio della lettura del database non passa
        act(() => {
            spingi('tennis_bot', 'tennis_bot_stato',
                busta(rigaServizio({ status: 'error' }), Date.now() - 60_000, 99));
        });
        expect(scalper().stato).toBe('running');
    });

    it('tennis_bot_stato per un bot_key non tennis: ignorato', async () => {
        vi.mocked(fetchTennisBotServices).mockResolvedValue([rigaServizio()]);
        const { result } = await montato();
        await waitFor(() => expect(result.current.bots.find((b) => b.bot === 'tennis_scalper')?.stato).toBe('stopped'));
        act(() => {
            spingi('tennis_bot', 'tennis_bot_stato', busta({ ...rigaServizio(), bot_key: 'omega', status: 'running' }, Date.now() + 1_000, 1));
        });
        expect(result.current.bots.find((b) => b.bot === 'omega')?.stato).toBeNull();
    });

    it('mai letto dal database: "stato non letto" anche se il canale parla (niente righe dal canale)', async () => {
        vi.mocked(fetchTennisBotServices).mockRejectedValue(new Error('PGRST205'));
        const { result } = await montato();
        act(() => {
            spingi('tennis_bot', 'tennis_bot_stato', busta(rigaServizio({ status: 'running' }), Date.now() + 1_000, 1));
        });
        expect(result.current.bots.find((b) => b.bot === 'tennis_scalper')?.stato).toBeNull();
    });
});

// ================================================================= 6) ripiego

describe('ripiego: canale 47337 giu\'', () => {
    it('stato off, eta\' del push azzerata, restano i numeri del database', async () => {
        vi.mocked(fetchTennisBotServices).mockResolvedValue([rigaServizio({ status: 'running' })]);
        vi.mocked(fetchTennisBotOrdersToday).mockResolvedValue([rigaTennis(4812, { size_matched: 1 })]);
        const { result } = await montato();
        const scalper = () => result.current.bots.find((b) => b.bot === 'tennis_scalper')!;
        await waitFor(() => expect(scalper().stato).toBe('running'));
        act(() => {
            spingi('tennis_bot', 'tennis_bot_stato', busta(rigaServizio({ status: 'running' }), Date.now() + 1_000, 1));
        });
        expect(scalper().etaPushS).toBe(0);
        act(() => { cambiaStato('tennis_bot', 'off'); });
        expect(scalper().canale).toBe('off');
        expect(scalper().etaPushS).toBeNull();
        expect(scalper().stato).toBe('running');
        expect(result.current.posizioni).toHaveLength(1);
        // gli altri bot non sono toccati dal canale tennis
        expect(result.current.bots.find((b) => b.bot === 'omega')?.canale).toBe('connected');
    });
});
