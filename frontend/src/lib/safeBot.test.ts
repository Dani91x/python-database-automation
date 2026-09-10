// Test del data-layer del BOT Safe Strategy. Il client Supabase e' mockato
// (nessuna rete): si verificano forma delle chiamate RPC e matematica pura.
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: {
        rpc: vi.fn(),
        from: vi.fn(),
        channel: vi.fn(),
        removeChannel: vi.fn(),
    },
}));

import { supabase } from '@/integrations/supabase/client';
import {
    activateSafe, stopSafe, updateSafeParams, fetchSafeState, fetchSafeTrades,
    requestSafe, fetchSafeRequests, fetchOpportunities, subscribeSafeBot,
    subscribeOpportunities, buildEquitySeries, detectSettlements, tradeExposure,
    mergeBotParams, oppScore, SAFE_BOT_DEFAULTS, safeTradeBook, resolveSignalPlacement, cappedFrom,
    cashoutInFlight, feedFreshness, staleReason, sameStrategyParams, strategyParamsOf,
    oppKind, oppKindCounts, comboLegStakes, comboLock, anomalyRefLabel, comboIdempotencyPrefix,
    tradeHold, holdReasonLabel, pLoseEntry, tradeOppKind, SAFE_RISK_DEFAULTS,
    groupClosingLegs, fmtEurIt, fmtOddsIt, hedgeTooltip,
    type SafeTrade,
} from './safeBot';
import { DEFAULT_PARAMS } from './safeStrategy';

const rpc = supabase.rpc as unknown as ReturnType<typeof vi.fn>;
const from = supabase.from as unknown as ReturnType<typeof vi.fn>;
const channel = supabase.channel as unknown as ReturnType<typeof vi.fn>;
const removeChannel = supabase.removeChannel as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
    rpc.mockReset();
    from.mockReset();
    channel.mockReset();
    removeChannel.mockReset();
    rpc.mockResolvedValue({ data: null, error: null });
});

function trade(over: Partial<SafeTrade> = {}): SafeTrade {
    return {
        id: 1, event_id: 'e1', event_name: 'A vs B', sport: 'calcio', strategy: 'base',
        market_id: '1.1', market_type: 'MATCH_ODDS', selection_id: 10, selection_name: 'A',
        side: 'lay', mode: 'paper', price: 3, size: 5, liability: 10, commission: 0.05,
        minute_at_entry: 55, score_at_entry: '1-0', status: 'open', pnl: 0, bet_id: null,
        placed_at: '2026-09-10T10:00:00Z', settled_at: null, origin: 'auto',
        closes_trade_id: null, signal_key: 'e1:base:1-0', meta: null,
        ...over,
    };
}

// --------------------------------------------------------------------- RPC
describe('safeBot RPC', () => {
    it('activateSafe chiama safe_activate con modalita e parametri', async () => {
        rpc.mockResolvedValue({ data: { id: 1, status: 'running' }, error: null });
        await activateSafe('live', { opps_stake: 7 });
        expect(rpc).toHaveBeenCalledWith('safe_activate', { p_mode: 'live', p_params: { opps_stake: 7 } });
    });

    it('activateSafe senza parametri passa null', async () => {
        await activateSafe('paper');
        expect(rpc).toHaveBeenCalledWith('safe_activate', { p_mode: 'paper', p_params: null });
    });

    it('stopSafe chiama safe_stop', async () => {
        await stopSafe();
        expect(rpc).toHaveBeenCalledWith('safe_stop', {});
    });

    it('updateSafeParams chiama safe_update_params', async () => {
        await updateSafeParams({ max_open_trades: 3 });
        expect(rpc).toHaveBeenCalledWith('safe_update_params', { p_params: { max_open_trades: 3 } });
    });

    it('fetchSafeState normalizza una risposta vuota', async () => {
        rpc.mockResolvedValue({ data: null, error: null });
        const st = await fetchSafeState();
        expect(st).toEqual({ control: null, trades: [], aggregates: null });
    });

    it('fetchSafeTrades passa il limite', async () => {
        rpc.mockResolvedValue({ data: [], error: null });
        await fetchSafeTrades(42);
        expect(rpc).toHaveBeenCalledWith('get_safe_trades', { p_limit: 42 });
    });

    it('requestSafe accoda kind + payload e ritorna l id', async () => {
        rpc.mockResolvedValue({ data: 77, error: null });
        const id = await requestSafe('place', { event_id: 'e1', size: 5 });
        expect(rpc).toHaveBeenCalledWith('safe_request', {
            p_kind: 'place', p_payload: { event_id: 'e1', size: 5 },
        });
        expect(id).toBe(77);
    });

    it('propaga l errore RPC come eccezione', async () => {
        rpc.mockResolvedValue({ data: null, error: { message: 'permesso negato' } });
        await expect(stopSafe()).rejects.toThrow('permesso negato');
    });
});

