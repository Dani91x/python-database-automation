// Test logica pura di liveOrders.ts (helper di legalizzazione lay informativi).
// Le funzioni RPC (sendLiveOrderCommand/fetchLiveOrders/fetchLivePositions) NON
// sono testate qui: richiederebbero la rete/Supabase. Verifichiamo solo la
// matematica lay size<->liability (mirror dei vettori MATEMATICA del backend).
import { describe, it, expect, vi } from 'vitest';

// liveOrders.ts importa il client Supabase, che in fase di import costruisce
// createClient(URL, KEY). In ambiente test le VITE_SUPABASE_* non esistono →
// "supabaseUrl is required" alla collection. Qui testiamo SOLO matematica pura
// (nessuna RPC), quindi mockiamo il modulo client per evitare la rete/login e
// non alterare il comportamento runtime di produzione.
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn() },
}));

import { layLiabilityFromSize, laySizeFromLiability, shouldResetLiveConfirm } from './liveOrders';

describe('lay size <-> liability', () => {
    it('liability = size*(price-1)', () => {
        expect(layLiabilityFromSize(5, 3.0)).toBe(10);   // 5*(3-1)=10
        expect(layLiabilityFromSize(4, 6.0)).toBe(20);   // 4*(6-1)=20
        expect(layLiabilityFromSize(5, 2.5)).toBe(7.5);  // 5*1.5=7.5
    });
    it('size = liability/(price-1)', () => {
        expect(laySizeFromLiability(10, 3.0)).toBe(5);   // 10/2=5
        expect(laySizeFromLiability(20, 5.0)).toBe(5);   // 20/4=5
        expect(laySizeFromLiability(7.5, 2.5)).toBe(5);  // 7.5/1.5=5
    });
    it('round-trip coerente', () => {
        const liab = layLiabilityFromSize(5, 3.0);
        expect(laySizeFromLiability(liab, 3.0)).toBe(5);
    });
    it('input non validi → 0 (no NaN/Infinity)', () => {
        expect(layLiabilityFromSize(5, 1.0)).toBe(0);    // price-1=0
        expect(laySizeFromLiability(10, 1.0)).toBe(0);
        expect(layLiabilityFromSize(NaN, 3.0)).toBe(0);
    });
});

// CODE-MED-2: la conferma "ordine REALE" deve essere one-shot, non permanente.
describe('shouldResetLiveConfirm (conferma LIVE one-shot)', () => {
    it('LIVE + esito ok → resetta la conferma', () => {
        expect(shouldResetLiveConfirm(true, true)).toBe(true);
    });
    it('LIVE + esito negativo → NON resetta (la spunta resta per ritentare)', () => {
        expect(shouldResetLiveConfirm(true, false)).toBe(false);
    });
    it('PAPER → mai resetta, qualunque esito (comportamento PAPER invariato)', () => {
        expect(shouldResetLiveConfirm(false, true)).toBe(false);
        expect(shouldResetLiveConfirm(false, false)).toBe(false);
    });
});
