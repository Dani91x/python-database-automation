// 24/09 - la barra dichiara lo stimato e le posizioni in corso; l'avanzamento
// comprende l'in corso, "obiettivo centrato" solo il realizzato.
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DayBar } from './DayBar';

describe('DayBar: reale, stimato, in corso', () => {
    it('scrive la parte stimata e le posizioni in corso', () => {
        render(<DayBar dayLabel="oggi" realized={5} realizedEstimated={-1} inProgress={2} goal={10} />);
        expect(screen.getByTestId('day-bar-stimato').textContent).toContain('stimato');
        expect(screen.getByTestId('day-bar-in-corso').textContent).toContain('in corso (stimato)');
        // avanzamento = 5 + 2 su 10 = 70%
        expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('70');
        expect(screen.getByTestId('day-bar-remaining')).toBeTruthy();
    });
    it('l in corso non basta per dire obiettivo centrato', () => {
        render(<DayBar dayLabel="oggi" realized={5} inProgress={6} goal={10} />);
        expect(screen.queryByTestId('day-bar-goal-hit')).toBeNull();
        expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100');
    });
    it('senza le props nuove e identica a prima', () => {
        render(<DayBar dayLabel="oggi" realized={10} goal={10} />);
        expect(screen.queryByTestId('day-bar-stimato')).toBeNull();
        expect(screen.queryByTestId('day-bar-in-corso')).toBeNull();
        expect(screen.getByTestId('day-bar-goal-hit')).toBeTruthy();
    });
});
