// ============================================================================
// betfairMedia.ts — deep-link a video live e statistiche/mercato Betfair.
//
// Video live e statistiche match (OPTA) NON hanno API pubblica: come fanno i
// software di trading concorrenti, si aprono le pagine Betfair in una finestra
// separata che usa la SESSIONE WEB dell'utente (login sul sito Betfair fatto
// una volta nella finestra stessa; nell'app desktop i cookie persistono).
// Nessun dato passa da qui: sono solo scorciatoie di navigazione, riusate da
// tutte le sezioni (Safe Strategy, Omega, Segui Live, Tennis, ladder, board).
// ============================================================================

/** Player video live Betfair per un evento (richiede login Betfair + evento con stream). */
export function betfairVideoUrl(eventId: string): string {
    return `https://videoplayer.betfair.com/GetPlayer.do?contentType=viewer&eID=${encodeURIComponent(eventId)}&allowPopup=true`;
}

/** Pagina Exchange del mercato (quote + widget statistiche/video per i loggati). */
export function betfairMarketUrl(marketId: string | null | undefined): string {
    return marketId
        ? `https://www.betfair.com/exchange/plus/market/${encodeURIComponent(marketId)}`
        : 'https://www.betfair.com/exchange/plus/';
}

/** Pagina Exchange dell'EVENTO (fallback quando il market_id non è noto). */
export function betfairEventUrl(eventId: string, sport: 'calcio' | 'tennis' = 'calcio'): string {
    const seg = sport === 'tennis' ? 'tennis' : 'football';
    return `https://www.betfair.com/exchange/plus/${seg}/event/${encodeURIComponent(eventId)}`;
}

/** Apre in finestra separata (desktop: BrowserWindow Chromium; browser: popup). */
export function openBetfairWindow(url: string): void {
    window.open(url, '_blank', 'noopener,width=980,height=700');
}
