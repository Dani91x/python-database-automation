// ============================================================================
// tier1_quasi.ts — DETECTOR TIER 1: QUASI-ARB / RISCHIO RIDOTTO.
//
// Opportunità near-certain basate su TEMPO o STRUTTURA del book. NON sono
// arbitraggi puri (tranne il caso "book incrociato" di backToLay): hanno un
// RISCHIO RESIDUO esplicitato in `explanation`/`exitPlan` e una `confidence`
// che lo riflette. Tutta la matematica è ESATTA e unit-testata.
//
// SEMANTICA EXCHANGE (vedi replay-pnl.ts):
//   BACK (PUNTA) stake S @ O:  vince → +S*(O-1) ; perde → -S
//   LAY  (BANCA) stake S @ O:  selez. vince → -S*(O-1) ; perde → +S
//   Commissione (5%) SOLO sulle vincite NETTE di mercato (netWin).
//
// LATO/LADDER: per PUNTARE (back) consumi `ladder.back` (quota >= target);
//              per BANCARE (lay) consumi `ladder.lay` (quota <= target).
//
// STORICO PREZZI: i detector che servono momentum/decadimento/evento accettano
// dal FACTORY un array `history: Snapshot[]` cronologico e STRETTAMENTE
// PRECEDENTE allo snapshot corrente (l'ultimo elemento è il più recente).
// I detector senza storico (layTheDrawWithInsurance, layTheFieldCorrectScore)
// lavorano sul singolo snapshot.
// ============================================================================
import type {
    Detector, Opportunity, OppConfig, Snapshot, MarketLite, MarketState, SelLite, Leg,
} from './types';
import { matchedStake, fillRatio, netWin } from './fill';
import {
    bestBack, bestLay, ltp,
    isMatchOdds, isOverUnder, isCorrectScore, isOver,
    matchOddsTriple, selectionMatchesScore,
} from './helpers';

// ----------------------------------------------------------------- costanti
// Spike tipico della quota del pareggio/scorer quando arriva un gol (per stima
// del costo di hedge "stop-loss su gol" del back-to-decay).
export const GOAL_SPIKE_FACTOR = 1.6;
// Frazione di overshoot che ci si attende rientri (mean reversion post-evento).
export const DEFAULT_REVERT_FRAC = 0.4;
// Movimento minimo (frazione) della quota per qualificare un "overshoot".
export const DEFAULT_OVERSHOOT = 0.20;
// Quota lay minima per considerare un correct-score "improbabile" (dutch-lay).
export const DEFAULT_MIN_LAY_PRICE = 11;
// Decadimento minimo (in quota assoluta) per qualificare il time-decay/momentum.
export const DEFAULT_MIN_DECAY = 0.02;

// -------------------------------------------------------------- utility math
export function clamp(x: number, lo: number, hi: number): number {
    return Math.max(lo, Math.min(hi, x));
}
function r6(x: number): number {
    return Math.round(x * 1e6) / 1e6;
}

export function phaseFromMinute(m: number | null): 'pre' | '1T' | '2T' | 'late' {
    if (m == null || m < 1) return 'pre';
    if (m <= 45) return '1T';
    if (m <= 75) return '2T';
    return 'late';
}

/**
 * backLayLock — green-up "PUNTA poi BANCA" (back-then-lay) a profitto uguale.
 * Back stake S @ B, poi LAY stake `layStake = S*B/L` @ L:
 *   profitto LORDO uguale su entrambi gli esiti = S*(B-L)/L
 *   (positivo se B > L → quota di back più alta della quota di lay = la quota CALA).
 * `profit` = netWin(gross) (commissione sul mercato solo se gross > 0).
 * Richiede B>1, L>1, S>0; altrimenti gross = 0.
 */
export function backLayLock(
    backStake: number, B: number, L: number, commission: number,
): { layStake: number; gross: number; profit: number } {
    if (!(backStake > 0) || !(B > 1) || !(L > 1)) return { layStake: 0, gross: 0, profit: 0 };
    const layStake = (backStake * B) / L;
    const gross = (backStake * (B - L)) / L;
    return { layStake: r6(layStake), gross: r6(gross), profit: r6(netWin(gross, commission)) };
}

