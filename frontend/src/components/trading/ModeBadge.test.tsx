// ============================================================================
// CERT. 13/09 — badge PAPER / LIVE di UNA riga.
//
// Il punto non è estetico: l'ASSENZA di badge non deve poter significare due
// cose opposte («è paper» / «il servizio non ha dichiarato la modalità»). Prima
// il badge esisteva solo sulle righe LIVE dello storico e da nessuna parte nel
// live, e con un control lasciato in LIVE una tabella di soldi veri si leggeva
// esattamente come una simulazione.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ModeBadge } from './ModeBadge';
import { modeMeta } from '@/lib/tradeStatus';

describe('ModeBadge', () => {
    it('PAPER: tono NEUTRO, nessun allarme', () => {
        render(<ModeBadge mode="paper" />);
        const b = screen.getByTestId('mode-badge');
        expect(b).toHaveTextContent('PAPER');
        expect(b).toHaveAttribute('data-mode', 'paper');
        expect(b.className).not.toMatch(/red/);
        expect(b.title).toMatch(/nessun denaro reale/);
    });

    it('LIVE: tono di ALLARME (rosso) e "soldi veri" nel tooltip', () => {
        render(<ModeBadge mode="live" />);
        const b = screen.getByTestId('mode-badge');
        expect(b).toHaveTextContent('LIVE');
        expect(b.className).toMatch(/red/);
        expect(b.title).toMatch(/soldi veri/);
    });

    it('modalità non dichiarata: lo DICE, non la inventa', () => {
        render(<ModeBadge mode={null} />);
        const b = screen.getByTestId('mode-badge');
        expect(b).toHaveTextContent('MODALITÀ N/D');
        expect(b).not.toHaveTextContent('PAPER');
        expect(b.title).toMatch(/non ha dichiarato/);
    });

    it('riga di un’altra modalità: attenuata e marcata, non nascosta', () => {
        render(<ModeBadge mode="live" dimmed title="il servizio è in PAPER" />);
        const b = screen.getByTestId('mode-badge');
        expect(b).toHaveAttribute('data-dimmed', '1');
        expect(b.className).toMatch(/opacity-60/);
        expect(b.title).toMatch(/il servizio è in PAPER/);
    });

    it('modeMeta: mappa PURA, case-insensitive, senza sorprese', () => {
        expect(modeMeta('LIVE').label).toBe('LIVE');
        expect(modeMeta(' paper ').label).toBe('PAPER');
        expect(modeMeta('demo').label).toBe('MODALITÀ N/D');
        expect(modeMeta(undefined).label).toBe('MODALITÀ N/D');
    });
});
