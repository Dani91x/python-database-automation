// ============================================================================
// multiLadderFinto.ts - SOLO PER L'ANTEPRIMA POPOLATA di /multi-ladder.
//
// Non e' importato dall'app: alias Vite ESATTO di '@/lib/multiLadder' (vedi
// AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/alias_analisi.mjs). Il modulo
// vero e' PURO (layout + localStorage): si ri-esporta tutto (percorso RELATIVO)
// e si ridefinisce solo `loadSlots`, che con il localStorage vuoto (il caso di
// ogni scatto) restituisce un workspace gia' composto. Il workspace salvato
// dall'utente nell'anteprima, se c'e', vince: si legge col modulo vero.
// I mercati sono quelli di Segui live con ladder nei finti comuni
// (seguiLiveDati.ts: Inter-Torino Match Odds e Over/Under 2.5, Real Betis-Getafe
// Match Odds), come il prototipo (prototipo/js/s_live.js, multi-ladder).
// ============================================================================
import type { LadderSlot } from '../lib/multiLadder';
import { loadSlots as loadSlotsVero, normalizeSlots } from '../lib/multiLadder';
import { EV, MK } from './seguiLiveDati';

export * from '../lib/multiLadder';

const WORKSPACE: Omit<LadderSlot, 'id'>[] = [
    { sport: 'calcio', eventId: EV.inter, marketId: MK.interMo, marketName: 'Match Odds', eventName: 'Inter — Torino' },
    { sport: 'calcio', eventId: EV.betis, marketId: MK.betisMo, marketName: 'Match Odds', eventName: 'Real Betis — Getafe' },
    { sport: 'calcio', eventId: EV.inter, marketId: MK.interOu25, marketName: 'Over/Under 2.5 Goals', eventName: 'Inter — Torino' },
];

export function loadSlots(): LadderSlot[] {
    const salvati = loadSlotsVero();
    return salvati.length ? salvati : normalizeSlots(WORKSPACE);
}
