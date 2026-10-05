// Test COMPONENTE per ScalperPanel (fix audit #28): un fallimento PERSISTENTE
// (≥3 di fila) di get_scalper_state deve produrre un avviso esplicito — prima
// il catch era muto e il pannello mostrava per sempre uno stato vecchio.
//
// 25/09 sera: sniper_mode ACCESO di default (ordine dell'utente, testuale:
// <<scalper, modalita' sniper: acceso>>). Il form nasce con lo sniper
// spuntato e lo manda esplicito (true/false) all'attivazione.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/scalper', () => ({
    activateScalper: vi.fn(),
    stopScalper: vi.fn(),
    fetchScalperState: vi.fn(),
    SCALPER_PARAM_DEFAULTS: { one_green_per_phase: true },
    SCALPER_PARAM_FIELDS: [],
}));

import { ScalperPanel } from './ScalperPanel';
import { activateScalper, fetchScalperState } from '@/lib/scalper';

const mState = vi.mocked(fetchScalperState);
const mActivate = vi.mocked(activateScalper);

beforeEach(() => {
    vi.clearAllMocks();
});

describe('ScalperPanel — fix audit #28 (errori persistenti visibili)', () => {
    it('3+ fallimenti di fila di get_scalper_state → banner esplicito', async () => {
        mState.mockRejectedValue(new Error('permission denied'));
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={15} />);
        // dopo ≥3 poll falliti compare l'avviso (i primi 2 blip restano silenziosi).
        expect(await screen.findByText(/Stato scalper NON aggiornato/, undefined,
            { timeout: 3000 })).toBeInTheDocument();
        expect(screen.getByText(/permission denied/)).toBeInTheDocument();
    });

    it('un successo azzera il contatore: nessun banner dopo un blip singolo', async () => {
        mState.mockRejectedValueOnce(new Error('blip'));
        mState.mockResolvedValue({ control: null, activity: [] });
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={15} />);
        await waitFor(() => expect(mState.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 3000 });
        expect(screen.queryByText(/Stato scalper NON aggiornato/)).not.toBeInTheDocument();
    });
});

describe('ScalperPanel — sniper ACCESO di default (ordine dell\'utente 25/09 sera)', () => {
    it('il form nasce con lo sniper spuntato e lo manda acceso (true esplicito) all\'attivazione', async () => {
        mState.mockResolvedValue({ control: null, activity: [] });
        mActivate.mockResolvedValue({} as never);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={100_000} />);
        await waitFor(() => expect(mState).toHaveBeenCalled());

        fireEvent.click(screen.getByText('Attiva Scalper Bot'));
        const sniperCheckbox = screen.getByRole('checkbox', { name: /SNIPER in-play/ });
        expect(sniperCheckbox).toBeChecked();

        fireEvent.click(screen.getByText(/Attiva in PAPER/));
        await waitFor(() => expect(mActivate).toHaveBeenCalledTimes(1));
        const params = mActivate.mock.calls[0][4] as Record<string, unknown>;
        expect(params.sniper_mode).toBe(true);
    });

    it('spegnendo il checkbox lo sniper parte spento (sniper_mode=false ESPLICITO, mai assente)', async () => {
        mState.mockResolvedValue({ control: null, activity: [] });
        mActivate.mockResolvedValue({} as never);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={100_000} />);
        await waitFor(() => expect(mState).toHaveBeenCalled());

        fireEvent.click(screen.getByText('Attiva Scalper Bot'));
        const sniperCheckbox = screen.getByRole('checkbox', { name: /SNIPER in-play/ });
        fireEvent.click(sniperCheckbox);
        expect(sniperCheckbox).not.toBeChecked();

        fireEvent.click(screen.getByText(/Attiva in PAPER/));
        await waitFor(() => expect(mActivate).toHaveBeenCalledTimes(1));
        const params = mActivate.mock.calls[0][4] as Record<string, unknown>;
        expect(params.sniper_mode).toBe(false);
    });
});

