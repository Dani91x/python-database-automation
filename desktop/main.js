// ============================================================================
// main.js — app desktop "AlphaScore Trading" (Electron).
//
// All'avvio:
//   (a) mini server HTTP statico su 127.0.0.1:47330 che serve ../frontend/dist
//       (fallback a index.html per le rotte SPA / history API);
//   (b) spawn dei runner via watchdog (calcio + tennis) con cwd = RADICE repo e
//       il python del .venv del progetto. Nessun doppio avvio: il lock porta dei
//       runner protegge già, e il watchdog esce da solo se già attivo;
//   (c) BrowserWindow 1600x900 → http://127.0.0.1:47330/board.
// Alla chiusura (28/09, K-SPEGNIMENTO-ORDINATO): file ARRESTO condiviso, poi
// fino al tempo massimo dichiarato per figlio (shutdownGraceMs), poi
// taskkill /T /F (tree-kill) su chi resta vivo — MAI processi orfani.
// ============================================================================
'use strict';

const { app, BrowserWindow, dialog, session, shell } = require('electron');
const http = require('http');
const https = require('https');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');
const crypto = require('crypto');
// 04/10: l'ambiente dei runner Python (tetto del tennis compreso), funzione pura
const { costruisciEnvRunner } = require('./ambiente_runner');

const UI_PORT = 47330;

// ---------------------------------------------------------------------------
// APP_BOOT_ID — L'IMPRONTA DI QUESTO AVVIO DELL'APP (FASE A, 16/09).
//
// «I bot li accendo solo io, in paper e in live. All'avvio dell'app nessun bot
// opera.» Ogni servizio rilegge la propria riga di controllo dal database: se
// ieri era rimasto 'running', oggi riparte da solo — anche in LIVE.
//
// Questo id nasce UNA volta per avvio dell'app e viaggia nell'ambiente di tutti
// i processi lanciati da qui. Il watchdog lancia il figlio SENZA passare `env`
// (`Betfair/stream/watchdog.py`: `popen(cmd, cwd=...)`), quindi il figlio
// eredita questo stesso ambiente: un riavvio dopo un crash porta lo STESSO id e
// NON spegne un bot che l'utente aveva acceso. Un avvio nuovo dell'app porta un
// id nuovo, e i servizi si fermano da soli (vedi Betfair/stream/avvio_app.py).
//
// Si genera qui e non nei servizi perche' qui c'e' UN processo solo: e' l'unico
// punto in cui «l'app si e' avviata» succede una volta sola.
// ---------------------------------------------------------------------------
const APP_BOOT_ID = `${Date.now().toString(36)}-${crypto.randomUUID()}`;

// ---------------------------------------------------------------------------
// C1 (24/09) - TOKEN DI SESSIONE DEI CANALI LOCALI.
// I canali 47331 (calcio) e 47332 (tennis) ESEGUONO ORDINI VERI. Un WebSocket
// del browser non e' soggetto a CORS: senza una chiave, qualunque pagina web
// aperta su questa macchina poteva mandare {"m":"order"}. Il token nasce qui,
// UNA volta per avvio (come APP_BOOT_ID), e va solo a due destinatari:
//   - i runner, nell'ambiente (LOCAL_CHANNEL_TOKEN): il watchdog lo eredita,
//     quindi un riavvio dopo un crash porta lo STESSO token;
//   - la pagina dell'app, dal preload (additionalArguments -> contextBridge).
// Il canale accetta un comando 'order' solo da una connessione che si e'
// presentata con questo token (e da un'origine dell'app): vedi
// Betfair/stream/local_channel.py. Il token non si scrive mai nei log.
// ---------------------------------------------------------------------------
const LOCAL_CHANNEL_TOKEN = crypto.randomBytes(32).toString('hex');
const ARG_TOKEN_CANALE = '--alphascore-canale-token=';

// webPreferences della UI: le stesse per la finestra principale e per le
// finestre della UI aperte da window.open (ladder popout), che altrimenti
// resterebbero senza token e manderebbero gli ordini sulla coda DB.
function uiWebPreferences() {
    return {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
        additionalArguments: [`${ARG_TOKEN_CANALE}${LOCAL_CHANNEL_TOKEN}`],
    };
}

// ---------------------------------------------------------------------------
// RADICE REPO — fix avvio da exe PACCHETTIZZATO: __dirname punta dentro app.asar
// (portable: scompattato in %TEMP%), quindi i path relativi si rompono. Si prova,
// in ordine: env esplicita → cartella dell'exe (desktop/release → repo) → exe
// copiato nella radice → dev (npm start). Valida = contiene .venv e frontend/dist.
// ---------------------------------------------------------------------------
function isRepoRoot(dir) {
    try {
        return fs.existsSync(path.join(dir, '.venv', 'Scripts', 'python.exe'))
            && fs.existsSync(path.join(dir, 'frontend', 'dist', 'index.html'));
    } catch (_) { return false; }
}

function resolveRepoRoot() {
    const exeDir = process.env.PORTABLE_EXECUTABLE_DIR
        || path.dirname(app.getPath('exe'));
    const candidates = [
        process.env.ALPHASCORE_REPO,                 // override esplicito
        path.resolve(exeDir, '..', '..'),            // desktop/release/*.exe → repo
        path.resolve(exeDir, '..'),                  // desktop/*.exe → repo
        exeDir,                                      // exe copiato nella radice repo
        path.resolve(__dirname, '..'),               // dev: npm start da desktop/
    ].filter(Boolean);
    for (const c of candidates) {
        if (isRepoRoot(c)) return c;
    }
    return null;
}

let repoRoot = null; // risolta in app.whenReady (serve app.getPath)
let DIST_DIR = null;
let PYTHON = null;

// figli (watchdog calcio + watchdog tennis) da terminare SEMPRE alla chiusura.
const children = [];

