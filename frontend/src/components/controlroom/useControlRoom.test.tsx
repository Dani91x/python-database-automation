// ============================================================================
// useControlRoom.test.tsx — due promesse del modello di vista, misurate.
//
//  1. UNA FONTE CHE CADE SI CHIAMA PER NOME. Il messaggio «fonti non raggiunte»
//     serve a sapere CHE COSA manca: una lettura senza nome nell'elenco ci
//     finiva dentro come «undefined» (`[...][14]` e' `undefined`, e
//     `undefined !== null` passa il filtro). Le quattro letture dei bot tennis
//     erano esattamente in quel caso.
//  2. LE POSIZIONI CHIUSE DEI QUATTRO BOT TENNIS SONO POSIZIONI COME LE ALTRE
//     (ordine dell'utente, 17/09: «indipendenti come gli altri»). Entrano in
//     `chiuse` con lo stesso contratto delle righe di Omega/Safe/Mike, con il
//     P&L NETTO e con la modalita' della riga — paper e live mai sommati.
//
// FALSIFICAZIONE (provata a mano, 17/09):
//   · togliendo una voce da `FONTI_RICARICA` il primo gruppo diventa rosso
//     («fonte #18» al posto del nome, e il nome non compare piu');
//   · togliendo il ciclo degli ordini tennis da `chiuse` il secondo gruppo
//     diventa rosso (nessuna posizione chiusa del tennis);
//   · sommando il paper al live, o dimenticando di sottrarre la commissione,
//     l'assenza di somma e il netto diventano rossi.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { TennisBotOrderRow } from '@/lib/tennis';
import type { ScanRow, CalcioScanPayload } from '@/lib/safeStrategyScan';
import { romeDay } from '@/lib/dailyHistory';

// ------------------------------------------------------------------- finti
// Ogni finto ha le IDENTICHE chiavi e gli identici tipi del vero: un finto
// piu' povero del vero certifica una pagina che dal vivo esplode (15/09).

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
    // B16 (24/09) - la coda manuale di Omega (`omega_request`/`get_omega_manual_requests`)
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
    // 24/09 - l'esito a video: stessa forma di `esitoApprovazione` (lib/safeBot.ts)
    fetchEsitiApprovazioni: vi.fn(async (ids: number[]) => ids.map((id) => ({
        id, stato: 'rifiutata', testo: 'rifiutato: prezzo cambiato fra il clic e l’esecuzione - visto 1.3, all’esecuzione 1.4',
    }))),
}));

vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    fetchMikeState: vi.fn(async () => ({ control: null, events: [], trades: [], activity: [], aggregates: null, requests: [], day_start: null, day_by: null })),
    // B16 (24/09) - la coda di Mike (`mike_request`/`mike_requests`)
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

// 18/09 (raccordo, R4) — `betfair_live_account`: NON entra nel poll dei 30s
// (niente `Promise.allSettled` qui), ma `useControlRoom.ts` ora fa UNA
// lettura one-shot al montaggio + una sottoscrizione Realtime, come
// `SaldoBetfairCard.tsx`. Finto con le stesse chiavi del vero.
vi.mock('@/lib/liveOrders', async (orig) => ({
    ...(await orig() as object),
    fetchLiveAccount: vi.fn(async () => null),
    subscribeLiveAccount: vi.fn(() => () => { /* nessuna spinta */ }),
}));

// 24/09 - lo scalper calcio: UNA lettura nel giro (`get_scalper_control_room`).
// Le funzioni pure restano le vere; il finto ha le chiavi della RPC.
vi.mock('@/lib/scalperControlRoom', async (orig) => ({
    ...(await orig() as object),
    fetchScalperControlRoom: vi.fn(async () => ({ sessioni: [], ordini: [], lettoAt: null })),
    stopScalperSessione: vi.fn(async () => ({})),
}));
// lo stato di UNA sessione (`get_scalper_state`), riletto per l'esito del Chiudi
vi.mock('@/lib/scalper', async (orig) => ({
    ...(await orig() as object),
    fetchScalperState: vi.fn(async () => ({ control: null, activity: [] })),
}));

import { fetchScanRows, fetchScanStatus, subscribeScanRows, subscribeScanStatus } from '@/lib/safeStrategyScan';
import { fetchOmegaState, fetchOmegaTrades, fetchOmegaEvents, updateOmegaParams } from '@/lib/omega';
import { fetchSafeState, fetchRunnerState, approvaPropostaOpportunita, type SafeTrade } from '@/lib/safeBot';
import { fetchMikeState } from '@/lib/mike';
import { fetchProposte } from '@/lib/controlRoomProposte';
import { fetchMissions } from '@/lib/omegaMissions';
import { fetchLiveFollows } from '@/lib/live';
import { fetchSafeDaily } from '@/lib/dailyHistory';
import {
    fetchTennisFollows, fetchTennisBotServices, fetchTennisBotDaily,
    fetchTennisBotOrdersToday,
} from '@/lib/tennis';
import { fetchLiveAccount, subscribeLiveAccount } from '@/lib/liveOrders';
import { fetchScalperControlRoom } from '@/lib/scalperControlRoom';
import { useControlRoom, FONTI_RICARICA } from '@/components/controlroom/useControlRoom';

/** tutte le letture del giro, nell'ORDINE in cui il hook le lancia */
function letture() {
    return [
        fetchScanRows, fetchScanStatus,
        fetchOmegaState, fetchOmegaTrades,
        fetchSafeState, fetchMikeState, fetchRunnerState, fetchProposte,
        fetchSafeDaily, fetchSafeDaily,
        fetchOmegaEvents, fetchMissions, fetchTennisFollows, fetchLiveFollows,
        fetchTennisBotServices, fetchTennisBotDaily, fetchTennisBotDaily,
        fetchTennisBotOrdersToday,
        fetchScalperControlRoom,
    ];
}

/** Gli stati VUOTI dei servizi. Le RPC non restituiscono mai `null`: danno
 *  l'oggetto con `control` assente. Il finto deve dire la stessa cosa. */
const OMEGA_VUOTO = { control: null, aggregates: null, activity: [] };
const SAFE_VUOTO = { control: null, trades: [], aggregates: null };
const RUNNER_VUOTO = { ts: null, mode: null, ageS: null, up: false };
const MIKE_VUOTO = {
    control: null, events: [], trades: [], activity: [], aggregates: null,
    requests: [], day_start: null, day_by: null,
};

