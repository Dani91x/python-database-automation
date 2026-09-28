// FIX-B (26/09/2026) KO11: rese dei casi limite. Valori dai casi del referto di fase 3.
import { describe, it, expect } from 'vitest';
import {
    golPrevisto, mediaPerPartita, serieMinuti, minutiTuttiAssenti, fmtDataRoma, giornoRoma, orarioPartita,
    confiniGiornoRoma,
} from './rese';

describe('golPrevisto (U0022)', () => {
    it('NULL -> trattino, mai "0"', () => {
        expect(golPrevisto(null)).toBe('—');
        expect(golPrevisto(undefined)).toBe('—');
        expect(golPrevisto('  ')).toBe('—');
    });
    it('valori veri invariati (anche "-2.5" e "0")', () => {
        expect(golPrevisto('-2.5')).toBe('-2.5');
        expect(golPrevisto('0')).toBe('0');
        expect(golPrevisto(1.5)).toBe('1.5');
    });
});

describe('mediaPerPartita (U0026)', () => {
    it('played=0 -> trattino, mai NaN', () => {
        expect(mediaPerPartita(0, 0)).toBe('—');
        expect(mediaPerPartita(3, 0)).toBe('—');
        expect(mediaPerPartita(null, 5)).toBe('—');
    });
    it('10 gol in 5 partite = 2.0', () => {
        expect(mediaPerPartita(10, 5)).toBe('2.0');
        expect(mediaPerPartita(9, 5)).toBe('1.8');
    });
});

describe('serieMinuti (U0029)', () => {
    it('NULL resta NULL (barra assente), numeri invariati, 0 vero resta 0', () => {
        const s = serieMinuti({ '0-15': { total: null }, '16-30': { total: 3 }, '31-45': { total: 0 } });
        expect(s.map(p => p.count)).toEqual([null, 3, 0, null, null, null, null, null]);
        expect(minutiTuttiAssenti(s)).toBe(false);
    });
    it('tutte NULL (partita D del referto) -> tutti assenti', () => {
        const tutti = Object.fromEntries(['0-15', '16-30', '31-45', '46-60', '61-75', '76-90', '91-105', '106-120'].map(k => [k, { total: null }]));
        expect(minutiTuttiAssenti(serieMinuti(tutti))).toBe(true);
    });
});

describe('date di Roma (U0056, U0011)', () => {
    it('ISO UTC dello Studio Ritardi -> gg/mm/aaaa di Roma', () => {
        expect(fmtDataRoma('2019-02-22T19:45:00+00:00')).toBe('22/02/2019');
        // 23:30 UTC d'estate = giorno dopo a Roma
        expect(fmtDataRoma('2026-09-25T23:30:00+00:00')).toBe('26/09/2026');
        expect(fmtDataRoma(null)).toBe('—');
    });
    it('giornoRoma: 22:00Z del 26/09 e\' il 27/09 a Roma', () => {
        expect(giornoRoma('2026-09-26T22:00:00+00:00')).toBe('2026-09-27');
        expect(giornoRoma('2026-09-26T14:00:00+00:00')).toBe('2026-09-26');
    });
    it('orarioPartita: stessa giornata -> solo ora; giorno dopo -> data + ora', () => {
        expect(orarioPartita('2026-09-26T14:00:00+00:00', '2026-09-26')).toBe('16:00');
        // Deportivo Madryn del referto: 22:00Z del 26/09 = 00:00 del 27/09
        expect(orarioPartita('2026-09-26T22:00:00+00:00', '2026-09-26')).toBe('27/09 00:00');
        expect(orarioPartita('2026-09-26T23:00:00+00:00', '2026-09-26')).toBe('27/09 01:00');
        expect(orarioPartita(null, '2026-09-26')).toBe('—');
    });
});

describe('confiniGiornoRoma — CANTIERE G voce 3 (28/09), lista partite 00:00-02:00 di Roma', () => {
    it('26/09/2026 (CEST, +2h): mezzanotte di Roma e\' 22:00Z del giorno prima', () => {
        const { inizio, fine } = confiniGiornoRoma('2026-09-26');
        expect(inizio).toBe('2026-09-25T22:00:00.000Z');
        expect(fine).toBe('2026-09-26T22:00:00.000Z');
    });

    it('15/01/2026 (CET, +1h): mezzanotte di Roma e\' 23:00Z del giorno prima', () => {
        const { inizio, fine } = confiniGiornoRoma('2026-01-15');
        expect(inizio).toBe('2026-01-14T23:00:00.000Z');
        expect(fine).toBe('2026-01-15T23:00:00.000Z');
    });

    it('una partita delle 00:30 di Roma (22:30Z del giorno prima) CADE dentro il giorno, non fuori', () => {
        const { inizio, fine } = confiniGiornoRoma('2026-09-26');
        const partita = new Date('2026-09-25T22:30:00Z').getTime();
        expect(partita >= new Date(inizio).getTime()).toBe(true);
        expect(partita < new Date(fine).getTime()).toBe(true);
    });

    it('una partita del giorno DOPO (22:00Z, = 00:00 di Roma del 27/09) resta FUORI (limite superiore)', () => {
        const { fine } = confiniGiornoRoma('2026-09-26');
        const partitaDomani = new Date('2026-09-26T22:00:00Z').getTime();
        expect(partitaDomani >= new Date(fine).getTime()).toBe(true); // esclusa da .lt(fine)
    });

    it('il giorno dura ESATTAMENTE 24h fuori dai due giorni del cambio ora', () => {
        const { inizio, fine } = confiniGiornoRoma('2026-09-26');
        expect(new Date(fine).getTime() - new Date(inizio).getTime()).toBe(24 * 3_600_000);
    });
});
