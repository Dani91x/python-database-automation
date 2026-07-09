// Test COMPONENTE leggero per MarketWatch (D30). Moduli data mockati (nessuna
// rete/realtime); lib/eventPnl REALE (matematica pura già testata a unità).
// Copre: render con fixture, riga calcio con score/minuto + bottone cash-out,
// riga tennis SENZA cash-out (capability gating).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/lib/live', () => ({
    fetchLiveFollows: vi.fn(),
    fetchLiveNow: vi.fn(),
    subscribeLiveNow: vi.fn(() => () => {}),
}));
vi.mock('@/lib/liveOrders', () => ({
    fetchLivePositionsEvent: vi.fn(),
    sendCashoutEvent: vi.fn(),
}));
vi.mock('@/lib/tennis', () => ({
    fetchTennisFollows: vi.fn(),
    fetchTennisNow: vi.fn(),
    subscribeTennisNow: vi.fn(() => () => {}),
    fetchTennisPositionsAll: vi.fn(),
}));

import MarketWatch from './MarketWatch';
import { fetchLiveFollows, fetchLiveNow } from '@/lib/live';
import { fetchLivePositionsEvent } from '@/lib/liveOrders';
import { fetchTennisFollows, fetchTennisNow, fetchTennisPositionsAll } from '@/lib/tennis';

const mFollows = vi.mocked(fetchLiveFollows);
const mNow = vi.mocked(fetchLiveNow);
const mPositions = vi.mocked(fetchLivePositionsEvent);
const mTFollows = vi.mocked(fetchTennisFollows);
const mTNow = vi.mocked(fetchTennisNow);
const mTPositions = vi.mocked(fetchTennisPositionsAll);

const CALCIO_FOLLOW = {
    event_id: 'ev1', fixture_id: null, league_name: 'Serie A',
    home_name: 'Milan', away_name: 'Inter',
    open_date: new Date().toISOString(), status: 'STREAMING' as const,
    error_detail: null, inplay: true, minute: 63, score_home: 1, score_away: 2,
    live_status: null, score_source: null, updated_at: null,
};

const CALCIO_NOW = {
    event_id: 'ev1', inplay: true, minute: 63, score_home: 1, score_away: 2,
    status: 'OPEN', score_source: null,
    state: {
        order_mode: 'PAPER',
        markets: [{
            market_id: '1.234', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
            selections: [{ selection_id: 7, name: 'Milan', back: 2.0, lay: 2.02, ltp: 2.0 }],
        }],
    },
    updated_at: new Date().toISOString(),
};

const TENNIS_FOLLOW = {
    event_id: 'tev1', competition_name: 'ATP Wimbledon',
    player1_name: 'Sinner', player2_name: 'Alcaraz',
    open_date: new Date().toISOString(), status: 'STREAMING' as const,
    error_detail: null, inplay: true,
    score: { set_summary: '6-4 3-2' } as never,
    live_status: null, updated_at: null,
};

const TENNIS_NOW = {
    event_id: 'tev1', inplay: true, status: 'OPEN',
    state: {
        order_mode: 'PAPER',
        markets: [{
            market_id: '1.999', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
            selections: [{ selection_id: 11, name: 'Sinner', back: 1.5, lay: 1.51, ltp: 1.5 }],
        }],
    },
    score: { set_summary: '6-4 3-2' } as never,
    points: null,
    updated_at: new Date().toISOString(),
};

beforeEach(() => {
    vi.clearAllMocks();
    mFollows.mockResolvedValue([CALCIO_FOLLOW] as never);
    mNow.mockResolvedValue(CALCIO_NOW as never);
    mPositions.mockResolvedValue([{
        id: 1, mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 7, handicap: 0,
        matched_if_win: 10, matched_if_lose: -5, worst_if_win: 10, worst_if_lose: -5,
        selection_exposure: 5, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
        net_position: 5, updated_at: null,
    }] as never);
    mTFollows.mockResolvedValue([TENNIS_FOLLOW] as never);
    mTNow.mockResolvedValue(TENNIS_NOW as never);
    mTPositions.mockResolvedValue([] as never);
});

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <MarketWatch />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

describe('MarketWatch', () => {
    it('renderizza le due sezioni con le righe dalle fixture', async () => {
        renderPage();
        expect(await screen.findByText('Milan – Inter')).toBeInTheDocument();
        expect(await screen.findByText('Sinner vs Alcaraz')).toBeInTheDocument();
        expect(screen.getByText('⚽ Calcio')).toBeInTheDocument();
        expect(screen.getByText('🎾 Tennis')).toBeInTheDocument();
    });

    it('riga calcio: badge in-play con minuto+score e bottone Cash-out EVENTO', async () => {
        renderPage();
        // badge LIVE con minuto e punteggio
        expect(await screen.findByText(/LIVE 63' · 1–2/)).toBeInTheDocument();
        // bottone cash-out presente sulla riga calcio
        const btn = await screen.findByRole('button', { name: /cash-out evento/i });
        expect(btn).toBeInTheDocument();
    });

    it('riga tennis: set_summary visibile e NESSUN bottone cash-out (capability gating)', async () => {
        renderPage();
        expect(await screen.findByText(/6-4 3-2/)).toBeInTheDocument();
        // UN SOLO bottone cash-out in tutta la pagina: quello del calcio.
        const cashButtons = screen.getAllByRole('button', { name: /cash-out/i });
        expect(cashButtons).toHaveLength(1);
        // la riga tennis mostra il placeholder onesto con spiegazione nel title
        expect(
            screen.getByTitle(/worker tennis non supporta il cash-out/i),
        ).toBeInTheDocument();
        // link al terminal tennis con i query param di TennisTerminal (event+market)
        const link = await screen.findByRole('link', { name: /apri terminal tennis/i });
        expect(link.getAttribute('href')).toContain('/tennis/terminal?');
        expect(link.getAttribute('href')).toContain('event=tev1');
        expect(link.getAttribute('href')).toContain('market=1.999');
    });
});
