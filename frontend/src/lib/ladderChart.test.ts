import { describe, it, expect } from 'vitest';
import {
    pushSample, bucketCandles, type PriceSample,
    pushVolumeSample, bucketCandlesV, vwapSeries, type VolumeSample, type CandleV,
} from './ladderChart';

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

// ============================================================================
// D29 — estensioni con VOLUME (pushVolumeSample / bucketCandlesV / vwapSeries)
// ============================================================================

describe('pushVolumeSample', () => {
    it('appende campioni validi e ignora p non finito', () => {
        const buf: VolumeSample[] = [];
        pushVolumeSample(buf, 1000, 2.5, 100);
        pushVolumeSample(buf, 2000, NaN, 150);       // p non finito → ignorato
        pushVolumeSample(buf, 3000, Infinity, 160);  // p non finito → ignorato
        pushVolumeSample(buf, 4000, 2.6, 170);
        expect(buf).toEqual([
            { t: 1000, p: 2.5, v: 100 },
            { t: 4000, p: 2.6, v: 170 },
        ]);
    });
    it('accetta v null (volume ignoto)', () => {
        const buf: VolumeSample[] = [];
        pushVolumeSample(buf, 1000, 2.5, null);
        expect(buf).toEqual([{ t: 1000, p: 2.5, v: null }]);
    });
    it('deduplica quando p E v sono ENTRAMBI invariati, tiene se uno dei due cambia', () => {
        const buf: VolumeSample[] = [];
        pushVolumeSample(buf, 1000, 2.5, 100);
        pushVolumeSample(buf, 2000, 2.5, 100);   // identico → skip (dedup rumore)
        pushVolumeSample(buf, 3000, 2.5, 120);   // v cambiato → tenuto
        pushVolumeSample(buf, 4000, 2.6, 120);   // p cambiato → tenuto
        expect(buf.map((s) => s.t)).toEqual([1000, 3000, 4000]);
    });
    it('deduplica anche i null identici consecutivi', () => {
        const buf: VolumeSample[] = [];
        pushVolumeSample(buf, 1000, 2.5, null);
        pushVolumeSample(buf, 2000, 2.5, null);  // p e v (null) invariati → skip
        expect(buf).toHaveLength(1);
    });
    it('rifiuta campioni fuori ordine temporale (come pushSample)', () => {
        const buf: VolumeSample[] = [];
        pushVolumeSample(buf, 5000, 2.5, 100);
        pushVolumeSample(buf, 4000, 2.7, 110);
        expect(buf).toHaveLength(1);
    });
    it('applica il cap FIFO custom', () => {
        const buf: VolumeSample[] = [];
        for (let i = 0; i < 20; i++) pushVolumeSample(buf, i * 1000, 2 + i * 0.02, i, 10);
        expect(buf).toHaveLength(10);
        expect(buf[0].v).toBe(10); // i primi 10 sono stati espulsi
    });
});

