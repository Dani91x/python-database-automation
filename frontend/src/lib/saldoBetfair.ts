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
import { fmtTime, DASH } from './format';

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

// ============================================================================
// 23/09 — IL VALORE dal canale locale (topic "account").
//
// Bug dell'utente: «il saldo non si aggiorna, né quando partono gli ordini, né
// quando vengono chiusi». Da oggi ogni processo che piazza ordini veri (runner
// calcio 47331, runner tennis 47332, Mike 47333, Omega 47334, Safe 47335)
// rilegge il saldo DOPO ogni ordine e ogni regolazione e lo pubblica sul
// PROPRIO canale col topic "account" (`Betfair/stream/saldo_evento.py`); il
// runner calcio lo pubblica anche a ogni giro di 20 s. La stessa lettura va
// anche sul database, quindi il canale non sostituisce la verità: la ANTICIPA.
// Regole (pure, testate):
//   * un messaggio è un SALDO solo se ha `available` numerico e `checked_at`
//     leggibile (i messaggi del P&L manuale viaggiano sullo stesso topic);
//   * fra due messaggi vince il `checked_at` più recente: uno vecchio o uguale
//     è IGNORATO (più canali, ordine d'arrivo non garantito);
//   * fra canale e database vince l'istante più recente (`checked_at` contro
//     `updated_at`): a canale muto resta esattamente il comportamento di prima.
// ============================================================================

export interface SaldoDalCanale {
    available: number;
    exposure: number | null;
    /** ISO dell'istante della lettura REST (UTC) */
    checkedAt: string;
    checkedMs: number;
}

/** Un messaggio del topic "account" → saldo, o null se non è un saldo. */
export function leggiSaldoDalCanale(d: unknown): SaldoDalCanale | null {
    const m = d as { available?: unknown; exposure?: unknown; checked_at?: unknown } | null;
    if (!m || typeof m !== 'object') return null;
    if (typeof m.available !== 'number' || !Number.isFinite(m.available)) return null;
    if (typeof m.checked_at !== 'string') return null;
    const ms = Date.parse(m.checked_at);
    if (!Number.isFinite(ms)) return null;
    const exp = typeof m.exposure === 'number' && Number.isFinite(m.exposure) ? m.exposure : null;
    return { available: m.available, exposure: exp, checkedAt: m.checked_at, checkedMs: ms };
}

/** Il più recente dei due; a parità o se `nuovo` è più vecchio resta `corrente`. */
export function saldoPiuRecente(corrente: SaldoDalCanale | null, nuovo: SaldoDalCanale | null): SaldoDalCanale | null {
    if (!nuovo) return corrente;
    if (!corrente) return nuovo;
    return nuovo.checkedMs > corrente.checkedMs ? nuovo : corrente;
}

export interface SaldoMostrato {
    available: number | null;
    exposure: number | null;
    /** istante del dato mostrato (ISO) — null se non c'è nessun dato */
    istante: string | null;
    fonte: 'canale' | 'database';
}

/** Cosa mostrare: vince l'istante più recente fra riga del database e canale. */
export function saldoDaMostrare(
    db: { available: number | null; exposure: number | null; updated_at: string } | null,
    canale: SaldoDalCanale | null,
): SaldoMostrato {
    const dbMs = db ? Date.parse(db.updated_at) : NaN;
    if (canale && (!db || !Number.isFinite(dbMs) || canale.checkedMs > dbMs)) {
        return { available: canale.available, exposure: canale.exposure, istante: canale.checkedAt, fonte: 'canale' };
    }
    return {
        available: db?.available ?? null,
        exposure: db?.exposure ?? null,
        istante: db?.updated_at ?? null,
        fonte: 'database',
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

// ============================================================================
// F2 revisore A (23/09) - l'istante del "non aggiornato da ...".
// Solo HH:MM se l'ultimo controllo e' di OGGI (giorno di Roma); altrimenti
// GG/MM HH:MM: un'ora di ieri non deve sembrare di oggi (o nel futuro).
// ============================================================================
const TZ_ROMA = 'Europe/Rome';

function giornoDiRoma(ms: number): string {
    return new Intl.DateTimeFormat('it-IT', {
        timeZone: TZ_ROMA, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(ms);
}

export function testoUltimaVerifica(iso: string | null | undefined, nowMs: number): string {
    const ms = typeof iso === 'string' ? Date.parse(iso) : NaN;
    if (!Number.isFinite(ms)) return DASH;
    const ora = fmtTime(ms);
    if (giornoDiRoma(ms) === giornoDiRoma(nowMs)) return ora;
    const giornoMese = new Intl.DateTimeFormat('it-IT', {
        timeZone: TZ_ROMA, day: '2-digit', month: '2-digit',
    }).format(ms);
    return `${giornoMese} ${ora}`;
}
