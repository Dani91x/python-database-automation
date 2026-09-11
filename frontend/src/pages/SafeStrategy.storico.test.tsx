// Test COMPONENTE della pagina Safe Strategy — tab STORICO (fetcher mockati,
// filtro sport, ritorno al tab Trade dal dettaglio), giornata operativa nel
// KPI "P&L oggi", badge USCITA nella tabella trade e sezione "Uscite
// automatiche" nel pannello parametri (exits preservati al salvataggio).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import { DEFAULT_PARAMS } from '@/lib/safeStrategy';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
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
        updateSafeParams: vi.fn(async () => ({})),
    };
});
vi.mock('@/lib/dailyHistory', async (orig) => {
    const actual = await orig<typeof import('@/lib/dailyHistory')>();
    return {
        ...actual,
        romeDay: () => '2026-09-10',
        fetchSafeDaily: vi.fn(async () => []),
        fetchSafeDayTrades: vi.fn(async () => []),
    };
});
vi.mock('@/components/safestrategy/SafeStrategyProvider', () => ({
    useSafeStrategy: () => ({
        football: [], tennis: [], signals: [], scanStatus: null,
        params: DEFAULT_PARAMS, saveParams: vi.fn(), resetParams: vi.fn(),
    }),
}));

import SafeStrategy from './SafeStrategy';
import { fetchSafeState, updateSafeParams } from '@/lib/safeBot';
import { fetchSafeDaily, fetchSafeDayTrades } from '@/lib/dailyHistory';

const mState = vi.mocked(fetchSafeState);
const mUpdate = vi.mocked(updateSafeParams);
const mDaily = vi.mocked(fetchSafeDaily);
const mDay = vi.mocked(fetchSafeDayTrades);

const CONTROL = {
    id: 1, status: 'running', mode: 'paper',
    params: {
        stake: { laySize: 6, backSize: 4 }, commission_pct: 5,
        exits: { enabled: true, base_exit_minute: 78, esatto_exit_minute: 72 },
        servizio_chiave_ignota: 'x',
    },
    stats: {}, error: null, started_at: null, stopped_at: null, heartbeat_at: null,
};
const TRADE = {
    id: 9, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'base',
    market_id: '1.1', market_type: 'MATCH_ODDS', selection_id: 11, selection_name: 'Roma',
    side: 'back', mode: 'paper', price: 1.3, size: 10, liability: 10, commission: 0.05,
    minute_at_entry: 60, score_at_entry: '1-0', status: 'won', pnl: 2.85, bet_id: null,
    placed_at: '2026-09-10T10:00:00Z', settled_at: '2026-09-10T11:00:00Z', origin: 'auto',
    closes_trade_id: null, signal_key: 'e1:base', meta: { exit_kind: 'profit', exit_reason: 'quota 1.05 raggiunta' },
};
const CLOSE = {
    ...TRADE, id: 10, side: 'lay', price: 1.05, size: 12.4, liability: 0.62, closes_trade_id: 9, signal_key: null,
    meta: { locked_pnl: 2.85, exit_kind: 'profit' },
};
const DAY_TRADE = {
    ...TRADE, closes: [CLOSE], total_pnl: 2.85, placed_in_day: true, settled_in_day: true, status: 'open',
};

beforeEach(() => {
    vi.clearAllMocks();
    mState.mockResolvedValue({
        control: CONTROL as never,
        trades: [TRADE, CLOSE] as never,
        aggregates: { realized_today: 2.85, realized_total: 40, open_liability: 0, open_count: 0, won: 1, lost: 0 },
    });
    mDaily.mockResolvedValue([]);
    mDay.mockResolvedValue([]);
});

function renderPage() {
    return render(<HelmetProvider><MemoryRouter><SafeStrategy /></MemoryRouter></HelmetProvider>);
}

