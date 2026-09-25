// ============================================================================
// RigaFreno.test.tsx - R3 (25/09): la riga FRENO della Control Room.
//
// Che cosa si prova:
//   * lo stato viene dal push del runner (`modo_ordini`/`hello.modo_ordini`,
//     chiavi VERE in lib/__fixtures__/runnerCanaleFinti.json, verificate da
//     Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py) se piu' recente
//     della lettura del database, altrimenti dal database;
//   * TIRA IL FRENO = un clic, RPC `set_live_kill_switch` con `p_on: true`;
//   * RILASCIA = due conferme (con la finestra anti-doppio-clic), poi
//     `p_on: false`; annulla torna indietro senza scrivere;
//   * freno dal .env: lo dice.
// Riga del database: `get_live_settings` = to_jsonb(betfair_live_settings).
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act, waitFor } from '@testing-library/react';
import type { LiveSettings } from '@/lib/liveOrders';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
let stato: 'connected' | 'off' = 'off';
let helloCorrente: Record<string, unknown> | null = null;
function spingi(topic: string, d: unknown): void {
    for (const cb of iscritti.get(topic) ?? []) cb(d);
}

vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn(() => ({
        getStatus: () => stato,
        getHello: () => helloCorrente,
        onStatus: () => () => { /* nessun cambio di stato nei test */ },
        subscribe: (topic: string, cb: Cb) => {
            let s = iscritti.get(topic);
            if (!s) { s = new Set(); iscritti.set(topic, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));
const rpc = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: (...a: unknown[]) => rpc(...a) },
}));

import { RigaFreno, leggiFrenoCanale, statoFreno } from './RigaFreno';
import { setKillSwitch } from '@/lib/liveOrders';
import finti from '@/lib/__fixtures__/runnerCanaleFinti.json';

function riga(over: Partial<LiveSettings> = {}): LiveSettings {
    return {
        id: 1, kill_switch: false, max_exposure_per_selection: null, max_orders_per_min: null,
        order_poll_sec: null, risk_poll_sec: null, daily_loss_limit: null, max_exposure_per_event: null,
        max_exposure_per_league: null, updated_at: '2026-09-25T20:00:00+00:00',
        order_mode: 'paper', order_mode_updated_at: '2026-09-25T12:00:00+00:00',
        order_mode_updated_by: 'avvio_app', order_mode_boot_id: 'boot-1',
        order_mode_tetto: 'live', order_mode_tetto_at: '2026-09-25T08:00:00+00:00',
        ...over,
    };
}

function monta(iniziale: LiveSettings) {
    let corrente = iniziale;
    const leggi = vi.fn(async () => corrente);
    const scrivi = vi.fn(async (on: boolean) => { corrente = { ...corrente, kill_switch: on }; return corrente; });
    const s = render(<RigaFreno leggi={leggi} scrivi={scrivi} riletturaMs={3_600_000} />);
    return { s, leggi, scrivi };
}

beforeEach(() => {
    iscritti.clear();
    stato = 'off';
    helloCorrente = null;
    rpc.mockReset();
});
afterEach(() => { vi.useRealTimers(); });

describe('lettura del freno dal messaggio del runner', () => {
    it('messaggi veri: rilasciato e tirato', () => {
        expect(leggiFrenoCanale(finti.modo_ordini)).toEqual({ tirato: false, env: false, ms: finti.modo_ordini.ts });
        expect(leggiFrenoCanale(finti.modo_ordini_freno)).toEqual({ tirato: true, env: false, ms: finti.modo_ordini_freno.ts });
    });

    it('riga non letta dal runner (e nessun freno dal .env): vale il database', () => {
        expect(leggiFrenoCanale({ ...finti.modo_ordini_freno, kill_switch_letto: false })).toBeNull();
        expect(leggiFrenoCanale({ ...finti.modo_ordini_freno, kill_switch_letto: false, kill_switch_env: true }))
            .toEqual({ tirato: true, env: true, ms: finti.modo_ordini_freno.ts });
    });

    it('runner di prima del 25/09 (senza le chiavi del freno) o messaggio storto: null', () => {
        const { kill_switch: _k, ...vecchio } = finti.modo_ordini;
        void _k;
        expect(leggiFrenoCanale(vecchio)).toBeNull();
        expect(leggiFrenoCanale(null)).toBeNull();
        expect(leggiFrenoCanale({ ...finti.modo_ordini, ts: 'ieri' })).toBeNull();
    });

    it('vince il piu\' recente fra database e push', () => {
        const push = leggiFrenoCanale(finti.modo_ordini_freno);
        expect(statoFreno(riga(), push!.ms - 1, push, push!.ms).fonte).toBe('canale');
        expect(statoFreno(riga(), push!.ms - 1, push, push!.ms).tirato).toBe(true);
        expect(statoFreno(riga(), push!.ms + 1, push, push!.ms + 1).fonte).toBe('db');
        expect(statoFreno(riga(), push!.ms + 1, push, push!.ms + 1).tirato).toBe(false);
        expect(statoFreno(null, null, null, 0).tirato).toBeNull();
    });
});

