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
}));

import { LiveControlsPanel } from './LiveControlsPanel';
import { getLiveSettings, setKillSwitch, setLiveSettings, fetchLiveAudit } from '@/lib/liveOrders';

const mGet = vi.mocked(getLiveSettings);
const mKill = vi.mocked(setKillSwitch);
const mSet = vi.mocked(setLiveSettings);
const mAudit = vi.mocked(fetchLiveAudit);

const settings = (over: Partial<LiveSettings> = {}): LiveSettings => ({
    id: 1,
    kill_switch: false,
    max_exposure_per_selection: null,
    max_orders_per_min: null,
    order_poll_sec: null,
    risk_poll_sec: null,
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
