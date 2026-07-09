// ============================================================================
// depthFlow.ts — profondità totale del book e flusso di denaro (roadmap D31).
// Matematica PURA: nessun I/O, nessun React. Il componente campiona il book a
// ogni update e chiede qui totali, cumulate e delta di flusso nella finestra.
// ============================================================================

export interface DepthSample {
    t: number;     // epoch ms del campione
    back: number;  // € totali disponibili lato BACK
    lay: number;   // € totali disponibili lato LAY
}

// Somma delle size di un lato del book ([[price,size],...]).
// Livelli malformati o size non finite/negative → ignorati: il totale è denaro
// mostrato a schermo, MAI NaN.
export function sideTotals(levels: ReadonlyArray<readonly [number, number]> | null | undefined): number {
    if (!Array.isArray(levels)) return 0;
    let tot = 0;
    for (const lv of levels) {
        if (!Array.isArray(lv)) continue;
        const size = lv[1];
        if (!Number.isFinite(size) || size < 0) continue;
        tot += size;
    }
    return tot;
}

// Livelli con cumulata progressiva dal best (primo livello) per le barre di depth.
// Livelli con prezzo o size non finiti → saltati senza rompere la cumulata.
export function cumulativeLevels(
    levels: ReadonlyArray<readonly [number, number]> | null | undefined,
): Array<{ price: number; size: number; cum: number }> {
    if (!Array.isArray(levels)) return [];
    const out: Array<{ price: number; size: number; cum: number }> = [];
    let cum = 0;
    for (const lv of levels) {
        if (!Array.isArray(lv)) continue;
        const [price, size] = lv;
        if (!Number.isFinite(price) || !Number.isFinite(size)) continue;
        cum += size;
        out.push({ price, size, cum });
    }
    return out;
}

// Appende un campione al ring buffer (MUTA il buffer, FIFO cap default 600).
// Appende SEMPRE anche se back/lay sono invariati (serve la storia temporale per
// il delta); se t <= ultimo t sostituisce l'ultimo (il buffer resta monotono).
export function pushDepthSample(buf: DepthSample[], t: number, back: number, lay: number, cap = 600): void {
    if (!Number.isFinite(t) || !Number.isFinite(back) || !Number.isFinite(lay)) return;
    const last = buf[buf.length - 1];
    if (last && t <= last.t) {
        buf[buf.length - 1] = { t, back, lay };
        return;
    }
    buf.push({ t, back, lay });
    if (buf.length > cap) buf.splice(0, buf.length - cap);
}

// Delta di flusso per lato negli ultimi windowMs: (campione più recente) −
// (campione più recente con t <= now−windowMs). Se NESSUN campione è così
// vecchio → null: storia insufficiente, la UI mostra "—", MAI un delta inventato.
export function depthDelta(
    buf: ReadonlyArray<DepthSample>,
    now: number,
    windowMs: number,
): { back: number; lay: number } | null {
    if (!Number.isFinite(now) || !Number.isFinite(windowMs)) return null;
    if (buf.length === 0) return null;
    const cutoff = now - windowMs;
    // Il buffer è monotono per t (pushDepthSample lo garantisce): scansione
    // dal fondo per trovare la baseline più recente con t <= cutoff.
    let base: DepthSample | null = null;
    for (let i = buf.length - 1; i >= 0; i--) {
        if (buf[i].t <= cutoff) { base = buf[i]; break; }
    }
    if (!base) return null;
    const latest = buf[buf.length - 1];
    return { back: latest.back - base.back, lay: latest.lay - base.lay };
}
