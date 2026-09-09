// ============================================================================
// bootstrap.js — ENTRY dell'exe: carica SEMPRE il main.js VIVO del repo.
//
// REGOLA (09/09, richiesta esplicita): l'app desktop deve avere SEMPRE l'ultimo
// codice a ogni avvio. I processi python girano dal sorgente e la UI viene
// ricostruita all'avvio (ensureFreshUi in main.js), ma il main.js stesso era
// impacchettato dentro l'exe al momento del build: l'exe del 17/07 non
// conteneva l'avvio dello scanner Safe Strategy (02/09), l'SSO video né la
// gestione delle finestre Betfair — "Scanner non attivo" con heartbeat di una
// settimana prima. Da qui in poi l'exe è solo questo avviatore: risolve la
// radice del repo e fa require() del desktop/main.js del repo, quindi ogni
// modifica a main.js è attiva al riavvio successivo SENZA ricompilare l'exe.
// Se il repo non si trova, ripiega sul main.js impacchettato (comportamento
// precedente) e lo dice nel log.
// ============================================================================
'use strict';

const path = require('path');
const fs = require('fs');
const { app } = require('electron');

function isRepoRoot(dir) {
    try {
        return fs.existsSync(path.join(dir, '.venv', 'Scripts', 'python.exe'))
            && fs.existsSync(path.join(dir, 'desktop', 'main.js'));
    } catch (_) { return false; }
}

// stessa strategia di main.js (env → cartella exe → radice → dev)
function resolveRepoRoot() {
    const exeDir = process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(app.getPath('exe'));
    const candidates = [
        process.env.ALPHASCORE_REPO,
        path.resolve(exeDir, '..', '..'),
        path.resolve(exeDir, '..'),
        exeDir,
        path.resolve(__dirname, '..'),
    ].filter(Boolean);
    for (const c of candidates) {
        if (isRepoRoot(c)) return c;
    }
    return null;
}

const repoRoot = resolveRepoRoot();
const liveMain = repoRoot ? path.join(repoRoot, 'desktop', 'main.js') : null;
const bundledMain = path.join(__dirname, 'main.js');

if (liveMain && fs.existsSync(liveMain) && path.resolve(liveMain) !== path.resolve(bundledMain)) {
    console.log(`[bootstrap] main.js VIVO dal repo: ${liveMain}`);
    process.env.ALPHASCORE_REPO = repoRoot;
    require(liveMain);
} else {
    console.warn('[bootstrap] repo non trovato: uso il main.js impacchettato nell\'exe (potrebbe essere vecchio).');
    require(bundledMain);
}
