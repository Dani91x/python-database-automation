// ============================================================================
// BottoneChiudiRiga.etichetta.test.tsx - 08/10 (cantiere W1): le due prop
// ADDITIVE del «Chiudi» di riga (`etichetta`, `ambito`). Di serie il pulsante e'
// quello di prima («Chiudi», nessun testo in piu'); con le prop dice quanto
// chiude il comando del suo bot. La richiesta mandata e' la STESSA.
// ============================================================================
import type { ReactElement } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BottoneChiudiRiga, ChiusuraRigaContext, type ChiusuraRigaApi } from './BottoneChiudiRiga';
import type { RigaDaChiudere } from './chiudiRiga';

const RIGA: RigaDaChiudere = { bot: 'mike', id: 5, eventId: 'E1', marketId: '1.OU35', modalita: 'paper', stato: 'open', chiudeId: null };

function monta(el: ReactElement, chiudi = vi.fn(async () => {})) {
    const api: ChiusuraRigaApi = { chiudi, stato: () => null };
    render(<ChiusuraRigaContext.Provider value={api}>{el}</ChiusuraRigaContext.Provider>);
    return chiudi;
}

describe('BottoneChiudiRiga: etichetta e ambito', () => {
    it('di serie: «Chiudi» e nessun testo di ambito (identico a prima)', () => {
        monta(<BottoneChiudiRiga riga={RIGA} />);
        expect(screen.getByTestId('cr-op-chiudi').textContent).toBe('Chiudi');
        expect(screen.queryByTestId('cr-op-chiudi-ambito')).toBeNull();
    });

    it('con le prop: il testo cambia, la richiesta e\' la stessa riga', () => {
        const chiudi = monta(<BottoneChiudiRiga riga={RIGA} etichetta="Cash out Mike" ambito="tutte le 3 gambe di Mike" />);
        expect(screen.getByTestId('cr-op-chiudi').textContent).toBe('Cash out Mike');
        expect(screen.getByTestId('cr-op-chiudi-ambito').textContent).toBe('tutte le 3 gambe di Mike');
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        expect(chiudi).toHaveBeenCalledWith(RIGA);
    });
});