describe('safeBot letture su tabella', () => {
    it('fetchSafeRequests legge safe_strategy_requests ordinata', async () => {
        const limit = vi.fn().mockResolvedValue({ data: [{ id: 1 }], error: null });
        const order = vi.fn(() => ({ limit }));
        const select = vi.fn(() => ({ order }));
        from.mockReturnValue({ select });
        const rows = await fetchSafeRequests(5);
        expect(from).toHaveBeenCalledWith('safe_strategy_requests');
        expect(order).toHaveBeenCalledWith('id', { ascending: false });
        expect(limit).toHaveBeenCalledWith(5);
        expect(rows).toHaveLength(1);
    });

    it('fetchOpportunities legge safe_strategy_opportunities', async () => {
        const select = vi.fn().mockResolvedValue({ data: [], error: null });
        from.mockReturnValue({ select });
        await fetchOpportunities();
        expect(from).toHaveBeenCalledWith('safe_strategy_opportunities');
    });
});

describe('safeBot realtime', () => {
    it('subscribeSafeBot usa UN canale su control+trades+requests', () => {
        const tables: string[] = [];
        const ch: Record<string, unknown> = {};
        ch.on = vi.fn((_ev: string, cfg: { table: string }) => { tables.push(cfg.table); return ch; });
        ch.subscribe = vi.fn(() => ch);
        channel.mockReturnValue(ch);
        const off = subscribeSafeBot(() => {});
        expect(channel).toHaveBeenCalledWith('safe-bot');
        expect(tables).toEqual([
            'safe_strategy_control', 'safe_strategy_trades', 'safe_strategy_requests',
        ]);
        off();
        expect(removeChannel).toHaveBeenCalledWith(ch);
    });

    it('subscribeOpportunities emette upsert e delete', () => {
        let handler: ((p: Record<string, unknown>) => void) | null = null;
        const ch: Record<string, unknown> = {};
        ch.on = vi.fn((_ev: string, _cfg: unknown, cb: (p: Record<string, unknown>) => void) => {
            handler = cb; return ch;
        });
        ch.subscribe = vi.fn(() => ch);
        channel.mockReturnValue(ch);
        const seen: unknown[] = [];
        subscribeOpportunities((ev) => seen.push(ev));
        handler!({ eventType: 'INSERT', new: { event_id: 'e1', sport: 'calcio', payload: { opps: [] } } });
        handler!({ eventType: 'DELETE', old: { event_id: 'e1' } });
        expect(seen).toEqual([
            { type: 'upsert', row: { event_id: 'e1', sport: 'calcio', payload: { opps: [] } } },
            { type: 'delete', eventId: 'e1' },
        ]);
    });
});

