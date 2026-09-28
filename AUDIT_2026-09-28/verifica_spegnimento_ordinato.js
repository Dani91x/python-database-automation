// verifica_spegnimento_ordinato.js — CANTIERE K (28/09): prova dell'avviatore
// (desktop/main.js) senza Electron, sullo stesso principio di
// AUDIT_2026-09-26/verifica_log_figli.js: si estrae dal main.js VERO il
// blocco K2-LOG-FIGLI + K-SPEGNIMENTO-ORDINATO + spawnRunner/startRunners/
// killChildren (codice di PRODUZIONE, non una copia) e lo si esegue con node
// puro, con processi figli VERI (node al posto del python del venv) che
// simulano un servizio ben educato (guarda il file ARRESTO condiviso, esce
// da solo) e uno testardo (lo ignora, va forzato).
//
// Il meccanismo (SPEC_SPEGNIMENTO_ORDINATO.md, cantiere A, lato Python su
// master in Betfair/stream/arresto_ordinato.py): UN file condiviso, non uno
// per figlio. main.js lo scrive una volta sola alla chiusura; ogni figlio
// "consapevole" (ARRESTO_ORDINATO_LABELS) lo legge da solo ed esce con 0.
//
// Prova, in ordine:
//   1) arrestoCartella/arrestoPercorso: stessa risoluzione del modulo Python
//      (APP_ARRESTO_DIR, altrimenti <LIVE_STREAM_DATA_DIR o repo/_live_raw>/_arresto),
//      nome file ARRESTO;
//   2) cancellaArrestoAllAvvio: toglie un file di ieri, non solleva se assente;
//   3) ARRESTO_ORDINATO_LABELS / shutdownGraceMs: gli 8 figli consapevoli
//      (i due runner + i 6 servizi del cantiere K) e i loro tempi dichiarati;
//   4) spawnRunner: imposta SOLO _label (niente piu' file per figlio);
//   5) orderedShutdown(): UN file scritto una volta sola; un figlio
//      consapevole che lo vede ed esce da solo NON viene mai forzato; uno
//      che lo ignora viene forzato entro il tempo dichiarato (qui abbreviato
//      via una COPIA del sorgente, mai il file vero, solo per non aspettare
//      70s/25s in un test); un figlio NON consapevole (es. tennis-odds) non
//      viene atteso e finisce comunque forzato se ancora vivo;
//   6) waitForExit + killChildren presi singolarmente, timeout breve VERA.
//
// Uso:  node AUDIT_2026-09-28/verifica_spegnimento_ordinato.js [percorso/main.js]
// Esce 0 se tutto verde, 1 al primo controllo rosso. Nessun processo lasciato
// vivo: ogni figlio finto o e' uscito da solo o e' stato forzato prima della
// fine dello script (verificato).
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const mainPath = process.argv[2] || path.join(__dirname, '..', 'desktop', 'main.js');
const src = fs.readFileSync(mainPath, 'utf8');

let rossi = 0;
function check(cond, msg) {
    console.log(`${cond ? 'VERDE' : 'ROSSO'}: ${msg}`);
    if (!cond) rossi += 1;
}

// ---------------------------------------------------------------------------
// estrazione del blocco di produzione (K2-LOG-FIGLI ... 2° K-SPEGNIMENTO-ORDINATO)
// ---------------------------------------------------------------------------
const start = src.indexOf('// >>> K2-LOG-FIGLI');
const end = src.indexOf('\n// ------------------------------------------------------- SSO web Betfair');
if (start < 0 || end < 0 || end < start) {
    console.error('ROSSO: blocco K2-LOG-FIGLI/K-SPEGNIMENTO-ORDINATO non trovato in', mainPath);
    process.exit(1);
}
const code = src.slice(start, end);
const exportsExtra = `\nreturn { prepareChildLogs, childLogFileName, childLogLine, writeChildLog,
    spawnRunner, setDir: (d) => { childLogDir = d; }, streams: childLogStreams, STAMP: CHILD_LOG_STAMP,
    arrestoCartella, arrestoPercorso, cancellaArrestoAllAvvio,
    ARRESTO_ORDINATO_LABELS, shutdownGraceMs,
    waitForExit, orderedShutdown, killChildren, shutdownAndQuit,
    getChildren: () => children };`;

