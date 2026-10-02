// ============================================================================
// TennisBotServiceParamsSheet.test.tsx — il foglio parametri dei 4 bot tennis
// COME SERVIZIO (18/09).
//
// I FINTI PARLANO COME IL VERO: i valori di default e i campi vengono da
// `TENNIS_BOT_REGISTRY` (`lib/tennis.ts`), lo STESSO registro verificato
// contro il codice Python dei bot (`c.get(chiave, default)`), non duplicati
// qui a mano.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn() },
}));
vi.mock('@/lib/tennis', async () => {
    const actual = await vi.importActual<typeof import('@/lib/tennis')>('@/lib/tennis');
    return { ...actual, updateTennisBotService: vi.fn(async () => ({})) };
});

import { TennisBotServiceParamsSheet } from './TennisBotServiceParamsSheet';
import { updateTennisBotService, TENNIS_BOT_REGISTRY } from '@/lib/tennis';

const mUpdate = vi.mocked(updateTennisBotService);

beforeEach(() => { vi.clearAllMocks(); });

async function apri(botKey: 'tennis_scalper' | 'tennis_flb', rawParams: Record<string, unknown> | null) {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(<TennisBotServiceParamsSheet botKey={botKey} rawParams={rawParams} onSaved={onSaved} />);
    await user.click(screen.getByTestId(`cr-tennis-params-trigger-${botKey}`));
    await screen.findByTestId('params-sheet');
    return { user, onSaved };
}

describe('TennisBotServiceParamsSheet', () => {
    it('senza parametri letti mostra i default del registro e lo DICHIARA', async () => {
        await apri('tennis_scalper', null);
        const desc = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_scalper')!;
        expect((screen.getByLabelText('Tick profitto') as HTMLInputElement).value)
            .toBe(String(desc.defaults.scalp_ticks));
        expect(screen.getByText(/parametri non ancora letti dal servizio/i)).toBeTruthy();
    });

    it('con parametri letti mostra i VALORI SALVATI, non i default', async () => {
        await apri('tennis_scalper', { scalp_ticks: 3, stop_ticks: 5, one_tick_per_phase: false });
        expect((screen.getByLabelText('Tick profitto') as HTMLInputElement).value).toBe('3');
        expect((screen.getByLabelText('Tick stop') as HTMLInputElement).value).toBe('5');
        // booleano vero -> select 'on'/'off' (stesso schema di TennisBotPanel)
        expect((screen.getByLabelText('Missione 1 tick/fase') as HTMLSelectElement).value).toBe('off');
    });

    it('salvare converte i booleani in VERI boolean (il bot Python attende bool, non stringhe)', async () => {
        const { user } = await apri('tennis_scalper', {
            scalp_ticks: 1, one_tick_per_phase: true, inplay_tick_enabled: false,
            chiave_ignota_dal_servizio: 42,
        });
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const [botKey, cambi] = mUpdate.mock.calls[0];
        expect(botKey).toBe('tennis_scalper');
        const payload = cambi.params as Record<string, unknown>;
        expect(payload.one_tick_per_phase).toBe(true);
        expect(typeof payload.one_tick_per_phase).toBe('boolean');
        expect(payload.inplay_tick_enabled).toBe(false);
        // si riparte SEMPRE dai correnti: una chiave che il registro non
        // conosce ancora non sparisce (`updateTennisBotService` sostituisce
        // l'intera colonna `params`)
        expect(payload.chiave_ignota_dal_servizio).toBe(42);
    });

    it('cambiare un numero e salvare manda il numero cambiato, non il default', async () => {
        const { user } = await apri('tennis_flb', { lay_max: 1.1, green_ticks: 8 });
        const campo = screen.getByLabelText('Lay max (quota)') as HTMLInputElement;
        fireEvent.change(campo, { target: { value: '1.15' } });
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const payload = mUpdate.mock.calls[0][1].params as Record<string, unknown>;
        expect(payload.lay_max).toBeCloseTo(1.15);
        expect(payload.green_ticks).toBe(8); // non toccato, resta quello vero
    });

    it('FALSIFICAZIONE — un select booleano NON convertito manderebbe la stringa \'on\'/\'off\'', async () => {
        // qui NON mutiamo il codice: verifichiamo che il tipo sia davvero
        // boolean (il test precedente gia' lo fa con `typeof`); qui si
        // controlla anche l'opposto esplicito (mai la stringa)
        const { user } = await apri('tennis_scalper', { one_tick_per_phase: false });
        await user.click(screen.getByTestId('params-save'));
        await waitFor(() => expect(mUpdate).toHaveBeenCalled());
        const payload = mUpdate.mock.calls[0][1].params as Record<string, unknown>;
        expect(payload.one_tick_per_phase).not.toBe('on');
        expect(payload.one_tick_per_phase).not.toBe('off');
    });
});

// ============================================================================
// FRONTEND MINORI, reperto 2 (02/10) - un campo numerico SVUOTATO veniva
// salvato 0 (`Number('')` = 0, finito). Regola unica: campo svuotato = chiave
// ASSENTE dal payload (`tennis_bot_service_update_params` sostituisce la
// colonna); il bot usa allora `c.get(chiave, default)` e lo scalper, prima, il
// preset del runner (tabella nel referto).
// FALSIFICAZIONE: togliendo il ramo "vuoto" da `save` torna 0 -> rosso.
// ============================================================================
describe('TennisBotServiceParamsSheet - reperto 2: campo numerico svuotato = chiave assente', () => {
    for (const d of TENNIS_BOT_REGISTRY) {
        const numerici = d.params.filter((f) => f.type !== 'select');
        it(`${d.key}: OGNI campo numerico (${numerici.length}) svuotato -> chiave assente, il resto identico`, async () => {
            const raw: Record<string, unknown> = { chiave_ignota_dal_servizio: 42 };
            for (const f of numerici) raw[f.key] = f.max;
            const male: string[] = [];
            for (const f of numerici) {
                mUpdate.mockClear();
                const user = userEvent.setup();
                render(<TennisBotServiceParamsSheet botKey={d.key} rawParams={raw} onSaved={vi.fn()} />);
                await user.click(screen.getByTestId(`cr-tennis-params-trigger-${d.key}`));
                await screen.findByTestId('params-sheet');
                fireEvent.change(screen.getByLabelText(f.label), { target: { value: '' } });
                await user.click(screen.getByTestId('params-save'));
                await waitFor(() => expect(mUpdate).toHaveBeenCalled());
                const payload = mUpdate.mock.calls[0][1].params as Record<string, unknown>;
                if (f.key in payload) male.push(`${f.key}: presente (${String(payload[f.key])})`);
                for (const g of numerici) if (g.key !== f.key && payload[g.key] !== g.max) male.push(`${f.key}: cambiato ${g.key}`);
                if (payload.chiave_ignota_dal_servizio !== 42) male.push(`${f.key}: persa la chiave ignota`);
                cleanup();
            }
            expect(male).toEqual([]);
            expect(numerici.length).toBeGreaterThan(0);
        }, 120_000);
    }
});
