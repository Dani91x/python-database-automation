import { beforeEach, describe, it, expect } from 'vitest';
import {
    MAX_SLOTS, slotId, normalizeSlots, addSlot, removeSlot, loadSlots, saveSlots,
    type LadderSlot,
} from './multiLadder';

const mkSlot = (n: number, sport = 'calcio'): Omit<LadderSlot, 'id'> => ({
    sport, eventId: `ev${n}`, marketId: `1.${n}`, marketName: `M${n}`, eventName: `E${n}`,
});

describe('multiLadder — layout puro', () => {
    it('addSlot aggiunge con id deterministico e deduplica', () => {
        let slots: LadderSlot[] = [];
        slots = addSlot(slots, mkSlot(1));
        expect(slots).toHaveLength(1);
        expect(slots[0].id).toBe(slotId('calcio', '1.1'));
        const again = addSlot(slots, mkSlot(1));
        expect(again).toBe(slots); // duplicato → STESSA referenza (esito testabile)
    });

    it('stesso mercato su sport diversi = slot distinti', () => {
        let slots: LadderSlot[] = [];
        slots = addSlot(slots, mkSlot(1, 'calcio'));
        slots = addSlot(slots, mkSlot(1, 'tennis'));
        expect(slots).toHaveLength(2);
    });

    it('rispetta il cap MAX_SLOTS', () => {
        let slots: LadderSlot[] = [];
        for (let i = 0; i < MAX_SLOTS + 3; i++) slots = addSlot(slots, mkSlot(i));
        expect(slots).toHaveLength(MAX_SLOTS);
    });

    it('removeSlot rimuove per id', () => {
        let slots: LadderSlot[] = [];
        slots = addSlot(slots, mkSlot(1));
        slots = addSlot(slots, mkSlot(2));
        slots = removeSlot(slots, slotId('calcio', '1.1'));
        expect(slots).toHaveLength(1);
        expect(slots[0].marketId).toBe('1.2');
    });

    it('normalizeSlots scarta voci malformate/duplicate e ricalcola gli id', () => {
        const raw = [
            { sport: 'calcio', eventId: 'e', marketId: '1.9', marketName: 'X', eventName: 'Y', id: 'FASULLO' },
            { sport: 'calcio', eventId: 'e', marketId: '1.9' },       // duplicato (stesso id)
            { sport: '', eventId: 'e', marketId: '1.8' },             // sport mancante
            null, 42, 'x',
            { sport: 'tennis', eventId: 'e2', marketId: '1.7', p1: 'Sinner', p2: 'Alcaraz' },
        ];
        const norm = normalizeSlots(raw);
        expect(norm).toHaveLength(2);
        expect(norm[0].id).toBe(slotId('calcio', '1.9'));
        expect(norm[1].p1).toBe('Sinner');
    });

    it('normalizeSlots su input non-array → []', () => {
        expect(normalizeSlots(null)).toEqual([]);
        expect(normalizeSlots({})).toEqual([]);
    });
});

describe('multiLadder — persistenza', () => {
    beforeEach(() => localStorage.clear());

    it('round-trip save/load', () => {
        let slots: LadderSlot[] = [];
        slots = addSlot(slots, mkSlot(1));
        slots = addSlot(slots, mkSlot(2, 'tennis'));
        expect(saveSlots(slots)).toBe(true);
        expect(loadSlots()).toEqual(slots);
    });

    it('storage corrotto → []', () => {
        localStorage.setItem('multiLadder:slots', '{non-json');
        expect(loadSlots()).toEqual([]);
    });
});