/**
 * layThenBackLock — green-up "BANCA poi PUNTA" (lay-then-back) a profitto uguale.
 * Lay stake S @ L, poi BACK stake `backStake = S*L/B` @ B:
 *   profitto LORDO uguale = S*(B-L)/B  (positivo se B > L → la quota SALE).
 */
export function layThenBackLock(
    layStake: number, L: number, B: number, commission: number,
): { backStake: number; gross: number; profit: number } {
    if (!(layStake > 0) || !(B > 1) || !(L > 1)) return { backStake: 0, gross: 0, profit: 0 };
    const backStake = (layStake * L) / B;
    const gross = (layStake * (B - L)) / B;
    return { backStake: r6(backStake), gross: r6(gross), profit: r6(netWin(gross, commission)) };
}

/**
 * ltdInsurance — struttura "BANCA il pareggio + PUNTA lo 0-0 (assicurazione)".
 * Sd = stake (backer) della LAY sul pareggio @ Dl ; lo 0-0 viene PUNTATO @ Zb
 * con stake `sz` dimensionato per AZZERARE l'esito 0-0 (break-even):
 *     sz = Sd*(Dl-1) / ((Zb-1)*(1-c))
 * Esiti (commissione per-mercato: MATCH_ODDS e CORRECT_SCORE separati):
 *   (a) 0-0           → pareggio vince, 0-0 vince  ≈ 0 (assicurato)
 *   (b) altro pareggio→ pareggio vince, 0-0 perde  = -Sd*(Dl-1) - sz   (RISCHIO residuo)
 *   (c) c'è un vincitore → pareggio perde, 0-0 perde = Sd*(1-c) - sz    (PROFITTO)
 */
export function ltdInsurance(
    layDrawStake: number, Dl: number, Zb: number, commission: number,
): { sz: number; a: number; b: number; c: number } {
    if (!(layDrawStake > 0) || !(Dl > 1) || !(Zb > 1)) return { sz: 0, a: 0, b: 0, c: 0 };
    const sz = (layDrawStake * (Dl - 1)) / ((Zb - 1) * (1 - commission));
    const a = -layDrawStake * (Dl - 1) + netWin(sz * (Zb - 1), commission);
    const b = -layDrawStake * (Dl - 1) - sz;
    const c = netWin(layDrawStake, commission) - sz;
    return { sz: r6(sz), a: r6(a), b: r6(b), c: r6(c) };
}

/**
 * dutchLayField — BANCA un insieme di correct-score improbabili a LIABILITY
 * UGUALE `liab` (Si = liab/(Oi-1)). Esiti:
 *   - "field miss" (nessuno esce): incassi Σ Si  → netWin(ΣSi, c)
 *   - esce lo score j: P&L = (ΣSi - Sj) - liab   (perdita)
 * worstLiability = il peggiore di questi (lo score con stake Sj più alto = quota
 * più bassa). Restituisce stake per selezione e i due estremi.
 */
export function dutchLayField(
    oddsLay: number[], liab: number, commission: number,
): { stakes: number[]; bestReturn: number; worstLiability: number } {
    const valid = oddsLay.filter((o) => o > 1);
    if (valid.length === 0 || !(liab > 0)) return { stakes: [], bestReturn: 0, worstLiability: 0 };
    const stakes = oddsLay.map((o) => (o > 1 ? liab / (o - 1) : 0));
    const sumS = stakes.reduce((s, x) => s + x, 0);
    const bestReturn = netWin(sumS, commission);
    let worst = 0;
    let any = false;
    for (let j = 0; j < oddsLay.length; j++) {
        if (!(oddsLay[j] > 1)) continue;
        const lossJ = (sumS - stakes[j]) - liab;
        if (!any || lossJ < worst) { worst = lossJ; any = true; }
    }
    return {
        stakes: stakes.map(r6),
        bestReturn: r6(bestReturn),
        worstLiability: r6(worst),
    };
}

// --------------------------------------------------------------- helper book
interface MV { lite: MarketLite; state: MarketState }

function marketsBy(snap: Snapshot, pred: (m: MarketLite) => boolean): MV[] {
    const out: MV[] = [];
    for (const lite of snap.markets) {
        if (!pred(lite)) continue;
        const state = snap.state[lite.market_id];
        if (!state) continue;
        out.push({ lite, state });
    }
    return out;
}

