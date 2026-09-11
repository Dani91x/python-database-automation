// Test di PAGINA per /mike: data-layer e sonner mockati, helper puri VERI.
// Copre i "test mancanti" dell'audit sul frontend Mike: sezioni PRE-MATCH/LIVE,
// ordine STABILE delle schede al cambio di fase, ERROR/SKIPPED con "Riprendi"
// (H6), cash out spento con motivo a feed fermo, tab Trade con le chiusure
// annidate, attività in italiano, esito delle richieste (M1).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

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
    requestMike: vi.fn(async () => 1),
}));

import Mike from './Mike';
import { fetchMikeState, subscribeMike, requestMike, activateMike, stopMike, updateMikeParams } from '@/lib/mike';
import { fetchMikeDaily } from '@/lib/dailyHistory';

const mState = vi.mocked(fetchMikeState);
const mSubscribe = vi.mocked(subscribeMike);
const mRequest = vi.mocked(requestMike);
const mDaily = vi.mocked(fetchMikeDaily);
const mActivate = vi.mocked(activateMike);
const mStop = vi.mocked(stopMike);
const mSaveParams = vi.mocked(updateMikeParams);

const NOW = new Date().toISOString();
const DAY_START = new Date(Date.now() - 6 * 3600_000).toISOString();

const CONTROL = {
    id: 1, status: 'running', mode: 'paper', params: { stake: 10, cashout_profit_pct: 5 },
    stats: { events_feed: 12, events_tracked: 3, by_state: {}, trades_open: 1, open_liability: 12.5,
             realized_today: 1.2, realized_total: 3.4, scanner_age_s: 2, last_cycle: NOW,
             dry: false, mode: 'paper' },
    error: null, started_at: null, stopped_at: null, heartbeat_at: NOW, updated_at: NOW,
};

const AGGREGATES = {
    realized_total: 3.4, realized_today: 1.2, open_liability: 12.5, open_count: 2,
    won: 3, lost: 1, won_today: 1, lost_today: 0, cycles_today: 4, events_today: 2,
    live_now: 1, reconciling: 1, open_liability_rows: 20, day_by: 'placed',
};

function book(over: Record<string, unknown> = {}) {
    return { best_back: 1.47, back_size: 30, best_lay: 1.48, lay_size: 20, status: 'OPEN', inplay: false, bet_delay: 0, ...over };
}

/** pre-match con posizione aperta, KO fra un'ora */
const PRE = {
    event_id: 'e1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
    ko_at: new Date(Date.now() + 3600_000).toISOString(), mode: 'paper', markets: { OU35: { market_id: '1.1' } },
    state: 'PRE_OPEN', cycle_no: 0, entry_price_initial: 1.5,
    dossier: { p4_pre: 0.14, lambda_home: 1.4, lambda_away: 1.1 },
    live: {
        inplay: false, minute: null, goals: null, ht: false, hazard: null, p4_market: 0.12, p4_model: null,
        p_over45_model: 0.06, feed_age_s: 3, scanner_age_s: 2, lines_missing: [], reconcile_pending: false,
        liability: 10, locked: 0.13, total_matched: 4200,
        p_total_model: { '0': 0.08, '1': 0.2, '2': 0.24, '3': 0.2, '4': 0.14, '5': 0.08, '6': 0.04, '7': 0.01, '8': 0.01 },
        cashout: { net: 0.35, gross: 0.37, base: 10, complete: true, pct: 3.5, target_pct: 5,
                   per: { 'OU35|UNDER': 0.35 }, per_gross: { 'OU35|UNDER': 0.37 }, decided: [], commission: 0.05 },
        cover_wait: null, pnl_by_total: { '0': 4.75, '3': 4.75, '4': -10, '5': -10 },
        books: { 'OU35|UNDER': book() }, feed_fresh: true,
    },
    positions: [{ role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10, matched: 10,
                  avg_price: 1.5, ref: 'under_entry-0-1', status: 'open', placed_at: 0, persistence: 'LAPSE', cycle_no: 0,
                  final: false, archived: false }],
    ctx: { selections: { 'OU35|UNDER': 1222344 } }, skipped: false, settled_pnl: null, updated_at: NOW,
};

