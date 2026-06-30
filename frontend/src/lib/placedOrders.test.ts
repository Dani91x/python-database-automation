// Test della logica "Ordini piazzati": stato sintetico (placedOrderState) e
// lettura (fetchBetfairOrders). betfair.ts importa il client Supabase in fase di
// import → lo mockiamo per evitare rete/login (come liveOrders.test.ts).
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn() },
}));

import { supabase } from '@/integrations/supabase/client';
import { placedOrderState, fetchBetfairOrders, type PlacedOrder } from './betfair';

const rpc = supabase.rpc as unknown as ReturnType<typeof vi.fn>;

function ord(partial: Partial<PlacedOrder>): PlacedOrder {
    return {
        id: 1, market: 'ht_1x2', selection: 'D', side: 'back', price: 2.6, size: 2,
        liability: null, persistence: 'LAPSE', fill_or_kill: false,
        status: 'done', result: null, error: null,
        requested_at: '2026-06-30T13:40:29Z', processed_at: '2026-06-30T13:40:31Z',
        ...partial,
    };
}

describe('placedOrderState — stato sintetico dell ordine', () => {
    it('pending → queued', () => {
        expect(placedOrderState(ord({ status: 'pending', result: null }))).toBe('queued');
    });
    it('processing → sending', () => {
        expect(placedOrderState(ord({ status: 'processing', result: null }))).toBe('sending');
    });
    it('status error → error', () => {
        expect(placedOrderState(ord({ status: 'error', error: 'rifiutato' }))).toBe('error');
    });
    it('done ma result.ok=false → error', () => {
        expect(placedOrderState(ord({ status: 'done', result: { ok: false } }))).toBe('error');
    });
    it('done + abbinato completo → matched', () => {
        expect(placedOrderState(ord({ size: 2, result: { ok: true, size_matched: 2 } }))).toBe('matched');
    });
    it('done + abbinato parziale → partial', () => {
        expect(placedOrderState(ord({ size: 10, result: { ok: true, size_matched: 4 } }))).toBe('partial');
    });
    it('done + 0 abbinato (resta sul book) → unmatched', () => {
        expect(placedOrderState(ord({ size: 5, result: { ok: true, size_matched: 0 } }))).toBe('unmatched');
    });
    it('matched gestisce arrotondamenti (matched ~ stake) → matched', () => {
        expect(placedOrderState(ord({ size: 2, result: { ok: true, size_matched: 1.999999999 } }))).toBe('matched');
    });
    it('done con result=null → unmatched (matched=0 di default)', () => {
        expect(placedOrderState(ord({ status: 'done', result: null }))).toBe('unmatched');
    });
    it('stake da result.size quando size riga è null (matched completo) → matched', () => {
        expect(placedOrderState(ord({ size: null, result: { ok: true, size: 5, size_matched: 5 } }))).toBe('matched');
    });
});

describe('fetchBetfairOrders', () => {
    beforeEach(() => rpc.mockReset());

    it('chiama get_betfair_orders col fixture_id e ritorna l array', async () => {
        const rows = [ord({ id: 2 }), ord({ id: 1 })];
        rpc.mockResolvedValue({ data: rows, error: null });
        const res = await fetchBetfairOrders(1554594);
        expect(rpc).toHaveBeenCalledWith('get_betfair_orders', { p_fixture_id: 1554594 });
        expect(res).toHaveLength(2);
    });
    it('data non-array → []', async () => {
        rpc.mockResolvedValue({ data: null, error: null });
        expect(await fetchBetfairOrders(1)).toEqual([]);
    });
    it('errore RPC → throw', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'non autorizzato (owner-only)' } });
        await expect(fetchBetfairOrders(1)).rejects.toThrow('owner-only');
    });
});
