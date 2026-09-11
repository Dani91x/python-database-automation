// Test COMPONENTE della pagina Omega — GIORNATA OPERATIVA (obiettivo di oggi /
// realizzato oggi / resta) e tab STORICO con i fetcher dello storico mockati.
// Copre H-10: un obiettivo NON storicizzato non produce giudizi "centrato".
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
vi.mock('@/components/omega/MissionPanel', () => ({
    default: () => <div data-testid="mission-panel-stub" />,
}));
vi.mock('@/lib/useScanLiveFeed', () => ({
    useScanLiveFeedRows: () => ({}),
    useScanLiveFeed: () => ({}),
    liveScoreLabel: () => null,
}));
vi.mock('@/lib/omega', async (orig) => {
    const actual = await orig<typeof import('@/lib/omega')>();
    return {
        ...actual,
        fetchOmegaState: vi.fn(),
        fetchOmegaTrades: vi.fn(async () => []),
        subscribeOmega: vi.fn(() => () => {}),
        activateOmega: vi.fn(),
        stopOmega: vi.fn(),
        updateOmegaParams: vi.fn(),
        requestManual: vi.fn(),
        fetchOmegaEvents: vi.fn(async () => []),
        fetchOmegaMarket: vi.fn(async () => null),
        fetchManualRequests: vi.fn(async () => []),
    };
});
vi.mock('@/lib/dailyHistory', async (orig) => {
    const actual = await orig<typeof import('@/lib/dailyHistory')>();
    return {
        ...actual,
        romeDay: () => '2026-09-10',
        fetchOmegaDaily: vi.fn(async () => []),
        fetchOmegaDayTrades: vi.fn(async () => []),
    };
});

import Omega from './Omega';
import { fetchOmegaState } from '@/lib/omega';
import { fetchOmegaDaily, fetchOmegaDayTrades, type DailyRow } from '@/lib/dailyHistory';

const mState = vi.mocked(fetchOmegaState);
const mDaily = vi.mocked(fetchOmegaDaily);
const mDay = vi.mocked(fetchOmegaDayTrades);

const CONTROL = {
    id: 1, status: 'running', mode: 'paper', daily_goal: 250, params: {},
    stats: { realized_profit: 900, target_match: 9.5, bot_running: true },
    error: null, started_at: null, stopped_at: null, heartbeat_at: new Date().toISOString(), updated_at: new Date().toISOString(),
};
const DAILY_ROW: DailyRow = {
    day: '2026-09-10', pnl_realized: 60, trades_placed: 3, settled: 2, won: 2, lost: 0, void: 0, hedged_closed: 0,
    win_rate: 1, avg_win: 30, avg_loss: null, best_trade: 40, worst_trade: 20, max_liability: 480,
    gross_profit: 60, gross_loss: 0, profit_factor: null, commission_paid: 3.16,
    goal: 250, goal_pct: 24, goal_snapshot: true,
    by_strategy: { ht_cs: { n: 3, pnl: 60, won: 2, lost: 0 } }, by_sport: {}, by_origin: { auto: { n: 3, pnl: 60, won: 2, lost: 0 } },
    first_trade_at: null, last_trade_at: null,
};

beforeEach(() => {
    vi.clearAllMocks();
    mState.mockResolvedValue({
        control: CONTROL as never,
        // l'RPC separa il realizzato STORICO da quello della GIORNATA operativa
        aggregates: {
            realized_profit: 900, realized_today: 60, open_liability: 480, matches_traded: 3,
            matches_open: 1, matches_won: 2, matches_lost: 0,
            legs_today: 3, events_today: 2, won_today: 2, lost_today: 0, live_now: 1,
        },
        activity: [], activity_more: 0, goal_today: 250, goal_snapshot: true,
    });
    mDaily.mockResolvedValue([DAILY_ROW]);
    mDay.mockResolvedValue([]);
});

function renderPage() {
    return render(<HelmetProvider><MemoryRouter><Omega /></MemoryRouter></HelmetProvider>);
}

