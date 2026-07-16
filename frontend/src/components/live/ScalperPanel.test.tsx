// Test COMPONENTE per ScalperPanel (fix audit #28): un fallimento PERSISTENTE
// (≥3 di fila) di get_scalper_state deve produrre un avviso esplicito — prima
// il catch era muto e il pannello mostrava per sempre uno stato vecchio.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/scalper', () => ({
    activateScalper: vi.fn(),
    stopScalper: vi.fn(),
    fetchScalperState: vi.fn(),
    SCALPER_PARAM_DEFAULTS: { one_green_per_phase: true },
    SCALPER_PARAM_FIELDS: [],
}));

import { ScalperPanel } from './ScalperPanel';
import { fetchScalperState } from '@/lib/scalper';

const mState = vi.mocked(fetchScalperState);

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
        mState.mockResolvedValue(null);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={15} />);
        await waitFor(() => expect(mState.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 3000 });
        expect(screen.queryByText(/Stato scalper NON aggiornato/)).not.toBeInTheDocument();
    });
});