function reset() {
    vi.mocked(fetchScanRows).mockResolvedValue([]);
    vi.mocked(fetchScanStatus).mockResolvedValue(null);
    vi.mocked(subscribeScanRows).mockReturnValue(() => { /* niente */ });
    vi.mocked(subscribeScanStatus).mockReturnValue(() => { /* niente */ });
    vi.mocked(fetchOmegaState).mockResolvedValue(OMEGA_VUOTO);
    vi.mocked(fetchOmegaTrades).mockResolvedValue([]);
    vi.mocked(fetchOmegaEvents).mockResolvedValue([]);
    vi.mocked(fetchSafeState).mockResolvedValue(SAFE_VUOTO);
    vi.mocked(fetchRunnerState).mockResolvedValue(RUNNER_VUOTO);
    vi.mocked(fetchMikeState).mockResolvedValue(MIKE_VUOTO);
    vi.mocked(fetchProposte).mockResolvedValue([]);
    vi.mocked(fetchMissions).mockResolvedValue({ missions: [] } as never);
    vi.mocked(fetchLiveFollows).mockResolvedValue([]);
    vi.mocked(fetchSafeDaily).mockResolvedValue([]);
    vi.mocked(fetchTennisFollows).mockResolvedValue([]);
    vi.mocked(fetchTennisBotServices).mockResolvedValue([]);
    vi.mocked(fetchTennisBotDaily).mockResolvedValue([]);
    vi.mocked(fetchTennisBotOrdersToday).mockResolvedValue([]);
    vi.mocked(updateOmegaParams).mockResolvedValue({} as never);
    vi.mocked(fetchLiveAccount).mockResolvedValue(null);
    vi.mocked(subscribeLiveAccount).mockReturnValue(() => { /* niente */ });
    vi.mocked(fetchScalperControlRoom).mockResolvedValue({ sessioni: [], ordini: [], lettoAt: null });
}

beforeEach(() => {
    vi.clearAllMocks();
    reset();
});

// ============================================================ 1) LE FONTI

describe('«fonti non raggiunte»: ogni lettura si chiama per nome', () => {
    it('i nomi sono tanti quante le letture, e nessuno e vuoto', () => {
        expect(FONTI_RICARICA).toHaveLength(letture().length);
        for (const n of FONTI_RICARICA) expect(n.trim()).not.toBe('');
    });

    it('le quattro letture dei bot tennis hanno un nome PARLANTE', () => {
        // 24/09 - dopo di loro c'e' la lettura dello scalper calcio
        expect(FONTI_RICARICA.slice(-5, -1)).toEqual([
            'servizi bot tennis',
            'giornata bot tennis live',
            'giornata bot tennis paper',
            'ordini bot tennis di oggi',
        ]);
        expect(FONTI_RICARICA[FONTI_RICARICA.length - 1]).toBe('scalper calcio');
    });

    it('cade la lettura degli ORDINI dei bot tennis: compare col suo nome', async () => {
        vi.mocked(fetchTennisBotOrdersToday).mockRejectedValue(new Error('RPC assente'));
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.errore).toBe('fonti non raggiunte: ordini bot tennis di oggi');
    });

    it('cade la lettura dei SERVIZI dei bot tennis: compare col suo nome', async () => {
        vi.mocked(fetchTennisBotServices).mockRejectedValue(new Error('migrazione non applicata'));
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.errore).toBe('fonti non raggiunte: servizi bot tennis');
    });

    it('cadono TUTTE: l elenco le nomina tutte, nell ordine, senza «undefined»', async () => {
        for (const f of letture()) {
            vi.mocked(f as unknown as ReturnType<typeof vi.fn>)
                .mockRejectedValue(new Error('giu'));
        }
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const msg = result.current.errore ?? '';
        expect(msg).toBe(`fonti non raggiunte: ${FONTI_RICARICA.join(', ')}`);
        // i due modi in cui una fonte senza nome si presenterebbe
        expect(msg).not.toContain('undefined');
        expect(msg).not.toContain('fonte #');
    });

    it('niente cade: nessun messaggio inventato', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.errore).toBeNull();
    });
});

// ================================================ 2) LE CHIUSE DEL TENNIS

const OGGI = romeDay(new Date());
const PIAZZATO = `${OGGI}T12:00:00.000Z`;
const REGOLATO = `${OGGI}T12:30:00.000Z`;

/** Un ordine di `tennis_live_orders` come lo manda `get_tennis_bot_orders_today`. */
function ordine(over: Partial<TennisBotOrderRow> = {}): TennisBotOrderRow {
    return {
        id: 41, source: 'tennis_scalper', bet_id: '3300', client_order_ref: 'ts-41',
        request_id: null, mode: 'live', event_id: 'T1', market_id: '1.77',
        selection_id: 5001, handicap: 0, side: 'back', order_type: 'LIMIT',
        price: 1.9, size: 3, size_matched: 3, size_remaining: 0, size_cancelled: 0,
        size_lapsed: 0, size_voided: 0, average_price_matched: 1.9,
        status: 'EXECUTION_COMPLETE', persistence: 'LAPSE',
        placed_at: PIAZZATO, matched_at: PIAZZATO, updated_at: REGOLATO,
        pnl: 1.2, commission: 0.06, settled_at: REGOLATO,
        ...over,
    };
}

async function conOrdini(righe: TennisBotOrderRow[]) {
    vi.mocked(fetchTennisBotOrdersToday).mockResolvedValue(righe);
    const { result } = renderHook(() => useControlRoom());
    await waitFor(() => expect(result.current.caricamento).toBe(false));
    return result;
}

