// ============================================================================
// replay-pnl.ts — funzioni PURE (unit-testabili) per la simulazione di trading
// stile Betfair Exchange usata da Match Replay. Nessuna dipendenza da React.
//
// SEMANTICA EXCHANGE (per selezione K, mercato a UN solo vincitore):
//   BACK  stake S a quota O su K:  K vince → +S*(O-1)   ;  K perde → -S
//   LAY   stake S (stake del backer) a quota O su K:
//                                  K vince → -S*(O-1)   ;  K perde → +S
//
//   "Position" di una selezione K nel mercato = P&L NETTO del libro di scommesse
//   del mercato NEL CASO in cui l'esito vincente sia K (somma dei payoff di TUTTE
//   le bet del mercato sotto l'ipotesi "vince K").
//
//   "Cash out" / valore di chiusura di un mercato = valore "green book" garantito
//   se si chiude ora alle quote correnti. Modello adottato (commentato sotto):
//   valore atteso del vettore-posizioni sotto le probabilità implicite NORMALIZZATE
//   (overround rimosso). Con prezzi equi e mercato "completo" (si può tradare ogni
//   esito) questo valore atteso è convertibile in un importo CERTO equalizzando il
//   libro → coincide con il cash-out garantito. Cash_out = Σ_i q_i · position(i).
// ============================================================================
import type { Ladder as LadderMap, LadderEntry as PriceLevels } from '@/lib/live';

// Ri-export per i consumer di questo modulo (tipi unificati con live.ts).
export type { LadderMap, PriceLevels };

export type BetSide = 'back' | 'lay';

export interface SimBet {
    id: string;
    marketId: string;
    selectionId: number;
    selectionName: string;
    marketName: string;
    side: BetSide;
    odds: number;        // quota MEDIA (VWAP) degli abbinamenti → base del P&L
    stake: number;       // stake EFFETTIVAMENTE abbinato (backer's stake) → base del P&L
    requestedStake?: number; // stake richiesto dall'utente (se > stake = fill PARZIALE)
    minute: number | null;
    // --- stato di matching (display-only, NON usato dalla matematica P&L) ---
    limitPrice?: number;    // quota limite richiesta (prezzo cliccato)
    remaining?: number;     // stake non ancora abbinato (a riposo / in ritardo / annullato)
    matchStatus?: 'PENDING' | 'OPEN' | 'MATCHED' | 'CANCELLED' | 'LAPSED';
    // --- post cash-out (solo in-memory, finché la pagina resta aperta) ---
    closed?: boolean;       // true = posizione chiusa con cash-out (resta visibile, esclusa dai calcoli aperti)
    realizedPnl?: number;   // P&L bloccato del MERCATO al cash-out (registrato una sola volta per gruppo)
}

// --------------------------------------------------------------- primitive P&L
// BACK: K vince → profitto stake*(odds-1); K perde → -stake.
export function backPnl(stake: number, odds: number, win: boolean): number {
    return win ? stake * (odds - 1) : -stake;
}

// LAY: il layer VINCE quando la selezione PERDE.
//   selezione perde (layer vince) → +stake
//   selezione vince (layer perde) → -stake*(odds-1)  (liability)
// `win` qui = "la selezione laydata ha vinto?".
export function layPnl(stake: number, odds: number, win: boolean): number {
    return win ? -stake * (odds - 1) : stake;
}

// Payoff di UNA bet dato l'esito vincente del mercato.
export function betPayoff(bet: SimBet, winningSelectionId: number): number {
    const selectionWon = bet.selectionId === winningSelectionId;
    return bet.side === 'back'
        ? backPnl(bet.stake, bet.odds, selectionWon)
        : layPnl(bet.stake, bet.odds, selectionWon);
}

// "Position" mostrata sulla riga della selezione K = P&L del mercato se vince K.
export function positionIfWins(bets: SimBet[], winningSelectionId: number): number {
    return bets.reduce((sum, b) => sum + betPayoff(b, winningSelectionId), 0);
}

