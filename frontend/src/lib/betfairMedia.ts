// ============================================================================
// betfairMedia.ts — pop-out live ufficiale dell'Exchange Betfair.
//
// URL verificato dal vivo (es. Udinese–Venezia):
//   https://www.betfair.it/exchange/plus/pop-out-live-stream/<eventId>?feedType=...
// Il popout contiene GIÀ tutto quello che offre Betfair per l'evento:
//   · feedType=dataVisualization → "Visualizzazione partita" (animazione) +
//     "Statistiche partita" con tutte le sue tab interne;
//   · feedType=video            → lo stream video vero (dove Betfair ha i diritti).
// Serve la sessione web dell'utente: l'app desktop la inietta all'avvio via SSO
// (desktop/main.js); nel browser il popout chiede il login una tantum.
// Dominio .it: account su giurisdizione italiana (config.py → identitysso .it).
// Nessun dato passa da qui: sono solo scorciatoie di navigazione.
// ============================================================================

export type BetfairFeedType = 'video' | 'dataVisualization';

/** Pop-out live dell'Exchange per un evento (video o animazione+statistiche). */
export function betfairLivePopoutUrl(eventId: string, feed: BetfairFeedType): string {
    return `https://www.betfair.it/exchange/plus/pop-out-live-stream/${encodeURIComponent(eventId)}?feedType=${feed}`;
}

/** Apre in finestra separata (desktop: BrowserWindow Chromium; browser: popup).
 *  Dimensioni tarate sul popout Betfair (colonna singola, contenuto verticale). */
export function openBetfairWindow(url: string): void {
    window.open(url, '_blank', 'noopener,width=640,height=780');
}
