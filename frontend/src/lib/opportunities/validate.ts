// ============================================================================
// validate.ts — HARNESS DI VALIDAZIONE su dati reali (replay).
//
// validateReplay(replay, cfg):
//   1. costruisce le Snapshot (buildSnapshots) a bucket fissi;
//   2. esegue TUTTI i detector su OGNI snapshot (i factory tier1 ricevono lo
//      storico = snapshot precedenti);
//   3. per ogni opportunità fa un controllo di ESEGUIBILITÀ REALISTICA:
//        - FILLABLE: lo stake richiesto (matchedStake) è davvero presente nella
//          profondità del book ORA (matchedStake > 0 su tutte le gambe d'ingresso);
//        - PERSISTED: il prezzo "regge" per `delaySec` (ritardo in-play 5-8s):
//          guardando avanti nei frame, lo stesso stake è ancora abbinabile al
//          prezzo della gamba dopo il ritardo.
//      Un'opportunità è ESEGUIBILE se è insieme fillable e persisted.
//   4. aggrega un Report: conteggi per tier/type/fase, distribuzione profitto
//      £/% (min/mediana/max), eseguibili vs teoriche, e un focus sugli arbitraggi
//      eseguibili per fase (per la card "Validazione" della UI).
//
// PURE TypeScript, nessuna dipendenza da React → interamente unit-testabile.
// ============================================================================
import type { ReplayData } from '@/lib/live';
import type { Opportunity, OppConfig, RiskTier, Snapshot, Leg, Detector } from './types';
import { buildSnapshots } from './snapshot';
import { runDetectors, DEFAULT_OPP_CONFIG } from './engine';
import { matchedStake } from './fill';
import { TIER0_DETECTORS } from './tier0_arb';
import { tier1Detectors } from './tier1_quasi';
import { orderFlowImbalance, weightOfMoney, spreadScalp } from './tier2_micro';

// ----------------------------------------------------------------- tipi report
export interface ExecCheck {
    fillable: boolean;   // tutte le gambe d'ingresso hanno matchedStake > 0
    persisted: boolean;  // il prezzo regge per delaySec (look-ahead nei frame)
    executable: boolean; // fillable && persisted
    checkedAhead: boolean; // esisteva un frame a +delaySec da controllare
}

export interface OppRecord {
    id: string;
    type: string;
    tier: RiskTier;
    phase: string;
    profit: number;
    profitPct: number;
    confidence: number;
    snapshotIndex: number;
    ts: string;
    minute: number | null;
    exec: ExecCheck;
}

export interface DistStats {
    count: number;
    min: number;
    median: number;
    max: number;
}

export interface TierBucket {
    total: number;
    executable: number;
    avgProfitPct: number;
}

export interface Report {
    bucketMs: number;
    delaySec: number;
    totalSnapshots: number;
    totalOpportunities: number;
    executable: number;
    theoretical: number; // totale - eseguibili
    byTier: Record<RiskTier, TierBucket>;
    byType: Record<string, { total: number; executable: number }>;
    byPhase: Record<string, { total: number; executable: number }>;
    profit: DistStats;     // £ (su tutte le opportunità)
    profitPct: DistStats;  // %
    // Focus arbitraggi (tier 'arb') per la card di validazione.
    arb: {
        total: number;
        executable: number;
        avgProfitPct: number;       // media % sugli arb eseguibili
        executableByPhase: Record<string, number>;
    };
    records: OppRecord[];
}

// --------------------------------------------------------------- util interni
function tsMs(ts: string): number {
    const v = Date.parse(ts);
    return Number.isFinite(v) ? v : NaN;
}

function emptyTierBuckets(): Record<RiskTier, TierBucket> {
    return {
        arb: { total: 0, executable: 0, avgProfitPct: 0 },
        low: { total: 0, executable: 0, avgProfitPct: 0 },
        directional: { total: 0, executable: 0, avgProfitPct: 0 },
    };
}

function stats(values: number[]): DistStats {
    if (values.length === 0) return { count: 0, min: 0, median: 0, max: 0 };
    const s = [...values].sort((a, b) => a - b);
    const n = s.length;
    const mid = n >> 1;
    const median = n % 2 === 1 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
    return { count: n, min: s[0], median, max: s[n - 1] };
}

