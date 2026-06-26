import { describe, it, expect } from 'vitest';
import type { Leg, MarketLite, MarketState, OppConfig, SelLite, Snapshot } from './types';
import {
    matchOddsVsDoubleChance,
    correctScoreVsBTTS,
    correctScoreVsOverUnder,
    overUnderMonotonicity,
    matchOddsBookCheck,
    // helper esposti
    dutchStakes,
    syntheticBackOdds,
    hedgeLayStake,
    scenarioProfit,
    guaranteedProfit,
    parseScore,
    doubleChanceKind,
    phaseFromMinute,
    type Scenario,
} from './tier0_arb';

// ----------------------------------------------------------------- builders
const CFG: OppConfig = { stake: 100, minProfitPct: 0.5, commission: 0.05, delaySec: 6 };

type Level = [number, number];
function entry(back: Level[], lay: Level[] = []) {
    return { back, lay, ltp: null, tv: null };
}
function sel(id: number, name: string | null, sp?: number): SelLite {
    return { selection_id: id, name, sort_priority: sp };
}
function market(market_id: string, market_type: string, selections: SelLite[]): MarketLite {
    return { market_id, market_type, market_name: market_type, selections };
}
function state(market_id: string, market_type: string, ladder: Record<string, ReturnType<typeof entry>>): MarketState {
    return { market_id, market_type, status: 'OPEN', ladder: ladder as MarketState['ladder'] };
}
function snapshot(over: Partial<Snapshot>): Snapshot {
    return {
        ts: '2026-01-01T00:00:00.000Z',
        minute: 10,
        scoreHome: 0,
        scoreAway: 0,
        markets: [],
        state: {},
        ...over,
    };
}

// ===========================================================================
// MATH HELPERS — valori calcolati a mano
// ===========================================================================
describe('dutchStakes — ∝ 1/quota, return lordo uguale', () => {
    it('[2,3] total 120 → [72,48] (entrambi rendono 144)', () => {
        const s = dutchStakes([2, 3], 120);
        expect(s[0]).toBeCloseTo(72, 6);
        expect(s[1]).toBeCloseTo(48, 6);
        expect(s[0] * 2).toBeCloseTo(s[1] * 3, 6); // return uguale
    });
    it('[2,3] total 100 → [60,40]', () => {
        const s = dutchStakes([2, 3], 100);
        expect(s[0]).toBeCloseTo(60, 6);
        expect(s[1]).toBeCloseTo(40, 6);
    });
});

describe('syntheticBackOdds — 1/Σ(1/o)', () => {
    it('[5,8,10,20] → 2.105263 (Σ inv = 0.475)', () => {
        expect(syntheticBackOdds([5, 8, 10, 20])).toBeCloseTo(2.1052631579, 8);
    });
    it('[4,4] → 2.0', () => {
        expect(syntheticBackOdds([4, 4])).toBeCloseTo(2.0, 8);
    });
});

describe('hedgeLayStake — pareggia i due gruppi di scenari', () => {
    it('back 2.0 / lay 1.9 / stake 100 / c 5% → 105.405405', () => {
        expect(hedgeLayStake(2.0, 1.9, 100, 0.05)).toBeCloseTo(105.405405, 6);
    });
    it('back 1.10 / lay 1.05 / stake 100 / c 5% → 109.5', () => {
        expect(hedgeLayStake(1.1, 1.05, 100, 0.05)).toBeCloseTo(109.5, 6);
    });
});

describe('scenarioProfit — commissione sul NETTO di mercato', () => {
    const legs: Leg[] = [
        { marketId: 'm', marketName: 'm', selectionId: 1, selectionName: 'A', side: 'back', price: 4, stake: 10, matchedStake: 10 },
        { marketId: 'm', marketName: 'm', selectionId: 2, selectionName: 'B', side: 'back', price: 4, stake: 10, matchedStake: 10 },
    ];
    it('stesso mercato: netto = +30-10 = 20 → 20*0.95 = 19', () => {
        expect(scenarioProfit(legs, new Set([1]), 0.05)).toBeCloseTo(19, 6);
    });
    it('legge la commissione per-mercato separatamente', () => {
        const cross: Leg[] = [
            { marketId: 'm1', marketName: 'm1', selectionId: 1, selectionName: 'A', side: 'back', price: 4, stake: 40, matchedStake: 40 },
            { marketId: 'm2', marketName: 'm2', selectionId: 2, selectionName: 'B', side: 'back', price: 2, stake: 60, matchedStake: 60 },
        ];
        // winner=1: m1 net +120→114 ; m2 net -60 → 54
        expect(scenarioProfit(cross, new Set([1]), 0.05)).toBeCloseTo(54, 6);
    });
});

