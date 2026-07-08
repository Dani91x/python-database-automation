import { beforeEach, describe, it, expect } from 'vitest';
import {
    MAX_SERVANTS, normalizeServants, loadServants, saveServants, upsertServant,
    removeServant, resolveStepPrice, servantLabel, type Servant, type ServantStep,
} from './servants';
import { tickUp, tickDown } from './matching';

const tickStep = (p: number, n: number) => (n >= 0 ? tickUp(p, n) : tickDown(p, -n));

const mkServant = (slot: number, steps?: ServantStep[]): Servant => ({
    slot,
    name: `M${slot}`,
    steps: steps ?? [{ kind: 'place', side: 'back', price: 'best', stake: 'current' }],
});

describe('servants — normalizzazione', () => {
    it('scarta slot fuori range, duplicati e step malformati', () => {
        const raw = [
            mkServant(1),
            mkServant(1),                        // slot duplicato
            mkServant(0), mkServant(10),         // fuori range
            { slot: 2, name: 'X', steps: [{ kind: 'boh' }, { kind: 'greenup' }] },
            { slot: 3, name: 'vuota', steps: [{ kind: 'boh' }] },  // resta senza step → scartata
            null, 'x',
        ];
        const norm = normalizeServants(raw);
        expect(norm.map(s => s.slot)).toEqual([1, 2]);
        expect(norm[1].steps).toEqual([{ kind: 'greenup' }]);
    });

    it('valida i place: side/price/stake', () => {
        const ok = normalizeServants([{
            slot: 1, name: 'ok', steps: [
                { kind: 'place', side: 'lay', price: { ticksFromBest: 3 }, stake: 12.345 },
                { kind: 'place', side: 'back', price: 'ltp', stake: 'current' },
                { kind: 'place', side: 'back', price: { ticksFromBest: 99 }, stake: 5 }, // ±20 max → scartato
                { kind: 'place', side: 'back', price: 'best', stake: -5 },               // stake ≤ 0 → scartato
            ],
        }]);
        expect(ok[0].steps).toHaveLength(2);
        expect(ok[0].steps[0]).toEqual({ kind: 'place', side: 'lay', price: { ticksFromBest: 3 }, stake: 12.35 });
    });

    it('cancel_side valida il lato', () => {
        const norm = normalizeServants([{
            slot: 1, name: 'c', steps: [
                { kind: 'cancel_side', side: 'both' },
                { kind: 'cancel_side', side: 'su' },
            ],
        }]);
        expect(norm[0].steps).toEqual([{ kind: 'cancel_side', side: 'both' }]);
    });
});

describe('servants — persistenza e CRUD', () => {
    beforeEach(() => localStorage.clear());

    it('round-trip save/load', () => {
        const list = [mkServant(1), mkServant(9)];
        expect(saveServants(list)).toBe(true);
        expect(loadServants()).toEqual(list);
    });

    it('upsert sostituisce lo slot, remove lo toglie', () => {
        let list = [mkServant(1)];
        list = upsertServant(list, mkServant(1, [{ kind: 'greenup' }]));
        expect(list).toHaveLength(1);
        expect(list[0].steps).toEqual([{ kind: 'greenup' }]);
        list = upsertServant(list, mkServant(2));
        expect(list.map(s => s.slot)).toEqual([1, 2]);
        expect(removeServant(list, 1).map(s => s.slot)).toEqual([2]);
    });

    it('storage corrotto → []', () => {
        localStorage.setItem('servants:v1', '{rotto');
        expect(loadServants()).toEqual([]);
    });
});

describe('resolveStepPrice', () => {
    const book = { bestBack: 3.0, bestLay: 3.05, ltp: 3.0 };

    it('best/ltp', () => {
        expect(resolveStepPrice({ kind: 'place', side: 'back', price: 'best', stake: 'current' }, book, tickStep)).toBe(3.0);
        expect(resolveStepPrice({ kind: 'place', side: 'lay', price: 'best', stake: 'current' }, book, tickStep)).toBe(3.05);
        expect(resolveStepPrice({ kind: 'place', side: 'back', price: 'ltp', stake: 'current' }, book, tickStep)).toBe(3.0);
    });

    it('ticksFromBest: back sale, lay scende (meno aggressivi)', () => {
        expect(resolveStepPrice({ kind: 'place', side: 'back', price: { ticksFromBest: 2 }, stake: 5 }, book, tickStep)).toBe(3.1);
        // 3.05 → 3.00 (banda 0.05) → 2.98 (banda 0.02): il tick step cambia sotto quota 3
        expect(resolveStepPrice({ kind: 'place', side: 'lay', price: { ticksFromBest: 2 }, stake: 5 }, book, tickStep)).toBe(2.98);
    });

    it('book vuoto → null (mai piazzare al buio)', () => {
        expect(resolveStepPrice(
            { kind: 'place', side: 'back', price: 'best', stake: 5 },
            { bestBack: null, bestLay: null, ltp: null }, tickStep,
        )).toBeNull();
    });
});

describe('servantLabel', () => {
    it('descrive la sequenza in modo leggibile', () => {
        const s = mkServant(3, [
            { kind: 'place', side: 'back', price: { ticksFromBest: 2 }, stake: 10 },
            { kind: 'greenup' },
        ]);
        expect(servantLabel(s)).toBe('3· M3: BACK €10@+2t → green-up');
    });
});

it('MAX_SERVANTS = 9 (hotkey 1-9)', () => {
    expect(MAX_SERVANTS).toBe(9);
});
