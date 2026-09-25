// ============================================================================
// esitoAbbinamento.test.ts - B17 (25/09): i MESSAGGI dopo il clic, esatti.
//
// I finti parlano come il vero: righe di `safe_strategy_trades`/`omega_trades`
// (colonne della migrazione del 16/09 + `meta` coi nomi scritti da
// `execution.py`), righe di `tennis_live_orders` (nomi dello specchio
// flumine: `average_price_matched`, `updated_at`, stati flumine), messaggi del
// canale del bot con la busta vera (`fonte`, `_seq`, `_pubblicato_ms`),
// `result` della coda coi campi veri (`trade_id`, `trade_ids`,
// `closing_trade_id`).
// ============================================================================
import { describe, expect, it } from 'vitest';
import {
    aggiungiSeguito, candidateDallaMappa, comeRigaOrdine, deltaTick, esitoAbbinamento,
    esitoDelClic, esitoGamba, gambeDelClic, idsDaRisultato, idsNotiSullaPartita,
    MAX_SEGUITI, SCADENZA_SEGUITO_MS, testoDelta,
    type ClicOrdine, type GambaSeguita, type RichiestaSeguita,
} from './esitoAbbinamento';
import { applicaBloccoDb, applicaMessaggioCanale, leggiMessaggioRiga, mappaVuota } from './righeCanale';
import type { RigaOrdine } from './statoOrdine';

const T0 = 1_790_000_000_000;

function clic(p: Partial<ClicOrdine> = {}): ClicOrdine {
    return {
        chiave: 'safe:apertura:56', bot: 'safe', tipo: 'apertura', etichetta: 'Safe · opportunità #56',
        requestId: 56, tradeIdApertura: null, eventId: '35001', lato: 'back',
        prezzoVisto: 2.40, prezzoSegnale: 2.44, contesto: null, modo: 'live',
        clicMs: T0, idsNotiAlClic: [], ruoli: null, ...p,
    };
}

/** riga di `safe_strategy_trades` (chiavi vere) */
function rigaSafe(p: Record<string, unknown> = {}): Record<string, unknown> {
    return {
        id: 901, event_id: '35001', market_id: '1.23', selection_id: 7, side: 'back',
        price: 2.40, size: 5, status: 'open', mode: 'live', placed_at: '2026-09-25T10:00:00Z',
        closes_trade_id: null, size_requested: 5, size_matched: 5, size_remaining: 0,
        avg_price_matched: 2.42, betfair_updated_at: '2026-09-25T10:00:01Z',
        meta: { fill: 'live_rest:EXECUTION_COMPLETE', da_proposta: true, prezzo_segnale: 2.44 },
        ...p,
    };
}

/** riga di `tennis_live_orders` (chiavi vere dello specchio flumine) */
function rigaTennis(p: Record<string, unknown> = {}): Record<string, unknown> {
    return {
        id: 77, source: 'tennis_pro', bet_id: '3401', client_order_ref: 'x', request_id: null,
        mode: 'paper', event_id: '36077210', market_id: '1.9', selection_id: 11, handicap: 0,
        side: 'lay', order_type: 'LIMIT', price: 1.50, size: 4, size_matched: 4, size_remaining: 0,
        size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 1.49,
        status: 'EXECUTION_COMPLETE', persistence: 'LAPSE', placed_at: '2026-09-25T10:00:00Z',
        matched_at: '2026-09-25T10:00:01Z', updated_at: '2026-09-25T10:00:01Z', ...p,
    };
}

function gamba(riga: Record<string, unknown>, p: Partial<GambaSeguita> = {}): GambaSeguita {
    return { id: Number(riga.id), riga: comeRigaOrdine(riga), fonte: 'canale', etaS: 0, seq: 12, ...p };
}

const eseguita = (ids: number[] = [901]): RichiestaSeguita =>
    ({ fase: 'eseguita', motivo: 'eseguito', tradeIds: ids, lettaMs: T0 + 500 });

