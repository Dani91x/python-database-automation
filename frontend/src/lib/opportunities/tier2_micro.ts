// ============================================================================
// tier2_micro.ts — DETECTOR TIER 2: DIREZIONALI / MICROSTRUTTURA.
//
// ⚠️ ONESTÀ INTELLETTUALE: questi NON sono arbitraggi. Sono segnali con un edge
// STATISTICO a breve orizzonte. Il profitto indicato è il profitto POTENZIALE
// realizzabile SE il movimento atteso si verifica (greening al target), già al
// netto della commissione Betfair. La `confidence` riflette l'incertezza e la
// liquidità realmente disponibile (fill). Ogni opp porta un exitPlan con
// target/stop espliciti. tier = 'directional' per tutti.
//
// CONVENZIONE DIREZIONALE (heuristica documentata, non legge fisica):
//   imbalance I = (backLiq - layLiq) / (backLiq + layLiq), range [-1,+1].
//   I > 0  → peso del denaro lato BACK domina → quota attesa in COMPRESSIONE
//            (si accorcia) → segnale BACK ora, uscita LAY più in basso (greenBack).
//   I < 0  → peso del denaro lato LAY domina → quota attesa in DRIFT
//            (si allunga) → segnale LAY ora, uscita BACK più in alto (greenLay).
//
// MATEMATICA GREENING (lock equo su entrambi gli esiti, STESSO mercato):
//   back S @ B poi lay L @ T (T<B):  L = S*B/T  → profitto = S*(B-T)/T
//   lay  S @ L poi back B @ T (T>L): B = S*L/T  → profitto = S*(T-L)/T
//   Commissione: prelevata solo su vincita netta di mercato → netWin(profit,c).
// ============================================================================
import type { Detector, Leg, MarketLite, Opportunity, OppConfig, SelLite, Snapshot } from './types';
import { matchedStake, fillRatio, netWin } from './fill';
import { bestBack, bestLay, isMatchOdds, isOverUnder, isOver, isDraw } from './helpers';
import { isMarketOpen, tradeableSelection } from './tradeable';

// ------------------------------------------------------------------ costanti
// Soglie esportate così i test possono ricalcolare gli stessi valori.
export const IMBALANCE_THRESHOLD = 0.6;      // orderFlowImbalance: |I| minimo
export const TARGET_TICKS = 2;               // tick di movimento atteso (target)
export const STOP_TICKS = 2;                 // tick di stop-loss
export const WOM_TOPK = 3;                    // weightOfMoney: livelli aggregati
export const WOM_IMBALANCE = 0.5;            // weightOfMoney: |wom| minimo
export const WOM_MIN_LIQ = 100;              // weightOfMoney: liquidità minima (£)
export const VALUE_EDGE_THRESHOLD = 0.05;    // valueVsModel: edge minimo (per £1)
export const PRESSURE_THRESHOLD = 0.6;       // momentumPressure: pressione minima
export const SCALP_MAX_SPREAD_TICKS = 2;     // spreadScalp: spread massimo (tick)
export const SCALP_MIN_LIQ = 50;             // spreadScalp: liquidità minima (£)
export const SCALP_IMBALANCE = 0.3;          // spreadScalp: |I| minimo
export const SCALP_TICKS = 1;                // spreadScalp: tick scalpati

// Confidence cap per detector (onestà: nessuno è risk-free).
const CONF_CAP_OFI = 0.8;
const CONF_CAP_WOM = 0.8;
const CONF_CAP_VALUE = 0.7;
const CONF_CAP_PRESSURE = 0.75;
const CONF_CAP_SCALP = 0.6;

// =========================================================== tick ladder Betfair
// Bande [lower, upper) e incremento. Identiche al tick-size ufficiale Betfair.
const TICK_BANDS: ReadonlyArray<readonly [number, number, number]> = [
    [1.0, 2.0, 0.01],
    [2.0, 3.0, 0.02],
    [3.0, 4.0, 0.05],
    [4.0, 6.0, 0.1],
    [6.0, 10.0, 0.2],
    [10.0, 20.0, 0.5],
    [20.0, 30.0, 1.0],
    [30.0, 50.0, 2.0],
    [50.0, 100.0, 5.0],
    [100.0, 1000.0, 10.0],
];