function levels(state: MarketState, selId: number, side: 'back' | 'lay'): [number, number][] | undefined {
    const e = state.ladder[String(selId)];
    return side === 'back' ? e?.back : e?.lay;
}

// Ultimo prezzo back noto di una selezione nello storico + total gol di quel frame.
function prevBack(history: Snapshot[], marketId: string, selId: number): { price: number; total: number } | null {
    for (let i = history.length - 1; i >= 0; i--) {
        const st = history[i].state[marketId];
        if (!st) continue;
        const v = bestBack(st.ladder, selId) ?? ltp(st.ladder, selId);
        if (v != null && v > 1) return { price: v, total: history[i].scoreHome + history[i].scoreAway };
    }
    return null;
}

// Ultimo snapshot dello storico con MENO gol di `currentTotal` (frame pre-gol).
function preEventSnap(history: Snapshot[], currentTotal: number): Snapshot | null {
    for (let i = history.length - 1; i >= 0; i--) {
        if (history[i].scoreHome + history[i].scoreAway < currentTotal) return history[i];
    }
    return null;
}

function selName(lite: MarketLite, selId: number): string {
    return lite.selections.find((s) => s.selection_id === selId)?.name ?? String(selId);
}

function mkLeg(
    lite: MarketLite, sel: { selection_id: number; name?: string | null },
    side: 'back' | 'lay', price: number, stake: number, matched: number,
): Leg {
    return {
        marketId: lite.market_id,
        marketName: lite.market_name ?? lite.market_type ?? lite.market_id,
        selectionId: sel.selection_id,
        selectionName: sel.name ?? selName(lite, sel.selection_id),
        side,
        price: r6(price),
        stake: r6(stake),
        matchedStake: r6(matched),
    };
}

function gbp(v: number): string {
    return `£${v.toFixed(2)}`;
}

// ============================================================================
// 1) thetaDecay — TIME-DECAY su Pareggio / 0-0 in partita senza gol.
//    In partita goalless la quota del pareggio (MATCH_ODDS) CALA col tempo:
//    PUNTI ora @B e prevedi di BANCARE più in basso @L (back-then-lay).
//    profitto ATTESO = netWin(stake*(B-L)/L). Rischio: un gol fa schizzare la
//    quota (hedge-on-goal = stop-loss). tier 'low'.
//    PROFIT FORMULA: profit = netWin( matchedBack*(B-L)/L , commission ),
//      con B = best back del pareggio ORA, L = max(1.01, B - decay),
//      decay = prezzoPrecedente(pareggio) - B (>0), partita senza gol nuovi.
// ============================================================================
export function thetaDecay(history: Snapshot[] = []): Detector {
    return (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
        const out: Opportunity[] = [];
        const currentTotal = snap.scoreHome + snap.scoreAway;
        for (const { lite, state } of marketsBy(snap, isMatchOdds)) {
            const trip = matchOddsTriple(lite.selections);
            const draw = trip.draw;
            if (!draw) continue;
            const B = bestBack(state.ladder, draw.selection_id);
            if (B == null || B <= 1) continue;
            const prev = prevBack(history, lite.market_id, draw.selection_id);
            if (!prev) continue;
            // time-decay = nessun gol nuovo dal frame precedente + quota in calo.
            if (prev.total !== currentTotal) continue;
            const decay = prev.price - B;
            if (decay < DEFAULT_MIN_DECAY) continue;
            const L = Math.max(1.01, B - decay);
            if (!(L < B)) continue;

            const matchedBack = matchedStake(levels(state, draw.selection_id, 'back'), B, cfg.stake, 'back');
            if (matchedBack <= 0) continue;
            const lock = backLayLock(matchedBack, B, L, cfg.commission);
            if (lock.profit <= 0) continue;
            const layFill = fillRatio(levels(state, draw.selection_id, 'lay'), L, lock.layStake, 'lay');
            const backFill = matchedBack / cfg.stake;
            const minFill = Math.min(backFill, Math.max(layFill, 0));
            const profitPct = r6((lock.profit / matchedBack) * 100);
            const confidence = r6(clamp(0.3 + 0.4 * minFill, 0.3, 0.8));

            // stima costo di hedge se arriva un gol (stop-loss): BANCO a B*spike.
            const G = B * GOAL_SPIKE_FACTOR;
            const hedge = backLayLock(matchedBack, B, G, cfg.commission); // gross negativo

            out.push({
                id: `theta_decay:${lite.market_id}:${draw.selection_id}:${snap.ts}`,
                tier: 'low',
                type: 'theta_decay',
                title: 'Time-decay sul Pareggio (partita senza gol)',
                instruction: `PUNTA il Pareggio ${gbp(matchedBack)} @${B} ora; appena la quota cala BANCA `
                    + `${gbp(lock.layStake)} @${L} → profitto atteso ${gbp(lock.profit)}.`,
                legs: [
                    mkLeg(lite, draw, 'back', B, matchedBack, matchedBack),
                    mkLeg(lite, draw, 'lay', L, lock.layStake,
                        matchedStake(levels(state, draw.selection_id, 'lay'), L, lock.layStake, 'lay')),
                ],
                profit: lock.profit,
                profitPct,
                confidence,
                explanation: `Quota Pareggio scesa da ${prev.price} a ${B} senza gol: decadimento temporale `
                    + `${decay.toFixed(2)}. Profitto NON garantito: dipende dal completamento del calo.`,
                phase: phaseFromMinute(snap.minute),
                exitPlan: `Chiudi BANCANDO @${L}. STOP se arriva un gol: la quota schizza (~${G.toFixed(2)}), `
                    + `costo di hedge ~${gbp(hedge.gross)}.`,
            });
        }
        return out;
    };
}

