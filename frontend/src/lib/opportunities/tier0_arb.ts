// ============================================================================
// tier0_arb.ts — DETECTOR di ARBITRAGGIO PURO (Tier 0, risk-free).
//
// Un arbitraggio Tier-0 è un insieme di bet che copre TUTTI gli esiti possibili
// con profitto GARANTITO in OGNI esito, al NETTO della commissione Betfair (5%).
//
// MODELLO DI CALCOLO (money-critical, esatto):
//   Tutti i profitti sono calcolati con un MOTORE A SCENARI:
//     - si enumerano gli scenari mutuamente esclusivi ed esaustivi (es. esito
//       1X2, oppure ogni Correct Score, oppure le fasce di gol totali);
//     - per OGNI scenario, per OGNI mercato coinvolto, si sommano i payoff lordi
//       delle gambe (back/lay) in quel mercato e si applica la commissione SOLO
//       sul NETTO POSITIVO di quel mercato (netWin);
//     - il profitto garantito = MIN del profitto sugli scenari.
//   Questo riflette ESATTAMENTE la semantica Betfair: la commissione è prelevata
//   per-mercato sulle vincite NETTE di mercato, non per singola scommessa.
//
//   Semantica P&L (da replay-pnl.ts):
//     BACK stake S @ O:  selezione vince → +S*(O-1) ; perde → -S
//     LAY  stake S @ O:  selezione vince → -S*(O-1) ; perde → +S
//
//   FILL REALISTICO: ogni gamba usa matchedStake (fill.ts) → lo stake riportato
//   e il profitto sono calcolati sulla liquidità DAVVERO disponibile ai prezzi
//   correnti (no fill teorico). Se la liquidità è sottile il profitto scende e
//   l'opportunità può non scattare.
//
//   ALLOCAZIONE STAKE: dutching ∝ 1/quota (return lordo uguale su ogni esito);
//   per le coperture back+lay si calcola lo stake di lay in forma CHIUSA che
//   pareggia il profitto tra i due gruppi di scenari.
// ============================================================================
import type { Detector, Leg, MarketLite, MarketState, Opportunity, OppConfig, RiskTier, SelLite, Snapshot } from './types';
import { matchedStake } from './fill';
import {
    backPnl,
    layPnl,
    bestBack,
    bestLay,
    isMatchOdds,
    isCorrectScore,
    isBtts,
    isOverUnder,
    matchOddsTriple,
    lineFromType,
    isYes,
    isNo,
    isOver,
    isUnder,
} from './helpers';
import { netWin } from './fill';

// Soglia anti-rumore numerico sui profitti (£).
const PROFIT_EPS = 1e-9;

// ---------------------------------------------------------------------------
// MOTORE A SCENARI
// ---------------------------------------------------------------------------

// Uno scenario = chiave leggibile + insieme delle selection_id VINCENTI
// (su tutti i mercati coinvolti) in quell'esito.
export interface Scenario {
    key: string;
    winners: Set<number>;
}

// Profitto NETTO (£) di un set di gambe in UNO scenario.
// Raggruppa per mercato, somma i payoff lordi, applica commissione sul netto
// positivo del mercato (netWin), somma i mercati.
export function scenarioProfit(legs: Leg[], winners: Set<number>, commission: number): number {
    const byMarket = new Map<string, number>();
    for (const l of legs) {
        const win = winners.has(l.selectionId);
        const gross = l.side === 'back'
            ? backPnl(l.matchedStake, l.price, win)
            : layPnl(l.matchedStake, l.price, win);
        byMarket.set(l.marketId, (byMarket.get(l.marketId) ?? 0) + gross);
    }
    let total = 0;
    for (const net of byMarket.values()) total += netWin(net, commission);
    return total;
}

// Profitto GARANTITO (£) = minimo del profitto su tutti gli scenari.
export function guaranteedProfit(legs: Leg[], scenarios: Scenario[], commission: number): number {
    if (scenarios.length === 0) return 0;
    let min = Infinity;
    for (const s of scenarios) {
        const p = scenarioProfit(legs, s.winners, commission);
        if (p < min) min = p;
    }
    return Number.isFinite(min) ? min : 0;
}

