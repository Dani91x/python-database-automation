// ============================================================================
// Pagina Safe Strategy — CERT. 13/09: PAPER e LIVE sono due cose separate,
// i dati assenti non sono zeri, e si deve vedere PERCHÉ base/punta non entrano.
//
// Regressioni coperte qui (tutte nate da schermate montate sui dati veri):
//   1. la modalità mostrata era quella LOCALE del browser a bot fermo, mentre
//      il DB ne conosceva un'altra — e il servizio RIFIUTA gli ordini di una
//      modalità diversa dalla sua (`modalita_non_corrispondente`);
//   2. «Avvia» in LIVE non chiedeva NESSUNA conferma: `safe_stop()` non riporta
//      il control a 'paper', quindi bastava riaprire l'app il giorno dopo e
//      premere Avvia per mandare il bot a piazzare con soldi veri;
//   3. i KPI «P&L oggi»/«P&L totale» non dicevano a quale modalità si riferivano;
//   4. ogni grandezza aveva un `?? 0` a monte: un dato mai arrivato diventava
//      «0,00 €», cioè un'affermazione precisa e falsa;
//   5. le partite senza riferimento 1X2 pre-kickoff (BASE e PUNTA NON
//      VALUTABILI, non "condizioni false") erano visibili solo card per card
//      dentro il sub-tab Monitor;
//   6. nel feed attività non si vedeva la modalità della riga e non c'era modo
//      di isolare le righe «NON ENTRATO».
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

const scan = vi.hoisted(() => ({ status: null as unknown }));
vi.mock('@/lib/safeStrategyScan', async (orig) => {
    const actual = await orig<typeof import('@/lib/safeStrategyScan')>();
    return { ...actual, fetchScanStatus: vi.fn(async () => scan.status) };
});

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
import { fetchSafeState, fetchOpportunities, activateSafe } from '@/lib/safeBot';

const mState = vi.mocked(fetchSafeState);
const mOpps = vi.mocked(fetchOpportunities);
const mActivate = vi.mocked(activateSafe);

const secondsAgo = (s: number) => new Date(Date.now() - s * 1000).toISOString();

function control(over: Record<string, unknown> = {}) {
    return {
        id: 1, status: 'running', mode: 'paper',
        params: { stake: { laySize: 2, backSize: 2 }, commission_pct: 5, variants: ['base', 'punta'] },
        stats: { params_effective: { commission_pct: 5, opps_stake: 5, min_stake: 2 } },
        error: null, started_at: null, stopped_at: null,
        heartbeat_at: new Date().toISOString(),
        ...over,
    };
}

const AGG = {
    realized_today: 1.9, realized_total: 10.98, open_liability: 300, open_count: 5,
    day_liability: 472, legs_today: 6, events_today: 5, won_today: 1, lost_today: 0,
    operating_day: romeDay(),
};

/** partita in corso SENZA riferimento pre-KO: BASE e PUNTA non valutabili */
function monitor(eventId: string, preMatchMissing: boolean, pressureIndex: number | null = 0.2) {
    return {
        eventId,
        updatedAt: secondsAgo(2),
        payload: { event_name: `Partita ${eventId}`, competition: 'Serie A', open_date: '2026-09-13T18:00:00Z', media: null },
        ctx: { home: 'Casa', away: 'Ospite', minute: 58, scoreHome: 1, scoreAway: 0, inplay: true, preMatch: preMatchMissing ? null : { fav: 1.6 }, pressureIndex },
        evaluations: [],
        preMatchMissing,
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    provider.football = [];
    provider.tennis = [];
    provider.signals = [];
    provider.scanStatus = null;
    scan.status = { id: 'scanner', payload: { calcio_inplay: 4, tennis_inplay: 0, source: 'stream' }, updated_at: secondsAgo(2) };
    mState.mockResolvedValue({
        control: control() as never, trades: [] as never, aggregates: AGG as never,
        activity: [] as never, params_effective: control().stats.params_effective as never,
        operating_day: romeDay(),
    });
    mOpps.mockResolvedValue([]);
});

function renderPage() {
    return render(
        <HelmetProvider><MemoryRouter><SafeStrategy /></MemoryRouter></HelmetProvider>,
    );
}

