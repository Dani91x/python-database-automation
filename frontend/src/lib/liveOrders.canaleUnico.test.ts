// 23/09 — BUG DEL SALDO FERMO IN CONTROL ROOM: due sottoscrizioni alla stessa
// riga `betfair_live_account` (SaldoBetfairCard + useControlRoom) con lo
// STESSO nome di canale. realtime-js 2.95 restituisce lo stesso canale per lo
// stesso nome; il secondo binding postgres_changes arriva dopo il join, e alla
// risposta del server (1 filtro contro 2 binding) il canale va in errore.
//
// 1) ANCORA AL VERO: il RealtimeClient VERO di @supabase/realtime-js
//    restituisce davvero lo stesso oggetto per lo stesso nome (nessuna rete:
//    `channel()` non connette nulla finché non si chiama subscribe).
// 2) Il finto di `supabase.channel` riproduce ESATTAMENTE quel comportamento
//    (stesso nome → stesso canale) e conta i binding per canale: ogni
//    sottoscrizione deve avere il SUO canale con UN solo binding.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RealtimeClient } from '@supabase/realtime-js';

interface CanaleFinto {
    nome: string;
    bindings: number;
    subscribes: number;
    on: (...a: unknown[]) => CanaleFinto;
    subscribe: () => CanaleFinto;
}

const canali = new Map<string, CanaleFinto>();

vi.mock('@/integrations/supabase/client', () => ({
    supabase: {
        rpc: vi.fn(),
        // come RealtimeClient.channel: nome già visto → STESSO canale
        channel: vi.fn((nome: string) => {
            let c = canali.get(nome);
            if (!c) {
                const nuovo: CanaleFinto = {
                    nome, bindings: 0, subscribes: 0,
                    on: () => { nuovo.bindings += 1; return nuovo; },
                    subscribe: () => { nuovo.subscribes += 1; return nuovo; },
                };
                c = nuovo;
                canali.set(nome, c);
            }
            return c;
        }),
        removeChannel: vi.fn(),
    },
}));

import { subscribeLiveAccount, subscribeLiveHeartbeat } from './liveOrders';

beforeEach(() => canali.clear());

describe('realtime-js vero: stesso nome → stesso canale (la causa)', () => {
    it('RealtimeClient.channel restituisce lo stesso oggetto per lo stesso nome', () => {
        const rc = new RealtimeClient('ws://127.0.0.1:9/realtime/v1', { params: { apikey: 'finto' } });
        const a = rc.channel('betfair_live_account:1');
        const b = rc.channel('betfair_live_account:1');
        expect(a).toBe(b);
    });
});

describe('subscribeLiveAccount / subscribeLiveHeartbeat — un canale per sottoscrizione', () => {
    it('due sottoscrizioni al saldo (card + useControlRoom) = due canali, UN binding ciascuno', () => {
        const off1 = subscribeLiveAccount(() => {});
        const off2 = subscribeLiveAccount(() => {});
        const tutti = [...canali.values()];
        expect(tutti).toHaveLength(2);
        for (const c of tutti) {
            expect(c.nome.startsWith('betfair_live_account:1:')).toBe(true);
            expect(c.bindings).toBe(1);
            expect(c.subscribes).toBe(1);
        }
        off1(); off2();
    });

    it('lo stesso per il battito del runner', () => {
        subscribeLiveHeartbeat(() => {});
        subscribeLiveHeartbeat(() => {});
        const tutti = [...canali.values()];
        expect(tutti).toHaveLength(2);
        for (const c of tutti) expect(c.bindings).toBe(1);
    });
});
