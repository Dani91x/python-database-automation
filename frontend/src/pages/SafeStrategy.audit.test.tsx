// ============================================================================
// Pagina Safe Strategy — regressioni dell'indagine 11/09/2026 a livello pagina:
//   C-01  UNA sola giornata operativa (giorno di PIAZZAMENTO dal DB)
//   H-03  KPI liability con "di cui in verifica su Betfair"
//   H-16  blocco ATTIVITÀ DEL SERVIZIO (prima invisibile)
//   M-04  UN solo toast per POSIZIONE regolata, col P&L della POSIZIONE
//   M-21  contatori delle opportunità uguali fra tab e pannello Rischio,
//         azione "Annulla" sulle riserve, esito di ogni richiesta
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { romeDay, dayLabel } from '@/lib/dailyHistory';
import { act, render, screen, within, waitFor } from '@testing-library/react';
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

/** callback del canale realtime: la si richiama per simulare un cambiamento sul DB */
const rt = vi.hoisted(() => ({ onChange: null as null | (() => void) }));

vi.mock('@/lib/safeBot', async (orig) => {
    const actual = await orig<typeof import('@/lib/safeBot')>();
    return {
        ...actual,
        fetchSafeState: vi.fn(),
        fetchSafeTrades: vi.fn(async () => []),
        fetchSafeRequests: vi.fn(async () => []),
        fetchSafeActivity: vi.fn(async () => []),
        fetchOpportunities: vi.fn(async () => []),
        subscribeSafeBot: vi.fn((cb: () => void) => { rt.onChange = cb; return () => {}; }),
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
import { RELOAD_DEBOUNCE_MS } from '@/components/safestrategy/useSafeBot';
import { fetchSafeState, fetchSafeActivity, fetchOpportunities, fetchSafeRequests, requestSafe } from '@/lib/safeBot';
import { toast } from 'sonner';

const mState = vi.mocked(fetchSafeState);
const mActivity = vi.mocked(fetchSafeActivity);
const mOpps = vi.mocked(fetchOpportunities);
const mRequests = vi.mocked(fetchSafeRequests);
const mRequest = vi.mocked(requestSafe);
const mToastSuccess = vi.mocked(toast.success);
const mToastError = vi.mocked(toast.error);
const mToastWarning = vi.mocked(toast.warning);

const secondsAgo = (s: number) => new Date(Date.now() - s * 1000).toISOString();

const CONTROL = {
    id: 1, status: 'running', mode: 'paper',
    params: { stake: { laySize: 6, backSize: 4 }, commission_pct: 5, variants: ['base'] },
    stats: {
        realized_today: 2, realized_total: 40, open_liability: 130, trades_open: 2,
        params_effective: { commission_pct: 5, opps_stake: 5, min_stake: 2, variants: ['base'] },
    },
    error: null, started_at: null, stopped_at: null, heartbeat_at: null,
};

const OPEN = {
    id: 9, event_id: 'e1', event_name: 'Roma vs Lazio', sport: 'calcio', strategy: 'manual',
    market_id: '1.30', market_type: 'OVER_UNDER_35', selection_id: 47973, selection_name: 'Under 3.5',
    side: 'back', mode: 'paper', price: 1.38, size: 10, liability: 10, commission: 0.05,
    minute_at_entry: 62, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
    placed_at: new Date().toISOString(), settled_at: null, origin: 'manual',
    closes_trade_id: null, signal_key: null, meta: null as Record<string, unknown> | null,
};

const AGG = {
    realized_today: 2, realized_total: 40, open_liability: 130, open_count: 2, won: 3, lost: 1,
    reconciling_liability: 117, reconciling_count: 1, day_liability: 260, day_trades: 4,
    legs_today: 4, events_today: 2, won_today: 2, lost_today: 1,
    operating_day: romeDay(),
};

const ACTIVITY = [
    { id: 3, ts: '2026-09-11T18:05:00Z', kind: 'risk_block', payload: { event_name: 'Roma vs Lazio', reason: 'daily_liability_cap' } },
    { id: 2, ts: '2026-09-11T18:04:00Z', kind: 'skip', payload: { event_name: 'Inter vs Milan', reason: 'spread_troppo_ampio' } },
    { id: 1, ts: '2026-09-11T18:03:00Z', kind: 'place', payload: { event_name: 'Roma vs Lazio', side: 'back', selection_name: 'Under 3.5', size: 10, price: 1.38 } },
];

/** forza un nuovo giro di lettura (come una notifica realtime) e attende */
/** Notifica realtime + attesa della finestra di COALESCENZA dell'hook: le
 *  notifiche sono debounced (RELOAD_DEBOUNCE_MS) perche' un settlement ne
 *  produce quattro o piu'. Il test deve aspettare la finestra, non pretendere
 *  una ricarica per notifica. */
async function reloadFromDb() {
    await act(async () => {
        rt.onChange?.();
        await new Promise((r) => setTimeout(r, RELOAD_DEBOUNCE_MS + 50));
    });
}

beforeEach(() => {
    vi.clearAllMocks();
    rt.onChange = null;
    scanState.football = [];
    scanState.tennis = [];
    scanState.signals = [];
    scanState.scanStatus = { id: 'scanner', payload: { calcio_inplay: 1 }, updated_at: secondsAgo(2) };
    mState.mockResolvedValue({
        control: CONTROL as never,
        trades: [OPEN] as never,
        aggregates: AGG as never,
        activity: ACTIVITY as never,
        params_effective: CONTROL.stats.params_effective as never,
        operating_day: romeDay(),
    });
    mActivity.mockResolvedValue([]);
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

describe('C-01 / H-03 — una sola giornata, una sola liability', () => {
    it('la giornata operativa è quella dichiarata dal DB (giorno di PIAZZAMENTO)', async () => {
        renderPage();
        // il giorno dichiarato dal DB (qui: oggi a Roma) compare identico in KPI e pannello Rischio
        const label = dayLabel(romeDay(), { year: false });
        expect(await screen.findByTestId('safe-operating-day')).toHaveTextContent(label);
        // KPI e pannello Rischio parlano dello STESSO giorno
        expect(screen.getByTestId('risk-day')).toHaveTextContent(label);
    });

    it('V/P di oggi dagli aggregates, non ricontati a mano', async () => {
        renderPage();
        expect(await screen.findByTestId('safe-operating-day')).toHaveTextContent('2V 1P');
        expect(screen.getByTestId('day-bar-line')).toHaveTextContent('2V 1P');
    });

    it('"Liability aperta" dichiara quanta parte è IN VERIFICA su Betfair', async () => {
        renderPage();
        const tile = await screen.findByTestId('safe-kpi-liability');
        expect(tile).toHaveTextContent('130,00 €');
        expect(within(tile).getByTestId('safe-liability-reconciling'))
            .toHaveTextContent('di cui in verifica su Betfair 117,00 €');
    });

    it('pannello Rischio: "impegnato oggi" e "rischio aperto ora" sono numeri DIVERSI e dichiarati', async () => {
        renderPage();
        const panel = await screen.findByTestId('risk-panel');
        expect(within(panel).getByTestId('risk-liability')).toHaveTextContent('260,00 €');
        expect(within(panel).getByText(/impegnato oggi/)).toBeInTheDocument();
        expect(within(panel).getByTestId('risk-open-liability')).toHaveTextContent('130,00 €');
        expect(within(panel).getByTestId('risk-reconciling')).toHaveTextContent('117,00 €');
    });
});

describe('H-16 — attività del servizio visibile', () => {
    it('il blocco elenca le righe con etichette italiane e marca le critiche', async () => {
        renderPage();
        const feed = await screen.findByTestId('safe-activity');
        const rows = within(feed).getAllByTestId('activity-row');
        expect(rows).toHaveLength(3);
        expect(rows[0]).toHaveAttribute('data-kind', 'risk_block');
        expect(rows[0]).toHaveAttribute('data-critical', '1');
        expect(rows[0]).toHaveTextContent('BLOCCATO DAL RISCHIO');
        expect(rows[0]).toHaveTextContent('cap di liability giornaliera raggiunto');
        expect(rows[1]).toHaveTextContent('NON ENTRATO');
        expect(rows[1]).toHaveTextContent('spread troppo ampio');
        expect(rows[2]).toHaveTextContent('ORDINE PIAZZATO');
        expect(screen.getByTestId('safe-activity-note')).toHaveTextContent('1 da guardare');
    });

    it('si può filtrare per evento', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByTestId('safe-activity');
        const filter = screen.getByTestId('activity-filter');
        await user.click(within(filter).getByRole('button', { name: 'Inter vs Milan' }));
        expect(screen.getAllByTestId('activity-row')).toHaveLength(1);
        expect(screen.getByTestId('activity-row')).toHaveTextContent('NON ENTRATO');
    });

    it('senza log: testo che spiega cosa manca, mai una lista muta', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never, trades: [] as never, aggregates: AGG as never,
            activity: [] as never, params_effective: null, operating_day: romeDay(),
        });
        renderPage();
        const feed = await screen.findByTestId('safe-activity');
        expect(feed).toHaveAttribute('data-empty', '1');
        expect(feed).toHaveTextContent(/safe_strategy_bot_v2\.sql/);
    });
});

describe('M-04 — UN solo toast per POSIZIONE regolata', () => {
    it('green-up in utile: un toast con il P&L della POSIZIONE, non due per gamba', async () => {
        const apertura = {
            ...OPEN, id: 70, side: 'lay', price: 55, size: 2.16, liability: 116.64,
            status: 'hedged', pnl: -22.1, settled_at: new Date().toISOString(),
            meta: { locked_pnl: -22.1, exit_kind: 'greenup', position_pnl: 1.9, position_result: 'won' },
        };
        const chiusura = {
            ...OPEN, id: 71, side: 'back', price: 4.9, size: 24.24, status: 'hedged',
            pnl: 24, settled_at: new Date().toISOString(), closes_trade_id: 70,
        };
        // primo caricamento senza regolate: nessun toast (si memorizza lo storico)
        mState.mockResolvedValue({
            control: CONTROL as never, trades: [] as never, aggregates: AGG as never,
            activity: [] as never, params_effective: null, operating_day: romeDay(),
        });
        renderPage();
        await screen.findByTestId('bot-status');
        expect(mToastSuccess).not.toHaveBeenCalled();
        // poi la posizione si regola: arriva la notifica realtime
        mState.mockResolvedValue({
            control: CONTROL as never, trades: [apertura, chiusura] as never, aggregates: AGG as never,
            activity: [] as never, params_effective: null, operating_day: romeDay(),
        });
        await reloadFromDb();
        await waitFor(() => expect(mToastSuccess).toHaveBeenCalled());
        // UNA sola notifica, con il P&L della POSIZIONE (+1,90 €) e non −22,10 €
        expect(mToastSuccess).toHaveBeenCalledTimes(1);
        expect(mToastError).not.toHaveBeenCalled();
        const [title, opts] = mToastSuccess.mock.calls[0] as [string, { description: string }];
        expect(title).toContain('Roma vs Lazio');
        expect(opts.description).toContain('+1,90 €');
    });
});

describe('M-21 — Annulla la riserva e vedi l esito', () => {
    it('la riserva pending si annulla dalla tabella (kind cancel)', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: CONTROL as never,
            trades: [{ ...OPEN, id: 40, status: 'pending' }] as never,
            aggregates: AGG as never,
            activity: [] as never, params_effective: null, operating_day: romeDay(),
        });
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
        await user.click(await screen.findByTestId('safe-cancel'));
        await waitFor(() => expect(mRequest).toHaveBeenCalledWith('cancel', { trade_id: 40 }));
    });

    it('richiesta rifiutata dal servizio: notifica col motivo', async () => {
        renderPage();
        await screen.findByTestId('bot-status');
        // il servizio risponde: RIFIUTATA, con il motivo
        mRequests.mockResolvedValue([{
            id: 5, kind: 'cancel', payload: { trade_id: 40 }, status: 'rejected',
            result: { rejected: true, message: 'in riconciliazione' },
            created_at: secondsAgo(1), updated_at: null,
        }]);
        await reloadFromDb();
        await waitFor(() => expect(mToastWarning).toHaveBeenCalled());
        const calls = mToastWarning.mock.calls;
        const [title, opts] = calls[calls.length - 1] as [string, { description?: string }];
        expect(title).toMatch(/Annullo: rifiutato/);
        expect(opts?.description).toBe('in riconciliazione');
    });
});

