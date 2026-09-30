// ============================================================================
// DayBar.aperto.test.tsx - W_G/P6 (30/09): i parametri NUOVI e OPZIONALI della
// DayBar (usata anche da Mike/Omega/Safe). Senza di loro la barra e' quella di
// prima; con loro: realizzato che manca detto, aperto tratteggiato nella barra.
// ============================================================================
import { describe, expect, it } from 'vitest';
import { render, within } from '@testing-library/react';
import { DayBar } from './DayBar';

describe('DayBar - parametri opzionali di W_G', () => {
    it('senza i parametri nuovi: niente aperto, niente nota, niente «—» inventato (le altre pagine non cambiano)', () => {
        const s = render(<DayBar dayLabel="mercoledì 30 settembre" realized={null} goal={100} operations={0} live={2} />);
        expect(s.queryByTestId('day-bar-aperto')).toBeNull();
        expect(s.queryByTestId('day-bar-aperto-barra')).toBeNull();
        expect(s.queryByTestId('day-bar-realizzato')).toBeNull();
        expect(s.queryByTestId('day-bar-rischio')).toBeNull();
        expect(s.getByTestId('day-bar-counts').textContent).toContain('2 vive');
    });

    it('realizzato mancante con `realizedMissing`: «—» e il perche\'', () => {
        const s = render(<DayBar dayLabel="x" realized={null} realizedMissing="conto non letto: P&L dalle righe dei bot" />);
        expect(s.getByTestId('day-bar-realizzato').textContent).toBe('—');
        expect(s.getByTestId('day-bar-realizzato-nota').textContent).toBe('conto non letto: P&L dalle righe dei bot');
    });

    it('aperto +10 su realizzato +20 e obiettivo 100: barra al 30 %, tratteggio dal 20 % largo 10 %', () => {
        const s = render(<DayBar dayLabel="x" realized={20} goal={100} openNow={10}
            openNowNode={<span>aperto adesso +10</span>} liveLabel="partite con posizione LIVE" operations={0} live={1} />);
        const barra = s.getByRole('progressbar');
        expect(barra.getAttribute('aria-valuenow')).toBe('30');
        const t = within(barra).getByTestId('day-bar-aperto-barra');
        expect(t.style.left).toBe('20%');
        expect(t.style.width).toBe('10%');
        expect(s.getByTestId('day-bar-aperto').textContent).toBe('aperto adesso +10');
        expect(s.getByTestId('day-bar-counts').textContent).toContain('1 partite con posizione LIVE');
        // «obiettivo centrato» resta sul SOLO realizzato
        expect(s.queryByTestId('day-bar-goal-hit')).toBeNull();
    });
});
