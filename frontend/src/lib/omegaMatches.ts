// ============================================================================
// omegaMatches.ts — UNA RIGA PER PARTITA (Omega §14, 11/09/2026).
//
// Le righe di omega_trades sono GAMBE: apertura 1T (Half Time Score), apertura
// 2T (Correct Score), gambe di chiusura (back sulla stessa selezione: green-up
// / cash out, `closes_trade_id`), trade v1 senza fase, manuali, scalp. Il
// trader vuole vedere la PARTITA: le due operazioni affiancate, con le loro
// chiusure attaccate, il risultato REALE di fine 1T e di fine 2T e il P&L
// complessivo della partita in verde/rosso.
//
// Tutto PURO e testato (omegaMatches.test.ts). Funziona sia sui trade live
// (OmegaTrade) sia sulle righe dello storico (DayTrade + closes appiattite).
// ============================================================================

export type LegKind = 'ht' | 'ft' | 'other';
export type PnlState = 'settled' | 'locked' | 'open' | 'none';

/** campi minimi che una riga deve avere (OmegaTrade e DayTradeLeg li hanno) */
export interface MatchTradeLike {
    id: number;
    event_id: string;
    event_name?: string | null;
    phase?: string | null;
    side: string;
    status: string;
    pnl: number;
    price?: number | null;
    size?: number | null;
    liability?: number | null;
    placed_at: string;
    settled_at?: string | null;
    kickoff?: string | null;
    closes_trade_id?: number | null;
    meta: Record<string, unknown> | null | undefined;
    runner_name?: string | null;
    minute_at_entry?: number | null;
    score_at_entry?: string | null;
    origin?: string | null;
    mode?: string;
}

export interface LegPnl {
    state: PnlState;
    /** P&L regolato (apertura + chiusure regolate) oppure bloccato dalla copertura */
    value: number | null;
}

export interface MatchLeg<T extends MatchTradeLike> {
    kind: LegKind;
    trade: T;
    /** gambe di chiusura (back/lay opposto sulla stessa selezione), in ordine di id */
    closes: T[];
    pnl: LegPnl;
    /** posizione ancora viva (pending/open/hedged) */
    live: boolean;
}

export interface MatchGroup<T extends MatchTradeLike> {
    event_id: string;
    event_name: string | null;
    kickoff: string | null;
    /** prima apertura piazzata */
    placed_at: string;
    /** ultima attività (apertura, chiusura o regolazione) */
    last_at: string;
    ht: MatchLeg<T> | null;
    ft: MatchLeg<T> | null;
    others: MatchLeg<T>[];
    /** tutte le gambe in ordine 1T → 2T → altre */
    legs: MatchLeg<T>[];
    /** risultato REALE al 45′ / finale (da meta.result_ht / result_ft di qualunque gamba) */
    result_ht: string | null;
    result_ft: string | null;
    /** P&L della partita: somma dei P&L regolati (aperture + chiusure) */
    pnl_settled: number;
    /** P&L bloccato dalle coperture ancora da regolare (null se nessuna) */
    pnl_locked: number | null;
    /** liability ancora a rischio (aperture vive senza P&L bloccato) */
    open_liability: number;
    /** stato complessivo */
    state: 'open' | 'partial' | 'settled';
    /** quante gambe hanno un esito (regolate o bloccate) */
    n_decided: number;
    n_legs: number;
    live: boolean;
}

const SETTLED = new Set(['won', 'lost', 'void']);
const LIVE = new Set(['pending', 'open', 'hedged']);

function num(v: unknown): number | null {
    if (v == null || v === '') return null;          // Number(null) === 0: mai un falso 'bloccato 0'
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}
function metaOf(t: MatchTradeLike): Record<string, unknown> {
    return (t.meta ?? {}) as Record<string, unknown>;
}
function ts(iso: string | null | undefined): number {
    const n = iso ? new Date(iso).getTime() : NaN;
    return Number.isFinite(n) ? n : 0;
}
function laterIso(a: string, b: string | null | undefined): string {
    return b && ts(b) > ts(a) ? b : a;
}

