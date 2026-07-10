import { describe, it, expect } from 'vitest';
import {
    detectPulledWalls, newFlowState, pushFlowSample, tradeSpike, womShift,
    type FlowState,
} from './orderFlow';

const T0 = 1_000_000;

type Lv = ReadonlyArray<readonly [number, number]>;

function feed(state: FlowState, t: number, back: Lv, lay: Lv, trd: Lv): void {
    pushFlowSample(state, t, back, lay, trd);
}

describe('detectPulledWalls (muri finti)', () => {
    it('muro che sparisce SENZA trade → segnalato con peak/drop/traded esatti', () => {
        const s = newFlowState();
        // t0: muro €800 LAY a 2.10, tradato cumulato 100
        feed(s, T0, [[2.08, 50]], [[2.10, 800]], [[2.10, 100]]);
        // t0+5s: il muro sparisce (resta €40), tradato quasi invariato (=ritirato)
        feed(s, T0 + 5_000, [[2.08, 50]], [[2.10, 40]], [[2.10, 110]]);
        const walls = detectPulledWalls(s, T0 + 5_000);
        expect(walls).toHaveLength(1);
        expect(walls[0]).toMatchObject({ side: 'lay', price: 2.10, peak: 800, dropped: 760 });
        expect(walls[0].traded).toBe(10);   // 110−100: nulla rispetto ai €760 spariti
    });

    it('muro CONSUMATO dai trade → NON segnalato (mercato vero, non spoof)', () => {
        const s = newFlowState();
        feed(s, T0, [], [[2.10, 800]], [[2.10, 100]]);
        // sparito ma il tradato a quel prezzo è cresciuto di €700 → consumato
        feed(s, T0 + 5_000, [], [[2.10, 40]], [[2.10, 800]]);
        expect(detectPulledWalls(s, T0 + 5_000)).toHaveLength(0);
    });

    it('size piccola (sotto minWall) → mai segnalata (niente rumore)', () => {
        const s = newFlowState();
        feed(s, T0, [[3.0, 100]], [], []);
        feed(s, T0 + 5_000, [[3.0, 0]], [], []);
        expect(detectPulledWalls(s, T0 + 5_000)).toHaveLength(0); // 100 < 150 default
    });

    it('drop parziale (sotto minDropFrac) → non segnalato', () => {
        const s = newFlowState();
        feed(s, T0, [[3.0, 400]], [], []);
        feed(s, T0 + 5_000, [[3.0, 200]], [], []); // −50% < 70% richiesto
        expect(detectPulledWalls(s, T0 + 5_000)).toHaveLength(0);
    });

    it('storia insufficiente (un solo campione) → []', () => {
        const s = newFlowState();
        feed(s, T0, [[3.0, 500]], [], []);
        expect(detectPulledWalls(s, T0)).toHaveLength(0);
    });

    it('muro FUORI finestra → non considerato (solo la finestra osservata)', () => {
        const s = newFlowState();
        feed(s, T0, [], [[2.10, 800]], []);
        feed(s, T0 + 60_000, [], [[2.10, 40]], []);
        feed(s, T0 + 61_000, [], [[2.10, 40]], []);
        // finestra 15s da T0+61s: il picco 800 è a T0, fuori finestra
        expect(detectPulledWalls(s, T0 + 61_000)).toHaveLength(0);
    });

    it('massimo 3 segnalazioni, ordinate per drop decrescente', () => {
        const s = newFlowState();
        feed(s, T0, [[2.0, 500], [2.02, 900], [2.04, 300], [2.06, 700]], [], []);
        feed(s, T0 + 5_000, [[2.0, 0], [2.02, 0], [2.04, 0], [2.06, 0]], [], []);
        const walls = detectPulledWalls(s, T0 + 5_000);
        expect(walls).toHaveLength(3);
        expect(walls.map(w => w.peak)).toEqual([900, 700, 500]); // il 300 escluso
    });
});

describe('womShift', () => {
    it('shift calcolato su top-3 in punti percentuali (a mano)', () => {
        const s = newFlowState();
        // baseline: back 300 / lay 100 → WOM 75%
        feed(s, T0, [[2.0, 100], [1.99, 100], [1.98, 100]], [[2.02, 100]], []);
        // adesso: back 100 / lay 300 → WOM 25% → shift −50pp
        feed(s, T0 + 31_000, [[2.0, 100]], [[2.02, 100], [2.04, 100], [2.06, 100]], []);
        expect(womShift(s, T0 + 31_000, 30_000)).toBeCloseTo(-50, 6);
    });
    it('storia insufficiente o book vuoto → null (mai inventare)', () => {
        const s = newFlowState();
        feed(s, T0, [[2.0, 100]], [[2.02, 100]], []);
        expect(womShift(s, T0 + 1_000, 30_000)).toBeNull();      // nessuna baseline
        const empty = newFlowState();
        feed(empty, T0, [], [], []);
        feed(empty, T0 + 31_000, [], [], []);
        expect(womShift(empty, T0 + 31_000, 30_000)).toBeNull(); // book vuoto
    });
});

describe('tradeSpike', () => {
    it('volume recente vs finestra precedente (a mano)', () => {
        const s = newFlowState();
        feed(s, T0, [], [], [[2.0, 0]]);                 // cum 0
        feed(s, T0 + 60_000, [], [], [[2.0, 100]]);      // baseline: +100
        feed(s, T0 + 120_000, [], [], [[2.0, 700]]);     // recente: +600
        const spike = tradeSpike(s, T0 + 120_000, 60_000);
        expect(spike).toMatchObject({ recent: 600, baseline: 100 });
        expect(spike!.ratio).toBeCloseTo(6, 6);
    });
    it('serve storia di DUE finestre → altrimenti null', () => {
        const s = newFlowState();
        feed(s, T0, [], [], [[2.0, 0]]);
        feed(s, T0 + 60_000, [], [], [[2.0, 500]]);
        expect(tradeSpike(s, T0 + 60_000, 60_000)).toBeNull();
    });
    it('baseline 0 con volume recente → ratio Infinity (mai divisione NaN)', () => {
        const s = newFlowState();
        feed(s, T0, [], [], [[2.0, 50]]);
        feed(s, T0 + 60_000, [], [], [[2.0, 50]]);      // baseline 0
        feed(s, T0 + 120_000, [], [], [[2.0, 550]]);    // recente 500
        const spike = tradeSpike(s, T0 + 120_000, 60_000);
        expect(spike!.recent).toBe(500);
        expect(spike!.ratio).toBe(Infinity);
    });
});

describe('pushFlowSample', () => {
    it('ring FIFO col cap e t non monotono sostituisce l\'ultimo', () => {
        const s = newFlowState();
        for (let i = 0; i < 10; i++) feed(s, T0 + i * 1000, [[2.0, i]], [], []);
        pushFlowSample(s, T0 + 9 * 1000, [[2.0, 99]], [], [], 5);
        expect(s.snaps.length).toBeLessThanOrEqual(5);
        expect(s.snaps[s.snaps.length - 1].back.get(2.0)).toBe(99);
    });
});
