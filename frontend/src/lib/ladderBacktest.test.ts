import { describe, it, expect } from 'vitest';
import type { BookSnapshot } from './matching';
import { runLadderBacktest, type LadderBacktestParams } from './ladderBacktest';

const T0 = 1_000_000;

const P: LadderBacktestParams = {
    side: 'back', entryOffsetTicks: 1, tpTicks: 1, stopTicks: 2,
    stake: 10, entryTtlSec: 60, maxHoldSec: 120, everySec: 600, phase: 'both',
};

// s0: best back 2.0 → entrata back MAKER a 2.02 (tickUp 1). Baseline trd nota.
function s0(ts = T0): BookSnapshot {
    return {
        ts, back: [[2.0, 100], [1.99, 100]], lay: [[2.06, 100]],
        ltp: 2.0, tv: 500, trd: [[2.02, 0]], status: 'OPEN',
    };
}

describe('runLadderBacktest — round-trip TP (pre-match, NESSUN delay)', () => {
    it('entrata maker riempita dal volume tradato, TP greened → P&L flat a mano', () => {
        const snaps: BookSnapshot[] = [
            s0(),
            // t+10s: il mercato tratta €50 ATTRAVERSO 2.02 → fill maker 10@2.02;
            // il TP lay a 2.0 trova subito book.lay best 2.0 → taker 10.1@2.0
            { ts: T0 + 10_000, back: [[1.99, 100]], lay: [[2.0, 100]], ltp: 2.02, tv: 550, trd: [[2.02, 50]], status: 'OPEN' },
            { ts: T0 + 20_000, back: [[1.99, 100]], lay: [[2.0, 100]], ltp: 2.0, tv: 560, trd: [[2.02, 50]], status: 'OPEN' },
        ];
        const res = runLadderBacktest(snaps, P, () => false);
        expect(res.attempted).toBe(1);
        expect(res.trades).toHaveLength(1);
        const t = res.trades[0];
        expect(t.exit).toBe('tp');
        expect(t.entryPrice).toBe(2.02);
        expect(t.exitPrice).toBe(2.0);
        // a mano: back 10@2.02 (+10.2/−10) + lay 10.1@2.0 (−10.1/+10.1) → +0.1/+0.1
        expect(t.pnl).toBeCloseTo(0.1, 2);
        expect(t.incomplete).toBe(false);
        expect(res.totalPnl).toBeCloseTo(0.1, 2);
        expect(res.wins).toBe(1);
    });
});

describe('runLadderBacktest — STOP con flatten taker (slippage reale)', () => {
    it('lo stop scatta al tocco e chiude greened al book VISIBILE → perdita a mano', () => {
        const snaps: BookSnapshot[] = [
            s0(),
            // fill dell'entrata (trd attraverso 2.02); best lay ancora lontano dal TP
            { ts: T0 + 10_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.02, tv: 550, trd: [[2.02, 50]], status: 'OPEN' },
            // il prezzo SALE: best lay 2.06 = stop level (tickUp(2.02, 2)) → flatten
            { ts: T0 + 20_000, back: [[2.04, 100]], lay: [[2.06, 100]], ltp: 2.06, tv: 560, trd: [[2.02, 50]], status: 'OPEN' },
            { ts: T0 + 30_000, back: [[2.04, 100]], lay: [[2.06, 100]], ltp: 2.06, tv: 570, trd: [[2.02, 50]], status: 'OPEN' },
        ];
        const res = runLadderBacktest(snaps, P, () => false);
        expect(res.trades).toHaveLength(1);
        const t = res.trades[0];
        expect(t.exit).toBe('stop');
        // a mano: hedge lay h = 20.2/2.06 = 9.81 @2.06 → ifWin = 10.2 − 9.81·1.06 ≈ −0.19
        expect(t.pnl).toBeCloseTo(-0.19, 1);
        expect(t.incomplete).toBe(false);
        expect(res.losses).toBe(1);
    });

    it('book VUOTO al momento dello stop → trade resta APERTO e DICHIARATO (worst-case)', () => {
        const snaps: BookSnapshot[] = [
            s0(),
            { ts: T0 + 10_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.02, tv: 550, trd: [[2.02, 50]], status: 'OPEN' },
            // stop toccato ma NESSUNA liquidità lay per uscire
            { ts: T0 + 20_000, back: [], lay: [[2.06, 0.5]], ltp: 2.06, tv: 560, trd: [[2.02, 50]], status: 'OPEN' },
        ];
        const res = runLadderBacktest(snaps, P, () => false);
        expect(res.trades).toHaveLength(1);
        expect(res.trades[0].incomplete).toBe(true);           // dichiarato, mai nascosto
        expect(res.incomplete).toBe(1);
        // worst-case: min(ifWin, ifLose) con la posizione quasi aperta → ≈ −10 (lato lose)
        expect(res.trades[0].pnl).toBeLessThan(-5);
    });
});

