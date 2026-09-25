// ============================================================================
// RigaOrdiniReali.canale.test.tsx - 25/09 (voce 6): la riga "Ordini reali"
// dal canale del runner calcio (47331) prima del poll dei 30 s.
//
// Finti = messaggi VERI:
//  - hello: Betfair/stream/local_channel.py:353 {"sport", "mode"} (mode =
//    LIVE_ORDER_MODE del runner, runner.py:1798);
//  - now: Betfair/stream/db.py:294-309 riga di live_now; `state` da
//    runner.py:259-303 con order_mode / order_mode_tetto / order_mode_scelto /
//    updated_ms;
//  - riga del database: `get_live_settings` = to_jsonb(betfair_live_settings)
//    (stesse chiavi del test storico RigaOrdiniReali.test.tsx).
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act, waitFor } from '@testing-library/react';
import type { LiveSettings } from '@/lib/liveOrders';

type Cb = (d: unknown) => void;
const iscritti = new Map<string, Set<Cb>>();
let stato: 'connected' | 'off' = 'off';
let helloCorrente: Record<string, unknown> | null = null;
const statoCb = new Set<(s: 'connected' | 'off') => void>();
function spingi(topic: string, d: unknown): void {
    for (const cb of iscritti.get(topic) ?? []) cb(d);
}

vi.mock('@/lib/localChannel', async (orig) => ({
    ...(await orig() as object),
    getLocalChannel: vi.fn(() => ({
        getStatus: () => stato,
        getHello: () => helloCorrente,
        onStatus: (cb: (s: 'connected' | 'off') => void) => { statoCb.add(cb); return () => { statoCb.delete(cb); }; },
        subscribe: (topic: string, cb: Cb) => {
            let s = iscritti.get(topic);
            if (!s) { s = new Set(); iscritti.set(topic, s); }
            s.add(cb);
            return () => { s.delete(cb); };
        },
        request: async () => ({ ok: true }),
    })),
}));
vi.mock('@/integrations/supabase/client', () => ({ supabase: { rpc: vi.fn() } }));

import { RigaOrdiniReali } from './RigaOrdiniReali';
import finti from '@/lib/__fixtures__/runnerCanaleFinti.json';

function riga(over: Partial<LiveSettings> = {}): LiveSettings {
    return {
        id: 1, kill_switch: false, max_exposure_per_selection: null, max_orders_per_min: null,
        order_poll_sec: null, risk_poll_sec: null, daily_loss_limit: null, max_exposure_per_event: null,
        max_exposure_per_league: null, updated_at: '2026-09-25T09:00:00+00:00',
        order_mode: 'paper', order_mode_updated_at: '2026-09-25T09:00:00+00:00',
        order_mode_updated_by: 'avvio_app', order_mode_boot_id: 'boot-1',
        order_mode_tetto: 'live', order_mode_tetto_at: '2026-09-25T08:00:00+00:00',
        ...over,
    };
}

function now(state: Record<string, unknown>) {
    return {
        event_id: '34567890', inplay: true, minute: 30, score_home: 1, score_away: 0,
        status: 'OPEN', score_source: 'ips',
        state: { markets: [], ...state },
        updated_at: new Date().toISOString(),
    };
}

beforeEach(() => {
    iscritti.clear();
    statoCb.clear();
    stato = 'off';
    helloCorrente = null;
});

