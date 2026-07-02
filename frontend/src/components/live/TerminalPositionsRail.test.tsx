// Test COMPONENTE per TerminalPositionsRail (colonna sinistra del trading terminal).
// @/lib/liveOrders mockato (nessuna rete). Copre: rendering posizioni con P&L dal
// mirror (mai ricalcolato), filtro per mode, ordini unmatched con cancel MEDIATO
// dalla coda (payload esatto), matched in sola lettura, banner di poll fallito (M3).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/liveOrders', () => ({
    fetchLiveOrders: vi.fn(),
    fetchLivePositions: vi.fn(),
    sendLiveOrderCommand: vi.fn(),
}));

import {
    fetchLiveOrders, fetchLivePositions, sendLiveOrderCommand,
} from '@/lib/liveOrders';
import { TerminalPositionsRail } from './TerminalPositionsRail';

const SELS = [
    { selection_id: 1, name: 'Milan' },
    { selection_id: 2, name: 'Inter' },
];

const POS = (over: Record<string, unknown> = {}) => ({
    id: 1, mode: 'paper', event_id: 'E1', market_id: '1.1', selection_id: 1, handicap: 0,
    matched_if_win: 12.5, matched_if_lose: -5.0, worst_if_win: 12.5, worst_if_lose: -5.0,
    selection_exposure: 5.0, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
    net_position: 5.0, updated_at: null, ...over,
});

const ORD = (over: Record<string, unknown> = {}) => ({
    id: 10, bet_id: 'B10', client_order_ref: 'awlq10', request_id: 10, mode: 'paper',
    event_id: 'E1', market_id: '1.1', selection_id: 2, handicap: 0, side: 'back',
    order_type: 'LIMIT', price: 2.5, size: 5, size_matched: 0, size_remaining: 5,
    size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 0,
    status: 'EXECUTABLE', persistence: 'LAPSE', placed_at: null, matched_at: null,
    updated_at: null, ...over,
});

beforeEach(() => {
    vi.clearAllMocks();
    (fetchLiveOrders as any).mockResolvedValue([]);
    (fetchLivePositions as any).mockResolvedValue([]);
    (sendLiveOrderCommand as any).mockResolvedValue({ ok: true, action: 'cancel', mode: 'paper' });
});

describe('TerminalPositionsRail', () => {
    it('mostra le posizioni con P&L vince/perde dal mirror', async () => {
        (fetchLivePositions as any).mockResolvedValue([POS()]);
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={SELS} />);
        expect(await screen.findByText('Milan')).toBeInTheDocument();
        expect(screen.getByText('+12.50')).toBeInTheDocument();
        expect(screen.getByText('-5.00')).toBeInTheDocument();
    });

    it('filtra i dati sul mode corrente (una riga live NON compare in paper)', async () => {
        (fetchLivePositions as any).mockResolvedValue([POS({ mode: 'live' })]);
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={SELS} />);
        await waitFor(() => expect(fetchLivePositions).toHaveBeenCalled());
        expect(screen.queryByText('Milan')).not.toBeInTheDocument();
        expect(screen.getByText(/nessuna posizione/i)).toBeInTheDocument();
    });

    it('cancel di un ordine unmatched invia il comando ESATTO alla coda', async () => {
        (fetchLiveOrders as any).mockResolvedValue([ORD()]);
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={SELS} />);
        const btn = await screen.findByRole('button', { name: /annulla ordine back su inter/i });
        await userEvent.click(btn);
        await waitFor(() => expect(sendLiveOrderCommand).toHaveBeenCalledWith({
            action: 'cancel', mode: 'paper', market_id: '1.1', bet_id: 'B10',
        }));
    });

    it('un ordine matched è in sola lettura (nessun bottone cancel)', async () => {
        (fetchLiveOrders as any).mockResolvedValue([
            ORD({ id: 11, bet_id: 'B11', size_matched: 5, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
        ]);
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={SELS} />);
        expect(await screen.findByText(/✓ 5.00@/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /annulla ordine/i })).not.toBeInTheDocument();
    });

    it('poll fallito → banner "dati NON aggiornati" (mai numeri stantii come freschi)', async () => {
        (fetchLivePositions as any).mockRejectedValue(new Error('rete KO'));
        render(<TerminalPositionsRail marketId="1.1" mode="paper" selections={SELS} />);
        expect(await screen.findByText(/dati non aggiornati/i)).toBeInTheDocument();
    });
});
