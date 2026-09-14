// ============================================================================
// ritorno.ts — TORNARE ESATTAMENTE DOVE SI ERA.
//
// «OGNI PULSANTE CHE MI MANDA DA ALTRE PARTI DEVE POI PERMETTERMI DI TORNARE
// INDIETRO IN QUELL'ESATTO PUNTO» (utente, 14/09).
//
// Nel software questo non esisteva: c'era solo `?from=omega`, che riporta
// alla PAGINA e la fa ripartire dal tab predefinito, in cima. Su una pagina
// con 59 partite e quattro schede, «torna a Omega» vuol dire ricominciare a
// cercare.
//
// UN PUNTO DI RITORNO sono quattro cose, e servono tutte e quattro:
//   · la rotta         — dove tornare;
//   · la scheda        — quale tab era aperta;
//   · la partita       — quale riga stava guardando, per riportarla in vista
//                        e accenderla un attimo;
//   · lo scorrimento   — a che altezza era la pagina, per gli altri casi.
//
// DOVE VIVE: `sessionStorage`. Non l'URL, perche' lo scorrimento e la scheda
// sporcherebbero un indirizzo che il trader potrebbe condividere; non la
// memoria del processo, perche' una navigazione vera ricarica tutto. Nella
// sessione del browser e basta: chiusa la scheda, il punto muore con lei.
//
// REGOLA: `sessionStorage` puo' non esserci (finestra anonima, dati bloccati)
// e puo' contenere spazzatura scritta da una versione precedente. Ogni
// lettura e' difensiva e in caso di dubbio ritorna `null`: si perde il
// ritorno preciso, non la navigazione.
// ============================================================================

const CHIAVE = 'ritorno.punto';

/** Dove tornare, e con quale vista. */
export interface PuntoDiRitorno {
    /** rotta completa, es. '/control-room' */
    rotta: string;
    /** etichetta per il pulsante, es. 'Control Room' */
    nome: string;
    /** la scheda aperta in quel momento; null = quella predefinita */
    scheda: string | null;
    /** l'evento che stava guardando; null = nessuno in particolare */
    eventId: string | null;
    /** altezza della pagina in pixel */
    scorrimento: number;
    /** quando e' stato salvato (ms) */
    quando: number;
}

/**
 * Oltre questo tempo un punto di ritorno non vale piu'.
 *
 * Non e' prudenza generica: su una pagina di partite in corso, tornare dopo
 * mezz'ora alla riga di allora significa tornare su una partita finita,
 * magari scorrendo su una posizione che nel frattempo e' un'altra. Scaduto
 * il punto si torna alla pagina, che e' onesto, invece di fingere precisione.
 */
export const VALIDO_PER_MS = 15 * 60 * 1000;

function magazzino(): Storage | null {
    try {
        // l'accesso stesso puo' lanciare (dati del sito bloccati)
        return typeof sessionStorage === 'undefined' ? null : sessionStorage;
    } catch {
        return null;
    }
}

/** Salva il punto da cui si sta partendo. Non lancia mai. */
export function salvaRitorno(p: Omit<PuntoDiRitorno, 'quando'>): void {
    const m = magazzino();
    if (!m) return;
    try {
        m.setItem(CHIAVE, JSON.stringify({ ...p, quando: Date.now() }));
    } catch { /* memoria piena o negata: si perde il ritorno, non la navigazione */ }
}

/** Legge il punto salvato. `null` se non c'e', se e' illeggibile o se e'
 *  scaduto. Non lancia mai. */
export function leggiRitorno(adessoMs: number = Date.now()): PuntoDiRitorno | null {
    const m = magazzino();
    if (!m) return null;
    let grezzo: string | null = null;
    try { grezzo = m.getItem(CHIAVE); } catch { return null; }
    if (!grezzo) return null;

    let d: unknown;
    try { d = JSON.parse(grezzo); } catch { return null; }
    if (d == null || typeof d !== 'object') return null;
    const o = d as Record<string, unknown>;

    const rotta = typeof o.rotta === 'string' && o.rotta.startsWith('/') ? o.rotta : null;
    if (!rotta) return null;          // senza rotta non e' un punto di ritorno
    const quando = typeof o.quando === 'number' && Number.isFinite(o.quando) ? o.quando : null;
    if (quando == null || adessoMs - quando > VALIDO_PER_MS || adessoMs < quando) return null;

    return {
        rotta,
        nome: typeof o.nome === 'string' && o.nome.trim() ? o.nome : 'pagina precedente',
        scheda: typeof o.scheda === 'string' && o.scheda ? o.scheda : null,
        eventId: typeof o.eventId === 'string' && o.eventId ? o.eventId : null,
        scorrimento: typeof o.scorrimento === 'number' && Number.isFinite(o.scorrimento)
            && o.scorrimento >= 0 ? Math.round(o.scorrimento) : 0,
        quando,
    };
}

/** Cancella il punto: si usa DOPO averlo consumato, così un secondo ritorno
 *  non riporta a un posto in cui non si è più stati. */
export function dimenticaRitorno(): void {
    const m = magazzino();
    if (!m) return;
    try { m.removeItem(CHIAVE); } catch { /* niente da fare, e non importa */ }
}

/**
 * Riporta in vista la riga di un evento e la accende per un attimo.
 *
 * Lo stesso gesto che fa gia' Mike (`pages/Mike.tsx`, `openEventCard`): la
 * riga si evidenzia per due secondi, perche' «portata in vista» senza un
 * segnale visivo su una lista di sessanta righe non si nota.
 *
 * Ritorna `true` se la riga esisteva: se no, chi chiama puo' dire che la
 * partita non c'e' piu' invece di lasciare il trader a cercarla.
 */
export function portaInVista(eventId: string, doc: Document = document): boolean {
    const el = doc.querySelector<HTMLElement>(`[data-event-id="${CSS.escape(eventId)}"]`);
    if (!el) return false;
    try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch { el.scrollIntoView(); }
    el.classList.add('ring-2', 'ring-primary');
    window.setTimeout(() => el.classList.remove('ring-2', 'ring-primary'), 2000);
    return true;
}
