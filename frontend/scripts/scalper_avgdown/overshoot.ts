// overshoot.ts — backtest del FADE POST-GOL (la tecnica pro: "scalping the
// overreactions"). Dopo un gol il mercato riapre con un salto; se ha esagerato,
// il prezzo rientra di qualche tick nei primi minuti. Si entra CONTRO il salto,
// take-profit a +T tick (ordine maker), scratch a −S tick, time-stop.
//
// Uso: npx tsx overshoot.ts <dataDir> <outFile.json>
import { readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import {
    simulateOrder, tickUp, tickDown, roundToTick,
    type BookSnapshot, type OrderRequest, type OrderSide,
} from '../../src/lib/matching';
import { tickIdx } from './ticks';
import type { SelFrame } from './engine';
import { loadEvent, selFrames, selsOf } from './data';

const STAKE = 25;
const COMMISSION = 0.05;
// NB: il recorder NON salva le sospensioni brevi (firma write-on-change sui soli
// best price) → i gol si rilevano dal SALTO di prezzo, non dallo status.
const JUMP_MIN_TICKS = 8;         // salto minimo in ≤ JUMP_WINDOW per firmare un gol
const JUMP_WINDOW_MS = 30_000;
const EPISODE_COOLDOWN_MS = 120_000; // dedupe: 1 episodio per selezione per gol
const TRADABLE = /^(MATCH_ODDS|OVER_UNDER_\d+)$/;

interface Episode {
    reopenIdx: number;            // indice del frame in cui il salto è compiuto
    jumpTicks: number;            // salto firmato in tick (post − pre)
    prePrice: number;
    postPrice: number;
}

function bestOf(levels: ReadonlyArray<readonly [number, number]>): readonly [number, number] | null {
    for (const lvl of levels) {
        if (lvl && Number.isFinite(lvl[0]) && Number.isFinite(lvl[1]) && lvl[1] > 0) return lvl;
    }
    return null;
}

// episodi = salto di prezzo ≥ JUMP_MIN_TICKS entro JUMP_WINDOW (firma del gol),
// con cooldown per non contare lo stesso gol più volte.
function findEpisodes(frames: SelFrame[]): Episode[] {
    const out: Episode[] = [];
    let lastEpisodeTs = -Infinity;
    // serie dei best back con ts (solo frame OPEN in-play con book valido)
    const pts: { ts: number; idx: number; price: number; frameIdx: number }[] = [];
    for (let i = 0; i < frames.length; i++) {
        const fr = frames[i];
        if (!fr.inplay || (fr.status ?? '').toUpperCase() !== 'OPEN') continue;
        const bb = bestOf(fr.back);
        if (!bb) continue;
        try {
            pts.push({ ts: fr.ts, idx: tickIdx(bb[0]), price: bb[0], frameIdx: i });
        } catch { /* fuori griglia */ }
    }
    let lo = 0;
    for (let k = 1; k < pts.length; k++) {
        while (pts[k].ts - pts[lo].ts > JUMP_WINDOW_MS) lo++;
        if (pts[k].ts - lastEpisodeTs < EPISODE_COOLDOWN_MS) continue;
        // estremo della finestra: massimo salto firmato rispetto a k
        let ref = pts[k].idx;
        let refPrice = pts[k].price;
        let jump = 0;
        for (let j = lo; j < k; j++) {
            const d = pts[k].idx - pts[j].idx;
            if (Math.abs(d) > Math.abs(jump)) { jump = d; ref = pts[j].idx; refPrice = pts[j].price; }
        }
        void ref;
        if (Math.abs(jump) >= JUMP_MIN_TICKS) {
            out.push({ reopenIdx: pts[k].frameIdx, jumpTicks: jump, prePrice: refPrice, postPrice: pts[k].price });
            lastEpisodeTs = pts[k].ts;
        }
    }
    return out;
}

interface TradeResult {
    pnl: number;
    exit: 'take_profit' | 'scratch' | 'time_stop' | 'suspended' | 'no_entry';
    entryPrice: number | null;
    jumpTicks: number;
    holdMs: number;
}

function outcomes(fills: { side: OrderSide; price: number; size: number }[]): { win: number; lose: number } {
    let win = 0, lose = 0;
    for (const f of fills) {
        if (f.side === 'back') { win += f.size * (f.price - 1); lose -= f.size; }
        else { win -= f.size * (f.price - 1); lose += f.size; }
    }
    return { win, lose };
}

/**
 * Un trade di fade per un episodio: entra taker CONTRO il salto al reopen,
 * take-profit maker a +T tick, scratch taker a −S tick, chiusura al time-stop.
 */
function runEpisode(
    frames: SelFrame[], ep: Episode, T: number, S: number, timeStopMs: number, settleMs: number,
): TradeResult {
    // ingresso RITARDATO di settleMs (i pro aspettano che la tempesta post-gol
    // si calmi), e solo se il prezzo è ANCORA dislocato ≥ metà salto vs pre-gol.
    const jumpTs = frames[ep.reopenIdx].ts;
    let i0 = -1;
    for (let j = ep.reopenIdx; j < frames.length; j++) {
        const fr = frames[j];
        if (fr.ts < jumpTs + settleMs) continue;
        if ((fr.status ?? '').toUpperCase() !== 'OPEN' || !fr.inplay) continue;
        const bb = bestOf(fr.back);
        const bl = bestOf(fr.lay);
        if (!bb || !bl) continue;
        // gate pro: solo quote basse (liability contenuta), spread stretto, book vero
        if (bb[0] < 1.2 || bl[0] > 4.0) return { pnl: 0, exit: 'no_entry', entryPrice: null, jumpTicks: ep.jumpTicks, holdMs: 0 };
        try {
            if (tickIdx(bl[0]) - tickIdx(bb[0]) > 3) continue;
        } catch { continue; }
        if (bb[1] < 25 || bl[1] < 25) continue;
        try {
            const disp = tickIdx(bb[0]) - tickIdx(roundToTick(ep.prePrice));
            const stillDisplaced = ep.jumpTicks < 0
                ? disp <= Math.ceil(ep.jumpTicks / 2)
                : disp >= Math.ceil(ep.jumpTicks / 2);
            if (!stillDisplaced) return { pnl: 0, exit: 'no_entry', entryPrice: null, jumpTicks: ep.jumpTicks, holdMs: 0 };
        } catch { return { pnl: 0, exit: 'no_entry', entryPrice: null, jumpTicks: ep.jumpTicks, holdMs: 0 }; }
        i0 = j;
        break;
    }
    if (i0 < 0) return { pnl: 0, exit: 'no_entry', entryPrice: null, jumpTicks: ep.jumpTicks, holdMs: 0 };
    const f0 = frames[i0];
    // fade: salto in giù (quota compressa, es. Over dopo gol) → BACK? NO:
    // quota SCESA oltre il giusto → ci aspettiamo che RISALGA → LAY adesso
    // conviene... attenzione ai ruoli: LAY profitta se la quota SALE dopo.
    // salto < 0 (postPrice < prePrice, compressione) → LAY; salto > 0 → BACK.
    const side: OrderSide = ep.jumpTicks < 0 ? 'lay' : 'back';
    const best = side === 'lay' ? bestOf(f0.lay) : bestOf(f0.back);
    if (!best) return { pnl: 0, exit: 'no_entry', entryPrice: null, jumpTicks: ep.jumpTicks, holdMs: 0 };
    const limit = side === 'lay' ? tickUp(best[0], 2) : tickDown(best[0], 2);
    const entryReq: OrderRequest = {
        side, limitPrice: limit, stake: STAKE, placedTs: f0.ts, inPlay: true,
        persistence: 'LAPSE', cancelledTs: f0.ts + 5000 + 10_000,
    };
    const slice = frames.slice(i0) as BookSnapshot[];
    const endTs = frames[frames.length - 1].ts;
    const entry = simulateOrder(entryReq, slice, endTs);
    if (entry.matched < STAKE * 0.5) {
        return { pnl: 0, exit: 'no_entry', entryPrice: null, jumpTicks: ep.jumpTicks, holdMs: 0 };
    }
    const entryPx = roundToTick(entry.avgPrice ?? limit);
    const entryTs = entry.fills[0].ts;
    const fills = entry.fills.map(f => ({ side, price: f.price, size: f.size }));

    // take-profit maker: hedge opposto a ±T tick dal prezzo di entrata
    const tpPx = side === 'lay' ? tickUp(entryPx, T) : tickDown(entryPx, T);
    const hedgeSide: OrderSide = side === 'lay' ? 'back' : 'lay';
    const d0 = outcomes(fills);
    const hedgeStake = Math.abs(d0.win - d0.lose) / tpPx;
    const tpReq: OrderRequest = {
        side: hedgeSide, limitPrice: tpPx, stake: hedgeStake,
        placedTs: entryTs, inPlay: true, persistence: 'LAPSE',
    };
    const tp = simulateOrder(tpReq, slice, endTs);
    let tpFullTs: number | null = null;
    {
        let cum = 0;
        for (const f of tp.fills) { cum += f.size; if (cum >= tpReq.stake - 0.01) { tpFullTs = f.ts; break; } }
    }

    // scratch trigger: prezzo oltre S tick contro; time-stop; sospensione (nuovo gol)
    const scratchPx = side === 'lay' ? tickDown(entryPx, S) : tickUp(entryPx, S);
    let exitTs = entryTs + timeStopMs;
    let exitKind: TradeResult['exit'] = 'time_stop';
    for (let j = i0; j < frames.length; j++) {
        const fr = frames[j];
        if (fr.ts <= entryTs) continue;
        if (fr.ts >= entryTs + timeStopMs) break;
        const st = (fr.status ?? '').toUpperCase();
        if (st !== 'OPEN') { exitTs = fr.ts; exitKind = 'suspended'; break; }
        const b = side === 'lay' ? bestOf(fr.lay) : bestOf(fr.back);
        if (!b) continue;
        try {
            const cur = tickIdx(b[0]);
            const trig = side === 'lay'
                ? cur <= tickIdx(scratchPx)     // quota scesa ancora: il fade ha torto
                : cur >= tickIdx(scratchPx);    // quota salita ancora
            if (trig) { exitTs = fr.ts; exitKind = 'scratch'; break; }
        } catch { /* fuori griglia */ }
    }

    if (tpFullTs !== null && tpFullTs <= exitTs) {
        for (const f of tp.fills) fills.push({ side: hedgeSide, price: f.price, size: f.size });
        const { win, lose } = outcomes(fills);
        const gross = Math.min(win, lose);
        return {
            pnl: gross > 0 ? gross * (1 - COMMISSION) : gross, exit: 'take_profit',
            entryPrice: entryPx, jumpTicks: ep.jumpTicks, holdMs: tpFullTs - entryTs,
        };
    }

    // uscita a mercato (scratch / time-stop / sospensione): cancella il TP e chiudi taker
    const tpCancelled = simulateOrder({ ...tpReq, cancelledTs: exitTs }, slice, endTs);
    for (const f of tpCancelled.fills) fills.push({ side: hedgeSide, price: f.price, size: f.size });
    let closed = false;
    for (let j = i0; j < frames.length && !closed; j++) {
        const fr = frames[j];
        if (fr.ts < exitTs) continue;
        if ((fr.status ?? '').toUpperCase() !== 'OPEN') continue;
        const { win, lose } = outcomes(fills);
        const d = win - lose;
        if (Math.abs(d) < 0.05) { closed = true; break; }
        const cSide: OrderSide = d > 0 ? 'lay' : 'back';
        const cBest = cSide === 'lay' ? bestOf(fr.lay) : bestOf(fr.back);
        if (!cBest) continue;
        const cReq: OrderRequest = {
            side: cSide, limitPrice: cSide === 'lay' ? tickUp(cBest[0], 5) : tickDown(cBest[0], 5),
            stake: Math.abs(d) / cBest[0], placedTs: fr.ts, inPlay: true,
            persistence: 'LAPSE', cancelledTs: fr.ts + 5000 + 10_000,
        };
        const c = simulateOrder(cReq, slice, endTs);
        for (const f of c.fills) fills.push({ side: cSide, price: f.price, size: f.size });
        if (c.remaining < 0.01) closed = true;
        else {
            const skipTo = (cReq.cancelledTs as number);
            while (j + 1 < frames.length && frames[j + 1].ts <= skipTo) j++;
        }
    }
    const { win, lose } = outcomes(fills);
    const gross = Math.min(win, lose); // MTM conservativo se non completamente chiusa
    return {
        pnl: gross > 0 ? gross * (1 - COMMISSION) : gross, exit: exitKind,
        entryPrice: entryPx, jumpTicks: ep.jumpTicks, holdMs: exitTs - entryTs,
    };
}

async function main(): Promise<void> {
    const [dataDir, outFile] = process.argv.slice(2);
    const grid: { T: number; S: number; stop: number; W: number }[] = [];
    for (const T of [2, 3]) for (const S of [3, 5]) for (const W of [30_000, 60_000]) {
        grid.push({ T, S, stop: 180_000, W });
    }

    const results: Record<string, TradeResult[]> = {};
    for (const g of grid) results[`T${g.T}_S${g.S}_W${g.W / 1000}s`] = [];
    let nEpisodes = 0;

    for (const f of readdirSync(dataDir).filter(x => x.endsWith('.jsonl.gz'))) {
        const { meta, snaps } = await loadEvent(path.join(dataDir, f));
        for (const m of meta.markets.filter(m => TRADABLE.test(m.market_type ?? ''))) {
            const raw = snaps.get(m.market_id);
            if (!raw || raw.length < 10) continue;
            for (const sel of selsOf(m)) {
                const frames = selFrames(raw, sel.selection_id);
                if (frames.length < 10) continue;
                const eps = findEpisodes(frames);
                for (const ep of eps) {
                    // gate quota: il fade pro si fa solo dove la liability è contenuta
                    if (ep.postPrice < 1.2 || ep.postPrice > 4.0) continue;
                    const f0 = frames[ep.reopenIdx];
                    const bb = bestOf(f0.back), bl = bestOf(f0.lay);
                    if (!bb || !bl || bb[1] + bl[1] < 25) continue;
                    nEpisodes++;
                    for (const g of grid) {
                        results[`T${g.T}_S${g.S}_W${g.W / 1000}s`].push({
                            ...runEpisode(frames, ep, g.T, g.S, g.stop, g.W),
                        });
                    }
                }
            }
        }
        console.log(`${meta.event.home_name}-${meta.event.away_name}: episodi cumulati ${nEpisodes}`);
    }
    writeFileSync(outFile, JSON.stringify(results));

    console.log(`\nepisodi (selezione×gol) totali: ${nEpisodes}`);
    for (const [k, trades] of Object.entries(results)) {
        const t = trades.filter(x => x.exit !== 'no_entry');
        if (!t.length) continue;
        const pnls = t.map(x => x.pnl).sort((a, b) => a - b);
        const tot = pnls.reduce((a, b) => a + b, 0);
        const tp = t.filter(x => x.exit === 'take_profit').length;
        const scr = t.filter(x => x.exit === 'scratch').length;
        const med = pnls[Math.floor(pnls.length / 2)];
        console.log(`${k.padEnd(14)} n=${t.length} tp=${Math.round(100 * tp / t.length)}% scr=${Math.round(100 * scr / t.length)}% tot=${tot.toFixed(2)} medio=${(tot / t.length).toFixed(3)} mediana=${med.toFixed(3)} peggiore=${pnls[0].toFixed(2)}`);
    }
}

main().catch(err => { console.error(err); process.exit(1); });
