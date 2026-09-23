// ============================================================================
// ladderAlMs.test.ts - sorgente ladder "al ms" (ordine utente 23/09): canale
// locale come via principale, realtime DB SOLO a canale assente/muto, ritorno al
// canale appena riprende, freschezza su ladder.updated_ms, una sola lettura DB,
// parita' ladderDaCanale <-> riga live_ladder.
//
// I finti parlano come il vero: il push e' la busta di local_channel.py
// {"t": "ladder", "d": row} con `row` costruita come nel ladder_worker di
// Betfair/stream/runner.py (event_id, market_id, market_type, market_name,
// status, ladder={updated_ms, selections=[build_ladder_selection...]}); la riga
// DB e' la stessa dict + id + updated_at (db.upsert_live_ladder).
// Il canale e' il LocalChannel VERO su un WebSocket finto.
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn(), from: vi.fn(), channel: vi.fn(), removeChannel: vi.fn() },
}));

import type { LadderSource } from '@/components/live/LadderView';
import type { LiveLadderRow } from '@/lib/live';
import { __resetLocalChannels, getLocalChannel } from './localChannel';
import {
    ladderDaCanale, piuFresca, sorgenteLadderAlMs, __resetLocalTransport,
    LADDER_MUTO_MS_DEFAULT, LADDER_POTATURA_MS_DEFAULT,
} from './localTransport';

class MockWebSocket {
    static instances: MockWebSocket[] = [];
    url: string;
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    constructor(url: string) { this.url = url; MockWebSocket.instances.push(this); }
    send(): void { /* niente richieste in questi test */ }
    close(): void { /* serverClose() nei test */ }
    serverOpen(): void { this.onopen?.(); }
    serverMessage(obj: unknown): void { this.onmessage?.({ data: JSON.stringify(obj) }); }
    serverClose(): void { this.onclose?.(); }
}
const wsDi = (porta: number) => {
    const w = [...MockWebSocket.instances].reverse().find((x) => x.url.endsWith(`:${porta}`));
    if (!w) throw new Error(`nessun socket sulla porta ${porta}`);
    return w;
};

// --- riga come la costruisce il ladder_worker del runner (chiavi e tipi veri) ---
const MID = '1.234567890';
function rigaRunner(updatedMs: number, bestBack: number): Omit<LiveLadderRow, 'updated_at'> {
    return {
        event_id: '34567890',
        market_id: MID,
        market_type: 'MATCH_ODDS',
        market_name: 'Match Odds',
        status: 'OPEN',
        ladder: {
            updated_ms: updatedMs,
            selections: [
                {
                    selection_id: 47972, name: 'Casa', ltp: 2.9, tv: 1234.5,
                    back: [[bestBack, 10.5], [2.86, 5.0]], lay: [[2.9, 20.0], [2.92, 8.0]],
                    trd: [[2.9, 100.0], [2.88, 40.0]], wom: { back_pct: 40.0, lay_pct: 60.0 },
                },
                {
                    selection_id: 58805, name: 'Ospite', ltp: 2.6, tv: 800.0,
                    back: [[2.56, 12.0]], lay: [[2.6, 15.0]], trd: [], wom: { back_pct: 44.4, lay_pct: 55.6 },
                },
            ],
        },
    };
}
// riga DB: stessa dict + id (bigserial) + updated_at (_now_iso() di Python)
function rigaDb(updatedMs: number, bestBack: number): LiveLadderRow & { id: number } {
    return { id: 17, ...rigaRunner(updatedMs, bestBack), updated_at: '2026-09-23T10:00:00.123456+00:00' };
}
const pushLadder = (ws: MockWebSocket, d: unknown) => ws.serverMessage({ t: 'ladder', d });
const bestBack = (r: LiveLadderRow | null | undefined) => r?.ladder?.selections[0]?.back[0]?.[0];
const ultimaRiga = (cb: ReturnType<typeof vi.fn>): LiveLadderRow | null | undefined => {
    const c = cb.mock.calls;
    return c.length ? (c[c.length - 1][0] as LiveLadderRow | null) : undefined;
};

