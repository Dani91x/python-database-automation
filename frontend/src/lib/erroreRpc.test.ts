// FIX-B (26/09): un timeout della RPC non si presenta come "nessun dato".
// Messaggi presi dal referto di fase 3 (testo vero di PostgREST/Postgres).
import { describe, it, expect } from 'vitest';
import { classificaErroreRpc, fmtOrarioRiepilogo } from './erroreRpc';

describe('classificaErroreRpc', () => {
    it('statement timeout (testo vero del referto) = timeout, dichiara che i dati NON sono vuoti', () => {
        const e = classificaErroreRpc('canceling statement due to statement timeout');
        expect(e.tipo).toBe('timeout');
        expect(e.testo).toMatch(/NON sono vuoti/);
        expect(e.originale).toBe('canceling statement due to statement timeout');
    });
    it('codice 57014 in un Error = timeout', () => {
        expect(classificaErroreRpc(new Error('57014: query canceled')).tipo).toBe('timeout');
    });
    it('altro errore = errore, con il messaggio originale', () => {
        const e = classificaErroreRpc('permission denied for function get_analytics');
        expect(e.tipo).toBe('errore');
        expect(e.testo).toContain('permission denied for function get_analytics');
        expect(e.testo).toMatch(/non sono stati letti/);
    });
    it('vuoto/null = errore sconosciuto, mai stringa vuota', () => {
        expect(classificaErroreRpc(null).originale).toBe('errore sconosciuto');
        expect(classificaErroreRpc('').tipo).toBe('errore');
    });
});

describe('fmtOrarioRiepilogo', () => {
    it('ISO UTC -> ora di Roma', () => {
        expect(fmtOrarioRiepilogo('2026-09-26T01:40:00+00:00')).toBe('26/09/2026, 03:40');
    });
    it('null / invalido -> null', () => {
        expect(fmtOrarioRiepilogo(null)).toBeNull();
        expect(fmtOrarioRiepilogo('non-una-data')).toBeNull();
    });
});
