// ============================================================================
// statoOrdine.test.ts — C.12b: LA CONSAPEVOLEZZA DELL'ORDINE, riga per riga.
//
// Le righe qui sotto sono costruite con le colonne VERE della migrazione
// `migrations/trades_consapevolezza_ordine_2026-09-16.sql` e con i `meta` che
// i servizi scrivono davvero (`omega_service.py:1527,1654-1658`,
// `safe_strategy/execution.py:407,493-503,614-620`, `mike/service.py:1166-1170`).
// Regola del 15/09: un finto deve avere le IDENTICHE chiavi del vero.
//
// Le tre situazioni che contano:
//   1. migrazione APPLICATA  -> tutti i numeri, fonte 'colonna';
//   2. migrazione NON applicata ma note nel meta -> numeri con fonte 'nota';
//   3. niente di niente -> «—» ovunque, MAI «0,00 €».
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    statoOrdine, ordineAppoggiato, etaBetfairSec, valoreMoney, valoreOdds,
    statoOrdineTesto, statoOrdineTitolo,
} from './statoOrdine';

// --------------------------------------------------------------------------
// 1. COLONNE NUOVE (migrazione applicata): tutti i numeri, nessuna deduzione
// --------------------------------------------------------------------------
describe('riga con le colonne nuove — tutti i numeri, fonte dichiarata', () => {
    /** parziale reale: 5,00 chiesti, 2,00 abbinati a 2,38, 3,00 ancora vivi */
    const parziale = {
        status: 'pending', side: 'lay', price: 2.4, size: 2,
        size_requested: 5, size_matched: 2, size_remaining: 3,
        avg_price_matched: 2.38,
        betfair_updated_at: '2026-09-16T10:00:00.000Z',
        meta: null,
    };

    it('chiesto, abbinato, residuo e prezzo medio arrivano dalle COLONNE', () => {
        const s = statoOrdine(parziale);
        expect(s.chiesto).toEqual({ valore: 5, fonte: 'colonna' });
        expect(s.abbinato).toEqual({ valore: 2, fonte: 'colonna' });
        expect(s.residuo).toEqual({ valore: 3, fonte: 'colonna' });
        expect(s.prezzoMedio).toEqual({ valore: 2.38, fonte: 'colonna' });
        expect(s.dallaNota).toBe(false);
    });

    it('abbinato + residuo vivo = PARZIALE, non «aperto»', () => {
        expect(statoOrdine(parziale).esito).toBe('parziale');
        expect(statoOrdine(parziale).meta.label).toBe('ABBINATO IN PARTE');
    });

    it('il prezzo medio NON e mai il prezzo chiesto travestito', () => {
        const senzaMedio = { ...parziale, avg_price_matched: null };
        const s = statoOrdine(senzaMedio);
        expect(s.prezzoMedio.valore).toBeNull();
        expect(valoreOdds(s.prezzoMedio)).toBe('—');
        // il prezzo CHIESTO resta leggibile: sono due numeri, non uno
        expect(s.prezzoChiesto.valore).toBe(2.4);
    });

    it('«quando l ho saputo da Betfair» in secondi', () => {
        const s = statoOrdine(parziale);
        const now = Date.parse('2026-09-16T10:02:00.000Z');
        expect(etaBetfairSec(s, now)).toBe(120);
    });

    it('abbinato intero e residuo zero = ABBINATO', () => {
        const s = statoOrdine({ ...parziale, size_matched: 5, size_remaining: 0 });
        expect(s.esito).toBe('abbinato');
    });
});

