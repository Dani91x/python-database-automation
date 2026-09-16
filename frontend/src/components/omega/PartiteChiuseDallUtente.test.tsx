// ============================================================================
// PartiteChiuseDallUtente.test.tsx — «RIPRENDI», e l'elenco che lo giustifica.
//
// FALSIFICAZIONE (verificata: i test diventano rossi):
//   · «Riprendi» che non passa l'event_id → rosso;
//   · elenco vuoto per un ERRORE mostrato come «nessuna partita» → rosso;
//   · istante assente stampato come un orario → rosso.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PartiteChiuseDallUtente } from './PartiteChiuseDallUtente';
import type { OmegaEventoChiuso } from '@/lib/omega';

/** la forma VERA della RPC `omega_eventi_chiusi_dall_utente()` */
const RIGA: OmegaEventoChiuso = {
    event_id: '35760084', name: 'Trinec v Mlada Boleslav',
    stato_utente: { chiuso_dall_utente: true, quando: '2026-09-16T20:15:00Z', come: 'fuori_app' },
};

describe('l elenco delle partite chiuse dall utente', () => {
    it('mostra nome, come e quando', async () => {
        render(<PartiteChiuseDallUtente carica={async () => [RIGA]} riprendi={vi.fn()} />);
        await waitFor(() => expect(screen.getByTestId('omega-chiusa-riga')).toBeTruthy());
        const t = screen.getByTestId('omega-chiuse-dall-utente').textContent ?? '';
        expect(t).toContain('Trinec v Mlada Boleslav');
        expect(t).toMatch(/Betfair/);          // «fuori_app» tradotto
    });

    it('istante assente: «—», mai un orario inventato', async () => {
        render(<PartiteChiuseDallUtente
            carica={async () => [{ ...RIGA, stato_utente: { chiuso_dall_utente: true } }]}
            riprendi={vi.fn()} />);
        await waitFor(() => expect(screen.getByTestId('omega-chiusa-riga')).toBeTruthy());
        expect(screen.getByTestId('omega-chiusa-riga').textContent).toContain('—');
    });

    it('nessuna partita e nessun errore: il riquadro non esiste proprio', async () => {
        const { container } = render(<PartiteChiuseDallUtente carica={async () => []} riprendi={vi.fn()} />);
        await waitFor(() => expect(container.querySelector('[data-testid="omega-chiuse-dall-utente"]')).toBeNull());
    });

    it('migrazione non applicata: l ERRORE si legge, e non passa per «nessuna partita»', async () => {
        render(<PartiteChiuseDallUtente
            carica={async () => { throw new Error('function omega_eventi_chiusi_dall_utente() does not exist'); }}
            riprendi={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByTestId('omega-chiuse-errore').textContent).toMatch(/does not exist/);
        });
        expect(screen.getByTestId('omega-chiuse-errore').textContent)
            .toMatch(/non vuol dire che non ce ne siano/);
    });
});

describe('il gesto «Riprendi»', () => {
    it('passa l event_id e rilegge l elenco', async () => {
        const riprendi = vi.fn().mockResolvedValue({ ripreso: true });
        const carica = vi.fn()
            .mockResolvedValueOnce([RIGA])
            .mockResolvedValue([]);
        const onRipreso = vi.fn();
        render(<PartiteChiuseDallUtente carica={carica} riprendi={riprendi} onRipreso={onRipreso} />);
        await waitFor(() => expect(screen.getByTestId('omega-riprendi-35760084')).toBeTruthy());
        fireEvent.click(screen.getByTestId('omega-riprendi-35760084'));
        await waitFor(() => expect(riprendi).toHaveBeenCalledWith('35760084'));
        await waitFor(() => expect(onRipreso).toHaveBeenCalled());
        expect(carica).toHaveBeenCalledTimes(2);
    });

    it('la RPC che rifiuta: il messaggio si legge, la riga resta', async () => {
        const riprendi = vi.fn().mockRejectedValue(new Error('non autorizzato (owner-only)'));
        render(<PartiteChiuseDallUtente carica={async () => [RIGA]} riprendi={riprendi} />);
        await waitFor(() => expect(screen.getByTestId('omega-riprendi-35760084')).toBeTruthy());
        fireEvent.click(screen.getByTestId('omega-riprendi-35760084'));
        await waitFor(() => {
            expect(screen.getByTestId('omega-chiuse-errore').textContent).toMatch(/owner-only/);
        });
        expect(screen.getByTestId('omega-chiusa-riga')).toBeTruthy();
    });
});
