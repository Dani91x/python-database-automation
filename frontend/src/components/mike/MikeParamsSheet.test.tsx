// Test del pannello parametri di Mike, ora sul componente CONDIVISO
// (ParamsSheetBase): clamp dichiarato, "Default", filtro competizioni come
// testo libero, salvataggio dell'oggetto intero passato da mergeMikeParams.
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeParamsSheet } from './MikeParamsSheet';
import { MIKE_PARAM_DEFAULTS, MIKE_PARAM_GROUP_LABEL } from '@/lib/mike';

async function open(params = { ...MIKE_PARAM_DEFAULTS }, onSave = vi.fn()) {
    // `userEvent.setup()` (e non l'API diretta): il pannello e' una Sheet di
    // Radix e senza la sessione utente il click sul trigger non apre nulla.
    const user = userEvent.setup();
    render(<MikeParamsSheet params={params} busy={false} onSave={onSave} />);
    await user.click(screen.getByTestId('mike-params-trigger'));
    await screen.findByTestId('params-sheet');
    return { onSave, user };
}

describe('MikeParamsSheet', () => {
    it('mostra tutti i gruppi del bot', async () => {
        await open();
        for (const label of Object.values(MIKE_PARAM_GROUP_LABEL)) {
            expect(screen.getByText(label), label).toBeInTheDocument();
        }
    });

    it('il filtro competizioni è un campo di TESTO (non un numero)', async () => {
        const { user } = await open();
        const input = screen.getByLabelText('Filtro competizioni');
        expect(input).toHaveAttribute('type', 'text');
        await user.type(input, 'serie a');
        expect(input).toHaveValue('serie a');
    });

    it('un valore fuori limite viene clampato e DICHIARATO', async () => {
        const { user } = await open();
        const stake = screen.getByLabelText('Stake Under 3.5 (€)');
        await user.clear(stake);
        await user.type(stake, '9000');
        const clamped = await screen.findByTestId('params-clamped');
        expect(clamped).toHaveTextContent('clampato a 500');
        expect(screen.getByTestId('params-dirty')).toBeInTheDocument();
    });

    it('Default riporta ai valori del servizio e Salva manda l’oggetto intero', async () => {
        const { onSave, user } = await open({ ...MIKE_PARAM_DEFAULTS, stake: 25 });
        expect(screen.getByLabelText('Stake Under 3.5 (€)')).toHaveValue(25);
        await user.click(screen.getByTestId('params-reset'));
        expect(screen.getByLabelText('Stake Under 3.5 (€)')).toHaveValue(10);
        await user.click(screen.getByTestId('params-save'));
        expect(onSave).toHaveBeenCalledTimes(1);
        const sent = onSave.mock.calls[0][0] as Record<string, unknown>;
        expect(sent.stake).toBe(10);
        // i parametri inerti non esistono più (audit M3)
        expect(sent).not.toHaveProperty('max_matches');
        expect(sent).not.toHaveProperty('stream_extra_lines');
    });
});
