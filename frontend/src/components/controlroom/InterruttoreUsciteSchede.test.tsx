// ============================================================================
// InterruttoreUsciteSchede.test.tsx - 28/09 (CANTIERE N): nelle SCHEDE
// PARAMETRI l'interruttore delle uscite e' lo stesso componente della Control
// Room (`InterruttoreUscite`): stesse parole, e passare ad automatiche chiede
// SEMPRE la conferma. Prima nella scheda di Mike era una spunta e in quella di
// Safe (tennis) la spunta "le chiusure le approvo io": un clic, nessuna
// conferma. (Omega: `OmegaParamsSheet.test.tsx`.)
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeParamsSheet } from '@/components/mike/MikeParamsSheet';
import { BotParamsSheet } from '@/components/safestrategy/BotParamsSheet';
import { mergeMikeParams } from '@/lib/mike';
import { mergeBotParams } from '@/lib/safeBot';

describe('scheda parametri di Mike', () => {
    it('uscite: componente comune, conferma per passare ad automatiche, poi Salva', async () => {
        const user = userEvent.setup();
        const onSave = vi.fn(async () => {});
        render(<MikeParamsSheet params={mergeMikeParams({ stake: 10 })} busy={false} onSave={onSave} />);
        await user.click(screen.getByTestId('mike-params-trigger'));
        await screen.findByTestId('params-sheet');
        const ID = 'params-uscite_automatiche';
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('MANUALI, approvi tu');
        await user.click(screen.getByTestId(`cr-uscite-cambia-${ID}`));
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('MANUALI, approvi tu');
        const conferma = await screen.findByTestId(`cr-uscite-conferma-${ID}`);
        await waitFor(() => expect(conferma).not.toBeDisabled());
        await user.click(conferma);
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const salvati = onSave.mock.calls[0] as unknown as [Record<string, unknown>];
        expect(salvati[0].uscite_automatiche).toBe(true);
        // nessuna spunta libera per le uscite nella scheda
        expect(screen.queryByRole('checkbox', { name: /uscite automatiche/i })).toBeNull();
    });
});

describe('scheda parametri di Safe (tennis)', () => {
    it('"le chiusure le approvo io" e\' il componente comune: automatiche solo con conferma', async () => {
        const user = userEvent.setup();
        const onSave = vi.fn(async () => {});
        const raw = { tennis_exit_approval: true };
        render(<BotParamsSheet params={mergeBotParams(raw)} rawParams={raw} onSave={onSave} />);
        await user.click(screen.getAllByRole('button').find((b) => /parametri/i.test(b.textContent ?? ''))!);
        await screen.findByTestId('params-sheet');
        const ID = 'params-tennis_exit_approval';
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('MANUALI, approvi tu');
        await user.click(screen.getByTestId(`cr-uscite-cambia-${ID}`));
        const conferma = await screen.findByTestId(`cr-uscite-conferma-${ID}`);
        await waitFor(() => expect(conferma).not.toBeDisabled());
        await user.click(conferma);
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('AUTOMATICHE');
    });
});
