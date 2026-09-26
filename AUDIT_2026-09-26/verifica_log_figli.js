// verifica_log_figli.js - K2 (26/09): prova del log su file dei figli di desktop/main.js.
//
// Nessun banco di test esiste in desktop/: questo script estrae dal main.js VERO
// il blocco K2-LOG-FIGLI e la funzione spawnRunner (il codice di produzione, non
// una copia) e li esegue con node puro (niente electron). spawnRunner lancia un
// figlio vero (node al posto del python del venv) che scrive su stdout/stderr e
// muore con exit 1 + "traceback": il file _logs/<label>_<avvio>.log deve
// contenere tutto, con timestamp. Poi: potatura >7 giorni e cartella non
// scrivibile (l'avvio non si blocca).
//
// Uso:  node AUDIT_2026-09-26/verifica_log_figli.js [percorso/main.js]
// Esce 0 se tutto verde, 1 al primo controllo rosso.
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const mainPath = process.argv[2] || path.join(__dirname, '..', 'desktop', 'main.js');
const src = fs.readFileSync(mainPath, 'utf8');
const start = src.indexOf('// >>> K2-LOG-FIGLI');
const end = src.indexOf('\nfunction startRunners');
if (start < 0 || end < 0 || end < start) {
    console.error('ROSSO: blocco K2-LOG-FIGLI o spawnRunner non trovati in', mainPath);
    process.exit(1);
}
const code = src.slice(start, end);

let rossi = 0;
function check(cond, msg) {
    console.log(`${cond ? 'VERDE' : 'ROSSO'}: ${msg}`);
    if (!cond) rossi += 1;
}

function carica(root) {
    const children = [];
    const quiet = { log() {}, warn() {}, error() {} };
    // eslint-disable-next-line no-new-func
    const factory = new Function(
        'fs', 'path', 'spawn', 'console', 'PYTHON', 'repoRoot', 'children',
        'APP_BOOT_ID', 'LOCAL_CHANNEL_TOKEN',
        `${code}\nreturn { prepareChildLogs, childLogFileName, childLogLine, writeChildLog,
            spawnRunner, setDir: (d) => { childLogDir = d; }, streams: childLogStreams,
            STAMP: CHILD_LOG_STAMP };`,
    );
    return factory(fs, path, spawn, quiet, process.execPath, root, children, 'boot-test', 'tok');
}

async function main() {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'k2-log-'));

    // 1) prepareChildLogs crea _logs e pota i .log piu' vecchi di 7 giorni
    const m = carica(root);
    const dir0 = path.join(root, '_logs');
    fs.mkdirSync(dir0, { recursive: true });
    const vecchio = path.join(dir0, 'runner-calcio_vecchio.log');
    const recente = path.join(dir0, 'runner-calcio_recente.log');
    const altro = path.join(dir0, 'nota.txt');
    for (const f of [vecchio, recente, altro]) fs.writeFileSync(f, 'x');
    const ottoGiorni = (Date.now() - 8 * 24 * 3600 * 1000) / 1000;
    fs.utimesSync(vecchio, ottoGiorni, ottoGiorni);
    fs.utimesSync(altro, ottoGiorni, ottoGiorni);
    const dir = m.prepareChildLogs(root);
    check(dir === dir0, 'prepareChildLogs restituisce <repo>/_logs');
    check(!fs.existsSync(vecchio), 'il .log di 8 giorni e\' cancellato');
    check(fs.existsSync(recente), 'il .log recente resta');
    check(fs.existsSync(altro), 'un file non .log non si tocca');

    // 2) nome file per label e per avvio, riga con timestamp ISO
    check(m.childLogFileName('runner-tennis:err', 'S') === 'runner-tennis_err_S.log',
        'nome file ripulito dai caratteri non ammessi');
    const riga = m.childLogLine('runner-calcio:err', 'Traceback', new Date('2026-09-26T15:04:20.000Z'));
    check(riga === '2026-09-26T15:04:20.000Z [runner-calcio:err] Traceback\n', 'riga con prefisso timestamp');

    // 3) spawnRunner VERO: figlio che scrive stdout+stderr e muore con exit 1
    m.setDir(dir);
    const script = [
        "process.stdout.write('riga stdout 1\\nriga stdout 2\\n');",
        "process.stderr.write('Traceback (most recent call last):\\n  File x\\nConnectionError: boom\\n');",
        'setTimeout(() => process.exit(1), 50);',
    ].join('');
    const child = m.spawnRunner('runner-finto', ['-e', script]);
    await new Promise((resolve) => child.on('exit', () => setTimeout(resolve, 200)));
    const ws = m.streams.get('runner-finto');
    await new Promise((resolve) => (ws ? ws.end(resolve) : resolve()));
    const file = path.join(dir, m.childLogFileName('runner-finto', m.STAMP));
    const testo = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
    check(testo.includes('[runner-finto] riga stdout 2'), 'stdout del figlio nel file');
    check(testo.includes('[runner-finto:err] ConnectionError: boom'), 'stderr (traceback) del figlio nel file');
    check(testo.includes('terminato (exit 1)'), 'exit code del figlio nel file');
    check(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z \[/m.test(testo), 'ogni riga ha il timestamp ISO');

    // 4) cartella non scrivibile: nessuna eccezione, solo console
    const bloccato = path.join(root, 'file-non-cartella');
    fs.writeFileSync(bloccato, 'x');
    const m2 = carica(bloccato);
    let esito;
    let eccezione = null;
    try { esito = m2.prepareChildLogs(bloccato); } catch (e) { eccezione = e; }
    check(eccezione === null && esito === null, 'radice non scrivibile -> null, nessuna eccezione');
    let ecc2 = null;
    try { m2.writeChildLog('x', 'x', 'y'); } catch (e) { ecc2 = e; }
    check(ecc2 === null, 'writeChildLog senza cartella non solleva');

    try { fs.rmSync(root, { recursive: true, force: true }); } catch (_) { /* tmp */ }
    console.log(rossi === 0 ? 'ESITO: TUTTO VERDE' : `ESITO: ${rossi} ROSSI`);
    process.exit(rossi === 0 ? 0 : 1);
}

main().catch((e) => { console.error('ROSSO: eccezione', e); process.exit(1); });
