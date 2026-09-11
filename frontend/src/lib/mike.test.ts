import { describe, it, expect } from 'vitest';
import {
    MIKE_PARAM_FIELDS, MIKE_PARAM_DEFAULTS, MIKE_STATES, MIKE_PHASE_META, mergeMikeParams,
    phaseMeta, sortEvents, cashoutPct, activeLegs, investedOf, requestInFlight, detectSettledEvents,
    selectionExposure, lockedIfClosed, positionRows,
    splitMikeEvents, isEventLive, rememberLive, needsAttention, feedFreshness, lineLabel,
    bookOrders, legStatusLabel, pnlByTotalCells, groupMikeTrades, groupsOfDay, tradeDayMs,
    mikeEquitySeries, requestOutcome, lastRequestFor, mikeActivityLine, controlSignature,
    isHeartbeatOnlyChange, reasonLabel, roleLabel,
    eventFlags, marketLabel, marketCode, voidedMarketsOf, isManualTrade, VOID_ALL,
    marketStatusMeta, awaitingKickoff, mikeHistoryErrorMessage, withMikeHistoryError,
    MIKE_ACTIVITY_KINDS, MIKE_ACTIVITY_EXTRA, MIKE_REQUEST_CODE_MESSAGE, MIKE_REQUEST_KIND_LABEL,
    MIKE_REALTIME_TABLES, MIKE_AWAITING_KICKOFF_NOTE, MIKE_HISTORY_MIGRATION_HINT,
    type MikeEvent, type MikeLeg, type MikeRequest, type MikeTrade, romeDayStartMs, dayResultCounts } from './mike';
import { activityMeta } from './tradeStatus';

function leg(over: Partial<MikeLeg> = {}): MikeLeg {
    return {
        role: 'under_entry', market: 'OU35', selection: 'UNDER', side: 'back', price: 1.5, size: 10,
        matched: 10, avg_price: 1.5, ref: 'r1', status: 'open', placed_at: 0, persistence: 'LAPSE',
        cycle_no: 0, final: false, archived: false, ...over,
    };
}
function ev(over: Partial<MikeEvent> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'A v B', competition: 'X', league_id: null,
        ko_at: '2026-09-12T14:00:00Z', mode: 'paper', markets: {}, state: 'WATCH', cycle_no: 0,
        entry_price_initial: null, dossier: null, live: null, positions: [], ctx: null, skipped: false,
        settled_pnl: null, updated_at: '2026-09-12T12:00:00Z', ...over,
    };
}

describe('mike params', () => {
    it('every field has a default and every default has a field (specchio della whitelist)', () => {
        const keys = MIKE_PARAM_FIELDS.map((f) => f.key);
        expect(new Set(keys).size).toBe(keys.length);
        for (const k of keys) expect(MIKE_PARAM_DEFAULTS).toHaveProperty(k);
        for (const k of Object.keys(MIKE_PARAM_DEFAULTS)) expect(keys).toContain(k);
    });
    it('defaults match the backend plan', () => {
        expect(MIKE_PARAM_DEFAULTS.stake).toBe(10);
        expect(MIKE_PARAM_DEFAULTS.entry_hours_before_ko).toBe(3);
        expect(MIKE_PARAM_DEFAULTS.cashout_profit_pct).toBe(5);
        expect(MIKE_PARAM_DEFAULTS.ht_loss_pct).toBe(25);
        expect(MIKE_PARAM_DEFAULTS.pre_exit_mode).toBe('resting');
        expect(MIKE_PARAM_DEFAULTS.pre_max_spread_ticks).toBe(6);
        expect(MIKE_PARAM_DEFAULTS.exact_sizes).toBe(true);
        expect(MIKE_PARAM_DEFAULTS.cashout_smart_enabled).toBe(true);
        expect(MIKE_PARAM_DEFAULTS.cashout_smart_min_pct).toBe(2);
        expect(MIKE_PARAM_DEFAULTS.cashout_smart_goals_hot).toBe(3);
        expect(MIKE_PARAM_DEFAULTS.loss_exit_mode).toBe('model');
        expect(MIKE_PARAM_DEFAULTS.loss_exit_risk_premium_pct).toBe(50);
    });
    it('number defaults are inside their bounds', () => {
        for (const f of MIKE_PARAM_FIELDS) {
            if (f.kind !== 'number') continue;
            const d = Number(MIKE_PARAM_DEFAULTS[f.key]);
            expect(d).toBeGreaterThanOrEqual(f.min);
            expect(d).toBeLessThanOrEqual(f.max);
        }
    });
    it('mergeMikeParams clamps, casts and drops unknown keys', () => {
        const p = mergeMikeParams({ stake: '1000', pre_green_ticks: 0, pre_enabled: 'false', cover_policy: 'wait',
                                     cover_rounding: 'banana', foo: 1, mode: 'live' });
        expect(p.stake).toBe(500);
        expect(p.pre_green_ticks).toBe(1);
        expect(p.pre_enabled).toBe(false);
        expect(p.cover_policy).toBe('wait');
        expect(p.cover_rounding).toBe('ceil');
        expect(p).not.toHaveProperty('foo');
        expect(p).not.toHaveProperty('mode');
        expect(mergeMikeParams(null)).toEqual(MIKE_PARAM_DEFAULTS);
    });
});

