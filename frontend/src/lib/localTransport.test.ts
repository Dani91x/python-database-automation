// ============================================================================
// localTransport.test.ts — adapter LadderSource/LadderOrderApi sul canale locale:
// fallback INTEGRALE al dbSource/dbApi quando off, cache dai push quando connesso,
// INVALIDAZIONE cache su disconnessione, filtro mode sui push order/position
// (MONEY-CRITICAL: mai mescolare paper/live), mapping esiti ordine via WS
// (ok:false applicativo → result, errore busta → throw).
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// il modulo liveOrders importa il client supabase (env non presente nei test):
// qui non usiamo MAI il DB — mock inerte come negli altri test della lib.
vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn(), from: vi.fn(), channel: vi.fn(), removeChannel: vi.fn() },
}));

import type { LadderSource, LadderOrderApi } from '@/components/live/LadderView';
import type { LiveLadderRow } from '@/lib/live';
import type { LiveOrderResult, LiveOrderRow, LivePositionRow } from '@/lib/liveOrders';
import { __resetLocalChannels } from './localChannel';
import {
    localLadderSource, localOrderApi, subscribeLocalNow, __resetLocalTransport,
} from './localTransport';

// ---- mock WebSocket globale (speculare a localChannel.test.ts) ----
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
    close(): void { /* nei test si usa serverClose() */ }
    serverOpen(): void { this.onopen?.(); }
    serverMessage(obj: unknown): void { this.onmessage?.({ data: JSON.stringify(obj) }); }
    serverClose(): void { this.onclose?.(); }
}
const lastWs = () => MockWebSocket.instances[MockWebSocket.instances.length - 1];

// ---- fixture ----
const ladderRow = (marketId: string): LiveLadderRow => ({
    event_id: 'e1', market_id: marketId, market_type: 'MATCH_ODDS', market_name: 'Match Odds',
    status: 'OPEN', ladder: { updated_ms: 1, selections: [] }, updated_at: '2026-07-09T10:00:00Z',
});
const orderRow = (over: Partial<LiveOrderRow>): LiveOrderRow => ({
    id: 1, bet_id: 'b1', client_order_ref: null, request_id: null, mode: 'paper',
    event_id: 'e1', market_id: '1.1', selection_id: 101, handicap: 0, side: 'back',
    order_type: 'LIMIT', price: 2, size: 5, size_matched: 0, size_remaining: 5,
    size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 0,
    status: 'EXECUTABLE', persistence: 'LAPSE', placed_at: null, matched_at: null,
    updated_at: null, source: 'runner', ...over,
});
const positionRow = (over: Partial<LivePositionRow>): LivePositionRow => ({
    id: 1, mode: 'paper', event_id: 'e1', market_id: '1.1', selection_id: 101, handicap: 0,
    matched_if_win: 0, matched_if_lose: 0, worst_if_win: 0, worst_if_lose: 0,
    selection_exposure: 0, unmatched_back_exposure: 0, unmatched_lay_exposure: 0,
    net_position: 0, updated_at: null, ...over,
});

function makeDbSource(row: LiveLadderRow | null = null) {
    const dbUnsub = vi.fn();
    const dbSource: LadderSource = {
        fetch: vi.fn(async () => row),
        subscribe: vi.fn(() => dbUnsub),
    };
    return { dbSource, dbUnsub };
}

