import fs from 'node:fs';
const here = new URL('.', import.meta.url);
const src = fs.readFileSync(new URL('../../../../../frontend/src/components/live/DutchingPanel.tsx', here), 'utf8');
const a = src.indexOf('// ------------------- aritmetica IDENTICA');
const b = src.indexOf('// ----------------------------- badge');
fs.writeFileSync(new URL('./_funcs.ts', here), src.slice(a, b));
const { dutchVariablePlan, nearestTickPrice } = await import('./_funcs.ts');
const py = JSON.parse(fs.readFileSync(new URL('./_cases.json', here)));
let bad = 0, ex = [];
for (const c of py) {
  const input = c.sels.map(([, p, w]) => ({ price: p, weight: w }));
  const r = dutchVariablePlan(input, c.T);
  const okTs = r.negativeIndex < 0;
  let same = okTs === c.ok;
  if (same && okTs) {
    same = r.total === c.total && r.bookPct === c.book && r.legs.length === c.legs.length
      && r.legs.every((l, i) => l.price === c.legs[i][0] && l.stake === c.legs[i][1] && l.profit === c.legs[i][2]);
  } else if (same && !okTs) {
    same = r.bookPct === c.book;
  }
  if (!same) { bad++; if (ex.length < 5) ex.push({ c, r }); }
}
console.log('casi', py.length, 'divergenti', bad);
if (ex.length) console.log(JSON.stringify(ex[0]).slice(0, 800));
const tp = JSON.parse(fs.readFileSync(new URL('./_tick_py.json', here)));
let tb = 0; for (const [k, v] of Object.entries(tp)) if (nearestTickPrice(Number(k)) !== v) tb++;
console.log('tick griglia', Object.keys(tp).length, 'divergenti', tb);
