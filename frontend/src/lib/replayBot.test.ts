// 06/10 — "Applica bot" del Match Replay: ricostruzione degli ordini del bot
// all'istante della timeline. Fixture = cronologia VERA prodotta dal banco
// (applica_bot.esegui, Scalper media under 2,5 in prova sulla 35797769).
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: vi.fn() } }));

import { conOrdiniDelBot, ordiniBotAlMs, type RigaBot } from './replayBot';
import type { LadderOrderApi } from '@/components/live/LadderView';
import righe from './__fixtures__/replay_bot_media_under_35797769.json';

const R = righe as unknown as RigaBot[];
const MID = '1.259819682';

describe('ordiniBotAlMs — cronologia vera della media under', () => {
    it('prima del primo ordine: niente', () => {
        expect(ordiniBotAlMs(R, R[0]._ms - 1)).toEqual([]);
    });
    it('all\'ingresso: punta abbinata e banca appoggiata (PERSIST, in coda)', () => {
        const o = ordiniBotAlMs(R, R[0]._ms);
        expect(o.map(x => [x.side, x.price, x.status])).toEqual([
            ['back', 2.18, 'EXECUTION_COMPLETE'],
            ['lay', 2.14, 'EXECUTABLE'],
        ]);
        expect(o[1].persistence).toBe('PERSIST');
        expect(o.every(x => x.id < 0 && x.updated_at)).toBe(true);
    });
    it('a fine registrazione: 5 ordini, banca finale 20,18 @2,18 abbinata per intero', () => {
        const o = ordiniBotAlMs(R, Number.MAX_SAFE_INTEGER);
        expect(o).toHaveLength(5);
        const banca = o.find(x => x.side === 'lay' && x.price === 2.18);
        expect(banca?.size_matched).toBeCloseTo(20.18, 2);
        expect(banca?.status).toBe('EXECUTION_COMPLETE');
    });
    it('filtro per mercato', () => {
        expect(ordiniBotAlMs(R, Number.MAX_SAFE_INTEGER, 'altro')).toEqual([]);
        expect(ordiniBotAlMs(R, Number.MAX_SAFE_INTEGER, MID)).toHaveLength(5);
    });
});

describe('conOrdiniDelBot — orderApi del ladder training', () => {
    function base(): LadderOrderApi & { mandati: unknown[] } {
        const mandati: unknown[] = [];
        return {
            mandati,
            send: async (cmd) => { mandati.push(cmd); return { ok: true, action: cmd.action, mode: 'paper' }; },
            fetchOrders: async () => [],
            fetchPositions: async () => [],
        };
    }
    it('fetchOrders aggiunge gli ordini del bot del mercato', async () => {
        const b = base();
        const api = conOrdiniDelBot(b, mid => ordiniBotAlMs(R, R[0]._ms, mid));
        expect(await api.fetchOrders(MID, 'paper')).toHaveLength(2);
        expect(await api.fetchOrders('altro', 'paper')).toHaveLength(0);
    });
    it('l\'annullo di un ordine del bot e\' rifiutato, gli altri passano', async () => {
        const b = base();
        const api = conOrdiniDelBot(b, mid => ordiniBotAlMs(R, R[0]._ms, mid));
        const delBot = ordiniBotAlMs(R, R[0]._ms)[1].bet_id;
        const r = await api.send({ action: 'cancel', mode: 'paper', market_id: MID, bet_id: delBot } as never);
        expect(r.ok).toBe(false);
        expect(b.mandati).toHaveLength(0);
        const r2 = await api.send({ action: 'cancel', mode: 'paper', market_id: MID, bet_id: 'T1' } as never);
        expect(r2.ok).toBe(true);
        expect(b.mandati).toHaveLength(1);
    });
});

import { noteUtili } from './replayBot';
import noteVere from './__fixtures__/replay_bot_note_35797769.json';

describe('noteUtili — cosa ha fatto il bot e perche\' non entrava (note vere del banco)', () => {
    it('tiene ciclo, P&L e motivi di non ingresso; scarta i dettagli tecnici', () => {
        const n = noteUtili(noteVere as string[]);
        expect(n.some(x => x.startsWith('ciclo 1: ingresso 10.00 @2.18'))).toBe(true);
        expect(n.some(x => x.includes('NETTO +0.17'))).toBe(true);
        expect(n.some(x => x.includes("liquidita' sotto il minimo") && x.includes('x4891'))).toBe(true);
        expect(n.some(x => x.includes('controlli M sollecitati'))).toBe(false);
        expect(n).toHaveLength(3);
    });
});
