// usePosizioniCanale.test.tsx - l'aggancio React sul canale locale VERO
// (localChannel.ts) con un WebSocket finto che parla la busta del server
// (Betfair/stream/local_channel.py: {"t": topic, "d": payload}). E' l'hook
// usato da SeguiLive (posizioni dell'evento, calcio 47331) e da MarketWatch.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import type { LivePositionRow } from '@/lib/liveOrders';
import { __resetLocalChannels } from '@/lib/localChannel';
import { vistaPosizioni } from '@/lib/canaleRunner';
import { usePosizioniCanale } from './usePosizioniCanale';

class FintoWs {
    static tutti: FintoWs[] = [];
    url: string;
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    constructor(url: string) { this.url = url; FintoWs.tutti.push(this); }
    send(): void { /* niente richieste in questi test */ }
    close(): void { /* chiusura lato server: serverClose */ }
    apri(): void { this.onopen?.(); }
    push(t: string, d: unknown): void { this.onmessage?.({ data: JSON.stringify({ t, d }) }); }
}
const ws = (porta: number) => FintoWs.tutti.find(w => w.url.endsWith(`:${porta}`))!;

const T0 = '2026-09-23T18:00:00.100000+00:00';
const T2 = '2026-09-23T18:00:05.000000+00:00';
const RIGA: LivePositionRow = {
    id: 41, mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 7, handicap: 0,
    matched_if_win: 10, matched_if_lose: -5, worst_if_win: 10, worst_if_lose: -5,
    selection_exposure: 5, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
    net_position: 5, updated_at: T0,
};
const PUSH = {
    mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 7, handicap: 0.0,
    matched_if_win: 20.0, matched_if_lose: -9.0, worst_if_win: 20.0, worst_if_lose: -9.0,
    selection_exposure: 9.0, unmatched_back_exposure: 0.0, unmatched_lay_exposure: 0.0,
    net_position: 9.0, updated_at: T2,
};

function usaVista(sport: 'calcio' | 'tennis', righe: LivePositionRow[] | null) {
    const s = usePosizioniCanale(sport, righe);
    return righe == null ? null : vistaPosizioni(righe, s);
}

beforeEach(() => {
    FintoWs.tutti = [];
    vi.stubGlobal('WebSocket', FintoWs);
});
afterEach(() => {
    __resetLocalChannels();
    vi.unstubAllGlobals();
});

describe('usePosizioniCanale', () => {
    it('calcio: porta 47331, push fresco vince sulla riga del poll', () => {
        const righe = [RIGA];
        const { result } = renderHook(() => usaVista('calcio', righe));
        act(() => { ws(47331).apri(); ws(47331).push('position', PUSH); });
        expect(result.current?.[0].selection_exposure).toBe(9);
    });

    it('messaggio vecchio ignorato', () => {
        const righe = [{ ...RIGA, updated_at: T2 }];
        const { result } = renderHook(() => usaVista('calcio', righe));
        act(() => { ws(47331).apri(); ws(47331).push('position', { ...PUSH, updated_at: T0, selection_exposure: 1 }); });
        expect(result.current?.[0].selection_exposure).toBe(5);
    });

    it('canale muto -> le righe del poll, stesso array; il poll nuovo passa', () => {
        let righe = [RIGA];
        const { result, rerender } = renderHook(() => usaVista('calcio', righe));
        expect(result.current).toBe(righe);
        righe = [{ ...RIGA, selection_exposure: 7, updated_at: T2 }];
        rerender();
        expect(result.current).toBe(righe);
    });

    it('riga sparita dal blocco nuovo: sparisce, il canale non la riporta', () => {
        let righe: LivePositionRow[] = [RIGA];
        const { result, rerender } = renderHook(() => usaVista('calcio', righe));
        act(() => { ws(47331).apri(); ws(47331).push('position', PUSH); });
        righe = [];
        rerender();
        expect(result.current).toEqual([]);
        act(() => { ws(47331).push('position', { ...PUSH, updated_at: '2026-09-23T18:00:09+00:00' }); });
        expect(result.current).toEqual([]);
    });

    it('riga arrivata con un poll successivo: il push dopo la sovrappone', () => {
        let righe: LivePositionRow[] = [];
        const { result, rerender } = renderHook(() => usaVista('calcio', righe));
        act(() => { ws(47331).apri(); });
        righe = [RIGA];
        rerender();
        act(() => { ws(47331).push('position', PUSH); });
        expect(result.current?.[0].selection_exposure).toBe(9);
    });

    it('tennis ascolta 47332 (nessun socket calcio aperto)', () => {
        const righe = [RIGA];
        const { result } = renderHook(() => usaVista('tennis', righe));
        expect(FintoWs.tutti.some(w => w.url.endsWith(':47331'))).toBe(false);
        act(() => { ws(47332).apri(); ws(47332).push('position', PUSH); });
        expect(result.current?.[0].selection_exposure).toBe(9);
    });
});