// ---------------------------------------------------------------------------
// ALLOCAZIONE STAKE
// ---------------------------------------------------------------------------

// Dutching ∝ 1/quota: distribuisce `total` sugli esiti per RETURN LORDO uguale.
// stake_i = total * (1/o_i) / Σ(1/o). Il return lordo costante = total/Σ(1/o).
export function dutchStakes(odds: number[], total: number): number[] {
    const inv = odds.map((o) => (o > 0 ? 1 / o : 0));
    const sum = inv.reduce((a, b) => a + b, 0);
    if (sum <= 0) return odds.map(() => 0);
    return inv.map((x) => (total * x) / sum);
}

// Quota sintetica di un gruppo backato in dutch: 1/Σ(1/o). È la quota "back"
// effettiva per l'evento composto (es. "entrambe segnano" via Correct Score).
export function syntheticBackOdds(odds: number[]): number | null {
    const inv = odds.map((o) => (o > 0 ? 1 / o : 0));
    const sum = inv.reduce((a, b) => a + b, 0);
    return sum > 0 ? 1 / sum : null;
}

// Stake di LAY (stake del backer) che PAREGGIA il profitto tra lo scenario in
// cui l'evento backato si verifica e quello in cui non si verifica, data una
// copertura BACK @backOdds con backStake e un LAY @layOdds.
//
// win-side (evento accade):   netWin(backStake*(backOdds-1), c) - layStake*(layOdds-1)
// lose-side (evento NON accade): -backStake + netWin(layStake, c)
// Eguagliando (entrambi i netWin sono su importi positivi):
//   backStake*(backOdds-1)*(1-c) + backStake = layStake*(layOdds - c)
//   layStake = backStake*((backOdds-1)*(1-c) + 1) / (layOdds - c)
export function hedgeLayStake(backOdds: number, layOdds: number, backStake: number, commission: number): number {
    const denom = layOdds - commission;
    if (denom <= 0) return 0;
    return (backStake * ((backOdds - 1) * (1 - commission) + 1)) / denom;
}

// ---------------------------------------------------------------------------
// PARSING SELEZIONI specifiche di Tier-0
// ---------------------------------------------------------------------------

// "2-1" / "2 - 1" → [2,1] ; null se non è un punteggio.
export function parseScore(name: string | null): [number, number] | null {
    if (!name) return null;
    const c = name.replace(/\s/g, '');
    const m = /^(\d+)-(\d+)$/.exec(c);
    if (!m) return null;
    return [Number(m[1]), Number(m[2])];
}

// Tipo di Doppia Chance dal nome selezione (convenzione codebase: 1X/X2/12;
// 1X = Casa o Pari, X2 = Pari o Trasferta, 12 = Casa o Trasferta).
export function doubleChanceKind(name: string | null): '1X' | 'X2' | '12' | null {
    if (!name) return null;
    const c = name.trim().toLowerCase();
    if (/^1\s*x$/.test(c)) return '1X';
    if (/^x\s*2$/.test(c)) return 'X2';
    if (/^1\s*2$/.test(c)) return '12';
    const draw = /draw|pareggio/.test(c);
    const home = /home|casa/.test(c);
    const away = /away|trasf|ospite/.test(c);
    if (draw && home && !away) return '1X';
    if (draw && away && !home) return 'X2';
    if (home && away && !draw) return '12';
    return null;
}

// La Doppia Chance `kind` copre l'esito 1X2 `o`?
function dcCovers(kind: '1X' | 'X2' | '12', o: 'home' | 'draw' | 'away'): boolean {
    if (kind === '1X') return o === 'home' || o === 'draw';
    if (kind === 'X2') return o === 'draw' || o === 'away';
    return o === 'home' || o === 'away'; // '12'
}

export function isDoubleChance(m: { market_type: string | null }): boolean {
    return (m.market_type || '').toUpperCase() === 'DOUBLE_CHANCE';
}