const round2 = (x: number): number => Math.round(x * 100) / 100;
export const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);

// Incremento per SALIRE da `odds` (banda che contiene odds: lower<=odds<upper).
function upTickSize(odds: number): number | null {
    for (const [lo, hi, step] of TICK_BANDS) if (odds >= lo && odds < hi) return step;
    return null;
}
// Incremento per SCENDERE da `odds` (banda che termina in odds: lower<odds<=upper).
function downTickSize(odds: number): number | null {
    for (const [lo, hi, step] of TICK_BANDS) if (odds > lo && odds <= hi) return step;
    return null;
}

// Quota dopo n tick verso l'ALTO. null se fuori scala.
export function tickUp(odds: number, n: number): number | null {
    let o = odds;
    for (let i = 0; i < n; i++) {
        const s = upTickSize(o);
        if (s == null) return null;
        o = round2(o + s);
    }
    return o;
}
// Quota dopo n tick verso il BASSO. null se scende a <=1.01 o fuori scala.
export function tickDown(odds: number, n: number): number | null {
    let o = odds;
    for (let i = 0; i < n; i++) {
        const s = downTickSize(o);
        if (s == null) return null;
        o = round2(o - s);
        if (o <= 1.0) return null;
    }
    return o;
}
// Numero di tick tra due quote (low<high). null se non allineate/fuori scala.
export function ticksBetween(low: number, high: number): number | null {
    if (!(high > low)) return low === high ? 0 : null;
    let o = low;
    for (let i = 1; i <= 5000; i++) {
        const s = upTickSize(o);
        if (s == null) return null;
        o = round2(o + s);
        if (Math.abs(o - high) < 1e-9) return i;
        if (o > high) return null;
    }
    return null;
}

// ===================================================== profitto di greening
// back @B poi lay @T (T<B). Lordo. >0 quando T<B.
export function greenBack(stake: number, backOdds: number, target: number): number {
    return (stake * (backOdds - target)) / target;
}
// lay @L poi back @T (T>L). Lordo. >0 quando T>L.
export function greenLay(stake: number, layOdds: number, target: number): number {
    return (stake * (target - layOdds)) / target;
}

// =============================================================== fase partita
export function phaseOf(minute: number | null): string {
    if (minute == null || minute <= 0) return 'pre';
    if (minute <= 45) return '1T';
    if (minute <= 75) return '2T';
    return 'late';
}

// ===================================================== utilità snapshot/nomi
function marketIndex(snap: Snapshot): Map<string, MarketLite> {
    const m = new Map<string, MarketLite>();
    for (const mk of snap.markets) m.set(mk.market_id, mk);
    return m;
}
function selName(mkt: MarketLite | undefined, selId: number): string {
    const s = mkt?.selections.find((x) => x.selection_id === selId);
    return s?.name ?? `#${selId}`;
}
function mktName(mkt: MarketLite | undefined, marketId: string): string {
    return mkt?.market_name ?? marketId;
}
// Liste degli ID selezione presenti nel ladder di un mercato.
function ladderSelIds(ladder: Record<string, unknown>): number[] {
    return Object.keys(ladder)
        .map((k) => Number(k))
        .filter((n) => Number.isFinite(n));
}

// Costruisce una Leg con matchedStake realistico via fill.ts.
interface BuiltLeg {
    leg: Leg;
    matched: number;
    ratio: number;
}
function buildLeg(
    snap: Snapshot,
    marketId: string,
    mkt: MarketLite | undefined,
    selId: number,
    side: 'back' | 'lay',
    price: number,
    desired: number,
): BuiltLeg | null {
    const st = snap.state[marketId];
    const entry = st?.ladder?.[String(selId)];
    if (!entry) return null;
    const levels = side === 'back' ? entry.back : entry.lay;
    const matched = matchedStake(levels, price, desired, side);
    if (matched <= 0) return null;
    const ratio = fillRatio(levels, price, desired, side);
    const leg: Leg = {
        marketId,
        marketName: mktName(mkt, marketId),
        selectionId: selId,
        selectionName: selName(mkt, selId),
        side,
        price,
        stake: desired,
        matchedStake: matched,
    };
    return { leg, matched, ratio };
}