// ============================================================================
// 2) layTheDrawWithInsurance — BANCA il Pareggio + PUNTA lo 0-0 (assicurazione).
//    Struttura BLOCCATA: l'esito 0-0 è coperto (≈break-even), un vincitore dà
//    profitto, SOLO un pareggio diverso da 0-0 (1-1, 2-2…) è in perdita.
//    tier 'low'. PROFIT = ltdInsurance.c (esito "c'è un vincitore", netto comm).
//    profitPct = c / |b| * 100 ; confidence = clamp(1 - pOther, 0.5, 0.95),
//    pOther = max(0, 1/Dl - 1/Zb) (prob. stimata di pareggio ≠ 0-0).
// ============================================================================
export function layTheDrawWithInsurance(): Detector {
    return (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
        const out: Opportunity[] = [];
        const moMarkets = marketsBy(snap, isMatchOdds);
        const csMarkets = marketsBy(snap, isCorrectScore);
        if (moMarkets.length === 0 || csMarkets.length === 0) return out;
        const cs = csMarkets[0];
        const zero = cs.lite.selections.find((s) => selectionMatchesScore(s, 0, 0));
        if (!zero) return out;
        const Zb = bestBack(cs.state.ladder, zero.selection_id);
        if (Zb == null || Zb <= 1) return out;

        for (const mo of moMarkets) {
            const draw = matchOddsTriple(mo.lite.selections).draw;
            if (!draw) continue;
            const Dl = bestLay(mo.state.ladder, draw.selection_id);
            if (Dl == null || Dl <= 1) continue;

            const Sd = matchedStake(levels(mo.state, draw.selection_id, 'lay'), Dl, cfg.stake, 'lay');
            if (Sd <= 0) continue;
            const ins = ltdInsurance(Sd, Dl, Zb, cfg.commission);
            if (ins.c <= 0) continue; // non conviene: lo 0-0 costa più del guadagno
            const szMatched = matchedStake(levels(cs.state, zero.selection_id, 'back'), Zb, ins.sz, 'back');
            if (szMatched <= 0) continue;

            const maxLoss = -ins.b; // perdita su pareggio ≠ 0-0
            const profitPct = r6((ins.c / maxLoss) * 100);
            const pOther = Math.max(0, 1 / Dl - 1 / Zb);
            const confidence = r6(clamp(1 - pOther, 0.5, 0.95));

            out.push({
                id: `ltd_insurance:${mo.lite.market_id}:${cs.lite.market_id}:${snap.ts}`,
                tier: 'low',
                type: 'ltd_insurance',
                title: 'Lay-the-Draw con assicurazione 0-0',
                instruction: `BANCA il Pareggio ${gbp(Sd)} @${Dl} e PUNTA lo 0-0 ${gbp(ins.sz)} @${Zb} `
                    + `→ profitto ${gbp(ins.c)} se esce un vincitore, 0-0 coperto.`,
                legs: [
                    mkLeg(mo.lite, draw, 'lay', Dl, Sd, Sd),
                    mkLeg(cs.lite, zero, 'back', Zb, ins.sz, szMatched),
                ],
                profit: ins.c,
                profitPct,
                confidence,
                explanation: `Esito 0-0 assicurato (≈${gbp(ins.a)}); un vincitore → ${gbp(ins.c)}. `
                    + `RISCHIO residuo: un pareggio diverso da 0-0 (1-1, 2-2…) → ${gbp(ins.b)}.`,
                phase: phaseFromMinute(snap.minute),
                exitPlan: `Se arriva il 1° gol, valuta di chiudere il lay sul pareggio in profitto. `
                    + `Perdita massima ${gbp(ins.b)} solo su pareggio ≠ 0-0.`,
            });
        }
        return out;
    };
}