describe('posizioni chiuse: i quattro bot tennis sono indipendenti come gli altri', () => {
    it('un ordine REGOLATO diventa una posizione chiusa, col suo bot e la sua giornata', async () => {
        const result = await conOrdini([ordine()]);
        const c = result.current.chiuse;
        expect(c).toHaveLength(1);
        expect(c[0].bot).toBe('tennis_scalper');
        expect(c[0].sport).toBe('tennis');
        expect(c[0].eventId).toBe('T1');
        expect(c[0].giorno).toBe(OGGI);
        expect(c[0].esito).toBe('vinta');
    });

    it('il P&L e NETTO di commissione: 1,20 lordi meno 0,06 fanno 1,14', async () => {
        const result = await conOrdini([ordine()]);
        expect(result.current.chiuse[0].pnlGlobale).toBe(1.14);
        expect(result.current.chiuse[0].righe[0].pnl).toBe(1.14);
    });

    it('la MODALITA e quella della riga, e paper e live restano due posizioni', async () => {
        const result = await conOrdini([
            ordine({ id: 41, mode: 'live', pnl: 1.2, commission: 0.06 }),
            ordine({ id: 42, mode: 'paper', pnl: 4, commission: 0.2 }),
        ]);
        const c = result.current.chiuse;
        expect(c).toHaveLength(2);
        const modi = c.map((x) => x.modo).sort();
        expect(modi).toEqual(['live', 'paper']);
        // MAI la somma: 1,14 e 3,80 restano due numeri
        expect(c.map((x) => x.pnlGlobale).sort((a, b) => a - b)).toEqual([1.14, 3.8]);
    });

    it('una perdita e una perdita: l esito non si addolcisce', async () => {
        const result = await conOrdini([ordine({ pnl: -2, commission: 0 })]);
        expect(result.current.chiuse[0].pnlGlobale).toBe(-2);
        expect(result.current.chiuse[0].esito).toBe('persa');
    });

    it('i quattro bot arrivano tutti, ognuno con la sua riga', async () => {
        const result = await conOrdini([
            ordine({ id: 1, source: 'tennis_scalper' }),
            ordine({ id: 2, source: 'tennis_pro' }),
            ordine({ id: 3, source: 'tennis_flb' }),
            ordine({ id: 4, source: 'tennis_swing' }),
        ]);
        expect(result.current.chiuse.map((x) => x.bot).sort())
            .toEqual(['tennis_flb', 'tennis_pro', 'tennis_scalper', 'tennis_swing']);
    });

    // ---------------------------------------------------- quello che NON entra

    it('NON regolato non e chiuso: «abbinato tutto» non vuol dire «regolato»', async () => {
        const result = await conOrdini([ordine({ settled_at: null, pnl: null, commission: null })]);
        expect(result.current.chiuse).toHaveLength(0);
        // ma resta visibile fra le aperte: non sparisce da nessuna parte
        expect(result.current.posizioni.map((p) => p.bot)).toContain('tennis_scalper');
    });

    it('con il P&L gia scritto ma SENZA settled_at resta aperta: decide il regolamento', async () => {
        const result = await conOrdini([ordine({ settled_at: null })]);
        expect(result.current.chiuse).toHaveLength(0);
    });

    it('regolato SENZA P&L non entra: «0,00 €» sarebbe uno zero travestito', async () => {
        const result = await conOrdini([ordine({ pnl: null, commission: null })]);
        expect(result.current.chiuse).toHaveLength(0);
    });

    it('una riga in errore non e un operazione e non entra', async () => {
        const result = await conOrdini([ordine({ status: 'error' })]);
        expect(result.current.chiuse).toHaveLength(0);
    });

    it('un ordine del RUNNER (source non di un bot) non finisce fra le chiuse', async () => {
        const result = await conOrdini([ordine({ source: 'runner' })]);
        expect(result.current.chiuse).toHaveLength(0);
    });

    // 24/09 - VELOCITA': le chiuse NON si ricostruiscono a ogni battito del
    // feed. Prima dipendevano da `feedPerEvento` (nuovo a ogni lotto dello
    // scanner) e rifacevano tutte le posizioni anche a scheda chiusa.
    it('un battito del feed con gli stessi nomi NON ricostruisce le chiuse; un nome nuovo si', async () => {
        let spingi: ((ev: { type: 'upsert'; row: ScanRow }) => void) | null = null;
        vi.mocked(subscribeScanRows).mockImplementation((cb) => {
            spingi = cb as unknown as typeof spingi;
            return () => { /* niente */ };
        });
        const riga = (minuto: number, nome: string): ScanRow => ({
            event_id: 'T1', sport: 'tennis', updated_at: `${OGGI}T12:0${minuto}:00.000Z`,
            payload: {
                event_name: nome, p1: 'Sinner', p2: 'Alcaraz', competition: 'ATP', open_date: null,
                inplay: true, mo_market_id: '1.77', mo_status: 'OPEN', odds: null,
                sets: { p1: 0, p2: 0 }, games: { p1: minuto, p2: 0 },
            },
        });
        const result = await conOrdini([ordine()]);
        expect(spingi).not.toBeNull();
        spingi!({ type: 'upsert', row: riga(1, 'Sinner - Alcaraz') });
        await waitFor(() => expect(result.current.chiuse[0].partita).toBe('Sinner - Alcaraz'));
        const prima = result.current.chiuse;
        // stesso nome, games cambiati: il feed si muove, le chiuse no
        spingi!({ type: 'upsert', row: riga(2, 'Sinner - Alcaraz') });
        await new Promise((r) => setTimeout(r, 80));
        await waitFor(() => expect(result.current.righeChiuse).toBeDefined());
        expect(result.current.chiuse).toBe(prima);
        // un nome nuovo invece si vede
        spingi!({ type: 'upsert', row: riga(3, 'J. Sinner - C. Alcaraz') });
        await waitFor(() => expect(result.current.chiuse[0].partita).toBe('J. Sinner - C. Alcaraz'));
    });
});

// ================================ 3) LE GAMBE DI CHIUSURA NON SONO POSIZIONI (17/09 sera)

/** Una riga di `safe_strategy_trades` come la manda `get_safe_trades`: chiavi vere. */
function tradeSafe(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 321, event_id: '36061420', event_name: 'Union Brescia - Treviso', sport: 'calcio',
        strategy: 'esatto', market_id: '1.262', market_type: 'CORRECT_SCORE', selection_id: 4,
        selection_name: 'Altro risultato Casa', side: 'lay', mode: 'paper', price: 70, size: 2,
        liability: 138, commission: 0.05, minute_at_entry: 61, score_at_entry: '1-1',
        status: 'open', pnl: 0, bet_id: null, placed_at: PIAZZATO, settled_at: null,
        origin: 'auto', closes_trade_id: null, signal_key: null, meta: {},
        ...over,
    } as SafeTrade;
}

describe('gambe di chiusura: il back che chiude un lay NON e una posizione aperta', () => {
    // il caso vero della sera del 17/09: lay 2 @70 chiuso in perdita da tre back
    // ancora `open` con `closes_trade_id: 321`. In Control Room comparivano come
    // tre posizioni con «chiudi ora»: proporre di chiudere una chiusura.
    it('l apertura resta fra le posizioni, le tre chiusure collegate no', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({
            ...SAFE_VUOTO,
            trades: [
                tradeSafe(),
                tradeSafe({ id: 322, side: 'back', price: 9.6, size: 4.78, liability: 4.78, closes_trade_id: 321 }),
                tradeSafe({ id: 323, side: 'back', price: 9.6, size: 7.2, liability: 7.2, closes_trade_id: 321 }),
                tradeSafe({ id: 324, side: 'back', price: 12, size: 2.08, liability: 2.08, closes_trade_id: 321 }),
            ],
        });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const safe = result.current.posizioni.filter((p) => p.bot === 'safe');
        expect(safe.map((p) => p.id)).toEqual([321]);
        // le tre chiusure restano visibili nella scheda della partita, ANNIDATE
        // sotto l apertura (23/09: non piu' come righe proprie, che mostravano
        // una chiusura come un'operazione a se')
        const op = result.current.operazioni.get('36061420') ?? [];
        expect(op.map((o) => o.id)).toEqual([321]);
        expect(op[0].dettaglio?.chiusure).toHaveLength(3);
        expect(op[0].chiusureOrdini).toHaveLength(3);
    });

    // FALSIFICAZIONE: senza `closes_trade_id` la stessa riga back e una posizione
    it('un back SENZA closes_trade_id e una posizione come le altre', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({
            ...SAFE_VUOTO,
            trades: [tradeSafe({ id: 330, side: 'back', price: 9.6, size: 4.78, liability: 4.78 })],
        });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.posizioni.filter((p) => p.bot === 'safe').map((p) => p.id)).toEqual([330]);
    });
});

// ================================ 4) OBIETTIVO (Task 2, 18/09) ============

import type { TennisBotDailyRow } from '@/lib/tennis';
import type { OmegaTrade } from '@/lib/omega';
import type { MikeTrade } from '@/lib/mike';