/** live coperta, feed FERMO (90 s): il cash out deve essere spento con motivo */
const LIVE = {
    event_id: 'e2', fixture_id: null, event_name: 'Napoli v Torino', competition: 'Serie A', league_id: null,
    ko_at: new Date(Date.now() - 1800_000).toISOString(), mode: 'paper', markets: { OU35: { market_id: '1.2' }, OU45: { market_id: '1.3' } },
    state: 'LIVE_COVERED', cycle_no: 1, entry_price_initial: 1.5,
    dossier: { p4_pre: 0.14, lambda_home: 1.6, lambda_away: 0.9 },
    live: {
        inplay: true, minute: 31, goals: 1, score_home: 1, score_away: 0, red_home: 0, red_away: 1, ht: false,
        hazard: 0.11, hazard_atlas: 0.09, hazard_model: 0.11, pressure: 1.2, p4_market: 0.15, p4_model: 0.14,
        feed_age_s: 90, scanner_age_s: 2, lines_missing: ['OU45|UNDER'], reconcile_pending: true, no_reentry: true,
        liability: 12.26, locked: -0.4, total_matched: 18400, ht_score: [1, 0],
        cashout: { net: 0.5, gross: 0.55, base: 12.26, complete: true, pct: 4.1, target_pct: 5,
                   per: { 'OU35|UNDER': -1.28, 'OU45|OVER': 1.78 }, per_gross: { 'OU35|UNDER': -1.28, 'OU45|OVER': 1.87 },
                   decided: [], commission: 0.05,
                   smart: { enabled: true, floor: 0.25, near: true, hot: true, ev_hold: 0.31, trigger: 'hot_near' } },
        cover_wait: { hazard: 0.04, p4: 0.1, until_min: 10 }, cover_gain_pct: 9,
        pnl_by_total: { '0': 4.75, '4': -12.26, '5': 2 },
        loss_exit: { mode: 'model', window: '2t', ev_hold: -0.79, p4: 0.22, premium: 2.64, threshold: -3.43, sources: ['model', 'emp'] },
        books: { 'OU35|UNDER': book({ best_back: 1.7, best_lay: 1.72, inplay: true, bet_delay: 5 }),
                 'OU45|OVER': book({ best_back: 4.2, best_lay: 4.4, inplay: true, bet_delay: 5 }) },
        feed_fresh: false,
    },
    positions: [{ role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10, matched: 10,
                  avg_price: 1.5, ref: 'under_entry-0-1', status: 'open', placed_at: 0, persistence: 'LAPSE', cycle_no: 0,
                  final: false, archived: false },
                { role: 'over_cover', market: 'OU45', selection: 'OVER', side: 'back', price: 6.6, size: 2.26, matched: 2.26,
                  avg_price: 6.6, ref: 'over_cover-0-2', status: 'open', placed_at: 0, persistence: 'LAPSE', cycle_no: 0,
                  final: false, archived: false },
                { role: 'under_green', market: 'OU35', selection: 'UNDER', side: 'lay', price: 1.44, size: 10.4, matched: 0,
                  avg_price: null, ref: 'under_green-0-3', status: 'pending', placed_at: 0, persistence: 'LAPSE', cycle_no: 1,
                  final: false, archived: false }],
    ctx: { selections: { 'OU35|UNDER': 1222344, 'OU45|OVER': 1222346 } }, skipped: false, settled_pnl: null, updated_at: NOW,
};

/** pre-match senza posizione, KO più tardi: serve a controllare l'ordine */
const PRE_LATE = {
    ...PRE, event_id: 'e3', event_name: 'Milan v Inter', state: 'WATCH',
    ko_at: new Date(Date.now() + 7200_000).toISOString(), entry_price_initial: null,
    dossier: {}, live: { inplay: false, feed_age_s: 2, lines_missing: [], books: {}, pnl_by_total: {} },
    positions: [], ctx: {},
};

const ERRORED = {
    ...PRE, event_id: 'e4', event_name: 'Genoa v Empoli', state: 'ERROR',
    ko_at: new Date(Date.now() + 1800_000).toISOString(), positions: [], live: { inplay: false, feed_age_s: 4, books: {}, pnl_by_total: {} },
};
const SKIPPED = {
    ...PRE, event_id: 'e5', event_name: 'Parma v Como', state: 'SKIPPED', skipped: true,
    ko_at: new Date(Date.now() + 2700_000).toISOString(), positions: [], live: { inplay: false, feed_age_s: 4, books: {}, pnl_by_total: {} },
};

const TRADES = [
    { id: 10, event_id: 'e1', event_name: 'Roma v Lazio', strategy: 'mike', role: 'under_entry', cycle_no: 0,
      market_type: 'OVER_UNDER_35', selection_name: 'Under 3.5', side: 'back', mode: 'paper', price: 1.5, size: 10,
      liability: 10, status: 'won', pnl: 4.75, placed_at: NOW, settled_at: NOW, signal_key: null,
      meta: { pnl_gross: 5, commission_paid: 0.25 }, closes_trade_id: null, day_placed_at: NOW },
    { id: 11, event_id: 'e1', event_name: 'Roma v Lazio', strategy: 'mike', role: 'under_green', cycle_no: 0,
      market_type: 'OVER_UNDER_35', selection_name: 'Under 3.5', side: 'lay', mode: 'live', price: 1.48, size: 10.14,
      liability: 4.87, status: 'lost', pnl: -4.62, placed_at: NOW, settled_at: NOW, signal_key: null,
      meta: { exit_kind: 'greenup', exit_reason: 'green-up a +2 tick' }, closes_trade_id: 10, day_placed_at: NOW },
];

