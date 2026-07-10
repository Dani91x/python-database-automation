// ============================================================================
// fairOverlay.ts — F38: fair price del MOTORE nel ladder + EV per livello — PURO.
//
// MONEY-CRITICAL: qui NON si ricalcola nessun modello. Il fair è ESATTAMENTE il
// fair_back scritto dal motore live (Betfair/stream/engine/live_engine_pro.py:
// fair = 1/model_prob, prob calibrata+rinormalizzata Dixon-Coles in-play).
// L'EV per livello usa le STESSE formule del motore, al NETTO della commissione
// che il motore stesso serializza nel payload (signals.commission):
//   EV back a prezzo p:  prob·(p−1)·(1−c) − (1−prob)
//   EV lay  a prezzo p:  (1−prob)·(1−c) − prob·(p−1)
//
// VALIDITÀ (richiesta esplicita utente: i segnali che hanno ancora valore restano
// visibili, quelli senza valore scompaiono): il runner ri-scrive la riga anche a
// segnale invariato (keepalive ≤60s, F38) → "fresco" significa "il motore lo sta
// ancora confermando". Qui un segnale è mostrato SOLO se:
//   - la riga non è stantia (updated_at entro maxAgeMs, default 150s = 2.5×keepalive:
//     tollera un ciclo saltato, mai un fair di un motore fermo);
//   - model_prob è finita e in (0,1) ESCLUSI gli estremi decisi (mercato deciso:
//     prob ≤0.001 o ≥0.999 → fair privo di senso operativo, riga esclusa);
//   - fair_back è finito e > 1 (coerenza col motore: 1/prob).
// La direzione HOLD NON nasconde il fair: HOLD = "nessun lato azionabile ora",
// ma il fair resta informazione valida (il chip Kelly resta gestito a parte).
// ============================================================================
import type { LiveSignalsRow } from '@/lib/live';
import { signalsStale } from '@/lib/kellySuggest';

// Commissione di fallback = DEFAULT_COMMISSION del motore (live_engine_pro).
// Usata SOLO per righe scritte prima che il payload includesse `commission`.
export const FALLBACK_COMMISSION = 0.05;

// Keepalive del runner = 60s (SIGNALS_KEEPALIVE_SEC): 2.5 cicli di tolleranza.
export const FAIR_MAX_AGE_MS = 150_000;

export interface FairInfo {
    /** Fair del motore (1/prob), quota Betfair. */
    fair: number;
    /** Probabilità calibrata del motore (0..1). */
    prob: number;
    /** Direzione operativa del motore (BACK/LAY/HOLD) — solo informativa qui. */
    direction: 'BACK' | 'LAY' | 'HOLD';
    /** Commissione con cui il motore ha calcolato EV/Kelly. */
    commission: number;
    confidence: number;
}

/** EV per 1€ di stake di un BACK a prezzo p (netta commissione) — formula del motore. */
export function evBack(prob: number, price: number, commission: number): number {
    return prob * (price - 1) * (1 - commission) - (1 - prob);
}

/** EV per 1€ di stake di un LAY a prezzo p (netta commissione) — formula del motore. */
export function evLay(prob: number, price: number, commission: number): number {
    return (1 - prob) * (1 - commission) - prob * (price - 1);
}

/** Il lato con EV migliore a QUESTO livello di prezzo (null se nessuno è positivo).
 *  Vicino al fair entrambe le EV sono negative per via della commissione: '—'. */
export function bestEvAt(
    prob: number, price: number, commission: number,
): { side: 'back' | 'lay'; ev: number } | null {
    if (!Number.isFinite(prob) || !Number.isFinite(price) || price <= 1) return null;
    const b = evBack(prob, price, commission);
    const l = evLay(prob, price, commission);
    if (b <= 0 && l <= 0) return null;
    return b >= l ? { side: 'back', ev: b } : { side: 'lay', ev: l };
}

/** Fair del motore per le selezioni di UN mercato: selection_id → FairInfo.
 *  Riga nulla/stantia o prob non valida → mappa vuota (mai un fair inventato). */
export function fairInfos(
    row: LiveSignalsRow | null | undefined,
    marketId: string,
    nowMs: number,
    maxAgeMs = FAIR_MAX_AGE_MS,
): Map<number, FairInfo> {
    const out = new Map<number, FairInfo>();
    if (!row || signalsStale(row, nowMs, maxAgeMs)) return out;
    const state = row.signals;
    const signals = state?.signals;
    if (!Array.isArray(signals)) return out;
    const rawComm = (state as { commission?: unknown } | null)?.commission;
    const commission = typeof rawComm === 'number' && rawComm >= 0 && rawComm < 1
        ? rawComm : FALLBACK_COMMISSION;
    for (const s of signals) {
        if (!s || s.market_id !== marketId || !Number.isFinite(s.selection_id)) continue;
        const prob = Number(s.model_prob);
        // mercato deciso (prob agli estremi): fair privo di senso operativo → escluso.
        if (!Number.isFinite(prob) || prob <= 0.001 || prob >= 0.999) continue;
        const fair = Number(s.fair_back);
        if (!Number.isFinite(fair) || fair <= 1) continue;
        const direction = s.direction === 'BACK' || s.direction === 'LAY' ? s.direction : 'HOLD';
        out.set(s.selection_id, {
            fair,
            prob,
            direction,
            commission,
            confidence: Number.isFinite(s.confidence) ? s.confidence : 0,
        });
    }
    return out;
}

/** Formatta l'EV migliore a un livello: "B +4.2%" / "L +1.3%" / null (nessun valore). */
export function fmtEvAt(info: FairInfo | null | undefined, price: number): string | null {
    if (!info) return null;
    const best = bestEvAt(info.prob, price, info.commission);
    if (!best) return null;
    return `${best.side === 'back' ? 'B' : 'L'} +${(best.ev * 100).toFixed(1)}%`;
}
