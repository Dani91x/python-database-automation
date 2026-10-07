// 07/10 sera (REPLAY PROFESSIONALE): il ladder del trading vivo NON cambia.
// LadderView riceve dal replay una prop OPZIONALE nuova (`botReplay`, gli ordini
// e il P&L del bot applicato). SENZA quella prop il DOM deve restare IDENTICO a
// quello di prima: l'istantanea di questo file e' stata scritta sul codice di
// PRIMA della modifica (commit 778189ec) e il test la confronta col codice di
// adesso. Con la prop: il bot si vede (appoggiati, abbinati, P&L).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('@/lib/live', () => ({
    fetchLiveLadder: vi.fn(),
    subscribeLiveLadder: vi.fn(() => () => {}),
}));
vi.mock('@/lib/liveOrders', () => ({
    fetchLiveOrders: vi.fn(async () => []),
    fetchLivePositions: vi.fn(async () => []),
    sendLiveOrderCommand: vi.fn(),
    sendGreenup: vi.fn(),
    requestRiskRule: vi.fn(),
    subscribeLiveOrders: vi.fn(() => () => {}),
    subscribeLivePositions: vi.fn(() => () => {}),
}));

import { LadderView, type BotLadderOverlay, type LadderOrderApi, type LadderSource } from './LadderView';
import type { LiveLadderRow } from '@/lib/live';
import type { LiveOrderRow, LivePositionRow } from '@/lib/liveOrders';

const T0 = 1_783_700_000_000;

function riga(): LiveLadderRow {
    return {
        event_id: 'evt1', market_id: '1.234', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        status: 'OPEN',
        ladder: {
            updated_ms: T0,
            selections: [
                {
                    selection_id: 1, name: 'Casa', ltp: 3.0, tv: 100,
                    back: [[2.9, 10], [2.88, 5]], lay: [[3.0, 20], [3.05, 8]],
                    trd: [[3.0, 50]], wom: { back_pct: 60, lay_pct: 40 },
                },
                {
                    selection_id: 2, name: 'Ospite', ltp: 2.0, tv: 80,
                    back: [[1.99, 30]], lay: [[2.02, 12]], trd: [[2.0, 40]],
                    wom: { back_pct: 50, lay_pct: 50 },
                },
            ],
        },
        updated_at: new Date(T0).toISOString(),
    } as LiveLadderRow;
}

const ORDINE: LiveOrderRow = {
    id: 1, bet_id: 'b1', client_order_ref: 'r1', request_id: null, mode: 'paper',
    event_id: 'evt1', market_id: '1.234', selection_id: 1, handicap: 0,
    side: 'back', order_type: 'LIMIT', price: 3.0, size: 5,
    size_matched: 0, size_remaining: 5, size_cancelled: 0, size_lapsed: 0, size_voided: 0,
    average_price_matched: 0, status: 'EXECUTABLE', persistence: 'LAPSE',
    placed_at: null, matched_at: null, updated_at: null,
};
const POSIZIONE: LivePositionRow = {
    id: 1, mode: 'paper', event_id: 'evt1', market_id: '1.234', selection_id: 1, handicap: 0,
    matched_if_win: 10, matched_if_lose: -5, worst_if_win: 10, worst_if_lose: -5,
    selection_exposure: 5, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
    net_position: 5, updated_at: null,
};

const sorgente: LadderSource = { fetch: async () => riga(), subscribe: () => () => {} };
const api: LadderOrderApi = {
    send: vi.fn(),
    fetchOrders: async () => [ORDINE],
    fetchPositions: async () => [POSIZIONE],
};

beforeEach(() => {
    localStorage.clear();
    vi.spyOn(Date, 'now').mockReturnValue(T0 + 1000);
});
afterEach(() => vi.restoreAllMocks());

async function monta(extra: Record<string, unknown> = {}) {
    const r = render(
        <LadderView marketId="1.234" orderMode="paper" sport="calcio" flussoRunner={false}
            ladderSource={sorgente} orderApi={api} {...extra} />,
    );
    await waitFor(() => expect(screen.getAllByText('Casa').length).toBeGreaterThan(0));
    // l'overlay ordini/posizioni e' caricato
    await waitFor(() => expect(r.container.innerHTML).toContain('5.00'));
    return r;
}

describe('LadderView senza la prop del replay: identico a prima', () => {
    it('il DOM e\' quello del codice di prima (istantanea scritta su 778189ec)', async () => {
        const { container } = await monta();
        expect(container.innerHTML).toMatchSnapshot();
        expect(screen.queryByTestId('bot-pnl-selezione')).toBeNull();
        expect(screen.queryByTestId('bot-appoggiato')).toBeNull();
    });
});

describe('LadderView con la prop del replay: il bot si vede sul ladder', () => {
    const botReplay: BotLadderOverlay = {
        etichetta: 'Scalper - Media Under 2,5',
        perSelezione: {
            1: {
                livelli: [
                    { lato: 'lay', quota: 4.0, appoggiato: 10.19, abbinato: 0, inVolo: 0 },
                    { lato: 'back', quota: 2.9, appoggiato: 0, abbinato: 10, inVolo: 0 },
                ],
                seVinceSel: 19, sePerdeSel: -10, seVinceMercato: 19, abbinatoBack: 10, abbinatoLay: 0,
            },
        },
    };
    it('appoggiato in ambra nella colonna del suo lato, abbinato in verde, P&L del bot', async () => {
        await monta({ botReplay });
        const app = screen.getByTestId('bot-appoggiato');
        expect(app.getAttribute('data-lato')).toBe('lay');
        expect(app.getAttribute('data-quota')).toBe('4');
        expect(app.textContent).toBe('10.19');
        const abb = screen.getByTestId('bot-abbinato');
        expect(abb.getAttribute('data-lato')).toBe('back');
        expect(abb.textContent).toBe('✓10.00');
        expect(screen.getAllByTestId('bot-pnl-selezione')).toHaveLength(2);
        expect(screen.getByTestId('bot-se-vince').textContent).toBe('€19.00');
        // la quota 4,00 del bot e' nel ladder anche se il book non arriva fin li'
        expect(app.closest('[class*="ds-v2-ladder-riga"]')?.textContent).toContain('4.00');
    });
    it('il bot e\' SOLA LETTURA: la cella del suo ordine non annulla nulla', async () => {
        await monta({ botReplay });
        const cella = screen.getByTestId('bot-appoggiato').closest('button');
        expect(cella?.hasAttribute('disabled')).toBe(true);
    });
});
