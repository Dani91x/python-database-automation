// ============================================================================
// orderFlow.ts — F44: order-flow analytics (muri finti / shift WOM / picchi di
// volume) — matematica PURA, nessun I/O, nessun React.
//
// ONESTÀ (money-critical): queste sono detezioni STATISTICHE su ciò che il book
// mostra — INDIZI, mai prove. Un "muro finto" (denaro grosso che appare e sparisce
// senza essere consumato dai trade) può anche essere un ritiro legittimo; la UI
// deve presentarli come segnali di attenzione, MAI come certezze, e non deve mai
// bloccare un'azione dell'utente. Storia insufficiente → null/[] — mai inventare.
//
// Fonte dati: gli stessi update del ladder stream già ingeriti dal DepthPanel
// (back/lay = [[price,size],...] best-first; trd = [[price,volume_CUMULATO],...]).
// ============================================================================

export interface FlowSnap {
    t: number;                          // epoch ms del campione
    back: ReadonlyMap<number, number>;  // price → size disponibile lato BACK
    lay: ReadonlyMap<number, number>;   // price → size disponibile lato LAY
    trd: ReadonlyMap<number, number>;   // price → volume TRADATO cumulato
    trdTotal: number;                   // Σ volume tradato (cumulato) su tutti i prezzi
    backTop: number;                    // Σ size dei primi 3 livelli BACK (per WOM)
    layTop: number;                     // Σ size dei primi 3 livelli LAY
}

export interface FlowState {
    snaps: FlowSnap[]; // ring FIFO, monotono per t
}

export function newFlowState(): FlowState {
    return { snaps: [] };
}

type Levels = ReadonlyArray<readonly [number, number]> | null | undefined;

function toMap(levels: Levels): Map<number, number> {
    const m = new Map<number, number>();
    if (!Array.isArray(levels)) return m;
    for (const lv of levels) {
        if (!Array.isArray(lv)) continue;
        const [price, size] = lv;
        if (!Number.isFinite(price) || !Number.isFinite(size) || size < 0) continue;
        m.set(price, size);
    }
    return m;
}

function topN(levels: Levels, n = 3): number {
    if (!Array.isArray(levels)) return 0;
    let tot = 0;
    let k = 0;
    for (const lv of levels) {
        if (!Array.isArray(lv)) continue;
        const size = lv[1];
        if (!Number.isFinite(size) || size < 0) continue;
        tot += size;
        if (++k >= n) break;
    }
    return tot;
}

/** Appende un campione del book (MUTA lo stato, FIFO cap default 150 ≈ 2.5 min @1Hz).
 *  t non monotono → sostituisce l'ultimo (stesso contratto di pushDepthSample). */
export function pushFlowSample(
    state: FlowState, t: number, back: Levels, lay: Levels, trd: Levels, cap = 150,
): void {
    if (!Number.isFinite(t)) return;
    const trdMap = toMap(trd);
    let trdTotal = 0;
    for (const v of trdMap.values()) trdTotal += v;
    const snap: FlowSnap = {
        t, back: toMap(back), lay: toMap(lay), trd: trdMap, trdTotal,
        backTop: topN(back), layTop: topN(lay),
    };
    const last = state.snaps[state.snaps.length - 1];
    if (last && t <= last.t) {
        state.snaps[state.snaps.length - 1] = snap;
    } else {
        state.snaps.push(snap);
    }
    // cap SEMPRE applicato (anche sul replace: contratto uniforme del ring)
    if (state.snaps.length > cap) state.snaps.splice(0, state.snaps.length - cap);
}

// ---------------------------------------------------------------------------
// 1) MURI FINTI — size grossa che sparisce SENZA essere consumata dai trade
// ---------------------------------------------------------------------------
export interface PulledWall {
    side: 'back' | 'lay';
    price: number;
    /** picco di size osservato nella finestra (€). */
    peak: number;
    /** quanto è sparito dal picco (€). */
    dropped: number;
    /** quanto è stato TRADATO a quel prezzo nella stessa finestra (€):
     *  se ≪ dropped, il denaro è stato RITIRATO, non consumato. */
    traded: number;
}

export interface PulledWallOpts {
    windowMs?: number;      // finestra di osservazione (default 15s)
    minWall?: number;       // size minima del picco per contare come "muro" (€, default 150)
    minDropFrac?: number;   // frazione del picco sparita per segnalare (default 0.7)
    maxTradedFrac?: number; // trade ammessi come frazione del drop (default 0.25)
}

/** Rileva i "muri" spariti senza consumo nella finestra. Ordinati per drop
 *  decrescente, max 3 per lato (i più grossi: il resto è rumore). */
