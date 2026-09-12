// ============================================================================
// COLLAUDO DELLA CHIUSURA (12/09/2026) — Omega, dalla cella al bottone.
//
// CHIUSURA-01  "se chiudo ora" della cella e l'etichetta del Cash out devono
//              essere LO STESSO numero (quello che il servizio bloccherà).
// CHIUSURA-04  Feed oltre i 20 s: il bottone che muove soldi si spegne col
//              motivo scritto.
// CHIUSURA-05  Copertura PARZIALE: il residuo resta chiudibile e il dialog dice
//              che si chiude il RESIDUO, non la posizione intera.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MatchTradesTable, closeNowPnl } from './MatchTradesTable';
import { partialLockedPnl, netAfterCommission } from '@/components/trading/CashOutButton';
import type { MatchTradeLike } from '@/lib/omegaMatches';

function t(over: Partial<MatchTradeLike> & { id: number }): MatchTradeLike {
    return {
        event_id: 'e1', event_name: 'Roma vs Lazio', phase: 'ft_cs', side: 'lay', status: 'open', pnl: 0,
        price: 110, size: 5.26, liability: 573.34, placed_at: '2026-09-11T14:00:00Z', settled_at: null,
        kickoff: '2026-09-11T13:30:00Z', closes_trade_id: null, meta: {}, runner_name: '3 - 2',
        minute_at_entry: 42, score_at_entry: '0-0', origin: 'auto', mode: 'paper', selection_id: 4,
        ...over,
    } as MatchTradeLike & { selection_id?: number };
}

const NOW = Date.parse('2026-09-11T16:00:00Z');
const FEED = {
    e1: {
        minute: 60, score_home: 0, score_away: 0,
        cs: {
            market_id: '1.1', status: 'OPEN',
            selections: [{ selection_id: 4, name: '3 - 2', back: 200, lay: 220 }],
        },
    },
} as never;

function renderTable(trades: MatchTradeLike[], over: Record<string, unknown> = {}) {
    const onCashOut = vi.fn();
    render(
        <MatchTradesTable
            trades={trades}
            liveFeed={FEED}
            feedUpdatedAt={{ e1: new Date(NOW - 3000).toISOString() }}
            nowMs={NOW}
            liveView
            commission={5}
            day="2026-09-11"
            onCashOut={onCashOut}
            {...over}
        />,
    );
    return { onCashOut };
}

describe('CHIUSURA-01 — cella e bottone dicono lo STESSO numero', () => {
    it('"se chiudo ora" = etichetta del Cash out = bloccato del servizio', () => {
        const r = closeNowPnl({ win: -573.34, lose: 5.26 }, { back: 200, lay: 220 }, 5)!;
        expect(r.gross).toBeCloseTo(partialLockedPnl(200, -573.34, 5.26, 1), 2);
        expect(r.net).toBeCloseTo(netAfterCommission(r.gross, 5), 2);
        expect(r.net).toBeCloseTo(1.68, 2);

        renderTable([t({ id: 1 })]);
        expect(screen.getByTestId('omega-close-now')).toHaveTextContent('+1,68 €');
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('+1,68 €');
    });

    it('commissione FISSATA sul trade (2 %): coerente su cella e bottone', () => {
        renderTable([t({ id: 1, meta: { commission: 0.02 } })]);
        expect(screen.getByTestId('omega-close-now')).toHaveTextContent('+1,73 €');
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('+1,73 €');
    });

    it('il dialog conferma lo stesso numero della cella', async () => {
        const user = userEvent.setup();
        renderTable([t({ id: 1 })]);
        await user.click(screen.getByTestId('cashout-trigger'));
        expect(await screen.findByTestId('cashout-locked')).toHaveTextContent('+1,68 €');
    });
});

describe('CHIUSURA-04 — feed fermo: nessuna chiusura su prezzi vecchi', () => {
    it('oltre 20 s il cash out è spento e il motivo è scritto', () => {
        renderTable([t({ id: 1 })], { feedUpdatedAt: { e1: new Date(NOW - 60_000).toISOString() } });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
        expect(screen.getByTestId('cashout-disabled-wrap')).toBeInTheDocument();
        expect(screen.getAllByTestId('omega-feed-age')[0]).toHaveAttribute('data-stale', '1');
    });

    it('nessuna riga di feed: cash out spento (FEED ASSENTE non è "va tutto bene")', () => {
        renderTable([t({ id: 1 })], { feedUpdatedAt: {} });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
    });
});

describe('CHIUSURA-05 — copertura PARZIALE: si chiude il RESIDUO', () => {
    const parziale = {
        hedge: {
            fraction: 0.4, remaining_liability: 344.0, hedged_size: 1.16,
            residual_size: 3.16, complete: false,
        },
    };

    it('nota sul residuo, bottone vivo e dialog che parla di residuo', async () => {
        const user = userEvent.setup();
        const { onCashOut } = renderTable([t({ id: 1, meta: parziale })]);
        expect(screen.getByTestId('omega-residual-note')).toHaveTextContent(/residuo scoperto/);
        const btn = screen.getByTestId('cashout-trigger');
        expect(btn).toBeEnabled();
        expect(btn).toHaveAttribute('data-residual', '1');
        await user.click(btn);
        expect(await screen.findByTestId('cashout-residual-note')).toHaveTextContent(/residuo/);
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(onCashOut).toHaveBeenCalledTimes(1);
    });

    it('lo stato della gamba dice quanto è coperto e quanto resta', () => {
        renderTable([t({ id: 1, meta: parziale })]);
        const leg = screen.getByTestId('omega-leg-ft');
        expect(within(leg).getByTestId('omega-status')).toHaveTextContent(/COPERTA 40\s*%/);
    });

    it('chiusura IN VOLO (pending): nessun secondo ordine di copertura', () => {
        renderTable([t({ id: 1, meta: parziale })], { isCashOutPending: () => true });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
    });
});