// ---------------------------------------------------------------------------
// UTILITY su mercati/snapshot/leg
// ---------------------------------------------------------------------------

function stateOf(snap: Snapshot, marketId: string): MarketState | undefined {
    return snap.state[marketId];
}

function levelsOf(st: MarketState, selId: number, side: 'back' | 'lay'): ReadonlyArray<readonly [number, number]> | undefined {
    const e = st.ladder?.[String(selId)];
    return side === 'back' ? e?.back : e?.lay;
}

// Costruisce una gamba con matchedStake realistico.
function makeLeg(
    meta: MarketLite,
    st: MarketState,
    sel: SelLite,
    side: 'back' | 'lay',
    price: number,
    desired: number,
): Leg {
    const matched = matchedStake(levelsOf(st, sel.selection_id, side), price, desired, side);
    return {
        marketId: meta.market_id,
        marketName: meta.market_name ?? meta.market_id,
        selectionId: sel.selection_id,
        selectionName: sel.name ?? String(sel.selection_id),
        side,
        price,
        stake: desired,
        matchedStake: matched,
    };
}

// Fase di gioco dal minuto.
export function phaseFromMinute(minute: number | null): string {
    if (minute == null || minute <= 0) return 'pre';
    if (minute <= 45) return '1T';
    if (minute <= 75) return '2T';
    return 'late';
}

const GBP = (v: number) => `£${v.toFixed(2)}`;
const ODDS = (v: number) => v.toFixed(2);

// Frase italiana per una gamba: PUNTA (back) / BANCA (lay).
function legPhrase(l: Leg): string {
    const verb = l.side === 'back' ? 'PUNTA' : 'BANCA';
    return `${verb} ${l.selectionName} ${GBP(l.matchedStake)} @${ODDS(l.price)}`;
}

// Assembla un'Opportunity arb dai pezzi calcolati. Ritorna null se non c'è
// profitto garantito o esposizione valida.
//
// `tier` (default 'arb'): per i detector la cui "garanzia" dipende dalla
// COMPLETEZZA della griglia (CS×BTTS, CS×O/U — la certificazione adversarial ha
// dimostrato che un esito FUORI griglia produce una perdita reale non enumerata)
// si passa `tier:'low'` + `riskNote`. In quel caso l'istruzione NON promette
// "profitto garantito qualunque esito" e la confidence è smorzata: l'opportunità
// è onesta sul rischio residuo "punteggio fuori dalla griglia quotata".
function assembleArb(args: {
    type: string;
    title: string;
    explanation: string;
    phase: string;
    legs: Leg[];
    scenarios: Scenario[];
    cfg: OppConfig;
    idSuffix: string;
    tier?: RiskTier;
    riskNote?: string;
    exitPlan?: string;
}): Opportunity | null {
    const { type, title, explanation, phase, legs, scenarios, cfg, idSuffix, riskNote, exitPlan } = args;
    const tier: RiskTier = args.tier ?? 'arb';
    if (legs.some((l) => l.matchedStake <= 0)) return null;

    const profit = guaranteedProfit(legs, scenarios, cfg.commission);
    if (!(profit > PROFIT_EPS)) return null;

    // Esposizione = capitale impegnato (back: stake ; lay: liability=stake*(o-1)).
    const exposure = legs.reduce(
        (s, l) => s + (l.side === 'back' ? l.matchedStake : l.matchedStake * (l.price - 1)),
        0,
    );
    if (!(exposure > 0)) return null;
    const profitPct = (profit / exposure) * 100;

    // Confidence = frazione minima di fill (liquidità sufficiente?).
    let conf = 1;
    for (const l of legs) {
        const r = l.stake > 0 ? l.matchedStake / l.stake : 0;
        if (r < conf) conf = r;
    }
    conf = Math.max(0, Math.min(1, conf));
    // Tier non-arb: la "garanzia" è condizionata alla griglia → smorza la confidence.
    if (tier !== 'arb') conf = conf * 0.6;

    const guaranteeTxt = tier === 'arb'
        ? `profitto garantito ${GBP(profit)} qualunque esito`
        : `profitto ${GBP(profit)} se il punteggio rientra nella griglia quotata`;
    const instruction = `${legs.map(legPhrase).join(' + ')} → ${guaranteeTxt}`;

    return {
        id: `${type}:${idSuffix}`,
        tier,
        type,
        title,
        instruction,
        legs,
        profit,
        profitPct,
        confidence: conf,
        explanation: riskNote ? `${explanation} ${riskNote}` : explanation,
        phase,
        ...(exitPlan ? { exitPlan } : {}),
    };
}

