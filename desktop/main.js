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

const { app, BrowserWindow } = require('electron');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');

const UI_PORT = 47330;
const REPO_ROOT = path.resolve(__dirname, '..');
const DIST_DIR = path.join(REPO_ROOT, 'frontend', 'dist');
const PYTHON = path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');

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
    };
    const child = spawn(PYTHON, args, {
        cwd: REPO_ROOT,
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
    try {
        await startStaticServer();
    } catch (err) {
        // porta occupata = probabilmente un'altra istanza dell'app: usa quella UI.
        console.warn(`[desktop] server statico non avviato (${err && err.message}): forse già attivo`);
    }
    startRunners();
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