const ACTIVITY = [
    { id: 1, ts: NOW, event_id: 'e1', kind: 'armed', payload: { ko: NOW } },
    { id: 2, ts: NOW, event_id: 'e2', kind: 'feed_line_missing', payload: { markets: ['OU45|UNDER'], state: 'LIVE_COVERED' } },
    { id: 3, ts: NOW, event_id: 'e2', kind: 'fill_resting', payload: { role: 'under_green', size: 10.4, price: 1.44 } },
    { id: 4, ts: NOW, event_id: 'e2', kind: 'reconcile_pending', payload: { leg: 'over_cover-0-2', critical: true } },
];

const REQUESTS = [
    { id: 5, kind: 'cashout', payload: { event_id: 'e2' }, status: 'rejected',
      result: { code: 'feed_stantio', message: 'Feed stantio: cash out rifiutato.' },
      created_at: NOW, updated_at: NOW },
];

function state(over: Record<string, unknown> = {}) {
    return {
        control: CONTROL, events: [PRE, LIVE, PRE_LATE], trades: TRADES, activity: ACTIVITY,
        aggregates: AGGREGATES, requests: REQUESTS, day_start: DAY_START, day_by: 'placed', ...over,
    } as never;
}

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter><Mike /></MemoryRouter>
        </HelmetProvider>,
    );
}

function cardOrder(): string[] {
    return screen.getAllByTestId('mike-match-card').map((c) => c.getAttribute('data-event-id') ?? '');
}

describe('Mike page — sezioni e schede ferme', () => {
    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue(state());
    });
    afterEach(() => { vi.useRealTimers(); });

    it('due sezioni fisse: PRE-MATCH per KO crescente, poi LIVE', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT IN CORSA'));
        expect(screen.getByTestId('mike-section-pre')).toHaveTextContent('PRE-MATCH (2)');
        expect(screen.getByTestId('mike-section-live')).toHaveTextContent('LIVE (1)');
        // ordine globale: le due pre-match (KO +1h, +2h) e poi la live
        expect(cardOrder()).toEqual(['e1', 'e3', 'e2']);
        const pre = within(screen.getByTestId('mike-cards-pre')).getAllByTestId('mike-match-card');
        expect(pre[0]).toHaveTextContent('Roma v Lazio');
        expect(pre[1]).toHaveTextContent('Milan v Inter');
        expect(within(screen.getByTestId('mike-cards-live')).getAllByTestId('mike-match-card')[0])
            .toHaveTextContent('Napoli v Torino');
    });

    it('le schede NON si muovono quando cambiano fase (e il realtime è debounced)', async () => {
        let notify: (() => void) | null = null;
        mSubscribe.mockImplementation((cb: (t?: string) => void) => { notify = cb as () => void; return () => {}; });
        vi.useFakeTimers({ shouldAdvanceTime: true });
        renderPage();
        await waitFor(() => expect(screen.getAllByTestId('mike-match-card')).toHaveLength(3));
        expect(cardOrder()).toEqual(['e1', 'e3', 'e2']);
        const callsBefore = mState.mock.calls.length;

        // il servizio cambia fase a tutte e tre (e la live perde `inplay`)
        mState.mockResolvedValue(state({
            events: [
                { ...PRE, state: 'PRE_GREEN_PENDING', updated_at: new Date().toISOString() },
                { ...LIVE, state: 'LIVE_CLOSING', live: { ...LIVE.live, inplay: false }, updated_at: new Date().toISOString() },
                { ...PRE_LATE, state: 'PRE_ENTRY_PENDING', updated_at: new Date().toISOString() },
            ],
        }));
        // dieci notifiche ravvicinate = UNA sola ricarica
        await act(async () => {
            for (let i = 0; i < 10; i += 1) notify?.();
            await vi.advanceTimersByTimeAsync(1_600);
        });
        await waitFor(() => expect(screen.getByTestId('mike-section-live')).toHaveTextContent('LIVE (1)'));
        expect(mState.mock.calls.length).toBe(callsBefore + 1);
        // stesso ordine, e la partita che era in gioco RESTA nella sezione LIVE
        expect(cardOrder()).toEqual(['e1', 'e3', 'e2']);
        expect(screen.getByTestId('mike-section-pre')).toHaveTextContent('PRE-MATCH (2)');
    });

    it('ERROR e SKIPPED finiscono in DA SISTEMARE con il bottone Riprendi (H6)', async () => {
        mState.mockResolvedValue(state({ events: [PRE, ERRORED, SKIPPED] }));
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-section-fix')).toBeInTheDocument());
        const fix = screen.getByTestId('mike-cards-fix');
        expect(fix).toHaveTextContent('Genoa v Empoli');
        expect(fix).toHaveTextContent('Parma v Como');
        expect(within(fix).getAllByTestId('mike-resume-btn')).toHaveLength(2);
        expect(screen.getByTestId('mike-section-fix')).toHaveTextContent('DA SISTEMARE (2)');
    });

    it('la richiesta parte dal bottone Riprendi', async () => {
        mState.mockResolvedValue(state({ events: [ERRORED] }));
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-resume-btn')).toBeEnabled());
        await userEvent.click(screen.getByTestId('mike-resume-btn'));
        await waitFor(() => expect(mRequest).toHaveBeenCalledWith('resume_event', { event_id: 'e4' }));
    });
});