// ===========================================================================
// DETECTOR 1 — Match Odds × Doppia Chance
// Coppie complementari (coprono i 3 esiti 1X2 con 2 BACK):
//   DC(1X)+MO(Away) , DC(12)+MO(Draw) , DC(X2)+MO(Home).
// Arb se 1/o1+1/o2 < 1 al netto commissione. Stake ∝ 1/o (return uguale).
// Profitto = MIN sui 3 esiti dopo commissione per-mercato.
// ===========================================================================
export const matchOddsVsDoubleChance: Detector = (snap, cfg) => {
    const out: Opportunity[] = [];
    const moMeta = snap.markets.find((m) => isMatchOdds(m));
    const dcMeta = snap.markets.find((m) => isDoubleChance(m));
    if (!moMeta || !dcMeta) return out;
    const moSt = stateOf(snap, moMeta.market_id);
    const dcSt = stateOf(snap, dcMeta.market_id);
    if (!moSt || !dcSt) return out;

    const triple = matchOddsTriple(moMeta.selections);
    const phase = phaseFromMinute(snap.minute);

    const pairings: Array<{ dcKind: '1X' | 'X2' | '12'; mo: 'home' | 'draw' | 'away' }> = [
        { dcKind: '1X', mo: 'away' },
        { dcKind: '12', mo: 'draw' },
        { dcKind: 'X2', mo: 'home' },
    ];

    for (const p of pairings) {
        const dcSel = dcMeta.selections.find((s) => doubleChanceKind(s.name) === p.dcKind);
        const moSel = triple[p.mo];
        if (!dcSel || !moSel) continue;

        const oDc = bestBack(dcSt.ladder, dcSel.selection_id);
        const oMo = bestBack(moSt.ladder, moSel.selection_id);
        if (oDc == null || oMo == null || oDc <= 1 || oMo <= 1) continue;

        // Filtro rapido overround grezzo (necessario, non sufficiente).
        if (1 / oDc + 1 / oMo >= 1) continue;

        const [sDc, sMo] = dutchStakes([oDc, oMo], cfg.stake);
        const legs: Leg[] = [
            makeLeg(dcMeta, dcSt, dcSel, 'back', oDc, sDc),
            makeLeg(moMeta, moSt, moSel, 'back', oMo, sMo),
        ];

        const scenarios: Scenario[] = (['home', 'draw', 'away'] as const).map((o) => {
            const winners = new Set<number>();
            if (dcCovers(p.dcKind, o)) winners.add(dcSel.selection_id);
            const moWin = triple[o];
            if (moWin) winners.add(moWin.selection_id);
            return { key: o, winners };
        });

        const opp = assembleArb({
            type: 'mo_vs_dc',
            title: 'Arbitraggio Match Odds × Doppia Chance',
            explanation: `Doppia Chance ${p.dcKind} @${ODDS(oDc)} + Match Odds ${moSel.name ?? ''} @${ODDS(oMo)} coprono i 3 esiti con somma probabilità implicite ${(1 / oDc + 1 / oMo).toFixed(3)} < 1.`,
            phase,
            legs,
            scenarios,
            cfg,
            idSuffix: `${p.dcKind}-${moSel.selection_id}`,
        });
        if (opp) out.push(opp);
    }
    return out;
};

