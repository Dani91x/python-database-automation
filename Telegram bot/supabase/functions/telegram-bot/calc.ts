// calc.ts — motore calcolatore valore (port 1:1 di value_engine Python).
// Verificato contro Python su una batteria di casi (vedi _calc_validation). Nessun import esterno:
// matematica pura, gira identica in Deno (bot) e Node (validazione).
// REGOLE PARITA' 1:1 col Python: floor (Math.floor, NON Math.round), stesse costanti, stessi range.

const MAX_GOALS = 15;
const LAM_MAX = 50.0;          // bound inversione lambda (totali)
const ROUNDTRIP_TOL = 0.02;    // tolleranza convergenza derive_lambdas

// CDF empirica dei minuti-gol (da value_engine/data/goal_time_cdf.json, 120k gol reali)
const GOAL_CDF: number[] = [0.0, 0.004795009208408687, 0.011954339566292247, 0.01999303147450681, 0.02771648056279139, 0.03598745665411226, 0.044689817656916264, 0.053790380116473926, 0.06256740389241924, 0.0718007001708948, 0.08108377163146455, 0.08977783677058619, 0.09863781918335518, 0.10822783760017256, 0.11732010419604785, 0.12704285643178312, 0.13623467339184683, 0.14526057307826318, 0.154477277629374, 0.16355295249788457, 0.1732757047336198, 0.18241774651158932, 0.19181696006371224, 0.20103366461482305, 0.21053242853113438, 0.220263476630552, 0.22949677290902756, 0.23873836505118548, 0.24773108128287236, 0.25660765542300606, 0.26655439597816527, 0.2759121302118764, 0.2855519238107879, 0.29476862836189877, 0.30422591295979823, 0.3140565114234043, 0.32320684906505615, 0.33336098621227456, 0.34329113504006903, 0.3527981948200627, 0.3626951601931277, 0.37166298883376747, 0.38174246320784455, 0.39199615071925137, 0.4027061107331884, 0.43476962386554063, 0.44072605398948084, 0.44997594199532115, 0.46012178327885717, 0.47045842942708765, 0.48136749016940156, 0.4918285742728675, 0.5033515289276767, 0.5144182110799556, 0.5256259229148347, 0.5374143452074795, 0.5487381991339119, 0.5600620530603441, 0.5710540724394817, 0.5819714290454779, 0.5935773423371107, 0.6042541188963183, 0.6152212506844088, 0.6256491513331452, 0.6362180816644821, 0.6479069535929386, 0.6583680376964046, 0.6695840453949661, 0.6806341358198802, 0.6916012676079707, 0.7026596538965671, 0.7129050455442916, 0.7236813724676876, 0.7346650959831428, 0.745399943588127, 0.7571966617444542, 0.7682467521693683, 0.7794378722768828, 0.7903718206102437, 0.8016624910819465, 0.8131356705546614, 0.824351678253223, 0.8353602893597253, 0.8469081316055814, 0.8580577723946841, 0.8699457450515173, 0.8817922383899388, 0.8935972524099484, 0.9050123608368867, 0.9172321680410147, 1.0];

// ---- Poisson ---------------------------------------------------------------
function factorial(k: number): number {
  let r = 1;
  for (let i = 2; i <= k; i++) r *= i;
  return r;
}
function pois(lam: number, k: number): number {
  if (lam < 0) throw new Error(`lam<0: ${lam}`);
  return Math.exp(-lam) * Math.pow(lam, k) / factorial(k);
}
function pLe(k: number, lam: number): number {
  if (lam < 0) throw new Error(`lam<0: ${lam}`);
  if (k < 0) return 0.0;
  let s = 0.0;
  for (let i = 0; i <= k; i++) s += Math.exp(-lam) * Math.pow(lam, i) / factorial(i);
  return s;
}

