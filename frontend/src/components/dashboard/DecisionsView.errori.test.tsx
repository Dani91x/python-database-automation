// FIX-B (26/09/2026) KO2: tab Decisioni, timeout != "Nessuna decisione".
// Referto fase 3 U0116-U0118. Finti con chiavi/tipi delle RPC get_decisions /
// get_decisions_filters (migrations/analytics_rpc_veloci_2026-09-26.sql).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import type { DecisionsFilters, DecisionsResult } from '@/lib/analytics';

vi.mock('@/lib/analytics', async (orig) => ({
    ...(await orig<typeof import('@/lib/analytics')>()),
    fetchDecisions: vi.fn(),
    fetchDecisionsFilters: vi.fn(),
}));

import { fetchDecisions, fetchDecisionsFilters } from '@/lib/analytics';
import DecisionsView from './DecisionsView';

const TIMEOUT = 'canceling statement due to statement timeout';
const filtri: DecisionsFilters = {
    logics: [{ value: 'google_sheets', n: 88966 }], statuses: [{ value: 'PLACED', n: 5000 }],
    engines: [{ value: 'poisson', n: 60000 }], markets: [{ value: '1x2', n: 20000 }],
    rejects: [{ value: 'edge', n: 30000 }], total: 88966,
};
const vuoto: DecisionsResult = { group_by: 'logic', groups: [] };

beforeEach(() => {
    vi.mocked(fetchDecisions).mockReset();
    vi.mocked(fetchDecisionsFilters).mockReset();
});

describe('DecisionsView - errore non e\' "nessun dato"', () => {
    it('timeout di get_decisions: messaggio di timeout, NESSUN "Nessuna decisione"', async () => {
        vi.mocked(fetchDecisionsFilters).mockResolvedValue(filtri);
        vi.mocked(fetchDecisions).mockRejectedValue(new Error(TIMEOUT));
        const s = render(<DecisionsView />);
        await waitFor(() => expect(s.getByTestId('decisioni-errore')).toBeTruthy(), { timeout: 3000 });
        expect(s.getByTestId('decisioni-errore').dataset.tipo).toBe('timeout');
        expect(s.queryByText(/Nessuna decisione per questi filtri/)).toBeNull();
    });

    it('timeout dei filtri: avviso dedicato', async () => {
        vi.mocked(fetchDecisionsFilters).mockRejectedValue(new Error(TIMEOUT));
        vi.mocked(fetchDecisions).mockResolvedValue(vuoto);
        const s = render(<DecisionsView />);
        await waitFor(() => expect(s.getByTestId('decisioni-filtri-errore')).toBeTruthy(), { timeout: 3000 });
        expect(s.getByTestId('decisioni-filtri-errore').textContent).toMatch(/menu dei filtri/i);
    });

    it('risposta vuota VERA: "Nessuna decisione" e nessun errore', async () => {
        vi.mocked(fetchDecisionsFilters).mockResolvedValue(filtri);
        vi.mocked(fetchDecisions).mockResolvedValue(vuoto);
        const s = render(<DecisionsView />);
        await waitFor(() => expect(s.getByText(/Nessuna decisione per questi filtri/)).toBeTruthy(), { timeout: 3000 });
        expect(s.queryByTestId('decisioni-errore')).toBeNull();
    });
});
