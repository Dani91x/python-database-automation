import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { ObiettivoEditor } from './ObiettivoEditor';

describe('ObiettivoEditor', () => {
    it('mostra la matita quando non si sta modificando', () => {
        const s = render(<ObiettivoEditor valoreAttuale={50} onSalva={vi.fn()} />);
        expect(s.getByTestId('obiettivo-editor-matita')).toBeTruthy();
        expect(s.queryByTestId('obiettivo-editor-input')).toBeNull();
    });

    it('click sulla matita apre bozza precompilata col valore attuale', () => {
        const s = render(<ObiettivoEditor valoreAttuale={50} onSalva={vi.fn()} />);
        fireEvent.click(s.getByTestId('obiettivo-editor-matita'));
        const input = s.getByTestId('obiettivo-editor-input') as HTMLInputElement;
        expect(input.value).toBe('50');
    });

    it('OBIETTIVO: valore non valido NON salva', async () => {
        const onSalva = vi.fn(async () => {});
        const s = render(<ObiettivoEditor valoreAttuale={50} onSalva={onSalva} />);
        fireEvent.click(s.getByTestId('obiettivo-editor-matita'));
        fireEvent.change(s.getByTestId('obiettivo-editor-input'), { target: { value: '0' } });
        fireEvent.click(s.getByTestId('obiettivo-editor-conferma'));
        await waitFor(() => expect(s.getByTestId('obiettivo-editor-errore')).toBeTruthy());
        expect(onSalva).not.toHaveBeenCalled();
        // il campo resta aperto (non si chiude su un errore)
        expect(s.getByTestId('obiettivo-editor-input')).toBeTruthy();
    });

    it('valore valido: chiama onSalva col numero e richiude', async () => {
        const onSalva = vi.fn(async () => {});
        const s = render(<ObiettivoEditor valoreAttuale={50} onSalva={onSalva} />);
        fireEvent.click(s.getByTestId('obiettivo-editor-matita'));
        fireEvent.change(s.getByTestId('obiettivo-editor-input'), { target: { value: '75,50' } });
        fireEvent.click(s.getByTestId('obiettivo-editor-conferma'));
        await waitFor(() => expect(onSalva).toHaveBeenCalledWith(75.5));
        await waitFor(() => expect(s.queryByTestId('obiettivo-editor-input')).toBeNull());
    });

    it('annulla richiude senza chiamare onSalva', () => {
        const onSalva = vi.fn(async () => {});
        const s = render(<ObiettivoEditor valoreAttuale={50} onSalva={onSalva} />);
        fireEvent.click(s.getByTestId('obiettivo-editor-matita'));
        fireEvent.change(s.getByTestId('obiettivo-editor-input'), { target: { value: '999' } });
        fireEvent.click(s.getByTestId('obiettivo-editor-annulla'));
        expect(onSalva).not.toHaveBeenCalled();
        expect(s.queryByTestId('obiettivo-editor-input')).toBeNull();
    });

    it('errore del server (onSalva rifiutata) resta visibile e non chiude il campo', async () => {
        const onSalva = vi.fn(async () => { throw new Error('non autorizzato'); });
        const s = render(<ObiettivoEditor valoreAttuale={50} onSalva={onSalva} />);
        fireEvent.click(s.getByTestId('obiettivo-editor-matita'));
        fireEvent.change(s.getByTestId('obiettivo-editor-input'), { target: { value: '60' } });
        fireEvent.click(s.getByTestId('obiettivo-editor-conferma'));
        await waitFor(() => expect(s.getByTestId('obiettivo-editor-errore').textContent).toMatch(/non autorizzato/));
        expect(s.getByTestId('obiettivo-editor-input')).toBeTruthy();
    });

    it('mostra l’avviso onesto sul motore mentre si modifica, se passato', () => {
        const s = render(<ObiettivoEditor valoreAttuale={50} onSalva={vi.fn()} avvisoMotore="Omega è in corsa: il target cambia subito" />);
        fireEvent.click(s.getByTestId('obiettivo-editor-matita'));
        expect(s.getByTestId('obiettivo-editor-avviso').textContent).toMatch(/in corsa/);
    });
});