// ---------------------------------------------------------------------------
describe('CERT. 13/09 — la modalità mostrata è quella del SERVIZIO', () => {
    it('i KPI del P&L dichiarano la modalità (paper e live non si sommano)', async () => {
        renderPage();
        const oggi = await screen.findByTestId('safe-kpi-pnl-today');
        expect(oggi).toHaveTextContent('PAPER');
        const totale = screen.getByTestId('safe-kpi-pnl-total');
        expect(totale).toHaveTextContent('PAPER');
        // il tooltip dice anche che è al netto della commissione DEL TRADE
        expect(oggi.title).toMatch(/commissione/i);
        expect(totale.title).toMatch(/contabilità separate/i);
    });

    it('control in LIVE: l’etichetta dei KPI dice LIVE anche a bot FERMO', async () => {
        mState.mockResolvedValue({
            control: control({ mode: 'live', status: 'stopped' }) as never,
            trades: [] as never, aggregates: AGG as never, activity: [] as never,
            params_effective: control().stats.params_effective as never, operating_day: romeDay(),
        });
        renderPage();
        // prima qui si leggeva PAPER (stato locale del browser) mentre il
        // servizio era armato in LIVE: la bugia più cara della pagina.
        expect(await screen.findByTestId('safe-kpi-pnl-today')).toHaveTextContent('LIVE');
    });

    it('selezione diversa dal servizio: si leggono ENTRAMBE, esplicitamente', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: control({ mode: 'live', status: 'stopped' }) as never,
            trades: [] as never, aggregates: AGG as never, activity: [] as never,
            params_effective: control().stats.params_effective as never, operating_day: romeDay(),
        });
        renderPage();
        await screen.findByTestId('safe-kpi-pnl-today');
        expect(screen.queryByTestId('safe-mode-mismatch')).toBeNull();
        // l'utente sceglie PAPER, ma il servizio resta armato in LIVE
        await user.click(within(screen.getByTestId('mode-toggle')).getByRole('button', { name: 'PAPER' }));
        const nota = await screen.findByTestId('safe-mode-mismatch');
        expect(within(nota).getByTestId('safe-mode-selected')).toHaveTextContent('PAPER');
        expect(within(nota).getByTestId('safe-mode-service')).toHaveTextContent('LIVE');
    });
});

// ---------------------------------------------------------------------------
describe('CERT. 13/09 — «Avvia» in LIVE senza conferma NON parte', () => {
    it('control lasciato in live + Avvia: dialog di conferma, nessuna attivazione', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: control({ mode: 'live', status: 'stopped' }) as never,
            trades: [] as never, aggregates: AGG as never, activity: [] as never,
            params_effective: control().stats.params_effective as never, operating_day: romeDay(),
        });
        renderPage();
        const start = await screen.findByTestId('bot-start');
        await user.click(start);
        // il bot NON è stato armato: prima `activateSafe('live')` partiva subito
        expect(mActivate).not.toHaveBeenCalled();
        expect(await screen.findByTestId('live-confirm')).toBeInTheDocument();
    });

    it('in PAPER l’avvio resta immediato (nessuna frizione dove non serve)', async () => {
        const user = userEvent.setup();
        mState.mockResolvedValue({
            control: control({ mode: 'paper', status: 'stopped' }) as never,
            trades: [] as never, aggregates: AGG as never, activity: [] as never,
            params_effective: control().stats.params_effective as never, operating_day: romeDay(),
        });
        renderPage();
        await user.click(await screen.findByTestId('bot-start'));
        expect(mActivate).toHaveBeenCalledWith('paper');
    });
});

// ---------------------------------------------------------------------------
describe('CERT. 13/09 — un dato assente è «—», mai 0,00 €', () => {
    it('senza aggregati e senza stats: P&L e liability sono «—»', async () => {
        mState.mockResolvedValue({
            control: control({ stats: {} }) as never, trades: [] as never,
            aggregates: null as never, activity: [] as never,
            params_effective: null as never, operating_day: romeDay(),
        });
        renderPage();
        const oggi = await screen.findByTestId('safe-kpi-pnl-today');
        expect(oggi).toHaveTextContent('—');
        expect(oggi).not.toHaveTextContent('0,00');
        expect(screen.getByTestId('safe-kpi-pnl-total')).toHaveTextContent('—');
        expect(screen.getByTestId('safe-kpi-liability')).toHaveTextContent('—');
        // e il pannello Rischio non inventa un impegnato di giornata
        expect(within(screen.getByTestId('risk-panel')).getByTestId('risk-liability')).toHaveTextContent('—');
    });
});

