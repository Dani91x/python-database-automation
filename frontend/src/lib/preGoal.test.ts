import { describe, it, expect } from 'vitest';
import { preGoalWarning, PREGOAL_AMBER, PREGOAL_RED } from './preGoal';
import type { GoalHazardState, LiveSignalsRow } from './live';

const NOW = Date.parse('2026-07-10T20:30:00.000Z');

const mkRow = (hazard: GoalHazardState | null | undefined, ageMs = 0): LiveSignalsRow => ({
    event_id: 'ev1',
    signals: { signals: [], updated_ms: NOW - ageMs, ...(hazard !== undefined ? { hazard } : {}) },
    model_meta: null,
    updated_at: new Date(NOW - ageMs).toISOString(),
});

const mkHazard = (p: number): GoalHazardState => ({
    p_next: p, exp_goals_next: -Math.log(1 - p), horizon_min: 5, minute: 75,
    lam_home: 0.6, lam_away: 0.5,
});

describe('preGoalWarning', () => {
    it('sotto soglia ambra → null (niente rumore)', () => {
        expect(preGoalWarning(mkRow(mkHazard(0.15)), true, NOW)).toBeNull();
        expect(preGoalWarning(mkRow(mkHazard(PREGOAL_AMBER - 0.001)), true, NOW)).toBeNull();
    });
    it('soglie: ambra a 0.22, rosso a 0.30', () => {
        expect(preGoalWarning(mkRow(mkHazard(0.24)), true, NOW)?.level).toBe('amber');
        expect(preGoalWarning(mkRow(mkHazard(PREGOAL_RED)), true, NOW)?.level).toBe('red');
        expect(preGoalWarning(mkRow(mkHazard(0.45)), true, NOW)?.level).toBe('red');
    });
    it('espone il numero (p, gol attesi, minuto): il trader vede il dato, non solo il colore', () => {
        const w = preGoalWarning(mkRow(mkHazard(0.33)), true, NOW);
        expect(w?.p).toBe(0.33);
        expect(w?.minute).toBe(75);
        expect(w?.horizonMin).toBe(5);
    });
    it('NON in-play → null anche con hazard alto (pre-match non ha "imminente")', () => {
        expect(preGoalWarning(mkRow(mkHazard(0.5)), false, NOW)).toBeNull();
        expect(preGoalWarning(mkRow(mkHazard(0.5)), null, NOW)).toBeNull();
    });
    it('riga stantia (motore fermo) → null, mai un hazard vecchio', () => {
        expect(preGoalWarning(mkRow(mkHazard(0.5), 10 * 60_000), true, NOW)).toBeNull();
    });
    it('hazard assente o p invalida → null', () => {
        expect(preGoalWarning(mkRow(undefined), true, NOW)).toBeNull();
        expect(preGoalWarning(mkRow(null), true, NOW)).toBeNull();
        expect(preGoalWarning(mkRow(mkHazard(NaN)), true, NOW)).toBeNull();
        expect(preGoalWarning(null, true, NOW)).toBeNull();
    });
});
