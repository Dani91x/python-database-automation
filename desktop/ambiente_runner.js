// ============================================================================
// ambiente_runner.js — L'AMBIENTE DEI RUNNER PYTHON, come funzione PURA (04/10).
//
// Prima `main.js` scriveva `TENNIS_LIVE_ORDER_MODE: process.env.TENNIS_LIVE_ORDER_MODE
// || 'PAPER'`: il `.env` dell'utente non arriva a `process.env` (Electron non lo
// carica; `readEnvFile` serviva solo al login) e `load_dotenv` del Python non
// sovrascrive una variabile gia' presente. Risultato: il runner tennis girava
// SEMPRE in PAPER, anche con l'installazione abilitata al live
// (`LIVE_ORDER_MODE=LIVE` nel `.env`), e ogni «soldi veri» sul tennis veniva
// rifiutato (incidente del 04/10, Safe tennis).
//
// REGOLA DEL TETTO TENNIS (capacita' del processo, NON il permesso di operare):
//   1. `TENNIS_LIVE_ORDER_MODE` se scritto esplicitamente (ambiente del processo,
//      poi `.env`: lo stesso ordine di precedenza di `load_dotenv`);
//   2. altrimenti lo stesso tetto del calcio: `LIVE_ORDER_MODE` = LIVE -> LIVE;
//   3. altrimenti PAPER (mai OFF di default: in prova i bot piazzano in prova).
// Con il tetto LIVE nessun ordine reale parte da solo: il runner tennis apre in
// soldi veri SOLO con «Ordini reali» = LIVE scelto in QUESTO avvio dell'app
// (`modo_ordini.modo_effettivo_tennis`, terza rete dentro flumine), e all'avvio
// dell'app la scelta torna a PAPER (`modo_ordini.dichiara_avvio`).
//
// Nessuna dipendenza da Electron: testabile con `node --test desktop/ambiente_runner.test.js`.
// ============================================================================
'use strict';

const MODI = ['OFF', 'PAPER', 'LIVE'];

/** 'live' / ' Paper ' -> 'LIVE' / 'PAPER'; vuoto o sconosciuto -> null. */
function normalizzaModo(v) {
    if (v == null) return null;
    const m = String(v).trim().toUpperCase();
    return MODI.includes(m) ? m : null;
}

/** Il primo valore SCRITTO (non vuoto) fra ambiente del processo e `.env`. */
function primoScritto(chiave, processEnv, envFile) {
    const p = processEnv && processEnv[chiave];
    if (p != null && String(p).trim() !== '') return p;
    const f = envFile && envFile[chiave];
    if (f != null && String(f).trim() !== '') return f;
    return null;
}

/** Il TETTO del runner tennis (vedi la regola in testa). */
function tettoTennis(processEnv, envFile) {
    const esplicito = primoScritto('TENNIS_LIVE_ORDER_MODE', processEnv, envFile);
    if (esplicito != null) {
        const m = normalizzaModo(esplicito);
        // scritto ma illeggibile: mai salire, la prova di sempre
        return m ?? 'PAPER';
    }
    const calcio = normalizzaModo(primoScritto('LIVE_ORDER_MODE', processEnv, envFile));
    return calcio === 'LIVE' ? 'LIVE' : 'PAPER';
}

/**
 * L'ambiente di un runner Python lanciato dall'app. PURA: niente file, niente
 * Electron. `envFile` = il `.env` del repo gia' letto (`readEnvFile`).
 */
function costruisciEnvRunner({ processEnv, envFile, bootId, token }) {
    return {
        ...processEnv,
        // IMPRONTA DELL'AVVIO: la leggono i servizi bot per capire se stanno
        // ripartendo dopo un crash (stesso id -> il bot acceso resta acceso) o
        // se l'app e' stata riaperta (id nuovo -> nessun bot opera).
        APP_BOOT_ID: bootId,
        // C1 (24/09): chiave dei comandi sui canali locali.
        LOCAL_CHANNEL_TOKEN: token,
        LIVE_ORDER_QUEUE_POLL_SEC: '0.15',
        LIVE_LADDER_PUBLISH_SEC: '0.3',
        TENNIS_LADDER_PUBLISH_SEC: '0.3',
        // AUDIT LATENZA 17/07: worker ordini tennis e risk engine a ~150 ms (il
        // drain locale e' separato dalla coda DB: nessuna query in piu').
        TENNIS_ORDER_POLL_SEC: '0.15',
        LIVE_RISK_ENGINE_POLL_SEC: '0.15',
        // desktop: i runner NON escono quando non ci sono eventi seguiti.
        LIVE_RUNNER_KEEP_ALIVE: '1',
        // 04/10: il TETTO del runner tennis dalla configurazione (regola in testa).
        TENNIS_LIVE_ORDER_MODE: tettoTennis(processEnv, envFile),
        // K2 (26/09): unbuffered e UTF-8, come legge il pipe di main.js.
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: (processEnv && processEnv.PYTHONIOENCODING) || 'utf-8',
    };
}

module.exports = { normalizzaModo, tettoTennis, costruisciEnvRunner };
