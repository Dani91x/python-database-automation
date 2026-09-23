// ============================================================================
// nettoCiclo.test.ts - 23/09: il P&L di un'operazione chiusa e' il NETTO DEL
// CICLO (apertura + tutte le gambe di chiusura regolate), mai la sola apertura.
//
// Finti con le chiavi VERE di `safe_strategy_trades` (righe lette dal
// coordinatore il 23/09, sport=tennis, mode=live).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { groupTradesIntoCicli, nettoCicloChiuso, type PnlTradeLike } from './eventGroups';
import { righeRealizzatoPerCiclo, componiObiettivo, type RigaTradeCiclo } from './composizioneObiettivo';
import { realizzatoGiornata } from './controlRoom';
import { posizioniChiuse, riepilogoChiuse, type TradeChiudibile } from './posizioniChiuse';

interface RigaSafe extends RigaTradeCiclo {
    event_name: string; sport: string; strategy: string; market_id: string;
    selection_id: number; selection_name: string; commission: number;
    settled_at: string | null; bet_id: string | null; origin: string;
    meta: Record<string, unknown>;
}

function riga(over: Partial<RigaSafe> & Pick<RigaSafe, 'id'>): RigaSafe {
    return {
        event_id: 'T1', event_name: 'Rossi v Bianchi', sport: 'tennis', strategy: 'tennis',
        market_id: '1.300', selection_id: 11, selection_name: 'Rossi', side: 'back',
        mode: 'live', price: 1.15, size: 3, liability: 3, commission: 0.05,
        status: 'won', pnl: 0, placed_at: '2026-09-22T10:00:00.000Z',
        settled_at: '2026-09-22T12:00:00.000Z', bet_id: 'B', origin: 'auto',
        closes_trade_id: null, meta: {},
        ...over,
    };
}

const CASH_OUT = { origin: 'manual', meta: { cashout: 'true', exit_kind: 'manual' } };

/** 326 back 3,00 @1.15 won +0.45 / 327 lay 3,17 @1.08 lost -0.25 -> +0.20 */
const C326 = [
    riga({ id: 326, side: 'back', price: 1.15, size: 3, status: 'won', pnl: 0.45 }),
    riga({ id: 327, side: 'lay', price: 1.08, size: 3.17, status: 'lost', pnl: -0.25,
        placed_at: '2026-09-22T10:30:00.000Z', closes_trade_id: 326, ...CASH_OUT }),
];
/** 307 back 3,00 @1.12 lost -3.00 / 317 lay 3,11 @1.08 won +3.11 -> +0.11 */
const C307 = [
    riga({ id: 307, side: 'back', price: 1.12, size: 3, status: 'lost', pnl: -3,
        placed_at: '2026-09-22T09:00:00.000Z' }),
    riga({ id: 317, side: 'lay', price: 1.08, size: 3.11, status: 'won', pnl: 3.11,
        placed_at: '2026-09-22T09:20:00.000Z', closes_trade_id: 307, ...CASH_OUT }),
];

const perChiuse = (r: readonly RigaSafe[]): TradeChiudibile[] =>
    r.map((t) => ({ ...t, __bot: 'safe' as const }));
const tuttoIlGiorno = { delGiorno: (p: string | null | undefined) => !!p && p.startsWith('2026-09-22') };

describe('nettoCicloChiuso: apertura + chiusure regolate', () => {
    it('326/327 -> +0.20 e 307/317 -> +0.11', () => {
        expect(nettoCicloChiuso(C326[0], [C326[1]])).toBe(0.2);
        expect(nettoCicloChiuso(C307[0], [C307[1]])).toBe(0.11);
    });
    it('senza chiusura vale il P&L dell apertura', () => {
        expect(nettoCicloChiuso(C326[0], [])).toBe(0.45);
    });
    it('una chiusura ancora viva: non definitivo -> null; annullata: non pesa', () => {
        expect(nettoCicloChiuso(C326[0], [{ ...C326[1], status: 'open' }])).toBeNull();
        expect(nettoCicloChiuso(C326[0], [{ ...C326[1], status: 'cancelled' }])).toBe(0.45);
        expect(nettoCicloChiuso({ ...C326[0], status: 'open' }, [C326[1]])).toBeNull();
    });
});

