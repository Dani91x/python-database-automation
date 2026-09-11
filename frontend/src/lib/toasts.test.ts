import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('sonner', () => ({
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

import { toast } from 'sonner';
import { settlementToastText, toastSettlement } from './toasts';

const mToast = vi.mocked(toast);

describe('settlementToastText', () => {
    it('vinto: 💰 nome + P&L firmato e selezione', () => {
        const r = settlementToastText({ name: 'Roma v Lazio', pnl: 4.2, side: 'lay', selection: '3 - 2' });
        expect(r.tone).toBe('win');
        expect(r.title).toBe('💰 Roma v Lazio');
        expect(r.description).toBe('+4,20 € · LAY 3 - 2');
    });
    it('perso: ⚠️ nome + P&L negativo col meno tipografico', () => {
        const r = settlementToastText({ name: 'Milan v Inter', pnl: -24.24, side: 'back', selection: 'Under 3.5' });
        expect(r.tone).toBe('loss');
        expect(r.title).toBe('⚠️ Milan v Inter');
        expect(r.description).toBe('−24,24 € · BACK Under 3.5');
    });
    it('void: nessuna icona, stato VOID e P&L zero', () => {
        const r = settlementToastText({ name: 'Napoli v Torino', pnl: 0 });
        expect(r.tone).toBe('void');
        expect(r.title).toBe('Napoli v Torino');
        expect(r.description).toBe('VOID · P&L 0,00 €');
    });
    it('manuale: marcato ✋ (trasparenza su chi ha deciso)', () => {
        expect(settlementToastText({ name: 'X', pnl: 1, manual: true }).title).toBe('💰 ✋ X');
    });
    it('senza lato/selezione la descrizione resta il solo P&L', () => {
        expect(settlementToastText({ name: 'X', pnl: 1 }).description).toBe('+1,00 €');
        expect(settlementToastText({ name: 'X', pnl: 1, selection: '  ' }).description).toBe('+1,00 €');
    });
});

describe('toastSettlement', () => {
    beforeEach(() => vi.clearAllMocks());
    it('instrada su success/error/neutro secondo il segno', () => {
        toastSettlement({ name: 'A', pnl: 1 });
        expect(mToast.success).toHaveBeenCalledWith('💰 A', { description: '+1,00 €' });
        toastSettlement({ name: 'B', pnl: -1 });
        expect(mToast.error).toHaveBeenCalledWith('⚠️ B', { description: '−1,00 €' });
        toastSettlement({ name: 'C', pnl: null });
        expect(mToast).toHaveBeenCalledWith('C', { description: 'VOID · P&L 0,00 €' });
    });
});
