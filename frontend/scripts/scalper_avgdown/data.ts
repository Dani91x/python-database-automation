// data.ts — caricamento condiviso delle registrazioni scaricate (jsonl.gz).
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { createGunzip } from 'node:zlib';
import type { SelFrame } from './engine';

export interface RawLadderEntry {
    back?: [number, number][];
    lay?: [number, number][];
    ltp?: number | null;
    tv?: number | null;
    trd?: [number, number][];
}
export interface RawSnap {
    id: number; market_id: string; ts: string; minute: number | null;
    inplay: boolean; status: string; ladder: Record<string, RawLadderEntry>;
}
export interface MetaSel { selection_id: number; name: string; sort_priority: number | null; }
export interface MetaMarket {
    market_id: string; market_type: string | null; market_name: string | null;
    selections: MetaSel[] | { selections?: MetaSel[] } | null;
}
export interface Meta {
    kind: 'meta';
    event: { event_id: string; home_name: string; away_name: string; open_date: string; league_name?: string | null };
    markets: MetaMarket[];
    score_timeline: { ts: string; minute: number | null; score_home: number | null; score_away: number | null; event_type: string | null }[];
}

export function selsOf(m: MetaMarket): MetaSel[] {
    const s = m.selections as unknown;
    if (Array.isArray(s)) return s as MetaSel[];
    if (s && typeof s === 'object' && Array.isArray((s as { selections?: unknown }).selections)) {
        return (s as { selections: MetaSel[] }).selections;
    }
    return [];
}

export async function loadEvent(file: string): Promise<{ meta: Meta; snaps: Map<string, RawSnap[]> }> {
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
    for (const arr of snaps.values()) {
        arr.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts) || a.id - b.id);
    }
    return { meta, snaps };
}

export function selFrames(rows: RawSnap[], selId: number): SelFrame[] {
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

export function firstBack(frames: SelFrame[]): number | null {
    for (const fr of frames) {
        for (const lvl of fr.back) {
            if (lvl && Number.isFinite(lvl[0]) && lvl[1] > 0) return lvl[0];
        }
    }
    return null;
}