describe('posizioniChiuse: il numero della riga e il netto del ciclo', () => {
    it('due cicli di cash out -> +0.20 e +0.11, riepilogo +0.31', () => {
        const p = posizioniChiuse(perChiuse([...C326, ...C307]));
        expect(Object.fromEntries(p.map((x) => [x.id, x.pnlGlobale]))).toEqual({ 326: 0.2, 307: 0.11 });
        expect(p.every((x) => x.orfana === false)).toBe(true);
        expect(riepilogoChiuse(p).totale).toBe(0.31);
        expect(riepilogoChiuse(p).vinte).toBe(2);
    });
    it('una chiusura senza apertura resta visibile e dichiarata orfana', () => {
        const p = posizioniChiuse(perChiuse([C326[1]]));
        expect(p.map((x) => [x.id, x.pnlGlobale, x.orfana])).toEqual([[327, -0.25, true]]);
    });
});

describe('righeRealizzatoPerCiclo: la barra conta operazioni, non gambe', () => {
    it('realizzato = somma dei netti, 2 vinte 0 perse (per gamba sarebbero 2 e 2)', () => {
        const r = realizzatoGiornata(righeRealizzatoPerCiclo([...C326, ...C307], tuttoIlGiorno));
        expect(r.live).toBe(0.31);
        expect(r.perSport.tennis).toBe(0.31);
        expect(r.righe).toBe(2);
        expect(r.vinte).toBe(2);
        expect(r.perse).toBe(0);
    });
    it('ciclo senza chiusura -> il P&L dell apertura', () => {
        const r = righeRealizzatoPerCiclo([C326[0]], tuttoIlGiorno);
        expect(r).toEqual([{ status: 'won', pnl: 0.45, mode: 'live', sport: 'tennis', origin: 'auto' }]);
    });
    it('la chiusura del cash out (origin manual) resta nel bot: Safe tennis +0.31, Manuale vuoto', () => {
        const safe = righeRealizzatoPerCiclo([...C326, ...C307], tuttoIlGiorno);
        const c = componiObiettivo({ omega: [], safe, mike: [], tennisBot: [] });
        const per = Object.fromEntries(c.righe.map((x) => [x.chiave, x.valore]));
        expect(per.safe_tennis).toBe(0.31);
        expect(per.manuale).toBeNull();
    });
    it('la giornata e quella dell APERTURA: una chiusura dopo mezzanotte non cambia giorno', () => {
        const dopo = [C326[0], { ...C326[1], placed_at: '2026-09-23T00:10:00.000Z' }];
        const r = righeRealizzatoPerCiclo(dopo, tuttoIlGiorno);
        expect(r.map((x) => x.pnl)).toEqual([0.2]);
        const domani = righeRealizzatoPerCiclo(dopo, {
            delGiorno: (p) => !!p && p.startsWith('2026-09-23'),
        });
        expect(domani).toEqual([]);
    });
    it('le righe in errore non entrano', () => {
        const r = righeRealizzatoPerCiclo([{ ...C326[0], status: 'error', pnl: 0 }], tuttoIlGiorno);
        expect(r).toEqual([]);
    });
});

describe('groupTradesIntoCicli: catena A <- B <- C sotto la radice', () => {
    it('la terza gamba entra nel netto dell apertura', () => {
        const righe: PnlTradeLike[] = [
            riga({ id: 1, status: 'won', pnl: 1 }),
            riga({ id: 2, status: 'lost', pnl: -0.5, closes_trade_id: 1 }),
            riga({ id: 3, status: 'lost', pnl: -0.2, closes_trade_id: 2 }),
        ];
        const g = groupTradesIntoCicli(righe);
        expect(g).toHaveLength(1);
        expect(g[0].closes.map((c) => c.id)).toEqual([2, 3]);
        expect(g[0].netPnl).toBe(0.3);
    });
});
