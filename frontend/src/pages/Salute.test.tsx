// ============================================================================
// Salute.test.tsx - T0A (09/10/2026): la pagina «Salute».
// Le letture sono le due RPC di lib/salute (finti con le chiavi e i tipi
// dell'output di `monitor_salute_stato` / `monitor_vitalita_raccoglitori`).
// Prove: righe e semafori dai dati; stato vuoto DETTO (migrazione o monitor
// spento); nessun canale locale aperto (nessun WebSocket costruito).
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';

vi.mock('@/lib/salute', async (orig) => ({
    ...(await orig<typeof import('@/lib/salute')>()),
    leggiStatoSalute: vi.fn(),
    leggiRaccoglitori: vi.fn(),
}));

import { leggiRaccoglitori, leggiStatoSalute, type RigaSalute, type StatoSalute } from '@/lib/salute';
import Salute from './Salute';

function riga(servizio: string, sport: string, etaS: number, over: Partial<RigaSalute> = {}): RigaSalute {
    return {
        servizio, sport, ts: new Date(Date.now() - etaS * 1000).toISOString(), pid: 10, host: 'pc',
        avvio_ts: new Date(Date.now() - 3600_000).toISOString(), uptime_s: 3600, cpu_pct: 4, rss_mb: 150,
        db_richieste: 15, rest_richieste: 1,
        metriche: { v: 1, finestra_s: 30, contatori: {}, tratti: {
            canale_coda_ms: { n: 3, somma: 6, min: 1, max: 3, p50: 2, p99: 5, secchi: [] },
        }, valori: {} },
        ...over,
    };
}

function stato(ultimi: RigaSalute[]): StatoSalute {
    return {
        adesso: new Date().toISOString(), ore: 6, ultimi,
        serie: [{ servizio: 'runner-calcio', t: new Date().toISOString(), cpu_media: 10, cpu_max: 12, rss_max: 300,
                  db_richieste: 100, rest_richieste: 5, righe: 10 }],
        sistema: [{ servizio: 'runner-calcio', ts: new Date().toISOString(),
                    sistema: { python: '3.13.7', pacchetti: { flumine: '2.13.11' }, windows: { wu_riavvio_pendente: false } } }],
    };
}

function apri() {
    return render(
        <HelmetProvider>
            <MemoryRouter><Salute /></MemoryRouter>
        </HelmetProvider>,
    );
}

let costruiti = 0;
const WsVero = globalThis.WebSocket;

beforeEach(() => {
    vi.mocked(leggiStatoSalute).mockReset();
    vi.mocked(leggiRaccoglitori).mockReset();
    vi.mocked(leggiRaccoglitori).mockResolvedValue({ tabelle: [], errore: null });
    costruiti = 0;
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = class extends (WsVero as unknown as { new (u: string): object }) {
        constructor(u: string) { super(u); costruiti += 1; }
    };
});

afterEach(() => {
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = WsVero;
});

describe('pagina Salute', () => {
    it('una riga per servizio, semafori, tratti; nessun canale aperto', async () => {
        vi.mocked(leggiStatoSalute).mockResolvedValue({
            stato: stato([
                riga('runner-calcio', 'calcio', 10, { cpu_pct: 45 }),
                riga('runner-tennis', 'tennis', 200),
                riga('omega-service', 'calcio', 900),
            ]),
            errore: null,
        });
        vi.mocked(leggiRaccoglitori).mockResolvedValue({
            tabelle: [{ tabella: 'matches', colonna: 'updated_at', max: '2026-10-10T07:00:00+00:00', eta_ore: 5 }],
            errore: null,
        });
        apri();
        await waitFor(() => expect(screen.getAllByTestId('salute-riga-servizio')).toHaveLength(3));
        const righe = screen.getAllByTestId('salute-riga-servizio');
        expect(within(righe[0]).getByText('runner-calcio')).toBeTruthy();
        expect(within(righe[0]).getByTestId('salute-stato-vivo')).toBeTruthy();
        expect(within(righe[1]).getByTestId('salute-stato-ritardo')).toBeTruthy();
        expect(within(righe[2]).getByTestId('salute-stato-muto')).toBeTruthy();
        expect(within(righe[1]).getByText('tennis')).toBeTruthy();       // sport per riga: mai mischiati
        // i muti non si sommano: 2 vivi o in ritardo su 3, uno solo VIVO
        expect(screen.getByTestId('salute-kpi-servizi').textContent).toContain('1/3');
        expect(screen.getAllByTestId('salute-riga-tratto').length).toBe(3);
        expect(screen.getByTestId('salute-versioni-python').textContent).toContain('flumine 2.13.11');
        await waitFor(() => expect(screen.getAllByTestId('salute-riga-raccoglitore')).toHaveLength(1));
        expect(leggiStatoSalute).toHaveBeenCalledWith(6);
        expect(costruiti).toBe(0);
    });

    it('migrazione non applicata o monitor spento: lo DICE, non mostra zeri', async () => {
        vi.mocked(leggiStatoSalute).mockResolvedValue({ stato: null, errore: 'Could not find the function' });
        apri();
        const vuota = await screen.findByTestId('salute-vuota');
        expect(vuota.textContent).toContain('monitor_metrics_2026-10-09.sql');
        expect(vuota.textContent).toContain('MONITOR_SALUTE=1');
        expect(screen.queryByTestId('salute-kpi-cpu')).toBeNull();
    });

    it('nessuna riga nelle ultime ore: servizi vuoti dichiarati', async () => {
        vi.mocked(leggiStatoSalute).mockResolvedValue({ stato: stato([]), errore: null });
        apri();
        expect((await screen.findByTestId('salute-servizi-vuoti')).textContent).toContain('MONITOR_SALUTE=0');
        expect(screen.getByTestId('salute-kpi-servizi').textContent).toContain('0/0');
    });
});
