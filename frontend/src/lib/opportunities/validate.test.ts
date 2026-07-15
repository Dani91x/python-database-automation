import { describe, it, expect } from 'vitest';
import type { ReplayData, Frame, Ladder, Market } from '@/lib/live';
import type { OppConfig } from './types';
import { validateReplay, harnessDetectors } from './validate';

const CFG: OppConfig = { stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 };

// ts a passo 10s da 2026-01-01T00:00:00Z.
const T = (s: number) => new Date(Date.UTC(2026, 0, 1, 0, 0, s)).toISOString();

type Lvl = [number, number];
function lad(back: Lvl[], lay: Lvl[]): Ladder['x'] {
    return { back, lay, ltp: back[0]?.[0] ?? null, tv: 0 };
}

// Mercato MATCH_ODDS: Home(1) / Away(2) / Draw(3).
const MO_MARKET: Market = {
    market_id: 'm1', market_type: 'MATCH_ODDS', market_name: 'Match Odds', sort_priority: 1,
    selections: [
        { selection_id: 1, name: 'Home', sort_priority: 1 },
        { selection_id: 2, name: 'Away', sort_priority: 2 },
        { selection_id: 3, name: 'The Draw', sort_priority: 3 },
    ],
};

// frame al tempo `sec` con Home (back/lay variabili) + Away/Draw fissi.
function frame(sec: number, homeBack: Lvl[], homeLay: Lvl[]): Frame {
    const ladder: Ladder = {
        '1': lad(homeBack, homeLay),
        '2': lad([[2.0, 500]], [[2.1, 500]]), // Away: spread largo, sizes uguali → nessun segnale
        '3': lad([[3.0, 500]], [[3.1, 500]]), // Draw: I=0 → nessun segnale
    };
    return { market_id: 'm1', ts: T(sec), minute: 10, inplay: true, status: 'OPEN', ladder };
}

// Replay: Home book INCROCIATO (back 3.6 > lay 3.4) ai bucket 0,1,2 → arbitraggio
// back_to_lay; al bucket 3 il book si normalizza (lay 3.7) → niente arb e niente
// decay (back resta 3.6) → nessuna opportunità.
const REPLAY: ReplayData = {
    event: {
        event_id: 'e1', fixture_id: null, league_name: 'Test League',
        home_name: 'Casa', away_name: 'Ospiti', open_date: T(0), status: 'OPEN',
    },
    markets: [MO_MARKET],
    frames: [
        frame(0, [[3.6, 500]], [[3.4, 500]]),   // bucket 0: crossed
        frame(10, [[3.6, 500]], [[3.4, 500]]),  // bucket 1: crossed
        frame(20, [[3.6, 500]], [[3.4, 500]]),  // bucket 2: crossed
        frame(30, [[3.6, 500]], [[3.7, 500]]),  // bucket 3: normale, nessun decay
    ],
    score_timeline: [
        { ts: T(0), minute: 10, score_home: 0, score_away: 0, event_type: null, source: 'x' },
    ],
};

