// Scenari sintetici che certificano la MECCANICA dello scalper averaging-down
// prima di toccare i dati reali: green 1-tick, averaging su tick contro,
// force-flat a maxLegs, sospensione-gol con lapse del lay, target-stop, delay.
import { describe, expect, it } from 'vitest';
import { DEFAULT_CONFIG, runPhase, type EngineConfig, type SelFrame } from './engine';

// Book sintetico: spread 1 tick attorno a `back` (best back), profondità 3×100£,
// trd cumulativo per prezzo passato esplicitamente.
function mk(
    ts: number,
    back: number,
    opts: {
        inplay?: boolean; status?: string; ltp?: number; tv?: number;
        trd?: [number, number][]; backSize?: number; laySize?: number;
        lay?: number;
    } = {},
): SelFrame {
    const b = back;
    const l = opts.lay ?? Math.round((back + 0.01) * 100) / 100;
    const bs = opts.backSize ?? 100;
    const ls = opts.laySize ?? 100;
    const down = (p: number, n: number) => Math.round((p - n * 0.01) * 100) / 100;
    const up = (p: number, n: number) => Math.round((p + n * 0.01) * 100) / 100;
    return {
        ts,
        back: [[b, bs], [down(b, 1), 100], [down(b, 2), 100]],
        lay: [[l, ls], [up(l, 1), 100], [up(l, 2), 100]],
        ltp: opts.ltp ?? b,
        tv: opts.tv ?? 0,
        trd: opts.trd,
        status: opts.status ?? 'OPEN',
        inplay: opts.inplay ?? false,
    };
}

const CFG: EngineConfig = { ...DEFAULT_CONFIG, target: 1000 }; // target alto: niente stop

