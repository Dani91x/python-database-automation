// ============================================================================
// CERT. 13/09 — SafeTradesTable: ogni riga dichiara la sua MODALITÀ.
//
// Il backend etichetta con `mode` ogni trade; la tabella non lo mostrava
// affatto. Con un control lasciato in LIVE (safe_stop non lo riporta a paper)
// una tabella di posizioni con soldi veri era indistinguibile da una
// simulazione, e il cash out di ogni riga usa la modalità DEL TRADE.
//
// Qui dentro anche la separazione dei colori: il VIOLA resta alla variante
// «Risultato Esatto», il MANUALE passa al ciano — nella stessa tabella lo
// stesso colore non può significare due cose.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { SafeTradesTable, safeRowStatus } from './SafeTradesTable';
import { VARIANT_STYLE } from './variantStyles';
import type { SafeTrade } from '@/lib/safeBot';

function trade(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'esatto',
        market_id: '1.9', market_type: 'CORRECT_SCORE', selection_id: 1, selection_name: 'Altro risultato Casa',
        side: 'lay', mode: 'paper', price: 40, size: 5, liability: 195, commission: 0.05,
        minute_at_entry: 49, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-13T10:00:00Z', settled_at: null, origin: 'auto',
        closes_trade_id: null, signal_key: null, meta: null,
        ...over,
    };
}

function renderTable(rows: SafeTrade[], currentMode?: 'paper' | 'live') {
    render(
        <SafeTradesTable
            trades={rows} commissionPct={5} liveFeed={{}} onCashOut={vi.fn()}
            currentMode={currentMode}
        />,
    );
}

describe('SafeTradesTable — modalità su OGNI riga', () => {
    it('la riga PAPER ha un badge ESPLICITO, non l’assenza di badge', () => {
        renderTable([trade({ mode: 'paper' })]);
        const row = screen.getByTestId('safe-trade-row');
        expect(row).toHaveAttribute('data-mode', 'paper');
        expect(within(row).getByTestId('safe-trade-mode')).toHaveTextContent('PAPER');
    });

    it('la riga LIVE è marcata in rosso (soldi veri)', () => {
        renderTable([trade({ mode: 'live' })]);
        const badge = screen.getByTestId('safe-trade-mode');
        expect(badge).toHaveTextContent('LIVE');
        expect(badge.className).toMatch(/red/);
    });

    it('riga di una modalità diversa da quella del servizio: visibile ma ATTENUATA', () => {
        renderTable([trade({ id: 1, mode: 'paper' }), trade({ id: 2, mode: 'live' })], 'paper');
        const rows = screen.getAllByTestId('safe-trade-row');
        const live = rows.find((r) => r.getAttribute('data-mode') === 'live') as HTMLElement;
        const paper = rows.find((r) => r.getAttribute('data-mode') === 'paper') as HTMLElement;
        expect(live).toHaveAttribute('data-other-mode', '1');
        expect(live.className).toMatch(/opacity-60/);
        expect(live.title).toMatch(/il servizio è in PAPER/);
        // la riga della modalità corrente resta a piena leggibilità
        expect(paper).not.toHaveAttribute('data-other-mode');
    });

    it('anche la gamba di CHIUSURA dichiara la sua modalità (è un ordine a sé)', () => {
        renderTable([
            trade({ id: 1, mode: 'live', status: 'hedged' }),
            trade({ id: 2, mode: 'live', closes_trade_id: 1, side: 'back', size: 4, price: 30 }),
        ]);
        expect(screen.getByTestId('safe-closing-mode')).toHaveTextContent('LIVE');
    });
});

describe('SafeTradesTable — un colore, un significato', () => {
    it('il VIOLA resta alla variante «Risultato Esatto»: il manuale è di un altro colore', () => {
        // la variante esatto è viola nel design system…
        expect(VARIANT_STYLE.esatto.badge).toMatch(/violet/);
        // …quindi nella tabella né il ✋ manuale né «CASH OUT MANUALE» possono esserlo
        renderTable([trade({ origin: 'manual' })]);
        const manuale = screen.getByTitle('piazzato manualmente');
        expect(manuale.className).not.toMatch(/violet/);

        const st = safeRowStatus(
            trade({ status: 'hedged' }),
            [trade({ id: 9, closes_trade_id: 1, origin: 'manual' })],
        );
        expect(st.label).toBe('CASH OUT MANUALE');
        expect(st.cls).not.toMatch(/violet/);
        expect(st.edge).not.toMatch(/violet/);
        // e nemmeno l'indaco, già occupato da «APPOGGIATA · NON ABBINATA»
        expect(st.cls).not.toMatch(/indigo/);
    });
});
