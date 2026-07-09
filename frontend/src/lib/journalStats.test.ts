// ============================================================================
// journalStats.test.ts — test della statistica PURA sul Trade Journal (E37).
// Nessun I/O: raggruppamenti per dimensione + join settled per market_id.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { groupJournal, settledByMarket } from '@/lib/journalStats';
import type { LiveJournalRow } from '@/lib/liveOrders';

// Fabbrica di righe journal con default innocui (mirror LiveJournalRow).
function row(over: Partial<LiveJournalRow>): LiveJournalRow {
    return {
        id: 1, ts: '2026-07-08T10:00:00Z', mode: 'paper', request_id: null,
        action: 'place', origin: 'manual',
        event_id: 'ev1', market_id: '1.234', market_name: 'Match Odds',
        selection_id: 1, side: 'back', price: 2.0, size: 5, persistence: 'LAPSE',
        bet_id: null, minute: 10, score_home: 0, score_away: 0, inplay: true,
        ltp: 2.0, best_back: 1.99, best_lay: 2.01, book: null, signals: null,
        params: null, tag: null, note: null,
        ...over,
    };
}

describe('groupJournal — tag', () => {
    it('raggruppa per tag, null → "(senza tag)", ordinato per count desc', () => {
        const rows = [
            row({ tag: 'scalp', size: 5 }),
            row({ tag: 'scalp', size: 3 }),
            row({ tag: null, size: 2 }),
        ];
        const stats = groupJournal(rows, 'tag');
        expect(stats).toEqual([
            { key: 'scalp', count: 2, stakeTotal: 8 },
            { key: '(senza tag)', count: 1, stakeTotal: 2 },
        ]);
    });

    it('righe senza size → contribuiscono 0 allo stakeTotal', () => {
        const rows = [row({ tag: 'x', size: null }), row({ tag: 'x', size: 4 })];
        expect(groupJournal(rows, 'tag')).toEqual([{ key: 'x', count: 2, stakeTotal: 4 }]);
    });
});

describe('groupJournal — action / side / origin', () => {
    it('action: raggruppa per azione', () => {
        const rows = [row({ action: 'place' }), row({ action: 'greenup' }), row({ action: 'place' })];
        const stats = groupJournal(rows, 'action');
        expect(stats[0]).toEqual({ key: 'place', count: 2, stakeTotal: 10 });
        expect(stats[1]).toEqual({ key: 'greenup', count: 1, stakeTotal: 5 });
    });

    it('side: null → "—" (es. greenup/cashout senza lato)', () => {
        const rows = [row({ side: 'back' }), row({ side: 'lay' }), row({ side: null, size: null })];
        const stats = groupJournal(rows, 'side');
        expect(stats).toHaveLength(3);
        expect(stats.map(s => s.key).sort()).toEqual(['back', 'lay', '—'].sort());
        expect(stats.find(s => s.key === '—')).toEqual({ key: '—', count: 1, stakeTotal: 0 });
    });

    it('origin: manual vs risk_rule', () => {
        const rows = [row({ origin: 'manual' }), row({ origin: 'risk_rule' }), row({ origin: 'risk_rule' })];
        const stats = groupJournal(rows, 'origin');
        expect(stats[0].key).toBe('risk_rule');
        expect(stats[0].count).toBe(2);
        expect(stats[1]).toEqual({ key: 'manual', count: 1, stakeTotal: 5 });
    });
});

describe('groupJournal — minuteBucket', () => {
    it('bucket da 15 minuti: 0-15, 15-30, …, 75-90, 90+', () => {
        const rows = [
            row({ minute: 0 }), row({ minute: 14 }),   // 0-15
            row({ minute: 15 }),                        // 15-30
            row({ minute: 44 }),                        // 30-45
            row({ minute: 89 }),                        // 75-90
            row({ minute: 90 }), row({ minute: 120 }),  // 90+
        ];
        const stats = groupJournal(rows, 'minuteBucket');
        const byKey = Object.fromEntries(stats.map(s => [s.key, s.count]));
        expect(byKey['0-15']).toBe(2);
        expect(byKey['15-30']).toBe(1);
        expect(byKey['30-45']).toBe(1);
        expect(byKey['75-90']).toBe(1);
        expect(byKey['90+']).toBe(2);
    });

    it('minute null + inplay false/null → "pre-match"; inplay true → "—" (minuto ignoto)', () => {
        const rows = [
            row({ minute: null, inplay: false }),
            row({ minute: null, inplay: null }),
            row({ minute: null, inplay: true }),
        ];
        const stats = groupJournal(rows, 'minuteBucket');
        const byKey = Object.fromEntries(stats.map(s => [s.key, s.count]));
        expect(byKey['pre-match']).toBe(2);
        expect(byKey['—']).toBe(1);
    });

    it('ordinamento per count desc', () => {
        const rows = [row({ minute: 5 }), row({ minute: 7 }), row({ minute: 50 })];
        const stats = groupJournal(rows, 'minuteBucket');
        expect(stats[0].key).toBe('0-15');
        expect(stats[0].count).toBe(2);
    });
});

describe('settledByMarket', () => {
    it('mappa market_id → profit', () => {
        const m = settledByMarket([
            { market_id: '1.1', profit: 3.5 },
            { market_id: '1.2', profit: -1.25 },
        ]);
        expect(m.get('1.1')).toBe(3.5);
        expect(m.get('1.2')).toBe(-1.25);
        expect(m.has('1.9')).toBe(false);
    });

    it('market_id duplicato (es. paper+live) → SOMMA dei profit', () => {
        const m = settledByMarket([
            { market_id: '1.1', profit: 2 },
            { market_id: '1.1', profit: -0.5 },
        ]);
        expect(m.get('1.1')).toBeCloseTo(1.5, 10);
    });

    it('lista vuota → mappa vuota', () => {
        expect(settledByMarket([]).size).toBe(0);
    });
});
