// ============================================================================
// engine.ts — Scalper AVERAGING-DOWN con cancel/replace (dossier utente 2026-07-16).
//
// Strategia (back-first): apre BACK a mercato, piazza il LAY di chiusura al tick
// di break-even dell'aggregato (il più ALTO profittevole — scansione DISCENDENTE
// dal prezzo corrente, §5-6 del dossier). Se il prezzo va CONTRO di 1+ tick:
// cancel del lay (immediato) + nuova gamba BACK da 25 + nuovo lay ricalcolato
// (place soggetto a bet delay in-play). A maxLegs raggiunto e nuovo tick contro:
// force-flat a mercato. Variante mirror (lay-first) simmetrica.
//
// I FILL non sono simulati qui: ogni ordine è risolto da simulateOrder di
// src/lib/matching.ts (taker book-walk + maker con coda FIFO, cap Δtv, trigger
// trd per-prezzo, bet delay 5s in-play, LAPSE su sospensione) sui frame REALI.
//
// P&L per ciclo = min(esito_win, esito_lose) dopo l'hedge: conservativo, nessun
// hindsight. Commissione 5% sul green positivo del ciclo.
// ============================================================================

import {
    simulateOrder, tickUp, tickDown, roundToTick,
    type BookSnapshot, type OrderRequest, type ResolvedOrder, type OrderSide,
} from '../../src/lib/matching';
import { tickIdx } from './ticks';

export interface SelFrame extends BookSnapshot {
    inplay: boolean;
}

export interface EngineConfig {
    stake: number;              // stake per gamba (25)
    stakeSeq?: number[];        // variante §10: stake per gamba n-esima (default piatto)
    maxLegs: number;            // gambe massime prima del force-flat (4)
    direction: 'back' | 'lay';  // back-first (primario) o mirror lay-first
    commission: number;         // 0.05 sul green positivo del ciclo
    target: number;             // target-stop di fase (+1€)
    greenEps: number;           // epsilon sul green (0.01)
    entryTtlMs: number;         // cancel dell'entry non abbinata dopo TTL
    closeTtlMs: number;         // cancel/retry della chiusura forzata dopo TTL
    delayMs: number;            // bet delay in-play (5000)
    spreadMaxTicks: number;     // gate apertura: spread massimo
    depthLevels: number;        // gate apertura: livelli sommati per la profondità
    minDepth: number;           // gate apertura: profondità minima per lato (>= stake)
    forceFlatCross: number;     // tick oltre il best opposto per il taker di emergenza
    maxEntryRetries: number;    // entry a vuoto consecutive prima di arrendersi
    openUntilTs?: number;       // dopo questo istante niente NUOVI cicli (la gestione continua)
    addSpacingTicks?: number;   // tick contro necessari per aggiungere una gamba (default 1)
}

export const DEFAULT_CONFIG: EngineConfig = {
    stake: 25,
    maxLegs: 4,
    direction: 'back',
    commission: 0.05,
    target: 1.0,
    greenEps: 0.01,
    entryTtlMs: 10_000,
    closeTtlMs: 10_000,
    delayMs: 5_000,
    spreadMaxTicks: 3,
    depthLevels: 3,
    minDepth: 25,
    forceFlatCross: 5,
    maxEntryRetries: 5,
};

// Un abbinamento reale della posizione (back o lay, prezzo del fill).
interface PosFill { side: OrderSide; price: number; size: number; }

export interface CycleResult {
    openTs: number;
    closeTs: number;
    legs: number;               // gambe di entry abbinate nel ciclo
    pnl: number;                // netto commissione, min(win, lose)
    kind: 'green' | 'force_flat' | 'phase_end' | 'settled';
    maxExposure: number;        // Σ stake gambe a rischio nel ciclo
}

export interface PhaseResult {
    cycles: CycleResult[];
    pnl: number;
    targetReached: boolean;
    targetTs: number | null;
    greens: number;
    forceFlats: number;
    settled: number;            // cicli chiusi a settlement (posizione non chiudibile)
    maxDrawdown: number;        // minimo del P&L cumulato di fase
    maxExposure: number;
    skippedNoLiquidity: boolean;// true se il gate non ha MAI aperto un ciclo
    framesUsed: number;
    spanMs: number;
}

// ------------------------------------------------------------------- utilità
function bestOf(levels: ReadonlyArray<readonly [number, number]>): readonly [number, number] | null {
    for (const lvl of levels) {
        if (lvl && Number.isFinite(lvl[0]) && Number.isFinite(lvl[1]) && lvl[1] > 0) return lvl;
    }
    return null;
}