describe('mike phases', () => {
    it('phase meta covers every state', () => {
        for (const s of MIKE_STATES) expect(MIKE_PHASE_META[s].label).toBeTruthy();
        expect(phaseMeta('nonsense').label).toBe(MIKE_PHASE_META.WATCH.label);
    });
    it('sortEvents: ordine STABILE per calcio di inizio, MAI per fase', () => {
        const list = [
            ev({ event_id: 'b', state: 'WATCH', ko_at: '2026-09-12T16:00:00Z' }),
            ev({ event_id: 'c', state: 'LIVE_COVERED', ko_at: '2026-09-12T18:00:00Z' }),
            ev({ event_id: 'd', state: 'WATCH', ko_at: '2026-09-12T14:00:00Z' }),
            ev({ event_id: 'a2', state: 'SETTLED', ko_at: '2026-09-12T14:00:00Z' }),
        ];
        expect(sortEvents(list).map((e) => e.event_id)).toEqual(['a2', 'd', 'b', 'c']);
        // la stessa lista con le FASI cambiate si ordina IDENTICA: le card non si muovono
        const moved = list.map((e) => ({ ...e, state: 'LIVE_CLOSING' as const }));
        expect(sortEvents(moved).map((e) => e.event_id)).toEqual(['a2', 'd', 'b', 'c']);
        // senza KO la partita va in fondo, mai in mezzo
        expect(sortEvents([...list, ev({ event_id: 'z', ko_at: null })]).map((e) => e.event_id))
            .toEqual(['a2', 'd', 'b', 'c', 'z']);
    });
});

describe('mike helpers', () => {
    it('cashoutPct', () => {
        expect(cashoutPct(1.31, 24)).toBe(5.5);
        expect(cashoutPct(1, 0)).toBeNull();
        expect(cashoutPct(null, 10)).toBeNull();
    });
    it('activeLegs excludes archived, investedOf sums opening backs', () => {
        const e = ev({ positions: [leg(), leg({ ref: 'r2', archived: true }), leg({ ref: 'r3', role: 'under_green', side: 'lay', size: 10.14, matched: 10.14 })] });
        expect(activeLegs(e).map((l) => l.ref)).toEqual(['r1', 'r3']);
        expect(investedOf(e)).toBe(10);
    });
    it('requestInFlight only for pending/processing of same event+kind', () => {
        const reqs = [
            { id: 1, kind: 'cashout' as const, payload: { event_id: 'E1' }, status: 'pending' as const, result: null, created_at: '' },
            { id: 2, kind: 'skip_event' as const, payload: { event_id: 'E1' }, status: 'done' as const, result: null, created_at: '' },
        ];
        expect(requestInFlight('E1', 'cashout', reqs)).toBe(true);
        expect(requestInFlight('E1', 'skip_event', reqs)).toBe(false);
        expect(requestInFlight('E2', 'cashout', reqs)).toBe(false);
    });
    it('detectSettledEvents: first load only memorizes', () => {
        const seen = new Set<string>();
        const list = [ev({ event_id: 'a', state: 'SETTLED' }), ev({ event_id: 'b', state: 'WATCH' })];
        expect(detectSettledEvents(list, seen, true)).toEqual([]);
        expect(detectSettledEvents([...list, ev({ event_id: 'c', state: 'SETTLED' })], seen, false).map((e) => e.event_id)).toEqual(['c']);
    });
});

