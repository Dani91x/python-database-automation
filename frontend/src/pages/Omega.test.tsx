// Test COMPONENTE per la dashboard Omega. Data-layer e sonner mockati.
// Verifica: header/stato, barra obiettivo (realizzato/goal), KPI, riga trade.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

// Il tab MISSIONE (default) ha il suo data-layer: qui stub — è testato a parte
// in lib/omegaMissions.test.ts.
vi.mock('@/components/omega/MissionPanel', () => ({
    default: () => <div data-testid="mission-panel-stub" />,
}));

// feed live mutabile per i test del cash out (book della selezione laid)
const liveState = vi.hoisted(() => ({ feed: {} as Record<string, unknown>, label: null as string | null }));
vi.mock('@/lib/useScanLiveFeed', () => ({
    useScanLiveFeed: () => liveState.feed,
    liveScoreLabel: (p: unknown) => (p ? liveState.label : null),
}));
vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig<typeof import('@/lib/omega')>()),
    fetchOmegaState: vi.fn(),
    fetchOmegaTrades: vi.fn(),
    subscribeOmega: vi.fn(() => () => {}),
    activateOmega: vi.fn(),
    stopOmega: vi.fn(),
    updateOmegaParams: vi.fn(),
    requestManual: vi.fn(),
    fetchOmegaEvents: vi.fn(async () => []),
    fetchOmegaMarket: vi.fn(async () => null),
    fetchManualRequests: vi.fn(async () => []),
    buildEquitySeries: () => [],
    phaseLabel: (p: string | null | undefined) => (p === 'ht_cs' ? '1T' : p === 'ft_cs' ? '2T' : '—'),
    OMEGA_PARAM_FIELDS: [],
}));

import Omega from './Omega';
import { fetchOmegaState, fetchOmegaTrades } from '@/lib/omega';

const mState = vi.mocked(fetchOmegaState);
const mTrades = vi.mocked(fetchOmegaTrades);

const CONTROL = {
    id: 1, status: 'running', mode: 'paper', daily_goal: 250, params: {},
    stats: {
        events_total: 42, matches_traded: 3, matches_open: 1, realized_profit: 60,
        open_liability: 480, matches_remaining: 20, target_match: 9.5, goal: 250,
        goal_pct: 24, last_cycle: new Date().toISOString(),
    },
    error: null, started_at: null, stopped_at: null, heartbeat_at: null, updated_at: new Date().toISOString(),
};

const TRADES = [
    {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', market_id: '1.1', selection_id: 4,
        runner_name: '3 - 2', side: 'lay', mode: 'paper', price: 110, size: 5.26, liability: 573.34,
        target: 5, minute_at_entry: 42, score_at_entry: '0-0', kickoff: null, status: 'open',
        pnl: 0, bet_id: null, placed_at: new Date().toISOString(), settled_at: null, meta: {},
    },
];

// book live della selezione laid (3-2 @110): back 100 / lay 120
const FEED_WITH_BOOK = {
    e1: {
        minute: 60, score_home: 0, score_away: 0,
        cs: { market_id: '1.1', status: 'OPEN', selections: [{ selection_id: 4, name: '3 - 2', back: 100, lay: 120 }] },
    },
};

beforeEach(() => {
    vi.clearAllMocks();
    liveState.feed = {};
    liveState.label = null;
    mState.mockResolvedValue({ control: CONTROL as never, aggregates: null, activity: [] });
    mTrades.mockResolvedValue(TRADES as never);
});

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <Omega />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

// Il default è il tab MISSIONE: per i contenuti della dashboard automatica
// bisogna prima cliccare "⚙️ Automatico".
async function gotoAutoTab() {
    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: /Automatico/ }));
}

