// ============================================================================
// ResiduiB17.schede.test.tsx - 25/09 (residui B17), le tre schede che
// restavano a meta':
//  1. CASH OUT GLOBALE: per OGNI ordine generato l'esito d'abbinamento, gambe
//     SOLO dagli id dichiarati dal servizio (`closing_trade_ids`);
//  2. «CHIUDI» DI RIGA e GAMBE DELLA COMBO al prezzo del MS prima del clic,
//     ripiego dichiarato sullo scanner;
//  3. MIKE: gambe dell'approvazione per CHIAVE (`meta.approvazione_id`),
//     correlazione solo come ripiego dichiarato.
// I finti parlano come il vero: righe `safe_strategy_trades`/`mike_trades`
// con le colonne della migrazione del 16/09, righe della coda (`id`/`status`/
// `result`) coi campi del servizio, ladder con la forma di `LiveLadderRow`.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { CashOutPartita } from './CashOutPartita';
import { ChiusuraRigaContext, type ChiusuraRigaApi } from './BottoneChiudiRiga';
import { EsitoAbbinamentoStriscia, righeOrdiniCashOut } from './EsitoAbbinamentoStriscia';
import { RigaOperazione } from './DettaglioRigaView';
import { SchedaPropostaOpportunita } from './SchedaPropostaOpportunita';
import type { EsitoSeguito } from './useSeguiOrdini';
import type { OperazionePartita } from './useControlRoom';
import { richiestaSeguita } from './useSeguiOrdini';
import { applicaBloccoDb, mappaVuota, type MappaRighe } from '@/lib/righeCanale';
import {
    chiaveCashOutPartita, esitoDelClic, type ClicOrdine, type RichiestaSeguita,
} from '@/lib/esitoAbbinamento';
import type { PropostaOpportunita } from '@/lib/safeBot';

const NOW = Date.now();

function mappaCon(bot: 'safe' | 'mike', righe: Record<string, unknown>[]): MappaRighe<unknown> {
    return applicaBloccoDb(mappaVuota<Record<string, unknown>>(), bot, righe, NOW - 1000) as MappaRighe<unknown>;
}

function seguitoDa(clic: ClicOrdine, richiesta: RichiestaSeguita | null, mappa: MappaRighe<unknown>): EsitoSeguito {
    return { clic, richiesta, ...esitoDelClic(clic, richiesta, mappa, NOW) };
}

// ======================================================= 1. cash out globale
function clicCashOut(p: Partial<ClicOrdine> = {}): ClicOrdine {
    return {
        chiave: chiaveCashOutPartita('safe', '35001'), bot: 'safe', tipo: 'chiusura',
        etichetta: 'Safe · cash out globale della partita', requestId: 77,
        tradeIdApertura: null, eventId: '35001', lato: null, prezzoVisto: null, prezzoSegnale: null,
        contesto: null, modo: 'paper', clicMs: NOW - 2000, idsNotiAlClic: [], ruoli: null,
        soloIdDichiarati: true, ...p,
    };
}

// le due gambe di chiusura come le scrive `execution.close_trade` (Safe)
const APERTURE = [
    { id: 901, event_id: '35001', side: 'back', price: 2.4, size: 5, status: 'hedged', mode: 'paper',
        closes_trade_id: null, meta: {} },
    { id: 902, event_id: '35001', side: 'lay', price: 3.0, size: 4, status: 'open', mode: 'paper',
        closes_trade_id: null, meta: {} },
];
const GAMBA_TOTALE = {
    id: 1001, event_id: '35001', side: 'lay', price: 2.3, size: 5, status: 'open', mode: 'paper',
    closes_trade_id: 901, size_requested: 5, size_matched: 5, size_remaining: 0,
    avg_price_matched: 2.3, betfair_updated_at: '2026-09-25T10:00:01Z',
    meta: { cashout: true, closes_trade_id: 901, fill: 'paper_fill:ok' },
};
const GAMBA_PARZIALE = {
    id: 1002, event_id: '35001', side: 'back', price: 3.1, size: 1.5, status: 'pending', mode: 'paper',
    closes_trade_id: 902, size_requested: 4, size_matched: 1.5, size_remaining: 2.5,
    avg_price_matched: 3.1, betfair_updated_at: '2026-09-25T10:00:01Z',
    meta: { cashout: true, closes_trade_id: 902 },
};
// una riga NUOVA del bot sulla stessa partita che il servizio NON ha dichiarato
const ESTRANEA = {
    id: 1003, event_id: '35001', side: 'back', price: 1.5, size: 2, status: 'open', mode: 'paper',
    closes_trade_id: null, size_requested: 2, size_matched: 2, size_remaining: 0,
    avg_price_matched: 1.5, meta: {},
};

