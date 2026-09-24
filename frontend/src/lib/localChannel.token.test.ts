// C1 (24/09) - token di sessione dei canali locali, lato pagina.
// Il canale del runner accetta 'order' solo da una connessione presentata col
// token dell'app (`?t=<token>`, esposto dal preload come
// window.alphascoreCanale.token). Qui: l'URL giusto per ogni canale, il token
// mai sui canali di sola lettura, e gli ordini sulla coda DB senza token.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({ supabase: {} }));

import { __resetLocalChannels, getLocalChannel, tokenCanale, urlCanale } from '@/lib/localChannel';
import { __resetLocalTransport, localOrderApi } from '@/lib/localTransport';
import type { LadderOrderApi } from '@/components/live/LadderView';

const TOKEN = '0123456789abcdef'.repeat(4);

class MockWebSocket {
    static instances: MockWebSocket[] = [];
    url: string;
    sent: string[] = [];
    onopen: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(url: string) {
        this.url = url;
        MockWebSocket.instances.push(this);
    }
    send(data: string) { this.sent.push(data); }
    close() { /* noop */ }
    serverOpen() { this.onopen?.(); }
}

const lastWs = () => MockWebSocket.instances[MockWebSocket.instances.length - 1];

function dbApiFinto(): LadderOrderApi {
    return {
        send: vi.fn(async () => ({ ok: true, action: 'place', mode: 'paper' })),
    } as unknown as LadderOrderApi;
}

beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
});

afterEach(() => {
    __resetLocalTransport();
    __resetLocalChannels();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe('tokenCanale', () => {
    it('fuori dall app non c e', () => {
        expect(tokenCanale()).toBeNull();
    });
    it('dal preload, solo se ha la forma giusta', () => {
        vi.stubGlobal('alphascoreCanale', { token: TOKEN });
        expect(tokenCanale()).toBe(TOKEN);
        vi.stubGlobal('alphascoreCanale', { token: 'corto' });
        expect(tokenCanale()).toBeNull();
        vi.stubGlobal('alphascoreCanale', { token: 42 });
        expect(tokenCanale()).toBeNull();
    });
});

describe('urlCanale', () => {
    it('col token: SOLO i canali che comandano lo portano', () => {
        expect(urlCanale('calcio', TOKEN)).toBe(`ws://127.0.0.1:47331/?t=${TOKEN}`);
        expect(urlCanale('tennis', TOKEN)).toBe(`ws://127.0.0.1:47332/?t=${TOKEN}`);
        for (const [sport, porta] of [['mike', 47333], ['omega', 47334], ['safe', 47335],
            ['scanner', 47336], ['tennis_bot', 47337]] as const) {
            expect(urlCanale(sport, TOKEN)).toBe(`ws://127.0.0.1:${porta}`);
        }
    });
    it('senza token: URL di sempre', () => {
        expect(urlCanale('calcio', null)).toBe('ws://127.0.0.1:47331');
    });
    it('il client si collega con l URL col token del preload', () => {
        vi.stubGlobal('alphascoreCanale', { token: TOKEN });
        getLocalChannel('calcio');
        expect(lastWs().url).toBe(`ws://127.0.0.1:47331/?t=${TOKEN}`);
        expect(getLocalChannel('calcio').puoComandare()).toBe(true);
        getLocalChannel('mike');
        expect(lastWs().url).toBe('ws://127.0.0.1:47333');
        expect(getLocalChannel('mike').puoComandare()).toBe(false);
    });
});

describe('localOrderApi senza token', () => {
    it('canale connesso ma senza token: l ordine va sulla coda DB, niente sul canale', async () => {
        const dbApi = dbApiFinto();
        const api = localOrderApi('calcio', dbApi);
        const ws = lastWs();
        ws.serverOpen();
        const cmd = { action: 'place' as const, mode: 'paper' as const, market_id: '1.1' };
        await api.send(cmd);
        expect(dbApi.send).toHaveBeenCalledWith(cmd);
        expect(ws.sent).toEqual([]);
    });
    it('col token lo stesso ordine va sul canale', async () => {
        vi.stubGlobal('alphascoreCanale', { token: TOKEN });
        const dbApi = dbApiFinto();
        const api = localOrderApi('calcio', dbApi);
        const ws = lastWs();
        ws.serverOpen();
        void api.send({ action: 'place', mode: 'paper', market_id: '1.1' }).catch(() => undefined);
        expect(JSON.parse(ws.sent[0]).m).toBe('order');
        expect(dbApi.send).not.toHaveBeenCalled();
    });
});