function depthSum(levels: ReadonlyArray<readonly [number, number]>, n: number): number {
    let s = 0, k = 0;
    for (const lvl of levels) {
        if (!lvl || !Number.isFinite(lvl[1])) continue;
        s += Math.max(0, lvl[1]);
        if (++k >= n) break;
    }
    return s;
}

// Esiti della posizione: win = la selezione VINCE, lose = PERDE.
function outcomes(fills: ReadonlyArray<PosFill>): { win: number; lose: number } {
    let win = 0, lose = 0;
    for (const f of fills) {
        if (f.side === 'back') { win += f.size * (f.price - 1); lose -= f.size; }
        else { win -= f.size * (f.price - 1); lose += f.size; }
    }
    return { win, lose };
}

// Stake dell'hedge di chiusura a quota x: azzera la differenza win-lose.
// d>0 → serve un LAY di d/x; d<0 → serve un BACK di |d|/x.
function hedgeAt(fills: ReadonlyArray<PosFill>, x: number): { side: OrderSide; stake: number; green: number } {
    const { win, lose } = outcomes(fills);
    const d = win - lose;
    const stake = Math.abs(d) / x;
    const green = d > 0 ? lose + stake : win + stake * (x - 1);
    return { side: d > 0 ? 'lay' : 'back', stake, green };
}

// Green a chiusura COMPLETA a quota x (per la scansione del BE).
function greenAt(fills: ReadonlyArray<PosFill>, x: number): number {
    return hedgeAt(fills, x).green;
}

// BE tick (§5): back-first scende DAL prezzo corrente (primo = il più alto
// profittevole); lay-first sale. Ritorna null se nessun tick è profittevole
// entro maxScan tick (posizione irrecuperabile con un solo storno).
function beTick(
    fills: ReadonlyArray<PosFill>, fromPrice: number, dir: 'back' | 'lay', eps: number,
): number | null {
    let x = roundToTick(fromPrice);
    for (let k = 0; k < 400; k++) {
        if (greenAt(fills, x) > eps) return x;
        const next = dir === 'back' ? tickDown(x) : tickUp(x);
        if (next === x) return null; // estremo del ladder
        x = next;
    }
    return null;
}

// ts del fill che COMPLETA l'ordine (cumulato >= richiesto − eps), o null.
function fullMatchTs(r: ResolvedOrder, eps = 0.01): number | null {
    let cum = 0;
    for (const f of r.fills) {
        cum += f.size;
        if (cum >= r.requested - eps) return f.ts;
    }
    return null;
}

// ---------------------------------------------------------------- fase runner
/**
 * runPhase — esegue lo scalper su UNA selezione per UNA fase (pre o in-play).
 *
 * @param frames  frame della selezione, ordinati per ts, GIÀ filtrati per fase
 * @param cfg     configurazione
 * @param settleWin true se la selezione ha VINTO il mercato (per il fallback
 *                  settlement di posizioni non chiudibili); null = ignoto → la
 *                  posizione residua viene valutata all'esito PEGGIORE.
 */
