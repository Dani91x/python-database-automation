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

// ============================================================================
// D29 — estensioni con VOLUME per il pannello chart per-selezione.
// v = `tv` della selezione (volume tradato CUMULATO in EUR) o null se ignoto.
// Le funzioni sopra (pushSample/bucketCandles) restano invariate: le usa il
// MiniPriceChart. Qui sotto solo AGGIUNTE.
// ============================================================================

export interface VolumeSample {
    t: number;            // epoch ms del campione
    p: number;            // LTP al campione
    v: number | null;     // tv cumulato della selezione (EUR) o null se ignoto
}

// Come pushSample ma con volume cumulato. MUTA `buf` (buffer in-ref del componente),
// FIFO con cap di default 2880 (a ~1 campione/s ≈ 48 minuti di storia).
// Dedup: salta il campione se p E v sono ENTRAMBI invariati rispetto all'ultimo
// (rumore dello stream). p non finito (o ≤ 0: mai un prezzo valido) → ignora.
export function pushVolumeSample(
    buf: VolumeSample[],
    t: number,
    p: number,
    v: number | null,
    cap = 2880,
): void {
    if (!Number.isFinite(t) || !Number.isFinite(p) || p <= 0) return;
    const vv = v != null && Number.isFinite(v) ? v : null; // normalizza NaN/±Inf → ignoto
    const last = buf[buf.length - 1];
    if (last && t < last.t) return;                        // mai campioni fuori ordine
    if (last && last.p === p && last.v === vv) return;     // dedup rumore (p e v invariati)
    buf.push({ t, p, v: vv });
    if (buf.length > cap) buf.splice(0, buf.length - cap);
}

export interface CandleV {
    t0: number;  // inizio bucket (epoch ms)
    o: number;   // open
    h: number;   // high
    l: number;   // low
    c: number;   // close
    v: number;   // volume TRADATO NEL BUCKET (EUR, ≥ 0) = delta del tv cumulato
}

// OHLC per bucket (come bucketCandles) + volume del bucket = max(0, ultimo v noto
// del bucket − ultimo v noto del bucket precedente). Regole:
// - v ignoto (null) per tutto il bucket → volume 0 (mai inventare volume), il
//   baseline del bucket precedente sopravvive per il bucket successivo;
// - un RESET del tv (valore che scende, es. riavvio stream) non produce mai
//   volume negativo (clamp a 0) e ri-basa i delta successivi sul nuovo valore;
// - primo bucket con volume noto: delta intra-bucket (ultimo − primo v del bucket),
//   MAI il cumulato dall'inizio del match (barra fuori scala e bugiarda);
// - i delta sono calcolati su TUTTI i bucket PRIMA del taglio a maxBuckets, così
//   la prima candela visibile ha il volume corretto.
export function bucketCandlesV(
    samples: ReadonlyArray<VolumeSample>,
    bucketMs: number,
    maxBuckets: number,
): CandleV[] {
    if (!(bucketMs > 0) || !(maxBuckets > 0)) return [];
    interface Acc { candle: CandleV; firstV: number | null; lastV: number | null }
    const byBucket = new Map<number, Acc>();
    for (const s of samples) {
        if (!Number.isFinite(s.t) || !Number.isFinite(s.p)) continue;
        const t0 = Math.floor(s.t / bucketMs) * bucketMs;
        const vv = s.v != null && Number.isFinite(s.v) ? s.v : null;
        const a = byBucket.get(t0);
        if (!a) {
            byBucket.set(t0, {
                candle: { t0, o: s.p, h: s.p, l: s.p, c: s.p, v: 0 },
                firstV: vv,
                lastV: vv,
            });
        } else {
            const c = a.candle;
            if (s.p > c.h) c.h = s.p;
            if (s.p < c.l) c.l = s.p;
            c.c = s.p; // i campioni arrivano in ordine (pushVolumeSample lo garantisce)
            if (vv != null) {
                a.lastV = vv;
                if (a.firstV == null) a.firstV = vv;
            }
        }
    }
    const accs = Array.from(byBucket.values()).sort((a, b) => a.candle.t0 - b.candle.t0);
    let prevV: number | null = null; // ultimo tv noto dei bucket precedenti (baseline)
    for (const a of accs) {
        if (a.lastV == null) continue; // volume ignoto → resta 0, baseline invariato
        const base = prevV ?? a.firstV; // primo bucket noto: delta intra-bucket
        a.candle.v = base == null ? 0 : Math.max(0, a.lastV - base);
        prevV = a.lastV;
    }
    const out = accs.map((a) => a.candle);
    return out.length > maxBuckets ? out.slice(out.length - maxBuckets) : out;
}

// VWAP CUMULATO sulla finestra visibile: vwap_i = Σ_{j≤i}(typical_j·v_j) / Σ_{j≤i} v_j,
// con typical = (h+l+c)/3. null finché Σv = 0: MAI inventare un VWAP senza volume.
export function vwapSeries(candles: ReadonlyArray<CandleV>): Array<number | null> {
    const out: Array<number | null> = [];
    let sumPV = 0;
    let sumV = 0;
    for (const c of candles) {
        const v = Number.isFinite(c.v) && c.v > 0 ? c.v : 0;
        if (v > 0) {
            sumPV += ((c.h + c.l + c.c) / 3) * v;
            sumV += v;
        }
        out.push(sumV > 0 ? sumPV / sumV : null);
    }
    return out;
}
