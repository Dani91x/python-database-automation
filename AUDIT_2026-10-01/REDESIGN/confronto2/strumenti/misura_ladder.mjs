// Misura delle AREE CLICCABILI del ladder (brief §6): per le prime righe di ogni
// ladder in pagina, getBoundingClientRect di ogni cella-bottone con il guscio
// spento e acceso. Le larghezze del contenuto devono essere le stesse: col guscio
// spento la finestra e' larga quanto il contenuto del guscio (larghezza - 244 px
// della sidebar), cosi' si confrontano le stesse colonne. Esito: ogni cella v2
// deve essere larga e alta ALMENO quanto in off.
// Uso (server.mjs acceso, PORTA): node misura_ladder.mjs '<percorso>' [larghezzaV2=1600]
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs');
const [,, URL = '/segui-live?event=34812001', WV2 = '1600'] = process.argv;
const PORTA = process.env.PORTA || 5198;
const b = await chromium.launch();
async function misura(stato, w) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } });
  await ctx.addInitScript((s) => { try { localStorage.setItem('ui.shell', s); } catch {} }, stato);
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.fulfill({ status: 200, body: '' }));
  if (process.env.CANALE_FINTO === '1') await (await import('./canaleFinto.mjs')).instradaCanali(ctx);
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${PORTA}${URL}`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);
  const celle = await p.evaluate(() => {
    const out = [];
    // righe del ladder: griglie con gridTemplateColumns in linea e celle-bottone
    const righe = [...document.querySelectorAll('div.grid.items-stretch')].filter((r) => r.style.gridTemplateColumns && r.querySelector(':scope > button'));
    righe.slice(0, 60).forEach((r, i) => [...r.children].forEach((c, j) => {
      const q = c.getBoundingClientRect();
      out.push({ k: `${i}.${j}`, tag: c.tagName, w: +q.width.toFixed(2), h: +q.height.toFixed(2) });
    }));
    return out;
  });
  await ctx.close();
  return celle;
}
const v2 = await misura('v2', Number(WV2));
const off = await misura('off', Number(WV2) - 244);
const mappa = new Map(off.map((c) => [c.k, c]));
let peggiori = [], confrontate = 0, minW = Infinity, minH = Infinity;
for (const c of v2) {
  const o = mappa.get(c.k); if (!o || c.tag !== 'BUTTON') continue;
  confrontate++;
  minW = Math.min(minW, c.w - o.w); minH = Math.min(minH, c.h - o.h);
  if (c.w + 0.01 < o.w || c.h + 0.01 < o.h) peggiori.push({ cella: c.k, off: [o.w, o.h], v2: [c.w, c.h] });
}
const esempio = v2.find((c) => c.tag === 'BUTTON'); const esempioOff = esempio && mappa.get(esempio.k);
console.log(JSON.stringify({ URL, celleOff: off.length, celleV2: v2.length, bottoniConfrontati: confrontate,
  scartoMinimoLarghezzaPx: +minW.toFixed(2), scartoMinimoAltezzaPx: +minH.toFixed(2),
  esempio: esempio && { off: [esempioOff.w, esempioOff.h], v2: [esempio.w, esempio.h] },
  piuPiccoleInV2: peggiori.length, dettaglio: peggiori.slice(0, 10) }, null, 1));
await b.close();
