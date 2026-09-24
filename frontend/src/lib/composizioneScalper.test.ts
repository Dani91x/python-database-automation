// ============================================================================
// composizioneScalper.test.ts - la voce "Scalper calcio" nella composizione
// dell'obiettivo di giornata (24/09). Solo soldi veri; l'invariante di sempre:
// la somma delle voci e' il realizzato LIVE di tutte le righe insieme.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { componiObiettivo, rigaSintetica, type RigaComponente } from '@/lib/composizioneObiettivo';
import { realizzatoGiornata } from '@/lib/controlRoom';

const live = (pnl: number, extra: Partial<RigaComponente> = {}): RigaComponente => ({
    status: pnl > 0 ? 'won' : pnl < 0 ? 'lost' : 'void', pnl, mode: 'live', sport: 'calcio',
    origin: 'auto', ...extra,
});

describe('voce Scalper calcio', () => {
    it('le righe dello scalper finiscono nella SUA voce, reale dichiarato, e l invariante regge', () => {
        const scalper = [rigaSintetica(0.3, null, { sport: 'calcio', origin: 'auto' })!,
            rigaSintetica(-0.1, null, { sport: 'calcio', origin: 'auto' })!];
        const omega = [live(1)];
        const c = componiObiettivo({ omega, safe: [], mike: [], tennisBot: [], scalper });
        const v = c.righe.find((r) => r.chiave === 'scalper')!;
        expect(v.etichetta).toBe('Scalper calcio');
        expect(v.valore).toBe(0.2);
        expect(v.stimato).toBeNull();                       // tutto regolato da Betfair
        expect(c.righe.find((r) => r.chiave === 'omega')!.valore).toBe(1);
        const somma = c.righe.reduce((s, r) => s + (r.valore ?? 0), 0);
        expect(Math.round(somma * 100) / 100).toBe(c.totale);
        expect(c.totale).toBe(realizzatoGiornata([...omega, ...scalper]).live);
        expect(c.reale).toBe(0.2);
    });

    it('una riga PAPER dello scalper non entra mai nel totale (solo nella prova)', () => {
        const c = componiObiettivo({
            omega: [], safe: [], mike: [], tennisBot: [],
            scalper: [{ status: 'won', pnl: 5, mode: 'paper', sport: 'calcio', origin: 'auto' }],
        });
        expect(c.righe.find((r) => r.chiave === 'scalper')!.valore).toBeNull();
        expect(c.totale).toBeNull();
        expect(c.provaPaper).toBe(5);
    });

    it('senza la voce (chiamante di prima): vuota, comportamento identico', () => {
        const c = componiObiettivo({ omega: [live(1)], safe: [], mike: [], tennisBot: [] });
        expect(c.righe.find((r) => r.chiave === 'scalper')!.valore).toBeNull();
        expect(c.totale).toBe(1);
    });
});
