// ============================================================================
// misuraSchermo.test.ts - 11/10/2026 (M-2): la misura M1 a schermo e il clic.
//
// Tre stati per ogni misura:
//   - SPENTA (VITE_MONITOR_SALUTE assente, di serie): nessun arrivo annotato,
//     nessun timer, nessun frame chiesto, nessun `emesso_ms` nel comando;
//   - ACCESA: tratti coerenti con gli orologi finti, riassunto con la forma che
//     il Python accetta, mandato sul canale gia' aperto come richiesta `salute`;
//   - ERRORE: payload storti, canale che solleva o rifiuta: mai un'eccezione.
// Parita' col Python: bordi dei secchi, nomi dei tratti, metodo `salute`.
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn(), from: vi.fn(), channel: vi.fn(), removeChannel: vi.fn() },
}));

import {
    BORDI_MS, TRATTI_PAGINA, VERSIONE_RIASSUNTO, INTERVALLO_RIASSUNTO_MS, MAX_ARRIVI,
    __resetMisuraSchermo, __statoMisuraSchermo, inviaRiassunti, notaArrivoLadder, riassuntoDi,
    secchioDi, segnaDipinto, useMisuraDipinto, type CanaleMisura,
} from './misuraSchermo';
import { getLocalChannel, __resetLocalChannels, type LocalResponse } from './localChannel';
import { localOrderApi, __resetLocalTransport } from './localTransport';
import type { LadderOrderApi } from '@/components/live/LadderView';
import type { LiveOrderResult, LiveOrderRow, LivePositionRow } from '@/lib/liveOrders';

const RADICE = join(__dirname, '..', '..', '..');
const leggi = (...p: string[]) => readFileSync(join(RADICE, ...p), 'utf-8').replace(/\r\n/g, '\n');

