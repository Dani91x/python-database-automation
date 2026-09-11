// Test COMPONENTE della pagina Safe Strategy (radar + bot).
// Provider del radar e data-layer del bot mockati: nessuna rete.
// Copre header/stato bot, KPI, tabella trade con cash out e il flusso
// "Investi" da un segnale (richiesta 'place' accodata con gli id giusti),
// piu' le regressioni money-critical: modalita' del TRADE nel cash out,
// feed stantio, tennis col book, sync parametri senza loop, LIVE ereditato.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import { DEFAULT_PARAMS } from '@/lib/safeStrategy';


// Questi test montano la pagina/sheet INTERI (decine di campi, Radix, portali):
// su una macchina carica il default di 5 s di vitest scade per LENTEZZA, non per
// un difetto. Timeout esplicito: la suite deve essere verde anche sotto carico.
vi.setConfig({ testTimeout: 20_000 });

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

vi.mock('@/lib/safeBot', async (orig) => {
    const actual = await orig<typeof import('@/lib/safeBot')>();
    return {
        ...actual,
        fetchSafeState: vi.fn(),
        fetchSafeTrades: vi.fn(async () => []),
        fetchSafeRequests: vi.fn(async () => []),
        fetchOpportunities: vi.fn(async () => []),
        subscribeSafeBot: vi.fn(() => () => {}),
        subscribeOpportunities: vi.fn(() => () => {}),
        requestSafe: vi.fn(async () => 123),
        activateSafe: vi.fn(async () => ({})),
        stopSafe: vi.fn(),
        updateSafeParams: vi.fn(),
    };
});

const scanState = vi.hoisted(() => ({
    football: [] as unknown[],
    tennis: [] as unknown[],
    signals: [] as unknown[],
    scanStatus: null as unknown,
    saveParams: vi.fn(),
}));
vi.mock('@/components/safestrategy/SafeStrategyProvider', () => ({
    useSafeStrategy: () => ({
        football: scanState.football,
        tennis: scanState.tennis,
        signals: scanState.signals,
        scanStatus: scanState.scanStatus,
        params: DEFAULT_PARAMS,
        saveParams: scanState.saveParams,
        resetParams: vi.fn(),
    }),
}));

import SafeStrategy from './SafeStrategy';
import { fetchSafeState, fetchOpportunities, fetchSafeRequests, requestSafe } from '@/lib/safeBot';

const mState = vi.mocked(fetchSafeState);
const mOpps = vi.mocked(fetchOpportunities);
const mRequests = vi.mocked(fetchSafeRequests);
const mRequest = vi.mocked(requestSafe);

const CONTROL = {
    id: 1, status: 'running', mode: 'paper',
    params: { stake: { laySize: 6, backSize: 4 }, commission_pct: 5 },
    stats: { realized_today: 12.5, realized_total: 40, open_liability: 30, trades_open: 1 },
    error: null, started_at: null, stopped_at: null, heartbeat_at: null,
};

const OPEN_TRADE = {
    id: 9, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'esatto',
    market_id: '1.5', market_type: 'CORRECT_SCORE', selection_id: 77, selection_name: 'Any Other Home Win',
    side: 'lay', mode: 'paper', price: 40, size: 5, liability: 195, commission: 0.05,
    minute_at_entry: 50, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
    placed_at: '2026-09-10T10:00:00Z', settled_at: null, origin: 'auto',
    closes_trade_id: null, signal_key: 'e1:esatto:home:1-0', meta: null,
};

const secondsAgo = (s: number) => new Date(Date.now() - s * 1000).toISOString();

// una partita monitorata col Match Odds risolvibile (id dentro odds.<lato>)
const FOOTBALL_MONITOR = {
    eventId: 'e1',
    updatedAt: secondsAgo(2),
    payload: {
        media: null, event_name: 'Roma vs Lazio', home: 'Roma', away: 'Lazio',
        competition: 'Serie A', open_date: null, inplay: true,
        mo_market_id: '1.1', mo_status: 'OPEN',
        odds: {
            home: { selection_id: 11, ltp: 1.31, back: 1.3, lay: 1.32, back_size: 250, lay_size: 180 },
            draw: null,
            away: { selection_id: 12, back: 9, lay: 9.4 },
        },
        minute: 60, score_home: 1, score_away: 0, red_home: 0, red_away: 0, pre_ko: null,
        cs: {
            market_id: '1.5', status: 'OPEN',
            selections: [{ selection_id: 77, name: 'Any Other Home Win', back: 38, lay: 42, back_size: 90 }],
            any_other_home: null, any_other_away: null,
        },
    },
    ctx: { home: 'Roma', away: 'Lazio', inplay: true, minute: 60, scoreHome: 1, scoreAway: 0 },
    evaluations: [],
    preMatchMissing: false,
};

