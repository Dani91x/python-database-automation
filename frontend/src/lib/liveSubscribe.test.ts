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
import { subscribeLiveNow } from './live';

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