function tennisDaily(over: Partial<TennisBotDailyRow> = {}): TennisBotDailyRow {
    return {
        giorno: OGGI, bot_key: 'tennis_scalper', ordini: 1, vinti: 1, persi: 0,
        pnl_lordo: 2, commissione: 0.1, pnl_netto: 1.9, volume: 10,
        ...over,
    };
}

function tradeOmega(over: Partial<OmegaTrade> = {}): OmegaTrade {
    return {
        id: 900, event_id: 'E1', market_id: '1.1', selection_id: 1, side: 'back',
        mode: 'live', price: 2, size: 10, liability: 0, status: 'won', pnl: 14.2,
        placed_at: PIAZZATO, settled_at: REGOLATO, origin: 'auto',
        ...over,
    } as OmegaTrade;
}

function tradeMike(over: Partial<MikeTrade> = {}): MikeTrade {
    return {
        id: 800, event_id: 'E2', market_id: '1.2', selection_id: 2, side: 'back',
        mode: 'live', price: 2, size: 9, liability: 0, status: 'won', pnl: 0.8,
        placed_at: PIAZZATO, settled_at: REGOLATO, origin: 'auto',
        ...over,
    } as MikeTrade;
}

// ============================================================================
// 23/09 — «SE CHIUDO ORA» ANCHE PER MIKE (Task f, market_id/selection_id).
//
// Fino a oggi `mike_trades` scriveva `market_id`/`selection_id` sulla riga
// (`service.py::_trade_row`, dall'11/09) ma il tipo `MikeTrade` non li
// dichiarava e la scheda della Control Room scriveva `chiusura: null,
// vivo: null` a mano per OGNI riga di Mike, qualunque cosa dicesse il feed:
// una posizione in profitto restava invisibile finche' il bot non proponeva.
// Omega/Safe usano lo STESSO meccanismo (`libroVivo`/`chiusuraViva`/
// `quotaViva`, con il feed dello scanner GIA' in memoria): qui si verifica che
// Mike lo condivida davvero, non che esista una sua propria formula.
// ============================================================================

/** payload minimo dello scanner con UN blocco Over/Under (la forma che Mike
 *  usa: `market_type`/`market_id`/`selections[]`, la stessa di `ScanMarketBlock`). */
function payloadConMercatoOU(marketId: string, selectionId: number, back: number, lay: number): CalcioScanPayload {
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

function scanRowMike(eventId: string, payload: CalcioScanPayload): ScanRow {
    return { event_id: eventId, sport: 'calcio', payload, updated_at: PIAZZATO };
}

describe('«chiudi ora» di Mike usa market_id/selection_id come Omega/Safe (23/09)', () => {
    it('con market_id/selection_id sulla riga e il mercato nel feed, chiusura e vivo si calcolano', async () => {
        vi.mocked(fetchScanRows).mockResolvedValue([
            scanRowMike('E2', payloadConMercatoOU('1.2', 2, 1.90, 1.92)),
        ]);
        vi.mocked(fetchMikeState).mockResolvedValue({
            ...MIKE_VUOTO,
            trades: [tradeMike({ id: 801, status: 'open', price: 1.85, settled_at: null })],
        });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const p = result.current.posizioni.find((x) => x.bot === 'mike' && x.id === 801);
        expect(p).toBeDefined();
        // lato back: si chiude con un lay, al prezzo LAY vivo del feed (1,92)
        expect(p!.chiusura?.prezzo).toBe(1.92);
        expect(p!.chiusura?.bloccabile).not.toBeNull();
        expect(p!.vivo?.back).toBe(1.90);
        expect(p!.vivo?.lay).toBe(1.92);
    });

    it('una riga STORICA senza market_id/selection_id resta "—": null, mai un numero indovinato', async () => {
        vi.mocked(fetchScanRows).mockResolvedValue([
            scanRowMike('E2', payloadConMercatoOU('1.2', 2, 1.90, 1.92)),
        ]);
        vi.mocked(fetchMikeState).mockResolvedValue({
            ...MIKE_VUOTO,
            trades: [tradeMike({
                id: 802, status: 'open', price: 1.85, settled_at: null,
                market_id: null, selection_id: null,
            })],
        });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const p = result.current.posizioni.find((x) => x.bot === 'mike' && x.id === 802);
        expect(p).toBeDefined();
        expect(p!.chiusura?.prezzo ?? null).toBeNull();
        expect(p!.vivo).toBeNull();
    });

    // FALSIFICAZIONE (provata a mano, 23/09): nel primo test, rimettendo
    // `chiusura: null, vivo: null` a mano nel ramo Mike di `posizioni`
    // (`useControlRoom.ts`) invece di `chiusuraViva(t)`/`quotaViva(...)`, il
    // primo test sopra torna ROSSO (`p!.chiusura?.prezzo` e `p!.vivo?.back`
    // tornano `undefined`/`null` invece dei prezzi del feed). Verificato e
    // ripristinato.
});

describe('bot tennis live entrano nel realizzato, paper mai (Task 2)', () => {
    it('il realizzato LIVE della barra include i 4 bot tennis dedicati', async () => {
        vi.mocked(fetchTennisBotDaily).mockImplementation(async (_from, _to, mode) => (
            mode === 'live'
                ? [tennisDaily({ bot_key: 'tennis_scalper', pnl_netto: 2 }), tennisDaily({ bot_key: 'tennis_pro', pnl_netto: 3 })]
                : []
        ));
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.realizzatoOggi.live.totale).toBe(5);
        expect(result.current.realizzatoOggi.live.perSport.tennis).toBe(5);
    });

    it('il PAPER dei bot tennis non entra MAI nel live', async () => {
        vi.mocked(fetchTennisBotDaily).mockImplementation(async (_from, _to, mode) => (
            mode === 'paper' ? [tennisDaily({ bot_key: 'tennis_swing', pnl_netto: -9 })] : []
        ));
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.realizzatoOggi.live.totale).toBeNull();
        expect(result.current.realizzatoOggi.paper.totale).toBe(-9);
    });

    // FALSIFICAZIONE: se si dimenticasse di aggiungere le righe sintetiche dei
    // bot tennis a `realizzatoOggi`, questo test tornerebbe rosso (totale
    // null invece di 5) — provato togliendo `...tennisBotRighe` dalla riga
    // costruita in `useControlRoom.ts` e ripristinato.
    it('falsificazione: senza i bot tennis il realizzato NON li includerebbe', async () => {
        vi.mocked(fetchTennisBotDaily).mockImplementation(async (_from, _to, mode) => (
            mode === 'live' ? [tennisDaily({ pnl_netto: 5 })] : []
        ));
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.realizzatoOggi.live.totale).toBe(5);
    });
});