// =============================================================== DETECTOR A
// orderFlowImbalance — imbalance al best back/lay per selezione → BACK/LAY.
export const orderFlowImbalance: Detector = (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
    const out: Opportunity[] = [];
    const mkIdx = marketIndex(snap);
    const phase = phaseOf(snap.minute);

    for (const marketId of Object.keys(snap.state)) {
        const st = snap.state[marketId];
        if (!st?.ladder) continue;
        if (!isMarketOpen(st)) continue; // mercato non operabile (SOSPESO/CHIUSO)
        const mkt = mkIdx.get(marketId);
        for (const selId of ladderSelIds(st.ladder)) {
            if (!tradeableSelection(st, selId)) continue; // mercato reale a due lati + prezzo plausibile
            const e = st.ladder[String(selId)];
            const backSize = e?.back?.[0]?.[1];
            const laySize = e?.lay?.[0]?.[1];
            if (typeof backSize !== 'number' || typeof laySize !== 'number') continue;
            if (backSize <= 0 && laySize <= 0) continue;
            const I = (backSize - laySize) / (backSize + laySize);
            if (Math.abs(I) < IMBALANCE_THRESHOLD) continue;

            const side: 'back' | 'lay' = I > 0 ? 'back' : 'lay';
            const entryPx = side === 'back' ? bestBack(st.ladder, selId) : bestLay(st.ladder, selId);
            if (entryPx == null || entryPx <= 1) continue;

            const target = side === 'back' ? tickDown(entryPx, TARGET_TICKS) : tickUp(entryPx, TARGET_TICKS);
            const stop = side === 'back' ? tickUp(entryPx, STOP_TICKS) : tickDown(entryPx, STOP_TICKS);
            if (target == null || target <= 1) continue;

            const built = buildLeg(snap, marketId, mkt, selId, side, entryPx, cfg.stake);
            if (!built) continue;

            const gross = side === 'back'
                ? greenBack(built.matched, entryPx, target)
                : greenLay(built.matched, entryPx, target);
            const profit = netWin(gross, cfg.commission);
            const profitPct = (profit / built.matched) * 100;
            const confidence = clamp01(Math.min(CONF_CAP_OFI, Math.abs(I)) * built.ratio);

            const name = selName(mkt, selId);
            const verb = side === 'back' ? 'PUNTA' : 'BANCA';
            const dir = side === 'back' ? 'discesa' : 'salita';
            const stopTxt = stop == null ? 'n/d' : stop.toFixed(2);
            out.push({
                id: `ofi:${marketId}:${selId}`,
                tier: 'directional',
                type: 'order_flow_imbalance',
                title: `Order-flow ${side === 'back' ? 'BACK' : 'LAY'} ${name}`,
                instruction: `${verb} ${name} £${round2(built.matched)} @${entryPx.toFixed(2)} `
                    + `(imbalance ${I >= 0 ? '+' : ''}${I.toFixed(2)}): attesa ${dir} quota → `
                    + `esci a ${target.toFixed(2)} per ~£${round2(profit)}.`,
                legs: [built.leg],
                profit,
                profitPct,
                confidence,
                explanation: `Best back £${round2(backSize)} vs best lay £${round2(laySize)} `
                    + `→ I=${I.toFixed(2)}. Segnale direzionale (NON garantito): `
                    + `il lato sottile cede, la quota si muove a breve orizzonte.`,
                phase,
                exitPlan: `Target: ${side === 'back' ? 'LAY' : 'BACK'} a ${target.toFixed(2)} `
                    + `(+£${round2(profit)} netti). Stop: a ${stopTxt} esci in perdita.`,
            });
        }
    }
    return out;
};

