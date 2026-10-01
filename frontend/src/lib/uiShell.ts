// ============================================================================
// uiShell — l'INTERRUTTORE del redesign «guscio v2» (01/10/2026).
//
// Ordine dell'utente: «Devo poter tornare alla vecchia app con un click».
// Due valori soltanto: 'off' (l'app di oggi, identica) e 'v2' (le stesse pagine
// dentro la cornice nuova: sidebar + testata). Spento di default.
//
// Da dove si legge, in quest'ordine:
//   1. la chiave locale `localStorage['ui.shell']` (la scrive il clic su
//      «Prova la nuova grafica» / «Torna alla grafica attuale»): vince sempre;
//   2. la variabile di build `VITE_UI_SHELL` ('v2' | 'off');
//   3. altrimenti 'off'.
// Un valore estraneo vale come assente. Un localStorage che lancia (finestra
// privata, archiviazione bloccata) vale come assente: mai un'eccezione verso
// l'app, mai il guscio acceso per sbaglio.
// Nessun altro stato e' persistito: questa e' l'unica chiave del redesign.
// ============================================================================

export type UiShell = 'v2' | 'off';

export const CHIAVE_UI_SHELL = 'ui.shell';

function valido(v: unknown): UiShell | null {
    return v === 'v2' || v === 'off' ? v : null;
}

function leggiChiaveLocale(): UiShell | null {
    try {
        return valido(window.localStorage.getItem(CHIAVE_UI_SHELL));
    } catch {
        return null;
    }
}

function leggiVariabileDiBuild(): UiShell | null {
    try {
        return valido(import.meta.env.VITE_UI_SHELL);
    } catch {
        return null;
    }
}

/** Stato attuale dell'interruttore: chiave locale, poi variabile di build, poi 'off'. */
export function leggiUiShell(): UiShell {
    return leggiChiaveLocale() ?? leggiVariabileDiBuild() ?? 'off';
}

/** Scrive la scelta nella chiave locale. Ritorna false se l'archiviazione e' bloccata. */
export function scriviUiShell(v: UiShell): boolean {
    try {
        window.localStorage.setItem(CHIAVE_UI_SHELL, v);
        return true;
    } catch {
        return false;
    }
}

/**
 * Il clic dei due bottoni: scrive la scelta e ricarica la pagina sulla STESSA
 * rotta, cosi' l'albero delle rotte riparte da zero nello stato scelto.
 */
export function cambiaUiShell(v: UiShell, ricarica: () => void = () => window.location.reload()): void {
    scriviUiShell(v);
    ricarica();
}

/**
 * Dove si atterra dopo l'accesso. Con il guscio SPENTO resta '/select-sport',
 * come oggi (LandingPage e AuthSection). Col guscio ACCESO la prima schermata e'
 * il Programma del giorno ('/board'), la prima voce della sidebar: e' la stessa
 * pagina che l'exe apre all'avvio (desktop/main.js).
 */
export function rottaDopoAccesso(): '/board' | '/select-sport' {
    return leggiUiShell() === 'v2' ? '/board' : '/select-sport';
}
