// ============================================================================
// safeBotChiusura.test.ts — LA RICHIESTA CHE PARTE DAVVERO.
//
// Non basta che il bottone esista: deve accodare la RPC GIUSTA col payload
// GIUSTO. Qui si guarda la chiamata campo per campo — `p_kind` e `p_payload` —
// perche' e' l'unico punto in cui un refuso diventa un ordine vero (o un
// ordine mancato).
//
// FALSIFICAZIONE (verificata: i test diventano rossi):
//   · `cashOutEvento` che manda `cashout` invece di `cashout_event` → rosso;
//   · payload senza `event_id` → rosso (non parte nemmeno);
//   · l'errore della RPC inghiottito invece che rilanciato → rosso.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn(), from: vi.fn(), channel: vi.fn(), removeChannel: vi.fn() },
}));

import { supabase } from '@/integrations/supabase/client';
import { cashOutEvento, riprendiEventoSafe } from './safeBot';

const rpc = vi.mocked(supabase.rpc);

beforeEach(() => { rpc.mockReset(); });

function ok(data: unknown = 42) {
    rpc.mockResolvedValue({ data, error: null } as never);
}

describe('cash out globale della partita — safe_request(cashout_event)', () => {
    it('manda il kind e il payload esatti', async () => {
        ok(101);
        const id = await cashOutEvento('35797769');
        expect(id).toBe(101);
        expect(rpc).toHaveBeenCalledTimes(1);
        const [nome, args] = rpc.mock.calls[0] as [string, Record<string, unknown>];
        expect(nome).toBe('safe_request');
        expect(args.p_kind).toBe('cashout_event');
        expect(args.p_payload).toEqual({ event_id: '35797769' });
    });

    it('NON manda trade_id: il cash out globale ragiona per PARTITA', async () => {
        ok();
        await cashOutEvento('35797769');
        const [, args] = rpc.mock.calls[0] as [string, Record<string, unknown>];
        expect(Object.keys(args.p_payload as object)).toEqual(['event_id']);
    });

    it('senza event_id non parte nessuna chiamata', async () => {
        await expect(cashOutEvento('')).rejects.toThrow(/identificativo della partita/);
        expect(rpc).not.toHaveBeenCalled();
    });

    it('la RPC che rifiuta (migrazione non applicata) RILANCIA il suo messaggio', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'kind non valido: cashout_event' } } as never);
        await expect(cashOutEvento('35797769')).rejects.toThrow('kind non valido: cashout_event');
    });
});

describe('riprendi — safe_request(riprendi_evento)', () => {
    it('kind e payload esatti', async () => {
        ok(7);
        await riprendiEventoSafe('35760084');
        const [nome, args] = rpc.mock.calls[0] as [string, Record<string, unknown>];
        expect(nome).toBe('safe_request');
        expect(args.p_kind).toBe('riprendi_evento');
        expect(args.p_payload).toEqual({ event_id: '35760084' });
    });

    it('senza event_id non parte nessuna chiamata', async () => {
        await expect(riprendiEventoSafe('   ')).rejects.toThrow();
        expect(rpc).not.toHaveBeenCalled();
    });
});
