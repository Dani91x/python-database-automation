import { describe, it, expect } from 'vitest';
import type { BookSnapshot } from './matching';
import {
    createTrainingApi, frameToLadderRow, selectionExposures, womOf,
    type TrainingContext,
} from './trainingLadder';

const T0 = 1_000_000;

// book: back best 2.0 (€100), lay best 2.02 (€100)
function snap(ts: number, over: Partial<BookSnapshot> = {}): BookSnapshot {
    return {
        ts,
        back: [[2.0, 100], [1.99, 100]],
        lay: [[2.02, 100], [2.04, 100]],
        ltp: 2.0, tv: 500, trd: [[2.0, 500]], status: 'OPEN',
        ...over,
    };
}

function makeCtx(snaps: BookSnapshot[], nowRef: { t: number }, inplay = false): TrainingContext {
    return {
        eventId: 'ev1',
        getSnaps: () => snaps,
        getNow: () => nowRef.t,
        isInplayAt: () => inplay,
    };
}

describe('womOf / frameToLadderRow', () => {
    it('WOM dai top-3 livelli; book vuoto → 50/50', () => {
        expect(womOf([[2.0, 300]], [[2.02, 100]]).back_pct).toBeCloseTo(75, 6);
        expect(womOf([], []).back_pct).toBe(50);
    });
    it('converte il frame replay nella riga LadderView (nomi dal catalogo)', () => {
        const row = frameToLadderRow({
            eventId: 'ev1', marketId: '1.5', marketType: 'MATCH_ODDS', marketName: 'Match Odds',
            status: 'OPEN', nowMs: T0,
            ladder: { 11: { back: [[2.0, 100]], lay: [[2.02, 50]], ltp: 2.0, tv: 500, trd: [[2.0, 500]] } },
            names: new Map([[11, 'Casa']]),
        });
        expect(row.market_id).toBe('1.5');
        expect(row.ladder?.selections).toHaveLength(1);
        const sel = row.ladder!.selections[0];
        expect(sel.selection_id).toBe(11);
        expect(sel.name).toBe('Casa');
        expect(sel.back).toEqual([[2.0, 100]]);
        expect(sel.wom.back_pct).toBeCloseTo(66.67, 1);
    });
});

describe('createTrainingApi — place/cancel/mirror', () => {
    it('place PRE-MATCH: taker fill immediato al book, mirror coerente', async () => {
        const now = { t: T0 };
        const api = createTrainingApi(makeCtx([snap(T0)], now));
        const res = await api.send({
            action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.0, size: 10, persistence: 'LAPSE',
        });
        expect(res.ok).toBe(true);
        expect(res.size_matched).toBe(10);            // back 2.0 contro €100 disponibili
        expect(res.average_price_matched).toBe(2.0);
        const orders = await api.fetchOrders('1.5', 'paper');
        expect(orders).toHaveLength(1);
        expect(orders[0].status).toBe('EXECUTION_COMPLETE');
        const pos = await api.fetchPositions('1.5', 'paper');
        // a mano: back €10 @ 2.0 → if_win +10, if_lose −10
        expect(pos[0].matched_if_win).toBe(10);
        expect(pos[0].matched_if_lose).toBe(-10);
        expect(pos[0].net_position).toBe(10);
        expect(pos[0].selection_exposure).toBe(10);
    });

    it('IN-PLAY: bet-delay reale → PENDING prima del delay, fill dopo', async () => {
        const now = { t: T0 };
        const snaps = [snap(T0), snap(T0 + 6_000)];
        const api = createTrainingApi(makeCtx(snaps, now, true));
        const res = await api.send({
            action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.0, size: 10, persistence: 'LAPSE',
        });
        expect(res.ok).toBe(true);
        expect(res.size_matched).toBe(0);              // delay 5s: non ancora al matcher
        expect(res.detail).toMatch(/bet-delay 5s/);
        now.t = T0 + 6_000;                            // dopo il delay
        const orders = await api.fetchOrders('1.5', 'paper');
        expect(orders[0].size_matched).toBe(10);
    });

    it('stake sotto €2 → RIFIUTATO con errore esplicito (mai fill finti)', async () => {
        const api = createTrainingApi(makeCtx([snap(T0)], { t: T0 }));
        const res = await api.send({
            action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.0, size: 1.5, persistence: 'LAPSE',
        });
        expect(res.ok).toBe(false);
        expect(res.error).toMatch(/sotto il minimo/);
    });

    it('cancel di un resting → CANCELLED nel mirror, size_remaining 0', async () => {
        const now = { t: T0 };
        // book senza liquidità al limite → l'ordine resta OPEN; serve un frame DOPO il
        // cancel perché il matcher lo applichi (coerente col comportamento a snapshot).
        const api = createTrainingApi(makeCtx(
            [snap(T0, { back: [[1.9, 100]] }), snap(T0 + 2_000, { back: [[1.9, 100]] })], now));
        const res = await api.send({
            action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.5, size: 10, persistence: 'LAPSE',
        });
        expect(res.size_matched).toBe(0);
        const orders1 = await api.fetchOrders('1.5', 'paper');
        expect(orders1[0].status).toBe('EXECUTABLE');
        expect(orders1[0].size_remaining).toBe(10);
        now.t = T0 + 1_000;
        await api.send({ action: 'cancel', mode: 'paper', market_id: '1.5', bet_id: res.bet_id! });
        now.t = T0 + 2_000; // il frame successivo applica il cancel
        const orders2 = await api.fetchOrders('1.5', 'paper');
        expect(orders2[0].status).toBe('EXECUTION_COMPLETE');
        expect(orders2[0].size_remaining).toBe(0);
        expect(orders2[0].size_cancelled).toBe(10);
    });

    it('azione non supportata → errore esplicito, mai un ok bugiardo', async () => {
        const api = createTrainingApi(makeCtx([snap(T0)], { t: T0 }));
        const res = await api.send({ action: 'dutch', mode: 'paper' });
        expect(res.ok).toBe(false);
        expect(res.error).toMatch(/non supportata/);
    });
});