// ------------------------------------------------------------- matematica
describe('tradeExposure', () => {
    it('LAY 5 @ 3.0 -> vince -10, perde +5', () => {
        expect(tradeExposure({ side: 'lay', price: 3, size: 5 })).toEqual({ win: -10, lose: 5 });
    });

    it('BACK 10 @ 2.5 -> vince +15, perde -10', () => {
        expect(tradeExposure({ side: 'back', price: 2.5, size: 10 })).toEqual({ win: 15, lose: -10 });
    });

    it('LAY grosso (Correct Score) arrotonda ai centesimi', () => {
        expect(tradeExposure({ side: 'lay', price: 110, size: 5.26 })).toEqual({ win: -573.34, lose: 5.26 });
    });

    it('prezzo o size non validi -> nessuna esposizione', () => {
        expect(tradeExposure({ side: 'lay', price: null, size: 5 })).toEqual({ win: 0, lose: 0 });
        expect(tradeExposure({ side: 'back', price: 1, size: 5 })).toEqual({ win: 0, lose: 0 });
        expect(tradeExposure({ side: 'back', price: 2, size: 0 })).toEqual({ win: 0, lose: 0 });
    });
});

describe('buildEquitySeries', () => {
    it('cumula solo i regolati in ordine di settlement', () => {
        const s = buildEquitySeries([
            { settled_at: '2026-09-10T12:00:00Z', status: 'won', pnl: 5 },
            { settled_at: null, status: 'open', pnl: 0 },
            { settled_at: '2026-09-10T11:00:00Z', status: 'lost', pnl: -2 },
            { settled_at: '2026-09-10T13:00:00Z', status: 'hedged', pnl: 1.5 },
        ]);
        expect(s.map((p) => p.v)).toEqual([-2, 3, 4.5]);
    });

    it('nessun regolato -> serie vuota', () => {
        expect(buildEquitySeries([{ settled_at: null, status: 'open', pnl: 0 }])).toEqual([]);
    });
});

describe('detectSettlements', () => {
    it('al primo caricamento memorizza lo storico senza notificare', () => {
        const seen = new Set<number>();
        const fresh = detectSettlements(
            [trade({ id: 1, status: 'won', settled_at: '2026-09-10T10:00:00Z', pnl: 3 })], seen, true,
        );
        expect(fresh).toEqual([]);
        expect(seen.has(1)).toBe(true);
    });

    it('ritorna solo i regolati mai visti prima', () => {
        const seen = new Set<number>([1]);
        const rows = [
            trade({ id: 1, status: 'won', settled_at: '2026-09-10T10:00:00Z' }),
            trade({ id: 2, status: 'lost', settled_at: '2026-09-10T11:00:00Z' }),
            trade({ id: 3, status: 'open' }),
        ];
        expect(detectSettlements(rows, seen, false).map((t) => t.id)).toEqual([2]);
        expect(detectSettlements(rows, seen, false)).toEqual([]);
    });
});

describe('parametri bot', () => {
    it('mergeBotParams su null ritorna i default', () => {
        expect(mergeBotParams(null)).toEqual(SAFE_BOT_DEFAULTS);
    });

    it('mergeBotParams tiene i valori validi e scarta i malformati', () => {
        const p = mergeBotParams({
            max_open_trades: 9, opps_stake: 'x', variants: ['base', 'boh'], base: { minuteMin: 70 },
        });
        expect(p.max_open_trades).toBe(9);
        expect(p.opps_stake).toBe(SAFE_BOT_DEFAULTS.opps_stake);
        expect(p.variants).toEqual(['base']);
        expect(p.base.minuteMin).toBe(70);
        expect(p.base.scoreConfirmSec).toBe(SAFE_BOT_DEFAULTS.base.scoreConfirmSec);
    });

    it('variants vuoto ricade sui default (mai bot cieco per errore)', () => {
        expect(mergeBotParams({ variants: [] }).variants).toEqual(SAFE_BOT_DEFAULTS.variants);
    });

    it('lo stake di default e annidato in `stake` (contratto motore)', () => {
        expect(SAFE_BOT_DEFAULTS.stake).toEqual({ laySize: 2, backSize: 2 });
        expect(mergeBotParams({ stake: { laySize: 8 } }).stake).toEqual({ laySize: 8, backSize: 2 });
        expect(mergeBotParams({ stake: 'boom' }).stake).toEqual(SAFE_BOT_DEFAULTS.stake);
    });
});

