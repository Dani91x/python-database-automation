// Test COMPONENTE per LiveAlertBanner (fix audit #24): il dismiss è ottimistico,
// ma se ackAlert FALLISCE l'avviso deve RIENTRARE nella lista — mai far sparire
// in silenzio un alert money-critical il cui ack non è mai avvenuto.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/live', () => ({
    fetchLiveAlerts: vi.fn(),
    subscribeLiveAlerts: vi.fn(() => () => {}),
    ackAlert: vi.fn(),
}));

import { LiveAlertBanner } from './LiveAlertBanner';
import { fetchLiveAlerts, ackAlert } from '@/lib/live';

const mFetch = vi.mocked(fetchLiveAlerts);
const mAck = vi.mocked(ackAlert);

const ALERT = {
    id: 7, level: 'CRITICAL', code: 'STOP', message: 'chiusura FALLITA: intervenire',
    acknowledged: false, ts: new Date().toISOString(),
} as never;

beforeEach(() => {
    vi.clearAllMocks();
    mFetch.mockResolvedValue([ALERT]);
});

describe('LiveAlertBanner — fix audit #24', () => {
    it('ack riuscito: l\'avviso sparisce e non torna', async () => {
        mAck.mockResolvedValue(undefined as never);
        const user = userEvent.setup();
        render(<LiveAlertBanner />);
        await screen.findByText(/chiusura FALLITA/);
        await user.click(screen.getByRole('button', { name: /Ignora avviso/ }));
        await waitFor(() => expect(mAck).toHaveBeenCalledWith(7));
        expect(screen.queryByText(/chiusura FALLITA/)).not.toBeInTheDocument();
    });

    it('ack FALLITO: l\'avviso RIENTRA nella lista (mai dismissal silenzioso)', async () => {
        mAck.mockRejectedValue(new Error('permission denied'));
        const user = userEvent.setup();
        render(<LiveAlertBanner />);
        await screen.findByText(/chiusura FALLITA/);
        await user.click(screen.getByRole('button', { name: /Ignora avviso/ }));
        await waitFor(() => expect(mAck).toHaveBeenCalledWith(7));
        // rollback della rimozione ottimistica: l'alert è di nuovo visibile.
        expect(await screen.findByText(/chiusura FALLITA/)).toBeInTheDocument();
    });
});
