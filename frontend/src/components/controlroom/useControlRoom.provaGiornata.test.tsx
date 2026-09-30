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
import { fetchLiveAccount } from '@/lib/liveOrders';
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

// ============================================================================
// P7 (30/09) - la composizione LIVE per bot dal CONTO (`pnl_reale_oggi.per_fonte`).
// Una posizione LIVE di Mike piazzata IERI e regolata OGGI: `get_mike_state` non
// la porta (solo righe piazzate oggi o aperte), il conto si'. Deve stare sotto
// Mike, non in «Altro sul conto Betfair». Finto del conto con le chiavi della
// colonna JSONB `betfair_live_account.pnl_reale_oggi`.
// ============================================================================
function contoConMike(netto: number) {
    const zero = { netto: 0, ordini: 0 };
    return {
        pnl_reale_oggi: {
            day: OGGI, netto, ordini: 1,
            per_fonte: {
                omega: zero, safe_calcio: zero, safe_tennis: zero, mike: { netto, ordini: 1 },
                bot_tennis: zero, manuale_app: zero, manuale_sito: zero, altri_bot: zero, scalper: zero,
            },
            bet_ids: ['3900001'], senza_commissione: 0, sospetti_sito: 0,
            letto_at: `${OGGI}T12:41:00+00:00`,
        },
    };
}

describe('P8bis - la plancia dei bot: prova di oggi e arretrati a parte', () => {
    it('Safe base in prova: +7,60 di partite vecchie regolate oggi NON e\' la cifra di oggi; arretrati a parte', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: SAFE_ARRETRATI } as never);
        vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO as never);
        const v = await vista();
        const safe = v.bots.find((b) => b.bot === 'safe')!;
        const base = safe.pnlOggiPerStrategia!.base;
        expect(base.paper).toBeNull();
        expect(base.arretratiPaper!.map((g) => [g.giorno, g.origine, g.pnl, g.operazioni])).toEqual([[PRIMA, 'apertura', 7.6, 4]]);
        // le altre strategie non ereditano gli arretrati della base
        expect(safe.pnlOggiPerStrategia!.esatto.arretratiPaper).toEqual([]);
    });

    it('Mike: gli arretrati della plancia vengono dalla chiave del backend', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue(SAFE_VUOTO as never);
        vi.mocked(fetchMikeState).mockResolvedValue({ ...MIKE_VUOTO, arretrati_prova: arretratiMike('piene') } as never);
        const v = await vista();
        const mike = v.bots.find((b) => b.bot === 'mike')!;
        expect(mike.pnlOggiPaper).toBeNull();
        expect(mike.arretratiPaper!.map((g) => g.pnl)).toEqual([-18.29]);
    });
});

describe('R_G - prestazioni: la prova non si ricalcola a ogni secondo', () => {
    it('nowMs avanza nello stesso giorno: provaGiornata e\' LO STESSO oggetto; al cambio di giorno cambia', async () => {
        vi.useFakeTimers({ toFake: ['Date'], shouldAdvanceTime: true });
        try {
            vi.setSystemTime(new Date(`${OGGI}T10:00:00+00:00`));
            vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: SAFE_ARRETRATI } as never);
            vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO as never);
            const { result } = renderHook(() => useControlRoom());
            await waitFor(() => expect(result.current.caricamento).toBe(false));
            await waitFor(() => expect(result.current.provaGiornata).toBeTruthy());
            const primo = result.current.provaGiornata;
            const apertoPrimo = result.current.apertoAdesso;
            const t0 = result.current.nowMs;
            await waitFor(() => expect(result.current.nowMs).toBeGreaterThan(t0), { timeout: 3000 });
            expect(result.current.provaGiornata).toBe(primo);
            // W_G: anche l'«aperto adesso» non si ricalcola a ogni secondo (dipende dai dati)
            expect(result.current.apertoAdesso).toBeTruthy();
            expect(result.current.apertoAdesso).toBe(apertoPrimo);
            // il giorno dopo: la prova si ricalcola (gli arretrati di ieri non sono piu' «di oggi»)
            vi.setSystemTime(new Date(Date.parse(`${OGGI}T10:00:00+00:00`) + 24 * 3600 * 1000));
            await waitFor(() => expect(result.current.provaGiornata).not.toBe(primo), { timeout: 3000 });
        } finally {
            vi.useRealTimers();
        }
    });
});