// =============================================================== DETECTOR B
// weightOfMoney — peso aggregato (top-K) vs traded volume (tv) → steam.
export const weightOfMoney: Detector = (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
    const out: Opportunity[] = [];
    const mkIdx = marketIndex(snap);
    const phase = phaseOf(snap.minute);

    const sumTopK = (lv: ReadonlyArray<readonly [number, number]> | undefined): number => {
        if (!lv) return 0;
        let s = 0;
        for (let i = 0; i < Math.min(WOM_TOPK, lv.length); i++) {
            const v = lv[i]?.[1];
            if (typeof v === 'number' && Number.isFinite(v) && v > 0) s += v;
        }
        return s;
    };

    for (const marketId of Object.keys(snap.state)) {
        const st = snap.state[marketId];
        if (!st?.ladder) continue;
        if (!isMarketOpen(st)) continue; // mercato non operabile (SOSPESO/CHIUSO)
        const mkt = mkIdx.get(marketId);
        for (const selId of ladderSelIds(st.ladder)) {
            if (!tradeableSelection(st, selId)) continue; // mercato reale a due lati + prezzo plausibile
            const e = st.ladder[String(selId)];
            const backVol = sumTopK(e?.back);
            const layVol = sumTopK(e?.lay);
            const liq = backVol + layVol;
            if (liq < WOM_MIN_LIQ) continue;
            const wom = (backVol - layVol) / liq;
            if (Math.abs(wom) < WOM_IMBALANCE) continue;

            const tv = typeof e?.tv === 'number' && Number.isFinite(e.tv) && e.tv > 0 ? e.tv : 0;
            // steamFactor: denaro fresco vicino al best rispetto al già scambiato.
            const steamFactor = tv > 0 ? Math.min(1, liq / tv) : 1;

            const side: 'back' | 'lay' = wom > 0 ? 'back' : 'lay';
            const entryPx = side === 'back' ? bestBack(st.ladder, selId) : bestLay(st.ladder, selId);
            if (entryPx == null || entryPx <= 1) continue;
            const target = side === 'back' ? tickDown(entryPx, TARGET_TICKS) : tickUp(entryPx, TARGET_TICKS);
            const stop = side === 'back' ? tickUp(entryPx, STOP_TICKS) : tickDown(entryPx, STOP_TICKS);
            if (target == null || target <= 1) continue;

            const built = buildLeg(snap, marketId, mkt, selId, side, entryPx, cfg.stake);
            if (!built) continue;

            const gross = side === 'back'
                ? greenBack(built.matched, entryPx, target)
                : greenLay(built.matched, entryPx, target);
            const profit = netWin(gross, cfg.commission);
            const profitPct = (profit / built.matched) * 100;
            const confidence = clamp01(Math.min(CONF_CAP_WOM, Math.abs(wom)) * built.ratio * steamFactor);

            const name = selName(mkt, selId);
            const verb = side === 'back' ? 'PUNTA' : 'BANCA';
            const stopTxt = stop == null ? 'n/d' : stop.toFixed(2);
            out.push({
                id: `wom:${marketId}:${selId}`,
                tier: 'directional',
                type: 'weight_of_money',
                title: `Steam ${side === 'back' ? 'BACK' : 'LAY'} ${name}`,
                instruction: `${verb} ${name} £${round2(built.matched)} @${entryPx.toFixed(2)} `
                    + `(WoM ${wom >= 0 ? '+' : ''}${wom.toFixed(2)}, top-${WOM_TOPK}): steam in corso → `
                    + `esci a ${target.toFixed(2)} per ~£${round2(profit)}.`,
                legs: [built.leg],
                profit,
                profitPct,
                confidence,
                explanation: `Denaro aggregato top-${WOM_TOPK}: back £${round2(backVol)} vs lay £${round2(layVol)} `
                    + `→ WoM=${wom.toFixed(2)}; tv=£${round2(tv)} → steam ${steamFactor.toFixed(2)}. `
                    + `Segnale momentum, NON garantito.`,
                phase,
                exitPlan: `Target: ${side === 'back' ? 'LAY' : 'BACK'} a ${target.toFixed(2)} `
                    + `(+£${round2(profit)} netti). Stop: a ${stopTxt} chiudi.`,
            });
        }
    }
    return out;
};