describe('guaranteedProfit — minimo sugli scenari', () => {
    it('prende il peggiore', () => {
        const legs: Leg[] = [
            { marketId: 'm', marketName: 'm', selectionId: 1, selectionName: 'A', side: 'back', price: 4, stake: 10, matchedStake: 10 },
            { marketId: 'm', marketName: 'm', selectionId: 2, selectionName: 'B', side: 'back', price: 4, stake: 10, matchedStake: 10 },
        ];
        const sc: Scenario[] = [
            { key: 'a', winners: new Set([1]) }, // 19
            { key: 'b', winners: new Set([2]) }, // 19
            { key: 'none', winners: new Set([9]) }, // entrambe perdono: -20
        ];
        expect(guaranteedProfit(legs, sc, 0.05)).toBeCloseTo(-20, 6);
    });
});

describe('parseScore', () => {
    it('"2-1" → [2,1]; "2 - 1" → [2,1]', () => {
        expect(parseScore('2-1')).toEqual([2, 1]);
        expect(parseScore('2 - 1')).toEqual([2, 1]);
    });
    it('non-punteggio → null', () => {
        expect(parseScore('Any Other Home')).toBeNull();
        expect(parseScore(null)).toBeNull();
    });
});

describe('doubleChanceKind', () => {
    it('canonici 1X/X2/12', () => {
        expect(doubleChanceKind('1X')).toBe('1X');
        expect(doubleChanceKind('X2')).toBe('X2');
        expect(doubleChanceKind('12')).toBe('12');
    });
    it('descrittivi', () => {
        expect(doubleChanceKind('Home or Draw')).toBe('1X');
        expect(doubleChanceKind('Draw or Away')).toBe('X2');
        expect(doubleChanceKind('Home or Away')).toBe('12');
    });
    it('ignoto → null', () => {
        expect(doubleChanceKind('foo')).toBeNull();
    });
});

describe('phaseFromMinute', () => {
    it('pre/1T/2T/late', () => {
        expect(phaseFromMinute(null)).toBe('pre');
        expect(phaseFromMinute(0)).toBe('pre');
        expect(phaseFromMinute(30)).toBe('1T');
        expect(phaseFromMinute(60)).toBe('2T');
        expect(phaseFromMinute(88)).toBe('late');
    });
});

