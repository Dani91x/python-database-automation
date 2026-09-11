// Test delle RPC e del canale realtime di Mike (client Supabase mockato).
//
// Copre la checklist di certificazione:
//   * 2  — ogni pulsante chiama la RPC owner-only attesa, con i parametri attesi;
//   * 3  — UN solo canale, e sottoscrive TUTTE le tabelle che il servizio scrive
//          (`mike_activity` compresa); il battito NON scatena un cambio;
//   * 9  — la RPC VECCHIA (`get_mike_state` v1, senza requests/day_start/day_by)
//          non rompe la pagina: il data-layer normalizza con dei ripieghi.
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn(), from: vi.fn(), channel: vi.fn(), removeChannel: vi.fn() },
}));

import { supabase } from '@/integrations/supabase/client';
import {
    activateMike, stopMike, updateMikeParams, fetchMikeState, fetchMikeTrades, requestMike,
    fetchMikeRequests, subscribeMike, MIKE_REALTIME_TABLES, MIKE_PARAM_DEFAULTS,
} from './mike';

const rpc = vi.mocked(supabase.rpc);
const from = vi.mocked(supabase.from);
const channel = vi.mocked(supabase.channel);

function okRpc(data: unknown) {
    rpc.mockResolvedValue({ data, error: null } as never);
}

beforeEach(() => {
    rpc.mockReset();
    from.mockReset();
    channel.mockReset();
});

describe('mike RPC: un pulsante, una RPC owner-only', () => {
    it('Avvia / PAPER-LIVE → mike_activate con la modalità', async () => {
        okRpc({ id: 1, status: 'running', mode: 'live' });
        await activateMike('live');
        expect(rpc).toHaveBeenCalledWith('mike_activate', { p_mode: 'live', p_params: null });
        okRpc({ id: 1 });
        await activateMike('paper', { ...MIKE_PARAM_DEFAULTS });
        expect(rpc.mock.calls[1][1]).toMatchObject({ p_mode: 'paper' });
        expect((rpc.mock.calls[1][1] as { p_params: Record<string, unknown> }).p_params.stake).toBe(10);
    });

    it('Ferma → mike_stop senza argomenti', async () => {
        okRpc({ id: 1, status: 'stopping' });
        await stopMike();
        expect(rpc).toHaveBeenCalledWith('mike_stop', {});
    });

    it('Salva parametri → mike_update_params (modalità solo se richiesta)', async () => {
        okRpc({ id: 1 });
        await updateMikeParams({ stake: 12 });
        expect(rpc).toHaveBeenCalledWith('mike_update_params', { p_params: { stake: 12 }, p_mode: null });
        okRpc({ id: 1 });
        await updateMikeParams({ stake: 12 }, 'live');
        expect(rpc.mock.calls[1][1]).toEqual({ p_params: { stake: 12 }, p_mode: 'live' });
    });

    it('Cash out / Flatten / Annulla / Salta / Riprendi → mike_request con il kind', async () => {
        for (const kind of ['cashout', 'flatten', 'cancel', 'skip_event', 'resume_event'] as const) {
            rpc.mockReset();
            okRpc(42);
            await expect(requestMike(kind, { event_id: 'E1' })).resolves.toBe(42);
            expect(rpc).toHaveBeenCalledWith('mike_request', { p_kind: kind, p_payload: { event_id: 'E1' } });
        }
    });

    it('ogni errore della RPC arriva alla UI come Error (mai un silenzio)', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'non autorizzato (owner-only)' } } as never);
        await expect(activateMike('paper')).rejects.toThrow('non autorizzato');
        await expect(stopMike()).rejects.toThrow('non autorizzato');
        await expect(updateMikeParams({})).rejects.toThrow('non autorizzato');
        await expect(fetchMikeState()).rejects.toThrow('non autorizzato');
        await expect(fetchMikeTrades()).rejects.toThrow('non autorizzato');
        await expect(requestMike('cashout', {})).rejects.toThrow('non autorizzato');
    });

    it('le richieste di ripiego si leggono dalla tabella in sola lettura', async () => {
        const limit = vi.fn(async () => ({ data: [{ id: 1 }], error: null }));
        const order = vi.fn(() => ({ limit }));
        const select = vi.fn(() => ({ order }));
        from.mockReturnValue({ select } as never);
        await expect(fetchMikeRequests(5)).resolves.toEqual([{ id: 1 }]);
        expect(from).toHaveBeenCalledWith('mike_requests');
        expect(order).toHaveBeenCalledWith('id', { ascending: false });
        expect(limit).toHaveBeenCalledWith(5);
    });
});