describe('la riga FRENO', () => {
    it('dal database: rilasciato, fonte "db"', async () => {
        const { s } = monta(riga());
        await waitFor(() => expect(s.getByTestId('cr-freno-stato').textContent).toMatch(/rilasciato/));
        expect(s.getByTestId('cr-freno-fonte').textContent).toMatch(/^db /);
        expect(s.queryByTestId('cr-freno-rilascia')).toBeNull();
    });

    it('il push del runner mostra il freno tirato senza aspettare il poll', async () => {
        stato = 'connected';
        const { s, leggi } = monta(riga());
        await waitFor(() => expect(s.getByTestId('cr-freno-stato').textContent).toMatch(/rilasciato/));
        await act(async () => { await new Promise((r) => setTimeout(r, 15)); });
        act(() => spingi('modo_ordini', { ...finti.modo_ordini_freno, ts: Date.now() }));
        await waitFor(() => expect(s.getByTestId('cr-freno-stato').textContent).toMatch(/TIRATO/));
        expect(s.getByTestId('cr-freno-fonte').textContent).toMatch(/^canale /);
        expect(leggi).toHaveBeenCalledTimes(1);
    });

    it('dall\'hello: chi si collega dopo vede subito il freno', async () => {
        stato = 'connected';
        helloCorrente = { ...finti.hello, modo_ordini: { ...finti.modo_ordini_freno, ts: Date.now() + 60_000 } };
        const { s } = monta(riga());
        await waitFor(() => expect(s.getByTestId('cr-freno-stato').textContent).toMatch(/TIRATO/));
    });

    it('TIRA IL FRENO: un clic, nessuna conferma, scrive true', async () => {
        const { s, scrivi } = monta(riga());
        await waitFor(() => expect(s.getByTestId('cr-freno-tira')).toBeTruthy());
        fireEvent.click(s.getByTestId('cr-freno-tira'));
        await waitFor(() => expect(scrivi).toHaveBeenCalledTimes(1));
        expect(scrivi).toHaveBeenCalledWith(true);
        await waitFor(() => expect(s.getByTestId('cr-freno-stato').textContent).toMatch(/TIRATO/));
    });

    it('RILASCIA: nulla parte prima della SECONDA conferma, poi scrive false', async () => {
        const { s, scrivi } = monta(riga({ kill_switch: true }));
        await waitFor(() => expect(s.getByTestId('cr-freno-stato').textContent).toMatch(/TIRATO/));
        expect(s.queryByTestId('cr-freno-tira')).toBeNull();
        vi.useFakeTimers();
        fireEvent.click(s.getByTestId('cr-freno-rilascia'));
        expect(scrivi).not.toHaveBeenCalled();
        // prima conferma: inerte nel doppio clic
        const c1 = s.getByTestId('cr-freno-conferma-1');
        expect(c1).toHaveProperty('disabled', true);
        fireEvent.click(c1);
        expect(s.queryByTestId('cr-freno-conferma-2')).toBeNull();
        act(() => { vi.advanceTimersByTime(500); });
        fireEvent.click(s.getByTestId('cr-freno-conferma-1'));
        expect(scrivi).not.toHaveBeenCalled();
        // seconda conferma: inerte nel doppio clic
        const c2 = s.getByTestId('cr-freno-conferma-2');
        expect(c2).toHaveProperty('disabled', true);
        fireEvent.click(c2);
        expect(scrivi).not.toHaveBeenCalled();
        act(() => { vi.advanceTimersByTime(500); });
        fireEvent.click(s.getByTestId('cr-freno-conferma-2'));
        expect(scrivi).toHaveBeenCalledTimes(1);
        expect(scrivi).toHaveBeenCalledWith(false);
    });

    it('RILASCIA poi annulla: niente scritto, si torna al pulsante', async () => {
        const { s, scrivi } = monta(riga({ kill_switch: true }));
        await waitFor(() => expect(s.getByTestId('cr-freno-rilascia')).toBeTruthy());
        fireEvent.click(s.getByTestId('cr-freno-rilascia'));
        fireEvent.click(s.getByTestId('cr-freno-annulla'));
        expect(s.getByTestId('cr-freno-rilascia')).toBeTruthy();
        expect(s.queryByTestId('cr-freno-conferma-1')).toBeNull();
        expect(scrivi).not.toHaveBeenCalled();
    });

    it('freno dal .env del runner: lo dice', async () => {
        stato = 'connected';
        helloCorrente = { ...finti.hello, modo_ordini: { ...finti.modo_ordini_freno, kill_switch_env: true, ts: Date.now() + 60_000 } };
        const { s } = monta(riga());
        await waitFor(() => expect(s.getByTestId('cr-freno-env').textContent).toMatch(/LIVE_KILL_SWITCH/));
    });

    it('stato non letto: il freno si puo\' tirare lo stesso', async () => {
        const leggi = vi.fn(async () => { throw new Error('rete giu'); });
        const scrivi = vi.fn(async () => riga({ kill_switch: true }));
        const s = render(<RigaFreno leggi={leggi} scrivi={scrivi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-freno-non-letto').textContent).toMatch(/rete giu/));
        fireEvent.click(s.getByTestId('cr-freno-tira'));
        await waitFor(() => expect(scrivi).toHaveBeenCalledWith(true));
    });
});

describe('la RPC vera', () => {
    it('setKillSwitch chiama set_live_kill_switch con p_on', async () => {
        rpc.mockResolvedValue({ data: riga({ kill_switch: true }), error: null });
        await setKillSwitch(true);
        expect(rpc).toHaveBeenCalledWith('set_live_kill_switch', { p_on: true });
        await setKillSwitch(false);
        expect(rpc).toHaveBeenLastCalledWith('set_live_kill_switch', { p_on: false });
    });
});
