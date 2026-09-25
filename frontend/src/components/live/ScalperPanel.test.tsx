// Test COMPONENTE per ScalperPanel (fix audit #28): un fallimento PERSISTENTE
// (≥3 di fila) di get_scalper_state deve produrre un avviso esplicito — prima
// il catch era muto e il pannello mostrava per sempre uno stato vecchio.
//
// 25/09 sera: sniper_mode ACCESO di default (ordine dell'utente, testuale:
// <<scalper, modalita' sniper: acceso>>). Il form nasce con lo sniper
// spuntato e lo manda esplicito (true/false) all'attivazione.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/scalper', () => ({
    activateScalper: vi.fn(),
    stopScalper: vi.fn(),
    fetchScalperState: vi.fn(),
    SCALPER_PARAM_DEFAULTS: { one_green_per_phase: true },
    SCALPER_PARAM_FIELDS: [],
}));

import { ScalperPanel } from './ScalperPanel';
import { activateScalper, fetchScalperState } from '@/lib/scalper';

const mState = vi.mocked(fetchScalperState);
const mActivate = vi.mocked(activateScalper);

beforeEach(() => {
    vi.clearAllMocks();
});

describe('ScalperPanel — fix audit #28 (errori persistenti visibili)', () => {
    it('3+ fallimenti di fila di get_scalper_state → banner esplicito', async () => {
        mState.mockRejectedValue(new Error('permission denied'));
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={15} />);
        // dopo ≥3 poll falliti compare l'avviso (i primi 2 blip restano silenziosi).
        expect(await screen.findByText(/Stato scalper NON aggiornato/, undefined,
            { timeout: 3000 })).toBeInTheDocument();
        expect(screen.getByText(/permission denied/)).toBeInTheDocument();
    });

    it('un successo azzera il contatore: nessun banner dopo un blip singolo', async () => {
        mState.mockRejectedValueOnce(new Error('blip'));
        mState.mockResolvedValue({ control: null, activity: [] });
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={15} />);
        await waitFor(() => expect(mState.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 3000 });
        expect(screen.queryByText(/Stato scalper NON aggiornato/)).not.toBeInTheDocument();
    });
});

describe('ScalperPanel — sniper ACCESO di default (ordine dell\'utente 25/09 sera)', () => {
    it('il form nasce con lo sniper spuntato e lo manda acceso (true esplicito) all\'attivazione', async () => {
        mState.mockResolvedValue({ control: null, activity: [] });
        mActivate.mockResolvedValue({} as never);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={100_000} />);
        await waitFor(() => expect(mState).toHaveBeenCalled());

        fireEvent.click(screen.getByText('Attiva Scalper Bot'));
        const sniperCheckbox = screen.getByRole('checkbox', { name: /SNIPER in-play/ });
        expect(sniperCheckbox).toBeChecked();

        fireEvent.click(screen.getByText(/Attiva in PAPER/));
        await waitFor(() => expect(mActivate).toHaveBeenCalledTimes(1));
        const params = mActivate.mock.calls[0][4] as Record<string, unknown>;
        expect(params.sniper_mode).toBe(true);
    });

    it('spegnendo il checkbox lo sniper parte spento (sniper_mode=false ESPLICITO, mai assente)', async () => {
        mState.mockResolvedValue({ control: null, activity: [] });
        mActivate.mockResolvedValue({} as never);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={100_000} />);
        await waitFor(() => expect(mState).toHaveBeenCalled());

        fireEvent.click(screen.getByText('Attiva Scalper Bot'));
        const sniperCheckbox = screen.getByRole('checkbox', { name: /SNIPER in-play/ });
        fireEvent.click(sniperCheckbox);
        expect(sniperCheckbox).not.toBeChecked();

        fireEvent.click(screen.getByText(/Attiva in PAPER/));
        await waitFor(() => expect(mActivate).toHaveBeenCalledTimes(1));
        const params = mActivate.mock.calls[0][4] as Record<string, unknown>;
        expect(params.sniper_mode).toBe(false);
    });
});