describe('salvataggio dell’obiettivo non tocca gli altri parametri (Task 2)', () => {
    it('salvaObiettivo chiama updateOmegaParams SOLO con dailyGoal', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.salvaObiettivo(75);
        expect(updateOmegaParams).toHaveBeenCalledWith({ dailyGoal: 75 });
        // NON un secondo argomento, NON `params`/`mode` dentro l'oggetto
        const arg = vi.mocked(updateOmegaParams).mock.calls[0][0];
        expect(Object.keys(arg)).toEqual(['dailyGoal']);
    });

    it('dopo il salvataggio la pagina si ricarica (la barra si riallinea)', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        vi.mocked(fetchOmegaState).mockResolvedValueOnce({ ...OMEGA_VUOTO, goal_today: 75 } as never);
        await result.current.salvaObiettivo(75);
        await waitFor(() => expect(result.current.obiettivo).toBe(75));
    });
});

describe('composizioneOggi separa Omega/Safe calcio/Safe tennis/Mike/bot tennis/manuale', () => {
    it('ogni bucket prende solo le sue righe, il manuale è distinto e non raddoppiato', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([tradeOmega()]);
        vi.mocked(fetchSafeState).mockResolvedValue({
            ...SAFE_VUOTO,
            trades: [
                tradeSafe({ id: 1, sport: 'calcio', mode: 'live', status: 'won', pnl: 9.6, origin: 'auto' }),
                tradeSafe({ id: 2, sport: 'calcio', mode: 'live', status: 'won', pnl: 2, origin: 'manual' }),
            ],
        });
        vi.mocked(fetchMikeState).mockResolvedValue({ ...MIKE_VUOTO, trades: [tradeMike()] });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const per = Object.fromEntries(result.current.composizioneOggi.righe.map((r) => [r.chiave, r.valore]));
        expect(per.omega).toBe(14.2);
        expect(per.safe_calcio).toBe(9.6);   // SOLO la riga auto
        expect(per.manuale).toBe(2);         // la riga manuale, distinta
        expect(per.mike).toBe(0.8);
        // MAI raddoppiata: la somma delle righe è il totale delle STESSE righe di realizzatoOggi
        expect(result.current.composizioneOggi.totale).toBeCloseTo(result.current.realizzatoOggi.live.totale ?? 0, 2);
    });

    it('manualeSitoBetfair è sempre "non disponibile" oggi, mai un numero inventato', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.manualeSitoBetfair.pnlOggi).toBeNull();
        expect(result.current.manualeSitoBetfair.fonte).toBe('non-disponibile');
    });
});

// ================================= RACCORDO R3 — money-critical (falsificato)
describe('una posizione HEDGED con esposizione residua resta fra le Aperte', () => {
    it('non sparisce solo perche il bot l ha marcata hedged: resta finche non e REGOLATA', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({
            ...SAFE_VUOTO,
            trades: [tradeSafe({ id: 900, status: 'hedged', closes_trade_id: null })],
        });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.posizioni.some((p) => p.id === 900)).toBe(true);
        expect(result.current.chiuse.some((c) => c.righe.some((r) => r.id === 900))).toBe(false);
    });
    // FALSIFICAZIONE: `aMercato()` (useControlRoom.ts) mutata per trattare
    // 'hedged' come regolata (`isSettled(t.status) || t.status === 'hedged'`
    // negato) -> la posizione sparisce dalle Aperte -> test sopra ROSSO.
    // Verificata a mano e ripristinata, md5 del file invariato.
});

// ================================= RACCORDO R2 — money-critical (falsificato)
describe('piazzaOpportunita manda ESATTAMENTE il prezzo che la scheda mostra', () => {
    it('il prezzo visto passato dalla scheda arriva IDENTICO a approvaPropostaOpportunita (mai quello della proposta)', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        vi.mocked(approvaPropostaOpportunita).mockReset().mockResolvedValue(undefined);
        await result.current.piazzaOpportunita(55, 1.87);
        expect(approvaPropostaOpportunita).toHaveBeenCalledWith(
            55, { prezzoVisto: 1.87, legsPricesVisti: undefined, slippagePct: undefined },
        );
    });
    // FALSIFICAZIONE: in `piazzaOpportunita` (useControlRoom.ts) tolto
    // l'inoltro di `prezzoVisto` (passato `undefined` a `approvaProposta
    // Opportunita`) -> l'asserzione sopra (`prezzoVisto: 1.87`) diventa
    // ROSSA. Verificata a mano e ripristinata, md5 del file invariato.

    // 24/09 — il CONTESTO del prezzo visto (eta', fonte, flag) viaggia con la firma
    const CTX = { eta_ms: 42000, fonte: 'scanner' as const, prezzo_vivo_assente: true, clic_ms: 1 };

    it('il contesto del prezzo visto arriva alla RPC (p_contesto)', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        vi.mocked(approvaPropostaOpportunita).mockReset().mockResolvedValue(undefined);
        await act(async () => { await result.current.piazzaOpportunita(55, 1.3, undefined, undefined, CTX); });
        expect(approvaPropostaOpportunita).toHaveBeenCalledTimes(1);
        expect(approvaPropostaOpportunita).toHaveBeenCalledWith(55, expect.objectContaining({
            prezzoVisto: 1.3, contesto: CTX }));
        expect(result.current.avvisoOpportunita).toBeNull();
    });

    it('migrazione del 24/09 assente: UN ripiego senza contesto, col prezzo visto, e lo dice', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        vi.mocked(approvaPropostaOpportunita).mockReset()
            .mockRejectedValueOnce(new Error('PGRST202 function not found'))
            .mockResolvedValueOnce(undefined);
        await act(async () => { await result.current.piazzaOpportunita(55, 1.3, undefined, undefined, CTX); });
        expect(approvaPropostaOpportunita).toHaveBeenCalledTimes(2);
        expect(vi.mocked(approvaPropostaOpportunita).mock.calls[1]).toEqual(
            [55, { prezzoVisto: 1.3, legsPricesVisti: undefined, slippagePct: undefined }]);
        expect(result.current.avvisoOpportunita).toMatch(/migrazione del 24\/09/);
    });

    it('un rifiuto VERO non si ripiega (mai una doppia approvazione)', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        vi.mocked(approvaPropostaOpportunita).mockReset()
            .mockRejectedValueOnce(new Error('la proposta non è più in attesa di approvazione'));
        await expect(result.current.piazzaOpportunita(55, 1.3, undefined, undefined, CTX)).rejects.toThrow(/non è più/);
        expect(approvaPropostaOpportunita).toHaveBeenCalledTimes(1);
    });

    it('l’esito dell’approvazione arriva a video: inviata, poi rifiutata coi due prezzi', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        vi.mocked(approvaPropostaOpportunita).mockReset().mockResolvedValue(undefined);
        await act(async () => { await result.current.piazzaOpportunita(56, 1.3, undefined, undefined, CTX); });
        await waitFor(() => expect(result.current.esitiOpportunita[0]?.stato).toBe('rifiutata'));
        expect(result.current.esitiOpportunita[0].id).toBe(56);
        expect(result.current.esitiOpportunita[0].testo).toMatch(/visto 1\.3, all’esecuzione 1\.4/);
    });
});

