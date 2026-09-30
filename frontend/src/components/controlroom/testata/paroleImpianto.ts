// ============================================================================
// paroleImpianto.ts - P5 (30/09): chip dei bot e impianto in parole da trader.
//
// Ordine dell'utente (30/09): "2 bot senza spinta. Distinzione "live-paper"
// hardcoded, che significa??? mike e' in live! il trader cosa sta vedendo???".
// Stessa grammatica per OGNI bot: MODO, STATO, AGGIORNATO.
//   * "senza spinta" sparisce: un bot FERMO che per costruzione non invia =
//     "fermo: non invia aggiornamenti" (grigio, normale); un bot ACCESO e muto
//     oltre la sua cadenza (`freschezzaPush`, calcolata dal hook con la cadenza
//     DICHIARATA dal servizio) = "ACCESO MA MUTO da N s" (rosso).
//   * Runner: `heartbeat_mode()` (Betfair/stream/runner.py:2176-2192) scrive le
//     modalita' che il runner PUO' servire secondo `LIVE_ORDER_MODE` del suo
//     .env (il tetto): LIVE+PAPER = "ordini veri consentiti", PAPER = "solo
//     simulati". Non dice in che modo opera un bot.
//   * Feed: `rest` = lo scanner e' in RIPIEGO (stream fermo): ambra.
// Funzioni PURE: la presentazione sta in `pages/ControlRoom.tsx` (Testata).
// ============================================================================
import { fmtAge } from '@/lib/format';
import { botStatusMeta, BOT_STATUS_META } from '@/lib/tradeStatus';
import type { Freschezza } from '@/lib/controlRoom';
import type { Modalita } from '../useControlRoom';

export type Tono = 'live' | 'paper' | 'neutro' | 'ok' | 'attenzione' | 'allarme';

export interface ParolaChip { testo: string; tono: Tono }

/**
 * MODO del bot: SEMPRE quello dichiarato dal servizio (`control.mode`), anche a
 * bot fermo: un Mike fermo in LIVE puo' avere posizioni vere aperte e ripartira'
 * in LIVE, quindi resta "LIVE" col tono live. "ultimo modo <m>" SOLO quando il
 * modo viene dal ripiego `modalitaUltima` (scalper calcio senza sessioni).
 * (T_P5b, reperto del coordinatore: prima "SPENTO - ultimo modo live" in grigio.)
 */
export function modoChip(b: {
    modalita: Modalita | null; modalitaUltima?: Modalita | null;
}): ParolaChip {
    if (b.modalita === 'live') return { testo: 'LIVE', tono: 'live' };
    if (b.modalita === 'paper') return { testo: 'PAPER', tono: 'paper' };
    if (b.modalitaUltima) return { testo: `ultimo modo ${b.modalitaUltima}`, tono: 'neutro' };
    return { testo: 'modalit\u00e0 ignota', tono: 'attenzione' };
}

/**
 * STATO del servizio con le parole del design system (`botStatusMeta`,
 * `lib/tradeStatus.ts`): running = nessuna parola in piu' (il chip dice gia'
 * il modo e l'aggiornamento); stopping = IN ARRESTO; stopped = FERMO; idle =
 * INATTIVO; error = ERRORE (rosso). Stato non letto = "stato non letto", MAI
 * "spento". Uno stato che la mappa non conosce si scrive com'e' (ambra).
 */
export function statoChip(stato: string | null | undefined): ParolaChip | null {
    const k = String(stato ?? '').trim().toLowerCase();
    if (!k) return { testo: 'stato non letto', tono: 'attenzione' };
    if (k === 'running') return null;
    if (!(k in BOT_STATUS_META)) return { testo: k.toUpperCase(), tono: 'attenzione' };
    const label = botStatusMeta(k).label;
    const tono: Tono = k === 'error' ? 'allarme' : k === 'stopping' ? 'attenzione' : 'neutro';
    return { testo: label, tono };
}

/** La frase di `PannelloBot` sul pulsante "ferma" (stessa verita', stesse parole). */
export const USCITE_ATTIVE_TITOLO = 'Le posizioni gi\u00e0 aperte restano sorvegliate: coperture, green-up, cash out e regolamento continuano';