const TENNIS_MONITOR = {
    eventId: 't1',
    updatedAt: secondsAgo(2),
    payload: {
        media: null, event_name: 'Sinner v Alcaraz', p1: 'Sinner', p2: 'Alcaraz',
        competition: 'ATP', open_date: null, inplay: true,
        mo_market_id: '2.1', mo_status: 'OPEN',
        odds: {
            p1: { selection_id: 501, back: 1.5, lay: 1.52, back_size: 300, lay_size: 200 },
            p2: { selection_id: 502, back: 2.9, lay: 3.0 },
        },
        sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 },
    },
    ctx: { p1: 'Sinner', p2: 'Alcaraz', inplay: true, sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 } },
    evaluation: { variant: 'tennis', conditions: [], allMet: false },
};

const TENNIS_TRADE = {
    ...OPEN_TRADE, id: 21, event_id: 't1', event_name: 'Sinner v Alcaraz', sport: 'tennis', strategy: 'tennis',
    market_id: '2.1', market_type: 'MATCH_ODDS', selection_id: 502, selection_name: 'Alcaraz',
    side: 'lay', price: 3, size: 10, liability: 20, signal_key: null,
};

const SIGNAL = {
    key: 'e1:base:1-0', sport: 'calcio', variant: 'base', eventId: 'e1',
    matchLabel: 'Roma – Lazio', headline: 'BANCA il pareggio', side: 'BACK',
    selection: 'Roma', entryOdds: 1.3, entrySize: 250,
    contextAtTrigger: '60′ · 1-0', triggeredAtMs: Date.now(), status: 'active', expiredAtMs: null,
};

const OPP_ROW = {
    event_id: 'e1', sport: 'calcio', updated_at: secondsAgo(3),
    payload: {
        minute: 60, score_home: 1, score_away: 0, event_name: 'Roma vs Lazio',
        opps: [{
            market_type: 'OVER_UNDER_25', market_name: 'Over/Under 2.5', line: 2.5,
            market_id: '1.9', selection_id: 1, selection_name: 'Over 2.5', side: 'back',
            price: 2.1, size_available: 50, p_model: 0.55, p_implied: 0.48, edge: 0.07,
            ev: 0.15, confidence: 0.6, rationale: null,
        }],
    },
};

beforeEach(() => {
    vi.clearAllMocks();
    scanState.football = [FOOTBALL_MONITOR];
    scanState.tennis = [];
    scanState.signals = [SIGNAL];
    scanState.scanStatus = { id: 'scanner', payload: { calcio_inplay: 1 }, updated_at: secondsAgo(2) };
    mState.mockResolvedValue({
        control: CONTROL as never,
        trades: [OPEN_TRADE] as never,
        aggregates: {
            realized_today: 12.5, realized_total: 40, open_liability: 30,
            open_count: 1, won: 2, lost: 1,
        },
    });
    mOpps.mockResolvedValue([]);
    mRequests.mockResolvedValue([]);
    mRequest.mockResolvedValue(123);
});

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <SafeStrategy />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

async function openTradesTab(user: ReturnType<typeof userEvent.setup>) {
    await screen.findByTestId('bot-status');
    await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
    return (await screen.findAllByTestId('safe-trade-row'))[0];
}

