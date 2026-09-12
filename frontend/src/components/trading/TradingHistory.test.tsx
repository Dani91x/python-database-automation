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
        commission_paid: null, goal: 250, goal_pct: null, goal_snapshot: true, by_strategy: {}, by_sport: {}, by_origin: {},
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
        // la finestra copre la GRIGLIA del mese (lun 31 ago → dom 4 ott), non il
        // solo mese: le celle fuori mese sono disegnate e devono essere dati letti
        await waitFor(() => expect(fetchDaily).toHaveBeenCalledWith('2026-08-31', '2026-10-04'));
        expect(await screen.findByTestId('calendar-month')).toHaveTextContent(/settembre 2026/);
        await waitFor(() => expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('+8,50 €'));
        expect(screen.getByTestId('kpi-goal')).toHaveTextContent('0/2');
        // dettaglio del giorno corrente
        await waitFor(() => expect(fetchDayTrades).toHaveBeenCalledWith('2026-09-10'));
        expect(await screen.findByText('Roma vs Lazio')).toBeInTheDocument();
        expect(screen.getByTestId('trading-history')).toHaveTextContent('10 settembre 2026');
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
        await waitFor(() => expect(fetchDaily).toHaveBeenLastCalledWith('2026-06-13', '2026-10-04'));
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
        // Omega §14: dettaglio giorno = una riga per PARTITA, link live dentro la gamba
        const row = await screen.findByTestId('omega-match-row');
        await user.click(within(row).getByTestId('day-trade-live'));
        expect(onGoLive).toHaveBeenCalledWith(TRADE);
    });
});

// ============================================================================
// CERTIFICAZIONE UI 12/09 — mai i trade di un'altra giornata sotto la data nuova
// ============================================================================
describe('TradingHistory — coerenza giorno ↔ trade mostrati (12/09)', () => {
    it('cambiando giorno i trade del giorno prima spariscono SUBITO', async () => {
        const T3 = { ...TRADE, id: 3, event_name: 'Partita del 3' };
        const T4 = { ...TRADE, id: 4, event_name: 'Partita del 4' };
        let release: (() => void) | undefined;
        const fetchDaily = vi.fn(async () => [row('2026-09-03', 12.5), row('2026-09-04', -4)]);
        const fetchDayTrades = vi.fn(async (day: string) => {
            if (day === '2026-09-04') {
                // risposta LENTA: è la finestra in cui prima restavano i trade del 3
                await new Promise<void>((r) => { release = r as () => void; });
                return [T4];
            }
            return [T3];
        });
        render(
            <TradingHistory variant="safe" fetchDaily={fetchDaily} fetchDayTrades={fetchDayTrades} today="2026-09-03" />,
        );
        expect(await screen.findByText('Partita del 3')).toBeInTheDocument();

        await userEvent.setup().click(screen.getByRole('gridcell', { name: /^venerdì 4 settembre/ }));
        // il titolo è già del 4: i trade del 3 NON devono essere più a schermo
        await waitFor(() => expect(screen.getByTestId('day-detail')).toHaveTextContent(/4 settembre/));
        expect(screen.queryByText('Partita del 3')).toBeNull();

        (release as (() => void) | undefined)?.();
        expect(await screen.findByText('Partita del 4')).toBeInTheDocument();
    });

    it('mese lontano: la finestra tiene il MESE e dichiara il periodo fuori', async () => {
        const fetchDaily = vi.fn(async () => []);
        const fetchDayTrades = vi.fn(async () => []);
        render(
            <TradingHistory variant="omega" fetchDaily={fetchDaily} fetchDayTrades={fetchDayTrades} today="2026-09-12" />,
        );
        await waitFor(() => expect(fetchDaily).toHaveBeenCalled());
        // indietro di 20 mesi con il pulsante "Mese precedente"
        const user = userEvent.setup();
        const prev = screen.getByRole('button', { name: 'Mese precedente' });
        for (let i = 0; i < 20; i += 1) await user.click(prev);
        await waitFor(() => expect(screen.getByTestId('calendar-month')).toHaveTextContent(/gennaio 2025/));
        await waitFor(() => {
            const [from, to] = fetchDaily.mock.calls[fetchDaily.mock.calls.length - 1] as unknown as [string, string];
            // il mese a schermo è DENTRO la finestra caricata
            expect(from <= '2025-01-01').toBe(true);
            expect(to >= '2025-01-31').toBe(true);
        });
        expect(screen.getByTestId('history-clamped')).toBeInTheDocument();
        expect(screen.getByTestId('period-unavailable')).toHaveTextContent('Periodo non calcolabile');
    });
});
