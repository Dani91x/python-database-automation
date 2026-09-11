// Test COMPONENTE del calendario mensile: celle con P&L/trade, marcatore
// obiettivo (Omega), selezione via click e tastiera, navigazione mese,
// stato vuoto, accessibilità (grid/gridcell, aria-selected, roving tabindex).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DailyCalendar, intensityClass, goalMarkOf } from './DailyCalendar';
import type { DailyRow } from '@/lib/dailyHistory';

function row(day: string, pnl: number, over: Partial<DailyRow> = {}): DailyRow {
    return {
        day, pnl_realized: pnl, trades_placed: 3, settled: 2, won: 1, lost: 1, void: 0, hedged_closed: 0,
        win_rate: 0.5, avg_win: null, avg_loss: null, best_trade: null, worst_trade: null, max_liability: null,
        gross_profit: pnl > 0 ? pnl : 0, gross_loss: pnl < 0 ? -pnl : 0, profit_factor: null, commission_paid: null,
        goal: null, goal_pct: null, goal_snapshot: true, by_strategy: {}, by_sport: {}, by_origin: {}, first_trade_at: null, last_trade_at: null,
        ...over,
    };
}

const ROWS = [row('2026-09-03', 12.5, { goal: 250 }), row('2026-09-10', -4, { goal: 250, trades_placed: 1 }), row('2026-09-12', 300, { goal: 250 })];

function renderCal(over: Partial<React.ComponentProps<typeof DailyCalendar>> = {}) {
    const onSelectDay = vi.fn();
    const onMonthChange = vi.fn();
    const utils = render(
        <DailyCalendar
            rows={ROWS} year={2026} month={9} selectedDay="2026-09-10" today="2026-09-10"
            onSelectDay={onSelectDay} onMonthChange={onMonthChange} {...over}
        />,
    );
    return { ...utils, onSelectDay, onMonthChange };
}

describe('DailyCalendar', () => {
    it('mostra il mese, 30 celle del mese, P&L e trade nelle celle attive', () => {
        renderCal();
        expect(screen.getByTestId('calendar-month')).toHaveTextContent(/settembre 2026/);
        expect(screen.getAllByTestId('calendar-day')).toHaveLength(30);
        const grid = screen.getByRole('grid');
        expect(within(grid).getAllByRole('columnheader')).toHaveLength(7);
        const c3 = screen.getByRole('gridcell', { name: / 3 settembre/ });
        expect(c3).toHaveTextContent('+12,50 €');
        expect(c3).toHaveTextContent('3 trade');
        const c10 = screen.getByRole('gridcell', { name: /10 settembre/ });
        expect(c10).toHaveTextContent('−4,00 €');
        expect(c10).toHaveAttribute('aria-selected', 'true');
        expect(c10).toHaveAttribute('aria-current', 'date');
        expect(screen.getByTestId('calendar-month-total')).toHaveTextContent('+308,50 €');
        expect(screen.getByTestId('calendar-month-total')).toHaveTextContent('3 giornate');
    });

    it('la griglia parte da lunedì 31 agosto (fuori mese, non selezionabile via tab)', () => {
        renderCal();
        const outside = screen.getAllByTestId('calendar-day-outside');
        expect(outside[0]).toHaveAttribute('data-day', '2026-08-31');
        expect(outside[0]).toHaveAttribute('tabindex', '-1');
    });

    it('marcatore obiettivo solo con showGoal: centrato/mancato', () => {
        renderCal({ showGoal: true });
        expect(screen.getAllByTestId('goal-hit')).toHaveLength(1);       // 12/09: 300 ≥ 250
        expect(screen.getAllByTestId('goal-miss')).toHaveLength(2);      // 3/09 e 10/09
        expect(screen.getByRole('gridcell', { name: /12 settembre.*obiettivo centrato/ })).toBeInTheDocument();
    });
    it('senza showGoal nessun marcatore', () => {
        renderCal();
        expect(screen.queryByTestId('goal-hit')).toBeNull();
        expect(screen.queryByTestId('goal-miss')).toBeNull();
    });

    it('click su una cella → onSelectDay col giorno', async () => {
        const user = userEvent.setup();
        const { onSelectDay } = renderCal();
        await user.click(screen.getByRole('gridcell', { name: / 3 settembre/ }));
        expect(onSelectDay).toHaveBeenCalledWith('2026-09-03');
    });

    it('tastiera: frecce muovono il focus (roving tabindex), Invio seleziona', async () => {
        const user = userEvent.setup();
        const { onSelectDay } = renderCal();
        const c10 = screen.getByRole('gridcell', { name: /10 settembre/ });
        expect(c10).toHaveAttribute('tabindex', '0');
        c10.focus();
        await user.keyboard('{ArrowRight}');
        expect(screen.getByRole('gridcell', { name: /11 settembre/ })).toHaveFocus();
        await user.keyboard('{ArrowDown}');
        expect(screen.getByRole('gridcell', { name: /18 settembre/ })).toHaveFocus();
        await user.keyboard('{ArrowUp}{ArrowLeft}');
        expect(screen.getByRole('gridcell', { name: /10 settembre/ })).toHaveFocus();
        await user.keyboard('{Home}');
        expect(screen.getByRole('gridcell', { name: / 7 settembre/ })).toHaveFocus();
        await user.keyboard('{End}');
        expect(screen.getByRole('gridcell', { name: /13 settembre/ })).toHaveFocus();
        await user.keyboard('{Enter}');
        expect(onSelectDay).toHaveBeenLastCalledWith('2026-09-13');
        // la cella focalizzata è l'unica nel tab order
        expect(screen.getAllByRole('gridcell').filter((c) => c.getAttribute('tabindex') === '0')).toHaveLength(1);
    });

    it('mese precedente/successivo e "Oggi"', async () => {
        const user = userEvent.setup();
        const { onMonthChange, onSelectDay } = renderCal({ year: 2026, month: 1 });
        await user.click(screen.getByRole('button', { name: 'Mese precedente' }));
        expect(onMonthChange).toHaveBeenLastCalledWith(2025, 12);
        await user.click(screen.getByRole('button', { name: 'Mese successivo' }));
        expect(onMonthChange).toHaveBeenLastCalledWith(2026, 2);
        await user.click(screen.getByRole('button', { name: 'Oggi' }));
        expect(onMonthChange).toHaveBeenLastCalledWith(2026, 9);
        expect(onSelectDay).toHaveBeenLastCalledWith('2026-09-10');
    });

    it('stato vuoto quando il mese non ha giornate operative', () => {
        renderCal({ rows: [], year: 2026, month: 8 });
        expect(screen.getByTestId('calendar-empty')).toHaveTextContent(/nessuna operazione in agosto 2026/);
        expect(screen.getByRole('gridcell', { name: / 5 agosto.*nessuna operazione/ })).toBeInTheDocument();
    });

    it('intensityClass: zero neutro, segno e livelli relativi al massimo', () => {
        expect(intensityClass(0, 100)).toMatch(/bg-white\/5/);
        expect(intensityClass(5, 0)).toMatch(/bg-white\/5/);
        expect(intensityClass(100, 100)).toMatch(/emerald-500\/55/);
        expect(intensityClass(10, 100)).toMatch(/emerald-500\/10/);
        expect(intensityClass(-100, 100)).toMatch(/red-500\/55/);
        expect(intensityClass(-50, 100)).toMatch(/red-500\/35/);
    });
});

