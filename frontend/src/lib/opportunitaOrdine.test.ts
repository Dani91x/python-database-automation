import { describe, it, expect } from 'vitest';
import {
    ordinaOpportunitaStabile, raggruppaPerPartita, organizzaOpportunita, type VoceOrdinabile,
} from './opportunitaOrdine';

function voce(over: Partial<VoceOrdinabile> & { id: number }): VoceOrdinabile {
    return { eventId: null, live: false, creataAlleMs: over.id, ...over };
}

describe('ordinaOpportunitaStabile', () => {
    it('chi scade prima viene prima', () => {
        const out = ordinaOpportunitaStabile([
            voce({ id: 1, scadeAlleMs: 5000 }),
            voce({ id: 2, scadeAlleMs: 1000 }),
        ]);
        expect(out.map((v) => v.id)).toEqual([2, 1]);
    });

    it('senza scadenza, le LIVE vengono prima delle PAPER', () => {
        const out = ordinaOpportunitaStabile([
            voce({ id: 1, live: false }),
            voce({ id: 2, live: true }),
        ]);
        expect(out.map((v) => v.id)).toEqual([2, 1]);
    });

    it('a parità di tutto, la più vecchia (creataAlleMs) viene prima', () => {
        const out = ordinaOpportunitaStabile([
            voce({ id: 1, creataAlleMs: 200 }),
            voce({ id: 2, creataAlleMs: 100 }),
        ]);
        expect(out.map((v) => v.id)).toEqual([2, 1]);
    });

    it('pareggio assoluto: l’id decide, mai il caso', () => {
        const out = ordinaOpportunitaStabile([
            voce({ id: 2, creataAlleMs: 100 }),
            voce({ id: 1, creataAlleMs: 100 }),
        ]);
        expect(out.map((v) => v.id)).toEqual([1, 2]);
    });

    it('ORDINE STABILE A PARITÀ DI INSIEME: chiamare due volte con le stesse voci (nessuna nuova, nessuna uscita) da SEMPRE lo stesso risultato, qualunque proprietà "di prezzo" cambi nel frattempo', () => {
        const voci = [
            voce({ id: 3, live: true, creataAlleMs: 10 }),
            voce({ id: 1, live: false, creataAlleMs: 5 }),
            voce({ id: 2, live: true, creataAlleMs: 1 }),
        ];
        const primo = ordinaOpportunitaStabile(voci).map((v) => v.id);
        // "il prezzo cambia" non è nemmeno un campo qui: chiamare di nuovo con lo
        // STESSO insieme (via spread, nuovi oggetti ma stessi valori chiave)
        // deve produrre lo stesso ordine.
        const secondo = ordinaOpportunitaStabile(voci.map((v) => ({ ...v }))).map((v) => v.id);
        expect(secondo).toEqual(primo);
    });

    it('l’ordine cambia SOLO quando una voce entra o esce, non a ogni chiamata', () => {
        const voci = [voce({ id: 1, creataAlleMs: 1 }), voce({ id: 2, creataAlleMs: 2 })];
        const primo = ordinaOpportunitaStabile(voci).map((v) => v.id);
        expect(primo).toEqual([1, 2]);
        // entra una nuova voce piu' vecchia: SOLO ora l'ordine cambia
        const conNuova = ordinaOpportunitaStabile([...voci, voce({ id: 3, creataAlleMs: 0 })]).map((v) => v.id);
        expect(conNuova).toEqual([3, 1, 2]);
    });
});

describe('raggruppaPerPartita', () => {
    it('due voci della stessa partita finiscono nello stesso gruppo, in ordine di prima apparizione', () => {
        const ordinate = [
            voce({ id: 1, eventId: 'E1' }),
            voce({ id: 2, eventId: 'E2' }),
            voce({ id: 3, eventId: 'E1' }),
        ];
        const gruppi = raggruppaPerPartita(ordinate);
        expect(gruppi.map((g) => g.eventId)).toEqual(['E1', 'E2']);
        expect(gruppi[0].voci.map((v) => v.id)).toEqual([1, 3]);
        expect(gruppi[1].voci.map((v) => v.id)).toEqual([2]);
    });

    it('le combinazioni multi-evento (eventId null) restano gruppi separati, mai fuse fra loro', () => {
        const ordinate = [voce({ id: 1, eventId: null }), voce({ id: 2, eventId: null })];
        const gruppi = raggruppaPerPartita(ordinate);
        expect(gruppi).toHaveLength(2);
    });
});

describe('organizzaOpportunita', () => {
    it('ordina e raggruppa insieme', () => {
        const out = organizzaOpportunita([
            voce({ id: 2, eventId: 'E1', creataAlleMs: 50 }),
            voce({ id: 1, eventId: 'E2', creataAlleMs: 10 }),
            voce({ id: 3, eventId: 'E1', creataAlleMs: 20 }),
        ]);
        // ordine per creataAlleMs: 1(10,E2) poi 3(20,E1) poi 2(50,E1)
        // raggruppamento: E2 appare prima (dalla voce 1), poi E1 (dalla voce 3, con 2 appesa dopo)
        expect(out.map((g) => g.eventId)).toEqual(['E2', 'E1']);
        expect(out[1].voci.map((v) => v.id)).toEqual([3, 2]);
    });
});