describe('Ordini reali dal canale 47331', () => {
    it('canale spento: la lettura del database, fonte "db"', async () => {
        const leggi = vi.fn(async () => riga());
        const s = render(<RigaOrdiniReali leggi={leggi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/));
        expect(s.getByTestId('cr-ordini-reali-fonte').textContent).toMatch(/^db /);
    });

    it('now fresco: effettivo del runner, fonte "canale"; scelta diversa -> rilettura SUBITO', async () => {
        stato = 'connected';
        helloCorrente = { sport: 'calcio', mode: 'LIVE' };
        let sblocca: (r: LiveSettings) => void = () => { /* assegnata sotto */ };
        let n = 0;
        const leggi = vi.fn(async () => {
            n += 1;
            if (n === 1) return riga();
            return new Promise<LiveSettings>((res) => { sblocca = res; });
        });
        const s = render(<RigaOrdiniReali leggi={leggi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/));
        // il runner pubblica DOPO la lettura (orologio che avanza)
        await act(async () => { await new Promise((r) => setTimeout(r, 15)); });
        act(() => spingi('now', now({
            order_mode: 'LIVE', order_mode_tetto: 'LIVE', order_mode_scelto: 'LIVE', updated_ms: Date.now(),
        })));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/LIVE/));
        expect(s.getByTestId('cr-ordini-reali-fonte').textContent).toMatch(/^canale /);
        // il poll e' a un'ora: la seconda lettura l'ha chiesta il canale
        await waitFor(() => expect(leggi).toHaveBeenCalledTimes(2));
        await act(async () => { sblocca(riga({ order_mode: 'live', order_mode_updated_by: 'daniele' })); });
        // il database ha raggiunto il runner: chi/quando nuovi, fonte di nuovo "db"
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-chi').textContent).toMatch(/daniele/));
        expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/LIVE/);
        expect(s.getByTestId('cr-ordini-reali-fonte').textContent).toMatch(/^db /);
    });

    it('tetto dall\'hello del runner collegato: LIVE non si sceglie se il SUO .env e\' PAPER', async () => {
        stato = 'connected';
        helloCorrente = { sport: 'calcio', mode: 'PAPER' };
        const leggi = vi.fn(async () => riga({ order_mode_tetto: 'live' }));
        const s = render(<RigaOrdiniReali leggi={leggi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-tetto').textContent).toMatch(/PAPER/));
        expect((s.getByTestId('cr-ordini-reali-live') as HTMLButtonElement).disabled).toBe(true);
    });

    // 25/09 (punto 6): topic `modo_ordini` = modo_ordini.stato_corrente() + ts,
    // SOLO al cambio (live_order_worker._pubblica_modo_ordini_se_cambiato);
    // messaggi veri in lib/__fixtures__/runnerCanaleFinti.json
    it('modo_ordini al cambio, SENZA partite seguite: aggiorna senza poll e rilegge chi/quando', async () => {
        stato = 'connected';
        helloCorrente = { sport: 'calcio', mode: 'LIVE' };
        const leggi = vi.fn(async () => riga());
        const s = render(<RigaOrdiniReali leggi={leggi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/));
        await act(async () => { await new Promise((r) => setTimeout(r, 15)); });
        act(() => spingi('modo_ordini', { ...finti.modo_ordini_live, ts: Date.now() }));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/LIVE/));
        expect(s.getByTestId('cr-ordini-reali-fonte').textContent).toMatch(/^canale /);
        // il poll e' a un'ora: la seconda lettura l'ha chiesta il cambio del runner
        await waitFor(() => expect(leggi).toHaveBeenCalledTimes(2));
    });

    it('modo_ordini dall\'hello: chi si collega dopo il cambio lo vede subito', async () => {
        stato = 'connected';
        const leggi = vi.fn(async () => riga());
        const s = render(<RigaOrdiniReali leggi={leggi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/));
        await act(async () => { await new Promise((r) => setTimeout(r, 15)); });
        act(() => spingi('hello', {
            ...finti.hello, modo_ordini: { ...finti.hello.modo_ordini, effettivo: 'OFF', motivo: 'db_assente', scelto_ui: null, ts: Date.now() },
        }));
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/OFF/));
        expect(s.getByTestId('cr-ordini-reali-fonte').textContent).toMatch(/^canale /);
    });

    it('modo_ordini storto (senza ts): nessun effetto', async () => {
        stato = 'connected';
        helloCorrente = { sport: 'calcio', mode: 'LIVE' };
        const leggi = vi.fn(async () => riga());
        const s = render(<RigaOrdiniReali leggi={leggi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/));
        const storto: Record<string, unknown> = { ...finti.modo_ordini_live };
        delete storto.ts;
        act(() => spingi('modo_ordini', storto));
        await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
        expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/);
        expect(leggi).toHaveBeenCalledTimes(1);
    });

    it('now di un runner di prima (senza order_mode): nessun effetto', async () => {
        stato = 'connected';
        const leggi = vi.fn(async () => riga());
        const s = render(<RigaOrdiniReali leggi={leggi} riletturaMs={3_600_000} />);
        await waitFor(() => expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/));
        act(() => spingi('now', now({ updated_ms: Date.now() })));
        await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
        expect(s.getByTestId('cr-ordini-reali-effettivo').textContent).toMatch(/PAPER/);
        expect(leggi).toHaveBeenCalledTimes(1);
    });
});