describe('mike positions (ingresso vs quota live)', () => {
    it('selectionExposure + lockedIfClosed replicate engine.exposure / compute_greenup', () => {
        // Under 3.5 back 20 @ 1.50: W=10, L=-20 ; lay 1.31 -> locked = -20 + 30/1.31 = 2.90 (test Python)
        const legs = [leg({ size: 20, matched: 20, avg_price: 1.5 })];
        expect(selectionExposure(legs, 'OU35', 'UNDER')).toEqual({ w: 10, l: -20 });
        expect(lockedIfClosed(10, -20, 1.30, 1.31)).toBeCloseTo(2.90, 2);
        // green parziale: back 20 @1.50 + lay 10 @1.48 -> W = 10 - 4.8 = 5.2, L = -20 + 10 = -10
        const legs2 = [...legs, leg({ role: 'under_green', side: 'lay', price: 1.48, size: 20.27, matched: 10, avg_price: 1.48, ref: 'r2' })];
        expect(selectionExposure(legs2, 'OU35', 'UNDER')).toEqual({ w: 5.2, l: -10 });
        // posizione piatta -> min(W, L) ; prezzo mancante -> null ; gambe archiviate ignorate
        expect(lockedIfClosed(3, 3, null, null)).toBe(3);
        expect(lockedIfClosed(10, -20, 1.3, null)).toBeNull();
        expect(selectionExposure([leg({ archived: true })], 'OU35', 'UNDER')).toEqual({ w: 0, l: 0 });
    });
    it('positionRows: una riga per selezione con lato netto, prezzo medio e selection_id certificato', () => {
        const e = ev({
            ctx: { selections: { 'OU35|UNDER': 1222344, 'OU45|OVER': 1222346 } },
            positions: [
                leg({ size: 10, matched: 10, avg_price: 1.5 }),
                leg({ role: 'under_last', price: 1.6, size: 10, matched: 10, avg_price: 1.6, ref: 'r3', persistence: 'PERSIST' }),
                leg({ role: 'over_cover', market: 'OU45', selection: 'OVER', price: 8, size: 4, matched: 4, avg_price: 8, ref: 'r4' }),
                leg({ role: 'under_green', side: 'lay', price: 1.48, size: 10, matched: 0, status: 'pending', ref: 'r5' }),
                leg({ role: 'under_entry', size: 10, matched: 10, avg_price: 1.4, ref: 'old', archived: true }),
            ],
        });
        const rows = positionRows(e);
        expect(rows.map((r) => r.key)).toEqual(['OU35|UNDER', 'OU45|OVER']);
        expect(rows[0]).toMatchObject({ label: 'Under 3.5', netSide: 'BACK', matched: 20, entryPrice: 1.55, selectionId: 1222344 });
        expect(rows[0].roles).toEqual(['under_entry', 'under_last']);
        expect(rows[1]).toMatchObject({ label: 'Over 4.5', netSide: 'BACK', matched: 4, entryPrice: 8, selectionId: 1222346, w: 28, l: -4 });
    });
});

// ---------------------------------------------------------------- fixtures
function trade(over: Partial<MikeTrade> = {}): MikeTrade {
    return {
        id: 1, event_id: 'E1', event_name: 'A v B', strategy: 'mike', role: 'under_entry', cycle_no: 0,
        market_type: 'OVER_UNDER_35', selection_name: 'Under 3.5', side: 'back', mode: 'paper',
        price: 1.5, size: 10, liability: 10, status: 'won', pnl: 4.75,
        placed_at: '2026-09-11T10:00:00Z', settled_at: '2026-09-11T16:00:00Z', signal_key: null,
        meta: null, closes_trade_id: null, day_placed_at: '2026-09-11T10:00:00Z', ...over,
    };
}
function req(over: Partial<MikeRequest> = {}): MikeRequest {
    return {
        id: 1, kind: 'cashout', payload: { event_id: 'E1' }, status: 'done',
        result: { code: 'ok', message: 'Cash out inviato.' }, created_at: '2026-09-11T10:00:00Z',
        updated_at: '2026-09-11T10:00:05Z', ...over,
    };
}

describe('mike sezioni PRE-MATCH / LIVE / DA SISTEMARE', () => {
    it('divide per stato del gioco (non per fase) e ordina per KO crescente', () => {
        const list = [
            ev({ event_id: 'p2', state: 'WATCH', ko_at: '2026-09-12T18:00:00Z', live: { inplay: false } }),
            ev({ event_id: 'l1', state: 'LIVE_UNCOVERED', ko_at: '2026-09-12T12:00:00Z', live: { inplay: true } }),
            ev({ event_id: 'p1', state: 'PRE_OPEN', ko_at: '2026-09-12T14:00:00Z', live: { inplay: false } }),
            ev({ event_id: 'l2', state: 'LIVE_COVERED', ko_at: '2026-09-12T13:00:00Z', live: { inplay: true } }),
            ev({ event_id: 'x1', state: 'ERROR' }),
            ev({ event_id: 'x2', state: 'SKIPPED' }),
            ev({ event_id: 's1', state: 'SETTLED' }),
        ];
        const s = splitMikeEvents(list);
        expect(s.pre.map((e) => e.event_id)).toEqual(['p1', 'p2']);
        expect(s.live.map((e) => e.event_id)).toEqual(['l1', 'l2']);
        expect(s.fix.map((e) => e.event_id)).toEqual(['x1', 'x2']);
        expect(s.settled.map((e) => e.event_id)).toEqual(['s1']);
    });
    it('una partita in gioco NON torna in pre-match (memoria sticky)', () => {
        const sticky = new Set<string>();
        rememberLive([ev({ event_id: 'l1', live: { inplay: true } })], sticky);
        expect(sticky.has('l1')).toBe(true);
        // buco di feed: inplay sparisce, ma la card resta nella sezione LIVE
        const blind = ev({ event_id: 'l1', live: { inplay: false } });
        expect(isEventLive(blind)).toBe(false);
        expect(isEventLive(blind, sticky)).toBe(true);
        expect(splitMikeEvents([blind], sticky).live.map((e) => e.event_id)).toEqual(['l1']);
    });
    it('needsAttention copre ERROR, SKIPPED e skipped=true', () => {
        expect(needsAttention(ev({ state: 'ERROR' }))).toBe(true);
        expect(needsAttention(ev({ state: 'SKIPPED' }))).toBe(true);
        expect(needsAttention(ev({ state: 'WATCH', skipped: true }))).toBe(true);
        expect(needsAttention(ev({ state: 'PRE_OPEN' }))).toBe(false);
    });
});

