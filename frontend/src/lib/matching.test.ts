// Test del motore di matching FEDELE Betfair (matching.ts). Money-critical: copre
// taker/maker, price improvement, ritardo, fill nel tempo (trd e proxy ltp/Δtv),
// cap su volume tradato, queue position, cancel, lapse, tick e determinismo.
import { describe, it, expect } from 'vitest';
import {
    roundToTick, isValidTick, tickUp, tickDown, matchMarketable, simulateOrder,
    type BookSnapshot, type OrderRequest,
} from './matching';

// helper: snapshot compatto
function snap(p: Partial<BookSnapshot> & { ts: number }): BookSnapshot {
    return { back: [], lay: [], ltp: null, tv: null, ...p };
}

describe('roundToTick / isValidTick', () => {
    it('arrotonda alle fasce Betfair', () => {
        expect(roundToTick(2.811)).toBe(2.82); // fascia 2-3 step 0.02
        expect(roundToTick(3.06)).toBe(3.05);  // fascia 3-4 step 0.05
        expect(roundToTick(1.005)).toBe(1.01); // clamp basso
        expect(roundToTick(5.04)).toBe(5);     // fascia 4-6 step 0.1
        expect(roundToTick(11.3)).toBe(11.5);  // fascia 10-20 step 0.5
    });
    it('riconosce i tick validi', () => {
        expect(isValidTick(2.82)).toBe(true);
        expect(isValidTick(2.83)).toBe(false);
        expect(isValidTick(3.05)).toBe(true);
    });
    it('tickUp/tickDown rispettano i confini di banda', () => {
        expect(tickUp(2.98)).toBe(3.0);   // confine: 2-3 step 0.02 → 3.00
        expect(tickUp(3.0)).toBe(3.05);   // 3-4 step 0.05
        expect(tickDown(3.0)).toBe(2.98); // scendendo si usa lo step della banda sotto
        expect(tickUp(2.0, 3)).toBe(2.06);
        expect(tickDown(1.01)).toBe(1.01); // clamp basso
    });
});

describe('matchMarketable — taker', () => {
    it('back: fill pieno al best price', () => {
        const b = snap({ ts: 0, back: [[2.82, 200]] });
        const r = matchMarketable('back', 2.82, 100, b);
        expect(r.matched).toBe(100);
        expect(r.avgPrice).toBe(2.82);
        expect(r.remaining).toBe(0);
    });

    it('back: fill PARZIALE, non rotola sotto il limite', () => {
        const b = snap({ ts: 0, back: [[2.82, 50], [2.80, 100]] });
        const r = matchMarketable('back', 2.82, 100, b);
        expect(r.matched).toBe(50);          // solo il livello ≥ 2.82
        expect(r.avgPrice).toBe(2.82);
        expect(r.remaining).toBe(50);
    });

    it('back: PRICE IMPROVEMENT (limite sotto mercato → VWAP migliore)', () => {
        const b = snap({ ts: 0, back: [[2.82, 40], [2.70, 100]] });
        const r = matchMarketable('back', 2.50, 100, b);
        expect(r.matched).toBe(100);
        // (40*2.82 + 60*2.70)/100 = 2.748
        expect(r.avgPrice).toBeCloseTo(2.748, 6);
    });

    it('back: nessun fill se il limite è sopra il mercato', () => {
        const b = snap({ ts: 0, back: [[2.82, 200]] });
        const r = matchMarketable('back', 3.00, 100, b);
        expect(r.matched).toBe(0);
        expect(r.avgPrice).toBeNull();
        expect(r.remaining).toBe(100);
    });

    it('lay: fill parziale al best (≤ limite)', () => {
        const b = snap({ ts: 0, lay: [[3.05, 30], [3.10, 100]] });
        const r = matchMarketable('lay', 3.05, 100, b);
        expect(r.matched).toBe(30);
        expect(r.remaining).toBe(70);
    });

    it('lay: PRICE IMPROVEMENT (limite sopra mercato → VWAP più basso)', () => {
        const b = snap({ ts: 0, lay: [[3.05, 40], [3.15, 100]] });
        const r = matchMarketable('lay', 3.20, 100, b);
        expect(r.matched).toBe(100);
        // (40*3.05 + 60*3.15)/100 = 3.11
        expect(r.avgPrice).toBeCloseTo(3.11, 6);
    });
});