describe('pagina Safe Strategy', () => {
    it('mostra intestazione, stato bot e modalita PAPER', async () => {
        renderPage();
        expect(await screen.findByText(/SAFE STRATEGY/)).toBeInTheDocument();
        expect(await screen.findByTestId('bot-status')).toHaveTextContent('BOT IN CORSA');
        expect(await screen.findByTestId('mode-banner')).toHaveTextContent(/PAPER/);
    });

    it('non promette piu che nessun ordine venga piazzato', async () => {
        renderPage();
        await screen.findByTestId('bot-status');
        expect(screen.queryByText(/Nessun ordine viene mai piazzato/)).toBeNull();
    });

    it('KPI: segnali attivi, trade aperti e P&L', async () => {
        renderPage();
        expect(await screen.findByText('Segnali attivi')).toBeInTheDocument();
        expect(await screen.findByText('Trade aperti')).toBeInTheDocument();
        expect((await screen.findAllByText('+12,50 €')).length).toBeGreaterThan(0);
        expect((await screen.findAllByText('+40,00 €')).length).toBeGreaterThan(0);
    });

    // M-15: "Trade aperti" = POSIZIONI VIVE. Una gamba di CHIUSURA non e' una
    // posizione e non va contata; una copertura completa (hedged) nemmeno.
    it('M-15: "Trade aperti" conta le posizioni vive, non le chiusure ne le hedged complete', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [
                OPEN_TRADE,
                { ...OPEN_TRADE, id: 11, status: 'pending', signal_key: null },
                // gamba di chiusura: NON e' una posizione
                { ...OPEN_TRADE, id: 12, status: 'open', closes_trade_id: 9, signal_key: null },
                // coperta del tutto: liability azzerata, non e' viva
                { ...OPEN_TRADE, id: 13, status: 'hedged', signal_key: null, meta: { hedge: { fraction: 1, complete: true } } },
                // coperta A META': resta viva
                { ...OPEN_TRADE, id: 14, status: 'hedged', signal_key: null, meta: { hedge: { fraction: 0.4, complete: false, remaining_liability: 117 } } },
            ] as never,
            aggregates: null,
        });
        renderPage();
        const tile = await screen.findByTestId('safe-kpi-open');
        expect(within(tile).getByText('3')).toBeInTheDocument();
        expect(within(tile).getByTestId('safe-open-sub')).toHaveTextContent('1 coperte in parte');
    });

    it('la tab Trade elenca il trade aperto col cash out', async () => {
        const user = userEvent.setup();
        renderPage();
        const row = await openTradesTab(user);
        expect(within(row).getByText('Roma vs Lazio')).toBeInTheDocument();
        expect(within(row).getByText('LAY')).toBeInTheDocument();
        expect(within(row).getByText('APERTO')).toBeInTheDocument();
        // lay 5 @40 -> vince -195 / perde +5 ; back @38: locked = 5 - 200/38 = -0.26
        expect(within(row).getByTestId('cashout-trigger')).toBeEnabled();
    });

    it('dal segnale si accoda una richiesta place con gli id risolti dal feed', async () => {
        const user = userEvent.setup();
        renderPage();
        const btn = await screen.findByTestId('invest-place');
        expect(btn).toHaveTextContent('Piazza (PAPER)');
        await user.click(btn);
        expect(mRequest).toHaveBeenCalledTimes(1);
        const [kind, payload] = mRequest.mock.calls[0];
        expect(kind).toBe('place');
        expect(payload).toMatchObject({
            event_id: 'e1',
            sport: 'calcio',
            mode: 'paper',
            market_id: '1.1',
            market_type: 'MATCH_ODDS',
            selection_id: 11,
            selection_name: 'Roma',
            side: 'back',
            price: 1.3,
            strategy: 'base',
            signal_key: 'e1:base:1-0',
            // review 11/09 H1/L1: un solo trade per segnale (dedupe del servizio) e
            // contesto d'ingresso (minuto/punteggio) dal feed
            idempotency_key: 'sig:e1:base:1-0',
            minute: 60,
            score: '1-0',
        });
        // stake precompilato dai parametri del bot (stake.backSize = 4)
        expect(payload).toMatchObject({ size: 4 });
    });

    it('trade MANUALE piazzato da un segnale: agganciato alla card tramite meta.idempotency_key (H1)', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [{ ...OPEN_TRADE, id: 12, origin: 'manual', strategy: 'manual', signal_key: null,
                       meta: { manual: true, idempotency_key: 'sig:e1:base:1-0' } }] as never,
            aggregates: { realized_today: 0, realized_total: 0, open_liability: 0, open_count: 1, won: 0, lost: 0 },
        });
        renderPage();
        await screen.findByTestId('bot-status');
        // la card mostra lo stato del trade, NON il bottone "Piazza" (niente secondo trade)
        expect(await screen.findByTestId('signal-trade')).toBeInTheDocument();
        expect(screen.queryByTestId('invest-place')).toBeNull();
    });

    it('la gamba di chiusura tagliata dalla liquidita e marcata parziale', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [
                { ...OPEN_TRADE, status: 'hedged', pnl: 1.2, settled_at: '2026-09-10T10:30:00Z', meta: { locked_pnl: 1.2 } },
                {
                    ...OPEN_TRADE, id: 10, side: 'back', price: 38, size: 3, status: 'open',
                    closes_trade_id: 9, signal_key: null, meta: { size_capped_from: 5.13 },
                },
            ] as never,
            aggregates: null,
        });
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
        expect(await screen.findByTestId('cashout-capped')).toHaveTextContent('parziale');
    });

    it('senza id di selezione nel feed l azione resta non disponibile', async () => {
        scanState.football = [{
            ...FOOTBALL_MONITOR,
            payload: {
                ...FOOTBALL_MONITOR.payload,
                odds: { home: { back: 1.3, lay: 1.32 }, draw: null, away: null },
            },
        }];
        renderPage();
        expect(await screen.findByTestId('signal-no-placement')).toBeInTheDocument();
        expect(screen.queryByTestId('invest-place')).toBeNull();
    });

    it('se esiste gia un trade per il segnale mostra il suo stato al posto dell azione', async () => {
        scanState.signals = [{ ...SIGNAL, key: 'e1:esatto:home:1-0' }];
        renderPage();
        expect(await screen.findByTestId('signal-trade')).toHaveTextContent('APERTO');
        expect(screen.queryByTestId('invest-place')).toBeNull();
    });
});