// ---------------------------------------------------------------- tick
describe('deltaTick / testoDelta (ladder Betfair)', () => {
    it('punta: un medio piu alto del visto e a favore', () => {
        const d = deltaTick(2.40, 2.42, 'back');
        expect(d).toEqual({ tick: 1, aFavore: true });
        expect(testoDelta(d)).toBe('+1 tick a favore');
    });
    it('banca: un medio piu alto del visto e contro', () => {
        expect(testoDelta(deltaTick(2.40, 2.44, 'lay'))).toBe('+2 tick contro');
        expect(testoDelta(deltaTick(1.50, 1.49, 'lay'))).toBe('−1 tick a favore');
    });
    it('attraverso i gradini della ladder (1,99 -> 2,02 = 2 tick)', () => {
        expect(deltaTick(1.99, 2.02, 'back')?.tick).toBe(2);
    });
    it('zero, riferimento assente, medio 0 di Betfair: mai un numero inventato', () => {
        expect(testoDelta(deltaTick(2.4, 2.4, 'back'))).toBe('0 tick');
        expect(deltaTick(null, 2.4, 'back')).toBeNull();
        expect(deltaTick(2.4, 0, 'back')).toBeNull();
        expect(testoDelta(null)).toBe('—');
    });
});

// -------------------------------------------------------- id dal result
describe('idsDaRisultato', () => {
    it('apertura: trade_id e trade_ids (combo)', () => {
        expect(idsDaRisultato({ ok: true, trade_id: 901, status: 'open' }, 'apertura')).toEqual([901]);
        expect(idsDaRisultato({ ok: true, trade_ids: [5, 6], placed_legs: 2 }, 'apertura')).toEqual([5, 6]);
    });
    it('chiusura: SOLO closing_trade_id (trade_id e la posizione chiusa)', () => {
        expect(idsDaRisultato({ ok: true, trade_id: 40, closing_trade_id: 41 }, 'chiusura')).toEqual([41]);
        expect(idsDaRisultato({ ok: true, trade_id: 40 }, 'chiusura')).toEqual([]);
    });
    it('valori sporchi: niente', () => {
        expect(idsDaRisultato(null, 'apertura')).toEqual([]);
        expect(idsDaRisultato({ trade_id: 'x' }, 'apertura')).toEqual([]);
        expect(idsDaRisultato({ trade_id: 0 }, 'apertura')).toEqual([]);
    });
});

// -------------------------------------------------- quali righe
describe('gambeDelClic', () => {
    const cand = [
        { bot: 'safe' as const, id: 901, eventId: '35001', chiudeId: null, ruolo: null },
        { bot: 'safe' as const, id: 902, eventId: '35001', chiudeId: 901, ruolo: null },
        { bot: 'safe' as const, id: 903, eventId: '35001', chiudeId: 901, ruolo: null },
        { bot: 'omega' as const, id: 902, eventId: '35001', chiudeId: 901, ruolo: null },
        { bot: 'mike' as const, id: 10, eventId: '35001', chiudeId: null, ruolo: 'green' },
        { bot: 'mike' as const, id: 11, eventId: '35001', chiudeId: null, ruolo: 'reentry' },
        { bot: 'mike' as const, id: 12, eventId: '35001', chiudeId: null, ruolo: 'green' },
    ];
    it('id dichiarati dal servizio, solo se la riga e nota e dello stesso bot', () => {
        expect(gambeDelClic(clic(), eseguita([901, 999]), cand)).toEqual([901]);
    });
    it('apertura senza id del servizio: nessuna riga (non si indovina)', () => {
        expect(gambeDelClic(clic(), null, cand)).toEqual([]);
        expect(gambeDelClic(clic(), { ...eseguita([]), tradeIds: [] }, cand)).toEqual([]);
    });
    it('chiusura Safe: gambe della posizione nate dopo il clic', () => {
        const c = clic({ tipo: 'chiusura', tradeIdApertura: 901, idsNotiAlClic: [901, 902] });
        expect(gambeDelClic(c, null, cand)).toEqual([903]);
    });
    it('Mike: righe NUOVE sulla partita coi ruoli proposti', () => {
        const c = clic({ bot: 'mike', tipo: 'chiusura', tradeIdApertura: null, ruoli: ['green'], idsNotiAlClic: [10] });
        expect(gambeDelClic(c, null, cand)).toEqual([12]);
    });
});

