// ============================================================================
// Card operative (segnali e opportunità) — audit L-07 / M-21:
//   · lo stake accetta QUALSIASI importo fino a 0,01 € (place-and-trim del
//     servizio); il minimo di giurisdizione resta solo come nota;
//   · l'esito di ogni richiesta dice anche PERCHÉ (mai solo "errore");
//   · una riga di opportunità troppo vecchia spiega perché «Piazza» è spento
//     (prima restava elencata come "attuale" per mezz'ora senza dire nulla).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InvestAction, MIN_STAKE_ALLOWED } from './InvestAction';
import { OpportunityGroup } from './OpportunityGroup';
import type { SafeOpportunityRow, SafeRequest } from '@/lib/safeBot';

/**
 * CERT. 13/09 — questo blocco SOSTITUISCE «InvestAction — minimo Betfair sullo
 * stake (L-07)», che verificava il comportamento SBAGLIATO: bottone «Piazza»
 * SPENTO sotto 2 € e testo «minimo Betfair 2,00 €: sotto questa cifra l'ordine
 * non viene immesso».
 *
 * Perché era sbagliato: il backend fa place-and-trim (parcheggio a quota 1000 →
 * taglio → riprezzo, REST + coda, già collegato), quindi QUALSIASI importo fino
 * a 0,01 € finisce davvero a mercato. Il vecchio test certificava un blocco che
 * impediva operazioni legittime; il `CashOutButton` accettava già da 0,01 €.
 * Ora: il minimo di giurisdizione resta VISIBILE come NOTA, il bottone resta
 * ACCESO, e l'unico minimo che blocca è 0,01 €.
 */
describe('InvestAction — qualsiasi importo fino a 0,01 € è piazzabile (place-and-trim)', () => {
    it('sotto il minimo di giurisdizione: NOTA informativa, bottone ACCESO', async () => {
        const user = userEvent.setup();
        const onPlace = vi.fn(async () => 1);
        render(
            <InvestAction
                mode="paper" side="back" price={2.5} sizeAvailable={100}
                defaultStake={5} requests={[]} onPlace={onPlace}
            />,
        );
        const stake = screen.getByLabelText('Stake');
        expect(stake).toHaveAttribute('min', String(MIN_STAKE_ALLOWED));
        await user.clear(stake);
        await user.type(stake, '1');
        const note = screen.getByTestId('invest-min-stake');
        expect(note).toHaveTextContent('1000→cancella→sposta');
        expect(note).not.toHaveTextContent('non viene immesso');
        expect(screen.getByTestId('invest-place')).toBeEnabled();
        await user.clear(stake);
        await user.type(stake, '2');
        expect(screen.queryByTestId('invest-min-stake')).toBeNull();
        expect(screen.getByTestId('invest-place')).toBeEnabled();
    });

    it('0,01 € si piazza davvero; 0 € no (non esiste un ordine da zero)', async () => {
        const user = userEvent.setup();
        const onPlace = vi.fn(async () => 1);
        render(
            <InvestAction
                mode="paper" side="back" price={2.5} sizeAvailable={100}
                defaultStake={5} requests={[]} onPlace={onPlace}
            />,
        );
        const stake = screen.getByLabelText('Stake');
        await user.clear(stake);
        await user.type(stake, '0.01');
        expect(screen.getByTestId('invest-place')).toBeEnabled();
        await user.click(screen.getByTestId('invest-place'));
        expect(onPlace).toHaveBeenCalledWith(0.01);
        await user.clear(stake);
        await user.type(stake, '0');
        expect(screen.getByTestId('invest-place')).toBeDisabled();
    });

    it('il minimo di giurisdizione viene dai parametri EFFETTIVI del servizio', async () => {
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
        // nota, non blocco: si può piazzare comunque
        expect(screen.getByTestId('invest-place')).toBeEnabled();
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
        // CERT. 12/09 — il testo dice la VERITA': l'eta' della riga e' quella
        // dell'ultimo CALCOLO del servizio, non quella della quota.
        expect(screen.getByTestId('opp-stale-note')).toHaveTextContent('modello non ricalcolato da 75s');
        expect(screen.getByTestId('invest-place')).toBeDisabled();
        expect(screen.getByTestId('opp-age')).toHaveTextContent('calcolo 75s fa');
    });

    it('mercato e selezione Betfair nel tooltip: l ingresso deve corrispondere', () => {
        renderRow(5);
        const oppRow = screen.getByTestId('opp-row');
        expect(within(oppRow).getByText('Under 3.5').title).toMatch(/selezione 47973 · mercato 1\.30/);
    });
});