function dbFinto(iniziale: LiveLadderRow | null = null) {
    const cbs: Array<(r: LiveLadderRow | null) => void> = [];
    const unsub = vi.fn();
    const db: LadderSource = {
        fetch: vi.fn(async () => iniziale),
        subscribe: vi.fn((_mid: string, cb: (r: LiveLadderRow | null) => void) => { cbs.push(cb); return unsub; }),
    };
    return { db, cbs, unsub, emetti: (r: LiveLadderRow | null) => cbs[cbs.length - 1]?.(r) };
}

let ora = 1_000_000;
const adesso = () => ora;

beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout'] });
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    ora = 1_000_000;
});
afterEach(() => {
    __resetLocalTransport();
    __resetLocalChannels();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

// ================================================================ parita'
describe('ladderDaCanale - parita\' con la riga live_ladder', () => {
    it('dallo stesso book: riga dal canale == riga DB campo per campo (updated_at = ora del produttore)', () => {
        const ms = 1_758_621_600_123;
        const dalCanale = ladderDaCanale(rigaRunner(ms, 2.88));
        const dalDb = rigaDb(ms, 2.88);
        expect(dalCanale).not.toBeNull();
        // stesse chiavi della riga DB (tolta `id`, che il tipo LiveLadderRow non porta)
        const chiaviDb = Object.keys(dalDb).filter((k) => k !== 'id').sort();
        expect(Object.keys(dalCanale!).sort()).toEqual(chiaviDb);
        for (const k of chiaviDb) {
            if (k === 'updated_at') continue; // DB = ora della scrittura, canale = ora del produttore
            expect((dalCanale as unknown as Record<string, unknown>)[k]).toEqual((dalDb as unknown as Record<string, unknown>)[k]);
        }
        expect(dalCanale!.updated_at).toBe(new Date(ms).toISOString());
    });

    it('messaggi non validi -> null (mai una riga inventata)', () => {
        expect(ladderDaCanale(null)).toBeNull();
        expect(ladderDaCanale({ ...rigaRunner(1, 2), market_id: '' })).toBeNull();
        expect(ladderDaCanale({ ...rigaRunner(1, 2), ladder: { selections: [] } })).toBeNull();
        expect(ladderDaCanale({ ...rigaRunner(1, 2), ladder: { updated_ms: 5 } })).toBeNull();
    });

    it('piuFresca: strettamente piu\' recente sul timestamp del produttore', () => {
        expect(piuFresca(rigaDb(2, 1), rigaDb(1, 1))).toBe(true);
        expect(piuFresca(rigaDb(1, 1), rigaDb(1, 1))).toBe(false);
        expect(piuFresca(rigaDb(1, 1), rigaDb(2, 1))).toBe(false);
        expect(piuFresca(rigaDb(1, 1), null)).toBe(true);
    });
});

// ================================================================ sorgente
describe('sorgenteLadderAlMs - canale principale, DB solo a canale assente/muto', () => {
    it('default N = 2 x LADDER_PUBLISH_SEC (<= 5 s)', () => {
        expect(LADDER_MUTO_MS_DEFAULT).toBe(4_000);
    });

    it('canale che pubblica: la riga arriva dal canale, il realtime DB non viene mai aperto', () => {
        const { db } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        const cb = vi.fn();
        src.subscribe(MID, cb);
        expect(db.subscribe).not.toHaveBeenCalled();
        pushLadder(ws, rigaRunner(11, 3.1));
        expect(bestBack(ultimaRiga(cb))).toBe(3.1);
        expect(src.fonte(MID)).toBe('canale');
    });

    it('canale muto > N: si apre il realtime DB e le sue righe arrivano; il canale riprende: si torna al canale', () => {
        const { db, unsub, emetti } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso, mutoMs: 4_000 });
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        const cb = vi.fn();
        src.subscribe(MID, cb);
        expect(db.subscribe).not.toHaveBeenCalled();

        ora += 3_999; vi.advanceTimersByTime(1_000);
        expect(db.subscribe).not.toHaveBeenCalled();      // entro N: ancora canale
        ora += 2; vi.advanceTimersByTime(1_000);
        expect(db.subscribe).toHaveBeenCalledTimes(1);    // oltre N: DB

        emetti(rigaDb(20, 3.3));
        expect(bestBack(ultimaRiga(cb))).toBe(3.3);
        expect(src.fonte(MID)).toBe('db');

        pushLadder(ws, rigaRunner(30, 3.5));              // il canale riprende
        expect(unsub).toHaveBeenCalledTimes(1);
        expect(bestBack(ultimaRiga(cb))).toBe(3.5);
        expect(src.fonte(MID)).toBe('canale');
        const n = cb.mock.calls.length;
        emetti(rigaDb(40, 9.9));                          // notifica tardiva del DB chiuso
        expect(cb.mock.calls.length).toBe(n);
    });

    it('canale assente (off): DB subito; a connessione avvenuta e primo push si torna al canale', () => {
        const { db, unsub } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const cb = vi.fn();
        src.subscribe(MID, cb);
        expect(db.subscribe).toHaveBeenCalledTimes(1);
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        expect(unsub).toHaveBeenCalledTimes(1);
        expect(bestBack(ultimaRiga(cb))).toBe(2.88);
    });

    it('messaggio vecchio ignorato (canale e DB)', () => {
        const { db, emetti } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        const cb = vi.fn();
        src.subscribe(MID, cb);
        pushLadder(ws, rigaRunner(100, 2.88));
        pushLadder(ws, rigaRunner(99, 7.7));              // piu' vecchio: scartato
        pushLadder(ws, rigaRunner(100, 7.7));             // stesso istante: scartato
        expect(cb).toHaveBeenCalledTimes(1);
        expect(bestBack(cb.mock.calls[0][0])).toBe(2.88);
        ws.serverClose();                                  // canale giu' -> DB
        emetti(rigaDb(100, 7.7));                          // DB con lo stesso book: scartato
        expect(cb).toHaveBeenCalledTimes(1);
        emetti(rigaDb(101, 3.0));
        expect(bestBack(ultimaRiga(cb))).toBe(3.0);
    });

    it('fetch: una sola lettura DB; con il canale vivo e il mercato gia\' noto nessuna lettura', async () => {
        const { db } = dbFinto(rigaDb(5, 2.5));
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        await expect(src.fetch(MID)).resolves.toMatchObject({ market_id: MID });
        expect(db.fetch).toHaveBeenCalledTimes(1);
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        const r = await src.fetch(MID);
        expect(bestBack(r)).toBe(2.88);
        expect(db.fetch).toHaveBeenCalledTimes(1);
    });

    it('fetch: se il canale ha portato una riga piu\' fresca durante la lettura, vince quella', async () => {
        let rilascia: (r: LiveLadderRow | null) => void = () => {};
        const db: LadderSource = {
            fetch: vi.fn(() => new Promise<LiveLadderRow | null>((res) => { rilascia = res; })),
            subscribe: vi.fn(() => () => {}),
        };
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const p = src.fetch(MID);
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(50, 3.2));
        rilascia(rigaDb(40, 2.5));
        expect(bestBack(await p)).toBe(3.2);
    });

    it('tennis usa il canale 47332', () => {
        const { db } = dbFinto();
        const src = sorgenteLadderAlMs('tennis', { db, adesso });
        const cb = vi.fn();
        src.subscribe(MID, cb);
        const ws = wsDi(47332);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 1.5));
        expect(bestBack(ultimaRiga(cb))).toBe(1.5);
        expect(getLocalChannel('tennis').getStatus()).toBe('connected');
    });
});

