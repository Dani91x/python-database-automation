// MarketWatch.canale.test.tsx - 23/09: MarketWatch canale-first. Il canale
// locale e' quello VERO (localChannel.ts) con un WebSocket finto che parla la
// busta del server (local_channel.py: {"t","d"}); i push hanno le chiavi dei
// produttori (db.py::update_live_now / upsert_live_position, tennis_db.py
// idem). Il database e' mockato come nel test esistente (MarketWatch.test.tsx).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
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
vi.mock('@/lib/tennis', async (orig) => ({
    // 26/09: le funzioni PURE restano le vere (partitaTennisFinita)
    partitaTennisFinita: (await orig() as { partitaTennisFinita: unknown }).partitaTennisFinita,
    fetchTennisFollows: vi.fn(),
    fetchTennisNow: vi.fn(),
    subscribeTennisNow: vi.fn(() => () => {}),
    fetchTennisPositionsAll: vi.fn(),
}));

import MarketWatch from './MarketWatch';
import { __resetLocalChannels } from '@/lib/localChannel';
import { fetchLiveFollows, fetchLiveNow, subscribeLiveNow } from '@/lib/live';
import { fetchLivePositionsEvent } from '@/lib/liveOrders';
import { fetchTennisFollows, fetchTennisNow, fetchTennisPositionsAll } from '@/lib/tennis';

class FintoWs {
    static tutti: FintoWs[] = [];
    url: string;
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    constructor(url: string) { this.url = url; FintoWs.tutti.push(this); }
    send(): void { /* nessuna richiesta da MarketWatch */ }
    close(): void { /* chiusura lato server non usata */ }
    apri(): void { this.onopen?.(); }
    push(t: string, d: unknown): void { this.onmessage?.({ data: JSON.stringify({ t, d }) }); }
}
const ws = (porta: number) => FintoWs.tutti.find(w => w.url.endsWith(`:${porta}`))!;

const T0 = '2026-09-23T18:00:00.100000+00:00';
const T1 = '2026-09-23T18:00:02.000000+00:00';
const T2 = '2026-09-23T18:00:05.000000+00:00';

const CALCIO_FOLLOW = {
    event_id: 'ev1', fixture_id: null, league_name: 'Serie A',
    home_name: 'Milan', away_name: 'Inter',
    open_date: new Date().toISOString(), status: 'STREAMING' as const,
    error_detail: null, inplay: true, minute: 63, score_home: 1, score_away: 2,
    live_status: null, score_source: null, updated_at: null,
};
// riga now come update_live_now (db.py): event_id, inplay, minute, score_*, status, score_source, state, updated_at
const nowCalcio = (minute: number, updated_at: string) => ({
    event_id: 'ev1', inplay: true, minute, score_home: 1, score_away: 2,
    status: 'OPEN', score_source: 'betfair',
    state: {
        order_mode: 'PAPER',
        markets: [{
            market_id: '1.234', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
            selections: [{ selection_id: 7, name: 'Milan', back: 2.0, lay: 2.02, ltp: 2.0 }],
        }],
    },
    updated_at,
});
const TENNIS_FOLLOW = {
    event_id: 'tev1', competition_name: 'ATP Wimbledon',
    player1_name: 'Sinner', player2_name: 'Alcaraz',
    open_date: new Date().toISOString(), status: 'STREAMING' as const,
    error_detail: null, inplay: true,
    score: { set_summary: '6-4 3-2' } as never,
    live_status: null, updated_at: null,
};
// riga now tennis come update_tennis_live_now (tennis_db.py): event_id, inplay, status, state, score, points, updated_at
const nowTennis = (set_summary: string, updated_at: string) => ({
    event_id: 'tev1', inplay: true, status: 'OPEN',
    state: {
        order_mode: 'PAPER',
        markets: [{
            market_id: '1.999', market_type: 'MATCH_ODDS', market_name: 'Match Odds', status: 'OPEN',
            selections: [{ selection_id: 11, name: 'Sinner', back: 1.5, lay: 1.51, ltp: 1.5 }],
        }],
    },
    score: { set_summary }, points: null, updated_at,
});
// riga del database (LivePositionRow, get_live_positions_event)
const posDb = (over: Record<string, unknown> = {}) => ({
    id: 1, mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 7, handicap: 0,
    matched_if_win: 10, matched_if_lose: -5, worst_if_win: 10, worst_if_lose: -5,
    selection_exposure: 5, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
    net_position: 5, updated_at: T0, ...over,
});
// push come upsert_live_position (db.py): _position_row + updated_at, niente id
const posPush = (over: Record<string, unknown> = {}) => ({
    mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 7, handicap: 0.0,
    matched_if_win: 20.0, matched_if_lose: -9.0, worst_if_win: 20.0, worst_if_lose: -9.0,
    selection_exposure: 9.0, unmatched_back_exposure: 0.0, unmatched_lay_exposure: 0.0,
    net_position: 9.0, updated_at: T2, ...over,
});
const TENNIS_POS = posDb({ id: 9, event_id: 'tev1', market_id: '1.999', selection_id: 11, selection_exposure: 3 });

