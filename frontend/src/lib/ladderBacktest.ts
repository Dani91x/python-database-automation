// ============================================================================
// ladderBacktest.ts — F42: backtest del LADDER-TRADING sullo storico full-depth
// — matematica PURA sul matching engine fedele (lib/matching). Nessun I/O.
//
// Strategia parametrica classica dello scalping da ladder:
//   ENTRATA maker a best ∓ offset tick (con TTL: se non si abbina, si annulla);
//   USCITA bracket: take-profit maker a entry ± tp tick, stop a entry ∓ stop tick
//   (al tocco: flatten TAKER al book reale → slippage REALE), timeout maxHold.
//
// ONESTÀ (vincoli espliciti richiesti dall'utente — mai un backtest ottimista):
//   * PRE-MATCH: nessun delay. IN-PLAY: bet-delay del matching (5s misurati);
//   * i fill passano TUTTI dal matching engine: maker con coda al proprio prezzo
//     e cap sul volume REALMENTE tradato; taker consuma solo la liquidità
//     VISIBILE (slippage e fill parziali reali);
//   * un trade che non riesce a chiudersi resta APERTO e viene dichiarato
//     ('incomplete'), col worst-case in P&L — mai nascosto;
//   * niente probabilità inventate: il P&L di un round-trip FLAT è certo; se il
//     trade non è flat si riporta il WORST-CASE tra i due esiti.
// ============================================================================
import {
    DEFAULT_DELAY_MS, matchMarketable, roundToTick, simulateOrder, tickDown, tickUp,
    type BookSnapshot, type Fill, type OrderRequest,
} from '@/lib/matching';

export interface LadderBacktestParams {
    side: 'back' | 'lay';       // lato dell'ENTRATA
    entryOffsetTicks: number;   // ≥0: quanto dietro il best entra il maker (0 = join al best)
    tpTicks: number;            // ≥1: take-profit a entry ± tp tick
    stopTicks: number;          // ≥1: stop a entry ∓ stop tick (flatten taker)
    stake: number;              // € per entrata (≥2)
    entryTtlSec: number;        // TTL dell'entrata non abbinata (cancel)
    maxHoldSec: number;         // tempo massimo in posizione (flatten taker)
    everySec: number;           // cadenza tra un tentativo di entrata e il successivo
    phase: 'prematch' | 'inplay' | 'both';
}

export interface BacktestTrade {
    entryTs: number;
    entryPrice: number;         // VWAP dell'entrata
    size: number;               // stake abbinato dell'entrata
    exit: 'tp' | 'stop' | 'timeout' | 'eod';
    exitTs: number | null;
    exitPrice: number | null;   // VWAP dell'uscita (null se nessun fill di uscita)
    /** P&L del round-trip. Flat → certo; non flat → WORST-CASE dei due esiti. */
    pnl: number;
    /** true = il trade NON è tornato flat (dichiarato, mai nascosto). */
    incomplete: boolean;
}

export interface BacktestResult {
    trades: BacktestTrade[];
    attempted: number;          // tentativi di entrata (inclusi i non abbinati)
    unfilled: number;           // entrate mai abbinate (TTL scaduto)
    totalPnl: number;
    wins: number;
    losses: number;
    incomplete: number;         // trade non flat (worst-case in P&L)
}

const r2 = (v: number) => Math.round(v * 100) / 100;

// P&L (if_win, if_lose) da una lista di fill back/lay sulla STESSA selezione.
function pnlOf(fills: ReadonlyArray<{ side: 'back' | 'lay'; f: Fill }>): { ifWin: number; ifLose: number } {
    let ifWin = 0, ifLose = 0;
    for (const { side, f } of fills) {
        if (side === 'back') { ifWin += f.size * (f.price - 1); ifLose -= f.size; }
        else { ifWin -= f.size * (f.price - 1); ifLose += f.size; }
    }
    return { ifWin, ifLose };
}

// ultimo snapshot con ts <= t (null se nessuno)
function snapAt(snaps: ReadonlyArray<BookSnapshot>, t: number): BookSnapshot | null {
    let found: BookSnapshot | null = null;
    for (let i = snaps.length - 1; i >= 0; i--) {
        if (snaps[i].ts <= t) { found = snaps[i]; break; }
    }
    return found;
}

// best del lato a uno snapshot (null se vuoto)
function bestOf(s: BookSnapshot | null, side: 'back' | 'lay'): number | null {
    const p = (side === 'back' ? s?.back : s?.lay)?.[0]?.[0];
    return Number.isFinite(p as number) && (p as number) > 1 ? (p as number) : null;
}

