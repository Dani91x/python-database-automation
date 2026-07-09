// Test COMPONENTE per LiveControlsPanel (jsdom + React Testing Library).
// Tutte le RPC (@/lib/liveOrders) sono mockate: nessuna rete. Verifichiamo che il
// kill-switch rifletta getLiveSettings, che il toggle chiami setKillSwitch e che le
// righe di audit provengano da fetchLiveAudit.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { LiveSettings, LiveAuditRow } from '@/lib/liveOrders';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/liveOrders', () => ({
    getLiveSettings: vi.fn(),
    setKillSwitch: vi.fn(),
    setLiveSettings: vi.fn(),
    fetchLiveAudit: vi.fn(),
    // E34: stato rischio giornaliero (top strip del pannello)
    fetchLiveRiskState: vi.fn(() => Promise.resolve(null)),
    subscribeLiveRiskState: vi.fn(() => () => {}),
}));

import { toast } from 'sonner';
import { LiveControlsPanel } from './LiveControlsPanel';
import {
    getLiveSettings, setKillSwitch, setLiveSettings, fetchLiveAudit, fetchLiveRiskState,
    type LiveRiskState,
} from '@/lib/liveOrders';

const mGet = vi.mocked(getLiveSettings);
const mKill = vi.mocked(setKillSwitch);
const mSet = vi.mocked(setLiveSettings);
const mAudit = vi.mocked(fetchLiveAudit);
const mRisk = vi.mocked(fetchLiveRiskState);

const settings = (over: Partial<LiveSettings> = {}): LiveSettings => ({
    id: 1,
    kill_switch: false,
    max_exposure_per_selection: null,
    max_orders_per_min: null,
    order_poll_sec: null,
    risk_poll_sec: null,
    daily_loss_limit: null,
    max_exposure_per_event: null,
    max_exposure_per_league: null,
    updated_at: '2026-07-01T10:00:00Z',
    ...over,
});

const auditRow = (over: Partial<LiveAuditRow> = {}): LiveAuditRow => ({
    id: 1,
    ts: '2026-07-01T10:00:00Z',
    mode: 'live',
    action: 'place',
    market_id: '1.234',
    selection_id: 47,
    side: 'back',
    price: 2.0,
    size: 5,
    status: 'EXECUTION_COMPLETE',
    error: null,
    request_id: 10,
    detail: null,
    ...over,
});

beforeEach(() => {
    vi.clearAllMocks();
    mGet.mockResolvedValue(settings());
    mKill.mockResolvedValue(settings({ kill_switch: true }));
    mSet.mockResolvedValue(settings());
    mAudit.mockResolvedValue([]);
});

describe('LiveControlsPanel', () => {
    it('il kill-switch riflette lo stato OFF da getLiveSettings', async () => {
        render(<LiveControlsPanel pollMs={0} />);
        expect(await screen.findByText(/runner operativo/)).toBeInTheDocument();
    });

    it('il kill-switch riflette lo stato ATTIVO da getLiveSettings', async () => {
        mGet.mockResolvedValue(settings({ kill_switch: true }));
        render(<LiveControlsPanel pollMs={0} />);
        expect(await screen.findByText(/KILL-SWITCH ATTIVO/)).toBeInTheDocument();
    });

    it('il toggle chiama setKillSwitch(true)', async () => {
        const user = userEvent.setup();
        render(<LiveControlsPanel pollMs={0} />);
        await screen.findByText(/runner operativo/);
        await user.click(screen.getByRole('button', { name: /Kill-switch/ }));
        await waitFor(() => expect(mKill).toHaveBeenCalledWith(true));
    });

    it('rende le righe di audit da fetchLiveAudit', async () => {
        mAudit.mockResolvedValue([
            auditRow(),
            auditRow({ id: 2, action: 'cancel', market_id: '1.999', selection_id: 50 }),
        ]);
        render(<LiveControlsPanel pollMs={0} />);
        expect(await screen.findByText('place')).toBeInTheDocument();
        expect(screen.getByText('cancel')).toBeInTheDocument();
        expect(screen.getByText(/1\.234 · 47/)).toBeInTheDocument();
        expect(screen.getByText(/Registro eventi \(2\)/)).toBeInTheDocument();
    });
});

