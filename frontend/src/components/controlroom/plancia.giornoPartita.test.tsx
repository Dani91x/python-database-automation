// ============================================================================
// plancia.giornoPartita.test.tsx - RILIEVI BASSI 01/10, punto 1.
//
// La plancia «oggi per bot» (cifra LIVE dalle righe dei bot), il riassunto del
// gruppo della plancia («oggi» del gruppo BOT CALCIO) e la scheda Posizioni
// chiuse devono dire LO STESSO NUMERO per lo stesso giorno e la stessa moneta.
// Prima la plancia contava per giorno di REGOLAMENTO sulle sole righe in
// memoria; la scheda per giorno della PARTITA (dal database). Una partita di
// ieri sera regolata dopo mezzanotte finiva «oggi» nella plancia e «ieri»
// nella scheda.
//
// Finti: righe con le chiavi di `omega_trades` / `mike_trades` (le stesse dei
// test di `useControlRoom`), e la lettura della giornata con le chiavi del
// contratto del 01/10 (`giorno_partita`, `giorno_da`, `in_day`), costruita con
// la funzione VERA della scheda (`righeDaRisposta`). Le TRE viste ricevono gli
// STESSI finti.
//
// La barra del CONTO (regolato Betfair per giorno di regolamento) NON e' qui:
// resta com'e' (fonte CONTO). Il conto in questo test NON e' letto, quindi la
// cifra LIVE della plancia viene dalle righe dei bot (fonte BOT).
//
// FALSIFICAZIONE: vedi il referto `AUDIT_2026-10-01/RILIEVI_BASSI.md` (punto 1).
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { OmegaTrade } from '@/lib/omega';
import type { MikeTrade } from '@/lib/mike';

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
    fetchManualRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/safeBot', async (orig) => ({
    ...(await orig() as object),
    fetchSafeState: vi.fn(async () => ({ control: null, trades: [], aggregates: null })),
    fetchRunnerState: vi.fn(async () => ({ ts: null, mode: null, ageS: null, up: false })),
    fetchSafeRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    fetchMikeState: vi.fn(async () => ({ control: null, events: [], trades: [], activity: [], aggregates: null, requests: [], day_start: null, day_by: null })),
    fetchMikeRequests: vi.fn(async () => []),
}));
vi.mock('@/lib/controlRoomProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposte: vi.fn(async () => []),
    subscribeProposte: vi.fn(() => () => { /* nessun evento */ }),
}));
vi.mock('@/lib/omegaProposte', async (orig) => ({
    ...(await orig() as object),
    fetchProposteOmega: vi.fn(async () => []),
    subscribeProposteOmega: vi.fn(() => () => { /* nessun evento */ }),
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
}));
vi.mock('@/lib/scalper', async (orig) => ({
    ...(await orig() as object),
    fetchScalperState: vi.fn(async () => ({ control: null, activity: [] })),
}));
// la lettura della giornata: SOLO il lettore e' finto; `posizioniDellaGiornata`
// e `righeDaRisposta` restano le vere
vi.mock('@/lib/chiuseGiornata', async (orig) => ({
    ...(await orig() as object),
    chiuseGiornata: vi.fn(async () => { throw new Error('non letta'); }),
}));

import { fetchOmegaTrades } from '@/lib/omega';
import { fetchMikeState } from '@/lib/mike';
import { chiuseGiornata, righeDaRisposta, type ChiuseGiornata } from '@/lib/chiuseGiornata';
import { useControlRoom } from '@/components/controlroom/useControlRoom';
import { righeInterruttori } from '@/components/controlroom/righeBot';
import { PannelloBot } from '@/components/controlroom/PannelloBot';
import { PosizioniChiuse } from '@/components/controlroom/PosizioniChiuse';
import type { ComandiInterruttori } from '@/lib/interruttori';

// 15:00 di Roma del 01/10/2026 (ora legale: UTC+2)
const ADESSO = Date.parse('2026-10-01T13:00:00.000Z');
const OGGI = '2026-10-01';