// Insieme dei detector eseguiti dall'harness per uno snapshot (con storico).
// I factory tier1 ricevono lo storico; i tier2 con provider (momentum/value) sono
// esclusi (richiedono dati esterni assenti nel replay).
export function harnessDetectors(history: Snapshot[]): Detector[] {
    return [
        ...TIER0_DETECTORS,
        ...tier1Detectors(history),
        orderFlowImbalance,
        weightOfMoney,
        spreadScalp,
    ];
}

// Tipi di opportunità tier1 le cui gambe sono piazzate SIMULTANEAMENTE (struttura
// bloccata): l'assicurazione lay-the-draw + 0-0 e il dutch-lay dei correct-score.
// Per queste l'ingresso richiede TUTTE le gambe, non solo la prima.
const MULTI_LEG_ENTRY_TYPES = new Set(['ltd_insurance', 'lay_field_cs']);

// Gambe d'INGRESSO (piazzate ORA) di un'opportunità:
//  - tier 'arb': tutte le gambe (il lock richiede tutte le bet contestualmente);
//  - strutture simultanee multi-gamba (ltd_insurance / lay_field_cs): tutte le gambe;
//  - altrimenti: solo la prima (l'azione immediata; l'uscita è un piano futuro).
function entryLegs(o: Opportunity): Leg[] {
    if (o.tier === 'arb' || MULTI_LEG_ENTRY_TYPES.has(o.type)) return o.legs;
    return o.legs.length > 0 ? [o.legs[0]] : [];
}

// Stake abbinabile per una gamba sullo stato di mercato di una snapshot.
function legMatchedOn(snap: Snapshot, leg: Leg): number {
    const st = snap.state[leg.marketId];
    const entry = st?.ladder?.[String(leg.selectionId)];
    const lv = leg.side === 'back' ? entry?.back : entry?.lay;
    return matchedStake(lv, leg.price, leg.matchedStake, leg.side);
}

// Indice della prima snapshot con ts >= ts(snapshots[i]) + delaySec (o -1).
function lookAheadIndex(snapshots: Snapshot[], i: number, delaySec: number): number {
    const target = tsMs(snapshots[i].ts) + delaySec * 1000;
    for (let j = i + 1; j < snapshots.length; j++) {
        if (tsMs(snapshots[j].ts) >= target) return j;
    }
    return -1;
}

// Controllo di eseguibilità di una singola opportunità.
const EPS = 1e-6;
function execCheck(o: Opportunity, snapshots: Snapshot[], i: number, delaySec: number): ExecCheck {
    const legs = entryLegs(o);
    const fillable = legs.length > 0 && legs.every((l) => l.matchedStake > EPS);

    const aheadIdx = lookAheadIndex(snapshots, i, delaySec);
    const checkedAhead = aheadIdx >= 0;
    let persisted = false;
    if (checkedAhead && fillable) {
        const ahead = snapshots[aheadIdx];
        // il prezzo "regge" se, dopo il ritardo, lo STESSO stake è ancora abbinabile
        // al prezzo di ogni gamba d'ingresso (depth >= matchedStake richiesto).
        persisted = legs.every((l) => legMatchedOn(ahead, l) >= l.matchedStake - EPS);
    }
    return { fillable, persisted, executable: fillable && persisted, checkedAhead };
}

/**
 * validateFromDetections — costruisce il Report a partire da detection GIÀ
 * calcolate (una per snapshot). NON ri-rileva e NON ricostruisce le snapshot:
 * esegue solo il controllo di eseguibilità (fillable + look-ahead) e l'aggregazione.
 * Usato dalla UI (MatchReplay) per riusare `detectionsPerSnap` ed evitare una
 * seconda passata O(n) di detection.
 *
 * @param snapshots snapshot a bucket fissi (allineate alla griglia timeline)
 * @param detectionsPerSnap opportunità rilevate per ogni snapshot (stesso indice)
 * @param cfg config motore (serve delaySec/bucketMs per il report)
 */
