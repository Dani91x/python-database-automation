// ============================================================================
// useChiusuraAlMs.parita.test.tsx - 30/09 (P11): «chiudi ora» SEMPRE NETTO.
//
// La stessa gamba ha due strade per il «chiudi ora»:
//   * ramo SCANNER: `useControlRoom.chiusuraViva` -> `chiusura.bloccabile`
//     (NETTO dal 26/09, F-12, aliquota della riga via `aliquotaDi`);
//   * ramo AL MS: `useChiusuraAlMs` -> `chiusuraAlPrezzo` sul ladder al ms.
// Fino al 30/09 il ramo al ms era LORDO: in utile due cifre diverse per la
// stessa gamba (Mike back 9 @ 1,85, lay 1,70: scanner 0,75, ms 0,79).
// Qui si usa il modello di vista VERO (useControlRoom con i finti delle
// letture, chiavi identiche al vero) e lo si confronta al centesimo col ramo
// al ms allo STESSO prezzo.
//
// FALSIFICAZIONE (30/09): togliendo `netAfterCommission` in `chiusuraAlPrezzo`
// i test 1-2 tornano 0,79 (rossi); togliendo la riga `aliquota:` in
// `chiusuraViva` il test 2 da' 0,75 invece di 0,77 (rosso).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { ScanRow, CalcioScanPayload } from '@/lib/safeStrategyScan';
import type { MikeTrade } from '@/lib/mike';
import { romeDay } from '@/lib/dailyHistory';

// ------------------------------------------------------------------- finti
// Copia dei finti di `useControlRoom.test.tsx`: stesse chiavi e tipi del vero.
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

import { fetchScanRows } from '@/lib/safeStrategyScan';
import { fetchMikeState } from '@/lib/mike';
import { useControlRoom } from '@/components/controlroom/useControlRoom';
import { useChiusuraAlMs } from '@/components/controlroom/useChiusuraAlMs';

const OGGI = romeDay(new Date());
const PIAZZATO = `${OGGI}T12:00:00.000Z`;
const MIKE_VUOTO = {
    control: null, events: [], trades: [], activity: [], aggregates: null,
    requests: [], day_start: null, day_by: null,
};

function tradeMike(over: Partial<MikeTrade> = {}): MikeTrade {
    return {
        id: 800, event_id: 'E2', market_id: '1.2', selection_id: 2, side: 'back',
        mode: 'live', price: 2, size: 9, liability: 0, status: 'open', pnl: null,
        placed_at: PIAZZATO, settled_at: null, origin: 'auto',
        ...over,
    } as MikeTrade;
}

function payloadOU(marketId: string, selectionId: number, back: number, lay: number): CalcioScanPayload {
    return {
        event_name: 'Finto v Finto', home: 'Finto', away: 'Finto', competition: null,
        open_date: null, inplay: true, mo_market_id: null, mo_status: null, odds: null,
        minute: 10, score_home: 0, score_away: 0, red_home: 0, red_away: 0, pre_ko: null,
        cs: null, ht: null,
        ou: [{
            market_id: marketId, status: 'OPEN',
            selections: [{ selection_id: selectionId, name: 'Under 3.5', back, lay, back_size: 50, lay_size: 40 }],
        }],
    };
}

function scanRow(eventId: string, payload: CalcioScanPayload): ScanRow {
    return { event_id: eventId, sport: 'calcio', payload, updated_at: PIAZZATO };
}

/** Sorgente del ladder al ms finta: stessa forma di `ResiduiB17.schede.test.tsx`. */
function sorgenteFinta() {
    const cbs = new Map<string, (row: unknown) => void>();
    const src = {
        fetch: async () => null,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            cbs.set(mid, cb);
            return () => { cbs.delete(mid); };
        },
        fonte: () => 'canale' as const,
    };
    const spingi = (mid: string, sid: number, back: number, lay: number) => act(() => {
        const ms = Date.now();
        cbs.get(mid)?.({
            event_id: 'E2', market_id: mid, market_type: 'OVER_UNDER_35', market_name: 'OU 3.5',
            status: 'OPEN', updated_at: new Date(ms).toISOString(),
            ladder: { updated_ms: ms, selections: [
                { selection_id: sid, name: 'Under 3.5', ltp: back, tv: 0, back: [[back, 50]], lay: [[lay, 40]],
                    trd: [], wom: { back_pct: 50, lay_pct: 50 } },
            ] },
        });
    });
    return { sorgente: () => src as never, spingi };
}