// ============================================================================
// 23/09 - IL NETTO DEL CICLO (bug segnalato dall'utente su Safe tennis live).
//
// Righe VERE di `safe_strategy_trades` (lette dal coordinatore, 14-22/09): la
// chiusura del cash out e' una riga SEPARATA con `closes_trade_id` = apertura,
// `meta.cashout = "true"`, `exit_kind = "manual"`, `origin = 'manual'`
// (bot_service.py:2684), stesso `settled_at` dell'apertura; `pnl` per gamba e
// LORDO, `commission` = 0.05 e' l'aliquota.
//   326 back 3,00 @1.15 won +0.45 + 327 lay 3,17 @1.08 lost -0.25 -> +0.20
//   307 back 3,00 @1.12 lost -3.00 + 317 lay 3,11 @1.08 won +3.11 -> +0.11
// ============================================================================
function cicliVeri(): SafeTrade[] {
    const base = {
        event_id: 'T1', event_name: 'Rossi v Bianchi', sport: 'tennis', strategy: 'tennis',
        market_id: '1.300', market_type: 'MATCH_ODDS', selection_id: 11, selection_name: 'Rossi',
        mode: 'live', liability: 3, commission: 0.05, minute_at_entry: null, score_at_entry: null,
        bet_id: 'B', settled_at: REGOLATO, signal_key: null,
    } as const;
    return [
        tradeSafe({ ...base, id: 326, side: 'back', price: 1.15, size: 3, status: 'won', pnl: 0.45,
            placed_at: `${OGGI}T12:00:00.000Z`, origin: 'auto', closes_trade_id: null, meta: {} }),
        tradeSafe({ ...base, id: 327, side: 'lay', price: 1.08, size: 3.17, status: 'lost', pnl: -0.25,
            placed_at: `${OGGI}T12:10:00.000Z`, origin: 'manual', closes_trade_id: 326,
            meta: { cashout: 'true', exit_kind: 'manual' } }),
        tradeSafe({ ...base, id: 307, side: 'back', price: 1.12, size: 3, status: 'lost', pnl: -3,
            placed_at: `${OGGI}T11:00:00.000Z`, origin: 'auto', closes_trade_id: null, meta: {} }),
        tradeSafe({ ...base, id: 317, side: 'lay', price: 1.08, size: 3.11, status: 'won', pnl: 3.11,
            placed_at: `${OGGI}T11:20:00.000Z`, origin: 'manual', closes_trade_id: 307,
            meta: { cashout: 'true', exit_kind: 'manual' } }),
    ];
}

describe('23/09 - ogni operazione chiusa mostra il NETTO del ciclo, barra compresa', () => {
    it('scheda partita: una riga per ciclo, col netto (+0.20 / +0.11), mai la chiusura come riga', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: cicliVeri() });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const op = result.current.operazioni.get('T1') ?? [];
        const per = Object.fromEntries(op.map((o) => [o.id, o.pnl]));
        expect(Object.keys(per).map(Number).sort()).toEqual([307, 326]);
        expect(per[326]).toBe(0.2);
        expect(per[307]).toBe(0.11);
    });

    it('posizioni chiuse: +0.20 e +0.11, nessuna orfana', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: cicliVeri() });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const per = Object.fromEntries(result.current.chiuse.map((c) => [c.id, c.pnlGlobale]));
        expect(per).toEqual({ 326: 0.2, 307: 0.11 });
        expect(result.current.chiuse.every((c) => !c.orfana)).toBe(true);
    });

    it('barra: realizzato = somma dei netti, contatori per OPERAZIONE (2 vinte, 0 perse)', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: cicliVeri() });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.soldiGiornata.realizzato).toBe(0.31);
        expect(result.current.soldiGiornata.operazioni).toBe(2);
        expect(result.current.soldiGiornata.vinte).toBe(2);
        expect(result.current.soldiGiornata.perse).toBe(0);
    });

    it('composizione: Safe tennis = +0.31 (netto dei cicli), il cash out NON finisce in Manuale', async () => {
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: cicliVeri() });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const per = Object.fromEntries(result.current.composizioneOggi.righe.map((r) => [r.chiave, r.valore]));
        expect(per.safe_tennis).toBe(0.31);
        expect(per.manuale).toBeNull();
        expect(result.current.composizioneOggi.totale).toBe(0.31);
    });

    it('chiusura ORFANA (apertura fuori dalle righe lette): resta visibile, dichiarata, col suo P&L', async () => {
        const [, chiusura] = cicliVeri();
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: [chiusura] });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect(result.current.chiuse.map((c) => [c.id, c.pnlGlobale, c.orfana])).toEqual([[327, -0.25, true]]);
        expect((result.current.operazioni.get('T1') ?? []).map((o) => [o.id, o.pnl])).toEqual([[327, -0.25]]);
        expect(result.current.soldiGiornata.realizzato).toBe(-0.25);
    });

    it('chiusura ancora VIVA su un apertura regolata: il netto non e definitivo (null, trattino)', async () => {
        const righe = cicliVeri().slice(0, 2);
        righe[1] = { ...righe[1], status: 'open', pnl: 0, settled_at: null };
        vi.mocked(fetchSafeState).mockResolvedValue({ ...SAFE_VUOTO, trades: righe });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        expect((result.current.operazioni.get('T1') ?? []).map((o) => [o.id, o.pnl])).toEqual([[326, null]]);
    });
});

// ============================================================================
// B16 (24/09) — IL «CHIUDI» DI UNA RIGA VA AL SUO BOT, MAI A SAFE PER TUTTI.
//
// Il reperto: `chiudi(tradeId)` accodava `requestSafe('cashout', …)` per
// qualunque riga. Qui, dal modello di vista vero: ogni bot riceve la richiesta
// sulla SUA coda con bot/partita/modalita' della riga; i 4 bot tennis non
// mandano niente e lo dicono; l'esito si legge dalla coda del bot (rifiuto col
// motivo) e dalla riga che cambia (eseguita).
// FALSIFICAZIONE (24/09): rimettendo `requestSafe` per ogni bot in `INVIO`
// (chiudiRiga.ts) i test Omega/Mike diventano ROSSI; togliendo la lettura
// della coda il test del rifiuto diventa ROSSO.
// ============================================================================
import { requestManual, fetchManualRequests } from '@/lib/omega';
import { requestSafe } from '@/lib/safeBot';
import { requestMike } from '@/lib/mike';
import { svegliaBot } from '@/lib/localChannel';
import { faseMostrata } from './chiudiRiga';