// ---------------------------------------------------------------- static server
const MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.ico': 'image/x-icon',
    '.webp': 'image/webp',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.map': 'application/json',
    '.txt': 'text/plain; charset=utf-8',
};

// ------------------------------------------------- UI SEMPRE ULTIMA VERSIONE
// REGOLA (17/07, richiesta esplicita): l'exe deve servire SEMPRE l'ultima
// versione del codice. I processi python girano dal sorgente (sempre freschi);
// la UI invece è una build statica (frontend/dist) che restava stantia — i
// pulsanti nuovi "non esistevano" finché qualcuno non rifaceva `npm run build`
// a mano. Qui, a ogni avvio: se un sorgente in frontend/ è più nuovo della
// build → rebuild automatico PRIMA di servire. Build fallita → si serve la
// build precedente (mai bloccare l'app) con un avviso esplicito.
function newestMtimeUnder(dir) {
    let newest = 0;
    const stack = [dir];
    while (stack.length) {
        const d = stack.pop();
        let entries;
        try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch (_) { continue; }
        for (const e of entries) {
            if (e.name === 'node_modules' || e.name === 'dist') continue;
            const p = path.join(d, e.name);
            if (e.isDirectory()) { stack.push(p); continue; }
            try {
                const m = fs.statSync(p).mtimeMs;
                if (m > newest) newest = m;
            } catch (_) { /* file sparito: ignora */ }
        }
    }
    return newest;
}

function ensureFreshUi() {
    const feDir = path.join(repoRoot, 'frontend');
    let distM = 0;
    try { distM = fs.statSync(path.join(feDir, 'dist', 'index.html')).mtimeMs; } catch (_) {}
    const srcM = Math.max(
        newestMtimeUnder(path.join(feDir, 'src')),
        newestMtimeUnder(path.join(feDir, 'public')),
        ...['index.html', 'vite.config.ts', 'package.json', 'tailwind.config.js']
            .map((f) => { try { return fs.statSync(path.join(feDir, f)).mtimeMs; } catch (_) { return 0; } }),
    );
    if (distM > 0 && distM >= srcM) {
        console.log('[desktop] UI già aggiornata (build più recente dei sorgenti).');
        return;
    }
    console.log('[desktop] UI stantia: ricostruisco frontend/dist (npm run build)...');
    const r = spawnSync('npm', ['run', 'build'], {
        cwd: feDir, shell: true, windowsHide: true,
        stdio: 'pipe', encoding: 'utf8', timeout: 10 * 60 * 1000,
    });
    if (r.status === 0) {
        console.log('[desktop] build UI completata: si serve la versione aggiornata.');
    } else {
        dialog.showErrorBox(
            'AlphaScore — build UI fallita',
            'La ricostruzione automatica della UI è fallita: verrà servita la '
            + 'versione PRECEDENTE (potrebbero mancare le funzioni più nuove).\n\n'
            + 'Dettaglio:\n' + String(r.stderr || r.stdout || r.error || '').slice(-1200),
        );
    }
}

function startStaticServer() {
    return new Promise((resolve, reject) => {
        const server = http.createServer((req, res) => {
            try {
                // solo il path, senza query; niente traversal fuori da dist.
                const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);
                let filePath = path.normalize(path.join(DIST_DIR, urlPath));
                if (!filePath.startsWith(DIST_DIR)) {
                    res.writeHead(403); res.end('forbidden'); return;
                }
                if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
                    // history API fallback: ogni rotta SPA → index.html
                    filePath = path.join(DIST_DIR, 'index.html');
                }
                const ext = path.extname(filePath).toLowerCase();
                res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
                fs.createReadStream(filePath).pipe(res);
            } catch (err) {
                res.writeHead(500);
                res.end('errore interno');
            }
        });
        server.on('error', reject);
        // SOLO loopback: la UI non deve essere raggiungibile dalla rete.
        server.listen(UI_PORT, '127.0.0.1', () => {
            console.log(`[desktop] UI su http://127.0.0.1:${UI_PORT} (dist: ${DIST_DIR})`);
            resolve(server);
        });
    });
}

// >>> K2-LOG-FIGLI (26/09) ---------------------------------------------------
// La console dei figli (stdout/stderr dei servizi python) non finiva in nessun
// file: crash dei runner senza traceback (calcio 10:00Z e 14:46Z, tennis
// 15:04Z del 26/09). Ora ogni riga va ANCHE in <repo>/_logs/<label>_<avvio>.log
// (un file per figlio e per avvio dell'app, append con timestamp ISO). All'avvio
// si cancellano i .log piu' vecchi di 7 giorni. Mai bloccare l'avvio: cartella
// o file non scrivibili = solo console, con un avviso.
const CHILD_LOG_RETENTION_MS = 7 * 24 * 3600 * 1000;
const CHILD_LOG_STAMP = new Date().toISOString().replace(/[:.]/g, '-');
let childLogDir = null;               // null = log su file spento (solo console)
const childLogStreams = new Map();    // label -> WriteStream | null