function richiestaCashOut(result: Record<string, unknown>): RichiestaSeguita {
    return richiestaSeguita(clicCashOut(), { id: 77, status: 'done', result }, NOW - 500);
}

describe('1. CASH OUT GLOBALE: un esito per ogni ordine dichiarato dal servizio', () => {
    const mappa = mappaCon('safe', [...APERTURE, GAMBA_TOTALE, GAMBA_PARZIALE, ESTRANEA]);
    const risultato = {
        ok: true, event_id: '35001', chiuse: [901, 902], riserve_annullate: [],
        non_chiuse: [{ trade_id: 903, motivo: 'stato hedged' }],
        closing_trade_ids: [1001, 1002],
        gambe: [{ trade_id: 901, closing_trade_id: 1001, ok: true },
            { trade_id: 902, closing_trade_id: 1002, ok: true }],
        message: 'cash out globale: 2 posizioni chiuse, 0 riserve annullate, 1 NON chiuse (vedi dettaglio)',
    };

    it('gambe = SOLO gli id dichiarati (la riga estranea sulla partita non entra)', () => {
        const s = seguitoDa(clicCashOut(), richiestaCashOut(risultato), mappa);
        expect(s.gambe.map((g) => g.id)).toEqual([1001, 1002]);
        expect(s.modoGambe).toBe('id');
        expect(s.esito.fase).toBe('parziale');
        expect(s.esito.terminale).toBe(false);   // la seconda ha ancora 2,50 € sul book
    });

    it('senza id dichiarati NON si indovina nulla dalle righe della partita', () => {
        const s = seguitoDa(clicCashOut(), null, mappa);
        expect(s.gambe).toEqual([]);
        expect(s.modoGambe).toBe('nessuno');
        expect(s.esito.testo).toBe('inviato: in attesa del servizio');
    });

    it('la scheda mostra i due ordini (uno totale, uno parziale) e la posizione non chiusa', () => {
        const s = seguitoDa(clicCashOut(), richiestaCashOut(risultato), mappa);
        const api: ChiusuraRigaApi = {
            chiudi: vi.fn(), stato: () => null,
            esitoOrdine: (k) => (k === chiaveCashOutPartita('safe', '35001') ? s : null),
        };
        render(
            <ChiusuraRigaContext.Provider value={api}>
                <CashOutPartita eventId="35001" modalita="paper" posizioniVive={0}
                    stato={{ chiusa: true, fonte: 'righe', marcatore: null }}
                    onCashOut={vi.fn()} onRiprendi={vi.fn()} compatto />
            </ChiusuraRigaContext.Provider>,
        );
        const righe = screen.getAllByTestId('cr-cashout-partita-ordini-riga');
        expect(righe.map((r) => r.textContent)).toEqual([
            'ordine #1001: ABBINATO TOTALMENTE a prezzo medio 2,30 (Δ vs visto —, vs segnale —), size 5,00 €',
            'ordine #1002: ABBINATO PARZIALMENTE: 1,50 € su 4,00 € a 3,10 (Δ vs visto —, vs segnale —), '
                + 'resto 2,50 € in attesa sul book',
            'posizione #903 NON chiusa: rifiutato: stato hedged',
        ]);
        expect(righe.map((r) => r.getAttribute('data-tono'))).toEqual(['ok', 'parziale', 'ko']);
        // il messaggio complessivo con fonte ed eta' resta sopra
        expect(screen.getByTestId('cr-cashout-partita-ordini-esito-fonte').textContent)
            .toMatch(/^esito: database \(ripiego: lettura del blocco del bot\)/);
    });

    it('un ordine dichiarato ma la cui riga non e\' ancora arrivata: «in attesa della riga»', () => {
        const s = seguitoDa(clicCashOut(), richiestaCashOut(risultato), mappaCon('safe', [GAMBA_TOTALE]));
        expect(righeOrdiniCashOut(s).map((r) => r.testo)).toEqual([
            'ordine #1001: ABBINATO TOTALMENTE a prezzo medio 2,30 (Δ vs visto —, vs segnale —), size 5,00 €',
            'ordine #1002: in attesa della riga dell\'ordine',
            'posizione #903 NON chiusa: rifiutato: stato hedged',
        ]);
    });

    it('nessun ordine partito (tutte rifiutate): esito terminale, non «in attesa» per 3 minuti', () => {
        const r = richiestaCashOut({ ok: true, chiuse: [], closing_trade_ids: [],
            non_chiuse: [{ trade_id: 901, motivo: 'in riconciliazione' }],
            message: 'cash out globale: 0 posizioni chiuse, 0 riserve annullate, 1 NON chiuse (vedi dettaglio)' });
        const s = seguitoDa(clicCashOut(), r, mappa);
        expect(s.esito.terminale).toBe(true);
        expect(s.esito.fase).toBe('rifiutato');
        expect(s.esito.testo).toBe('nessun ordine di chiusura partito: cash out globale: 0 posizioni chiuse, '
            + '0 riserve annullate, 1 NON chiuse (vedi dettaglio)');
    });

    it('senza il contesto della Control Room non si monta nessun dettaglio', () => {
        render(<CashOutPartita eventId="35001" modalita="paper" posizioniVive={1}
            stato={{ chiusa: false, fonte: null, marcatore: null }} onCashOut={vi.fn()} onRiprendi={vi.fn()} />);
        expect(screen.queryByTestId('cr-cashout-partita-ordini')).toBeNull();
    });
});

