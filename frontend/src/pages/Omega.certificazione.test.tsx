// ============================================================================
// Omega.certificazione.test.tsx — certificazione 11/09/2026 dei punti della
// checklist che nessun altro test di pagina copriva:
//
//   §7  la pagina funziona SENZA la migrazione v5 (payload della RPC v4:
//       niente locked_pnl_open, activity_more, goal_snapshot, live_now)
//   §4  equity della GIORNATA = cumulato dei regolati delle partite PIAZZATE
//       oggi (una posizione di ieri regolata oggi non entra nella giornata)
//   §4  i KPI e la barra NON contano mai righe 'error' né riserve mai piazzate
//   §2  il filtro dell'attività e il toggle "mostra tutte / solo oggi"
//
// Data-layer mockato (nessuna rete). Gli helper puri di omegaMatches sono
// quelli VERI: è il loro raggruppamento che decide cosa entra nella giornata.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));

vi.mock('@/components/omega/MissionPanel', () => ({
    default: () => <div data-testid="mission-panel-stub" />,
}));
vi.mock('@/components/omega/ManualPanel', () => ({
    default: () => <div data-testid="manual-panel-stub" />,
}));
vi.mock('@/lib/useScanLiveFeed', () => ({
    useScanLiveFeedRows: () => ({}),
    useScanLiveFeed: () => ({}),
    liveScoreLabel: () => null,
}));
vi.mock('@/lib/safeStrategyScan', async (orig) => ({
    ...(await orig<typeof import('@/lib/safeStrategyScan')>()),
    fetchScanStatus: vi.fn(async () => null),
}));

// `buildEquitySeries` NON è stubbata: è la funzione sotto esame (§4).
vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig<typeof import('@/lib/omega')>()),
    fetchOmegaState: vi.fn(),
    fetchOmegaTrades: vi.fn(),
    subscribeOmega: vi.fn(() => () => {}),
    activateOmega: vi.fn(),
    stopOmega: vi.fn(),
    updateOmegaParams: vi.fn(),
    requestManual: vi.fn(),
}));

import Omega from './Omega';
import { fetchOmegaState, fetchOmegaTrades, buildEquitySeries } from '@/lib/omega';
import { groupTradesByMatch, filterMatchesForDay, romeDayOf } from '@/lib/omegaMatches';
import { romeDay } from '@/lib/dailyHistory';

const mState = vi.mocked(fetchOmegaState);
const mTrades = vi.mocked(fetchOmegaTrades);

