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
}));

vi.mock('@/lib/safeBot', async (orig) => ({
    ...(await orig() as object),
    fetchSafeState: vi.fn(async () => ({ control: null, trades: [], aggregates: null })),
    fetchRunnerState: vi.fn(async () => ({ ts: null, mode: null, ageS: null, up: false })),
    requestSafe: vi.fn(async () => undefined),
    cashOutEvento: vi.fn(async () => undefined),
    riprendiEventoSafe: vi.fn(async () => undefined),
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

import { fetchScanRows, fetchScanStatus, subscribeScanRows, subscribeScanStatus } from '@/lib/safeStrategyScan';
import { fetchOmegaState, fetchOmegaTrades, fetchOmegaEvents } from '@/lib/omega';
import { fetchSafeState, fetchRunnerState } from '@/lib/safeBot';
import { fetchMikeState } from '@/lib/mike';
import { fetchProposte } from '@/lib/controlRoomProposte';
import { fetchMissions } from '@/lib/omegaMissions';
import { fetchLiveFollows } from '@/lib/live';
import { fetchSafeDaily } from '@/lib/dailyHistory';
import {
    fetchTennisFollows, fetchTennisBotServices, fetchTennisBotDaily,
    fetchTennisBotOrdersToday,
} from '@/lib/tennis';
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
