// Scatto del PROTOTIPO (prototipo/index.html#<id>) a pagina intera. Uso: node scatta_prototipo.mjs <uscita> <id,id> [larghezza] [intera=0|1]
const { chromium } = await import('/opt/node22/lib/node_modules/playwright/index.mjs');
const [,, out, ids, w='1600', full='0'] = process.argv;
const b = await chromium.launch();
for (const id of ids.split(',')) {
  const ctx = await b.newContext({ viewport: { width: +w, height: +w===1280?800:900 } });
  await ctx.route(/^https?:/, r => r.fulfill({ status: 200, body: '' }));
  const p = await ctx.newPage();
  await p.goto(new URL('../../prototipo/index.html', import.meta.url).href + '#' + id);
  await p.waitForTimeout(800);
  await p.screenshot({ path: `${out}/${id}.${w}.png`, fullPage: full==='1' });
  await ctx.close();
}
await b.close();