function tradeOmega(over: Partial<OmegaTrade> = {}): OmegaTrade {
    return {
        id: 900, event_id: 'E1', market_id: '1.1', selection_id: 1, side: 'back',
        mode: 'live', price: 2, size: 10, liability: 0, status: 'won', pnl: 1,
        placed_at: '2026-10-01T10:00:00.000Z', settled_at: '2026-10-01T11:50:00.000Z', origin: 'auto',
        ...over,
    } as OmegaTrade;
}
function tradeMike(over: Partial<MikeTrade> = {}): MikeTrade {
    return {
        id: 800, event_id: 'E2', market_id: '1.2', selection_id: 2, side: 'back',
        mode: 'live', price: 2, size: 9, liability: 0, status: 'won', pnl: 0.8,
        placed_at: '2026-10-01T09:00:00.000Z', settled_at: '2026-10-01T10:30:00.000Z', origin: 'auto',
        ...over,
    } as MikeTrade;
}
/** le chiavi del contratto del 01/10, come le aggiunge la lettura del database */
const DEL_GIORNO = { giorno_partita: OGGI, giorno_da: 'partita', in_day: true } as const;

// -- IN MEMORIA (lettura dei 30 s): nessuna chiave del giorno --------------
// 501: partita di IERI sera (22:30 di Roma), regolata alle 00:40 di OGGI
const O501 = tradeOmega({ id: 501, event_id: 'E501', pnl: 4,
    placed_at: '2026-09-30T20:30:00.000Z', settled_at: '2026-09-30T22:40:00.000Z' });
// 502: partita di oggi, gia' confermata dal database
const O502 = tradeOmega({ id: 502, event_id: 'E502', pnl: 1.5 });
// 503: regolata 2 minuti fa, la lettura non la porta ancora: PROVVISORIA, conta oggi
const O503 = tradeOmega({ id: 503, event_id: 'E503', status: 'lost', pnl: -0.5,
    placed_at: '2026-10-01T12:00:00.000Z', settled_at: '2026-10-01T12:58:00.000Z' });
// Mike 7001 + copertura 7002
const M7001 = tradeMike({ id: 7001, event_id: 'E7', pnl: 2.25 });
const M7002 = tradeMike({ id: 7002, event_id: 'E7', side: 'lay', status: 'lost', pnl: -1, closes_trade_id: 7001 } as Partial<MikeTrade>);

// -- LA LETTURA DELLA GIORNATA (stessa per le tre viste) -------------------
// Mike 7010: fuori dalla finestra della memoria, solo nella lettura
const M7010 = tradeMike({ id: 7010, event_id: 'E70', pnl: 0.8 });
function lettura(): ChiuseGiornata {
    const righe = righeDaRisposta({
        omega: [{ ...O502, ...DEL_GIORNO }],
        safe: [],
        mike: [{ ...M7001, ...DEL_GIORNO }, { ...M7002, ...DEL_GIORNO }, { ...M7010, ...DEL_GIORNO }],
        tennis: [],
    });
    return {
        giorno: OGGI, modo: 'live', righe, fonte: 'rpc', avvisi: [], lettoAlle: ADESSO,
        giornoPartita: true, chiestoAlle: ADESSO,
    };
}

// Omega = 502 + 503 = 1,50 - 0,50 = 1,00 (la 501 e' di IERI)
// Mike  = 7001 + 7002 + 7010 = 2,25 - 1,00 + 0,80 = 2,05
const ATTESO_OMEGA = 1;
const ATTESO_MIKE = 2.05;
const ATTESO_TOTALE = 3.05;

function comandiFinti(): ComandiInterruttori {
    return {
        accendi: vi.fn(async () => {}), spegni: vi.fn(async () => {}),
        cambiaModalita: vi.fn(async () => {}), cambiaImporto: vi.fn(async () => {}),
        fermaBot: vi.fn(async () => {}), scriviAccensioni: vi.fn(async () => {}),
        cambiaModalitaServizio: vi.fn(async () => {}),
    };
}

beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(ADESSO);
    vi.mocked(fetchOmegaTrades).mockResolvedValue([O501, O502, O503]);
    vi.mocked(fetchMikeState).mockResolvedValue({
        control: null, events: [], trades: [M7001, M7002], activity: [], aggregates: null,
        requests: [], day_start: null, day_by: null,
    } as never);
    vi.mocked(chiuseGiornata).mockImplementation(async () => lettura());
});
afterEach(() => {
    vi.useRealTimers();
    vi.mocked(chiuseGiornata).mockReset();
});

async function modello() {
    const { result } = renderHook(() => useControlRoom());
    await waitFor(() => expect(result.current.caricamento).toBe(false));
    await waitFor(() => {
        const o = result.current.bots.find((b) => b.bot === 'omega');
        expect(o?.pnlOggi).toBe(ATTESO_OMEGA);
    });
    return result;
}

