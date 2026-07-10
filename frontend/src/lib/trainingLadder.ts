// ============================================================================
// trainingLadder.ts — F41: REPLAY-TRAINING sul ladder — logica PURA + orderApi
// SIMULATO in-memory (drop-in per LadderView via dependency injection).
//
// ONESTÀ (il training vale solo se fedele):
//   * gli ordini NON si abbinano mai "per magia": passano TUTTI dal matching
//     engine fedele (lib/matching.simulateOrder — taker con price improvement,
//     maker con queue position e cap sul volume tradato, bet-delay in-play
//     DEFAULT_DELAY_MS, LAPSE che decade alla sospensione);
//   * il green-up è UN ORDINE simulato come gli altri: può NON abbinarsi (come
//     nella realtà) — mai un cash-out istantaneo inventato;
//   * stake sotto il minimo .it (€2) → rifiutato con errore esplicito (il flusso
//     submin non esiste nel simulatore: meglio un no chiaro che un fill finto);
//   * tutto è DETERMINISTICO e ricalcolato da zero a ogni istante: riavvolgere
//     la timeline dà sempre lo stesso risultato (stesso contratto di matching.ts).
//
// NIENTE denaro reale in questo modulo: nessuna chiamata a Supabase/coda ordini.
// ============================================================================
import {
    DEFAULT_DELAY_MS, simulateOrder,
    type BookSnapshot, type OrderRequest, type ResolvedOrder,
} from '@/lib/matching';
import type { LadderEntry, LiveLadderRow, LiveLadderSelection } from '@/lib/live';
import type {
    LiveOrderCommand, LiveOrderResult, LiveOrderRow, LivePositionRow,
} from '@/lib/liveOrders';
import type { LadderGreenupArgs, LadderOrderApi } from '@/components/live/LadderView';

// minimo stake .it: sotto, il place REALE verrebbe rifiutato → il training fa lo stesso.
export const TRAINING_MIN_STAKE = 2.0;

// ---------------------------------------------------------------------------
// Conversione frame replay → LiveLadderRow (ciò che LadderView si aspetta)
// ---------------------------------------------------------------------------
/** WOM dai primi n livelli (stessa convenzione LADDER_WOM_LEVELS=3 del runner). */
export function womOf(
    back: ReadonlyArray<readonly [number, number]> | undefined,
    lay: ReadonlyArray<readonly [number, number]> | undefined,
    n = 3,
): { back_pct: number; lay_pct: number } {
    const sum = (levels?: ReadonlyArray<readonly [number, number]>) => {
        if (!Array.isArray(levels)) return 0;
        let tot = 0;
        for (const lv of levels.slice(0, n)) {
            const s = lv?.[1];
            if (Number.isFinite(s) && (s as number) > 0) tot += s as number;
        }
        return tot;
    };
    const b = sum(back);
    const l = sum(lay);
    const tot = b + l;
    if (tot <= 0) return { back_pct: 50, lay_pct: 50 };
    return { back_pct: (b / tot) * 100, lay_pct: (l / tot) * 100 };
}

/** Converte il ladder di un frame replay nella riga che LadderView consuma. */
export function frameToLadderRow(args: {
    eventId: string;
    marketId: string;
    marketType: string | null;
    marketName: string | null;
    status: string | null;
    nowMs: number;
    ladder: Record<string | number, LadderEntry> | null | undefined;
    names: ReadonlyMap<number, string>;
}): LiveLadderRow {
    const selections: LiveLadderSelection[] = [];
    const entries = args.ladder ? Object.entries(args.ladder) : [];
    for (const [sidRaw, entry] of entries) {
        const sid = Number(sidRaw);
        if (!Number.isFinite(sid) || !entry) continue;
        const back = Array.isArray(entry.back) ? entry.back : [];
        const lay = Array.isArray(entry.lay) ? entry.lay : [];
        selections.push({
            selection_id: sid,
            name: args.names.get(sid) ?? null,
            ltp: Number.isFinite(entry.ltp as number) ? (entry.ltp as number) : null,
            tv: Number.isFinite(entry.tv as number) ? (entry.tv as number) : null,
            back: back as [number, number][],
            lay: lay as [number, number][],
            trd: (Array.isArray(entry.trd) ? entry.trd : []) as [number, number][],
            wom: womOf(back, lay),
        });
    }
    return {
        event_id: args.eventId,
        market_id: args.marketId,
        market_type: args.marketType,
        market_name: args.marketName,
        status: args.status,
        ladder: { updated_ms: args.nowMs, selections },
        updated_at: new Date(args.nowMs).toISOString(),
    };
}