// ---- mock WebSocket (speculare a localChannel.test.ts) ----
class MockWebSocket {
    static instances: MockWebSocket[] = [];
    url: string;
    sent: string[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    constructor(url: string) { this.url = url; MockWebSocket.instances.push(this); }
    send(data: string): void { this.sent.push(data); }
    close(): void { /* nei test si usa serverClose() */ }
    serverOpen(): void { this.onopen?.(); }
    serverMessage(obj: unknown): void { this.onmessage?.({ data: JSON.stringify(obj) }); }
}
const lastWs = () => MockWebSocket.instances[MockWebSocket.instances.length - 1];

// ---- orologi finti ----
let perf = 1000;
let wall = 1_760_000_000_000;
const accendi = () => vi.stubEnv('VITE_MONITOR_SALUTE', '1');

function canaleFinto(stato: 'connected' | 'off' = 'connected',
    risposta?: () => Promise<LocalResponse>): CanaleMisura & { chiamate: Array<[string, Record<string, unknown>]> } {
    const chiamate: Array<[string, Record<string, unknown>]> = [];
    return {
        sport: 'calcio',
        chiamate,
        getStatus: () => stato,
        request: (m: string, p: Record<string, unknown>) => {
            chiamate.push([m, p]);
            return risposta ? risposta() : Promise.resolve({ ok: true });
        },
    };
}

function makeDbApi(): LadderOrderApi {
    return {
        send: vi.fn(async () => ({ ok: true, action: 'place', mode: 'paper' } as LiveOrderResult)),
        fetchOrders: vi.fn(async () => [] as LiveOrderRow[]),
        fetchPositions: vi.fn(async () => [] as LivePositionRow[]),
        supportsFok: true,
    };
}

beforeEach(() => {
    perf = 1000;
    wall = 1_760_000_000_000;
    __resetMisuraSchermo({ perf: () => perf, wall: () => wall });
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    vi.stubGlobal('alphascoreCanale', { token: 'ab'.repeat(32) });
});

afterEach(() => {
    __resetMisuraSchermo();
    __resetLocalTransport();
    __resetLocalChannels();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe('parita\' col Python (Betfair/monitor)', () => {
    it('bordi dei secchi identici a registro.BORDI_MS', () => {
        const py = leggi('Betfair', 'monitor', 'registro.py');
        const blocco = py.split('BORDI_MS: tuple = (')[1].split(')')[0];
        const bordi = blocco.split(',').map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x));
        expect([...BORDI_MS]).toEqual(bordi);
    });

    it('tratti, versione e metodo identici a sonde.py', () => {
        const py = leggi('Betfair', 'monitor', 'sonde.py');
        const blocco = py.split('TRATTI_PAGINA = frozenset({')[1].split('})')[0];
        const nomi = [...blocco.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).sort();
        expect([...TRATTI_PAGINA].sort()).toEqual(nomi);
        expect(py).toContain(`VERSIONE_PAGINA = ${VERSIONE_RIASSUNTO}`);
        expect(py).toContain('METODO_PAGINA = "salute"');
        expect(INTERVALLO_RIASSUNTO_MS).toBe(30_000);
    });

    it('secchio = primo bordo >= v (bisect_left)', () => {
        expect(secchioDi(0.1)).toBe(0);
        expect(secchioDi(0.10001)).toBe(1);
        expect(secchioDi(-5)).toBe(0);
        expect(secchioDi(16)).toBe(7);          // (10, 20]
        expect(secchioDi(20)).toBe(7);
        expect(secchioDi(60000)).toBe(17);
        expect(secchioDi(60001)).toBe(18);      // troppo pieno
    });
});

describe('SPENTA (di serie)', () => {
    it('un push ladder sul canale vero non annota niente e non accende timer', () => {
        const ch = getLocalChannel('calcio');
        lastWs().serverOpen();
        const visti: unknown[] = [];
        ch.subscribe('ladder', (d) => visti.push(d));
        lastWs().serverMessage({ t: 'ladder', d: { market_id: '1.9', ts_pub_ms: wall - 5, ladder: {} } });
        expect(visti).toHaveLength(1);                       // il push arriva come sempre
        expect(__statoMisuraSchermo()).toEqual({ arrivi: 0, sport: 0, timer: false });
    });

    it('il ladder non chiede frame', () => {
        const raf = vi.fn(() => 1);
        vi.stubGlobal('requestAnimationFrame', raf);
        renderHook(() => useMisuraDipinto('1.9', { x: 1 }));
        expect(raf).not.toHaveBeenCalled();
    });

    it('il comando del ladder non porta emesso_ms', async () => {
        const api = localOrderApi('calcio', makeDbApi());
        const ws = lastWs();
        ws.serverOpen();
        api.send({ action: 'place', mode: 'paper', market_id: '1.1' }).catch(() => { /* canale chiuso a fine test */ });
        const req = JSON.parse(ws.sent[0]);
        expect(req.m).toBe('order');
        expect('emesso_ms' in req.p).toBe(false);
    });

    it('inviaRiassunti non manda niente', () => {
        const c = canaleFinto();
        notaArrivoLadder(c, { market_id: '1.9', ts_pub_ms: wall });   // chiamata diretta
        expect(inviaRiassunti()).toBe(0);
        expect(c.chiamate).toHaveLength(0);
    });
});

describe('ACCESA', () => {
    it('arrivo -> frame: i cinque tratti coerenti con gli orologi', () => {
        accendi();
        const c = canaleFinto();
        notaArrivoLadder(c, { market_id: '1.9', ts_pub_ms: wall - 3, rx_ms: wall - 8, pt: wall - 900 });
        perf += 12;                    // il frame comincia 12 ms dopo l'arrivo
        segnaDipinto('1.9');
        const r = riassuntoDi('calcio') as { v: number; bordi: number[]; tratti: Record<string, { n: number; min: number; secchi: number[] }>; contatori: Record<string, number> };
        expect(r.v).toBe(1);
        expect(r.bordi).toEqual([...BORDI_MS]);
        expect(r.tratti.pagina_canale_ms.min).toBe(3);
        expect(r.tratti.pagina_dipinto_ms.min).toBe(12);
        expect(r.tratti.pagina_pub_dipinto_ms.min).toBe(15);
        expect(r.tratti.pagina_rx_dipinto_ms.min).toBe(20);
        expect(r.tratti.pagina_pt_dipinto_ms.min).toBe(912);
        for (const t of Object.values(r.tratti)) {
            expect(t.n).toBe(1);
            expect(t.secchi.reduce((a, b) => a + b, 0)).toBe(1);
            expect(t.secchi).toHaveLength(BORDI_MS.length + 1);
        }
        expect(r.contatori).toEqual({ push_ladder: 1, dipinti: 1 });
    });

    it('un frame chiude UN arrivo; un mercato mai dipinto non produce dipinti', () => {
        accendi();
        const c = canaleFinto();
        notaArrivoLadder(c, { market_id: '1.9', ts_pub_ms: wall });
        notaArrivoLadder(c, { market_id: '1.9', ts_pub_ms: wall });    // fuso nello stesso render
        notaArrivoLadder(c, { market_id: '1.8', ts_pub_ms: wall });    // nessun ladder aperto
        segnaDipinto('1.9');
        segnaDipinto('1.9');                                             // niente da chiudere
        const r = riassuntoDi('calcio') as { contatori: Record<string, number>; tratti: Record<string, { n: number }> };
        expect(r.contatori).toEqual({ push_ladder: 3, dipinti: 1 });
        expect(r.tratti.pagina_dipinto_ms.n).toBe(1);
        expect(r.tratti.pagina_canale_ms.n).toBe(3);
        expect(__statoMisuraSchermo().arrivi).toBe(1);
    });

    it('memoria limitata: al massimo MAX_ARRIVI mercati in attesa', () => {
        accendi();
        const c = canaleFinto();
        for (let i = 0; i < MAX_ARRIVI + 50; i++) notaArrivoLadder(c, { market_id: `1.${i}` });
        expect(__statoMisuraSchermo().arrivi).toBe(MAX_ARRIVI);
    });

    it('il canale VERO annota l\'arrivo del push ladder e accende il timer', () => {
        accendi();
        getLocalChannel('tennis');
        lastWs().serverOpen();
        lastWs().serverMessage({ t: 'ladder', d: { market_id: '1.7', ts_pub_ms: wall - 2 } });
        lastWs().serverMessage({ t: 'now', d: { market_id: '1.7' } });           // altri topic: niente
        expect(__statoMisuraSchermo()).toEqual({ arrivi: 1, sport: 1, timer: true });
        expect((riassuntoDi('tennis') as { contatori: Record<string, number> }).contatori.push_ladder).toBe(1);
    });

    it('il riassunto parte sul canale gia\' aperto come richiesta salute, poi si azzera', () => {
        accendi();
        const c = canaleFinto();
        notaArrivoLadder(c, { market_id: '1.9', ts_pub_ms: wall - 1 });
        expect(inviaRiassunti()).toBe(1);
        expect(c.chiamate).toHaveLength(1);
        expect(c.chiamate[0][0]).toBe('salute');
        expect(Object.keys(c.chiamate[0][1]).sort()).toEqual(['bordi', 'contatori', 'tratti', 'v']);
        expect(riassuntoDi('calcio')).toBeNull();
        expect(inviaRiassunti()).toBe(0);                    // nulla di nuovo: nessun messaggio
    });

    it('ogni 30 s col timer, sul socket vero del runner', () => {
        vi.useFakeTimers();
        accendi();
        getLocalChannel('calcio');
        const ws = lastWs();
        ws.serverOpen();
        ws.serverMessage({ t: 'ladder', d: { market_id: '1.9', ts_pub_ms: wall - 1 } });
        expect(ws.sent).toHaveLength(0);
        vi.advanceTimersByTime(INTERVALLO_RIASSUNTO_MS);
        expect(ws.sent).toHaveLength(1);
        const req = JSON.parse(ws.sent[0]);
        expect(req.m).toBe('salute');
        expect(req.p.tratti.pagina_canale_ms.n).toBe(1);
    });

    it('il comando del ladder porta emesso_ms preso prima dell\'invio', async () => {
        accendi();
        const prima = Date.now();
        const api = localOrderApi('calcio', makeDbApi());
        const ws = lastWs();
        ws.serverOpen();
        api.send({ action: 'place', mode: 'live', market_id: '1.1' }).catch(() => { /* canale chiuso a fine test */ });
        const req = JSON.parse(ws.sent[0]);
        expect(typeof req.p.emesso_ms).toBe('number');
        expect(req.p.emesso_ms).toBeGreaterThanOrEqual(prima);
        expect(req.p.emesso_ms).toBeLessThanOrEqual(Date.now());
        const { emesso_ms: _e, client_ref: _c, ...resto } = req.p;
        expect(resto).toEqual({ action: 'place', mode: 'live', market_id: '1.1' });
    });

    it('il comando sulla coda DB (canale giu\') resta identico', async () => {
        accendi();
        const db = makeDbApi();
        const api = localOrderApi('calcio', db);
        const cmd = { action: 'place' as const, mode: 'paper' as const, market_id: '1.1' };
        await api.send(cmd);
        expect(db.send).toHaveBeenCalledWith(cmd);
    });

    it('il ladder chiede UN frame dopo il commit e lo segna', () => {
        accendi();
        const cbs: FrameRequestCallback[] = [];
        vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { cbs.push(cb); return cbs.length; });
        vi.stubGlobal('cancelAnimationFrame', vi.fn());
        const c = canaleFinto();
        notaArrivoLadder(c, { market_id: '1.9', rx_ms: wall - 4 });
        renderHook(() => useMisuraDipinto('1.9', { r: 1 }));
        expect(cbs).toHaveLength(1);
        perf += 7;
        cbs[0](perf);
        const r = riassuntoDi('calcio') as { tratti: Record<string, { min: number }> };
        expect(r.tratti.pagina_dipinto_ms.min).toBe(7);
        expect(r.tratti.pagina_rx_dipinto_ms.min).toBe(11);
    });
});