// ============================================================================
// 3) layTheFieldCorrectScore — DUTCH-LAY dei correct-score improbabili.
//    BANCA gli score con quota lay >= minLayPrice a LIABILITY uguale (`liab`).
//    Incassi Σ Si se NESSUNO esce; perdi (ΣSi - Sj) - liab se esce lo score j.
//    tier 'low'. PROFIT = netWin(ΣSi) (field miss). profitPct = profit/|worst|*100.
//    confidence = clamp(1 - Σ(1/Oi), 0.5, 0.97) (prob. che il field non esca).
// ============================================================================
export function layTheFieldCorrectScore(opts?: { minLayPrice?: number }): Detector {
    const minLay = opts?.minLayPrice ?? DEFAULT_MIN_LAY_PRICE;
    return (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
        const out: Opportunity[] = [];
        for (const { lite, state } of marketsBy(snap, isCorrectScore)) {
            const picks: { sel: SelLite; Ol: number }[] = [];
            for (const sel of lite.selections) {
                if (!sel.name) continue;
                const Ol = bestLay(state.ladder, sel.selection_id);
                if (Ol == null || Ol < minLay) continue;
                picks.push({ sel, Ol });
            }
            if (picks.length < 2) continue;

            const liab = cfg.stake;
            const dl = dutchLayField(picks.map((p) => p.Ol), liab, cfg.commission);
            if (dl.bestReturn <= 0 || dl.worstLiability >= 0) continue;

            // FIX certificazione (MEDIUM): il profitto/worst NON vanno calcolati sugli
            // stake DESIDERATI ma su quelli REALMENTE abbinabili (matched). Con
            // liquidità sottile su una selezione, il return crolla: si ricalcola
            // bestReturn/worstLiability dagli stake effettivi (Si_eff = matched).
            const eff = picks.map((p, i) => ({
                p,
                stake: dl.stakes[i],
                matched: matchedStake(levels(state, p.sel.selection_id, 'lay'), p.Ol, dl.stakes[i], 'lay'),
            }));
            const sumEff = eff.reduce((s, x) => s + x.matched, 0);
            const bestReturn = r6(netWin(sumEff, cfg.commission));
            let worst = 0;
            let anyWorst = false;
            for (const x of eff) {
                if (!(x.matched > 0)) continue;
                // esce lo score x: incassi gli altri stake, paghi la liability di x.
                const grossJ = (sumEff - x.matched) - x.matched * (x.p.Ol - 1);
                if (!anyWorst || grossJ < worst) { worst = grossJ; anyWorst = true; }
            }
            worst = r6(worst);
            if (bestReturn <= 0 || worst >= 0) continue;

            const legs: Leg[] = eff.map((x) => mkLeg(lite, x.p.sel, 'lay', x.p.Ol, x.stake, x.matched));

            const sumImplied = picks.reduce((s, p) => s + 1 / p.Ol, 0);
            const confidence = r6(clamp(1 - sumImplied, 0.5, 0.97));
            const profitPct = r6((bestReturn / (-worst)) * 100);
            const list = picks.map((p) => `${p.sel.name}@${p.Ol}`).join(', ');

            out.push({
                id: `lay_field_cs:${lite.market_id}:${snap.ts}`,
                tier: 'low',
                type: 'lay_field_cs',
                title: 'Dutch-lay correct-score improbabili',
                instruction: `BANCA i risultati improbabili (${list}) a liability ${gbp(liab)} ciascuno `
                    + `→ incassi ${gbp(bestReturn)} se non escono.`,
                legs,
                profit: bestReturn,
                profitPct,
                confidence,
                explanation: `${picks.length} score improbabili bancati (stake effettivi al netto della liquidità). `
                    + `Prob. stimata che NESSUNO esca ≈ ${((1 - sumImplied) * 100).toFixed(1)}%. RISCHIO: se ne esce uno perdi fino a `
                    + `${gbp(worst)}.`,
                phase: phaseFromMinute(snap.minute),
                exitPlan: `Se uno degli score bancati diventa probabile (gol che avvicina), chiudi BANCANDO `
                    + `lo scenario o PUNTANDO lo score per ridurre la liability. Max perdita ${gbp(worst)}.`,
            });
        }
        return out;
    };
}

