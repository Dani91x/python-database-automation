// ============================================================================
// posizioniCanale.pannelli.test.tsx - 25/09 (voce 13): le posizioni dal canale
// dei runner nelle pagine FUORI dalla Control Room che le leggevano solo a poll:
// TerminalPositionsRail (4 s), LiveTradingPanel (3 s) - SeguiLive - e LivePnl
// (15 s). Stesso aggancio gia' certificato (`usePosizioniCanale` +
// `vistaPosizioni`): qui si prova che i tre punti lo usano davvero.
//
// Finto = messaggio VERO `position`: Betfair/stream/db.py:643-645
// (`upsert_live_position`, push PRIMA della scrittura): {mode, event_id,
// market_id, selection_id, handicap, matched_if_win, matched_if_lose,
// worst_if_win, worst_if_lose, selection_exposure, unmatched_back_exposure,
// unmatched_lay_exposure, net_position, updated_at} (niente `id`).
// Righe del poll = `get_live_positions` (to_jsonb della tabella, con `id`).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
function spingi(sport: string, topic: string, d: unknown) {
    for (const cb of iscritti.get(`${sport}:${topic}`) ?? []) cb(d);
}

vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn((sport: string) => ({
        getStatus: () => 'connected' as const,
        getHello: () => null,
        onStatus: () => () => { /* nessun cambio */ },
        subscribe: (topic: string, cb: Cb) => {
            const k = `${sport}:${topic}`;
            let s = iscritti.get(k);
            if (!s) { s = new Set(); iscritti.set(k, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));
vi.mock('@/lib/liveOrders', async (orig) => ({
    ...(await orig() as object),
    fetchLiveOrders: vi.fn(async () => []),
    fetchLivePositions: vi.fn(async () => []),
    sendLiveOrderCommand: vi.fn(),
    fetchLiveSettled: vi.fn(async () => []),
    fetchLiveRiskState: vi.fn(async () => null),
    subscribeLiveRiskState: vi.fn(() => () => { /* nessuna spinta */ }),
    fetchLivePositionsAll: vi.fn(async () => []),
}));
vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    fetchTennisPositionsAll: vi.fn(async () => []),
}));

import { fetchLiveOrders, fetchLivePositions, fetchLivePositionsAll } from '@/lib/liveOrders';
import { applicaPushOrdine, leggiPushOrdine, potaOrdini, vistaOrdini } from '@/lib/ordiniCanale';
import { TerminalPositionsRail } from './TerminalPositionsRail';
import { LiveTradingPanel } from './LiveTradingPanel';
import LivePnl from '@/pages/LivePnl';

const T0 = '2026-09-25T13:00:00.100000+00:00';
const T1 = '2026-09-25T13:00:01.900000+00:00';

function rigaDb(over: Record<string, unknown> = {}) {
    return {
        id: 1, mode: 'paper', event_id: 'E1', market_id: '1.1', selection_id: 1, handicap: 0,
        matched_if_win: 12.5, matched_if_lose: -5.0, worst_if_win: 12.5, worst_if_lose: -5.0,
        selection_exposure: 5.0, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
        net_position: 5.0, updated_at: T0, ...over,
    };
}
function push(over: Record<string, unknown> = {}) {
    const { id: _id, ...r } = rigaDb(over);
    void _id;
    return r;
}

beforeEach(() => {
    iscritti.clear();
    vi.mocked(fetchLivePositions).mockResolvedValue([]);
    vi.mocked(fetchLivePositionsAll).mockResolvedValue([]);
    vi.mocked(fetchLiveOrders).mockResolvedValue([]);
});

describe('TerminalPositionsRail - position dal canale 47331', () => {
    it('un push piu\' fresco aggiorna il P&L della riga nota, fonte "canale"', async () => {
        vi.mocked(fetchLivePositions).mockResolvedValue([rigaDb()] as never);
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={[{ selection_id: 1, name: 'Milan' }]} />);
        expect(await screen.findByText('+12.50')).toBeInTheDocument();
        expect(screen.getByTestId('rail-fonte-posizioni').textContent).toMatch(/^db/);
        act(() => spingi('calcio', 'position', push({ matched_if_win: 20, worst_if_win: 20, updated_at: T1 })));
        expect(await screen.findByText('+20.00')).toBeInTheDocument();
        expect(screen.getByTestId('rail-fonte-posizioni').textContent).toBe('canale');
    });

    it('mai unione: una posizione che il poll non ha non compare', async () => {
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={[{ selection_id: 1, name: 'Milan' }]} />);
        await waitFor(() => expect(fetchLivePositions).toHaveBeenCalled());
        act(() => spingi('calcio', 'position', push({ updated_at: T1 })));
        await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
        expect(screen.queryByText('+12.50')).toBeNull();
    });
});