export function runPhase(
    frames: ReadonlyArray<SelFrame>,
    cfg: EngineConfig,
    settleWin: boolean | null,
): PhaseResult {
    const res: PhaseResult = {
        cycles: [], pnl: 0, targetReached: false, targetTs: null,
        greens: 0, forceFlats: 0, settled: 0, maxDrawdown: 0, maxExposure: 0,
        skippedNoLiquidity: true, framesUsed: frames.length,
        spanMs: frames.length ? frames[frames.length - 1].ts - frames[0].ts : 0,
    };
    if (frames.length < 2) return res;
    const phaseEnd = frames[frames.length - 1].ts;
    const dir = cfg.direction;

    // lato "contro": per back-first il prezzo va contro quando il best BACK sale;
    // per lay-first quando il best LAY scende.
    const advSide = dir === 'back' ? 'back' : 'lay';

    let i = 0;
    let fills: PosFill[] = [];
    let legPrices: number[] = [];      // prezzo (tick) dell'ultima gamba per il trigger
    let cycleOpenTs = 0;
    let cycleExposure = 0;
    let entryMisses = 0;
    // add-leg saturato: dopo maxEntryRetries miss consecutivi nel ciclo smettiamo
    // di inseguire (il book non ci fa entrare) e restiamo in attesa dello storno
    // col lay al BE — NON si force-flatta pagando spread per un miss di entry.
    let addSaturated = false;
    // ultimo book USABILE visto (per il mark-to-market di posizioni non chiudibili:
    // niente settlement all'esito reale = niente hindsight)
    let lastMark: { lay: number | null; back: number | null; ltp: number | null } =
        { lay: null, back: null, ltp: null };
    const noteMark = (b: SelFrame): void => {
        if ((b.status ?? '').toUpperCase() !== 'OPEN') return;
        const bb = bestOf(b.back), bl = bestOf(b.lay);
        if (bb) lastMark.back = bb[0];
        if (bl) lastMark.lay = bl[0];
        if (b.ltp != null && Number.isFinite(b.ltp)) lastMark.ltp = b.ltp;
    };

    const legStake = (n: number): number =>
        cfg.stakeSeq && cfg.stakeSeq.length > n ? cfg.stakeSeq[n] : cfg.stake;

    // riferimento del trigger: per back-first il fill PEGGIORE è il più alto;
    // per lay-first (mirror) il più basso.
    const legRefPrice = (fs: ReadonlyArray<PosFill>): number =>
        roundToTick(dir === 'back'
            ? Math.max(...fs.map(f => f.price))
            : Math.min(...fs.map(f => f.price)));

    // indice dell'ultimo frame con ts <= t (per lo slice di simulateOrder)
    const idxAt = (t: number, lo: number): number => {
        let k = lo;
        while (k + 1 < frames.length && frames[k + 1].ts <= t) k++;
        return k;
    };

    const resolveOrder = (req: OrderRequest, fromIdx: number): ResolvedOrder =>
        simulateOrder(req, frames.slice(Math.max(0, fromIdx)) as BookSnapshot[], phaseEnd);

    // esegue un ordine di entry (taker + resto maker con TTL) dal frame k.
    // Ritorna i fill reali e l'indice del frame successivo all'ultimo evento.
    const doEntry = (k: number, side: OrderSide, stake: number): { fills: PosFill[]; nextIdx: number } => {
        const b = frames[k];
        const best = side === 'back' ? bestOf(b.back) : bestOf(b.lay);
        if (!best) return { fills: [], nextIdx: k + 1 };
        const req: OrderRequest = {
            side, limitPrice: best[0], stake,
            placedTs: b.ts, inPlay: b.inplay, delayMs: cfg.delayMs,
            persistence: 'LAPSE',
            cancelledTs: b.ts + (b.inplay ? cfg.delayMs : 0) + cfg.entryTtlMs,
        };
        const r = resolveOrder(req, k);
        const got: PosFill[] = r.fills.map(f => ({ side, price: f.price, size: f.size }));
        const lastTs = r.fills.length ? r.fills[r.fills.length - 1].ts : (req.cancelledTs as number);
        return { fills: got, nextIdx: idxAt(Math.min(lastTs, phaseEnd), k) + 1 };
    };

    // chiusura aggressiva a mercato (force-flat / fine fase): taker che attraversa
    // lo spread, con retry a TTL finché la posizione non è piatta o i frame finiscono.
    const closeAtMarket = (k: number, kind: CycleResult['kind']): number => {
        let j = k;
        while (j < frames.length) {
            const b = frames[j];
            noteMark(b);
            const st = (b.status ?? '').toUpperCase();
            const { win, lose } = outcomes(fills);
            if (Math.abs(win - lose) < 0.05) break; // piatta (residuo trascurabile)
            if (st !== 'OPEN') { j++; continue; }
            const need = hedgeAt(fills, 2); // side dal segno (x irrilevante per il lato)
            const oppBest = need.side === 'lay' ? bestOf(b.lay) : bestOf(b.back);
            if (!oppBest) { j++; continue; }
            const limit = need.side === 'lay'
                ? tickUp(oppBest[0], cfg.forceFlatCross)
                : tickDown(oppBest[0], cfg.forceFlatCross);
            const h = hedgeAt(fills, oppBest[0]);
            if (h.stake < 0.01) break;
            const req: OrderRequest = {
                side: need.side, limitPrice: limit, stake: h.stake,
                placedTs: b.ts, inPlay: b.inplay, delayMs: cfg.delayMs,
                persistence: 'LAPSE',
                cancelledTs: b.ts + (b.inplay ? cfg.delayMs : 0) + cfg.closeTtlMs,
            };
            const r = resolveOrder(req, j);
            for (const f of r.fills) fills.push({ side: need.side, price: f.price, size: f.size });
            const lastTs = r.fills.length ? r.fills[r.fills.length - 1].ts : (req.cancelledTs as number);
            j = idxAt(Math.min(lastTs, phaseEnd), j) + 1;
        }
        settleCycle(j >= frames.length ? phaseEnd : frames[Math.min(j, frames.length - 1)].ts, kind);
        return j;
    };

    // chiude il ciclo corrente: P&L conservativo min(win, lose); se la posizione
    // NON è piatta (settlement) usa l'esito reale se noto, altrimenti il peggiore.
    const settleCycle = (ts: number, kind: CycleResult['kind']): void => {
        const { win, lose } = outcomes(fills);
        const flat = Math.abs(win - lose) < 0.05;
        let gross: number;
        if (flat) gross = Math.min(win, lose);
        else {
            // posizione NON piatta: mark-to-market al prezzo ESEGUIBILE dell'ultimo
            // book usabile (mai l'esito reale del match — sarebbe hindsight).
            const d = win - lose;
            const mark = d > 0
                ? (lastMark.lay ?? lastMark.ltp)     // serve un lay → prezzo lay
                : (lastMark.back ?? lastMark.ltp);   // serve un back → prezzo back
            if (mark != null && mark > 1) gross = hedgeAt(fills, roundToTick(mark)).green;
            else if (settleWin !== null) gross = settleWin ? win : lose; // mai visto un book: esito reale
            else gross = Math.min(win, lose);
            kind = 'settled';
        }
        const net = gross > 0 ? gross * (1 - cfg.commission) : gross;
        res.cycles.push({ openTs: cycleOpenTs, closeTs: ts, legs: legPrices.length, pnl: net, kind, maxExposure: cycleExposure });
        res.pnl += net;
        if (kind === 'green') res.greens++;
        else if (kind === 'force_flat') res.forceFlats++;
        else if (kind === 'settled') res.settled++;
        res.maxDrawdown = Math.min(res.maxDrawdown, res.pnl);
        res.maxExposure = Math.max(res.maxExposure, cycleExposure);
        if (!res.targetReached && res.pnl >= cfg.target) { res.targetReached = true; res.targetTs = ts; }
        fills = []; legPrices = []; cycleExposure = 0; entryMisses = 0; addSaturated = false;
    };

    // gate di apertura ciclo (liquidità + spread + mercato aperto)
    const canOpen = (b: SelFrame): boolean => {
        if ((b.status ?? '').toUpperCase() !== 'OPEN') return false;
        const bb = bestOf(b.back), bl = bestOf(b.lay);
        if (!bb || !bl) return false;
        // spazio sul lato PROFITTO: a 1.01 (back) o al tetto (lay) il green è
        // impossibile per costruzione → non si apre mai lì.
        if (dir === 'back' && bb[0] < 1.02 - 1e-9) return false;
        if (dir === 'lay' && bl[0] > 990) return false;
        try {
            if (tickIdx(bl[0]) - tickIdx(bb[0]) > cfg.spreadMaxTicks) return false;
        } catch { return false; }
        return depthSum(b.back, cfg.depthLevels) >= cfg.minDepth
            && depthSum(b.lay, cfg.depthLevels) >= cfg.minDepth;
    };

    // trigger "tick contro" al frame b (solo mercato OPEN)
    const isAdverse = (b: SelFrame): boolean => {
        if ((b.status ?? '').toUpperCase() !== 'OPEN' || legPrices.length === 0) return false;
        const best = bestOf(advSide === 'back' ? b.back : b.lay);
        if (!best) return false;
        try {
            const cur = tickIdx(best[0]);
            const ref = tickIdx(legPrices[legPrices.length - 1]);
            const spacing = cfg.addSpacingTicks ?? 1;
            return dir === 'back' ? cur - ref >= spacing : ref - cur >= spacing;
        } catch { return false; }
    };

    // ------------------------------------------------------------- loop fase
    while (i < frames.length && !res.targetReached) {
        noteMark(frames[i]);
        // ---- FLAT: cerca un frame apribile
        if (fills.length === 0) {
            if (cfg.openUntilTs != null && frames[i].ts > cfg.openUntilTs) break; // finestra ingressi chiusa
            if (!canOpen(frames[i])) { i++; continue; }
            res.skippedNoLiquidity = false;
            cycleOpenTs = frames[i].ts;
            const e = doEntry(i, dir, legStake(0));
            i = e.nextIdx;
            if (e.fills.length === 0) {
                fills = []; legPrices = [];
                if (++entryMisses > cfg.maxEntryRetries * 4) break; // book inagibile
                continue;
            }
            entryMisses = 0;
            fills = e.fills;
            legPrices = [legRefPrice(e.fills)];
            cycleExposure = e.fills.reduce((a, f) => a + f.size, 0);
            continue;
        }

        // ---- IN POSIZIONE, frame corrente non OPEN → avanza (lay già lapsato)
        const cur = frames[i];
        const st = (cur.status ?? '').toUpperCase();
        if (st !== 'OPEN') { i++; continue; }

        // ---- trigger contro PRIMA di (ri)piazzare la chiusura
        if (isAdverse(cur) && !addSaturated) {
            if (legPrices.length >= cfg.maxLegs) { i = closeAtMarket(i, 'force_flat'); continue; }
            const e = doEntry(i, dir, legStake(legPrices.length));
            i = e.nextIdx;
            if (e.fills.length > 0) {
                fills.push(...e.fills);
                legPrices.push(legRefPrice(e.fills));
                cycleExposure += e.fills.reduce((a, f) => a + f.size, 0);
                entryMisses = 0;
            } else if (++entryMisses > cfg.maxEntryRetries) {
                addSaturated = true; // il book non ci fa accumulare: si aspetta lo storno
            }
            continue;
        }

        // ---- piazza la chiusura al BE e aspetta il primo evento
        const ref = bestOf(dir === 'back' ? cur.back : cur.lay);
        if (!ref) { i++; continue; }
        const be = beTick(fills, ref[0], dir, cfg.greenEps);
        if (be === null) { i = closeAtMarket(i, 'force_flat'); continue; }
        // stake dell'hedge sul prezzo di fill ATTESO: se il BE attraversa il best
        // opposto, il taker riempie al best (migliore del limite) → stake su quello.
        const opp = bestOf(dir === 'back' ? cur.lay : cur.back);
        const expPx = opp === null ? be : (dir === 'back' ? Math.min(be, opp[0]) : Math.max(be, opp[0]));
        const h = hedgeAt(fills, expPx);
        if (h.stake < 0.01) { settleCycle(cur.ts, 'green'); continue; }
        const closeReq: OrderRequest = {
            side: h.side, limitPrice: be, stake: h.stake,
            placedTs: cur.ts, inPlay: cur.inplay, delayMs: cfg.delayMs,
            persistence: 'LAPSE',
        };
        const open = resolveOrder(closeReq, i);
        const fullTs = fullMatchTs(open);

        // primo evento successivo: trigger contro / sospensione / full match / fine fase
        let evTs = phaseEnd + 1;
        let evKind: 'full' | 'adverse' | 'susp' | 'end' = 'end';
        if (fullTs !== null && fullTs <= phaseEnd) { evTs = fullTs; evKind = 'full'; }
        for (let j = i + 1; j < frames.length && frames[j].ts < evTs; j++) {
            const f = frames[j];
            const s = (f.status ?? '').toUpperCase();
            if (s !== 'OPEN') { evTs = f.ts; evKind = 'susp'; break; }
            if (isAdverse(f)) { evTs = f.ts; evKind = 'adverse'; break; }
        }

        if (evKind === 'full') {
            for (const f of open.fills) fills.push({ side: h.side, price: f.price, size: f.size });
            settleCycle(evTs, 'green');
            i = idxAt(evTs, i) + 1;
            continue;
        }

        // cancel (immediato) del resto al momento dell'evento; i fill parziali
        // maturati PRIMA dell'evento restano in posizione.
        const cancelled = resolveOrder({ ...closeReq, cancelledTs: evTs }, i);
        for (const f of cancelled.fills) fills.push({ side: h.side, price: f.price, size: f.size });
        // il parziale può aver già chiuso tutto (raro: hedge quasi completo)
        {
            const { win, lose } = outcomes(fills);
            if (Math.abs(win - lose) < 0.02 && fills.length > 0) {
                settleCycle(evTs, 'green');
                i = idxAt(evTs, i) + 1;
                continue;
            }
        }
        if (evKind === 'end') { i = frames.length; break; }
        i = idxAt(evTs, i); // il frame dell'evento verrà gestito in testa al loop
        if (frames[i].ts < evTs) i++;
    }

    // fine fase con posizione aperta → chiusura forzata sugli ultimi frame,
    // altrimenti settlement all'esito reale.
    if (fills.length > 0) {
        const { win, lose } = outcomes(fills);
        if (Math.abs(win - lose) >= 0.02) {
            closeAtMarket(Math.min(i, frames.length - 1), 'phase_end');
        } else settleCycle(phaseEnd, 'phase_end');
    }
    return res;
}
