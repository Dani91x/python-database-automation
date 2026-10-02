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
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/omega', async () => {
    const actual = await vi.importActual<typeof import('@/lib/omega')>('@/lib/omega');
    return { ...actual, updateOmegaParams: vi.fn(async () => ({})) };
});

import { OmegaParamsSheet } from './OmegaParamsSheet';
import { updateOmegaParams, OMEGA_PARAM_DEFAULTS, OMEGA_PARAM_GROUPS, omegaParamsPatch } from '@/lib/omega';

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

    // ---- 24/09 "QUESTO PER TUTTI I BOT"; 28/09 (CANTIERE N): l'interruttore
    // delle uscite e' il componente COMUNE (stesse parole della Control Room),
    // e passare ad automatiche chiede SEMPRE la conferma (secondo clic).
    const ID = 'params-uscite_protezione';

    it('28/09 uscite: default "MANUALI, approvi tu" (chiave assente)', async () => {
        await apri({ min_stake: 0.5 }, 100);
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('MANUALI, approvi tu');
        expect(screen.getByTestId(`cr-uscite-cambia-${ID}`).textContent).toBe('passa ad automatiche');
    });

    it('valore sconosciuto sul DB -> MANUALI (fail-closed, come il servizio)', async () => {
        await apri({ uscite_protezione: 'boh' }, 100);
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('MANUALI, approvi tu');
    });

    it('passare ad automatiche CHIEDE CONFERMA; confermato e salvato manda uscite_protezione=automatico (resto invariato)', async () => {
        const { user } = await apri({ min_stake: 0.5, v3_k_minimo: 1.2 }, 100);
        await user.click(screen.getByTestId(`cr-uscite-cambia-${ID}`));
        // un solo clic non cambia niente: serve la conferma
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('MANUALI, approvi tu');
        const conferma = await screen.findByTestId(`cr-uscite-conferma-${ID}`);
        await waitFor(() => expect(conferma).not.toBeDisabled());
        await user.click(conferma);
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('AUTOMATICHE');
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const payload = mUpdate.mock.calls[0][0].params as Record<string, unknown>;
        expect(payload.uscite_protezione).toBe('automatico');
        expect(payload.min_stake).toBe(0.5);
        expect(payload.v3_k_minimo).toBe(1.2);
    });

    it('salvare SENZA toccare l\'interruttore non scrive la chiave (nessun default della UI sul DB)', async () => {
        const { user } = await apri({ min_stake: 0.5 }, 100);
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const payload = mUpdate.mock.calls[0][0].params as Record<string, unknown>;
        expect(payload).not.toHaveProperty('uscite_protezione');
    });

    it('da "automatico" si torna a MANUALI con un clic, senza conferma', async () => {
        const { user } = await apri({ uscite_protezione: 'automatico' }, 100);
        expect(screen.getByTestId(`cr-uscite-stato-${ID}`).textContent).toBe('AUTOMATICHE');
        await user.click(screen.getByTestId(`cr-uscite-cambia-${ID}`));
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        expect((mUpdate.mock.calls[0][0].params as Record<string, unknown>).uscite_protezione).toBe('avvisa_e_proponi');
    });

    it('«Default» ripristina i valori di fabbrica (compreso l\'obiettivo a 250)', async () => {
        const { user } = await apri({ min_stake: 9 }, 999);
        await user.click(screen.getByTestId('params-reset'));
        expect((screen.getByLabelText('Obiettivo giornaliero (€)') as HTMLInputElement).value).toBe('250');
    });
});

// ============================================================================
// FRONTEND MINORI, reperto 2 (02/10) - un campo numerico SVUOTATO veniva
// scritto come "" (`omegaParamsPatch`: '' diverso dal valore -> inviato).
// Regola unica: campo svuotato = chiave ASSENTE (`omega_config.resolve_params`
// usa DEFAULTS, tabella nel referto). L'obiettivo giornaliero e' una COLONNA
// (`omega_control.daily_goal`), senza valore di serie nel servizio: svuotato,
// il foglio RIFIUTA il salvataggio ("campo obbligatorio") invece di scrivere 0.
// FALSIFICAZIONE: togliendo il ramo "vuoto" da `omegaParamsPatch` o il rifiuto
// in `save` questi test tornano rossi.
// ============================================================================
const NUMERICI_OMEGA = OMEGA_PARAM_GROUPS.flatMap((g) => g.fields)
    .filter((f) => f.type === 'number').map((f) => ({ key: f.key, max: f.max as number }));

describe('OmegaParamsSheet - reperto 2: campo numerico svuotato = chiave assente', () => {
    it('omegaParamsPatch puro, OGNI campo numerico: vuoto -> chiave assente (sul DB o no), il resto identico', () => {
        const server: Record<string, unknown> = { chiave_ignota: 'x' };
        for (const f of NUMERICI_OMEGA) server[f.key] = f.max;
        const male: string[] = [];
        for (const f of NUMERICI_OMEGA) {
            const out = omegaParamsPatch(server, { ...server, [f.key]: '' });
            if (f.key in out) male.push(`${f.key}: presente (${String(out[f.key])})`);
            for (const g of NUMERICI_OMEGA) if (g.key !== f.key && out[g.key] !== g.max) male.push(`${f.key}: cambiato ${g.key}`);
            if (out.chiave_ignota !== 'x') male.push(`${f.key}: persa la chiave ignota`);
            // chiave che il servizio non ha: vuoto -> non si scrive nemmeno ""
            const senza = { ...server };
            delete senza[f.key];
            if (f.key in omegaParamsPatch(senza, { [f.key]: '' })) male.push(`${f.key}: "" scritto su chiave assente`);
        }
        expect(male).toEqual([]);
        expect(NUMERICI_OMEGA.length).toBeGreaterThan(50);
    });

    it('nel foglio vero: svuotati TUTTI i campi numerici (non l\'obiettivo) -> nessuna chiave numerica, nessun ""', async () => {
        const raw: Record<string, unknown> = { chiave_ignota: 'x' };
        for (const f of NUMERICI_OMEGA) raw[f.key] = f.max;
        const { user } = await apri(raw, 180);
        const obiettivo = screen.getByLabelText('Obiettivo giornaliero (€)');
        const inputs = Array.from(screen.getByTestId('params-sheet').querySelectorAll('input[type="number"]'))
            .filter((i) => i !== obiettivo);
        expect(inputs.length).toBe(NUMERICI_OMEGA.length);
        for (const i of inputs) {
            fireEvent.change(i, { target: { value: '1' } });
            fireEvent.change(i, { target: { value: '' } });
        }
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const args = mUpdate.mock.calls[0][0];
        const payload = args.params as Record<string, unknown>;
        expect(NUMERICI_OMEGA.filter((f) => f.key in payload).map((f) => f.key)).toEqual([]);
        expect(Object.entries(payload).filter(([, v]) => v === '').map(([k]) => k)).toEqual([]);
        expect(payload.chiave_ignota).toBe('x');
        expect(args.dailyGoal).toBe(180);
    }, 60_000);

    it('obiettivo giornaliero svuotato: salvataggio RIFIUTATO con "campo obbligatorio", nessuna scrittura', async () => {
        const { user } = await apri({ min_stake: 0.5 }, 180);
        fireEvent.change(screen.getByLabelText('Obiettivo giornaliero (€)'), { target: { value: '' } });
        await user.click(screen.getByTestId('params-save'));
        expect(await screen.findByTestId('omega-params-obbligatorio')).toHaveTextContent(/campo obbligatorio/i);
        expect(mUpdate).not.toHaveBeenCalled();
    });
});