describe('Safe Strategy — cash out con la modalita del TRADE (CRITICAL-2)', () => {
    it('pagina LIVE ma trade paper: nessuna doppia conferma "soldi veri"', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: { ...CONTROL, mode: 'live' } as never,
            trades: [OPEN_TRADE] as never,
            aggregates: null,
        });
        renderPage();
        expect(await screen.findByTestId('mode-banner')).toHaveTextContent(/LIVE/);
        const row = await openTradesTab(user);
        await user.click(within(row).getByTestId('cashout-trigger'));
        await screen.findByTestId('cashout-confirm');
        expect(screen.queryByText(/Modalità LIVE: soldi veri/)).toBeNull();
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(mRequest).toHaveBeenCalledWith('cashout', { trade_id: 9, fraction: 1 });
    });

    it('pagina PAPER ma trade live: doppia conferma e avviso soldi veri', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [{ ...OPEN_TRADE, mode: 'live' }] as never,
            aggregates: null,
        });
        renderPage();
        const row = await openTradesTab(user);
        await user.click(within(row).getByTestId('cashout-trigger'));
        expect(await screen.findByText(/Modalità LIVE: soldi veri/)).toBeInTheDocument();
        await user.click(screen.getByTestId('cashout-confirm'));
        expect(screen.getByTestId('cashout-confirm')).toHaveTextContent(/Confermi/);
        expect(mRequest).not.toHaveBeenCalled();
    });

    it('anche nella card del segnale il cash out usa la modalita del trade', async () => {
        const user = userEvent.setup();
        scanState.signals = [{ ...SIGNAL, key: 'e1:esatto:home:1-0' }];
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [{ ...OPEN_TRADE, mode: 'live' }] as never,
            aggregates: null,
        });
        renderPage();
        const card = await screen.findByTestId('signal-trade');
        await user.click(within(card).getByTestId('cashout-trigger'));
        expect(await screen.findByText(/Modalità LIVE: soldi veri/)).toBeInTheDocument();
    });
});

describe('Safe Strategy — un solo cash out per trade (HIGH-1)', () => {
    it('gamba di chiusura gia in coda: bottone spento', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [
                OPEN_TRADE,
                { ...OPEN_TRADE, id: 10, side: 'back', price: 38, size: 5.13, status: 'pending', closes_trade_id: 9, signal_key: null },
            ] as never,
            aggregates: null,
        });
        renderPage();
        const row = await openTradesTab(user);
        expect(within(row).getByTestId('cashout-trigger')).toBeDisabled();
    });

    it('richiesta cashout pending sul DB: bottone spento', async () => {
        const user = userEvent.setup();
        mRequests.mockResolvedValue([
            { id: 5, kind: 'cashout', payload: { trade_id: 9, fraction: 1 }, status: 'pending', result: null, created_at: secondsAgo(1), updated_at: null },
        ]);
        renderPage();
        const row = await openTradesTab(user);
        expect(within(row).getByTestId('cashout-trigger')).toBeDisabled();
    });
});