describe('validateReplay', () => {
    const report = validateReplay(REPLAY, CFG, 10000);

    it('builds one snapshot per 10s bucket', () => {
        expect(report.totalSnapshots).toBe(4);
        expect(report.bucketMs).toBe(10000);
        expect(report.delaySec).toBe(6);
    });

    it('conta UN episodio per l\'arb che persiste sui bucket 0-2 (dedup per firma)', () => {
        // stessa firma per 3 snapshot consecutivi = 1 opportunità reale, non 3.
        expect(report.totalOpportunities).toBe(1);
        expect(report.byTier.arb.total).toBe(1);
        expect(report.byType['back_to_lay_arb'].total).toBe(1);
        expect(report.byTier.low.total).toBe(0);
        expect(report.byTier.directional.total).toBe(0);
    });

    it('l\'episodio è eseguibile: al look-ahead (+6s, frame NUOVO) il book regge', () => {
        expect(report.executable).toBe(1);
        expect(report.theoretical).toBe(0);
        expect(report.byTier.arb.executable).toBe(1);
        expect(report.arb.total).toBe(1);
        expect(report.arb.executable).toBe(1);
        expect(report.arb.executableByPhase['1T']).toBe(1);
    });

    it('per-record executability flags are correct', () => {
        const r0 = report.records.find((r) => r.snapshotIndex === 0)!;
        expect(r0.exec.fillable).toBe(true);
        expect(r0.exec.checkedAhead).toBe(true); // il frame @10s è un'osservazione NUOVA
        expect(r0.exec.persisted).toBe(true);
        expect(r0.exec.executable).toBe(true);
    });

    it('profit distribution: single full-lock arb ≈ £5.588235', () => {
        expect(report.profit.count).toBe(1);
        expect(report.profit.min).toBeCloseTo(5.588235, 5);
        expect(report.profit.median).toBeCloseTo(5.588235, 5);
        expect(report.profit.max).toBeCloseTo(5.588235, 5);
        expect(report.profitPct.median).toBeCloseTo(5.588235, 5);
        expect(report.arb.avgProfitPct).toBeCloseTo(5.588235, 5);
    });

    it('aggregates by phase', () => {
        expect(report.byPhase['1T'].total).toBe(1);
        expect(report.byPhase['1T'].executable).toBe(1);
    });
});

describe('validateReplay — episodio NON persistente (il book non regge il delay)', () => {
    // crossed SOLO al bucket 2: al look-ahead (+6s → frame @30s, nuovo) il lay
    // è tornato normale → l'arb è teorico, non eseguibile.
    const REPLAY2: ReplayData = {
        ...REPLAY,
        frames: [
            frame(0, [[3.6, 500]], [[3.7, 500]]),
            frame(10, [[3.6, 500]], [[3.7, 500]]),
            frame(20, [[3.6, 500]], [[3.4, 500]]),  // crossed (episodio)
            frame(30, [[3.6, 500]], [[3.7, 500]]),  // normalizzato
        ],
    };
    const report = validateReplay(REPLAY2, CFG, 10000);

    it('1 episodio, teorico (persisted=false su osservazione nuova)', () => {
        expect(report.totalOpportunities).toBe(1);
        expect(report.executable).toBe(0);
        expect(report.theoretical).toBe(1);
        const r2 = report.records.find((r) => r.snapshotIndex === 2)!;
        expect(r2.exec.fillable).toBe(true);
        expect(r2.exec.checkedAhead).toBe(true);
        expect(r2.exec.persisted).toBe(false);
        expect(r2.exec.executable).toBe(false);
    });
});

describe('validateReplay — riemersione dopo un gap = NUOVO episodio', () => {
    // crossed @0, normale @10, crossed @20: la firma sparisce e ricompare → 2 episodi.
    const REPLAY3: ReplayData = {
        ...REPLAY,
        frames: [
            frame(0, [[3.6, 500]], [[3.4, 500]]),   // episodio 1
            frame(10, [[3.6, 500]], [[3.7, 500]]),  // normalizzato
            frame(20, [[3.6, 500]], [[3.4, 500]]),  // episodio 2
            frame(30, [[3.6, 500]], [[3.7, 500]]),  // normalizzato
        ],
    };
    const report = validateReplay(REPLAY3, CFG, 10000);

    it('conta 2 episodi distinti', () => {
        expect(report.totalOpportunities).toBe(2);
        expect(report.byType['back_to_lay_arb'].total).toBe(2);
    });
});

describe('validateReplay — empty replay', () => {
    it('returns a zeroed report', () => {
        const empty: ReplayData = { ...REPLAY, frames: [], score_timeline: [] };
        const report = validateReplay(empty, CFG, 10000);
        expect(report.totalSnapshots).toBe(0);
        expect(report.totalOpportunities).toBe(0);
        expect(report.executable).toBe(0);
        expect(report.theoretical).toBe(0);
        expect(report.profit).toEqual({ count: 0, min: 0, median: 0, max: 0 });
    });
});

describe('harnessDetectors', () => {
    it('includes tier0 + tier1 + stateless tier2 detectors', () => {
        const dets = harnessDetectors([]);
        // 5 tier0 + 5 tier1 + 3 tier2 = 13
        expect(dets.length).toBe(13);
    });
});
