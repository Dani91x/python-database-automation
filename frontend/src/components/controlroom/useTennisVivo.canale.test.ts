// ============================================================================
// useTennisVivo.canale.test.ts - 25/09 (voce 5): il tennis della scheda
// partita dal canale del runner tennis (47332, topic `now`) prima del
// realtime Supabase, che resta il RIPIEGO dichiarato.
//
// Finto = messaggio VERO: `Betfair/stream/tennis_live/tennis_db.py:279-291`
// pubblica sul canale la STESSA riga che poi va in upsert su `tennis_live_now`:
// {event_id, inplay, status, state, score, points, updated_at} (updated_at =
// `_now_iso()`, isoformat UTC con microsecondi).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const h = vi.hoisted(() => ({
    rowDb: null as unknown,
    realtime: new Map<string, (row: unknown) => void>(),
    canale: new Set<(d: unknown) => void>(),
}));

vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    fetchTennisNow: vi.fn(async () => h.rowDb),
    subscribeTennisNow: vi.fn((eventId: string, cb: (row: unknown) => void) => {
        h.realtime.set(eventId, cb);
        return () => { h.realtime.delete(eventId); };
    }),
}));
vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn(() => ({
        getStatus: () => 'connected' as const,
        getHello: () => null,
        onStatus: () => () => { /* nessun cambio */ },
        subscribe: (topic: string, cb: (d: unknown) => void) => {
            if (topic !== 'now') return () => { /* altro topic */ };
            h.canale.add(cb);
            return () => { h.canale.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));

import { useTennisVivo } from './useTennisVivo';

function riga(eventId: string, updatedAt: string, games: { p1: number; p2: number }) {
    return {
        event_id: eventId, inplay: true, status: 'OPEN',
        state: {
            markets: [{
                market_id: '1.99', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
                selections: [
                    { selection_id: 111, name: 'Sinner J.', back: 1.5, lay: 1.52, ltp: 1.5 },
                    { selection_id: 222, name: 'Alcaraz C.', back: 2.9, lay: 2.96, ltp: 2.9 },
                ],
            }],
            order_mode: 'PAPER', updated_ms: Date.parse(updatedAt),
        },
        score: {
            status: 'InPlay', sets: { p1: 0, p2: 0 }, games, points: { p1: '15', p2: '0' }, server: 1,
            tiebreak: false, game_sequence: { p1: [], p2: [] }, service_breaks: { p1: 0, p2: 0 },
            current_set: 1, current_game: games.p1 + games.p2 + 1, set_summary: `${games.p1}-${games.p2}`,
            pressure: { break_point: false, set_point: false, game_point: false },
            win_prob_p1: 0.6, source: 'ips', updated_ms: Date.parse(updatedAt),
        },
        points: [],
        updated_at: updatedAt,
    };
}
function spingi(d: unknown) { for (const cb of h.canale) cb(d); }

const T0 = '2026-09-25T13:00:00.100000+00:00';
const T1 = '2026-09-25T13:00:02.300000+00:00';
const T2 = '2026-09-25T13:00:04.000000+00:00';

beforeEach(() => {
    h.rowDb = null;
    h.realtime.clear();
    h.canale.clear();
});

describe('useTennisVivo - canale 47332 prima del realtime', () => {
    it('riga dal database: fonte "database"; riga piu\' recente dal canale: fonte "canale"', async () => {
        h.rowDb = riga('EV1', T0, { p1: 1, p2: 0 });
        const r = renderHook(() => useTennisVivo('EV1'));
        await waitFor(() => expect(r.result.current.fonte).toBe('database'));
        act(() => spingi(riga('EV1', T1, { p1: 2, p2: 0 })));
        await waitFor(() => expect(r.result.current.fonte).toBe('canale'));
        expect(r.result.current.row?.score?.games).toEqual({ p1: 2, p2: 0 });
        r.unmount();
    });

    it('la stessa scrittura arrivata poi dal realtime non cambia la fonte (a parita\' resta)', async () => {
        h.rowDb = riga('EV2', T0, { p1: 1, p2: 0 });
        const r = renderHook(() => useTennisVivo('EV2'));
        await waitFor(() => expect(r.result.current.loaded).toBe(true));
        act(() => spingi(riga('EV2', T1, { p1: 2, p2: 0 })));
        await waitFor(() => expect(r.result.current.fonte).toBe('canale'));
        act(() => h.realtime.get('EV2')?.(riga('EV2', T1, { p1: 2, p2: 0 })));
        expect(r.result.current.fonte).toBe('canale');
        r.unmount();
    });

    it('un messaggio del canale piu\' vecchio di cio\' che e\' mostrato si scarta', async () => {
        h.rowDb = riga('EV3', T1, { p1: 3, p2: 3 });
        const r = renderHook(() => useTennisVivo('EV3'));
        await waitFor(() => expect(r.result.current.fonte).toBe('database'));
        act(() => spingi(riga('EV3', T0, { p1: 0, p2: 0 })));
        expect(r.result.current.row?.score?.games).toEqual({ p1: 3, p2: 3 });
        expect(r.result.current.fonte).toBe('database');
        r.unmount();
    });

    it('canale muto: il realtime resta il ripiego (riga piu\' recente dal database)', async () => {
        h.rowDb = riga('EV4', T0, { p1: 1, p2: 1 });
        const r = renderHook(() => useTennisVivo('EV4'));
        await waitFor(() => expect(r.result.current.loaded).toBe(true));
        act(() => h.realtime.get('EV4')?.(riga('EV4', T2, { p1: 2, p2: 1 })));
        expect(r.result.current.row?.score?.games).toEqual({ p1: 2, p2: 1 });
        expect(r.result.current.fonte).toBe('database');
        r.unmount();
    });

    it('le righe di altre partite sul topic `now` non toccano questa', async () => {
        h.rowDb = riga('EV5', T0, { p1: 1, p2: 0 });
        const r = renderHook(() => useTennisVivo('EV5'));
        await waitFor(() => expect(r.result.current.loaded).toBe(true));
        act(() => spingi(riga('ALTRA', T2, { p1: 5, p2: 5 })));
        expect(r.result.current.row?.event_id).toBe('EV5');
        expect(r.result.current.fonte).toBe('database');
        r.unmount();
    });

    it('allo smontaggio l\'iscrizione al canale si chiude', async () => {
        const r = renderHook(() => useTennisVivo('EV6'));
        await waitFor(() => expect(h.canale.size).toBe(1));
        r.unmount();
        expect(h.canale.size).toBe(0);
    });
});