// ============================================================================
// 4) backToLay — PUNTA poi BANCA.
//    (A) BOOK INCROCIATO (raro): best back > best lay sulla STESSA selezione →
//        lock IMMEDIATO garantito. tier 'arb'. profit = netWin(stake*(B-L)/L).
//    (B) MOMENTUM: favorita (MATCH_ODDS) / Over (OVER_UNDER) con quota in calo
//        nello storico → PUNTA ora, prevedi di BANCARE più in basso. tier 'low'.
//        Lock ATTESO (NON garantito). PROFIT (B) = netWin(matchedBack*(B-L)/L)
//        con L = max(1.01, 2*B - prevBack) (estrapolazione del calo).
// ============================================================================
export function backToLay(history: Snapshot[] = []): Detector {
    return (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
        const out: Opportunity[] = [];
        const candidates = marketsBy(snap, (m) => isMatchOdds(m) || isOverUnder(m));

        for (const { lite, state } of candidates) {
            // selezioni candidate: TUTTE le selezioni quotate del mercato. Un book
            // incrociato è un arbitraggio su QUALSIASI selezione (anche Pareggio /
            // Under), non solo favorita / Over — la certificazione ha segnalato la
            // perdita di arbitraggi reali su Draw/Under quando si filtravano via.
            // Per il MOMENTUM (B) restano candidate solo non-draw MO + Over O/U
            // (un calo direzionale ha senso lì), gestito col flag `momentumOk`.
            let sels: SelLite[];
            let momentumSels: Set<number>;
            if (isMatchOdds(lite)) {
                const t = matchOddsTriple(lite.selections);
                sels = lite.selections;
                momentumSels = new Set([t.home, t.away].filter((s): s is SelLite => !!s).map((s) => s.selection_id));
            } else {
                sels = lite.selections;
                momentumSels = new Set(lite.selections.filter((s) => isOver(s.name)).map((s) => s.selection_id));
            }

            for (const sel of sels) {
                const B = bestBack(state.ladder, sel.selection_id);
                const Lnow = bestLay(state.ladder, sel.selection_id);
                if (B == null || B <= 1) continue;

                // (A) book incrociato → arbitraggio immediato.
                if (Lnow != null && Lnow > 1 && B > Lnow + 1e-9) {
                    const matchedBack = matchedStake(levels(state, sel.selection_id, 'back'), B, cfg.stake, 'back');
                    if (matchedBack <= 0) continue;
                    // FIX certificazione (HIGH): un lock richiede ENTRAMBE le gambe
                    // riempite. La size bloccabile è vincolata anche dalla liquidità
                    // di LAY: layStake = backUsable*B/L ≤ matchedLay
                    //   ⇒ backUsable = min(matchedBack, matchedLay*L/B).
                    // Si dimensiona il profitto sulla size REALMENTE bloccabile, non
                    // sul back-stake intero (che lascerebbe il residuo non coperto).
                    const desiredLay = (matchedBack * B) / Lnow;
                    const matchedLay = matchedStake(levels(state, sel.selection_id, 'lay'), Lnow, desiredLay, 'lay');
                    if (matchedLay <= 0) continue;
                    const backUsable = Math.min(matchedBack, (matchedLay * Lnow) / B);
                    if (!(backUsable > 0)) continue;
                    const lock = backLayLock(backUsable, B, Lnow, cfg.commission);
                    if (lock.profit <= 0) continue;
                    // confidence = frazione dello stake desiderato realmente bloccabile.
                    const usableFill = clamp(backUsable / cfg.stake, 0, 1);
                    out.push({
                        id: `back_to_lay_arb:${lite.market_id}:${sel.selection_id}:${snap.ts}`,
                        tier: 'arb',
                        type: 'back_to_lay_arb',
                        title: 'Book incrociato: lock immediato PUNTA/BANCA',
                        instruction: `ARBITRAGGIO: PUNTA ${sel.name} ${gbp(backUsable)} @${B} e BANCA `
                            + `${gbp(lock.layStake)} @${Lnow} → profitto bloccato ${gbp(lock.profit)} qualunque esito.`,
                        legs: [
                            mkLeg(lite, sel, 'back', B, backUsable, backUsable),
                            mkLeg(lite, sel, 'lay', Lnow, lock.layStake, lock.layStake),
                        ],
                        profit: lock.profit,
                        profitPct: r6((lock.profit / backUsable) * 100),
                        confidence: r6(usableFill),
                        explanation: `Best back ${B} > best lay ${Lnow}: book incrociato. Size bloccabile `
                            + `limitata dalla liquidità di lay → ${gbp(backUsable)} con profitto ${gbp(lock.profit)} `
                            + `su entrambi gli esiti (netto commissione).`,
                        phase: phaseFromMinute(snap.minute),
                    });
                    continue;
                }

                // (B) momentum: solo selezioni "direzionali" (favorita MO / Over O/U),
                // quota in calo nello storico.
                if (!momentumSels.has(sel.selection_id)) continue;
                const prev = prevBack(history, lite.market_id, sel.selection_id);
                if (!prev) continue;
                const decay = prev.price - B;
                if (decay < DEFAULT_MIN_DECAY) continue;
                const L = Math.max(1.01, 2 * B - prev.price); // estrapola un altro passo di calo
                if (!(L < B) || L <= 1) continue;
                const matchedBack = matchedStake(levels(state, sel.selection_id, 'back'), B, cfg.stake, 'back');
                if (matchedBack <= 0) continue;
                const lock = backLayLock(matchedBack, B, L, cfg.commission);
                if (lock.profit <= 0) continue;
                const layFill = fillRatio(levels(state, sel.selection_id, 'lay'), L, lock.layStake, 'lay');
                const minFill = Math.min(matchedBack / cfg.stake, Math.max(layFill, 0));
                const confidence = r6(clamp(0.3 + 0.3 * minFill, 0.3, 0.7));

                out.push({
                    id: `back_to_lay:${lite.market_id}:${sel.selection_id}:${snap.ts}`,
                    tier: 'low',
                    type: 'back_to_lay',
                    title: 'Back-to-Lay su momentum (quota in calo)',
                    instruction: `PUNTA ${sel.name} ${gbp(matchedBack)} @${B} ora; quando la quota cala BANCA `
                        + `${gbp(lock.layStake)} @${L} → profitto atteso ${gbp(lock.profit)}.`,
                    legs: [
                        mkLeg(lite, sel, 'back', B, matchedBack, matchedBack),
                        mkLeg(lite, sel, 'lay', L, lock.layStake,
                            matchedStake(levels(state, sel.selection_id, 'lay'), L, lock.layStake, 'lay')),
                    ],
                    profit: lock.profit,
                    profitPct: r6((lock.profit / matchedBack) * 100),
                    confidence,
                    explanation: `Quota ${sel.name} scesa da ${prev.price} a ${B} (momentum ${decay.toFixed(2)}). `
                        + `Lock NON garantito: dipende dal proseguire del calo fino a @${L}.`,
                    phase: phaseFromMinute(snap.minute),
                    exitPlan: `Chiudi BANCANDO @${L}. STOP se la quota inverte e risale sopra ${B}.`,
                });
            }
        }
        return out;
    };
}

