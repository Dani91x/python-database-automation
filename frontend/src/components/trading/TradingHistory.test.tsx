// Test COMPONENTE della sezione Storico composta: fetcher mockati, finestra
// di caricamento (mese ∪ periodo), selezione giorno → dettaglio, cambio
// periodo, errore RPC, ritorno al live.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TradingHistory } from './TradingHistory';
import type { DailyRow, DayTrade } from '@/lib/dailyHistory';

function row(day: string, pnl: number): DailyRow {
    return {
        day, pnl_realized: pnl, trades_placed: 2, settled: 1, won: pnl > 0 ? 1 : 0, lost: pnl < 0 ? 1 : 0, void: 0,
        hedged_closed: 0, win_rate: null, avg_win: null, avg_loss: null, best_trade: null, worst_trade: null,
        max_liability: null, gross_profit: pnl > 0 ? pnl : 0, gross_loss: pnl < 0 ? -pnl : 0, profit_factor: null,
        commission_paid: null, goal: 250, goal_pct: null, by_strategy: {}, by_sport: {}, by_origin: {},
        first_trade_at: null, last_trade_at: null,
    };
}
const TRADE: DayTrade = {
    id: 7, event_id: 'e', event_name: 'Roma vs Lazio', side: 'lay', mode: 'paper', price: 40, size: 5, liability: 195,
    status: 'open', pnl: 0, placed_at: '2026-09-10T18:00:00Z', settled_at: null, meta: null, runner_name: '3 - 2',
    phase: 'ft_cs', closes: [], total_pnl: 0, placed_in_day: true, settled_in_day: false, sport: 'calcio',
};

describe('TradingHistory', () => {
    it('carica mese ∪ periodo, mostra calendario/KPI e il dettaglio del giorno corrente', async () => {
        const fetchDaily = vi.fn(async () => [row('2026-09-03', 12.5), row('2026-09-10', -4)]);
        const fetchDayTrades = vi.fn(async () => [TRADE]);
        render(<TradingHistory variant="omega" fetchDaily={fetchDaily} fetchDayTrades={fetchDayTrades} today="2026-09-10" />);
        await waitFor(() => expect(fetchDaily).toHaveBeenCalledWith('2026-09-01', '2026-09-30'));
        expect(await screen.findByTestId('calendar-month')).toHaveTextContent(/settembre 2026/);
        await waitFor(() => expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('+€8.50'));
        expect(screen.getByTestId('kpi-goal')).toHaveTextContent('0/2');
        // dettaglio del giorno corrente
        await waitFor(() => expect(fetchDayTrades).toHaveBeenCalledWith('2026-09-10'));
        expect(await screen.findByText('Roma vs Lazio')).toBeInTheDocument();
        expect(screen.getByTestId('trading-history')).toHaveTextContent('2026-09-10');
    });

    it('selezione di un altro giorno → nuovo dettaglio; periodo 90 gg allarga la finestra', async () => {
        const user = userEvent.setup();
        const fetchDaily = vi.fn(async () => [row('2026-09-03', 12.5)]);
        const fetchDayTrades = vi.fn(async (day: string) => (day === '2026-09-03' ? [TRADE] : []));
        render(<TradingHistory variant="safe" fetchDaily={fetchDaily} fetchDayTrades={fetchDayTrades} today="2026-09-10" />);
        await screen.findByTestId('calendar-month');
        expect(await screen.findByTestId('day-detail-none')).toBeInTheDocument();
        await user.click(screen.getByRole('gridcell', { name: / 3 settembre/ }));
        await waitFor(() => expect(fetchDayTrades).toHaveBeenLastCalledWith('2026-09-03'));
        expect(await screen.findByText('Roma vs Lazio')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: '90 giorni' }));
        await waitFor(() => expect(fetchDaily).toHaveBeenLastCalledWith('2026-06-13', '2026-09-30'));
    });

    it('errore dell RPC: banner esplicito, la pagina resta usabile', async () => {
        const fetchDaily = vi.fn(async () => { throw new Error('function get_safe_daily does not exist'); });
        const fetchDayTrades = vi.fn(async () => []);
        render(<TradingHistory variant="safe" fetchDaily={fetchDaily} fetchDayTrades={fetchDayTrades} today="2026-09-10" />);
        expect(await screen.findByTestId('history-error')).toHaveTextContent(/get_safe_daily/);
        expect(screen.getByTestId('calendar-month')).toBeInTheDocument();
    });

    it('posizione viva nel dettaglio → onGoLive', async () => {
        const user = userEvent.setup();
        const onGoLive = vi.fn();
        render(<TradingHistory variant="omega" fetchDaily={async () => []} fetchDayTrades={async () => [TRADE]} today="2026-09-10" onGoLive={onGoLive} />);
        const row = await screen.findByTestId('day-trade-row');
        await user.click(within(row).getByTestId('day-trade-live'));
        expect(onGoLive).toHaveBeenCalledWith(TRADE);
    });
});