function carica(codiceSorgente, root, appStub) {
    const children = [];
    const quiet = { log() {}, warn() {}, error() {} };
    // eslint-disable-next-line no-new-func
    const factory = new Function(
        'fs', 'path', 'spawn', 'spawnSync', 'console', 'PYTHON', 'repoRoot', 'children',
        'APP_BOOT_ID', 'LOCAL_CHANNEL_TOKEN', 'app',
        `${codiceSorgente}${exportsExtra}`,
    );
    return factory(fs, path, spawn, spawnSync, quiet, process.execPath, root, children,
        'boot-test', 'tok', appStub);
}

async function main() {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'k-spegnimento-'));
    const savedEnv = { APP_ARRESTO_DIR: process.env.APP_ARRESTO_DIR, LIVE_STREAM_DATA_DIR: process.env.LIVE_STREAM_DATA_DIR };
    delete process.env.APP_ARRESTO_DIR;
    delete process.env.LIVE_STREAM_DATA_DIR;

    const m = carica(code, root, { exit() {} });
    const dir = m.prepareChildLogs(root);
    m.setDir(dir);

    // -----------------------------------------------------------------------
    // 1) risoluzione della cartella/percorso di ARRESTO (stessa di arresto_ordinato.py)
    // -----------------------------------------------------------------------
    check(m.arrestoCartella(root) === path.join(root, '_live_raw', '_arresto'),
        'arrestoCartella: default <repo>/_live_raw/_arresto (come config_stream.DATA_DIR)');
    check(m.arrestoPercorso(root) === path.join(root, '_live_raw', '_arresto', 'ARRESTO'),
        'arrestoPercorso: .../_arresto/ARRESTO');

    process.env.LIVE_STREAM_DATA_DIR = path.join(root, 'dati_custom');
    check(m.arrestoCartella(root) === path.join(root, 'dati_custom', '_arresto'),
        'arrestoCartella rispetta LIVE_STREAM_DATA_DIR');
    delete process.env.LIVE_STREAM_DATA_DIR;

    process.env.APP_ARRESTO_DIR = path.join(root, 'arresto_esplicito');
    check(m.arrestoCartella(root) === path.join(root, 'arresto_esplicito'),
        'arrestoCartella rispetta APP_ARRESTO_DIR (priorita massima, come cartella() in Python)');
    delete process.env.APP_ARRESTO_DIR;

    // -----------------------------------------------------------------------
    // 2) cancellaArrestoAllAvvio
    // -----------------------------------------------------------------------
    const arrestoFile = m.arrestoPercorso(root);
    fs.mkdirSync(path.dirname(arrestoFile), { recursive: true });
    fs.writeFileSync(arrestoFile, 'arresto di ieri');
    check(fs.existsSync(arrestoFile), 'file ARRESTO di "ieri" creato per il test');
    m.cancellaArrestoAllAvvio(root);
    check(!fs.existsSync(arrestoFile), 'cancellaArrestoAllAvvio lo toglie');
    let eccezioneCancella = null;
    try { m.cancellaArrestoAllAvvio(root); } catch (e) { eccezioneCancella = e; }
    check(eccezioneCancella === null, 'cancellaArrestoAllAvvio senza file non solleva');

    // -----------------------------------------------------------------------
    // 3) figli consapevoli e tempi dichiarati
    // -----------------------------------------------------------------------
    const attesi = ['runner-calcio', 'runner-tennis', 'omega-service', 'safe-strategy-service',
        'safe-strategy-bot', 'mike-service', 'tennis-bot-service', 'scalper-service'];
    for (const l of attesi) {
        check(m.ARRESTO_ORDINATO_LABELS.has(l), `${l} e' fra i consapevoli del file ARRESTO`);
    }
    check(!m.ARRESTO_ORDINATO_LABELS.has('tennis-odds'), 'tennis-odds (job breve) NON e\' consapevole');
    check(m.shutdownGraceMs('scalper-service') === 70_000,
        'shutdownGraceMs(scalper-service) = 70s (fino a 60s di attesa flat + margine)');
    check(m.shutdownGraceMs('runner-calcio') === 25_000, 'shutdownGraceMs(runner-calcio) = 25s (spec)');
    check(m.shutdownGraceMs('omega-service') === 25_000, 'shutdownGraceMs(omega-service) = 25s');

    // -----------------------------------------------------------------------
    // 4) spawnRunner: SOLO _label (niente piu' file per figlio)
    // -----------------------------------------------------------------------
    const childDiretto = m.spawnRunner('runner-finto-diretto', ['-e', 'process.exit(0);']);
    check(childDiretto._label === 'runner-finto-diretto', '_label valorizzato');
    check(!('_stopFile' in childDiretto) || childDiretto._stopFile === undefined,
        'nessun _stopFile per-figlio (superato: un unico file condiviso)');
    await new Promise((resolve) => childDiretto.on('exit', resolve));

    // -----------------------------------------------------------------------
    // 5a) orderedShutdown(): il figlio "bene" (consapevole, label vera) vede
    //     il file ARRESTO ed esce da solo — mai un taskkill.
    // -----------------------------------------------------------------------
    const scriptBene = [
        "const fs = require('fs');",
        `const p = ${JSON.stringify(arrestoFile)};`,
        "const t = setInterval(() => { if (fs.existsSync(p)) { clearInterval(t); process.exit(0); } }, 50);",
    ].join('');
    // riusa una label VERA e consapevole cosi' orderedShutdown() la aspetta davvero.
    const childBene = m.spawnRunner('omega-service', ['-e', scriptBene]);
    const t0 = Date.now();
    await m.orderedShutdown();
    const durataMs = Date.now() - t0;
    check(fs.existsSync(arrestoFile), 'orderedShutdown ha scritto il file ARRESTO condiviso');
    check(childBene.exitCode === 0, 'il figlio "bene" (omega-service) e\' uscito (exit 0) dopo aver visto ARRESTO');
    check(durataMs < 5_000, `orderedShutdown ha aspettato ${durataMs}ms, molto meno dei 25s di grace (uscita spontanea)`);
    check(m.getChildren().length === 0, 'children vuoto dopo orderedShutdown (nessun residuo)');

    // -----------------------------------------------------------------------
    // 5b) orderedShutdown() con grace ABBREVIATA (solo per il test, via una
    //     COPIA del sorgente: mai il file vero) su un figlio CONSAPEVOLE ma
    //     TESTARDO che ignora il file — deve essere forzato.
    // -----------------------------------------------------------------------
    // CRLF-safe: main.js su disco ha fine riga CRLF (git core.autocrlf).
    const reGrace = /function shutdownGraceMs\(label\) \{\r?\n\s*if \(label === 'scalper-service'\) return 70_000;\r?\n\s*return 25_000;\r?\n\}/;
    check(reGrace.test(code), 'il testo atteso di shutdownGraceMs esiste nel sorgente vero');
    const codiceBreve = code.replace(
        reGrace,
        "function shutdownGraceMs(label) {\n    if (label === 'scalper-service') return 400;\n    return 300;\n}",
    );
    check(codiceBreve !== code, 'sostituzione della grace riuscita');
    const root2 = fs.mkdtempSync(path.join(os.tmpdir(), 'k-spegnimento-breve-'));
    delete process.env.APP_ARRESTO_DIR;
    delete process.env.LIVE_STREAM_DATA_DIR;
    const m2 = carica(codiceBreve, root2, { exit() {} });
    m2.setDir(m2.prepareChildLogs(root2));
    const scriptTestardo = [
        "setInterval(() => {}, 1000);", // vivo per sempre, ignora il file ARRESTO
        "setTimeout(() => process.exit(1), 20000);", // rete di sicurezza SOLO se il test fallisse a forzarlo
    ].join('');
    const childTestardo = m2.spawnRunner('mike-service', ['-e', scriptTestardo]);
    const t1 = Date.now();
    await m2.orderedShutdown();
    const durata2 = Date.now() - t1;
    // idem sopra: taskkill e' sincrono, l'evento 'exit' di Node no.
    await new Promise((r) => setTimeout(r, 300));
    check(childTestardo.exitCode !== null, 'il figlio "testardo" (mike-service) NON e\' piu\' vivo dopo orderedShutdown (forzato)');
    check(durata2 < 5_000, `orderedShutdown (grace abbreviata) ha impiegato ${durata2}ms: forzato entro il tempo dichiarato, non appeso`);
    check(m2.getChildren().length === 0, 'children vuoto anche nel caso forzato');

    // -----------------------------------------------------------------------
    // 5c) un figlio NON consapevole (label fuori da ARRESTO_ORDINATO_LABELS,
    //     come tennis-odds) non viene atteso ma finisce comunque forzato.
    // -----------------------------------------------------------------------
    const root3b = fs.mkdtempSync(path.join(os.tmpdir(), 'k-spegnimento-nonconsapevole-'));
    const m3b = carica(codiceBreve, root3b, { exit() {} });
    m3b.setDir(m3b.prepareChildLogs(root3b));
    const childIgnaro = m3b.spawnRunner('tennis-odds', ['-e', "setInterval(() => {}, 1000);"]);
    const t2 = Date.now();
    await m3b.orderedShutdown();
    const durata3 = Date.now() - t2;
    // taskkill (spawnSync, sincrono) e' gia' tornato dentro orderedShutdown():
    // l'evento 'exit' di Node sul figlio puo' arrivare con un filo di ritardo.
    await new Promise((r) => setTimeout(r, 300));
    check(childIgnaro.exitCode !== null, 'tennis-odds (non consapevole) viene comunque forzato, non lasciato vivo');
    check(durata3 < 2_000, `tennis-odds non e' stato ATTESO (${durata3}ms): forzato subito, non fino al grace`);

    // -----------------------------------------------------------------------
    // 6) waitForExit + killChildren presi singolarmente, timeout breve VERA
    // -----------------------------------------------------------------------
    const root3 = fs.mkdtempSync(path.join(os.tmpdir(), 'k-spegnimento-isolato-'));
    const m3 = carica(code, root3, { exit() {} });
    const childIsolato = m3.spawnRunner('runner-finto-isolato', ['-e', "setInterval(() => {}, 1000);"]);
    const esitoAtteso = await m3.waitForExit(childIsolato, 250);
    check(esitoAtteso === false, 'waitForExit ritorna false (non uscito) entro un timeout breve su un figlio vivo');
    check(childIsolato.exitCode === null, 'waitForExit NON uccide nessuno: il figlio e\' ancora vivo dopo il timeout');
    m3.killChildren();
    await new Promise((r) => setTimeout(r, 300));
    check(childIsolato.exitCode !== null, 'killChildren forza davvero (taskkill /T /F): il figlio e\' morto');
    check(m3.getChildren().length === 0, 'killChildren svuota children');

    for (const [k, v] of Object.entries(savedEnv)) {
        if (v === undefined) delete process.env[k]; else process.env[k] = v;
    }
    for (const r of [root, root2, root3, root3b]) {
        try { fs.rmSync(r, { recursive: true, force: true }); } catch (_) { /* tmp */ }
    }
    console.log(rossi === 0 ? 'ESITO: TUTTO VERDE' : `ESITO: ${rossi} ROSSI`);
    process.exit(rossi === 0 ? 0 : 1);
}

main().catch((e) => { console.error('ROSSO: eccezione', e); process.exit(1); });