describe('B16 - «Chiudi» cablato per singolo bot', () => {
    // `vi.clearAllMocks` non azzera le implementazioni: ogni test parte dalle
    // code VUOTE dei tre bot, come un servizio appena avviato
    beforeEach(() => {
        vi.mocked(fetchManualRequests).mockResolvedValue([]);
        vi.mocked(requestManual).mockResolvedValue(7001);
        vi.mocked(requestSafe).mockResolvedValue(7002);
        vi.mocked(requestMike).mockResolvedValue(7003);
    });

    it('riga OMEGA: omega_request sulla coda di Omega, MAI safe_request', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([
            tradeOmega({ id: 900, status: 'open', pnl: 0, settled_at: null }),
        ]);
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.chiudi({ bot: 'omega', id: 900, eventId: 'E1', modalita: 'live', stato: 'open' });
        expect(requestManual).toHaveBeenCalledWith('cashout', {
            trade_id: 900, fraction: 1, bot: 'omega', event_id: 'E1', mode: 'live',
        });
        expect(requestSafe).not.toHaveBeenCalled();
        expect(requestMike).not.toHaveBeenCalled();
        expect(svegliaBot).toHaveBeenCalledWith('omega', 'comando');
        await waitFor(() => expect(result.current.statoChiusuraRiga('omega', 900)?.requestId).toBe(7001));
    });

    it("riga MIKE: mike_request per la PARTITA della riga, nella sua modalita'", async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.chiudi({ bot: 'mike', id: 801, eventId: 'E2', modalita: 'paper', stato: 'open' });
        expect(requestMike).toHaveBeenCalledWith('cashout', {
            event_id: 'E2', trade_id: 801, bot: 'mike', mode: 'paper',
        });
        expect(requestSafe).not.toHaveBeenCalled();
        expect(requestManual).not.toHaveBeenCalled();
        expect(svegliaBot).toHaveBeenCalledWith('mike', 'comando');
    });

    it("riga SAFE: safe_request con bot/partita/modalita' della riga", async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.chiudi({ bot: 'safe', id: 321, eventId: '36061420', modalita: 'paper', stato: 'open' });
        expect(requestSafe).toHaveBeenCalledWith('cashout', {
            trade_id: 321, fraction: 1, bot: 'safe', event_id: '36061420', mode: 'paper',
        });
        expect(requestManual).not.toHaveBeenCalled();
        expect(requestMike).not.toHaveBeenCalled();
    });

    it('bot TENNIS: nessuna richiesta a nessuno, il motivo si legge', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.chiudi({ bot: 'tennis_pro', id: 5, eventId: 'T1', modalita: 'paper', stato: 'EXECUTABLE' });
        expect(requestSafe).not.toHaveBeenCalled();
        expect(requestManual).not.toHaveBeenCalled();
        expect(requestMike).not.toHaveBeenCalled();
        await waitFor(() => expect(result.current.statoChiusuraRiga('tennis_pro', 5)).not.toBeNull());
        const s = result.current.statoChiusuraRiga('tennis_pro', 5)!;
        expect(faseMostrata(s)).toBe('rifiutata');
        expect(s.motivo).toContain('bot tennis');
    });

    it('il RIFIUTO scritto dal servizio sulla coda di Omega arriva con il suo motivo', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([
            tradeOmega({ id: 900, status: 'open', pnl: 0, settled_at: null }),
        ]);
        vi.mocked(fetchManualRequests).mockResolvedValue([{
            id: 7001, kind: 'cashout', payload: { trade_id: 900 }, status: 'error',
            result: {
                error: 'richiesta_ambigua',
                message: "rifiutato: la modalita' della richiesta (live) non e' quella della riga (paper)",
            },
            created_at: PIAZZATO, processed_at: REGOLATO,
        }]);
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.chiudi({ bot: 'omega', id: 900, eventId: 'E1', modalita: 'live', stato: 'open' });
        await waitFor(() => {
            const s = result.current.statoChiusuraRiga('omega', 900);
            expect(s && faseMostrata(s)).toBe('rifiutata');
        });
        expect(result.current.statoChiusuraRiga('omega', 900)!.motivo).toContain('modalita');
    });

    it('la riga che CAMBIA (gamba di chiusura nuova) = eseguita', async () => {
        vi.mocked(fetchOmegaTrades).mockResolvedValue([
            tradeOmega({ id: 900, status: 'open', pnl: 0, settled_at: null }),
        ]);
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.chiudi({ bot: 'omega', id: 900, eventId: 'E1', modalita: 'live', stato: 'open' });
        await waitFor(() => expect(result.current.statoChiusuraRiga('omega', 900)).not.toBeNull());
        expect(faseMostrata(result.current.statoChiusuraRiga('omega', 900)!)).toBe('inviata');
        // il bot ha piazzato la chiusura: la riga porta ora la sua gamba figlia
        vi.mocked(fetchOmegaTrades).mockResolvedValue([
            tradeOmega({ id: 900, status: 'hedged', pnl: 0, settled_at: null }),
            tradeOmega({ id: 901, side: 'lay', status: 'open', pnl: 0, settled_at: null, closes_trade_id: 900 } as never),
        ]);
        result.current.ricarica();
        await waitFor(() => expect(faseMostrata(result.current.statoChiusuraRiga('omega', 900)!)).toBe('eseguita'));
    });
});

// ============================================================================
// 24/09 - LO SCALPER CALCIO IN CONTROL ROOM ("come tutti gli altri bot").
// Una lettura (`get_scalper_control_room`): la riga della plancia, le righe
// per partita (sessioni), le posizioni aperte e chiuse, la barra (reale di
// Betfair per bet_id, spostato dal "manuale app" dove il runner lo mette oggi),
// e il Chiudi (stop della sessione con la sua firma).
// FALSIFICAZIONE (24/09, patch salvata): tolto `scalperRighe` dalla
// composizione -> rossa la voce; tolta la sottrazione dal manuale app ->
// rossa (1,30 invece di 1,00); `ordiniDellaSessione` senza filtro di
// modalita' -> rossa l'esposizione paper; `firma` non passata -> rosso il Chiudi.
// ============================================================================
import { stopScalperSessione } from '@/lib/scalperControlRoom';
import { fetchScalperState } from '@/lib/scalper';
import { sessione as sessioneScalper, ordine as ordineScalper } from '@/lib/__fixtures__/scalperFinti';