// --------------------------------------------------------------------------
// 2. NIENTE COLONNE, SOLO NOTE: i numeri ci sono ma sono un ripiego DICHIARATO
// --------------------------------------------------------------------------
describe('riga senza colonne ma con meta — numeri col badge «dalla nota»', () => {
    /** Omega: `requested_size` + `size_remaining` + `betfair_updated_at` nel meta
     *  (omega_service.py:1527, 1654-1658) */
    const omega = {
        status: 'open', side: 'lay', price: 12.5, size: 4.2,
        meta: {
            order_status: 'EXECUTION_COMPLETE',
            requested_size: 6,
            size_remaining: 1.8,
            betfair_updated_at: '2026-09-16T09:59:30.000Z',
        },
    };

    /** Safe: la catena dei tempi di `execution.place` (execution.py:614-620) */
    const safe = {
        status: 'open', side: 'back', price: 3.05, size: 0.8,
        meta: {
            fill: 'live_submin:EXECUTION_COMPLETE',
            size_capped_from: 2,
            esecuzione: {
                t4_inviato: 1, t5_risposta: 2, betfair_ms: 1,
                price_richiesto: 3.1, price_medio: 3.05, scorrimento_tick: -1,
                percorso: 'submin',
                size_richiesta: 2, size_abbinata: 0.8, size_residua: 1.2,
            },
        },
    };

    it('Omega: chiesto e residuo dal meta, dichiarati come nota', () => {
        const s = statoOrdine(omega);
        expect(s.chiesto).toEqual({ valore: 6, fonte: 'nota' });
        expect(s.residuo).toEqual({ valore: 1.8, fonte: 'nota' });
        expect(s.aggiornatoDa).toBe('nota');
        expect(s.dallaNota).toBe(true);
    });

    it('Safe: chiesto/abbinato/residuo/prezzo medio/scorrimento dalla catena dei tempi', () => {
        const s = statoOrdine(safe);
        expect(s.chiesto).toEqual({ valore: 2, fonte: 'nota' });
        expect(s.abbinato).toEqual({ valore: 0.8, fonte: 'nota' });
        expect(s.residuo).toEqual({ valore: 1.2, fonte: 'nota' });
        expect(s.prezzoMedio).toEqual({ valore: 3.05, fonte: 'nota' });
        // §C.10: `scorrimento_tick` e `price_medio` erano salvati e MAI mostrati
        expect(s.scorrimento).toEqual({ valore: -1, fonte: 'nota' });
        expect(s.prezzoChiesto).toEqual({ valore: 3.1, fonte: 'nota' });
        expect(s.esito).toBe('parziale');
        expect(s.dallaNota).toBe(true);
    });

    it('la colonna VINCE sempre sulla nota (la nota e un ripiego)', () => {
        const s = statoOrdine({ ...safe, size_matched: 0.9 });
        expect(s.abbinato).toEqual({ valore: 0.9, fonte: 'colonna' });
    });
});

// --------------------------------------------------------------------------
// 3. NIENTE DI NIENTE: «—» ovunque, mai uno zero
// --------------------------------------------------------------------------
describe('riga senza colonne e senza meta — «—» ovunque, mai «0,00 €»', () => {
    const nuda = { status: 'pending', side: 'lay', price: 2.2, size: 5, meta: null };

    it('i quattro numeri sono assenti, non zero', () => {
        const s = statoOrdine(nuda);
        for (const v of [s.chiesto, s.abbinato, s.residuo, s.prezzoMedio, s.scorrimento]) {
            expect(v).toEqual({ valore: null, fonte: 'assente' });
        }
        expect(valoreMoney(s.chiesto)).toBe('—');
        expect(valoreMoney(s.abbinato)).toBe('—');
        expect(valoreMoney(s.residuo)).toBe('—');
        // ⚠️ il bug che questo test rende rosso: «0,00 €» al posto di «—»
        expect(valoreMoney(s.abbinato)).not.toBe('0,00 €');
    });

    it('nessun abbinato DEDOTTO da `size` (dopo la conferma size E l abbinato,', () => {
        // ...ma su una riga `pending` non lo e affatto: dedurlo era il reperto n. 5)
        expect(statoOrdine(nuda).abbinato.valore).toBeNull();
    });

    it('nessun residuo DEDOTTO da chiesto - abbinato', () => {
        const s = statoOrdine({ ...nuda, size_requested: 5, size_matched: 2 });
        expect(s.residuo.valore).toBeNull();     // 3 sarebbe un ipotesi, non un fatto
        expect(s.esito).toBe('abbinato');        // abbinato certo, residuo ignoto
    });

    it('senza nulla l esito e dichiarato ignoto, non «non abbinato»', () => {
        const s = statoOrdine(nuda);
        expect(s.esito).toBe('ignoto');
        expect(s.meta.label).toBe('ESITO NON DICHIARATO');
        expect(statoOrdineTesto(s)).toBe('abbinamento non dichiarato dal servizio');
    });

    it('riga nulla/undefined non esplode', () => {
        expect(statoOrdine(null).esito).toBe('ignoto');
        expect(statoOrdine(undefined).chiesto.valore).toBeNull();
    });
});

// --------------------------------------------------------------------------
// 4. APPOGGIATO != APERTO
// --------------------------------------------------------------------------
describe('un ordine APPOGGIATO non e una posizione aperta', () => {
    /** Mike: `_aggiorna_riga_resting` scrive `fill: 'live_resting'` (service.py:1165) */
    const appoggiato = {
        status: 'pending', side: 'lay', price: 2.14, size: 0,
        size_requested: 5, size_matched: 0, size_remaining: 5,
        meta: { phase: 'open', fill: 'live_resting' },
    };

    it('niente abbinato + residuo vivo = APPOGGIATO, con etichetta sua', () => {
        const s = statoOrdine(appoggiato);
        expect(s.esito).toBe('appoggiato');
        expect(s.meta.label).toBe('APPOGGIATA · NON ABBINATA');
        expect(s.meta.label).not.toBe('APERTO');
        expect(ordineAppoggiato(appoggiato)).toBe(true);
    });

    it('anche senza numeri, il marcatore `fill` del servizio basta', () => {
        const soloMarcatore = { status: 'open', meta: { fill: 'paper_resting' } };
        expect(statoOrdine(soloMarcatore).esito).toBe('appoggiato');
        // `live_resting_immediato` NON finisce per 'resting': `isRestingMeta`
        // lo perdeva, qui no (stesso significato, stessa etichetta)
        expect(statoOrdine({ status: 'open', meta: { fill: 'live_resting_immediato' } }).esito)
            .toBe('appoggiato');
    });

    it('appena si abbina qualcosa NON e piu «appoggiato»', () => {
        const s = statoOrdine({ ...appoggiato, size_matched: 5, size_remaining: 0 });
        expect(s.esito).toBe('abbinato');
        expect(ordineAppoggiato({ ...appoggiato, size_matched: 5, size_remaining: 0 })).toBe(false);
    });

    it('una riga REGOLATA non torna «appoggiata»', () => {
        expect(statoOrdine({ ...appoggiato, status: 'won' }).esito).toBe('regolato');
        expect(statoOrdine({ ...appoggiato, status: 'won' }).meta.label).toBe('VINTO');
    });
});