/** gamba 1T / 2T / altro: dal campo phase (v2); i trade v1 senza fase sono sul
 *  Correct Score finale → 2T; scalp e mercati diversi → 'other'. */
export function legKindOf(t: { phase?: string | null; meta?: Record<string, unknown> | null; closes_trade_id?: number | null }): LegKind {
    if (t.closes_trade_id != null) return 'other';   // chiusura ORFANA: mai nella cella 1T/2T (review MED-1)
    const p = t.phase ?? null;
    if (p === 'ht_cs') return 'ht';
    if (p === 'ft_cs' || p == null) return 'ft';
    return 'other';
}

/** P&L di una gamba con le sue chiusure. */
export function legPnl<T extends MatchTradeLike>(trade: T, closes: T[]): LegPnl {
    if (SETTLED.has(trade.status)) {
        let v = Number(trade.pnl) || 0;
        for (const c of closes) if (SETTLED.has(c.status)) v += Number(c.pnl) || 0;
        return { state: 'settled', value: Math.round(v * 100) / 100 };
    }
    const locked = num(metaOf(trade)['locked_pnl']);
    // bloccato solo con una chiusura DAVVERO abbinata: una chiusura ancora 'pending'
    // (cash out in coda) lascia la gamba aperta e il suo rischio vivo (review 11/09 HIGH-1)
    if (trade.status === 'hedged' || (locked != null && closes.some((c) => c.status !== 'error' && c.status !== 'pending'))) {
        return { state: 'locked', value: locked ?? 0 };
    }
    if (LIVE.has(trade.status)) return { state: 'open', value: null };
    return { state: 'none', value: null };
}

export function resultsOf(t: { meta?: Record<string, unknown> | null }): { ht: string | null; ft: string | null } {
    const m = (t.meta ?? {}) as Record<string, unknown>;
    const s = (v: unknown) => (typeof v === 'string' && /^\d+-\d+$/.test(v) ? v : null);
    return { ht: s(m.result_ht), ft: s(m.result_ft) };
}

