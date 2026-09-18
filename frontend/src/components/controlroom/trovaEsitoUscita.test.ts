// ============================================================================
// trovaEsitoUscita.test.ts — IL PONTE proposta → striscia di esito (A1).
//
// Le righe (`RigaOrdine`) portano le IDENTICHE chiavi del vero (v.
// `StrisciaEsitoChiusura.test.tsx`): nessuna chiave inventata.
//
// FALSIFICAZIONE (verificata a mano): togliere `o.id === tradeId` dal
// `.find()` fa sì che una proposta con `trade_id` diverso trovi comunque la
// riga sbagliata — rosso su "chiave composta bot+id"; togliere `!riga.modalita`
// fa passare `modo: null` a `StrisciaEsitoChiusuraProps` (che vuole
// `'paper'|'live'`) — rosso di tipo.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { trovaEsitoUscita, trovaEsitoCashOut } from './trovaEsitoUscita';
import { certezzaChiusura } from '@/lib/certezzaChiusura';
import type { RigaOrdine } from '@/lib/statoOrdine';
import type { OperazionePartita } from './useControlRoom';

function ordine(over: Partial<RigaOrdine> = {}): RigaOrdine {
    return {
        status: 'open', side: 'back', price: 2.0, size: 10,
        size_requested: 10, size_matched: 10, size_remaining: 0,
        avg_price_matched: 2.0, betfair_updated_at: '2026-09-18T10:00:00.000Z',
        meta: null,
        ...over,
    };
}

function operazione(over: Partial<OperazionePartita> = {}): OperazionePartita {
    return {
        bot: 'safe', id: 42, selezione: 'Juventus', lato: 'back', prezzo: 2.0,
        size: 10, stato: 'open', pnl: null, modalita: 'live',
        at: '2026-09-18T10:00:00.000Z', quale: 'base',
        ordine: ordine(),
        dettaglio: null, marketId: null, selectionId: null, liability: null,
        vivo: null, etaQuoteS: null, chiusura: null, chiusureOrdini: [],
        ...over,
    };
}

describe('trovaEsitoUscita: chiave composta bot+id', () => {
    it('apertura trovata con chiusura abbinata in PARTE → certezzaChiusura dice PARZIALE col residuo', () => {
        const gambaAbbinataMeta = ordine({
            side: 'lay', size: 5, size_requested: 5, size_matched: 5, size_remaining: 0,
            avg_price_matched: 2.0,
        });
        const riga = operazione({ id: 7, chiusureOrdini: [gambaAbbinataMeta] });
        const esito = trovaEsitoUscita([riga], 'safe', 7);
        expect(esito).toBeDefined();
        const r = certezzaChiusura({
            apertura: esito!.apertura!, chiusure: esito!.chiusure,
            regolataDalMercato: esito!.regolataDalMercato ?? false, modo: esito!.modo,
        });
        expect(r.stato).toBe('CHIUSA_PARZIALE');
        expect(r.esposizione.stake).toBeGreaterThan(0);
    });

    it('apertura NON trovata (id diverso) → undefined: nessuna striscia', () => {
        const riga = operazione({ id: 7 });
        expect(trovaEsitoUscita([riga], 'safe', 999)).toBeUndefined();
        // stesso id ma bot diverso: non deve confondersi (id di tabelle diverse collidono)
        expect(trovaEsitoUscita([riga], 'omega', 7)).toBeUndefined();
    });

    it('nessun elenco di operazioni per la partita → undefined', () => {
        expect(trovaEsitoUscita(undefined, 'safe', 7)).toBeUndefined();
    });

    it('modalita non dichiarata → undefined (mai indovinare paper/live)', () => {
        const riga = operazione({ id: 7, modalita: null, chiusureOrdini: [ordine()] });
        expect(trovaEsitoUscita([riga], 'safe', 7)).toBeUndefined();
    });
});

describe('trovaEsitoCashOut: la gamba più recente fra le operazioni del bot', () => {
    it('sceglie l\'operazione con la chiusura più recente e ignora chi non ha tentato nulla', () => {
        const vecchia = operazione({
            id: 1, at: '2026-09-18T09:00:00.000Z',
            chiusureOrdini: [ordine({ betfair_updated_at: '2026-09-18T09:05:00.000Z' })],
        });
        const recente = operazione({
            id: 2, at: '2026-09-18T10:00:00.000Z',
            chiusureOrdini: [ordine({ betfair_updated_at: '2026-09-18T10:30:00.000Z' })],
        });
        const senzaChiusura = operazione({ id: 3, chiusureOrdini: [] });
        const esito = trovaEsitoCashOut([vecchia, recente, senzaChiusura], 'safe');
        expect(esito).toBeDefined();
        expect(esito!.apertura).toBe(recente.ordine);
    });

    it('nessuna operazione con chiusure → undefined', () => {
        expect(trovaEsitoCashOut([operazione({ chiusureOrdini: [] })], 'safe')).toBeUndefined();
    });
});