/**
 * Bot NON in corsa che, per dichiarazione del servizio
 * (`stats.stop_ferma_solo_aperture`), ha fermato solo le APERTURE: le uscite
 * continuano. Non dichiarato = non si afferma nulla sulle uscite.
 */
export function usciteChip(b: { stato: string | null | undefined; stopFermaSoloAperture?: boolean }):
    { testo: string; titolo: string } | null {
    const k = String(b.stato ?? '').trim().toLowerCase();
    if (k === 'running' || b.stopFermaSoloAperture !== true) return null;
    return { testo: 'aperture ferme \u00b7 uscite attive', titolo: `aperture ferme. ${USCITE_ATTIVE_TITOLO}` };
}

/** Il pallino: acceso sano / acceso muto / fermo in LIVE (puo' avere posizioni vere) / fermo. */
export function pallinoChip(b: { inCorsa: boolean; muto: boolean; modalita: Modalita | null }):
    'vivo' | 'muto' | 'fermo-live' | 'fermo' {
    if (b.inCorsa) return b.muto ? 'muto' : 'vivo';
    return b.modalita === 'live' ? 'fermo-live' : 'fermo';
}

/**
 * AGGIORNATO: eta' della notizia piu' recente (push del canale, altrimenti il
 * battito del servizio). `freschezza` e' quella del hook (`freschezzaBattito`
 * con la cadenza dichiarata dal servizio): nessuna soglia nuova qui.
 */
export function aggiornatoChip(b: {
    inCorsa: boolean; etaS: number | null; freschezza: Freschezza;
}): ParolaChip {
    const eta = b.etaS == null ? null : Math.max(0, Math.round(b.etaS));
    if (!b.inCorsa) {
        return eta == null
            ? { testo: 'fermo: non invia aggiornamenti', tono: 'neutro' }
            : { testo: `aggiornato ${fmtAge(eta)} fa`, tono: 'neutro' };
    }
    if (b.freschezza === 'vecchia' || b.freschezza === 'ignota') {
        return {
            testo: eta == null ? 'ACCESO MA MUTO: nessun aggiornamento ricevuto' : `ACCESO MA MUTO da ${fmtAge(eta)}`,
            tono: 'allarme',
        };
    }
    return { testo: `aggiornato ${fmtAge(eta)} fa`, tono: b.freschezza === 'lenta' ? 'attenzione' : 'ok' };
}

/** Il tetto del runner (colonna `mode` del battito) in parole vere. */
export function tettoRunner(mode: string | null | undefined): { testo: string; titolo: string } | null {
    const m = String(mode ?? '').trim().toUpperCase();
    if (!m) return null;
    const titolo = 'tetto del file di configurazione del runner (LIVE_ORDER_MODE): cosa PUO\' servire. '
        + 'Con che soldi opera ogni bot lo dicono i chip dei bot e la riga "Ordini reali".';
    if (m === 'LIVE+PAPER' || m === 'LIVE') return { testo: 'ordini veri consentiti', titolo };
    if (m === 'PAPER') return { testo: 'solo simulati', titolo };
    if (m === 'OFF') return { testo: 'ordini spenti', titolo };
    return { testo: `tetto ${m.toLowerCase()}`, titolo };
}

/** La sorgente delle quote dello scanner. */
export function sorgenteFeed(sorgente: string | null | undefined): { testo: string; tono: Tono } {
    const s = String(sorgente ?? '').trim().toLowerCase();
    if (s === 'rest') return { testo: 'RIPIEGO REST (stream fermo)', tono: 'attenzione' };
    if (s === 'stream') return { testo: 'stream', tono: 'ok' };
    if (!s) return { testo: 'sorgente ignota', tono: 'attenzione' };
    return { testo: s, tono: 'neutro' };
}

/**
 * "Dati: tempo reale" oppure "Dati: dal database (ogni 30 s) per: ...".
 * `fonti` = per ogni voce se arriva dal canale locale (true) o dal database.
 */
export function riassuntoDati(fonti: ReadonlyArray<{ nome: string; canale: boolean }>): { testo: string; tono: Tono } {
    const lenti = fonti.filter((f) => !f.canale).map((f) => f.nome);
    if (lenti.length === 0) return { testo: 'Dati: tempo reale', tono: 'ok' };
    return { testo: `Dati: dal database (ogni 30 s) per: ${lenti.join(', ')}`, tono: 'attenzione' };
}