// --------------------------------------------------------------------------
// 5. RIFIUTO CON CODICE, ANNULLO, RICONCILIAZIONE
// --------------------------------------------------------------------------
describe('rifiuto, annullo e riconciliazione hanno parole proprie', () => {
    it('il CODICE di Betfair si vede in chiaro nell etichetta', () => {
        const s = statoOrdine({
            status: 'error', side: 'back', price: 3, size: 0,
            meta: { error_final: true, error_code: 'INSUFFICIENT_FUNDS', cashout: true },
        });
        expect(s.esito).toBe('rifiutato');
        expect(s.errorCode).toBe('INSUFFICIENT_FUNDS');
        expect(s.meta.label).toBe('RIFIUTATO DA BETFAIR: INSUFFICIENT_FUNDS');
    });

    it('il codice si pesca anche dalla nota `live_rifiutato:<CODICE>`', () => {
        // execution.py:562 — `PlaceOutcome(..., f"live_rifiutato:{codice}")`
        const s = statoOrdine({ status: 'error', meta: { fill: 'live_rifiutato:INVALID_PROFIT_RATIO' } });
        expect(s.errorCode).toBe('INVALID_PROFIT_RATIO');
    });

    it('«senza_codice» non e un codice: non si inventa', () => {
        const s = statoOrdine({ status: 'error', meta: { fill: 'live_rifiutato:senza_codice' } });
        expect(s.errorCode).toBeNull();
        expect(s.esito).not.toBe('rifiutato');
    });

    it('un ordine ANNULLATO dal bot lo dice (meta.phase di Mike)', () => {
        const s = statoOrdine({
            status: 'error', size_matched: 0,
            meta: { phase: 'cancelled', reason: 'uscita_non_piu_valida' },
        });
        expect(s.esito).toBe('annullato');
        expect(s.meta.label).toBe('ANNULLATO');
    });

    it('esito IGNOTO: la riga resta in verifica su Betfair', () => {
        // execution.py:225 — `meta.reason = 'place_exception_reconciling'`
        const s = statoOrdine({
            status: 'pending', meta: { reason: 'place_exception_reconciling', reconciling: true },
        });
        expect(s.esito).toBe('riconciliazione');
        expect(s.meta.label).toBe('IN VERIFICA SU BETFAIR');
    });

    it('un esito CERTO batte il rifiuto: una riga regolata resta regolata', () => {
        const s = statoOrdine({ status: 'lost', meta: { error_code: 'BET_TAKEN_OR_LAPSED' } });
        expect(s.esito).toBe('regolato');
    });
});

// --------------------------------------------------------------------------
// 6. TESTO E TOOLTIP: quello che il trader legge davvero
// --------------------------------------------------------------------------
describe('testo compatto e tooltip', () => {
    it('la riga compatta dice i tre numeri, con i formatter unici', () => {
        const s = statoOrdine({
            price: 2.4, size_requested: 5, size_matched: 2, size_remaining: 3,
            avg_price_matched: 2.38, status: 'pending',
        });
        expect(statoOrdineTesto(s))
            .toBe('chiesti 5,00 € @2,40 · abbinati 2,00 € @2,38 · residuo 3,00 €');
    });

    it('il tooltip DICHIARA la provenienza di ogni numero', () => {
        const t = statoOrdineTitolo(statoOrdine({
            status: 'open', meta: { esecuzione: { size_richiesta: 2, size_abbinata: 0.8, size_residua: 1.2 } },
        }));
        expect(t).toContain('chiesto: 2,00 € (dalla nota del servizio)');
        expect(t).toContain('residuo vivo sul book: 1,20 € (dalla nota del servizio)');
        expect(t).toContain('non dichiarato');            // il prezzo medio manca
        expect(t).toContain('almeno un numero viene dalla nota');
    });

    it('il tooltip di una riga nuda non inventa zeri', () => {
        const t = statoOrdineTitolo(statoOrdine({ status: 'pending' }));
        expect(t).toContain('chiesto: — (non dichiarato)');
        expect(t).not.toContain('0,00');
    });
});