// ------------------------------------------------ una gamba, i messaggi
describe('esitoAbbinamento: i messaggi esatti', () => {
    it('ABBINATO TOTALMENTE col Δ vs visto e vs segnale', () => {
        const e = esitoAbbinamento(clic(), eseguita(), [gamba(rigaSafe())], T0 + 1000);
        expect(e.fase).toBe('totale');
        expect(e.terminale).toBe(true);
        expect(e.testo).toBe('ABBINATO TOTALMENTE a prezzo medio 2,42 (Δ vs visto +1 tick a favore, '
            + 'vs segnale −1 tick contro), size 5,00 €');
        expect(e.prezzoMedio).toBe(2.42);
        expect(e.abbinato).toBe(5);
    });
    it('ABBINATO PARZIALMENTE con il resto in attesa sul book', () => {
        const r = rigaSafe({ status: 'open', size_matched: 2, size_remaining: 3, avg_price_matched: 2.40 });
        const e = esitoAbbinamento(clic(), eseguita(), [gamba(r)], T0 + 1000);
        expect(e.fase).toBe('parziale');
        expect(e.terminale).toBe(false);
        expect(e.testo).toBe('ABBINATO PARZIALMENTE: 2,00 € su 5,00 € a 2,40 (Δ vs visto 0 tick, '
            + 'vs segnale −2 tick contro), resto 3,00 € in attesa sul book');
    });
    it('ABBINATO PARZIALMENTE con il resto annullato (FOK/place-and-trim)', () => {
        const r = rigaSafe({ size_matched: 2, size_remaining: 0, avg_price_matched: 2.40 });
        const e = esitoAbbinamento(clic(), eseguita(), [gamba(r)], T0 + 1000);
        expect(e.fase).toBe('parziale');
        expect(e.terminale).toBe(true);
        expect(e.testo).toMatch(/^ABBINATO PARZIALMENTE: 2,00 € su 5,00 € a 2,40 .*, resto annullato$/);
    });
    it('accettato da Betfair: sul book, niente abbinato', () => {
        const r = rigaSafe({ status: 'pending', size_matched: 0, size_remaining: 5, avg_price_matched: 0,
            meta: { esecuzione: { price_richiesto: 2.40 } } });
        const e = esitoAbbinamento(clic(), eseguita(), [gamba(r)], T0 + 1000);
        expect(e.fase).toBe('accettato');
        expect(e.testo).toBe('accettato da Betfair a 2,40: in attesa di abbinamento, 5,00 € sul book');
    });
    it('NON abbinato (FOK) paper: il parziale ucciso come in live', () => {
        const r = rigaSafe({ status: 'error', mode: 'paper', size_matched: null, size_remaining: null,
            avg_price_matched: null, meta: { reason: 'paper_fok_parziale:0.43/5.0', error_final: true } });
        const e = esitoAbbinamento(clic({ modo: 'paper' }), eseguita(), [gamba(r)], T0 + 1000);
        expect(e.fase).toBe('non_abbinato');
        expect(e.simulato).toBe(true);
        expect(e.testo).toBe('NON abbinato (FOK): il book non copriva l’intera size, ordine ucciso senza abbinamento');
    });
    it('NON abbinato (FOK) live: `live_not_matched:EXPIRED` NON e un rifiuto', () => {
        const r = rigaSafe({ status: 'error', size_matched: null, size_remaining: null, avg_price_matched: null,
            meta: { reason: 'live_not_matched:EXPIRED' } });
        expect(esitoGamba(comeRigaOrdine(r)).fase).toBe('non_abbinato');
    });
    it('rifiutato da Betfair col codice', () => {
        const r = rigaSafe({ status: 'error', size_matched: null, size_remaining: 0, avg_price_matched: null,
            meta: { reason: 'live_rifiutato:INSUFFICIENT_FUNDS', error_code: 'INSUFFICIENT_FUNDS' } });
        const e = esitoAbbinamento(clic(), eseguita(), [gamba(r)], T0 + 1000);
        expect(e.fase).toBe('rifiutato');
        expect(e.testo).toBe('rifiutato: Betfair: INSUFFICIENT_FUNDS');
    });
    it('in riconciliazione: esito ignoto, NON terminale', () => {
        const r = rigaSafe({ status: 'pending', size_matched: null, size_remaining: null, avg_price_matched: null,
            meta: { phase: 'reserved', reason: 'place_exception_reconciling' } });
        const e = esitoGamba(comeRigaOrdine(r));
        expect(e.terminale).toBe(false);
    });
    it('riga «open» senza numeri: abbinata per il servizio, il medio NON si inventa', () => {
        const r = rigaSafe({ size_requested: null, size_matched: null, size_remaining: null,
            avg_price_matched: null, meta: {} });
        const e = esitoAbbinamento(clic(), eseguita(), [gamba(r)], T0 + 1000);
        expect(e.fase).toBe('totale');
        expect(e.testo).toBe('ABBINATO TOTALMENTE (prezzo medio non dichiarato dal servizio; prezzo della riga 2,40), size 5,00 €');
        expect(e.prezzoMedio).toBeNull();
    });
    it('tennis (specchio flumine): EXECUTION_COMPLETE abbinato = totale col medio vero', () => {
        const c = clic({ bot: 'tennis_pro', tipo: 'chiusura', lato: 'lay', prezzoVisto: 1.50, prezzoSegnale: null, modo: 'paper' });
        const e = esitoAbbinamento(c, null, [gamba(rigaTennis())], T0 + 1000);
        expect(e.testo).toBe('ABBINATO TOTALMENTE a prezzo medio 1,49 (Δ vs visto −1 tick a favore, vs segnale —), size 4,00 €');
    });
    it('tennis: EXECUTION_COMPLETE senza abbinato = NON abbinato (lapsed)', () => {
        const r = rigaTennis({ size_matched: 0, size_remaining: 0, average_price_matched: 0, size_lapsed: 4 });
        const e = esitoGamba(comeRigaOrdine(r));
        expect(e.fase).toBe('non_abbinato');
        expect(e.terminale).toBe(true);
    });
    it('paper e live: STESSO messaggio (cambia solo `simulato`)', () => {
        const live = esitoAbbinamento(clic({ modo: 'live' }), eseguita(), [gamba(rigaSafe())], T0 + 1000);
        const paper = esitoAbbinamento(clic({ modo: 'paper' }), eseguita(), [gamba(rigaSafe({ mode: 'paper' }))], T0 + 1000);
        expect(paper.testo).toBe(live.testo);
        expect([live.simulato, paper.simulato]).toEqual([false, true]);
    });
});

