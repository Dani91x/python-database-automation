// ============================================================================
// FIX-A (26/09) — pagina Safe: «P&L totale · PAPER» è SOLO paper (KO 1 della
// fase 3 E2E: −45,25 € = −47,83 paper + 2,58 live sotto l'etichetta PAPER).
//
// Gli aggregati sono le risposte VERE di `safe_aggregates_sql` del 26/09 (sola
// lettura): tutte le modalità −40,47 = paper −43,05 + live 2,58.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import { DEFAULT_PARAMS } from '@/lib/safeStrategy';

vi.setConfig({ testTimeout: 20_000 });

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

vi.mock('@/lib/safeBot', async (orig) => {
    const actual = await orig<typeof import('@/lib/safeBot')>();
    return {
        ...actual,
        fetchSafeState: vi.fn(),
        fetchSafeTrades: vi.fn(async () => []),
        fetchSafeRequests: vi.fn(async () => []),
        fetchSafeActivity: vi.fn(async () => []),
        fetchOpportunities: vi.fn(async () => []),
        subscribeSafeBot: vi.fn(() => () => {}),
        subscribeOpportunities: vi.fn(() => () => {}),
        requestSafe: vi.fn(async () => 1),
        activateSafe: vi.fn(async () => ({})),
        stopSafe: vi.fn(),
        updateSafeParams: vi.fn(),
        fetchRunnerState: vi.fn(async () => ({ ts: null, mode: null, ageS: null, up: false, streaming: null })),
    };
});
vi.mock('@/lib/safeStrategyScan', async (orig) => {
    const actual = await orig<typeof import('@/lib/safeStrategyScan')>();
    return { ...actual, fetchScanStatus: vi.fn(async () => null) };
});
vi.mock('@/components/safestrategy/SafeStrategyProvider', () => ({
    useSafeStrategy: () => ({
        football: [], tennis: [], signals: [], scanStatus: null,
        params: DEFAULT_PARAMS, saveParams: vi.fn(), resetParams: vi.fn(),
    }),
}));

import SafeStrategy from './SafeStrategy';
import { fetchSafeState } from '@/lib/safeBot';

const mState = vi.mocked(fetchSafeState);

const A_ALL = {
    won: 130, lost: 51, mode: null, won_today: 7, day_trades: 11, legs_today: 11, lost_today: 1,
    open_count: 3, events_today: 11, day_liability: 490, operating_day: '2026-09-26',
    open_liability: 104, realized_today: 4.78, realized_total: -40.47, reconciling_count: 0,
    day_liability_model: 0, realized_live_total: 2.58, realized_paper_total: -43.05,
    reconciling_liability: 0,
};
const A_PAPER = { ...A_ALL, won: 112, mode: 'paper', realized_total: -43.05 };
const A_LIVE = {
    ...A_ALL, won: 18, lost: 0, mode: 'live', won_today: 0, day_trades: 0, legs_today: 0,
    lost_today: 0, open_count: 0, events_today: 0, day_liability: 0, open_liability: 0,
    realized_today: 0, realized_total: 2.58,
};

function control(mode: 'paper' | 'live') {
    return {
        id: 1, status: 'running', mode,
        params: { stake: { laySize: 2, backSize: 2 }, commission_pct: 5, variants: ['base'] },
        stats: { params_effective: { commission_pct: 5, min_stake: 2 } },
        error: null, started_at: null, stopped_at: null, heartbeat_at: new Date().toISOString(),
    };
}

function stato(mode: 'paper' | 'live', perModo: boolean) {
    return {
        control: control(mode) as never, trades: [] as never, aggregates: A_ALL as never,
        activity: [] as never, params_effective: control(mode).stats.params_effective as never,
        operating_day: '2026-09-26',
        aggregates_by_mode: perModo ? { paper: A_PAPER as never, live: A_LIVE as never } : null,
    };
}

function renderPage() {
    return render(<HelmetProvider><MemoryRouter><SafeStrategy /></MemoryRouter></HelmetProvider>);
}

beforeEach(() => { vi.clearAllMocks(); });

describe('FIX-A — Safe: i numeri di una modalità, mai la somma', () => {
    it('la pagina chiede gli aggregati PER MODALITÀ', async () => {
        mState.mockResolvedValue(stato('paper', true));
        renderPage();
        await screen.findByTestId('safe-kpi-pnl-total');
        expect(mState).toHaveBeenCalledWith({ perModalita: true });
    });

    it('PAPER: «P&L totale · PAPER» = −43,05 (non −40,47); il live a parte, con la sua etichetta', async () => {
        mState.mockResolvedValue(stato('paper', true));
        renderPage();
        const tot = await screen.findByTestId('safe-kpi-pnl-total');
        expect(tot).toHaveTextContent('PAPER');
        expect(tot).toHaveTextContent('−43,05');
        expect(tot).not.toHaveTextContent('40,47');
        expect(screen.getByTestId('safe-kpi-pnl-today')).toHaveTextContent('+4,78');
        const altra = screen.getByTestId('safe-altra-modalita');
        expect(altra).toHaveAttribute('data-mode', 'live');
        expect(altra).toHaveTextContent('LIVE');
        expect(screen.getByTestId('safe-altra-pnl-totale')).toHaveTextContent('+2,58');
    });

    it('LIVE: il totale LIVE è +2,58 e il paper sta nella riga a parte', async () => {
        mState.mockResolvedValue(stato('live', true));
        renderPage();
        const tot = await screen.findByTestId('safe-kpi-pnl-total');
        expect(tot).toHaveTextContent('LIVE');
        expect(tot).toHaveTextContent('+2,58');
        expect(screen.getByTestId('safe-kpi-liability')).toHaveTextContent('0,00');
        expect(screen.getByTestId('safe-altra-modalita')).toHaveAttribute('data-mode', 'paper');
        expect(screen.getByTestId('safe-altra-pnl-totale')).toHaveTextContent('−43,05');
    });

    it('senza gli aggregati per modalità: il totale separato dalla RPC, MAI la somma', async () => {
        mState.mockResolvedValue(stato('paper', false));
        renderPage();
        const tot = await screen.findByTestId('safe-kpi-pnl-total');
        expect(tot).toHaveTextContent('−43,05');
        expect(tot).not.toHaveTextContent('40,47');
        // oggi e liability non sono separabili da quegli aggregati: «—», non la somma
        expect(screen.getByTestId('safe-kpi-pnl-today')).not.toHaveTextContent('4,78');
    });

    it('nessuna attività nell’altra modalità: nessuna riga in più', async () => {
        mState.mockResolvedValue({
            ...stato('paper', true),
            aggregates_by_mode: { paper: A_PAPER as never, live: { ...A_LIVE, realized_total: 0 } as never },
        });
        renderPage();
        await screen.findByTestId('safe-kpi-pnl-total');
        expect(screen.queryByTestId('safe-altra-modalita')).toBeNull();
    });
});
