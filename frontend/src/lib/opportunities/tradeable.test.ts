// ============================================================================
// tradeable.test.ts — il GATE "specchio della realtà": un'opportunità si mostra
// SOLO se è davvero piazzabile (mercato OPEN + controparte reale su ogni gamba).
// Blinda contro la regressione del bug "abbinato £0 / +375%" su mercati
// sospesi o con prezzi fantasma senza controparte.
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { MarketState, Opportunity, Snapshot, Leg, RiskTier } from './types';
import { isMarketOpen, tradeableSelection, isExecutableNow, entryLegs } from './tradeable';
import { runDetectors, DEFAULT_OPP_CONFIG } from './engine';
import { backToLay } from './tier1_quasi';

type Lvl = [number, number][];
function st(status: string, sels: Record<number, { back?: Lvl; lay?: Lvl }>): MarketState {
    const ladder: Record<string, { back: Lvl; lay: Lvl; ltp: number | null; tv: number | null }> = {};
    for (const [sid, e] of Object.entries(sels)) {
        ladder[sid] = { back: e.back ?? [], lay: e.lay ?? [], ltp: null, tv: null };
    }
    return { market_id: 'm1', market_type: 'MATCH_ODDS', status, ladder };
}

function leg(over: Partial<Leg> = {}): Leg {
    return {
        marketId: 'm1', marketName: 'Match Odds', selectionId: 1, selectionName: 'A',
        side: 'back', price: 2.0, stake: 100, matchedStake: 100, ...over,
    };
}
function opp(over: Partial<Opportunity> = {}): Opportunity {
    return {
        id: 'x', tier: 'directional' as RiskTier, type: 't', title: 't', instruction: 'i',
        legs: [leg()], profit: 5, profitPct: 5, confidence: 0.5, explanation: 'e', phase: 'p', ...over,
    };
}
function snap(state: Record<string, MarketState>, over: Partial<Snapshot> = {}): Snapshot {
    return { ts: '2026-01-01T00:30:00.000Z', minute: 30, scoreHome: 0, scoreAway: 0, markets: [], state, ...over };
}

describe('isMarketOpen', () => {
    it('true solo per OPEN', () => {
        expect(isMarketOpen(st('OPEN', {}))).toBe(true);
        expect(isMarketOpen(st('SUSPENDED', {}))).toBe(false);
        expect(isMarketOpen(st('CLOSED', {}))).toBe(false);
        expect(isMarketOpen(undefined)).toBe(false);
    });
});

describe('tradeableSelection — mercato reale a due lati', () => {
    it('OK: book normale stretto (back<lay, spread sano)', () => {
        const book = tradeableSelection(st('OPEN', { 1: { back: [[3.5, 100]], lay: [[3.55, 100]] } }), 1);
        expect(book).toEqual({ bestBack: 3.5, bestLay: 3.55 });
    });
    it('NO: mercato SOSPESO', () => {
        expect(tradeableSelection(st('SUSPENDED', { 1: { back: [[3.5, 100]], lay: [[3.55, 100]] } }), 1)).toBeNull();
    });
    it('NO: lato lay assente (book a un lato → niente controparte per uscire)', () => {
        expect(tradeableSelection(st('OPEN', { 1: { back: [[3.5, 100]], lay: [] } }), 1)).toBeNull();
    });
    it('NO: livelli a size 0 (quota fantasma senza denaro)', () => {
        expect(tradeableSelection(st('OPEN', { 1: { back: [[3.5, 0]], lay: [[3.55, 0]] } }), 1)).toBeNull();
    });
    it('NO: spread di probabilità troppo largo (back 5 / lay 1000 = quota fantasma)', () => {
        expect(tradeableSelection(st('OPEN', { 1: { back: [[5, 50]], lay: [[1000, 50]] } }), 1)).toBeNull();
    });
});