describe('simulateOrder — taker immediato', () => {
    it('pre-match: fill pieno e MATCHED', () => {
        const req: OrderRequest = { side: 'back', limitPrice: 2.82, stake: 100, placedTs: 1000, inPlay: false };
        const frames = [snap({ ts: 1000, back: [[2.82, 200]] })];
        const r = simulateOrder(req, frames, 1000);
        expect(r.matched).toBe(100);
        expect(r.avgPrice).toBe(2.82);
        expect(r.status).toBe('MATCHED');
    });

    it('in-play: PENDING prima del ritardo, abbinato al book ritardato', () => {
        const req: OrderRequest = { side: 'back', limitPrice: 2.90, stake: 100, placedTs: 1000, inPlay: true, delayMs: 5000 };
        const frames = [
            snap({ ts: 1000, back: [[2.82, 200]] }),  // al piazzamento (non ancora colpito)
            snap({ ts: 6000, back: [[3.00, 200]] }),  // book a placedTs+delay → marketable (≥2.90)
        ];
        // prima del ritardo
        expect(simulateOrder(req, frames, 5000).status).toBe('PENDING');
        expect(simulateOrder(req, frames, 5000).matched).toBe(0);
        // al ritardo: si abbina contro il book di ts=6000 (3.00 ≥ 2.90)
        const r = simulateOrder(req, frames, 6000);
        expect(r.matched).toBe(100);
        expect(r.avgPrice).toBe(3.00);
        expect(r.effectiveTs).toBe(6000);
    });
});

describe('simulateOrder — maker (resto a riposo) con trd per-prezzo', () => {
    const req: OrderRequest = { side: 'back', limitPrice: 3.00, stake: 100, placedTs: 1000, inPlay: false };
    // best back 2.82 < 3.00 → 0 taker; il resto riposa a 3.00 e si abbina quando il
    // mercato TRATTA a ≥ 3.00 (trd cumulativo per-prezzo).
    const frames = [
        snap({ ts: 1000, back: [[2.82, 200]], lay: [[3.05, 50]], trd: [[2.90, 100]] }),
        snap({ ts: 2000, back: [[2.95, 200]], lay: [[3.05, 50]], trd: [[2.90, 100], [3.00, 40]] }),
        snap({ ts: 3000, back: [[3.00, 200]], lay: [[3.10, 50]], trd: [[2.90, 100], [3.00, 90]] }),
    ];

    it('niente fill finché il mercato non tratta a ≥ limite', () => {
        const r = simulateOrder(req, frames, 1000);
        expect(r.matched).toBe(0);
        expect(r.status).toBe('OPEN');
    });

    it('fill incrementale al proprio prezzo limite man mano che si tratta', () => {
        const r2 = simulateOrder(req, frames, 2000);
        expect(r2.matched).toBe(40);            // 40 tradati a 3.00
        expect(r2.avgPrice).toBe(3.00);          // maker → prende il proprio prezzo
        expect(r2.fills.every(f => f.taker === false)).toBe(true);

        const r3 = simulateOrder(req, frames, 3000);
        expect(r3.matched).toBe(90);            // +50 (cum 90 a 3.00)
        expect(r3.remaining).toBe(10);
        expect(r3.status).toBe('OPEN');
    });

    it('è deterministico e monotòno nello scrubbing', () => {
        const m1 = simulateOrder(req, frames, 1000).matched;
        const m2 = simulateOrder(req, frames, 2000).matched;
        const m3 = simulateOrder(req, frames, 3000).matched;
        expect(m1).toBeLessThanOrEqual(m2);
        expect(m2).toBeLessThanOrEqual(m3);
        // ricalcolo ripetuto → identico
        expect(simulateOrder(req, frames, 2000).matched).toBe(m2);
    });
});

