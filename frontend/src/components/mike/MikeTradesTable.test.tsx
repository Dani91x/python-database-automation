// Test COMPONENTE del tab "Trade" di Mike: chiusure ANNIDATE sotto l'apertura
// (H4), P&L NETTO del ciclo sulla riga di apertura, ✋ sulle righe decise
// dall'utente, VOID per MERCATO, nota del tetto di 500 righe della RPC, toggle
// della giornata operativa e rimando alla scheda della partita per le posizioni
// ancora aperte (il cash out di Mike è per EVENTO).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeTradesTable } from './MikeTradesTable';
import { MIKE_TRADES_LIMIT, type MikeTrade } from '@/lib/mike';

const DAY_START = Date.parse('2026-09-11T00:00:00+02:00');
const TODAY = '2026-09-11T14:00:00Z';
const YESTERDAY = '2026-09-10T14:00:00Z';

function trade(over: Partial<MikeTrade> = {}): MikeTrade {
    return {
        id: 1, event_id: 'E1', event_name: 'Roma v Lazio', strategy: 'under_entry',
        role: 'under_entry', cycle_no: 1, market_type: 'OVER_UNDER_35',
        selection_name: 'Under 3.5 Goals', side: 'back', mode: 'paper', price: 1.5, size: 10,
        liability: 10, status: 'won', pnl: 4.75, placed_at: TODAY, settled_at: TODAY,
        signal_key: 'under_entry-1-1', meta: {}, closes_trade_id: null, origin: 'auto', ...over,
    };
}

describe('MikeTradesTable — chiusure annidate e P&L netto del ciclo', () => {
    const open = trade({ id: 10, pnl: -10, status: 'lost', meta: { pnl_gross: -10 } });
    const close = trade({
        id: 11, closes_trade_id: 10, role: 'under_green', side: 'lay', price: 1.48, size: 10,
        status: 'won', pnl: 10.4, selection_name: 'Under 3.5 Goals',
        meta: { exit_kind: 'greenup', exit_reason: 'under_green', pnl_gross: 11.0, commission_paid: 0.6 },
    });

    it('la chiusura sta SOTTO la sua apertura e il netto del ciclo è la somma', () => {
        render(<MikeTradesTable trades={[open, close]} dayStartMs={DAY_START} dayLabel="ven 11/09" />);
        const rows = screen.getAllByTestId('mike-trade-row');
        expect(rows).toHaveLength(1);                      // una riga di APERTURA
        const closes = screen.getAllByTestId('mike-trade-close');
        expect(closes).toHaveLength(1);
        expect(closes[0]).toHaveAttribute('data-closes', '10');
        // netto del ciclo = -10 + 10,40 = +0,40 (mai il lordo)
        expect(within(rows[0]).getByTestId('mike-trade-pnl')).toHaveTextContent('+0,40 €');
    });

    it('il tooltip del P&L dichiara lordo e commissione (riga NETTA)', () => {
        render(<MikeTradesTable trades={[open, close]} dayStartMs={DAY_START} />);
        const cell = within(screen.getAllByTestId('mike-trade-row')[0]).getByTestId('mike-trade-pnl');
        expect(cell).toHaveAttribute('title', expect.stringContaining('P&L di riga NETTO'));
    });

    it('una chiusura senza apertura fra le righe caricate è dichiarata ORFANA', () => {
        render(<MikeTradesTable trades={[close]} dayStartMs={DAY_START} />);
        expect(screen.getAllByTestId('mike-trade-row')[0]).toHaveTextContent('orfana');
    });
});

describe('MikeTradesTable — righe manuali, VOID per mercato, modalità', () => {
    it('✋ sulle righe decise dall’utente (origin/ruolo/uscita manuale)', () => {
        const rows = [
            trade({ id: 1, origin: 'manual' }),
            trade({ id: 2, role: 'manual_close', origin: 'auto' }),
            trade({ id: 3, meta: { exit_kind: 'manual' } }),
            trade({ id: 4 }),
        ];
        render(<MikeTradesTable trades={rows} dayStartMs={DAY_START} />);
        const trs = screen.getAllByTestId('mike-trade-row');
        expect(trs).toHaveLength(4);
        expect(screen.getAllByLabelText('manuale')).toHaveLength(3);
    });

    it('VOID dice QUALE selezione è stata annullata, non "partita annullata"', () => {
        render(
            <MikeTradesTable
                trades={[trade({ status: 'void', pnl: 0, selection_name: 'Under 3.5 Goals',
                                 meta: { void_reason: 'mercato_annullato' } })]}
                dayStartMs={DAY_START}
            />,
        );
        expect(screen.getByTestId('mike-trade-status')).toHaveTextContent('(Under 3.5 Goals)');
    });

    it('le righe LIVE sono marcate (soldi veri)', () => {
        render(<MikeTradesTable trades={[trade({ mode: 'live' })]} dayStartMs={DAY_START} />);
        expect(screen.getByTestId('mike-trade-live')).toHaveTextContent('LIVE');
    });
});

