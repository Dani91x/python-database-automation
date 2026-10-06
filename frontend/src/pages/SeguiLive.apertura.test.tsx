// 06/10 — Segui Live: "clicco una partita e non si carica nulla".
// * le partite seguite in automatico dai bot (origine 'auto') si APRONO con la
//   RPC segui_live_apri_partita (migrazione segui_live_apri_partita_2026-10-06.sql);
// * la scheda di aggancio mostra la spia del runner (prima stava solo nel
//   terminale, assente proprio mentre l'aggancio e' fermo) e l'esito
//   dell'apertura, compreso l'errore (migrazione non applicata).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const { rpcMock, hbRef } = vi.hoisted(() => ({
    rpcMock: vi.fn(),
    hbRef: { ts: null as string | null },
}));

vi.mock('@/integrations/supabase/client', () => {
    const channelStub: Record<string, unknown> = {};
    channelStub.on = () => channelStub;
    channelStub.subscribe = () => channelStub;
    return {
        supabase: {
            rpc: rpcMock,
            channel: () => channelStub,
            removeChannel: vi.fn(),
        },
    };
});

vi.mock('@/lib/liveOrders', async (importOriginal) => {
    const vero = await importOriginal<typeof import('@/lib/liveOrders')>();
    return {
        ...vero,
        // riga betfair_live_heartbeat con le chiavi vere (LiveHeartbeatRow)
        fetchLiveHeartbeat: vi.fn(async () => (hbRef.ts
            ? { id: 1, ts: hbRef.ts, pid: 4242, mode: 'PAPER', watchdog_ts: null,
                watchdog_pid: null, updated_at: hbRef.ts }
            : null)),
        subscribeLiveHeartbeat: vi.fn(() => () => {}),
    };
});

import { apriPartitaSeguiLive, seguitaDaiBot } from '@/lib/live';
import { AttachProgress } from './SeguiLive';

beforeEach(() => {
    rpcMock.mockReset();
    hbRef.ts = null;
});

describe('apriPartitaSeguiLive (RPC segui_live_apri_partita)', () => {
    it('chiama la RPC con event_id e dice se ha promosso la riga', async () => {
        rpcMock.mockResolvedValue({ data: { promossa: true, follow: { event_id: 'E1' } }, error: null });
        await expect(apriPartitaSeguiLive('E1')).resolves.toEqual({ promossa: true });
        expect(rpcMock).toHaveBeenCalledWith('segui_live_apri_partita', { p_event_id: 'E1' });
    });

    it('riga gia\' manuale: promossa=false, nessun errore', async () => {
        rpcMock.mockResolvedValue({ data: { promossa: false, follow: { event_id: 'E1' } }, error: null });
        await expect(apriPartitaSeguiLive('E1')).resolves.toEqual({ promossa: false });
    });

    it('propaga l\'errore (migrazione non applicata)', async () => {
        rpcMock.mockResolvedValue({ data: null, error: { message: 'function segui_live_apri_partita does not exist' } });
        await expect(apriPartitaSeguiLive('E1')).rejects.toThrow('does not exist');
    });

    it('seguitaDaiBot: solo origine auto', () => {
        expect(seguitaDaiBot({ origine: 'auto' })).toBe(true);
        expect(seguitaDaiBot({ origine: 'manuale' })).toBe(false);
        expect(seguitaDaiBot({ origine: null })).toBe(false);
        expect(seguitaDaiBot(null)).toBe(false);
    });
});

describe('AttachProgress — spia del runner ed esito dell\'apertura', () => {
    it('runner vivo: spia verde dentro la scheda', async () => {
        hbRef.ts = new Date(Date.now() - 4000).toISOString();
        render(<AttachProgress stage={3} />);
        const spia = await screen.findByText(/♥ runner/);
        expect(spia.getAttribute('data-testid')).toBe('spia-runner');
        expect(screen.queryByText(/Il runner non risponde/)).toBeNull();
    });

    it('runner fermo: lo dice nella scheda (non rimanda alla barra che non c\'e\')', async () => {
        hbRef.ts = new Date(Date.now() - 600_000).toISOString();
        render(<AttachProgress stage={2} />);
        expect(await screen.findByText(/RUNNER GIÙ/)).toBeTruthy();
        expect(screen.getByText(/Il runner non risponde/)).toBeTruthy();
    });

    it('partita dei bot in apertura e poi aperta', async () => {
        hbRef.ts = new Date().toISOString();
        const { rerender } = render(
            <AttachProgress stage={2} apertura={{ eventId: 'E1', stato: 'in_corso' }} />);
        expect(screen.getByText(/La sto aprendo nel terminale/)).toBeTruthy();
        rerender(<AttachProgress stage={2} apertura={{ eventId: 'E1', stato: 'fatta' }} />);
        expect(screen.getByText(/il runner la aggancia a caldo/)).toBeTruthy();
    });

    it('apertura fallita: errore e migrazione da applicare', () => {
        render(<AttachProgress stage={2}
            apertura={{ eventId: 'E1', stato: 'errore', errore: 'function does not exist' }} />);
        expect(screen.getByText(/Non riesco ad aprire la partita: function does not exist/)).toBeTruthy();
        expect(screen.getByText(/segui_live_apri_partita_2026-10-06\.sql/)).toBeTruthy();
    });
});