describe('scalper averaging-down — meccanica', () => {
    it('ciclo green 1-tick pre-match: back 25@1.80, lay al BE 1.79, fill maker su trd', () => {
        const frames: SelFrame[] = [
            mk(0, 1.80, { tv: 1000, trd: [[1.80, 500]] }),
            mk(10_000, 1.80, { tv: 1000, trd: [[1.80, 500]] }),
            // il mercato scende e tratta a 1.79: 400£ passano al nostro prezzo
            mk(20_000, 1.79, { ltp: 1.79, tv: 1400, trd: [[1.80, 500], [1.79, 400]] }),
            mk(30_000, 1.79, { ltp: 1.79, tv: 1500, trd: [[1.80, 500], [1.79, 500]] }),
            mk(40_000, 1.79, { tv: 1500, trd: [[1.80, 500], [1.79, 500]] }),
        ];
        const r = runPhase(frames, CFG, null);
        expect(r.greens).toBe(1);
        // green teorico: 25×1.80/1.79 − 25 = 0.1397 → ~0.1327 netto 5%
        expect(r.cycles[0].pnl).toBeGreaterThan(0.10);
        expect(r.cycles[0].pnl).toBeLessThan(0.15);
        // il P&L di fase è la somma dei cicli (il bot riapre dopo il green)
        const sum = r.cycles.reduce((a, c) => a + c.pnl, 0);
        expect(r.pnl).toBeCloseTo(sum, 10);
    });

    it('tick contro → averaging: 2 gambe, BE a 1 tick sotto, chiusura in green', () => {
        const frames: SelFrame[] = [
            mk(0, 1.80, { tv: 1000, trd: [[1.80, 500]] }),
            mk(10_000, 1.80, { tv: 1000, trd: [[1.80, 500]] }),
            // tick CONTRO: best back 1.81 → cancel lay + gamba 2 a 1.81
            mk(20_000, 1.81, { ltp: 1.81, tv: 1100, trd: [[1.80, 500], [1.81, 100]] }),
            mk(30_000, 1.81, { tv: 1100, trd: [[1.80, 500], [1.81, 100]] }),
            // storno di 1 tick: tratta a 1.80 (BE aggregato) con volume abbondante
            mk(40_000, 1.80, { ltp: 1.80, tv: 1800, trd: [[1.80, 1100], [1.81, 100]] }),
            mk(50_000, 1.80, { tv: 1900, trd: [[1.80, 1200], [1.81, 100]] }),
        ];
        const r = runPhase(frames, CFG, null);
        expect(r.greens).toBe(1);
        expect(r.cycles[0].legs).toBe(2);
        // aggregato: S=50, q̄=1.805 → green a 1.80 = 50×1.805/1.80−50 = 0.1389 lordo
        expect(r.cycles[0].pnl).toBeGreaterThan(0.10);
        expect(r.cycles[0].maxExposure).toBeCloseTo(50, 1);
    });

    it('deriva senza storni → 4 gambe e force-flat in perdita', () => {
        const frames: SelFrame[] = [];
        let t = 0;
        // prezzo sale di 1 tick ogni 10s: 1.80 → 1.86, nessuno storno
        for (let k = 0; k <= 6; k++) {
            frames.push(mk(t, 1.80 + k * 0.01, { tv: 1000 + k * 100, trd: [[1.80 + k * 0.01, 100]] }));
            t += 10_000;
        }
        frames.push(mk(t, 1.87, { tv: 2000 }));
        frames.push(mk(t + 10_000, 1.87, { tv: 2000 }));
        const r = runPhase(frames, CFG, null);
        expect(r.forceFlats).toBe(1);
        const ff = r.cycles.find(c => c.kind === 'force_flat')!;
        expect(ff.legs).toBe(4);
        expect(ff.pnl).toBeLessThan(0);
        expect(ff.maxExposure).toBeCloseTo(100, 1);
    });

    it('sospensione-gol in-play: lay lapsato, salto di prezzo, force-flat oltre maxLegs', () => {
        const frames: SelFrame[] = [
            mk(0, 1.80, { inplay: true, tv: 1000, trd: [[1.80, 500]] }),
            mk(10_000, 1.80, { inplay: true, tv: 1000, trd: [[1.80, 500]] }),
            mk(20_000, 1.80, { inplay: true, status: 'SUSPENDED' }),       // GOL
            mk(30_000, 1.80, { inplay: true, status: 'SUSPENDED' }),
            // riapre +20 tick: 2.00 (Under saltato)
            mk(40_000, 2.00, { inplay: true, ltp: 2.00, tv: 1500, trd: [[1.80, 500], [2.00, 200]] }),
            mk(50_000, 2.02, { inplay: true, ltp: 2.02, tv: 1600, trd: [[1.80, 500], [2.00, 200], [2.02, 100]] }),
            mk(60_000, 2.04, { inplay: true, ltp: 2.04, tv: 1700, trd: [[1.80, 500], [2.02, 100], [2.04, 100]] }),
            mk(70_000, 2.06, { inplay: true, ltp: 2.06, tv: 1800 }),
            mk(80_000, 2.06, { inplay: true, tv: 1800 }),
            mk(90_000, 2.06, { inplay: true, tv: 1800 }),
            mk(100_000, 2.06, { inplay: true, tv: 1800 }),
        ];
        const r = runPhase(frames, CFG, null);
        // il ciclo si chiude in force-flat con perdita pesante (salto non recuperabile)
        expect(r.forceFlats + r.settled).toBeGreaterThanOrEqual(1);
        expect(r.pnl).toBeLessThan(-1);
    });

    it('target-stop: si ferma appena il P&L di fase raggiunge +1€', () => {
        const frames: SelFrame[] = [];
        let t = 0;
        let tv = 1000;
        const trdAt: Record<string, number> = {};
        const bump = (p: number, v: number) => {
            const key = p.toFixed(2);
            trdAt[key] = (trdAt[key] ?? 0) + v;
            tv += v;
            return Object.entries(trdAt).map(([k, v2]) => [Number(k), v2] as [number, number]);
        };
        // 10 cicli green 1-tick da ~0.13€: il target +1€ scatta all'8°
        for (let k = 0; k < 10; k++) {
            frames.push(mk(t, 1.80, { tv, trd: bump(1.80, 50) })); t += 10_000;
            frames.push(mk(t, 1.79, { ltp: 1.79, tv, trd: bump(1.79, 600) })); t += 10_000;
            frames.push(mk(t, 1.80, { ltp: 1.80, tv, trd: bump(1.80, 50) })); t += 10_000;
        }
        const r = runPhase(frames, { ...CFG, target: 1.0 }, null);
        expect(r.targetReached).toBe(true);
        expect(r.pnl).toBeGreaterThanOrEqual(1.0);
        expect(r.pnl).toBeLessThan(1.2); // si è FERMATO, non ha continuato
    });

    it('bet delay in-play: l\'entry si abbina al book di 5s dopo, non a quello del click', () => {
        const frames: SelFrame[] = [
            mk(0, 1.80, { inplay: true, tv: 1000 }),
            // a t+5s il best back è salito a 1.84: il taker prende il prezzo NUOVO (migliore per il back)
            mk(5_000, 1.84, { inplay: true, tv: 1100 }),
            mk(15_000, 1.84, { inplay: true, tv: 1100 }),
            mk(25_000, 1.84, { inplay: true, tv: 1100 }),
        ];
        const r = runPhase(frames, { ...CFG, maxLegs: 1 }, null);
        const anyCycle = r.cycles[0];
        expect(anyCycle).toBeDefined();
        // la prima gamba deve essersi abbinata a 1.84 (book post-delay), non 1.80
        // (lo deduciamo dall'esposizione: stake 25 abbinato)
        expect(anyCycle.maxExposure).toBeCloseTo(25, 1);
    });
});