describe('Safe Strategy — giornata operativa e uscite', () => {
    it('il KPI "P&L oggi" dichiara la giornata operativa (Europe/Rome)', async () => {
        renderPage();
        expect(await screen.findByTestId('safe-operating-day')).toHaveTextContent(/giornata operativa 10 settembre · Europe\/Rome/);
        expect(screen.getByText('+€2.85')).toBeInTheDocument();
    });

    it('la tabella trade mostra il badge di uscita su apertura e chiusura', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
        // la gamba di chiusura e' una SUB-RIGA attaccata all'apertura, mai un trade a se'
        const rows = await screen.findAllByTestId('safe-trade-row');
        expect(rows).toHaveLength(1);
        const closing = screen.getAllByTestId('safe-closing-row');
        expect(closing).toHaveLength(1);
        expect(closing[0]).toHaveAttribute('data-closes', '9');
        const badges = screen.getAllByTestId('exit-badge');
        expect(badges).toHaveLength(2);
        expect(badges[0]).toHaveTextContent('Uscita: profitto');
        expect(badges[0]).toHaveAttribute('title', 'quota 1.05 raggiunta');
        expect(within(closing[0]).getByText(/chiude #9/)).toBeInTheDocument();
        expect(within(closing[0]).getByText(/Chiusura di #9/)).toBeInTheDocument();
    });

    it('pannello parametri: sezione Uscite automatiche legge params.exits e li preserva al salvataggio', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(screen.getByRole('button', { name: /Parametri/ }));
        expect(await screen.findByTestId('exits-section')).toBeInTheDocument();
        const base = screen.getByLabelText('BASE · uscita a tempo dal minuto') as HTMLInputElement;
        expect(base.value).toBe('78');                                  // dal DB
        expect((screen.getByLabelText('PUNTA · uscita a tempo dal minuto') as HTMLInputElement).value).toBe('83'); // default
        expect(screen.getByRole('checkbox', { name: 'Uscite automatiche attive' })).toHaveAttribute('data-state', 'checked');
        await user.clear(base);
        await user.type(base, '85');
        await user.click(screen.getByRole('checkbox', { name: 'Rosso alla favorita: esci subito' }));
        await user.click(screen.getByRole('button', { name: 'Salva parametri' }));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const saved = mUpdate.mock.calls[0][0] as Record<string, unknown>;
        const exits = saved.exits as Record<string, unknown>;
        expect(exits.base_exit_minute).toBe(85);
        expect(exits.esatto_exit_minute).toBe(72);
        expect(exits.punta_exit_minute).toBe(83);
        expect(exits.red_card_fav_exit).toBe(false);
        expect(exits.tennis_take_profit_next_game).toBe(true);
        // chiavi del servizio sconosciute alla UI: preservate, non cancellate
        expect(saved.servizio_chiave_ignota).toBe('x');
        expect((saved.stake as Record<string, number>).laySize).toBe(6);
    });
});

describe('Safe Strategy — tab Trade: solo la giornata operativa (come Omega)', () => {
    it('una posizione di ieri già regolata compare solo con "mostra tutte"; una di ieri ancora viva resta visibile', async () => {
        const OLD_WON = { ...TRADE, id: 30, event_id: 'old1', event_name: 'Vecchia vs Regolata', signal_key: null,
            placed_at: '2026-09-09T18:00:00Z', settled_at: '2026-09-09T20:00:00Z', meta: null };
        const OLD_LIVE = { ...TRADE, id: 31, event_id: 'old2', event_name: 'Vecchia vs Viva', signal_key: null,
            status: 'open', pnl: 0, placed_at: '2026-09-09T18:00:00Z', settled_at: null, meta: null };
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [TRADE, CLOSE, OLD_WON, OLD_LIVE] as never,
            aggregates: { realized_today: 2.85, realized_total: 40, open_liability: 10, open_count: 1, won: 2, lost: 0 },
        });
        const user = userEvent.setup();
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
        // oggi (10/09 mockato): la vinta di oggi + la viva di ieri; la regolata di ieri NO
        const rows = await screen.findAllByTestId('safe-trade-row');
        expect(rows).toHaveLength(2);
        expect(screen.getByText('Roma vs Lazio')).toBeInTheDocument();
        expect(screen.getByText('Vecchia vs Viva')).toBeInTheDocument();
        expect(screen.queryByText('Vecchia vs Regolata')).toBeNull();
        expect(screen.getByTestId('safe-trades-card')).toHaveTextContent('Operazioni di oggi (2)');
        expect(screen.getByTestId('safe-trades-summary')).toHaveTextContent('2 posizioni oggi · 1V 0P · 1 vive');
        expect(screen.getByRole('tab', { name: /^Trade/ })).toHaveTextContent('Trade (2)');
        // mostra tutte → anche la regolata di ieri
        await user.click(screen.getByTestId('safe-trades-toggle'));
        expect(await screen.findAllByTestId('safe-trade-row')).toHaveLength(3);
        expect(screen.getByText('Vecchia vs Regolata')).toBeInTheDocument();
        expect(screen.getByTestId('safe-trades-card')).toHaveTextContent('Tutte le operazioni (3)');
        await user.click(screen.getByTestId('safe-trades-toggle'));
        expect(await screen.findAllByTestId('safe-trade-row')).toHaveLength(2);
    });

    it('nessuna operazione oggi: stato vuoto che rimanda allo Storico', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [{ ...TRADE, placed_at: '2026-09-09T18:00:00Z', settled_at: '2026-09-09T20:00:00Z' }] as never,
            aggregates: { realized_today: 0, realized_total: 40, open_liability: 0, open_count: 0, won: 0, lost: 0 },
        });
        const user = userEvent.setup();
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
        expect(await screen.findByTestId('safe-trades-empty')).toHaveTextContent(/nessuna operazione oggi/);
        expect(screen.getByTestId('safe-trades-empty')).toHaveTextContent(/Storico/);
    });
});