describe('cappedFrom', () => {
    it('legge meta.size_capped_from della gamba di chiusura', () => {
        expect(cappedFrom({ meta: { size_capped_from: 5.13 } })).toBe(5.13);
    });
    it('assente o non valido -> null', () => {
        expect(cappedFrom({ meta: null })).toBeNull();
        expect(cappedFrom({ meta: { size_capped_from: 0 } })).toBeNull();
    });
});

describe('oppScore', () => {
    it('ordina per EV pesato dalla confidenza', () => {
        const a = { ev: 0.5, confidence: 0.4 } as never;
        const b = { ev: 0.3, confidence: 0.9 } as never;
        expect(oppScore(b)).toBeGreaterThan(oppScore(a));
    });
    it('valori non numerici -> 0', () => {
        expect(oppScore({ ev: NaN, confidence: 1 } as never)).toBe(0);
    });
});

// -------------------------------------------------------- book e placement
const PAYLOAD = {
    media: null, event_name: 'Roma vs Lazio', home: 'Roma', away: 'Lazio',
    competition: 'Serie A', open_date: null, inplay: true,
    mo_market_id: '1.1', mo_status: 'OPEN',
    // il feed odierno porta gli id DENTRO odds.<lato> (niente mo_selections)
    odds: {
        home: { selection_id: 11, ltp: 1.31, back: 1.3, lay: 1.32, back_size: 250, lay_size: 180 },
        draw: { selection_id: 13, back: 5, lay: 5.2 },
        away: { selection_id: 12, back: 9, lay: 9.4 },
    },
    minute: 60, score_home: 1, score_away: 0, red_home: 0, red_away: 0, pre_ko: null,
    cs: {
        market_id: '1.5', status: 'OPEN',
        selections: [
            { selection_id: 77, name: 'Any Other Home Win', back: 38, lay: 42, lay_size: 60 },
            { selection_id: 78, name: 'Any Other Away Win', back: 60, lay: 70 },
        ],
        any_other_home: null, any_other_away: null,
    },
    ht: {
        market_id: '1.7', status: 'OPEN',
        selections: [{ selection_id: 55, name: '1 - 0', back: 3, lay: 3.1 }],
    },
} as never;

const TENNIS = {
    media: null, event_name: 'Sinner vs Alcaraz', p1: 'Sinner', p2: 'Alcaraz',
    competition: 'ATP', open_date: null, inplay: true,
    mo_market_id: '1.9', mo_status: 'OPEN',
    odds: {
        p1: { selection_id: 21, back: 1.05, lay: 1.06, back_size: 400, lay_size: 300 },
        p2: { selection_id: 22, back: 18, lay: 20 },
    },
    sets: { p1: 1, p2: 0 }, games: { p1: 4, p2: 2 },
} as never;

describe('safeTradeBook', () => {
    it('Correct Score: prende la selezione per id', () => {
        expect(safeTradeBook(
            { market_type: 'CORRECT_SCORE', selection_id: 77, selection_name: null }, PAYLOAD,
        )).toEqual({ back: 38, lay: 42 });
    });

    it('Half Time Score: legge il ramo ht del feed', () => {
        expect(safeTradeBook(
            { market_type: 'HALF_TIME_SCORE', selection_id: 55, selection_name: null }, PAYLOAD,
        )).toEqual({ back: 3, lay: 3.1 });
    });

    it('Match Odds calcio: per nome o per selection_id del lato', () => {
        expect(safeTradeBook(
            { market_type: 'MATCH_ODDS', selection_id: 11, selection_name: 'Roma' }, PAYLOAD,
        )).toEqual({ back: 1.3, lay: 1.32 });
        expect(safeTradeBook(
            { market_type: 'MATCH_ODDS', selection_id: 13, selection_name: null }, PAYLOAD,
        )).toEqual({ back: 5, lay: 5.2 });
    });

    it('Match Odds tennis: legge odds.p1/p2', () => {
        expect(safeTradeBook(
            { market_type: 'MATCH_ODDS', selection_id: 22, selection_name: 'Alcaraz' }, TENNIS,
        )).toEqual({ back: 18, lay: 20 });
    });

    it('mercato sconosciuto o feed assente -> null', () => {
        expect(safeTradeBook({ market_type: 'OVER_UNDER_25', selection_id: 1, selection_name: 'x' }, PAYLOAD)).toBeNull();
        expect(safeTradeBook({ market_type: 'MATCH_ODDS', selection_id: 11, selection_name: 'Roma' }, null)).toBeNull();
    });
});