describe('Safe Strategy — feed stantio (HIGH-2)', () => {
    it('riga vecchia E scanner morto: cash out e Investi spenti con motivo', async () => {
        const user = userEvent.setup();
        scanState.football = [{ ...FOOTBALL_MONITOR, updatedAt: secondsAgo(30) }];
        scanState.scanStatus = { id: 'scanner', payload: {}, updated_at: secondsAgo(90) };
        renderPage();
        const invest = await screen.findByTestId('invest-place');
        expect(invest).toBeDisabled();
        expect(screen.getByTestId('invest-disabled-reason')).toHaveTextContent('quote non aggiornate (30s)');
        const row = await openTradesTab(user);
        expect(within(row).getByTestId('cashout-trigger')).toBeDisabled();
        expect(within(row).getByTestId('feed-age')).toHaveTextContent('30s');
    });

    it('riga vecchia ma scanner vivo (write-on-change): badge eta, bottoni attivi', async () => {
        const user = userEvent.setup();
        scanState.football = [{ ...FOOTBALL_MONITOR, updatedAt: secondsAgo(30) }];
        scanState.scanStatus = { id: 'scanner', payload: {}, updated_at: secondsAgo(2) };
        renderPage();
        expect(await screen.findByTestId('invest-place')).toBeEnabled();
        expect(screen.getByTestId('feed-age')).toHaveTextContent('feed 30s');
        const row = await openTradesTab(user);
        expect(within(row).getByTestId('cashout-trigger')).toBeEnabled();
        expect(within(row).getByTestId('feed-age')).toHaveTextContent('30s');
    });
});

describe('Safe Strategy — tennis (HIGH-3)', () => {
    it('un trade tennis riceve il book dal feed tennis: cash out attivo e live "set/game"', async () => {
        const user = userEvent.setup();
        scanState.tennis = [TENNIS_MONITOR];
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [TENNIS_TRADE] as never,
            aggregates: null,
        });
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /Tennis/ }));
        await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
        const row = await screen.findByTestId('safe-trade-row');
        expect(within(row).getByText('Sinner v Alcaraz')).toBeInTheDocument();
        expect(within(row).getByText('set 1-0 · game 3-2')).toBeInTheDocument();
        // lay 10 @3 (vince -20 / perde +10) coperto back @2.9: locked = 10 - 30/2.9 = -0.34
        const trigger = within(row).getByTestId('cashout-trigger');
        expect(trigger).toBeEnabled();
        // formato normativo (DESIGN_SYSTEM.md §2): virgola decimale, € dopo il numero, meno U+2212
        expect(trigger).toHaveTextContent('−0,34 €');
    });
});

describe('Safe Strategy — sync parametri (HIGH-4)', () => {
    it('payload server con chiave ignota: nessun salvataggio (niente loop)', async () => {
        mState.mockResolvedValue({
            control: {
                ...CONTROL,
                params: { ...CONTROL.params, base: { ...DEFAULT_PARAMS.base, unknown_key: 1, legacy: null } },
            } as never,
            trades: [] as never,
            aggregates: null,
        });
        renderPage();
        await screen.findByTestId('bot-status');
        // qualche render in piu' (tab) per dare al loop l'occasione di scattare
        const user = userEvent.setup();
        await user.click(await screen.findByRole('tab', { name: /Monitor/ }));
        expect(scanState.saveParams).not.toHaveBeenCalled();
    });

    it('condizione davvero diversa sul server: UN solo salvataggio normalizzato', async () => {
        mState.mockResolvedValue({
            control: {
                ...CONTROL,
                params: { ...CONTROL.params, base: { ...DEFAULT_PARAMS.base, minuteMin: 70, unknown_key: 1 } },
            } as never,
            trades: [] as never,
            aggregates: null,
        });
        renderPage();
        await screen.findByTestId('bot-status');
        const user = userEvent.setup();
        await user.click(await screen.findByRole('tab', { name: /Monitor/ }));
        expect(scanState.saveParams).toHaveBeenCalledTimes(1);
        const saved = scanState.saveParams.mock.calls[0][0];
        expect(saved.base.minuteMin).toBe(70);
        expect('unknown_key' in saved.base).toBe(false);
    });
});