const OGGI = romeDay();
const iso = (h: number, m = 0) => {
    // un istante di OGGI nella giornata operativa di Roma (mezzogiorno ± ore:
    // così il giorno di Roma non cambia qualunque sia il fuso del runner)
    const d = new Date(`${OGGI}T12:00:00Z`);
    d.setUTCHours(12 + h, m, 0, 0);
    return d.toISOString();
};
const IERI_ISO = (() => {
    const d = new Date(`${OGGI}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString();
})();

const CONTROL = {
    id: 1, status: 'running', mode: 'paper', daily_goal: 250, params: { commission_pct: 5 },
    stats: { bot_running: true, events_total: 10, target_leg: 5, target_match: 10 },
    error: null, started_at: null, stopped_at: null, heartbeat_at: iso(0),
    updated_at: iso(0),
};

function trade(over: Record<string, unknown>) {
    return {
        id: 1, event_id: 'e1', event_name: 'Roma vs Lazio', market_id: '1.1', selection_id: 4,
        runner_name: '3 - 2', side: 'lay', mode: 'paper', origin: 'auto', phase: 'ft_cs',
        price: 110, size: 5, liability: 545, target: 5, minute_at_entry: 55,
        score_at_entry: '0-0', kickoff: null, status: 'open', pnl: 0, bet_id: 'b1',
        placed_at: iso(0), settled_at: null, closes_trade_id: null, meta: {},
        ...over,
    } as never;
}

function renderPage() {
    return render(
        <HelmetProvider>
            <MemoryRouter>
                <Omega />
            </MemoryRouter>
        </HelmetProvider>,
    );
}

async function gotoAutoTab() {
    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: /Automatico/ }));
    return user;
}

beforeEach(() => {
    vi.clearAllMocks();
    mTrades.mockResolvedValue([] as never);
});

// ===========================================================================
// §7 — senza la migrazione v5
// ===========================================================================
describe('§7 — la pagina funziona con la RPC v4 (migrazione v5 NON applicata)', () => {
    /** payload v4: mancano locked_pnl_open(_today), reconciling_liability,
     *  live_now, activity_more, activity_day, goal_snapshot. */
    const AGG_V4 = {
        realized_profit: 120, realized_today: 40, open_liability: 545,
        matches_traded: 5, matches_traded_today: 2, matches_open: 1,
        matches_won: 3, matches_lost: 2,
        legs_today: 2, events_today: 1, won_today: 1, lost_today: 1,
    };

    function stateV4(over: Record<string, unknown> = {}) {
        return {
            control: CONTROL as never,
            aggregates: AGG_V4 as never,
            activity: [{ id: 1, ts: iso(-1), kind: 'place', payload: { event_id: 'e1' } }],
            // la v4 non li manda: il client li normalizza (lib/omega.fetchOmegaState)
            activity_more: 0,
            activity_day: null,
            goal_today: null,
            goal_snapshot: false,
            ...over,
        } as never;
    }

    it('nessun crash: guscio, barra di giornata e KPI presenti', async () => {
        mState.mockResolvedValue(stateV4());
        renderPage();
        expect(await screen.findByTestId('omega-daily-mission')).toBeInTheDocument();
        expect(screen.getByTestId('omega-kpi-pnl')).toBeInTheDocument();
        expect(screen.getByTestId('omega-kpi-liability')).toBeInTheDocument();
    });

    it('il KPI «P&L bloccato» C’È comunque, STIMATO dalle righe caricate', async () => {
        // Certificazione con i dati reali: prima la riga KPI spariva del tutto
        // (`lockedOpen === null`) e i due numeri che dicono quanto si è già
        // perso e quanto è a esito ignoto non erano da nessuna parte.
        mState.mockResolvedValue(stateV4());
        mTrades.mockResolvedValue([
            // posizione COPERTA per intero: −22,50 € già bloccati
            trade({
                id: 1, status: 'hedged', liability: 545,
                meta: { locked_pnl: -22.5, hedged_size: 5, residual_size: 0, hedge: { fraction: 1, complete: true, hedged_size: 5, residual_size: 0 } },
            }),
            trade({ id: 2, event_id: 'e1', status: 'won', pnl: 0, side: 'back', closes_trade_id: 1, settled_at: iso(1) }),
            // ordine REALE a esito ignoto: 300 € in verifica su Betfair
            trade({
                id: 3, event_id: 'e3', status: 'pending', liability: 300, bet_id: null,
                meta: { reconciling: true, reconciling_since: iso(0) },
            }),
        ] as never);
        renderPage();
        const locked = await screen.findByTestId('omega-kpi-locked');
        expect(locked).toHaveTextContent('−22,50 €');
        expect(locked).toHaveTextContent(/stimato dal client/i);
        expect(locked).toHaveTextContent(/omega_models_v5\.sql/);
        const rec = screen.getByTestId('omega-kpi-reconciling');
        expect(rec).toHaveTextContent('300,00 €');
        expect(rec).toHaveTextContent(/stimato dal client/i);
    });

    it('con la v5 vince la RPC e la nota della STIMA scompare', async () => {
        mState.mockResolvedValue(stateV4({
            aggregates: { ...AGG_V4, locked_pnl_open: -40, locked_pnl_open_today: -40, reconciling_liability: 0 } as never,
        }));
        // le righe caricate direbbero −22,50: la RPC è la fonte, non il client
        mTrades.mockResolvedValue([
            trade({ id: 1, status: 'hedged', meta: { locked_pnl: -22.5, hedged_size: 5, residual_size: 0 } }),
            trade({ id: 2, event_id: 'e1', status: 'won', pnl: 0, side: 'back', closes_trade_id: 1, settled_at: iso(1) }),
        ] as never);
        renderPage();
        const locked = await screen.findByTestId('omega-kpi-locked');
        expect(locked).toHaveTextContent('−40,00 €');
        expect(locked).not.toHaveTextContent(/stimato dal client/i);
        expect(locked).toHaveTextContent(/di oggi −40,00 €/);
    });

    it('nessuna posizione coperta: la stima è 0 e lo dichiara (non un dato dal DB)', async () => {
        mState.mockResolvedValue(stateV4());
        mTrades.mockResolvedValue([trade({ id: 1, status: 'open' })] as never);
        renderPage();
        const locked = await screen.findByTestId('omega-kpi-locked');
        expect(locked).toHaveTextContent('+0,00 €');
        expect(locked).toHaveTextContent(/stimato dal client/i);
    });

    it('obiettivo NON storicizzato: la barra lo DICHIARA (H-10) e usa quello corrente', async () => {
        mState.mockResolvedValue(stateV4());
        renderPage();
        const bar = await screen.findByTestId('omega-daily-mission');
        expect(bar).toHaveTextContent(/obiettivo non ancora storicizzato/i);
        // ripiego sul daily_goal del control: 250 €
        expect(within(bar).getByTestId('omega-remaining')).toHaveTextContent('210,00 €');
    });

    it('attività: senza `activity_day` il filtro di giornata è del client e lo dice', async () => {
        mState.mockResolvedValue(stateV4({
            activity: [
                { id: 1, ts: iso(-1), kind: 'place', payload: { event_id: 'e1' } },
                // riga di IERI: la v4 la manderebbe, il client la scarta
                { id: 2, ts: IERI_ISO, kind: 'settle', payload: { event_id: 'e0' } },
            ],
        }));
        renderPage();
        await gotoAutoTab();
        const card = await screen.findByTestId('omega-activity');
        expect(card).toHaveTextContent(/migrazione v5 non applicata/i);
        expect(within(card).getAllByTestId('omega-activity-row')).toHaveLength(1);
    });

    it('niente «carica altre» quando la RPC non sa quante righe restano', async () => {
        mState.mockResolvedValue(stateV4());
        renderPage();
        await gotoAutoTab();
        await screen.findByTestId('omega-activity');
        expect(screen.queryByTestId('omega-activity-more')).toBeNull();
    });
});

// ===========================================================================
// header: «IN CORSA» su un servizio fermo (certificazione con i dati reali)
// ===========================================================================
describe('header — un bot senza battito non è «IN CORSA»', () => {
    const AGG_MIN = {
        realized_profit: 0, realized_today: 0, open_liability: 0, matches_traded: 0,
        matches_open: 0, matches_won: 0, matches_lost: 0,
        legs_today: 0, events_today: 0, won_today: 0, lost_today: 0, live_now: 0,
        locked_pnl_open: 0, locked_pnl_open_today: 0, reconciling_liability: 0,
    };
    function withBeat(heartbeat_at: string | null) {
        return {
            control: { ...CONTROL, status: 'running', heartbeat_at } as never,
            aggregates: AGG_MIN as never, activity: [],
            activity_more: 0, activity_day: OGGI, goal_today: 250, goal_snapshot: true,
        } as never;
    }

    it('battito fresco: badge normale', async () => {
        mState.mockResolvedValue(withBeat(new Date().toISOString()));
        renderPage();
        const badge = await screen.findByTestId('bot-status');
        expect(badge).toHaveTextContent('IN CORSA');
        expect(badge).not.toHaveAttribute('data-stale');
    });

    it('servizio fermo da ore con `status=running`: il badge lo DICE', async () => {
        // lo scenario trovato sui dati reali: tre servizi fermi da 5 h, tre
        // badge che dicevano "IN CORSA" perché nessuno aveva premuto Ferma
        mState.mockResolvedValue(withBeat(new Date(Date.now() - 5 * 3600_000).toISOString()));
        renderPage();
        const badge = await screen.findByTestId('bot-status');
        expect(badge).toHaveTextContent('IN CORSA · SENZA BATTITO');
        expect(badge).toHaveAttribute('data-stale', 'true');
        expect(badge.getAttribute('title')).toMatch(/riavvia l/i);
    });

    it('battito mai scritto: anomalia dichiarata', async () => {
        mState.mockResolvedValue(withBeat(null));
        renderPage();
        expect(await screen.findByTestId('bot-status')).toHaveTextContent('SENZA BATTITO');
    });
});

// ===========================================================================
// §4 — i numeri della giornata
// ===========================================================================
describe('§4 — KPI e barra SOLO dagli aggregati (nessun conteggio client)', () => {
    const AGG = {
        realized_profit: 10, realized_today: 10, open_liability: 545,
        matches_traded: 1, matches_open: 1, matches_won: 1, matches_lost: 0,
        legs_today: 1, events_today: 1, won_today: 1, lost_today: 0, live_now: 1,
        locked_pnl_open: 0, locked_pnl_open_today: 0, reconciling_liability: 0,
    };

    it('righe `error` e riserve mai piazzate non spostano i contatori', async () => {
        // la tabella riceve 4 righe (1 buona + 1 error + 1 riserva + 1 chiusura)
        // ma la giornata resta quella della RPC: 1 operazione, 1V, 0P
        mState.mockResolvedValue({
            control: CONTROL as never, aggregates: AGG as never, activity: [],
            activity_more: 0, activity_day: OGGI, goal_today: 250, goal_snapshot: true,
        } as never);
        mTrades.mockResolvedValue([
            trade({ id: 1, status: 'won', pnl: 10, settled_at: iso(1) }),
            trade({ id: 2, event_id: 'e2', status: 'error', pnl: 0, bet_id: null, meta: { leg_failed: true, error_at: iso(1) } }),
            trade({ id: 3, event_id: 'e3', status: 'pending', pnl: 0, bet_id: null, meta: {} }),
            trade({ id: 4, event_id: 'e1', status: 'won', pnl: -2, side: 'back', closes_trade_id: 1, settled_at: iso(1) }),
        ] as never);
        renderPage();
        const bar = await screen.findByTestId('omega-daily-mission');
        expect(within(bar).getByTestId('omega-today-legs')).toHaveTextContent('1');
        const kpi = screen.getByTestId('omega-kpi-legs');
        expect(kpi).toHaveTextContent('1V');
        expect(kpi).toHaveTextContent('0P');
        // il riepilogo della tabella usa gli STESSI numeri della RPC
        await gotoAutoTab();
        expect(await screen.findByTestId('omega-matches-summary'))
            .toHaveTextContent('1 operazioni oggi · 1V 0P');
    });

    it('«resta» e «CENTRATO» dall’obiettivo storicizzato, non da quello corrente', async () => {
        mState.mockResolvedValue({
            control: { ...CONTROL, daily_goal: 1000 } as never,
            aggregates: { ...AGG, realized_today: 60 } as never,
            activity: [], activity_more: 0, activity_day: OGGI,
            // lo SNAPSHOT di oggi dice 50 €: già centrato
            goal_today: 50, goal_snapshot: true,
        } as never);
        renderPage();
        const bar = await screen.findByTestId('omega-daily-mission');
        expect(within(bar).getByTestId('omega-goal-hit')).toHaveTextContent('CENTRATO');
    });

    it('liability «in verifica su Betfair» dichiarata nel sottotitolo del KPI', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never,
            aggregates: { ...AGG, open_liability: 545, reconciling_liability: 545 } as never,
            activity: [], activity_more: 0, activity_day: OGGI, goal_today: 250, goal_snapshot: true,
        } as never);
        renderPage();
        const kpi = await screen.findByTestId('omega-kpi-liability');
        expect(kpi).toHaveTextContent('545,00 €');
        expect(kpi).toHaveTextContent(/di cui 545,00 € in verifica su Betfair/);
    });
});

// ===========================================================================
// §4 — equity della giornata (funzione pura + vista)
// ===========================================================================
describe('§4 — equity della giornata: cumulato dei regolati per giorno di PIAZZAMENTO', () => {
    it('buildEquitySeries cumula in ordine di regolazione', () => {
        const serie = buildEquitySeries([
            trade({ id: 1, status: 'won', pnl: 10, settled_at: iso(2) }),
            trade({ id: 2, status: 'lost', pnl: -4, settled_at: iso(1) }),
            trade({ id: 3, status: 'open', pnl: 0, settled_at: null }),       // vivo: fuori
            trade({ id: 4, status: 'error', pnl: 0, settled_at: null }),      // error: fuori
            trade({ id: 5, status: 'void', pnl: 0, settled_at: iso(3) }),
        ] as never);
        expect(serie.map((p) => p.v)).toEqual([-4, 6, 6]);
    });

    it('la vista di GIORNATA esclude una partita di IERI già regolata', () => {
        // il filtro della vista è per giorno di PIAZZAMENTO (le partite vive di
        // ieri restano, quelle già chiuse no): è la regola della barra e dei KPI
        const righe = [
            trade({ id: 1, status: 'won', pnl: 10, placed_at: iso(0), settled_at: iso(1) }),
            trade({ id: 2, event_id: 'ieri', status: 'won', pnl: 99, placed_at: IERI_ISO, settled_at: IERI_ISO }),
        ] as never;
        const gruppi = filterMatchesForDay(groupTradesByMatch(righe), OGGI);
        expect(gruppi.map((g) => g.event_id)).toEqual(['e1']);
        const idsOggi = new Set(gruppi.map((g) => g.event_id));
        const serie = buildEquitySeries((righe as never[]).filter((t: never) => idsOggi.has((t as { event_id: string }).event_id)) as never);
        expect(serie.map((p) => p.v)).toEqual([10]);
        // controprova: la partita di ieri è di un ALTRO giorno operativo
        expect(romeDayOf(IERI_ISO)).not.toBe(OGGI);
    });

    it('una posizione di ieri ancora VIVA resta nella vista (il rischio non ha giorno)', () => {
        const righe = [
            trade({ id: 9, event_id: 'viva', status: 'open', placed_at: IERI_ISO }),
        ] as never;
        const gruppi = filterMatchesForDay(groupTradesByMatch(righe), OGGI);
        expect(gruppi.map((g) => g.event_id)).toEqual(['viva']);
    });

    it('«mostra tutte» allarga la vista, «solo oggi» la richiude', async () => {
        mState.mockResolvedValue({
            control: CONTROL as never,
            aggregates: {
                realized_profit: 109, realized_today: 10, open_liability: 0,
                matches_traded: 2, matches_open: 0, matches_won: 2, matches_lost: 0,
                legs_today: 1, events_today: 1, won_today: 1, lost_today: 0, live_now: 0,
                locked_pnl_open: 0, locked_pnl_open_today: 0, reconciling_liability: 0,
            } as never,
            activity: [], activity_more: 0, activity_day: OGGI, goal_today: 250, goal_snapshot: true,
        } as never);
        mTrades.mockResolvedValue([
            trade({ id: 1, status: 'won', pnl: 10, placed_at: iso(0), settled_at: iso(1) }),
            trade({ id: 2, event_id: 'ieri', event_name: 'Vecchia vs Partita', status: 'won', pnl: 99, placed_at: IERI_ISO, settled_at: IERI_ISO }),
        ] as never);
        renderPage();
        const user = await gotoAutoTab();
        const card = await screen.findByTestId('omega-matches-card');
        expect(card).toHaveTextContent('Partite di oggi');
        expect(within(card).queryByText(/Vecchia vs Partita/)).toBeNull();

        await user.click(within(card).getByTestId('omega-matches-toggle'));
        await waitFor(() => {
            expect(screen.getByTestId('omega-matches-card')).toHaveTextContent('Tutte le partite');
        });
        expect(await within(screen.getByTestId('omega-matches-card')).findByText(/Vecchia vs Partita/))
            .toBeInTheDocument();

        // i NUMERI di giornata non cambiano: sono quelli della RPC
        expect(within(screen.getByTestId('omega-daily-mission')).getByTestId('omega-today-legs'))
            .toHaveTextContent('1');
    });
});
