// Confronto pixel per pixel di due cartelle di screenshot (stessi nomi).
// Uso: node confronta_png.mjs <cartellaA> <cartellaB> [filtro]
// Esempio del referto: A = app di master con ui.shell=off, B = ramo con ui.shell=off,
// stessa anteprima popolata, scattati uno dopo l'altro.
import { readFileSync, readdirSync } from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs');
const [,, A, B, FILTRO = ''] = process.argv;
const b = await chromium.launch(); const p = await b.newPage();
let tutti = true;
for (const n of readdirSync(A).filter((x) => x.endsWith('.png') && x.includes(FILTRO)).sort()) {
  const a = 'data:image/png;base64,' + readFileSync(`${A}/${n}`).toString('base64');
  const c = 'data:image/png;base64,' + readFileSync(`${B}/${n}`).toString('base64');
  const r = await p.evaluate(async ([x, y]) => {
    const load = (s) => new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.src = s; });
    const [i1, i2] = await Promise.all([load(x), load(y)]);
    if (i1.width !== i2.width || i1.height !== i2.height) return { dim: [i1.width, i1.height, i2.width, i2.height] };
    const cv = (i) => { const k = document.createElement('canvas'); k.width = i.width; k.height = i.height; const g = k.getContext('2d'); g.drawImage(i, 0, 0); return g.getImageData(0, 0, i.width, i.height).data; };
    const d1 = cv(i1), d2 = cv(i2); let diff = 0; let minY = 1e9, maxY = -1;
    for (let j = 0; j < d1.length; j += 4) if (d1[j] !== d2[j] || d1[j+1] !== d2[j+1] || d1[j+2] !== d2[j+2]) { diff++; const y = Math.floor(j / 4 / i1.width); minY = Math.min(minY, y); maxY = Math.max(maxY, y); }
    return diff ? { diff, minY, maxY } : { diff: 0 };
  }, [a, c]);
  if (r.dim || r.diff) tutti = false;
  console.log(n, JSON.stringify(r));
}
console.log(tutti ? 'IDENTICHE' : 'DIFFERENZE');
await b.close();
