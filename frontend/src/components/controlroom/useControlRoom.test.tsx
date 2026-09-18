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
import { renderHook, waitFor } from '@testing-library/react';
import type { TennisBotOrderRow } from '@/lib/tennis';
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
}));

vi.mock('@/lib/safeBot', async (orig) => ({
    ...(await orig() as object),
    fetchSafeState: vi.fn(async () => ({ control: null, trades: [], aggregates: null })),
    fetchRunnerState: vi.fn(async () => ({ ts: null, mode: null, ageS: null, up: false })),
    requestSafe: vi.fn(async () => undefined),
    cashOutEvento: vi.fn(async () => undefined),
    riprendiEventoSafe: vi.fn(async () => undefined),
    approvaPropostaOpportunita: vi.fn(async () => undefined),
}));

vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    fetchMikeState: vi.fn(async () => ({ control: null, events: [], trades: [], activity: [], aggregates: null, requests: [], day_start: null, day_by: null })),
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
        expect(FONTI_RICARICA.slice(-4)).toEqual([
            'servizi bot tennis',
            'giornata bot tennis live',
            'giornata bot tennis paper',
            'ordini bot tennis di oggi',
        ]);
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
        // le tre chiusure restano visibili nella scheda della partita, sotto l apertura
        const op = result.current.operazioni.get('36061420') ?? [];
        expect(op.map((o) => o.id).sort()).toEqual([321, 322, 323, 324]);
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
        vi.mocked(approvaPropostaOpportunita).mockClear().mockResolvedValueOnce(undefined);
        await result.current.piazzaOpportunita(55, 1.87);
        expect(approvaPropostaOpportunita).toHaveBeenCalledWith(
            55, { prezzoVisto: 1.87, legsPricesVisti: undefined, slippagePct: undefined },
        );
    });
    // FALSIFICAZIONE: in `piazzaOpportunita` (useControlRoom.ts) tolto
    // l'inoltro di `prezzoVisto` (passato `undefined` a `approvaProposta
    // Opportunita`) -> l'asserzione sopra (`prezzoVisto: 1.87`) diventa
    // ROSSA. Verificata a mano e ripristinata, md5 del file invariato.
});
