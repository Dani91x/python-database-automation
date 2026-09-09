// ============================================================================
// betfairMedia.ts — pop-out live ufficiale dell'Exchange Betfair.
//
// URL verificato dal vivo (es. Udinese–Venezia):
//   https://www.betfair.it/exchange/plus/pop-out-live-stream/<eventId>?feedType=...
// I valori di feedType sono quelli del bundle ufficiale Betfair (LiveStreamMod
// CONFIG.tabs, letti il 09/09 nel sorgente app.*.js servito dal popout):
//   · liveVideo         → stream video vero (dove Betfair ha i diritti; richiede
//                          la sessione web: "requireLogin: true");
//   · dataVisualization → "Visualizzazione partita" (animazione);
//   · matchStats        → "Statistiche partita" (tutte le tab interne).
// Un feedType sconosciuto (il vecchio `video`) NON dà errore lato Betfair: il
// popout ripiega sulla PRIMA tab disponibile — video se c'è, altrimenti la
// visualizzazione — quindi il pulsante "Video" apriva una cosa a caso. Da qui
// i valori esatti.
// Serve la sessione web dell'utente: l'app desktop la inietta all'avvio via SSO
// (desktop/main.js) e apre queste finestre solo a SSO pronto; nel browser il
// popout chiede il login una tantum. Dominio .it: account italiano.
// Nessun dato passa da qui: sono solo scorciatoie di navigazione.
// ============================================================================

export type BetfairFeedType = 'liveVideo' | 'dataVisualization' | 'matchStats';

const POPOUT_HOST = 'https://www.betfair.it';

/** Pop-out live dell'Exchange per un evento (video / animazione / statistiche). */
export function betfairLivePopoutUrl(eventId: string, feed: BetfairFeedType): string {
    return `${POPOUT_HOST}/exchange/plus/pop-out-live-stream/${encodeURIComponent(eventId)}?feedType=${feed}`;
}

/** Nome finestra STABILE per evento+feed: un secondo click sullo stesso pulsante
 *  riporta davanti la finestra già aperta invece di aprirne un'altra (browser:
 *  target per nome; desktop: mappa frameName → BrowserWindow in main.js).
 *  Solo caratteri sicuri per un window name. */
export function betfairPopoutWindowName(eventId: string, feed: BetfairFeedType): string {
    return `bf_${feed}_${eventId.replace(/[^0-9A-Za-z_]/g, '_')}`;
}

/** Dimensioni tarate sul popout Betfair (colonna singola, contenuto verticale). */
export const BETFAIR_POPOUT_FEATURES = 'width=640,height=780';

function isElectron(): boolean {
    return typeof navigator !== 'undefined' && /electron/i.test(navigator.userAgent);
}

/** Apre il popout in finestra separata (desktop: BrowserWindow gestita da
 *  main.js, già loggata; browser: popup). Ritorna false SOLO se il browser ha
 *  bloccato l'apertura (popup blocker), così la UI può avvisare. In Electron
 *  l'apertura passa dal main process (handler → finestra propria) e window.open
 *  ritorna null anche quando la finestra si apre: lì il null non è un blocco. */
export function openBetfairPopout(eventId: string, feed: BetfairFeedType): boolean {
    const w = window.open(
        betfairLivePopoutUrl(eventId, feed),
        betfairPopoutWindowName(eventId, feed),
        BETFAIR_POPOUT_FEATURES,
    );
    return w !== null || isElectron();
}
