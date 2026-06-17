// validate.mts — esegue il motore TS (calc.ts) sulla batteria generata da Python e confronta 1:1.
// Uso: node --experimental-strip-types validate.mts
import { readFileSync } from "node:fs";
import { evalTotal, evalScore } from "../supabase/functions/telegram-bot/calc.ts";

const cases = JSON.parse(readFileSync(new URL("./battery.json", import.meta.url), "utf-8"));

let maxProb = 0, maxFair = 0, maxBack = 0, maxLay = 0, worst: any = null;
let fails = 0;
for (const c of cases) {
  let mp;
  if (c.kind === "total") mp = evalTotal(c.market, c.q0, c.q_opp ?? undefined, c.minute, c.goals);
  else mp = evalScore(c.market, c.qH, c.qD, c.qA, c.qO, c.qU, c.minute, c.gh, c.ga);
  const dProb = Math.abs(mp.prob - c.prob);
  const dFair = Math.abs(mp.fairOdds - c.fair);
  const dBack = Math.abs(mp.minBack - c.min_back);
  const dLay = Math.abs(mp.maxLay - c.max_lay);
  if (dProb > maxProb) { maxProb = dProb; worst = { c, ts: mp.prob, py: c.prob }; }
  maxFair = Math.max(maxFair, dFair);
  maxBack = Math.max(maxBack, dBack);
  maxLay = Math.max(maxLay, dLay);
  if (dProb > 1e-9) fails++;
}

console.log(`Casi: ${cases.length}`);
console.log(`Max diff PROB  (TS vs Python): ${maxProb.toExponential(3)}`);
console.log(`Max diff FAIR  : ${maxFair.toExponential(3)}  (Python arrotonda a 3 decimali)`);
console.log(`Max diff MINBACK: ${maxBack.toExponential(3)}`);
console.log(`Max diff MAXLAY : ${maxLay.toExponential(3)}`);
console.log(`Casi con diff prob > 1e-9: ${fails}`);
if (worst && maxProb > 1e-9) console.log("Caso peggiore:", JSON.stringify(worst));
console.log(maxProb < 1e-9 ? "\n✅ PORT TS == PYTHON (1:1 sulle probabilita')" : "\n❌ DIVERGENZA — port NON 1:1");
process.exit(maxProb < 1e-9 ? 0 : 1);
