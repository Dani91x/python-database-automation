// Test COMPONENTE della tabella trade Safe: badge del TIPO sui trade di
// modello (meta.kind), stato di ATTESA (meta.exit_hold) e P(perdita) all'ingresso.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { SafeTradesTable, pctIt } from './SafeTradesTable';
import type { SafeTrade } from '@/lib/safeBot';

function trade(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'model',
        market_id: '1.9', market_type: 'OVER_UNDER_25', selection_id: 1, selection_name: 'Over 2.5',
        side: 'back', mode: 'paper', price: 2.1, size: 5, liability: 5, commission: 0.05,
        minute_at_entry: 60, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-10T10:00:00Z', settled_at: null, origin: 'auto',
        closes_trade_id: null, signal_key: null, meta: null,
        ...over,
    };
}

function renderTable(rows: SafeTrade[]) {
    render(<SafeTradesTable trades={rows} commissionPct={5} liveFeed={{}} onCashOut={vi.fn()} />);
}

describe('SafeTradesTable — trade di modello', () => {
    it('badge del tipo da meta.kind e P(perdita) all ingresso', () => {
        renderTable([trade({ meta: { kind: 'anomaly', p_lose_entry: 0.032 } })]);
        expect(screen.getByTestId('trade-kind')).toHaveAttribute('data-kind', 'anomaly');
        expect(screen.getByTestId('trade-kind')).toHaveTextContent('ANOMALIA');
        expect(screen.getByTestId('trade-p-lose-entry')).toHaveTextContent('P(perdita) ingresso 3,2%');
    });

    it('strategy model senza meta.kind = MODELLO; strategie classiche senza badge', () => {
        renderTable([trade({ id: 1 }), trade({ id: 2, strategy: 'esatto' })]);
        const kinds = screen.getAllByTestId('trade-kind');
        expect(kinds).toHaveLength(1);
        expect(kinds[0]).toHaveTextContent('MODELLO');
        expect(screen.getByText('R. ESATTO')).toBeInTheDocument();
        expect(screen.queryByTestId('trade-p-lose-entry')).toBeNull();
    });

    it('stato di attesa da meta.exit_hold: "In attesa: margine ampio, P(perdita) 0,4%"', () => {
        renderTable([trade({
            meta: { kind: 'model', exit_hold: { reason: 'wide_margin', p_lose: 0.004, source: 'model', locked: 1.2, ev_hold: 1.5, ts: '2026-09-10T10:05:00Z' } },
        })]);
        const hold = screen.getByTestId('trade-hold');
        expect(hold).toHaveTextContent('In attesa: margine ampio, P(perdita) 0,4%');
        expect(hold.title).toMatch(/fonte: model/);
        expect(hold.title).toMatch(/bloccabile ora: \+€1\.20/);
    });

    it('motivo ignoto: mostrato cosi com e; attesa non mostrata su trade chiusi', () => {
        renderTable([
            trade({ id: 1, meta: { exit_hold: { reason: 'custom_reason', p_lose: 0.1 } } }),
            trade({ id: 2, status: 'won', settled_at: '2026-09-10T12:00:00Z', meta: { exit_hold: { reason: 'wide_margin', p_lose: 0.004 } } }),
        ]);
        const holds = screen.getAllByTestId('trade-hold');
        expect(holds).toHaveLength(1);
        expect(holds[0]).toHaveTextContent('In attesa: custom_reason, P(perdita) 10,0%');
    });

    it('uscita registrata: badge esito accanto allo stato', () => {
        renderTable([trade({ status: 'hedged', pnl: 0.8, meta: { kind: 'combo', exit_kind: 'profit', exit_reason: 'take profit 80%' } })]);
        expect(screen.getByTestId('exit-badge')).toHaveTextContent('Uscita: profitto');
        expect(screen.getByTestId('trade-kind')).toHaveTextContent('COMBINAZIONE');
    });

    it('coppia lay + back di copertura: sub-riga attaccata, CHIUSO IN GREEN-UP, P&L bloccato, tooltip', () => {
        renderTable([
            trade({
                id: 70, strategy: 'esatto', side: 'lay', price: 55, size: 2.16, liability: 116.64, status: 'hedged', pnl: -22.1,
                meta: { locked_pnl: -22.1, exit_kind: 'greenup', exit_reason: "gol al 29': 1-2 raggiungibile" },
            }),
            trade({ id: 71, strategy: 'esatto', side: 'back', price: 4.9, size: 24.24, liability: 24.24, status: 'open', closes_trade_id: 70, meta: { exit_kind: 'greenup' } }),
        ]);
        const rows = screen.getAllByTestId('safe-trade-row');
        expect(rows).toHaveLength(1);
        expect(within(rows[0]).getByTestId('safe-side')).toHaveTextContent('LAY');
        expect(within(rows[0]).getByTestId('safe-status')).toHaveTextContent('CHIUSO IN GREEN-UP');
        expect(within(rows[0]).getByTestId('safe-status').title).toMatch(/il lay a 55,00 è stato coperto con un back a 4,90/);
        expect(within(rows[0]).getByTestId('safe-exit-reason')).toHaveTextContent("gol al 29': 1-2 raggiungibile");
        expect(within(rows[0]).getByTestId('safe-locked-pnl')).toHaveTextContent('−22,10 € bloccato');
        const sub = screen.getByTestId('safe-closing-row');
        expect(sub).toHaveAttribute('data-closes', '70');
        expect(sub).toHaveTextContent('↳ Green-up di #70 · BACK 24,24 € @4,90');
        expect(within(sub).getByText(/chiude #70/)).toBeInTheDocument();
        expect(screen.queryByTestId('cashout-trigger')).toBeNull();
    });

    it('chiusura orfana (apertura non in lista): resta in coda con "chiude #"', () => {
        renderTable([trade({ id: 71, side: 'back', price: 4.9, size: 24.24, status: 'open', closes_trade_id: 70 })]);
        expect(screen.getAllByTestId('safe-trade-row')).toHaveLength(1);
        expect(screen.queryByTestId('safe-closing-row')).toBeNull();
        expect(screen.getByText('chiude #70')).toBeInTheDocument();
    });

    it('pctIt formatta con la virgola', () => {
        expect(pctIt(0.004)).toBe('0,4%');
        expect(pctIt(null)).toBe('—');
    });
});
