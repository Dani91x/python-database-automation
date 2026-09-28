// ============================================================================
// replay-pnl.formatValuta.test.ts — CANTIERE G, voce 4 (28/09).
// Il conto e' in EUR: `formatGbp` mostrava «£» anche prima del fix K1 (bug di
// etichetta indipendente dalla conversione delle size).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { formatGbp } from './replay-pnl';

describe('formatGbp — il conto e\' in EUR, mai «£»', () => {
    it('positivo e negativo in euro', () => {
        expect(formatGbp(12.3)).toBe('€12.30');
        expect(formatGbp(-12.3)).toBe('-€12.30');
    });
    it('null/undefined/NaN -> €0.00', () => {
        expect(formatGbp(null)).toBe('€0.00');
        expect(formatGbp(undefined)).toBe('€0.00');
        expect(formatGbp(NaN)).toBe('€0.00');
    });
    it('mai il simbolo sterlina', () => {
        expect(formatGbp(5)).not.toMatch(/£/);
    });
});
