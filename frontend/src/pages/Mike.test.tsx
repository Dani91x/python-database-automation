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
        expect(cards).toHaveLength(2);
        // la partita con posizione sta prima e mostra la cella "4" in evidenza
        expect(cards[0]).toHaveTextContent('Roma v Lazio');
        expect(screen.getByTestId('pnl-total-4')).toHaveTextContent('−10,00 €');
        expect(screen.getByTestId('mike-cashout-value')).toHaveTextContent('+0,35 €');
        expect(screen.getByTestId('mike-cashout-btn')).toBeEnabled();
        expect(screen.getByTestId('mike-params-trigger')).toBeInTheDocument();
    });

    it('shows the migration hint when the control row is missing', async () => {
        mState.mockResolvedValue({ control: null, events: [], trades: [], activity: [], aggregates: null });
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-mode-banner')).toHaveTextContent('mike_bot.sql'));
        expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT INATTIVO');
    });
});
