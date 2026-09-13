// ============================================================================
// Pagina Safe Strategy — CERTIFICAZIONE DI CHIAREZZA (12/09/2026).
//
// Il trader deve sapere esattamente cosa guardare. Qui le regressioni delle
// incoerenze trovate montando la pagina sui dati reali:
//   1. salute del FEED dalla stessa fonte di /omega e /mike (fetchScanStatus):
//      Safe urlava «feed: nessun dato — riavvia l'app desktop» e «Partite
//      monitorate 0» mentre lo scanner era vivo e le altre due pagine, sullo
//      STESSO feed unico, mostravano «feed vivo ⚽ 9 · 🎾 3»;
//   2. la LIABILITY si legge in un posto solo (la sua tile);
//   3. il tab Opportunità non promette "N partite con opportunità" quando le
//      opportunità sono zero;
//   4. l'ATTIVITÀ del servizio dice il NOME della partita, non l'event_id, e
//      il mercato in chiaro.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import { romeDay } from '@/lib/dailyHistory';
import { DEFAULT_PARAMS } from '@/lib/safeStrategy';

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
        fetchSafeActivity: vi.fn(async () => []),
        fetchOpportunities: vi.fn(async () => []),
        subscribeSafeBot: vi.fn(() => () => {}),
        subscribeOpportunities: vi.fn(() => () => {}),
        requestSafe: vi.fn(async () => 1),
        activateSafe: vi.fn(async () => ({})),
        stopSafe: vi.fn(),
        updateSafeParams: vi.fn(),
    };
});

/** lo SCANNER letto direttamente dalla pagina (come Omega e Mike) */
const scan = vi.hoisted(() => ({ status: null as unknown }));
vi.mock('@/lib/safeStrategyScan', async (orig) => {
    const actual = await orig<typeof import('@/lib/safeStrategyScan')>();
    return { ...actual, fetchScanStatus: vi.fn(async () => scan.status) };
});

/** il PROVIDER: qui resta a mani vuote (sessione non risolta) — è il caso reale */
const provider = vi.hoisted(() => ({
    football: [] as unknown[],
    tennis: [] as unknown[],
    signals: [] as unknown[],
    scanStatus: null as unknown,
}));
vi.mock('@/components/safestrategy/SafeStrategyProvider', () => ({
    useSafeStrategy: () => ({
        football: provider.football,
        tennis: provider.tennis,
        signals: provider.signals,
        scanStatus: provider.scanStatus,
        params: DEFAULT_PARAMS,
        saveParams: vi.fn(),
        resetParams: vi.fn(),
    }),
}));

import SafeStrategy from './SafeStrategy';
import { fetchSafeState, fetchOpportunities } from '@/lib/safeBot';

const mState = vi.mocked(fetchSafeState);
const mOpps = vi.mocked(fetchOpportunities);

const secondsAgo = (s: number) => new Date(Date.now() - s * 1000).toISOString();

const CONTROL = {
    id: 1, status: 'running', mode: 'paper',
    params: { stake: { laySize: 2, backSize: 2 }, commission_pct: 5, variants: ['esatto'] },
    stats: { params_effective: { commission_pct: 5, opps_stake: 5, min_stake: 2 } },
    error: null, started_at: null, stopped_at: null,
    heartbeat_at: new Date().toISOString(),
};

const TRADE = {
    id: 47, event_id: '36050110', event_name: 'Bucheon FC 1995 – Jeju Utd', sport: 'calcio',
    strategy: 'esatto', market_id: '1.5', market_type: 'CORRECT_SCORE', selection_id: 77,
    selection_name: 'Altro risultato Casa', side: 'lay', mode: 'paper', price: 46, size: 2,
    liability: 90, commission: 0.05, minute_at_entry: 30, score_at_entry: '0-0',
    status: 'open', pnl: 0, bet_id: null, placed_at: new Date().toISOString(),
    settled_at: null, origin: 'auto', closes_trade_id: null, signal_key: null, meta: null,
};

const AGG = {
    realized_today: 1.9, realized_total: 10.98, open_liability: 300, open_count: 5,
    won: 1, lost: 0, day_liability: 472, legs_today: 6, events_today: 5,
    won_today: 1, lost_today: 0, operating_day: romeDay(),
};