// ============================================ 2a. «Chiudi» di riga al ms
function sorgenteFinta(fonte: 'canale' | 'db' = 'canale') {
    const cbs = new Map<string, (row: unknown) => void>();
    const src = {
        fetch: async () => null,
        subscribe: (mid: string, cb: (row: unknown) => void) => {
            cbs.set(mid, cb);
            return () => { cbs.delete(mid); };
        },
        fonte: () => fonte,
    };
    const spingi = (mid: string, sid: number, back: number, lay: number, ms = Date.now()) => act(() => {
        cbs.get(mid)?.({
            event_id: '35001', market_id: mid, market_type: 'MATCH_ODDS', market_name: 'MO',
            status: 'OPEN', updated_at: new Date(ms).toISOString(),
            ladder: { updated_ms: ms, selections: [
                { selection_id: sid, name: 'X', ltp: back, tv: 0, back: [[back, 80]], lay: [[lay, 60]],
                    trd: [], wom: { back_pct: 50, lay_pct: 50 } },
            ] },
        });
    });
    return { sorgente: () => src as never, spingi, iscritti: () => [...cbs.keys()] };
}

function rigaOp(): OperazionePartita {
    // back 10 € a 2,00 di Safe: +10 / -10, si chiude BANCANDO
    return {
        bot: 'safe', id: 901, selezione: 'Home', lato: 'back', prezzo: 2.0,
        size: 10, stato: 'open', pnl: null, modalita: 'paper',
        at: '2026-09-25T10:00:00.000Z', quale: null,
        ordine: { status: 'open', side: 'back', price: 2.0, size: 10, size_requested: 10, size_matched: 10,
            size_remaining: 0, avg_price_matched: 2.0, betfair_updated_at: null, meta: null },
        dettaglio: null, marketId: '1.23', selectionId: 7, liability: null,
        vivo: null, etaQuoteS: 12, chiusureOrdini: [], eventId: '35001', chiudeId: null,
        chiusura: {
            lato: 'lay', prezzo: 1.9, abbinabile: 50, bloccabile: 0.52,
            alMs: {
                win: 10, lose: -10, marketId: '1.23', selectionId: 7, sport: 'calcio',
                istanteScannerMs: Date.now() - 12_000,
                scanner: { back: 1.88, backSize: 30, lay: 1.9, laySize: 50 },
            },
        },
    };
}