// ===========================================================================
// DETECTOR 2 — Correct Score × BTTS
// Copertura: BACK (dutch) tutti i Correct Score del GRUPPO di un esito BTTS
// (Yes = entrambe ≥1 ; No = altrimenti) + BANCA (lay) la selezione BTTS
// corrispondente → hedge back-vs-lay sullo stesso evento composto.
// Richiede griglia CS COMPLETA (tutte le selezioni sono punteggi "h-a").
// ===========================================================================
export const correctScoreVsBTTS: Detector = (snap, cfg) => {
    const out: Opportunity[] = [];
    const csMeta = snap.markets.find((m) => isCorrectScore(m));
    const btMeta = snap.markets.find((m) => isBtts(m));
    if (!csMeta || !btMeta) return out;
    const csSt = stateOf(snap, csMeta.market_id);
    const btSt = stateOf(snap, btMeta.market_id);
    if (!csSt || !btSt) return out;

    // Griglia CS: tutte le selezioni con nome devono essere punteggi.
    const named = csMeta.selections.filter((s) => !!s.name);
    const scores = named.map((s) => ({ sel: s, sc: parseScore(s.name) }));
    if (scores.length === 0 || scores.some((x) => x.sc == null)) return out;

    const yesSel = btMeta.selections.find((s) => isYes(s.name));
    const noSel = btMeta.selections.find((s) => isNo(s.name));
    const phase = phaseFromMinute(snap.minute);

    // Scenari = ogni Correct Score (partizione completa). Winner: il CS stesso +
    // la selezione BTTS corretta per quel punteggio.
    const buildScenarios = (): Scenario[] =>
        scores.map(({ sel, sc }) => {
            const [h, a] = sc as [number, number];
            const both = h >= 1 && a >= 1;
            const winners = new Set<number>([sel.selection_id]);
            const bt = both ? yesSel : noSel;
            if (bt) winners.add(bt.selection_id);
            return { key: `${h}-${a}`, winners };
        });

    // Per ciascun lato BTTS: gruppo CS corrispondente + lay della selezione BTTS.
    const sides: Array<{ bt: SelLite | undefined; both: boolean; label: string }> = [
        { bt: yesSel, both: true, label: 'BTTS Sì' },
        { bt: noSel, both: false, label: 'BTTS No' },
    ];

    for (const side of sides) {
        if (!side.bt) continue;
        const group = scores.filter(({ sc }) => {
            const [h, a] = sc as [number, number];
            const both = h >= 1 && a >= 1;
            return both === side.both;
        });
        if (group.length === 0) continue;

        const groupOdds = group.map(({ sel }) => bestBack(csSt.ladder, sel.selection_id));
        if (groupOdds.some((o) => o == null || (o as number) <= 1)) continue;
        const oList = groupOdds as number[];

        const pSyn = syntheticBackOdds(oList);
        if (pSyn == null || pSyn <= 1) continue;

        const layOdds = bestLay(btSt.ladder, side.bt.selection_id);
        if (layOdds == null || layOdds <= 1) continue;

        // Quick filter: sintetica deve superare la quota di lay (back alto, lay basso).
        if (pSyn <= layOdds) continue;

        const backStake = cfg.stake;
        const layStake = hedgeLayStake(pSyn, layOdds, backStake, cfg.commission);
        if (!(layStake > 0)) continue;

        const csStakes = dutchStakes(oList, backStake);
        const legs: Leg[] = group.map(({ sel }, i) =>
            makeLeg(csMeta, csSt, sel, 'back', oList[i], csStakes[i]),
        );
        legs.push(makeLeg(btMeta, btSt, side.bt, 'lay', layOdds, layStake));

        const opp = assembleArb({
            type: 'cs_vs_btts',
            title: 'Quasi-arb Correct Score × BTTS',
            explanation: `Backando in dutch i Correct Score "${side.both ? 'entrambe segnano' : 'almeno una a secco'}" (quota sintetica @${ODDS(pSyn)}) e bancando ${side.label} @${ODDS(layOdds)} si blocca un profitto sui punteggi quotati.`,
            phase,
            legs,
            scenarios: buildScenarios(),
            cfg,
            idSuffix: `${side.both ? 'yes' : 'no'}`,
            tier: 'low',
            riskNote: 'RISCHIO RESIDUO: i Correct Score quotati NON coprono tutti i punteggi possibili. Un risultato "entrambe segnano" fuori griglia (es. 3-3, 4-1) fa perdere tutti i back CS mentre la BANCA su BTTS perde la liability → perdita reale non garantita come arbitraggio.',
            exitPlan: 'Verifica che la griglia CS includa TUTTI i punteggi rilevanti (di norma i mercati reali hanno "Any Other ..." che rende la copertura impossibile). Se manca un punteggio composito, NON trattare come profitto certo.',
        });
        if (opp) out.push(opp);
    }
    return out;
};