describe('Omega dashboard', () => {
    it('mostra header OMEGA e stato IN CORSA', async () => {
        renderPage();
        expect(await screen.findByText('OMEGA')).toBeInTheDocument();
        expect(await screen.findByText('IN CORSA')).toBeInTheDocument();
    });

    it('il tab Missione è il default e monta il pannello', async () => {
        renderPage();
        expect(await screen.findByTestId('mission-panel-stub')).toBeInTheDocument();
    });

    it('barra obiettivo mostra realizzato e goal', async () => {
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByText('Obiettivo giornaliero')).toBeInTheDocument();
        // +€60.00 compare sia nella barra obiettivo sia nel KPI "P&L realizzato"
        expect((await screen.findAllByText('+€60.00')).length).toBeGreaterThanOrEqual(1);
        expect(await screen.findByText(/€250\.00/)).toBeInTheDocument();
    });

    it('KPI target/match e liability aperta presenti', async () => {
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByText('Target / match')).toBeInTheDocument();
        expect(await screen.findByText('€9.50')).toBeInTheDocument();
        expect(await screen.findByText('Liability aperta')).toBeInTheDocument();
        expect(await screen.findByText('€480.00')).toBeInTheDocument();
    });

    it('elenca il trade piazzato con il punteggio laid', async () => {
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByText('Roma vs Lazio')).toBeInTheDocument();
        expect(await screen.findByText('3 - 2')).toBeInTheDocument();
        expect(await screen.findByText('APERTO')).toBeInTheDocument();
    });

    it('mostra il pulsante Ferma quando è in corsa', async () => {
        renderPage();
        expect(await screen.findByText('Ferma')).toBeInTheDocument();
    });
});

describe('Omega — cash out', () => {
    it('CRITICAL-2: la conferma usa la modalità del TRADE, non quella della pagina', async () => {
        liveState.feed = FEED_WITH_BOOK;
        // pagina in PAPER (control.mode) ma trade piazzato in LIVE
        mTrades.mockResolvedValue([{ ...TRADES[0], mode: 'live' }] as never);
        renderPage();
        await gotoAutoTab();
        const user = userEvent.setup();
        const trigger = await screen.findByTestId('cashout-trigger');
        expect(trigger).toBeEnabled();
        await user.click(trigger);
        expect(await screen.findByText(/Modalità LIVE: soldi veri/)).toBeInTheDocument();
        // doppia conferma richiesta (soldi veri) anche se la pagina è in paper
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(screen.getByTestId('cashout-confirm')).toHaveTextContent(/Confermi/);
    });

    it('CRITICAL-2 (inverso): pagina LIVE ma trade paper -> nessuna doppia conferma', async () => {
        liveState.feed = FEED_WITH_BOOK;
        mState.mockResolvedValue({ control: { ...CONTROL, mode: 'live' } as never, aggregates: null, activity: [] });
        renderPage();
        await gotoAutoTab();
        const user = userEvent.setup();
        await user.click(await screen.findByTestId('cashout-trigger'));
        await screen.findByTestId('cashout-confirm');
        expect(screen.queryByText(/Modalità LIVE: soldi veri/)).toBeNull();
    });

    it('HIGH-1: gamba di chiusura già scritta -> cash out spento (nessuna seconda copertura)', async () => {
        liveState.feed = FEED_WITH_BOOK;
        mTrades.mockResolvedValue([
            TRADES[0],
            { ...TRADES[0], id: 2, side: 'back', price: 100, size: 5.79, status: 'pending', closes_trade_id: 1, runner_name: '3 - 2' },
        ] as never);
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByTestId('cashout-trigger')).toBeDisabled();
        expect(screen.getByText(/chiude #1/)).toBeInTheDocument();
    });

    it('HIGH-1: meta.hedging alzato dal servizio -> cash out spento', async () => {
        liveState.feed = FEED_WITH_BOOK;
        mTrades.mockResolvedValue([{ ...TRADES[0], meta: { hedging: true } }] as never);
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByTestId('cashout-trigger')).toBeDisabled();
    });
});

