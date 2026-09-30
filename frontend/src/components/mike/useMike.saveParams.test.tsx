// 30/09 - `useMike().saveParams` RIGETTA con il testo dell'errore della RPC
// (`mike_update_params`), oltre alla notifica `onError`: prima `wrap` lo
// ingoiava e il pannello parametri non poteva dire che il salvataggio era
// fallito. A salvataggio riuscito risolve e rilegge lo stato.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const h = vi.hoisted(() => ({
    update: vi.fn(),
    fetchState: vi.fn(),
}));

vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig<typeof import('@/lib/mike')>()),
    updateMikeParams: h.update,
    fetchMikeState: h.fetchState,
    fetchMikeRequests: vi.fn(async () => []),
    subscribeMike: vi.fn(() => () => {}),
}));

vi.mock('@/lib/localChannel', () => ({
    getLocalChannel: () => ({
        getStatus: () => 'off',
        onStatus: () => () => {},
        on: () => () => {},
        onMessage: () => () => {},
        subscribe: () => () => {},
    }),
}));

import { useMike } from './useMike';
import { MIKE_PARAM_DEFAULTS } from '@/lib/mike';

const STATO = {
    control: null, events: [], trades: [], activity: [], aggregates: null,
    requests: [], day_start: null, day_by: null,
};

describe('useMike.saveParams', () => {
    beforeEach(() => {
        h.update.mockReset();
        h.fetchState.mockReset();
        h.fetchState.mockResolvedValue(STATO);
    });

    it('errore della RPC: rigetta col testo e lo notifica', async () => {
        h.update.mockRejectedValue(new Error('non autorizzato (owner-only)'));
        const onError = vi.fn();
        const { result } = renderHook(() => useMike({ onError }));
        await waitFor(() => expect(h.fetchState).toHaveBeenCalled());
        let errore: unknown = null;
        await act(async () => {
            try { await result.current.saveParams({ ...MIKE_PARAM_DEFAULTS }); } catch (e) { errore = e; }
        });
        expect((errore as Error | null)?.message).toBe('non autorizzato (owner-only)');
        expect(onError).toHaveBeenCalledWith('non autorizzato (owner-only)');
        expect(result.current.busy).toBe(false);
    });

    it('salvataggio riuscito: risolve e rilegge lo stato', async () => {
        h.update.mockResolvedValue({});
        const { result } = renderHook(() => useMike({}));
        await waitFor(() => expect(h.fetchState).toHaveBeenCalled());
        const letture = h.fetchState.mock.calls.length;
        await act(async () => { await result.current.saveParams({ ...MIKE_PARAM_DEFAULTS }); });
        expect(h.update).toHaveBeenCalledTimes(1);
        expect(h.fetchState.mock.calls.length).toBeGreaterThan(letture);
    });
});
