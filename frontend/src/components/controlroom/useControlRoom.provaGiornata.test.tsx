// ============================================================================
// useControlRoom.provaGiornata.test.tsx - P8 (30/09) sul modello di vista VERO:
// la corsia PROVA «oggi» e' per partite di OGGI; le partite di giorni
// precedenti regolate oggi sono ARRETRATI, a parte e mai sommati a oggi.
//
// Finti: gli stessi dei test del hook (`useControlRoom.test.tsx`), chiavi e
// tipi del vero. Gli arretrati di Mike arrivano da `get_mike_state` nella
// chiave `arretrati_prova` (forma di migrations/mike_state_arretrati_prova_
// 2026-09-30.sql: bot, mode, id, event_id, event_name, ko_at, placed_at
// dell'apertura, settled_at, status, pnl, closes_trade_id). Qui
// `fetchMikeState` e' finto e la porta gia'; nel codice vero serve che
// `lib/mike.ts::fetchMikeState` la inoltri (vedi referto G_P8).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { romeDay } from '@/lib/dailyHistory';

vi.mock('@/lib/safeStrategyScan', async (orig) => ({
    ...(await orig() as object),
    fetchScanRows: vi.fn(async () => []),
    fetchScanStatus: vi.fn(async () => null),
    subscribeScanRows: vi.fn(() => () => { /* nessun evento */ }),
    subscribeScanStatus: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omega', async (orig) => ({
    ...(await orig() as object),
    fetchOmegaState: vi.fn(async () => ({ control: null, aggregates: null, activity: [] })),
    fetchOmegaTrades: vi.fn(async () => []),
    fetchOmegaEvents: vi.fn(async () => []),
    updateOmegaParams: vi.fn(async () => ({})),
    requestManual: vi.fn(async () => 7001),
    fetchManualRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/safeBot', async (orig) => ({
    ...(await orig() as object),
    fetchSafeState: vi.fn(async () => ({ control: null, trades: [], aggregates: null })),
    fetchRunnerState: vi.fn(async () => ({ ts: null, mode: null, ageS: null, up: false })),
    requestSafe: vi.fn(async () => 7002),
    fetchSafeRequests: vi.fn(async () => []),
    cashOutEvento: vi.fn(async () => undefined),
    riprendiEventoSafe: vi.fn(async () => undefined),
    approvaPropostaOpportunita: vi.fn(async () => undefined),
    fetchEsitiApprovazioni: vi.fn(async () => []),
    fetchRichiestaSafe: vi.fn(async () => null),
}));
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    fetchMikeState: vi.fn(async () => ({ control: null, events: [], trades: [], activity: [], aggregates: null, requests: [], day_start: null, day_by: null })),
    requestMike: vi.fn(async () => 7003),
    fetchMikeRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/controlRoomProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposte: vi.fn(async () => []),
    subscribeProposte: vi.fn(() => () => { /* nessun evento */ }),
    approvaProposta: vi.fn(async () => undefined),
    ignoraProposta: vi.fn(async () => undefined),
}));
vi.mock('@/lib/omegaProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposteOmega: vi.fn(async () => []),
    subscribeProposteOmega: vi.fn(() => () => { /* nessun evento */ }),
    approvaPropostaOmega: vi.fn(async () => undefined),
    ignoraPropostaOmega: vi.fn(async () => undefined),
}));
vi.mock('@/lib/omegaMissions', async (orig) => ({
    ...(await orig() as object),
    fetchMissions: vi.fn(async () => ({ missions: [] })),
}));
vi.mock('@/lib/live', async (orig) => ({
    ...(await orig() as object),
    fetchLiveFollows: vi.fn(async () => []),
}));
vi.mock('@/lib/dailyHistory', async (orig) => ({
    ...(await orig() as object),
    fetchSafeDaily: vi.fn(async () => []),
}));
vi.mock('@/lib/tennis', async (orig) => ({
    ...(await orig() as object),
    fetchTennisFollows: vi.fn(async () => []),
    fetchTennisBotServices: vi.fn(async () => []),
    fetchTennisBotDaily: vi.fn(async () => []),
    fetchTennisBotOrdersToday: vi.fn(async () => []),
}));
vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn(() => ({
        getStatus: () => 'off' as const,
        onStatus: () => () => { /* nessun cambio */ },
        subscribe: () => () => { /* nessuna spinta */ },
    })),
    svegliaBot: vi.fn(),
}));
vi.mock('@/lib/liveOrders', async (orig) => ({
    ...(await orig() as object),
    fetchLiveAccount: vi.fn(async () => null),
    subscribeLiveAccount: vi.fn(() => () => { /* nessuna spinta */ }),
}));
vi.mock('@/lib/scalperControlRoom', async (orig) => ({
    ...(await orig() as object),
    fetchScalperControlRoom: vi.fn(async () => ({ sessioni: [], ordini: [], lettoAt: null })),
    stopScalperSessione: vi.fn(async () => ({})),
}));
vi.mock('@/lib/scalper', async (orig) => ({
    ...(await orig() as object),
    fetchScalperState: vi.fn(async () => ({ control: null, activity: [] })),
}));

import { fetchSafeState, type SafeTrade } from '@/lib/safeBot';
import { fetchMikeState } from '@/lib/mike';
import { useControlRoom } from '@/components/controlroom/useControlRoom';

