// Test dell'hook useSafeBot: guardie del reload (risultati fuori ordine e
// smontaggio), LIVE non ereditato come autorizzazione, cash out in volo.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('@/lib/safeBot', async (orig) => {
    const actual = await orig<typeof import('@/lib/safeBot')>();
    return {
        ...actual,
        fetchSafeState: vi.fn(),
        fetchSafeTrades: vi.fn(async () => []),
        fetchSafeRequests: vi.fn(async () => []),
        fetchOpportunities: vi.fn(async () => []),
        subscribeSafeBot: vi.fn(() => () => {}),
        subscribeOpportunities: vi.fn(() => () => {}),
        requestSafe: vi.fn(async () => 123),
        activateSafe: vi.fn(async () => ({})),
        stopSafe: vi.fn(),
        updateSafeParams: vi.fn(),
    };
});

import { useSafeBot, RELOAD_DEBOUNCE_MS } from './useSafeBot';
import { fetchSafeState, requestSafe, activateSafe, subscribeSafeBot, type SafeState } from '@/lib/safeBot';

const mState = vi.mocked(fetchSafeState);
const mRequest = vi.mocked(requestSafe);
const mActivate = vi.mocked(activateSafe);

function control(over: Record<string, unknown> = {}) {
    return {
        id: 1, status: 'running', mode: 'paper', params: {}, stats: {}, error: null,
        started_at: null, stopped_at: null, heartbeat_at: null, ...over,
    };
}
function stateWith(realizedTotal: number, over: Record<string, unknown> = {}): SafeState {
    return {
        control: control(over) as never,
        trades: [],
        aggregates: { realized_today: 0, realized_total: realizedTotal, open_liability: 0, open_count: 0, won: 0, lost: 0 },
    };
}
function deferred<T>() {
    let resolve!: (v: T) => void;
    const promise = new Promise<T>((r) => { resolve = r; });
    return { promise, resolve };
}

beforeEach(() => {
    vi.clearAllMocks();
    mState.mockResolvedValue(stateWith(0));
});

describe('useSafeBot — reload (MEDIUM-1)', () => {
    it('un risultato fuori ordine NON sovrascrive quello piu recente', async () => {
        const first = deferred<SafeState>();
        const second = deferred<SafeState>();
        mState.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
        const { result } = renderHook(() => useSafeBot());
        // il primo reload (montaggio) e in attesa: se ne lancia un secondo
        await act(async () => { void result.current.reload(); });
        await act(async () => { second.resolve(stateWith(200)); });
        await waitFor(() => expect(result.current.aggregates?.realized_total).toBe(200));
        // ora arriva il PRIMO, vecchio: deve essere ignorato
        await act(async () => { first.resolve(stateWith(100)); });
        expect(result.current.aggregates?.realized_total).toBe(200);
        expect(result.current.loading).toBe(false);
    });

    it('dopo lo smontaggio il reload in volo non tocca lo stato (nessun warning React)', async () => {
        const first = deferred<SafeState>();
        mState.mockReturnValueOnce(first.promise);
        const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
        const { unmount } = renderHook(() => useSafeBot());
        unmount();
        await act(async () => { first.resolve(stateWith(1)); });
        expect(spy).not.toHaveBeenCalled();
        spy.mockRestore();
    });
});

describe('useSafeBot — LIVE ereditato (MEDIUM-4)', () => {
    it('control gia in live: mode=live (banner) ma liveConfirmed=false', async () => {
        mState.mockResolvedValue(stateWith(0, { mode: 'live' }));
        const { result } = renderHook(() => useSafeBot());
        await waitFor(() => expect(result.current.available).toBe(true));
        expect(result.current.mode).toBe('live');
        expect(result.current.liveConfirmed).toBe(false);
    });

    it('setMode(live) su un bot GIA live conferma senza ri-armare il servizio', async () => {
        mState.mockResolvedValue(stateWith(0, { mode: 'live' }));
        const { result } = renderHook(() => useSafeBot());
        await waitFor(() => expect(result.current.available).toBe(true));
        await act(async () => { await result.current.setMode('live'); });
        expect(result.current.liveConfirmed).toBe(true);
        expect(mActivate).not.toHaveBeenCalled();
        // tornare a paper (bot in corsa) ri-arma e toglie la conferma
        await act(async () => { await result.current.setMode('paper'); });
        expect(mActivate).toHaveBeenCalledWith('paper');
        expect(result.current.liveConfirmed).toBe(false);
    });
});

