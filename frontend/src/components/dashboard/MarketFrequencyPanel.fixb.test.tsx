// FIX-B (26/09/2026) KO3, referto fase 3 U0043: su lega 667 get_league_seasons andava in
// timeout e il menu Stagioni delle Frequenze restava VUOTO senza dirlo.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';

vi.mock('@/lib/marketFrequency', async (orig) => ({
    ...(await orig<typeof import('@/lib/marketFrequency')>()),
    fetchMarketFrequency: vi.fn(),
    fetchLeagueSeasons: vi.fn(),
}));

import { fetchMarketFrequency, fetchLeagueSeasons } from '@/lib/marketFrequency';
import { MarketFrequencyPanel } from './MarketFrequencyPanel';

const TIMEOUT = 'canceling statement due to statement timeout';

beforeEach(() => {
    vi.mocked(fetchMarketFrequency).mockReset();
    vi.mocked(fetchLeagueSeasons).mockReset();
});

describe('MarketFrequencyPanel - stagioni non caricate', () => {
    it('timeout di get_league_seasons: avviso "Stagioni non caricate" in modalita\' Stagioni', async () => {
        vi.mocked(fetchLeagueSeasons).mockRejectedValue(new Error(TIMEOUT));
        vi.mocked(fetchMarketFrequency).mockRejectedValue(new Error(TIMEOUT));
        const s = render(<MarketFrequencyPanel leagueId={667} leagueName="Friendlies Clubs" />);
        fireEvent.click(s.getByRole('button', { name: /Frequenze Mercati/ }));
        await waitFor(() => expect(fetchLeagueSeasons).toHaveBeenCalledWith(667));
        fireEvent.click(s.getByRole('button', { name: 'Stagioni' }));
        await waitFor(() => expect(s.getByTestId('freq-stagioni-errore')).toBeTruthy());
        expect(s.getByTestId('freq-stagioni-errore').dataset.tipo).toBe('timeout');
    });

    it('timeout della serie: messaggio di timeout (non "Errore: canceling statement...")', async () => {
        vi.mocked(fetchLeagueSeasons).mockResolvedValue([{ season_year: 2026, n_settled: 164, ht_coverage_pct: 87.7 }]);
        vi.mocked(fetchMarketFrequency).mockRejectedValue(new Error(TIMEOUT));
        const s = render(<MarketFrequencyPanel leagueId={667} leagueName="Friendlies Clubs" />);
        fireEvent.click(s.getByRole('button', { name: /Frequenze Mercati/ }));
        await waitFor(() => expect(s.getByTestId('freq-errore')).toBeTruthy());
        expect(s.getByTestId('freq-errore').textContent).toMatch(/non ha risposto in tempo/);
    });
});
