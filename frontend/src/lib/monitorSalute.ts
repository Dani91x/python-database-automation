// ============================================================================
// monitorSalute.ts - 09/10 (R-5 della verifica del PC): la voce di menu
// «Salute» si vede SOLO con il monitor acceso.
//
// Acceso = la riga `MONITOR_SALUTE=1` nel `.env` del checkout principale, la
// STESSA che accende il monitor nei servizi Python. `vite.config.ts` la legge al
// momento della build e la passa come `VITE_MONITOR_SALUTE`: un solo
// interruttore, nessuna chiamata al backend (la fotografia di parita' vieta al
// guscio letture nuove). Dopo aver cambiato la riga: `npm run build` ad app spenta.
// Valore assente o diverso da '1' = spento. La rotta /salute resta raggiungibile.
// ============================================================================

/** True solo se la build e' stata fatta con `MONITOR_SALUTE=1`. */
export function monitorSaluteAcceso(): boolean {
    try {
        return import.meta.env.VITE_MONITOR_SALUTE === '1';
    } catch {
        return false;
    }
}
