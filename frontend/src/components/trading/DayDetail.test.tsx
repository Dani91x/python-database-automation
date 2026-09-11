// Test COMPONENTE del dettaglio giornata: aperture con chiusure annidate,
// badge uscita automatica, P&L bloccato, link live per posizioni vive,
// totali, stati vuoto/errore. Include ExitBadge.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DayDetail } from './DayDetail';
import { ExitBadge } from './ExitBadge';
import type { DayTrade } from '@/lib/dailyHistory';

const OPEN: DayTrade = {
    id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'base', side: 'back', mode: 'paper',
    price: 1.3, size: 10, liability: 10, status: 'open', pnl: 0, placed_at: '2026-09-10T18:00:00Z', settled_at: null,
    origin: 'auto', closes_trade_id: null, meta: null, selection_name: 'Roma', closes: [], total_pnl: 0,
    placed_in_day: true, settled_in_day: false,
};
const HEDGED_WON: DayTrade = {
    ...OPEN, id: 2, event_name: 'Inter vs Milan', strategy: 'esatto', side: 'lay', price: 40, size: 5, liability: 195,
    status: 'won', pnl: 3.1, settled_at: '2026-09-10T20:00:00Z', mode: 'live',
    meta: { locked_pnl: 2.5, exit_kind: 'time', exit_reason: "72' raggiunto" },
    closes: [{
        id: 3, event_id: 'e1', event_name: 'Inter vs Milan', side: 'back', mode: 'live', price: 30, size: 6.5, liability: 6.5,
        status: 'won', pnl: -0.6, placed_at: '2026-09-10T19:30:00Z', settled_at: '2026-09-10T20:00:00Z',
        closes_trade_id: 2, meta: { size_capped_from: 8 }, selection_name: 'Any Other Home Win',
    }],
    total_pnl: 2.5, placed_in_day: false, settled_in_day: true,
};
const LOST: DayTrade = {
    ...OPEN, id: 4, event_name: 'Sinner v Alcaraz', sport: 'tennis', strategy: 'tennis', origin: 'manual',
    status: 'lost', pnl: -10, total_pnl: -10, settled_at: '2026-09-10T21:00:00Z', meta: { exit_kind: 'loss' },
};

