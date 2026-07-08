import { describe, it, expect } from 'vitest';
import { pushSample, bucketCandles, type PriceSample } from './ladderChart';

describe('pushSample', () => {
    it('appende campioni validi e scarta i non-finiti', () => {
        const buf: PriceSample[] = [];
        pushSample(buf, 1000, 2.5);
        pushSample(buf, 2000, NaN);
        pushSample(buf, NaN, 2.6);
        pushSample(buf, 3000, -1);
        pushSample(buf, 4000, 2.6);
        expect(buf).toEqual([{ t: 1000, p: 2.5 }, { t: 4000, p: 2.6 }]);
    });
    it('deduplica prezzi identici ravvicinati (<1s) ma tiene quelli distanti', () => {
        const buf: PriceSample[] = [];
        pushSample(buf, 1000, 2.5);
        pushSample(buf, 1500, 2.5);  // stesso prezzo a 0.5s → dedup
        pushSample(buf, 2500, 2.5);  // stesso prezzo a 1.5s → tenuto
        expect(buf).toHaveLength(2);
    });
    it('rifiuta campioni fuori ordine temporale', () => {
        const buf: PriceSample[] = [];
        pushSample(buf, 5000, 2.5);
        pushSample(buf, 4000, 2.7);
        expect(buf).toHaveLength(1);
    });
    it('applica il cap FIFO', () => {
        const buf: PriceSample[] = [];
        for (let i = 0; i < 20; i++) pushSample(buf, i * 2000, 2 + i * 0.02, 10);
        expect(buf).toHaveLength(10);
        expect(buf[0].p).toBeCloseTo(2.2, 9); // i primi 10 sono stati espulsi
    });
});

describe('bucketCandles', () => {
    it('aggrega OHLC per bucket, in ordine temporale', () => {
        const s: PriceSample[] = [
            { t: 0, p: 2.0 }, { t: 10_000, p: 2.1 }, { t: 20_000, p: 1.9 }, { t: 29_000, p: 2.05 },
            { t: 30_000, p: 2.05 }, { t: 45_000, p: 2.3 },
        ];
        const c = bucketCandles(s, 30_000, 10);
        expect(c).toHaveLength(2);
        expect(c[0]).toEqual({ t0: 0, o: 2.0, h: 2.1, l: 1.9, c: 2.05 });
        expect(c[1]).toEqual({ t0: 30_000, o: 2.05, h: 2.3, l: 2.05, c: 2.3 });
    });
    it('tiene solo le ultime maxBuckets candele', () => {
        const s: PriceSample[] = Array.from({ length: 10 }, (_, i) => ({ t: i * 30_000, p: 2 + i * 0.1 }));
        const c = bucketCandles(s, 30_000, 3);
        expect(c).toHaveLength(3);
        expect(c[0].t0).toBe(7 * 30_000);
    });
    it('input invalidi → vuoto', () => {
        expect(bucketCandles([], 30_000, 10)).toEqual([]);
        expect(bucketCandles([{ t: 0, p: 2 }], 0, 10)).toEqual([]);
        expect(bucketCandles([{ t: 0, p: 2 }], 30_000, 0)).toEqual([]);
    });
});
