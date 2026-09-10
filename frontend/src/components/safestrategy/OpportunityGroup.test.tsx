// Test COMPONENTE di OpportunityGroup: filtri (helper esportato per lo stato
// vuoto della pagina), eta' della riga e "Investi" spento oltre 60 s.
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { OpportunityGroup, filterOpps, OPP_ROW_STALE_MS } from './OpportunityGroup';
import type { SafeOpportunityRow } from '@/lib/safeBot';

const NOW = Date.parse('2026-09-10T12:00:00Z');

function row(over: Partial<SafeOpportunityRow> = {}): SafeOpportunityRow {
    return {
        event_id: 'e1', sport: 'calcio',
        updated_at: new Date(NOW - 5_000).toISOString(),
        payload: {
            minute: 60, score_home: 1, score_away: 0, event_name: 'Roma vs Lazio',
            opps: [
                {
                    market_type: 'OVER_UNDER_25', market_name: 'Over/Under 2.5', line: 2.5,
                    market_id: '1.9', selection_id: 1, selection_name: 'Over 2.5', side: 'back',
                    price: 2.1, size_available: 50, p_model: 0.55, p_implied: 0.48, edge: 0.07,
                    ev: 0.15, confidence: 0.8, rationale: null,
                },
                {
                    market_type: 'MATCH_ODDS', market_name: 'Match Odds', line: null,
                    market_id: '1.1', selection_id: 2, selection_name: 'Lazio', side: 'lay',
                    price: 9, size_available: 20, p_model: 0.05, p_implied: 0.11, edge: 0.06,
                    ev: 0.1, confidence: 0.4, rationale: null,
                },
            ],
        },
        ...over,
    };
}

function renderGroup(r: SafeOpportunityRow, over: Partial<Parameters<typeof OpportunityGroup>[0]> = {}) {
    const onPlace = vi.fn(async () => 1);
    render(
        <OpportunityGroup
            row={r} mode="paper" stake={5} requests={[]} minConfidence={0} sideFilter="all"
            nowMs={NOW} onPlace={onPlace} {...over}
        />,
    );
    return { onPlace };
}

describe('filterOpps', () => {
    it('applica confidenza minima e lato, ordina per EV × confidenza', () => {
        expect(filterOpps(row(), 0, 'all').map((o) => o.selection_id)).toEqual([1, 2]);
        expect(filterOpps(row(), 0.5, 'all').map((o) => o.selection_id)).toEqual([1]);
        expect(filterOpps(row(), 0, 'lay').map((o) => o.selection_id)).toEqual([2]);
        expect(filterOpps(row(), 0.9, 'all')).toEqual([]);
    });

    it('payload senza opps -> vuoto', () => {
        expect(filterOpps(row({ payload: { opps: [] } as never }), 0, 'all')).toEqual([]);
    });
});

describe('OpportunityGroup — eta della riga (MEDIUM-3)', () => {
    it('riga fresca: mostra l eta e Investi e attivo', () => {
        renderGroup(row());
        expect(screen.getByTestId('opp-age')).toHaveTextContent('5s fa');
        for (const b of screen.getAllByTestId('invest-place')) expect(b).toBeEnabled();
    });

    it('riga piu vecchia di 60 s: Investi spento con motivo', () => {
        renderGroup(row({ updated_at: new Date(NOW - OPP_ROW_STALE_MS - 15_000).toISOString() }));
        expect(screen.getByTestId('opp-age')).toHaveTextContent('75s fa');
        for (const b of screen.getAllByTestId('invest-place')) expect(b).toBeDisabled();
        expect(screen.getAllByTestId('invest-disabled-reason')[0]).toHaveTextContent('quote non aggiornate (75s)');
    });

    it('filtri che escludono tutto: il gruppo non rende nulla', () => {
        renderGroup(row(), { minConfidence: 0.9 });
        expect(screen.queryByTestId('opp-group')).toBeNull();
    });
});