// ===========================================================================
// DETECTOR 3 — Correct Score × Over/Under (per linea)
// Come CS×BTTS ma il gruppo è la partizione "Over linea" (totale > linea) o
// "Under linea". Hedge: BACK (dutch) il gruppo CS + BANCA il lato O/U.
// ===========================================================================
export const correctScoreVsOverUnder: Detector = (snap, cfg) => {
    const out: Opportunity[] = [];
    const csMeta = snap.markets.find((m) => isCorrectScore(m));
    if (!csMeta) return out;
    const csSt = stateOf(snap, csMeta.market_id);
    if (!csSt) return out;

    const named = csMeta.selections.filter((s) => !!s.name);
    const scores = named.map((s) => ({ sel: s, sc: parseScore(s.name) }));
    if (scores.length === 0 || scores.some((x) => x.sc == null)) return out;

    const phase = phaseFromMinute(snap.minute);
    const ouMarkets = snap.markets.filter((m) => isOverUnder(m));

    for (const ouMeta of ouMarkets) {
        const ouSt = stateOf(snap, ouMeta.market_id);
        if (!ouSt) continue;
        const line = lineFromType((ouMeta.market_type || '').toUpperCase());
        if (line == null) continue;
        const overSel = ouMeta.selections.find((s) => isOver(s.name));
        const underSel = ouMeta.selections.find((s) => isUnder(s.name));

        // Scenari = ogni CS ; winner = il CS + il lato O/U corretto per quel totale.
        const buildScenarios = (): Scenario[] =>
            scores.map(({ sel, sc }) => {
                const [h, a] = sc as [number, number];
                const over = h + a > line;
                const winners = new Set<number>([sel.selection_id]);
                const ou = over ? overSel : underSel;
                if (ou) winners.add(ou.selection_id);
                return { key: `${h}-${a}`, winners };
            });

        const sides: Array<{ ou: SelLite | undefined; over: boolean; label: string }> = [
            { ou: overSel, over: true, label: `Over ${line}` },
            { ou: underSel, over: false, label: `Under ${line}` },
        ];

        for (const side of sides) {
            if (!side.ou) continue;
            const group = scores.filter(({ sc }) => {
                const [h, a] = sc as [number, number];
                return (h + a > line) === side.over;
            });
            if (group.length === 0) continue;

            const groupOdds = group.map(({ sel }) => bestBack(csSt.ladder, sel.selection_id));
            if (groupOdds.some((o) => o == null || (o as number) <= 1)) continue;
            const oList = groupOdds as number[];

            const pSyn = syntheticBackOdds(oList);
            if (pSyn == null || pSyn <= 1) continue;

            const layOdds = bestLay(ouSt.ladder, side.ou.selection_id);
            if (layOdds == null || layOdds <= 1) continue;
            if (pSyn <= layOdds) continue;

            const backStake = cfg.stake;
            const layStake = hedgeLayStake(pSyn, layOdds, backStake, cfg.commission);
            if (!(layStake > 0)) continue;

            const csStakes = dutchStakes(oList, backStake);
            const legs: Leg[] = group.map(({ sel }, i) =>
                makeLeg(csMeta, csSt, sel, 'back', oList[i], csStakes[i]),
            );
            legs.push(makeLeg(ouMeta, ouSt, side.ou, 'lay', layOdds, layStake));

            const opp = assembleArb({
                type: 'cs_vs_ou',
                title: 'Quasi-arb Correct Score × Over/Under',
                explanation: `Backando in dutch i Correct Score del lato "${side.label}" (sintetica @${ODDS(pSyn)}) e bancando ${side.label} @${ODDS(layOdds)} si blocca un profitto sui punteggi quotati.`,
                phase,
                legs,
                scenarios: buildScenarios(),
                cfg,
                idSuffix: `${ouMeta.market_id}-${side.over ? 'over' : 'under'}`,
                tier: 'low',
                riskNote: `RISCHIO RESIDUO: i Correct Score quotati NON coprono tutti i totali "${side.label}". Un risultato del lato giusto ma fuori griglia (es. 3-1, 2-2) fa perdere tutti i back CS mentre la BANCA su ${side.label} perde la liability → perdita reale, non un arbitraggio garantito.`,
                exitPlan: `Tratta come quasi-arb solo se la griglia CS è esaustiva sul lato "${side.label}" (di norma impossibile per "Any Other ..."). Altrimenti il profitto NON è certo.`,
            });
            if (opp) out.push(opp);
        }
    }
    return out;
};

