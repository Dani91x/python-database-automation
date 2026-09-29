// Cantiere J (28/09/2026): la partita col FLUSSO PREZZI interrotto si vede in
// Control Room. Il blocco `flusso` ha le chiavi e i tipi che scrive lo scanner
// (`Betfair/safe_strategy/service.py::flusso_evento`).
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { giudizioFlusso, type FlussoRiga } from './flussoPrezzi';
import { costruisciGiornata } from './controlRoom';
import FlussoBadge from '@/components/controlroom/FlussoBadge';

const ORA = Date.parse('2026-09-26T11:00:00Z');
const FERMO: FlussoRiga = { vivo: false, motivo: 'flusso_interrotto', dal_ms: ORA - 312_000, mercati_fermi: [] };
const VIVO: FlussoRiga = { vivo: true, motivo: null, dal_ms: ORA - 5_000, mercati_fermi: [] };

describe('giudizioFlusso', () => {
    it('26/09: prezzi fermi da 5 minuti = FLUSSO PREZZI INTERROTTO col tempo', () => {
        const g = giudizioFlusso(FERMO, ORA);
        expect(g.stato).toBe('interrotto');
        expect(g.testo).toContain('FLUSSO PREZZI INTERROTTO da 5 min');
        expect(g.testo).toContain('Nessun bot apre né chiude');
    });
    it('vivo, senza prezzi, linee ferme, dato assente', () => {
        expect(giudizioFlusso(VIVO, ORA).stato).toBe('vivo');
        expect(giudizioFlusso({ ...FERMO, motivo: 'senza_prezzi' }, ORA).stato).toBe('senza_prezzi');
        expect(giudizioFlusso({ ...VIVO, mercati_fermi: ['1.35', '1.45'] }, ORA).mercatiFermi).toBe(2);
        expect(giudizioFlusso(undefined, ORA).stato).toBe('non_dichiarato');
    });
});

describe('Control Room', () => {
    it('la giornata porta il giudizio del flusso di ogni partita', () => {
        const gruppi = costruisciGiornata({
            righe: [{ event_id: 'c1', sport: 'calcio', updated_at: new Date(ORA).toISOString(),
                payload: { event_name: 'Roma v Lazio', inplay: true, flusso: FERMO } }],
            soldi: new Map(), nowMs: ORA,
        });
        expect(gruppi[0].partite[0].flusso?.stato).toBe('interrotto');
    });
    it('il badge si vede rosso col flusso interrotto e sparisce coi prezzi vivi', () => {
        const { rerender } = render(<FlussoBadge flusso={giudizioFlusso(FERMO, ORA)} />);
        const b = screen.getByTestId('cr-flusso');
        expect(b.textContent).toContain('FLUSSO PREZZI INTERROTTO');
        expect(b.getAttribute('data-stato')).toBe('interrotto');
        rerender(<FlussoBadge flusso={giudizioFlusso(VIVO, ORA)} />);
        expect(screen.queryByTestId('cr-flusso')).toBeNull();
    });
});