describe('mike freschezza feed e linee', () => {
    it('verde fino a 5 s, ambra fino a 20 s, poi FEED FERMO', () => {
        expect(feedFreshness(3).tone).toBe('ok');
        expect(feedFreshness(12).tone).toBe('warn');
        expect(feedFreshness(45).tone).toBe('stale');
        expect(feedFreshness(45).label).toContain('FEED FERMO');
        expect(feedFreshness(null).tone).toBe('unknown');
    });
    it('lineLabel traduce la chiave del feed', () => {
        expect(lineLabel('OU35|UNDER')).toBe('Under 3.5');
        expect(lineLabel('OU45|OVER')).toBe('Over 4.5');
        expect(lineLabel('OU45|UNDER')).toBe('Under 4.5');
    });
});

describe('mike gambe e P&L per gol', () => {
    it('bookOrders = solo ordini vivi con residuo; legStatusLabel sempre in italiano', () => {
        const e = ev({ positions: [
            leg({ ref: 'a', status: 'pending', size: 10, matched: 0 }),
            leg({ ref: 'b', status: 'pending', size: 10, matched: 10 }),
            leg({ ref: 'c', status: 'pending_reconcile', size: 4, matched: 0 }),
            leg({ ref: 'd', status: 'open' }),
            leg({ ref: 'e', status: 'pending', size: 10, matched: 0, archived: true }),
        ] });
        expect(bookOrders(e).map((l) => l.ref)).toEqual(['a', 'c']);
        expect(legStatusLabel(leg({ status: 'pending_reconcile' }))).toBe('IN VERIFICA');
        expect(legStatusLabel(leg({ status: 'pending', matched: 0 }))).toBe('SUL BOOK');
        expect(legStatusLabel(leg({ status: 'pending', matched: 3 }))).toBe('SUL BOOK (parziale)');
        expect(legStatusLabel(leg({ status: 'open' }))).toBe('ABBINATA');
    });
    it('pnlByTotalCells marca i 4 gol, i gol attuali e l ultima cella', () => {
        const cells = pnlByTotalCells({ '0': 4.75, '4': -10, '5': -10, '8': -10 }, 4);
        expect(cells.map((c) => c.total)).toEqual([0, 4, 5, 8]);
        expect(cells.find((c) => c.total === 4)).toMatchObject({ isFour: true, isCurrent: true, value: -10 });
        expect(cells[cells.length - 1].isLast).toBe(true);
        expect(pnlByTotalCells(null, null)).toEqual([]);
    });
});

describe('mike attivita: tutti i kind in italiano', () => {
    it('ogni kind del servizio ha una etichetta dichiarata (mai "kind sconosciuto")', () => {
        for (const k of MIKE_ACTIVITY_KINDS) {
            const m = activityMeta(k, MIKE_ACTIVITY_EXTRA);
            expect(m.label, k).toBeTruthy();
            expect(m.label, k).not.toContain('kind sconosciuto');
            expect(m.label, k).not.toMatch(/[a-z]+_[a-z]+/);
        }
    });
    it('i kind money-critical sono CRITICI (rossi, mai sepolti)', () => {
        for (const k of ['error', 'feed_line_missing', 'reconcile_pending', 'close_retries_exhausted',
                         'daily_stop', 'resting_live_unsupported']) {
            expect(activityMeta(k, MIKE_ACTIVITY_EXTRA).critical, k).toBe(true);
        }
    });
    it('mikeActivityLine scrive righe leggibili con i formatter unici', () => {
        expect(mikeActivityLine('place', { role: 'under_entry', side: 'back', size: 10, price: 1.5 }))
            .toBe('Ingresso Under 3.5 BACK 10,00 € @ 1,50');
        expect(mikeActivityLine('pre_cycle', { cycle: 1, entry: 1.5, exit: 1.48, locked: 0.13 }))
            .toContain('P&L bloccato +0,13 €');
        expect(mikeActivityLine('settled', { total: 3, net: 4.51 })).toBe('totale gol 3 · P&L +4,51 €');
        expect(mikeActivityLine('settled', { void: true, reason: 'mercato_annullato', pnl: 0 }))
            .toContain('mercato annullato');
        expect(mikeActivityLine('feed_line_missing', { markets: ['OU45|OVER'], state: 'LIVE_UNCOVERED' }))
            .toContain('Over 4.5');
        expect(mikeActivityLine('reconcile_pending', { leg: 'over_cover-0-2', reason: 'place_exception_reconciling' }))
            .toContain('esito ignoto');
        expect(mikeActivityLine('daily_stop', { day_pnl: -51, realized_today: -40, locked_open: -11, stop: 50 }))
            .toContain('−51,00 €');
        expect(mikeActivityLine('no_fill', { role: 'over_cover', side: 'back', wanted: 6.6, available: 6.2 }))
            .toContain('non abbinato');
        expect(mikeActivityLine('mai_visto', { reason: 'feed_stantio' })).toBe('feed stantio');
        expect(reasonLabel('feed_stantio')).toBe('feed stantio');
    });
});

