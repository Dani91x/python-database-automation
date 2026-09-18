import { describe, it, expect } from 'vitest';
import { statoSaldoBetfair, SALDO_HEARTBEAT_STALE_S } from './saldoBetfair';

describe('statoSaldoBetfair', () => {
    it('saldo mai letto: ignoto, con attenzione', () => {
        const r = statoSaldoBetfair({ etaSaldoS: null });
        expect(r.stato).toBe('ignoto');
        expect(r.attenzione).toBe(true);
    });

    it('saldo fresco e battito fresco: ok, nessuna attenzione', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 8, etaHeartbeatS: 5 });
        expect(r.stato).toBe('ok');
        expect(r.attenzione).toBe(false);
        expect(r.messaggio).toMatch(/8 s fa/);
    });

    it('battito non letto: non-verificato ma senza inventare un guasto', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 8 });
        expect(r.stato).toBe('non-verificato');
        expect(r.attenzione).toBe(true);
        expect(r.messaggio).toMatch(/non letto/i);
    });

    it('SALDO VECCHIO → stato arancione: battito oltre la soglia', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 300, etaHeartbeatS: SALDO_HEARTBEAT_STALE_S + 1 });
        expect(r.stato).toBe('non-verificato');
        expect(r.attenzione).toBe(true);
        expect(r.messaggio).toMatch(/non verificato di recente/i);
    });

    it('esattamente alla soglia resta ok (il limite è ESCLUSIVO oltre)', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 10, etaHeartbeatS: SALDO_HEARTBEAT_STALE_S });
        expect(r.stato).toBe('ok');
    });

    // ── FALSIFICAZIONE (documentata nel referto): mutazione manuale
    // `etaHeartbeatS > SALDO_HEARTBEAT_STALE_S` → `>=` , poi ripristinato:
    // il test sopra ("esattamente alla soglia") diventa rosso con la mutazione. ──
    it('falsificazione: un battito appena sopra la soglia deve sempre essere non-verificato', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 10, etaHeartbeatS: SALDO_HEARTBEAT_STALE_S + 0.01 });
        expect(r.stato).toBe('non-verificato');
    });

    // ── 18/09 (raccordo) — messaggio "account" del canale locale (47331) ──
    it('canale locale recente ("checked_at" fresco): ok, anche se il battito manca', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 500, etaCanaleS: 3 });
        expect(r.stato).toBe('ok');
        expect(r.attenzione).toBe(false);
        expect(r.messaggio).toMatch(/canale locale/i);
    });

    it('canale locale muto (nessun "checked_at" mai ricevuto): ripiega sul battito/DB, dichiarato', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 8, etaHeartbeatS: 5, etaCanaleS: null });
        expect(r.stato).toBe('ok');
        expect(r.messaggio).not.toMatch(/canale locale/i);
    });

    it('canale locale vecchio: arancione, non un guasto muto', () => {
        const r = statoSaldoBetfair({ etaSaldoS: 8, etaCanaleS: SALDO_HEARTBEAT_STALE_S + 1 });
        expect(r.stato).toBe('non-verificato');
        expect(r.attenzione).toBe(true);
        expect(r.messaggio).toMatch(/canale locale/i);
    });

    it('falsificazione: il canale locale deve avere PRIORITA sul battito quando entrambi sono presenti', () => {
        // canale fresco (3s) ma battito vecchissimo: deve vincere il canale (piu' preciso)
        const r = statoSaldoBetfair({ etaSaldoS: 8, etaHeartbeatS: 99999, etaCanaleS: 3 });
        expect(r.stato).toBe('ok');
    });
});
