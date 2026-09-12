// ============================================================================
// COLLAUDO DELLA CHIUSURA (12/09/2026) — Safe Strategy, dalla colonna al bottone.
//
// CHIUSURA-01  La colonna "Se chiudo ora" e l'etichetta del bottone Cash out
//              devono essere LO STESSO numero, e quel numero deve essere quello
//              che il servizio bloccherà (stake di copertura al centesimo).
// CHIUSURA-04  Feed stantio: i bottoni che muovono soldi si spengono col motivo.
// CHIUSURA-05  Dopo una copertura PARZIALE il residuo resta chiudibile e il
//              bottone dice che chiude il RESIDUO (difetto storico C-02).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SafeTradesTable } from './SafeTradesTable';
import { partialLockedPnl, netAfterCommission } from '@/components/trading/CashOutButton';
import type { FeedFreshness, SafeTrade } from '@/lib/safeBot';
import type { CalcioScanPayload } from '@/lib/safeStrategyScan';

/** lay 5,26 @110 su un correct score: −573,34 € se esce, +5,26 € altrimenti */
function trade(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 47, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'esatto',
        market_id: '1.5', market_type: 'CORRECT_SCORE', selection_id: 4, selection_name: '3 - 2',
        side: 'lay', mode: 'paper', price: 110, size: 5.26, liability: 573.34, commission: 0.05,
        minute_at_entry: 42, score_at_entry: '0-0', status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-12T10:00:00Z', settled_at: null, origin: 'auto',
        closes_trade_id: null, signal_key: null, meta: null,
        ...over,
    };
}

// il 3-2 si è allontanato: la quota è SALITA a 200 → chiudere il lay incassa
const FEED: Record<string, CalcioScanPayload> = {
    e1: {
        media: null, event_name: 'Roma vs Lazio', home: 'Roma', away: 'Lazio',
        competition: 'Serie A', open_date: null, inplay: true,
        mo_market_id: '1.1', mo_status: 'OPEN',
        odds: {
            home: { selection_id: 11, back: 1.3, lay: 1.32 },
            draw: { selection_id: 58805, back: 5, lay: 5.2 },
            away: { selection_id: 12, back: 9, lay: 9.4 },
        },
        minute: 60, score_home: 0, score_away: 0, red_home: 0, red_away: 0, pre_ko: null,
        cs: {
            market_id: '1.5', status: 'OPEN', any_other_home: null, any_other_away: null,
            selections: [{
                selection_id: 4, name: '3 - 2', runner_status: 'ACTIVE',
                back: 200, lay: 220, back_size: 40, lay_size: 30,
            }],
        },
        ou: [],
    } as unknown as CalcioScanPayload,
};

const FRESH: FeedFreshness = { ageSec: 3, scannerAlive: true, hardOld: false, stale: false };
const STALE: FeedFreshness = { ageSec: 480, scannerAlive: false, hardOld: true, stale: true };

function renderTable(rows: SafeTrade[], extra: Partial<React.ComponentProps<typeof SafeTradesTable>> = {}) {
    const onCashOut = vi.fn();
    render(
        <SafeTradesTable
            trades={rows}
            commissionPct={5}
            liveFeed={FEED}
            freshnessOf={() => FRESH}
            onCashOut={onCashOut}
            {...extra}
        />,
    );
    return { onCashOut };
}

describe('CHIUSURA-01 — colonna e bottone dicono lo STESSO numero', () => {
    it('"Se chiudo ora" = etichetta del cash out = bloccato del servizio (+1,68 € netti)', () => {
        // verità del backend: stake 2,89 (2,893 arrotondati) → peggiore dei due
        // esiti +1,77 lordi; con la commissione del TRADE (5 %) → +1,68 netti.
        const atteso = netAfterCommission(partialLockedPnl(200, -573.34, 5.26, 1), 0.05);
        expect(atteso).toBeCloseTo(1.68, 2);

        renderTable([trade()]);
        expect(screen.getByTestId('safe-close-now')).toHaveTextContent('+1,68 €');
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('+1,68 €');
        // il valore IDEALE (+2,37 lordi / +2,25 netti) non compare da nessuna parte
        expect(screen.getByTestId('safe-close-now')).not.toHaveTextContent('2,25');
        expect(screen.getByTestId('cashout-trigger')).not.toHaveTextContent('2,25');
    });

    it('vale la commissione DEL TRADE (2 %), non il parametro del form (5 %)', () => {
        renderTable([trade({ commission: 0.02 })]);
        const atteso = netAfterCommission(partialLockedPnl(200, -573.34, 5.26, 1), 0.02);
        expect(atteso).toBeCloseTo(1.73, 2);
        expect(screen.getByTestId('safe-close-now')).toHaveTextContent('+1,73 €');
        expect(screen.getByTestId('cashout-trigger')).toHaveTextContent('+1,73 €');
    });

    it('il dialog conferma lo stesso numero della card', async () => {
        const user = userEvent.setup();
        renderTable([trade()]);
        await user.click(screen.getByTestId('cashout-trigger'));
        expect(await screen.findByTestId('cashout-locked')).toHaveTextContent('+1,68 €');
    });
});

