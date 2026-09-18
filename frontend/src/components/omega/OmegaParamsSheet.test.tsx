// ============================================================================
// OmegaParamsSheet.test.tsx — il foglio parametri di Omega montato fuori da
// `pages/Omega.tsx` (Control Room, 18/09).
//
// Non si ricollauda `ParamsSheetBase` (gia' testato) ne' `omegaParamsPatch`
// (gia' testato in `lib/omega.test.ts`): qui si certifica SOLO che questo
// componente li colleghi bene — l'obiettivo di giornata viaggia sulla
// colonna dedicata, il salvataggio manda lo stato del servizio piu' le
// modifiche vere, mai un default della UI sopra un valore vivo.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/omega', async () => {
    const actual = await vi.importActual<typeof import('@/lib/omega')>('@/lib/omega');
    return { ...actual, updateOmegaParams: vi.fn(async () => ({})) };
});

import { OmegaParamsSheet } from './OmegaParamsSheet';
import { updateOmegaParams, OMEGA_PARAM_DEFAULTS } from '@/lib/omega';

const mUpdate = vi.mocked(updateOmegaParams);

beforeEach(() => { vi.clearAllMocks(); });

async function apri(rawParams: Record<string, unknown> | null, dailyGoal: number | null = 250) {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(
        <OmegaParamsSheet rawParams={rawParams} dailyGoal={dailyGoal} onSaved={onSaved} />,
    );
    await user.click(screen.getByTestId('cr-omega-params-trigger'));
    await screen.findByTestId('params-sheet');
    return { user, onSaved };
}

describe('OmegaParamsSheet', () => {
    it('mostra l\'obiettivo di giornata corrente, letto dalla colonna dedicata', async () => {
        await apri({ min_stake: 2 }, 180);
        expect((screen.getByLabelText('Obiettivo giornaliero (€)') as HTMLInputElement).value).toBe('180');
    });

    it('senza obiettivo storicizzato mostra 250 (il ripiego dichiarato)', async () => {
        await apri({ min_stake: 2 }, null);
        expect((screen.getByLabelText('Obiettivo giornaliero (€)') as HTMLInputElement).value).toBe('250');
    });

    it('salvare manda il NUOVO obiettivo e SOLO le chiavi cambiate, mai un default sopra un valore vivo', async () => {
        const { user } = await apri({ min_stake: 0.5, v3_k_minimo: 1.2 }, 180);
        const campo = screen.getByLabelText('Obiettivo giornaliero (€)') as HTMLInputElement;
        await user.clear(campo);
        await user.type(campo, '220');
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const args = mUpdate.mock.calls[0][0];
        expect(args.dailyGoal).toBe(220);
        const payload = args.params as Record<string, unknown>;
        // le chiavi VIVE del servizio restano quelle vere, non i default della UI
        expect(payload.min_stake).toBe(0.5);
        expect(payload.v3_k_minimo).toBe(1.2);
        // e non manda l'obiettivo dentro `params` (viaggia su `dailyGoal`)
        expect(payload.__daily_goal).toBeUndefined();
    });

    it('FALSIFICAZIONE — se il default della UI sostituisse il valore del servizio, questo test lo direbbe', async () => {
        // valore del servizio DIVERSO dal default della UI, per una chiave che
        // omegaParamsPatch tratta con "manda solo se e' cambiato davvero"
        const valoreVivo = OMEGA_PARAM_DEFAULTS.v3_k_minimo + 5;
        const { user } = await apri({ v3_k_minimo: valoreVivo }, 100);
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const payload = mUpdate.mock.calls[0][0].params as Record<string, unknown>;
        expect(payload.v3_k_minimo).toBe(valoreVivo);
    });

    it('«Default» ripristina i valori di fabbrica (compreso l\'obiettivo a 250)', async () => {
        const { user } = await apri({ min_stake: 9 }, 999);
        await user.click(screen.getByTestId('params-reset'));
        expect((screen.getByLabelText('Obiettivo giornaliero (€)') as HTMLInputElement).value).toBe('250');
    });
});