// =============================================================== DETECTOR C
// momentumPressure — pressione di gioco (corner/tiri/cards) → back Over / lay Draw.
// Le statistiche NON sono nello Snapshot: si forniscono via provider opzionale.
export interface MatchPressure {
    pressure: number;     // 0..1 intensità offensiva corrente
    rising: boolean;      // la pressione sta salendo (trend)
    side?: 'home' | 'away' | 'both';
}
export type PressureProvider = (snap: Snapshot) => MatchPressure | null;

export function makeMomentumPressure(getPressure?: PressureProvider): Detector {
    return (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
        if (!getPressure) return [];
        const p = getPressure(snap);
        if (!p || !p.rising || p.pressure < PRESSURE_THRESHOLD) return [];

        const out: Opportunity[] = [];
        const mkIdx = marketIndex(snap);
        const phase = phaseOf(snap.minute);
        const pressure = clamp01(p.pressure);

        for (const marketId of Object.keys(snap.state)) {
            const st = snap.state[marketId];
            if (!st?.ladder) continue;
            if (!isMarketOpen(st)) continue; // mercato non operabile (SOSPESO/CHIUSO)
            const mkt = mkIdx.get(marketId);
            if (!mkt) continue;

            // --- OVER_UNDER: BACK l'Over (un gol accorcia la quota Over).
            if (isOverUnder(mkt)) {
                const over: SelLite | undefined = mkt.selections.find((s) => isOver(s.name));
                if (over && tradeableSelection(st, over.selection_id)) {
                    const entryPx = bestBack(st.ladder, over.selection_id);
                    if (entryPx != null && entryPx > 1) {
                        const target = tickDown(entryPx, TARGET_TICKS);
                        const stop = tickUp(entryPx, STOP_TICKS);
                        const built = buildLeg(snap, marketId, mkt, over.selection_id, 'back', entryPx, cfg.stake);
                        if (built && target != null && target > 1) {
                            const profit = netWin(greenBack(built.matched, entryPx, target), cfg.commission);
                            const name = selName(mkt, over.selection_id);
                            out.push({
                                id: `mom:over:${marketId}:${over.selection_id}`,
                                tier: 'directional',
                                type: 'momentum_pressure',
                                title: `Pressione → BACK ${name}`,
                                instruction: `PUNTA ${name} £${round2(built.matched)} @${entryPx.toFixed(2)} `
                                    + `(pressione ${pressure.toFixed(2)} in salita) → esci a ${target.toFixed(2)} per ~£${round2(profit)}.`,
                                legs: [built.leg],
                                profit,
                                profitPct: (profit / built.matched) * 100,
                                confidence: clamp01(Math.min(CONF_CAP_PRESSURE, pressure) * built.ratio),
                                explanation: `Pressione offensiva ${pressure.toFixed(2)} in salita: gol più probabile → Over si accorcia. NON garantito.`,
                                phase,
                                exitPlan: `Target: LAY ${name} a ${target.toFixed(2)} (+£${round2(profit)}). `
                                    + `Stop: ${stop == null ? 'n/d' : stop.toFixed(2)}.`,
                            });
                        }
                    }
                }
            }

            // --- MATCH_ODDS: LAY il Draw (un gol allunga la quota del Pareggio).
            if (isMatchOdds(mkt)) {
                const draw: SelLite | undefined = mkt.selections.find((s) => isDraw(s.name));
                if (draw && tradeableSelection(st, draw.selection_id)) {
                    const entryPx = bestLay(st.ladder, draw.selection_id);
                    if (entryPx != null && entryPx > 1) {
                        const target = tickUp(entryPx, TARGET_TICKS);
                        const stop = tickDown(entryPx, STOP_TICKS);
                        const built = buildLeg(snap, marketId, mkt, draw.selection_id, 'lay', entryPx, cfg.stake);
                        if (built && target != null && target > 1) {
                            const profit = netWin(greenLay(built.matched, entryPx, target), cfg.commission);
                            const name = selName(mkt, draw.selection_id);
                            out.push({
                                id: `mom:draw:${marketId}:${draw.selection_id}`,
                                tier: 'directional',
                                type: 'momentum_pressure',
                                title: `Pressione → LAY ${name}`,
                                instruction: `BANCA ${name} £${round2(built.matched)} @${entryPx.toFixed(2)} `
                                    + `(pressione ${pressure.toFixed(2)} in salita) → esci a ${target.toFixed(2)} per ~£${round2(profit)}.`,
                                legs: [built.leg],
                                profit,
                                profitPct: (profit / built.matched) * 100,
                                confidence: clamp01(Math.min(CONF_CAP_PRESSURE, pressure) * built.ratio),
                                explanation: `Pressione offensiva ${pressure.toFixed(2)} in salita: gol più probabile → il Pareggio si allunga. NON garantito.`,
                                phase,
                                exitPlan: `Target: BACK ${name} a ${target.toFixed(2)} (+£${round2(profit)}). `
                                    + `Stop: ${stop == null ? 'n/d' : stop.toFixed(2)}.`,
                            });
                        }
                    }
                }
            }
        }
        return out;
    };
}
// Detector di comodo senza provider (registrabile; restituisce [] senza dati).
export const momentumPressure: Detector = makeMomentumPressure();

