// ============================================================================
// eventPnl.test.ts — test della matematica PURA di MTM/esposizione per evento.
// MONEY-CRITICAL: coerenza verificata CONTRO lockedPnlAt (stessa aritmetica del
// green-up), prezzi mancanti/invalidi → null (mai numeri inventati).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { lockedPnlAt } from '@/lib/ladderMath';
import { positionMtm, eventMtm, eventExposure } from '@/lib/eventPnl';
import type { LivePositionRow } from '@/lib/liveOrders';

// Fabbrica di posizioni con default innocui (mirror LivePositionRow).
function pos(over: Partial<LivePositionRow>): LivePositionRow {
    return {
        id: 1, mode: 'paper', event_id: 'ev1', market_id: '1.234', selection_id: 1, handicap: 0,
        matched_if_win: 0, matched_if_lose: 0, worst_if_win: 0, worst_if_lose: 0,
        selection_exposure: 0, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
        net_position: 0, updated_at: null,
        ...over,
    };
}

describe('positionMtm', () => {
    it('W>L → greening al best LAY, identico a lockedPnlAt(lay, W, L)', () => {
        // posizione BACK vinta virtualmente: chiudo layando al best lay.
        const w = 10, l = -5, back = 2.0, lay = 2.5;
        const got = positionMtm(w, l, back, lay);
        expect(got).not.toBeNull();
        expect(got!).toBeCloseTo(lockedPnlAt(lay, w, l), 10); // -5 + 15/2.5 = 1
        expect(got!).toBeCloseTo(1, 10);
    });

    it('W<L → greening al best BACK, identico a lockedPnlAt(back, W, L)', () => {
        // posizione LAY: chiudo backando al best back.
        const w = -5, l = 10, back = 3.0, lay = 3.1;
        const got = positionMtm(w, l, back, lay);
        expect(got).not.toBeNull();
        expect(got!).toBeCloseTo(lockedPnlAt(back, w, l), 10); // 10 - 15/3 = 5
        expect(got!).toBeCloseTo(5, 10);
    });

    it('posizione piatta (|W−L|<0.01) → (W+L)/2 anche SENZA prezzi', () => {
        expect(positionMtm(5, 5, null, null)).toBeCloseTo(5, 10);
        expect(positionMtm(2.004, 2.0, null, null)).toBeCloseTo((2.004 + 2.0) / 2, 10);
        expect(positionMtm(0, 0, null, null)).toBe(0);
    });

    it('prezzo mancante/invalidо sul lato necessario → null (MAI inventare)', () => {
        expect(positionMtm(10, -5, 2.0, null)).toBeNull();      // serve il lay
        expect(positionMtm(-5, 10, null, 3.0)).toBeNull();      // serve il back
        expect(positionMtm(10, -5, 2.0, 1.0)).toBeNull();       // lay <= 1
        expect(positionMtm(10, -5, 2.0, 0.5)).toBeNull();       // lay <= 1
        expect(positionMtm(10, -5, 2.0, NaN)).toBeNull();       // non finito
        expect(positionMtm(10, -5, 2.0, Infinity)).toBeNull();  // non finito
    });

    it('W/L non finiti → null', () => {
        expect(positionMtm(NaN, -5, 2.0, 2.5)).toBeNull();
        expect(positionMtm(10, Infinity, 2.0, 2.5)).toBeNull();
    });
});

describe('eventMtm', () => {
    const prices = new Map<number, { back: number | null; lay: number | null }>([
        [1, { back: 2.0, lay: 2.5 }],
        [2, { back: 3.0, lay: 3.2 }],
        [3, { back: null, lay: null }], // book vuoto
    ]);

    it('aggrega i positionMtm delle posizioni con prezzo disponibile', () => {
        const positions = [
            pos({ selection_id: 1, matched_if_win: 10, matched_if_lose: -5 }),  // lay 2.5 → 1
            pos({ selection_id: 2, matched_if_win: -5, matched_if_lose: 10 }),  // back 3.0 → 5
        ];
        const r = eventMtm(positions, prices);
        expect(r.mtm).toBeCloseTo(1 + 5, 10);
        expect(r.priced).toBe(2);
        expect(r.unpriced).toBe(0);
    });

    it('posizioni senza prezzo → conteggiate in unpriced (la UI DEVE mostrarle)', () => {
        const positions = [
            pos({ selection_id: 1, matched_if_win: 10, matched_if_lose: -5 }),
            pos({ selection_id: 3, matched_if_win: 8, matched_if_lose: -2 }),   // book vuoto
            pos({ selection_id: 99, matched_if_win: 4, matched_if_lose: -1 }),  // assente dal priceMap
        ];
        const r = eventMtm(positions, prices);
        expect(r.priced).toBe(1);
        expect(r.unpriced).toBe(2);
        expect(r.mtm).toBeCloseTo(1, 10); // solo la posizione valutabile
    });

    it('posizioni piatte-zero (|W|,|L|<0.01) sono ignorate (né priced né unpriced)', () => {
        const positions = [
            pos({ selection_id: 1, matched_if_win: 0, matched_if_lose: 0 }),
            pos({ selection_id: 99, matched_if_win: 0.004, matched_if_lose: -0.004 }),
        ];
        const r = eventMtm(positions, prices);
        expect(r).toEqual({ mtm: 0, priced: 0, unpriced: 0 });
    });

    it('posizione già pareggiata (W≈L≠0) è valutata (W+L)/2 senza bisogno del book', () => {
        const positions = [pos({ selection_id: 99, matched_if_win: 4, matched_if_lose: 4 })];
        const r = eventMtm(positions, prices);
        expect(r.mtm).toBeCloseTo(4, 10);
        expect(r.priced).toBe(1);
        expect(r.unpriced).toBe(0);
    });

    it('lista vuota → zero pulito', () => {
        expect(eventMtm([], prices)).toEqual({ mtm: 0, priced: 0, unpriced: 0 });
    });
});

describe('eventExposure', () => {
    it('somma selection_exposure di tutte le righe', () => {
        const positions = [
            pos({ selection_exposure: 5 }),
            pos({ selection_exposure: 7.5 }),
            pos({ selection_exposure: 0 }),
        ];
        expect(eventExposure(positions)).toBeCloseTo(12.5, 10);
    });

    it('valori non finiti trattati come 0 (upper bound onesto, mai NaN in UI)', () => {
        const positions = [
            pos({ selection_exposure: 5 }),
            pos({ selection_exposure: NaN as unknown as number }),
        ];
        expect(eventExposure(positions)).toBe(5);
    });

    it('lista vuota → 0', () => {
        expect(eventExposure([])).toBe(0);
    });
});