describe('Mike page — profondità dei dati sulla card', () => {
    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue(state());
    });

    it('pre-match: λ, P(4) modello e mercato, istogramma dei gol, quote con size e scambiato', async () => {
        renderPage();
        const card = (await screen.findAllByTestId('mike-match-card'))[0];
        expect(within(card).getByTestId('mike-lambda')).toHaveTextContent('1,40 / 1,10');
        expect(within(card).getByTestId('mike-model')).toHaveTextContent('14,0 %');   // P(4) modello (dossier)
        expect(within(card).getByTestId('mike-model')).toHaveTextContent('12,0 %');   // P(4) mercato
        expect(within(card).getByTestId('mike-goals-histogram')).toHaveTextContent('modello');
        expect(within(card).getByTestId('mike-quote-ou35')).toHaveTextContent('1,47');
        expect(within(card).getByTestId('mike-meta-line')).toHaveTextContent('scambiato 4200 €');
        expect(within(card).getByTestId('mike-countdown')).toBeInTheDocument();
    });

    it('live: punteggio, espulsioni, hazard, pressione, uscita a modello, attesa copertura, allarmi', async () => {
        renderPage();
        const card = (await screen.findAllByTestId('mike-match-card')).find((c) => c.getAttribute('data-event-id') === 'e2')!;
        expect(within(card).getByTestId('mike-score')).toHaveTextContent('1–0');
        expect(within(card).getByTestId('mike-score')).toHaveTextContent('0/1');
        expect(within(card).getByTestId('mike-pressure')).toHaveTextContent('×1,20 🔥');
        expect(within(card).getByTestId('mike-model')).toHaveTextContent('11,0 %');
        expect(within(card).getByTestId('mike-loss-exit'))
            .toHaveTextContent('uscita 2t a modello: tenere vale −0,79 € · P(4) 22 % · premio 2,64 € · → chiude');
        expect(within(card).getByTestId('mike-cashout-smart')).toHaveTextContent('a un passo dal 5%');
        expect(within(card).getByTestId('mike-cover-wait')).toHaveTextContent('attende quota migliore');
        // allarmi: linea assente, ordine in verifica, nessun rientro, feed fermo
        expect(within(card).getByTestId('mike-lines-missing')).toHaveTextContent('Under 4.5');
        expect(within(card).getByTestId('mike-reconcile')).toHaveTextContent('ORDINE IN VERIFICA SU BETFAIR');
        expect(within(card).getByTestId('mike-no-reentry')).toHaveTextContent('NESSUN RIENTRO');
        expect(within(card).getByTestId('mike-feed-age')).toHaveTextContent('FEED FERMO');
        // liability NETTA e bloccato dal servizio
        expect(within(card).getByTestId('mike-liability')).toHaveTextContent('12,26 €');
        expect(within(card).getByTestId('mike-locked')).toHaveTextContent('−0,40 €');
        // P&L per gol totali, con i 4 gol presenti
        expect(within(card).getByTestId('pnl-total-4')).toHaveTextContent('−12,26 €');
    });

    it('posizioni: "se chiudo ora" è il NETTO del servizio, ordini sul book a parte', async () => {
        renderPage();
        const card = (await screen.findAllByTestId('mike-match-card')).find((c) => c.getAttribute('data-event-id') === 'e2')!;
        const rows = within(card).getAllByTestId('mike-pos-row');
        expect(rows).toHaveLength(2);
        expect(rows[0]).toHaveTextContent('Under 3.5');
        expect(within(rows[0]).getByTestId('mike-pos-locked')).toHaveTextContent('−1,28 €');
        expect(within(rows[1]).getByTestId('mike-pos-locked')).toHaveTextContent('+1,78 €');
        // la lay appoggiata non abbinata è un ORDINE, non una posizione
        const orders = within(card).getAllByTestId('mike-order-row');
        expect(orders).toHaveLength(1);
        expect(orders[0]).toHaveTextContent('Green-up Under 3.5');
        expect(orders[0]).toHaveTextContent('SUL BOOK');
    });

    it('cash out spento CON MOTIVO quando il feed della partita è fermo, ed esito della richiesta visibile (M1)', async () => {
        renderPage();
        const card = (await screen.findAllByTestId('mike-match-card')).find((c) => c.getAttribute('data-event-id') === 'e2')!;
        expect(within(card).getByTestId('mike-cashout-btn')).toBeDisabled();
        expect(within(card).getByTestId('mike-cashout-off-reason')).toHaveTextContent('Feed di questa partita fermo');
        expect(within(card).getByTestId('mike-request-outcome'))
            .toHaveTextContent('Cash out rifiutato: Feed stantio: cash out rifiutato.');
        // la card pre-match, con feed fresco, ha il cash out ATTIVO col netto del servizio
        const pre = (await screen.findAllByTestId('mike-match-card')).find((c) => c.getAttribute('data-event-id') === 'e1')!;
        expect(within(pre).getByTestId('mike-cashout-btn')).toBeEnabled();
        expect(within(pre).getByTestId('mike-cashout-btn')).toHaveTextContent('+0,35 €');
        expect(within(pre).getByTestId('mike-cashout-value')).toHaveTextContent('3,5 % · soglia 5,0 %');
    });
});

