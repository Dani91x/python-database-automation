// ============================================================================
// eventGroups — la matematica comune sotto la sezione Operazioni dei tre bot.
//
// Qui si maneggiano SOLDI: si certifica che il raggruppamento non inventi mai
// un numero, non sommi due volte gli stessi euro, non spacci un dato assente
// per uno zero e non mescoli paper e live in un unico totale.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    groupTradesIntoCicli, groupCicliByEvent, totaliOperazioni, tradesOfMode,
    isSettled, isErrorRow, type PnlTradeLike,
} from './eventGroups';

let seq = 0;
function t(over: Partial<PnlTradeLike> = {}): PnlTradeLike {
    seq += 1;
    return {
        id: seq, event_id: 'E1', event_name: 'Roma v Lazio',
        side: 'back', mode: 'paper', price: 1.5, size: 10, liability: 10,
        status: 'won', pnl: 0, placed_at: '2026-09-13T10:00:00Z', closes_trade_id: null,
        ...over,
    };
}

/** un ciclo completo: apertura + chiusura che la riferisce */
function ciclo(over: Partial<PnlTradeLike>, pnlApre: number, pnlChiude: number) {
    const apre = t({ ...over, pnl: pnlApre });
    const chiude = t({
        ...over, side: 'lay', pnl: pnlChiude,
        closes_trade_id: apre.id, placed_at: '2026-09-13T10:05:00Z',
    });
    return [apre, chiude];
}

describe('le chiusure stanno sotto la loro apertura', () => {
    it('un ciclo è UNA posizione, non due operazioni scollegate', () => {
        const g = groupTradesIntoCicli(ciclo({}, -10, 10.13));
        expect(g).toHaveLength(1);
        expect(g[0].closes).toHaveLength(1);
        expect(g[0].netPnl).toBe(0.13);
    });

    it('una chiusura senza la sua apertura è dichiarata orfana, mai nascosta', () => {
        const g = groupTradesIntoCicli([t({ closes_trade_id: 99999, pnl: 4 })]);
        expect(g).toHaveLength(1);
        expect(g[0].orphan).toBe(true);
    });

    it('un ciclo senza righe regolate non vale zero: vale «non lo so»', () => {
        const g = groupTradesIntoCicli([t({ status: 'open', pnl: null })]);
        expect(g[0].netPnl).toBeNull();
    });

    it('le aperture sono ordinate dalla più recente', () => {
        const g = groupTradesIntoCicli([
            t({ id: 1, placed_at: '2026-09-13T08:00:00Z' }),
            t({ id: 2, placed_at: '2026-09-13T12:00:00Z' }),
        ]);
        expect(g.map((x) => x.open.id)).toEqual([2, 1]);
    });
});

describe('il netto della PARTITA', () => {
    it('somma i cicli della stessa partita in una riga sola', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([
            ...ciclo({}, -10, 10.13),
            ...ciclo({}, -10, 10.20),
        ]));
        expect(e).toHaveLength(1);
        expect(e[0].cicli).toHaveLength(2);
        expect(e[0].netPnl).toBe(0.33);
    });

    it('tiene separate due partite diverse', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([
            ...ciclo({ event_id: 'A', event_name: 'Alfa' }, -10, 10.1),
            ...ciclo({ event_id: 'B', event_name: 'Beta' }, -10, 9),
        ]));
        expect(e.map((x) => x.event_id).sort()).toEqual(['A', 'B']);
    });

    it('una partita senza niente di regolato ha netto NULL, non zero', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([t({ status: 'open', pnl: null })]));
        expect(e[0].netPnl).toBeNull();
        expect(e[0].apertaAncora).toBe(true);
    });

    it('le righe in errore non sono operazioni: non fanno netto', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([t({ status: 'error', pnl: 0 })]));
        expect(e[0].netPnl).toBeNull();
    });

    it('grida «mista» se la partita mescola paper e soldi veri', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([
            t({ mode: 'paper' }), t({ mode: 'live' }),
        ]));
        expect(e[0].mode).toBe('mista');
    });
});