describe('2a. «Chiudi» di riga: prezzo e P&L al ms prima del clic', () => {
    it('col ladder al ms: prezzo, P&L ricalcolato al tick, eta\' e fonte', () => {
        const f = sorgenteFinta();
        const chiudi = vi.fn(async () => undefined);
        render(
            <ChiusuraRigaContext.Provider value={{ chiudi, stato: () => null, sorgenteLadder: f.sorgente }}>
                <RigaOperazione o={rigaOp()} />
            </ChiusuraRigaContext.Provider>,
        );
        expect(f.iscritti()).toEqual(['1.23']);
        f.spingi('1.23', 7, 1.79, 1.8, Date.now() - 400);
        expect(screen.getByTestId('cr-op-chiudo-ora-prezzo').textContent).toBe('1,80');
        expect(screen.getByTestId('cr-op-chiudo-ora-pnl').textContent).toBe('+1,11 €');
        expect(screen.getByTestId('cr-op-chiudo-ora-fonte').textContent).toMatch(/^ladder al ms, 0,\d s fa$/);
        expect(screen.getByTestId('cr-op-chiudo-ora').getAttribute('data-fonte')).toBe('canale');
        // un tick dopo il P&L si ricalcola
        f.spingi('1.23', 7, 2.18, 2.2);
        expect(screen.getByTestId('cr-op-chiudo-ora-pnl').textContent).toBe('−0,91 €');
        // al clic parte (solo alla scheda) il prezzo a video col suo contesto
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        expect(chiudi).toHaveBeenCalledTimes(1);
        const riga = (chiudi.mock.calls[0] as unknown[])[0] as Record<string, unknown>;
        expect(riga.prezzoVisto).toBe(2.2);
        expect(riga.contestoVisto).toMatchObject({ fonte: 'canale', prezzo_vivo_assente: false });
    });

    it('mercato non portato dal canale: ripiego DICHIARATO sul prezzo dello scanner', () => {
        const f = sorgenteFinta();
        render(
            <ChiusuraRigaContext.Provider value={{ chiudi: vi.fn(), stato: () => null, sorgenteLadder: f.sorgente }}>
                <RigaOperazione o={rigaOp()} />
            </ChiusuraRigaContext.Provider>,
        );
        expect(screen.getByTestId('cr-op-chiudo-ora-prezzo').textContent).toBe('1,90');
        // P&L ricalcolato allo stesso prezzo con la stessa matematica
        expect(screen.getByTestId('cr-op-chiudo-ora-pnl').textContent).toBe('+0,52 €');
        expect(screen.getByTestId('cr-op-chiudo-ora-fonte').textContent)
            .toBe('prezzo dello scanner, 12 s fa (il canale non porta questo mercato)');
        expect(screen.getByTestId('cr-op-chiudo-ora').getAttribute('data-fonte')).toBe('scanner');
    });

    it('il payload della richiesta di chiusura NON cambia (il prezzo visto resta alla scheda)', async () => {
        const mod = await import('./chiudiRiga');
        const invio = vi.spyOn(mod.INVIO, 'safe').mockResolvedValue(55);
        await mod.inviaChiusura({
            bot: 'safe', id: 901, eventId: '35001', modalita: 'paper', stato: 'open',
            prezzoVisto: 2.2, contestoVisto: { eta_ms: 10, fonte: 'canale', prezzo_vivo_assente: false, clic_ms: 1 },
        });
        expect(invio).toHaveBeenCalledTimes(1);
        invio.mockRestore();
        // il payload lo costruisce `INVIO.safe` campo per campo: la fonte lo
        // dimostra senza rete (nessuna chiave del prezzo visto)
        const src = mod.INVIO.safe.toString();
        expect(src).not.toMatch(/prezzoVisto|contestoVisto/);
    });
});

// ================================================ 2b. combo con 3 gambe
function propostaCombo3(): PropostaOpportunita {
    return {
        id: 88, kind: 'place', status: 'proposed',
        created_at: '2026-09-25T21:00:00Z', updated_at: '2026-09-25T21:00:00Z',
        payload: {
            opp_key: '35001|combo:cB', strategy: 'model', kind: 'combo',
            event_id: '35001', event_name: 'Roma v Lazio', sport: 'calcio',
            combo_id: 'cB', mode: 'paper', minute: 40, score: '1-0', signal_key: 'combo:cB',
            size: 10, liability: 10, ev: 0.05, confidence: 0.85, edge: 0.05,
            rationale: 'dutching', p_model: null, p_implied: null,
            decided_at: '2026-09-25T21:00:00Z', proposed_at: '2026-09-25T21:00:05Z',
            valutazione: { valida: true, causa: null, motivi: [] },
            legs: [
                { market_id: '1.10', market_type: 'MATCH_ODDS', selection_id: 1,
                    selection_name: 'Roma', side: 'back', price: 2.0, size: 4, liability: 4 },
                { market_id: '1.10', market_type: 'MATCH_ODDS', selection_id: 2,
                    selection_name: 'Lazio', side: 'back', price: 3.0, size: 3, liability: 3 },
                { market_id: '1.20', market_type: 'OVER_UNDER_25', selection_id: 3,
                    selection_name: 'Over 2.5', side: 'lay', price: 5.0, size: 3, liability: 12 },
            ],
        } as unknown as PropostaOpportunita['payload'],
    };
}

