// ============================================================================
// TennisBotPanel.superficie.test.tsx - 25/09 (decisione utente).
//
// tennis_pro: la SUPERFICIE della partita la decide il runner dal nome del
// torneo (Betfair/stream/tennis_scalper/superficie.py) e la scrive nei params
// della riga tennis_bot_control (tennis_runner._scrivi_superficie). Il pannello
// per partita la MOSTRA con la sua fonte; non la sceglie piu'.
// Le varianti trend/adapt/maker partono ACCESE.
//
// I FINTI PARLANO COME IL VERO: la riga di control ha le chiavi di
// TennisBotControl + le chiavi che il runner scrive (surface, surface_fonte,
// surface_voce, surface_torneo, surface_testo), coi valori che
// superficie.risolvi produce davvero.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const stato: { controls: unknown[] } = { controls: [] };

vi.mock('@/lib/tennis', async () => {
    const actual = await vi.importActual<typeof import('@/lib/tennis')>('@/lib/tennis');
    return {
        ...actual,
        fetchTennisBotsState: vi.fn(async () => ({ controls: stato.controls, activity: [] })),
        subscribeTennisBots: vi.fn(() => () => { /* no-op */ }),
        armTennisBot: vi.fn(async (eventId: string, botKey: string, dryRun: boolean,
            stake: number, params: Record<string, number | string | boolean>) => ({
            event_id: eventId, bot_key: botKey, status: 'requested', dry_run: dryRun, stake,
            params, stats: null, error: null, requested_at: null, started_at: null,
            stopped_at: null, heartbeat_at: null,
        })),
        disarmTennisBot: vi.fn(),
    };
});

import { TennisBotPanel } from './TennisBotPanel';
import { armTennisBot, superficieDaParams, TENNIS_BOT_REGISTRY } from '@/lib/tennis';

const mArm = vi.mocked(armTennisBot);

/** Riga VERA di tennis_bot_control dopo l'armamento del runner. */
function rigaPro(params: Record<string, unknown>) {
    return {
        event_id: 'evt1', bot_key: 'tennis_pro', status: 'running', dry_run: false, stake: 2,
        params, stats: null, error: null, requested_at: null, started_at: null,
        stopped_at: null, heartbeat_at: null,
    };
}

// i params come li scrive il runner (superficie.Superficie.come_params)
const ROLAND = {
    bp_target_ticks: 5, surface: 'clay', surface_fonte: 'mappa', surface_voce: 'Roland Garros',
    surface_torneo: 'Roland Garros 2026', surface_testo: 'terra (mappa: Roland Garros)',
};
const IGNOTO = {
    surface: 'hard', surface_fonte: 'default', surface_voce: 'torneo sconosciuto',
    surface_torneo: 'Torneo Mai Visto', surface_testo: 'cemento (default: torneo sconosciuto)',
};

async function cardPro() {
    render(<TennisBotPanel eventId="evt1" marketId="mkt1" orderMode="PAPER" />);
    await screen.findByText('Tennis Pro');
    const el = screen.getByText('Tennis Pro').closest('div.rounded-xl.border') as HTMLElement;
    return within(el);
}

beforeEach(() => {
    vi.clearAllMocks();
    stato.controls = [];
});

describe('superficieDaParams (lettura dei params scritti dal runner)', () => {
    it('mappa: "terra (mappa: Roland Garros)"', () => {
        const s = superficieDaParams(ROLAND)!;
        expect(s.testo).toBe('terra (mappa: Roland Garros)');
        expect(s.testo).toBe(ROLAND.surface_testo);   // stesso testo del Python
        expect(s.fonte).toBe('mappa');
    });

    it('default dichiarato: "cemento (default: torneo sconosciuto)"', () => {
        const s = superficieDaParams(IGNOTO)!;
        expect(s.testo).toBe(IGNOTO.surface_testo);
        expect(s.fonte).toBe('default');
    });

    it('senza fonte NON inventa: "fonte non dichiarata"', () => {
        const s = superficieDaParams({ surface: 'grass' })!;
        expect(s.fonte).toBeNull();
        expect(s.testo).toBe('erba (fonte non dichiarata)');
    });

    it('senza superficie: null (il runner non l\'ha ancora scritta)', () => {
        expect(superficieDaParams({})).toBeNull();
        expect(superficieDaParams(null)).toBeNull();
    });
});

describe('TennisBotPanel - superficie di tennis_pro a video', () => {
    it('mostra superficie e fonte della mappa', async () => {
        stato.controls = [rigaPro(ROLAND)];
        const card = await cardPro();
        await waitFor(() => expect(card.getByTestId('tennis-pro-superficie').textContent)
            .toBe('superficie: terra (mappa: Roland Garros)'));
        expect(card.getByTestId('tennis-pro-superficie').getAttribute('title'))
            .toBe('torneo: Roland Garros 2026');
    });

    it('mostra il default DICHIARATO (in ambra)', async () => {
        stato.controls = [rigaPro(IGNOTO)];
        const card = await cardPro();
        await waitFor(() => expect(card.getByTestId('tennis-pro-superficie').textContent)
            .toBe('superficie: cemento (default: torneo sconosciuto)'));
        expect(card.getByTestId('tennis-pro-superficie').className).toContain('amber');
    });

    it('superficie senza fonte: in rosso, "fonte non dichiarata"', async () => {
        stato.controls = [rigaPro({ surface: 'grass' })];
        const card = await cardPro();
        await waitFor(() => expect(card.getByTestId('tennis-pro-superficie').textContent)
            .toBe('superficie: erba (fonte non dichiarata)'));
        expect(card.getByTestId('tennis-pro-superficie').className).toContain('red');
    });

    it('prima dell\'armamento dice chi la decide', async () => {
        const card = await cardPro();
        expect(card.getByTestId('tennis-pro-superficie').textContent)
            .toMatch(/la decide il runner/);
    });

    it('solo tennis_pro mostra la riga superficie', async () => {
        render(<TennisBotPanel eventId="evt1" marketId="mkt1" orderMode="PAPER" />);
        await screen.findByText('Tennis Pro');
        expect(screen.getAllByTestId('tennis-pro-superficie')).toHaveLength(1);
    });
});

describe('TennisBotPanel - varianti di tennis_pro ACCESE di default', () => {
    it('ARMA senza toccare nulla: trend/adapt/maker = true, nessuna "surface" nel payload', async () => {
        const user = userEvent.setup();
        const card = await cardPro();
        await user.click(card.getByRole('button', { name: /ARMA/i }));
        await waitFor(() => expect(mArm).toHaveBeenCalledTimes(1));
        const params = mArm.mock.calls[0][4] as Record<string, unknown>;
        expect(params.trend).toBe(true);
        expect(params.adapt).toBe(true);
        expect(params.maker).toBe(true);
        expect(params).not.toHaveProperty('surface');
    });

    it('il registro non espone piu\' la superficie come parametro', () => {
        const pro = TENNIS_BOT_REGISTRY.find((d) => d.key === 'tennis_pro')!;
        expect(pro.params.map((f) => f.key)).not.toContain('surface');
        expect(pro.defaults).not.toHaveProperty('surface');
    });
});
