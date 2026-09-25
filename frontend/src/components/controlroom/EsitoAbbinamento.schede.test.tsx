// ============================================================================
// EsitoAbbinamento.schede.test.tsx - B17 (25/09): la scheda SEGUE il suo
// ordine dopo il clic e lo dice con un messaggio.
//
// Qui: il seguito (`useSeguiOrdini`: coda del bot riletta per id, rilettura
// mirata solo mentre il canale tace, stop all'esito terminale), la striscia
// (`EsitoAbbinamentoStriscia`), le colonne che la montano (Opportunita',
// Uscite), il «Chiudi» di riga e la proposta d'uscita di Mike.
//
// I finti parlano come il vero: righe di `safe_strategy_trades` con le colonne
// della migrazione del 16/09, messaggi del canale con la busta vera
// (`fonte`/`_seq`/`_pubblicato_ms`), righe della coda (`id`/`status`/`result`)
// coi campi veri del servizio (`trade_id`, `closing_trade_id`, `message`).
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, renderHook, act, waitFor } from '@testing-library/react';
import { useSeguiOrdini, type EsitoSeguito } from './useSeguiOrdini';
import { EsitoAbbinamentoStriscia } from './EsitoAbbinamentoStriscia';
import { OpportunitaColonna } from './OpportunitaColonna';
import { UsciteColonna } from './UsciteColonna';
import { BottoneChiudiRiga, ChiusuraRigaContext, type ChiusuraRigaApi } from './BottoneChiudiRiga';
import type { useControlRoom } from './useControlRoom';
import {
    applicaBloccoDb, applicaMessaggioCanale, leggiMessaggioRiga, mappaVuota, type MappaRighe,
} from '@/lib/righeCanale';
import { esitoAbbinamento, type ClicOrdine } from '@/lib/esitoAbbinamento';
import type { MikeEvent } from '@/lib/mike';

const requestMike = vi.fn(async () => 321);
vi.mock('@/lib/mike', async (orig) => ({
    ...(await orig() as object),
    requestMike: (...a: unknown[]) => requestMike(...a as []),
}));
import { PropostaUscitaMike } from './PropostaUscitaMike';

type Vm = ReturnType<typeof useControlRoom>;

function clic(p: Partial<ClicOrdine> = {}): ClicOrdine {
    return {
        chiave: 'safe:apertura:56', bot: 'safe', tipo: 'apertura', etichetta: 'Safe · opportunità #56',
        requestId: 56, tradeIdApertura: null, eventId: '35001', lato: 'back',
        prezzoVisto: 2.40, prezzoSegnale: 2.44, contesto: null, modo: 'paper',
        clicMs: Date.now(), idsNotiAlClic: [], ruoli: null, ...p,
    };
}

function rigaSafe(p: Record<string, unknown> = {}): Record<string, unknown> {
    return {
        id: 901, event_id: '35001', market_id: '1.23', selection_id: 7, side: 'back',
        price: 2.40, size: 5, status: 'open', mode: 'paper', placed_at: '2026-09-25T10:00:00Z',
        closes_trade_id: null, size_requested: 5, size_matched: 5, size_remaining: 0,
        avg_price_matched: 2.42, betfair_updated_at: '2026-09-25T10:00:01Z',
        meta: { fill: 'paper_fill:ok', da_proposta: true }, ...p,
    };
}

const vuota = () => mappaVuota<Record<string, unknown>>() as MappaRighe<unknown>;

