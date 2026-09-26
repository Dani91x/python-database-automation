// ============================================================================
// FIX-A (26/09) — Omega: «Se chiudo ora» della barra = somma delle CELLE, e
// gli aggregati di UNA modalità (E2E fase 3, U0427 e U0419/U0426).
//
// REPERTO U0427: barra «Se chiudo ora · PAPER +0,00 €» (il P&L bloccato)
// mentre le due righe dicevano −0,50 € (lay 1 @48 chiusa back @32) e −2,20 €
// (lay 1 @80 chiusa back @25). Righe con le chiavi di omega_trades.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MatchTradesTable, omegaCloseNowTotal } from './MatchTradesTable';
import type { MatchTradeLike } from '@/lib/omegaMatches';
import { aggregatiOmegaDellaModalita, omegaModalitaConAttivita, type OmegaAggregates } from '@/lib/omega';

function t(over: Partial<MatchTradeLike> & { id: number; selection_id: number }): MatchTradeLike {
    return {
        event_id: 'e1', event_name: 'Casa vs Ospite', phase: 'ft_cs', side: 'lay', status: 'open', pnl: 0,
        price: 48, size: 1, liability: 47, placed_at: '2026-09-26T09:10:57Z', settled_at: null,
        kickoff: '2026-09-26T09:00:00Z', closes_trade_id: null, meta: {}, runner_name: '2 - 3',
        minute_at_entry: 10, score_at_entry: '0-0', origin: 'auto', mode: 'paper',
        ...over,
    } as MatchTradeLike;
}

const TRADES = [
    t({ id: 1, event_id: 'e1', selection_id: 4, price: 48, liability: 47 }),
    t({ id: 2, event_id: 'e2', selection_id: 5, price: 80, liability: 79, runner_name: '0 - 0' }),
];
const FEED = {
    e1: { minute: 30, score_home: 2, score_away: 3,
        cs: { market_id: '1.1', status: 'OPEN', selections: [{ selection_id: 4, name: '2 - 3', back: 32, lay: 34 }] } },
    e2: { minute: 30, score_home: 0, score_away: 0,
        cs: { market_id: '1.2', status: 'OPEN', selections: [{ selection_id: 5, name: '0 - 0', back: 25, lay: 26 }] } },
} as never;

describe('omegaCloseNowTotal — la barra somma le stesse chiusure delle celle', () => {
    it('lay 1@48 → back 32 = −0,50; lay 1@80 → back 25 = −2,20: totale −2,70', () => {
        const r = omegaCloseNowTotal(TRADES, FEED, 5);
        expect(r.totale).toBe(-2.7);
        expect(r.valutate).toBe(2);
        expect(r.nonValutabili).toBe(0);
    });

    it('il totale coincide con la somma dei valori scritti nelle celle', () => {
        render(<MatchTradesTable trades={TRADES} liveFeed={FEED} commission={5} liveView
            feedUpdatedAt={{ e1: new Date().toISOString(), e2: new Date().toISOString() }} day="2026-09-26" />);
        const celle = screen.getAllByTestId('omega-close-now').map((c) => c.textContent ?? '');
        expect(celle.join(' ')).toContain('−0,50');
        expect(celle.join(' ')).toContain('−2,20');
    });

    it('una gamba viva senza prezzo NON vale zero: resta fuori e si conta', () => {
        const r = omegaCloseNowTotal(TRADES, { e1: (FEED as Record<string, unknown>).e1 } as never, 5);
        expect(r.totale).toBe(-0.5);
        expect(r.nonValutabili).toBe(1);
        expect(omegaCloseNowTotal(TRADES, {} as never, 5).totale).toBeNull();
    });
});

describe('aggregatiOmegaDellaModalita — mai la somma sotto un’etichetta', () => {
    const tutti = { realized_profit: -42.06, matches_traded: 109, open_liability: 274 } as OmegaAggregates;
    const paper = { realized_profit: -44.64, matches_traded: 109, events_traded: 100, open_liability: 274, mode: 'paper' } as OmegaAggregates;
    const live = { realized_profit: 2.58, matches_traded: 1, events_traded: 1, open_liability: 0, mode: 'live' } as OmegaAggregates;

    it('con la migrazione: ciascuna modalità i suoi numeri', () => {
        const st = { aggregates: tutti, aggregates_by_mode: { paper, live } };
        expect(aggregatiOmegaDellaModalita(st, 'paper')?.realized_profit).toBe(-44.64);
        expect(aggregatiOmegaDellaModalita(st, 'paper')?.events_traded).toBe(100);
        expect(aggregatiOmegaDellaModalita(st, 'live', 'paper')?.realized_profit).toBe(2.58);
        expect(omegaModalitaConAttivita(live)).toBe(true);
    });

    it('senza la migrazione: la modalità del bot come prima, l’altra ASSENTE (mai i numeri di tutte)', () => {
        const st = { aggregates: tutti, aggregates_by_mode: null };
        expect(aggregatiOmegaDellaModalita(st, 'paper', 'paper')).toBe(tutti);
        expect(aggregatiOmegaDellaModalita(st, 'live', 'paper')).toBeNull();
    });
});