describe('resolveSignalPlacement', () => {
    it('segnale Match Odds: risolve id, prezzo e size del lato operato', () => {
        expect(resolveSignalPlacement(
            { variant: 'base', side: 'BACK', selection: 'Roma' }, PAYLOAD,
        )).toEqual({
            market_id: '1.1', market_type: 'MATCH_ODDS', selection_id: 11,
            selection_name: 'Roma', price: 1.3, size_available: 250,
        });
    });

    it('segnale LAY prende il prezzo lay e la size lay', () => {
        const out = resolveSignalPlacement({ variant: 'punta', side: 'LAY', selection: 'Roma' }, PAYLOAD);
        expect(out).toMatchObject({ price: 1.32, size_available: 180 });
    });

    it('risultato esatto: Correct Score "Any Other Home/Away Win"', () => {
        expect(resolveSignalPlacement(
            { variant: 'esatto', subId: 'home', side: 'LAY', selection: null }, PAYLOAD,
        )).toMatchObject({ market_id: '1.5', selection_id: 77, price: 42, size_available: 60 });
        expect(resolveSignalPlacement(
            { variant: 'esatto', subId: 'away', side: 'LAY', selection: null }, PAYLOAD,
        )).toMatchObject({ selection_id: 78 });
    });

    it('tennis: id dal lato p1/p2 del Match Odds', () => {
        expect(resolveSignalPlacement({ variant: 'tennis', side: 'BACK', selection: 'Sinner' }, TENNIS))
            .toEqual({
                market_id: '1.9', market_type: 'MATCH_ODDS', selection_id: 21,
                selection_name: 'Sinner', price: 1.05, size_available: 400,
            });
    });

    it('mo_selections, se presente, ha la precedenza come override', () => {
        const p = {
            ...(PAYLOAD as object),
            mo_selections: [{ selection_id: 99, name: 'Roma', back: 1.4, lay: 1.45, back_size: 10 }],
        } as never;
        expect(resolveSignalPlacement({ variant: 'base', side: 'BACK', selection: 'Roma' }, p))
            .toMatchObject({ selection_id: 99, price: 1.4, size_available: 10 });
    });

    it('senza selection_id nel feed non indovina nulla', () => {
        const p = {
            ...(PAYLOAD as object),
            odds: { home: { back: 1.3, lay: 1.32 }, draw: null, away: null },
        } as never;
        expect(resolveSignalPlacement({ variant: 'base', side: 'BACK', selection: 'Roma' }, p)).toBeNull();
    });

    it('nome selezione sconosciuto -> null', () => {
        expect(resolveSignalPlacement({ variant: 'base', side: 'BACK', selection: 'Napoli' }, PAYLOAD)).toBeNull();
    });

    it('feed assente -> null', () => {
        expect(resolveSignalPlacement({ variant: 'base', side: 'BACK', selection: 'Roma' }, null)).toBeNull();
    });
});