// ------------------------------------------------------------ il seguito
describe('useSeguiOrdini: dalla coda alla riga, fino all\'esito terminale', () => {
    beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: false }); });
    afterEach(() => { vi.useRealTimers(); });

    it('coda -> id della riga -> rilettura mirata -> ABBINATO; poi si ferma', async () => {
        const leggi = vi.fn(async () => ({ id: 56, status: 'done', result: { ok: true, trade_id: 901, message: 'eseguito' } }));
        const rileggi = vi.fn();
        const now0 = Date.now();
        const { result, rerender } = renderHook(
            ({ mappa, nowMs }) => useSeguiOrdini({ mappa, nowMs, chiediRilettura: rileggi, leggi }),
            { initialProps: { mappa: vuota(), nowMs: now0 } },
        );
        act(() => result.current.segui(clic({ clicMs: now0 })));
        expect(result.current.esiti[0].esito.fase).toBe('inviato');
        await act(async () => { await vi.advanceTimersByTimeAsync(0); });
        expect(leggi).toHaveBeenCalledTimes(1);
        // la coda dice «eseguita, trade 901»; la riga non c'e' ancora
        expect(result.current.esiti[0].esito.fase).toBe('in_corso');
        expect(rileggi).toHaveBeenCalledWith('safe');
        // arriva la riga dal database (rilettura mirata)
        const m = applicaBloccoDb(mappaVuota<Record<string, unknown>>(), 'safe', [rigaSafe()], now0 + 1500) as MappaRighe<unknown>;
        rerender({ mappa: m, nowMs: now0 + 2000 });
        expect(result.current.esiti[0].esito.fase).toBe('totale');
        expect(result.current.esiti[0].esito.testo).toMatch(/^ABBINATO TOTALMENTE a prezzo medio 2,42/);
        // terminale: niente piu' letture ne' riletture
        const letture = leggi.mock.calls.length;
        const riletture = rileggi.mock.calls.length;
        await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
        expect(leggi.mock.calls.length).toBe(letture);
        expect(rileggi.mock.calls.length).toBe(riletture);
    });

    it('col canale del bot fresco NON si chiede la rilettura del blocco', async () => {
        const leggi = vi.fn(async () => ({ id: 56, status: 'done', result: { trade_id: 901 } }));
        const rileggi = vi.fn();
        const now0 = Date.now();
        // riga appoggiata dal database, poi il canale la aggiorna (ancora appoggiata)
        let m = applicaBloccoDb(mappaVuota<Record<string, unknown>>(), 'safe',
            [rigaSafe({ status: 'pending', size_matched: 0, size_remaining: 5, avg_price_matched: 0 })], now0 - 5000);
        const msg = leggiMessaggioRiga({ ...rigaSafe({ status: 'pending', size_matched: 0, size_remaining: 5,
            avg_price_matched: 0 }), fonte: 'canale', _seq: 9, _pubblicato_ms: now0 - 100 });
        m = applicaMessaggioCanale(m, 'safe', msg!, now0);
        const { result } = renderHook(
            ({ mappa, nowMs }) => useSeguiOrdini({ mappa, nowMs, chiediRilettura: rileggi, leggi }),
            { initialProps: { mappa: m as MappaRighe<unknown>, nowMs: now0 } },
        );
        act(() => result.current.segui(clic({ clicMs: now0 })));
        await act(async () => { await vi.advanceTimersByTimeAsync(0); });
        expect(result.current.esiti[0].esito.fase).toBe('accettato');
        expect(result.current.esiti[0].esito.fonte).toMatch(/^canale del bot al ms \(seq 9\)/);
        // al PRIMO giro l'id della riga non era ancora noto (la coda non era
        // letta): una rilettura e' giusta. Dai giri seguenti, col canale che
        // porta la riga fresca, nessuna rilettura del blocco.
        const primo = rileggi.mock.calls.length;
        expect(primo).toBeLessThanOrEqual(1);
        await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
        expect(rileggi.mock.calls.length).toBe(primo);
        expect(leggi).toHaveBeenCalledTimes(1);   // la coda chiusa non si rilegge
    });

    it('la coda rifiuta: messaggio col motivo del servizio, e ci si ferma', async () => {
        const leggi = vi.fn(async () => ({ id: 56, status: 'error', result: {
            error: 'prezzo_visto_fuori_tolleranza', price_visto: 1.3, price_attuale: 1.4,
            message: 'rifiutato: il prezzo si e\' mosso (visto 1,30, adesso 1,40)' } }));
        const { result } = renderHook(() => useSeguiOrdini({
            mappa: vuota(), nowMs: Date.now(), chiediRilettura: vi.fn(), leggi }));
        act(() => result.current.segui(clic()));
        await act(async () => { await vi.advanceTimersByTimeAsync(0); });
        expect(result.current.esiti[0].esito.fase).toBe('rifiutato');
        expect(result.current.esiti[0].esito.testo)
            .toBe('rifiutato: rifiutato: il prezzo si e\' mosso (visto 1,30, adesso 1,40)');
        await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
        expect(leggi).toHaveBeenCalledTimes(1);
    });
});

// ------------------------------------------------------------- la striscia
function seguito(riga: Record<string, unknown> | null, c: Partial<ClicOrdine> = {}): EsitoSeguito {
    const cl = clic(c);
    const gambe = riga ? [{ id: Number(riga.id), riga: riga as never, fonte: 'canale' as const, etaS: 0, seq: 3 }] : [];
    const r = { fase: 'eseguita' as const, motivo: 'eseguito', tradeIds: [901], lettaMs: Date.now() };
    return { clic: cl, gambe, esito: esitoAbbinamento(cl, r, gambe, Date.now()) };
}