// ---- goal timing -----------------------------------------------------------
export function remainingFrac(t: number, T = 90.0): number {
  const cdf = GOAL_CDF;
  let ti = t > 0 ? Math.floor(t) : 0;
  if (T <= 45.5) {
    ti = Math.min(ti, 45);
    const c45 = cdf[45];
    if (c45 <= 0) return Math.max(0.0, (45.0 - t) / 45.0);
    return Math.max(0.0, Math.min(1.0, (c45 - cdf[ti]) / c45));
  }
  if (ti >= 90) return 0.0;
  return Math.max(0.0, Math.min(1.0, 1.0 - cdf[ti]));
}

// ---- de-vig ----------------------------------------------------------------
export function devigPair(o: number, oOpp?: number): number {
  if (!o || o <= 1.0) return 0.0;
  if (!oOpp || oOpp <= 1.0) return 1.0 / o;
  const imp = 1.0 / o, impO = 1.0 / oOpp;
  return imp / (imp + impO);
}
export function devigMultiplicative(odds: Record<string, number>): Record<string, number> {
  for (const v of Object.values(odds)) if (!v || v <= 1.0) throw new Error(`quote >1 richieste: ${JSON.stringify(odds)}`);
  const raw: Record<string, number> = {};
  let s = 0;
  for (const [k, v] of Object.entries(odds)) { raw[k] = 1.0 / v; s += raw[k]; }
  const out: Record<string, number> = {};
  for (const k of Object.keys(raw)) out[k] = raw[k] / s;
  return out;
}

// ---- Dixon-Coles -----------------------------------------------------------
function dcTau(x: number, y: number, lam: number, mu: number, rho: number): number {
  if (x === 0 && y === 0) return 1.0 - lam * mu * rho;
  if (x === 0 && y === 1) return 1.0 + lam * rho;
  if (x === 1 && y === 0) return 1.0 + mu * rho;
  if (x === 1 && y === 1) return 1.0 - rho;
  return 1.0;
}
function scoreMatrix(lam: number, mu: number, rho = -0.13, maxGoals = MAX_GOALS): number[][] {
  lam = Math.max(lam, 1e-6); mu = Math.max(mu, 1e-6);
  const ph: number[] = [], pa: number[] = [];
  for (let i = 0; i <= maxGoals; i++) ph.push(pois(lam, i));
  for (let j = 0; j <= maxGoals; j++) pa.push(pois(mu, j));
  const M: number[][] = [];
  for (let i = 0; i <= maxGoals; i++) { M.push([]); for (let j = 0; j <= maxGoals; j++) M[i].push(ph[i] * pa[j]); }
  for (const [i, j] of [[0, 0], [0, 1], [1, 0], [1, 1]]) M[i][j] *= Math.max(0.0, dcTau(i, j, lam, mu, rho));
  let s = 0; for (const row of M) for (const v of row) s += v;
  for (let i = 0; i <= maxGoals; i++) for (let j = 0; j <= maxGoals; j++) M[i][j] /= s;
  return M;
}
function marketsFromMatrix(M: number[][]): Record<string, number> {
  const n = M.length;
  let H = 0, D = 0, A = 0, btts = 0;
  const tot: Record<number, number> = {};
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const p = M[i][j];
    if (i > j) H += p; else if (i === j) D += p; else A += p;
    if (i >= 1 && j >= 1) btts += p;
    tot[i + j] = (tot[i + j] || 0) + p;
  }
  const over = (lf: number) => { let s = 0; for (const [k, v] of Object.entries(tot)) if (Number(k) >= lf + 1) s += v; return s; };
  const ha = H + A;
  const dnbH = ha < 1e-9 ? NaN : H / ha;
  const dnbA = ha < 1e-9 ? NaN : A / ha;
  return {
    H, D, A, DC_1X: H + D, DC_12: H + A, DC_X2: D + A, DNB_H: dnbH, DNB_A: dnbA,
    BTTS: btts, BTTS_NO: 1 - btts,
    O15: over(1), U15: 1 - over(1), O25: over(2), U25: 1 - over(2), O35: over(3), U35: 1 - over(3),
  };
}

