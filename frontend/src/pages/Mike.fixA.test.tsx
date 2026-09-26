// ============================================================================
// FIX-A (26/09) — pagina Mike (E2E fase 3):
//   U0536: con le uscite MANUALI di default la proposta d'uscita non si poteva
//          firmare da /mike (solo dalla Control Room);
//   U0537: «Se chiudo ora» delle Operazioni era il P&L BLOCCATO («—») mentre la
//          card diceva −0,38 €.
// Fixture con le chiavi di get_mike_state (come pages/Mike.test.tsx); la
// proposta ha le chiavi VERE di `engine.gate_uscite` (PropostaUscitaMikeDati).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.setConfig({ testTimeout: 20_000 });

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
vi.mock('@/lib/safeStrategyScan', async (orig) => ({
    ...(await orig<typeof import('@/lib/safeStrategyScan')>()),
    fetchScanStatus: vi.fn(async () => ({ id: 'scanner', payload: {}, updated_at: new Date().toISOString() })),
}));
vi.mock('@/lib/dailyHistory', async (orig) => ({
    ...(await orig<typeof import('@/lib/dailyHistory')>()),
    fetchMikeDaily: vi.fn(async () => []),
    fetchMikeDayTrades: vi.fn(async () => []),
}));
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig<typeof import('@/lib/mike')>()),
    fetchMikeState: vi.fn(),
    fetchMikeRequests: vi.fn(async () => []),
    subscribeMike: vi.fn(() => () => {}),
    activateMike: vi.fn(),
    stopMike: vi.fn(),
    updateMikeParams: vi.fn(),
    requestMike: vi.fn(async () => 77),
}));

import Mike from './Mike';
import { fetchMikeState, requestMike, closeNowTotal, type MikeEvent } from '@/lib/mike';

const mState = vi.mocked(fetchMikeState);
const mRequest = vi.mocked(requestMike);
const NOW = new Date().toISOString();

const CONTROL = {
    id: 1, status: 'running', mode: 'paper', params: { stake: 5, cashout_profit_pct: 5, uscite_automatiche: false },
    stats: { events_feed: 12, events_tracked: 2, by_state: {}, trades_open: 2, open_liability: 10,
             realized_today: 0, realized_total: 8.14, scanner_age_s: 2, last_cycle: NOW, dry: false, mode: 'paper' },
    error: null, started_at: null, stopped_at: null, heartbeat_at: NOW, updated_at: NOW,
};
const AGGREGATES = {
    realized_total: 8.14, realized_today: 0, open_liability: 10, open_count: 2, won: 0, lost: 0,
    won_today: 0, lost_today: 0, cycles_today: 2, events_today: 2, live_now: 0, reconciling: 0,
    open_liability_rows: 10, day_by: 'placed',
};
const book = (bb: number, bl: number) => ({ best_back: bb, back_size: 30, best_lay: bl, lay_size: 20, status: 'OPEN', inplay: false, bet_delay: 0 });

function evento(id: string, net: number | null, locked: number | null, proposta?: Record<string, unknown>) {
    return {
        event_id: id, fixture_id: null, event_name: `Casa ${id} v Ospite`, competition: 'Liga', league_id: null,
        ko_at: new Date(Date.now() + 3600_000).toISOString(), mode: 'paper', markets: { OU35: { market_id: `1.${id}` } },
        state: 'PRE_OPEN', cycle_no: 0, entry_price_initial: 1.6,
        dossier: { p4_pre: 0.18 },
        live: {
            inplay: false, minute: null, goals: null, ht: false, hazard: null, p4_market: 0.18, p4_model: null,
            feed_age_s: 3, scanner_age_s: 2, lines_missing: [], reconcile_pending: false,
            liability: 5, locked, total_matched: 4200,
            cashout: net == null ? null : { net, gross: net, base: 5, complete: true, pct: net / 5 * 100, target_pct: 5,
                per: { 'OU35|UNDER': net }, per_gross: { 'OU35|UNDER': net }, decided: [], commission: 0.05 },
            pnl_by_total: { '0': 2.85, '4': -5 }, books: { 'OU35|UNDER': book(1.69, 1.73) }, feed_fresh: true,
        },
        positions: [{ role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.6, size: 5, matched: 5,
                      avg_price: 1.6, ref: 'under_entry-1-1', status: 'open', placed_at: 0, persistence: 'LAPSE',
                      cycle_no: 1, final: false, archived: false }],
        ctx: { selections: { 'OU35|UNDER': 1222344 }, ...(proposta ? { uscita_proposta: proposta } : {}) },
        skipped: false, settled_pnl: null, updated_at: NOW,
    };
}