describe('EsitoAbbinamentoStriscia', () => {
    it('messaggio, prezzo visto e segnale, fonte; in paper il cartellino', () => {
        render(<EsitoAbbinamentoStriscia seguito={seguito(rigaSafe())} />);
        const s = screen.getByTestId('cr-esito-abbinamento');
        expect(s.getAttribute('data-fase')).toBe('totale');
        expect(screen.getByTestId('cr-esito-abbinamento-testo').textContent).toBe(
            'ABBINATO TOTALMENTE a prezzo medio 2,42 (Δ vs visto +1 tick a favore, vs segnale −1 tick contro), size 5,00 €');
        expect(screen.getByTestId('cr-esito-abbinamento-prezzi').textContent)
            .toBe('visto al clic 2,40segnale 2,44medio abbinato 2,42');
        expect(screen.getByTestId('cr-esito-abbinamento-fonte').textContent).toMatch(/^esito: canale del bot al ms \(seq 3\)/);
        expect(screen.getByTestId('cr-esito-abbinamento-paper')).toBeTruthy();
    });
    it('live: nessun cartellino paper, «soldi veri»', () => {
        render(<EsitoAbbinamentoStriscia seguito={seguito(rigaSafe({ mode: 'live' }), { modo: 'live' })} />);
        expect(screen.queryByTestId('cr-esito-abbinamento-paper')).toBeNull();
        expect(screen.getByTestId('cr-esito-abbinamento').textContent).toContain('soldi veri');
    });
});

// ------------------------------------------------------------- le colonne
function vmCon(esitiOrdini: EsitoSeguito[], over: Partial<Vm> = {}): Vm {
    return {
        bots: [], proposte: [], proposteOmega: [], proposteOpportunita: [],
        piazzaOpportunita: vi.fn(), rifiutaOpportunita: vi.fn(), slippagePct: 2, setSlippagePct: vi.fn(),
        approva: vi.fn(), ignora: vi.fn(), approvaOmega: vi.fn(), ignoraOmega: vi.fn(),
        operazioni: new Map(), feedEtaS: 0, esitiOpportunita: [], esitiOrdini, ...over,
    } as unknown as Vm;
}

describe('le colonne montano l\'esito del clic', () => {
    it('Opportunita\': la striscia sostituisce la riga dell\'esito della richiesta per la stessa proposta', () => {
        const vm = vmCon([seguito(rigaSafe())], {
            esitiOpportunita: [
                { id: 56, stato: 'eseguita', testo: 'eseguito' },
                { id: 57, stato: 'rifiutata', testo: 'rifiutato: x' },
            ],
        } as Partial<Vm>);
        render(<OpportunitaColonna vm={vm} filtroSport={null} sorgenteLadder={null} />);
        expect(screen.getAllByTestId('cr-esito-abbinamento')).toHaveLength(1);
        const vecchie = screen.getAllByTestId('cr-opportunita-esito');
        expect(vecchie).toHaveLength(1);
        expect(vecchie[0].textContent).toContain('#57');
    });
    it('Uscite: solo le chiusure approvate di Safe e Omega', () => {
        const vm = vmCon([
            seguito(null, { chiave: 'omega:chiusura:9', bot: 'omega', tipo: 'chiusura', etichetta: 'Omega · uscita #9' }),
            seguito(null, { chiave: 'safe:chiusura:4', tipo: 'chiusura', etichetta: 'Safe · uscita #4' }),
            seguito(null),   // apertura: non e' un'uscita
            seguito(null, { chiave: 'omega:chiusura-riga:3', bot: 'omega', tipo: 'chiusura' }), // «Chiudi» di riga: sta sulla riga
        ]);
        render(<UsciteColonna vm={vm} filtroSport={null} sorgenteLadder={null} />);
        const s = screen.getAllByTestId('cr-esito-uscita');
        expect(s.map((x) => x.getAttribute('data-chiave'))).toEqual(['omega:chiusura:9', 'safe:chiusura:4']);
    });
});

