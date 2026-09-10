// Test COMPONENTE del pannello performance: KPI calcolati da righe fixture,
// selettore periodo, breakdown (Safe: strategia/sport/origine · Omega: gamba),
// tile "Obiettivo centrato" solo per Omega, stato vuoto.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PerformancePanel } from './PerformancePanel';
import type { DailyRow } from '@/lib/dailyHistory';

function row(day: string, pnl: number, over: Partial<DailyRow> = {}): DailyRow {
    const won = pnl > 0 ? 2 : 0, lost = pnl < 0 ? 1 : 0;
    return {
        day, pnl_realized: pnl, trades_placed: 3, settled: won + lost, won, lost, void: 0, hedged_closed: 1,
        win_rate: null, avg_win: null, avg_loss: null, best_trade: null, worst_trade: null, max_liability: 50,
        gross_profit: pnl > 0 ? pnl : 0, gross_loss: pnl < 0 ? -pnl : 0, profit_factor: null, commission_paid: 0.5,
        goal: 250, goal_pct: null, by_strategy: {}, by_sport: {}, by_origin: {}, first_trade_at: null, last_trade_at: null,
        ...over,
    };
}

// 3 giornate: +100 (2V), −40 (1P), +300 (2V) → pnl 360, PF 10, exp 72, DD 40, goal hit 1/3
const ROWS: DailyRow[] = [
    row('2026-09-01', 100, { by_strategy: { base: { n: 2, pnl: 100, won: 2, lost: 0 } }, by_sport: { calcio: { n: 2, pnl: 100, won: 2, lost: 0 } }, by_origin: { auto: { n: 2, pnl: 100, won: 2, lost: 0 } } }),
    row('2026-09-02', -40, { by_strategy: { tennis: { n: 1, pnl: -40, won: 0, lost: 1 } }, by_sport: { tennis: { n: 1, pnl: -40, won: 0, lost: 1 } }, by_origin: { manual: { n: 1, pnl: -40, won: 0, lost: 1 } } }),
    row('2026-09-03', 300, { by_strategy: { base: { n: 1, pnl: 300, won: 2, lost: 0 } }, by_sport: { calcio: { n: 1, pnl: 300, won: 2, lost: 0 } }, by_origin: { auto: { n: 1, pnl: 300, won: 2, lost: 0 } } }),
];

describe('PerformancePanel', () => {
    it('KPI dal fixture (Safe): P&L, giornate, win rate, PF, expectancy, DD, best/worst, serie', () => {
        render(<PerformancePanel rows={ROWS} period="month" onPeriodChange={() => {}} variant="safe" range={{ from: '2026-09-01', to: '2026-09-10' }} />);
        expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('+€360.00');
        expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('commissioni ≈ €1.50');
        expect(screen.getByTestId('kpi-days')).toHaveTextContent('2 / 1');
        expect(screen.getByTestId('kpi-winrate')).toHaveTextContent('80%');          // 4V / 5
        expect(screen.getByTestId('kpi-winrate')).toHaveTextContent('3 chiusi a mercato');
        expect(screen.getByTestId('kpi-pf')).toHaveTextContent('10.00');
        expect(screen.getByTestId('kpi-expectancy')).toHaveTextContent('+€72.00');
        expect(screen.getByTestId('kpi-dd')).toHaveTextContent('€40.00');
        expect(screen.getByTestId('kpi-dd')).toHaveTextContent('sul picco');
        expect(screen.getByTestId('kpi-best')).toHaveTextContent('+€300.00');
        expect(screen.getByTestId('kpi-best')).toHaveTextContent(/3 settembre/);
        expect(screen.getByTestId('kpi-worst')).toHaveTextContent('−€40.00');
        expect(screen.getByTestId('kpi-streak')).toHaveTextContent('1+ / 1−');
        expect(screen.getByTestId('kpi-streak')).toHaveTextContent('1 giornate positive di fila');
        expect(screen.getByTestId('kpi-liab')).toHaveTextContent('€50.00');
        expect(screen.queryByTestId('kpi-goal')).toBeNull();                          // solo Omega
        expect(screen.getByTestId('period-range')).toHaveTextContent(/1 settembre → 10 settembre 2026/);
        expect(screen.getByRole('img', { name: 'Equity per giornata' })).toBeInTheDocument();
    });

    it('breakdown Safe: strategia, sport, origine con etichette italiane e ordinamento per P&L', () => {
        render(<PerformancePanel rows={ROWS} period="month" onPeriodChange={() => {}} variant="safe" />);
        const strat = screen.getByTestId('breakdown-strategy');
        const rows = within(strat).getAllByRole('row').slice(1);
        expect(rows[0]).toHaveTextContent('BASE');
        expect(rows[0]).toHaveTextContent('+€400.00');
        expect(rows[0]).toHaveTextContent('100%');
        expect(rows[1]).toHaveTextContent('TENNIS');
        expect(rows[1]).toHaveTextContent('−€40.00');
        expect(within(screen.getByTestId('breakdown-sport')).getByText('⚽ Calcio')).toBeInTheDocument();
        expect(within(screen.getByTestId('breakdown-origin')).getByText('✋ Manuale')).toBeInTheDocument();
    });

    it('Omega: tile obiettivo centrato (1/3) e breakdown per gamba senza sport', () => {
        const rows = ROWS.map((r) => ({ ...r, by_strategy: { ht_cs: { n: 1, pnl: r.pnl_realized, won: r.won, lost: r.lost } } }));
        render(<PerformancePanel rows={rows} period="30d" onPeriodChange={() => {}} variant="omega" />);
        expect(screen.getByTestId('kpi-goal')).toHaveTextContent('1/3');
        expect(screen.getByTestId('kpi-goal')).toHaveTextContent('33% delle giornate');
        expect(within(screen.getByTestId('breakdown-strategy')).getByText('Gamba 1T (Half Time Score)')).toBeInTheDocument();
        expect(screen.queryByTestId('breakdown-sport')).toBeNull();
    });

    it('selettore periodo: stato premuto e callback', async () => {
        const user = userEvent.setup();
        const onPeriodChange = vi.fn();
        render(<PerformancePanel rows={ROWS} period="month" onPeriodChange={onPeriodChange} variant="safe" />);
        expect(screen.getByRole('button', { name: 'Mese corrente' })).toHaveAttribute('aria-pressed', 'true');
        await user.click(screen.getByRole('button', { name: '90 giorni' }));
        expect(onPeriodChange).toHaveBeenCalledWith('90d');
    });

    it('senza righe: KPI neutri, nessun breakdown, curva vuota', () => {
        render(<PerformancePanel rows={[]} period="year" onPeriodChange={() => {}} variant="omega" />);
        expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('+€0.00');
        expect(screen.getByTestId('kpi-pnl')).toHaveTextContent('0 giornate operative');
        expect(screen.getByTestId('kpi-winrate')).toHaveTextContent('—');
        expect(screen.getByTestId('kpi-pf')).toHaveTextContent('—');
        expect(screen.getByTestId('kpi-goal')).toHaveTextContent('nessun obiettivo registrato');
        expect(screen.queryByTestId('breakdown-strategy')).toBeNull();
        expect(screen.getByText(/nessuna giornata regolata nel periodo/)).toBeInTheDocument();
    });
});