describe('Safe Strategy — LIVE ereditato dal control (MEDIUM-4)', () => {
    it('banner LIVE ma nessun piazzamento senza conferma in questa sessione', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: { ...CONTROL, mode: 'live' } as never,
            trades: [] as never,
            aggregates: null,
        });
        renderPage();
        expect(await screen.findByTestId('mode-banner')).toHaveTextContent(/MODALITÀ LIVE/);
        const btn = await screen.findByTestId('invest-place');
        expect(btn).toHaveTextContent('Piazza (LIVE)');
        await user.click(btn); // arma
        await user.click(btn); // confermerebbe: invece chiede la conferma LIVE di sessione
        expect(mRequest).not.toHaveBeenCalled();
        expect(await screen.findByText(/Passare a LIVE \(soldi veri\)\?/)).toBeInTheDocument();
    });
});

const COMBO_ROW = {
    event_id: 'e1', sport: 'calcio', updated_at: secondsAgo(3),
    payload: {
        minute: 60, score_home: 1, score_away: 0, event_name: 'Roma vs Lazio',
        kinds: { model: 1, combo: 1 },
        opps: [
            OPP_ROW.payload.opps[0],
            {
                kind: 'combo', combo: 'under_stack', market_type: 'OVER_UNDER_25', market_name: 'Under stack', line: null,
                market_id: '1.25', selection_id: 10, selection_name: 'Under 2.5 + Under 3.5', side: 'back',
                price: 1.5, size_available: 40, p_model: 0.7, p_implied: 0.66, edge: 0.04, ev: 0.06, confidence: 0.9,
                rationale: null, total_stake: 10, locked_profit_per_eur: 0.03, best_case_per_eur: 0.25,
                legs: [
                    { market_type: 'OVER_UNDER_25', market_id: '1.25', selection_id: 10, selection_name: 'Under 2.5', side: 'back', price: 1.9, size_available: 40, stake_ratio: 0.6, stake: 6 },
                    { market_type: 'OVER_UNDER_35', market_id: '1.35', selection_id: 11, selection_name: 'Under 3.5', side: 'lay', price: 1.3, size_available: 25, stake_ratio: 0.4, stake: 4 },
                ],
            },
        ],
    },
};
const TENNIS_OPP_ROW = {
    event_id: 't1', sport: 'tennis', updated_at: secondsAgo(3),
    payload: {
        minute: null, score_home: null, score_away: null, event_name: 'Sinner v Alcaraz',
        sets: { p1: 1, p2: 0 }, games: { p1: 3, p2: 2 },
        opps: [{
            kind: 'tennis', market_type: 'MATCH_ODDS', market_name: 'Match Odds', line: null,
            market_id: '2.1', selection_id: 501, selection_name: 'Sinner', side: 'back',
            price: 1.4, size_available: 300, p_model: 0.8, p_implied: 0.71, edge: 0.09, ev: 0.12, confidence: 0.75,
            rationale: null, extra: { retire_risk: 0.02, best_of: 3, server: 'Alcaraz', momentum_against: false },
        }],
    },
};