const mPositions = vi.mocked(fetchLivePositionsEvent);
const mTPositions = vi.mocked(fetchTennisPositionsAll);

async function scorri(ms = 0) {
    await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <MarketWatch />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

// i due "Rischio" della pagina: [0] calcio ev1, [1] tennis tev1 (simbolo euro
// reso "EUR" per tenere il sorgente ASCII). 26/09 (KO §9-bis n.2): il rischio
// e' diviso per modalita'; le righe di questo file sono tutte PAPER, quindi si
// legge il numero «prova» (e quello «live» resta a zero, mai sommato).
const EURO = String.fromCharCode(0x20ac);
const rischi = () => screen.getAllByTitle(/Esposizione worst-case/)
    .map((el) => {
        const live = el.querySelector('[data-testid="mw-rischio-live"]')?.textContent ?? '';
        if (!live.endsWith(`${EURO}0.00`)) return `live ${live}`;
        return (el.querySelector('[data-testid="mw-rischio-paper"]')?.textContent ?? '')
            .replace('prova', '').replace(EURO, 'EUR');
    });

beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'setInterval', 'clearTimeout', 'clearInterval'] });
    vi.clearAllMocks();
    FintoWs.tutti = [];
    vi.stubGlobal('WebSocket', FintoWs);
    vi.mocked(fetchLiveFollows).mockResolvedValue([CALCIO_FOLLOW] as never);
    vi.mocked(fetchLiveNow).mockResolvedValue(nowCalcio(63, T0) as never);
    mPositions.mockResolvedValue([posDb()] as never);
    vi.mocked(fetchTennisFollows).mockResolvedValue([TENNIS_FOLLOW] as never);
    vi.mocked(fetchTennisNow).mockResolvedValue(nowTennis('6-4 3-2', T0) as never);
    mTPositions.mockResolvedValue([TENNIS_POS] as never);
});
afterEach(() => {
    __resetLocalChannels();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe('MarketWatch - canale locale sopra il poll', () => {
    it('parita\': senza canale (nessun WebSocket) la pagina rende i dati del database come oggi', async () => {
        vi.stubGlobal('WebSocket', undefined);
        renderPage();
        await scorri();
        expect(screen.getByText(/LIVE 63' \S 1\S2/)).toBeInTheDocument();
        expect(rischi()).toEqual(['EUR5.00', 'EUR3.00']);
        expect(screen.getByText(/6-4 3-2/)).toBeInTheDocument();
        // stesse letture di prima: 1 follows calcio + 1 now + 1 posizioni, poi 10 s -> +1 posizioni
        expect(mPositions).toHaveBeenCalledTimes(1);
        await scorri(10_000);
        expect(mPositions).toHaveBeenCalledTimes(2);
        expect(mTPositions).toHaveBeenCalledTimes(2);
    });

    it('position calcio: il push fresco vince sulla riga del poll', async () => {
        renderPage();
        await scorri();
        act(() => { ws(47331).apri(); ws(47331).push('position', posPush()); });
        expect(rischi()[0]).toBe('EUR9.00');
        expect(rischi()[1]).toBe('EUR3.00'); // il tennis non si tocca
    });

    it('position calcio: messaggio vecchio (updated_at non oltre il database) ignorato', async () => {
        mPositions.mockResolvedValue([posDb({ updated_at: T2 })] as never);
        renderPage();
        await scorri();
        act(() => { ws(47331).apri(); ws(47331).push('position', posPush({ updated_at: T1 })); });
        expect(rischi()[0]).toBe('EUR5.00');
    });

    it('canale muto: il poll a 10 s resta la fonte e porta il dato nuovo', async () => {
        renderPage();
        await scorri();
        ws(47331).apri();
        mPositions.mockResolvedValue([posDb({ selection_exposure: 7, updated_at: T1 })] as never);
        await scorri(10_000);
        expect(rischi()[0]).toBe('EUR7.00');
    });

    it('riga sparita dal blocco del database: sparisce e il canale non la riporta', async () => {
        renderPage();
        await scorri();
        act(() => { ws(47331).apri(); ws(47331).push('position', posPush()); });
        expect(rischi()[0]).toBe('EUR9.00');
        mPositions.mockResolvedValue([] as never);
        await scorri(10_000);
        expect(rischi()[0]).toBe('EUR0.00');
        act(() => { ws(47331).push('position', posPush({ updated_at: '2026-09-23T18:00:30+00:00' })); });
        expect(rischi()[0]).toBe('EUR0.00');
    });

    it('now calcio: il push piu\' recente aggiorna il badge, quello vecchio no', async () => {
        renderPage();
        await scorri();
        act(() => { ws(47331).apri(); ws(47331).push('now', nowCalcio(70, T2)); });
        expect(screen.getByText(/LIVE 70' \S 1\S2/)).toBeInTheDocument();
        act(() => { ws(47331).push('now', nowCalcio(64, T1)); });
        expect(screen.getByText(/LIVE 70' \S 1\S2/)).toBeInTheDocument();
        // un evento non seguito non compare (la pagina rende solo i follows:
        // il filtro per evento nel componente non e' osservabile da qui)
        act(() => { ws(47331).push('now', { ...nowCalcio(80, T2), event_id: 'altro' }); });
        expect(screen.queryByText(/LIVE 80'/)).toBeNull();
    });

    it('now calcio: il realtime del database piu\' vecchio del canale non torna indietro', async () => {
        const cbs: Array<(r: unknown) => void> = [];
        vi.mocked(subscribeLiveNow).mockImplementation(((_id: string, cb: (r: unknown) => void) => {
            cbs.push(cb); return () => {};
        }) as never);
        renderPage();
        await scorri();
        act(() => { ws(47331).apri(); ws(47331).push('now', nowCalcio(70, T2)); });
        act(() => { cbs.forEach(cb => cb(nowCalcio(65, T1))); });
        expect(screen.getByText(/LIVE 70' \S 1\S2/)).toBeInTheDocument();
    });

    it('tennis: now e position dalla porta 47332', async () => {
        renderPage();
        await scorri();
        act(() => {
            ws(47332).apri();
            ws(47332).push('now', nowTennis('6-4 5-2', T2));
            ws(47332).push('position', posPush({
                event_id: 'tev1', market_id: '1.999', selection_id: 11, selection_exposure: 4.5,
            }));
        });
        expect(screen.getByText(/6-4 5-2/)).toBeInTheDocument();
        expect(rischi()[1]).toBe('EUR4.50');
        expect(rischi()[0]).toBe('EUR5.00'); // il calcio non si tocca
    });
});