// ------------------------------------------------------------ il «Chiudi»
describe('«Chiudi» di riga: dopo la richiesta, l\'ordine', () => {
    it('mostra il messaggio dell\'abbinamento della gamba di chiusura', () => {
        const es = seguito(rigaSafe({ id: 950, side: 'lay', closes_trade_id: 901, avg_price_matched: 2.38 }),
            { chiave: 'safe:chiusura-riga:901', tipo: 'chiusura', lato: 'lay', prezzoVisto: 2.38, prezzoSegnale: null });
        const api: ChiusuraRigaApi = {
            chiudi: vi.fn(), stato: () => ({ bot: 'safe', id: 901, requestId: 5, faseRichiesta: 'eseguita',
                richiestaChiusa: true, motivo: null, rigaCambiata: true, inviataMs: Date.now() }),
            esito: (bot, id) => (bot === 'safe' && id === 901 ? es : null),
        };
        render(
            <ChiusuraRigaContext.Provider value={api}>
                <BottoneChiudiRiga riga={{ bot: 'safe', id: 901, eventId: '35001', modalita: 'paper', stato: 'hedged' }} />
            </ChiusuraRigaContext.Provider>,
        );
        const o = screen.getByTestId('cr-op-chiudi-ordine');
        expect(o.getAttribute('data-fase')).toBe('totale');
        expect(o.textContent).toBe('[paper] ABBINATO TOTALMENTE a prezzo medio 2,38 (Δ vs visto 0 tick, vs segnale —), size 5,00 €');
    });
    it('senza la funzione esito (pagine vecchie): nessuna riga in piu\'', () => {
        const api: ChiusuraRigaApi = { chiudi: vi.fn(), stato: () => null };
        render(
            <ChiusuraRigaContext.Provider value={api}>
                <BottoneChiudiRiga riga={{ bot: 'safe', id: 901, eventId: '35001', modalita: 'paper', stato: 'open' }} />
            </ChiusuraRigaContext.Provider>,
        );
        expect(screen.queryByTestId('cr-op-chiudi-ordine')).toBeNull();
    });
});

// ------------------------------------------------ la proposta di Mike
describe('Mike: l\'uscita approvata si segue fino alle gambe', () => {
    const ORA_S = Math.floor(Date.now() / 1000);
    const prop = {
        chiave: 'chiusura|c0', categoria: 'chiusura', ciclo: 0, stato: 'LIVE_COVERED',
        stato_voluto: 'LIVE_CLOSING', motivo: 'profit', close_reason: 'profit',
        ordini: [
            { ruolo: 'under_close', mercato: 'OU35', selezione: 'UNDER', lato: 'lay', prezzo: 1.31, size: 22.9 },
            { ruolo: 'over_close', mercato: 'OU45', selezione: 'OVER', lato: 'lay', prezzo: 12.5, size: 2.56 },
        ],
        bloccabile: 1.31, urgente: false, minuto: 30, gol: 0, decided_at: ORA_S - 5, proposed_at: ORA_S - 5,
    };
    function ev(ctx: Record<string, unknown> | null): MikeEvent {
        return {
            event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
            ko_at: new Date().toISOString(), mode: 'live', markets: {}, state: 'LIVE_COVERED',
            cycle_no: 0, entry_price_initial: 1.5, dossier: null,
            live: { feed_age_s: 2, cashout: { net: 1.28 },
                books: { 'OU35|UNDER': { best_back: 1.30, best_lay: 1.32 } } } as unknown as MikeEvent['live'],
            positions: [], ctx, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
        };
    }
    beforeEach(() => { requestMike.mockClear(); });

    it('al clic: prezzo visto e segnale nel contesto della richiesta, e il seguito coi ruoli proposti', async () => {
        const seguiClic = vi.fn();
        const api: ChiusuraRigaApi = { chiudi: vi.fn(), stato: () => null, seguiClic, esitiOrdini: [] };
        render(
            <ChiusuraRigaContext.Provider value={api}>
                <PropostaUscitaMike ev={ev({ uscita_proposta: prop })} />
            </ChiusuraRigaContext.Provider>,
        );
        fireEvent.click(screen.getByTestId('cr-mike-proposta-approva'));
        await waitFor(() => expect(seguiClic).toHaveBeenCalled());
        const payload = (requestMike.mock.calls[0] as unknown[])[1] as { contesto: Record<string, unknown> };
        expect(payload.contesto).toMatchObject({ prezzo_visto: 1.32, prezzo_segnale: 1.31 });
        expect(seguiClic.mock.calls[0][0]).toMatchObject({
            chiave: 'mike:uscita:E1:chiusura|c0', bot: 'mike', tipo: 'chiusura', requestId: 321,
            eventId: 'E1', lato: 'lay', prezzoVisto: 1.32, prezzoSegnale: 1.31, modo: 'live',
            ruoli: ['under_close', 'over_close'], tradeIdApertura: null,
        });
    });

    it('la proposta consumata dal motore: l\'esito resta a video', () => {
        const es = seguito(null, { chiave: 'mike:uscita:E1:chiusura|c0', bot: 'mike', tipo: 'chiusura', modo: 'live' });
        const api: ChiusuraRigaApi = { chiudi: vi.fn(), stato: () => null, esitiOrdini: [es] };
        render(
            <ChiusuraRigaContext.Provider value={api}>
                <PropostaUscitaMike ev={ev({ uscita_proposta: null })} />
            </ChiusuraRigaContext.Provider>,
        );
        expect(screen.getByTestId('cr-mike-proposta-ordine').getAttribute('data-fase')).toBe('in_corso');
    });
});