async function chiusuraScanner(trade: MikeTrade, back: number, lay: number) {
    vi.mocked(fetchScanRows).mockResolvedValue([scanRow('E2', payloadOU('1.2', 2, back, lay))]);
    vi.mocked(fetchMikeState).mockResolvedValue({ ...MIKE_VUOTO, trades: [trade] } as never);
    const { result } = renderHook(() => useControlRoom());
    await waitFor(() => expect(result.current.caricamento).toBe(false));
    const p = result.current.posizioni.find((x) => x.bot === 'mike' && x.id === trade.id);
    expect(p?.chiusura?.alMs).toBeDefined();
    return p!.chiusura!;
}

beforeEach(() => {
    vi.clearAllMocks();
});

describe('P11: stessa gamba in utile, ramo al ms = ramo scanner al centesimo', () => {
    it('Mike back 9 @ 1,85, lay 1,70: scanner 0,75 netto = ms 0,75 (prima ms 0,79 lordo)', async () => {
        const ch = await chiusuraScanner(tradeMike({ id: 811, price: 1.85 }), 1.68, 1.70);
        expect(ch.bloccabile).toBe(0.75);
        const f = sorgenteFinta();
        const { result } = renderHook(() => useChiusuraAlMs(ch, f.sorgente));
        f.spingi('1.2', 2, 1.68, 1.70);
        expect(result.current?.alMs).toBe(true);
        expect(result.current?.prezzo).toBe(ch.prezzo);
        expect(result.current?.bloccabile).toBe(ch.bloccabile);
        expect(result.current?.aliquota).toBe(0.05);
    });

    it('aliquota della riga 2 % (meta.commission): entrambi 0,77, non 0,75 del 5 %', async () => {
        const ch = await chiusuraScanner(
            tradeMike({ id: 812, price: 1.85, meta: { commission: 0.02 } } as Partial<MikeTrade>), 1.68, 1.70);
        // lordo 0,79 x 0,98 = 0,7742 -> 0,77
        expect(ch.bloccabile).toBe(0.77);
        expect(ch.alMs?.aliquota).toBe(0.02);
        const f = sorgenteFinta();
        const { result } = renderHook(() => useChiusuraAlMs(ch, f.sorgente));
        f.spingi('1.2', 2, 1.68, 1.70);
        expect(result.current?.bloccabile).toBe(0.77);
        expect(result.current?.aliquotaDiRipiego).toBe(false);
    });

    it('ripiego sullo scanner (il canale non porta il mercato): stessa cifra netta', async () => {
        const ch = await chiusuraScanner(tradeMike({ id: 813, price: 1.85 }), 1.68, 1.70);
        const f = sorgenteFinta();
        const { result } = renderHook(() => useChiusuraAlMs(ch, f.sorgente));
        expect(result.current?.fonte).toBe('scanner');
        expect(result.current?.bloccabile).toBe(ch.bloccabile);
    });

    it('in perdita nessuna commissione: lay 2,10 -> ms = scanner', async () => {
        const ch = await chiusuraScanner(tradeMike({ id: 814, price: 1.85 }), 2.08, 2.10);
        const f = sorgenteFinta();
        const { result } = renderHook(() => useChiusuraAlMs(ch, f.sorgente));
        f.spingi('1.2', 2, 2.08, 2.10);
        expect(ch.bloccabile).not.toBeNull();
        expect(ch.bloccabile!).toBeLessThan(0);
        expect(result.current?.bloccabile).toBe(ch.bloccabile);
    });
});