function makeDbApi(over: Partial<LadderOrderApi> = {}): LadderOrderApi {
    return {
        send: vi.fn(async () => ({ ok: true, action: 'place', mode: 'paper' } as LiveOrderResult)),
        fetchOrders: vi.fn(async () => [] as LiveOrderRow[]),
        fetchPositions: vi.fn(async () => [] as LivePositionRow[]),
        greenup: vi.fn(async () => ({ ok: true, action: 'greenup', mode: 'paper' } as LiveOrderResult)),
        armRule: vi.fn(async () => 42),
        supportsFok: true,
        ...over,
    };
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

// ============================================================ localLadderSource
describe('localLadderSource — fallback e cache', () => {
    it('canale OFF: fetch e subscribe delegano INTERAMENTE al dbSource', async () => {
        const row = ladderRow('1.1');
        const { dbSource, dbUnsub } = makeDbSource(row);
        const src = localLadderSource('calcio', dbSource);
        // canale mai aperto → off
        await expect(src.fetch('1.1')).resolves.toBe(row);
        expect(dbSource.fetch).toHaveBeenCalledWith('1.1');
        const cb = vi.fn();
        const unsub = src.subscribe('1.1', cb);
        expect(dbSource.subscribe).toHaveBeenCalledWith('1.1', cb);
        unsub();
        expect(dbUnsub).toHaveBeenCalled();
    });

    it('connesso: fetch = ultimo push in cache (senza toccare il DB); push filtrati per market', async () => {
        const { dbSource } = makeDbSource();
        const src = localLadderSource('calcio', dbSource);
        const ws = lastWs();
        ws.serverOpen();
        ws.serverMessage({ t: 'ladder', d: ladderRow('1.1') });
        ws.serverMessage({ t: 'ladder', d: ladderRow('9.9') });
        const got = await src.fetch('1.1');
        expect(got?.market_id).toBe('1.1');
        expect(dbSource.fetch).not.toHaveBeenCalled();

        const cb = vi.fn();
        src.subscribe('1.1', cb);
        expect(cb).toHaveBeenCalledTimes(1); // primo frame dalla cache
        ws.serverMessage({ t: 'ladder', d: ladderRow('1.1') });
        ws.serverMessage({ t: 'ladder', d: ladderRow('9.9') }); // altro mercato: ignorato
        expect(cb).toHaveBeenCalledTimes(2);
        expect(dbSource.subscribe).not.toHaveBeenCalled();
    });

    it('connesso ma senza push per il mercato: fetch fa fallback al dbSource', async () => {
        const row = ladderRow('7.7');
        const { dbSource } = makeDbSource(row);
        const src = localLadderSource('calcio', dbSource);
        lastWs().serverOpen();
        await expect(src.fetch('7.7')).resolves.toBe(row);
        expect(dbSource.fetch).toHaveBeenCalledWith('7.7');
    });

    it('DISCONNESSIONE: cache INVALIDATA (mai book congelato) e subscribe ri-delegata al DB', async () => {
        const { dbSource } = makeDbSource();
        const src = localLadderSource('calcio', dbSource);
        const ws = lastWs();
        ws.serverOpen();
        ws.serverMessage({ t: 'ladder', d: ladderRow('1.1') });
        const cb = vi.fn();
        src.subscribe('1.1', cb);
        expect(dbSource.subscribe).not.toHaveBeenCalled();

        ws.serverClose(); // caduta
        // il fetch NON deve servire la cache stantia: delega al DB
        await src.fetch('1.1');
        expect(dbSource.fetch).toHaveBeenCalledWith('1.1');
        // la sottoscrizione attiva si è ri-attaccata al dbSource da sola
        expect(dbSource.subscribe).toHaveBeenCalledWith('1.1', cb);
    });
});

// ============================================================= localOrderApi
describe('localOrderApi — send via WS', () => {
    it('canale OFF: send delega al dbApi', async () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        const cmd = { action: 'place' as const, mode: 'paper' as const, market_id: '1.1' };
        await api.send(cmd);
        expect(dbApi.send).toHaveBeenCalledWith(cmd);
    });

    it('esito applicativo ok:false → RITORNATO come result (mai throw), come il path DB', async () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        const ws = lastWs();
        ws.serverOpen();
        const p = api.send({ action: 'place', mode: 'paper', market_id: '1.1' });
        const req = JSON.parse(ws.sent[0]);
        expect(req.m).toBe('order');
        expect(req.p).toMatchObject({ action: 'place', mode: 'paper', market_id: '1.1' });
        ws.serverMessage({
            id: req.id, ok: true,
            d: { ok: false, action: 'place', mode: 'paper', error: 'LIMITE esposizione' },
        });
        const res = await p;
        expect(res.ok).toBe(false);
        expect(res.error).toBe('LIMITE esposizione');
        expect(dbApi.send).not.toHaveBeenCalled();
    });

    it('errore di busta/trasporto (e senza esito) → throw Error(e)', async () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        const ws = lastWs();
        ws.serverOpen();
        const p = api.send({ action: 'place', mode: 'paper', market_id: '1.1' });
        const guard = p.catch((e: Error) => e);
        const req = JSON.parse(ws.sent[0]);
        ws.serverMessage({ id: req.id, ok: false, e: 'coda locale piena: comando NON accettato (riprova)' });
        const err = await guard;
        expect(err).toBeInstanceOf(Error);
        expect((err as Error).message).toMatch(/coda locale piena/);
        // MONEY-CRITICAL: nessun retry automatico sul path DB (rischio doppio ordine)
        expect(dbApi.send).not.toHaveBeenCalled();
    });
});

