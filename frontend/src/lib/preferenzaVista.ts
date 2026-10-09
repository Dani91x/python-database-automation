// ============================================================================
// preferenzaVista — un interruttore mostra/nascondi ricordato PER VIEWER.
//
// 09/10 (ordine dell'utente, Control Room): «toggle per nascondere» una
// sezione. E' una preferenza di vista, non un dato: vive in `localStorage`
// (mai sul server), come le tendine di `PannelloBot` e i filtri di
// `SectionFilter`. `localStorage` puo' lanciare (finestra privata, quota
// piena): ogni accesso e' protetto e il default e' VISIBILE, cioe' la pagina
// di oggi (nessuna regressione al primo avvio).
// ============================================================================
import { useCallback, useState } from 'react';

const PREFISSO = 'vista.';

/** Legge la preferenza salvata; assente o illeggibile = `predefinito`. */
export function leggiVisibile(chiave: string, predefinito = true): boolean {
    try {
        const v = window.localStorage.getItem(PREFISSO + chiave);
        if (v === '1') return true;
        if (v === '0') return false;
        return predefinito;
    } catch {
        return predefinito;
    }
}

/** Scrive la preferenza. Ritorna false se l'archiviazione e' bloccata. */
export function scriviVisibile(chiave: string, v: boolean): boolean {
    try {
        window.localStorage.setItem(PREFISSO + chiave, v ? '1' : '0');
        return true;
    } catch {
        return false;
    }
}

/** [visibile, imposta]: lo stato sopravvive al ricaricamento della pagina. */
export function useVisibile(chiave: string, predefinito = true): [boolean, (v: boolean) => void] {
    const [visibile, setVisibile] = useState<boolean>(() => leggiVisibile(chiave, predefinito));
    const imposta = useCallback((v: boolean) => {
        setVisibile(v);
        scriviVisibile(chiave, v);
    }, [chiave]);
    return [visibile, imposta];
}