export function validateFromDetections(
    snapshots: Snapshot[],
    detectionsPerSnap: Opportunity[][],
    cfg: OppConfig = DEFAULT_OPP_CONFIG,
    bucketMs = 10000,
): Report {
    const records: OppRecord[] = [];
    for (let i = 0; i < snapshots.length; i++) {
        const opps = detectionsPerSnap[i] ?? [];
        for (const o of opps) {
            records.push({
                id: o.id,
                type: o.type,
                tier: o.tier,
                phase: o.phase,
                profit: o.profit,
                profitPct: o.profitPct,
                confidence: o.confidence,
                snapshotIndex: i,
                ts: snapshots[i].ts,
                minute: snapshots[i].minute,
                exec: execCheck(o, snapshots, i, cfg.delaySec),
            });
        }
    }

    return aggregateReport(records, snapshots.length, cfg, bucketMs);
}

/**
 * validateReplay — esegue l'harness completo su un replay.
 * Delega: costruisce le snapshot, calcola le detection con storico INCREMENTALE
 * (O(n)) e poi aggrega via validateFromDetections.
 * @param replay dati del replay (markets/frames/score_timeline)
 * @param cfg config motore (default DEFAULT_OPP_CONFIG)
 * @param bucketMs ampiezza bucket temporale (default 10s, come la timeline UI)
 */
export function validateReplay(
    replay: ReplayData,
    cfg: OppConfig = DEFAULT_OPP_CONFIG,
    bucketMs = 10000,
): Report {
    const snapshots = buildSnapshots(replay, bucketMs);

    const history: Snapshot[] = [];
    const detectionsPerSnap: Opportunity[][] = [];
    for (let i = 0; i < snapshots.length; i++) {
        detectionsPerSnap.push(runDetectors(snapshots[i], harnessDetectors(history), cfg));
        history.push(snapshots[i]);
    }

    return validateFromDetections(snapshots, detectionsPerSnap, cfg, bucketMs);
}

// aggregateReport — costruisce il Report dai record di eseguibilità.
function aggregateReport(
    records: OppRecord[],
    totalSnapshots: number,
    cfg: OppConfig,
    bucketMs: number,
): Report {
    // --- aggregazioni ---
    const byTier = emptyTierBuckets();
    const byType: Record<string, { total: number; executable: number }> = {};
    const byPhase: Record<string, { total: number; executable: number }> = {};
    const tierPctSum: Record<RiskTier, number> = { arb: 0, low: 0, directional: 0 };
    const tierPctCount: Record<RiskTier, number> = { arb: 0, low: 0, directional: 0 };

    let executable = 0;
    let arbExecPctSum = 0;
    let arbExecCount = 0;
    const arbExecByPhase: Record<string, number> = {};

    for (const r of records) {
        const ex = r.exec.executable;
        if (ex) executable++;

        const tb = byTier[r.tier];
        tb.total++;
        if (ex) tb.executable++;
        tierPctSum[r.tier] += r.profitPct;
        tierPctCount[r.tier]++;

        const ty = (byType[r.type] ??= { total: 0, executable: 0 });
        ty.total++;
        if (ex) ty.executable++;

        const ph = (byPhase[r.phase] ??= { total: 0, executable: 0 });
        ph.total++;
        if (ex) ph.executable++;

        if (r.tier === 'arb') {
            if (ex) {
                arbExecCount++;
                arbExecPctSum += r.profitPct;
                arbExecByPhase[r.phase] = (arbExecByPhase[r.phase] ?? 0) + 1;
            }
        }
    }

    for (const t of ['arb', 'low', 'directional'] as RiskTier[]) {
        byTier[t].avgProfitPct = tierPctCount[t] > 0 ? tierPctSum[t] / tierPctCount[t] : 0;
    }

    const profit = stats(records.map((r) => r.profit));
    const profitPct = stats(records.map((r) => r.profitPct));

    return {
        bucketMs,
        delaySec: cfg.delaySec,
        totalSnapshots,
        totalOpportunities: records.length,
        executable,
        theoretical: records.length - executable,
        byTier,
        byType,
        byPhase,
        profit,
        profitPct,
        arb: {
            total: byTier.arb.total,
            executable: byTier.arb.executable,
            avgProfitPct: arbExecCount > 0 ? arbExecPctSum / arbExecCount : 0,
            executableByPhase: arbExecByPhase,
        },
        records,
    };
}
