// ============================================================================
// delayMercato.tennisReplay.test.ts — 07/10 (Replay Tennis): il bet-delay in
// gioco del MERCATO (betDelay registrato: 3 s sul Match Odds tennis) al posto dei
// 5 s fissi del calcio, nel ladder training e nel backtest. Senza il parametro
// tutto resta com'era (calcio invariato).
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { BookSnapshot } from './matching';
import { createTrainingApi } from './trainingLadder';
import { runLadderBacktest, type LadderBacktestParams } from './ladderBacktest';

const T0 = 1_000_000;

const libro = (ts: number): BookSnapshot => ({
    ts, back: [[2.0, 100], [1.99, 100]], lay: [[2.02, 100], [2.04, 100]],
    ltp: 2.0, tv: 500, trd: [[2.0, 500]], status: 'OPEN',
});

const piazza = { action: 'place' as const, mode: 'paper' as const, market_id: '1.5', selection_id: 11,
    handicap: 0, side: 'back' as const, order_type: 'LIMIT' as const, price: 2.0, size: 10, persistence: 'LAPSE' as const };

describe('ladder training: bet-delay del mercato', () => {
    it('col delay del mercato (3 s) l\'ordine in gioco aspetta 3 s, non 5', async () => {
        const ora = { t: T0 };
        const libri = [libro(T0), libro(T0 + 3_500), libro(T0 + 6_000)];
        const api = createTrainingApi({
            eventId: 'ev', getSnaps: () => libri, getNow: () => ora.t, isInplayAt: () => true,
            delayMsAt: () => 3_000,
        });
        const r = await api.send(piazza);
        expect(r.detail).toBe('bet-delay 3s applicato (in-play)');
        ora.t = T0 + 3_500;
        expect(api.resolved()[0].res.matched).toBeCloseTo(10, 6);
    });

    it('senza delayMsAt: i 5 s di sempre (calcio invariato)', async () => {
        const ora = { t: T0 };
        const libri = [libro(T0), libro(T0 + 3_500), libro(T0 + 6_000)];
        const api = createTrainingApi({ eventId: 'ev', getSnaps: () => libri, getNow: () => ora.t, isInplayAt: () => true });
        const r = await api.send(piazza);
        expect(r.detail).toBe('bet-delay 5s applicato (in-play)');
        ora.t = T0 + 3_500;
        expect(api.resolved()[0].res.matched).toBe(0);
    });
});

describe('backtest: bet-delay del mercato', () => {
    const P: LadderBacktestParams = {
        side: 'back', entryOffsetTicks: 1, tpTicks: 1, stopTicks: 2,
        stake: 10, entryTtlSec: 60, maxHoldSec: 120, everySec: 600, phase: 'inplay',
    };
    const s0: BookSnapshot = { ts: T0, back: [[2.0, 100], [1.99, 100]], lay: [[2.06, 100]], ltp: 2.0, tv: 500, trd: [[2.02, 0]], status: 'OPEN' };
    // volume attraverso 2.02 a t+2 s: dentro i 5 s del calcio, fuori da 1 s
    const libri: BookSnapshot[] = [
        s0,
        { ts: T0 + 2_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.02, tv: 550, trd: [[2.02, 50]], status: 'OPEN' },
        { ts: T0 + 40_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.0, tv: 555, trd: [[2.02, 50]], status: 'OPEN' },
        { ts: T0 + 90_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.0, tv: 555, trd: [[2.02, 50]], status: 'OPEN' },
    ];
    it('delay di 1 s: il volume a +2 s riempie l\'entrata; coi 5 s di default no', () => {
        expect(runLadderBacktest(libri, P, () => true).trades).toHaveLength(0);
        expect(runLadderBacktest(libri, P, () => true, 1_000).trades).toHaveLength(1);
    });
});
