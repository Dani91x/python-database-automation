// ============================================================================
// saldoBetfair.ts — regola PURA per lo stato di freschezza del saldo del
// conto Betfair mostrato in Control Room (riusa `betfair_live_account`/
// `betfair_live_heartbeat`, già lette da `pages/SeguiLive.tsx`, vedi
// `lib/liveOrders.ts`: nessuna tabella nuova).
//
// PERCHÉ una funzione isolata (18/09, ordine esplicito del task): oggi la riga
// del saldo si scrive SOLO al cambio (write-on-change) — un `updated_at`
// vecchio non vuol dire per forza «saldo sbagliato». Ma sul DB di oggi è
// vecchio di GIORNI perché il sincronizzatore (`reconcile_worker.py`) girava
// solo quando il runner calcio era acceso in PAPER/LIVE, e un altro
// costruttore sta correggendo QUEL pezzo. Finché non arriva un segnale di
// freschezza migliore, questa funzione decide UN'UNICA regola onesta, e il
// futuro aggancio (contratto nuovo) cambia SOLO l'input, mai questa funzione.
// ============================================================================

export type StatoSaldo = 'ok' | 'non-verificato' | 'ignoto';

export interface StatoSaldoBetfair {
    stato: StatoSaldo;
    /** frase pronta per la UI: "ultimo cambio: 8 s fa", "saldo non verificato di recente"… */
    messaggio: string;
    /** true = mostrare in arancione (dato non verificato di recente) */
    attenzione: boolean;
}

/** oltre questa età (secondi) del battito del runner, il saldo non è
 *  considerato "verificato di recente" anche se il valore è lo stesso da
 *  sempre (write-on-change: nessun cambio non vuol dire nessun controllo). */
export const SALDO_HEARTBEAT_STALE_S = 120;

export function statoSaldoBetfair(input: {
    /** età del saldo (updated_at → ora), secondi; null = mai scritto */
    etaSaldoS: number | null;
    /** età dell'ultimo battito del runner, secondi; null/undefined = non letto */
    etaHeartbeatS?: number | null;
    /**
     * 18/09 (raccordo) — età dell'ultimo "checked_at" ricevuto dal CANALE
     * LOCALE del runner (porta 47331, topic "account", vedi
     * `CHECKPOINT_B1_SALDO_E_MANUALI_2026-09-18.md` §6): pubblicato a OGNI
     * lettura REST riuscita, cambiata o no. È più preciso del `updated_at`
     * del database (write-on-change: un saldo IDENTICO da ore non vuol dire
     * "non controllato da ore"). `null`/`undefined` = canale muto o app non
     * desktop: si ripiega sul battito/DB, dichiarato nel messaggio.
     */
    etaCanaleS?: number | null;
}): StatoSaldoBetfair {
    const { etaSaldoS, etaHeartbeatS, etaCanaleS } = input;

    if (etaSaldoS == null) {
        return { stato: 'ignoto', messaggio: 'saldo mai letto', attenzione: true };
    }

    // IL CANALE LOCALE, quando parla, è la fonte più precisa: dice "il
    // servizio ha controllato adesso", non solo "il valore non è cambiato
    // da allora" (write-on-change). Fresco → "ok" anche se il DB non ha
    // scritto nulla di nuovo (l'ultima lettura ha confermato lo stesso saldo).
    if (etaCanaleS != null) {
        if (etaCanaleS <= SALDO_HEARTBEAT_STALE_S) {
            return {
                stato: 'ok',
                messaggio: `controllato ${formatoEta(etaCanaleS)} (canale locale del runner)`,
                attenzione: false,
            };
        }
        return {
            stato: 'non-verificato',
            messaggio: `ultimo controllo dal canale locale: ${formatoEta(etaCanaleS)} — non verificato di recente`,
            attenzione: true,
        };
    }

    // il battito non è stato letto: NON deduciamo nulla di male (fail-open
    // sull'informazione, non sull'azione), ma non possiamo nemmeno dire
    // "verificato di recente" — si dichiara solo l'età del dato.
    if (etaHeartbeatS == null) {
        return {
            stato: 'non-verificato',
            messaggio: `ultimo cambio: ${formatoEta(etaSaldoS)} — battito del runner non letto`,
            attenzione: true,
        };
    }

    if (etaHeartbeatS > SALDO_HEARTBEAT_STALE_S) {
        return {
            stato: 'non-verificato',
            messaggio: `ultimo cambio: ${formatoEta(etaSaldoS)} — saldo non verificato di recente`,
            attenzione: true,
        };
    }

    return {
        stato: 'ok',
        messaggio: `ultimo cambio: ${formatoEta(etaSaldoS)}`,
        attenzione: false,
    };
}

/** un formattatore MINIMO e locale, solo per il messaggio di questa funzione
 *  pura (che non può importare `lib/format.ts`/React): la UI che la consuma
 *  usa comunque `fmtAge` per il numero mostrato a schermo, questa stringa
 *  serve solo ai test e a un eventuale titolo/tooltip testuale. */
function formatoEta(s: number): string {
    if (s < 60) return `${Math.max(0, Math.round(s))} s fa`;
    const min = Math.round(s / 60);
    return `${min} min fa`;
}