/** attività com'è scritta DAVVERO dal servizio: solo event_id, motivo tecnico */
const ACTIVITY = [
    { id: 5, ts: secondsAgo(60), kind: 'risk_block', payload: { event_id: '36050110', market_type: 'CORRECT_SCORE', liability: 62, reason: 'per_event_liability_cap' } },
    { id: 4, ts: secondsAgo(120), kind: 'skip', payload: { event_id: '36050110', reason: 'spread_anomalo' } },
    { id: 3, ts: secondsAgo(180), kind: 'exit_wait', payload: { trade_id: 47, reason: 'lato_bancato_segna' } },
];

beforeEach(() => {
    vi.clearAllMocks();
    provider.football = [];
    provider.tennis = [];
    provider.signals = [];
    provider.scanStatus = null;
    scan.status = { id: 'scanner', payload: { calcio_inplay: 9, tennis_inplay: 3, source: 'stream' }, updated_at: secondsAgo(2) };
    mState.mockResolvedValue({
        control: CONTROL as never, trades: [TRADE] as never, aggregates: AGG as never,
        activity: ACTIVITY as never, params_effective: CONTROL.stats.params_effective as never,
        operating_day: romeDay(),
    });
    mOpps.mockResolvedValue([]);
});

function renderPage() {
    return render(
        <HelmetProvider><MemoryRouter><SafeStrategy /></MemoryRouter></HelmetProvider>,
    );
}

/**
 * CERT. 13/09 - SOSTITUISCE l'accesso DIRETTO alle righe di posizione.
 *
 * La sezione Operazioni di Safe ora mostra UNA RIGA PER PARTITA (tabella
 * condivisa `trading/EventPnlTable`) e le singole posizioni - con quote, stati
 * e bottoni di cash out - stanno nel DETTAGLIO, chiuso di default e apribile.
 * E' la richiesta dell'utente del 13/09: prima era un elenco piatto di gambe in
 * cui apertura e chiusura comparivano scollegate. I test che leggono
 * `safe-trade-row` devono quindi aprire prima il dettaglio, come il trader.
 *
 * Idempotente: apre solo le partite ancora chiuse, cosi si puo' richiamare dopo
 * un cambio di filtro senza richiudere quelle gia' aperte.
 */
async function apriPartite(user: ReturnType<typeof userEvent.setup>) {
    const bottoni = await screen.findAllByTestId(/^apri-/);
    for (const b of bottoni) {
        if (b.getAttribute('aria-expanded') === 'false') await user.click(b);
    }
}

describe('salute del feed: la STESSA fonte di /omega e /mike', () => {
    it('provider senza feed ma scanner vivo: feed VIVO e partite monitorate dallo scanner', async () => {
        renderPage();
        const health = await screen.findByTestId('service-health');
        expect(health).toHaveAttribute('data-feed', 'alive');
        expect(health).not.toHaveTextContent('nessun dato');
        expect(health).not.toHaveTextContent('riavvia');
        // i conteggi sono quelli dello scanner: 9 calcio + 3 tennis
        const tile = screen.getByTestId('safe-kpi-monitored');
        expect(tile).toHaveTextContent('12');
        expect(within(tile).getByTestId('safe-monitored-sub')).toHaveTextContent('⚽ 9 · 🎾 3');
    });

    it('scanner davvero fermo: il feed resta dichiarato FERMO (nessun falso verde)', async () => {
        scan.status = { id: 'scanner', payload: { calcio_inplay: 0, tennis_inplay: 0 }, updated_at: secondsAgo(600) };
        renderPage();
        const health = await screen.findByTestId('service-health');
        expect(health).toHaveAttribute('data-feed', 'stale');
    });

    it('vince la lettura PIÙ RECENTE fra provider e lettura diretta', async () => {
        provider.scanStatus = { id: 'scanner', payload: { calcio_inplay: 1, tennis_inplay: 0 }, updated_at: secondsAgo(300) };
        renderPage();
        const tile = await screen.findByTestId('safe-kpi-monitored');
        // la lettura diretta e' di 2 s fa: e' lei a comandare
        expect(within(tile).getByTestId('safe-monitored-sub')).toHaveTextContent('⚽ 9 · 🎾 3');
    });
});

