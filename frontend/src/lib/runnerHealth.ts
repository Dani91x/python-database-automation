// ============================================================================
// runnerHealth.ts — A5: stato dell'heartbeat del runner (PURO, testato).
//
// MONEY-CRITICAL: il chip in top bar deve dire la verità — un timestamp
// illeggibile/mancante è 'unknown' (mai un finto verde), oltre soglia è
// 'stale' (runner giù o appeso: stop/regole armate NON esistono più).
// ============================================================================
export type HeartbeatState = 'ok' | 'stale' | 'unknown';

// Tolleranza di clock-skew: un battito "nel futuro" oltre questa soglia è un
// orologio sballato → età INAFFIDABILE (fix review MEDIUM: un runner con clock
// avanti che muore lascerebbe un finto verde per tutta la durata dello skew).
const FUTURE_SKEW_TOLERANCE_SEC = 15;

/** Età in secondi dell'ultimo battito; null se assente/illeggibile o troppo nel futuro. */
export function heartbeatAgeSec(ts: string | null | undefined, nowMs: number): number | null {
    if (!ts) return null;
    const t = Date.parse(ts);
    if (!Number.isFinite(t)) return null;
    if (t - nowMs > FUTURE_SKEW_TOLERANCE_SEC * 1000) return null; // clock sballato
    return Math.max(0, (nowMs - t) / 1000);
}

/** Stato del runner dal battito: ok (fresco), stale (oltre soglia), unknown (mai visto). */
export function heartbeatState(
    ts: string | null | undefined,
    nowMs: number,
    staleSec = 30,
): HeartbeatState {
    const age = heartbeatAgeSec(ts, nowMs);
    if (age == null) return 'unknown';
    return age > staleSec ? 'stale' : 'ok';
}