describe('Mike page — tab Trade, Attività, Regolate, KPI', () => {
    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue(state());
    });

    it('KPI e giornata operativa leggono gli aggregati del DB', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('kpi-row')).toBeInTheDocument());
        expect(screen.getByTestId('mike-kpi-matches')).toHaveTextContent('2 pre-match · 1 live');
        expect(screen.getByTestId('day-bar')).toHaveTextContent('partite 2');
        expect(screen.getByTestId('day-bar')).toHaveTextContent('operazioni 4');
        expect(screen.getByTestId('day-bar-liability')).toHaveTextContent('12,50 €');
        expect(screen.getByTestId('mike-kpi-locked')).toHaveTextContent('−0,27 €');
    });

    it('tab Trade: chiusure annidate, uscita, LIVE, P&L netto del ciclo e toggle della giornata', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await userEvent.click(screen.getByRole('tab', { name: /Trade/ }));
        const table = await screen.findByTestId('mike-trades-table');
        const opens = within(table).getAllByTestId('mike-trade-row');
        expect(opens).toHaveLength(1);
        expect(opens[0]).toHaveTextContent('Ingresso Under 3.5');
        // il P&L della riga di apertura è il NETTO del ciclo (apertura + chiusure)
        expect(within(opens[0]).getByTestId('mike-trade-pnl')).toHaveTextContent('+0,13 €');
        const closes = within(table).getAllByTestId('mike-trade-close');
        expect(closes).toHaveLength(1);
        expect(closes[0]).toHaveTextContent('Green-up Under 3.5');
        expect(within(closes[0]).getByTestId('exit-badge')).toBeInTheDocument();
        expect(closes[0]).toHaveTextContent('LAY');
        expect(screen.getByTestId('mike-trades')).toHaveTextContent('giornata operativa');
        await userEvent.click(screen.getByTestId('mike-trades-toggle'));
        expect(screen.getByTestId('mike-trades')).toHaveTextContent('Tutti i trade caricati');
        expect(screen.getByTestId('equity-card')).toBeInTheDocument();
    });

    it('tab Attività: ogni kind in italiano, i critici in rosso, filtro per partita', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await userEvent.click(screen.getByRole('tab', { name: /Attività/ }));
        const rows = await screen.findAllByTestId('mike-activity-row');
        expect(rows).toHaveLength(4);
        expect(rows[0]).toHaveTextContent('ARMATA');
        expect(rows[1]).toHaveTextContent('LINEA ASSENTE NEL FEED');
        expect(rows[1]).toHaveTextContent('Under 4.5');
        expect(rows[1]).toHaveAttribute('data-critical', '1');
        expect(rows[2]).toHaveTextContent('APPOGGIATA ABBINATA');
        expect(rows[3]).toHaveTextContent('ORDINE IN VERIFICA');
        expect(screen.getByTestId('activity-filter')).toBeInTheDocument();
    });

    it('tab Regolate: solo le partite regolate, senza azioni', async () => {
        mState.mockResolvedValue(state({
            events: [PRE, { ...LIVE, state: 'SETTLED', settled_pnl: 4.51 }],
        }));
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await userEvent.click(screen.getByRole('tab', { name: /Regolate/ }));
        const settled = await screen.findByTestId('mike-cards-settled');
        const cards = within(settled).getAllByTestId('mike-match-card');
        expect(cards).toHaveLength(1);
        expect(cards[0]).toHaveTextContent('Napoli v Torino');
        expect(cards[0]).toHaveTextContent('+4,51 €');
        expect(within(cards[0]).queryByTestId('mike-cashout-btn')).toBeNull();
    });

    it('KPI Liability: dichiara "stimata dalle righe" e "dato stantio"', async () => {
        mState.mockResolvedValue(state({
            aggregates: { ...AGGREGATES, liability_source: 'rows_sum', liability_stale: true,
                          heartbeat_at: new Date(Date.now() - 120_000).toISOString() },
        }));
        renderPage();
        const sub = await screen.findByTestId('mike-liability-sub');
        expect(sub).toHaveTextContent('stimata dalle righe');
        expect(sub).toHaveTextContent('dato stantio');
        expect(sub).toHaveTextContent('di cui 1 in verifica');
    });

    it('KPI Liability: con la liability netta del servizio non dichiara nulla di strano', async () => {
        mState.mockResolvedValue(state({
            aggregates: { ...AGGREGATES, liability_source: 'net_positions', liability_stale: false },
        }));
        renderPage();
        const sub = await screen.findByTestId('mike-liability-sub');
        expect(sub).not.toHaveTextContent('stimata dalle righe');
        expect(sub).not.toHaveTextContent('dato stantio');
        expect(sub).toHaveTextContent('stop giornaliero');
    });

    it('tab Trade: nota del tetto di 500 righe, ✋ sulle chiusure manuali e VOID per mercato', async () => {
        const many = Array.from({ length: 500 }, (_, i) => ({
            ...TRADES[0], id: 1000 + i, closes_trade_id: null,
            status: i === 0 ? 'void' : 'won',
            market_type: i === 0 ? 'OVER_UNDER_35' : 'OVER_UNDER_45',
            selection_name: i === 0 ? 'Under 3.5' : 'Over 4.5',
            meta: i === 0 ? { void_reason: 'mercato_annullato' } : { exit_kind: 'manual' },
            origin: i === 0 ? 'auto' : 'manual',
        }));
        mState.mockResolvedValue(state({ trades: many }));
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await userEvent.click(screen.getByRole('tab', { name: /Trade/ }));
        expect(await screen.findByTestId('mike-trades-capped')).toHaveTextContent('mostrate le ultime 500');
        const rows = screen.getAllByTestId('mike-trade-row');
        // VOID dichiarato sulla SOLA gamba del mercato annullato
        expect(within(rows[0]).getByTestId('mike-trade-status')).toHaveTextContent('VOID (Under 3.5)');
        // ✋ sulle righe decise dall'utente
        expect(within(rows[1]).getByLabelText('manuale')).toBeInTheDocument();
        expect(within(rows[1]).getByTestId('mike-trade-status')).not.toHaveTextContent('VOID');
    });

    it('senza migrazione la pagina resta leggibile', async () => {
        mState.mockResolvedValue({ control: null, events: [], trades: [], activity: [], aggregates: null,
                                   requests: [], day_start: null, day_by: null } as never);
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-mode-banner')).toHaveTextContent('mike_bot.sql'));
        expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT INATTIVO');
    });
});