// ---------------------------------------------------------------------------
describe('CERT. 13/09 — perché BASE e PUNTA non scattano', () => {
    it('contatore delle partite senza riferimento pre-KO, visibile dalla tab di default', async () => {
        provider.football = [monitor('1', true), monitor('2', true), monitor('3', false)];
        renderPage();
        const nota = await screen.findByTestId('safe-pre-ko-missing');
        expect(nota).toHaveTextContent('2 partite senza riferimento pre-KO');
        expect(nota).toHaveTextContent('BASE e PUNTA non valutabili');
        // è nella riga KPI, non sepolto nel sub-tab Monitor
        expect(within(screen.getByTestId('safe-kpi-monitored')).getByTestId('safe-pre-ko-missing')).toBeTruthy();
    });

    it('tutte le partite col riferimento pre-KO: nessun contatore (niente rumore)', async () => {
        provider.football = [monitor('1', false)];
        renderPage();
        await screen.findByTestId('safe-kpi-monitored');
        expect(screen.queryByTestId('safe-pre-ko-missing')).toBeNull();
    });
});

// ---------------------------------------------------------------------------
describe('CERT. 13/09 — feed attività: modalità e filtro per tipo', () => {
    const ACTIVITY = [
        { id: 5, ts: secondsAgo(30), kind: 'skip', payload: { event_id: '1', mode: 'paper', reason: 'pre_ko_assente' } },
        { id: 4, ts: secondsAgo(60), kind: 'skip', payload: { event_id: '2', mode: 'paper', reason: 'spread_anomalo' } },
        { id: 3, ts: secondsAgo(90), kind: 'place', payload: { event_id: '1', mode: 'live', size: 5, price: 1.3 } },
        { id: 2, ts: secondsAgo(120), kind: 'exit', payload: { event_id: '1', mode: 'paper' } },
    ];

    beforeEach(() => {
        mState.mockResolvedValue({
            control: control() as never, trades: [] as never, aggregates: AGG as never,
            activity: ACTIVITY as never,
            params_effective: control().stats.params_effective as never, operating_day: romeDay(),
        });
    });

    it('ogni riga porta il chip PAPER/LIVE scritto dal servizio', async () => {
        renderPage();
        const feed = await screen.findByTestId('safe-activity');
        const chips = within(feed).getAllByTestId('activity-mode');
        expect(chips).toHaveLength(4);
        expect(chips.map((c) => c.textContent)).toContain('LIVE');
        expect(chips.map((c) => c.textContent)).toContain('PAPER');
        // la riga LIVE, con servizio in PAPER, è attenuata e marcata
        const rows = within(feed).getAllByTestId('activity-row');
        const live = rows.find((r) => r.getAttribute('data-mode') === 'live');
        expect(live).toHaveAttribute('data-other-mode', '1');
    });

    it('chip «solo NON ENTRATO»: isola gli scarti col motivo (pre-KO compreso)', async () => {
        const user = userEvent.setup();
        renderPage();
        const feed = await screen.findByTestId('safe-activity');
        expect(within(feed).getAllByTestId('activity-row')).toHaveLength(4);
        await user.click(within(feed).getByTestId('activity-kind-quick'));
        const rows = within(screen.getByTestId('safe-activity')).getAllByTestId('activity-row');
        expect(rows).toHaveLength(2);
        expect(rows.every((r) => r.getAttribute('data-kind') === 'skip')).toBe(true);
        // ed è LÌ che si legge perché BASE/PUNTA non sono valutabili
        expect(screen.getByTestId('safe-activity')).toHaveTextContent(/riferimento quote pre-partita non disponibile/);
    });

    it('filtro per TIPO: si può isolare un singolo kind', async () => {
        const user = userEvent.setup();
        renderPage();
        const feed = await screen.findByTestId('safe-activity');
        const opzioni = within(feed).getAllByTestId('activity-kind-option');
        const place = opzioni.find((b) => b.getAttribute('data-kind') === 'place');
        expect(place).toBeTruthy();
        await user.click(place as HTMLElement);
        expect(within(screen.getByTestId('safe-activity')).getAllByTestId('activity-row')).toHaveLength(1);
    });
});