// posizione FLAT = profitto (quasi) uguale sui due esiti
const FLAT_EPS = 0.05;

/** Flatten TAKER "greened": a ogni snapshot utile calcola la size di hedge che
 *  EQUALIZZA i due esiti al best corrente e consuma la liquidità VISIBILE
 *  (slippage reale, anche su più snapshot). MUTA `legs` coi fill di uscita.
 *  Può restare NON flat se la liquidità manca: il chiamante lo dichiara. */
function flattenGreenedTaker(
    snaps: ReadonlyArray<BookSnapshot>,
    legs: Array<{ side: 'back' | 'lay'; f: Fill }>,
    fromTs: number,
    endTs: number,
): void {
    for (const s of snaps) {
        if (s.ts < fromTs) continue;
        if (s.ts > endTs) break;
        const st = (s.status ?? '').toUpperCase();
        if (st === 'SUSPENDED' || st === 'CLOSED') continue; // mai fill a mercato sospeso
        const { ifWin, ifLose } = pnlOf(legs);
        const diff = ifWin - ifLose;
        if (Math.abs(diff) <= FLAT_EPS) return;
        const side: 'back' | 'lay' = diff > 0 ? 'lay' : 'back';
        const p = bestOf(s, side);
        if (p == null) continue;
        const h = Math.abs(diff) / p;                 // size che equalizza al best
        // limite ESTREMO = ordine "a mercato": prende ciò che c'è, al prezzo che c'è
        const limit = side === 'back' ? 1.01 : 1000;
        const m = matchMarketable(side, limit, h, s);
        legs.push(...m.fills.map(f => ({ side, f })));
    }
}

/** Esegue il backtest della strategia su UNA selezione (snapshots ordinati per ts).
 *  `isInplay(ts)` decide fase e bet-delay. Deterministico. */