describe('scalper calcio: riga, sessioni, posizioni, barra e Chiudi', () => {
    const ADESSO = new Date().toISOString();
    const FIRMA_B = `${OGGI}T11:00:00.654321+00:00`;
    /** A: sessione LIVE ferma, due ordini regolati oggi da Betfair (+0,50 e -0,20) */
    const A = sessioneScalper({
        event_id: '101', status: 'stopped', dry_run: false, requested_at: `${OGGI}T10:00:00+00:00`,
        started_at: `${OGGI}T10:00:03+00:00`, stopped_at: `${OGGI}T10:40:00+00:00`,
        event_name: 'Roma v Lazio', stats: { pnl_locked: 0.35 },
    });
    /** B: sessione PAPER in corso, un back abbinato e un lay sul book */
    const B = sessioneScalper({
        event_id: '202', status: 'running', dry_run: true, requested_at: FIRMA_B,
        started_at: `${OGGI}T11:00:03+00:00`, heartbeat_at: ADESSO, event_name: 'Inter v Milan',
    });
    const ORDINI = [
        ordineScalper({ id: 1, event_id: '101', mode: 'live', bet_id: '11', pnl_betfair: 0.5,
            placed_at: `${OGGI}T10:05:00+00:00`, pnl_betfair_settled_at: ADESSO }),
        ordineScalper({ id: 2, event_id: '101', mode: 'live', bet_id: '12', side: 'lay', pnl_betfair: -0.2,
            placed_at: `${OGGI}T10:06:00+00:00`, pnl_betfair_settled_at: ADESSO }),
        ordineScalper({ id: 3, event_id: '202', mode: 'paper', bet_id: '100000000001',
            size_matched: 10, average_price_matched: 2.5, placed_at: `${OGGI}T11:05:00+00:00` }),
        ordineScalper({ id: 4, event_id: '202', mode: 'paper', bet_id: '100000000002', side: 'lay',
            size: 10, size_matched: 0, size_remaining: 10, status: 'EXECUTABLE',
            placed_at: `${OGGI}T11:05:01+00:00` }),
    ];
    /** il P&L reale del conto: il runner ha messo i due ordini dello scalper nel "manuale app" */
    const CONTO = {
        day: OGGI, netto: 1.3, ordini: 3,
        per_fonte: {
            omega: { netto: 0, ordini: 0 }, safe_calcio: { netto: 0, ordini: 0 },
            safe_tennis: { netto: 0, ordini: 0 }, mike: { netto: 0, ordini: 0 },
            bot_tennis: { netto: 0, ordini: 0 }, manuale_app: { netto: 1.3, ordini: 3 },
            manuale_sito: { netto: 0, ordini: 0 }, altri_bot: { netto: 0, ordini: 0 },
        },
        bet_ids: ['11', '12', '99'], senza_commissione: 0, sospetti_sito: 0, letto_at: ADESSO,
    };

    beforeEach(() => {
        vi.mocked(fetchScalperControlRoom).mockResolvedValue({ sessioni: [A, B], ordini: ORDINI, lettoAt: ADESSO });
        vi.mocked(stopScalperSessione).mockResolvedValue({} as never);
        vi.mocked(fetchScalperState).mockResolvedValue({ control: null, activity: [] });
    });

    it('la riga della plancia: acceso in PROVA (solo B e viva), nota con fonte ed eta, P&L reale di oggi', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.bots.find((b) => b.bot === 'scalper')?.stato).toBe('running'));
        const s = result.current.bots.find((b) => b.bot === 'scalper')!;
        expect(s).toMatchObject({ inCorsa: true, modalita: 'paper', pnlOggi: 0.3, pnlOggiPaper: null });
        expect(s.nota).toContain('1 sessione viva (1 prova)');
        expect(s.nota).toMatch(/dal database, letto \d+ s fa/);
    });

    it('lettura mai riuscita: stato non letto, mai "fermo"', async () => {
        vi.mocked(fetchScalperControlRoom).mockRejectedValue(new Error('RPC assente'));
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        const s = result.current.bots.find((b) => b.bot === 'scalper')!;
        expect(s.stato).toBeNull();
        expect(s.inCorsa).toBe(false);
        expect(result.current.errore).toBe('fonti non raggiunte: scalper calcio');
    });

    it('posizioni aperte: la sessione VIVA, con abbinato, responsabilita e firma; la ferma e regolata no', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.posizioni.some((p) => p.bot === 'scalper')).toBe(true));
        const pos = result.current.posizioni.filter((p) => p.bot === 'scalper');
        expect(pos).toHaveLength(1);
        expect(pos[0]).toMatchObject({
            id: 202, eventId: '202', partita: 'Inter v Milan', modalita: 'paper',
            size: 10, liability: 10, firma: FIRMA_B,
        });
        // paper e live mai mischiati: gli ordini LIVE della partita 101 non entrano in B
        expect(pos[0].ordine).toMatchObject({ size_requested: 20, size_matched: 10, size_remaining: 10 });
    });

    it('righe per partita: una per sessione, con firma, nota (fonte/eta/lordo) e P&L reale solo se tutto regolato', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.operazioni.get('101')?.length).toBe(1));
        const a = result.current.operazioni.get('101')![0];
        expect(a).toMatchObject({ bot: 'scalper', id: 101, stato: 'stopped', modalita: 'live', pnl: 0.3 });
        expect(a.notaSessione).toContain('+0.35 EUR lordo');
        expect(a.notaSessione).toContain('fonte: database');
        const b = result.current.operazioni.get('202')![0];
        expect(b).toMatchObject({ bot: 'scalper', id: 202, modalita: 'paper', pnl: null, firma: FIRMA_B });
    });

    it('posizioni chiuse: la sessione LIVE ferma e regolata, col netto di Betfair', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.chiuse.some((c) => c.bot === 'scalper')).toBe(true));
        const c = result.current.chiuse.filter((x) => x.bot === 'scalper');
        expect(c).toHaveLength(1);   // la sessione PAPER non entra: il bot ha solo un lordo
        expect(c[0]).toMatchObject({ id: 101, pnlGlobale: 0.3, modo: 'live', fontePnl: 'betfair', esito: 'vinta' });
    });

    it('barra: voce Scalper = reale di Betfair; il manuale app perde gli stessi euro (mai due volte)', async () => {
        vi.mocked(fetchLiveAccount).mockResolvedValue({ pnl_reale_oggi: CONTO } as never);
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(
            result.current.composizioneOggi.righe.find((r) => r.chiave === 'scalper')?.valore).toBe(0.3));
        const voce = (k: string) => result.current.composizioneOggi.righe.find((r) => r.chiave === k)?.valore;
        expect(voce('manuale_app')).toBe(1);
        // il totale e' quello del conto: nessun euro contato due volte
        expect(result.current.composizioneOggi.totale).toBe(1.3);
        expect(result.current.soldiGiornata.perBot.scalper).toBe(0.3);
    });

    it('Chiudi: stop della SESSIONE con la sua firma e modalita, poi presa in carico', async () => {
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.operazioni.get('202')?.length).toBe(1));
        vi.mocked(fetchScalperState).mockResolvedValue({
            control: { ...B, status: 'stopping' } as never, activity: [],
        });
        await result.current.chiudi({
            bot: 'scalper', id: 202, eventId: '202', modalita: 'paper', stato: 'running', firma: FIRMA_B,
        });
        expect(stopScalperSessione).toHaveBeenCalledWith('202', FIRMA_B, 'paper');
        expect(requestSafe).not.toHaveBeenCalled();
        await waitFor(() => expect(
            faseMostrata(result.current.statoChiusuraRiga('scalper', 202)!)).toBe('presa_in_carico'));
    });

    it('Chiudi rifiutato dalla guardia d identita: rifiutata, col motivo', async () => {
        vi.mocked(stopScalperSessione).mockRejectedValue(
            new Error('richiesta_ambigua: la sessione di 202 e\' stata riarmata'));
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await result.current.chiudi({
            bot: 'scalper', id: 202, eventId: '202', modalita: 'paper', stato: 'running', firma: FIRMA_B,
        });
        await waitFor(() => expect(result.current.statoChiusuraRiga('scalper', 202)).not.toBeNull());
        const s = result.current.statoChiusuraRiga('scalper', 202)!;
        expect(faseMostrata(s)).toBe('rifiutata');
        expect(s.motivo).toContain('richiesta_ambigua');
    });
});