// =============================================================== DETECTOR D
// valueVsModel — edge atteso vs probabilità "fair" da un modello esterno.
export type FairProbProvider = (snap: Snapshot, marketId: string, selectionId: number) => number | null;

export function makeValueVsModel(getFairProb?: FairProbProvider): Detector {
    return (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
        if (!getFairProb) return [];
        const out: Opportunity[] = [];
        const mkIdx = marketIndex(snap);
        const phase = phaseOf(snap.minute);
        const c = cfg.commission;

        for (const marketId of Object.keys(snap.state)) {
            const st = snap.state[marketId];
            if (!st?.ladder) continue;
            if (!isMarketOpen(st)) continue; // mercato non operabile (SOSPESO/CHIUSO)
            const mkt = mkIdx.get(marketId);
            for (const selId of ladderSelIds(st.ladder)) {
                if (!tradeableSelection(st, selId)) continue; // mercato reale a due lati + prezzo plausibile
                const p = getFairProb(snap, marketId, selId);
                if (p == null || !(p > 0) || !(p < 1)) continue;
                const oBack = bestBack(st.ladder, selId);
                const oLay = bestLay(st.ladder, selId);

                // EV per £1 di stake, commissione sulla vincita netta.
                const backEdge = oBack != null && oBack > 1 ? p * (oBack - 1) * (1 - c) - (1 - p) : -Infinity;
                const layEdge = oLay != null && oLay > 1 ? (1 - p) * (1 - c) - p * (oLay - 1) : -Infinity;

                const useBack = backEdge >= layEdge;
                const edge = useBack ? backEdge : layEdge;
                if (!(edge >= VALUE_EDGE_THRESHOLD)) continue;

                const side: 'back' | 'lay' = useBack ? 'back' : 'lay';
                const entryPx = useBack ? (oBack as number) : (oLay as number);
                const built = buildLeg(snap, marketId, mkt, selId, side, entryPx, cfg.stake);
                if (!built) continue;

                const profit = edge * built.matched; // EV £ (già al netto commissione)
                const profitPct = edge * 100;
                const confidence = clamp01(Math.min(CONF_CAP_VALUE, edge) * built.ratio);

                const name = selName(mkt, selId);
                const verb = side === 'back' ? 'PUNTA' : 'BANCA';
                const impliedTxt = (1 / entryPx).toFixed(3);
                out.push({
                    id: `val:${marketId}:${selId}`,
                    tier: 'directional',
                    type: 'value_vs_model',
                    title: `Value ${side === 'back' ? 'BACK' : 'LAY'} ${name}`,
                    instruction: `${verb} ${name} £${round2(built.matched)} @${entryPx.toFixed(2)} `
                        + `(modello p=${p.toFixed(3)} vs mercato ${impliedTxt}) → EV ~£${round2(profit)}.`,
                    legs: [built.leg],
                    profit,
                    profitPct,
                    confidence,
                    explanation: `Prob. fair modello=${p.toFixed(3)}, implicita mercato=${impliedTxt}; `
                        + `edge=${(edge * 100).toFixed(2)}% per £ (netto comm.). Valore ATTESO, non garantito.`,
                    phase,
                    exitPlan: `Mantieni a scadenza o esci se l'edge sparisce (quota allineata al modello).`,
                });
            }
        }
        return out;
    };
}
export const valueVsModel: Detector = makeValueVsModel();

