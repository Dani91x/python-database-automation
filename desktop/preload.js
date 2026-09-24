// preload.js - la UI parla col runner via WebSocket locale
// (ws://127.0.0.1:47331/47332), nessuna API Node esposta al renderer.
// contextIsolation: true (vedi main.js).
//
// C1 (24/09): UNA sola cosa esce da qui verso la pagina, in sola lettura: il
// token di sessione dei canali locali, che main.js passa con
// additionalArguments ('--alphascore-canale-token=<hex>'). Senza token il
// canale del runner rifiuta i comandi 'order' e la UI usa la coda DB.
'use strict';

const { contextBridge } = require('electron');

const PREFISSO = '--alphascore-canale-token=';

function tokenDaArgv(argv) {
    const arg = (argv || []).find((a) => typeof a === 'string' && a.startsWith(PREFISSO));
    const t = arg ? arg.slice(PREFISSO.length) : '';
    return /^[0-9a-f]{64}$/.test(t) ? t : null;
}

const token = tokenDaArgv(process.argv);
if (token) {
    contextBridge.exposeInMainWorld('alphascoreCanale', Object.freeze({ token }));
}
