// ============================================================================
// navigazione.salute.test.ts - 09/10 (T0A): la voce «Salute» in fondo al
// gruppo Analisi, con un'icona che esiste; la rotta nuova e' nel guscio e nei
// due rami di App.tsx (protetta nel ramo di oggi); le voci di prima identiche.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { NAV, ROTTE_NEL_GUSCIO, titoloDi, CANALI_DELLA_PAGINA, gruppiVisibili } from './navigazione';

const APP = readFileSync(join(__dirname, '..', '..', 'App.tsx'), 'utf-8');

describe('voce Salute', () => {
    it('ultima voce del gruppo «analisi»; le altre voci del gruppo invariate', () => {
        const analisi = NAV.find((g) => g.id === 'analisi');
        const ids = analisi?.voci.map((v) => v.id) ?? [];
        expect(ids).toEqual(['match-replay', 'analytics', 'report-personale', 'trade-journal', 'salute']);
        const v = analisi?.voci.find((x) => x.id === 'salute');
        expect(v?.rotta).toBe('/salute');
        expect(v?.icona).toBe('impulso');
        expect(v?.sport).toBe('comune');
        expect(titoloDi('/salute')).toEqual({ gruppo: 'Analisi', titolo: 'Salute' });
    });

    it('rotta nel guscio e nei due rami di App.tsx (protetta nel ramo di oggi)', () => {
        expect(ROTTE_NEL_GUSCIO).toContain('/salute');
        const guscio = APP.slice(APP.indexOf('function RotteGuscioV2'), APP.indexOf('function App()'));
        expect(guscio).toContain('<Route path="/salute" element={<Salute />} />');
        const oggi = APP.slice(APP.indexOf('function App()'));
        expect(oggi).toMatch(/path="\/salute"\s*\n\s*element=\{\s*\n\s*<ProtectedRoute>\s*\n\s*<Salute \/>/);
    });

    it('la pagina non apre canali locali (nessuna voce in CANALI_DELLA_PAGINA)', () => {
        expect(CANALI_DELLA_PAGINA['/salute']).toBeUndefined();
    });
});

// 09/10 (R-5 della verifica del PC): a monitor spento la voce non si vede
describe('voce Salute solo a monitor acceso', () => {
    const idsAnalisi = (attivo?: boolean) =>
        (attivo === undefined ? gruppiVisibili('tutti') : gruppiVisibili('tutti', attivo))
            .find((g) => g.id === 'analisi')?.voci.map((v) => v.id) ?? [];

    it('spento (anche di serie): niente «Salute», le altre voci identiche', () => {
        expect(idsAnalisi()).toEqual(['match-replay', 'analytics', 'report-personale', 'trade-journal']);
        expect(idsAnalisi(false)).toEqual(['match-replay', 'analytics', 'report-personale', 'trade-journal']);
    });

    it('acceso: la voce torna in fondo al gruppo', () => {
        expect(idsAnalisi(true)).toEqual(['match-replay', 'analytics', 'report-personale', 'trade-journal', 'salute']);
    });

    it('nessun\'altra voce dipende dal monitor', () => {
        const tutte = (a: boolean) => gruppiVisibili('tutti', a).flatMap((g) => g.voci.map((v) => v.id));
        expect(tutte(true).filter((id) => !tutte(false).includes(id))).toEqual(['salute']);
        for (const f of ['calcio', 'tennis'] as const) {
            const conta = (a: boolean) => gruppiVisibili(f, a).flatMap((g) => g.voci).length;
            expect(conta(true) - conta(false)).toBe(1);
        }
    });
});
