// ============================================================================
// Fixture della barra di avanzamento di Match Replay (07/10): DUE registrazioni
// VERE, ricostruite fedelmente a come le riceve la pagina dal database.
//   35797769  Spagna-Belgio (10/07, quarti Mondiale): 2h30 di pre-match lungo,
//             buchi dello stream (da 2 a 9 minuti), 3 gol, 4 gialli, 6 angoli.
//   35760084  Liepaja-Ogre (30/06): 4 gol, 3 gialli, 15 angoli, sospensione
//             finale lunga.
// Come sono fatti i file (generati dai file della registrazione `*.raw.jsonl`,
// `*.scores.jsonl`, `*.timeline.jsonl`):
//  - frames: righe di `live_market_snapshots` ottenute col curator VERO
//    (`Betfair/stream/curator.py::curate_event`, cadenza 10 s) e poi col
//    campionamento del server (`get_replay_frames`: 1 frame per mercato e per
//    bucket, bucket e finestre calcolati come `fetchReplayChunked`), nello stesso
//    ORDINE in cui li restituisce il server (per finestra, per mercato).
//  - per tenere il file sotto i 150 KB si conservano TUTTI i frame del MATCH_ODDS
//    (best back/lay di ogni selezione, stato, in-gioco) e, degli altri mercati,
//    solo i frame che DEFINISCONO la timeline (il primo di ogni bucket da 10 s e
//    quello che porta il primo minuto) piu' il primo frame in-gioco: sono marcati
//    "fantasma" (mercato 9.0, senza ladder). Provato con il confronto passo per
//    passo sulla pagina intera: stessi simboli, stessa barra, stesso pannello del
//    Match Odds, stesso punteggio, stesse sospensioni su TUTTI i passi.
//  - score_timeline: le righe di `live_score_timeline` (righe del punteggio dei due
//    provider + righe-evento della timeline Betfair), col payload ridotto alle
//    chiavi che la barra legge (conteggi angoli/cartellini; per gli eventi tipo,
//    squadra, minuto).
// ============================================================================
import type { Frame, Market, ReplayData, ScoreEvent } from '@/lib/live';
import fx35797769 from './replay_barra_35797769.json';
import fx35760084 from './replay_barra_35760084.json';

// riga frame: [1, ts, minute, inplay, status, {selId: [back1|null, lay1|null]}] (Match Odds)
//             [0, ts, minute, inplay]                                         (fantasma)
type RigaMatchOdds = [1, string, number | null, number, string, Record<string, [[number, number] | null, [number, number] | null]>];
type RigaFantasma = [0, string, number | null, number];
type RigaScore = [string, string, number | null, number | null, number | null, string | null, unknown];

export interface FixtureBarra {
    event: ReplayData['event'];
    mo: { market_id: string; selections: [number, string][] };
    frames: (RigaMatchOdds | RigaFantasma)[];
    score_timeline: RigaScore[];
}

export const FIXTURE_BARRA = {
    '35797769': fx35797769 as unknown as FixtureBarra,
    '35760084': fx35760084 as unknown as FixtureBarra,
} as const;
export type EventoBarra = keyof typeof FIXTURE_BARRA;

export const ID_MERCATO_FANTASMA = '9.0';

// ReplayData come lo restituisce `fetchReplayChunked` (chiavi e tipi del vero).
export function replayDaFixture(fx: FixtureBarra): ReplayData {
    const frames: Frame[] = fx.frames.map(r => {
        if (r[0] === 1) {
            const ladder: Frame['ladder'] = {};
            for (const [sid, [b, l]] of Object.entries(r[5])) {
                ladder[sid] = { back: b ? [b] : [], lay: l ? [l] : [], ltp: null, tv: null };
            }
            return { market_id: fx.mo.market_id, ts: r[1], minute: r[2], inplay: r[3] === 1, status: r[4], ladder };
        }
        return { market_id: ID_MERCATO_FANTASMA, ts: r[1], minute: r[2], inplay: r[3] === 1, status: 'OPEN', ladder: {} };
    });
    const markets: Market[] = [
        {
            market_id: fx.mo.market_id, market_type: 'MATCH_ODDS', market_name: 'MATCH_ODDS', sort_priority: 1,
            selections: fx.mo.selections.map(([selection_id, name], i) => ({ selection_id, name, sort_priority: i + 1 })),
        },
        { market_id: ID_MERCATO_FANTASMA, market_type: 'OVER_UNDER_25', market_name: 'OVER_UNDER_25', sort_priority: 2, selections: [] },
    ];
    const score_timeline: ScoreEvent[] = fx.score_timeline.map(t => ({
        ts: t[0], source: t[1], minute: t[2], score_home: t[3], score_away: t[4], event_type: t[5], payload: t[6],
    }));
    return { event: fx.event, markets, frames, score_timeline };
}

