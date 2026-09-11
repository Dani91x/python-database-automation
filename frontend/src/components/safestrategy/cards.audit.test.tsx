// ============================================================================
// Card operative (segnali e opportunità) — audit L-07 / M-21:
//   · lo step dello stake rispetta il MINIMO Betfair (2 €) in uso dal servizio;
//   · l'esito di ogni richiesta dice anche PERCHÉ (mai solo "errore");
//   · una riga di opportunità troppo vecchia spiega perché «Piazza» è spento
//     (prima restava elencata come "attuale" per mezz'ora senza dire nulla).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InvestAction, BETFAIR_MIN_STAKE } from './InvestAction';
import { OpportunityGroup } from './OpportunityGroup';
import type { SafeOpportunityRow, SafeRequest } from '@/lib/safeBot';

describe('InvestAction — minimo Betfair sullo stake (L-07)', () => {
    it('sotto il minimo il bottone è spento e il motivo è scritto', async () => {
        const user = userEvent.setup();
        const onPlace = vi.fn(async () => 1);
        render(
            <InvestAction
                mode="paper" side="back" price={2.5} sizeAvailable={100}
                defaultStake={5} requests={[]} onPlace={onPlace}
            />,
        );
        const stake = screen.getByLabelText('Stake');
        expect(stake).toHaveAttribute('min', String(BETFAIR_MIN_STAKE));
        await user.clear(stake);
        await user.type(stake, '1');
        expect(screen.getByTestId('invest-min-stake')).toHaveTextContent('minimo Betfair 2,00 €');
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        await user.clear(stake);
        await user.type(stake, '2');
        expect(screen.queryByTestId('invest-min-stake')).toBeNull();
        expect(screen.getByTestId('invest-place')).toBeEnabled();
    });

    it('il minimo viene dai parametri EFFETTIVI del servizio, non da una costante', async () => {
        const user = userEvent.setup();
        render(
            <InvestAction
                mode="paper" side="back" price={2.5} sizeAvailable={100}
                defaultStake={5} minStake={4} requests={[]} onPlace={vi.fn(async () => 1)}
            />,
        );
        const stake = screen.getByLabelText('Stake');
        await user.clear(stake);
        await user.type(stake, '3');
        expect(screen.getByTestId('invest-min-stake')).toHaveTextContent('4,00 €');
        expect(screen.getByTestId('invest-place')).toBeDisabled();
    });
});

describe('InvestAction — esito della richiesta col MOTIVO (L-07)', () => {
    const req = (over: Partial<SafeRequest>): SafeRequest => ({
        id: 7, kind: 'place', payload: {}, status: 'done', result: null,
        created_at: 'x', updated_at: null, ...over,
    } as SafeRequest);

    async function place(requests: SafeRequest[]) {
        const user = userEvent.setup();
        render(
            <InvestAction
                mode="paper" side="back" price={2.5} sizeAvailable={100}
                defaultStake={5} requests={requests} onPlace={vi.fn(async () => 7)}
            />,
        );
        await user.click(screen.getByTestId('invest-place'));
    }

    it('errore: badge rosso E dettaglio del servizio', async () => {
        await place([req({ status: 'error', result: { error: 'INSUFFICIENT_FUNDS' } })]);
        expect(await screen.findByTestId('invest-status')).toHaveAttribute('data-tone', 'error');
        expect(screen.getByTestId('invest-status-message')).toHaveTextContent('INSUFFICIENT_FUNDS');
    });

    it('rifiutato: non è un errore, e il motivo si legge', async () => {
        await place([req({ status: 'rejected', result: { rejected: true, message: 'feed non fresco' } })]);
        const badge = await screen.findByTestId('invest-status');
        expect(badge).toHaveAttribute('data-tone', 'rejected');
        expect(badge).toHaveTextContent('rifiutato');
        expect(screen.getByTestId('invest-status-message')).toHaveTextContent('feed non fresco');
    });

    it('eseguito: messaggio del servizio', async () => {
        await place([req({ result: { ok: true, message: 'ordine a mercato', trade_id: 42 } })]);
        expect(await screen.findByTestId('invest-status')).toHaveAttribute('data-tone', 'ok');
        expect(screen.getByTestId('invest-status-message')).toHaveTextContent('ordine a mercato');
    });
});

describe('OpportunityGroup — freschezza dichiarata (M-21)', () => {
    const row = (ageSec: number): SafeOpportunityRow => ({
        event_id: 'e1', sport: 'calcio',
        updated_at: new Date(Date.now() - ageSec * 1000).toISOString(),
        payload: {
            minute: 62, score_home: 2, score_away: 1, event_name: 'Roma vs Lazio',
            lambdas: null, opps: [{
                kind: 'model', market_type: 'OVER_UNDER_35', market_name: 'Over/Under 3.5', line: 3.5,
                market_id: '1.30', selection_id: 47973, selection_name: 'Under 3.5', side: 'back',
                price: 1.38, size_available: 80, p_model: 0.8, p_implied: 0.72,
                edge: 0.08, ev: 0.1, confidence: 0.8, rationale: null,
            }],
        },
    } as SafeOpportunityRow);

    function renderRow(ageSec: number) {
        render(
            <OpportunityGroup
                row={row(ageSec)} mode="paper" stake={5} requests={[]}
                minConfidence={0} sideFilter="all" nowMs={Date.now()}
                onPlace={vi.fn(async () => 1)}
            />,
        );
    }

    it('riga fresca: nessun avviso, «Piazza» disponibile', () => {
        renderRow(5);
        expect(screen.queryByTestId('opp-stale-note')).toBeNull();
        expect(screen.getByTestId('invest-place')).toBeEnabled();
    });

    it('riga vecchia: avviso ESPLICITO del perché «Piazza» è spento', () => {
        renderRow(75);
        expect(screen.getByTestId('opp-stale-note')).toHaveTextContent('non aggiornati da 75s');
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        expect(screen.getByTestId('opp-age')).toHaveTextContent('75s fa');
    });

    it('mercato e selezione Betfair nel tooltip: l ingresso deve corrispondere', () => {
        renderRow(5);
        const oppRow = screen.getByTestId('opp-row');
        expect(within(oppRow).getByText('Under 3.5').title).toMatch(/selezione 47973 · mercato 1\.30/);
    });
});