describe('Safe Strategy — opportunita per tipo, combinazioni e tennis', () => {
    it('chip per tipo con conteggi; il filtro tipo isola la combinazione', async () => {
        const user = userEvent.setup();
        mOpps.mockResolvedValue([COMBO_ROW as never]);
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /Opportunità modello/ }));
        const chips = await screen.findByTestId('opp-kind-filter');
        expect(within(chips).getByRole('button', { name: 'tutte 2' })).toBeInTheDocument();
        expect(within(chips).getByRole('button', { name: 'Modello 1' })).toBeInTheDocument();
        expect(within(chips).getByRole('button', { name: 'Combinazione 1' })).toBeInTheDocument();
        expect(within(chips).getByRole('button', { name: 'Anomalia 0' })).toBeInTheDocument();
        expect(screen.getAllByTestId('opp-row')).toHaveLength(2);
        await user.click(within(chips).getByRole('button', { name: 'Anomalia 0' }));
        expect(await screen.findByTestId('opp-filtered-empty')).toHaveTextContent(/tipo ANOMALIA/);
        await user.click(within(chips).getByRole('button', { name: 'Combinazione 1' }));
        expect(await screen.findAllByTestId('opp-row')).toHaveLength(1);
        expect(screen.getByTestId('opp-row')).toHaveAttribute('data-kind', 'combo');
    });

    it('combinazione: "Piazza" accoda UNA richiesta per gamba, stake scalato, stesso prefisso di idempotenza e modalita', async () => {
        const user = userEvent.setup();
        mOpps.mockResolvedValue([COMBO_ROW as never]);
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /Opportunità modello/ }));
        await user.click(screen.getByTestId('opp-kind-filter').querySelector('button[title*="gambe"]') as HTMLElement);
        const combo = (await screen.findAllByTestId('opp-row')).find((r) => r.getAttribute('data-kind') === 'combo') as HTMLElement;
        await user.click(within(combo).getByTestId('invest-place'));
        await waitFor(() => expect(mRequest).toHaveBeenCalledTimes(2));
        const calls = mRequest.mock.calls.map((c) => c[1] as Record<string, unknown>);
        expect(mRequest.mock.calls.every((c) => c[0] === 'place')).toBe(true);
        // stake totale = opps_stake di default (5) → 60/40
        expect(calls[0]).toMatchObject({ event_id: 'e1', sport: 'calcio', mode: 'paper', market_id: '1.25', selection_id: 10, side: 'back', price: 1.9, size: 3, strategy: 'model', kind: 'combo', combo: 'under_stack', combo_leg: 1, combo_legs: 2, combo_total_stake: 5 });
        expect(calls[1]).toMatchObject({ market_id: '1.35', selection_id: 11, side: 'lay', price: 1.3, size: 2, combo_leg: 2 });
        const k0 = String(calls[0].idempotency_key);
        const k1 = String(calls[1].idempotency_key);
        expect(k0).toMatch(/^combo:e1:under_stack:/);
        expect(k0.replace(/:\d+\/\d+$/, '')).toBe(k1.replace(/:\d+\/\d+$/, ''));
        expect(k0.endsWith(':1/2')).toBe(true);
        expect(k1.endsWith(':2/2')).toBe(true);
    });

    it('tennis: tab Opportunità tennis con la card e piazzamento con sport tennis e kind', async () => {
        const user = userEvent.setup();
        mOpps.mockResolvedValue([TENNIS_OPP_ROW as never]);
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /^Tennis \(/ }));
        await user.click(await screen.findByRole('tab', { name: /Opportunità tennis \(1\)/ }));
        expect(await screen.findByTestId('opp-group')).toHaveTextContent('Sinner v Alcaraz');
        expect(screen.getByTestId('opp-kind')).toHaveTextContent('TENNIS');
        expect(screen.getByTestId('tennis-extra')).toHaveTextContent('set 1-0 · game 3-2');
        await user.click(screen.getByTestId('invest-place'));
        await waitFor(() => expect(mRequest).toHaveBeenCalledTimes(1));
        expect(mRequest.mock.calls[0][1]).toMatchObject({ event_id: 't1', sport: 'tennis', kind: 'tennis', strategy: 'model', selection_id: 501, mode: 'paper' });
    });

    it('pannello Rischio nei KPI: liability vs cap e stop perdita dal control.stats', async () => {
        mState.mockResolvedValue({
            control: { ...CONTROL, stats: { ...CONTROL.stats, risk: { daily_liability: 240, daily_cap: 500, loss_stop_active: true, daily_loss_stop: -50 }, opps: { model: 2, anomaly: 1, combo: 0, tennis: 3 } } } as never,
            trades: [OPEN_TRADE] as never,
            aggregates: null,
        });
        renderPage();
        const panel = await screen.findByTestId('risk-panel');
        expect(panel).toHaveAttribute('data-loss-stop', 'active');
        expect(within(panel).getByTestId('risk-liability')).toHaveTextContent('240,00 €');
        expect(within(panel).getByText('impegnato oggi / cap 500,00 €')).toBeInTheDocument();
        expect(within(panel).getByTestId('loss-stop')).toHaveTextContent('STOP PERDITA');
        expect(within(panel).getByTestId('risk-opp-counts')).toHaveTextContent('TENNIS 3');
    });
});

describe('Safe Strategy — opportunita filtrate (MEDIUM-5)', () => {
    it('filtri che escludono tutto: stato vuoto esplicativo', async () => {
        const user = userEvent.setup();
        mOpps.mockResolvedValue([OPP_ROW as never]);
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /Opportunità modello/ }));
        expect(await screen.findByTestId('opp-group')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: '85%' }));
        expect(await screen.findByTestId('opp-filtered-empty')).toHaveTextContent(/confidenza ≥ 85%/);
        expect(screen.queryByTestId('opp-group')).toBeNull();
    });
});
