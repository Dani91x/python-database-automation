import { describe, it, expect } from 'vitest';
import {
    MIKE_PARAM_FIELDS, MIKE_PARAM_DEFAULTS, MIKE_STATES, MIKE_PHASE_META, mergeMikeParams,
    phaseMeta, sortEvents, cashoutPct, activeLegs, investedOf, requestInFlight, detectSettledEvents,
    type MikeEvent, type MikeLeg,
} from './mike';

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
        expect(MIKE_PARAM_DEFAULTS.pre_exit_mode).toBe('taker');
        expect(MIKE_PARAM_DEFAULTS.exact_sizes).toBe(true);
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
    it('sortEvents: live first, then flat, then pre by KO, then done', () => {
        const list = [
            ev({ event_id: 'a', state: 'SETTLED' }),
            ev({ event_id: 'b', state: 'WATCH', ko_at: '2026-09-12T16:00:00Z' }),
            ev({ event_id: 'c', state: 'LIVE_COVERED' }),
            ev({ event_id: 'd', state: 'WATCH', ko_at: '2026-09-12T14:00:00Z' }),
            ev({ event_id: 'e', state: 'FLAT' }),
        ];
        expect(sortEvents(list).map((e) => e.event_id)).toEqual(['c', 'e', 'd', 'b', 'a']);
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
