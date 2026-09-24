// ============================================================================
// RigaOrdiniReali.test.tsx - l'interruttore "Ordini reali: OFF / PAPER / LIVE".
//
// Che cosa si prova (24/09, "devo operare dalla UI, non dal codice"):
//   * ogni pulsante chiama la RPC giusta (`set_live_order_mode` col valore giusto);
//   * LIVE si conferma DUE volte, con la finestra anti-doppio-clic dei bot;
//   * il tetto dell'ambiente si vede e, se e' sotto LIVE, LIVE non si sceglie;
//   * il modo mostrato e' quello EFFETTIVO, con la STESSA regola del runner
//     (tabella identica a Betfair/stream/tests/test_modo_ordini_ui_2026_09_24.py);
//   * riga non letta / migrazione mancante -> OFF dichiarato, nessun comando.
// I finti hanno le chiavi della riga vera (`get_live_settings` = to_jsonb(s.*)).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, act, waitFor } from '@testing-library/react';
import { RigaOrdiniReali } from './RigaOrdiniReali';
import { PannelloBot } from './PannelloBot';
import type { LiveSettings } from '@/lib/liveOrders';
import type { ComandiInterruttori, ModoOrdini } from '@/lib/interruttori';

const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: (...a: unknown[]) => rpc(...a) },
}));

import { modoOrdiniEffettivo, scegliModoOrdini, statoOrdiniReali } from '@/lib/interruttori';

function riga(over: Partial<LiveSettings> = {}): LiveSettings {
    return {
        id: 1,
        kill_switch: false,
        max_exposure_per_selection: null,
        max_orders_per_min: null,
        order_poll_sec: null,
        risk_poll_sec: null,
        daily_loss_limit: null,
        max_exposure_per_event: null,
        max_exposure_per_league: null,
        updated_at: '2026-09-24T09:00:00+00:00',
        order_mode: 'paper',
        order_mode_updated_at: '2026-09-24T09:00:00+00:00',
        order_mode_updated_by: 'daniele.ritrovato@gmail.com',
        order_mode_boot_id: 'boot-1',
        order_mode_tetto: 'live',
        order_mode_tetto_at: '2026-09-24T08:00:00+00:00',
        ...over,
    };
}

function monta(r: LiveSettings | null, scrivi = vi.fn(async (_m: ModoOrdini) => r)) {
    const leggi = vi.fn(async () => r);
    const s = render(<RigaOrdiniReali leggi={leggi} scrivi={scrivi} riletturaMs={3_600_000} />);
    return { s, leggi, scrivi };
}

beforeEach(() => { vi.clearAllMocks(); vi.useRealTimers(); });

describe('la regola: la stessa del runner', () => {
    // (tetto, scelta) -> effettivo: tabella identica al test Python
    const ATTESO: [unknown, unknown, ModoOrdini][] = [
        ['OFF', 'off', 'OFF'], ['OFF', 'paper', 'OFF'], ['OFF', 'live', 'OFF'],
        ['PAPER', 'off', 'OFF'], ['PAPER', 'paper', 'PAPER'], ['PAPER', 'live', 'PAPER'],
        ['LIVE', 'off', 'OFF'], ['LIVE', 'paper', 'PAPER'], ['LIVE', 'live', 'LIVE'],
        ['OFF', null, 'OFF'], ['PAPER', null, 'OFF'], ['LIVE', null, 'OFF'],
        ['OFF', 'boh', 'OFF'], ['PAPER', 'boh', 'OFF'], ['LIVE', 'boh', 'OFF'],
        ['boh', 'live', 'OFF'], [null, 'live', 'OFF'], ['', 'live', 'OFF'],
    ];
    it.each(ATTESO)('tetto %s x scelta %s -> %s', (t, s, e) => {
        expect(modoOrdiniEffettivo(t, s)).toBe(e);
    });

    it('la migrazione mancante (niente order_mode) vale OFF e lo dice', () => {
        const r = riga();
        delete (r as Partial<LiveSettings>).order_mode;
        const st = statoOrdiniReali(r);
        expect(st.migrazioneMancante).toBe(true);
        expect(st.effettivo).toBe('OFF');
        expect(statoOrdiniReali(null).effettivo).toBe('OFF');
    });
});

describe('interruttore -> RPC giusta', () => {
    it('scegliModoOrdini chiama set_live_order_mode col valore minuscolo', async () => {
        rpc.mockResolvedValue({ data: riga({ order_mode: 'off' }), error: null });
        await scegliModoOrdini('OFF');
        expect(rpc).toHaveBeenCalledWith('set_live_order_mode', { p_mode: 'off' });
        await scegliModoOrdini('LIVE');
        expect(rpc).toHaveBeenLastCalledWith('set_live_order_mode', { p_mode: 'live' });
    });

    it('OFF e PAPER partono al primo clic', async () => {
        const { s, scrivi } = monta(riga({ order_mode: 'live' }));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toContain('LIVE'));
        fireEvent.click(s.getByTestId('cr-ordini-reali-paper'));
        await waitFor(() => expect(scrivi).toHaveBeenCalledWith('PAPER'));
        fireEvent.click(s.getByTestId('cr-ordini-reali-off'));
        await waitFor(() => expect(scrivi).toHaveBeenCalledWith('OFF'));
    });
});