// >>> K-SPEGNIMENTO-ORDINATO (28/09) -----------------------------------------
// Prima del 28/09 la chiusura era SEMPRE `taskkill /T /F` (TerminateProcess):
// nessun `finally` Python girava — ad app spenta restavano righe `live_follow`
// STREAMING e posizioni paper `open` mai regolate (verificato il 28/09: 29
// `live_follow` + 4 `tennis_live_follow`). SPEC_SPEGNIMENTO_ORDINATO.md
// (cantiere A, lato Python GIA' pronto su master): UN file, ``ARRESTO``, che
// ogni processo legge da SOLO (nessun segnale: su Windows un python senza
// console non riceve CTRL_C/CTRL_BREAK in modo affidabile, e fra main.js e i
// runner c'e' il watchdog in mezzo). Stessa cartella/nome del modulo Python
// ``Betfair/stream/arresto_ordinato.py`` (``cartella()``/``percorso()``):
// env APP_ARRESTO_DIR se valorizzata, altrimenti <DATA_DIR>/_arresto, dove
// DATA_DIR = LIVE_STREAM_DATA_DIR o <repo>/_live_raw (``config_stream.py``).
//
// CANTIERE K (28/09): oltre ai due runner (gia' del cantiere A), lo stesso
// controllo e' stato aggiunto (righe minime nel solo ciclo esterno, MAI nella
// logica) anche ai servizi bot: omega-service, safe-strategy-service,
// safe-strategy-bot, mike-service, tennis-bot-service (ponte), scalper-
// service (qui SOLO in OR col suo kill-switch STOP_SCALPER esistente: "il
// kill-switch non va mai scavalcato"). ``tennis-odds`` (job breve, periodico)
// NON lo controlla: resta chiuso dal taskkill come sempre, non serve altro.
function arrestoCartella(root) {
    const espl = (process.env.APP_ARRESTO_DIR || '').trim();
    if (espl) return espl;
    const dataDir = (process.env.LIVE_STREAM_DATA_DIR || '').trim() || path.join(root, '_live_raw');
    return path.join(dataDir, '_arresto');
}

function arrestoPercorso(root) {
    return path.join(arrestoCartella(root), 'ARRESTO');
}

// all'avvio (PRIMA di spawnRunner): un file rimasto da uno spegnimento
// precedente non deve fermare l'app appena riaperta.
function cancellaArrestoAllAvvio(root) {
    try { fs.unlinkSync(arrestoPercorso(root)); } catch (_) { /* assente: ok */ }
}

// tempo massimo dichiarato di attesa PRIMA di forzare (taskkill), SOLO per i
// figli che leggono il file (elenco sotto): lo scalper aspetta (vedi sotto) la
// chiusura flat delle sue sessioni (scalper_service.py, kill-switch) + un
// margine; i due runner 25s per la specifica del cantiere A (ramo peggiore
// 15s di attesa "nessun mercato" + chiusura follow + flush + logout Betfair);
// gli altri servizi rispondono in pochi secondi al loro giro (2-20s): stesso
// tetto dei runner come margine di sicurezza uniforme. Chi non e' in elenco
// (es. tennis-odds) non viene atteso: resta il solo taskkill di sempre.
const ARRESTO_ORDINATO_LABELS = new Set([
    'runner-calcio', 'runner-tennis',
    'omega-service', 'safe-strategy-service', 'safe-strategy-bot', 'mike-service',
    'tennis-bot-service', 'scalper-service',
]);

// 02/10 (R2): lo scalper ora aspetta le sue sessioni fino a
// scalper_service.tempo_supervisore_arresto_s() (132 s: battito + flat di 3
// strategie + annullo degli ordini + segnale): qui quel tempo + margine.
// Il test test_scalper_arresto_ordinato_2026_10_02.py confronta i due numeri.
// 02/10 (R1): Safe (safe-strategy-bot) e Omega all'arresto annullano i loro ordini
// vivi (tetto 10 s) dopo il giro in corso: arresto_bot.TEMPO_MASSIMO_ARRESTO_S (35 s)
// + margine. Il test test_arresto_bot_safe_omega_2026_10_02.py confronta i numeri.
function shutdownGraceMs(label) {
    if (label === 'scalper-service') return 150_000;
    if (label === 'omega-service' || label === 'safe-strategy-bot') return 45_000;
    return 25_000;
}
// <<< K-SPEGNIMENTO-ORDINATO --------------------------------------------------

function childLogFileName(label, stamp) {
    return `${String(label).replace(/[^A-Za-z0-9_.-]/g, '_')}_${stamp}.log`;
}

function childLogLine(tag, line, now) {
    return `${(now || new Date()).toISOString()} [${tag}] ${line}\n`;
}

function prepareChildLogs(root, nowMs) {
    const now = nowMs || Date.now();
    try {
        const dir = path.join(root, '_logs');
        fs.mkdirSync(dir, { recursive: true });
        for (const name of fs.readdirSync(dir)) {
            if (!name.endsWith('.log')) continue;
            const p = path.join(dir, name);
            try {
                if (now - fs.statSync(p).mtimeMs > CHILD_LOG_RETENTION_MS) fs.unlinkSync(p);
            } catch (_) { /* file in uso o sparito: resta */ }
        }
        return dir;
    } catch (err) {
        console.error(`[desktop] cartella _logs non disponibile (${err && err.message}): log dei figli solo su console`);
        return null;
    }
}

function childLogStream(label) {
    if (!childLogDir) return null;
    if (childLogStreams.has(label)) return childLogStreams.get(label);
    let ws = null;
    try {
        ws = fs.createWriteStream(path.join(childLogDir, childLogFileName(label, CHILD_LOG_STAMP)),
            { flags: 'a', encoding: 'utf8' });
        ws.on('error', (err) => {
            console.error(`[desktop] log su file di ${label} spento (${err && err.message}): resta la console`);
            childLogStreams.set(label, null);
        });
    } catch (err) {
        console.error(`[desktop] log su file di ${label} non aperto (${err && err.message}): resta la console`);
        ws = null;
    }
    childLogStreams.set(label, ws);
    return ws;
}

function writeChildLog(label, tag, line) {
    const ws = childLogStream(label);
    if (!ws) return;
    try { ws.write(childLogLine(tag, line)); } catch (_) { /* mai fermare il pipe */ }
}
// <<< K2-LOG-FIGLI -------------------------------------------------------------