describe('punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA)', () => {
    it('la plancia legge la giornata di oggi in SOLDI VERI con la lettura della scheda', async () => {
        await modello();
        expect(chiuseGiornata).toHaveBeenCalled();
        for (const c of vi.mocked(chiuseGiornata).mock.calls) {
            expect(c[0]).toBe(OGGI);
            expect(c[1]).toBe('live');
        }
    });

    it('per bot: Omega 1,00 (la partita di IERI regolata stanotte NON e\' di oggi), Mike 2,05', async () => {
        const vm = (await modello()).current;
        const omega = vm.bots.find((b) => b.bot === 'omega')!;
        const mike = vm.bots.find((b) => b.bot === 'mike')!;
        expect(omega.pnlOggi).toBe(ATTESO_OMEGA);
        expect(mike.pnlOggi).toBe(ATTESO_MIKE);
        expect(omega.fonteOggiLive?.fonte).toBe('bot');
        // la 503 non ha ancora il giorno del database: contata, ma DICHIARATA
        expect(omega.fonteOggiLive?.nota ?? '').toContain('1 chiusa senza il giorno della partita');
        expect(omega.fonteOggiLive?.nota ?? '').toContain('regolamento');
        expect(mike.fonteOggiLive?.nota ?? '').not.toContain('senza il giorno della partita');
        // la posizione di ieri e' fuori dal giorno anche per il contatore
        const p501 = vm.chiuse.find((p) => p.bot === 'omega' && p.id === 501)!;
        expect(vm.chiuseEscluse?.has(p501)).toBe(true);
    });

    it('le TRE viste con gli stessi finti: plancia = riassunto del gruppo = scheda Chiuse', async () => {
        const vm = (await modello()).current;
        // 1) la plancia, per bot
        const omega = vm.bots.find((b) => b.bot === 'omega')!;
        const mike = vm.bots.find((b) => b.bot === 'mike')!;
        const plancia = Math.round(((omega.pnlOggi ?? 0) + (mike.pnlOggi ?? 0)) * 100) / 100;
        expect(plancia).toBe(ATTESO_TOTALE);

        // 2) il riassunto del gruppo BOT CALCIO (Omega e Mike accesi in LIVE)
        const accesi = vm.bots
            .filter((b) => b.bot === 'omega' || b.bot === 'mike')
            .map((b) => ({ ...b, inCorsa: true, modalita: 'live' as const }));
        const g = render(<PannelloBot righe={righeInterruttori(accesi, 'calcio')} importi={{}} comandi={comandiFinti()} />);
        expect(g.getByTestId('cr-bot-pnl-omega').textContent).toContain('1,00');
        expect(g.getByTestId('cr-bot-pnl-mike').textContent).toContain('2,05');
        expect(g.getByTestId('cr-pannello-bot-gruppo-calcio-oggi-live').textContent).toContain('3,05');
        g.unmount();

        // 3) la scheda Posizioni chiuse di oggi, soldi veri, con la STESSA lettura
        const s = render(<MemoryRouter><PosizioniChiuse righe={vm.righeChiuse} chiuse={vm.chiuse} sport={null}
            giorno={OGGI} leggiGiornata={async () => lettura()} /></MemoryRouter>);
        await waitFor(() => expect(s.getByTestId('cr-chiuse-totale').textContent).toContain('3,05'));
        expect(s.getByTestId('cr-chiuse-totale').textContent).not.toContain('7,05');
    });

    it('senza lettura (database non raggiunto): ripiego al REGOLAMENTO, dichiarato', async () => {
        vi.mocked(chiuseGiornata).mockImplementation(async () => { throw new Error('giu'); });
        const { result } = renderHook(() => useControlRoom());
        await waitFor(() => expect(result.current.caricamento).toBe(false));
        await waitFor(() => expect(chiuseGiornata).toHaveBeenCalled());
        const omega = result.current.bots.find((b) => b.bot === 'omega')!;
        // 501 (regolata oggi) + 502 + 503: il criterio di prima, ma DETTO
        expect(omega.pnlOggi).toBe(5);
        expect(omega.fonteOggiLive?.nota ?? '').toContain('3 chiuse senza il giorno della partita');
    });
});
