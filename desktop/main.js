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
// Alla chiusura: taskkill /T /F sui figli (tree-kill) — MAI processi orfani.
// ============================================================================
'use strict';

const { app, BrowserWindow, dialog, session } = require('electron');
const http = require('http');
const https = require('https');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');

const UI_PORT = 47330;

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

// ---------------------------------------------------------------- runner python
function spawnRunner(label, args) {
    if (!fs.existsSync(PYTHON)) {
        console.error(`[desktop] python del venv non trovato: ${PYTHON} — runner ${label} NON avviato`);
        return;
    }
    // env passthrough + velocità canale locale (poll coda 0.15s, publish ladder 0.3s).
    const env = {
        ...process.env,
        LIVE_ORDER_QUEUE_POLL_SEC: '0.15',
        LIVE_LADDER_PUBLISH_SEC: '0.3',
        TENNIS_LADDER_PUBLISH_SEC: '0.3',
        // AUDIT LATENZA 17/07: il worker ordini TENNIS girava al default 1.0s
        // (click manuale 6.7x più lento del calcio, solo per env mancante);
        // il drain locale ora è splittato dalla coda DB (throttle ~1s interno),
        // quindi 0.15s NON moltiplica le query Supabase. Idem il risk engine:
        // stop/bracket automatici devono reagire in ~150ms, non ~1s.
        TENNIS_ORDER_POLL_SEC: '0.15',
        LIVE_RISK_ENGINE_POLL_SEC: '0.15',
        // desktop: i runner NON escono quando non ci sono eventi seguiti — restano
        // in attesa (canale locale + board vivi) finché non clicchi "Segui live".
        LIVE_RUNNER_KEEP_ALIVE: '1',
        // MODALITÀ ORDINI TENNIS: l'app nasce in PAPER (ordini SIMULATI, mai soldi
        // veri) se l'ambiente non specifica altro. Col vecchio default OFF il
        // worker ordini restava spento e i bot armati non piazzavano NEMMENO
        // ordini paper. MAI 'LIVE' di default: il LIVE va scelto esplicitamente.
        TENNIS_LIVE_ORDER_MODE: process.env.TENNIS_LIVE_ORDER_MODE || 'PAPER',
    };
    const child = spawn(PYTHON, args, {
        cwd: repoRoot,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
    });
    children.push(child);
    console.log(`[desktop] ${label} avviato (pid ${child.pid}): ${PYTHON} ${args.join(' ')}`);
    // log dei figli su console (prefissati per capire chi parla).
    const pipe = (stream, tag) => {
        stream.setEncoding('utf8');
        stream.on('data', (chunk) => {
            for (const line of String(chunk).split(/\r?\n/)) {
                if (line.trim()) console.log(`[${label}${tag}] ${line}`);
            }
        });
    };
    pipe(child.stdout, '');
    pipe(child.stderr, ':err');
    child.on('exit', (code) => {
        // uscita immediata = probabilmente watchdog già attivo altrove (lock porta): ok.
        console.log(`[desktop] ${label} terminato (exit ${code})`);
    });
}

function startRunners() {
    // niente doppio avvio: il lock porta dei runner protegge già; il watchdog esce
    // da solo se un'altra istanza è attiva.
    spawnRunner('runner-calcio', ['-m', 'Betfair.stream.watchdog']);
    spawnRunner('runner-tennis', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.stream.tennis_live.tennis_runner']);
    // SERVIZI BOT: senza di loro i bot non si armano e le "Partite del Giorno"
    // tennis restano vuote (tennis_bot_service popola tennis_markets). NON
    // avviare anche i .bat a mano: l'app avvia già tutto.
    spawnRunner('scalper-service', ['-m', 'Betfair.stream.scalper.scalper_service']);
    spawnRunner('tennis-bot-service', ['-m', 'Betfair.stream.tennis_live.tennis_bot_service']);
    // SAFE STRATEGY: scanner AUTONOMO degli eventi in-play (calcio+tennis).
    // REST leggero a cadenze adattive, scrive i fatti su safe_strategy_scan;
    // single-instance lock su 127.0.0.1:47315. Nessun ordine, mai.
    spawnRunner('safe-strategy-service', ['-m', 'Betfair.safe_strategy.service']);
    // OMEGA (Correct Score LAY): servizio leggero e ISOLATO. A riposo NON chiama
    // Betfair (idle = nessuna richiesta); agisce solo quando lo attivi/usi da /omega,
    // e di default in PAPER. Single-instance lock su 127.0.0.1:47313 → niente doppio
    // avvio se lanci anche avvia_omega_service.bat. Nessun impatto sugli altri runner.
    spawnRunner('omega-service', ['-m', 'Betfair.omega.omega_service']);
    // PARTITE DEL GIORNO tennis: il job quote (betfair_tennis_odds.py) popola
    // tennis_markets — all'avvio e poi ogni 30 minuti (processo breve, esce da solo).
    const runTennisOdds = () => spawnRunner('tennis-odds', ['betfair_tennis_odds.py']);
    runTennisOdds();
    setInterval(runTennisOdds, 30 * 60 * 1000);
}

// tree-kill via taskkill /T /F: termina il watchdog E i runner figli — mai orfani.
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

// ------------------------------------------------------- SSO web Betfair
// Le finestre "📺 Video" / "📊 Stats" aprono pagine betfair.it(.com) che
// richiedono la sessione WEB dell'utente. Per non chiedere un login manuale,
// all'avvio si fa lo STESSO certlogin del backend (credenziali+certificato dal
// .env del repo, mai chieste all'utente) e si inietta il sessionToken come
// cookie `ssoid` nella session di Electron: le finestre nascono già loggate.
// Keep-alive ogni 15 minuti (la sessione web italiana scade con l'inattività);
// se scade comunque → re-login automatico. QUALSIASI fallimento è soft: si
// logga un avviso e la finestra Betfair mostrerà il suo login (una tantum).
// Nessun ordine passa da qui: è solo navigazione (video + statistiche).
const BETFAIR_KEEPALIVE_MS = 15 * 60 * 1000;

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
    token = await doLogin();
    setInterval(async () => {
        if (!token) { token = await doLogin(); return; }
        const alive = await betfairKeepAlive(env, token);
        if (!alive) {
            console.warn('[desktop] sessione web Betfair scaduta: re-login automatico…');
            token = await doLogin();
        }
    }, BETFAIR_KEEPALIVE_MS);
}

// ---------------------------------------------------------------- finestra
function createWindow() {
    const win = new BrowserWindow({
        width: 1600,
        height: 900,
        backgroundColor: '#0b1220',
        title: 'AlphaScore Trading',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
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
    killChildren();
    app.quit();
});

// cintura+bretelle: anche su quit anomalo, mai figli orfani.
app.on('before-quit', killChildren);
process.on('exit', killChildren);