describe('bucketCandlesV', () => {
    it('OHLC per bucket + volume = delta del tv cumulato tra bucket', () => {
        const s: VolumeSample[] = [
            { t: 0, p: 2.0, v: 100 },
            { t: 10_000, p: 2.1, v: 150 },
            { t: 30_000, p: 2.05, v: 180 },
            { t: 65_000, p: 2.2, v: 180 },   // tv fermo → volume 0
        ];
        const c = bucketCandlesV(s, 30_000, 10);
        expect(c).toHaveLength(3);
        expect(c[0]).toEqual({ t0: 0, o: 2.0, h: 2.1, l: 2.0, c: 2.1, v: 50 });   // primo bucket: delta intra-bucket
        expect(c[1]).toEqual({ t0: 30_000, o: 2.05, h: 2.05, l: 2.05, c: 2.05, v: 30 });
        expect(c[2]).toEqual({ t0: 60_000, o: 2.2, h: 2.2, l: 2.2, c: 2.2, v: 0 });
    });
    it('reset del tv (valore che scende) → volume MAI negativo, delta successivi dal nuovo baseline', () => {
        const s: VolumeSample[] = [
            { t: 0, p: 2.0, v: 500 },
            { t: 30_000, p: 2.1, v: 50 },    // riavvio stream: tv riparte
            { t: 60_000, p: 2.2, v: 80 },
        ];
        const c = bucketCandlesV(s, 30_000, 10);
        expect(c.map((x) => x.v)).toEqual([0, 0, 30]);
        for (const x of c) expect(x.v).toBeGreaterThanOrEqual(0);
    });
    it('bucket con v ignoto (tutti null) → volume 0, il baseline sopravvive per il bucket dopo', () => {
        const s: VolumeSample[] = [
            { t: 0, p: 2.0, v: 100 },
            { t: 30_000, p: 2.1, v: null },  // volume ignoto per il bucket 1
            { t: 60_000, p: 2.2, v: 130 },
        ];
        const c = bucketCandlesV(s, 30_000, 10);
        expect(c.map((x) => x.v)).toEqual([0, 0, 30]);
    });
    it('nel bucket conta l\'ULTIMO v noto (i null in coda non lo cancellano)', () => {
        const s: VolumeSample[] = [
            { t: 0, p: 2.0, v: 100 },
            { t: 30_000, p: 2.1, v: 120 },
            { t: 35_000, p: 2.15, v: null }, // null dopo un v noto nello stesso bucket
        ];
        const c = bucketCandlesV(s, 30_000, 10);
        expect(c[1].v).toBe(20);
    });
    it('maxBuckets: i delta sono calcolati PRIMA del taglio (la prima candela visibile ha il volume giusto)', () => {
        const s: VolumeSample[] = Array.from({ length: 6 }, (_, i) => ({
            t: i * 30_000, p: 2 + i * 0.1, v: 100 + i * 10,
        }));
        const c = bucketCandlesV(s, 30_000, 2);
        expect(c).toHaveLength(2);
        expect(c[0].t0).toBe(4 * 30_000);
        expect(c[0].v).toBe(10); // delta vs bucket 3 (fuori finestra), NON vs zero
        expect(c[1].v).toBe(10);
    });
    it('bucket vuoti non producono candele; input invalidi → vuoto', () => {
        const s: VolumeSample[] = [
            { t: 0, p: 2.0, v: 10 },
            { t: 90_000, p: 2.5, v: 40 },    // gap di 2 bucket
        ];
        const c = bucketCandlesV(s, 30_000, 10);
        expect(c.map((x) => x.t0)).toEqual([0, 90_000]);
        expect(c[1].v).toBe(30);
        expect(bucketCandlesV([], 30_000, 10)).toEqual([]);
        expect(bucketCandlesV(s, 0, 10)).toEqual([]);
        expect(bucketCandlesV(s, 30_000, 0)).toEqual([]);
    });
});

describe('vwapSeries', () => {
    it('null finché Σv=0, poi VWAP cumulato sul typical price', () => {
        const candles: CandleV[] = [
            { t0: 0, o: 2, h: 2, l: 2, c: 2, v: 0 },       // nessun volume → null (mai inventare VWAP)
            { t0: 1, o: 2, h: 3, l: 1, c: 2, v: 10 },       // typical = 2
            { t0: 2, o: 2, h: 2, l: 2, c: 2, v: 0 },        // Σ invariata → VWAP invariato
            { t0: 3, o: 4, h: 4, l: 4, c: 4, v: 10 },       // typical = 4 → vwap = 3
        ];
        const w = vwapSeries(candles);
        expect(w[0]).toBeNull();
        expect(w[1]).toBeCloseTo(2, 9);
        expect(w[2]).toBeCloseTo(2, 9);
        expect(w[3]).toBeCloseTo(3, 9);
    });
    it('tutte le candele senza volume → tutti null; input vuoto → []', () => {
        const candles: CandleV[] = [
            { t0: 0, o: 2, h: 2, l: 2, c: 2, v: 0 },
            { t0: 1, o: 3, h: 3, l: 3, c: 3, v: 0 },
        ];
        expect(vwapSeries(candles)).toEqual([null, null]);
        expect(vwapSeries([])).toEqual([]);
    });
});