describe('DayDetail', () => {
    it('senza giorno: invito a selezionare', () => {
        render(<DayDetail day={null} trades={null} variant="safe" />);
        expect(screen.getByTestId('day-detail-empty')).toBeInTheDocument();
    });

    it('elenca aperture e chiusure con badge uscita, P&L bloccato, totale e link live', async () => {
        const user = userEvent.setup();
        const onGoLive = vi.fn();
        render(<DayDetail day="2026-09-10" trades={[OPEN, HEDGED_WON, LOST]} variant="safe" onGoLive={onGoLive} />);
        expect(screen.getByTestId('day-detail')).toHaveTextContent(/giovedì 10 settembre 2026/);
        expect(screen.getByTestId('day-detail')).toHaveTextContent('3 trade');
        expect(screen.getByText('1 ancora vivi')).toBeInTheDocument();
        // totale = solo regolati: 2.5 − 10
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('−€7.50');
        // liability piazzata OGGI: OPEN (10) + LOST (10); HEDGED_WON è di ieri
        expect(screen.getByTestId('day-detail')).toHaveTextContent('liability piazzata €20.00');

        const rows = screen.getAllByTestId('day-trade-row');
        expect(rows).toHaveLength(3);
        const hedged = rows[1];
        expect(within(hedged).getByText('R. ESATTO')).toBeInTheDocument();
        expect(within(hedged).getByText('LIVE')).toBeInTheDocument();
        expect(within(hedged).getByText('(prec.)')).toBeInTheDocument();
        expect(within(hedged).getByTestId('exit-badge')).toHaveTextContent('Uscita: tempo');
        expect(within(hedged).getByTestId('exit-badge')).toHaveAttribute('title', "72' raggiunto");
        expect(within(hedged).getByText('bloccato +€2.50')).toBeInTheDocument();
        expect(within(hedged).getByTestId('day-trade-pnl')).toHaveTextContent('+€2.50');

        const close = screen.getAllByTestId('day-close-row');
        expect(close).toHaveLength(1);
        expect(close[0]).toHaveTextContent('chiusura #3 di #2');
        expect(close[0]).toHaveTextContent('parziale');
        expect(close[0]).toHaveTextContent('−€0.60');

        const lost = rows[2];
        expect(within(lost).getByTestId('exit-badge')).toHaveTextContent('Uscita: perdita');
        expect(within(lost).getByText('✋')).toBeInTheDocument();
        expect(within(lost).getByTestId('day-trade-pnl')).toHaveTextContent('−€10.00');

        // apertura viva: link al live
        const open = rows[0];
        expect(within(open).getByTestId('day-trade-pnl')).toHaveTextContent('—');
        await user.click(within(open).getByTestId('day-trade-live'));
        expect(onGoLive).toHaveBeenCalledWith(OPEN);
        expect(within(hedged).queryByTestId('day-trade-live')).toBeNull();
    });

    it('Omega: una riga per PARTITA con gamba 2T, risultati reali e P&L (chiusure attaccate)', () => {
        const ft: DayTrade = {
            ...OPEN, strategy: undefined, selection_name: undefined, runner_name: '3 - 2', phase: 'ft_cs', side: 'lay',
            status: 'won', pnl: 2.16, total_pnl: -22.08, meta: { result_ht: '1-0', result_ft: '2-1', exit_kind: 'greenup', locked_pnl: -22.1 },
            closes: [{
                id: 9, event_id: 'e1', event_name: 'Roma vs Lazio', side: 'back', mode: 'paper', price: 4.9, size: 24.24, liability: 24.24,
                status: 'lost', pnl: -24.24, placed_at: '2026-09-10T18:30:00Z', settled_at: '2026-09-10T20:00:00Z',
                closes_trade_id: 1, meta: { exit_kind: 'greenup' },
            }],
        };
        render(<DayDetail day="2026-09-10" trades={[ft]} variant="omega" />);
        const row = screen.getByTestId('omega-match-row');
        expect(within(row).getByTestId('omega-leg-ht')).toHaveAttribute('data-empty', '1');
        const leg = within(row).getByTestId('omega-leg-ft');
        expect(within(leg).getByText('3 - 2')).toBeInTheDocument();
        expect(within(leg).getByTestId('omega-side')).toHaveTextContent('LAY');
        expect(within(leg).getByTestId('omega-leg-pnl')).toHaveTextContent('−22,08 €');
        expect(within(leg).getByTestId('omega-closing-line')).toHaveAttribute('data-closes', '1');
        expect(within(row).getByTestId('omega-result-ht')).toHaveTextContent('1-0');
        expect(within(row).getByTestId('omega-result-ft')).toHaveTextContent('2-1');
        expect(within(row).getByTestId('omega-match-pnl')).toHaveTextContent('−22,08 €');
        expect(within(row).getByTestId('omega-match-pnl').className).toMatch(/text-red-400/);
        expect(screen.getByTestId('day-total-pnl')).toHaveTextContent('−€22.08');
    });

    it('nessun trade / errore / caricamento', () => {
        const { rerender } = render(<DayDetail day="2026-09-10" trades={[]} variant="safe" />);
        expect(screen.getByTestId('day-detail-none')).toBeInTheDocument();
        rerender(<DayDetail day="2026-09-10" trades={null} loading variant="safe" />);
        expect(screen.getByText('caricamento…')).toBeInTheDocument();
        rerender(<DayDetail day="2026-09-10" trades={[]} error="RPC assente" variant="safe" />);
        expect(screen.getByTestId('day-detail-error')).toHaveTextContent('RPC assente');
    });
});

describe('ExitBadge', () => {
    it('non renderizza senza uscita; mappa kind e tooltip', () => {
        const { container, rerender } = render(<ExitBadge meta={{ locked_pnl: 1 }} />);
        expect(container).toBeEmptyDOMElement();
        rerender(<ExitBadge meta={{ exit_kind: 'red_card', exit_reason: 'rosso alla favorita 61′' }} />);
        const b = screen.getByTestId('exit-badge');
        expect(b).toHaveTextContent('Uscita: rosso');
        expect(b).toHaveAttribute('data-exit-kind', 'red_card');
        expect(b).toHaveAttribute('title', 'rosso alla favorita 61′');
        rerender(<ExitBadge meta={{ exit_kind: 'forced' }} />);
        expect(screen.getByTestId('exit-badge')).toHaveTextContent('Uscita: obbligatoria');
        rerender(<ExitBadge meta={{ exit_kind: 'profit' }} />);
        expect(screen.getByTestId('exit-badge')).toHaveTextContent('Uscita: profitto');
    });
});
