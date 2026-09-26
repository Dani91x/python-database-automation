// ============================================================================
// erroreRpc.ts - un errore di una RPC NON e' "nessun dato" (FIX-B, 26/09/2026).
//
// Reperto KO2 della fase 3 (AUDIT_2026-09-25/E2E_FASE3_PAGINE_SESSIONE_B_2026-09-26.md):
// get_analytics andava in "canceling statement due to statement timeout" (limite 8 s
// del ruolo authenticated) e la pagina mostrava anche "Nessun segnale settlato per
// questi filtri": un timeout presentato come assenza di dati. Qui l'unico posto che
// traduce il messaggio del database in una frase per il trader.
// ============================================================================

export type TipoErroreRpc = 'timeout' | 'errore';

export interface ErroreRpc {
    tipo: TipoErroreRpc;
    /** frase da mostrare: dice sempre che i dati NON sono "vuoti" */
    testo: string;
    /** messaggio originale del database (per il dettaglio) */
    originale: string;
}

// 57014 = query_canceled (statement_timeout); PostgREST riporta il testo di Postgres
const RE_TIMEOUT = /statement timeout|canceling statement|57014|timed out|timeout/i;

export function classificaErroreRpc(msg: unknown): ErroreRpc {
    const originale = (msg instanceof Error ? msg.message : String(msg ?? '')).trim() || 'errore sconosciuto';
    if (RE_TIMEOUT.test(originale)) {
        return {
            tipo: 'timeout',
            testo: 'Il database non ha risposto in tempo (limite 8 s): i dati NON sono vuoti, la lettura e\' stata interrotta. Riprova tra poco.',
            originale,
        };
    }
    return { tipo: 'errore', testo: `Errore del database: ${originale}. I dati non sono stati letti.`, originale };
}

/** orario di un riepilogo in ora di Roma, "dd/mm/yyyy, hh:mm"; null/invalid -> null */
export function fmtOrarioRiepilogo(iso: string | null | undefined): string | null {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString('it-IT', {
        timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
}
