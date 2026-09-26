// FIX-B (26/09/2026) KO3 + KO11 sullo Studio Ritardi:
//  - timeout della RPC = messaggio di timeout (non "Errore: canceling statement...")
//  - stagioni non caricate = avviso, non menu vuoto in silenzio (U0043)
//  - date del periodo in gg/mm/aaaa di Roma, non ISO UTC grezze (U0056)
// Il finto DelayResult ha le chiavi/tipi dell'output jsonb di get_market_delays
// (migrations/market_delays_ht_2026-09-25.sql, righe della jsonb_build_object finale).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import type { DelayResult } from '@/lib/marketDelays';

vi.mock('@/lib/marketDelays', async (orig) => ({
    ...(await orig<typeof import('@/lib/marketDelays')>()),
    fetchMarketDelays: vi.fn(),
    fetchLeagueSeasons: vi.fn(),
}));

import { fetchMarketDelays, fetchLeagueSeasons } from '@/lib/marketDelays';
import { RitardiPanel } from './RitardiPanel';
import { TooltipProvider } from '@/components/ui/tooltip';

const TIMEOUT = 'canceling statement due to statement timeout';

function risultato(): DelayResult {
    return {
        meta: {
            league_id: 358, market: 'sge', target: '3', mode: 'all', season_year: null, n_requested: null,
            n_scope: 1240, n_effective: 1240, uses_ht: false, ht_coverage_pct: 99.1, ht_missing_rule: 'escluse',
            n_ht_missing: 0, date_from: '2019-02-22T19:45:00+00:00', date_to: '2026-09-25T20:00:00+00:00',
        },
        stats: {
            n_occ: 268, frequency: 0.216129, media_storica: 4.626866, quota_oggettiva: 4.626866, ritardo_attuale: 1,
            record: 35, media_ritardi: 4.9372, sotto_media: 188, sopra_media: 80, sotto_media_pct: 0.7015,
            sopra_media_pct: 0.2985, rit_vs_media: 0.216, storico_cond_su: 2,
        },
        distribuzione_serie: [{ len: 0, occ_suc: 58, cnt_rit: 268 }, { len: 1, occ_suc: 46, cnt_rit: 211 }],
        ultime_10_serie: [1, 4, 0, 7, 2, 3, 1, 0, 5, 2],
        storico_serie: [{ len: 1, count: 10, pct: 0.5 }, { len: 0, count: 10, pct: 0.5 }],
        run_sopra_media: [{ run_len: 1, count: 40, pct: 0.8 }, { run_len: 2, count: 10, pct: 0.2 }],
        ultime_10_strisce_sopra_media: [0, 1, 0, 0, 2, 0, 0, 1, 0, 0],
        series: [
            { idx: 1, fid: 1, date: '2019-02-22T19:45:00+00:00', home: 'A', away: 'B', gc: 1, ga: 2, gcfh: 0, gafh: 1, gcsh: 1, gash: 1, out: 1, rit: 0, suc: 0 },
            { idx: 2, fid: 2, date: '2026-09-25T20:00:00+00:00', home: 'C', away: 'D', gc: 0, ga: 0, gcfh: 0, gafh: 0, gcsh: 0, gash: 0, out: 0, rit: 1, suc: null },
        ],
    };
}

function apri() {
    // TooltipProvider come in App.tsx (il pannello usa i Tooltip di Radix)
    const s = render(<TooltipProvider><RitardiPanel leagueId={358} leagueName="First Division" /></TooltipProvider>);
    fireEvent.click(s.getByRole('button', { name: /Studio Ritardi/ }));
    return s;
}

beforeEach(() => {
    vi.mocked(fetchMarketDelays).mockReset();
    vi.mocked(fetchLeagueSeasons).mockReset();
});

describe('RitardiPanel - FIX-B', () => {
    it('periodo DATI MATCH in gg/mm/aaaa (Roma), mai ISO grezzo', async () => {
        vi.mocked(fetchLeagueSeasons).mockResolvedValue([{ season_year: 2026, n_settled: 164, ht_coverage_pct: 99 }]);
        vi.mocked(fetchMarketDelays).mockResolvedValue(risultato());
        const s = apri();
        await waitFor(() => expect(s.getByTestId('ritardi-periodo')).toBeTruthy());
        expect(s.getByTestId('ritardi-periodo').textContent).toBe('22/02/2019 → 25/09/2026');
        expect(s.container.textContent).not.toContain('2019-02-22T19:45:00');
    });

    it('timeout della RPC: messaggio di timeout dichiarato', async () => {
        vi.mocked(fetchLeagueSeasons).mockResolvedValue([]);
        vi.mocked(fetchMarketDelays).mockRejectedValue(new Error(TIMEOUT));
        const s = apri();
        await waitFor(() => expect(s.getByTestId('ritardi-errore')).toBeTruthy());
        expect(s.getByTestId('ritardi-errore').dataset.tipo).toBe('timeout');
        expect(s.getByTestId('ritardi-errore').textContent).toMatch(/non ha risposto in tempo/);
    });

    it('stagioni non caricate: avviso visibile scegliendo "Stagione" (non un menu vuoto muto)', async () => {
        vi.mocked(fetchLeagueSeasons).mockRejectedValue(new Error(TIMEOUT));
        vi.mocked(fetchMarketDelays).mockResolvedValue(risultato());
        const s = apri();
        await waitFor(() => expect(fetchLeagueSeasons).toHaveBeenCalled());
        fireEvent.click(s.getByRole('button', { name: 'Stagione' }));
        await waitFor(() => expect(s.getByTestId('ritardi-stagioni-errore')).toBeTruthy());
        expect(s.getByTestId('ritardi-stagioni-errore').textContent).toMatch(/Stagioni non caricate/);
    });
});
