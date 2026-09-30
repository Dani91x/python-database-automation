// ============================================================================
// useControlRoom.soldiVeri.test.tsx - P3 (30/09) sul hook VERO: il campo
// `soldiVeri` della testata.
//
//  * l'esposizione e' quella del CONTO: riga `betfair_live_account` (gia' letta
//    dal hook) e, se piu' recente, il topic `account` di QUALSIASI canale che
//    lo pubblica (runner calcio/tennis, Mike, Omega, Safe - `CANALI_SALDO`);
//  * NESSUNA lettura nuova: `fetchLiveAccount`/`subscribeLiveAccount` restano
//    una volta sola (quelle che il hook faceva gia');
//  * il rischio dei bot e' la liability dichiarata LIVE dal servizio.
//
// Finti (chiavi e tipi dei produttori veri):
//  - account  Betfair/stream/reconcile_worker.py:161 {available, exposure, checked_at}
//             e Betfair/stream/saldo_evento.py (stesso messaggio dagli altri processi)
//  - riga     betfair_live_account (lib/liveOrders LiveAccountRow)
//  - aggregati Mike: migrations/mike_aggregati_per_modalita_2026-09-13.sql ('mode',
//             'open_liability', 'liability_source', 'liability_stale')
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
function spingi(sport: string, topic: string, d: unknown): void {
    for (const cb of iscritti.get(`${sport}:${topic}`) ?? []) cb(d);
}

vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn((sport: string) => ({
        getStatus: () => 'connected',
        getHello: () => null,
        onStatus: () => () => { /* niente */ },
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
    // T_P4: lo stop del conto (betfair_live_risk_state)
    fetchLiveRiskState: vi.fn(async () => null),
    subscribeLiveRiskState: vi.fn(() => () => { /* nessuna spinta */ }),
    // W_T/P14: gli ordini del conto fuori dai bot (contratto get_live_orders_account_open)
    fetchLiveOrdersAccountOpen: vi.fn(async () => { throw new Error('Could not find the function public.get_live_orders_account_open'); }),
}));
vi.mock('@/lib/scalperControlRoom', async (orig) => ({
    ...(await orig() as object),
    fetchScalperControlRoom: vi.fn(async () => ({ sessioni: [], ordini: [], lettoAt: null, servizio: null, servizioLetto: false })),
}));

import { fetchMikeState } from '@/lib/mike';
import {
    fetchLiveAccount, subscribeLiveAccount, fetchLiveRiskState, subscribeLiveRiskState,
    fetchLiveOrdersAccountOpen,
} from '@/lib/liveOrders';
import { useControlRoom } from '@/components/controlroom/useControlRoom';

// la riga del database: scritta al cambio, un minuto fa
const riga = () => ({
    id: 1, available: 30.61, exposure: -9.95,
    updated_at: new Date(Date.now() - 60_000).toISOString(),
});

beforeEach(() => {
    iscritti.clear();
    vi.mocked(fetchLiveAccount).mockReset();
    vi.mocked(fetchLiveAccount).mockResolvedValue(riga() as never);
    vi.mocked(subscribeLiveAccount).mockClear();
    vi.mocked(fetchMikeState).mockResolvedValue({
        control: null, events: [], trades: [], activity: [],
        aggregates: {
            mode: 'live', realized_total: 0, realized_today: 0, open_liability: 16.22, open_count: 5,
            won: 0, lost: 0, liability_source: 'net_positions', liability_stale: false,
        },
        requests: [], day_start: null, day_by: null,
    } as never);
});

async function montato() {
    const h = renderHook(() => useControlRoom());
    await waitFor(() => expect(h.result.current.caricamento).toBe(false));
    return h;
}

