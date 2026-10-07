// FASE della partita (1o/2o tempo) dallo stato IPS grezzo.
//
// Gemello FEDELE di `Betfair/stream/scalper/atlante_v4.py::tempo_da_stato_ips`
// (fonte unica del bot: Safe, Mike e nota del modello). Se cambia la funzione
// Python, cambia anche questa: le due devono dare la stessa risposta sullo
// stesso `score_raw`.
//
// Misure del 25/09 sulle 60 registrazioni vere dei punteggi IPS Betfair:
//  - matchStatus nel 1T e' 'KickOff', all'intervallo 'FirstHalfEnd', nel 2T
//    'SecondHalfKickOff', a fine partita 'Finished';
//  - nel RECUPERO del 1T il minuto e' cumulato (46, 47, ... con
//    elapsedRegularTime 45 e elapsedAddedTime 1, 2, ...): senza lo stato un 46'
//    del recupero e' indistinguibile dal 46' della ripresa;
//  - all'intervallo il minuto riparte da 45 e continua a contare: ancora tempo 1;
//  - uno stato puo' restare VECCHIO ('KickOff' con minuto 88): un 1T "in gioco"
//    oltre MAX_MINUTO_1T non si crede.

/** 45 + 15 di recupero: oltre, uno stato "1T in gioco" e' vecchio. */
export const MAX_MINUTO_1T = 60;
const STATI_INTERVALLO = ['firsthalfend', 'halftime'];
const STATI_1T = ['firsthalf'];
const STATI_2T = ['secondhalf', 'extratime', 'penalt'];

/** Come `int(x)` di Python su numeri e stringhe intere; null se non convertibile. */
function intOrNull(v: unknown): number | null {
    if (typeof v === 'number') return Number.isFinite(v) ? Math.trunc(v) : null;
    if (typeof v === 'boolean') return v ? 1 : 0;
    if (typeof v === 'string' && /^\s*[+-]?\d+\s*$/.test(v)) return parseInt(v, 10);
    return null;
}

function isRecord(v: unknown): v is Record<string, unknown> {
    return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Lo stato IPS grezzo come lo legge il bot: `matchStatus`, poi `status`. */
export function statoIpsGrezzo(raw: unknown): string | null {
    if (!isRecord(raw)) return null;
    const s = raw.matchStatus || raw.status;
    return s ? String(s) : null;
}

/** 1 o 2 (tempo in corso) dallo stato IPS grezzo (`score_raw`) e dal minuto del
 *  feed; null se non si sa. PURA, mai eccezioni. */
export function tempoDaStatoIps(raw: unknown, minute: unknown): 1 | 2 | null {
    const m = intOrNull(minute);
    let st = '';
    if (isRecord(raw)) {
        st = String(raw.matchStatus || raw.status || '')
            .toLowerCase()
            .replace(/[^a-z]/g, '');
    }
    if (st) {
        if (STATI_2T.some((k) => st.includes(k))) return 2;
        if (STATI_INTERVALLO.some((k) => st.includes(k))) return 1;
        if (STATI_1T.some((k) => st.includes(k)) || st === 'kickoff') {
            if (m === null || m <= MAX_MINUTO_1T) return 1;
        }
    }
    if (isRecord(raw)) {
        const reg = intOrNull(raw.elapsedRegularTime);
        if (
            reg !== null &&
            raw.elapsedAddedTime !== null &&
            raw.elapsedAddedTime !== undefined &&
            (reg === 45 || reg === 90) &&
            (m === null || m <= reg + 30)
        ) {
            return reg === 45 ? 1 : 2;
        }
    }
    if (m === null) return null;
    if (m < 45) return 1;
    if (m >= 90) return 2;
    return null; // 45-89 senza stato: ambiguo
}