describe('MikeTradesTable — giornata operativa e tetto della RPC', () => {
    const oggi = trade({ id: 1, placed_at: TODAY, day_placed_at: TODAY });
    const ieri = trade({ id: 2, placed_at: YESTERDAY, day_placed_at: YESTERDAY });

    it('default = SOLO la giornata operativa; il toggle mostra tutte', async () => {
        const user = userEvent.setup();
        render(<MikeTradesTable trades={[oggi, ieri]} dayStartMs={DAY_START} dayLabel="ven 11/09" />);
        expect(screen.getAllByTestId('mike-trade-row')).toHaveLength(1);
        expect(screen.getByTestId('mike-trades')).toHaveTextContent('ven 11/09');
        await user.click(screen.getByTestId('mike-trades-toggle'));
        expect(screen.getAllByTestId('mike-trade-row')).toHaveLength(2);
        expect(screen.getByTestId('mike-trades')).toHaveTextContent('Tutti i trade caricati');
        await user.click(screen.getByTestId('mike-trades-toggle'));
        expect(screen.getAllByTestId('mike-trade-row')).toHaveLength(1);
    });

    it('senza giornata dal DB lo DICHIARA e mostra tutto (migrazione v2 assente)', () => {
        render(<MikeTradesTable trades={[oggi, ieri]} dayStartMs={null} summary={{ openCount: 0 }} />);
        expect(screen.getByTestId('mike-trades-noday')).toHaveTextContent('mike_bot_v2.sql');
        expect(screen.getAllByTestId('mike-trade-row')).toHaveLength(2);
    });

    it('al tetto di 500 righe lo dice (la RPC non ne manda di più)', () => {
        const many = Array.from({ length: MIKE_TRADES_LIMIT }, (_, i) =>
            trade({ id: i + 1, signal_key: `s${i}` }));
        render(<MikeTradesTable trades={many} dayStartMs={DAY_START} summary={{ openCount: 1 }} />);
        expect(screen.getByTestId('mike-trades-capped'))
            .toHaveTextContent(`mostrate le ultime ${MIKE_TRADES_LIMIT} righe`);
    });

    it('il riepilogo legge gli AGGREGATI del DB, non ricontato dal client', () => {
        render(
            <MikeTradesTable
                trades={[oggi]}
                dayStartMs={DAY_START}
                summary={{ openCount: 7, won: 3, lost: 2, lockedPnl: 1.5, openLiability: 42, reconciling: 1 }}
            />,
        );
        const head = screen.getByTestId('mike-trades');
        expect(head).toHaveTextContent('posizioni aperte 7');
        expect(head).toHaveTextContent('3V');
        expect(head).toHaveTextContent('2P');
        expect(head).toHaveTextContent('42,00 €');
        expect(head).toHaveTextContent('1 in verifica');
    });

    it('senza trade nella giornata resta un vuoto parlante', () => {
        render(<MikeTradesTable trades={[ieri]} dayStartMs={DAY_START} />);
        expect(screen.queryByTestId('mike-trades-table')).toBeNull();
        expect(screen.getByTestId('mike-trades')).toHaveTextContent('Nessun trade nella giornata operativa');
    });
});

describe('MikeTradesTable — rimando alla scheda della partita', () => {
    it('una posizione APERTA porta alla card (il cash out è per evento)', async () => {
        const user = userEvent.setup();
        const onOpenEvent = vi.fn();
        render(
            <MikeTradesTable
                trades={[trade({ id: 1, status: 'open', pnl: 0, settled_at: null })]}
                dayStartMs={DAY_START}
                onOpenEvent={onOpenEvent}
            />,
        );
        const link = screen.getByTestId('mike-trade-goto-card');
        expect(link).toHaveTextContent('scheda partita');
        expect(link).toHaveAttribute('data-event-id', 'E1');
        await user.click(link);
        expect(onOpenEvent).toHaveBeenCalledWith('E1');
    });

    it('una riga già REGOLATA non ha nessun rimando (niente da chiudere)', () => {
        render(
            <MikeTradesTable trades={[trade({ status: 'won' })]} dayStartMs={DAY_START}
                             onOpenEvent={vi.fn()} />,
        );
        expect(screen.queryByTestId('mike-trade-goto-card')).toBeNull();
    });

    it('senza gestore il rimando non compare (tab Regolate / storico)', () => {
        render(<MikeTradesTable trades={[trade({ status: 'open' })]} dayStartMs={DAY_START} />);
        expect(screen.queryByTestId('mike-trade-goto-card')).toBeNull();
    });
});
