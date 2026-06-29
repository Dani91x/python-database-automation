// Test: un arbitraggio è mostrato solo se TUTTE le gambe reggono sotto il ritardo.
import { describe, it, expect } from 'vitest';
import { arbExecutableUnderDelay, type SnapsProvider } from './arb_exec';
import type { BookSnapshot } from '@/lib/matching';
import type { Opportunity } from './types';

function snap(p: Partial<BookSnapshot> & { ts: number }): BookSnapshot {
    return { back: [], lay: [], ltp: null, tv: null, ...p };
}

// arb a 2 gambe: back su selezione 1 (mercato A) @2.0, back su selezione 2 (mercato B) @2.1.
function opp(): Opportunity {
    return {
        id: 'x', tier: 'arb', type: 't', title: '', instruction: '',
        legs: [
            { marketId: 'A', marketName: 'A', selectionId: 1, selectionName: '1', side: 'back', price: 2.0, stake: 100, matchedStake: 100 },
            { marketId: 'B', marketName: 'B', selectionId: 2, selectionName: '2', side: 'back', price: 2.1, stake: 100, matchedStake: 100 },
        ],
        profit: 5, profitPct: 5, confidence: 1, explanation: '', phase: 'pre',
    };
}

describe('arbExecutableUnderDelay', () => {
    it('PRE-MATCH: passa sempre (nessun ritardo, book corrente)', () => {
        const get: SnapsProvider = (m) => [snap({ ts: 1000, back: m === 'A' ? [[2.0, 500]] : [[2.1, 500]] })];
        expect(arbExecutableUnderDelay(opp(), get, 1000, false)).toBe(true);
    });

    it('IN-PLAY: passa se entrambe le gambe reggono dopo il ritardo', () => {
        const get: SnapsProvider = (m) => [
            snap({ ts: 1000, back: m === 'A' ? [[2.0, 500]] : [[2.1, 500]] }),       // all'invio
            snap({ ts: 6000, back: m === 'A' ? [[2.0, 500]] : [[2.1, 500]] }),       // dopo 5s: prezzo regge
        ];
        expect(arbExecutableUnderDelay(opp(), get, 1000, true, 5000)).toBe(true);
    });

    it('IN-PLAY: BLOCCA se una gamba non regge dopo il ritardo (prezzo scappato)', () => {
        const get: SnapsProvider = (m) => [
            snap({ ts: 1000, back: m === 'A' ? [[2.0, 500]] : [[2.1, 500]] }),
            // dopo il ritardo: mercato B non offre più 2.1 (best back sceso a 1.9) → la
            // gamba back @2.1 non si abbina (serve prezzo ≥ limite).
            snap({ ts: 6000, back: m === 'A' ? [[2.0, 500]] : [[1.9, 500]] }),
        ];
        expect(arbExecutableUnderDelay(opp(), get, 1000, true, 5000)).toBe(false);
    });

    it('IN-PLAY: BLOCCA se la liquidità dopo il ritardo è insufficiente (fill parziale)', () => {
        const get: SnapsProvider = (m) => [
            snap({ ts: 1000, back: m === 'A' ? [[2.0, 500]] : [[2.1, 500]] }),
            snap({ ts: 6000, back: m === 'A' ? [[2.0, 500]] : [[2.1, 30]] }), // solo 30 di 100 richiesti
        ];
        expect(arbExecutableUnderDelay(opp(), get, 1000, true, 5000)).toBe(false);
    });

    it('BLOCCA se manca lo snapshot di una gamba', () => {
        const get: SnapsProvider = (m) => (m === 'A' ? [snap({ ts: 1000, back: [[2.0, 500]] })] : []);
        expect(arbExecutableUnderDelay(opp(), get, 1000, true, 5000)).toBe(false);
    });
});