describe('localOrderApi — specchi ordini/posizioni', () => {
    it('calcio: snapshot iniziale via WS + push successivi; filtro mode sui push', async () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        const ws = lastWs();
        ws.serverOpen();

        const p = api.fetchOrders('1.1', 'paper');
        const req = JSON.parse(ws.sent[0]);
        expect(req.m).toBe('snapshot');
        expect(req.p).toEqual({ market_id: '1.1' });
        ws.serverMessage({
            id: req.id, ok: true,
            d: {
                orders: [
                    orderRow({ id: 1, bet_id: 'paper-1', mode: 'paper' }),
                    orderRow({ id: 2, bet_id: 'live-1', mode: 'live' }),
                ],
                positions: [positionRow({ mode: 'paper', selection_id: 101 })],
            },
        });
        const rows = await p;
        // MONEY-CRITICAL: MAI mescolare mode — solo le righe paper
        expect(rows.map(r => r.bet_id)).toEqual(['paper-1']);
        expect(dbApi.fetchOrders).not.toHaveBeenCalled();

        // push successivi: aggiornano la cache (upsert per bet_id), sempre filtrati per mode
        ws.serverMessage({ t: 'order', d: orderRow({ id: 3, bet_id: 'paper-2', mode: 'paper' }) });
        ws.serverMessage({ t: 'order', d: orderRow({ id: 4, bet_id: 'live-2', mode: 'live' }) });
        ws.serverMessage({ t: 'order', d: orderRow({ id: 5, bet_id: 'no-mode', mode: 'x' as never }) }); // scartata
        const rows2 = await api.fetchOrders('1.1', 'paper');
        expect(rows2.map(r => r.bet_id).sort()).toEqual(['paper-1', 'paper-2']);

        const pos = await api.fetchPositions('1.1', 'paper');
        expect(pos).toHaveLength(1);
        expect(pos[0].selection_id).toBe(101);
    });

    it('tennis: snapshot WS vuoto by-design → seed iniziale dal dbApi', async () => {
        const seeded = orderRow({ id: 10, bet_id: 't-1', mode: 'paper', market_id: '1.2' });
        const dbApi = makeDbApi({
            fetchOrders: vi.fn(async () => [seeded]),
            fetchPositions: vi.fn(async () => [positionRow({ market_id: '1.2' })]),
        });
        const api = localOrderApi('tennis', dbApi);
        const ws = lastWs();
        expect(ws.url).toBe('ws://127.0.0.1:47332');
        ws.serverOpen();

        const rows = await api.fetchOrders('1.2', 'paper');
        expect(dbApi.fetchOrders).toHaveBeenCalledWith('1.2', 'paper');
        expect(rows.map(r => r.bet_id)).toEqual(['t-1']);
        expect(ws.sent.length).toBe(0); // nessuna richiesta snapshot WS per il tennis

        // i push tennis alimentano la stessa cache
        ws.serverMessage({ t: 'order', d: orderRow({ id: 11, bet_id: 't-2', mode: 'paper', market_id: '1.2' }) });
        const rows2 = await api.fetchOrders('1.2', 'paper');
        expect(rows2.map(r => r.bet_id).sort()).toEqual(['t-1', 't-2']);
    });

    it('canale OFF: fetchOrders/fetchPositions delegano al dbApi; su DISCONNESSIONE la cache è invalidata', async () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        // off → delega
        await api.fetchOrders('1.1', 'paper');
        expect(dbApi.fetchOrders).toHaveBeenCalledTimes(1);

        // connesso → snapshot WS + cache
        const ws = lastWs();
        ws.serverOpen();
        const p = api.fetchOrders('1.1', 'paper');
        const req = JSON.parse(ws.sent[0]);
        ws.serverMessage({ id: req.id, ok: true, d: { orders: [orderRow({})], positions: [] } });
        expect((await p).length).toBe(1);

        // caduta → cache/snapshot invalidati → di nuovo dbApi
        ws.serverClose();
        await api.fetchOrders('1.1', 'paper');
        expect(dbApi.fetchOrders).toHaveBeenCalledTimes(2);
    });
});

