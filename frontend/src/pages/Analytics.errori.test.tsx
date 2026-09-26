// FIX-B (26/09/2026) KO2: la pagina Analytics distingue timeout/errore da "nessun dato".
// Referto fase 3 U0112-U0113: get_analytics -> "canceling statement due to statement
// timeout" e sotto "Nessun segnale settlato per questi filtri." (fuorviante).
// I finti hanno le chiavi e i tipi dell'output jsonb delle RPC
// (migrations/analytics_rpc_veloci_2026-09-26.sql: get_analytics, get_analytics_filters).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { AnalyticsFilters, AnalyticsResult } from '@/lib/analytics';

vi.mock('@/lib/analytics', async (orig) => ({
    ...(await orig<typeof import('@/lib/analytics')>()),
    fetchAnalytics: vi.fn(),
    fetchAnalyticsFilters: vi.fn(),
    fetchAnalyticsRows: vi.fn(async () => []),
}));

import { fetchAnalytics, fetchAnalyticsFilters } from '@/lib/analytics';
import Analytics from './Analytics';

const TIMEOUT = 'canceling statement due to statement timeout';

function filtri(over: Partial<AnalyticsFilters> = {}): AnalyticsFilters {
    return {
        engines: [{ value: 'poisson', n: 400000 }, { value: 'api', n: 297726 }],
        markets: [{ value: '1x2', n: 500000 }],
        leagues: [{ id: 39, name: 'Premier League', n: 3000 }],
        seasons: [2026, 2025],
        total_settled: 1217790,
        fonte_dati: 'riepilogo',
        riepilogo_at: '2026-09-26T01:40:00+00:00',
        ...over,
    };
}

function risultato(groups: AnalyticsResult['groups']): AnalyticsResult {
    return { group_by: 'confidence', z: 1.96, groups, fonte_dati: 'riepilogo', riepilogo_at: '2026-09-26T01:40:00+00:00' };
}

function apri() {
    return render(<MemoryRouter><Analytics /></MemoryRouter>);
}

beforeEach(() => {
    vi.mocked(fetchAnalytics).mockReset();
    vi.mocked(fetchAnalyticsFilters).mockReset();
});

describe('Analytics - errore non e\' "nessun dato"', () => {
    it('timeout di get_analytics: messaggio di timeout, NESSUN "Nessun segnale settlato"', async () => {
        vi.mocked(fetchAnalyticsFilters).mockResolvedValue(filtri());
        vi.mocked(fetchAnalytics).mockRejectedValue(new Error(TIMEOUT));
        const s = apri();
        await waitFor(() => expect(s.getByTestId('analytics-errore')).toBeTruthy(), { timeout: 3000 });
        expect(s.getByTestId('analytics-errore').dataset.tipo).toBe('timeout');
        expect(s.getByTestId('analytics-errore').textContent).toMatch(/NON sono vuoti/);
        expect(s.queryByText(/Nessun segnale settlato/)).toBeNull();
    });

    it('timeout dei filtri: avviso dedicato (menu non caricati), non silenzio', async () => {
        vi.mocked(fetchAnalyticsFilters).mockRejectedValue(new Error(TIMEOUT));
        vi.mocked(fetchAnalytics).mockResolvedValue(risultato([]));
        const s = apri();
        await waitFor(() => expect(s.getByTestId('analytics-filtri-errore')).toBeTruthy(), { timeout: 3000 });
        expect(s.getByTestId('analytics-filtri-errore').textContent).toMatch(/menu dei filtri/i);
        expect(s.getByTestId('analytics-filtri-errore').dataset.tipo).toBe('timeout');
    });

    it('risposta vuota VERA: "Nessun segnale settlato" e nessun errore', async () => {
        vi.mocked(fetchAnalyticsFilters).mockResolvedValue(filtri());
        vi.mocked(fetchAnalytics).mockResolvedValue(risultato([]));
        const s = apri();
        await waitFor(() => expect(s.getByText(/Nessun segnale settlato per questi filtri/)).toBeTruthy(), { timeout: 3000 });
        expect(s.queryByTestId('analytics-errore')).toBeNull();
    });

    it('dati dal riepilogo: la pagina dice di quando sono (ora di Roma)', async () => {
        vi.mocked(fetchAnalyticsFilters).mockResolvedValue(filtri());
        vi.mocked(fetchAnalytics).mockResolvedValue(risultato([
            { grp: '60-65%', n: 1000, hits: 610, hit_rate: 0.61, avg_prob: 0.62, wilson_low: 0.58, wilson_high: 0.64, calib_gap: -0.01 },
            { grp: '65-70%', n: 900, hits: 600, hit_rate: 0.6667, avg_prob: 0.67, wilson_low: 0.63, wilson_high: 0.69, calib_gap: -0.0033 },
        ]));
        const s = apri();
        await waitFor(() => expect(s.getByTestId('analytics-eta-riepilogo')).toBeTruthy(), { timeout: 3000 });
        expect(s.getByTestId('analytics-eta-riepilogo').textContent).toContain('26/09/2026, 03:40');
    });
});