export function detectPulledWalls(
    state: FlowState, now: number, opts: PulledWallOpts = {},
): PulledWall[] {
    const windowMs = opts.windowMs ?? 15_000;
    const minWall = opts.minWall ?? 150;
    const minDropFrac = opts.minDropFrac ?? 0.7;
    const maxTradedFrac = opts.maxTradedFrac ?? 0.25;
    const snaps = state.snaps;
    if (snaps.length < 2 || !Number.isFinite(now)) return [];
    const inWin = snaps.filter(s => s.t >= now - windowMs && s.t <= now);
    if (inWin.length < 2) return [];
    const latest = inWin[inWin.length - 1];
    const first = inWin[0];
    const out: PulledWall[] = [];
    for (const side of ['back', 'lay'] as const) {
        // prezzi visti nella finestra su questo lato
        const prices = new Set<number>();
        for (const s of inWin) for (const p of s[side].keys()) prices.add(p);
        for (const price of prices) {
            let peak = 0;
            for (const s of inWin) peak = Math.max(peak, s[side].get(price) ?? 0);
            if (peak < minWall) continue;
            const current = latest[side].get(price) ?? 0;
            const dropped = peak - current;
            if (dropped < minDropFrac * peak) continue;
            // trade a QUEL prezzo nella finestra (il trd è cumulato → delta ≥ 0)
            const traded = Math.max(0, (latest.trd.get(price) ?? 0) - (first.trd.get(price) ?? 0));
            if (traded > maxTradedFrac * dropped) continue; // consumato: mercato vero
            out.push({ side, price, peak, dropped, traded });
        }
    }
    out.sort((a, b) => b.dropped - a.dropped);
    return out.slice(0, 3);
}

// ---------------------------------------------------------------------------
// 2) SHIFT WOM — sbilanciamento vicino al best che cambia bruscamente
// ---------------------------------------------------------------------------
/** Shift del WOM (top-3 livelli) in punti percentuali sulla finestra: WOM(now) −
 *  WOM(baseline). Positivo = pressione BACK in aumento. null = storia/book
 *  insufficienti (mai un delta inventato). */
export function womShift(
    state: FlowState, now: number, windowMs = 30_000,
): number | null {
    const snaps = state.snaps;
    if (snaps.length === 0 || !Number.isFinite(now)) return null;
    const cutoff = now - windowMs;
    let base: FlowSnap | null = null;
    for (let i = snaps.length - 1; i >= 0; i--) {
        if (snaps[i].t <= cutoff) { base = snaps[i]; break; }
    }
    if (!base) return null;
    const latest = snaps[snaps.length - 1];
    const womOf = (s: FlowSnap): number | null => {
        const tot = s.backTop + s.layTop;
        return tot > 0 ? (s.backTop / tot) * 100 : null;
    };
    const a = womOf(base);
    const b = womOf(latest);
    if (a == null || b == null) return null;
    return b - a;
}

// ---------------------------------------------------------------------------
// 3) PICCO DI VOLUME — tradato recente vs finestra precedente
// ---------------------------------------------------------------------------
export interface TradeSpike {
    recent: number;    // € tradati nell'ultima finestra
    baseline: number;  // € tradati nella finestra PRECEDENTE (stessa ampiezza)
    ratio: number;     // recent / baseline (Infinity se baseline 0 e recent > 0)
}

/** Volume tradato nell'ultima finestra vs la precedente. null = storia
 *  insufficiente (serve un campione più vecchio di 2 finestre). */
export function tradeSpike(
    state: FlowState, now: number, windowMs = 60_000,
): TradeSpike | null {
    const snaps = state.snaps;
    if (snaps.length === 0 || !Number.isFinite(now)) return null;
    const at = (cutoff: number): FlowSnap | null => {
        let found: FlowSnap | null = null;
        for (let i = snaps.length - 1; i >= 0; i--) {
            if (snaps[i].t <= cutoff) { found = snaps[i]; break; }
        }
        return found;
    };
    const latest = snaps[snaps.length - 1];
    const oneAgo = at(now - windowMs);
    const twoAgo = at(now - 2 * windowMs);
    if (!oneAgo || !twoAgo) return null;
    const recent = Math.max(0, latest.trdTotal - oneAgo.trdTotal);
    const baseline = Math.max(0, oneAgo.trdTotal - twoAgo.trdTotal);
    const ratio = baseline > 0 ? recent / baseline : (recent > 0 ? Infinity : 0);
    return { recent, baseline, ratio };
}

// ---------------------------------------------------------------------------
// Soglie UI (documentate: sotto queste soglie NON si mostra nulla — niente rumore)
// ---------------------------------------------------------------------------
export const WOM_SHIFT_ALERT_PP = 25;    // |shift| ≥ 25 punti percentuali in 30s
export const SPIKE_MIN_RATIO = 3;        // volume ≥ 3× la finestra precedente...
export const SPIKE_MIN_EUR = 200;        // ...e almeno €200 (mai spike su spiccioli)
