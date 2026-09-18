// ============================================================================
// obiettivoEditor.ts — validazione PURA della modifica dell'obiettivo di
// giornata dalla Control Room.
//
// L'obiettivo vive in `omega_control.daily_goal` (vedi `lib/omega.ts`,
// `updateOmegaParams`). Questo file non scrive nulla: dice solo se un testo
// digitato dall'utente e' un obiettivo valido, con un messaggio in italiano.
// La UI (bozza + conferma) sta in `components/controlroom/ObiettivoEditor.tsx`.
// ============================================================================

/** stesso tetto della colonna `daily_goal` (CHECK 0..100000, vedi
 *  `migrations/omega_daily_v2.sql` e `lib/omega.ts: OMEGA_DAILY_GOAL_MAX`) */
export const OBIETTIVO_MAX = 100000;

export interface ValidazioneObiettivo {
    ok: boolean;
    /** il valore normalizzato (2 decimali), solo se `ok` */
    valore: number | null;
    /** messaggio in italiano da mostrare accanto al campo, solo se NON `ok` */
    errore: string | null;
}

/**
 * Valida il testo digitato nel campo dell'obiettivo.
 *
 * Regole: numero (virgola o punto), maggiore di zero, al massimo due
 * decimali, entro il tetto della colonna. Un numero non valido non produce
 * MAI un `valore`: chi chiama non deve poter salvare un `NaN` per errore.
 */
export function validaObiettivo(input: string): ValidazioneObiettivo {
    const testo = (input ?? '').trim();
    if (!testo) {
        return { ok: false, valore: null, errore: 'inserisci un importo' };
    }
    const normalizzato = testo.replace(',', '.');
    if (!/^\d+(\.\d{1,2})?$/.test(normalizzato)) {
        return {
            ok: false, valore: null,
            errore: 'usa un numero con al massimo due decimali (es. 50 o 50,00)',
        };
    }
    const n = Number(normalizzato);
    if (!Number.isFinite(n)) {
        return { ok: false, valore: null, errore: 'numero non valido' };
    }
    if (n <= 0) {
        return { ok: false, valore: null, errore: "l'obiettivo deve essere maggiore di zero" };
    }
    if (n > OBIETTIVO_MAX) {
        return {
            ok: false, valore: null,
            errore: `l'obiettivo massimo e' ${OBIETTIVO_MAX.toLocaleString('it-IT')} €`,
        };
    }
    return { ok: true, valore: Math.round(n * 100) / 100, errore: null };
}