describe('capitale impegnato e responsabilità', () => {
    it('l’investito conta SOLO le aperture, non le gambe di chiusura', () => {
        // due gambe da 10 €, ma è un ciclo solo: impegnati 10, non 20
        const e = groupCicliByEvent(groupTradesIntoCicli(ciclo({}, -10, 10.13)));
        expect(e[0].investito).toBe(10);
    });

    it('un’apertura in errore non ha impegnato niente', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([t({ status: 'error', size: 25 })]));
        expect(e[0].investito).toBe(0);
    });

    it('la responsabilità è quella delle righe ANCORA VIVE', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([
            t({ status: 'won', liability: 40 }),          // regolata: non rischia più
            t({ status: 'open', liability: 15, pnl: null }),
        ]));
        expect(e[0].liability).toBe(15);
    });
});

describe('i totali non mentono', () => {
    it('senza nessuna partita con risultato il realizzato è NULL, non 0', () => {
        const tot = totaliOperazioni(groupCicliByEvent(groupTradesIntoCicli([
            t({ status: 'open', pnl: null }),
        ])));
        expect(tot.realizzato).toBeNull();
        expect(tot.partiteAperte).toBe(1);
    });

    it('conta le posizioni, non le gambe', () => {
        const tot = totaliOperazioni(groupCicliByEvent(groupTradesIntoCicli([
            ...ciclo({ event_id: 'A' }, -10, 10.13),
            ...ciclo({ event_id: 'B' }, -10, 9),
        ])));
        expect(tot.operazioni).toBe(2);   // 4 righe, 2 posizioni
        expect(tot.partite).toBe(2);
    });

    it('somma solo le partite con un risultato e separa utili e perdite', () => {
        const tot = totaliOperazioni(groupCicliByEvent(groupTradesIntoCicli([
            ...ciclo({ event_id: 'A' }, -10, 10.13),      // +0,13
            ...ciclo({ event_id: 'B' }, -10, 9.00),       // −1,00
            t({ event_id: 'C', status: 'open', pnl: null }),
        ])));
        expect(tot.realizzato).toBe(-0.87);
        expect(tot.partiteConRisultato).toBe(2);
        expect(tot.vinte).toBe(1);
        expect(tot.perse).toBe(1);
        expect(tot.partiteAperte).toBe(1);
    });

    it('su un insieme vuoto non inventa niente', () => {
        const tot = totaliOperazioni([]);
        expect(tot.realizzato).toBeNull();
        expect(tot.operazioni).toBe(0);
        expect(tot.investito).toBe(0);
    });
});

describe('paper e live sono contabilità separate', () => {
    const righe = [
        ...ciclo({ event_id: 'A', mode: 'paper' }, -10, 12),   // +2,00 simulati
        ...ciclo({ event_id: 'B', mode: 'live' }, -10, 5),     // −5,00 veri
    ];

    it('il totale di una modalità non contiene gli euro dell’altra', () => {
        const paper = totaliOperazioni(groupCicliByEvent(groupTradesIntoCicli(tradesOfMode(righe, 'paper'))));
        const live = totaliOperazioni(groupCicliByEvent(groupTradesIntoCicli(tradesOfMode(righe, 'live'))));
        expect(paper.realizzato).toBe(2);
        expect(live.realizzato).toBe(-5);
    });

    it('senza modalità dichiarata non filtra (e chi chiama non deve dichiararla)', () => {
        expect(tradesOfMode(righe, null)).toHaveLength(4);
        expect(tradesOfMode(righe, '')).toHaveLength(4);
    });
});

describe('classificazione delle righe', () => {
    it('solo won/lost/void sono esiti certi', () => {
        expect(isSettled('won')).toBe(true);
        expect(isSettled('lost')).toBe(true);
        expect(isSettled('void')).toBe(true);
        expect(isSettled('hedged')).toBe(false);
        expect(isSettled('open')).toBe(false);
        expect(isSettled(null)).toBe(false);
    });

    it('«error» non è un’operazione', () => {
        expect(isErrorRow('error')).toBe(true);
        expect(isErrorRow('open')).toBe(false);
    });
});

describe('non produce mai numeri rotti', () => {
    it('size e pnl non numerici non diventano NaN', () => {
        const e = groupCicliByEvent(groupTradesIntoCicli([
            t({ size: 'tanto' as unknown as number, pnl: 'boh' as unknown as number, status: 'won' }),
        ]));
        expect(Number.isNaN(e[0].investito)).toBe(false);
        expect(e[0].investito).toBe(0);
        expect(e[0].netPnl).toBe(0);
    });
});