describe('mike RPC: get_mike_state v1 (senza migrazione v2)', () => {
    it('la RPC VECCHIA non rompe nulla: ripieghi dichiarati', async () => {
        okRpc({
            control: { id: 1, status: 'running', mode: 'paper' },
            events: [{ event_id: 'E1' }],
            trades: [{ id: 1 }],
            activity: [{ id: 1, kind: 'armed' }],
            aggregates: null,
            // v1: nessun `requests`, nessun `day_start`, nessun `day_by`
        });
        const s = await fetchMikeState();
        expect(rpc).toHaveBeenCalledWith('get_mike_state', {});
        expect(s.control).not.toBeNull();
        expect(s.events).toHaveLength(1);
        expect(s.trades).toHaveLength(1);
        expect(s.activity).toHaveLength(1);
        expect(s.requests).toEqual([]);
        expect(s.day_start).toBeNull();
        expect(s.day_by).toBeNull();
        expect(s.aggregates).toBeNull();
    });

    it('una risposta vuota o malformata non manda in errore la pagina', async () => {
        okRpc(null);
        const s = await fetchMikeState();
        expect(s).toEqual({ control: null, events: [], trades: [], activity: [], aggregates: null,
                            requests: [], day_start: null, day_by: null });
        okRpc({ events: 'non un array', trades: null, activity: 7, requests: {} });
        const s2 = await fetchMikeState();
        expect(s2.events).toEqual([]);
        expect(s2.trades).toEqual([]);
        expect(s2.activity).toEqual([]);
        expect(s2.requests).toEqual([]);
    });
});

describe('mike realtime: UN canale, tutte le tabelle, nessun reload per il battito', () => {
    function fakeChannel() {
        const handlers: { table: string; cb: (p: { new?: unknown }) => void }[] = [];
        const ch: Record<string, unknown> = {};
        ch.on = vi.fn((_evt: string, opts: { table: string }, cb: (p: { new?: unknown }) => void) => {
            handlers.push({ table: opts.table, cb });
            return ch;
        });
        ch.subscribe = vi.fn(() => ch);
        channel.mockReturnValue(ch as never);
        return { ch, handlers };
    }

    it('un solo canale e le cinque tabelle del servizio', () => {
        const { ch, handlers } = fakeChannel();
        const off = subscribeMike(() => {});
        expect(channel).toHaveBeenCalledTimes(1);
        expect(channel).toHaveBeenCalledWith('mike-live');
        expect(handlers.map((h) => h.table)).toEqual([...MIKE_REALTIME_TABLES]);
        expect(handlers.map((h) => h.table)).toContain('mike_activity');
        expect(ch.subscribe).toHaveBeenCalledTimes(1);
        off();
        expect(supabase.removeChannel).toHaveBeenCalledWith(ch);
    });

    it('il battito del servizio NON fa ricaricare, un cambio vero sì (H5)', () => {
        const { handlers } = fakeChannel();
        const onChange = vi.fn();
        subscribeMike(onChange);
        const control = handlers.find((h) => h.table === 'mike_control')!;
        const base = {
            id: 1, status: 'running', mode: 'paper', params: { stake: 10 },
            stats: { trades_open: 2, last_cycle: 'T1', scanner_age_s: 2 },
            heartbeat_at: 'T1', updated_at: 'T1',
        };
        control.cb({ new: base });                       // primo giro: memorizza la firma
        expect(onChange).toHaveBeenCalledTimes(1);
        // SOLO battito (heartbeat/updated_at/last_cycle/scanner_age_s): nessun reload
        control.cb({ new: { ...base, heartbeat_at: 'T2', updated_at: 'T2',
                            stats: { trades_open: 2, last_cycle: 'T2', scanner_age_s: 9 } } });
        expect(onChange).toHaveBeenCalledTimes(1);
        // cambio VERO (una posizione in piu'): reload
        control.cb({ new: { ...base, stats: { trades_open: 3, last_cycle: 'T3', scanner_age_s: 9 } } });
        expect(onChange).toHaveBeenCalledTimes(2);
    });

    it('le altre tabelle notificano sempre, con il nome della tabella', () => {
        const { handlers } = fakeChannel();
        const onChange = vi.fn();
        subscribeMike(onChange);
        for (const table of ['mike_events', 'mike_trades', 'mike_activity', 'mike_requests']) {
            handlers.find((h) => h.table === table)!.cb({ new: { id: 1 } });
            expect(onChange).toHaveBeenLastCalledWith(table);
        }
        expect(onChange).toHaveBeenCalledTimes(4);
    });
});