// ===========================================================================
// Checklist 2 — Avvia / Ferma / PAPER-LIVE (+dialog) / Salva parametri:
// quale RPC parte e con quali argomenti.
// ===========================================================================
describe('Mike page — Avvia, Ferma, modalità, parametri', () => {
    beforeEach(() => {
        mState.mockReset();
        mActivate.mockReset();
        mStop.mockReset();
        mSaveParams.mockReset();
    });

    it('con il bot in corsa "Ferma" chiama mike_stop', async () => {
        mState.mockResolvedValue(state());
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT IN CORSA'));
        expect(screen.queryByTestId('bot-start')).toBeNull();
        await userEvent.click(screen.getByTestId('bot-stop'));
        await waitFor(() => expect(mStop).toHaveBeenCalledTimes(1));
        expect(mActivate).not.toHaveBeenCalled();
    });

    it('con il bot fermo "Avvia" chiama mike_activate in PAPER (paper-first)', async () => {
        mState.mockResolvedValue(state({ control: { ...CONTROL, status: 'stopped' } }));
        renderPage();
        await waitFor(() => expect(screen.getByTestId('bot-start')).toBeEnabled());
        expect(screen.queryByTestId('bot-stop')).toBeNull();
        await userEvent.click(screen.getByTestId('bot-start'));
        await waitFor(() => expect(mActivate).toHaveBeenCalledWith('paper'));
        expect(mStop).not.toHaveBeenCalled();
    });

    it('il passaggio a LIVE chiede CONFERMA e solo dopo attiva il bot a soldi veri', async () => {
        mState.mockResolvedValue(state());
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT IN CORSA'));
        await userEvent.click(within(screen.getByTestId('mode-toggle')).getByText(/LIVE/));
        const dialog = await screen.findByTestId('live-confirm');
        // nessuna attivazione finché non si conferma
        expect(mActivate).not.toHaveBeenCalled();
        expect(dialog).toHaveTextContent('denaro reale');
        expect(dialog).toHaveTextContent('esattamente 4 gol');
        await userEvent.click(screen.getByTestId('live-confirm-ok'));
        await waitFor(() => expect(mActivate).toHaveBeenCalledWith('live'));
    });

    it('Salva parametri manda l’oggetto intero a mike_update_params', async () => {
        mState.mockResolvedValue(state());
        const user = userEvent.setup();
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await user.click(screen.getByTestId('mike-params-trigger'));
        await screen.findByTestId('params-sheet');
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mSaveParams).toHaveBeenCalledTimes(1));
        const sent = mSaveParams.mock.calls[0][0] as Record<string, unknown>;
        expect(sent.stake).toBe(10);
        expect(sent.cashout_profit_pct).toBe(5);
        expect(sent).not.toHaveProperty('mode');
    });
});

