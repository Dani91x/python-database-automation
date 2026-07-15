// Test COMPONENTE per la dashboard Omega. Data-layer e sonner mockati.
// Verifica: header/stato, barra obiettivo (realizzato/goal), KPI, riga trade.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

// Il tab MISSIONE (default) ha il suo data-layer: qui stub — è testato a parte
// in lib/omegaMissions.test.ts.
vi.mock('@/components/omega/MissionPanel', () => ({
    default: () => <div data-testid="mission-panel-stub" />,
}));

vi.mock('@/lib/omega', () => ({
    fetchOmegaState: vi.fn(),
    fetchOmegaTrades: vi.fn(),
    subscribeOmega: vi.fn(() => () => {}),
    activateOmega: vi.fn(),
    stopOmega: vi.fn(),
    updateOmegaParams: vi.fn(),
    requestManual: vi.fn(),
    fetchOmegaEvents: vi.fn(async () => []),
    fetchOmegaMarket: vi.fn(async () => null),
    fetchManualRequests: vi.fn(async () => []),
    buildEquitySeries: () => [],
    OMEGA_PARAM_DEFAULTS: {
        price_min: 20, price_max: 120, entry_minute_min: 30, entry_minute_max: 60,
        max_events: 0, commission_pct: 5, min_lay_liquidity: 5, min_stake: 0.5,
        include_aggregate: false, stop_on_goal: true, entry_window_source: 'score',
        poll_interval_s: 20, max_liability_per_match: 0, daily_loss_cap: 0, max_open_liability: 0,
    },
    OMEGA_PARAM_FIELDS: [],
}));

import Omega from './Omega';
import { fetchOmegaState, fetchOmegaTrades } from '@/lib/omega';

const mState = vi.mocked(fetchOmegaState);
const mTrades = vi.mocked(fetchOmegaTrades);

const CONTROL = {
    id: 1, status: 'running', mode: 'paper', daily_goal: 250, params: {},
    stats: {
        events_total: 42, matches_traded: 3, matches_open: 1, realized_profit: 60,
        open_liability: 480, matches_remaining: 20, target_match: 9.5, goal: 250,
        goal_pct: 24, last_cycle: new Date().toISOString(),
    },
    error: null, started_at: null, stopped_at: null, heartbeat_at: null, updated_at: new Date().toISOString(),
};

const TRADES = [
    {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', market_id: '1.1', selection_id: 4,
        runner_name: '3 - 2', side: 'lay', mode: 'paper', price: 110, size: 5.26, liability: 573.34,
        target: 5, minute_at_entry: 42, score_at_entry: '0-0', kickoff: null, status: 'open',
        pnl: 0, bet_id: null, placed_at: new Date().toISOString(), settled_at: null, meta: {},
    },
];

beforeEach(() => {
    vi.clearAllMocks();
    mState.mockResolvedValue({ control: CONTROL as never, aggregates: null, activity: [] });
    mTrades.mockResolvedValue(TRADES as never);
});

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <Omega />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

// Il default è il tab MISSIONE: per i contenuti della dashboard automatica
// bisogna prima cliccare "⚙️ Automatico".
async function gotoAutoTab() {
    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: /Automatico/ }));
}

describe('Omega dashboard', () => {
    it('mostra header OMEGA e stato IN CORSA', async () => {
        renderPage();
        expect(await screen.findByText('OMEGA')).toBeInTheDocument();
        expect(await screen.findByText('IN CORSA')).toBeInTheDocument();
    });

    it('il tab Missione è il default e monta il pannello', async () => {
        renderPage();
        expect(await screen.findByTestId('mission-panel-stub')).toBeInTheDocument();
    });

    it('barra obiettivo mostra realizzato e goal', async () => {
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByText('Obiettivo giornaliero')).toBeInTheDocument();
        // +€60.00 compare sia nella barra obiettivo sia nel KPI "P&L realizzato"
        expect((await screen.findAllByText('+€60.00')).length).toBeGreaterThanOrEqual(1);
        expect(await screen.findByText(/€250\.00/)).toBeInTheDocument();
    });

    it('KPI target/match e liability aperta presenti', async () => {
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByText('Target / match')).toBeInTheDocument();
        expect(await screen.findByText('€9.50')).toBeInTheDocument();
        expect(await screen.findByText('Liability aperta')).toBeInTheDocument();
        expect(await screen.findByText('€480.00')).toBeInTheDocument();
    });

    it('elenca il trade piazzato con il punteggio laid', async () => {
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByText('Roma vs Lazio')).toBeInTheDocument();
        expect(await screen.findByText('3 - 2')).toBeInTheDocument();
        expect(await screen.findByText('APERTO')).toBeInTheDocument();
    });

    it('mostra il pulsante Ferma quando è in corsa', async () => {
        renderPage();
        expect(await screen.findByText('Ferma')).toBeInTheDocument();
    });
});
