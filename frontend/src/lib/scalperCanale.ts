// ============================================================================
// scalperCanale.ts - 25/09: LO SCALPER CALCIO DAL SUO CANALE (47338).
//
// Ordine dell'utente (25/09): «pubblicalo sul canale come tutti gli altri».
// Il supervisore (`Betfair/stream/scalper/scalper_service.py`) pubblica, con la
// busta di `canale_bot` (`fonte`/`_seq`/`_pubblicato_ms`):
//   * `scalper_stato`    = la riga di `scalper_service_control` (chiave `id`);
//   * `scalper_sessioni` = la riga di `scalper_control` di UNA sessione
//                          (chiave `event_id`, stringa).
// Stesse regole delle righe degli altri bot (`lib/righeCanale.ts`):
//   1. il canale NON aggiunge righe: una sessione che la lettura del database
//      non conosce chiede una RILETTURA (la porta il database), non entra;
//   2. un messaggio vince sul database solo se pubblicato DOPO l'inizio della
//      lettura (`_pubblicato_ms > letturaMs`); fra due messaggi vince
//      (`_pubblicato_ms`, `_seq`) maggiore;
//   3. una sessione che col messaggio DIVENTA ferma chiede una rilettura
//      (gli ordini e il P&L della chiusura li porta il database).
// Le colonne aggiunte dalla RPC (event_name, league_name, kickoff, ultima
// attivita') il canale non le porta: restano quelle del database.
//
// Modulo PURO: nessuna rete, nessun React.
// ============================================================================
import type { MessaggioRiga } from '@/lib/righeCanale';
import {
    sessioneViva, type ScalperControlRoom, type ServizioScalper, type SessioneScalper,
} from '@/lib/scalperControlRoom';

export const TOPIC_SCALPER_STATO = 'scalper_stato';
export const TOPIC_SCALPER_SESSIONI = 'scalper_sessioni';

export interface VoceCanaleScalper {
    riga: Record<string, unknown>;
    ms: number;
    seq: number;
    /** quando la PAGINA l'ha ricevuto (per l'eta' dichiarata) */
    ricevutoMs: number;
}

export interface OverlayScalper {
    sessioni: ReadonlyMap<string, VoceCanaleScalper>;
    servizio: VoceCanaleScalper | null;
}

export function overlayScalperVuoto(): OverlayScalper {
    return { sessioni: new Map(), servizio: null };
}

function piuNuovo(msg: MessaggioRiga, v: VoceCanaleScalper | null | undefined): boolean {
    if (v == null) return true;
    return msg.ms > v.ms || (msg.ms === v.ms && msg.seq > v.seq);
}

/**
 * Un messaggio `scalper_sessioni`. Ritorna l'overlay (lo STESSO oggetto se il
 * messaggio si scarta: nessun render) e se serve una rilettura del database.
 */
export function applicaSessioneCanale(
    ov: OverlayScalper, cr: ScalperControlRoom | null, letturaMs: number | null,
    msg: MessaggioRiga, ricevutoMs: number,
): { ov: OverlayScalper; rileggi: boolean } {
    const ev = String(msg.id);
    const db = cr?.sessioni.find((s) => String(s.event_id) === ev) ?? null;
    if (db == null) return { ov, rileggi: true };           // regola 1
    if (letturaMs != null && !(msg.ms > letturaMs)) return { ov, rileggi: false };
    const prima = ov.sessioni.get(ev);
    if (!piuNuovo(msg, prima)) return { ov, rileggi: false };
    const vistaPrima = prima ? { ...db, ...prima.riga } as SessioneScalper : db;
    const dopo = { ...db, ...msg.riga } as SessioneScalper;
    const rileggi = sessioneViva(vistaPrima) && !sessioneViva(dopo);   // regola 3
    const sessioni = new Map(ov.sessioni);
    sessioni.set(ev, { riga: msg.riga, ms: msg.ms, seq: msg.seq, ricevutoMs });
    return { ov: { ...ov, sessioni }, rileggi };
}

/** Un messaggio `scalper_stato` (la riga dell'interruttore, `id` = 1). */
export function applicaServizioCanale(
    ov: OverlayScalper, letturaMs: number | null, msg: MessaggioRiga, ricevutoMs: number,
): OverlayScalper {
    if (msg.id !== 1) return ov;
    if (letturaMs != null && !(msg.ms > letturaMs)) return ov;
    if (!piuNuovo(msg, ov.servizio)) return ov;
    return { ...ov, servizio: { riga: msg.riga, ms: msg.ms, seq: msg.seq, ricevutoMs } };
}

/**
 * Quello che la pagina mostra: le righe del database con sopra le colonne del
 * canale PIU' FRESCHE dell'inizio della lettura. Canale muto = la lettura
 * identica (stesso oggetto).
 */
export function vistaScalper(
    cr: ScalperControlRoom | null, letturaMs: number | null, ov: OverlayScalper,
): ScalperControlRoom | null {
    if (cr == null) return null;
    const fresca = (v: VoceCanaleScalper | null | undefined): v is VoceCanaleScalper =>
        v != null && (letturaMs == null || v.ms > letturaMs);
    let cambiata = false;
    const sessioni = cr.sessioni.map((s) => {
        const v = ov.sessioni.get(String(s.event_id));
        if (!fresca(v)) return s;
        cambiata = true;
        return { ...s, ...v.riga, event_id: s.event_id } as SessioneScalper;
    });
    let servizio = cr.servizio ?? null;
    if (fresca(ov.servizio) && cr.servizioLetto) {
        servizio = { ...(servizio ?? {}), ...ov.servizio.riga } as unknown as ServizioScalper;
        cambiata = true;
    }
    if (!cambiata) return cr;
    return { ...cr, sessioni, servizio };
}

/** Da quanto (s) la riga di QUESTA sessione e' dal canale, o `null` (database). */
export function etaCanaleSessione(
    ov: OverlayScalper, letturaMs: number | null, eventId: string, nowMs: number,
): number | null {
    const v = ov.sessioni.get(String(eventId));
    if (v == null || (letturaMs != null && !(v.ms > letturaMs))) return null;
    return Math.max(0, Math.round((nowMs - v.ricevutoMs) / 1000));
}

/** L'ultima notizia del canale ancora in uso (ricezione), o `null`. */
export function ultimoCanaleScalper(ov: OverlayScalper, letturaMs: number | null): number | null {
    let out: number | null = null;
    const usa = (v: VoceCanaleScalper | null | undefined) => {
        if (v == null || (letturaMs != null && !(v.ms > letturaMs))) return;
        if (out == null || v.ricevutoMs > out) out = v.ricevutoMs;
    };
    usa(ov.servizio);
    for (const v of ov.sessioni.values()) usa(v);
    return out;
}