// ---------------------------------------------------- cash out in corso (HIGH-1)
describe('cashoutInFlight', () => {
    const req = (over: Record<string, unknown>) => ({
        kind: 'cashout' as const, payload: { trade_id: 9 }, status: 'pending' as const, ...over,
    });

    it('richiesta cashout pending/processing per quel trade_id -> in volo', () => {
        expect(cashoutInFlight(9, [req({})], [])).toBe(true);
        expect(cashoutInFlight(9, [req({ status: 'processing' })], [])).toBe(true);
    });

    it('richiesta done/error, di altro tipo o di altro trade -> libero', () => {
        expect(cashoutInFlight(9, [req({ status: 'done' })], [])).toBe(false);
        expect(cashoutInFlight(9, [req({ status: 'error' })], [])).toBe(false);
        expect(cashoutInFlight(9, [req({ kind: 'place' })], [])).toBe(false);
        expect(cashoutInFlight(9, [req({ payload: { trade_id: 10 } })], [])).toBe(false);
    });

    it('gamba di chiusura gia scritta (non in errore) -> in volo; in errore -> libero', () => {
        expect(cashoutInFlight(9, [], [trade({ id: 10, closes_trade_id: 9, status: 'pending' })])).toBe(true);
        expect(cashoutInFlight(9, [], [trade({ id: 10, closes_trade_id: 9, status: 'open' })])).toBe(true);
        expect(cashoutInFlight(9, [], [trade({ id: 10, closes_trade_id: 9, status: 'error' })])).toBe(false);
    });

    it('meta.hedging sul trade stesso -> in volo', () => {
        expect(cashoutInFlight(9, [], [trade({ id: 9, meta: { hedging: true } })])).toBe(true);
        expect(cashoutInFlight(9, [], [trade({ id: 9, meta: { hedging: false } })])).toBe(false);
        expect(cashoutInFlight(9, [], [trade({ id: 9 })])).toBe(false);
    });
});

// ----------------------------------------------------- freschezza feed (HIGH-2)
describe('feedFreshness', () => {
    const now = Date.parse('2026-09-10T12:00:00Z');
    const ago = (s: number) => new Date(now - s * 1000).toISOString();

    it('riga fresca e scanner vivo -> non stantio', () => {
        const f = feedFreshness(ago(5), ago(3), now);
        expect(f).toEqual({ ageSec: 5, scannerAlive: true, stale: false });
        expect(staleReason(f)).toBeUndefined();
    });

    it('riga vecchia (>20s) ma scanner vivo -> write-on-change: NON stantio, solo eta', () => {
        const f = feedFreshness(ago(90), ago(10), now);
        expect(f.ageSec).toBe(90);
        expect(f.stale).toBe(false);
    });

    it('riga vecchia (>20s) E scanner morto (>45s) -> stantio, bottoni spenti', () => {
        const f = feedFreshness(ago(31), ago(60), now);
        expect(f).toEqual({ ageSec: 31, scannerAlive: false, stale: true });
        expect(staleReason(f)).toBe('quote non aggiornate (31s)');
    });

    it('riga fresca con scanner morto -> non stantio (la riga e appena stata scritta)', () => {
        expect(feedFreshness(ago(10), ago(60), now).stale).toBe(false);
    });

    it('senza timestamp di riga: stantio solo se lo scanner e morto', () => {
        expect(feedFreshness(null, ago(3), now)).toEqual({ ageSec: null, scannerAlive: true, stale: false });
        expect(feedFreshness(null, null, now)).toEqual({ ageSec: null, scannerAlive: false, stale: true });
        expect(staleReason(feedFreshness(null, null, now))).toBe('quote non aggiornate (n/d)');
    });
});