// ===========================================================================
// Checklist 4 — SCHEDE FISSE: 6 partite, 3 ricariche con stati diversi.
// L'ordine delle card NON cambia se non per il passaggio PRE -> LIVE, e nessuna
// zona di dati sparisce quando compaiono posizioni od ordini.
// ===========================================================================
describe('Mike page — sei schede, tre ricariche, nessun salto', () => {
    const SIX = [1, 2, 3, 4, 5, 6].map((i) => ({
        ...PRE_LATE,
        event_id: `s${i}`,
        event_name: `Squadra ${i}A v Squadra ${i}B`,
        ko_at: new Date(Date.now() + i * 600_000).toISOString(),
        state: 'PRE_OPEN',
        positions: [],
        live: { inplay: false, feed_age_s: 2, lines_missing: [], books: {}, pnl_by_total: {} },
    }));

    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue(state({ events: SIX }));
    });
    afterEach(() => { vi.useRealTimers(); });

    it('PRE_OPEN → HOLD → LIVE_COVERED → FLAT: si muove SOLO chi entra in gioco', async () => {
        let notify: (() => void) | null = null;
        mSubscribe.mockImplementation((cb: (t?: string) => void) => { notify = cb as () => void; return () => {}; });
        vi.useFakeTimers({ shouldAdvanceTime: true });
        renderPage();
        await waitFor(() => expect(screen.getAllByTestId('mike-match-card')).toHaveLength(6));
        const ordine = ['s1', 's2', 's3', 's4', 's5', 's6'];
        expect(cardOrder()).toEqual(ordine);
        expect(screen.getByTestId('mike-section-pre')).toHaveTextContent('PRE-MATCH (6)');

        const tick = async (events: unknown[]) => {
            mState.mockResolvedValue(state({ events }));
            await act(async () => { notify?.(); await vi.advanceTimersByTimeAsync(1_600); });
        };
        const stamp = (ms: number) => new Date(Date.now() + ms).toISOString();

        // giro 1 — tutte in HOLD: fase cambiata, nessuna in gioco, ordine identico
        await tick(SIX.map((e) => ({ ...e, state: 'HOLD', updated_at: stamp(1_000) })));
        await waitFor(() => expect(screen.getByTestId('mike-section-pre')).toHaveTextContent('PRE-MATCH (6)'));
        expect(cardOrder()).toEqual(ordine);

        // giro 2 — le prime due entrano in gioco con posizione e copertura aperte
        const inGioco = (e: typeof SIX[number]) => ({
            ...e,
            state: 'LIVE_COVERED',
            updated_at: stamp(2_000),
            positions: LIVE.positions,
            live: { ...LIVE.live, feed_age_s: 2, feed_fresh: true, lines_missing: [] },
        });
        await tick([
            inGioco(SIX[0]), inGioco(SIX[1]),
            ...SIX.slice(2).map((e) => ({ ...e, state: 'HOLD', updated_at: stamp(2_000) })),
        ]);
        await waitFor(() => expect(screen.getByTestId('mike-section-live')).toHaveTextContent('LIVE (2)'));
        // unica variazione ammessa: le due in gioco passano nella sezione LIVE
        expect(cardOrder()).toEqual(['s3', 's4', 's5', 's6', 's1', 's2']);
        expect(within(screen.getByTestId('mike-cards-pre')).getAllByTestId('mike-match-card')
            .map((c) => c.getAttribute('data-event-id'))).toEqual(['s3', 's4', 's5', 's6']);
        // altezza stabile: le zone di dati sono montate su TUTTE le card, anche
        // quelle senza posizioni e senza ordini
        for (const card of screen.getAllByTestId('mike-match-card')) {
            for (const zone of ['mike-score', 'mike-alerts', 'mike-model', 'mike-goals-histogram',
                                'mike-quotes', 'mike-meta-line', 'mike-positions', 'mike-orders',
                                'mike-pnl-by-total', 'mike-cashout-smart', 'mike-loss-exit',
                                'mike-cover-wait']) {
                expect(within(card).getByTestId(zone),
                    `${card.getAttribute('data-event-id')} ${zone}`).toBeInTheDocument();
            }
        }

        // giro 3 — le due in gioco chiudono (FLAT) e perdono `inplay`: NON tornano in PRE
        await tick([
            { ...inGioco(SIX[0]), state: 'FLAT', positions: [], live: { ...LIVE.live, inplay: false }, updated_at: stamp(3_000) },
            { ...inGioco(SIX[1]), state: 'FLAT', positions: [], live: { ...LIVE.live, inplay: false }, updated_at: stamp(3_000) },
            ...SIX.slice(2).map((e) => ({ ...e, state: 'PRE_OPEN', updated_at: stamp(3_000) })),
        ]);
        await waitFor(() => expect(screen.getByTestId('mike-section-pre')).toHaveTextContent('PRE-MATCH (4)'));
        expect(screen.getByTestId('mike-section-live')).toHaveTextContent('LIVE (2)');
        expect(cardOrder()).toEqual(['s3', 's4', 's5', 's6', 's1', 's2']);
    });

    it('KO passato ma partita non ancora iniziata: resta in PRE-MATCH e lo dice', async () => {
        mState.mockResolvedValue(state({
            events: [{ ...SIX[0], state: 'HOLD', ko_at: new Date(Date.now() - 120_000).toISOString() }],
        }));
        renderPage();
        await waitFor(() => expect(screen.getAllByTestId('mike-match-card')).toHaveLength(1));
        expect(screen.getByTestId('mike-section-pre')).toHaveTextContent('PRE-MATCH (1)');
        expect(screen.getByTestId('mike-awaiting-kickoff')).toHaveTextContent('in attesa del fischio');
    });

    it('una partita appena ARMATA (senza live) va in PRE-MATCH', async () => {
        mState.mockResolvedValue(state({ events: [{ ...SIX[0], state: 'WATCH', live: null }] }));
        renderPage();
        await waitFor(() => expect(screen.getAllByTestId('mike-match-card')).toHaveLength(1));
        expect(screen.getByTestId('mike-section-pre')).toHaveTextContent('PRE-MATCH (1)');
        expect(screen.getByTestId('mike-live-empty')).toBeInTheDocument();
    });
});