// Finto `order` VERO: engine/live_trading_strategy.py:324-347 (`_order_row`) +
// `updated_at` di db.py:535-552; righe del poll = to_jsonb(betfair_live_orders).
function ordineDb(over: Record<string, unknown> = {}) {
    return {
        id: 10, bet_id: 'B10', client_order_ref: 'awlq10', request_id: 10, mode: 'paper',
        event_id: 'E1', market_id: '1.1', selection_id: 1, handicap: 0, side: 'back',
        order_type: 'LIMIT', price: 2.5, size: 5, size_matched: 0, size_remaining: 5,
        size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 0,
        status: 'EXECUTABLE', persistence: 'LAPSE', placed_at: T0, matched_at: null,
        updated_at: T0, ...over,
    };
}
function pushOrdine(over: Record<string, unknown> = {}) {
    const { id: _id, ...r } = ordineDb(over);
    void _id;
    return r;
}

describe('ordini dal canale 47331 (lib/ordiniCanale)', () => {
    it('Rail: l\'ordine abbinato dal canale esce dagli "in attesa" subito; ordine sconosciuto ignorato', async () => {
        vi.mocked(fetchLiveOrders).mockResolvedValue([ordineDb()] as never);
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={[{ selection_id: 1, name: 'Milan' }]} />);
        await waitFor(() => expect(fetchLiveOrders).toHaveBeenCalled());
        await waitFor(() => expect(screen.getByTestId('rail-fonte-posizioni').textContent).toMatch(/^db/));
        // ordine che il poll non ha: mai unione
        act(() => spingi('calcio', 'order', pushOrdine({ client_order_ref: 'awlq99', updated_at: T1 })));
        await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
        expect(screen.getByTestId('rail-fonte-posizioni').textContent).toMatch(/^db/);
        act(() => spingi('calcio', 'order', pushOrdine({
            size_matched: 5, size_remaining: 0, average_price_matched: 2.5,
            status: 'EXECUTION_COMPLETE', matched_at: T1, updated_at: T1,
        })));
        await waitFor(() => expect(screen.getByTestId('rail-fonte-posizioni').textContent).toBe('canale'));
    });

    it('modulo puro: push vecchio o di un altro modo scartato; poll nuovo pota', () => {
        const db = [ordineDb()] as never as import('@/lib/liveOrders').LiveOrderRow[];
        const vecchio = leggiPushOrdine(pushOrdine({ updated_at: '2026-09-25T12:00:00Z', size_matched: 5 }))!;
        const live = leggiPushOrdine(pushOrdine({ mode: 'live', updated_at: T1, size_matched: 5 }))!;
        const buono = leggiPushOrdine(pushOrdine({ updated_at: T1, size_matched: 5, size_remaining: 0 }))!;
        const vuota = new Map();
        expect(applicaPushOrdine(vuota, db, vecchio)).toBe(vuota);
        expect(applicaPushOrdine(vuota, db, live)).toBe(vuota);
        const s = applicaPushOrdine(vuota, db, buono);
        expect(vistaOrdini(db, s)[0].size_matched).toBe(5);
        expect(vistaOrdini(db, s)[0].mode).toBe('paper');
        expect(potaOrdini(s, [ordineDb({ updated_at: T1, size_matched: 5 })] as never).size).toBe(0);
        expect(vistaOrdini(db, new Map())).toBe(db);
        expect(leggiPushOrdine(pushOrdine({ size_matched: 'x' }))).toBeNull();
    });
});

describe('LiveTradingPanel - position dal canale 47331', () => {
    it('riga nota + push piu\' fresco: fonte "canale"; push vecchio: resta "db"', async () => {
        vi.mocked(fetchLivePositions).mockResolvedValue([rigaDb({ market_id: '1.234', selection_id: 47 })] as never);
        render(<LiveTradingPanel marketId="1.234" mode="paper" selections={[{ selection_id: 47, name: 'Over 2.5' }]} pollMs={0} />);
        await waitFor(() => expect(screen.getByTestId('ltp-fonte-posizioni').textContent).toBe('db'));
        act(() => spingi('calcio', 'position', push({ market_id: '1.234', selection_id: 47, updated_at: '2026-09-25T12:00:00Z' })));
        await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
        expect(screen.getByTestId('ltp-fonte-posizioni').textContent).toBe('db');
        act(() => spingi('calcio', 'position', push({ market_id: '1.234', selection_id: 47, net_position: 7, updated_at: T1 })));
        await waitFor(() => expect(screen.getByTestId('ltp-fonte-posizioni').textContent).toBe('canale'));
    });
});

describe('LivePnl - position dal canale', () => {
    it('il rischio in testata segue il push piu\' fresco, fonte dichiarata', async () => {
        vi.mocked(fetchLivePositionsAll).mockResolvedValue([rigaDb()] as never);
        render(<HelmetProvider><MemoryRouter><LivePnl /></MemoryRouter></HelmetProvider>);
        await waitFor(() => expect(screen.getByTestId('livepnl-fonte-posizioni').textContent).toMatch(/db/));
        act(() => spingi('calcio', 'position', push({ selection_exposure: 9, updated_at: T1 })));
        await waitFor(() => expect(screen.getByTestId('livepnl-fonte-posizioni').textContent).toMatch(/canale/));
    });
});
