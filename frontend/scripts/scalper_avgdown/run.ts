// run.ts — applica lo scalper averaging-down alle registrazioni reali.
//
// Uso: npx tsx run.ts <dataDir> <outDir> [eventId|all] [variants=primary,layfirst,decr]
//
// Per ogni evento: mercati MATCH_ODDS / OVER_UNDER_* / BTTS, ogni selezione,
// fase PRE e IN-PLAY separate, target-stop +1€ per fase. Risultati in
// <outDir>/<eventId>.json + progressi su stdout.
import { createReadStream } from 'node:fs';
import { mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { createGunzip } from 'node:zlib';
import path from 'node:path';
import { DEFAULT_CONFIG, runPhase, type EngineConfig, type PhaseResult, type SelFrame } from './engine';

interface RawLadderEntry {
    back?: [number, number][];
    lay?: [number, number][];
    ltp?: number | null;
    tv?: number | null;
    trd?: [number, number][];
}
interface RawSnap {
    id: number; market_id: string; ts: string; minute: number | null;
    inplay: boolean; status: string; ladder: Record<string, RawLadderEntry>;
}
interface MetaSel { selection_id: number; name: string; sort_priority: number | null; }
interface MetaMarket { market_id: string; market_type: string | null; market_name: string | null; selections: MetaSel[] | { selections?: MetaSel[] } | null; }
interface Meta {
    kind: 'meta';
    event: { event_id: string; home_name: string; away_name: string; open_date: string; league_name?: string | null };
    markets: MetaMarket[];
    score_timeline: { ts: string; minute: number | null; score_home: number | null; score_away: number | null; event_type: string | null }[];
}

const TRADABLE = /^(MATCH_ODDS|OVER_UNDER_\d+|BOTH_TEAMS_TO_SCORE)$/;

function selsOf(m: MetaMarket): MetaSel[] {
    const s = m.selections as unknown;
    if (Array.isArray(s)) return s as MetaSel[];
    if (s && typeof s === 'object' && Array.isArray((s as { selections?: unknown }).selections)) {
        return (s as { selections: MetaSel[] }).selections;
    }
    return [];
}

// esito reale della selezione (per il settlement di posizioni non chiudibili)
function settleWinOf(
    meta: Meta, m: MetaMarket, sel: MetaSel,
): boolean | null {
    let sh: number | null = null, sa: number | null = null;
    for (const ev of meta.score_timeline) {
        if (ev.score_home != null && ev.score_away != null) { sh = ev.score_home; sa = ev.score_away; }
    }
    if (sh == null || sa == null) return null;
    const total = sh + sa;
    const t = m.market_type ?? '';
    if (t === 'MATCH_ODDS') {
        const n = (sel.name ?? '').trim().toLowerCase();
        if (n === 'the draw') return sh === sa;
        if (n === (meta.event.home_name ?? '').trim().toLowerCase()) return sh > sa;
        if (n === (meta.event.away_name ?? '').trim().toLowerCase()) return sa > sh;
        // fallback: sort_priority 1=casa, 2=ospite, 3=pari
        if (sel.sort_priority === 1) return sh > sa;
        if (sel.sort_priority === 2) return sa > sh;
        if (sel.sort_priority === 3) return sh === sa;
        return null;
    }
    const ou = t.match(/^OVER_UNDER_(\d+)$/);
    if (ou) {
        const line = Number(ou[1]) / 10; // OVER_UNDER_25 → 2.5
        const isUnder = /under/i.test(sel.name ?? '');
        return isUnder ? total < line : total > line;
    }
    if (t === 'BOTH_TEAMS_TO_SCORE') {
        const yes = /yes/i.test(sel.name ?? '');
        const both = sh > 0 && sa > 0;
        return yes ? both : !both;
    }
    return null;
}

async function loadEvent(file: string): Promise<{ meta: Meta; snaps: Map<string, RawSnap[]> }> {
    const rl = createInterface({ input: createReadStream(file).pipe(createGunzip()), crlfDelay: Infinity });
    let meta: Meta | null = null;
    const snaps = new Map<string, RawSnap[]>();
    for await (const line of rl) {
        if (!line) continue;
        const row = JSON.parse(line) as Meta | RawSnap;
        if ((row as Meta).kind === 'meta') { meta = row as Meta; continue; }
        const s = row as RawSnap;
        let arr = snaps.get(s.market_id);
        if (!arr) { arr = []; snaps.set(s.market_id, arr); }
        arr.push(s);
    }
    if (!meta) throw new Error(`meta mancante in ${file}`);
    return { meta, snaps };
}

// frame per-selezione (carry-forward dell'entry se assente in una riga)
function selFrames(rows: RawSnap[], selId: number): SelFrame[] {
    const out: SelFrame[] = [];
    let last: RawLadderEntry | null = null;
    for (const r of rows) {
        const e = r.ladder?.[String(selId)] ?? last;
        if (!e) continue;
        last = e;
        out.push({
            ts: Date.parse(r.ts),
            back: e.back ?? [],
            lay: e.lay ?? [],
            ltp: e.ltp ?? null,
            tv: e.tv ?? null,
            trd: e.trd,
            status: r.status,
            inplay: r.inplay,
        });
    }
    return out;
}

interface InstrumentResult {
    market_id: string;
    market_type: string | null;
    market_name: string | null;
    selection_id: number;
    selection_name: string;
    phase: 'pre' | 'inplay' | 'precarry';
    variant: string;
    openPrice: number | null;   // primo best back della fase (per fav/linea principale)
    result: PhaseResult;
}

function firstBack(frames: SelFrame[]): number | null {
    for (const fr of frames) {
        for (const lvl of fr.back) {
            if (lvl && Number.isFinite(lvl[0]) && lvl[1] > 0) return lvl[0];
        }
    }
    return null;
}

const VARIANTS: Record<string, Partial<EngineConfig>> = {
    primary: {},                                                  // back-first, 25 piatto ×4 (dossier)
    layfirst: { direction: 'lay' },                               // mirror
    decr: { stakeSeq: [25, 15, 10, 6] },                          // fix §10: stake decrescente
    // martingala: ogni gamba ≈ intera posizione esistente → BE resta a 1 tick.
    // Esposizione max: mart6 = 800€, mart8 = 3.200€. I fill restano vincolati
    // alla liquidità REALE del book (è lì che la martingala si rompe).
    mart6: { stakeSeq: [25, 25, 50, 100, 200, 400], maxLegs: 6 },
    mart8: { stakeSeq: [25, 25, 50, 100, 200, 400, 800, 1600], maxLegs: 8 },
    // griglia "pochi centesimi senza esplodere": spaziatura add 2-3 tick,
    // crescita stake moderata, esposizione max 100-215€.
    sp2: { addSpacingTicks: 2 },
    sp3: { addSpacingTicks: 3 },
    sp2_ramp: { addSpacingTicks: 2, stakeSeq: [25, 40, 60, 90] },
    sp3_ramp: { addSpacingTicks: 3, stakeSeq: [25, 40, 60, 90] },
    sp2_r3: { addSpacingTicks: 2, stakeSeq: [25, 50, 100], maxLegs: 3 },
    sp3_r3: { addSpacingTicks: 3, stakeSeq: [25, 50, 100], maxLegs: 3 },
};

async function main(): Promise<void> {
    const [dataDir, outDir, evFilter = 'all', variantsArg = Object.keys(VARIANTS).join(',')] = process.argv.slice(2);
    if (!dataDir || !outDir) throw new Error('uso: run.ts <dataDir> <outDir> [eventId|all] [variants]');
    mkdirSync(outDir, { recursive: true });
    const variants = variantsArg.split(',').filter(v => v in VARIANTS);

    const files = readdirSync(dataDir).filter(f => f.endsWith('.jsonl.gz'))
        .filter(f => evFilter === 'all' || f.startsWith(evFilter));
    for (const f of files) {
        const t0 = Date.now();
        const { meta, snaps } = await loadEvent(path.join(dataDir, f));
        const rows: InstrumentResult[] = [];
        const markets = meta.markets.filter(m => TRADABLE.test(m.market_type ?? ''));
        for (const m of markets) {
            const raw = snaps.get(m.market_id);
            if (!raw || raw.length < 10) continue;
            raw.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts) || a.id - b.id);
            for (const sel of selsOf(m)) {
                const frames = selFrames(raw, sel.selection_id);
                if (frames.length < 10) continue;
                const kickIdx = frames.findIndex(fr => fr.inplay);
                const pre = kickIdx < 0 ? frames : frames.slice(0, kickIdx);
                const inp = kickIdx < 0 ? [] : frames.slice(kickIdx);
                const win = settleWinOf(meta, m, sel);
                for (const v of variants) {
                    const cfg: EngineConfig = { ...DEFAULT_CONFIG, ...VARIANTS[v] };
                    if (pre.length >= 10) {
                        rows.push({
                            market_id: m.market_id, market_type: m.market_type, market_name: m.market_name,
                            selection_id: sel.selection_id, selection_name: sel.name,
                            phase: 'pre', variant: v, openPrice: firstBack(pre), result: runPhase(pre, cfg, win),
                        });
                    }
                    if (inp.length >= 10) {
                        rows.push({
                            market_id: m.market_id, market_type: m.market_type, market_name: m.market_name,
                            selection_id: sel.selection_id, selection_name: sel.name,
                            phase: 'inplay', variant: v, openPrice: firstBack(inp), result: runPhase(inp, cfg, win),
                        });
                    }
                    // PRECARRY: ingressi solo pre-match, gestione della posizione
                    // che prosegue nei primi 5' in-play (la domanda "a cavallo del KO")
                    if (pre.length >= 10 && kickIdx >= 0) {
                        const kickTs = frames[kickIdx].ts;
                        const carry = [...pre, ...inp.filter(fr => fr.ts <= kickTs + 5 * 60_000)];
                        const cfgCarry: EngineConfig = { ...cfg, openUntilTs: pre[pre.length - 1].ts };
                        rows.push({
                            market_id: m.market_id, market_type: m.market_type, market_name: m.market_name,
                            selection_id: sel.selection_id, selection_name: sel.name,
                            phase: 'precarry', variant: v, openPrice: firstBack(pre), result: runPhase(carry, cfgCarry, win),
                        });
                    }
                }
            }
        }
        const out = {
            event: meta.event,
            n_markets_tradable: markets.length,
            goals: meta.score_timeline.filter(e => (e.event_type ?? '').toUpperCase().includes('GOAL')).length,
            rows,
        };
        const outFile = path.join(outDir, `${meta.event.event_id}.json`);
        writeFileSync(outFile, JSON.stringify(out));
        console.log(`OK ${meta.event.event_id} ${meta.event.home_name}-${meta.event.away_name}: ${rows.length} strumenti-fase in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    }
    console.log('FINITO');
}

main().catch(err => { console.error(err); process.exit(1); });