// ------------------------------------------------------------- ladder helpers
// `LadderMap`/`PriceLevels` sono alias dei tipi `Ladder`/`LadderEntry` di live.ts
// (importati e ri-esportati sopra) per evitare definizioni duplicate e cast.

export function bestBack(ladder: LadderMap | undefined, selectionId: number): number | null {
    const e = ladder?.[String(selectionId)];
    const v = e?.back?.[0]?.[0];
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
export function bestLay(ladder: LadderMap | undefined, selectionId: number): number | null {
    const e = ladder?.[String(selectionId)];
    const v = e?.lay?.[0]?.[0];
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
export function ltp(ladder: LadderMap | undefined, selectionId: number): number | null {
    const e = ladder?.[String(selectionId)];
    return typeof e?.ltp === 'number' && Number.isFinite(e.ltp) ? e.ltp : null;
}

// Win % implicita dal prezzo back: round(100/back, 1). null se manca il prezzo.
export function winPercent(backPrice: number | null): number | null {
    if (backPrice == null || !Number.isFinite(backPrice) || backPrice <= 0) return null;
    return Math.round((100 / backPrice) * 10) / 10;
}

// Probabilità implicite NORMALIZZATE (overround rimosso) dai migliori prezzi back
// (fallback su ltp). Ritorna mappa selectionId(string) → q (somma = 1).
export function impliedProbsFromLadder(selectionIds: number[], ladder: LadderMap | undefined): Record<string, number> {
    const raw: Record<string, number> = {};
    let total = 0;
    for (const sid of selectionIds) {
        const price = bestBack(ladder, sid) ?? ltp(ladder, sid);
        const p = price != null && price > 0 ? 1 / price : 0;
        raw[String(sid)] = p;
        total += p;
    }
    const out: Record<string, number> = {};
    for (const sid of selectionIds) {
        out[String(sid)] = total > 0 ? raw[String(sid)] / total : 0;
    }
    return out;
}

// Cash-out di un mercato = Σ_i q_i · positionIfWins(i) (vedi nota in testa al file).
// Se non c'è alcun prezzo (mercato non quotato) ritorna 0.
export function marketCashOut(bets: SimBet[], ladder: LadderMap | undefined, selectionIds: number[]): number {
    if (bets.length === 0) return 0;
    const q = impliedProbsFromLadder(selectionIds, ladder);
    const totalProb = selectionIds.reduce((s, sid) => s + (q[String(sid)] ?? 0), 0);
    if (totalProb <= 0) return 0;
    return selectionIds.reduce((sum, sid) => sum + (q[String(sid)] ?? 0) * positionIfWins(bets, sid), 0);
}

// Posizione complessiva = somma dei cash-out di tutti i mercati con bet aperte.
export interface MarketEval {
    bets: SimBet[];
    ladder: LadderMap | undefined;
    selectionIds: number[];
}
export function overallPosition(markets: MarketEval[]): number {
    return markets.reduce((sum, m) => sum + marketCashOut(m.bets, m.ladder, m.selectionIds), 0);
}

// ====================================================================
// SETTLEMENT sull'ESITO REALE (P&L "completo" dell'operazione)
// Quando l'esito di un mercato è DECISO dal punteggio, il P&L non è più
// mark-to-market ma quello DEFINITIVO (vince/perde davvero). Es: BTTS "Sì" è
// certo appena entrambe segnano; Over X.5 appena i gol superano la linea;
// Match Odds / Correct Score / Double Chance a fine partita.
// ====================================================================
export interface SelectionMeta {
    selection_id: number;
    name: string | null;
    sort_priority?: number | null;
}
export interface MarketMeta {
    market_type: string | null;
    selections: SelectionMeta[];
}
export interface SettleCtx {
    home: number;
    away: number;
    finished: boolean;   // la partita è terminata (fine replay / >=90')
}

function lineFromType(t: string): number | null {
    const m = /(\d)(\d)$/.exec(t); // OVER_UNDER_25 -> 2.5, OVER_UNDER_05 -> 0.5
    if (!m) return null;
    return Number(`${m[1]}.${m[2]}`);
}
const isDraw = (n: string | null) => !!n && /draw|pareggio/i.test(n);
const isYes = (n: string | null) => !!n && /^(yes|si|s[iì])$/i.test(n.trim());
const isNo = (n: string | null) => !!n && /^no$/i.test(n.trim());
const isOver = (n: string | null) => !!n && /over/i.test(n);
const isUnder = (n: string | null) => !!n && /under/i.test(n);

// Selezione vincente se il mercato è DECISO ora, altrimenti null (non deciso).
export function decideWinner(market: MarketMeta, ctx: SettleCtx): number | null {
    const t = (market.market_type || '').toUpperCase();
    const sels = market.selections;
    const total = ctx.home + ctx.away;
    const bothScored = ctx.home >= 1 && ctx.away >= 1;

    if (t === 'BOTH_TEAMS_TO_SCORE' || t === 'BTTS') {
        if (bothScored) return sels.find(s => isYes(s.name))?.selection_id ?? null;
        if (ctx.finished) return sels.find(s => isNo(s.name))?.selection_id ?? null;
        return null;
    }
    if (t.startsWith('OVER_UNDER')) {
        const line = lineFromType(t);
        if (line == null) return null;
        if (total > line) return sels.find(s => isOver(s.name))?.selection_id ?? null;
        if (ctx.finished) return sels.find(s => isUnder(s.name))?.selection_id ?? null;
        return null;
    }
    if (t === 'MATCH_ODDS') {
        if (!ctx.finished) return null;
        const draw = sels.find(s => isDraw(s.name));
        const nd = sels.filter(s => !isDraw(s.name))
            .sort((a, b) => (a.sort_priority ?? 0) - (b.sort_priority ?? 0));
        if (ctx.home > ctx.away) return nd[0]?.selection_id ?? null;
        if (ctx.home < ctx.away) return nd[1]?.selection_id ?? null;
        return draw?.selection_id ?? null;
    }
    if (t === 'CORRECT_SCORE') {
        if (!ctx.finished) return null;
        const key = `${ctx.home}-${ctx.away}`;
        return sels.find(s => (s.name || '').replace(/\s/g, '') === key)?.selection_id ?? null;
    }
    return null; // mercati non gestiti (HT, ecc.) → mark-to-market
}

// Valore di un mercato: P&L DEFINITIVO se l'esito è deciso, altrimenti cash-out.
export interface MarketSettleEval extends MarketEval {
    market: MarketMeta;
}
export function settleOrCashOut(
    e: MarketSettleEval, ctx: SettleCtx,
): { value: number; settled: boolean; winnerId: number | null } {
    if (e.bets.length === 0) return { value: 0, settled: false, winnerId: null };
    const winner = decideWinner(e.market, ctx);
    if (winner != null) {
        return { value: positionIfWins(e.bets, winner), settled: true, winnerId: winner };
    }
    return { value: marketCashOut(e.bets, e.ladder, e.selectionIds), settled: false, winnerId: null };
}

// Posizione complessiva con SETTLEMENT: somma dei valori (definitivi o cash-out).
export function overallSettled(markets: MarketSettleEval[], ctx: SettleCtx): number {
    return markets.reduce((sum, e) => sum + settleOrCashOut(e, ctx).value, 0);
}

// ----------------------------------------------------------------- formatting
// Importi in sterline: £12.31 / £-12.31.
export function formatGbp(v: number | null | undefined, decimals = 2): string {
    if (v == null || !Number.isFinite(v)) return '£0.00';
    const sign = v < 0 ? '-' : '';
    return `${sign}£${Math.abs(v).toFixed(decimals)}`;
}