const PROPOSTA = {
    chiave: 'green_pre:1', categoria: 'green_pre', ciclo: 1, stato: 'PRE_OPEN', stato_voluto: 'PRE_GREEN',
    motivo: 'green-up pre-partita: quota scesa di 3 tick', close_reason: 'green_pre',
    ordini: [{ ruolo: 'under_green', mercato: 'OU35', selezione: 'UNDER', lato: 'lay', prezzo: 1.73, size: 4.62 }],
    bloccabile: -0.38, urgente: false, minuto: null, gol: null,
    decided_at: Math.floor(Date.now() / 1000) - 4, proposed_at: Math.floor(Date.now() / 1000) - 4,
};

function state(events: unknown[]) {
    return {
        control: CONTROL, events, trades: [], activity: [], aggregates: AGGREGATES, requests: [],
        day_start: NOW, day_by: 'placed',
    } as never;
}

function renderPage() {
    return render(<HelmetProvider><MemoryRouter><Mike /></MemoryRouter></HelmetProvider>);
}

beforeEach(() => { vi.clearAllMocks(); });

describe('FIX-A — «Se chiudo ora» = somma dei netti delle card', () => {
    it('closeNowTotal: −0,38 + 0,12 = −0,26 (il bloccato −0,10 non c’entra); card senza netto fuori', () => {
        const evs = [evento('a', -0.38, null), evento('b', 0.12, -0.1), evento('c', null, null)] as unknown as MikeEvent[];
        expect(closeNowTotal(evs)).toEqual({ value: -0.26, known: 2, pending: 1 });
        expect(closeNowTotal([evento('c', null, null)] as unknown as MikeEvent[]).value).toBeNull();
    });

    it('la barra Operazioni scrive la somma delle card, non il bloccato', async () => {
        mState.mockResolvedValue(state([evento('a', -0.38, null), evento('b', 0.12, -0.1)]));
        renderPage();
        await screen.findByTestId('mike-cards');
        await userEvent.click(screen.getByRole('tab', { name: /Operazioni/ }));
        expect(await screen.findByTestId('mike-operazioni-totali-aperto')).toHaveTextContent('−0,26');
    });
});

describe('FIX-A — la proposta d’uscita si firma da /mike (stesso comando della Control Room)', () => {
    it('la card mostra la proposta e APPROVA manda approva_uscita con la chiave', async () => {
        mState.mockResolvedValue(state([evento('a', -0.38, null, PROPOSTA)]));
        renderPage();
        const box = await screen.findByTestId('mike-proposta-a');
        expect(box).toHaveTextContent('Mike vorrebbe uscire: green-up pre-partita');
        await userEvent.click(within(box).getByTestId('mike-proposta-a-approva'));
        await waitFor(() => expect(mRequest).toHaveBeenCalledTimes(1));
        const [kind, payload] = mRequest.mock.calls[0] as [string, Record<string, unknown>];
        expect(kind).toBe('approva_uscita');
        expect(payload).toMatchObject({ event_id: 'a', bot: 'mike', mode: 'paper', chiave: 'green_pre:1' });
    });

    it('senza proposta: nessun riquadro in più', async () => {
        mState.mockResolvedValue(state([evento('a', -0.38, null)]));
        renderPage();
        await screen.findByTestId('mike-cards');
        expect(screen.queryByTestId('mike-proposta-a')).toBeNull();
    });
});