describe('CHIUSURA-04 — feed stantio: niente soldi su prezzi fantasma', () => {
    it('quote oltre il tetto: cash out spento e motivo leggibile', () => {
        renderTable([trade()], { freshnessOf: () => STALE });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
        expect(screen.getByTestId('cashout-disabled-wrap')).toBeInTheDocument();
    });

    it('mercato SOSPESO: cash out spento e motivo sulla riga', () => {
        const feed = JSON.parse(JSON.stringify(FEED)) as typeof FEED;
        (feed.e1 as unknown as { cs: { status: string } }).cs.status = 'SUSPENDED';
        renderTable([trade()], { liveFeed: feed });
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
        expect(screen.getByTestId('safe-market-blocked')).toHaveTextContent('mercato sospeso');
    });
});

describe('CHIUSURA-05 — dopo una copertura PARZIALE il residuo resta chiudibile', () => {
    const parziale = {
        hedge: {
            fraction: 0.4, remaining_liability: 344.0, hedged_size: 1.16,
            residual_size: 3.16, complete: false,
        },
        hedged_size: 1.16, residual_size: 3.16,
        if_win: -344.0, if_lose: 3.16,
    };

    it('posizione APERTA coperta al 40 %: bottone vivo, marcato "residuo"', () => {
        renderTable([trade({ meta: parziale })]);
        const btn = screen.getByTestId('cashout-trigger');
        expect(btn).toBeEnabled();
        expect(btn).toHaveAttribute('data-residual', '1');
        expect(btn).toHaveTextContent('residuo');
        expect(screen.getByTestId('safe-status')).toHaveTextContent('COPERTA 40 %');
    });

    it('la chiusura parziale NON blocca il resto: il dialog parla di RESIDUO', async () => {
        const user = userEvent.setup();
        const { onCashOut } = renderTable([trade({ meta: parziale })]);
        await user.click(screen.getByTestId('cashout-trigger'));
        expect(await screen.findByTestId('cashout-residual-note')).toHaveTextContent(/residuo/);
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(onCashOut).toHaveBeenCalledTimes(1);
    });

    it('anche una riga già "hedged" ma incompleta resta chiudibile', () => {
        renderTable([trade({ status: 'hedged', meta: parziale })]);
        expect(screen.getByTestId('cashout-trigger')).toBeEnabled();
    });

    it('copertura COMPLETA: nessun bottone, solo "coperto"', () => {
        renderTable([trade({
            status: 'hedged',
            meta: {
                hedge: { fraction: 1, remaining_liability: 0, hedged_size: 2.89, residual_size: 0, complete: true },
                locked_pnl: 1.77,
            },
        })]);
        expect(screen.queryByTestId('cashout-trigger')).toBeNull();
        expect(screen.getByText('coperto')).toBeInTheDocument();
    });
});

describe('CHIUSURA-06 — il P&L REALE della posizione, non della sola apertura', () => {
    // caso REALE dal DB (safe_strategy_trades #47, 12/09): lay 2 € @46 coperto
    // con tre back. L'apertura chiude a +2,00 €, la POSIZIONE a −10,27 €.
    const apertura = trade({
        id: 47, status: 'won', pnl: 2, price: 46, size: 2, liability: 90,
        meta: {
            cashout: true, exit_kind: 'loss', position_id: 47,
            position_pnl: -10.27, position_result: 'lost',
        },
    });
    const chiusura = (id: number, price: number, size: number, pnl: number): SafeTrade =>
        trade({ id, closes_trade_id: 47, side: 'back', status: 'lost', price, size, pnl, meta: null });

    it('la riga dichiara il risultato della POSIZIONE accanto a quello della gamba', () => {
        renderTable([apertura, chiusura(51, 2.48, 6.01, -6.01), chiusura(52, 10.5, 3.43, -3.43), chiusura(53, 14.5, 2.83, -2.83)]);
        const pos = screen.getByTestId('safe-position-result');
        expect(pos).toHaveTextContent('posizione in perdita');
        expect(pos).toHaveTextContent(/[-−]10,27 €/);
    });

    it('senza gambe di chiusura non si inventa nessuna posizione', () => {
        renderTable([trade({ status: 'won', pnl: 1.9, meta: null })]);
        expect(screen.queryByTestId('safe-position-result')).toBeNull();
    });
});
