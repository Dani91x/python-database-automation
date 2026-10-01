// Scatto dopo un'interazione (clic su una linguetta, apertura di un foglio).
// Uso (server.mjs acceso sulla 5198):
//   node interagisci.mjs <uscita.png> <percorso> <larghezza> <stato off|v2> <clic1;clic2;...> [intera=0|1]
// Ogni clic e' un selettore CSS (es. [data-testid="cr-tab-aperte"]); i clic
// passano dal mouse vero (Radix ascolta eventi di puntatore).
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs');
const [,, OUT, URL, W = '1600', STATO = 'v2', CLIC = '', INTERA = '0'] = process.argv;
const ORA = process.env.ORA_FISSA === undefined ? '2026-10-01T08:38:00Z' : process.env.ORA_FISSA;
const w = Number(W); const h = w === 1280 ? 800 : w === 1600 ? 900 : 1080;
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: w, height: h }, timezoneId: 'Europe/Rome', locale: 'it-IT' });
await ctx.addInitScript(([s, ora]) => {
  try { localStorage.setItem('ui.shell', s); } catch {}
  if (ora && ora !== '0') {
    const t0 = Date.parse(ora); const avvio = performance.now(); const D = Date;
    const ora2 = () => t0 + (performance.now() - avvio);
    // eslint-disable-next-line no-global-assign
    Date = class extends D { constructor(...a) { if (a.length) super(...a); else super(ora2()); } static now() { return ora2(); } };
  }
}, [STATO, ORA]);
await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.fulfill({ status: 200, body: '' }));
const page = await ctx.newPage();
const errori = []; page.on('pageerror', (e) => errori.push(String(e.message).slice(0, 200)));
await page.goto(URL.startsWith('file:') ? URL : 'http://127.0.0.1:' + (process.env.PORTA || 5198) + URL, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
for (const sel of CLIC.split(';').filter(Boolean)) {
  const el = page.locator(sel).first();
  await el.scrollIntoViewIfNeeded();
  await el.click();
  await page.waitForTimeout(700);
}
if (INTERA === '1') {
  const alto = await page.evaluate(() => { const c = document.querySelector('.ds-contenuto'); return c ? c.scrollHeight + 56 : document.documentElement.scrollHeight; });
  if (STATO === 'v2') await page.setViewportSize({ width: w, height: Math.min(alto, 16000) });
  await page.waitForTimeout(500);
  await page.screenshot({ path: OUT, fullPage: STATO !== 'v2' });
} else {
  await page.screenshot({ path: OUT });
}
console.log(JSON.stringify({ OUT, errori }));
await browser.close();
