// ============================================================================
// liveOrders.fuoriBot.test.ts - 08/10 (cantiere W1): il comando degli ordini
// fuori dai bot, col payload ESATTO del contratto con il cantiere W2:
//   { action: 'greenup', mode: 'live', market_id, selection_id, handicap: 0,
//     params: { esposizione: 'fuori_bot' } }
// sulla STESSA coda di sempre (`request_betfair_live_order`, client_ref).
// `sendGreenup` e `buildGreenupParams` non cambiano.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: vi.fn() } }));

import { supabase } from '@/integrations/supabase/client';
import { sendGreenupFuoriBot, sendGreenup, buildGreenupParams } from './liveOrders';

const rpc = supabase.rpc as unknown as ReturnType<typeof vi.fn>;
beforeEach(() => {
    rpc.mockReset();
    rpc.mockImplementation((fn: string) => {
        if (fn === 'request_betfair_live_order') return Promise.resolve({ data: 41, error: null });
        if (fn === 'get_betfair_live_order') {
            return Promise.resolve({ data: { status: 'done', result: { ok: true, action: 'greenup', mode: 'live' } }, error: null });
        }
        return Promise.resolve({ data: null, error: null });
    });
});

function primoP(): Record<string, unknown> {
    const c = rpc.mock.calls.find((x) => x[0] === 'request_betfair_live_order');
    return (c?.[1] as { p: Record<string, unknown> }).p;
}

describe('sendGreenupFuoriBot', () => {
    it('payload ESATTO del contratto W2 (piu\' il client_ref di ogni comando)', async () => {
        const r = await sendGreenupFuoriBot({ marketId: '1.OU25', selectionId: 47973 });
        expect(r.ok).toBe(true);
        const { client_ref: ref, ...p } = primoP();
        expect(p).toEqual({
            action: 'greenup', mode: 'live', market_id: '1.OU25', selection_id: 47973, handicap: 0,
            params: { esposizione: 'fuori_bot' },
        });
        expect(typeof ref).toBe('string');
    });

    it('mercato o selezione mancanti: nessun comando accodato', async () => {
        await expect(sendGreenupFuoriBot({ marketId: '', selectionId: 1 })).rejects.toThrow(/mercato/);
        await expect(sendGreenupFuoriBot({ marketId: '1.2', selectionId: Number.NaN })).rejects.toThrow(/selezione/);
        expect(rpc).not.toHaveBeenCalled();
    });

    it('sendGreenup e buildGreenupParams invariati (nessun `esposizione` di serie)', async () => {
        expect(buildGreenupParams()).toEqual({});
        await sendGreenup({ marketId: '1.9', selectionId: 3, mode: 'paper' });
        const { client_ref: ref, ...p } = primoP();
        expect(typeof ref).toBe('string');
        expect(p).toEqual({ action: 'greenup', mode: 'paper', market_id: '1.9', selection_id: 3, handicap: 0 });
    });
});