// --------------------------------------------- senza righe: la coda
describe('esitoAbbinamento: prima della riga dell\'ordine', () => {
    it('inviato', () => {
        const e = esitoAbbinamento(clic(), null, [], T0 + 500);
        expect(e.fase).toBe('inviato');
        expect(e.testo).toBe('inviato: in attesa del servizio');
        expect(e.fonte).toBe('coda del bot: non ancora letta');
    });
    it('eseguita dal servizio, riga non ancora arrivata', () => {
        const e = esitoAbbinamento(clic(), eseguita(), [], T0 + 1500);
        expect(e.fase).toBe('in_corso');
        expect(e.testo).toBe('in corso: eseguito · in attesa della riga dell’ordine');
        expect(e.fonte).toBe('coda del bot (riletta ogni 2 s) · 1 s fa');
    });
    it('rifiutata dal servizio: col motivo (i due prezzi della Safe)', () => {
        const r: RichiestaSeguita = { fase: 'rifiutata', tradeIds: [], lettaMs: T0,
            motivo: 'rifiutato: prezzo mosso oltre la tolleranza (visto 1,30, adesso 1,40)' };
        const e = esitoAbbinamento(clic(), r, [], T0 + 1000);
        expect(e.fase).toBe('rifiutato');
        expect(e.testo).toBe('rifiutato: rifiutato: prezzo mosso oltre la tolleranza (visto 1,30, adesso 1,40)');
    });
    it('rifiutata per FOK non abbinato: si dice NON abbinato, non «rifiutato»', () => {
        const r: RichiestaSeguita = { fase: 'rifiutata', tradeIds: [901], lettaMs: T0,
            motivo: 'non eseguito: non eseguito (paper fok parziale:0.43/5.0)' };
        const e = esitoAbbinamento(clic(), r, [], T0 + 1000);
        expect(e.fase).toBe('non_abbinato');
        expect(e.testo).toMatch(/^NON abbinato \(FOK\)/);
    });
    it('scadenza: dopo 3 minuti senza esito finale lo si dice', () => {
        const e = esitoAbbinamento(clic(), null, [], T0 + SCADENZA_SEGUITO_MS);
        expect(e.fase).toBe('ignoto');
        expect(e.terminale).toBe(true);
    });
});

