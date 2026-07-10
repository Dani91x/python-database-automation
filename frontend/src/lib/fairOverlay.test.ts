import { describe, it, expect } from 'vitest';
import { bestEvAt, evBack, evLay, fairInfos, fmtEvAt, FAIR_MAX_AGE_MS } from './fairOverlay';
import type { LiveSignalsRow, Signal } from './live';

const NOW = Date.parse('2026-07-10T15:00:00.000Z');

const mkSignal = (over: Partial<Signal> = {}): Signal => ({
    market_id: '1.1',
    market_type: 'MATCH_ODDS',
    selection_id: 11,
    selection_name: 'Home FC',
    model_prob: 0.5,
    market_back: 2.1,
    market_lay: 2.12,
    fair_back: 2.0,
    fair_lay: 2.0,
    edge: 0.02,
    direction: 'BACK',
    confidence: 0.5,
    kelly_stake: 3.5,
    ...over,
});

const mkRow = (signals: Signal[], over: Partial<LiveSignalsRow> = {}, commission?: number): LiveSignalsRow => ({
    event_id: 'ev1',
    signals: { signals, updated_ms: NOW, ...(commission != null ? { commission } : {}) },
    model_meta: null,
    updated_at: new Date(NOW).toISOString(),
    ...over,
});

// ---------------------------------------------------------------------------
// Formule EV — DEVONO combaciare col motore (live_engine_pro, nette commissione):
//   back: prob·(p−1)·(1−c) − (1−prob) · lay: (1−prob)·(1−c) − prob·(p−1)
// ---------------------------------------------------------------------------
describe('evBack / evLay (formule del motore, a mano)', () => {
    it('back: prob 0.5 @ 2.10, c=5% → 0.5·1.10·0.95 − 0.5 = +2.25%', () => {
        expect(evBack(0.5, 2.10, 0.05)).toBeCloseTo(0.5 * 1.10 * 0.95 - 0.5, 12);
        expect(evBack(0.5, 2.10, 0.05)).toBeCloseTo(0.0225, 4);
    });
    it('lay: prob 0.5 @ 1.90, c=5% → 0.5·0.95 − 0.5·0.90 = +2.5%', () => {
        expect(evLay(0.5, 1.90, 0.05)).toBeCloseTo(0.5 * 0.95 - 0.5 * 0.90, 12);
        expect(evLay(0.5, 1.90, 0.05)).toBeCloseTo(0.025, 4);
    });
    it('senza commissione il fair è il pareggio esatto (EV=0 al fair)', () => {
        expect(evBack(0.5, 2.0, 0)).toBeCloseTo(0, 12);
        expect(evLay(0.5, 2.0, 0)).toBeCloseTo(0, 12);
    });
    it('con commissione, AL fair entrambe le EV sono NEGATIVE (costo reale)', () => {
        expect(evBack(0.5, 2.0, 0.05)).toBeLessThan(0);
        expect(evLay(0.5, 2.0, 0.05)).toBeLessThan(0);
    });
});

describe('bestEvAt', () => {
    it('sopra il fair vince il BACK, sotto vince il LAY', () => {
        expect(bestEvAt(0.5, 2.30, 0.05)?.side).toBe('back');
        expect(bestEvAt(0.5, 1.80, 0.05)?.side).toBe('lay');
    });
    it('vicino al fair (entrambe negative per la commissione) → null, mai un valore finto', () => {
        expect(bestEvAt(0.5, 2.0, 0.05)).toBeNull();
        expect(bestEvAt(0.5, 2.02, 0.05)).toBeNull();
    });
    it('input non validi → null', () => {
        expect(bestEvAt(NaN, 2.0, 0.05)).toBeNull();
        expect(bestEvAt(0.5, 1.0, 0.05)).toBeNull();
    });
});

describe('fairInfos (validità: resta finché ha valore, sparisce quando non ne ha)', () => {
    it('riga fresca e valida → fair per selezione del mercato', () => {
        const m = fairInfos(mkRow([mkSignal()]), '1.1', NOW);
        expect(m.get(11)?.fair).toBe(2.0);
        expect(m.get(11)?.prob).toBe(0.5);
        expect(m.get(11)?.commission).toBe(0.05); // fallback = default motore
    });
    it('usa la commissione del payload quando presente', () => {
        const m = fairInfos(mkRow([mkSignal()], {}, 0.02), '1.1', NOW);
        expect(m.get(11)?.commission).toBe(0.02);
    });
    it('riga stantia (oltre il keepalive tollerato) → mappa vuota', () => {
        const m = fairInfos(mkRow([mkSignal()]), '1.1', NOW + FAIR_MAX_AGE_MS + 1);
        expect(m.size).toBe(0);
    });
    it('riga fresca resta visibile ANCHE dopo i vecchi 2 minuti (keepalive del runner)', () => {
        // 140s < 150s: col solo write-on-change sarebbe già sparita (>120s) — ora
        // la freschezza è garantita dal keepalive e il segnale valido RESTA.
        const m = fairInfos(mkRow([mkSignal()]), '1.1', NOW + 140_000);
        expect(m.get(11)?.fair).toBe(2.0);
    });
    it('HOLD non nasconde il fair (è informazione, non un invito a puntare)', () => {
        const m = fairInfos(mkRow([mkSignal({ direction: 'HOLD' })]), '1.1', NOW);
        expect(m.get(11)?.direction).toBe('HOLD');
    });
    it('mercato deciso (prob agli estremi) → selezione esclusa', () => {
        const rows = [
            mkSignal({ selection_id: 21, model_prob: 0.9995, fair_back: 1.0005 }),
            mkSignal({ selection_id: 22, model_prob: 0.0005, fair_back: 2000 }),
        ];
        expect(fairInfos(mkRow(rows), '1.1', NOW).size).toBe(0);
    });
    it('fair mancante/invalido o prob invalida → selezione esclusa', () => {
        const rows = [
            mkSignal({ selection_id: 31, fair_back: null }),
            mkSignal({ selection_id: 32, fair_back: 0.8 }),
            mkSignal({ selection_id: 33, model_prob: NaN }),
        ];
        expect(fairInfos(mkRow(rows), '1.1', NOW).size).toBe(0);
    });
    it('filtra per mercato; riga null → vuoto', () => {
        expect(fairInfos(mkRow([mkSignal()]), '9.9', NOW).size).toBe(0);
        expect(fairInfos(null, '1.1', NOW).size).toBe(0);
    });
});

describe('fmtEvAt', () => {
    it('formatta lato+percentuale; null dove non c\'è valore', () => {
        const info = { fair: 2.0, prob: 0.5, direction: 'HOLD' as const, commission: 0.05, confidence: 0.5 };
        // a mano: evBack(0.5, 2.5, 5%) = 0.5·1.5·0.95 − 0.5 = 0.2125 → "B +21.2/21.3%"
        const s = fmtEvAt(info, 2.5);
        expect(s).toMatch(/^B \+21\.[23]%$/);
        // sotto il fair vince il LAY: evLay(0.5, 1.7, 5%) = 0.475 − 0.35 = 0.125 → "L +12.5%"
        expect(fmtEvAt(info, 1.7)).toMatch(/^L \+12\.5%$/);
        expect(fmtEvAt(info, 2.0)).toBeNull();
        expect(fmtEvAt(null, 2.0)).toBeNull();
    });
});