const SAFE_VUOTO = { control: null, trades: [], aggregates: null };
const MIKE_VUOTO = {
    control: null, events: [], trades: [], activity: [], aggregates: null,
    requests: [], day_start: null, day_by: null,
};

beforeEach(() => { vi.clearAllMocks(); });

const OGGI = romeDay(new Date());
const PRIMA = romeDay(new Date(Date.now() - 4 * 24 * 3600 * 1000));
const REGOLATO = `${OGGI}T12:41:11.195408+00:00`;

function tradeSafe(over: Partial<SafeTrade>): SafeTrade {
    return {
        id: 363, event_id: '35925583', event_name: 'Iceland – Estonia', sport: 'calcio',
        strategy: 'base', market_id: '1.1', market_type: 'MATCH_ODDS', selection_id: 1,
        selection_name: 'Iceland', side: 'lay', mode: 'paper', price: 1.3, size: 2,
        liability: 0.6, commission: 0.05, minute_at_entry: 70, score_at_entry: '0-2',
        status: 'won', pnl: 1.9, bet_id: null, placed_at: `${PRIMA}T17:25:20.390038+00:00`,
        settled_at: REGOLATO, origin: 'auto', closes_trade_id: null, signal_key: null, meta: {},
        ...over,
    } as SafeTrade;
}

/** le 4 righe di Safe di una partita di 4 giorni fa regolate oggi (+1,90 l'una) */
const SAFE_ARRETRATI = [363, 359, 361, 362].map((id) => tradeSafe({ id, event_id: `E${id}` }));

/** la chiave del backend con le 5 righe di Mike (2 partite, -18,29) */
function arretratiMike(righe: 'piene' | 'vuote') {
    const r = (id: number, event_id: string, status: string, pnl: number) => ({
        bot: 'mike', mode: 'paper', id, event_id, event_name: `Partita ${event_id}`,
        ko_at: `${PRIMA}T15:00:00+00:00`, placed_at: `${PRIMA}T15:18:51.839091+00:00`,
        settled_at: `${OGGI}T12:41:20.434352+00:00`, status, pnl, closes_trade_id: null,
    });
    return {
        day: OGGI,
        righe: righe === 'vuote' ? [] : [
            r(5077, '36109477', 'lost', -5.0), r(5078, '36109477', 'lost', -2.5),
            r(5080, '36109477', 'lost', -6.4), r(5081, '36109477', 'lost', -6.67),
            r(5082, '36093027', 'won', 2.28),
        ],
    };
}

async function vista() {
    const { result } = renderHook(() => useControlRoom());
    await waitFor(() => expect(result.current.caricamento).toBe(false));
    await waitFor(() => expect(result.current.provaGiornata).toBeTruthy());
    return result.current;
}

describe('P8 - la prova di oggi non contiene partite di giorni precedenti', () => {
    it('Safe +7,60 di 4 giorni fa regolato oggi: tessera PROVA «oggi» 0,00, arretrati a parte', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: SAFE_ARRETRATI } as never);
        vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO as never);
        const v = await vista();
        expect(v.soldiGiornata.perSportPaper?.calcio).toEqual({ n: 0, pnl: 0, won: 0, lost: 0 });
        const safe = v.provaGiornata!.voci.find((x) => x.chiave === 'safe_calcio')!;
        expect(safe.oggi!.pnl).toBe(0);
        expect(safe.arretrati!.map((g) => [g.giorno, g.origine, g.pnl, g.partite])).toEqual([[PRIMA, 'apertura', 7.6, 4]]);
        // chiave del backend assente (migrazione non applicata): Mike «non letti»
        expect(v.provaGiornata!.arretratiNonLetti.calcio).toEqual(['Mike']);
    });

    it('con la chiave del backend: Mike -18,29 negli arretrati, mai in oggi, mai fuso con Safe', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: SAFE_ARRETRATI } as never);
        vi.mocked(fetchMikeState).mockResolvedValue({ ...MIKE_VUOTO, arretrati_prova: arretratiMike('piene') } as never);
        const v = await vista();
        const p = v.provaGiornata!;
        expect(p.oggiPerSport.calcio!.pnl).toBe(0);
        expect(p.arretratiPerSport.calcio.map((g) => [g.origine, g.pnl])).toEqual([['apertura', 7.6], ['fischio', -18.29]]);
        expect(p.arretratiNonLetti.calcio).toEqual([]);
    });

    it('chiave con righe: [] = nessun arretrato di Mike (letto e vuoto)', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue(SAFE_VUOTO as never);
        vi.mocked(fetchMikeState).mockResolvedValue({ ...MIKE_VUOTO, arretrati_prova: arretratiMike('vuote') } as never);
        const v = await vista();
        expect(v.provaGiornata!.voci.find((x) => x.chiave === 'mike')!.arretrati).toEqual([]);
        expect(v.provaGiornata!.arretratiNonLetti.calcio).toEqual([]);
    });

    it('una partita di OGGI regolata oggi resta in «oggi» (tessera PROVA)', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({
            ...SAFE_VUOTO,
            trades: [...SAFE_ARRETRATI, tradeSafe({ id: 500, event_id: 'E500', pnl: 0.95, placed_at: `${OGGI}T10:00:00+00:00` })],
        } as never);
        vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO as never);
        const v = await vista();
        expect(v.soldiGiornata.perSportPaper?.calcio).toEqual({ n: 1, pnl: 0.95, won: 1, lost: 0 });
    });
});