describe('Omega — giornata operativa', () => {
    it('obiettivo di oggi / realizzato oggi (NON lo storico) / resta, con la giornata operativa', async () => {
        renderPage();
        const card = await screen.findByTestId('omega-daily-mission');
        const line = within(card).getByTestId('omega-mission-line');
        expect(line).toHaveTextContent('Obiettivo di oggi 250,00 €');
        expect(line).toHaveTextContent('realizzato oggi +60,00 €');
        expect(within(line).getByTestId('omega-remaining')).toHaveTextContent('190,00 €');
        expect(within(card).getByTestId('omega-operating-day')).toHaveTextContent(/giovedì 10 settembre 2026/);
        expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '24');
        expect(card).toHaveTextContent('24,0 %');
        // lo storico cumulato (+900) resta nel KPI, non nella missione
        expect(card).not.toHaveTextContent('900');
        expect(screen.getByText('totale storico +900,00 €')).toBeInTheDocument();
    });

    it('obiettivo centrato quando il realizzato di oggi supera il goal', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never,
            aggregates: {
                realized_profit: 900, realized_today: 260, open_liability: 0, matches_traded: 3,
                matches_open: 0, matches_won: 3, matches_lost: 0, legs_today: 3, events_today: 2,
            },
            activity: [], goal_today: 250, goal_snapshot: true,
        });
        renderPage();
        const card = await screen.findByTestId('omega-daily-mission');
        expect(within(card).getByTestId('omega-goal-hit')).toHaveTextContent('CENTRATO');
        expect(card).toHaveTextContent('+10,00 € oltre');
        expect(within(card).queryByTestId('omega-remaining')).toBeNull();
    });

    it('H-10: obiettivo NON storicizzato → la barra lo dichiara', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never,
            aggregates: { realized_profit: 900, realized_today: 60, open_liability: 0, matches_traded: 3, matches_open: 0, matches_won: 2, matches_lost: 0 },
            activity: [], goal_today: 250, goal_snapshot: false,
        });
        renderPage();
        const card = await screen.findByTestId('omega-daily-mission');
        expect(card).toHaveTextContent('obiettivo non ancora storicizzato per oggi');
    });
});

describe('Omega — tab Storico', () => {
    it('monta calendario, performance e dettaglio con i fetcher dello storico', async () => {
        const user = userEvent.setup();
        renderPage();
        await user.click(await screen.findByRole('tab', { name: /Storico/ }));
        expect(await screen.findByTestId('trading-history')).toBeInTheDocument();
        await waitFor(() => expect(mDaily).toHaveBeenCalledWith('2026-09-01', '2026-09-30'));
        await waitFor(() => expect(mDay).toHaveBeenCalledWith('2026-09-10'));
        expect(await screen.findByRole('gridcell', { name: /10 settembre.*\+60,00 €.*3 trade.*obiettivo mancato/ })).toBeInTheDocument();
        await waitFor(() => expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('+60,00 €'));
        expect(screen.getByTestId('kpi-goal')).toHaveTextContent('0/1');
        expect(within(screen.getByTestId('breakdown-strategy')).getByText('Gamba 1T (Half Time Score)')).toBeInTheDocument();
        expect(screen.getByTestId('day-detail')).toBeInTheDocument();
        // L-08: il testo dice l'attribuzione VERA (Omega storicizza per piazzamento)
        expect(screen.getByTestId('trading-history')).toHaveTextContent(/posizioni PIAZZATE nel giorno/);
    });

    it('H-10: giornata con obiettivo di RIPIEGO → nessun ●/○ e niente giudizio', async () => {
        mDaily.mockResolvedValue([{ ...DAILY_ROW, goal_snapshot: false }]);
        const user = userEvent.setup();
        renderPage();
        await user.click(await screen.findByRole('tab', { name: /Storico/ }));
        expect(await screen.findByRole('gridcell', { name: /10 settembre.*obiettivo non storicizzato/ })).toBeInTheDocument();
        expect(screen.queryByTestId('goal-miss')).toBeNull();
        expect(screen.queryByTestId('goal-hit')).toBeNull();
        expect(screen.getByTestId('goal-not-historized')).toBeInTheDocument();
        expect(screen.getByTestId('kpi-goal')).toHaveTextContent('non giudicabili');
    });
});
