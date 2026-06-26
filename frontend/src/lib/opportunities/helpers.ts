// ============================================================================
// helpers.ts — parsing delle SELEZIONI identico a replay-pnl.ts (decideWinner).
// Mantiene UNA sola fonte di verità: i predicati sono ri-derivati con la STESSA
// logica (regex) di replay-pnl.ts, e le funzioni di settlement/ladder vengono
// RI-ESPORTATE direttamente da replay-pnl.ts per evitare divergenze.
// ============================================================================
import type { SelLite, MarketLite } from './types';

// Ri-export delle primitive già certificate in replay-pnl.ts (fonte di verità).
export {
    bestBack,
    bestLay,
    ltp,
    decideWinner,
    positionIfWins,
    backPnl,
    layPnl,
} from '@/lib/replay-pnl';
export type { MarketMeta, SelectionMeta, SettleCtx } from '@/lib/replay-pnl';

// ---------------------------------------------------------------- predicati
// IDENTICI a quelli (module-private) di replay-pnl.ts.

// OVER_UNDER_25 -> 2.5 ; OVER_UNDER_05 -> 0.5
export function lineFromType(t: string): number | null {
    const m = /(\d)(\d)$/.exec(t);
    if (!m) return null;
    return Number(`${m[1]}.${m[2]}`);
}

export const isDraw = (n: string | null): boolean => !!n && /draw|pareggio/i.test(n);
export const isYes = (n: string | null): boolean => !!n && /^(yes|si|s[iì])$/i.test(n.trim());
export const isNo = (n: string | null): boolean => !!n && /^no$/i.test(n.trim());
export const isOver = (n: string | null): boolean => !!n && /over/i.test(n);
export const isUnder = (n: string | null): boolean => !!n && /under/i.test(n);

// ------------------------------------------------------------- MATCH_ODDS
// Convenzione replay-pnl.ts: HOME = sort_priority più basso tra i non-draw,
// AWAY = il successivo, DRAW = la selezione "pareggio".
export interface MatchOddsTriple {
    home: SelLite | null;
    away: SelLite | null;
    draw: SelLite | null;
}
export function matchOddsTriple(selections: SelLite[]): MatchOddsTriple {
    const draw = selections.find((s) => isDraw(s.name)) ?? null;
    const nd = selections
        .filter((s) => !isDraw(s.name))
        .sort((a, b) => (a.sort_priority ?? 0) - (b.sort_priority ?? 0));
    return { home: nd[0] ?? null, away: nd[1] ?? null, draw };
}

// --------------------------------------------------------- CORRECT_SCORE
// Chiave "h-a" (es. 2-1). Lo spazio viene rimosso nel match in decideWinner;
// qui produciamo la chiave canonica senza spazi.
export function correctScoreKey(home: number, away: number): string {
    return `${home}-${away}`;
}
export function selectionMatchesScore(sel: SelLite, home: number, away: number): boolean {
    return (sel.name || '').replace(/\s/g, '') === correctScoreKey(home, away);
}

// ----------------------------------------------------------- type guards
export function isMatchOdds(m: { market_type: string | null }): boolean {
    return (m.market_type || '').toUpperCase() === 'MATCH_ODDS';
}
export function isOverUnder(m: { market_type: string | null }): boolean {
    return (m.market_type || '').toUpperCase().startsWith('OVER_UNDER');
}
export function isBtts(m: { market_type: string | null }): boolean {
    const t = (m.market_type || '').toUpperCase();
    return t === 'BOTH_TEAMS_TO_SCORE' || t === 'BTTS';
}
export function isCorrectScore(m: { market_type: string | null }): boolean {
    return (m.market_type || '').toUpperCase() === 'CORRECT_SCORE';
}

// Numero di selezioni "attive" (con nome) di un mercato leggero.
export function namedSelections(m: MarketLite): SelLite[] {
    return m.selections.filter((s) => !!s.name);
}
