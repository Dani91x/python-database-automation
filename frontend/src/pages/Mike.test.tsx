// Test COMPONENTE (smoke) per la pagina /mike: data-layer e sonner mockati.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
vi.mock('@/lib/safeStrategyScan', async (orig) => ({
    ...(await orig<typeof import('@/lib/safeStrategyScan')>()),
    fetchScanStatus: vi.fn(async () => ({ id: 'scanner', payload: {}, updated_at: new Date().toISOString() })),
}));
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig<typeof import('@/lib/mike')>()),
    fetchMikeState: vi.fn(),
    fetchMikeRequests: vi.fn(async () => []),
    subscribeMike: vi.fn(() => () => {}),
    activateMike: vi.fn(),
    stopMike: vi.fn(),
    updateMikeParams: vi.fn(),
    requestMike: vi.fn(),
}));

import Mike from './Mike';
import { fetchMikeState } from '@/lib/mike';

const mState = vi.mocked(fetchMikeState);

const CONTROL = {
    id: 1, status: 'running', mode: 'paper', params: { stake: 10 },
    stats: { events_feed: 12, events_tracked: 2, by_state: {}, trades_open: 1, open_liability: 12.5,
             realized_today: 1.2, realized_total: 3.4, scanner_age_s: 2, last_cycle: new Date().toISOString(),
             dry: false, mode: 'paper' },
    error: null, started_at: null, stopped_at: null, heartbeat_at: new Date().toISOString(), updated_at: new Date().toISOString(),
};

const EVENTS = [
    {
        event_id: 'e1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date(Date.now() + 3600_000).toISOString(), mode: 'paper', markets: {}, state: 'PRE_OPEN',
        cycle_no: 0, entry_price_initial: 1.5, dossier: { p4_pre: 0.14, lambda_home: 1.4, lambda_away: 1.1 },
        live: { inplay: false, minute: null, goals: null, ht: false, hazard: null, p4_market: 0.12, p4_model: null,
                cashout: { net: 0.35, gross: 0.37, base: 10, complete: true, pct: 3.5 }, cover_wait: null,
                pnl_by_total: { '0': 4.75, '3': 4.75, '4': -10, '5': -10 },
                books: { 'OU35|UNDER': { best_back: 1.47, back_size: 30, best_lay: 1.48, lay_size: 20, status: 'OPEN', inplay: false, bet_delay: 0 } },
                feed_fresh: true },
        positions: [{ role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10, matched: 10,
                      avg_price: 1.5, ref: 'under_entry-0-1', status: 'open', placed_at: 0, persistence: 'LAPSE', cycle_no: 0,
                      final: false, archived: false }],
        ctx: {}, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
    },
    {
        event_id: 'e3', fixture_id: null, event_name: 'Napoli v Torino', competition: 'Serie A', league_id: null,
        ko_at: new Date(Date.now() - 1800_000).toISOString(), mode: 'paper', markets: {}, state: 'LIVE_COVERED',
        cycle_no: 1, entry_price_initial: 1.5, dossier: { p4_pre: 0.14, lambda_home: 1.6, lambda_away: 0.9 },
        live: { inplay: true, minute: 31, goals: 1, score_home: 1, score_away: 0, red_home: 0, red_away: 1, ht: false,
                hazard: 0.11, pressure: 1.2, p4_market: 0.15, p4_model: 0.14,
                cashout: { net: 0.5, gross: 0.55, base: 12.26, complete: true, pct: 4.1,
                           smart: { enabled: true, floor: 0.25, near: true, hot: true, ev_hold: 0.31, trigger: 'hot_near' } },
                cover_wait: null, pnl_by_total: { '0': 4.75, '4': -12.26, '5': 2 },
                books: { 'OU35|UNDER': { best_back: 1.7, back_size: 30, best_lay: 1.72, lay_size: 20, status: 'OPEN', inplay: true, bet_delay: 5 },
                         'OU45|OVER': { best_back: 4.2, back_size: 30, best_lay: 4.4, lay_size: 20, status: 'OPEN', inplay: true, bet_delay: 5 } },
                feed_fresh: true },
        positions: [{ role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10, matched: 10,
                      avg_price: 1.5, ref: 'under_entry-0-1', status: 'open', placed_at: 0, persistence: 'LAPSE', cycle_no: 0,
                      final: false, archived: false },
                    { role: 'over_cover', market: 'OU45', selection: 'OVER', side: 'back', price: 6.6, size: 2.26, matched: 2.26,
                      avg_price: 6.6, ref: 'over_cover-0-2', status: 'open', placed_at: 0, persistence: 'LAPSE', cycle_no: 0,
                      final: false, archived: false }],
        ctx: {}, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
    },
    {
        event_id: 'e2', fixture_id: null, event_name: 'Milan v Inter', competition: 'Serie A', league_id: null,
        ko_at: new Date(Date.now() + 7200_000).toISOString(), mode: 'paper', markets: {}, state: 'WATCH',
        cycle_no: 0, entry_price_initial: null, dossier: {}, live: {}, positions: [], ctx: {}, skipped: false,
        settled_pnl: null, updated_at: new Date().toISOString(),
    },
];

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter><Mike /></MemoryRouter>
        </HelmetProvider>,
    );
}

describe('Mike page', () => {
    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue({ control: CONTROL as never, events: EVENTS as never, trades: [], activity: [], aggregates: null });
    });

    it('renders status, KPI and one card per active match', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT IN CORSA'));
        expect(screen.getByTestId('mike-mode-banner')).toHaveTextContent('PAPER');
        const cards = await screen.findAllByTestId('mike-match-card');
        expect(cards).toHaveLength(3);
        // la partita LIVE sta prima di tutte, con punteggio, espulsioni e pressione
        expect(cards[0]).toHaveTextContent('Napoli v Torino');
        expect(screen.getByTestId('mike-score')).toHaveTextContent('1–0');
        expect(screen.getByTestId('mike-score')).toHaveTextContent('0/1');
        expect(cards[0]).toHaveTextContent('Pressione');
        expect(cards[0]).toHaveTextContent('×1,20 🔥');
        expect(screen.getByTestId('mike-cashout-smart')).toHaveTextContent('a un passo dal 5%');
        expect(screen.getByTestId('mike-cashout-smart')).toHaveTextContent('fase calda');
        expect(screen.getByTestId('mike-cashout-smart')).toHaveTextContent('chiude (hot_near)');
        // poi la partita pre-match con posizione: cella "4" in evidenza, nessun punteggio
        expect(cards[1]).toHaveTextContent('Roma v Lazio');
        expect(screen.getAllByTestId('mike-score')).toHaveLength(1);
        expect(screen.getAllByTestId('pnl-total-4')[1]).toHaveTextContent('−10,00 €');
        expect(screen.getAllByTestId('mike-cashout-value')[1]).toHaveTextContent('+0,35 €');
        expect(screen.getAllByTestId('mike-cashout-btn')[1]).toBeEnabled();
        expect(screen.getByTestId('mike-params-trigger')).toBeInTheDocument();
    });

    it('shows the migration hint when the control row is missing', async () => {
        mState.mockResolvedValue({ control: null, events: [], trades: [], activity: [], aggregates: null });
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-mode-banner')).toHaveTextContent('mike_bot.sql'));
        expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT INATTIVO');
    });
});