describe('createTrainingApi — green-up simulato (ordine vero, non magia)', () => {
    it('chiude una posizione back con un LAY al best: P&L equalizzato (a mano)', async () => {
        const now = { t: T0 };
        const api = createTrainingApi(makeCtx([snap(T0)], now));
        // apri: back €10 @ 2.0 (fill immediato) → if_win +10, if_lose −10
        await api.send({
            action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.0, size: 10, persistence: 'LAPSE',
        });
        now.t = T0 + 1_000;
        // green-up: diff=20 → lay €(20/2.02)=9.90 @ 2.02 (best lay), fill immediato
        const res = await api.greenup!({ marketId: '1.5', selectionId: 11, mode: 'paper', handicap: 0 });
        expect(res.ok).toBe(true);
        const pos = await api.fetchPositions('1.5', 'paper');
        // a mano: if_win = 10 − 9.9·1.02 = −0.098→−0.1 · if_lose = −10 + 9.9 = −0.1
        expect(pos[0].matched_if_win).toBeCloseTo(-0.1, 2);
        expect(pos[0].matched_if_lose).toBeCloseTo(-0.1, 2);
    });

    it('book vuoto → errore esplicito (mai un cash-out inventato)', async () => {
        const now = { t: T0 };
        const api = createTrainingApi(makeCtx([snap(T0)], now));
        await api.send({
            action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.0, size: 10, persistence: 'LAPSE',
        });
        // dal T0+1s in poi il book è VUOTO
        const ctx2 = makeCtx([snap(T0), snap(T0 + 1_000, { back: [], lay: [] })], now);
        const api2 = createTrainingApi(ctx2);
        await api2.send({
            action: 'place', mode: 'paper', market_id: '1.5', selection_id: 11,
            handicap: 0, side: 'back', order_type: 'LIMIT', price: 2.0, size: 10, persistence: 'LAPSE',
        });
        now.t = T0 + 1_000;
        const res = await api2.greenup!({ marketId: '1.5', selectionId: 11, mode: 'paper', handicap: 0 });
        expect(res.ok).toBe(false);
        expect(res.error).toMatch(/book vuoto/);
    });

    it('posizione piatta → nessun ordine', async () => {
        const api = createTrainingApi(makeCtx([snap(T0)], { t: T0 }));
        const res = await api.greenup!({ marketId: '1.5', selectionId: 11, mode: 'paper', handicap: 0 });
        expect(res.ok).toBe(true);
        expect(res.detail).toMatch(/piatta/);
    });
});

describe('selectionExposures', () => {
    it('math a mano: back+lay misti', () => {
        // back €10@3.0 (fill) → +20/−10 · lay €5@2.0 (fill) → −5/+5 ⇒ if_win 15, if_lose −5
        const mk = (side: 'back' | 'lay', price: number, size: number) => ({
            order: { id: 1, bet_id: 'T1', market_id: '1.5', selection_id: 11,
                req: { side, limitPrice: price, stake: size, placedTs: T0, inPlay: false } },
            res: { side, limitPrice: price, requested: size, matched: size, avgPrice: price,
                remaining: 0, fills: [{ price, size, ts: T0, taker: true }],
                status: 'MATCHED', effectiveTs: T0 },
        }) as any;
        const e = selectionExposures([mk('back', 3.0, 10), mk('lay', 2.0, 5)], '1.5', 11);
        expect(e.ifWin).toBe(15);
        expect(e.ifLose).toBe(-5);
        expect(e.net).toBe(5);
    });
});