describe('LIVE: doppia conferma', () => {
    it('il primo clic arma soltanto, la conferma e\' inerte nel doppio clic, poi scrive LIVE', async () => {
        const { s, scrivi } = monta(riga({ order_mode: 'paper', order_mode_tetto: 'live' }));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toContain('PAPER'));
        vi.useFakeTimers();
        fireEvent.click(s.getByTestId('cr-ordini-reali-live'));
        expect(scrivi).not.toHaveBeenCalled();
        const conferma = s.getByTestId('cr-ordini-reali-conferma-live');
        expect(conferma).toHaveProperty('disabled', true);
        fireEvent.click(conferma);
        expect(scrivi).not.toHaveBeenCalled();
        act(() => { vi.advanceTimersByTime(500); });
        fireEvent.click(s.getByTestId('cr-ordini-reali-conferma-live'));
        expect(scrivi).toHaveBeenCalledTimes(1);
        expect(scrivi).toHaveBeenCalledWith('LIVE');
    });
});

describe('il tetto dell\'ambiente si vede e comanda', () => {
    it('scelta LIVE con tetto PAPER: effettivo PAPER, avviso, LIVE non selezionabile', async () => {
        const { s, scrivi } = monta(riga({ order_mode: 'live', order_mode_tetto: 'paper' }));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toContain('PAPER'));
        expect(s.getByTestId('cr-ordini-reali-tetto').textContent).toContain("tetto dell'ambiente: PAPER");
        expect(s.getByTestId('cr-ordini-reali-limitato').textContent).toContain('vale PAPER');
        expect(s.getByTestId('cr-ordini-reali-live')).toHaveProperty('disabled', true);
        fireEvent.click(s.getByTestId('cr-ordini-reali-live'));
        expect(scrivi).not.toHaveBeenCalled();
    });

    it('scelta PAPER con tetto PAPER: LIVE non si arma nemmeno (la UI non supera il tetto)', async () => {
        const { s, scrivi } = monta(riga({ order_mode: 'paper', order_mode_tetto: 'paper' }));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-tetto').textContent).toContain('PAPER'));
        expect(s.getByTestId('cr-ordini-reali-live')).toHaveProperty('disabled', true);
        fireEvent.click(s.getByTestId('cr-ordini-reali-live'));
        expect(s.queryByTestId('cr-ordini-reali-conferma-live')).toBeNull();
        expect(scrivi).not.toHaveBeenCalled();
    });

    it('chi e quando l\'ha cambiato', async () => {
        const { s } = monta(riga({ order_mode: 'paper', order_mode_updated_by: 'avvio_app' }));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-chi').textContent).toContain("avvio dell'app"));
    });
});

describe('riga non letta: OFF dichiarato, nessun comando', () => {
    it('lettura fallita', async () => {
        const leggi = vi.fn(async () => { throw new Error('rete giu'); });
        const scrivi = vi.fn(async (_m: ModoOrdini) => null);
        const s = render(<RigaOrdiniReali leggi={leggi} scrivi={scrivi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-non-letto').textContent).toContain('OFF'));
        expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toContain('OFF');
        expect(s.getByTestId('cr-ordini-reali-paper')).toHaveProperty('disabled', true);
        expect(s.getByTestId('cr-ordini-reali-live')).toHaveProperty('disabled', true);
    });

    it('migrazione non applicata', async () => {
        const r = riga();
        delete (r as Partial<LiveSettings>).order_mode;
        const { s } = monta(r);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-non-letto').textContent).toContain('migrazione'));
        expect(s.getByTestId('cr-ordini-reali-off')).toHaveProperty('disabled', true);
    });
});

describe('sta nella plancia dei bot, non in un riquadro nuovo', () => {
    it('PannelloBot la monta dentro la sua card, prima delle righe', () => {
        const comandi = {
            accendi: vi.fn(), spegni: vi.fn(), cambiaModalita: vi.fn(), cambiaImporto: vi.fn(),
            fermaBot: vi.fn(), scriviAccensioni: vi.fn(), cambiaModalitaServizio: vi.fn(),
        } as unknown as ComandiInterruttori;
        const s = render(
            <PannelloBot righe={[]} importi={{}} comandi={comandi}
                ordiniReali={<div data-testid="riga-finta-ordini" />} />,
        );
        const card = s.getByTestId('cr-pannello-bot');
        expect(card.contains(s.getByTestId('riga-finta-ordini'))).toBe(true);
    });
});
