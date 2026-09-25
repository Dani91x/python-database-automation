// R5 (25/09/2026): soglie dell'eta' del dato materializzato.
import { describe, it, expect } from 'vitest';
import { calcolaEta, formatEta, SOGLIA_CALIBRAZIONE_ORE, SOGLIA_PREVISIONE_ORE, SOGLIA_PAGELLA_ORE } from './etaDato';

const NOW = new Date('2026-09-25T12:00:00Z');
const oreFa = (h: number) => new Date(NOW.getTime() - h * 3_600_000).toISOString();

describe('calcolaEta', () => {
    it('soglie dichiarate: 36 h previsioni e pagella, 8 giorni calibrazione', () => {
        expect(SOGLIA_PREVISIONE_ORE).toBe(36);
        expect(SOGLIA_PAGELLA_ORE).toBe(36);
        expect(SOGLIA_CALIBRAZIONE_ORE).toBe(192);
    });

    it('previsione: fresca fino a 36 h comprese, vecchia oltre', () => {
        expect(calcolaEta(oreFa(2.5), SOGLIA_PREVISIONE_ORE, NOW).stato).toBe('fresco');
        expect(calcolaEta(oreFa(36), SOGLIA_PREVISIONE_ORE, NOW).stato).toBe('fresco');
        expect(calcolaEta(oreFa(36.1), SOGLIA_PREVISIONE_ORE, NOW).stato).toBe('vecchio');
        expect(calcolaEta(oreFa(24 * 7), SOGLIA_PREVISIONE_ORE, NOW).stato).toBe('vecchio');
    });

    it('calibrazione settimanale: 4 giorni fresca, 8 giorni ancora fresca, 9 giorni vecchia', () => {
        expect(calcolaEta(oreFa(24 * 4), SOGLIA_CALIBRAZIONE_ORE, NOW).stato).toBe('fresco');
        expect(calcolaEta(oreFa(24 * 8), SOGLIA_CALIBRAZIONE_ORE, NOW).stato).toBe('fresco');
        expect(calcolaEta(oreFa(24 * 9), SOGLIA_CALIBRAZIONE_ORE, NOW).stato).toBe('vecchio');
    });

    it('dato mancante o non valido = assente (mai "fresco" per difetto)', () => {
        expect(calcolaEta(null, 36, NOW).stato).toBe('assente');
        expect(calcolaEta(undefined, 36, NOW).stato).toBe('assente');
        expect(calcolaEta('', 36, NOW).stato).toBe('assente');
        expect(calcolaEta('non-una-data', 36, NOW).stato).toBe('assente');
    });

    it('orario nel futuro (orologi sfasati) = eta 0, fresco', () => {
        const e = calcolaEta(oreFa(-3), 36, NOW);
        expect(e.stato).toBe('fresco');
        expect(e.ore).toBe(0);
    });

    it('eta leggibile', () => {
        expect(formatEta(0.25)).toBe('15 min');
        expect(formatEta(5.9)).toBe('5 h');
        expect(formatEta(47)).toBe('47 h');
        expect(formatEta(24 * 3 + 4.5)).toBe('3 g 4 h');
        expect(formatEta(24 * 8)).toBe('8 g');
        expect(calcolaEta(oreFa(2.5), 36, NOW).testoEta).toBe('2 h');
    });
});