describe('mike esito richieste (M1)', () => {
    it('ogni codice documentato ha un messaggio italiano', () => {
        for (const code of ['ok', 'evento_non_seguito', 'stato_terminale', 'posizione_aperta',
                            'stato_non_riprendibile', 'feed_assente', 'snapshot_assente',
                            'niente_da_chiudere', 'feed_stantio', 'kind_non_valido',
                            'errore_interno', 'processing_stale']) {
            expect(MIKE_REQUEST_CODE_MESSAGE[code], code).toBeTruthy();
        }
        expect(MIKE_REQUEST_KIND_LABEL.cashout).toBe('Cash out');
    });
    it('rifiuto, errore, in corso ed esito positivo hanno riga e tono propri', () => {
        const rejected = requestOutcome(req({ status: 'rejected', result: { code: 'feed_stantio', message: 'Feed stantio: cash out rifiutato.' } }));
        expect(rejected.tone).toBe('warn');
        expect(rejected.label).toBe('Cash out rifiutato: Feed stantio: cash out rifiutato.');
        expect(requestOutcome(req({ status: 'rejected', result: { code: 'niente_da_chiudere' } })).label)
            .toBe('Cash out rifiutato: niente da chiudere');
        expect(requestOutcome(req({ status: 'error', result: { code: 'errore_interno' } })).tone).toBe('bad');
        expect(requestOutcome(req({ status: 'pending', result: null })).label).toBe('Cash out in corso…');
        expect(requestOutcome(req()).tone).toBe('ok');
        expect(requestOutcome(req({ result: { code: 'ok', message: 'ok', warning: 'reconcile' } })).label)
            .toContain('ordini in verifica');
    });
    it('chiusura ARMATA (phase "armed"): ordini annullati, netto stimato in italiano', () => {
        const armed = requestOutcome(req({
            result: {
                code: 'ok', phase: 'armed', cancelled: 1, cashout_net: 0.47, complete: true,
                message: 'Cash out: annullati 1 ordini sul book, chiusura in corso (netto stimato 0.47 EUR).',
            },
        }));
        expect(armed.tone).toBe('ok');
        expect(armed.armed).toBe(true);
        expect(armed.net).toBe(0.47);
        expect(armed.label).toBe('Cash out armato: annullati 1 ordini sul book · chiusura in corso · netto stimato +0,47 €');
        // il messaggio grezzo del servizio resta come dettaglio (tooltip)
        expect(armed.message).toContain('netto stimato 0.47 EUR');
        // senza ordini da annullare, con prezzi incompleti e riconciliazione in corso
        const partial = requestOutcome(req({
            kind: 'flatten',
            result: { code: 'ok', phase: 'armed', cancelled: 0, cashout_net: -1.2, complete: false, warning: 'reconcile' },
        }));
        expect(partial.label).toBe('Flatten armato: chiusura in corso · netto stimato −1,20 € · prezzi incompleti su una selezione · ordini in verifica');
    });
    it('lastRequestFor prende la piu recente per evento e kind', () => {
        const reqs = [req({ id: 1 }), req({ id: 7, kind: 'skip_event' }), req({ id: 9 }),
                      req({ id: 12, payload: { event_id: 'E2' } })];
        expect(lastRequestFor('E1', reqs)?.id).toBe(9);
        expect(lastRequestFor('E1', reqs, 'skip_event')?.id).toBe(7);
        expect(lastRequestFor('E3', reqs)).toBeNull();
    });
});

describe('mike contesto: chiusura armata e rientro bloccato', () => {
    it('eventFlags legge ctx.flatten_pending e ctx.no_reentry (con ripiego su live)', () => {
        expect(eventFlags(ev())).toEqual({ flattenPending: false, noReentry: false });
        expect(eventFlags(ev({ ctx: { flatten_pending: true } })).flattenPending).toBe(true);
        expect(eventFlags(ev({ ctx: { no_reentry: true } })).noReentry).toBe(true);
        // il servizio pubblica no_reentry anche in live.*: la UI non deve perderlo
        expect(eventFlags(ev({ live: { inplay: false, no_reentry: true } })).noReentry).toBe(true);
    });
});

