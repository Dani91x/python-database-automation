// ============================================================================
// posizioniChiuse.test.ts
//
// Il caso che conta davvero è il GREEN-UP: apertura che vince, copertura che
// perde, e la posizione in realtà guadagna. Guardare le righe da sole fa
// sembrare una copertura riuscita una sconfitta a metà — ed è successo per
// davvero il 14/09 (#287 +0,33 / #288 −0,30 = +0,03).
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    posizioniChiuse, filtraChiuse, riepilogoChiuse, esitoDi, type TradeChiudibile,
} from './posizioniChiuse';

function t(over: Partial<TradeChiudibile> & { id: number }): TradeChiudibile {
    return {
        __bot: 'safe', event_id: 'E1', event_name: 'Rossi – Bianchi', sport: 'tennis',
        mode: 'live', status: 'won', pnl: 0, side: 'back', price: 1.1, size: 3,
        selection_name: 'Rossi', placed_at: '2026-09-14T14:00:00Z',
        settled_at: '2026-09-14T15:00:00Z', closes_trade_id: null, strategy: 'tennis',
        ...over,
    };
}

describe('una posizione = apertura + le sue coperture', () => {
    it('GREEN-UP: apertura +0,33 e copertura −0,30 fanno UNA posizione da +0,03', () => {
        const p = posizioniChiuse([
            t({ id: 287, status: 'won', pnl: 0.33 }),
            t({ id: 288, status: 'lost', pnl: -0.30, closes_trade_id: 287, side: 'lay', price: 1.1, size: 3.03 }),
        ]);
        expect(p).toHaveLength(1);              // UNA posizione, non due
        expect(p[0].id).toBe(287);
        expect(p[0].pnlGlobale).toBe(0.03);
        expect(p[0].esito).toBe('vinta');       // e ha VINTO, anche se una gamba ha perso
        expect(p[0].righe).toHaveLength(2);
        expect(p[0].righe.filter((r) => r.chiusura)).toHaveLength(1);
    });

    it('le coperture NON diventano posizioni proprie: raddoppierebbero il conto', () => {
        const p = posizioniChiuse([
            t({ id: 1, pnl: 5 }),
            t({ id: 2, pnl: -4, closes_trade_id: 1 }),
        ]);
        expect(p.map((x) => x.id)).toEqual([1]);
    });

    it('una posizione ANCORA APERTA non è chiusa, e non compare', () => {
        expect(posizioniChiuse([t({ id: 1, status: 'open', pnl: null })])).toHaveLength(0);
        expect(posizioniChiuse([t({ id: 1, status: 'hedged', pnl: null })])).toHaveLength(0);
    });

    it('le righe in ERRORE non sono operazioni: non entrano in nessun conto', () => {
        const p = posizioniChiuse([
            t({ id: 1, status: 'won', pnl: 2 }),
            t({ id: 2, status: 'error', pnl: -100, closes_trade_id: 1 }),
        ]);
        expect(p[0].pnlGlobale).toBe(2);
        expect(p[0].righe).toHaveLength(1);
    });

    it('le più recenti stanno in cima', () => {
        const p = posizioniChiuse([
            t({ id: 1, settled_at: '2026-09-14T10:00:00Z' }),
            t({ id: 2, settled_at: '2026-09-14T16:00:00Z' }),
        ]);
        expect(p.map((x) => x.id)).toEqual([2, 1]);
    });
});

describe('esito — un centesimo di arrotondamento non è una vittoria', () => {
    it('sopra soglia vinta, sotto persa, in mezzo pari', () => {
        expect(esitoDi(0.03)).toBe('vinta');
        expect(esitoDi(-0.03)).toBe('persa');
        expect(esitoDi(0)).toBe('pari');
        expect(esitoDi(0.001)).toBe('pari');
    });
});

describe('paper e live restano posizioni DIVERSE', () => {
    it('la modalità si legge dalla riga di apertura ed è fail-closed', () => {
        const p = posizioniChiuse([
            t({ id: 1, mode: 'live' }),
            t({ id: 2, mode: 'paper', event_id: 'E2' }),
            t({ id: 3, mode: undefined, event_id: 'E3' }),
        ]);
        expect(p.find((x) => x.id === 1)?.modo).toBe('live');
        expect(p.find((x) => x.id === 2)?.modo).toBe('paper');
        // non dichiarata = paper, mai soldi veri per distrazione
        expect(p.find((x) => x.id === 3)?.modo).toBe('paper');
    });

    it('il filtro per modalità tiene separati i due mondi', () => {
        const p = posizioniChiuse([
            t({ id: 1, mode: 'live', pnl: 1 }),
            t({ id: 2, mode: 'paper', pnl: -50, event_id: 'E2' }),
        ]);
        const soloVeri = filtraChiuse(p, { modo: 'live' });
        expect(soloVeri).toHaveLength(1);
        expect(riepilogoChiuse(soloVeri).totale).toBe(1);   // mai 1 − 50
    });
});

describe('filtri', () => {
    const p = posizioniChiuse([
        t({ id: 1, pnl: 3, sport: 'tennis', __bot: 'safe' }),
        t({ id: 2, pnl: -2, sport: 'calcio', event_id: 'E2', __bot: 'omega' }),
        t({ id: 3, pnl: 0, sport: 'calcio', event_id: 'E3', __bot: 'mike' }),
    ]);

    it('per esito', () => {
        expect(filtraChiuse(p, { esito: 'vinta' }).map((x) => x.id)).toEqual([1]);
        expect(filtraChiuse(p, { esito: 'persa' }).map((x) => x.id)).toEqual([2]);
        expect(filtraChiuse(p, { esito: 'pari' }).map((x) => x.id)).toEqual([3]);
    });

    it('per sport e per bot', () => {
        expect(filtraChiuse(p, { sport: 'calcio' })).toHaveLength(2);
        expect(filtraChiuse(p, { bot: 'mike' }).map((x) => x.id)).toEqual([3]);
    });

    it('«tutte» non filtra niente', () => {
        expect(filtraChiuse(p, { esito: 'tutte', sport: 'tutti', bot: 'tutti' })).toHaveLength(3);
        expect(filtraChiuse(p, {})).toHaveLength(3);
    });
});

describe('riepilogo — descrive QUELLO CHE SI VEDE, non tutto il resto', () => {
    it('conta esiti e somma i P&L globali delle righe che riceve', () => {
        const p = posizioniChiuse([
            t({ id: 1, pnl: 3 }),
            t({ id: 2, pnl: -2, event_id: 'E2' }),
            t({ id: 3, pnl: 0, event_id: 'E3' }),
        ]);
        const r = riepilogoChiuse(p);
        expect(r).toMatchObject({ n: 3, vinte: 1, perse: 1, pari: 1, totale: 1 });
        expect(r.percentualeVinte).toBeCloseTo(0.5, 5);
    });

    it('nessuna posizione: totale null, non 0,00 €', () => {
        const r = riepilogoChiuse([]);
        expect(r.totale).toBeNull();
        expect(r.percentualeVinte).toBeNull();
    });

    it('solo pareggi: nessuna percentuale inventata', () => {
        const p = posizioniChiuse([t({ id: 1, pnl: 0 })]);
        expect(riepilogoChiuse(p).percentualeVinte).toBeNull();
    });
});
