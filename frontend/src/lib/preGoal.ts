// ============================================================================
// preGoal.ts — F40: pre-goal warning dal modello in-play — PURO.
//
// MONEY-CRITICAL / ONESTÀ: l'hazard NON viene ricalcolato qui — è quello scritto
// dal motore in live_signals.hazard (λ residui calibrati per lega × CDF empirica
// dei tempi-gol, live_engine_pro.event_goal_hazard). Deriva da minuto/punteggio/
// cartellini: NON vede tiri/corner live (hook pressure non calibrato) e la UI lo
// dichiara nel tooltip. Il warning:
//   - esiste SOLO in-play e SOLO se la riga segnali è fresca (keepalive runner:
//     stessa soglia del fair overlay — mai un hazard di un motore fermo);
//   - ha due livelli: AMBRA (attenzione) e ROSSO (rischio alto), con soglie
//     esplicite documentate qui sotto;
//   - propone "Copri ora" (cash-out evento già esistente): l'utente CONFERMA,
//     mai un'azione automatica.
//
// SOGLIE: baseline p(gol ≤5') a ritmo medio (λ_tot residuo ~1.0 a metà ripresa)
// è ~12-16%. AMBRA = 0.22 (~1.5× baseline), ROSSO = 0.30 (~2× baseline):
// scattano su stati di gioco realmente caldi (chi insegue nel finale, rossi,
// λ pre-match alti), non sul rumore.
// ============================================================================
import type { GoalHazardState, LiveSignalsRow } from '@/lib/live';
import { signalsStale } from '@/lib/kellySuggest';
import { FAIR_MAX_AGE_MS } from '@/lib/fairOverlay';

export const PREGOAL_AMBER = 0.22;
export const PREGOAL_RED = 0.30;

export type PreGoalLevel = 'amber' | 'red';

export interface PreGoalWarning {
    level: PreGoalLevel;
    /** P(≥1 gol nell'orizzonte), 0..1 — il numero VA mostrato, non solo il colore. */
    p: number;
    expGoals: number;
    horizonMin: number;
    minute: number;
}

/** Warning pre-gol dalla riga segnali. null = nessun warning (niente hazard,
 *  riga stantia, non in-play, o sotto soglia). Mai un warning inventato. */
export function preGoalWarning(
    row: LiveSignalsRow | null | undefined,
    inplay: boolean | null | undefined,
    nowMs: number,
    maxAgeMs = FAIR_MAX_AGE_MS,
): PreGoalWarning | null {
    if (inplay !== true) return null;                       // solo in-play
    if (!row || signalsStale(row, nowMs, maxAgeMs)) return null;
    const hz = (row.signals as { hazard?: GoalHazardState | null } | null)?.hazard;
    if (!hz) return null;
    const p = Number(hz.p_next);
    if (!Number.isFinite(p) || p <= 0 || p >= 1) return null;
    if (p < PREGOAL_AMBER) return null;
    return {
        level: p >= PREGOAL_RED ? 'red' : 'amber',
        p,
        expGoals: Number.isFinite(hz.exp_goals_next) ? hz.exp_goals_next : 0,
        horizonMin: Number.isFinite(hz.horizon_min) ? hz.horizon_min : 5,
        minute: Number.isFinite(hz.minute) ? hz.minute : 0,
    };
}
