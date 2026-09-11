// Test COMPONENTE per la dashboard Omega. Data-layer e sonner mockati.
// Verifica: header/stato, barra obiettivo (realizzato/goal), KPI da RPC (H-08),
// riga partita, stati del green-up (H-04), verifica su Betfair (H-02),
// freschezza del feed, pannello parametri spec-driven (M-09/M-10) e patch dei
// parametri (H-07), attività con i kind mappati (M-01/M-02) e "carica altre"
// (M-22).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

// Il tab MISSIONE (default) ha il suo data-layer: qui stub — è testato a parte
// in lib/omegaMissions.test.ts.
vi.mock('@/components/omega/MissionPanel', () => ({
    default: () => <div data-testid="mission-panel-stub" />,
}));

// feed live mutabile per i test del cash out (book della selezione laid) e
// della FRESCHEZZA (updated_at per evento)
const liveState = vi.hoisted(() => ({
    rows: {} as Record<string, { payload: unknown; updated_at: string | null }>,
    label: null as string | null,
}));
vi.mock('@/lib/useScanLiveFeed', () => ({
    useScanLiveFeedRows: () => liveState.rows,
    useScanLiveFeed: () => Object.fromEntries(Object.entries(liveState.rows).map(([k, v]) => [k, v.payload])),
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
        goal_pct: 24, last_cycle: new Date().toISOString(), bot_running: true,
    },
    error: null, started_at: null, stopped_at: null,
    // un bot 'running' ha un battito FRESCO: senza, il badge dell'header
    // dice (giustamente) "IN CORSA - SENZA BATTITO" (certificazione 11/09)
    heartbeat_at: new Date().toISOString(), updated_at: new Date().toISOString(),
};

// H-08: i numeri della giornata li dice SOLO la RPC
const AGG = {
    realized_profit: 60, realized_today: 60, open_liability: 480, matches_traded: 3,
    matches_open: 1, matches_won: 2, matches_lost: 0,
    legs_today: 2, events_today: 1, won_today: 1, lost_today: 1, live_now: 1,
    locked_pnl_open: 0, reconciling_liability: 0,
};

const TRADES = [
    {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', market_id: '1.1', selection_id: 4,
        runner_name: '3 - 2', side: 'lay', mode: 'paper', price: 110, size: 5.26, liability: 573.34,
        target: 5, minute_at_entry: 42, score_at_entry: '0-0', kickoff: null, status: 'open',
        pnl: 0, bet_id: 'b1', placed_at: new Date().toISOString(), settled_at: null, meta: {},
    },
];

// book live della selezione laid (3-2 @110): back 100 / lay 120
function feedWithBook(ageS = 2) {
    return {
        e1: {
            payload: {
                minute: 60, score_home: 0, score_away: 0,
                cs: { market_id: '1.1', status: 'OPEN', selections: [{ selection_id: 4, name: '3 - 2', back: 100, lay: 120 }] },
            },
            updated_at: new Date(Date.now() - ageS * 1000).toISOString(),
        },
    };
}

function state(over: Record<string, unknown> = {}) {
    return {
        control: CONTROL as never, aggregates: AGG as never, activity: [],
        activity_more: 0, activity_day: null, goal_today: 250, goal_snapshot: true,
        ...over,
    } as never;
}

beforeEach(() => {
    vi.clearAllMocks();
    liveState.rows = {};
    liveState.label = null;
    mState.mockResolvedValue(state());
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
        expect(await screen.findByText('Giornata operativa')).toBeInTheDocument();
        // +60,00 € compare sia nella barra della giornata sia nel KPI "P&L oggi"
        expect((await screen.findAllByText('+60,00 €')).length).toBeGreaterThanOrEqual(1);
        expect(await screen.findByText(/250,00 €/)).toBeInTheDocument();
    });

    it('H-08: i contatori della giornata vengono dalla RPC, non dal client', async () => {
        renderPage();
        const bar = await screen.findByTestId('omega-daily-mission');
        // legs_today=2, events_today=1, won/lost dalla RPC (il client ne conterebbe altri)
        expect(within(bar).getByTestId('omega-today-legs')).toHaveTextContent('partite 1');
        expect(within(bar).getByTestId('omega-today-legs')).toHaveTextContent('operazioni 2');
        expect(within(bar).getByTestId('omega-today-legs')).toHaveTextContent('1V');
        expect(within(bar).getByTestId('omega-today-legs')).toHaveTextContent('1P');
        expect(screen.getByTestId('omega-kpi-legs')).toHaveTextContent('2');
        expect(screen.getByTestId('omega-kpi-legs')).toHaveTextContent('1V · 1P');
        // e il riepilogo della tabella usa gli STESSI numeri
        await gotoAutoTab();
        expect(screen.getByTestId('omega-matches-summary')).toHaveTextContent('2 operazioni oggi · 1V 1P');
    });

    it('H-06/H-02: KPI P&L bloccato e liability con il dettaglio "in verifica"', async () => {
        mState.mockResolvedValue(state({
            aggregates: { ...AGG, locked_pnl_open: -22.1, reconciling_liability: 120, open_liability: 600 },
        }));
        renderPage();
        expect(await screen.findByTestId('omega-kpi-locked')).toHaveTextContent('−22,10 €');
        expect(screen.getByTestId('omega-kpi-locked')).toHaveTextContent('P&L bloccato');
        expect(screen.getByTestId('omega-kpi-liability')).toHaveTextContent('di cui 120,00 € in verifica su Betfair');
        expect(screen.getByTestId('omega-kpi-reconciling')).toHaveTextContent('120,00 €');
    });

    it('L-03: a bot FERMO eventi e target non si spacciano per dati vivi', async () => {
        mState.mockResolvedValue(state({
            control: { ...CONTROL, status: 'stopped', stats: { ...CONTROL.stats, bot_running: false } } as never,
        }));
        renderPage();
        expect(await screen.findByTestId('omega-kpi-events')).toHaveTextContent('disponibile a bot avviato');
        expect(screen.getByTestId('omega-kpi-target')).toHaveTextContent('bot fermo: nessun target in corso');
    });

    it('KPI target/match e liability aperta presenti', async () => {
        renderPage();
        expect(await screen.findByText('Target / operazione')).toBeInTheDocument();
        expect(await screen.findByText('9,50 €')).toBeInTheDocument();
        expect((await screen.findAllByText('Liability aperta')).length).toBeGreaterThanOrEqual(1);
        expect((await screen.findAllByText('480,00 €')).length).toBeGreaterThanOrEqual(1);
    });

    it('elenca la PARTITA con la gamba 2T bancata (3-2), stato APERTO e le colonne 1°/2° tempo + risultati', async () => {
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByText('Roma vs Lazio')).toBeInTheDocument();
        expect(await screen.findByText('3 - 2')).toBeInTheDocument();
        expect(await screen.findByText('APERTO')).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: '1° tempo' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'Risultato 1T' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: '2° tempo' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'Risultato 2T' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'P&L partita' })).toBeInTheDocument();
        const row = screen.getByTestId('omega-match-row');
        // trade senza fase (v1) → colonna 2T; 1T vuota; risultati in attesa; P&L in corso
        expect(within(row).getByTestId('omega-leg-ht')).toHaveAttribute('data-empty', '1');
        expect(within(within(row).getByTestId('omega-leg-ft')).getByText('3 - 2')).toBeInTheDocument();
        expect(within(row).getByTestId('omega-result-ht')).toHaveTextContent('—');
        expect(within(row).getByTestId('omega-match-pnl')).toHaveTextContent('—');
        expect(row).toHaveTextContent('rischio 573,34 €');
        expect(screen.getByTestId('omega-matches-card')).toHaveTextContent('Partite di oggi (1)');
    });

    it('mostra tutte / solo oggi: una partita di ieri già regolata compare solo con "mostra tutte"', async () => {
        mTrades.mockResolvedValue([
            TRADES[0],
            { ...TRADES[0], id: 5, event_id: 'old', event_name: 'Vecchia vs Regolata', status: 'won', pnl: 3, placed_at: '2026-01-05T10:00:00Z', settled_at: '2026-01-05T12:00:00Z' },
        ] as never);
        renderPage();
        await gotoAutoTab();
        expect(await screen.findAllByTestId('omega-match-row')).toHaveLength(1);
        expect(screen.queryByText('Vecchia vs Regolata')).toBeNull();
        await userEvent.setup().click(screen.getByTestId('omega-matches-toggle'));
        expect(await screen.findAllByTestId('omega-match-row')).toHaveLength(2);
        expect(screen.getByText('Vecchia vs Regolata')).toBeInTheDocument();
        expect(screen.getByTestId('omega-matches-card')).toHaveTextContent('Tutte le partite (2)');
    });

    it('risultati REALI 1T/2T e P&L della partita in verde/rosso (entrambe le gambe con le chiusure)', async () => {
        const base = { ...TRADES[0], placed_at: new Date().toISOString() };
        mTrades.mockResolvedValue([
            { ...base, id: 70, phase: 'ht_cs', runner_name: '1 - 2', price: 55, size: 2.16, liability: 116.64, status: 'won', pnl: 2.16, settled_at: new Date().toISOString(),
              meta: { result_ht: '1-1', result_ft: '1-1', exit_kind: 'greenup', exit_reason: "gol al 28': 1-2 raggiungibile", locked_pnl: -22.1 } },
            { ...base, id: 71, phase: 'ht_cs', runner_name: '1 - 2', side: 'back', price: 4.9, size: 24.24, liability: 24.24, status: 'lost', pnl: -24.24, closes_trade_id: 70, settled_at: new Date().toISOString(), meta: { exit_kind: 'greenup' } },
            { ...base, id: 72, phase: 'ft_cs', runner_name: '4 - 1', price: 90, size: 2.71, liability: 241.19, status: 'won', pnl: 2.57, settled_at: new Date().toISOString(), meta: { result_ft: '1-1' } },
        ] as never);
        renderPage();
        await gotoAutoTab();
        const rows = await screen.findAllByTestId('omega-match-row');
        expect(rows).toHaveLength(1);
        const row = rows[0];
        expect(row).toHaveAttribute('data-state', 'settled');
        const ht = within(row).getByTestId('omega-leg-ht');
        expect(within(ht).getByText('1 - 2')).toBeInTheDocument();
        expect(within(ht).getByTestId('omega-leg-pnl')).toHaveTextContent('−22,08 €');
        expect(within(ht).getByTestId('omega-closing-line')).toHaveTextContent(/Green-up/);
        expect(within(ht).getByTestId('omega-closing-line')).toHaveTextContent(/24,24 € @4,90/);
        expect(within(ht).getByTestId('omega-exit-reason')).toHaveTextContent("gol al 28': 1-2 raggiungibile");
        const ft = within(row).getByTestId('omega-leg-ft');
        expect(within(ft).getByText('4 - 1')).toBeInTheDocument();
        expect(within(ft).getByTestId('omega-leg-pnl')).toHaveTextContent('+2,57 €');
        expect(within(ft).getByTestId('omega-leg-pnl').className).toMatch(/text-emerald-400/);
        expect(within(row).getByTestId('omega-result-ht')).toHaveTextContent('1-1');
        expect(within(row).getByTestId('omega-result-ft')).toHaveTextContent('1-1');
        expect(within(row).getByTestId('omega-result-ft')).toHaveTextContent('bancato non uscito');
        const pnl = within(row).getByTestId('omega-match-pnl');
        expect(pnl).toHaveTextContent('−19,51 €');
        expect(pnl.className).toMatch(/text-red-400/);
    });

    it('mostra il pulsante Ferma quando è in corsa', async () => {
        renderPage();
        expect(await screen.findByText('Ferma')).toBeInTheDocument();
    });
});