// ---------------------------------------------------------------------------
// CERT. 13/09 — accessibilità dei filtri delle opportunità.
// «Confidenza minima» e «Lato» erano gli unici filtri della pagina senza
// `aria-pressed`: uno screen reader leggeva quattro bottoni identici senza
// dire quale fosse attivo, mentre tipo/evento/sport lo dicevano già.
// ---------------------------------------------------------------------------
describe('CERT. 13/09 — i filtri dicono quale è attivo', () => {
    it('«Confidenza minima» e «Lato» hanno aria-pressed come gli altri', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByTestId('safe-kpi-pnl-today');
        await user.click(screen.getByRole('tab', { name: /Opportunità modello/ }));
        // stato iniziale: "tutte" e "tutti" premuti
        expect(screen.getByRole('button', { name: 'tutte', pressed: true })).toBeTruthy();
        const lay = screen.getByRole('button', { name: 'lay' });
        expect(lay).toHaveAttribute('aria-pressed', 'false');
        await user.click(lay);
        expect(screen.getByRole('button', { name: 'lay' })).toHaveAttribute('aria-pressed', 'true');
        const c70 = screen.getByRole('button', { name: '70%' });
        expect(c70).toHaveAttribute('aria-pressed', 'false');
        await user.click(c70);
        expect(screen.getByRole('button', { name: '70%' })).toHaveAttribute('aria-pressed', 'true');
    });
});

// ---------------------------------------------------------------------------
// CERT. 14/09 — «implementata» e «attiva» non sono la stessa cosa.
// La condizione di controllo del gioco esiste nel codice ma nasce SPENTA:
// finche' lo e', BASE e PUNTA aprono SENZA una condizione che il manuale
// dichiara vincolante. Il trader deve vederlo dalla tab di default, non
// dedurlo. Una scheda di segnale non puo' vantare un filtro che non ha girato.
describe('CERT. 14/09 — il controllo del gioco dichiara di NON essere applicato', () => {
    it('condizione spenta: lo dice, e dice su quante partite il dato ci sarebbe', async () => {
        provider.football = [monitor('1', false, 0.3), monitor('2', false, null), monitor('3', false, null)];
        renderPage();
        const nota = await screen.findByTestId('safe-controllo-non-applicato');
        expect(nota).toHaveTextContent('controllo del gioco: NON applicato');
        expect(nota).toHaveTextContent('dato presente su 1 partite su 3');
        // sta nella riga KPI, accanto al contatore pre-KO
        expect(within(screen.getByTestId('safe-kpi-monitored')).getByTestId('safe-controllo-non-applicato')).toBeTruthy();
    });

    it('condizione accesa e dato completo: nessuna nota (niente rumore)', async () => {
        mState.mockResolvedValue({
            control: control({ params: { base: { requireControl: true } } }) as never,
            trades: [] as never, aggregates: AGG as never, activity: [] as never,
            params_effective: null as never, operating_day: romeDay(),
        });
        provider.football = [monitor('1', false, 0.3)];
        renderPage();
        await screen.findByTestId('safe-kpi-monitored');
        expect(screen.queryByTestId('safe-controllo-non-applicato')).toBeNull();
        expect(screen.queryByTestId('safe-controllo-dato-assente')).toBeNull();
    });

    it('condizione accesa ma dato assente: lo dichiara, il calcio non si puo valutare la', async () => {
        mState.mockResolvedValue({
            control: control({ params: { punta: { requireControl: true } } }) as never,
            trades: [] as never, aggregates: AGG as never, activity: [] as never,
            params_effective: null as never, operating_day: romeDay(),
        });
        provider.football = [monitor('1', false, 0.3), monitor('2', false, null)];
        renderPage();
        const nota = await screen.findByTestId('safe-controllo-dato-assente');
        expect(nota).toHaveTextContent('il dato manca su 1 partita su 2');
        expect(nota).toHaveTextContent('calcio non valutabile');
    });

    it('nessuna partita in corso: nessuna nota (non si allarma sul vuoto)', async () => {
        provider.football = [];
        renderPage();
        await screen.findByTestId('safe-kpi-monitored');
        expect(screen.queryByTestId('safe-controllo-non-applicato')).toBeNull();
    });
});