describe('useSafeBot — cash out in volo (HIGH-1)', () => {
    it('isCashOutPending e true mentre la richiesta e in volo e poi si libera', async () => {
        const req = deferred<number>();
        mRequest.mockReturnValueOnce(req.promise);
        const { result } = renderHook(() => useSafeBot());
        await waitFor(() => expect(result.current.available).toBe(true));
        expect(result.current.isCashOutPending(9)).toBe(false);
        let done: Promise<number | null> | undefined;
        await act(async () => { done = result.current.cashout(9, { fraction: 1 }); });
        expect(result.current.isCashOutPending(9)).toBe(true);
        expect(result.current.isCashOutPending(10)).toBe(false);
        await act(async () => { req.resolve(55); await done; });
        expect(result.current.isCashOutPending(9)).toBe(false);
        expect(mRequest).toHaveBeenCalledWith('cashout', { trade_id: 9, fraction: 1 });
    });

    it('gamba di chiusura gia sul DB -> pending anche senza richiesta locale', async () => {
        mState.mockResolvedValue({
            ...stateWith(0),
            trades: [{ id: 10, closes_trade_id: 9, status: 'pending', meta: null } as never],
        });
        const { result } = renderHook(() => useSafeBot());
        await waitFor(() => expect(result.current.trades.length).toBe(1));
        expect(result.current.isCashOutPending(9)).toBe(true);
    });
});

// ---------------------------------------------------------------------------
// Realtime COALIZZATO: un settlement tocca apertura, chiusura, richiesta e
// control (4+ notifiche). Senza debounce partiva una get_safe_state per
// notifica: con dieci posizioni che si regolano insieme sono decine di RPC in
// un secondo. Omega usa 1,2 s, Mike 1,5 s: Safe deve fare lo stesso.
// ---------------------------------------------------------------------------
describe('useSafeBot — notifiche realtime debounced', () => {
    const mSub = vi.mocked(subscribeSafeBot);

    /** cattura la callback passata a subscribeSafeBot */
    function notifier() {
        const calls = mSub.mock.calls;
        const cb = calls.length ? calls[calls.length - 1][0] : undefined;
        if (!cb) throw new Error('subscribeSafeBot non e stato chiamato');
        return cb as () => void;
    }

    it('la finestra e almeno 1 s (come Omega e Mike)', () => {
        expect(RELOAD_DEBOUNCE_MS).toBeGreaterThanOrEqual(1_000);
    });

    it('una RAFFICA di notifiche produce UNA sola ricarica', async () => {
        vi.useFakeTimers();
        try {
            const { result } = renderHook(() => useSafeBot());
            await act(async () => { await Promise.resolve(); });
            expect(mState).toHaveBeenCalledTimes(1);                        // carico iniziale
            const notify = notifier();

            // 8 notifiche ravvicinate (settlement di due posizioni con chiusura)
            act(() => { for (let i = 0; i < 8; i++) notify(); });
            expect(mState).toHaveBeenCalledTimes(1);                       // nessuna ancora

            await act(async () => { await vi.advanceTimersByTimeAsync(RELOAD_DEBOUNCE_MS + 10); });
            expect(mState).toHaveBeenCalledTimes(2);                       // UNA ricarica
            expect(result.current.error).toBeNull();
        } finally {
            vi.useRealTimers();
        }
    });

    it('una notifica dopo la finestra ricarica di nuovo (non si perde nulla)', async () => {
        vi.useFakeTimers();
        try {
            renderHook(() => useSafeBot());
            await act(async () => { await Promise.resolve(); });
            expect(mState).toHaveBeenCalledTimes(1);
            const notify = notifier();

            act(() => { notify(); });
            await act(async () => { await vi.advanceTimersByTimeAsync(RELOAD_DEBOUNCE_MS + 10); });
            expect(mState).toHaveBeenCalledTimes(2);

            act(() => { notify(); });
            await act(async () => { await vi.advanceTimersByTimeAsync(RELOAD_DEBOUNCE_MS + 10); });
            expect(mState).toHaveBeenCalledTimes(3);
        } finally {
            vi.useRealTimers();
        }
    });

    it('smontaggio durante la finestra: nessuna ricarica dopo lo smontaggio', async () => {
        vi.useFakeTimers();
        try {
            const { unmount } = renderHook(() => useSafeBot());
            await act(async () => { await Promise.resolve(); });
            expect(mState).toHaveBeenCalledTimes(1);
            const notify = notifier();
            act(() => { notify(); });
            unmount();
            await act(async () => { await vi.advanceTimersByTimeAsync(RELOAD_DEBOUNCE_MS + 50); });
            expect(mState).toHaveBeenCalledTimes(1);
        } finally {
            vi.useRealTimers();
        }
    });
});