describe('ERRORE: mai propagato', () => {
    it('payload storti', () => {
        accendi();
        const c = canaleFinto();
        for (const d of [null, 3, 'x', [], {}, { market_id: 5 }, { market_id: '1.1', ts_pub_ms: 'no', rx_ms: NaN }]) {
            expect(() => notaArrivoLadder(c, d)).not.toThrow();
        }
        expect(() => segnaDipinto('inesistente')).not.toThrow();
    });

    it('canale che solleva, rifiuta o e\' giu\'', async () => {
        accendi();
        const giu = canaleFinto('off');
        notaArrivoLadder(giu, { market_id: '1.1', ts_pub_ms: wall });
        expect(inviaRiassunti()).toBe(0);                    // scartato, non accumulato
        expect(giu.chiamate).toHaveLength(0);
        expect(riassuntoDi('calcio')).toBeNull();
        const rifiuta = canaleFinto('connected', () => Promise.reject(new Error('caduto')));
        notaArrivoLadder(rifiuta, { market_id: '1.1', ts_pub_ms: wall });
        expect(inviaRiassunti()).toBe(1);
        await Promise.resolve();
        const solleva: CanaleMisura = { sport: 'calcio', getStatus: () => 'connected', request: () => { throw new Error('x'); } };
        notaArrivoLadder(solleva, { market_id: '1.1', ts_pub_ms: wall });
        expect(() => inviaRiassunti()).not.toThrow();
    });
});