// ---------------------------------------------------------------- runner python
function spawnRunner(label, args) {
    if (!fs.existsSync(PYTHON)) {
        console.error(`[desktop] python del venv non trovato: ${PYTHON} — runner ${label} NON avviato`);
        return;
    }
    // env passthrough + velocità canale locale (poll coda 0.15s, publish ladder 0.3s).
    // 04/10: costruito dalla funzione PURA `costruisciEnvRunner` (ambiente_runner.js,
    // test di contratto `node --test desktop/ambiente_runner.test.js`). Il TETTO del runner tennis viene
    // dalla configurazione (`TENNIS_LIVE_ORDER_MODE` scritto, altrimenti il tetto del
    // calcio `LIVE_ORDER_MODE`, altrimenti PAPER): prima era FORZATO a PAPER e il
    // tennis non poteva mai servire i soldi veri. Il tetto e' la CAPACITA': gli
    // ordini reali partono solo con «Ordini reali» = LIVE scelto in questo avvio.
    const env = costruisciEnvRunner({
        processEnv: process.env,
        envFile: readEnvFile(path.join(repoRoot, '.env')),
        bootId: APP_BOOT_ID,
        token: LOCAL_CHANNEL_TOKEN,
    });
    if (label === 'runner-tennis') {
        console.log(`[desktop] tetto ordini del runner tennis: ${env.TENNIS_LIVE_ORDER_MODE}`);
    }
    const child = spawn(PYTHON, args, {
        cwd: repoRoot,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
    });
    children.push(child);
    // K-SPEGNIMENTO-ORDINATO: orderedShutdown() legge questa proprieta' per
    // sapere CHI e', per loggare e per decidere quanto aspettarlo (vedi sopra).
    child._label = label;
    console.log(`[desktop] ${label} avviato (pid ${child.pid}): ${PYTHON} ${args.join(' ')}`);
    writeChildLog(label, 'desktop', `avviato (pid ${child.pid}): ${args.join(' ')}`);
    // log dei figli su console (prefissati per capire chi parla) E su file
    // (K2, 26/09: i crash dei runner restavano senza traceback).
    const pipe = (stream, tag) => {
        stream.setEncoding('utf8');
        stream.on('data', (chunk) => {
            for (const line of String(chunk).split(/\r?\n/)) {
                if (line.trim()) {
                    console.log(`[${label}${tag}] ${line}`);
                    writeChildLog(label, `${label}${tag}`, line);
                }
            }
        });
    };
    pipe(child.stdout, '');
    pipe(child.stderr, ':err');
    child.on('exit', (code) => {
        // uscita immediata = probabilmente watchdog già attivo altrove (lock porta): ok.
        console.log(`[desktop] ${label} terminato (exit ${code})`);
        writeChildLog(label, 'desktop', `terminato (exit ${code})`);
        // niente riferimenti morti: il registro dei figli resta = processi VIVI
        // (prima cresceva di 1 a ogni job tennis-odds, 48/giorno)
        const i = children.indexOf(child);
        if (i >= 0) children.splice(i, 1);
    });
    return child;
}