describe('localOrderApi — greenup e passthrough', () => {
    it('connesso: greenup instradato via send locale con la STESSA validazione buildGreenupParams', async () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        const ws = lastWs();
        ws.serverOpen();
        const p = api.greenup!({ marketId: '1.1', selectionId: 101, mode: 'paper', fraction: 0.5 });
        const req = JSON.parse(ws.sent[0]);
        expect(req.m).toBe('order');
        expect(req.p).toMatchObject({
            action: 'greenup', mode: 'paper', market_id: '1.1', selection_id: 101,
            handicap: 0, params: { fraction: 0.5 },
        });
        ws.serverMessage({ id: req.id, ok: true, d: { ok: true, action: 'greenup', mode: 'paper' } });
        await expect(p).resolves.toMatchObject({ ok: true });
        expect(dbApi.greenup).not.toHaveBeenCalled();

        // validazione condivisa: fraction<=0 rifiutata PRIMA di ogni invio
        await expect(
            api.greenup!({ marketId: '1.1', selectionId: 101, mode: 'paper', fraction: 0 }),
        ).rejects.toThrow(/fraction/);
        expect(ws.sent.length).toBe(1);
    });

    it('canale OFF: greenup delega al dbApi; dbApi senza greenup → assente anche nel wrapper', async () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        await api.greenup!({ marketId: '1.1', selectionId: 101, mode: 'paper' });
        expect(dbApi.greenup).toHaveBeenCalled();

        const noGreen = localOrderApi('tennis', makeDbApi({ greenup: undefined }));
        expect(noGreen.greenup).toBeUndefined();
    });

    it('armRule/supportsFok = passthrough al dbApi (risk rules su DB by design)', () => {
        const dbApi = makeDbApi();
        const api = localOrderApi('calcio', dbApi);
        expect(api.armRule).toBe(dbApi.armRule);
        expect(api.supportsFok).toBe(true);
        const noRules = localOrderApi('tennis', makeDbApi({ armRule: undefined, supportsFok: undefined }));
        expect(noRules.armRule).toBeUndefined();
        expect(noRules.supportsFok).toBeUndefined();
    });
});

describe('subscribeLocalNow', () => {
    it('consegna i push "now" e rispetta l\'unsubscribe', () => {
        const seen: unknown[] = [];
        const unsub = subscribeLocalNow('calcio', d => seen.push(d));
        const ws = lastWs();
        ws.serverOpen();
        ws.serverMessage({ t: 'now', d: { event_id: 'e1', state: { order_mode: 'PAPER' } } });
        expect(seen).toEqual([{ event_id: 'e1', state: { order_mode: 'PAPER' } }]);
        unsub();
        ws.serverMessage({ t: 'now', d: { event_id: 'e2' } });
        expect(seen.length).toBe(1);
    });
});