describe('una sola liability, conteggi non duplicati', () => {
    it('la liability aperta si legge SOLO nella sua tile', async () => {
        renderPage();
        const tile = await screen.findByTestId('safe-kpi-liability');
        expect(tile).toHaveTextContent('300,00 €');
        expect(within(tile).getByTestId('safe-liability-sub')).toHaveTextContent('rischio vivo ora su 5 posizioni');
        expect(screen.queryByTestId('day-bar-liability')).toBeNull();
        expect(within(screen.getByTestId('risk-panel')).queryByTestId('risk-open-liability')).toBeNull();
        // il pannello Rischio mostra l'IMPEGNATO della giornata (altra grandezza)
        expect(screen.getByTestId('risk-liability')).toHaveTextContent('472,00 €');
    });

    it('"Trade aperti" non ripete le operazioni della giornata', async () => {
        renderPage();
        const tile = await screen.findByTestId('safe-kpi-open');
        expect(within(tile).getByTestId('safe-open-sub')).toHaveTextContent('vive adesso');
        expect(within(tile).getByTestId('safe-open-sub')).not.toHaveTextContent('oggi');
        // le operazioni della giornata stanno nella barra, una volta sola
        expect(screen.getByTestId('day-bar-counts')).toHaveTextContent('operazioni 6');
    });
});

describe('tab Opportunità: il tooltip non promette opportunità che non ci sono', () => {
    it('righe analizzate senza opportunità: 0 nel tab e tooltip coerente', async () => {
        mOpps.mockResolvedValue([
            { event_id: 'a', sport: 'calcio', updated_at: new Date().toISOString(), payload: { minute: 30, score_home: 0, score_away: 0, opps: [] } },
            { event_id: 'b', sport: 'calcio', updated_at: new Date().toISOString(), payload: { minute: 30, score_home: 0, score_away: 0, opps: [] } },
        ] as never);
        renderPage();
        const tab = await screen.findByRole('tab', { name: /Opportunità modello/ });
        expect(tab).toHaveTextContent('Opportunità modello (0)');
        expect(tab.title).toBe('0 opportunità sopra le soglie del servizio, su 2 partite analizzate dal modello in questo momento');
    });
});

describe('attività del servizio leggibile', () => {
    it('event_id risolto in NOME partita, mercato e motivo in italiano', async () => {
        renderPage();
        const feed = await screen.findByTestId('safe-activity');
        const rows = within(feed).getAllByTestId('activity-row');
        // risk_block: nome partita (risolto dall'event_id del trade) + mercato in chiaro
        expect(rows[0]).toHaveTextContent('Bucheon FC 1995 – Jeju Utd');
        expect(rows[0]).toHaveTextContent('Risultato Esatto');
        expect(rows[0]).toHaveTextContent('cap di liability per evento raggiunto');
        expect(rows[0]).not.toHaveTextContent('CORRECT_SCORE');
        expect(rows[0]).not.toHaveTextContent('per_event_liability_cap');
        // skip: motivo tecnico del servizio tradotto
        expect(rows[1]).toHaveTextContent('spread troppo largo fra back e lay');
        expect(rows[1]).not.toHaveTextContent('spread_anomalo');
        // exit_wait: nessun event_id nel payload, il nome arriva dal trade_id
        expect(rows[2]).toHaveTextContent('Bucheon FC 1995 – Jeju Utd');
        expect(rows[2]).toHaveTextContent('il lato bancato ha segnato');
    });

    it('il filtro per evento funziona anche sulle righe che portavano solo l id', async () => {
        const user = userEvent.setup();
        const altro = { ...TRADE, id: 48, event_id: '36038848', event_name: 'Daegu Fc – Yongin FC' };
        mState.mockResolvedValue({
            control: CONTROL as never, trades: [TRADE, altro] as never, aggregates: AGG as never,
            activity: [
                ...ACTIVITY,
                { id: 2, ts: secondsAgo(240), kind: 'place', payload: { event_id: '36038848', side: 'lay', size: 2, price: 30 } },
            ] as never,
            params_effective: CONTROL.stats.params_effective as never,
            operating_day: romeDay(),
        });
        renderPage();
        await screen.findByTestId('safe-activity');
        const filter = screen.getByTestId('activity-filter');
        // il filtro elenca i NOMI, non gli event_id: possibile solo dopo la risoluzione
        await user.click(within(filter).getByRole('button', { name: 'Daegu Fc – Yongin FC' }));
        const rows = screen.getAllByTestId('activity-row');
        expect(rows).toHaveLength(1);
        expect(rows[0]).toHaveTextContent('Daegu Fc – Yongin FC');
    });
});

describe('tabella trade: mercato in chiaro', () => {
    it('CORRECT_SCORE si legge "Risultato Esatto"', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByTestId('bot-status');
        await user.click(await screen.findByRole('tab', { name: /^Trade/ }));
        await apriPartite(user);
        const cell = await screen.findByTestId('safe-market');
        expect(cell).toHaveTextContent('Risultato Esatto');
        // l'id tecnico resta nel tooltip, per il confronto con Betfair
        expect(cell.title).toMatch(/CORRECT_SCORE/);
    });
});
