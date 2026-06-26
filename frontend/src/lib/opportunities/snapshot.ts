// ============================================================================
// snapshot.ts — costruisce le fotografie (Snapshot) a bucket temporali fissi a
// partire da un ReplayData. Per ogni bucket fa CARRY-FORWARD dell'ultimo book
// noto di ciascun mercato (ultimo frame con ts <= bucketTs) e attacca il
// punteggio dell'ultimo evento <= bucketTs.
// ============================================================================
import type { ReplayData, Frame, Market } from '@/lib/live';
import type { Snapshot, MarketLite, MarketState, SelLite } from './types';

function tsMs(ts: string): number {
    const v = Date.parse(ts);
    return Number.isFinite(v) ? v : NaN;
}

// Indice dell'ULTIMO elemento con key(arr[i]) <= target (array ORDINATO asc).
// Ritorna -1 se nessun elemento soddisfa la condizione.
function bisectLast<T>(arr: T[], target: number, key: (x: T) => number): number {
    let lo = 0;
    let hi = arr.length - 1;
    let ans = -1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (key(arr[mid]) <= target) {
            ans = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    return ans;
}

function toMarketLite(m: Market): MarketLite {
    const selections: SelLite[] = m.selections.map((s) => ({
        selection_id: s.selection_id,
        name: s.name,
        sort_priority: s.sort_priority,
    }));
    return {
        market_id: m.market_id,
        market_type: m.market_type,
        market_name: m.market_name,
        selections,
    };
}

/**
 * buildSnapshots — genera una Snapshot per ogni bucket temporale [bucketMs].
 *
 * - bucket: da t0 (primo ts tra frame e score) a tEnd (ultimo ts), passo bucketMs.
 * - per ogni mercato: ultimo frame con ts <= bucketTs (carry-forward); i mercati
 *   senza ancora alcun frame non compaiono in `state` (ma restano in `markets`).
 * - score: ultimo score_timeline con ts <= bucketTs (default 0-0 se nessuno).
 * - minute: dal frame più recente <= bucketTs; fallback sull'ultimo score event.
 */
export function buildSnapshots(replay: ReplayData, bucketMs = 10000): Snapshot[] {
    const markets = replay.markets ?? [];
    const frames = (replay.frames ?? []).slice();
    const scores = (replay.score_timeline ?? []).slice();

    const marketsLite: MarketLite[] = markets.map(toMarketLite);

    // Frame per mercato, ordinati per ts asc.
    const framesByMarket = new Map<string, Frame[]>();
    for (const f of frames) {
        if (!Number.isFinite(tsMs(f.ts))) continue;
        const arr = framesByMarket.get(f.market_id);
        if (arr) arr.push(f);
        else framesByMarket.set(f.market_id, [f]);
    }
    for (const arr of framesByMarket.values()) {
        arr.sort((a, b) => tsMs(a.ts) - tsMs(b.ts));
    }

    // Score timeline ordinata per ts asc (solo ts validi).
    const scoresSorted = scores
        .filter((s) => Number.isFinite(tsMs(s.ts)))
        .sort((a, b) => tsMs(a.ts) - tsMs(b.ts));

    // Estremi temporali.
    const allTs: number[] = [];
    for (const arr of framesByMarket.values()) {
        if (arr.length) {
            allTs.push(tsMs(arr[0].ts));
            allTs.push(tsMs(arr[arr.length - 1].ts));
        }
    }
    if (scoresSorted.length) {
        allTs.push(tsMs(scoresSorted[0].ts));
        allTs.push(tsMs(scoresSorted[scoresSorted.length - 1].ts));
    }
    if (allTs.length === 0) return [];

    const t0 = Math.min(...allTs);
    const tEnd = Math.max(...allTs);

    // Allinea i bucket alla STESSA griglia floor della timeline UI
    // (MatchReplay usa Math.floor(ts/TIMELINE_BUCKET_MS)*TIMELINE_BUCKET_MS): così
    // il ts di ogni snapshot coincide con l'indice di timeline corrispondente e i
    // prezzi mostrati in OpportunitaPanel combaciano con quelli del MarketPanel.
    const t0aligned = Math.floor(t0 / bucketMs) * bucketMs;

    const out: Snapshot[] = [];
    for (let bucketTs = t0aligned; bucketTs <= tEnd; bucketTs += bucketMs) {
        const state: Record<string, MarketState> = {};
        let latestFrameMinute: number | null = null;
        let latestFrameTs = -Infinity;

        for (const m of markets) {
            const arr = framesByMarket.get(m.market_id);
            if (!arr || arr.length === 0) continue;
            const idx = bisectLast(arr, bucketTs, (f) => tsMs(f.ts));
            if (idx < 0) continue; // nessun frame ancora disponibile a questo bucket
            const f = arr[idx];
            state[m.market_id] = {
                market_id: m.market_id,
                market_type: m.market_type,
                status: f.status,
                ladder: f.ladder,
            };
            const fts = tsMs(f.ts);
            if (fts > latestFrameTs) {
                latestFrameTs = fts;
                latestFrameMinute = f.minute;
            }
        }

        // Score: ultimo evento <= bucketTs.
        let scoreHome = 0;
        let scoreAway = 0;
        let scoreMinute: number | null = null;
        const sIdx = bisectLast(scoresSorted, bucketTs, (s) => tsMs(s.ts));
        if (sIdx >= 0) {
            const sc = scoresSorted[sIdx];
            scoreHome = sc.score_home ?? 0;
            scoreAway = sc.score_away ?? 0;
            scoreMinute = sc.minute;
        }

        const minute = latestFrameMinute != null ? latestFrameMinute : scoreMinute;

        out.push({
            ts: new Date(bucketTs).toISOString(),
            minute,
            scoreHome,
            scoreAway,
            markets: marketsLite,
            state,
        });
    }

    return out;
}
