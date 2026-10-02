const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs');
import { mkdirSync, writeFileSync } from 'node:fs';
// Uso (con confronto2/strumenti/server.mjs acceso sulla 5198):
//   node scatta.mjs <cartella-uscita> <pagine> <larghezze> [stati=off,v2] [fullPage=0|1]
//   es. node scatta.mjs /tmp/out control-room 1600 off,v2 1
// <pagine>: nomi separati da virgola (vedi PAGINE) oppure 'tutte'.
// fullPage=1: pagina intera. Col guscio spento (off) e' il fullPage di Playwright;
// col guscio acceso (v2) lo scorrimento e' dentro `.ds-contenuto`: la viewport si
// allunga a scrollHeight del contenitore + 56 (la testata del guscio) e si scatta.
// Orologio: ORA_FISSA (ISO, default 2026-10-01T08:38:00Z, lo stesso dei finti di
// frontend/src/anteprima) fissa Date.now nella pagina; ORA_FISSA=0 la lascia vera.
// Playwright: PLAYWRIGHT_MODULE=/percorso/playwright/index.mjs (default: quello globale di questo ambiente)
const PORTA = Number(process.env.PORTA || 5198);
const OUT = process.argv[2];
if (!OUT) { console.error('uso: node scatta.mjs <uscita> <pagine> <larghezze> [stati] [fullPage]'); process.exit(2); }
const SOLO = process.argv[3] && process.argv[3] !== 'tutte' ? process.argv[3].split(',') : null;
const LARGHEZZE = (process.argv[4] || '1280,1600').split(',').map(Number);
const STATI = (process.argv[5] || 'off,v2').split(',');
const INTERA = process.argv[6] === '1';
const ORA_FISSA = process.env.ORA_FISSA === undefined ? '2026-10-01T08:38:00Z' : process.env.ORA_FISSA;
mkdirSync(OUT, { recursive: true });
const PAGINE = [
  ['board', '/board'], ['control-room', '/control-room'], ['dashboard', '/dashboard'], ['omega', '/omega'],
  ['safe-strategy', '/safe-strategy'], ['mike', '/mike'], ['segui-live', '/segui-live'], ['segui-live-terminal', '/segui-live?event=34812001'], ['multi-ladder', '/multi-ladder'],
  ['market-watch', '/market-watch'], ['live-pnl', '/live-pnl'], ['storico-calcio', '/storico/calcio'],
  ['storico-tennis', '/storico/tennis'], ['tennis', '/tennis'], ['tennis-terminal', '/tennis/terminal'],
  ['tennis-terminal-sinner', '/tennis/terminal?event=34813501&market=1.248135010&name=Match%20Odds&p1=J.%20Sinner&p2=J.%20Draper'], ['tennis-terminal-match', '/tennis/terminal?event=34000001&market=1.250000001&name=Match%20Odds&p1=Giocatore%20Uno&p2=Giocatore%20Due'],
  ['trade-journal', '/trade-journal'], ['report-personale', '/report-personale'], ['watchlist', '/watchlist'],
  ['analytics', '/analytics'], ['match-replay', '/match-replay'], ['select-sport', '/select-sport'],
  ['ladder-popout', '/ladder-popout?market=1.248120010&event=34812001&name=Match%20Odds&eventName=Inter%20-%20Torino'],
];
const browser = await chromium.launch();
const misure = [];
for (const [nome, url] of PAGINE) {
  if (SOLO && !SOLO.includes(nome)) continue;
  for (const stato of STATI) {
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
      if (process.env.CANALE_FINTO === '1') await (await import('./canaleFinto.mjs')).instradaCanali(ctx);
      const page = await ctx.newPage();
      // orologio della pagina allineato ai finti (i timer restano veri)
      if (ORA_FISSA && ORA_FISSA !== '0') await page.clock.setFixedTime(new Date(ORA_FISSA));
      const ws = [];
      page.on('websocket', (s) => ws.push(s.url().replace(/\?.*$/, '')));
      const errori = [];
      page.on('pageerror', (e) => errori.push(String(e.message).slice(0, 200)));
      await page.goto(`http://127.0.0.1:${PORTA}` + url, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(3500);
      const m = await page.evaluate((porta) => {
        const d = document.documentElement;
        const c = document.querySelector('.ds-contenuto');
        return {
          wsCostruiti: (window.__ws || []).filter((u) => !u.includes(':' + porta)),
          scrollOrizzontalePagina: d.scrollWidth > d.clientWidth + 1,
          scrollOrizzontaleContenuto: c ? c.scrollWidth > c.clientWidth + 1 : null,
          guscio: !!document.querySelector('[data-shell="v2"]'),
          prova: !!document.querySelector('[data-testid="shell-prova-nuova-grafica"]'),
          altezzaContenuto: c ? c.scrollHeight : null,
        };
      }, PORTA);
      const file = `${OUT}/${nome}.${stato}.${w}${INTERA ? '.intera' : ''}.png`;
      if (!INTERA) {
        await page.screenshot({ path: file });
      } else if (m.guscio && m.altezzaContenuto != null) {
        // guscio acceso: lo scorrimento e' in `.ds-contenuto`. Si allunga la viewport a
        // scrollHeight + 56 (la testata del guscio); poi, siccome alcuni riquadri hanno
        // un'altezza legata alla viewport (max-h calc(100vh-...)), si rimisura il fondo
        // VERO del contenuto (non lo scrollHeight, che con un contenitore alto quanto la
        // viewport crescerebbe con lei) finche' l'altezza non si stabilizza.
        let alta = Math.max(h, m.altezzaContenuto + 56);
        for (let giro = 0; giro < 5; giro++) {
          await page.setViewportSize({ width: w, height: alta });
          await page.waitForTimeout(giro === 0 ? 700 : 400);
          const fondo = await page.evaluate(() => {
            const c = document.querySelector('.ds-contenuto');
            if (!c) return 0;
            const top = c.getBoundingClientRect().top;
            let max = 0;
            for (const e of c.querySelectorAll('*')) {
              const r = e.getBoundingClientRect();
              if (r.height > 0 && r.bottom - top > max) max = r.bottom - top;
            }
            const pad = parseFloat(getComputedStyle(c).paddingBottom) || 0;
            return Math.ceil(max + c.scrollTop + pad + 56);
          });
          const nuova = Math.max(h, fondo);
          if (Math.abs(nuova - alta) < 4) break;
          alta = nuova;
        }
        await page.screenshot({ path: file, fullPage: true });
      } else {
        await page.screenshot({ path: file, fullPage: true });
      }
      const { wsCostruiti, ...resto } = m;
      misure.push({ nome, stato, w, intera: INTERA, file, websocket: [...new Set(wsCostruiti)].sort(), nWebsocket: wsCostruiti.length, ...resto, errori });
      await ctx.close();
    }
  }
}
await browser.close();
writeFileSync(`${OUT}/misure.json`, JSON.stringify(misure, null, 1));
console.log('fatto', misure.length);