// ---- bisezione (solleva se non c'e' cambio di segno) -----------------------
function bisect(f: (x: number) => number, lo: number, hi: number, it = 64): number {
  let flo = f(lo); const fhi = f(hi);
  if (flo === 0.0) return lo;
  if (fhi === 0.0) return hi;
  if (flo * fhi > 0) throw new Error(`bisect: nessun cambio segno su [${lo},${hi}]`);
  for (let k = 0; k < it; k++) {
    const m = (lo + hi) / 2.0;
    const fm = f(m);
    if (fm === 0.0) return m;
    if (flo * fm <= 0) hi = m; else { lo = m; flo = fm; }
  }
  return (lo + hi) / 2.0;
}

// ---- totali (univariato) ---------------------------------------------------
const TOTALS: Record<string, [string, number, number]> = {
  O05: ["over", 0.5, 90], U05: ["under", 0.5, 90], O15: ["over", 1.5, 90], U15: ["under", 1.5, 90],
  O25: ["over", 2.5, 90], U25: ["under", 2.5, 90], O35: ["over", 3.5, 90], U35: ["under", 3.5, 90],
  O45: ["over", 4.5, 90], U45: ["under", 4.5, 90], O55: ["over", 5.5, 90], U55: ["under", 5.5, 90],
  HT05: ["over", 0.5, 45], HT_U05: ["under", 0.5, 45], HT15: ["over", 1.5, 45], HT_U15: ["under", 1.5, 45],
};
function lamFromPrematchTotal(side: string, k: number, prob: number): number {
  prob = Math.min(Math.max(prob, 1e-6), 1 - 1e-6);
  const f = side === "under" ? (L: number) => pLe(k, L) - prob : (L: number) => (1 - pLe(k, L)) - prob;
  if (f(1e-4) * f(LAM_MAX) > 0) throw new Error(`lambda non bracketabile (side=${side},k=${k},prob=${prob})`);
  return bisect(f, 1e-4, LAM_MAX);
}
function condProbTotal(side: string, k: number, lamFull: number, minute: number, goals: number,
                       T: number, rf: (t: number, T: number) => number): number {
  let frac = rf(minute, T);
  frac = Math.max(0.0, Math.min(1.0, frac));
  const lamRem = lamFull * frac;
  if (side === "under") { const need = k - goals; return need < 0 ? 0.0 : pLe(need, lamRem); }
  const need = (k + 1) - goals; return need <= 0 ? 1.0 : 1.0 - pLe(need - 1, lamRem);
}
function probTotal(market: string, prematchProb: number, minute: number, periodGoals: number,
                   rf: (t: number, T: number) => number): number {
  const [side, line, T] = TOTALS[market];
  return condProbTotal(side, Math.floor(line), lamFromPrematchTotal(side, Math.floor(line), prematchProb),
                        minute, periodGoals, T, rf);
}