describe('Omega — cash out', () => {
    it('CRITICAL-2: la conferma usa la modalità del TRADE, non quella della pagina', async () => {
        liveState.rows = feedWithBook();
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
        liveState.rows = feedWithBook();
        mState.mockResolvedValue(state({ control: { ...CONTROL, mode: 'live' } as never }));
        renderPage();
        await gotoAutoTab();
        const user = userEvent.setup();
        await user.click(await screen.findByTestId('cashout-trigger'));
        await screen.findByTestId('cashout-confirm');
        expect(screen.queryByText(/Modalità LIVE: soldi veri/)).toBeNull();
    });

    it('HIGH-1: chiusura in volo (pending) -> cash out spento (nessuna seconda copertura)', async () => {
        liveState.rows = feedWithBook();
        mTrades.mockResolvedValue([
            TRADES[0],
            { ...TRADES[0], id: 2, side: 'back', price: 100, size: 5.79, status: 'pending', closes_trade_id: 1, runner_name: '3 - 2' },
        ] as never);
        renderPage();
        await gotoAutoTab();
        const line = await screen.findByTestId('omega-closing-line');
        expect(line).toHaveAttribute('data-closes', '1');
        expect(screen.queryByTestId('cashout-trigger')).toBeNull();
    });

    it('HIGH-1: meta.hedging alzato dal servizio -> cash out spento', async () => {
        liveState.rows = feedWithBook();
        mTrades.mockResolvedValue([{ ...TRADES[0], meta: { hedging: true } }] as never);
        renderPage();
        await gotoAutoTab();
        expect(await screen.findByTestId('cashout-trigger')).toBeDisabled();
    });

    it('M-24: feed FERMO (> 20 s) -> cash out spento e la riga lo dice', async () => {
        liveState.rows = feedWithBook(90);
        renderPage();
        await gotoAutoTab();
        const age = await screen.findAllByTestId('omega-feed-age');
        expect(age[0]).toHaveAttribute('data-stale', '1');
        expect(age[0]).toHaveTextContent(/FEED FERMO/);
        expect(screen.getByTestId('cashout-trigger')).toBeDisabled();
    });

    it('M-06: copertura PARZIALE -> stato "COPERTA 40 %", residuo e cash out del SOLO residuo', async () => {
        liveState.rows = feedWithBook();
        mTrades.mockResolvedValue([{
            ...TRADES[0], status: 'open',
            meta: {
                hedged_size: 2.1, residual_size: 3.16,
                hedge: { fraction: 0.4, remaining_liability: 315.78, hedged_size: 2.1, size: 5.26, complete: false, residual_size: 3.16 },
            },
        }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-match-row');
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('COPERTA 40 % (restano 315,78 €)');
        expect(within(row).getByTestId('omega-residual-note')).toHaveTextContent('residuo scoperto 3,16 €');
        expect(row).toHaveTextContent('rischio 315,78 €');
        expect(screen.getByTestId('cashout-trigger')).toBeEnabled();
    });
});

describe('Omega — stati critici sulla riga', () => {
    it('H-02: pending in riconciliazione = IN VERIFICA SU BETFAIR e conta nel rischio', async () => {
        mTrades.mockResolvedValue([{
            ...TRADES[0], status: 'pending', bet_id: null,
            meta: { reconciling: true, reconciling_since: new Date().toISOString() },
        }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-match-row');
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('IN VERIFICA SU BETFAIR');
        expect(within(row).getByTestId('omega-match-reconciling')).toHaveTextContent('di cui 573,34 € in verifica');
    });

    it('M-05: riga TERMINALE (nessun ordine reale) = ERRORE definitivo, non "in corso per sempre"', async () => {
        mTrades.mockResolvedValue([{
            ...TRADES[0], status: 'error',
            meta: { leg_failed: true, error_final: true, reason: 'FOK ucciso da Betfair', no_fill_at: new Date().toISOString() },
        }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-match-row');
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('ERRORE (definitivo)');
        expect(within(row).getByTestId('omega-terminal-error')).toHaveTextContent('nessun ordine reale');
        expect(within(row).getByTestId('omega-terminal-error')).toHaveTextContent('FOK ucciso da Betfair');
    });

    it('M-04: esito della POSIZIONE accanto a quello della gamba', async () => {
        mTrades.mockResolvedValue([{
            ...TRADES[0], status: 'lost', pnl: -573.34, settled_at: new Date().toISOString(),
            meta: { position_id: 9, position_pnl: 4.2, position_result: 'won' },
        }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-match-row');
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('PERSO');
        expect(within(row).getByTestId('omega-position-result')).toHaveTextContent('posizione in utile +4,20 €');
    });

    it('L-02: la commissione del cash out è quella FISSATA sul trade, non quella del form', async () => {
        liveState.rows = feedWithBook();
        mTrades.mockResolvedValue([{ ...TRADES[0], meta: { commission: 0.02 } }] as never);
        renderPage();
        await gotoAutoTab();
        const now = await screen.findByTestId('omega-close-now');
        expect(now.getAttribute('title')).toMatch(/commissione 2,0 % fissata sul trade/);
    });
});

describe('Omega — green-up automatico', () => {
    const GREENUP_CASES: [string, Record<string, unknown>, RegExp][] = [
        ['pending', { state: 'pending', reason: 'residuo da coprire' }, /GREEN-UP in attesa/],
        ['hold', { state: 'hold', reason: 'margine ampio', p_lose: 0.004, ev: 1.8 }, /TENGO · P\(perdita\) 0,4 % · EV \+1,80 €/],
        ['failed', { state: 'failed', reason: 'tentativi esauriti', next_retry_at: '2026-09-11T18:35:00Z' }, /GREEN-UP fallito, ritento alle/],
        ['blind', { state: 'blind', reason: 'nessun dato live da 3 cicli' }, /GREEN-UP CIECO \(senza feed\)/],
        ['residual_dropped', { state: 'residual_dropped', reason: 'residuo non copribile' }, /residuo abbandonato/],
        ['done', { state: 'done', reason: 'coperta del tutto' }, /GREEN-UP fatto/],
    ];

    it.each(GREENUP_CASES)('H-04: stato %s visibile sulla riga', async (st, greenup, re) => {
        mTrades.mockResolvedValue([{ ...TRADES[0], meta: { greenup } }] as never);
        renderPage();
        await gotoAutoTab();
        const badge = await screen.findByTestId('omega-greenup-badge');
        expect(badge).toHaveAttribute('data-greenup-state', st);
        expect(badge).toHaveTextContent(re);
    });

    it('pannello parametri: gruppi, green-up, default del SERVIZIO e clamp dichiarato', async () => {
        mState.mockResolvedValue(state({
            control: { ...CONTROL, params: { greenup_enabled: false, greenup_mode: 'off', greenup_trigger_distance: 2, model_calibration: 'off' } } as never,
        }));
        renderPage();
        await screen.findByText('OMEGA');
        const user = userEvent.setup();
        await user.click(screen.getByTestId('omega-params-trigger'));
        const sheet = await screen.findByTestId('params-sheet');
        expect(within(sheet).getAllByTestId('params-group').length).toBeGreaterThanOrEqual(6);
        expect(screen.getByRole('checkbox', { name: 'Green-up automatico attivo' })).not.toBeChecked();
        expect((screen.getByLabelText('Modalità green-up') as HTMLSelectElement).value).toBe('off');
        expect((screen.getByLabelText('Scatta a distanza (gol)') as HTMLInputElement).value).toBe('2');
        expect((screen.getByLabelText('Attesa assestamento dopo il gol (s)') as HTMLInputElement).value).toBe('30');
        expect((screen.getByLabelText('Residuo: tentativi massimi') as HTMLInputElement).value).toBe('15');
        expect((screen.getByLabelText('Calibrazione P(modello)') as HTMLSelectElement).value).toBe('off');
        // M-09: il margine EV è in EURO (fino a 1000), non una frazione
        expect(screen.getByLabelText('Margine EV per tenere (€)')).toHaveAttribute('max', '1000');
        // M-10: chiavi prima senza UI
        expect(screen.getByLabelText('Motore')).toBeInTheDocument();
        expect(screen.getByLabelText('Fattore di coda su P ≤ 5 %')).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: 'Usa i cartellini gialli del feed' })).toBeInTheDocument();
    });

    it('M-09: un valore fuori range viene clampato e DICHIARATO', async () => {
        renderPage();
        await screen.findByText('OMEGA');
        const user = userEvent.setup();
        await user.click(screen.getByTestId('omega-params-trigger'));
        const dist = await screen.findByLabelText('Scatta a distanza (gol)');
        await user.clear(dist);
        await user.type(dist, '9');
        const cl = await screen.findByTestId('params-clamped');
        expect(cl).toHaveAttribute('data-field', 'greenup_trigger_distance');
        expect(cl).toHaveTextContent('clampato a 3 (ammesso 0 … 3)');
    });

    it('H-07: "Salva" manda i parametri del SERVIZIO + le modifiche, mai i default della UI', async () => {
        const { updateOmegaParams } = await import('@/lib/omega');
        const mUpdate = vi.mocked(updateOmegaParams);
        mUpdate.mockResolvedValue({} as never);
        // il servizio ha già i SUOI valori: model_calibration off, risk cap 0.15
        mState.mockResolvedValue(state({
            control: { ...CONTROL, params: { model_calibration: 'off', greenup_risk_cap: 0.15, greenup_mode: 'auto' } } as never,
        }));
        renderPage();
        await screen.findByText('OMEGA');
        const user = userEvent.setup();
        await user.click(screen.getByTestId('omega-params-trigger'));
        await screen.findByTestId('params-sheet');
        await user.selectOptions(screen.getByLabelText('Modalità green-up'), 'off');
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const args = mUpdate.mock.calls[0][0] as { params: Record<string, unknown>; dailyGoal?: number };
        expect(args.params.greenup_mode).toBe('off');
        // i valori del servizio restano quelli del servizio
        expect(args.params.model_calibration).toBe('off');
        expect(args.params.greenup_risk_cap).toBe(0.15);
        // le chiavi mai toccate e uguali al default della UI non vengono inviate
        expect(args.params).not.toHaveProperty('select_k_se');
        expect(args.dailyGoal).toBe(250);
    });

    it('riga trade: badge Green-up da meta.exit_kind e colonna P modello vs mercato', async () => {
        liveState.rows = feedWithBook();
        mTrades.mockResolvedValue([{
            ...TRADES[0], status: 'hedged', pnl: 4.2,
            meta: { exit_kind: 'greenup', exit_reason: 'distanza 1 gol dal 3-2', locked_pnl: 4.2, model: { p_model_raw: 0.018, calibrated: 0.012 } },
        }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-match-row');
        // apertura coperta in green-up: lo stato lo dice, il motivo sotto
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('CHIUSO IN GREEN-UP');
        expect(within(row).getByTestId('omega-exit-reason')).toHaveTextContent('distanza 1 gol dal 3-2');
        expect(within(row).getByTestId('omega-locked-pnl')).toHaveTextContent('+4,20 € bloccato');
        const model = within(row).getByTestId('omega-model-p');
        expect(model).toHaveTextContent('1,2 %');
        expect(model.title).toMatch(/grezza 1,8 %/);
        // P(perdita) del MERCATO: 1/120 = 0,8 %
        expect(model).toHaveTextContent('mercato 0,8 %');
    });

    it('coppia lay + back di copertura: una sola riga partita, CHIUSO IN GREEN-UP, P&L bloccato, live', async () => {
        liveState.rows = feedWithBook();
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
        const rows = await screen.findAllByTestId('omega-match-row');
        expect(rows).toHaveLength(1);
        const row = rows[0];
        expect(within(row).getByTestId('omega-side')).toHaveTextContent('LAY');
        expect(within(row).getByTestId('omega-side').className).toMatch(/rose/);
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('CHIUSO IN GREEN-UP');
        expect(within(row).getByTestId('omega-status').title)
            .toBe('il lay a 55,00 è stato coperto con un back a 4,90 sulla stessa selezione: esito identico su ogni risultato');
        expect(within(row).getByTestId('omega-exit-reason')).toHaveTextContent("gol al 29': 1-2 raggiungibile");
        expect(within(row).getByTestId('omega-locked-pnl')).toHaveTextContent('−22,10 € bloccato');
        expect(within(row).getByTestId('omega-locked-pnl').className).toMatch(/text-red-400/);
        expect(within(row).getByTestId('omega-live-score')).toHaveTextContent("71′ · 1-2");
        const sub = within(row).getByTestId('omega-closing-line');
        expect(sub).toHaveAttribute('data-closes', '70');
        expect(sub).toHaveTextContent(/Green-up/);
        expect(sub).toHaveTextContent(/24,24 € @4,90/);
        expect(within(sub).getByText('BACK').className).toMatch(/sky/);
        expect(within(sub).getByText('APERTO')).toBeInTheDocument();
        expect(within(row).getByTestId('omega-match-pnl')).toHaveTextContent('−22,10 €');
        expect(within(row).getByTestId('omega-match-pnl').className).toMatch(/text-red-400/);
        expect(screen.queryByTestId('cashout-trigger')).toBeNull();
    });

    it('M-19: la chiusura chiesta a mano si chiama "Cash out", mai "Chiusura"', async () => {
        mTrades.mockResolvedValue([
            { ...TRADES[0], id: 80, status: 'hedged', pnl: 0, meta: { locked_pnl: 1.2 } },
            { ...TRADES[0], id: 81, side: 'back', price: 100, size: 5.79, status: 'open', pnl: 0, closes_trade_id: 80, meta: { cashout: true } },
        ] as never);
        renderPage();
        await gotoAutoTab();
        const sub = await screen.findByTestId('omega-closing-line');
        expect(sub).toHaveTextContent('Cash out');
        expect(sub).not.toHaveTextContent('Chiusura');
        expect(screen.getByTestId('omega-status')).toHaveTextContent('CASH OUT MANUALE');
    });

    it('uscita non green-up (es. profitto) su trade regolato: badge di uscita classico', async () => {
        mTrades.mockResolvedValue([{ ...TRADES[0], status: 'won', pnl: 5, meta: { exit_kind: 'profit', exit_reason: 'take profit' } }] as never);
        renderPage();
        await gotoAutoTab();
        const row = await screen.findByTestId('omega-match-row');
        expect(within(row).getByTestId('exit-badge')).toHaveTextContent('Uscita: profitto');
        expect(within(row).getByTestId('omega-status')).toHaveTextContent('VINTO');
        expect(within(row).getByTestId('omega-match-pnl')).toHaveTextContent('+5,00 €');
        expect(within(row).getByTestId('omega-match-pnl').className).toMatch(/text-emerald-400/);
    });
});

describe('Omega — attività del servizio', () => {
    it('M-01/M-02: kind in italiano, nome partita risolto dai trade, critici in rosso', async () => {
        mState.mockResolvedValue(state({
            activity: [
                { id: 6, ts: new Date().toISOString(), kind: 'greenup', payload: { event_id: 'e1', leg: 'ft_cs', locked_pnl: 4.2, minute: 71, score: '2-1', exit_reason: 'a distanza 1 gol' } },
                { id: 5, ts: new Date().toISOString(), kind: 'greenup_hold', payload: { event_id: 'e1', p_lose: 0.004, reason: 'margine ampio' } },
                { id: 4, ts: new Date().toISOString(), kind: 'greenup_retry', payload: { event_id: 'e1', attempt: 2, max_attempts: 15 } },
                { id: 3, ts: new Date().toISOString(), kind: 'stale_open_alert', payload: { event_id: 'e1', liability: 573.34 } },
                { id: 2, ts: new Date().toISOString(), kind: 'flumine_no_fill', payload: { event_id: 'e1', reason: 'no_fill', leg: 'ht_cs', attempt: 1, max_attempts: 3 } },
                { id: 1, ts: new Date().toISOString(), kind: 'error', payload: { reason: 'greenup_attempts_exhausted' } },
                // di un giorno PASSATO: non compare (il passato sta nello Storico)
                { id: 0, ts: '2026-01-05T10:00:00Z', kind: 'settle', payload: { event_id: 'e1' } },
            ],
        }));
        renderPage();
        await gotoAutoTab();
        const feed = await screen.findByTestId('omega-activity');
        expect(feed).toHaveTextContent('Attività del servizio di oggi (6)');
        const rows = within(feed).getAllByTestId('omega-activity-row');
        expect(rows[0]).toHaveTextContent('GREEN-UP');
        expect(rows[0]).toHaveTextContent('Roma vs Lazio · 2T · 71′ · 2-1 · bloccato +4,20 € · a distanza 1 gol');
        expect(rows[1]).toHaveTextContent('GREEN-UP · TENGO');
        expect(rows[1]).toHaveTextContent('P(perdita) 0,4 % · margine ampio');
        expect(rows[2]).toHaveTextContent('GREEN-UP · ritento');
        expect(rows[2]).toHaveTextContent('tentativo 2/15');
        expect(rows[3]).toHaveTextContent('POSIZIONE APERTA DA TROPPO');
        expect(rows[3]).toHaveAttribute('data-critical', '1');
        expect(rows[4]).toHaveTextContent('CODA: NON ABBINATO');
        expect(rows[5]).toHaveTextContent('ERRORE');
        expect(rows[5]).toHaveTextContent('green-up: tentativi esauriti, posizione SCOPERTA');
    });

    it('M-22: "carica altre" quando la giornata ha più righe del limite', async () => {
        mState.mockResolvedValue(state({
            activity: [{ id: 1, ts: new Date().toISOString(), kind: 'place', payload: { event_id: 'e1' } }],
            activity_more: 42,
        }));
        renderPage();
        await gotoAutoTab();
        const more = await screen.findByTestId('omega-activity-more');
        expect(more).toHaveTextContent('carica altre (42)');
        await userEvent.setup().click(more);
        await waitFor(() => expect(mState).toHaveBeenCalledWith(180));
    });
});

describe('Omega — contratto aggiornato (salute e bloccato)', () => {
    it('control.stats.degraded → avviso ambra nel chip salute, non "servizio morto"', async () => {
        mState.mockResolvedValue(state({
            control: {
                ...CONTROL,
                heartbeat_at: new Date().toISOString(),
                stats: { ...CONTROL.stats, degraded: 'fase green-up interrotta' },
            } as never,
        }));
        renderPage();
        const chip = await screen.findByTestId('service-health');
        expect(chip).toHaveAttribute('data-degraded', '1');
        expect(screen.getByTestId('service-degraded')).toHaveTextContent('fase green-up interrotta');
    });

    it('locked_pnl_open_today: la barra mostra il bloccato di OGGI, il KPI anche il totale', async () => {
        mState.mockResolvedValue(state({
            aggregates: { ...AGG, locked_pnl_open: -30, locked_pnl_open_today: -22.1 },
        }));
        renderPage();
        const bar = await screen.findByTestId('omega-daily-mission');
        expect(within(bar).getByTestId('day-bar-locked')).toHaveTextContent('−22,10 €');
        expect(screen.getByTestId('omega-kpi-locked')).toHaveTextContent('−30,00 €');
        expect(screen.getByTestId('omega-kpi-locked')).toHaveTextContent('di oggi −22,10 €');
    });
});