// ===========================================================================
// DETECTOR 1 — Match Odds × Doppia Chance
// ===========================================================================
describe('matchOddsVsDoubleChance', () => {
    // MO: home id1 @3.0 ; DC: X2 id12 @2.0 → coppia X2(draw/away)+home(home).
    const moSels = [sel(1, 'Team A', 1), sel(2, 'Team B', 2), sel(3, 'The Draw', 3)];
    const dcSels = [sel(11, '1X'), sel(12, 'X2'), sel(13, '12')];

    function buildSnap(opts: { oX2?: number; oHome?: number }): Snapshot {
        const { oX2 = 2.0, oHome = 3.0 } = opts;
        return snapshot({
            markets: [market('mo', 'MATCH_ODDS', moSels), market('dc', 'DOUBLE_CHANCE', dcSels)],
            state: {
                mo: state('mo', 'MATCH_ODDS', { '1': entry([[oHome, 1000]]) }), // away/draw senza back → altre coppie skip
                dc: state('dc', 'DOUBLE_CHANCE', { '12': entry([[oX2, 1000]]) }), // solo X2 quotata
            },
        });
    }

    it('TRUE ARB: X2@2.0 + Home@3.0 → profitto garantito £16', () => {
        const res = matchOddsVsDoubleChance(buildSnap({ oX2: 2.0, oHome: 3.0 }), CFG);
        expect(res.length).toBe(1);
        const o = res[0];
        expect(o.tier).toBe('arb');
        expect(o.type).toBe('mo_vs_dc');
        expect(o.legs.length).toBe(2);
        expect(o.profit).toBeCloseTo(16, 6);
        expect(o.profitPct).toBeCloseTo(16, 6); // 16/100
        expect(o.confidence).toBeCloseTo(1, 6);
        // stake dutch: X2=60, home=40
        const x2 = o.legs.find((l) => l.selectionId === 12)!;
        const home = o.legs.find((l) => l.selectionId === 1)!;
        expect(x2.matchedStake).toBeCloseTo(60, 6);
        expect(home.matchedStake).toBeCloseTo(40, 6);
    });

    it('NO ARB: 1/o somma ≥ 1 → niente', () => {
        // X2@1.6 + Home@2.5 : 0.625+0.4 = 1.025 ≥ 1
        expect(matchOddsVsDoubleChance(buildSnap({ oX2: 1.6, oHome: 2.5 }), CFG)).toEqual([]);
    });

    it('COMMISSION BOUNDARY: Σ1/o<1 ma negativo dopo commissione → niente', () => {
        // X2@1.6 + Home@2.7 : 0.625+0.37037 = 0.99537 < 1, ma il 5% lo azzera.
        const res = matchOddsVsDoubleChance(buildSnap({ oX2: 1.6, oHome: 2.7 }), CFG);
        expect(res).toEqual([]);
    });

    it('EDGE: prezzi mancanti → niente', () => {
        const snap = snapshot({
            markets: [market('mo', 'MATCH_ODDS', moSels), market('dc', 'DOUBLE_CHANCE', dcSels)],
            state: {
                mo: state('mo', 'MATCH_ODDS', {}),
                dc: state('dc', 'DOUBLE_CHANCE', {}),
            },
        });
        expect(matchOddsVsDoubleChance(snap, CFG)).toEqual([]);
    });

    it('EDGE: quota ≤ 1 → niente', () => {
        expect(matchOddsVsDoubleChance(buildSnap({ oX2: 1.0, oHome: 3.0 }), CFG)).toEqual([]);
    });

    it('EDGE: manca il mercato DC → niente', () => {
        const snap = snapshot({
            markets: [market('mo', 'MATCH_ODDS', moSels)],
            state: { mo: state('mo', 'MATCH_ODDS', { '1': entry([[3.0, 1000]]) }) },
        });
        expect(matchOddsVsDoubleChance(snap, CFG)).toEqual([]);
    });
});

// ===========================================================================
// DETECTOR 5 — Match Odds book check (overround residuo)
// ===========================================================================
describe('matchOddsBookCheck', () => {
    const moSels = [sel(1, 'Team A', 1), sel(2, 'Team B', 2), sel(3, 'The Draw', 3)];

    function buildSnap(oH: number, oD: number, oA: number, size = 1000): Snapshot {
        return snapshot({
            markets: [market('mo', 'MATCH_ODDS', moSels)],
            state: {
                mo: state('mo', 'MATCH_ODDS', {
                    '1': entry([[oH, size]]),
                    '3': entry([[oD, size]]),
                    '2': entry([[oA, size]]),
                }),
            },
        });
    }

    it('TRUE ARB: 4/4/4 → Σ1/o=0.75; profitto £31.67 (commissione sul netto)', () => {
        const res = matchOddsBookCheck(buildSnap(4, 4, 4), CFG);
        expect(res.length).toBe(1);
        const o = res[0];
        expect(o.legs.length).toBe(3);
        // netto mercato per esito = 100 - 66.667 = 33.333 → *0.95 = 31.6667
        expect(o.profit).toBeCloseTo(31.6667, 3);
        expect(o.profitPct).toBeCloseTo(31.6667, 3);
    });

    it('NO ARB: 3/3.5/2.5 → Σ1/o>1 → niente', () => {
        expect(matchOddsBookCheck(buildSnap(3, 3.5, 2.5), CFG)).toEqual([]);
    });

    it('THIN LIQUIDITY: size 10 cappa matchedStake; profitto sul matched = £9.50', () => {
        const res = matchOddsBookCheck(buildSnap(4, 4, 4, 10), CFG);
        expect(res.length).toBe(1);
        const o = res[0];
        // ogni gamba: desired 33.333, matched 10
        for (const l of o.legs) expect(l.matchedStake).toBeCloseTo(10, 6);
        // netto = 30 - 20 = 10 → *0.95 = 9.5
        expect(o.profit).toBeCloseTo(9.5, 6);
        expect(o.confidence).toBeCloseTo(10 / (100 / 3), 4); // ~0.3
    });

    it('EDGE: una quota mancante → niente', () => {
        const snap = snapshot({
            markets: [market('mo', 'MATCH_ODDS', moSels)],
            state: { mo: state('mo', 'MATCH_ODDS', { '1': entry([[4, 1000]]), '3': entry([[4, 1000]]) }) },
        });
        expect(matchOddsBookCheck(snap, CFG)).toEqual([]);
    });
});

