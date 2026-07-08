// ============================================================================
// ladderChart.ts — serie prezzo del ladder → CANDELE per il mini-chart laterale
// (stile BetTrader "matchstick"). Matematica PURA: il campionamento avviene nel
// componente (ogni update del ladder ≈ 0.25–2s), qui solo bucketing/aggregazione.
// ============================================================================

export interface PriceSample {
    t: number;   // epoch ms del campione
    p: number;   // LTP al campione
}

export interface Candle {
    t0: number;  // inizio bucket (epoch ms)
    o: number;   // open
    h: number;   // high
    l: number;   // low
    c: number;   // close
}

// Appende un campione alla serie (MUTA l'array: è un buffer in-ref del componente),
// scartando i non-finiti e deduplicando i campioni identici consecutivi ravvicinati.
// `cap` limita la memoria (FIFO): 720 campioni a 2s ≈ 24 minuti di storia.
export function pushSample(buf: PriceSample[], t: number, p: number, cap = 720): void {
    if (!Number.isFinite(t) || !Number.isFinite(p) || p <= 0) return;
    const last = buf[buf.length - 1];
    if (last && last.p === p && t - last.t < 1000) return; // dedup rumore ravvicinato
    if (last && t < last.t) return;                        // mai campioni fuori ordine
    buf.push({ t, p });
    if (buf.length > cap) buf.splice(0, buf.length - cap);
}

// Aggrega i campioni in candele OHLC per bucket temporale di `bucketMs`,
// ordinate per tempo crescente, al più le ULTIME `maxBuckets`.
// Bucket senza campioni non producono candele (gap visibile = nessun trade street).
export function bucketCandles(
    samples: readonly PriceSample[],
    bucketMs: number,
    maxBuckets: number,
): Candle[] {
    if (!(bucketMs > 0) || !(maxBuckets > 0)) return [];
    const byBucket = new Map<number, Candle>();
    for (const s of samples) {
        if (!Number.isFinite(s.t) || !Number.isFinite(s.p)) continue;
        const t0 = Math.floor(s.t / bucketMs) * bucketMs;
        const c = byBucket.get(t0);
        if (!c) {
            byBucket.set(t0, { t0, o: s.p, h: s.p, l: s.p, c: s.p });
        } else {
            if (s.p > c.h) c.h = s.p;
            if (s.p < c.l) c.l = s.p;
            c.c = s.p; // i campioni arrivano in ordine (pushSample lo garantisce)
        }
    }
    const out = Array.from(byBucket.values()).sort((a, b) => a.t0 - b.t0);
    return out.length > maxBuckets ? out.slice(out.length - maxBuckets) : out;
}
