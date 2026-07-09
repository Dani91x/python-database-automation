// Test di kellySuggest.ts (E36) — mai un suggerimento con dati invalidi/stantii.
import { describe, expect, it } from 'vitest';
import { kellySuggestions, signalsStale } from './kellySuggest';
import type { LiveSignalsRow, Signal } from './live';

const NOW = Date.parse('2026-07-08T20:00:00Z');

function sig(over: Partial<Signal> = {}): Signal {
    return {
        market_id: '1.1',
        market_type: 'MATCH_ODDS',
        selection_id: 111,
        selection_name: 'Home',
        model_prob: 0.55,
        market_back: 2.0,
        market_lay: 2.02,
        fair_back: 1.82,
        fair_lay: 1.84,
        edge: 0.06,
        direction: 'BACK',
        confidence: 0.8,
        kelly_stake: 2.437,
        ...over,
    };
}

function row(signals: Signal[], updatedAt = '2026-07-08T19:59:30Z'): LiveSignalsRow {
    return {
        event_id: '31.5',
        signals: { signals, updated_ms: null },
        model_meta: null,
        updated_at: updatedAt,
    };
}

describe('signalsStale', () => {
    it('fresco entro maxAge', () => {
        expect(signalsStale(row([]), NOW)).toBe(false);
    });
    it('stantio oltre maxAge', () => {
        expect(signalsStale(row([], '2026-07-08T19:57:00Z'), NOW)).toBe(true);
    });
    it('età ignota = stantio (mai fingere freschezza)', () => {
        expect(signalsStale({ updated_at: null }, NOW)).toBe(true);
        expect(signalsStale(null, NOW)).toBe(true);
        expect(signalsStale({ updated_at: 'boh' }, NOW)).toBe(true);
    });
});

describe('kellySuggestions', () => {
    it('suggerimento BACK valido con stake arrotondato al centesimo', () => {
        const m = kellySuggestions(row([sig()]), '1.1', NOW);
        const s = m.get(111)!;
        expect(s.side).toBe('back');
        expect(s.stake).toBe(2.44);
        expect(s.fair).toBe(1.82);
        expect(s.edge).toBe(0.06);
    });

    it('LAY usa fair_lay', () => {
        const m = kellySuggestions(row([sig({ direction: 'LAY' })]), '1.1', NOW);
        expect(m.get(111)!.side).toBe('lay');
        expect(m.get(111)!.fair).toBe(1.84);
    });

    it('HOLD mai suggerito', () => {
        expect(kellySuggestions(row([sig({ direction: 'HOLD' })]), '1.1', NOW).size).toBe(0);
    });

    it('kelly_stake 0/negativo/non finito mai suggerito', () => {
        expect(kellySuggestions(row([sig({ kelly_stake: 0 })]), '1.1', NOW).size).toBe(0);
        expect(kellySuggestions(row([sig({ kelly_stake: -3 })]), '1.1', NOW).size).toBe(0);
        expect(kellySuggestions(row([sig({ kelly_stake: NaN })]), '1.1', NOW).size).toBe(0);
    });

    it('prob fuori (0,1) mai suggerita', () => {
        expect(kellySuggestions(row([sig({ model_prob: 0 })]), '1.1', NOW).size).toBe(0);
        expect(kellySuggestions(row([sig({ model_prob: 1.2 })]), '1.1', NOW).size).toBe(0);
    });

    it('filtra per mercato', () => {
        const m = kellySuggestions(row([sig(), sig({ market_id: '1.2', selection_id: 222 })]), '1.1', NOW);
        expect(m.size).toBe(1);
        expect(m.has(111)).toBe(true);
    });

    it('segnali stantii → mappa vuota (mai suggerire su dati vecchi)', () => {
        expect(kellySuggestions(row([sig()], '2026-07-08T19:00:00Z'), '1.1', NOW).size).toBe(0);
    });

    it('riga nulla / payload malformato → mappa vuota', () => {
        expect(kellySuggestions(null, '1.1', NOW).size).toBe(0);
        const bad = { ...row([]), signals: { signals: 'boh' } } as unknown as LiveSignalsRow;
        expect(kellySuggestions(bad, '1.1', NOW).size).toBe(0);
    });

    it('fair invalido (<=1) → null, il suggerimento resta', () => {
        const m = kellySuggestions(row([sig({ fair_back: 1.0 })]), '1.1', NOW);
        expect(m.get(111)!.fair).toBeNull();
    });
});