// ===========================================================================
// DETECTOR 4 — Monotonicità Over/Under
// Per linee L1<L2 adiacenti DEVE valere P(Over L1) ≥ P(Over L2). Se il mercato
// quota P(Over L1) < P(Over L2) (cioè back-odds Over L1 > back-odds Over L2) è
// sfruttabile: BACK Over L1 + BANCA Over L2 (Over L2 ⟹ Over L1 → rischio nullo
// nella fascia intermedia). Profitto bloccato = MIN sulle fasce di gol.
// ===========================================================================
export const overUnderMonotonicity: Detector = (snap, cfg) => {
    const out: Opportunity[] = [];
    const phase = phaseFromMinute(snap.minute);

    const ou = snap.markets
        .filter((m) => isOverUnder(m))
        .map((m) => ({ meta: m, line: lineFromType((m.market_type || '').toUpperCase()) }))
        .filter((x): x is { meta: MarketLite; line: number } => x.line != null)
        .sort((a, b) => a.line - b.line);

    for (let i = 0; i + 1 < ou.length; i++) {
        const lo = ou[i];
        const hi = ou[i + 1];
        const loSt = stateOf(snap, lo.meta.market_id);
        const hiSt = stateOf(snap, hi.meta.market_id);
        if (!loSt || !hiSt) continue;

        const overLo = lo.meta.selections.find((s) => isOver(s.name));
        const underLo = lo.meta.selections.find((s) => isUnder(s.name));
        const overHi = hi.meta.selections.find((s) => isOver(s.name));
        const underHi = hi.meta.selections.find((s) => isUnder(s.name));
        if (!overLo || !underLo || !overHi || !underHi) continue;

        const backOdds = bestBack(loSt.ladder, overLo.selection_id); // BACK Over L1
        const layOdds = bestLay(hiSt.ladder, overHi.selection_id); // LAY Over L2
        if (backOdds == null || layOdds == null || backOdds <= 1 || layOdds <= 1) continue;

        // Violazione di monotonicità: P(Over L1) < P(Over L2) ⇔ backOdds L1 > L2.
        if (!(backOdds > layOdds)) continue;

        const backStake = cfg.stake;
        const layStake = hedgeLayStake(backOdds, layOdds, backStake, cfg.commission);
        if (!(layStake > 0)) continue;

        const legs: Leg[] = [
            makeLeg(lo.meta, loSt, overLo, 'back', backOdds, backStake),
            makeLeg(hi.meta, hiSt, overHi, 'lay', layOdds, layStake),
        ];

        // Scenari = totali rappresentativi: sotto L1, tra L1 e L2, sopra L2.
        const tUnder = Math.floor(lo.line); // es. 0 per linea 0.5
        const tMid = Math.ceil(lo.line); // es. 1 (Over L1 ma Under L2 se gap .5..1.5)
        const tOver = Math.ceil(hi.line); // es. 2 per linea 1.5
        const totals = Array.from(new Set([tUnder, tMid, tOver]));
        const scenarios: Scenario[] = totals.map((t) => {
            const winners = new Set<number>();
            winners.add(t > lo.line ? overLo.selection_id : underLo.selection_id);
            winners.add(t > hi.line ? overHi.selection_id : underHi.selection_id);
            return { key: `t${t}`, winners };
        });

        const opp = assembleArb({
            type: 'ou_monotonicity',
            title: 'Arbitraggio Monotonicità Over/Under',
            explanation: `Over ${lo.line} è quotato @${ODDS(backOdds)} mentre Over ${hi.line} si banca @${ODDS(layOdds)}: prob. implicita di Over ${lo.line} (più probabile) INFERIORE a Over ${hi.line}. Back Over ${lo.line} + lay Over ${hi.line} blocca il profitto.`,
            phase,
            legs,
            scenarios,
            cfg,
            idSuffix: `${lo.meta.market_id}-${hi.meta.market_id}`,
        });
        if (opp) out.push(opp);
    }
    return out;
};

