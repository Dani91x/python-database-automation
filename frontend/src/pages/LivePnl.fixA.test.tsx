// ============================================================================
// FIX-A (26/09) — /live-pnl: paper e live MAI mischiati (E2E fase 3, U0275/U0281).
// Posizioni con le righe VERE di betfair_live_positions (14265 live, 14291 e
// 14294 paper, lette in sola lettura il 26/09) e righe tennis paper.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/lib/liveOrders', () => ({
    fetchLiveSettled: vi.fn(),
    fetchLiveRiskState: vi.fn(),
    subscribeLiveRiskState: vi.fn(() => () => {}),
    fetchLivePositionsAll: vi.fn(),
}));
vi.mock('@/lib/tennis', () => ({ fetchTennisPositionsAll: vi.fn() }));

import LivePnl from './LivePnl';
import { fetchLiveSettled, fetchLiveRiskState, fetchLivePositionsAll } from '@/lib/liveOrders';
import { fetchTennisPositionsAll } from '@/lib/tennis';

const pos = (id: number, mode: string, event_id: string, market_id: string, expo: number) => ({
    id, mode, event_id, market_id, selection_id: 5851482, handicap: 0,
    matched_if_win: -expo, matched_if_lose: 1, worst_if_win: -expo, worst_if_lose: 1,
    selection_exposure: expo, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
    net_position: -1, updated_at: '2026-09-26T15:28:03.542233+00:00',
});
const POS = [
    pos(14265, 'live', '35797769', '1.259819675', 4.4),
    pos(14291, 'paper', '36091663', '1.262661065', 47),
    pos(14294, 'paper', '36091656', '1.262661305', 78),
];
const TENNIS = [pos(501, 'paper', 'T-paper', '1.3', 12)];
const SETTLED = [
    { id: 18, mode: 'live', event_id: 'ev-l', market_id: '1.9', market_name: null, profit: 0.3, orders: 1,
      source: 'cleared', settled_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    { id: 19, mode: 'paper', event_id: 'ev-p', market_id: '1.8', market_name: null, profit: -5, orders: 1,
      source: 'simulated', settled_at: new Date().toISOString(), updated_at: new Date().toISOString() },
];

function renderPage() {
    return render(<HelmetProvider><MemoryRouter><LivePnl /></MemoryRouter></HelmetProvider>);
}

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchLiveSettled).mockResolvedValue(SETTLED as never);
    vi.mocked(fetchLiveRiskState).mockResolvedValue(null as never);
    vi.mocked(fetchLivePositionsAll).mockResolvedValue(POS as never);
    vi.mocked(fetchTennisPositionsAll).mockResolvedValue(TENNIS as never);
});

describe('FIX-A — Live P&L: una modalità alla volta, in ogni sezione', () => {
    it('non esiste più «tutte»: si parte da LIVE (runner senza stato) e si passa a PAPER', async () => {
        renderPage();
        const select = await screen.findByRole('combobox');
        expect(within(select).queryByRole('option', { name: 'tutte' })).toBeNull();
        expect(select).toHaveValue('live');
    });

    it('LIVE: solo le posizioni live, il tennis paper NON compare, realizzato solo live', async () => {
        renderPage();
        expect(await screen.findByTestId('livepnl-posizioni')).toHaveTextContent('1 posizioni aperte · rischio €4.40 (live)');
        expect(await screen.findByText('Nessuna posizione tennis aperta.')).toBeInTheDocument();
        expect(screen.queryByText('T-paper')).toBeNull();
        expect((await screen.findAllByText('+€0.30')).length).toBeGreaterThan(0);
        expect(screen.queryByText('−€5.00')).toBeNull();
    });

    it('PAPER: solo le posizioni paper (47+78), il tennis paper sì, niente della riga live', async () => {
        renderPage();
        await userEvent.selectOptions(await screen.findByRole('combobox'), 'paper');
        expect(await screen.findByTestId('livepnl-posizioni')).toHaveTextContent('2 posizioni aperte · rischio €125.00 (paper)');
        expect(await screen.findByText('T-paper')).toBeInTheDocument();
        expect(screen.queryByText('+€0.30')).toBeNull();
    });
});