// ---- bivariato (score) -----------------------------------------------------
function deriveLambdas(pHome: number, pOver25: number, rho = -0.13, maxGoals = MAX_GOALS): [number, number] {
  pHome = Math.min(Math.max(pHome, 1e-4), 1 - 1e-4);
  pOver25 = Math.min(Math.max(pOver25, 1e-4), 1 - 1e-4);
  const o25at = (muTot: number, s: number) => marketsFromMatrix(scoreMatrix(Math.max((muTot + s) / 2, 1e-6), Math.max((muTot - s) / 2, 1e-6), rho, maxGoals)).O25;
  const homeAt = (muTot: number, s: number) => marketsFromMatrix(scoreMatrix(Math.max((muTot + s) / 2, 1e-6), Math.max((muTot - s) / 2, 1e-6), rho, maxGoals)).H;
  let s = 0.0, muTot = 2.5;
  for (let it = 0; it < 12; it++) {
    const sFixed = s;
    muTot = bisect((mt) => o25at(mt, sFixed) - pOver25, 0.05, 15.0);
    const mFixed = muTot;
    s = bisect((x) => homeAt(mFixed, x) - pHome, -12.0, 12.0);
  }
  const lam = Math.max((muTot + s) / 2, 1e-6), mu = Math.max((muTot - s) / 2, 1e-6);
  const mk = marketsFromMatrix(scoreMatrix(lam, mu, rho, maxGoals));
  if (Math.abs(mk.H - pHome) > ROUNDTRIP_TOL || Math.abs(mk.O25 - pOver25) > ROUNDTRIP_TOL)
    throw new Error(`derive_lambdas non converge (quote incoerenti): H ${pHome}->${mk.H}, O25 ${pOver25}->${mk.O25}`);
  return [lam, mu];
}
function conditionalMarkets(lam: number, mu: number, rho: number, minute: number, gh: number, ga: number,
                            T: number, rf: (t: number, T: number) => number, maxGoals = MAX_GOALS): Record<string, number> {
  let frac = rf(minute, T); frac = Math.max(0.0, Math.min(1.0, frac));
  const R = scoreMatrix(lam * frac, mu * frac, rho, maxGoals);
  const n = R.length, fn = n + Math.max(gh, ga);
  const M: number[][] = []; for (let i = 0; i < fn; i++) M.push(new Array(fn).fill(0));
  for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) M[gh + a][ga + b] += R[a][b];
  return marketsFromMatrix(M);
}
function evalScoreMarket(market: string, pHome: number, pOver25: number, minute: number, gh: number, ga: number,
                         rf: (t: number, T: number) => number, rho = -0.13): number {
  const [lam, mu] = deriveLambdas(pHome, pOver25, rho);
  const mk = conditionalMarkets(lam, mu, rho, minute, gh, ga, 90.0, rf);
  if (!(market in mk)) throw new Error(`mercato bivariato sconosciuto: ${market}`);
  return mk[market];
}

// ---- pricing ---------------------------------------------------------------
export interface MarketPrice { market: string; prob: number; fairOdds: number; minBack: number; maxLay: number; }
export function price(market: string, prob: number, commission = 0.05): MarketPrice {
  if (!Number.isFinite(prob)) return { market, prob: NaN, fairOdds: NaN, minBack: NaN, maxLay: NaN };
  const p = Math.min(Math.max(prob, 1e-9), 1 - 1e-9);
  return {
    market, prob,
    fairOdds: 1.0 / p,
    minBack: 1.0 + (1.0 - p) / (p * (1.0 - commission)),
    maxLay: 1.0 + (1.0 - p) * (1.0 - commission) / p,
  };
}

// ---- API pubblica per il bot -----------------------------------------------
export const SCORE_MARKETS = new Set(["H", "D", "A", "DC_1X", "DC_12", "DC_X2", "DNB_H", "DNB_A", "BTTS", "BTTS_NO"]);
export function isTotal(market: string): boolean { return market in TOTALS; }

/** Totali: quota pre-match (+opzionale opposta per de-vig), minuto, gol nel periodo. */
export function evalTotal(market: string, q0: number, qOpp: number | undefined, minute: number, goals: number): MarketPrice {
  const p0 = qOpp ? devigPair(q0, qOpp) : 1.0 / q0;
  return price(market, probTotal(market, p0, minute, goals, remainingFrac));
}
/** Score: quote 1X2 + Over/Under 2.5, minuto, punteggio attuale. */
export function evalScore(market: string, qH: number, qD: number, qA: number, qO: number, qU: number,
                          minute: number, gh: number, ga: number): MarketPrice {
  const pHome = devigMultiplicative({ H: qH, D: qD, A: qA }).H;
  const pO25 = devigPair(qO, qU);
  return price(market, evalScoreMarket(market, pHome, pO25, minute, gh, ga, remainingFrac));
}