describe('Safe Strategy — tab Storico', () => {
    it('monta lo storico con i fetcher Safe; il filtro sport ricarica con lo sport', async () => {
        const user = userEvent.setup();
        mDaily.mockResolvedValue([{
            day: '2026-09-10', pnl_realized: 2.85, trades_placed: 1, settled: 1, won: 1, lost: 0, void: 0, hedged_closed: 1,
            win_rate: 1, avg_win: 2.85, avg_loss: null, best_trade: 2.85, worst_trade: 2.85, max_liability: 10,
            gross_profit: 2.85, gross_loss: 0, profit_factor: null, commission_paid: 0.15, goal: null, goal_pct: null,
            by_strategy: { base: { n: 1, pnl: 2.85, won: 1, lost: 0 } }, by_sport: { calcio: { n: 1, pnl: 2.85, won: 1, lost: 0 } },
            by_origin: { auto: { n: 1, pnl: 2.85, won: 1, lost: 0 } }, first_trade_at: null, last_trade_at: null,
        }]);
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(screen.getByRole('tab', { name: /Storico/ }));
        expect(await screen.findByTestId('trading-history')).toBeInTheDocument();
        await waitFor(() => expect(mDaily).toHaveBeenCalledWith('2026-09-01', '2026-09-30', null));
        await waitFor(() => expect(mDay).toHaveBeenCalledWith('2026-09-10', null));
        await waitFor(() => expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('+€2.85'));
        expect(within(screen.getByTestId('breakdown-sport')).getByText('⚽ Calcio')).toBeInTheDocument();
        expect(screen.queryByTestId('kpi-goal')).toBeNull();
        await user.click(within(screen.getByTestId('history-sport-filter')).getByRole('button', { name: /tennis/ }));
        await waitFor(() => expect(mDaily).toHaveBeenLastCalledWith('2026-09-01', '2026-09-30', 'tennis'));
        await waitFor(() => expect(mDay).toHaveBeenLastCalledWith('2026-09-10', 'tennis'));
    });

    it('dal dettaglio di una posizione viva si torna al tab Trade dello sport', async () => {
        const user = userEvent.setup();
        mDay.mockResolvedValue([DAY_TRADE as never]);
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(screen.getByRole('tab', { name: /Storico/ }));
        const row = await screen.findByTestId('day-trade-row');
        await user.click(within(row).getByTestId('day-trade-live'));
        expect(await screen.findByRole('tab', { name: /Calcio/ })).toHaveAttribute('data-state', 'active');
        expect(screen.getByRole('tab', { name: /^Trade/ })).toHaveAttribute('data-state', 'active');
        expect(await screen.findAllByTestId('safe-trade-row')).toHaveLength(1);
        expect(screen.getAllByTestId('safe-closing-row')).toHaveLength(1);
    });
});