describe('ScalperPanel — MEDIA UNDER (05/10, SPEC_MEDIA_UNDER_2026-10-05.md)', () => {
    it('spenta di serie: l\'attivazione normale non manda la modalità', async () => {
        mState.mockResolvedValue({ control: null, activity: [] });
        mActivate.mockResolvedValue({} as never);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={100_000} />);
        await waitFor(() => expect(mState).toHaveBeenCalled());
        fireEvent.click(screen.getByText('Attiva Scalper Bot'));
        expect(screen.getByRole('checkbox', { name: /MEDIA UNDER/ })).not.toBeChecked();
        fireEvent.click(screen.getByText(/Attiva in PAPER/));
        await waitFor(() => expect(mActivate).toHaveBeenCalledTimes(1));
        const params = mActivate.mock.calls[0][4] as Record<string, unknown>;
        expect(params.media_mode).toBeUndefined();
    });

    it('accesa: senza mercato non parte; col mercato manda tutti i parametri e spegne lo sniper', async () => {
        mState.mockResolvedValue({ control: null, activity: [] });
        mActivate.mockResolvedValue({} as never);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={100_000} />);
        await waitFor(() => expect(mState).toHaveBeenCalled());
        fireEvent.click(screen.getByText('Attiva Scalper Bot'));
        fireEvent.click(screen.getByRole('checkbox', { name: /MEDIA UNDER/ }));
        expect(screen.getByRole('checkbox', { name: /SNIPER in-play/ })).not.toBeChecked();
        fireEvent.click(screen.getByText(/Attiva in PAPER/));
        expect(mActivate).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText('Mercato della Media Under'), { target: { value: 'OVER_UNDER_35' } });
        fireEvent.click(screen.getByText(/Attiva in PAPER/));
        await waitFor(() => expect(mActivate).toHaveBeenCalledTimes(1));
        const params = mActivate.mock.calls[0][4] as Record<string, unknown>;
        expect(params.media_mode).toBe(true);
        expect(params.media_mercato).toBe('OVER_UNDER_35');
        expect(params.media_stake).toBe(10);
        expect(params.media_obiettivi_live).toEqual([0, 0.3, 1]);
        expect(params.sniper_mode).toBe(false);
        expect(params.theta_mode).toBe(false);
        expect(params.ht_mode).toBe(false);
    });

    it('la sessione attiva mostra lo stato del ciclo e il riquadro di chiusura', async () => {
        mState.mockResolvedValue({
            control: {
                event_id: 'evt1', status: 'running', mode: 'maker', dry_run: true, stake: 25,
                params: { media_mode: true }, bias: null, bias_meta: null, error: null,
                requested_at: '2026-10-05T10:00:00Z', started_at: null, stopped_at: null,
                heartbeat_at: null,
                stats: {
                    media_stato: 'LIVE', media_mercato: 'OVER_UNDER_25', media_rientri: 2,
                    media_max_rientri: 5, media_totale_puntato: 40, media_quota_media: 1.525,
                    media_se_vince: 21, media_se_perde: -40,
                    media_banca: { stato: 'caduta', importo: 40.13, quota: 1.52, abbinato: 0,
                                   testo: "la banca non e' piu' a mercato" },
                    media_chiusura: {
                        fonte: 'solo ordini del bot', tick: 2, banca: { stato: 'caduta' },
                        posizione: { totale_puntato: 40, quota_media: 1.525, banche_abbinate: 0,
                                     se_vince: 21, se_perde: -40 },
                        chiudi_adesso: { banca: 36.53, quota: 1.67, pnl_lordo: -3.47, pnl_netto: -3.47 },
                        obiettivi: [],
                    },
                },
            },
            activity: [],
        } as never);
        render(<ScalperPanel eventId="evt1" eventName="A-B" pollMs={100_000} />);
        expect(await screen.findByText(/Media Under — Under 2,5/)).toBeInTheDocument();
        expect(screen.getByText(/NESSUN ordine, gestisci tu la chiusura/)).toBeInTheDocument();
        expect(screen.getByText(/2 su 5/)).toBeInTheDocument();
        expect(screen.getByText(/non e' piu' a mercato/)).toBeInTheDocument();
        expect(screen.getByText(/Chiusura — solo ordini del bot/)).toBeInTheDocument();
        expect(screen.getByText(/BANCA €36,53/)).toBeInTheDocument();
    });
});