describe('Omega — green-up automatico', () => {
    it('pannello parametri: sezione Green-up con interruttore, modalita, campi e calibrazione', async () => {
        mState.mockResolvedValue({
            control: { ...CONTROL, params: { greenup_enabled: false, greenup_mode: 'off', greenup_trigger_distance: 2, model_calibration: 'off' } } as never,
            aggregates: null, activity: [],
        });
        renderPage();
        await screen.findByText('OMEGA');
        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: /Parametri/ }));
        expect(await screen.findByTestId('greenup-section')).toHaveTextContent('Green-up automatico');
        expect(screen.getByRole('checkbox', { name: 'Green-up automatico attivo' })).not.toBeChecked();
        expect((screen.getByLabelText('Modalità green-up') as HTMLSelectElement).value).toBe('off');
        expect((screen.getByLabelText('Scatta a distanza (gol)') as HTMLInputElement).value).toBe('2');
        expect((screen.getByLabelText('Attesa conferma punteggio (s)') as HTMLInputElement).value).toBe('30');  // default
        expect((screen.getByLabelText('Residuo · tentativi max') as HTMLInputElement).value).toBe('15');
        expect((screen.getByLabelText('Calibrazione P(modello)') as HTMLSelectElement).value).toBe('off');
        expect(screen.getByText(/appena il risultato layato diventa/)).toBeInTheDocument();
    });

    it('salvataggio: i parametri green-up viaggiano con omega_update_params', async () => {
        const { updateOmegaParams } = await import('@/lib/omega');
        const mUpdate = vi.mocked(updateOmegaParams);
        mUpdate.mockResolvedValue({} as never);
        renderPage();
        await screen.findByText('OMEGA');
        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: /Parametri/ }));
        await screen.findByTestId('greenup-section');
        await user.selectOptions(screen.getByLabelText('Modalità green-up'), 'off');
        const dist = screen.getByLabelText('Scatta a distanza (gol)');
        await user.clear(dist);
        await user.type(dist, '2');
        await user.click(screen.getByRole('button', { name: 'Salva parametri' }));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const args = mUpdate.mock.calls[0][0] as { params: Record<string, unknown> };
        expect(args.params.greenup_mode).toBe('off');
        expect(args.params.greenup_trigger_distance).toBe(2);
        expect(args.params.greenup_enabled).toBe(true);
        expect(args.params.greenup_take_profit_minute).toBe(80);
        expect(args.params.model_calibration).toBe('auto');
    });

    it('riga trade: badge Green-up da meta.exit_kind e colonna Modello calibrata vs grezza', async () => {
        mTrades.mockResolvedValue([{
            ...TRADES[0], status: 'hedged', pnl: 4.2,
            meta: { exit_kind: 'greenup', exit_reason: 'distanza 1 gol dal 3-2', locked_pnl: 4.2, model: { p_model_raw: 0.018, calibrated: 0.012 } },
        }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-trade-row');
        // apertura coperta in green-up: lo stato lo dice, il motivo sotto
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('CHIUSO IN GREEN-UP');
        expect(within(row).getByTestId('omega-exit-reason')).toHaveTextContent('distanza 1 gol dal 3-2');
        expect(within(row).getByTestId('omega-locked-pnl')).toHaveTextContent('+4,20 € bloccato');
        const model = within(row).getByTestId('omega-model-p');
        expect(model).toHaveTextContent('1,2%');
        expect(model).toHaveTextContent('grezza 1,8%');
    });

    it('coppia lay + back di copertura: colonne Selezione/Lato, sub-riga "↳ Green-up di #70", CHIUSO IN GREEN-UP con P&L bloccato, motivo, tooltip e live', async () => {
        liveState.feed = FEED_WITH_BOOK;
        liveState.label = "71′ · 1-2";
        mTrades.mockResolvedValue([
            {
                ...TRADES[0], id: 70, price: 55, size: 2.16, liability: 116.64, status: 'hedged', pnl: -22.1,
                meta: { locked_pnl: -22.1, exit_kind: 'greenup', exit_reason: "gol al 29': 1-2 raggiungibile" },
            },
            {
                ...TRADES[0], id: 71, side: 'back', price: 4.9, size: 24.24, liability: 24.24, status: 'open', pnl: 0,
                closes_trade_id: 70, meta: { exit_kind: 'greenup' }, placed_at: new Date().toISOString(),
            },
        ] as never);
        renderPage();
        await gotoAutoTab();
        // intestazioni: "Selezione" + "Lato" (niente piu' "Lay" come titolo di colonna)
        expect(screen.getByRole('columnheader', { name: 'Selezione' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'Lato' })).toBeInTheDocument();
        expect(screen.queryByRole('columnheader', { name: 'Lay' })).toBeNull();
        // UNA sola riga trade: la chiusura e' una sub-riga attaccata
        const rows = await screen.findAllByTestId('omega-trade-row');
        expect(rows).toHaveLength(1);
        const row = rows[0];
        expect(within(row).getByTestId('omega-side')).toHaveTextContent('LAY');
        expect(within(row).getByTestId('omega-side').className).toMatch(/rose/);
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('CHIUSO IN GREEN-UP');
        expect(within(row).getByTestId('omega-status').title)
            .toBe('il lay a 55,00 è stato coperto con un back a 4,90 sulla stessa selezione: esito identico su ogni risultato');
        expect(within(row).getByTestId('omega-exit-reason')).toHaveTextContent("gol al 29': 1-2 raggiungibile");
        expect(within(row).getByTestId('omega-locked-pnl')).toHaveTextContent('−22,10 € bloccato');
        expect(within(row).getByTestId('omega-locked-pnl').closest('td')?.className).toMatch(/text-red-400/);
        // la colonna Live sull'apertura continua a mostrare il punteggio
        expect(within(row).getByText("71′ · 1-2")).toBeInTheDocument();
        // sub-riga della copertura
        const sub = screen.getByTestId('omega-closing-row');
        expect(sub).toHaveAttribute('data-closes', '70');
        expect(sub).toHaveTextContent('↳ Green-up di #70 · BACK 24,24 € @4,90');
        expect(within(sub).getByText('BACK').className).toMatch(/sky/);
        expect(within(sub).getByText(/chiude #70/)).toBeInTheDocument();
        expect(within(sub).getByText('APERTO')).toBeInTheDocument();
        // nessun cash out sull'apertura coperta ne' sulla copertura
        expect(screen.queryByTestId('cashout-trigger')).toBeNull();
    });

    it('uscita non green-up (es. profitto) su trade regolato: badge di uscita classico', async () => {
        mTrades.mockResolvedValue([{ ...TRADES[0], status: 'won', pnl: 5, meta: { exit_kind: 'profit', exit_reason: 'take profit' } }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-trade-row');
        expect(within(row).getByTestId('exit-badge')).toHaveTextContent('Uscita: profitto');
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('VINTO');
    });

    it('attivita: green-up / attesa / ritento leggibili in italiano', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never, aggregates: null,
            activity: [
                { id: 3, ts: '2026-09-10T10:20:00Z', kind: 'greenup', payload: { event_name: 'Roma vs Lazio', runner_name: '3 - 2', minute: 71, live_score: '2-1', locked: 4.2, reason: 'a distanza 1 gol' } },
                { id: 2, ts: '2026-09-10T10:15:00Z', kind: 'greenup_hold', payload: { event_name: 'Roma vs Lazio', p_lose: 0.004, reason: 'margine ampio' } },
                { id: 1, ts: '2026-09-10T10:10:00Z', kind: 'greenup_retry', payload: { event_name: 'Roma vs Lazio', attempt: 2, max_attempts: 15 } },
            ],
        });
        renderPage();
        await gotoAutoTab();
        const feed = await screen.findByTestId('omega-activity');
        expect(feed).toHaveTextContent('Attività del servizio (3)');
        const rows = within(feed).getAllByTestId('omega-activity-row');
        expect(rows[0]).toHaveTextContent('GREEN-UP');
        expect(rows[0]).toHaveTextContent('Roma vs Lazio · lay 3 - 2 · 71′ · 2-1 · +€4.20 · a distanza 1 gol');
        expect(rows[1]).toHaveTextContent('GREEN-UP · attesa');
        expect(rows[1]).toHaveTextContent('P(perdita) 0,4% · margine ampio');
        expect(rows[2]).toHaveTextContent('GREEN-UP · ritento');
        expect(rows[2]).toHaveTextContent('tentativo 2/15');
    });
});