describe('simulateOrder — maker con QUEUE position (trd)', () => {
    it('smaltisce prima la coda davanti, poi riempie', () => {
        const req: OrderRequest = { side: 'back', limitPrice: 3.00, stake: 100, placedTs: 1000, inPlay: false };
        const frames = [
            // 80 già in coda a 3.00 (available-to-lay) davanti a noi
            snap({ ts: 1000, back: [[2.82, 200]], lay: [[3.00, 80]], trd: [[2.90, 10]] }),
            // tradati 100 a 3.00: 80 vanno alla coda, 20 a noi
            snap({ ts: 2000, back: [[3.00, 50]], lay: [[3.05, 50]], trd: [[2.90, 10], [3.00, 100]] }),
        ];
        const r = simulateOrder(req, frames, 2000);
        expect(r.matched).toBe(20);
        expect(r.remaining).toBe(80);
    });
});

describe('simulateOrder — maker proxy ltp/Δtv (senza trd)', () => {
    const req: OrderRequest = { side: 'back', limitPrice: 3.00, stake: 100, placedTs: 1000, inPlay: false };

    it('riempie solo quando ltp attraversa il limite, con cap su Δtv', () => {
        const frames = [
            snap({ ts: 1000, back: [[2.82, 200]], lay: [[3.05, 50]], ltp: 2.90, tv: 1000 }),
            snap({ ts: 2000, back: [[2.95, 200]], lay: [[3.05, 50]], ltp: 3.05, tv: 1030 }), // Δtv=30, ltp≥3.00
            snap({ ts: 3000, back: [[3.00, 200]], lay: [[3.10, 50]], ltp: 3.10, tv: 1100 }), // Δtv=70
        ];
        expect(simulateOrder(req, frames, 1000).matched).toBe(0);
        expect(simulateOrder(req, frames, 2000).matched).toBe(30); // cap su Δtv=30
        expect(simulateOrder(req, frames, 3000).matched).toBe(100); // 30 + min(70, 70)
    });

    it('NON riempie se l’ltp non raggiunge mai il limite (anche se cresce il volume)', () => {
        const frames = [
            snap({ ts: 1000, back: [[2.82, 200]], lay: [[3.05, 50]], ltp: 2.90, tv: 1000 }),
            snap({ ts: 2000, back: [[2.85, 200]], lay: [[3.05, 50]], ltp: 2.92, tv: 1500 }), // tanto volume ma sotto 3.00
        ];
        expect(simulateOrder(req, frames, 2000).matched).toBe(0);
    });
});

describe('simulateOrder — cancel & lapse', () => {
    const base: OrderRequest = { side: 'back', limitPrice: 3.00, stake: 100, placedTs: 1000, inPlay: false };
    const frames = [
        snap({ ts: 1000, back: [[2.82, 200]], lay: [[3.05, 50]], ltp: 2.90, tv: 1000, status: 'OPEN' }),
        snap({ ts: 2000, back: [[2.95, 200]], lay: [[3.05, 50]], ltp: 3.05, tv: 1030, status: 'OPEN' }),
        snap({ ts: 3000, back: [[3.00, 200]], lay: [[3.10, 50]], ltp: 3.10, tv: 1100, status: 'OPEN' }),
    ];

    it('cancel rimuove il resto non abbinato', () => {
        const req = { ...base, cancelledTs: 2500 }; // dopo il primo fill di 30, prima del resto
        const r = simulateOrder(req, frames, 3000);
        expect(r.matched).toBe(30);
        expect(r.remaining).toBe(0);
        expect(r.status).toBe('OPEN'); // parzialmente abbinato poi cancellato
    });

    it('cancel totale prima di ogni fill → CANCELLED', () => {
        const req = { ...base, cancelledTs: 1500 };
        const r = simulateOrder(req, frames, 3000);
        expect(r.matched).toBe(0);
        expect(r.status).toBe('CANCELLED');
    });

    it('LAPSE alla sospensione annulla il resto', () => {
        const susp = [
            frames[0],
            snap({ ts: 2000, back: [[2.95, 200]], lay: [[3.05, 50]], ltp: 2.95, tv: 1000, status: 'SUSPENDED' }),
        ];
        const r = simulateOrder(base, susp, 2000);
        expect(r.matched).toBe(0);
        expect(r.status).toBe('LAPSED');
    });

    it('PERSIST mantiene il resto alla sospensione', () => {
        const susp = [
            frames[0],
            snap({ ts: 2000, back: [[2.95, 200]], lay: [[3.05, 50]], ltp: 2.95, tv: 1000, status: 'SUSPENDED' }),
        ];
        const r = simulateOrder({ ...base, persistence: 'PERSIST' }, susp, 2000);
        expect(r.status).toBe('OPEN'); // non annullato
    });
});