describe('isExecutableNow — gate centrale', () => {
    it('OK quando mercato OPEN e ogni gamba ha controparte (matched>0)', () => {
        const s = snap({ m1: st('OPEN', {}) });
        expect(isExecutableNow(s, opp())).toBe(true);
    });
    it('SCARTA se una gamba ha matchedStake 0 ("abbinato £0")', () => {
        const s = snap({ m1: st('OPEN', {}) });
        const o = opp({ legs: [leg(), leg({ side: 'lay', price: 1.01, matchedStake: 0 })] });
        expect(isExecutableNow(s, o)).toBe(false);
    });
    it('SCARTA se il mercato è SOSPESO', () => {
        const s = snap({ m1: st('SUSPENDED', {}) });
        expect(isExecutableNow(s, opp())).toBe(false);
    });
    it('SCARTA se il mercato della gamba non esiste nello snapshot', () => {
        const s = snap({});
        expect(isExecutableNow(s, opp())).toBe(false);
    });
});

describe('runDetectors applica il gate realtà', () => {
    it('scarta una direzionale su mercato SOSPESO', () => {
        const s = snap({ m1: st('SUSPENDED', {}) });
        const res = runDetectors(s, [() => [opp()]], DEFAULT_OPP_CONFIG);
        expect(res).toHaveLength(0);
    });
    it('scarta una opp con gamba senza controparte (matched 0)', () => {
        const s = snap({ m1: st('OPEN', {}) });
        const o = opp({ legs: [leg({ matchedStake: 0 })] });
        const res = runDetectors(s, [() => [o]], DEFAULT_OPP_CONFIG);
        expect(res).toHaveLength(0);
    });
});

describe('entryLegs', () => {
    it('arb → tutte le gambe; direzionale → solo la prima', () => {
        const legs = [leg({ selectionId: 1 }), leg({ selectionId: 2 })];
        expect(entryLegs(opp({ tier: 'arb', legs }))).toHaveLength(2);
        expect(entryLegs(opp({ tier: 'directional', legs }))).toHaveLength(1);
    });
    it('ltd_insurance / lay_field_cs → tutte le gambe (struttura simultanea)', () => {
        const legs = [leg({ selectionId: 1 }), leg({ selectionId: 2 })];
        expect(entryLegs(opp({ tier: 'low', type: 'ltd_insurance', legs }))).toHaveLength(2);
        expect(entryLegs(opp({ tier: 'low', type: 'lay_field_cs', legs }))).toHaveLength(2);
    });
});

// ---- riproduzione del BUG segnalato: book degenere senza controparte di lay ----
describe('REGRESSIONE bug "+375% abbinato £0"', () => {
    const moLite = { market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'Match Odds',
        selections: [{ selection_id: 1, name: 'Home', sort_priority: 1 },
                     { selection_id: 2, name: 'Away', sort_priority: 2 },
                     { selection_id: 3, name: 'The Draw', sort_priority: 3 }] };

    it('back-to-lay momentum NON scatta su una favorita con book degenere (back 5, lay assente)', () => {
        // quota crollata 85→5 nello storico, ma a fine gara il book non ha lato lay
        // reale → nessuna controparte per uscire → opportunità inesistente.
        const prev = snap({ m1: st('OPEN', { 1: { back: [[85, 50]], lay: [] } }) }, { markets: [moLite] });
        const cur = snap({ m1: st('OPEN', { 1: { back: [[5, 50]], lay: [] } }) }, { markets: [moLite] });
        const res = backToLay([prev])(cur, DEFAULT_OPP_CONFIG);
        expect(res.filter((o) => o.type === 'back_to_lay')).toHaveLength(0);
    });

    it('back-to-lay momentum NON scatta con spread fantasma (back 5 / lay 1000)', () => {
        const prev = snap({ m1: st('OPEN', { 1: { back: [[85, 50]], lay: [[1000, 50]] } }) }, { markets: [moLite] });
        const cur = snap({ m1: st('OPEN', { 1: { back: [[5, 50]], lay: [[1000, 50]] } }) }, { markets: [moLite] });
        const res = backToLay([prev])(cur, DEFAULT_OPP_CONFIG);
        expect(res.filter((o) => o.type === 'back_to_lay')).toHaveLength(0);
    });
});
