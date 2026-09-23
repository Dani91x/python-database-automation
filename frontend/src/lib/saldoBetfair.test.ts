import { describe, it, expect } from 'vitest';
import {
    statoSaldoBetfair, SALDO_HEARTBEAT_STALE_S, leggiSaldoDalCanale, saldoPiuRecente, saldoDaMostrare,
    testoUltimaVerifica,
} from './saldoBetfair';

// 23/09 — il valore dal canale "account": regole pure.
describe('saldo dal canale "account" (23/09)', () => {
    const t0 = '2026-09-23T10:00:00.000000+00:00';
    const t1 = '2026-09-23T10:00:05.000000+00:00';

    it('un messaggio di saldo con le chiavi vere del backend si legge', () => {
        const s = leggiSaldoDalCanale({ available: 812.37, exposure: -41.5, checked_at: t0, fonte: 'omega:ordine' });
        expect(s).toMatchObject({ available: 812.37, exposure: -41.5, checkedAt: t0 });
    });

    it('messaggio manuale (senza available), checked_at illeggibile o malformato: null', () => {
        expect(leggiSaldoDalCanale({ manual_pnl_eur: 3, checked_at: t0 })).toBeNull();
        expect(leggiSaldoDalCanale({ available: 3, checked_at: 'ieri' })).toBeNull();
        expect(leggiSaldoDalCanale({ available: Number.NaN, checked_at: t0 })).toBeNull();
        expect(leggiSaldoDalCanale(null)).toBeNull();
    });

    it('vince il checked_at più recente; uno vecchio o uguale è ignorato', () => {
        const a = leggiSaldoDalCanale({ available: 1, exposure: 0, checked_at: t1 });
        const b = leggiSaldoDalCanale({ available: 2, exposure: 0, checked_at: t0 });
        const c = leggiSaldoDalCanale({ available: 3, exposure: 0, checked_at: t1 });
        expect(saldoPiuRecente(a, b)).toBe(a);
        expect(saldoPiuRecente(a, c)).toBe(a);
        expect(saldoPiuRecente(b, a)).toBe(a);
        expect(saldoPiuRecente(null, b)).toBe(b);
    });

    it('fra database e canale vince l’istante più recente; canale muto = database', () => {
        const db = { available: 100, exposure: -1, updated_at: t0 };
        const nuovo = leggiSaldoDalCanale({ available: 90, exposure: -2, checked_at: t1 });
        expect(saldoDaMostrare(db, nuovo)).toMatchObject({ available: 90, fonte: 'canale', istante: t1 });
        expect(saldoDaMostrare({ ...db, updated_at: t1 }, leggiSaldoDalCanale({ available: 5, exposure: 0, checked_at: t0 })))
            .toMatchObject({ available: 100, fonte: 'database' });
        expect(saldoDaMostrare(db, null)).toEqual({ available: 100, exposure: -1, istante: t0, fonte: 'database' });
        expect(saldoDaMostrare(null, null)).toEqual({ available: null, exposure: null, istante: null, fonte: 'database' });
    });
});

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

// F2 revisore A (23/09): "non aggiornato da ..." con la DATA quando l'ultimo
// controllo non e' di oggi (giorno di Roma), altrimenti un'ora di ieri sembra
// di oggi (anche nel futuro).
describe('testoUltimaVerifica (F2)', () => {
    const adesso = Date.parse('2026-09-23T08:00:00Z'); // 10:00 a Roma, 23/09

    it('stesso giorno di Roma: solo HH:MM', () => {
        expect(testoUltimaVerifica('2026-09-23T06:15:00Z', adesso)).toBe('08:15');
    });

    it('giorno prima: GG/MM HH:MM', () => {
        expect(testoUltimaVerifica('2026-09-22T13:51:00Z', adesso)).toBe('22/09 15:51');
    });

    it('il confine e\x27 la mezzanotte di ROMA, non quella UTC', () => {
        // 22:30 UTC del 22/09 = 00:30 a Roma del 23/09 -> oggi
        expect(testoUltimaVerifica('2026-09-22T22:30:00Z', adesso)).toBe('00:30');
        // 21:30 UTC del 22/09 = 23:30 a Roma del 22/09 -> ieri
        expect(testoUltimaVerifica('2026-09-22T21:30:00Z', adesso)).toBe('22/09 23:30');
    });

    it('istante assente o illeggibile: il trattino', () => {
        expect(testoUltimaVerifica(null, adesso)).toBe('\u2014');
        expect(testoUltimaVerifica('non-una-data', adesso)).toBe('\u2014');
    });
});
