// R5 (25/09/2026): l'etichetta unica "aggiornato al ... (eta')" delle tab Dashboard.
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { EtaDato } from './EtaDato';

const NOW = new Date('2026-09-25T12:00:00Z');
const oreFa = (h: number) => new Date(NOW.getTime() - h * 3_600_000).toISOString();

describe('EtaDato', () => {
    it('verde entro la soglia, con data ed eta', () => {
        const s = render(<EtaDato etichetta="Previsione ML" at={oreFa(3)} sogliaOre={36} now={NOW} />);
        const el = s.getByTestId('eta-dato');
        expect(el.dataset.stato).toBe('fresco');
        expect(el.className).toContain('text-emerald-400');
        expect(el.className).not.toContain('text-red-400');
        expect(el.textContent).toMatch(/Previsione ML: aggiornato al .*\(3 h fa\)/);
        expect(el.textContent).not.toMatch(/oltre/);
    });

    it('ROSSO oltre la soglia, e dice quale soglia ha superato', () => {
        const s = render(<EtaDato etichetta="Calibrazione" at={oreFa(24 * 10)} sogliaOre={24 * 8} now={NOW} />);
        const el = s.getByTestId('eta-dato');
        expect(el.dataset.stato).toBe('vecchio');
        expect(el.className).toContain('text-red-400');
        expect(el.textContent).toMatch(/\(10 g fa\).*oltre 8 g/);
    });

    it('ROSSO quando il dato manca, con il testo scelto dal pannello', () => {
        const s = render(<EtaDato etichetta="Pagella" at={null} sogliaOre={36} now={NOW} testoAssente="pagella vuota" testId="x" />);
        const el = s.getByTestId('x');
        expect(el.dataset.stato).toBe('assente');
        expect(el.className).toContain('text-red-400');
        expect(el.textContent).toBe('Pagella: pagella vuota');
    });
});