// ------------------------------------------ sincronizzazione parametri (HIGH-4)
describe('strategyParamsOf / sameStrategyParams', () => {
    it('un payload server con chiavi ignote/null coincide col locale normalizzato', () => {
        const server = mergeBotParams({
            base: { ...DEFAULT_PARAMS.base, unknown_key: 1, minuteMin: 70 },
            esatto: { ...DEFAULT_PARAMS.esatto, legacy: null },
        });
        const local = { ...DEFAULT_PARAMS, base: { ...DEFAULT_PARAMS.base, minuteMin: 70 } };
        expect(sameStrategyParams(server, local)).toBe(true);
        expect(strategyParamsOf(server)).toEqual(local);
    });

    it('una condizione davvero diversa NON coincide', () => {
        const server = mergeBotParams({ base: { ...DEFAULT_PARAMS.base, minuteMin: 75 } });
        expect(sameStrategyParams(server, DEFAULT_PARAMS)).toBe(false);
    });

    it('le chiavi del bot non di strategia (stake, variants…) sono ignorate', () => {
        expect(strategyParamsOf(SAFE_BOT_DEFAULTS)).toEqual(DEFAULT_PARAMS);
        expect(sameStrategyParams(SAFE_BOT_DEFAULTS, DEFAULT_PARAMS)).toBe(true);
    });
});

describe('opportunita per tipo (kind) e combinazioni', () => {
    const combo = {
        kind: 'combo', combo: 'dutch', market_type: 'MATCH_ODDS', market_name: null, line: null, market_id: '1.1',
        selection_id: 1, selection_name: 'x', side: 'back', price: 2, size_available: 10, p_model: 0.5, p_implied: 0.5,
        edge: 0, ev: 0.05, confidence: 0.8, rationale: null, total_stake: 10,
        locked_profit_per_eur: 0.04, best_case_per_eur: 0.2,
        legs: [
            { market_type: 'MATCH_ODDS', market_id: '1.1', selection_id: 1, selection_name: 'Roma', side: 'back', price: 3, size_available: 50, stake_ratio: null, stake: 4 },
            { market_type: 'MATCH_ODDS', market_id: '1.1', selection_id: 2, selection_name: 'Draw', side: 'back', price: 2, size_available: 50, stake_ratio: null, stake: 6 },
        ],
    } as const;

    it('oppKind: assente o ignoto = model', () => {
        expect(oppKind({})).toBe('model');
        expect(oppKind({ kind: 'boh' })).toBe('model');
        expect(oppKind({ kind: 'tennis' })).toBe('tennis');
    });

    it('oppKindCounts somma i tipi su tutte le righe', () => {
        const rows = [
            { payload: { opps: [{ kind: 'anomaly' }, {}, { kind: 'combo' }] } },
            { payload: { opps: [{ kind: 'tennis' }] } },
            { payload: null },
        ] as never;
        expect(oppKindCounts(rows)).toEqual({ model: 1, anomaly: 1, combo: 1, tennis: 1 });
    });

    it('comboLegStakes: ratio dallo stake/total del servizio, scalato allo stake scelto', () => {
        const legs = comboLegStakes(combo as never, 20);
        expect(legs.map((l) => l.stake)).toEqual([8, 12]);
        expect(comboLegStakes({ ...combo, legs: [] } as never, 20)).toEqual([]);
        // senza ratio ne' stake: parti uguali
        const eq = comboLegStakes({ ...combo, total_stake: null, legs: combo.legs.map((l) => ({ ...l, stake: null })) } as never, 9);
        expect(eq.map((l) => l.stake)).toEqual([4.5, 4.5]);
    });

    it('comboLock: per € e in € sullo stake totale', () => {
        expect(comboLock(combo as never, 25)).toEqual({ worstPerEur: 0.04, bestPerEur: 0.2, worstEur: 1, bestEur: 5 });
        expect(comboLock({ ...combo, locked_profit_per_eur: null } as never, 25).worstEur).toBeNull();
    });

    it('anomalyRefLabel: "sorella @q → anomala @q" da oggetto o stringa', () => {
        const a = { selection_name: 'Under 7.5', selection_id: 3, price: 1.1, ref: { selection_name: 'Under 6.5', price: 1.01 } };
        expect(anomalyRefLabel(a as never)).toBe('Under 6.5 @1.01 → Under 7.5 @1.10');
        expect(anomalyRefLabel({ ...a, ref: 'Under 6.5 @1.01' } as never)).toBe('Under 6.5 @1.01 → Under 7.5 @1.10');
        expect(anomalyRefLabel({ ...a, ref: null } as never)).toBeNull();
    });

    it('comboIdempotencyPrefix: stesso prefisso per tutte le gambe, evento e tipo dentro', () => {
        const p = comboIdempotencyPrefix('e1', combo as never, 1000);
        expect(p.startsWith('combo:e1:dutch:rs:')).toBe(true);
        expect(comboIdempotencyPrefix('e1', combo as never, 1000)).not.toBe(p);   // suffisso casuale
    });
});