describe('P7 - la voce di ogni bot dal conto Betfair', () => {
    it('Mike: posizione di ieri regolata oggi (riga non letta) -> sotto Mike dal CONTO, «Altro» vuoto', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue(SAFE_VUOTO as never);
        vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO as never);
        vi.mocked(fetchLiveAccount).mockResolvedValue(contoConMike(2.0) as never);
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await waitFor(() => expect(result.current.contoLettoAt).toBe(`${OGGI}T12:41:00+00:00`));
        const righe = result.current.composizioneOggi.righe;
        const mike = righe.find((r) => r.chiave === 'mike')!;
        expect(mike.valore).toBe(2);
        expect((mike as { fonte?: string }).fonte).toBe('conto');
        expect(righe.find((r) => r.chiave === 'altro')!.valore).toBeNull();
        // stessi soldi: il realizzato live della barra non cambia
        expect(result.current.soldiGiornata.realizzato).toBe(2);
    });
});

// ============================================================================
// W_B2 (30/09 sera, M15) - la plancia: la cifra LIVE «oggi» di ogni bot e la
// sua FONTE. Con il conto letto: `pnl_reale_oggi.per_fonte[bot].netto` (fonte
// CONTO, con l'eta' della lettura); letto e vuoto = 0 «nessuna regolata oggi».
// Safe per strategia: il conto separa solo per sport -> calcio dalle righe (BOT).
// ============================================================================
describe('W_B2 - plancia: fonte della cifra LIVE di oggi', () => {
    it('conto letto: Mike 2,00 dal CONTO; Omega letto e vuoto = 0 «nessuna regolata»; Safe calcio dalle righe', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue(SAFE_VUOTO as never);
        vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO as never);
        vi.mocked(fetchLiveAccount).mockResolvedValue(contoConMike(2.0) as never);
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await waitFor(() => expect(result.current.contoLettoAt).toBe(`${OGGI}T12:41:00+00:00`));
        const mike = result.current.bots.find((b) => b.bot === 'mike')!;
        expect(mike.pnlOggi).toBe(2);
        expect(mike.fonteOggiLive).toMatchObject({ fonte: 'conto', vuoto: false });
        expect(typeof mike.fonteOggiLive!.etaS).toBe('number');
        const omega = result.current.bots.find((b) => b.bot === 'omega');
        if (omega) {
            expect(omega.pnlOggi).toBe(0);
            expect(omega.fonteOggiLive).toMatchObject({ fonte: 'conto', vuoto: true });
        }
        const safe = result.current.bots.find((b) => b.bot === 'safe');
        if (safe) {
            expect(safe.pnlOggiPerStrategia!.base.fonteLive).toMatchObject({ fonte: 'bot' });
            expect(safe.pnlOggiPerStrategia!.base.fonteLive!.nota).toMatch(/solo per sport/);
            expect(safe.pnlOggiPerStrategia!.tennis.fonteLive).toMatchObject({ fonte: 'conto', vuoto: true });
            // la prova non passa mai dal conto
            expect(safe.pnlOggiPerStrategia!.base.paper).toBeNull();
        }
    });

    it('senza conto: la cifra dalle righe del bot (fonte BOT); letto e vuoto = 0, mai inventato dal conto', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue(SAFE_VUOTO as never);
        vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO as never);
        vi.mocked(fetchLiveAccount).mockResolvedValue(null as never);
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await waitFor(() => expect(result.current.bots.find((b) => b.bot === 'mike')?.fonteOggiLive).toBeTruthy());
        const mike = result.current.bots.find((b) => b.bot === 'mike')!;
        expect(mike.pnlOggi).toBe(0);
        expect(mike.fonteOggiLive).toMatchObject({ fonte: 'bot', vuoto: true });
    });
});