export function runLadderBacktest(
    snaps: ReadonlyArray<BookSnapshot>,
    params: LadderBacktestParams,
    isInplay: (ts: number) => boolean,
): BacktestResult {
    const trades: BacktestTrade[] = [];
    let attempted = 0;
    let unfilled = 0;
    // guard completo: senza everySec/entryTtlSec/maxHoldSec > 0 il cursore non
    // avanza (cursor += 0) → while infinito che congela la tab. Mai un hang.
    if (snaps.length < 2 || !(params.stake >= 2) || params.tpTicks < 1 || params.stopTicks < 1
        || params.entryOffsetTicks < 0
        || !(params.everySec > 0) || !(params.entryTtlSec > 0) || !(params.maxHoldSec > 0)) {
        return { trades, attempted, unfilled, totalPnl: 0, wins: 0, losses: 0, incomplete: 0 };
    }
    const endTs = snaps[snaps.length - 1].ts;
    const exitSide: 'back' | 'lay' = params.side === 'back' ? 'lay' : 'back';
    let cursor = snaps[0].ts;

    while (cursor < endTs) {
        const s0 = snapAt(snaps, cursor);
        if (!s0) break;
        const inplay = isInplay(cursor);
        const phaseOk = params.phase === 'both'
            || (params.phase === 'inplay' ? inplay : !inplay);
        const st = (s0.status ?? '').toUpperCase();
        const best = bestOf(s0, params.side);
        if (!phaseOk || st === 'SUSPENDED' || st === 'CLOSED' || best == null) {
            cursor += params.everySec * 1000;
            continue;
        }
        attempted += 1;
        // ENTRATA maker: back dietro il best = quota PIÙ ALTA; lay dietro = PIÙ BASSA.
        const entryPrice = roundToTick(params.side === 'back'
            ? tickUp(best, params.entryOffsetTicks)
            : tickDown(best, params.entryOffsetTicks));
        const entryReq: OrderRequest = {
            side: params.side, limitPrice: entryPrice, stake: params.stake,
            placedTs: cursor, inPlay: inplay,
            delayMs: inplay ? DEFAULT_DELAY_MS : 0,               // PRE-MATCH: NESSUN delay
            persistence: 'LAPSE',
            cancelledTs: cursor + params.entryTtlSec * 1000,      // TTL: mai resting eterni
        };
        const entry = simulateOrder(entryReq, snaps, endTs);
        if (entry.matched < 0.01 || entry.fills.length === 0) {
            unfilled += 1;
            cursor += params.everySec * 1000;
            continue;
        }
        const fillTs = entry.fills[entry.fills.length - 1].ts;
        const avgEntry = entry.avgPrice ?? entryPrice;
        const size = r2(entry.matched);

        // USCITA bracket dal momento del fill
        const tpPrice = roundToTick(params.side === 'back'
            ? tickDown(avgEntry, params.tpTicks)   // back→esco in lay a quota più bassa
            : tickUp(avgEntry, params.tpTicks));   // lay→esco in back a quota più alta
        const stopLevel = roundToTick(params.side === 'back'
            ? tickUp(avgEntry, params.stopTicks)
            : tickDown(avgEntry, params.stopTicks));
        const deadline = Math.min(fillTs + params.maxHoldSec * 1000, endTs);

        // stop: primo snapshot dopo il fill in cui il BEST del lato d'uscita tocca lo stop
        let stopTs: number | null = null;
        for (const s of snaps) {
            if (s.ts <= fillTs) continue;
            if (s.ts > deadline) break;
            const b = bestOf(s, exitSide);
            if (b == null) continue;
            const touched = params.side === 'back' ? b >= stopLevel : b <= stopLevel;
            if (touched) { stopTs = s.ts; break; }
        }

        // take-profit MAKER "greened" (size·entry/tp → profitto uguale sui due esiti),
        // annullato allo stop/deadline
        const tpCancelTs = Math.min(stopTs ?? Infinity, deadline);
        const tpSize = r2(size * avgEntry / tpPrice);
        const tpReq: OrderRequest = {
            side: exitSide, limitPrice: tpPrice, stake: tpSize,
            placedTs: fillTs, inPlay: isInplay(fillTs),
            delayMs: isInplay(fillTs) ? DEFAULT_DELAY_MS : 0,
            persistence: 'LAPSE',
            cancelledTs: Number.isFinite(tpCancelTs) ? tpCancelTs : null,
        };
        const tp = simulateOrder(tpReq, snaps, endTs);

        const legs: Array<{ side: 'back' | 'lay'; f: Fill }> = [
            ...entry.fills.map(f => ({ side: params.side, f })),
            ...tp.fills.map(f => ({ side: exitSide, f })),
        ];
        let exit: BacktestTrade['exit'];
        let exitTs: number | null = tp.fills[tp.fills.length - 1]?.ts ?? null;
        const afterTp = pnlOf(legs);
        if (Math.abs(afterTp.ifWin - afterTp.ifLose) <= FLAT_EPS) {
            exit = 'tp';
        } else {
            // stop o timeout: flatten TAKER greened (slippage reale, può restare aperto)
            const from = stopTs ?? deadline;
            exit = stopTs != null ? 'stop' : (deadline < endTs ? 'timeout' : 'eod');
            const before = legs.length;
            flattenGreenedTaker(snaps, legs, from, endTs);
            exitTs = legs.length > before ? legs[legs.length - 1].f.ts : exitTs;
        }

        const { ifWin, ifLose } = pnlOf(legs);
        const flat = Math.abs(ifWin - ifLose) <= FLAT_EPS;
        // ONESTÀ: P&L = WORST-CASE dei due esiti (per un trade flat coincide col reale;
        // per uno non flat è il minimo garantito — mai sovrastimare un backtest).
        const pnl = r2(Math.min(ifWin, ifLose));
        const exitFills = legs.filter(l => l.side === exitSide);
        const exitMatched = exitFills.reduce((a, l) => a + l.f.size, 0);
        const exitAvg = exitMatched > 0
            ? exitFills.reduce((a, l) => a + l.f.size * l.f.price, 0) / exitMatched : null;
        trades.push({
            entryTs: fillTs, entryPrice: r2(avgEntry), size,
            exit, exitTs, exitPrice: exitAvg != null ? r2(exitAvg) : null,
            pnl, incomplete: !flat,
        });

        // prossimo tentativo: dopo la chiusura (mai due posizioni sovrapposte)
        cursor = Math.max((exitTs ?? deadline) + 1000, cursor + params.everySec * 1000);
    }

    const totalPnl = r2(trades.reduce((a, t) => a + t.pnl, 0));
    return {
        trades, attempted, unfilled, totalPnl,
        wins: trades.filter(t => t.pnl > 0).length,
        losses: trades.filter(t => t.pnl < 0).length,
        incomplete: trades.filter(t => t.incomplete).length,
    };
}
