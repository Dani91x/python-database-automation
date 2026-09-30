// ============================================================================
// BottoneChiudiMikeConferma.test.tsx - 30/09, difetto D5, decisione dell'utente:
// «Un clic in paper, conferma in live» per il «Chiudi» di Mike.
//   - PAPER: il primo clic manda la richiesta.
//   - LIVE: il primo clic NON manda nulla, arma («Conferma»); solo la conferma
//     manda; «annulla» disarma senza inviare. La richiesta e' identica.
//   - Gli altri bot restano a un clic (nessun cambiamento fuori perimetro).
// Il finto dell'API ha la forma di `ChiusuraRigaApi` (stessa del vero).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BottoneChiudiRiga, ChiusuraRigaContext, type ChiusuraRigaApi } from './BottoneChiudiRiga';
import type { RigaDaChiudere } from './chiudiRiga';

function riga(over: Partial<RigaDaChiudere> = {}): RigaDaChiudere {
    return {
        bot: 'mike', id: 801, eventId: 'E2', marketId: '1.9', modalita: 'paper', stato: 'open',
        chiudeId: null, regolata: false, ...over,
    };
}

function monta(r: RigaDaChiudere, stimaOra?: number | null) {
    const api: ChiusuraRigaApi = {
        chiudi: vi.fn(async () => undefined),
        stato: vi.fn(() => null),
    };
    render(
        <ChiusuraRigaContext.Provider value={api}>
            <BottoneChiudiRiga riga={r} stimaOra={stimaOra} />
        </ChiusuraRigaContext.Provider>,
    );
    return api;
}

describe('D5 - Chiudi di Mike: un clic in paper, conferma in live', () => {
    it('PAPER: il primo clic chiude, senza conferma', () => {
        const api = monta(riga({ modalita: 'paper' }));
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        expect(api.chiudi).toHaveBeenCalledTimes(1);
        expect(screen.queryByTestId('cr-op-chiudi-conferma')).toBeNull();
    });

    it('LIVE: il primo clic NON manda, chiede conferma con la stima', () => {
        const api = monta(riga({ modalita: 'live' }), 4.75);
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        expect(api.chiudi).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-op-chiudi-conferma')).toBeTruthy();
        expect(screen.getByTestId('cr-op-chiudi-armato').textContent).toMatch(/soldi veri/);
        expect(screen.getByTestId('cr-op-chiudi-armato').textContent).toMatch(/4[.,]75/);
    });

    it('LIVE: la conferma manda la STESSA richiesta di sempre, una volta sola', () => {
        const r = riga({ modalita: 'live' });
        const api = monta(r);
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        fireEvent.click(screen.getByTestId('cr-op-chiudi-conferma'));
        expect(api.chiudi).toHaveBeenCalledTimes(1);
        expect(api.chiudi).toHaveBeenCalledWith(r);
    });

    it('LIVE: annulla disarma senza mandare nulla e il Chiudi torna al primo passaggio', () => {
        const api = monta(riga({ modalita: 'live' }));
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        fireEvent.click(screen.getByTestId('cr-op-chiudi-annulla'));
        expect(api.chiudi).not.toHaveBeenCalled();
        expect(screen.queryByTestId('cr-op-chiudi-conferma')).toBeNull();
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        expect(api.chiudi).not.toHaveBeenCalled();
    });

    it('modalita\' IGNOTA (null): bottone spento, nessuna richiesta, nessuna conferma armata', () => {
        // fail-closed: lo blocca `chiudibile` a monte; se non lo facesse, la conferma
        // scatterebbe comunque (`modalita !== 'paper'`). Vedi la falsificazione nel referto.
        const api = monta(riga({ modalita: null }));
        const b = screen.getByTestId('cr-op-chiudi');
        expect(b).toBeDisabled();
        fireEvent.click(b);
        expect(api.chiudi).not.toHaveBeenCalled();
        expect(screen.queryByTestId('cr-op-chiudi-conferma')).toBeNull();
        expect(screen.queryByTestId('cr-op-chiudi-armato')).toBeNull();
    });

    it('gli altri bot non cambiano: Omega live chiude ancora al primo clic', () => {
        const api = monta(riga({ bot: 'omega', modalita: 'live' }));
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        expect(api.chiudi).toHaveBeenCalledTimes(1);
    });
});
