// 30/09 — OGNI CIFRA DICE COS'E' (ordine dell'utente). Le righe sono quelle
// di `mike_trades` con le chiavi vere (id 5087 della partita 36130526, e la
// riga «utente» che Mike scrive al regolamento: `Betfair/mike/regolato_conto.py`).
import { describe, it, expect } from 'vitest';
import {
    FONTE_PNL_TESTO, fontePnlPartita, fontePnlRiga, fontePnlRighe, isRigaUtente,
    scomposizioneConto, scomposizionePartita, sommaPerChi,
} from './fontePnl';
import { mikeActivityLine, roleLabel, MIKE_ACTIVITY_EXTRA, MIKE_ACTIVITY_KINDS } from './mike';

const MIKE_5087 = {
    id: 5087, role: 'under_entry', mode: 'live', status: 'won', pnl: 5.6, pnl_betfair: 5.6,
    meta: { leg_ref: 'under_entry-0-2', pnl_fonte: 'betfair', pnl_interno: 5.37 },
};
const UTENTE = {
    id: 7001, role: 'utente', mode: 'live', status: 'lost', pnl: -4.34, pnl_betfair: -4.34,
    meta: { fonte: 'utente', pnl_fonte: 'betfair' },
};

describe('fontePnl — le tre fonti', () => {
    it('live regolata da Betfair = conto; live senza = stima; paper = simulato', () => {
        expect(fontePnlRiga(MIKE_5087)).toBe('conto');
        expect(fontePnlRiga({ ...MIKE_5087, pnl_betfair: null, meta: {} })).toBe('stima');
        expect(fontePnlRiga({ ...MIKE_5087, mode: 'paper' })).toBe('simulato');
        expect(FONTE_PNL_TESTO.conto).toBe('P&L del conto Betfair (tutte le operazioni: Mike + utente)');
        expect(FONTE_PNL_TESTO.simulato).toBe('simulato (runner paper)');
    });

    it('un insieme e\' «conto» solo se TUTTE le righe regolate lo sono', () => {
        expect(fontePnlRighe([MIKE_5087, UTENTE])).toBe('conto');
        expect(fontePnlRighe([MIKE_5087, { ...UTENTE, pnl_betfair: null, meta: { fonte: 'utente' } }]))
            .toBe('stima');
        expect(fontePnlRighe([{ ...MIKE_5087, mode: 'paper' }])).toBe('simulato');
        expect(fontePnlRighe([{ ...MIKE_5087, status: 'open' }])).toBeNull();
    });

    it('la partita: conto se il regolamento l\'ha scritta dal conto, con la scomposizione', () => {
        const ev = { mode: 'live', ctx: { pnl_conto: { fonte: 'betfair', mike: 2.1, utente: -2.15, conto: -0.05 } } };
        expect(fontePnlPartita(ev)).toBe('conto');
        expect(scomposizionePartita(ev)).toMatch(/^di cui Mike \+2,10 .* · di cui utente −2,15 /);
        expect(fontePnlPartita({ mode: 'live', ctx: {} })).toBe('stima');
        expect(fontePnlPartita({ mode: 'paper', ctx: ev.ctx })).toBe('simulato');
        expect(scomposizioneConto(1.87, 0)).toBe('');
    });

    it('di chi e\' la riga: la riga «utente» non e\' di Mike', () => {
        expect(isRigaUtente(UTENTE)).toBe(true);
        expect(isRigaUtente(MIKE_5087)).toBe(false);
        expect(sommaPerChi([MIKE_5087, UTENTE, { ...UTENTE, status: 'open', pnl: 9 }]))
            .toEqual({ mike: 5.6, utente: -4.34 });
        expect(roleLabel('utente')).toBe('Ordine tuo (non del bot)');
    });
});

describe('diario di Mike — il regolamento dice la fonte', () => {
    it('settled dal conto: la cifra e\' quella del conto, non il calcolo del bot', () => {
        const riga = mikeActivityLine('settled', {
            total: 3, pnl: -0.05, net: 1.87, pnl_fonte: 'betfair', pnl_mike: 2.1, pnl_utente: -2.15,
        });
        expect(riga).toContain(FONTE_PNL_TESTO.conto);
        expect(riga).toContain('−0,05');
        expect(riga).not.toContain('1,87');
        expect(riga).toContain('di cui utente −2,15');
        // paper / prima del 30/09: come sempre
        expect(mikeActivityLine('settled', { total: 3, net: 1.87, pnl: 1.87 })).toContain('+1,87');
    });

    it('i quattro kind nuovi hanno etichetta italiana e riga leggibile', () => {
        for (const k of ['attesa_regolato_betfair', 'pnl_differenza_betfair', 'ordini_utente_nel_conto',
                         'regolato_conto_non_leggibile']) {
            expect((MIKE_ACTIVITY_KINDS as readonly string[]).includes(k), k).toBe(true);
            expect(MIKE_ACTIVITY_EXTRA[k]?.label, k).toBeTruthy();
        }
        expect(mikeActivityLine('pnl_differenza_betfair',
            { interno_mike: 1.87, betfair_mike: 2.1, differenza: 0.23 }))
            .toBe('il calcolo del bot (+1,87 €) differisce da Betfair (+2,10 €): vale Betfair (differenza +0,23 €)');
        expect(mikeActivityLine('attesa_regolato_betfair', { reason: 'x', tetto: true }))
            .toContain(FONTE_PNL_TESTO.stima);
        expect(mikeActivityLine('ordini_utente_nel_conto', { ordini: 3, netto_utente: -2.15 }))
            .toContain('−2,15');
    });
});