function startRunners() {
    // l'impronta di questo avvio finisce nei log: senza, un bot fermato
    // all'avvio non sarebbe riconducibile a nessun evento visibile.
    console.log(`[desktop] APP_BOOT_ID di questo avvio: ${APP_BOOT_ID}`);
    // niente doppio avvio: il lock porta dei runner protegge già; il watchdog esce
    // da solo se un'altra istanza è attiva.
    spawnRunner('runner-calcio', ['-m', 'Betfair.stream.watchdog']);
    spawnRunner('runner-tennis', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.stream.tennis_live.tennis_runner']);
    // SERVIZI BOT: senza di loro i bot non si armano. NON avviare anche i .bat
    // a mano: l'app avvia già tutto.
    // CANTIERE K (28/09, SPEC_WATCHDOG_SCALPER_PONTE_2026-09-26.md): prima non
    // aveva watchdog — se moriva, niente auto-mode/supervisione delle sessioni
    // e nessun avviso; le sessioni già vive restavano sole. Ora sotto watchdog
    // come tutti gli altri: crash → alert CRITICAL + riavvio con backoff.
    spawnRunner('scalper-service', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.stream.scalper.scalper_service']);
    // PONTE bot→follow tennis in sola modalità ponte (audit 09/09): l'hosting dei
    // bot lo fa il runner tennis sotto watchdog (sopra). Senza --bridge-only i
    // due processi si contendevano il lock 47312 e, a seconda di chi vinceva, il
    // tennis restava senza sentinella o il ponte girava a vuoto. Le "Partite del
    // Giorno" tennis (tennis_markets) le popola il job betfair_tennis_odds sotto.
    // CANTIERE K (28/09): idem sopra — prima senza watchdog, se moriva lo
    // «ferma» della UI non diventava più `stopping` e il battito invecchiava.
    // `--bridge-only` arriva al ponte perché il watchdog passa TUTTO cio' che
    // segue il modulo (`Betfair.stream.watchdog._parse_argv`).
    spawnRunner('tennis-bot-service', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.stream.tennis_live.tennis_bot_service', '--bridge-only']);
    // SAFE STRATEGY: scanner AUTONOMO degli eventi in-play (calcio+tennis).
    // REST leggero a cadenze adattive, scrive i fatti su safe_strategy_scan;
    // single-instance lock su 127.0.0.1:47315. Nessun ordine, mai.
    // sotto WATCHDOG (audit 09/09): è il FEED UNICO di quote/punteggi per tutti
    // gli altri processi — se cade va rilanciato (crash → backoff), come i runner.
    spawnRunner('safe-strategy-service', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.safe_strategy.service']);
    // OMEGA (Correct Score LAY): servizio leggero e ISOLATO. A riposo fa solo il
    // keep-alive di sessione (1 chiamata ogni 10 min); agisce quando lo attivi/usi
    // da /omega, e di default in PAPER. Single-instance lock su 127.0.0.1:47313 → niente doppio
    // avvio se lanci anche avvia_omega_service.bat. Nessun impatto sugli altri runner.
    // sotto WATCHDOG (09/09 sera): come scanner e runner, se cade riparte.
    // Lock occupato (altra istanza) → esce 0 → il watchdog si ferma (corretto).
    spawnRunner('omega-service', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.omega.omega_service']);
    // SAFE STRATEGY BOT (10/09): esecuzione AUTOMATICA dei segnali Safe (paper di
    // default, live solo su scelta esplicita da /safe-strategy), resoconto trade in
    // tempo reale, cash out, opportunità modello. Legge SOLO il feed unico dello
    // scanner (nessuna chiamata Betfair duplicata). A riposo (bot fermo) processa
    // solo le richieste manuali e i settlement. Lock single-instance 127.0.0.1:47318.
    spawnRunner('safe-strategy-bot', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.safe_strategy.bot_service']);
    // MIKE (Under 3.5 / Over 4.5, 11/09): bot di trading come il Safe bot — legge SOLO
    // il feed unico dello scanner (ramo pre-KO O/U: SAFE_PRE_KO_OU_HOURS nel .env),
    // nessun login/stream proprio; paper di default, live solo da /mike. A riposo
    // processa richieste manuali, protezioni e settlement. Lock 127.0.0.1:47319.
    spawnRunner('mike-service', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.mike.service']);
    // BANCO DEL REPLAY (06/10, ordine dell'utente: «deve andare dalla UI»): il
    // worker del Backtest Automatico, che esegue anche "Applica bot" di Match
    // Replay (il bot col codice di produzione sulla registrazione, dal banco
    // comune). Prima andava avviato a mano da terminale. A riposo legge la coda
    // live_backtest_requests ogni 5 s (una SELECT); NESSUN ordine, nessun login
    // Betfair: il banco gira su flumine simulato e non tocca il DB vero.
    // Sotto WATCHDOG come gli altri servizi (crash -> riavvio con backoff).
    spawnRunner('backtest-worker', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.stream.backtest.worker']);
    // PARTITE DEL GIORNO tennis: il job quote (betfair_tennis_odds.py) popola
    // tennis_markets — all'avvio e poi ogni 30 minuti (processo breve, esce da solo).
    // MAI due run sovrapposte (audit 09/09): una run lenta ancora viva NON viene
    // raddoppiata (il job ha anche un lock di singola istanza sulla porta 47316).
    let tennisOddsChild = null;
    const runTennisOdds = () => {
        if (tennisOddsChild && tennisOddsChild.exitCode === null) {
            console.log('[desktop] tennis-odds ancora in corso: salto questo giro.');
            return;
        }
        tennisOddsChild = spawnRunner('tennis-odds', ['betfair_tennis_odds.py']) || null;
    };
    runTennisOdds();
    setInterval(runTennisOdds, 30 * 60 * 1000);
}

// tree-kill via taskkill /T /F: termina il watchdog E i runner figli — mai
// orfani. Cintura+bretelle: e' il FORZATO finale, chiamato SOLO su chi resta
// vivo dopo che orderedShutdown() ha gia' provato a chiederglielo per bene.
function killChildren() {
    for (const child of children) {
        if (child.pid == null || child.exitCode !== null) continue;
        try {
            spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true });
        } catch (err) {
            try { child.kill('SIGKILL'); } catch (_) { /* best-effort */ }
        }
    }
    children.length = 0;
}

// >>> K-SPEGNIMENTO-ORDINATO (28/09), seguito -------------------------------
// risolve quando il figlio esce DA SOLO entro timeoutMs, altrimenti quando il
// tempo scade (senza mai lanciare): orderedShutdown() decide dopo cosa fare.
function waitForExit(child, timeoutMs) {
    if (child.pid == null || child.exitCode !== null) return Promise.resolve(true);
    return new Promise((resolve) => {
        let done = false;
        const finish = (esito) => {
            if (done) return;
            done = true;
            clearTimeout(timer);
            child.removeListener('exit', onExit);
            resolve(esito);
        };
        const onExit = () => finish(true);
        const timer = setTimeout(() => finish(false), timeoutMs);
        child.once('exit', onExit);
    });
}

// Scrive il file ARRESTO (UNA volta, condiviso: lo leggono tutti i figli
// consapevoli, vedi ARRESTO_ORDINATO_LABELS sopra), aspetta ciascuno di loro
// per il proprio tempo massimo dichiarato (shutdownGraceMs), logga chi e'
// uscito da solo e chi no, poi forza (killChildren) chi resta vivo — MAI
// processi orfani, come da sempre, ma ora dopo aver dato una possibilita'
// al `finally`/ai context manager Python di girare per davvero.
async function orderedShutdown() {
    const targets = children.filter((c) => c.pid != null && c.exitCode === null);
    if (targets.length === 0) return;
    console.log(`[desktop] arresto ordinato: chiedo lo stop (file ARRESTO) a ${targets.length} figli...`);
    try {
        const p = arrestoPercorso(repoRoot);
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, `arresto ${Date.now()}`);
    } catch (err) {
        console.warn(`[desktop] file ARRESTO non scritto (${err && err.message}): nessun arresto ordinato, solo taskkill.`);
    }
    const risultati = await Promise.all(targets.map(async (child) => {
        const label = child._label || '?';
        if (!ARRESTO_ORDINATO_LABELS.has(label)) {
            // non legge il file (es. il job breve tennis-odds): nessuna
            // richiesta ordinata possibile da qui, resta il taskkill finale.
            return { label, consapevole: false, uscitoDaSolo: child.exitCode !== null };
        }
        const uscitoDaSolo = await waitForExit(child, shutdownGraceMs(label));
        return { label, consapevole: true, uscitoDaSolo };
    }));
    for (const r of risultati) {
        const riga = !r.consapevole
            ? 'non legge il file ARRESTO: niente arresto ordinato da qui'
            : (r.uscitoDaSolo ? 'arresto ordinato: uscito da solo' : `arresto ordinato: NON uscito entro ${shutdownGraceMs(r.label)}ms, forzo`);
        console.log(`[desktop] ${r.label}: ${riga}`);
        writeChildLog(r.label, 'desktop', riga);
    }
    // cintura+bretelle: chi resta vivo (non ha risposto in tempo, o non legge
    // il file) viene forzato — mai orfani.
    killChildren();
}

let shutdownStarted = false;
// Un solo punto d'uscita, idempotente: sia "chiudo la finestra" sia qualunque
// altro percorso di quit (Cmd+Q, logout, ecc.) passano da qui UNA volta sola.
async function shutdownAndQuit() {
    if (shutdownStarted) return;
    shutdownStarted = true;
    try {
        await orderedShutdown();
    } catch (err) {
        console.error(`[desktop] arresto ordinato KO (${err && err.message}): forzo comunque.`);
        killChildren();
    }
    app.exit(0); // MAI app.quit(): rilancerebbe 'before-quit' e farebbe un loop
}
// <<< K-SPEGNIMENTO-ORDINATO --------------------------------------------------

// ------------------------------------------------------- SSO web Betfair
// Le finestre "📺 Video" / "📊 Stats" aprono pagine betfair.it(.com) che
// richiedono la sessione WEB dell'utente. Per non chiedere un login manuale,
// all'avvio si fa lo STESSO certlogin del backend (credenziali+certificato dal
// .env del repo, mai chieste all'utente) e si inietta il sessionToken come
// cookie `ssoid` nella session di Electron: le finestre nascono già loggate.
// Keep-alive ogni 15 minuti (la sessione web italiana scade con l'inattività);
// se scade comunque → re-login automatico. Se il login all'avvio FALLISCE (rete
// non ancora su, Betfair lento) si ritenta con backoff 30s→60s→120s→300s: prima
// il tentativo successivo arrivava solo col keep-alive, cioè 15 minuti di
// finestre video "You need to be logged in". QUALSIASI fallimento resta soft: si
// logga un avviso e la finestra Betfair mostrerà il suo login (una tantum).
// Nessun ordine passa da qui: è solo navigazione (video + statistiche).
const BETFAIR_KEEPALIVE_MS = 15 * 60 * 1000;
const BETFAIR_LOGIN_RETRY_MS = [30_000, 60_000, 120_000, 300_000];
// le finestre Betfair aspettano l'esito del PRIMO login al massimo così: oltre,
// si aprono comunque (login manuale nel popout) — mai un click che non fa nulla.
const BETFAIR_SSO_WAIT_MS = 8_000;

// promessa risolta (true/false) al primo esito del login SSO: le finestre
// Betfair richieste PRIMA (click a 1s dall'avvio) aspettano qui, così nascono
// già loggate invece di mostrare la pagina di login.
let ssoReadyResolve = null;
const ssoReady = new Promise((resolve) => { ssoReadyResolve = resolve; });

function readEnvFile(file) {
    const out = {};
    try {
        const txt = fs.readFileSync(file, 'utf8');
        for (const raw of txt.split(/\r?\n/)) {
            const line = raw.trim();
            if (!line || line.startsWith('#')) continue;
            const eq = line.indexOf('=');
            if (eq <= 0) continue;
            const key = line.slice(0, eq).trim();
            let val = line.slice(eq + 1).trim();
            if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
                val = val.slice(1, -1);
            }
            out[key] = val;
        }
    } catch (_) { /* .env assente/illeggibile: si andrà di login manuale */ }
    return out;
}

// piccola utility https → JSON (mai throw: risolve null su qualunque errore).
function httpsJson(options, body) {
    return new Promise((resolve) => {
        try {
            const req = https.request(options, (res) => {
                let data = '';
                res.setEncoding('utf8');
                res.on('data', (c) => { data += c; });
                res.on('end', () => {
                    try { resolve(JSON.parse(data)); } catch (_) { resolve(null); }
                });
            });
            req.setTimeout(15000, () => { try { req.destroy(); } catch (_) {} resolve(null); });
            req.on('error', () => resolve(null));
            if (body) req.write(body);
            req.end();
        } catch (_) { resolve(null); }
    });
}

function resolveMaybeRelative(p) {
    if (!p) return null;
    return path.isAbsolute(p) ? p : path.join(repoRoot, p);
}

// certlogin identico al backend (config.py: identitysso-cert.betfair.it).
async function betfairCertLogin(env) {
    const identityUrl = (env.BETFAIR_IDENTITY_URL || 'https://identitysso-cert.betfair.it/api/certlogin').trim();
    const appKey = (env.BETFAIR_APP_KEY || '').trim();
    const username = (env.BETFAIR_USERNAME || '').trim();
    const password = (env.BETFAIR_PASSWORD || '').trim();
    const certFile = resolveMaybeRelative((env.BETFAIR_CERT_FILE || '').trim());
    const keyFile = resolveMaybeRelative((env.BETFAIR_KEY_FILE || '').trim());
    if (!appKey || !username || !password || !certFile || !keyFile) return null;
    let cert; let key;
    try {
        cert = fs.readFileSync(certFile);
        key = fs.readFileSync(keyFile);
    } catch (_) { return null; }
    let u;
    try { u = new URL(identityUrl); } catch (_) { return null; }
    const body = `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;
    const resp = await httpsJson({
        hostname: u.hostname,
        path: u.pathname,
        method: 'POST',
        cert,
        key,
        headers: {
            'X-Application': appKey,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Content-Length': Buffer.byteLength(body),
            Accept: 'application/json',
        },
    }, body);
    if (resp && resp.loginStatus === 'SUCCESS' && resp.sessionToken) return resp.sessionToken;
    if (resp && resp.status === 'SUCCESS' && resp.token) return resp.token; // variante interactive
    return null;
}

// host keep-alive: identitysso-cert.betfair.it → identitysso.betfair.it
function keepAliveHost(env) {
    const identityUrl = (env.BETFAIR_IDENTITY_URL || 'https://identitysso-cert.betfair.it/api/certlogin').trim();
    try { return new URL(identityUrl).hostname.replace('identitysso-cert', 'identitysso'); } catch (_) {
        return 'identitysso.betfair.it';
    }
}

// LOGIN INTERATTIVO (identitysso, senza certificato): produce un token di
// sessione WEB a tutti gli effetti — il servizio VIDEO accetta solo questo
// (il token del certlogin è pensato per le API: il sito lo tollera quasi
// ovunque, ma il player video risponde "You need to be logged in"). È la via
// dei tool concorrenti; il certlogin resta come fallback.
async function betfairInteractiveLogin(env) {
    const appKey = (env.BETFAIR_APP_KEY || '').trim();
    const username = (env.BETFAIR_USERNAME || '').trim();
    const password = (env.BETFAIR_PASSWORD || '').trim();
    if (!appKey || !username || !password) return null;
    const body = `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;
    const resp = await httpsJson({
        hostname: keepAliveHost(env),
        path: '/api/login',
        method: 'POST',
        headers: {
            'X-Application': appKey,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Content-Length': Buffer.byteLength(body),
            Accept: 'application/json',
        },
    }, body);
    if (resp && resp.status === 'SUCCESS' && resp.token) return resp.token;
    if (resp && resp.status) {
        console.warn(`[desktop] login interattivo Betfair non riuscito (${resp.status}${resp.error ? ': ' + resp.error : ''}) — fallback al certlogin.`);
    }
    return null;
}

async function betfairKeepAlive(env, token) {
    const resp = await httpsJson({
        hostname: keepAliveHost(env),
        path: '/api/keepAlive',
        method: 'GET',
        headers: {
            'X-Application': (env.BETFAIR_APP_KEY || '').trim(),
            'X-Authentication': token,
            Accept: 'application/json',
        },
    });
    return !!(resp && resp.status === 'SUCCESS');
}

// il cookie va su ENTRAMBI i domini: l'account è .it, ma i deep-link partono
// da betfair.com (che poi redirige) — così si arriva loggati in ogni caso.
async function setBetfairSsoCookie(token) {
    const targets = [
        { url: 'https://www.betfair.it/', domain: '.betfair.it' },
        { url: 'https://www.betfair.com/', domain: '.betfair.com' },
    ];
    let ok = false;
    for (const t of targets) {
        try {
            await session.defaultSession.cookies.set({
                url: t.url,
                name: 'ssoid',
                value: token,
                domain: t.domain,
                path: '/',
                secure: true,
                sameSite: 'no_restriction',
            });
            ok = true;
        } catch (err) {
            console.warn(`[desktop] cookie ssoid non impostato su ${t.domain}: ${err && err.message}`);
        }
    }
    return ok;
}

async function startBetfairWebSso() {
    const env = readEnvFile(path.join(repoRoot, '.env'));
    let token = null;
    let retryTimer = null;
    let retryIdx = 0;
    const doLogin = async () => {
        // 1) login INTERATTIVO: token web pieno (video incluso);
        // 2) fallback certlogin: copre sito/statistiche se l'interattivo fallisce.
        let t = await betfairInteractiveLogin(env);
        let kind = 'interattivo';
        if (!t) {
            t = await betfairCertLogin(env);
            kind = 'certlogin (fallback: il video potrebbe richiedere login manuale)';
        }
        if (!t) {
            console.warn('[desktop] SSO web Betfair non riuscito: la finestra video/stats chiederà il login manuale (una tantum, i cookie poi restano).');
            return null;
        }
        await setBetfairSsoCookie(t);
        console.log(`[desktop] SSO web Betfair OK (${kind}): finestre video/statistiche già loggate.`);
        return t;
    };
    // retry con backoff finché non c'è un token (poi il keep-alive fa il resto)
    const scheduleRetry = () => {
        if (retryTimer !== null) return;
        const delay = BETFAIR_LOGIN_RETRY_MS[Math.min(retryIdx, BETFAIR_LOGIN_RETRY_MS.length - 1)];
        retryIdx += 1;
        console.warn(`[desktop] SSO web Betfair: nuovo tentativo tra ${Math.round(delay / 1000)}s.`);
        retryTimer = setTimeout(async () => {
            retryTimer = null;
            token = await doLogin();
            if (!token) scheduleRetry(); else retryIdx = 0;
        }, delay);
    };
    token = await doLogin();
    if (ssoReadyResolve) { ssoReadyResolve(!!token); ssoReadyResolve = null; }
    if (!token) scheduleRetry();
    setInterval(async () => {
        if (!token) { if (retryTimer === null) scheduleRetry(); return; }
        const alive = await betfairKeepAlive(env, token);
        if (!alive) {
            console.warn('[desktop] sessione web Betfair scaduta: re-login automatico…');
            token = await doLogin();
            if (!token) scheduleRetry();
        }
    }, BETFAIR_KEEPALIVE_MS);
}

// ------------------------------------------------ finestre Betfair (popout)
// I pulsanti 📺 Video / 📊 Stats (frontend BetfairMediaButtons) fanno
// window.open(url, nome, features). Senza un handler Electron creava una
// finestra anonima per OGNI click (10 click = 10 finestre), con i webPreferences
// ereditati dalla UI e — al primo click dopo l'avvio — prima che l'SSO avesse
// impostato i cookie ("You need to be logged in"). Qui invece:
//   · una finestra per NOME (evento+feed): il secondo click la riporta davanti;
//   · si aspetta l'esito del primo login SSO (max BETFAIR_SSO_WAIT_MS);
//   · dimensioni tarate sul popout (640x780) e finestra pulita (niente menu);
//   · gli altri link esterni vanno al browser di sistema, le rotte della UI
//     (es. ladder popout /ladder-popout) restano finestre Electron normali.
const BETFAIR_HOST_RE = /^https:\/\/([a-z0-9-]+\.)*betfair\.(it|com)\//i;
const betfairWindows = new Map(); // frameName → BrowserWindow

function parseFeatureInt(features, key, fallback) {
    const m = new RegExp(`(?:^|,)\\s*${key}=(\\d+)`, 'i').exec(features || '');
    return m ? Number(m[1]) : fallback;
}

async function openBetfairWindow(url, frameName, features) {
    const key = frameName && frameName !== '_blank' ? frameName : null;
    const existing = key ? betfairWindows.get(key) : null;
    if (existing && !existing.isDestroyed()) {
        if (existing.webContents.getURL() !== url) existing.loadURL(url);
        if (existing.isMinimized()) existing.restore();
        existing.focus();
        return;
    }
    // le finestre nascono loggate: si aspetta il primo esito SSO (con tetto)
    await Promise.race([ssoReady, new Promise((r) => setTimeout(() => r(false), BETFAIR_SSO_WAIT_MS))]);
    const win = new BrowserWindow({
        width: parseFeatureInt(features, 'width', 640),
        height: parseFeatureInt(features, 'height', 780),
        autoHideMenuBar: true,
        backgroundColor: '#000000',
        title: 'Betfair',
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });
    if (key) {
        betfairWindows.set(key, win);
        win.on('closed', () => { if (betfairWindows.get(key) === win) betfairWindows.delete(key); });
    }
    // link aperti DAL popout Betfair (termini, help): browser di sistema
    win.webContents.setWindowOpenHandler(({ url: u }) => {
        if (/^https?:/i.test(u)) shell.openExternal(u);
        return { action: 'deny' };
    });
    await win.loadURL(url).catch((err) => {
        console.warn(`[desktop] finestra Betfair non caricata (${err && err.message})`);
    });
}

function attachWindowOpenHandler(win) {
    win.webContents.setWindowOpenHandler(({ url, frameName, features }) => {
        if (BETFAIR_HOST_RE.test(url)) {
            void openBetfairWindow(url, frameName, features);
            return { action: 'deny' };
        }
        if (url.startsWith(`http://127.0.0.1:${UI_PORT}/`)) {
            // rotte della UI (ladder popout multi-monitor): finestra Electron normale,
            // con le STESSE webPreferences della principale (preload + token, C1).
            return {
                action: 'allow',
                overrideBrowserWindowOptions: { webPreferences: uiWebPreferences() },
            };
        }
        if (/^https?:/i.test(url)) {
            shell.openExternal(url);
            return { action: 'deny' };
        }
        return { action: 'deny' };
    });
}

// ---------------------------------------------------------------- finestra
function createWindow() {
    const win = new BrowserWindow({
        width: 1600,
        height: 900,
        backgroundColor: '#0b1220',
        title: 'AlphaScore Trading',
        webPreferences: uiWebPreferences(),
    });
    attachWindowOpenHandler(win);
    win.loadURL(`http://127.0.0.1:${UI_PORT}/board`);
}

// ---------------------------------------------------------------- lifecycle
app.whenReady().then(async () => {
    repoRoot = resolveRepoRoot();
    if (!repoRoot) {
        dialog.showErrorBox(
            'AlphaScore Trading — repo non trovato',
            'Non trovo la cartella del progetto (.venv + frontend/dist).\n\n'
            + "L'exe va tenuto in desktop\\release\\ dentro il repo (o imposta la "
            + 'variabile ALPHASCORE_REPO col percorso del repo).\n'
            + 'Se manca frontend\\dist: esegui "npm run build" nella cartella frontend.',
        );
        app.quit();
        return;
    }
    DIST_DIR = path.join(repoRoot, 'frontend', 'dist');
    PYTHON = path.join(repoRoot, '.venv', 'Scripts', 'python.exe');
    console.log(`[desktop] repo: ${repoRoot}`);
    // K2 (26/09): console dei figli anche su file, prima di lanciare i runner
    childLogDir = prepareChildLogs(repoRoot);
    // K-SPEGNIMENTO-ORDINATO (28/09): un file di uno spegnimento PRECEDENTE
    // non deve fermare l'app appena riaperta — PRIMA di spawnRunner.
    cancellaArrestoAllAvvio(repoRoot);
    ensureFreshUi();  // l'exe serve SEMPRE l'ultima versione della UI (17/07)
    try {
        await startStaticServer();
    } catch (err) {
        // porta occupata = probabilmente un'altra istanza dell'app: usa quella UI.
        console.warn(`[desktop] server statico non avviato (${err && err.message}): forse già attivo`);
    }
    startRunners();
    // SSO web Betfair in background: NON blocca l'avvio (login ~1s; al primo
    // click su 📺/📊 i cookie sono già pronti; in caso di errore → login manuale).
    void startBetfairWebSso();
    createWindow();
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    void shutdownAndQuit();
});

// cintura+bretelle: anche su quit anomalo (Cmd+Q, logout, kill_switch UI, ecc.)
// mai figli orfani — e ora con l'arresto ORDINATO prima del taskkill (28/09).
// event.preventDefault() ferma la chiusura immediata: shutdownAndQuit() la
// completa da sé con app.exit(0) a lavoro fatto; se shutdownAndQuit() è già
// partito da window-all-closed non c'è nulla da fermare, si lascia proseguire.
app.on('before-quit', (event) => {
    if (shutdownStarted) return;
    event.preventDefault();
    void shutdownAndQuit();
});
process.on('exit', killChildren);