// ===========================================================================
// Checklist 9 — RPC v1 (senza `requests` / `day_start` / `day_by`): la pagina
// funziona, i KPI ripiegano su `control.stats`, la giornata lo DICHIARA.
// ===========================================================================
describe('Mike page — RPC v1, senza migrazione mike_bot_v2', () => {
    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue({
            control: CONTROL, events: [PRE], trades: TRADES, activity: ACTIVITY,
            aggregates: null, requests: [], day_start: null, day_by: null,
        } as never);
    });

    it('la pagina resta leggibile e i KPI vengono da control.stats', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toHaveTextContent('BOT IN CORSA'));
        expect(screen.getAllByTestId('mike-match-card')).toHaveLength(1);
        // liability dai `stats` del servizio (12,50) e nessun banner di tabelle assenti
        expect(screen.getByTestId('mike-liability-sub')).toBeInTheDocument();
        expect(screen.getAllByText('12,50 €').length).toBeGreaterThan(0);
        expect(screen.getByTestId('mike-mode-banner')).not.toHaveTextContent('mike_bot.sql');
    });

    it('tab Trade: senza giornata dal DB lo dichiara e mostra tutte le righe', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await userEvent.click(screen.getByRole('tab', { name: /Trade/ }));
        await waitFor(() => expect(screen.getByTestId('mike-trades-noday')).toBeInTheDocument());
        expect(screen.getByTestId('mike-trades-noday')).toHaveTextContent('mike_bot_v2.sql');
    });
});

// ===========================================================================
// Checklist 8 — storico: errore LEGGIBILE senza mike_history_v2.sql
// ===========================================================================
describe('Mike page — storico senza migrazione', () => {
    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue(state());
        mDaily.mockReset();
    });
    afterEach(() => { mDaily.mockResolvedValue([]); });

    it('non mostra "is not unique" nudo ma dice quale migrazione applicare', async () => {
        mDaily.mockRejectedValue(new Error('function public.trading_daily_history(unknown) is not unique'));
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await userEvent.click(screen.getByRole('tab', { name: /Storico/ }));
        await waitFor(() => expect(screen.getByText(/mike_history_v2\.sql/)).toBeInTheDocument());
    });
});

// ===========================================================================
// Tab Trade -> scheda della partita (il cash out di Mike e' per EVENTO)
// ===========================================================================
describe('Mike page — dalla tabella Trade alla scheda', () => {
    beforeEach(() => {
        mState.mockReset();
        mState.mockResolvedValue(state({
            trades: [{ ...TRADES[0], id: 20, status: 'open', pnl: 0, settled_at: null, closes_trade_id: null }],
        }));
    });

    it('la riga di una posizione APERTA porta al tab Partite e alla card', async () => {
        renderPage();
        await waitFor(() => expect(screen.getByTestId('mike-status')).toBeInTheDocument());
        await userEvent.click(screen.getByRole('tab', { name: /Trade/ }));
        const link = await screen.findByTestId('mike-trade-goto-card');
        expect(link).toHaveAttribute('data-event-id', 'e1');
        await userEvent.click(link);
        await waitFor(() => expect(screen.getByTestId('mike-cards')).toBeInTheDocument());
        expect(screen.getAllByTestId('mike-match-card')
            .some((c) => c.getAttribute('data-event-id') === 'e1')).toBe(true);
    });
});
