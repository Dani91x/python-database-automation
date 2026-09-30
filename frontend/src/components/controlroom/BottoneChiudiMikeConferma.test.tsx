// ============================================================================
// BottoneChiudiMikeConferma.test.tsx - 30/09, difetto D5, decisione dell'utente:
// «Un clic in paper, conferma in live» per il «Chiudi» di Mike.
//   - PAPER: il primo clic manda la richiesta.
//   - LIVE: il primo clic NON manda nulla, arma («Conferma»); solo la conferma
//     manda; «annulla» disarma senza inviare. La richiesta e' identica.
//   - 30/09 16:20 (decisione dell utente): la conferma live vale per TUTTI i bot.
// Il finto dell'API ha la forma di `ChiusuraRigaApi` (stessa del vero).
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ATTESA_CONFERMA_USCITE_MS } from './InterruttoreUscite';
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

/** review incrociata 30/09 (M2): il «Conferma» e' inerte nei primi ATTESA_CONFERMA_USCITE_MS */
const attesaConferma = () => waitFor(
    () => expect(screen.getByTestId('cr-op-chiudi-conferma')).not.toBeDisabled(),
    { timeout: ATTESA_CONFERMA_USCITE_MS + 1000 },
);

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

    it('LIVE: la conferma manda la STESSA richiesta di sempre, una volta sola', async () => {
        const r = riga({ modalita: 'live' });
        const api = monta(r);
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        // review incrociata 30/09 (M2): «Conferma» inerte per ATTESA_CONFERMA_USCITE_MS
        fireEvent.click(screen.getByTestId('cr-op-chiudi-conferma'));
        expect(api.chiudi).not.toHaveBeenCalled();
        await attesaConferma();
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

    // 30/09 16:20 - decisione dell utente: la conferma live vale per TUTTI i bot.
    // Sostituisce «Omega live chiude ancora al primo clic» (superato dalla decisione).
    it.each(['omega', 'tennis_scalper', 'tennis_pro', 'safe'] as const)(
        'TUTTI i bot - %s: LIVE arma al primo clic, conferma manda la STESSA richiesta, annulla non manda; PAPER un clic',
        async (bot) => {
            const rl = riga({ bot, modalita: 'live' });
            const api = monta(rl);
            fireEvent.click(screen.getByTestId('cr-op-chiudi'));
            expect(api.chiudi).not.toHaveBeenCalled();
            fireEvent.click(screen.getByTestId('cr-op-chiudi-annulla'));
            expect(api.chiudi).not.toHaveBeenCalled();
            fireEvent.click(screen.getByTestId('cr-op-chiudi'));
            await attesaConferma();
            fireEvent.click(screen.getByTestId('cr-op-chiudi-conferma'));
            expect(api.chiudi).toHaveBeenCalledTimes(1);
            expect(api.chiudi).toHaveBeenCalledWith(rl);
        },
    );

    it.each(['omega', 'tennis_flb'] as const)('%s in PAPER: un clic, nessuna conferma', (bot) => {
        const api = monta(riga({ bot, modalita: 'paper' }));
        fireEvent.click(screen.getByTestId('cr-op-chiudi'));
        expect(api.chiudi).toHaveBeenCalledTimes(1);
        expect(screen.queryByTestId('cr-op-chiudi-conferma')).toBeNull();
    });
});