// ===========================================================================
// E34/E35 — validazione limiti (barriera client-side) + strip stato rischio
// ===========================================================================
describe('LiveControlsPanel — limiti E34/E35', () => {
    const riskState = (over: Partial<LiveRiskState> = {}): LiveRiskState => ({
        id: 1, mode: 'paper', day: '2026-07-09', realized: -12.5, open_mtm: -3.0,
        total: -15.5, limit_value: 50, stop_fired: false,
        detail: { reason: 'within_limit', degraded: false, kill_switch: false },
        updated_at: '2026-07-09T10:00:00Z',
        ...over,
    });

    it('stop giornaliero ≤ 0 → toast error e NESSUN salvataggio', async () => {
        const user = userEvent.setup();
        render(<LiveControlsPanel pollMs={0} />);
        await screen.findByText(/runner operativo/);
        const input = screen.getByTitle(/E34/);
        await user.clear(input);
        await user.type(input, '-5');
        await user.click(screen.getByRole('button', { name: /Salva/ }));
        await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled());
        expect(mSet).not.toHaveBeenCalled();
    });

    it('limite evento 0 → rifiutato; campo vuoto (disattivazione) → salvato con null', async () => {
        const user = userEvent.setup();
        render(<LiveControlsPanel pollMs={0} />);
        await screen.findByText(/runner operativo/);
        const evInput = screen.getByTitle(/E35: esposizione worst-case aggregata sui mercati di UN evento/);
        await user.clear(evInput);
        await user.type(evInput, '0');
        await user.click(screen.getByRole('button', { name: /Salva/ }));
        await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled());
        expect(mSet).not.toHaveBeenCalled();
        // campo svuotato = limite spento → il salvataggio passa con null
        await user.clear(evInput);
        await user.click(screen.getByRole('button', { name: /Salva/ }));
        await waitFor(() => expect(mSet).toHaveBeenCalled());
        expect(mSet.mock.calls[0][0]).toMatchObject({ max_exposure_per_event: null });
    });

    it('limiti validi → salvati nel patch', async () => {
        const user = userEvent.setup();
        render(<LiveControlsPanel pollMs={0} />);
        await screen.findByText(/runner operativo/);
        await user.type(screen.getByTitle(/E34/), '50');
        await user.type(screen.getByTitle(/UN evento/), '100');
        await user.type(screen.getByTitle(/stesso campionato/), '200');
        await user.click(screen.getByRole('button', { name: /Salva/ }));
        await waitFor(() => expect(mSet).toHaveBeenCalled());
        expect(mSet.mock.calls[0][0]).toMatchObject({
            daily_loss_limit: 50, max_exposure_per_event: 100, max_exposure_per_league: 200,
        });
    });

    it('strip rischio: stato entro soglia (nessun badge SCATTATO)', async () => {
        mRisk.mockResolvedValue(riskState());
        render(<LiveControlsPanel pollMs={0} />);
        expect(await screen.findByText(/P&L giornata \(2026-07-09\)/)).toBeInTheDocument();
        expect(screen.queryByText(/STOP GIORNALIERO SCATTATO/)).not.toBeInTheDocument();
        expect(screen.getByText(/stop a −/)).toBeInTheDocument();
    });

    it('strip rischio: stop SCATTATO → badge rosso esplicito', async () => {
        mRisk.mockResolvedValue(riskState({ total: -60, stop_fired: true }));
        render(<LiveControlsPanel pollMs={0} />);
        expect(await screen.findByText(/STOP GIORNALIERO SCATTATO/)).toBeInTheDocument();
    });

    it('strip rischio: limite spento dichiarato', async () => {
        mRisk.mockResolvedValue(riskState({ limit_value: null }));
        render(<LiveControlsPanel pollMs={0} />);
        expect(await screen.findByText(/stop giornaliero spento/)).toBeInTheDocument();
    });
});
