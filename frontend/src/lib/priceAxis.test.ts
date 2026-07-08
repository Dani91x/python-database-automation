import { describe, it, expect } from 'vitest';
import {
    TOTAL_TICKS, MIN_PRICE, MAX_PRICE, priceToIndex, indexToPrice, moneyProfile,
} from './priceAxis';
import { roundToTick, tickUp } from './matching';

describe('scala tick Betfair (priceAxis)', () => {
    it('ha esattamente 350 prezzi validi da 1.01 a 1000', () => {
        expect(TOTAL_TICKS).toBe(350);
        expect(indexToPrice(0)).toBe(MIN_PRICE);
        expect(indexToPrice(TOTAL_TICKS - 1)).toBe(MAX_PRICE);
    });

    it('indexToPrice∘priceToIndex è identità sui prezzi validi', () => {
        for (const p of [1.01, 1.5, 2.0, 2.02, 3.0, 3.05, 4.1, 6.2, 10.5, 20, 32, 55, 100, 550, 1000]) {
            expect(indexToPrice(priceToIndex(p))).toBe(p);
        }
    });

    it('è coerente con la scala tick di matching.ts su TUTTO il range', () => {
        // percorre l'intera scala con tickUp e verifica la biiezione indice↔prezzo
        let p = 1.01;
        for (let i = 0; i < TOTAL_TICKS; i++) {
            expect(priceToIndex(p)).toBe(i);
            expect(indexToPrice(i)).toBeCloseTo(p, 9);
            const nx = tickUp(p, 1);
            if (nx <= p) break; // fine scala
            p = nx;
        }
        expect(p).toBe(1000);
    });

    it('clampa i prezzi fuori range e arrotonda i prezzi off-tick', () => {
        expect(priceToIndex(0.5)).toBe(0);
        expect(priceToIndex(5000)).toBe(TOTAL_TICKS - 1);
        // 2.03 non è un tick valido (banda 0.02): va al tick più vicino, come roundToTick
        expect(indexToPrice(priceToIndex(2.03))).toBe(roundToTick(2.03));
    });

    it('indexToPrice clampa indici fuori range', () => {
        expect(indexToPrice(-5)).toBe(MIN_PRICE);
        expect(indexToPrice(9999)).toBe(MAX_PRICE);
    });
});

describe('moneyProfile', () => {
    it('aggrega le size nelle zone giuste', () => {
        const back: [number, number][] = [[1.01, 100], [1.02, 50]];   // inizio scala → zona 0
        const lay: [number, number][] = [[1000, 200]];                 // fine scala → ultima zona
        const zones = moneyProfile([back, lay], 10);
        expect(zones).toHaveLength(10);
        expect(zones[0]).toBe(150);
        expect(zones[9]).toBe(200);
        expect(zones.slice(1, 9).every(v => v === 0)).toBe(true);
    });
    it('scarta size non finite o nulle e sorgenti assenti', () => {
        const dirty: [number, number][] = [[2.0, NaN], [2.0, 0], [2.0, -5], [NaN, 10]];
        expect(moneyProfile([dirty, undefined], 5).every(v => v === 0)).toBe(true);
    });
    it('nZones minimo 1', () => {
        expect(moneyProfile([[[2, 10]]], 0)).toEqual([10]);
    });
});