// =============================================================== DETECTOR E
// spreadScalp — mercato liquido + spread stretto + imbalance → scalp 1-2 tick.
export const spreadScalp: Detector = (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
    const out: Opportunity[] = [];
    const mkIdx = marketIndex(snap);
    const phase = phaseOf(snap.minute);

    for (const marketId of Object.keys(snap.state)) {
        const st = snap.state[marketId];
        if (!st?.ladder) continue;
        if (!isMarketOpen(st)) continue; // mercato non operabile (SOSPESO/CHIUSO)
        const mkt = mkIdx.get(marketId);
        for (const selId of ladderSelIds(st.ladder)) {
            if (!tradeableSelection(st, selId)) continue; // mercato reale a due lati + prezzo plausibile
            const e = st.ladder[String(selId)];
            const bb = bestBack(st.ladder, selId);
            const bl = bestLay(st.ladder, selId);
            if (bb == null || bl == null || bb <= 1 || bl <= 1) continue;
            if (!(bl > bb)) continue; // book incrociato/anomalo → salta
            const spread = ticksBetween(bb, bl);
            if (spread == null || spread > SCALP_MAX_SPREAD_TICKS) continue;

            const backSize = e?.back?.[0]?.[1];
            const laySize = e?.lay?.[0]?.[1];
            if (typeof backSize !== 'number' || typeof laySize !== 'number') continue;
            const liq = Math.min(backSize, laySize);
            if (liq < SCALP_MIN_LIQ) continue;
            if (backSize + laySize <= 0) continue;
            const I = (backSize - laySize) / (backSize + laySize);
            if (Math.abs(I) < SCALP_IMBALANCE) continue;

            const side: 'back' | 'lay' = I > 0 ? 'back' : 'lay';
            const entryPx = side === 'back' ? bb : bl;
            const target = side === 'back' ? tickDown(entryPx, SCALP_TICKS) : tickUp(entryPx, SCALP_TICKS);
            if (target == null || target <= 1) continue;

            const built = buildLeg(snap, marketId, mkt, selId, side, entryPx, cfg.stake);
            if (!built) continue;

            const gross = side === 'back'
                ? greenBack(built.matched, entryPx, target)
                : greenLay(built.matched, entryPx, target);
            const profit = netWin(gross, cfg.commission);
            const profitPct = (profit / built.matched) * 100;
            const confidence = clamp01(Math.min(CONF_CAP_SCALP, Math.abs(I)) * built.ratio);

            const name = selName(mkt, selId);
            const verb = side === 'back' ? 'PUNTA' : 'BANCA';
            out.push({
                id: `scalp:${marketId}:${selId}`,
                tier: 'directional',
                type: 'spread_scalp',
                title: `Scalp ${SCALP_TICKS} tick ${side === 'back' ? 'BACK' : 'LAY'} ${name}`,
                instruction: `${verb} ${name} £${round2(built.matched)} @${entryPx.toFixed(2)} `
                    + `(spread ${spread} tick, I ${I >= 0 ? '+' : ''}${I.toFixed(2)}) → chiudi a ${target.toFixed(2)} per ~£${round2(profit)}. `
                    + `⚠️ fill NON garantito: serve essere primi in coda.`,
                legs: [built.leg],
                profit,
                profitPct,
                confidence,
                explanation: `Spread ${spread} tick, liquidità min £${round2(liq)}, I=${I.toFixed(2)}. `
                    + `Scalp ${SCALP_TICKS} tick: margine sottile, dipende dal riempimento in coda. NON risk-free.`,
                phase,
                exitPlan: `Target: chiusura opposta a ${target.toFixed(2)} (+£${round2(profit)}). `
                    + `Stop: se il prezzo va contro di ${STOP_TICKS} tick, esci a mercato.`,
            });
        }
    }
    return out;
};

// Tutti i detector tier2 (i factory-based usano provider opzionali).
export const TIER2_DETECTORS: Detector[] = [
    orderFlowImbalance,
    weightOfMoney,
    momentumPressure,
    valueVsModel,
    spreadScalp,
];
