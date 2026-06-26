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
    odds: number;        // quota decimale a cui è stata piazzata
    stake: number;       // stake del backer (per lay = backer's stake)
    minute: number | null;
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

// ----------------------------------------------------------------- formatting
// Importi in sterline: £12.31 / £-12.31.
export function formatGbp(v: number | null | undefined, decimals = 2): string {
    if (v == null || !Number.isFinite(v)) return '£0.00';
    const sign = v < 0 ? '-' : '';
    return `${sign}£${Math.abs(v).toFixed(decimals)}`;
}