// ------------------------------------------- dalla mappa del canale
describe('esitoDelClic: la riga dal canale del bot (seq) o dal database', () => {
    function mappaCon(riga: Record<string, unknown>, lettoMs: number) {
        return applicaBloccoDb(mappaVuota<Record<string, unknown>>(), 'safe', [riga], lettoMs);
    }
    it('database: fonte dichiarata come ripiego, con l\'eta', () => {
        const m = mappaCon(rigaSafe(), T0);
        const { esito } = esitoDelClic(clic(), eseguita(), m, T0 + 4000);
        expect(esito.fase).toBe('totale');
        expect(esito.fonte).toBe('database (ripiego: lettura del blocco del bot) · 4 s fa');
    });
    it('canale: il messaggio con `_seq` sovrappone la riga e la fonte lo dice', () => {
        const pending = rigaSafe({ status: 'pending', size_matched: 0, size_remaining: 5, avg_price_matched: 0 });
        let m = mappaCon(pending, T0);
        const msg = leggiMessaggioRiga({ ...rigaSafe(), fonte: 'canale', _seq: 44, _pubblicato_ms: T0 + 900 });
        expect(msg).not.toBeNull();
        m = applicaMessaggioCanale(m, 'safe', msg!, T0 + 950);
        const { esito } = esitoDelClic(clic(), eseguita(), m, T0 + 1950);
        expect(esito.fase).toBe('totale');
        expect(esito.fonte).toBe('canale del bot al ms (seq 44) · 1 s fa');
    });
    it('esito Betfair arrivato dal canale ordini del runner: seq e fase del runner', () => {
        const r = rigaSafe({ meta: { canale_ref: 'safe-t901', canale_ack_seq: 3, canale_seq: 7, canale_fase: 'matched' } });
        const { esito } = esitoDelClic(clic(), eseguita(), mappaCon(r, T0), T0);
        expect(esito.fonte).toBe('database (ripiego: lettura del blocco del bot) · 0 s fa'
            + ' · esito Betfair dal canale ordini del runner (seq 7, matched)');
    });
    it('righe note al clic e candidate dalla mappa (tennis: `source` = bot)', () => {
        const m = applicaBloccoDb(mappaVuota<Record<string, unknown>>(), 'tennis_pro', [rigaTennis()], T0);
        expect(candidateDallaMappa(m)).toEqual([
            { bot: 'tennis_pro', id: 77, eventId: '36077210', chiudeId: null, ruolo: null }]);
        expect(idsNotiSullaPartita(m, 'tennis_pro', '36077210')).toEqual([77]);
        expect(idsNotiSullaPartita(m, 'tennis_pro', null)).toEqual([]);
    });
});

describe('piu gambe (combo, Mike)', () => {
    it('una totale e una NON abbinata: fase parziale, una riga per gamba', () => {
        const a = gamba(rigaSafe({ id: 5 }));
        const b = gamba(rigaSafe({ id: 6, status: 'error', size_matched: null, size_remaining: null,
            avg_price_matched: null, meta: { reason: 'paper_fok_parziale:0/5' } }));
        const e = esitoAbbinamento(clic({ prezzoVisto: null }), eseguita([5, 6]), [a, b], T0 + 1000);
        expect(e.fase).toBe('parziale');
        expect(e.righe).toHaveLength(2);
        expect(e.testo.startsWith('2 gambe: gamba 1 ABBINATO TOTALMENTE')).toBe(true);
    });
});

describe('aggiungiSeguito', () => {
    it('in testa, senza doppioni, al massimo MAX_SEGUITI', () => {
        let l: ClicOrdine[] = [];
        for (let i = 0; i < MAX_SEGUITI + 3; i += 1) l = aggiungiSeguito(l, clic({ chiave: `k${i}` }));
        expect(l).toHaveLength(MAX_SEGUITI);
        expect(l[0].chiave).toBe(`k${MAX_SEGUITI + 2}`);
        l = aggiungiSeguito(l, clic({ chiave: 'k5' }));
        expect(l.filter((x) => x.chiave === 'k5')).toHaveLength(1);
        expect(l[0].chiave).toBe('k5');
    });
});

describe('comeRigaOrdine', () => {
    it('tennis: i nomi dello specchio flumine diventano quelli di statoOrdine', () => {
        const r: RigaOrdine = comeRigaOrdine(rigaTennis());
        expect(r.avg_price_matched).toBe(1.49);
        expect(r.betfair_updated_at).toBe('2026-09-25T10:00:01Z');
        expect(r.size_requested).toBe(4);
    });
    it('Safe: le colonne vere restano quelle', () => {
        const r = comeRigaOrdine(rigaSafe());
        expect(r.avg_price_matched).toBe(2.42);
        expect(r.size_requested).toBe(5);
    });
});