// ===========================================================================
// DETECTOR 5 — Match Odds book check (overround residuo)
// BACK tutte e 3 le selezioni Match Odds: se Σ(1/o) < 1 c'è overround negativo
// (raro: lag tra exchange/matcher). Stake ∝ 1/o ; profitto = MIN sui 3 esiti.
// NB: le 3 gambe sono nello STESSO mercato → commissione sul NETTO di mercato.
// ===========================================================================
export const matchOddsBookCheck: Detector = (snap, cfg) => {
    const out: Opportunity[] = [];
    const moMeta = snap.markets.find((m) => isMatchOdds(m));
    if (!moMeta) return out;
    const moSt = stateOf(snap, moMeta.market_id);
    if (!moSt) return out;

    const triple = matchOddsTriple(moMeta.selections);
    const home = triple.home;
    const draw = triple.draw;
    const away = triple.away;
    if (!home || !draw || !away) return out;

    const oH = bestBack(moSt.ladder, home.selection_id);
    const oD = bestBack(moSt.ladder, draw.selection_id);
    const oA = bestBack(moSt.ladder, away.selection_id);
    if (oH == null || oD == null || oA == null) return out;
    if (oH <= 1 || oD <= 1 || oA <= 1) return out;
    if (1 / oH + 1 / oD + 1 / oA >= 1) return out;

    const [sH, sD, sA] = dutchStakes([oH, oD, oA], cfg.stake);
    const legs: Leg[] = [
        makeLeg(moMeta, moSt, home, 'back', oH, sH),
        makeLeg(moMeta, moSt, draw, 'back', oD, sD),
        makeLeg(moMeta, moSt, away, 'back', oA, sA),
    ];
    const scenarios: Scenario[] = [
        { key: 'home', winners: new Set([home.selection_id]) },
        { key: 'draw', winners: new Set([draw.selection_id]) },
        { key: 'away', winners: new Set([away.selection_id]) },
    ];

    const opp = assembleArb({
        type: 'mo_book',
        title: 'Arbitraggio Match Odds (overround residuo)',
        explanation: `Somma probabilità implicite back ${(1 / oH + 1 / oD + 1 / oA).toFixed(3)} < 1: backando tutti e 3 gli esiti si incassa profitto certo.`,
        phase: phaseFromMinute(snap.minute),
        legs,
        scenarios,
        cfg,
        idSuffix: moMeta.market_id,
    });
    if (opp) out.push(opp);
    return out;
};

// Tutti i detector Tier-0.
export const TIER0_DETECTORS: Detector[] = [
    matchOddsVsDoubleChance,
    correctScoreVsBTTS,
    correctScoreVsOverUnder,
    overUnderMonotonicity,
    matchOddsBookCheck,
];