// ============================================ audit 11/09: H-10 goal_snapshot
describe('DailyCalendar — obiettivo STORICIZZATO (H-10)', () => {
    it('con lo snapshot: ●/○ e giudizio nel nome accessibile', () => {
        renderCal({ rows: [row('2026-09-03', 300, { goal: 250, goal_snapshot: true })], showGoal: true });
        expect(screen.getByTestId('goal-hit')).toBeInTheDocument();
        expect(screen.getByRole('gridcell', { name: /3 settembre.*obiettivo centrato/ })).toBeInTheDocument();
    });

    it('senza snapshot: nessun ●/○, la cella dice "obiettivo non storicizzato"', () => {
        renderCal({ rows: [row('2026-09-03', 300, { goal: 250, goal_snapshot: false })], showGoal: true });
        expect(screen.queryByTestId('goal-hit')).toBeNull();
        expect(screen.queryByTestId('goal-miss')).toBeNull();
        expect(screen.getByTestId('goal-not-historized')).toBeInTheDocument();
        expect(screen.getByRole('gridcell', { name: /3 settembre.*obiettivo non storicizzato/ })).toBeInTheDocument();
    });

    it('goalMarkOf: puro e difensivo', () => {
        expect(goalMarkOf(null, true)).toBeNull();
        expect(goalMarkOf(row('2026-09-03', 300, { goal: 0, goal_snapshot: true }), true)).toBeNull();
        expect(goalMarkOf(row('2026-09-03', 300, { goal: 250, goal_snapshot: false }), true)).toBeNull();
        expect(goalMarkOf(row('2026-09-03', 300, { goal: 250, goal_snapshot: true }), false)).toBeNull();
        expect(goalMarkOf(row('2026-09-03', 300, { goal: 250, goal_snapshot: true }), true)).toBe(true);
        expect(goalMarkOf(row('2026-09-03', 100, { goal: 250, goal_snapshot: true }), true)).toBe(false);
    });

    it('formato monetario italiano nelle celle e nel totale del mese', () => {
        renderCal({ rows: [row('2026-09-03', 12.5, { goal: 250, goal_snapshot: true })] });
        expect(screen.getByTestId('calendar-month-total')).toHaveTextContent('+12,50 €');
    });
});
