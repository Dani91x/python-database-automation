// ============================================================================
// navigazione.cashOut.test.ts - 08/10 (cantiere W1): la voce «Cash Out» sta
// SUBITO sotto la Control Room, con un'icona che esiste; la voce della Control
// Room e la sua rotta restano identiche; la rotta nuova e' nel guscio e nei
// due rami di App.tsx.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { NAV, ROTTE_NEL_GUSCIO, titoloDi, CANALI_DELLA_PAGINA } from './navigazione';

const APP = readFileSync(join(__dirname, '..', '..', 'App.tsx'), 'utf-8');

describe('voce Cash Out', () => {
    it('subito dopo la Control Room, nel gruppo «inizio»; la Control Room identica', () => {
        const inizio = NAV.find((g) => g.id === 'inizio');
        const ids = inizio?.voci.map((v) => v.id) ?? [];
        expect(ids.indexOf('cash-out')).toBe(ids.indexOf('control-room') + 1);
        expect(inizio?.voci.find((v) => v.id === 'control-room')).toEqual({
            id: 'control-room', etichetta: 'Control Room', rotta: '/control-room', icona: 'radar', sport: 'comune',
        });
        expect(inizio?.voci.find((v) => v.id === 'cash-out')).toEqual({
            id: 'cash-out', etichetta: 'Cash Out', rotta: '/cash-out', icona: 'portafoglio', sport: 'comune',
        });
        expect(titoloDi('/cash-out')).toEqual({ gruppo: null, titolo: 'Cash Out' });
        expect(titoloDi('/control-room')).toEqual({ gruppo: null, titolo: 'Control Room' });
    });

    it('rotta nel guscio e nei due rami di App.tsx (protetta nel ramo di oggi)', () => {
        expect(ROTTE_NEL_GUSCIO).toContain('/cash-out');
        expect(ROTTE_NEL_GUSCIO.indexOf('/cash-out')).toBe(ROTTE_NEL_GUSCIO.indexOf('/control-room') + 1);
        const guscio = APP.slice(APP.indexOf('function RotteGuscioV2'), APP.indexOf('function App()'));
        expect(guscio).toContain('<Route path="/cash-out" element={<CashOut />} />');
        const oggi = APP.slice(APP.indexOf('function App()'));
        expect(oggi).toMatch(/path="\/cash-out"\s*\n\s*element=\{\s*\n\s*<ProtectedRoute>\s*\n\s*<CashOut \/>/);
    });

    it('i canali della Control Room non cambiano', () => {
        expect(CANALI_DELLA_PAGINA['/control-room']).toEqual(['calcio', 'tennis', 'mike', 'omega', 'safe', 'scanner', 'tennis_bot', 'scalper']);
    });
});
