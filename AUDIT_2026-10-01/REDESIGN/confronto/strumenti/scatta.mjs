const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs');
import { mkdirSync, writeFileSync } from 'node:fs';
// Uso: node scatta.mjs <cartella-uscita> [pagina,pagina] [1280,1600]   (con server.mjs acceso)
// Playwright: PLAYWRIGHT_MODULE=/percorso/playwright/index.mjs (default: quello globale di questo ambiente)
const OUT = process.argv[2];
const SOLO = process.argv[3] ? process.argv[3].split(',') : null;
const LARGHEZZE = (process.argv[4] || '1280,1600').split(',').map(Number);
mkdirSync(OUT, { recursive: true });
const PAGINE = [
  ['board', '/board'], ['control-room', '/control-room'], ['dashboard', '/dashboard'], ['omega', '/omega'],
  ['safe-strategy', '/safe-strategy'], ['mike', '/mike'], ['segui-live', '/segui-live'], ['multi-ladder', '/multi-ladder'],
  ['market-watch', '/market-watch'], ['live-pnl', '/live-pnl'], ['storico-calcio', '/storico/calcio'],
  ['storico-tennis', '/storico/tennis'], ['tennis', '/tennis'], ['tennis-terminal', '/tennis/terminal'],
  ['tennis-terminal-match', '/tennis/terminal?event=34000001&market=1.250000001&name=Match%20Odds&p1=Giocatore%20Uno&p2=Giocatore%20Due'],
  ['trade-journal', '/trade-journal'], ['report-personale', '/report-personale'], ['watchlist', '/watchlist'],
  ['analytics', '/analytics'], ['match-replay', '/match-replay'], ['select-sport', '/select-sport'],
  ['ladder-popout', '/ladder-popout?market=1.250000001&event=34000001&name=Match%20Odds'],
];
const browser = await chromium.launch();
const misure = [];
for (const [nome, url] of PAGINE) {
  if (SOLO && !SOLO.includes(nome)) continue;
  for (const stato of ['off', 'v2']) {
    for (const w of LARGHEZZE) {
      const h = w === 1280 ? 800 : w === 1600 ? 900 : 1080;
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, timezoneId: 'Europe/Rome', locale: 'it-IT' });
      await ctx.addInitScript((s) => {
        try { localStorage.setItem('ui.shell', s); } catch {}
        // conta i WebSocket che la pagina COSTRUISCE (i canali locali: rifiutati qui, ma aperti)
        const W = window.WebSocket; window.__ws = [];
        window.WebSocket = function (u, p) { window.__ws.push(String(u).replace(/\?.*$/, '')); return p === undefined ? new W(u) : new W(u, p); };
        window.WebSocket.prototype = W.prototype; Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
      }, stato);
      // nessuna rete esterna (font, texture): risposte vuote, deterministiche
      await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.fulfill({ status: 200, body: '' }));
      if (process.env.CANALE_FINTO === '1') {
        // tabellone finto sul canale locale (solo anteprima): stesse chiavi del push 'board' vero
        const ora = Date.parse('2026-10-01T08:00:00Z');
        const riga = (i, sport) => ({
          event_id: String(34000000 + i), event_name: sport === 'calcio' ? ['Squadra A v Squadra B', 'Squadra C v Squadra D', 'Squadra E v Squadra F', 'Squadra G v Squadra H'][i % 4] : ['Giocatore Uno v Giocatore Due', 'Giocatore Tre v Giocatore Quattro'][i % 2],
          open_date: new Date(ora + (i - 1) * 2400e3).toISOString(), market_id: '1.25000000' + i, status: 'OPEN', inplay: i === 0,
          total_matched: 12345 * (i + 1),
          selections: (sport === 'calcio' ? ['Casa', 'Pareggio', 'Trasferta'] : ['Giocatore 1', 'Giocatore 2']).map((n, k) => ({ selection_id: k + 1, name: n, back: 1.8 + k + i / 10, lay: 1.82 + k + i / 10, ltp: null })),
        });
        await ctx.routeWebSocket(/:4733[12]/, (ws) => {
          const sport = ws.url().includes('47331') ? 'calcio' : 'tennis';
          setTimeout(() => ws.send(JSON.stringify({ t: 'board', d: { rows: [0, 1, 2, 3].map((i) => riga(i, sport)) } })), 300);
        });
      }
      const page = await ctx.newPage();
      const ws = [];
      page.on('websocket', (s) => ws.push(s.url().replace(/\?.*$/, '')));
      const errori = [];
      page.on('pageerror', (e) => errori.push(String(e.message).slice(0, 200)));
      await page.goto('http://127.0.0.1:5199' + url, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(3500);
      const m = await page.evaluate(() => {
        const d = document.documentElement;
        const c = document.querySelector('.ds-contenuto');
        return {
          wsCostruiti: (window.__ws || []).filter((u) => !u.includes(':5199')),
          scrollOrizzontalePagina: d.scrollWidth > d.clientWidth + 1,
          scrollOrizzontaleContenuto: c ? c.scrollWidth > c.clientWidth + 1 : null,
          guscio: !!document.querySelector('[data-shell="v2"]'),
          prova: !!document.querySelector('[data-testid="shell-prova-nuova-grafica"]'),
        };
      });
      await page.screenshot({ path: `${OUT}/${nome}.${stato}.${w}.png` });
      const { wsCostruiti, ...resto } = m;
      misure.push({ nome, stato, w, websocket: [...new Set(wsCostruiti)].sort(), nWebsocket: wsCostruiti.length, ...resto, errori });
      await ctx.close();
    }
  }
}
await browser.close();
writeFileSync(`${OUT}/misure.json`, JSON.stringify(misure, null, 1));
console.log('fatto', misure.length);