// ---------------------------------------------------------------------------
// orderApi SIMULATO in-memory
// ---------------------------------------------------------------------------
export interface TrainingOrder {
    id: number;
    bet_id: string;
    market_id: string;
    selection_id: number;
    req: OrderRequest;          // immutabile salvo cancelledTs
}

export interface TrainingContext {
    eventId: string;
    /** snapshot del book della selezione (BookSnapshot[] ordinati per ts). */
    getSnaps: (marketId: string, selectionId: number) => ReadonlyArray<BookSnapshot>;
    /** istante corrente della timeline replay (ms). */
    getNow: () => number;
    /** il mercato è in-play a questo istante? (decide il bet-delay). */
    isInplayAt: (marketId: string, ts: number) => boolean;
}

export interface TrainingApi extends LadderOrderApi {
    /** ordini simulati risolti all'istante corrente (per pannelli/riepiloghi). */
    resolved: () => Array<{ order: TrainingOrder; res: ResolvedOrder }>;
    /** azzera tutti gli ordini simulati (nuova sessione di training). */
    reset: () => void;
}

const r2 = (v: number) => Math.round(v * 100) / 100;

function resolve(ctx: TrainingContext, o: TrainingOrder): ResolvedOrder {
    return simulateOrder(o.req, ctx.getSnaps(o.market_id, o.selection_id), ctx.getNow());
}

/** Miglior prezzo del lato al più recente snapshot ≤ now (null se book vuoto). */
function bestAt(ctx: TrainingContext, marketId: string, selectionId: number, side: 'back' | 'lay'): number | null {
    const snaps = ctx.getSnaps(marketId, selectionId);
    const now = ctx.getNow();
    let snap: BookSnapshot | null = null;
    for (let i = snaps.length - 1; i >= 0; i--) {
        if (snaps[i].ts <= now) { snap = snaps[i]; break; }
    }
    const levels = side === 'back' ? snap?.back : snap?.lay;
    const p = levels?.[0]?.[0];
    return Number.isFinite(p as number) && (p as number) > 1 ? (p as number) : null;
}

/** Esposizioni matched/unmatched di una selezione dagli ordini risolti. */
export function selectionExposures(
    resolved: ReadonlyArray<{ order: TrainingOrder; res: ResolvedOrder }>,
    marketId: string,
    selectionId: number,
): {
    ifWin: number; ifLose: number; net: number;
    unmatchedBack: number; unmatchedLay: number;
} {
    let ifWin = 0, ifLose = 0, net = 0, unmatchedBack = 0, unmatchedLay = 0;
    for (const { order, res } of resolved) {
        if (order.market_id !== marketId || order.selection_id !== selectionId) continue;
        for (const f of res.fills) {
            if (order.req.side === 'back') {
                ifWin += f.size * (f.price - 1);
                ifLose -= f.size;
                net += f.size;
            } else {
                ifWin -= f.size * (f.price - 1);
                ifLose += f.size;
                net -= f.size;
            }
        }
        if (res.status === 'OPEN' && res.remaining > 0) {
            if (order.req.side === 'back') unmatchedBack += res.remaining;
            else unmatchedLay += res.remaining * (order.req.limitPrice - 1);
        }
    }
    return { ifWin: r2(ifWin), ifLose: r2(ifLose), net: r2(net), unmatchedBack: r2(unmatchedBack), unmatchedLay: r2(unmatchedLay) };
}