describe('soldiVeri - l\'esposizione e\' quella del CONTO', () => {
    it('dalla riga del database: -9,95, fonte database', async () => {
        const h = await montato();
        await waitFor(() => expect(h.result.current.soldiVeri.conto.esposizione).toBe(-9.95));
        expect(h.result.current.soldiVeri.conto.fonte).toBe('database');
        expect(h.result.current.soldiVeri.conto.disponibile).toBe(30.61);
    });

    it('un saldo piu\' recente dal canale di MIKE (non solo dal runner calcio) vince', async () => {
        const h = await montato();
        await waitFor(() => expect(h.result.current.soldiVeri.conto.esposizione).toBe(-9.95));
        act(() => spingi('mike', 'account', {
            available: 30.41, exposure: -10.15, checked_at: new Date().toISOString(),
        }));
        await waitFor(() => expect(h.result.current.soldiVeri.conto.esposizione).toBe(-10.15));
        expect(h.result.current.soldiVeri.conto.fonte).toBe('canale');
    });

    it('il messaggio del P&L manuale (senza available) sullo stesso topic NON e\' un saldo', async () => {
        const h = await montato();
        await waitFor(() => expect(h.result.current.soldiVeri.conto.esposizione).toBe(-9.95));
        act(() => spingi('calcio', 'account', {
            manual_pnl_eur: 1.2, pnl_reale_oggi: null, checked_at: new Date().toISOString(),
        }));
        await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
        expect(h.result.current.soldiVeri.conto.esposizione).toBe(-9.95);
        expect(h.result.current.soldiVeri.conto.fonte).toBe('database');
    });

    it('conto mai letto: nessuna cifra', async () => {
        vi.mocked(fetchLiveAccount).mockResolvedValue(null as never);
        const h = await montato();
        await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
        expect(h.result.current.soldiVeri.conto.letto).toBe(false);
        expect(h.result.current.soldiVeri.conto.esposizione).toBeNull();
    });

    it('NESSUNA lettura nuova del conto: una sola fetch e una sola sottoscrizione (quelle di prima)', async () => {
        const h = await montato();
        await waitFor(() => expect(h.result.current.soldiVeri.conto.esposizione).toBe(-9.95));
        expect(vi.mocked(fetchLiveAccount)).toHaveBeenCalledTimes(1);
        expect(vi.mocked(subscribeLiveAccount)).toHaveBeenCalledTimes(1);
    });
});

describe('stopPerdita (T_P4) - lo stop del CONTO dal runner, una lettura sola', () => {
    // riga come la scrive daily_stop_worker._publish_state (daily_stop_worker.py:334-347)
    const RIGA_RISCHIO = {
        id: 1, mode: 'live', day: '2026-09-30', realized: 0, open_mtm: -0.74, total: -0.74,
        limit_value: null, stop_fired: false,
        detail: { reason: 'limit_off', degraded: false, kill_switch: false },
        updated_at: new Date(Date.now() - 30_000).toISOString(),
    };

    it('oggi: stop del conto SPENTO (limit_off), letto con UNA fetch e UNA sottoscrizione', async () => {
        vi.mocked(fetchLiveRiskState).mockClear();
        vi.mocked(subscribeLiveRiskState).mockClear();
        vi.mocked(fetchLiveRiskState).mockResolvedValue(RIGA_RISCHIO as never);
        const h = await montato();
        await waitFor(() => expect(h.result.current.stopPerdita.conto.letto).toBe(true));
        expect(h.result.current.stopPerdita.conto.soglia).toBeNull();
        expect(h.result.current.stopPerdita.conto.motivo).toBe('limit_off');
        expect(vi.mocked(fetchLiveRiskState)).toHaveBeenCalledTimes(1);
        expect(vi.mocked(subscribeLiveRiskState)).toHaveBeenCalledTimes(1);
    });

    it('il push realtime della riga aggiorna lo stop (soglia attivata dall\'utente)', async () => {
        vi.mocked(fetchLiveRiskState).mockResolvedValue(RIGA_RISCHIO as never);
        let spinta: ((r: unknown) => void) | null = null;
        vi.mocked(subscribeLiveRiskState).mockImplementation(((cb: (r: unknown) => void) => {
            spinta = cb; return () => { /* niente */ };
        }) as never);
        const h = await montato();
        await waitFor(() => expect(h.result.current.stopPerdita.conto.letto).toBe(true));
        act(() => spinta?.({ ...RIGA_RISCHIO, limit_value: 40, detail: { reason: 'under_limit' } }));
        await waitFor(() => expect(h.result.current.stopPerdita.conto.soglia).toBe(40));
    });
});

