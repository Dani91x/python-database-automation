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
import { runDetectors, DEFAULT_OPP_CONFIG, opportunitySignature } from './engine';
import { matchedStake } from './fill';
import { TIER0_DETECTORS } from './tier0_arb';
import { tier1Detectors } from './tier1_quasi';
import { orderFlowImbalance, weightOfMoney, spreadScalp } from './tier2_micro';
import { entryLegs } from './tradeable';

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

// `entryLegs` (gambe d'ingresso da piazzare ORA) è importato da tradeable.ts —
// unica fonte condivisa col gate del motore.

// Stake abbinabile per una gamba sullo stato di mercato di una snapshot.
function legMatchedOn(snap: Snapshot, leg: Leg): number {
    const st = snap.state[leg.marketId];
    const entry = st?.ladder?.[String(leg.selectionId)];
    const lv = leg.side === 'back' ? entry?.back : entry?.lay;
    return matchedStake(lv, leg.price, leg.matchedStake, leg.side);
}

// Controllo di eseguibilità di una singola opportunità.
const EPS = 1e-6;
function execCheck(o: Opportunity, snapshots: Snapshot[], i: number, delaySec: number): ExecCheck {
    const legs = entryLegs(o);
    const fillable = legs.length > 0 && legs.every((l) => l.matchedStake > EPS);

    // FIX (look-ahead vacuo): con frame downsampled lo snapshot a +delaySec è
    // quasi sempre il CARRY-FORWARD dello stesso frame → confrontarlo con sé
    // stesso dava "persisted" gratis. Il check vale solo su un'osservazione
    // NUOVA: la prima snapshot in cui TUTTI i mercati delle gambe hanno un frame
    // (a) più recente di quello della detection e (b) ad ALMENO +delaySec dal
    // frame della detection (ancora al frame_ts REALE, non all'inizio bucket:
    // un frame a fine bucket renderebbe il ritardo quasi nullo). Se non esiste
    // (fine registrazione, mercato muto) → NON verificabile → NON eseguibile.
    let checkedAhead = false;
    let persisted = false;
    if (fillable) {
        // un frame base per MERCATO (più gambe possono condividere lo stesso
        // mercato, es. back+lay della stessa selezione): se anche un solo
        // mercato è senza frame → non verificabile.
        const baseTs = new Map<string, number>();
        let missingBase = false;
        for (const l of legs) {
            if (baseTs.has(l.marketId)) continue;
            const b = snapshots[i].state[l.marketId]?.frame_ts;
            const ms = b != null ? tsMs(b) : NaN;
            if (!Number.isFinite(ms)) { missingBase = true; break; }
            baseTs.set(l.marketId, ms);
        }
        const target = !missingBase && baseTs.size > 0
            ? Math.max(...baseTs.values()) + delaySec * 1000
            : NaN;
        if (Number.isFinite(target)) {
            for (let j = i + 1; j < snapshots.length; j++) {
                const fresh = legs.every((l) => {
                    const b = baseTs.get(l.marketId);
                    const a = snapshots[j].state[l.marketId]?.frame_ts;
                    if (b == null || a == null) return false;
                    const aMs = tsMs(a);
                    return aMs > b && aMs >= target;
                });
                if (!fresh) continue;
                checkedAhead = true;
                // il prezzo "regge" se, alla prima osservazione nuova dopo il ritardo,
                // lo STESSO stake è ancora abbinabile al prezzo di ogni gamba.
                persisted = legs.every((l) => legMatchedOn(snapshots[j], l) >= l.matchedStake - EPS);
                break;
            }
        }
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
    // DEDUP EPISODI: la stessa opportunità che persiste per N snapshot consecutivi
    // (o resta "viva" per carry-forward del medesimo frame) è UN episodio, non N
    // opportunità: si conta alla prima apparizione della sua firma. Senza dedup i
    // totali del report erano conteggi ponderati per durata ("30 arb" per 1 episodio).
    let prevSignatures = new Set<string>();
    for (let i = 0; i < snapshots.length; i++) {
        const opps = detectionsPerSnap[i] ?? [];
        const curSignatures = new Set<string>();
        for (const o of opps) {
            const sig = opportunitySignature(o);
            curSignatures.add(sig);
            if (prevSignatures.has(sig)) continue; // episodio già contato
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
        prevSignatures = curSignatures;
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