/** Crea l'orderApi SIMULATO (drop-in per LadderView). Tutto in-memory. */
export function createTrainingApi(ctx: TrainingContext): TrainingApi {
    const orders: TrainingOrder[] = [];
    let seq = 0;

    const resolvedAll = () => orders.map(o => ({ order: o, res: resolve(ctx, o) }));

    const err = (action: string, message: string): LiveOrderResult =>
        ({ ok: false, action, mode: 'paper', error: message });

    const place = (cmd: LiveOrderCommand): LiveOrderResult => {
        const side = cmd.side;
        const price = Number(cmd.price);
        // il ladder invia size (back) o liability (lay in modalità Liab): normalizza a stake.
        let size = Number(cmd.size);
        if (!Number.isFinite(size) && Number.isFinite(Number(cmd.liability)) && price > 1) {
            size = Number(cmd.liability) / (price - 1);
        }
        size = r2(size);
        if (side !== 'back' && side !== 'lay') return err('place', 'side non valido');
        if (!Number.isFinite(price) || price <= 1 || price > 1000) return err('place', 'prezzo fuori range');
        if (!Number.isFinite(size) || size < TRAINING_MIN_STAKE) {
            return err('place', `stake €${Number.isFinite(size) ? size.toFixed(2) : '?'} sotto il minimo `
                + `€${TRAINING_MIN_STAKE.toFixed(2)} (.it) — nel training il flusso sotto-minimo non esiste`);
        }
        if (!cmd.market_id || cmd.selection_id == null) return err('place', 'market/selection mancanti');
        const now = ctx.getNow();
        const inPlay = ctx.isInplayAt(cmd.market_id, now);
        const o: TrainingOrder = {
            id: ++seq,
            bet_id: `T${seq}`,
            market_id: cmd.market_id,
            selection_id: cmd.selection_id,
            req: {
                side, limitPrice: price, stake: size, placedTs: now, inPlay,
                delayMs: inPlay ? DEFAULT_DELAY_MS : 0,
                persistence: cmd.persistence === 'PERSIST' ? 'PERSIST' : 'LAPSE',
                cancelledTs: null,
            },
        };
        orders.push(o);
        const res = resolve(ctx, o);
        return {
            ok: true, action: 'place', mode: 'paper', bet_id: o.bet_id,
            status: res.status, size_matched: r2(res.matched),
            average_price_matched: res.avgPrice, size_remaining: r2(res.remaining),
            market_id: o.market_id, selection_id: o.selection_id, side,
            price, size,
            detail: inPlay ? `bet-delay ${Math.round(DEFAULT_DELAY_MS / 1000)}s applicato (in-play)` : undefined,
        };
    };

    const cancel = (cmd: LiveOrderCommand): LiveOrderResult => {
        const o = orders.find(x => x.bet_id === cmd.bet_id);
        if (!o) return err('cancel', `ordine ${cmd.bet_id ?? '?'} non trovato`);
        if (o.req.cancelledTs == null) o.req = { ...o.req, cancelledTs: ctx.getNow() };
        return { ok: true, action: 'cancel', mode: 'paper', bet_id: o.bet_id };
    };

    const send = async (cmd: LiveOrderCommand): Promise<LiveOrderResult> => {
        if (cmd.action === 'place') return place(cmd);
        if (cmd.action === 'cancel') return cancel(cmd);
        return err(cmd.action, `azione '${cmd.action}' non supportata nel TRAINING`);
    };

    const fetchOrders = async (marketId: string): Promise<LiveOrderRow[]> => {
        const now = ctx.getNow();
        return orders
            .filter(o => o.market_id === marketId && o.req.placedTs <= now)
            .map(o => {
                const res = resolve(ctx, o);
                // "vivo sul book" = stato aperto E residuo > 0. NB matching: alla
                // cancellazione remaining viene AZZERATO (lo stake annullato non è
                // più "remaining") e un parziale cancellato può restare status OPEN
                // → la quota annullata/decaduta si ricava da requested − matched.
                const open = (res.status === 'OPEN' || res.status === 'PENDING') && res.remaining > 0;
                const unfilled = r2(Math.max(0, res.requested - res.matched));
                const wasCancelled = o.req.cancelledTs != null && !open;
                return {
                    id: o.id, source: 'runner', bet_id: o.bet_id, client_order_ref: `train${o.id}`,
                    request_id: null, mode: 'paper', event_id: ctx.eventId,
                    market_id: o.market_id, selection_id: o.selection_id, handicap: 0,
                    side: o.req.side, order_type: 'LIMIT',
                    price: o.req.limitPrice, size: o.req.stake,
                    size_matched: r2(res.matched),
                    size_remaining: open ? r2(res.remaining) : 0,
                    size_cancelled: res.status === 'LAPSED' ? 0 : (wasCancelled ? unfilled : 0),
                    size_lapsed: res.status === 'LAPSED' ? unfilled : 0,
                    size_voided: 0,
                    average_price_matched: res.avgPrice ?? 0,
                    status: open ? 'EXECUTABLE' : 'EXECUTION_COMPLETE',
                    persistence: o.req.persistence ?? 'LAPSE',
                    placed_at: new Date(o.req.placedTs).toISOString(),
                    matched_at: res.fills.length ? new Date(res.fills[res.fills.length - 1].ts).toISOString() : null,
                    updated_at: new Date(now).toISOString(),
                } as LiveOrderRow;
            });
    };

    const fetchPositions = async (marketId: string): Promise<LivePositionRow[]> => {
        const now = ctx.getNow();
        const all = resolvedAll();
        const sels = new Set(orders.filter(o => o.market_id === marketId).map(o => o.selection_id));
        const out: LivePositionRow[] = [];
        let id = 0;
        for (const sid of sels) {
            const e = selectionExposures(all, marketId, sid);
            if (e.ifWin === 0 && e.ifLose === 0 && e.unmatchedBack === 0 && e.unmatchedLay === 0) continue;
            out.push({
                id: ++id, mode: 'paper', event_id: ctx.eventId, market_id: marketId,
                selection_id: sid, handicap: 0,
                matched_if_win: e.ifWin, matched_if_lose: e.ifLose,
                worst_if_win: r2(e.ifWin - e.unmatchedLay),
                worst_if_lose: r2(e.ifLose - e.unmatchedBack),
                selection_exposure: r2(Math.max(0, -Math.min(e.ifWin, e.ifLose))),
                unmatched_back_exposure: e.unmatchedBack,
                unmatched_lay_exposure: e.unmatchedLay,
                net_position: e.net,
                updated_at: new Date(now).toISOString(),
            });
        }
        return out;
    };

    // Green-up = UN ORDINE simulato (può NON abbinarsi, come nella realtà).
    const greenup = async (args: LadderGreenupArgs): Promise<LiveOrderResult> => {
        const { marketId, selectionId } = args;
        const fraction = args.fraction != null && args.fraction > 0 && args.fraction <= 1 ? args.fraction : 1;
        if (args.cancelUnmatched) {
            for (const o of orders) {
                if (o.market_id === marketId && o.selection_id === selectionId && o.req.cancelledTs == null) {
                    const res = resolve(ctx, o);
                    if (res.status === 'OPEN' || res.status === 'PENDING') {
                        o.req = { ...o.req, cancelledTs: ctx.getNow() };
                    }
                }
            }
        }
        const e = selectionExposures(resolvedAll(), marketId, selectionId);
        const diff = e.ifWin - e.ifLose;
        if (Math.abs(diff) < 0.01) {
            return { ok: true, action: 'greenup', mode: 'paper', detail: 'posizione già piatta' };
        }
        const side: 'back' | 'lay' = diff > 0 ? 'lay' : 'back';
        const price = args.targetPrice ?? bestAt(ctx, marketId, selectionId, side);
        if (price == null || !(price > 1)) {
            return err('greenup', 'nessun prezzo disponibile per la chiusura (book vuoto a questo istante)');
        }
        const size = r2((Math.abs(diff) / price) * fraction);
        if (size < TRAINING_MIN_STAKE) {
            return err('greenup', `size di chiusura €${size.toFixed(2)} sotto il minimo €2 (.it) — `
                + 'nel training il flusso sotto-minimo non esiste');
        }
        return place({
            action: 'place', mode: 'paper', market_id: marketId, selection_id: selectionId,
            handicap: 0, side, order_type: 'LIMIT', price, size, persistence: 'LAPSE',
        });
    };

    return {
        send,
        fetchOrders,
        fetchPositions,
        greenup,
        // armRule OMESSO: gli strumenti del risk engine non esistono nel training
        // (capability gating: la toolbar mostra solo ciò che funziona davvero).
        supportsFok: false,
        resolved: resolvedAll,
        reset: () => { orders.length = 0; },
    };
}