describe('ordiniConto (W_T/P14) - ordini del conto fuori dai bot, nel giro dei 30 s', () => {
    const RIGA = {
        bet_id: '351001', market_id: '1.OU35V', selection_id: 1222347, event_id: 'VSETIN',
        event_name: 'FC Vsetin v Bohemians', market_name: 'Over/Under 3.5 Goals', selection_name: 'Over 3.5 Goals',
        side: 'BACK', price_matched: 1.92, size_matched: 4.43, size_remaining: 0,
        status: 'EXECUTION_COMPLETE', source: 'account', placed_at: '2026-09-30T13:31:02Z',
    };

    it('RPC non ancora applicata: «non letti (RPC non disponibile)», e NON fra le «fonti non raggiunte»', async () => {
        vi.mocked(fetchLiveOrdersAccountOpen).mockRejectedValue(new Error('Could not find the function public.get_live_orders_account_open'));
        const h = await montato();
        await waitFor(() => expect(h.result.current.ordiniConto.motivo).toBe('RPC non disponibile'));
        expect(h.result.current.ordiniConto.stato).toBe('non-letti');
        expect(h.result.current.soldiVeri.ordiniFuori).toMatchObject({ letto: false, motivo: 'RPC non disponibile' });
        expect(h.result.current.errore ?? '').not.toMatch(/ordini/);
    });

    it('letti: per partita, e in testata «1 partita (FC Vsetin v Bohemians)»', async () => {
        vi.mocked(fetchLiveOrdersAccountOpen).mockResolvedValue({ rows: [RIGA], letto_at: new Date().toISOString() } as never);
        const h = await montato();
        await waitFor(() => expect(h.result.current.ordiniConto.stato).toBe('letti'));
        expect(h.result.current.ordiniConto.perEvento.get('VSETIN')?.[0].bet_id).toBe('351001');
        expect(h.result.current.soldiVeri.ordiniFuori).toMatchObject({ letto: true, n: 1, nomi: ['FC Vsetin v Bohemians'] });
    });

    it('una lettura per giro (dentro la ricarica), nessuna lettura in piu\' al montaggio', async () => {
        vi.mocked(fetchLiveOrdersAccountOpen).mockClear();
        vi.mocked(fetchLiveOrdersAccountOpen).mockResolvedValue({ rows: [], letto_at: new Date().toISOString() } as never);
        const h = await montato();
        await waitFor(() => expect(h.result.current.ordiniConto.stato).toBe('letti'));
        expect(vi.mocked(fetchLiveOrdersAccountOpen)).toHaveBeenCalledTimes(1);
        act(() => h.result.current.ricarica());
        await waitFor(() => expect(vi.mocked(fetchLiveOrdersAccountOpen)).toHaveBeenCalledTimes(2));
    });
});

describe('soldiVeri - il rischio secondo i bot', () => {
    it('Mike dichiara 16,22 LIVE: totale 16,22; scarto col conto 6,27', async () => {
        const h = await montato();
        await waitFor(() => expect(h.result.current.soldiVeri.rischioBot.totale).toBe(16.22));
        expect(h.result.current.soldiVeri.scarto).toEqual({ differenza: 6.27, contoPiuAlto: false });
        // la vecchia somma lorda per riga resta dov'era, per chi la usa: la
        // testata non la legge piu'
        expect(h.result.current.totali).toBeDefined();
    });
});
