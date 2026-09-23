// 23/09 — BUG DELLA TOP BAR RISCHIO FERMA IN CONTROL ROOM / SEGUI LIVE / LIVE PNL:
// piu' sottoscrizioni alla stessa riga singleton `betfair_live_risk_state`
// (LiveControlsPanel + SeguiLive + LivePnl) con lo STESSO nome di canale.
// realtime-js 2.95 restituisce lo stesso canale per lo stesso nome; il secondo
// (e il terzo) binding postgres_changes arrivano dopo il join, e alla risposta
// del server (1 filtro contro 2+ binding) il canale va in errore. Stessa forma
// gia' vista e corretta per subscribeLiveAccount/subscribeLiveHeartbeat.
//
// 1) ANCORA AL VERO: il RealtimeClient VERO di @supabase/realtime-js
//    restituisce davvero lo stesso oggetto per lo stesso nome (nessuna rete:
//    `channel()` non connette nulla finche' non si chiama subscribe).
// 2) Il finto di `supabase.channel` riproduce ESATTAMENTE quel comportamento
//    (stesso nome -> stesso canale) e conta i binding per canale: ogni
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
        // come RealtimeClient.channel: nome gia' visto -> STESSO canale
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

import { subscribeLiveRiskState } from './liveOrders';

beforeEach(() => canali.clear());

describe('realtime-js vero: stesso nome -> stesso canale (la causa)', () => {
    it('RealtimeClient.channel restituisce lo stesso oggetto per lo stesso nome', () => {
        const rc = new RealtimeClient('ws://127.0.0.1:9/realtime/v1', { params: { apikey: 'finto' } });
        const a = rc.channel('betfair_live_risk_state:1');
        const b = rc.channel('betfair_live_risk_state:1');
        expect(a).toBe(b);
    });
});

describe('subscribeLiveRiskState — un canale per sottoscrizione', () => {
    it('due sottoscrizioni alla top bar rischio (LiveControlsPanel + SeguiLive/LivePnl) = due canali, UN binding ciascuno', () => {
        const off1 = subscribeLiveRiskState(() => {});
        const off2 = subscribeLiveRiskState(() => {});
        const tutti = [...canali.values()];
        expect(tutti).toHaveLength(2);
        for (const c of tutti) {
            expect(c.nome.startsWith('betfair_live_risk_state:1:')).toBe(true);
            expect(c.bindings).toBe(1);
            expect(c.subscribes).toBe(1);
        }
        off1(); off2();
    });

    it('anche con tre montanti (LiveControlsPanel + SeguiLive + LivePnl): tre canali distinti', () => {
        const off1 = subscribeLiveRiskState(() => {});
        const off2 = subscribeLiveRiskState(() => {});
        const off3 = subscribeLiveRiskState(() => {});
        const tutti = [...canali.values()];
        expect(tutti).toHaveLength(3);
        for (const c of tutti) expect(c.bindings).toBe(1);
        off1(); off2(); off3();
    });
});