// ============================================================================
// 5) meanReversionPostEvent — FADE dell'overreaction post-gol.
//    Dopo un gol la quota della squadra che segna CROLLA, spesso troppo
//    (overshoot). Si BANCA ora la marcatrice prevedendo un rientro della quota
//    (lay-then-back: BANCA basso ora, PUNTA più alto dopo). tier 'directional'.
//    target Bexit = curOdds + revertFrac*(preOdds - curOdds). PROFIT =
//    netWin(layStake*(Bexit - Lnow)/Bexit) con Lnow = best lay ORA.
//    NB: i cartellini NON sono nello schema Snapshot → si rileva solo il gol
//    (delta punteggio). Stop-loss se la quota continua a scendere.
// ============================================================================
export function meanReversionPostEvent(history: Snapshot[] = []): Detector {
    return (snap: Snapshot, cfg: OppConfig): Opportunity[] => {
        const out: Opportunity[] = [];
        const currentTotal = snap.scoreHome + snap.scoreAway;
        const pre = preEventSnap(history, currentTotal);
        if (!pre) return out;
        const homeScored = snap.scoreHome > pre.scoreHome;
        const awayScored = snap.scoreAway > pre.scoreAway;
        if (!homeScored && !awayScored) return out;

        for (const { lite, state } of marketsBy(snap, isMatchOdds)) {
            const trip = matchOddsTriple(lite.selections);
            const scorer = homeScored ? trip.home : trip.away;
            if (!scorer) continue;
            const preOdds = bestBack(pre.state[lite.market_id]?.ladder ?? {}, scorer.selection_id)
                ?? ltp(pre.state[lite.market_id]?.ladder ?? {}, scorer.selection_id);
            const curOdds = bestBack(state.ladder, scorer.selection_id);
            const Lnow = bestLay(state.ladder, scorer.selection_id);
            if (preOdds == null || preOdds <= 1) continue;
            if (curOdds == null || curOdds <= 1) continue;
            if (Lnow == null || Lnow <= 1) continue;

            const move = (curOdds - preOdds) / preOdds; // negativo = quota crollata
            if (move > -DEFAULT_OVERSHOOT) continue; // overshoot verso il basso insufficiente
            const overshootFrac = Math.abs(move);

            const Bexit = curOdds + DEFAULT_REVERT_FRAC * (preOdds - curOdds);
            if (!(Bexit > Lnow)) continue; // serve rientro sopra la quota di lay attuale

            const layMatched = matchedStake(levels(state, scorer.selection_id, 'lay'), Lnow, cfg.stake, 'lay');
            if (layMatched <= 0) continue;
            const lock = layThenBackLock(layMatched, Lnow, Bexit, cfg.commission);
            if (lock.profit <= 0) continue;

            const confidence = r6(clamp(0.2 + overshootFrac, 0.2, 0.6));
            const profitPct = r6((lock.profit / layMatched) * 100);

            out.push({
                id: `mean_reversion:${lite.market_id}:${scorer.selection_id}:${snap.ts}`,
                tier: 'directional',
                type: 'mean_reversion',
                title: 'Mean-reversion post-gol (fade overreaction)',
                instruction: `BANCA ${scorer.name} ${gbp(layMatched)} @${Lnow} (reazione eccessiva al gol), `
                    + `obiettivo PUNTARE @${r6(Bexit)} → profitto atteso ${gbp(lock.profit)}.`,
                legs: [
                    mkLeg(lite, scorer, 'lay', Lnow, layMatched, layMatched),
                    mkLeg(lite, scorer, 'back', r6(Bexit), lock.backStake,
                        matchedStake(levels(state, scorer.selection_id, 'back'), Bexit, lock.backStake, 'back')),
                ],
                profit: lock.profit,
                profitPct,
                confidence,
                explanation: `Quota ${scorer.name} crollata da ${preOdds} a ${curOdds} (${(move * 100).toFixed(1)}%) `
                    + `dopo il gol: overshoot. Si stima un rientro al ${(DEFAULT_REVERT_FRAC * 100).toFixed(0)}% `
                    + `(→ ${r6(Bexit)}). RISCHIO direzionale: la quota può continuare a scendere.`,
                phase: phaseFromMinute(snap.minute),
                exitPlan: `Chiudi PUNTANDO @${r6(Bexit)}. STOP se la quota scende sotto ${r6(curOdds * 0.9)} `
                    + `(il calo prosegue, niente reversion).`,
            });
        }
        return out;
    };
}

// Comodo factory: tutti i detector Tier 1 con lo stesso storico.
export function tier1Detectors(history: Snapshot[] = []): Detector[] {
    return [
        thetaDecay(history),
        layTheDrawWithInsurance(),
        layTheFieldCorrectScore(),
        backToLay(history),
        meanReversionPostEvent(history),
    ];
}
