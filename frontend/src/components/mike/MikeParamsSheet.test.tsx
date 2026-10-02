// Test del pannello parametri di Mike, ora sul componente CONDIVISO
// (ParamsSheetBase): clamp dichiarato, "Default", filtro competizioni come
// testo libero, salvataggio dell'oggetto intero passato da mergeMikeParams.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MikeParamsSheet } from './MikeParamsSheet';
import {
    MIKE_PARAM_DEFAULTS, MIKE_PARAM_GROUP_LABEL, MIKE_PARAM_FIELDS, mergeMikeParams, parametriMikeDaSalvare,
} from '@/lib/mike';

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

// ============================================================================
// FRONTEND MINORI, reperto 2 (02/10) - un campo numerico SVUOTATO veniva
// salvato al MINIMO del campo (`mergeMikeParams`: Number('') = 0, poi clamp):
// uno stake svuotato diventava 0,50. Regola unica: campo svuotato = chiave
// ASSENTE dal payload; `mike_update_params` sostituisce la colonna e
// `Betfair/mike/config.py` `merge_params` usa DEFAULTS (tabella nel referto).
// FALSIFICAZIONE: togliendo il ramo "vuoto" da `parametriMikeDaSalvare` o da
// `mergeMikeParams` questi test tornano rossi.
// ============================================================================
const NUMERICI = MIKE_PARAM_FIELDS.filter((f) => f.kind === 'number').map((f) => f.key);

describe('MikeParamsSheet - reperto 2: campo numerico svuotato = chiave assente', () => {
    it('mergeMikeParams: "" su un numero vale il DEFAULT, mai il minimo del campo', () => {
        const male = NUMERICI.filter((k) => mergeMikeParams({ [k]: '' })[k] !== MIKE_PARAM_DEFAULTS[k]);
        expect(male).toEqual([]);
    });

    it('puro, OGNI campo numerico: vuoto -> chiave assente, tutti gli altri identici, nessun ""', () => {
        // valori diversi dal default (il massimo del campo): si vede se qualcosa cambia
        const v: Record<string, number | boolean | string> = { ...MIKE_PARAM_DEFAULTS };
        for (const f of MIKE_PARAM_FIELDS) if (f.kind === 'number') v[f.key] = f.max;
        const base = parametriMikeDaSalvare(v);
        const male: string[] = [];
        for (const k of NUMERICI) {
            const out = parametriMikeDaSalvare({ ...v, [k]: '' });
            if (k in out) male.push(`${k}: presente (${String(out[k])})`);
            for (const altro of Object.keys(base)) {
                if (altro !== k && out[altro] !== base[altro]) male.push(`${k}: cambiato anche ${altro}`);
            }
            for (const [d, x] of Object.entries(out)) {
                if (NUMERICI.includes(d) && typeof x !== 'number') male.push(`${k}: ${d} non numero`);
            }
        }
        expect(male).toEqual([]);
        expect(NUMERICI.length).toBeGreaterThan(50);
    });

    it('nel foglio vero: svuotati TUTTI i campi numerici e salvato -> nessuna chiave numerica, il resto intero', async () => {
        const { onSave, user } = await open({ ...MIKE_PARAM_DEFAULTS, stake: 25 });
        const inputs = Array.from(screen.getByTestId('params-sheet').querySelectorAll('input[type="number"]'));
        expect(inputs.length).toBe(NUMERICI.length);
        for (const i of inputs) {
            fireEvent.change(i, { target: { value: '1' } });
            fireEvent.change(i, { target: { value: '' } });
        }
        await user.click(screen.getByTestId('params-save'));
        expect(onSave).toHaveBeenCalledTimes(1);
        const sent = onSave.mock.calls[0][0] as Record<string, unknown>;
        expect(NUMERICI.filter((k) => k in sent)).toEqual([]);
        // i campi non numerici restano (filtro competizioni, interruttori, scelte)
        for (const f of MIKE_PARAM_FIELDS) if (f.kind !== 'number') expect(sent, f.key).toHaveProperty(f.key);
    }, 60_000);

    it('lo stake svuotato non diventa 0,50: la chiave non c\'e\' (il servizio usa 10)', async () => {
        const { onSave, user } = await open({ ...MIKE_PARAM_DEFAULTS, stake: 25 });
        await user.clear(screen.getByLabelText('Stake Under 3.5 (€)'));
        await user.click(screen.getByTestId('params-save'));
        const sent = onSave.mock.calls[0][0] as Record<string, unknown>;
        expect('stake' in sent).toBe(false);
    });
});