/** Raggruppa le righe (aperture + chiusure appiattite) per partita. */
export function groupTradesByMatch<T extends MatchTradeLike>(trades: T[]): MatchGroup<T>[] {
    const ids = new Set(trades.map((t) => t.id));
    const closesByParent = new Map<number, T[]>();
    const openings: T[] = [];
    for (const t of trades) {
        const p = t.closes_trade_id ?? null;
        if (p != null && ids.has(p)) {
            const list = closesByParent.get(p) ?? [];
            list.push(t);
            closesByParent.set(p, list);
        } else {
            openings.push(t);          // aperture + chiusure ORFANE (apertura non in lista)
        }
    }
    const byEvent = new Map<string, T[]>();
    for (const t of openings) {
        const list = byEvent.get(t.event_id) ?? [];
        list.push(t);
        byEvent.set(t.event_id, list);
    }
    const out: MatchGroup<T>[] = [];
    for (const [event_id, rows] of byEvent) {
        rows.sort((a, b) => a.id - b.id);
        const legs: MatchLeg<T>[] = rows.map((t) => {
            const closes = (closesByParent.get(t.id) ?? []).sort((a, b) => a.id - b.id);
            return { kind: legKindOf(t), trade: t, closes, pnl: legPnl(t, closes), live: LIVE.has(t.status) };
        });
        const order: Record<LegKind, number> = { ht: 0, ft: 1, other: 2 };
        legs.sort((a, b) => order[a.kind] - order[b.kind] || a.trade.id - b.trade.id);
        const ht = legs.find((l) => l.kind === 'ht') ?? null;
        const ft = legs.find((l) => l.kind === 'ft') ?? null;
        const others = legs.filter((l) => l !== ht && l !== ft);
        let result_ht: string | null = null;
        let result_ft: string | null = null;
        let pnl_settled = 0;
        let pnl_locked: number | null = null;
        let open_liability = 0;
        let n_decided = 0;
        let placed_at = rows[0].placed_at;
        let last_at = rows[0].placed_at;
        let kickoff: string | null = null;
        let event_name: string | null = null;
        for (const leg of legs) {
            const r = resultsOf(leg.trade);
            result_ht = result_ht ?? r.ht;
            result_ft = result_ft ?? r.ft;
            if (leg.pnl.state === 'settled') { pnl_settled += leg.pnl.value ?? 0; n_decided += 1; }
            else if (leg.pnl.state === 'locked') { pnl_locked = (pnl_locked ?? 0) + (leg.pnl.value ?? 0); n_decided += 1; }
            else if (leg.live && leg.trade.closes_trade_id != null) { /* chiusura orfana: rischio già nell'apertura */ }
            else if (leg.live && leg.trade.side !== 'back') { open_liability += Number(leg.trade.liability) || 0; }
            else if (leg.live) { open_liability += Number(leg.trade.size) || 0; }
            if (ts(leg.trade.placed_at) < ts(placed_at)) placed_at = leg.trade.placed_at;
            last_at = laterIso(last_at, leg.trade.placed_at);
            last_at = laterIso(last_at, leg.trade.settled_at);
            for (const c of leg.closes) { last_at = laterIso(last_at, c.placed_at); last_at = laterIso(last_at, c.settled_at); }
            kickoff = kickoff ?? leg.trade.kickoff ?? null;
            event_name = event_name ?? (leg.trade.event_name?.trim() ? leg.trade.event_name : null);
        }
        const n_legs = legs.length;
        const live = legs.some((l) => l.live);
        const allSettled = legs.every((l) => l.pnl.state === 'settled');
        const state: MatchGroup<T>['state'] = allSettled ? 'settled' : n_decided > 0 ? 'partial' : 'open';
        out.push({
            event_id, event_name, kickoff, placed_at, last_at, ht, ft, others, legs,
            result_ht, result_ft, pnl_settled: Math.round(pnl_settled * 100) / 100,
            pnl_locked: pnl_locked == null ? null : Math.round(pnl_locked * 100) / 100,
            open_liability: Math.round(open_liability * 100) / 100,
            state, n_decided, n_legs, live,
        });
    }
    out.sort((a, b) => ts(b.last_at) - ts(a.last_at) || ts(b.placed_at) - ts(a.placed_at));
    return out;
}

/** 'YYYY-MM-DD' Europe/Rome del piazzamento (giornata operativa della partita). */
export function romeDayOf(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(d);
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
    return `${get('year')}-${get('month')}-${get('day')}`;
}

/** Partite della GIORNATA (piazzate nel giorno) più quelle ancora vive di giorni
 *  precedenti (il trader deve vederle finché non sono regolate). */
export function filterMatchesForDay<T extends MatchTradeLike>(groups: MatchGroup<T>[], day: string): MatchGroup<T>[] {
    return groups.filter((g) => g.live || romeDayOf(g.placed_at) === day);
}

/** Totali di un insieme di partite (barra/riepilogo). */
export function summarizeMatches<T extends MatchTradeLike>(groups: MatchGroup<T>[]): {
    matches: number; legs: number; settled: number; won: number; lost: number;
    pnl_settled: number; pnl_locked: number | null; open_liability: number; live: number;
} {
    let legs = 0, settled = 0, won = 0, lost = 0, pnl_settled = 0, open_liability = 0, live = 0;
    let pnl_locked: number | null = null;
    for (const g of groups) {
        legs += g.n_legs;
        pnl_settled += g.pnl_settled;
        open_liability += g.open_liability;
        if (g.live) live += 1;
        if (g.pnl_locked != null) pnl_locked = (pnl_locked ?? 0) + g.pnl_locked;
        for (const l of g.legs) {
            if (l.pnl.state === 'settled') {
                settled += 1;
                if ((l.pnl.value ?? 0) > 0) won += 1;
                else if ((l.pnl.value ?? 0) < 0) lost += 1;
            }
        }
    }
    return {
        matches: groups.length, legs, settled, won, lost,
        pnl_settled: Math.round(pnl_settled * 100) / 100,
        pnl_locked: pnl_locked == null ? null : Math.round(pnl_locked * 100) / 100,
        open_liability: Math.round(open_liability * 100) / 100, live,
    };
}
