// ============================================================================
// MarchioSoldi.test.tsx - 30/09, P1_MARCHIO_FONTE: etichetta della fonte dei soldi.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MarchioSoldi } from './MarchioSoldi';
import { testoEta, type FonteSoldi } from '@/lib/fonteSoldi';

const CASI: Array<[FonteSoldi, string]> = [
    ['conto', 'CONTO BETFAIR'],
    ['bot', 'BOT'],
    ['prova', 'PROVA'],
    ['pagina', 'STIMA'],
];

describe('MarchioSoldi', () => {
    it.each(CASI)('fonte %s: etichetta e data-fonte, nessuna età', (fonte, label) => {
        render(<MarchioSoldi fonte={fonte} />);
        const el = screen.getByTestId('marchio-soldi');
        expect(el.getAttribute('data-fonte')).toBe(fonte);
        expect(el.textContent).toBe(label);
        expect(screen.queryByTestId('marchio-soldi-eta')).toBeNull();
    });

    it('età presente: «CONTO BETFAIR · 3 s fa», non arancione', () => {
        render(<MarchioSoldi fonte="conto" etaS={3} />);
        expect(screen.getByTestId('marchio-soldi-eta').textContent).toBe('· 3 s fa');
        expect(screen.getByTestId('marchio-soldi-eta').className).not.toContain('orange');
    });

    it('età 0 è un\'età vera: «0 s fa», non ignota', () => {
        render(<MarchioSoldi fonte="bot" etaS={0} />);
        const eta = screen.getByTestId('marchio-soldi-eta');
        expect(eta.textContent).toBe('· 0 s fa');
        expect(eta.className).not.toContain('orange');
    });

    it('età null: «età ignota» in arancione, mai «0 s»', () => {
        render(<MarchioSoldi fonte="conto" etaS={null} />);
        const eta = screen.getByTestId('marchio-soldi-eta');
        expect(eta.textContent).toContain('età ignota');
        expect(eta.textContent).not.toContain('0 s');
        expect(eta.className).toContain('text-orange-400');
    });

    it('dettaglio nel title, dopo il testo della fonte; testId personalizzato', () => {
        render(<MarchioSoldi fonte="prova" dettaglio="ultimo ciclo 12:00" testId="x" />);
        const t = screen.getByTestId('x').getAttribute('title') ?? '';
        expect(t).toContain('simulato (paper)');
        expect(t).toContain('ultimo ciclo 12:00');
    });

    it('title = solo il testo della fonte senza dettaglio', () => {
        render(<MarchioSoldi fonte="conto" />);
        expect(screen.getByTestId('marchio-soldi').getAttribute('title'))
            .toBe('cifra letta dal conto Betfair: comprende tutti gli ordini (bot, app e sito)');
    });
});

describe('testoEta', () => {
    it('undefined = null; null/NaN/negativa = ignota; numero = fmtAge + fa', () => {
        expect(testoEta(undefined)).toBeNull();
        expect(testoEta(null)).toBe('età ignota');
        expect(testoEta(Number.NaN)).toBe('età ignota');
        expect(testoEta(-1)).toBe('età ignota');
        expect(testoEta(125)).toBe('2 min fa');
    });
});
