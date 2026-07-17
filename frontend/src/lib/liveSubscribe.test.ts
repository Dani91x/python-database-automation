// Test di @/lib/live.subscribeLiveNow (fix audit #21): due sottoscrizioni allo
// STESSO evento devono usare canali con nomi DIVERSI — con lo stesso topic due
// slot multi-ladder dello stesso evento si contendevano il canale supabase e
// una sottoscrizione restava a secco (ladder congelato senza alcun segnale).
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => {
    const makeChannel = () => {
        const ch = {
            on: vi.fn(() => ch),
            subscribe: vi.fn(() => ch),
        };
        return ch;
    };
    return {
        supabase: {
            channel: vi.fn(() => makeChannel()),
            removeChannel: vi.fn(),
        },
    };
});

import { supabase } from '@/integrations/supabase/client';
import { subscribeLiveNow, subscribeLiveFollowEvent } from './live';

const mChannel = vi.mocked(supabase.channel);

beforeEach(() => {
    vi.clearAllMocks();
});

describe('subscribeLiveNow — fix audit #21 (topic unico per sottoscrizione)', () => {
    it('due subscribe sullo stesso evento → nomi canale DIVERSI, entrambi riconducibili all\'evento', () => {
        const un1 = subscribeLiveNow('evt1', () => {});
        const un2 = subscribeLiveNow('evt1', () => {});
        expect(mChannel).toHaveBeenCalledTimes(2);
        const [name1, name2] = [mChannel.mock.calls[0][0], mChannel.mock.calls[1][0]];
        expect(name1).not.toBe(name2);                 // MAI lo stesso topic (una starverebbe)
        expect(name1).toMatch(/^live_now:evt1:/);
        expect(name2).toMatch(/^live_now:evt1:/);
        un1();
        un2();
        expect(vi.mocked(supabase.removeChannel)).toHaveBeenCalledTimes(2);
    });
});

// Fix 17/07 "Trading = streaming immediato": la pagina Segui Live reagisce in
// REALTIME al cambio di stato del follow (PENDING→STREAMING) invece del poll 15s.
describe('subscribeLiveFollowEvent — aggancio realtime del follow (fix 17/07)', () => {
    it('sottoscrive live_follow filtrata per event_id con topic unico e inoltra payload.new', () => {
        const cb = vi.fn();
        const un = subscribeLiveFollowEvent('evt9', cb);

        expect(mChannel).toHaveBeenCalledTimes(1);
        expect(mChannel.mock.calls[0][0]).toMatch(/^live_follow:evt9:/); // topic unico per evento
        const ch = mChannel.mock.results[0].value;
        const [kind, cfg, handler] = ch.on.mock.calls[0];
        expect(kind).toBe('postgres_changes');
        expect(cfg).toMatchObject({
            schema: 'public',
            table: 'live_follow',
            filter: 'event_id=eq.evt9',
        });

        // il payload di UPDATE (PENDING→STREAMING) arriva al chiamante come riga
        handler({ new: { event_id: 'evt9', status: 'STREAMING' } });
        expect(cb).toHaveBeenCalledWith(expect.objectContaining({ status: 'STREAMING' }));
        // payload DELETE/vuoto → null (il chiamante decide, mai un crash)
        handler({ new: {} });
        expect(cb).toHaveBeenLastCalledWith(null);

        un();
        expect(vi.mocked(supabase.removeChannel)).toHaveBeenCalledTimes(1);
    });

    it('due sottoscrizioni allo stesso evento → topic diversi (nessuna contesa canale)', () => {
        const un1 = subscribeLiveFollowEvent('evt9', () => {});
        const un2 = subscribeLiveFollowEvent('evt9', () => {});
        expect(mChannel.mock.calls[0][0]).not.toBe(mChannel.mock.calls[1][0]);
        un1();
        un2();
    });
});