describe('simulateOrder — guardie input', () => {
    it('stake non valido → CANCELLED', () => {
        const r = simulateOrder({ side: 'back', limitPrice: 2.82, stake: 0, placedTs: 0, inPlay: false }, [snap({ ts: 0, back: [[2.82, 100]] })], 0);
        expect(r.status).toBe('CANCELLED');
        expect(r.matched).toBe(0);
    });
});

describe('simulateOrder — book SOSPESO/CHIUSO all\'arrivo al matcher (fedeltà)', () => {
    // il ladder residuo di un frame sospeso NON è liquidità disponibile: nessun
    // fill taker. LAPSE → decade; PERSIST → riposa e si abbina alla riapertura.
    const req: OrderRequest = { side: 'back', limitPrice: 2.82, stake: 100, placedTs: 0, inPlay: false };

    it('SUSPENDED + LAPSE → nessun fill, LAPSED', () => {
        const frames = [snap({ ts: 0, back: [[2.82, 500]], status: 'SUSPENDED' })];
        const r = simulateOrder(req, frames, 10_000);
        expect(r.matched).toBe(0);
        expect(r.status).toBe('LAPSED');
        expect(r.remaining).toBe(0);
    });

    it('CLOSED → LAPSED anche con PERSIST', () => {
        const frames = [snap({ ts: 0, back: [[2.82, 500]], status: 'CLOSED' })];
        const r = simulateOrder({ ...req, persistence: 'PERSIST' }, frames, 10_000);
        expect(r.matched).toBe(0);
        expect(r.status).toBe('LAPSED');
    });

    it('SUSPENDED + PERSIST → resta a riposo e si abbina alla RIAPERTURA (trd)', () => {
        const frames = [
            snap({ ts: 0, back: [[2.82, 500]], status: 'SUSPENDED', trd: [[2.82, 0]] }),
            // riapre: volume tradato attraversa il limite → fill maker al proprio prezzo
            snap({ ts: 5000, back: [[2.80, 100]], lay: [[2.84, 100]], ltp: 2.82, status: 'OPEN', trd: [[2.82, 300]] }),
        ];
        const r = simulateOrder({ ...req, persistence: 'PERSIST' }, frames, 10_000);
        expect(r.status).toBe('MATCHED');
        expect(r.matched).toBe(100);
        expect(r.avgPrice).toBe(2.82);
    });

    it('in-play col delay: piazzato su book OPEN ma SOSPESO all\'arrivo → LAPSED (mai fill post-gol)', () => {
        const frames = [
            snap({ ts: 0, back: [[2.82, 500]], status: 'OPEN' }),
            snap({ ts: 3000, back: [[2.82, 500]], status: 'SUSPENDED' }), // gol durante il delay
        ];
        const r = simulateOrder({ side: 'back', limitPrice: 2.82, stake: 100, placedTs: 0, inPlay: true, delayMs: 5000 }, frames, 10_000);
        expect(r.matched).toBe(0);
        expect(r.status).toBe('LAPSED');
    });
});

describe('simulateOrder — CLOSED durante il riposo maker', () => {
    it('PERSIST a riposo decade quando il mercato CHIUDE (mai ordini vivi post-regolamento)', () => {
        const frames = [
            snap({ ts: 0, back: [[2.80, 50]], lay: [[2.84, 100]], status: 'OPEN' }),
            snap({ ts: 5000, back: [], lay: [], status: 'CLOSED' }),
        ];
        const r = simulateOrder(
            { side: 'back', limitPrice: 2.82, stake: 100, placedTs: 0, inPlay: false, persistence: 'PERSIST' },
            frames, 10_000,
        );
        expect(r.remaining).toBe(0);
        expect(r.status).toBe('LAPSED'); // niente fill taker (limite 2.82 > best 2.80)
    });
});
