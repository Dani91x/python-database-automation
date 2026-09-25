// ============================================================================
// localChannel.test.ts — client WS del canale locale: connessione+hello,
// richiesta/risposta con timeout, reconnect con backoff, reiezione pendenti
// alla caduta (MONEY-CRITICAL: "NON reinviare"), subscribe per topic.
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
    getLocalChannel, __resetLocalChannels, LOCAL_REQUEST_TIMEOUT_MS, svegliaBot,
    CANALI_SOLA_LETTURA,
} from './localChannel';

// ---- mock WebSocket globale (jsdom non lo implementa) ----
class MockWebSocket {
    static instances: MockWebSocket[] = [];
    url: string;
    sent: string[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    constructor(url: string) {
        this.url = url;
        MockWebSocket.instances.push(this);
    }
    send(data: string): void { this.sent.push(data); }
    close(): void { /* la chiusura "vera" nei test è serverClose() */ }
    // --- helper lato "server" ---
    serverOpen(): void { this.onopen?.(); }
    serverMessage(obj: unknown): void { this.onmessage?.({ data: JSON.stringify(obj) }); }
    serverClose(): void { this.onclose?.(); }
}

const lastWs = () => MockWebSocket.instances[MockWebSocket.instances.length - 1];

beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
});

afterEach(() => {
    __resetLocalChannels();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe('localChannel — connessione e hello', () => {
    it('si connette alla porta giusta per sport e cambia stato su open', () => {
        const ch = getLocalChannel('calcio');
        expect(lastWs().url).toBe('ws://127.0.0.1:47331');
        expect(ch.getStatus()).toBe('off');
        lastWs().serverOpen();
        expect(ch.getStatus()).toBe('connected');
    });

    it('tennis usa la porta 47332 e il singleton è per-sport', () => {
        const t1 = getLocalChannel('tennis');
        expect(lastWs().url).toBe('ws://127.0.0.1:47332');
        expect(getLocalChannel('tennis')).toBe(t1);
        expect(MockWebSocket.instances.length).toBe(1); // nessuna seconda connessione
    });

    it('memorizza l\'ultimo hello ({sport, mode}) e lo invalida alla caduta', () => {
        const ch = getLocalChannel('calcio');
        const ws = lastWs();
        ws.serverOpen();
        ws.serverMessage({ t: 'hello', d: { sport: 'calcio', mode: 'paper' } });
        expect(ch.getHello()).toEqual({ sport: 'calcio', mode: 'paper' });
        ws.serverClose();
        expect(ch.getHello()).toBeNull();
        expect(ch.getStatus()).toBe('off');
    });

    it('notifica i cambi di stato via onStatus (con unsubscribe)', () => {
        const ch = getLocalChannel('calcio');
        const seen: string[] = [];
        const unsub = ch.onStatus(s => seen.push(s));
        lastWs().serverOpen();
        lastWs().serverClose();
        expect(seen).toEqual(['connected', 'off']);
        unsub();
        vi.advanceTimersByTime(1000); // riconnessione
        lastWs().serverOpen();
        expect(seen).toEqual(['connected', 'off']); // dopo unsub: nessuna notifica
    });
});

describe('localChannel — porte STADIO B (18/09, raccordo): scanner 47336, bot tennis 47337', () => {
    it('scanner e tennis_bot usano le nuove porte, sola lettura, stesso meccanismo', () => {
        expect(getLocalChannel('scanner')).toBeDefined();
        expect(lastWs().url).toBe('ws://127.0.0.1:47336');
        expect(getLocalChannel('tennis_bot')).toBeDefined();
        expect(lastWs().url).toBe('ws://127.0.0.1:47337');
    });

    it('25/09: lo scalper calcio sul 47338, sola lettura (nessun token), nessuna sveglia', () => {
        expect(getLocalChannel('scalper')).toBeDefined();
        expect(lastWs().url).toBe('ws://127.0.0.1:47338');
        expect(CANALI_SOLA_LETTURA).toContain('scalper');
        const ws = lastWs();
        ws.serverOpen();
        svegliaBot('scalper', 'comando');
        expect(ws.sent.length).toBe(0);
    });

    it('porta chiusa (nessun server dietro, mai un serverOpen): nessuna eccezione, resta "off"', () => {
        expect(() => getLocalChannel('scanner')).not.toThrow();
        const ch = getLocalChannel('scanner');
        expect(ch.getStatus()).toBe('off');
        // il ripiego (retry con backoff) non deve lanciare da solo
        expect(() => vi.advanceTimersByTime(5000)).not.toThrow();
        expect(ch.getStatus()).toBe('off');
    });
});

describe('svegliaBot — STADIO C (18/09, raccordo): la sveglia dopo il clic', () => {
    it('canale connesso: manda {m:"sveglia", p:{motivo}} sulla porta del bot giusto', () => {
        const ch = getLocalChannel('mike');
        ch.onStatus(() => {}); // solo per tenere vivo il riferimento, nessun effetto
        lastWs().serverOpen();
        svegliaBot('mike', 'approvazione');
        const inviato = JSON.parse(lastWs().sent[0]) as { m: string; p: { motivo: string } };
        expect(inviato.m).toBe('sveglia');
        expect(inviato.p).toEqual({ motivo: 'approvazione' });
    });

    it('i 4 bot tennis condividono il canale 47337, non uno a bot', () => {
        const chTennisBot = getLocalChannel('tennis_bot');
        const wsTennisBot = lastWs();
        wsTennisBot.serverOpen();
        svegliaBot('tennis_scalper', 'comando');
        svegliaBot('tennis_pro', 'comando');
        expect(wsTennisBot.sent.length).toBe(2);
        expect(chTennisBot.getStatus()).toBe('connected');
    });

    it('socket NON connesso: nessuna eccezione, nessun invio, nessun retry', () => {
        // 'safe' non e' mai stato aperto in questo test: resta "off" di default
        expect(() => svegliaBot('safe', 'comando')).not.toThrow();
        expect(getLocalChannel('safe').getStatus()).toBe('off');
    });

    it('richiesta di trasporto rifiutata (timeout): nessuna eccezione visibile al chiamante', async () => {
        const ch = getLocalChannel('omega');
        lastWs().serverOpen();
        expect(() => svegliaBot('omega', 'comando')).not.toThrow();
        // la richiesta e' partita ma non arriva mai risposta: allo scadere del
        // timeout il reject interno viene assorbito da svegliaBot, non da qui
        await vi.advanceTimersByTimeAsync(LOCAL_REQUEST_TIMEOUT_MS + 100);
        expect(ch.getStatus()).toBe('connected'); // nessuna caduta indotta dalla sveglia
    });
});

describe('localChannel — richieste', () => {
    it('richiesta/risposta: id incrementale, risolve con la busta {ok,d,e}', async () => {
        const ch = getLocalChannel('calcio');
        const ws = lastWs();
        ws.serverOpen();
        const p = ch.request('order', { action: 'place' });
        const sent = JSON.parse(ws.sent[0]);
        expect(sent).toEqual({ id: 1, m: 'order', p: { action: 'place' } });
        ws.serverMessage({ id: 1, ok: true, d: { ok: true, bet_id: 'b1' } });
        await expect(p).resolves.toEqual({ ok: true, d: { ok: true, bet_id: 'b1' }, e: undefined });
        // seconda richiesta → id 2
        const p2 = ch.request('snapshot', { market_id: '1.23' });
        expect(JSON.parse(ws.sent[1]).id).toBe(2);
        ws.serverMessage({ id: 2, ok: true, d: { orders: [], positions: [] } });
        await p2;
    });

    it('rejetta subito se non connesso (mai richieste in coda al buio)', async () => {
        const ch = getLocalChannel('calcio');
        await expect(ch.request('order', {})).rejects.toThrow(/non connesso/);
    });

    it('timeout 10s: rejetta con "NON reinviare" e ignora la risposta tardiva', async () => {
        const ch = getLocalChannel('calcio');
        const ws = lastWs();
        ws.serverOpen();
        const p = ch.request('order', { action: 'place' });
        const guard = p.catch((e: Error) => e);
        vi.advanceTimersByTime(LOCAL_REQUEST_TIMEOUT_MS);
        const err = await guard;
        expect(err).toBeInstanceOf(Error);
        expect((err as Error).message).toMatch(/NON reinviare/);
        // risposta tardiva: non deve esplodere né risolvere nulla
        ws.serverMessage({ id: 1, ok: true, d: { ok: true } });
    });

    it('caduta con richiesta pendente: reject con esito NON confermato (NON reinviare)', async () => {
        const ch = getLocalChannel('calcio');
        const ws = lastWs();
        ws.serverOpen();
        const p = ch.request('order', { action: 'place' });
        const guard = p.catch((e: Error) => e);
        ws.serverClose();
        const err = await guard;
        expect((err as Error).message).toMatch(/NON confermato/);
        expect((err as Error).message).toMatch(/NON reinviare/);
    });
});

describe('localChannel — reconnect con backoff', () => {
    it('riconnette dopo 1s, poi backoff crescente fino a 5s; reset su open', () => {
        getLocalChannel('calcio');
        expect(MockWebSocket.instances.length).toBe(1);
        lastWs().serverOpen();
        lastWs().serverClose();          // caduta → riconnessione in 1s (backoff → 2s)
        vi.advanceTimersByTime(999);
        expect(MockWebSocket.instances.length).toBe(1);
        vi.advanceTimersByTime(1);
        expect(MockWebSocket.instances.length).toBe(2);
        lastWs().serverClose();          // mai aperta → prossimo tentativo in 2s
        vi.advanceTimersByTime(1999);
        expect(MockWebSocket.instances.length).toBe(2);
        vi.advanceTimersByTime(1);
        expect(MockWebSocket.instances.length).toBe(3);
        lastWs().serverOpen();           // successo → backoff azzerato
        lastWs().serverClose();
        vi.advanceTimersByTime(1000);
        expect(MockWebSocket.instances.length).toBe(4);
    });

    it('il backoff non supera i 5s', () => {
        getLocalChannel('calcio');
        // fallisci più volte di quanto serva a saturare il backoff (1,2,3,4,5,5,...)
        for (let i = 0; i < 6; i++) {
            lastWs().serverClose();
            vi.advanceTimersByTime(5000);
        }
        const n = MockWebSocket.instances.length;
        lastWs().serverClose();
        vi.advanceTimersByTime(5000);   // al tetto: 5s bastano SEMPRE
        expect(MockWebSocket.instances.length).toBe(n + 1);
    });
});

describe('localChannel — subscribe per topic', () => {
    it('smista i push al topic giusto e rispetta l\'unsubscribe', () => {
        const ch = getLocalChannel('calcio');
        const ws = lastWs();
        ws.serverOpen();
        const ladders: unknown[] = [];
        const nows: unknown[] = [];
        const unsubLadder = ch.subscribe('ladder', d => ladders.push(d));
        ch.subscribe('now', d => nows.push(d));
        ws.serverMessage({ t: 'ladder', d: { market_id: '1.1' } });
        ws.serverMessage({ t: 'now', d: { event_id: 'e1' } });
        ws.serverMessage({ t: 'board', d: { rows: [] } });   // topic senza iscritti: ignorato
        expect(ladders).toEqual([{ market_id: '1.1' }]);
        expect(nows).toEqual([{ event_id: 'e1' }]);
        unsubLadder();
        ws.serverMessage({ t: 'ladder', d: { market_id: '1.2' } });
        expect(ladders.length).toBe(1);
    });
});
