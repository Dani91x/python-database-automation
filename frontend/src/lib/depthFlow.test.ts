import { describe, it, expect } from 'vitest';
import { sideTotals, cumulativeLevels, pushDepthSample, depthDelta, type DepthSample } from './depthFlow';

describe('sideTotals', () => {
    it('somma le size di livelli validi', () => {
        expect(sideTotals([[2.0, 100], [2.02, 50.5], [2.04, 10]])).toBeCloseTo(160.5, 9);
    });
    it('book vuoto / null / undefined → 0 (mai NaN)', () => {
        expect(sideTotals([])).toBe(0);
        expect(sideTotals(null)).toBe(0);
        expect(sideTotals(undefined)).toBe(0);
    });
    it('ignora livelli malformati e size non finite', () => {
        const levels = [
            [2.0, 100],
            [2.02, NaN],           // size NaN → ignorato
            [2.04, Infinity],      // size infinita → ignorata
            null,                  // livello nullo → ignorato
            [2.06],                // livello monco → ignorato
            [2.08, -5],            // size negativa → ignorata (denaro non può essere <0)
            [2.10, 20],
        ] as unknown as ReadonlyArray<readonly [number, number]>;
        expect(sideTotals(levels)).toBeCloseTo(120, 9);
        expect(Number.isFinite(sideTotals(levels))).toBe(true);
    });
});

describe('cumulativeLevels', () => {
    it('cumula progressivamente dal best (primo livello)', () => {
        expect(cumulativeLevels([[2.0, 100], [2.02, 50], [2.04, 25]])).toEqual([
            { price: 2.0, size: 100, cum: 100 },
            { price: 2.02, size: 50, cum: 150 },
            { price: 2.04, size: 25, cum: 175 },
        ]);
    });
    it('null / undefined / vuoto → array vuoto', () => {
        expect(cumulativeLevels(null)).toEqual([]);
        expect(cumulativeLevels(undefined)).toEqual([]);
        expect(cumulativeLevels([])).toEqual([]);
    });
    it('salta i livelli malformati senza rompere la cumulata', () => {
        const levels = [
            [2.0, 100],
            [NaN, 50],             // prezzo NaN → saltato
            [2.04, NaN],           // size NaN → saltata
            [2.06, 25],
        ] as unknown as ReadonlyArray<readonly [number, number]>;
        expect(cumulativeLevels(levels)).toEqual([
            { price: 2.0, size: 100, cum: 100 },
            { price: 2.06, size: 25, cum: 125 },
        ]);
    });
});

describe('pushDepthSample', () => {
    it('appende sempre (anche back/lay invariati: serve la storia per il delta)', () => {
        const buf: DepthSample[] = [];
        pushDepthSample(buf, 1000, 500, 300);
        pushDepthSample(buf, 2000, 500, 300); // invariato → comunque appeso
        expect(buf).toEqual([
            { t: 1000, back: 500, lay: 300 },
            { t: 2000, back: 500, lay: 300 },
        ]);
    });
    it('t <= ultimo t → sostituisce l\'ultimo campione (mai storia fuori ordine)', () => {
        const buf: DepthSample[] = [];
        pushDepthSample(buf, 1000, 500, 300);
        pushDepthSample(buf, 2000, 510, 310);
        pushDepthSample(buf, 2000, 520, 320); // stesso t → replace
        expect(buf).toHaveLength(2);
        expect(buf[1]).toEqual({ t: 2000, back: 520, lay: 320 });
        pushDepthSample(buf, 1500, 530, 330); // t indietro → replace dell'ultimo
        expect(buf).toHaveLength(2);
        expect(buf[1]).toEqual({ t: 1500, back: 530, lay: 330 });
    });
    it('scarta input non finiti (t/back/lay)', () => {
        const buf: DepthSample[] = [];
        pushDepthSample(buf, NaN, 500, 300);
        pushDepthSample(buf, 1000, NaN, 300);
        pushDepthSample(buf, 1000, 500, Infinity);
        expect(buf).toEqual([]);
    });
    it('applica il cap FIFO (default 600)', () => {
        const buf: DepthSample[] = [];
        for (let i = 0; i < 700; i++) pushDepthSample(buf, i * 1000, i, i * 2);
        expect(buf).toHaveLength(600);
        expect(buf[0]).toEqual({ t: 100_000, back: 100, lay: 200 }); // i primi 100 espulsi
    });
    it('rispetta un cap custom', () => {
        const buf: DepthSample[] = [];
        for (let i = 0; i < 10; i++) pushDepthSample(buf, i * 1000, i, i, 4);
        expect(buf).toHaveLength(4);
        expect(buf[0].t).toBe(6000);
    });
});

describe('depthDelta', () => {
    const mk = (rows: Array<[number, number, number]>): DepthSample[] =>
        rows.map(([t, back, lay]) => ({ t, back, lay }));

    it('buffer vuoto → null (mai delta inventato)', () => {
        expect(depthDelta([], 10_000, 5000)).toBeNull();
    });
    it('storia insufficiente (nessun campione con t <= now−windowMs) → null', () => {
        const buf = mk([[8000, 500, 300], [9000, 510, 310]]);
        expect(depthDelta(buf, 10_000, 5000)).toBeNull(); // cutoff 5000: nessun campione così vecchio
    });
    it('delta positivo = denaro ENTRATO nella finestra', () => {
        const buf = mk([[1000, 500, 300], [6000, 650, 380]]);
        expect(depthDelta(buf, 6000, 5000)).toEqual({ back: 150, lay: 80 }); // baseline: t=1000
    });
    it('delta negativo = denaro USCITO dalla finestra', () => {
        const buf = mk([[1000, 500, 300], [6000, 420, 250]]);
        expect(depthDelta(buf, 6000, 5000)).toEqual({ back: -80, lay: -50 });
    });
    it('baseline = campione più RECENTE con t <= now−windowMs (non il più vecchio)', () => {
        const buf = mk([[0, 100, 100], [2000, 200, 200], [4000, 300, 300], [9000, 500, 500]]);
        // cutoff = 10000 − 5000 = 5000 → baseline t=4000 (non t=0)
        expect(depthDelta(buf, 10_000, 5000)).toEqual({ back: 200, lay: 200 });
    });
    it('baseline esattamente al cutoff (t == now−windowMs) è valida', () => {
        const buf = mk([[5000, 400, 200], [10_000, 450, 260]]);
        expect(depthDelta(buf, 10_000, 5000)).toEqual({ back: 50, lay: 60 });
    });
    it('input non finiti → null', () => {
        const buf = mk([[1000, 500, 300], [6000, 650, 380]]);
        expect(depthDelta(buf, NaN, 5000)).toBeNull();
        expect(depthDelta(buf, 6000, NaN)).toBeNull();
    });
});