describe('runLadderBacktest — onestà di esecuzione', () => {
    it('entrata mai abbinata (nessun volume attraverso il limite) → unfilled, zero trade', () => {
        const snaps: BookSnapshot[] = [
            s0(),
            { ts: T0 + 30_000, back: [[2.0, 100]], lay: [[2.06, 100]], ltp: 2.0, tv: 500, trd: [[2.02, 0]], status: 'OPEN' },
            { ts: T0 + 90_000, back: [[2.0, 100]], lay: [[2.06, 100]], ltp: 2.0, tv: 500, trd: [[2.02, 0]], status: 'OPEN' },
        ];
        const res = runLadderBacktest(snaps, P, () => false);
        expect(res.trades).toHaveLength(0);
        expect(res.unfilled).toBeGreaterThanOrEqual(1);
        expect(res.totalPnl).toBe(0);
    });

    it('IN-PLAY: il bet-delay ritarda l\'entrata (volume PRIMA del delay non riempie)', () => {
        const snaps: BookSnapshot[] = [
            s0(),
            // trd attraverso il limite a t+2s: PRIMA del delay 5s → NON deve riempire
            { ts: T0 + 2_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.02, tv: 550, trd: [[2.02, 50]], status: 'OPEN' },
            { ts: T0 + 40_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.0, tv: 555, trd: [[2.02, 50]], status: 'OPEN' },
            { ts: T0 + 90_000, back: [[1.99, 100]], lay: [[2.04, 100]], ltp: 2.0, tv: 555, trd: [[2.02, 50]], status: 'OPEN' },
        ];
        const res = runLadderBacktest(snaps, { ...P, phase: 'inplay' }, () => true);
        expect(res.trades).toHaveLength(0);   // il fill "facile" pre-delay NON esiste
        expect(res.unfilled).toBeGreaterThanOrEqual(1);
    });

    it('filtro FASE: phase=prematch con partita in-play → zero tentativi', () => {
        const snaps: BookSnapshot[] = [s0(), s0(T0 + 60_000)];
        const res = runLadderBacktest(snaps, { ...P, phase: 'prematch' }, () => true);
        expect(res.attempted).toBe(0);
    });

    it('mercato SOSPESO → nessuna entrata a quel giro', () => {
        const snaps: BookSnapshot[] = [
            { ...s0(), status: 'SUSPENDED' },
            { ...s0(T0 + 700_000), status: 'SUSPENDED' },
        ];
        const res = runLadderBacktest(snaps, P, () => false);
        expect(res.attempted).toBe(0);
    });

    it('parametri invalidi → risultato vuoto (mai un run silenziosamente sbagliato)', () => {
        const snaps: BookSnapshot[] = [s0(), s0(T0 + 10_000)];
        expect(runLadderBacktest(snaps, { ...P, stake: 1 }, () => false).attempted).toBe(0);
        expect(runLadderBacktest(snaps, { ...P, tpTicks: 0 }, () => false).attempted).toBe(0);
    });
});