describe('M-21 — i contatori delle opportunità coincidono', () => {
    it('il tab conta le OPPORTUNITÀ, come il pannello Rischio', async () => {
        const user = userEvent.setup();
        mOpps.mockResolvedValue([{
            event_id: 'e1', sport: 'calcio', updated_at: secondsAgo(3),
            payload: {
                minute: 62, score_home: 2, score_away: 1, event_name: 'Roma vs Lazio',
                opps: [
                    { kind: 'model', market_type: 'OVER_UNDER_35', market_name: 'O/U 3.5', line: 3.5, market_id: '1.30', selection_id: 47973, selection_name: 'Under 3.5', side: 'back', price: 1.38, size_available: 80, p_model: 0.8, p_implied: 0.72, edge: 0.08, ev: 0.1, confidence: 0.8, rationale: null },
                    { kind: 'anomaly', market_type: 'OVER_UNDER_55', market_name: 'O/U 5.5', line: 5.5, market_id: '1.45', selection_id: 47973, selection_name: 'Under 5.5', side: 'back', price: 1.05, size_available: 10, p_model: 0.99, p_implied: 0.95, edge: 0.04, ev: 0.04, confidence: 0.9, rationale: null, rule: 'ou_ladder' },
                ],
            },
        } as never]);
        renderPage();
        await screen.findByTestId('bot-status');
        // 2 opportunità su 1 partita: il tab dice 2, non 1
        expect(await screen.findByRole('tab', { name: /Opportunità modello \(2\)/ })).toBeInTheDocument();
        const panel = screen.getByTestId('risk-panel');
        expect(within(panel).getByTestId('risk-opp-counts')).toHaveTextContent('MODELLO 1');
        expect(within(panel).getByTestId('risk-opp-counts')).toHaveTextContent('ANOMALIA 1');
        await user.click(screen.getByRole('tab', { name: /Opportunità modello/ }));
        expect(await screen.findAllByTestId('opp-row')).toHaveLength(2);
    });
});
