// Test COMPONENTE per LiveTradingPanel (jsdom + React Testing Library).
// @/lib/liveOrders è mockato (nessuna rete). Copre il fix audit #6: il flusso
// submin (place-and-trim) IGNORA FoK/min_fill/persistence lato worker → quando
// è attivo i controlli sono disabilitati e azzerati, con nota esplicita (mai
// promettere protezioni non implementate).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/liveOrders', () => ({
    sendLiveOrderCommand: vi.fn(),
    fetchLiveOrders: vi.fn(),
    fetchLivePositions: vi.fn(),
    // helper PURI reimplementati (mock totale del modulo → niente client supabase)
    layLiabilityFromSize: (size: number, price: number) =>
        Math.round(size * (price - 1) * 100) / 100,
    laySizeFromLiability: (liability: number, price: number) =>
        Math.round((liability / (price - 1)) * 100) / 100,
    shouldResetLiveConfirm: (isLive: boolean, ok: boolean) => isLive === true && ok === true,
    LIVE_ORDER_STATUS_LABEL: {},
}));

import { LiveTradingPanel } from './LiveTradingPanel';
import { fetchLiveOrders, fetchLivePositions, sendLiveOrderCommand } from '@/lib/liveOrders';

const mOrders = vi.mocked(fetchLiveOrders);
const mPositions = vi.mocked(fetchLivePositions);
const mSend = vi.mocked(sendLiveOrderCommand);

const selections = [{ selection_id: 47, name: 'Over 2.5' }];

beforeEach(() => {
    vi.clearAllMocks();
    mOrders.mockResolvedValue([]);
    mPositions.mockResolvedValue([]);
    mSend.mockResolvedValue({ ok: true, action: 'place', mode: 'paper' });
});

describe('LiveTradingPanel — fix audit #6 (submin vs FoK/persistence)', () => {
    it('attivando il place-and-trim, FoK e Persistenza si disabilitano e azzerano (con nota)', async () => {
        const user = userEvent.setup();
        render(<LiveTradingPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);
        await waitFor(() => expect(mOrders).toHaveBeenCalled());

        const fok = screen.getByRole('checkbox', { name: /Fill-or-Kill/ });
        const submin = screen.getByRole('checkbox', { name: /Place-and-trim/ });
        // FoK acceso prima del submin: deve venire AZZERATO all'attivazione.
        await user.click(fok);
        expect(fok).toBeChecked();

        await user.click(submin);
        expect(submin).toBeChecked();
        expect(fok).not.toBeChecked();      // azzerato: mai inviato "per sbaglio"
        expect(fok).toBeDisabled();
        // la persistenza è bloccata su LAPSE e disabilitata.
        const persistence = screen.getByDisplayValue('LAPSE (decade in-play)');
        expect(persistence).toBeDisabled();
        // nota esplicita: il flusso sotto-minimo non applica FoK/persistenza.
        expect(screen.getByText(/FoK e persistenza non si applicano/)).toBeInTheDocument();
    });

    it('disattivando il submin i controlli tornano operabili', async () => {
        const user = userEvent.setup();
        render(<LiveTradingPanel marketId="1.234" mode="paper" selections={selections} pollMs={0} />);
        await waitFor(() => expect(mOrders).toHaveBeenCalled());

        const submin = screen.getByRole('checkbox', { name: /Place-and-trim/ });
        await user.click(submin);
        await user.click(submin);
        expect(screen.getByRole('checkbox', { name: /Fill-or-Kill/ })).toBeEnabled();
        expect(screen.getByDisplayValue('LAPSE (decade in-play)')).toBeEnabled();
        expect(screen.queryByText(/FoK e persistenza non si applicano/)).not.toBeInTheDocument();
    });
});