describe('mike void PER MERCATO', () => {
    it('marketLabel e marketCode normalizzano le due linee', () => {
        expect(marketLabel('OU35')).toBe('linea 3.5');
        expect(marketLabel('OVER_UNDER_45')).toBe('linea 4.5');
        expect(marketCode('OVER_UNDER_35')).toBe('OU35');
    });
    it('voidedMarketsOf legge attività e righe, senza marchiare tutta la partita', () => {
        const act = [{ id: 1, ts: '2026-09-11T18:00:00Z', event_id: 'E1', kind: 'settled',
                       payload: { void: true, reason: 'mercato_annullato', voided: ['OU35'], pnl: 0, legs: 2 } }];
        expect(voidedMarketsOf('E1', act, [])).toEqual(['OU35']);
        expect(voidedMarketsOf('E2', act, [])).toEqual([]);
        // ripiego dalle righe annullate
        const rows = [trade({ id: 1, status: 'void', market_type: 'OVER_UNDER_45', meta: { void_reason: 'mercato_annullato' } })];
        expect(voidedMarketsOf('E1', [], rows)).toEqual(['OU45']);
        // payload senza elenco = tutta la partita
        const all = [{ id: 2, ts: '', event_id: 'E1', kind: 'settled', payload: { void: true, pnl: 0 } }];
        expect(voidedMarketsOf('E1', all, [])).toEqual([VOID_ALL]);
    });
    it('la riga di attività dice QUALE linea è stata annullata', () => {
        expect(mikeActivityLine('settled', { void: true, reason: 'mercato_annullato', voided: ['OU35'], pnl: 0 }))
            .toBe('mercato annullato (linea 3.5) · P&L +0,00 €');
        expect(mikeActivityLine('settled', { void: true, pnl: 0 })).toContain('tutta la partita');
    });
});

describe('mike righe manuali (✋)', () => {
    it('isManualTrade riconosce origin, ruolo e uscita manuale', () => {
        expect(isManualTrade(trade({ origin: 'manual' }))).toBe(true);
        expect(isManualTrade(trade({ role: 'manual_close' }))).toBe(true);
        expect(isManualTrade(trade({ meta: { exit_kind: 'manual' } }))).toBe(true);
        expect(isManualTrade(trade())).toBe(false);
        expect(roleLabel('manual_close')).toBe('Chiusura manuale');
    });
});

describe('mike trade: chiusure annidate sotto apertura (H4)', () => {
    it('raggruppa, somma il netto e dichiara le orfane', () => {
        const rows = [
            trade({ id: 1, pnl: 10, status: 'won', placed_at: '2026-09-11T10:00:00Z' }),
            trade({ id: 2, closes_trade_id: 1, role: 'under_green', side: 'lay', pnl: -7.1, status: 'lost',
                    placed_at: '2026-09-11T10:05:00Z', day_placed_at: '2026-09-11T10:00:00Z' }),
            trade({ id: 3, closes_trade_id: 1, role: 'under_close', pnl: 0, status: 'void',
                    placed_at: '2026-09-11T10:02:00Z', day_placed_at: '2026-09-11T10:00:00Z' }),
            trade({ id: 4, closes_trade_id: 99, role: 'manual_close', pnl: 1, status: 'won',
                    placed_at: '2026-09-11T11:00:00Z' }),
            trade({ id: 5, status: 'open', pnl: 0, placed_at: '2026-09-11T12:00:00Z' }),
        ];
        const groups = groupMikeTrades(rows);
        expect(groups.map((g) => g.open.id)).toEqual([5, 4, 1]);
        const cycle = groups.find((g) => g.open.id === 1)!;
        expect(cycle.closes.map((c) => c.id)).toEqual([3, 2]);
        expect(cycle.netPnl).toBe(2.9);
        expect(groups.find((g) => g.open.id === 4)!.orphan).toBe(true);
        expect(groups.find((g) => g.open.id === 5)!.netPnl).toBeNull();
    });
    it('giornata operativa = piazzamento della posizione', () => {
        const dayStart = Date.parse('2026-09-11T00:00:00+02:00');
        const oggi = trade({ id: 1, placed_at: '2026-09-11T10:00:00Z', day_placed_at: '2026-09-11T10:00:00Z' });
        const ieriVivo = trade({ id: 2, status: 'open', placed_at: '2026-09-10T20:00:00Z', day_placed_at: '2026-09-10T20:00:00Z' });
        const chiusuraDiIeri = trade({ id: 3, closes_trade_id: 2, placed_at: '2026-09-11T09:00:00Z', day_placed_at: '2026-09-10T20:00:00Z' });
        expect(tradeDayMs(chiusuraDiIeri)).toBe(Date.parse('2026-09-10T20:00:00Z'));
        const groups = groupMikeTrades([oggi, ieriVivo, chiusuraDiIeri]);
        expect(groupsOfDay(groups, dayStart).map((g) => g.open.id)).toEqual([1]);
        expect(groupsOfDay(groups, null)).toHaveLength(2);
    });
    it('mikeEquitySeries: P&L netto cumulato dei soli regolati', () => {
        const rows = [
            trade({ id: 1, pnl: 4.75, settled_at: '2026-09-11T16:00:00Z' }),
            trade({ id: 2, pnl: -2, status: 'lost', settled_at: '2026-09-11T18:00:00Z' }),
            trade({ id: 3, pnl: 0, status: 'open', settled_at: null }),
        ];
        expect(mikeEquitySeries(rows).map((p) => p.v)).toEqual([4.75, 2.75]);
        expect(mikeEquitySeries(rows, Date.parse('2026-09-12T00:00:00Z'))).toEqual([]);
    });
});