// ===========================================================================
// DETECTOR 2 — Correct Score × BTTS
// ===========================================================================
describe('correctScoreVsBTTS', () => {
    // Gruppo "entrambe segnano" (Y): 1-1@5, 2-1@8, 1-2@10, 2-2@20 → sintetica 2.105.
    // N: 0-0, 1-0, 0-1 (quotati ma usati solo come scenari per il lato Yes).
    const csSels = [
        sel(100, '0-0'), sel(101, '1-1'), sel(102, '2-1'), sel(103, '1-2'),
        sel(104, '2-2'), sel(105, '1-0'), sel(106, '0-1'),
    ];
    const btSels = [sel(201, 'Yes'), sel(202, 'No')];

    function buildSnap(layYes: number): Snapshot {
        return snapshot({
            markets: [market('cs', 'CORRECT_SCORE', csSels), market('bt', 'BOTH_TEAMS_TO_SCORE', btSels)],
            state: {
                cs: state('cs', 'CORRECT_SCORE', {
                    '100': entry([[6, 1000]]), '101': entry([[5, 1000]]), '102': entry([[8, 1000]]),
                    '103': entry([[10, 1000]]), '104': entry([[20, 1000]]), '105': entry([[4, 1000]]),
                    '106': entry([[6, 1000]]),
                }),
                // BTTS: solo Yes ha liquidità di LAY → lato No salta.
                bt: state('bt', 'BOTH_TEAMS_TO_SCORE', {
                    '201': entry([], [[layYes, 1000]]),
                    '202': entry([], []),
                }),
            },
        });
    }

    it('TRUE ARB: back CS-Yes (sint. 2.105) + lay BTTS Yes @1.9 → £5.27', () => {
        const res = correctScoreVsBTTS(buildSnap(1.9), CFG);
        expect(res.length).toBe(1);
        const o = res[0];
        expect(o.type).toBe('cs_vs_btts');
        expect(o.legs.length).toBe(5); // 4 CS back + 1 BTTS lay
        expect(o.profit).toBeCloseTo(5.2703, 3);
        expect(o.profitPct).toBeGreaterThan(CFG.minProfitPct);
        const lay = o.legs.find((l) => l.side === 'lay')!;
        expect(lay.selectionId).toBe(201);
        expect(lay.matchedStake).toBeCloseTo(110.8108, 3);
    });

    it('NO ARB: lay Yes @2.5 ≥ sintetica 2.105 → niente', () => {
        expect(correctScoreVsBTTS(buildSnap(2.5), CFG)).toEqual([]);
    });

    it('EDGE: griglia CS incompleta (selezione non-punteggio) → niente', () => {
        const csBad = [...csSels, sel(199, 'Any Other')];
        const snap = snapshot({
            markets: [market('cs', 'CORRECT_SCORE', csBad), market('bt', 'BOTH_TEAMS_TO_SCORE', btSels)],
            state: {
                cs: state('cs', 'CORRECT_SCORE', {
                    '101': entry([[5, 1000]]), '102': entry([[8, 1000]]),
                    '103': entry([[10, 1000]]), '104': entry([[20, 1000]]),
                }),
                bt: state('bt', 'BOTH_TEAMS_TO_SCORE', { '201': entry([], [[1.9, 1000]]) }),
            },
        });
        expect(correctScoreVsBTTS(snap, CFG)).toEqual([]);
    });

    it('THIN LIQUIDITY: lay insufficiente → hedge non sicuro, niente (money-critical)', () => {
        // desired lay ~110.8 ma disponibili solo 20: nello scenario "non entrambe
        // segnano" le vincite di lay non coprono più i back CS → profitto garantito
        // negativo → l'arb (non più risk-free) NON viene emesso.
        const snap = buildSnap(1.9);
        (snap.state.bt.ladder as Record<string, ReturnType<typeof entry>>)['201'] = entry([], [[1.9, 20]]);
        expect(correctScoreVsBTTS(snap, CFG)).toEqual([]);
    });
});