export function msDi(iso: string): number {
    return new Date(iso).getTime();
}

// ----------------------------------------------------------------------------
// ORACOLI: ricostruzioni indipendenti dal codice della pagina, scritte dalla
// regola (non dal codice): la griglia della barra e' il primo frame di ogni
// bucket da 10 s di orologio (nell'ordine in cui arrivano), col primo minuto
// non nullo del bucket; i passi sono ordinati per ts.
// ----------------------------------------------------------------------------
export interface PassoBarra { ts: string; ms: number; minute: number | null }
export function passiAttesi(frames: ReadonlyArray<Frame>): PassoBarra[] {
    const perBucket = new Map<number, { ts: string; minute: number | null }>();
    for (const f of frames) {
        const b = Math.floor(msDi(f.ts) / 10_000);
        const c = perBucket.get(b);
        if (!c) perBucket.set(b, { ts: f.ts, minute: f.minute });
        else if (c.minute == null && f.minute != null) c.minute = f.minute;
    }
    return Array.from(perBucket.values())
        .sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0))
        .map(s => ({ ts: s.ts, ms: msDi(s.ts), minute: s.minute }));
}

// primo passo con ts >= istante (e' il passo in cui un fatto diventa visibile
// scorrendo la barra); -1 se l'istante e' DOPO l'ultimo passo.
export function passoDa(passi: ReadonlyArray<PassoBarra>, istanteMs: number): number {
    for (let i = 0; i < passi.length; i++) if (passi[i].ms >= istanteMs) return i;
    return -1;
}

// ultimo frame del Match Odds con ts <= istante
export function frameMatchOddsA(replay: ReplayData, mercatoId: string, istanteMs: number): Frame | null {
    let best: Frame | null = null;
    for (const f of replay.frames) {
        if (f.market_id !== mercatoId) continue;
        if (msDi(f.ts) <= istanteMs && (best == null || msDi(f.ts) >= msDi(best.ts))) best = f;
    }
    return best;
}

export interface SimboloAtteso { kind: 'goal' | 'yellow' | 'red' | 'corner'; team: 'home' | 'away'; ts: string; minute: number | null }
// simboli attesi = gli eventi della timeline Betfair (gol, gialli, rossi) piu' gli
// angoli come cambi del conteggio nelle righe del punteggio.
export function simboliAttesi(righe: ReadonlyArray<ScoreEvent>): SimboloAtteso[] {
    const out: SimboloAtteso[] = [];
    const tipi: Record<string, SimboloAtteso['kind']> = { Goal: 'goal', YellowCard: 'yellow', RedCard: 'red' };
    for (const r of righe) {
        if (!r.event_type || !tipi[r.event_type]) continue;
        const team = (r.payload as { team?: string } | null)?.team;
        if (team !== 'home' && team !== 'away') continue;
        out.push({ kind: tipi[r.event_type], team, ts: r.ts, minute: r.minute });
    }
    let ch = 0, ca = 0;
    for (const r of righe) {
        if (r.event_type || r.source !== 'betfair') continue;
        const s = (r.payload as { score?: { home?: { numberOfCorners?: number }; away?: { numberOfCorners?: number } } } | null)?.score;
        const h = Number(s?.home?.numberOfCorners ?? 0) || 0;
        const a = Number(s?.away?.numberOfCorners ?? 0) || 0;
        if (h > ch) out.push({ kind: 'corner', team: 'home', ts: r.ts, minute: r.minute });
        if (a > ca) out.push({ kind: 'corner', team: 'away', ts: r.ts, minute: r.minute });
        ch = Math.max(ch, h); ca = Math.max(ca, a);
    }
    return out;
}