describe('mike realtime: il battito non fa ricaricare', () => {
    it('controlSignature ignora heartbeat_at, updated_at e stats volatili', () => {
        const a = { id: 1, status: 'running', mode: 'paper', params: { stake: 10 },
                    stats: { trades_open: 2, last_cycle: 'T1', scanner_age_s: 2 },
                    heartbeat_at: 'T1', updated_at: 'T1' };
        const beat = { ...a, heartbeat_at: 'T2', updated_at: 'T2',
                       stats: { trades_open: 2, last_cycle: 'T2', scanner_age_s: 3 } };
        const real = { ...a, stats: { trades_open: 3, last_cycle: 'T2', scanner_age_s: 3 } };
        expect(controlSignature(beat)).toBe(controlSignature(a));
        expect(controlSignature(real)).not.toBe(controlSignature(a));
        expect(isHeartbeatOnlyChange('mike_control', beat, controlSignature(a))).toBe(true);
        expect(isHeartbeatOnlyChange('mike_control', real, controlSignature(a))).toBe(false);
        expect(isHeartbeatOnlyChange('mike_events', beat, controlSignature(a))).toBe(false);
    });
});

describe('mike parametri: gli inerti sono stati rimossi (audit M3)', () => {
    it('max_matches, catalogue_refresh_s, min_total_matched, stream_extra_lines non esistono piu', () => {
        const keys = MIKE_PARAM_FIELDS.map((f) => f.key);
        for (const k of ['max_matches', 'catalogue_refresh_s', 'min_total_matched', 'stream_extra_lines']) {
            expect(keys, k).not.toContain(k);
            expect(MIKE_PARAM_DEFAULTS, k).not.toHaveProperty(k);
        }
        expect(keys).toContain('settle_confirm_s');
        expect(keys).toContain('skip_log_interval_s');
        expect(keys).toContain('cover_max_overshoot_pct');
    });
});

describe('mike stato del mercato Betfair in ITALIANO', () => {
    it('OPEN non si dice, gli altri stati sono tradotti e ALLARMANTI', () => {
        expect(marketStatusMeta('OPEN')).toBeNull();
        expect(marketStatusMeta('open')).toBeNull();
        expect(marketStatusMeta(null)).toBeNull();
        expect(marketStatusMeta('')).toBeNull();
        expect(marketStatusMeta('SUSPENDED')).toEqual(
            expect.objectContaining({ label: 'SOSPESO', alarming: true }));
        expect(marketStatusMeta('CLOSED')).toEqual(
            expect.objectContaining({ label: 'CHIUSO', alarming: true }));
        expect(marketStatusMeta('INACTIVE')).toEqual(
            expect.objectContaining({ label: 'NON ATTIVO', alarming: true }));
        // colori: ambra per "sospeso", rosso per "chiuso"/"non attivo"
        expect(marketStatusMeta('SUSPENDED')?.cls).toContain('amber');
        expect(marketStatusMeta('CLOSED')?.cls).toContain('red');
        // uno stato mai visto non resta muto: si mostra leggibile e in ambra
        const unknown = marketStatusMeta('some_new_state');
        expect(unknown?.label).toBe('SOME NEW STATE');
        expect(unknown?.alarming).toBe(true);
    });
});

describe('mike KO passato ma partita non ancora in gioco', () => {
    const past = '2026-09-12T14:00:00Z';
    const nowMs = Date.parse('2026-09-12T14:05:00Z');

    it('resta in PRE-MATCH e lo dichiara', () => {
        const e = ev({ ko_at: past, state: 'HOLD', live: { inplay: false } });
        expect(awaitingKickoff(e, nowMs)).toBe(true);
        expect(isEventLive(e)).toBe(false);
        expect(splitMikeEvents([e]).pre).toHaveLength(1);
        expect(splitMikeEvents([e]).live).toHaveLength(0);
        expect(MIKE_AWAITING_KICKOFF_NOTE).toBe('in attesa del fischio');
    });

    it('prima del KO, in gioco o in stato terminale: nessuna attesa', () => {
        expect(awaitingKickoff(ev({ ko_at: past }), Date.parse('2026-09-12T13:00:00Z'))).toBe(false);
        expect(awaitingKickoff(ev({ ko_at: past, live: { inplay: true } }), nowMs)).toBe(false);
        expect(awaitingKickoff(ev({ ko_at: past, state: 'SETTLED' }), nowMs)).toBe(false);
        expect(awaitingKickoff(ev({ ko_at: null }), nowMs)).toBe(false);
    });

    it('una partita appena ARMATA (senza live) va in PRE-MATCH', () => {
        const e = ev({ live: null, state: 'WATCH' });
        expect(isEventLive(e)).toBe(false);
        const s = splitMikeEvents([e]);
        expect(s.pre.map((x) => x.event_id)).toEqual(['E1']);
        expect(s.live).toHaveLength(0);
    });
});