describe('2b. combo a 3 gambe: prezzi al ms per gamba, EV e semaforo ricalcolati', () => {
    function f3() {
        const cbs = new Map<string, (row: unknown) => void>();
        const src = {
            fetch: async () => null,
            subscribe: (mid: string, cb: (row: unknown) => void) => {
                cbs.set(mid, cb);
                return () => { cbs.delete(mid); };
            },
            fonte: () => 'canale' as const,
        };
        const spingiMO = (roma: number, lazio: number) => act(() => {
            const ms = Date.now();
            cbs.get('1.10')?.({
                event_id: '35001', market_id: '1.10', market_type: 'MATCH_ODDS', market_name: 'MO',
                status: 'OPEN', updated_at: new Date(ms).toISOString(),
                ladder: { updated_ms: ms, selections: [
                    { selection_id: 1, name: 'Roma', ltp: roma, tv: 0, back: [[roma, 50]], lay: [[roma + 0.02, 50]],
                        trd: [], wom: { back_pct: 50, lay_pct: 50 } },
                    { selection_id: 2, name: 'Lazio', ltp: lazio, tv: 0, back: [[lazio, 50]], lay: [[lazio + 0.05, 50]],
                        trd: [], wom: { back_pct: 50, lay_pct: 50 } },
                ] },
            });
        });
        return { sorgente: () => src as never, spingiMO, iscritti: () => [...cbs.keys()].sort() };
    }

    it('una sottoscrizione per mercato; gamba 3 non portata dal canale -> scanner dichiarato', () => {
        const f = f3();
        render(<SchedaPropostaOpportunita proposta={propostaCombo3()} sorgenteLadder={f.sorgente}
            prezziViviGambe={{ 0: 2.0, 1: 3.0, 2: 5.0 }} etaQuoteS={8} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        expect(f.iscritti()).toEqual(['1.10', '1.20']);
        f.spingiMO(1.9, 3.1);
        const vivi = screen.getAllByTestId('cr-opp-combo-gamba-vivo').map((e) => e.textContent);
        expect(vivi).toEqual(['1,90', '3,10', '5,00']);
        const fonti = screen.getAllByTestId('cr-opp-combo-gamba-fonte');
        expect(fonti.map((e) => e.getAttribute('data-fonte'))).toEqual(['canale', 'canale', 'scanner']);
        expect(fonti[2].textContent).toMatch(/feed scanner \(mercato non seguito dal runner\)$/);
        expect(screen.getAllByTestId('cr-opp-combo-gamba-tick').map((e) => e.textContent))
            .toEqual([' (-10 tick contro)', ' (+2 tick a favore)']);
        // EV: 0,05 - 4 x 0,10 / 10 = 0,01 (limite inferiore) -> QUASI
        expect(screen.getByTestId('cr-opp-ev').textContent).toBe('0,010 (proposta 0,050)');
        expect(screen.getByTestId('cr-opp-semaforo').getAttribute('data-semaforo')).toBe('QUASI');
        expect(screen.getByTestId('cr-opp-avviso').textContent).toContain(
            'combinazione al prezzo di adesso: profitto bloccato almeno 0,010 per euro (proposta 0,050)');
    });

    it('PIAZZA manda i prezzi A VIDEO di ogni gamba (al ms), con la fonte peggiore', async () => {
        const f = f3();
        const onPiazza = vi.fn().mockResolvedValue(undefined);
        render(<SchedaPropostaOpportunita proposta={propostaCombo3()} sorgenteLadder={f.sorgente}
            prezziViviGambe={{ 0: 2.0, 1: 3.0, 2: 5.0 }} etaQuoteS={8} onPiazza={onPiazza} onRifiuta={vi.fn()} />);
        f.spingiMO(2.02, 3.05);
        expect(screen.getByTestId('cr-opp-semaforo').getAttribute('data-semaforo')).toBe('SI');
        fireEvent.click(screen.getByTestId('cr-opp-piazza'));
        await waitFor(() => expect(onPiazza).toHaveBeenCalled());
        const [id, prezzo, gambe, , contesto] = onPiazza.mock.calls[0];
        expect([id, prezzo, gambe]).toEqual([88, undefined, { 0: 2.02, 1: 3.05, 2: 5.0 }]);
        expect(contesto).toMatchObject({ fonte: 'scanner', prezzo_vivo_assente: false });
    });

    it('una lay salita oltre il margine: NO', () => {
        const f = f3();
        render(<SchedaPropostaOpportunita proposta={propostaCombo3()} sorgenteLadder={f.sorgente}
            prezziViviGambe={{ 0: 2.0, 1: 3.0, 2: 5.2 }} etaQuoteS={8} onPiazza={vi.fn()} onRifiuta={vi.fn()} />);
        f.spingiMO(2.0, 3.0);
        expect(screen.getByTestId('cr-opp-semaforo').getAttribute('data-semaforo')).toBe('NO');
        expect(screen.getByTestId('cr-opp-ev').textContent).toBe('-0,010 (proposta 0,050)');
    });
});

// ======================================== 3. Mike: chiave vs correlazione
function clicMike(p: Partial<ClicOrdine> = {}): ClicOrdine {
    return {
        chiave: 'mike:uscita:E1:green_pre|c0', bot: 'mike', tipo: 'chiusura',
        etichetta: 'Mike · uscita green-up pre-partita', requestId: 321, tradeIdApertura: null,
        eventId: 'E1', lato: 'lay', prezzoVisto: 1.48, prezzoSegnale: 1.48, contesto: null,
        modo: 'paper', clicMs: NOW - 3000, idsNotiAlClic: [500], ruoli: null, ...p,
    };
}

const MIKE_INGRESSO = { id: 500, event_id: 'E1', role: 'under_entry', side: 'back', price: 1.5, size: 10,
    status: 'open', mode: 'paper', size_requested: 10, size_matched: 10, size_remaining: 0,
    avg_price_matched: 1.5, meta: { phase: 'open' } };
const MIKE_GREEN = { id: 501, event_id: 'E1', role: 'under_green', side: 'lay', price: 1.48, size: 10.14,
    status: 'open', mode: 'paper', size_requested: 10.14, size_matched: 10.14, size_remaining: 0,
    avg_price_matched: 1.48, closes_trade_id: 500,
    meta: { phase: 'open', approvazione_id: 321 } };
// una PROTEZIONE nata nello stesso istante, senza la chiave
const MIKE_PROTEZIONE = { id: 502, event_id: 'E1', role: 'over_cover', side: 'back', price: 9.0, size: 1,
    status: 'open', mode: 'paper', size_requested: 1, size_matched: 1, size_remaining: 0,
    avg_price_matched: 9.0, meta: { phase: 'open' } };

describe('3. Mike: le gambe dell\'approvazione per chiave, non per correlazione', () => {
    it('con la chiave: SOLO la gamba approvata, la protezione dello stesso istante resta fuori', () => {
        const s = seguitoDa(clicMike(), null, mappaCon('mike', [MIKE_INGRESSO, MIKE_GREEN, MIKE_PROTEZIONE]));
        expect(s.gambe.map((g) => g.id)).toEqual([501]);
        expect(s.modoGambe).toBe('chiave');
        render(<EsitoAbbinamentoStriscia seguito={s} testId="t" />);
        expect(screen.getByTestId('t-testo').textContent).toBe(
            'ABBINATO TOTALMENTE a prezzo medio 1,48 (Δ vs visto 0 tick, vs segnale 0 tick), size 10,14 €');
        expect(screen.getByTestId('t-modo').textContent)
            .toBe('gambe: ordini con la chiave dell\'approvazione, scritta dal servizio sulla riga');
    });

    it('senza chiave sulle righe (servizio di prima): correlazione, DICHIARATA come ripiego', () => {
        const green = { ...MIKE_GREEN, meta: { phase: 'open' } };
        const s = seguitoDa(clicMike(), null, mappaCon('mike', [MIKE_INGRESSO, green, MIKE_PROTEZIONE]));
        expect(s.gambe.map((g) => g.id).sort()).toEqual([501, 502]);
        expect(s.modoGambe).toBe('correlazione');
        render(<EsitoAbbinamentoStriscia seguito={s} testId="t" />);
        expect(screen.getByTestId('t-modo').textContent).toBe('gambe: RIPIEGO: righe nuove del bot sulla partita '
            + 'dopo il clic (nessuna riga porta la chiave della richiesta)');
        expect(screen.getByTestId('t-modo').getAttribute('data-modo')).toBe('correlazione');
    });

    it('la chiave di un\'ALTRA approvazione non entra nemmeno nel ripiego', () => {
        const altra = { ...MIKE_GREEN, meta: { phase: 'open', approvazione_id: 999 } };
        const s = seguitoDa(clicMike(), null, mappaCon('mike', [MIKE_INGRESSO, altra, MIKE_PROTEZIONE]));
        expect(s.gambe.map((g) => g.id)).toEqual([502]);
        expect(s.modoGambe).toBe('correlazione');
    });
});