// ================================================================ memoria (F3)
// F3 revisore A (23/09): le mappe interne tenevano l'ultimo ladder di OGNI
// mercato passato sul canale e non si svuotavano mai (solo a canale caduto).
// Ora una voce senza sottoscrittori attivi e senza aggiornamenti da piu' di
// LADDER_POTATURA_MS_DEFAULT si scarta; osservabile da fuori: fonte() -> null
// e fetch() torna a leggere il DB.
describe('sorgenteLadderAlMs - potatura dei mercati abbandonati (F3)', () => {
    const MID2 = '1.999999999';
    const rigaAltro = (ms: number) => ({ ...rigaRunner(ms, 4.4), market_id: MID2 });

    it('default: 10 minuti', () => {
        expect(LADDER_POTATURA_MS_DEFAULT).toBe(10 * 60_000);
    });

    it('mercato visto sul canale, mai sottoscritto, fermo da piu\' di N: la voce si scarta', async () => {
        const { db } = dbFinto(rigaDb(5, 2.5));
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        expect(src.fonte(MID)).toBe('canale');
        ora += LADDER_POTATURA_MS_DEFAULT + 1;
        pushLadder(ws, rigaAltro(20));                     // il canale continua con altri mercati
        expect(src.fonte(MID)).toBeNull();
        expect(src.fonte(MID2)).toBe('canale');
        await src.fetch(MID);                              // voce scartata: si rilegge il DB
        expect(db.fetch).toHaveBeenCalledTimes(1);
    });

    it('entro N la voce resta (fetch dal canale, nessuna lettura DB)', async () => {
        const { db } = dbFinto(rigaDb(5, 2.5));
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        ora += LADDER_POTATURA_MS_DEFAULT - 1;
        pushLadder(ws, rigaAltro(20));
        expect(src.fonte(MID)).toBe('canale');
        expect(bestBack(await src.fetch(MID))).toBe(2.88);
        expect(db.fetch).not.toHaveBeenCalled();
    });

    it('mercato con un sottoscrittore attivo non si scarta mai, anche fermo da ore', () => {
        const { db } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        const off = src.subscribe(MID, vi.fn());
        for (let i = 1; i <= 30; i += 1) {                 // 30 x 5 minuti = 2 ore e mezza
            ora += 5 * 60_000;
            pushLadder(ws, rigaAltro(20 + i));
        }
        expect(src.fonte(MID)).toBe('canale');
        off();
    });

    it('dopo l\'unsubscribe dell\'ULTIMO consumatore, passati N, la voce si scarta', () => {
        const { db } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        pushLadder(ws, rigaRunner(10, 2.88));
        const off1 = src.subscribe(MID, vi.fn());
        const off2 = src.subscribe(MID, vi.fn());
        ora += LADDER_POTATURA_MS_DEFAULT + 1;
        off1();                                            // ne resta uno
        pushLadder(ws, rigaAltro(20));
        expect(src.fonte(MID)).toBe('canale');
        off2();                                            // l'ultimo se ne va: da qui si contano N
        ora += LADDER_POTATURA_MS_DEFAULT - 1;
        pushLadder(ws, rigaAltro(21));
        expect(src.fonte(MID)).toBe('canale');
        ora += 60_000;                                     // oltre N (il controllo gira al piu' ogni minuto)
        pushLadder(ws, rigaAltro(22));
        expect(src.fonte(MID)).toBeNull();
    });

    it('un mercato che continua a ricevere push resta, anche senza sottoscrittori', () => {
        const { db } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        for (let i = 0; i < 20; i += 1) {                  // un push al minuto per 20 minuti
            pushLadder(ws, rigaRunner(10 + i, 2.88));
            ora += 60_000;
        }
        pushLadder(ws, rigaAltro(99));
        expect(src.fonte(MID)).toBe('canale');
    });

    it('una giornata di mercati chiusi non resta in memoria', () => {
        const { db } = dbFinto();
        const src = sorgenteLadderAlMs('calcio', { db, adesso });
        const ws = wsDi(47331);
        ws.serverOpen();
        const mids = Array.from({ length: 300 }, (_, i) => `1.${100000000 + i}`);
        mids.forEach((m, i) => pushLadder(ws, { ...rigaRunner(10 + i, 2.0), market_id: m }));
        expect(mids.every((m) => src.fonte(m) === 'canale')).toBe(true);
        ora += LADDER_POTATURA_MS_DEFAULT + 1;
        pushLadder(ws, rigaAltro(1_000));
        expect(mids.filter((m) => src.fonte(m) !== null)).toEqual([]);
    });
});
