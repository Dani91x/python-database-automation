// ============================================================================
// ladderPopout.ts - 08/10 (cantiere W1, pagina «Cash Out»): aprire il ladder di
// UN mercato nella finestra pop-out, con GLI STESSI parametri, lo stesso nome
// di finestra e le stesse misure del bottone «stacca» del LadderView
// (`components/live/LadderView.tsx`, B19: `/ladder-popout?sport&market&event&
// name&eventName&p1&p2`, finestra `ladder_<marketId>`, 560x860). Il LadderView
// non si tocca: qui c'e' la stessa ricetta per chi non ha un LadderView aperto.
// La pagina che riceve e' `pages/LadderPopout.tsx` (servono market ed event).
// ============================================================================

export interface LadderPopoutArgs {
    sport: 'calcio' | 'tennis';
    marketId: string;
    eventId?: string | null;
    /** nome del mercato (titolo della finestra); assente = il marketId */
    marketName?: string | null;
    eventName?: string | null;
    p1?: string | null;
    p2?: string | null;
}

/** Le misure della finestra, identiche al bottone «stacca» del LadderView. */
export const FINESTRA_LADDER_POPOUT = 'popup=yes,width=560,height=860,resizable=yes,scrollbars=yes';

/** Il nome della finestra: un mercato = una finestra (riaprirlo la riporta avanti). */
export function nomeFinestraLadder(marketId: string): string {
    return `ladder_${marketId}`;
}

/** L'indirizzo, con i parametri nello stesso ordine del LadderView (assenti = omessi). */
export function urlLadderPopout(a: LadderPopoutArgs): string {
    const q = new URLSearchParams({
        sport: a.sport,
        market: a.marketId,
        ...(a.eventId ? { event: a.eventId } : {}),
        ...(a.marketName ? { name: a.marketName } : {}),
        ...(a.eventName ? { eventName: a.eventName } : {}),
        ...(a.p1 ? { p1: a.p1 } : {}),
        ...(a.p2 ? { p2: a.p2 } : {}),
    });
    return `/ladder-popout?${q.toString()}`;
}

/** Apre la finestra. Ritorna false se il browser la blocca. */
export function apriLadderPopout(a: LadderPopoutArgs): boolean {
    const w = window.open(urlLadderPopout(a), nomeFinestraLadder(a.marketId), FINESTRA_LADDER_POPOUT);
    return w != null;
}
