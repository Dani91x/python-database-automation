import fs from 'node:fs';
import { roundToTick } from '../../../../../frontend/src/lib/matching.ts';
const py = JSON.parse(fs.readFileSync(new URL('./_tick_py.json', import.meta.url)));
let bad = 0; const ex = [];
for (const [k, v] of Object.entries(py)) {
  const r = roundToTick(Number(k));
  if (Math.abs(r - v) > 1e-9) { bad++; if (ex.length < 10) ex.push([k, v, r]); }
}
console.log('diff', bad, JSON.stringify(ex));