// ===========================================================================
// DETECTOR 3 — Correct Score × Over/Under
// ===========================================================================
describe('correctScoreVsOverUnder', () => {
    // Over 1.5: gruppo Over = 1-1@4, 2-0@4 (sintetica 2.0). Under = 0-0,1-0,0-1.
    const csSels = [
        sel(300, '0-0'), sel(301, '1-0'), sel(302, '0-1'), sel(303, '1-1'), sel(304, '2-0'),
    ];
    const ouSels = [sel(401, 'Over 1.5 Goals'), sel(402, 'Under 1.5 Goals')];

    function buildSnap(layOver: number): Snapshot {
        return snapshot({
            markets: [market('cs', 'CORRECT_SCORE', csSels), market('ou15', 'OVER_UNDER_15', ouSels)],
            state: {
                cs: state('cs', 'CORRECT_SCORE', {
                    '300': entry([[6, 1000]]), '301': entry([[4, 1000]]), '302': entry([[6, 1000]]),
                    '303': entry([[4, 1000]]), '304': entry([[4, 1000]]),
                }),
                ou15: state('ou15', 'OVER_UNDER_15', {
                    '401': entry([], [[layOver, 1000]]), // solo Over layabile → lato Under salta
                    '402': entry([], []),
                }),
            },
        });
    }

    it('TRUE ARB: back CS-Over (sint. 2.0) + lay Over1.5 @1.8 → £5.86', () => {
        const res = correctScoreVsOverUnder(buildSnap(1.8), CFG);
        expect(res.length).toBe(1);
        const o = res[0];
        expect(o.type).toBe('cs_vs_ou');
        expect(o.legs.length).toBe(3); // 2 CS back + 1 OU lay
        expect(o.profit).toBeCloseTo(5.8571, 3);
        const lay = o.legs.find((l) => l.side === 'lay')!;
        expect(lay.matchedStake).toBeCloseTo(111.4286, 3);
    });

    it('NO ARB: lay Over @2.5 ≥ sintetica 2.0 → niente', () => {
        expect(correctScoreVsOverUnder(buildSnap(2.5), CFG)).toEqual([]);
    });
});

// ===========================================================================
// DETECTOR 4 — Monotonicità Over/Under
// ===========================================================================
describe('overUnderMonotonicity', () => {
    const ou05 = [sel(501, 'Over 0.5 Goals'), sel(502, 'Under 0.5 Goals')];
    const ou15 = [sel(511, 'Over 1.5 Goals'), sel(512, 'Under 1.5 Goals')];

    function buildSnap(backOver05: number, layOver15: number): Snapshot {
        return snapshot({
            markets: [market('ou05', 'OVER_UNDER_05', ou05), market('ou15', 'OVER_UNDER_15', ou15)],
            state: {
                ou05: state('ou05', 'OVER_UNDER_05', { '501': entry([[backOver05, 1000]]), '502': entry([]) }),
                ou15: state('ou15', 'OVER_UNDER_15', { '511': entry([], [[layOver15, 1000]]), '512': entry([], []) }),
            },
        });
    }

    it('TRUE ARB: Over0.5@1.10 (back) > Over1.5@1.05 (lay) → £4.025', () => {
        const res = overUnderMonotonicity(buildSnap(1.1, 1.05), CFG);
        expect(res.length).toBe(1);
        const o = res[0];
        expect(o.type).toBe('ou_monotonicity');
        expect(o.legs.length).toBe(2);
        expect(o.profit).toBeCloseTo(4.025, 4);
        const back = o.legs.find((l) => l.side === 'back')!;
        const lay = o.legs.find((l) => l.side === 'lay')!;
        expect(back.selectionId).toBe(501);
        expect(lay.selectionId).toBe(511);
        expect(lay.matchedStake).toBeCloseTo(109.5, 4);
    });

    it('NO VIOLATION: Over0.5@1.05 ≤ Over1.5@1.10 → niente', () => {
        expect(overUnderMonotonicity(buildSnap(1.05, 1.1), CFG)).toEqual([]);
    });

    it('EDGE: manca il prezzo di lay sulla linea alta → niente', () => {
        const snap = snapshot({
            markets: [market('ou05', 'OVER_UNDER_05', ou05), market('ou15', 'OVER_UNDER_15', ou15)],
            state: {
                ou05: state('ou05', 'OVER_UNDER_05', { '501': entry([[1.1, 1000]]) }),
                ou15: state('ou15', 'OVER_UNDER_15', { '511': entry([], []) }),
            },
        });
        expect(overUnderMonotonicity(snap, CFG)).toEqual([]);
    });
});