describe('parametri bot — rischio e auto-trade', () => {
    it('mergeBotParams: toggles e risk con default', () => {
        const p = mergeBotParams({ auto_trade_combos: true, risk: { daily_loss_stop: -20, correlated_cap: 'x' } });
        expect(p.auto_trade_combos).toBe(true);
        expect(p.auto_trade_anomalies).toBe(false);
        expect(p.auto_trade_tennis).toBe(false);
        expect(p.risk).toEqual({ ...SAFE_RISK_DEFAULTS, daily_loss_stop: -20 });
        expect(mergeBotParams(null).risk).toEqual(SAFE_RISK_DEFAULTS);
    });
});

describe('gambe di chiusura — raggruppamento e formati', () => {
    it('groupClosingLegs attacca le chiusure all apertura, orfane in coda', () => {
        const g = groupClosingLegs([
            { id: 70, closes_trade_id: null }, { id: 71, closes_trade_id: 70 }, { id: 72, closes_trade_id: 70 },
            { id: 80, closes_trade_id: null }, { id: 99, closes_trade_id: 5 },
        ]);
        expect(g.map((x) => [x.trade.id, x.closes.map((c) => c.id)])).toEqual([[70, [71, 72]], [80, []], [99, []]]);
    });

    it('fmtEurIt / fmtOddsIt / hedgeTooltip in formato italiano', () => {
        expect(fmtEurIt(-22.1, true)).toBe('−22,10 €');
        expect(fmtEurIt(24.24)).toBe('24,24 €');
        expect(fmtEurIt(3, true)).toBe('+3,00 €');
        expect(fmtOddsIt(4.9)).toBe('4,90');
        expect(fmtOddsIt(null)).toBe('—');
        expect(hedgeTooltip({ side: 'lay', price: 55 }, { side: 'back', price: 4.9 }))
            .toBe('il lay a 55,00 è stato coperto con un back a 4,90 sulla stessa selezione: esito identico su ogni risultato');
        expect(hedgeTooltip({ side: 'lay', price: 55 }, null)).toMatch(/un back a mercato/);
    });
});

describe('trade di modello — meta', () => {
    it('tradeHold legge meta.exit_hold; assente o malformato = null', () => {
        expect(tradeHold({ meta: null })).toBeNull();
        expect(tradeHold({ meta: { exit_hold: 'x' } })).toBeNull();
        expect(tradeHold({ meta: { exit_hold: { reason: 'wide_margin', p_lose: 0.004, source: 'model', locked: 1, ev_hold: 2, ts: 't' } } }))
            .toEqual({ reason: 'wide_margin', pLose: 0.004, source: 'model', locked: 1, evHold: 2, ts: 't' });
        expect(holdReasonLabel('wide_margin')).toBe('margine ampio');
        expect(holdReasonLabel('altro')).toBe('altro');
        expect(holdReasonLabel(null)).toBe('in attesa');
    });

    it('pLoseEntry e tradeOppKind', () => {
        expect(pLoseEntry({ meta: { p_lose_entry: 0.03 } })).toBe(0.03);
        expect(pLoseEntry({ meta: {} })).toBeNull();
        expect(tradeOppKind({ strategy: 'model', meta: { kind: 'combo' } })).toBe('combo');
        expect(tradeOppKind({ strategy: 'model', meta: null })).toBe('model');
        expect(tradeOppKind({ strategy: 'base', meta: { kind: 'combo' } })).toBeNull();
    });
});
