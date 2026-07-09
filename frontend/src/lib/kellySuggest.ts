// ============================================================================
// kellySuggest.ts — E36: position sizing assistito (Kelly frazionato) — PURO.
//
// MONEY-CRITICAL: lo stake suggerito è ESATTAMENTE il `kelly_stake` calcolato
// dal motore live (Betfair/stream/engine/live_engine_pro.py — Kelly frazionato
// al netto commissione, commit ac751fc). Qui NON si ricalcola nulla: si filtra,
// si valida e si formatta. Un suggerimento è mostrato SOLO se:
//   - direction è BACK o LAY (mai su HOLD);
//   - kelly_stake è finito e > 0;
//   - il segnale non è STANTIO (updated_at della riga entro maxAgeMs).
// L'accettazione è SEMPRE un click esplicito dell'utente: MAI auto-applicato.
// ============================================================================
import type { LiveSignalsRow, Signal } from '@/lib/live';

export interface KellySuggestion {
    side: 'back' | 'lay';
    /** Stake suggerito (EUR) = kelly_stake del motore, arrotondato al centesimo. */
    stake: number;
    edge: number | null;
    prob: number;
    fair: number | null;
    confidence: number;
    selectionName: string | null;
}

/** True se la riga segnali è troppo vecchia per essere mostrata (default 2 min). */
export function signalsStale(
    row: Pick<LiveSignalsRow, 'updated_at'> | null | undefined,
    nowMs: number,
    maxAgeMs = 120_000,
): boolean {
    const ts = row?.updated_at ? Date.parse(row.updated_at) : NaN;
    if (!Number.isFinite(ts)) return true; // età ignota = stantio (mai fingere freschezza)
    return nowMs - ts > maxAgeMs;
}

function validSuggestion(s: Signal): KellySuggestion | null {
    if (s.direction !== 'BACK' && s.direction !== 'LAY') return null;
    const stake = Number(s.kelly_stake);
    if (!Number.isFinite(stake) || stake <= 0) return null;
    const prob = Number(s.model_prob);
    if (!Number.isFinite(prob) || prob <= 0 || prob >= 1) return null;
    const side = s.direction === 'BACK' ? 'back' : 'lay';
    const fair = side === 'back' ? s.fair_back : s.fair_lay;
    return {
        side,
        stake: Math.round(stake * 100) / 100,
        edge: Number.isFinite(s.edge as number) ? (s.edge as number) : null,
        prob,
        fair: Number.isFinite(fair as number) && (fair as number) > 1 ? (fair as number) : null,
        confidence: Number.isFinite(s.confidence) ? s.confidence : 0,
        selectionName: s.selection_name ?? null,
    };
}

/** Suggerimenti Kelly per le selezioni di UN mercato: selection_id → suggerimento.
 *  Riga nulla, segnali stantii o senza direzione operativa → mappa vuota. */
export function kellySuggestions(
    row: LiveSignalsRow | null | undefined,
    marketId: string,
    nowMs: number,
    maxAgeMs = 120_000,
): Map<number, KellySuggestion> {
    const out = new Map<number, KellySuggestion>();
    if (!row || signalsStale(row, nowMs, maxAgeMs)) return out;
    const signals = row.signals?.signals;
    if (!Array.isArray(signals)) return out;
    for (const s of signals) {
        if (!s || s.market_id !== marketId) continue;
        const sug = validSuggestion(s);
        if (sug && Number.isFinite(s.selection_id)) out.set(s.selection_id, sug);
    }
    return out;
}
