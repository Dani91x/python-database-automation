// Test logica PURA di riskMath.ts (anteprime UI del risk engine). Nessuna rete:
// verifichiamo lo snap al ladder Betfair, la DIREZIONE dei tick per offset/stop e
// il book percentage. Vettori scelti sui confini di banda (dove sbaglia il naive).
import { describe, it, expect } from 'vitest';
import {
    nearestTick,
    ticksAway,
    offsetTargetPrice,
    stopTriggerPrice,
    bookPercentage,
} from './riskMath';

describe('nearestTick — snap al ladder Betfair', () => {
    it('quote già valide restano invariate', () => {
        expect(nearestTick(2.0)).toBe(2.0);
        expect(nearestTick(3.0)).toBe(3.0);
        expect(nearestTick(1.01)).toBe(1.01);
    });
    it('snappa al tick valido più vicino', () => {
        expect(nearestTick(2.031)).toBe(2.04);   // banda .02: 2.02,2.04
        expect(nearestTick(3.03)).toBe(3.05);    // banda .05
        expect(nearestTick(5.04)).toBe(5.0);     // banda .1
    });
    it('clampa agli estremi del ladder', () => {
        expect(nearestTick(0.5)).toBe(1.01);
        expect(nearestTick(99999)).toBe(1000);
    });
});

describe('ticksAway — passi contigui anche a cavallo di banda', () => {
    it('+1 tick sale, -1 tick scende (dentro banda)', () => {
        expect(ticksAway(2.5, 1)).toBe(2.52);
        expect(ticksAway(2.5, -1)).toBe(2.48);
    });
    it('attraversa il confine di banda con lo step corretto', () => {
        // 1.99 → +1 = 2.0 (fine banda .01) → +1 ancora = 2.02 (inizio banda .02)
        expect(ticksAway(1.99, 1)).toBe(2.0);
        expect(ticksAway(2.0, 1)).toBe(2.02);
        expect(ticksAway(2.02, -1)).toBe(2.0);
        expect(ticksAway(2.0, -1)).toBe(1.99);
    });
    it('0 tick = snap puro', () => {
        expect(ticksAway(4.03, 0)).toBe(4.0);
    });
});

describe('offsetTargetPrice — direzione presa di profitto', () => {
    it('BACK chiude PIÙ BASSO (ticks giù)', () => {
        expect(offsetTargetPrice('back', 3.0, 2)).toBe(2.96); // 3.0 →2.98→2.96
    });
    it('LAY chiude PIÙ ALTO (ticks su)', () => {
        expect(offsetTargetPrice('lay', 3.0, 2)).toBe(3.1);   // 3.0 →3.05→3.10
    });
    it('la magnitudine dei tick è sempre positiva', () => {
        expect(offsetTargetPrice('back', 3.0, -2)).toBe(offsetTargetPrice('back', 3.0, 2));
    });
});

describe('stopTriggerPrice — direzione movimento avverso', () => {
    it('BACK scatta PIÙ ALTO (prezzo sale = perdita)', () => {
        expect(stopTriggerPrice('back', 3.0, 2)).toBe(3.1);
    });
    it('LAY scatta PIÙ BASSO (prezzo scende = perdita)', () => {
        expect(stopTriggerPrice('lay', 3.0, 2)).toBe(2.96);
    });
    it('offset e stop vanno in direzioni OPPOSTE per lo stesso lato', () => {
        const off = offsetTargetPrice('back', 3.0, 2);
        const stop = stopTriggerPrice('back', 3.0, 2);
        expect(stop).toBeGreaterThan(off);
    });
});

describe('bookPercentage — overround Σ(1/quota)·100', () => {
    it('mercato equo a 2 vie = 100%', () => {
        expect(bookPercentage([2.0, 2.0])).toBe(100);
    });
    it('3 vie a quota 3.0 = 100%', () => {
        expect(bookPercentage([3.0, 3.0, 3.0])).toBe(100);
    });
    it('margine del banco > 100', () => {
        expect(bookPercentage([1.9, 1.9])).toBeGreaterThan(100);
    });
    it('ignora quote non valide (≤1) e input vuoto → 0', () => {
        expect(bookPercentage([])).toBe(0);
        expect(bookPercentage([1.0, 2.0])).toBe(50); // solo 2.0 conta
    });
});
