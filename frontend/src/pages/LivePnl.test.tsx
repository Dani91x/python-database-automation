// Test COMPONENTE leggero per LivePnl (D33). Moduli data mockati; verifica:
// KPI "P&L realizzato" = somma dei settled, badge SCATTATO quando stop_fired.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/lib/liveOrders', () => ({
    fetchLiveSettled: vi.fn(),
    fetchLiveRiskState: vi.fn(),
    subscribeLiveRiskState: vi.fn(() => () => {}),
    fetchLivePositionsAll: vi.fn(),
}));
vi.mock('@/lib/tennis', () => ({
    fetchTennisPositionsAll: vi.fn(),
}));

import LivePnl from './LivePnl';
import {
    fetchLiveSettled, fetchLiveRiskState, fetchLivePositionsAll,
} from '@/lib/liveOrders';
import { fetchTennisPositionsAll } from '@/lib/tennis';

const mSettled = vi.mocked(fetchLiveSettled);
const mRisk = vi.mocked(fetchLiveRiskState);
const mPositions = vi.mocked(fetchLivePositionsAll);
const mTPositions = vi.mocked(fetchTennisPositionsAll);

// due mercati regolati OGGI: +10 e −4 → realizzato +€6.00
function todayIso(hour: number): string {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate(), hour, 30).toISOString();
}
const SETTLED = [
    {
        id: 1, mode: 'paper', event_id: 'ev1', market_id: '1.1', market_name: 'Match Odds',
        profit: 10, orders: 2, source: 'simulated', settled_at: todayIso(10), updated_at: todayIso(10),
    },
    {
        id: 2, mode: 'paper', event_id: 'ev1', market_id: '1.2', market_name: 'Over/Under 2.5',
        profit: -4, orders: 1, source: 'simulated', settled_at: todayIso(11), updated_at: todayIso(11),
    },
];

const RISK = {
    id: 1, mode: 'paper', day: '2026-07-08', realized: 6, open_mtm: 2.5, total: 8.5,
    limit_value: 50, stop_fired: true, detail: null, updated_at: new Date().toISOString(),
};

beforeEach(() => {
    vi.clearAllMocks();
    mSettled.mockResolvedValue(SETTLED as never);
    mRisk.mockResolvedValue(RISK as never);
    mPositions.mockResolvedValue([] as never);
    mTPositions.mockResolvedValue([] as never);
});

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <LivePnl />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

describe('LivePnl', () => {
    it('KPI "P&L realizzato" mostra la somma corretta dei settled (+€6.00)', async () => {
        renderPage();
        expect(await screen.findByText('P&L realizzato')).toBeInTheDocument();
        // 10 − 4 = +6.00 (può comparire anche nell'aggregato per evento: basta ≥1)
        const sums = await screen.findAllByText('+€6.00');
        expect(sums.length).toBeGreaterThanOrEqual(1);
        // le righe per-mercato ci sono, con badge fonte 'simulato'
        expect(screen.getByText('Match Odds')).toBeInTheDocument();
        expect(screen.getAllByText('simulato').length).toBe(2);
    });

    it('badge ROSSO "SCATTATO" quando stop_fired è true', async () => {
        renderPage();
        expect(await screen.findByText('SCATTATO')).toBeInTheDocument();
        // e il limite dello stop è mostrato
        expect(screen.getByText('€50.00')).toBeInTheDocument();
    });

    it('sezione tennis separata con nota onesta sul settled non storicizzato', async () => {
        renderPage();
        expect(await screen.findByText(/settled tennis non è ancora storicizzato/i)).toBeInTheDocument();
        expect(await screen.findByText(/nessuna posizione tennis aperta/i)).toBeInTheDocument();
    });
});