describe('mike storico: errore LEGGIBILE senza la migrazione (R2)', () => {
    it('gli errori di firma/RPC diventano "applica migrations/mike_history_v2.sql"', () => {
        for (const raw of [
            new Error('function public.trading_daily_history(unknown, unknown) is not unique'),
            new Error('Could not find the function public.get_mike_daily(p_from, p_to)'),
            new Error('function get_mike_day_trades does not exist'),
            new Error('tabella non ammessa: mike_trades'),
            new Error('attribuzione non valida: placed'),
        ]) {
            expect(mikeHistoryErrorMessage(raw)).toContain(MIKE_HISTORY_MIGRATION_HINT);
            expect(mikeHistoryErrorMessage(raw)).not.toBe(raw.message);
        }
    });

    it('un errore diverso resta quello che è (mai un consiglio sbagliato)', () => {
        expect(mikeHistoryErrorMessage(new Error('non autorizzato (owner-only)')))
            .toBe('non autorizzato (owner-only)');
        expect(mikeHistoryErrorMessage(null)).toBe('storico Mike non disponibile');
    });

    it('withMikeHistoryError riscrive l’errore e lascia passare i dati', async () => {
        const ok = withMikeHistoryError(async (n: number) => n * 2);
        await expect(ok(3)).resolves.toBe(6);
        const ko = withMikeHistoryError(async () => {
            throw new Error('function public.trading_day_trades(...) is not unique');
        });
        await expect(ko()).rejects.toThrow(MIKE_HISTORY_MIGRATION_HINT);
    });
});

describe('mike realtime: le tabelle sottoscritte', () => {
    it('sono TUTTE quelle che il servizio scrive (mike_activity compresa)', () => {
        expect([...MIKE_REALTIME_TABLES]).toEqual([
            'mike_control', 'mike_events', 'mike_trades', 'mike_activity', 'mike_requests',
        ]);
    });
});


// ------------------------------------------------ ripieghi senza mike_bot_v2 (certificazione dati reali)
describe('ripieghi di giornata senza mike_bot_v2.sql', () => {
    it('romeDayStartMs: mezzanotte di Roma dell\'istante dato (estate = UTC+2, inverno = UTC+1)', () => {
        const now = Date.parse('2026-09-11T16:30:15.250Z');   // 18:30:15 a Roma
        expect(romeDayStartMs(now)).toBe(Date.parse('2026-09-10T22:00:00.000Z'));
        expect(romeDayStartMs(Date.parse('2026-01-15T00:00:00.000Z'))).toBe(Date.parse('2026-01-14T23:00:00.000Z'));
    });
    it('dayResultCounts: V/P per POSIZIONE (netto apertura+chiusure) e solo della giornata', () => {
        const mk = (id: number, placed: string, status: string, pnl: number, closes?: number): MikeTrade => ({
            id, event_id: 'E', event_name: 'A v B', signal_key: `k${id}`, strategy: 'mike', role: 'under_entry',
            side: 'back', price: 1.5, size: 10, matched: 10, status, pnl, placed_at: placed, settled_at: placed,
            mode: 'paper', origin: 'auto', market_id: '1.1', selection_id: 1, selection_name: 'Under 3.5',
            closes_trade_id: closes ?? null, meta: null,
        } as unknown as MikeTrade);
        const day = Date.parse('2026-09-10T22:00:00Z');
        const trades = [
            mk(1, '2026-09-11T10:00:00Z', 'lost', -10),          // apertura persa
            mk(2, '2026-09-11T10:05:00Z', 'won', 12, 1),         // chiusura della 1: posizione netta +2 -> VINTA
            mk(3, '2026-09-11T11:00:00Z', 'lost', -5),           // persa
            mk(4, '2026-09-09T11:00:00Z', 'won', 7),             // ieri: fuori giornata
            mk(5, '2026-09-11T12:00:00Z', 'open', 0),            // viva: non conta
        ];
        expect(dayResultCounts(trades, day)).toEqual({ won: 1, lost: 1 });
        expect(dayResultCounts(trades, null)).toEqual({ won: 2, lost: 1 });
    });
});
