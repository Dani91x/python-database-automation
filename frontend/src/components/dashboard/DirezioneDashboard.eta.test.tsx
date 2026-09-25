// R5 (25/09/2026): la Direzione dichiara eta' della pagella e presenza della quota.
// I finti hanno le STESSE chiavi e gli stessi tipi dell'output jsonb delle RPC
// get_direction (migrations/get_direction_rpc.sql:203-245) e get_direction_eta
// (migrations/get_direction_eta_2026-09-25.sql).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import type { DirMarket, DirezioneData, DirezioneEta } from '@/lib/direzione';

vi.mock('@/lib/direzione', async (orig) => ({
    ...(await orig<typeof import('@/lib/direzione')>()),
    fetchDirezione: vi.fn(),
    fetchDirezioneEta: vi.fn(),
}));
vi.mock('@/lib/betfair', async (orig) => ({
    ...(await orig<typeof import('@/lib/betfair')>()),
    fetchBetfairDirectionOdds: vi.fn(async () => ({})),
}));

import { fetchDirezione, fetchDirezioneEta } from '@/lib/direzione';
import { DirezioneDashboard } from './DirezioneDashboard';

function mercato(over: Partial<DirMarket>): DirMarket {
    return {
        market: '1x2', direction: 'H', calibrated: true, poisson_missing: false,
        affidabilita: 0.55, wilson_low: 0.5, wilson_high: 0.6, n: 400, base: 0.45, lift: 0.1,
        odds: null, scope: 'lega', concordi: ['poisson'], motori_totali: 2,
        engines: { poisson: { H: 0.55, D: 0.25, A: 0.2 }, ml: null, tacticai: null, api: null },
        ...over,
    };
}

function direzione(markets: DirMarket[]): DirezioneData {
    return { fixture_id: 77, league_id: 39, generated_at: '2026-09-25T10:00:00+00:00', poisson_present: true, markets };
}

function eta(over: Partial<DirezioneEta>): DirezioneEta {
    return {
        fixture_id: 77, pagella_generated_at: new Date(Date.now() - 3 * 3_600_000).toISOString(),
        quota_righe: 2, quota_con_prezzo: 1, quota_eta: null, now: new Date().toISOString(), ...over,
    };
}

async function apri(): Promise<ReturnType<typeof render>> {
    const s = render(<DirezioneDashboard fixtureId="77" leagueName="Premier League" homeName="Casa" awayName="Trasferta" />);
    fireEvent.click(s.getByRole('button', { name: /Direzione/ }));
    await waitFor(() => expect(s.getByTestId('direzione-eta')).toBeTruthy());
    return s;
}

beforeEach(() => {
    vi.mocked(fetchDirezione).mockReset();
    vi.mocked(fetchDirezioneEta).mockReset();
});

describe('DirezioneDashboard - eta e quota', () => {
    it('mostra "quota assente" sul mercato senza quota e la quota sul mercato che ce l\'ha', async () => {
        vi.mocked(fetchDirezione).mockResolvedValue(direzione([
            mercato({ market: '1x2', direction: 'H', odds: null }),
            mercato({ market: 'over_2_5', direction: 'Over', odds: 1.85, lift: 0.05 }),
        ]));
        vi.mocked(fetchDirezioneEta).mockResolvedValue(eta({}));
        const s = await apri();
        const assenti = s.getAllByTestId('quota-assente');
        expect(assenti).toHaveLength(1);
        expect(assenti[0].textContent).toBe('quota assente');
        expect(s.getByText('1.85')).toBeTruthy();
    });

    it('partita senza righe in analytics_bets: quota assente in rosso nell\'intestazione', async () => {
        vi.mocked(fetchDirezione).mockResolvedValue(direzione([mercato({ odds: null })]));
        vi.mocked(fetchDirezioneEta).mockResolvedValue(eta({ quota_righe: 0, quota_con_prezzo: 0 }));
        const s = await apri();
        await waitFor(() => expect(s.getByTestId('eta-quota').dataset.stato).toBe('assente'));
        expect(s.getByTestId('eta-quota').textContent).toMatch(/quota assente per questa partita/);
        expect(s.getByTestId('eta-quota').className).toContain('text-red-400');
    });

    it('pagella di ieri sera = verde; pagella di 3 giorni fa = ROSSA', async () => {
        vi.mocked(fetchDirezione).mockResolvedValue(direzione([mercato({ odds: 2.1 })]));
        vi.mocked(fetchDirezioneEta).mockResolvedValue(eta({}));
        const s = await apri();
        await waitFor(() => expect(s.getByTestId('eta-pagella').dataset.stato).toBe('fresco'));
        s.unmount();

        vi.mocked(fetchDirezioneEta).mockResolvedValue(eta({ pagella_generated_at: new Date(Date.now() - 72 * 3_600_000).toISOString() }));
        const s2 = await apri();
        await waitFor(() => expect(s2.getByTestId('eta-pagella').dataset.stato).toBe('vecchio'));
        expect(s2.getByTestId('eta-pagella').className).toContain('text-red-400');
    });

    it('RPC di eta non applicata: lo dice (rosso), il resto del pannello funziona', async () => {
        vi.mocked(fetchDirezione).mockResolvedValue(direzione([mercato({ odds: 2.1 })]));
        vi.mocked(fetchDirezioneEta).mockRejectedValue(new Error('function public.get_direction_eta(bigint) does not exist'));
        const s = await apri();
        await waitFor(() => expect(s.getByTestId('eta-pagella').dataset.stato).toBe('assente'));
        expect(s.getByTestId('eta-pagella').textContent).toMatch(/non disponibile/);
        expect(s.queryByTestId('eta-quota')).toBeNull();
        expect(s.getByText('2.10')).toBeTruthy();
    });
});
