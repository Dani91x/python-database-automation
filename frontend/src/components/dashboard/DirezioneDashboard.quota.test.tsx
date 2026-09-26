// FIX-B (26/09/2026) KO6: la "quota" della carta Direzione.
// Referto fase 3 U0100, partita A (1492980): get_direction.odds = coalesce(odds_betfair,
// odds_book) e odds_betfair e' quasi sempre NULL -> la carta mostrava 1.36 (book, Under 3.5)
// come "quota" e ci giudicava il "valore", mentre lo stesso pannello aveva le quote Betfair
// Under 3.5 back 1.42 / lay 1.46. Regola nuova (solo etichetta/fonte, logica invariata):
//   - quota Betfair (back migliore della direzione) quando c'e' -> "Betfair", giudizio di valore;
//   - altrimenti la quota di get_direction si etichetta "quota book" e NON si chiama valore.
// Finti con le chiavi dell'output jsonb di get_direction / get_direction_eta /
// get_betfair_direction_odds (DirectionOdds = {market: {selection: {back[], lay[]}}}).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor, within } from '@testing-library/react';
import type { DirMarket, DirezioneData, DirezioneEta } from '@/lib/direzione';
import type { DirectionOdds } from '@/lib/betfair';

vi.mock('@/lib/direzione', async (orig) => ({
    ...(await orig<typeof import('@/lib/direzione')>()),
    fetchDirezione: vi.fn(),
    fetchDirezioneEta: vi.fn(),
}));
vi.mock('@/lib/betfair', async (orig) => ({
    ...(await orig<typeof import('@/lib/betfair')>()),
    fetchBetfairDirectionOdds: vi.fn(),
}));
vi.mock('@/lib/signalContext', async (orig) => ({
    ...(await orig<typeof import('@/lib/signalContext')>()),
    fetchSignalContext: vi.fn(async () => null),
}));

import { fetchDirezione, fetchDirezioneEta } from '@/lib/direzione';
import { fetchBetfairDirectionOdds } from '@/lib/betfair';
import { DirezioneDashboard } from './DirezioneDashboard';
import { quotaDirezione } from '@/lib/direzione';

function mercato(over: Partial<DirMarket>): DirMarket {
    return {
        market: 'over_3_5', direction: 'Under', calibrated: true, poisson_missing: false,
        affidabilita: 0.761, wilson_low: 0.6729, wilson_high: 0.8313, n: 109, base: 0.6569, lift: 0.1041,
        odds: 1.36, scope: 'lega', concordi: ['poisson', 'ml', 'tacticai'], motori_totali: 3,
        engines: { poisson: { Under: 0.779, Over: 0.221 }, ml: { Under: 0.656, Over: 0.344 }, tacticai: { Under: 0.721, Over: 0.279 }, api: null },
        ...over,
    };
}
const eta: DirezioneEta = {
    fixture_id: 1492980, pagella_generated_at: new Date(Date.now() - 3_600_000).toISOString(),
    quota_righe: 45, quota_con_prezzo: 20, quota_eta: null, now: new Date().toISOString(),
};
const BF: DirectionOdds = {
    over_3_5: { Over: { back: [{ price: 3.15, size: 20 }], lay: [{ price: 3.4, size: 10 }] },
                Under: { back: [{ price: 1.42, size: 50 }], lay: [{ price: 1.46, size: 40 }] } },
};

async function apri(markets: DirMarket[], bf: DirectionOdds) {
    const data: DirezioneData = { fixture_id: 1492980, league_id: 358, generated_at: new Date().toISOString(), poisson_present: true, markets };
    vi.mocked(fetchDirezione).mockResolvedValue(data);
    vi.mocked(fetchDirezioneEta).mockResolvedValue(eta);
    vi.mocked(fetchBetfairDirectionOdds).mockResolvedValue(bf);
    const s = render(<DirezioneDashboard fixtureId="1492980" leagueName="First Division" homeName="Cobh" awayName="Athlone" />);
    fireEvent.click(s.getByRole('button', { name: /Direzione/ }));
    await waitFor(() => expect(s.getAllByTestId('quota-carta').length).toBe(markets.length));
    return s;
}

beforeEach(() => {
    vi.mocked(fetchDirezione).mockReset();
    vi.mocked(fetchDirezioneEta).mockReset();
    vi.mocked(fetchBetfairDirectionOdds).mockReset();
});

describe('quotaDirezione (pura)', () => {
    it('Betfair presente: back migliore della direzione, giudicabile', () => {
        expect(quotaDirezione(mercato({}), BF.over_3_5)).toEqual({ odds: 1.42, fonte: 'betfair', giudicabile: true });
    });
    it('Betfair assente: quota di get_direction come "book", NON giudicabile', () => {
        expect(quotaDirezione(mercato({ market: '1x2', direction: 'H', odds: 2.5 }), undefined))
            .toEqual({ odds: 2.5, fonte: 'book', giudicabile: false });
    });
    it('nessuna quota: null', () => {
        expect(quotaDirezione(mercato({ odds: null }), undefined)).toEqual({ odds: null, fonte: null, giudicabile: false });
    });
});

describe('DirezioneDashboard - fonte della quota', () => {
    it('Under 3.5 del referto: la carta usa la quota Betfair 1.42 (non il book 1.36)', async () => {
        const s = await apri([mercato({})], BF);
        await waitFor(() => expect(s.getByTestId('quota-carta').dataset.fonte).toBe('betfair'));
        const q = s.getByTestId('quota-carta');
        expect(within(q).getByText('1.42')).toBeTruthy();
        expect(q.textContent).not.toContain('1.36');
        expect(q.textContent).toMatch(/Betfair/i);
    });

    it('1X2 senza Betfair: "quota book", mai "valore" anche se la banda batte 1/quota', async () => {
        // wilson_low 0.50 > 1/2.50 = 0.40: prima la carta scriveva "valore" sul book
        const s = await apri([mercato({ market: '1x2', direction: 'H', odds: 2.5, wilson_low: 0.5, affidabilita: 0.55, wilson_high: 0.6 })], {});
        const q = s.getByTestId('quota-carta');
        expect(q.dataset.fonte).toBe('book');
        expect(q.textContent).toMatch(/book/i);
        expect(q.textContent).not.toMatch(/valore/i);
    });
});
