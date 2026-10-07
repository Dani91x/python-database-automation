// ============================================================================
// Conversione della fixture di una registrazione (`replay_barra_<event>.json`) nel
// `ReplayData` che la pagina riceve da `fetchReplayChunked`. Staccata da `replayBarra.ts`
// (che importa a nome le due fixture storiche) cosi' i test su TUTTE le registrazioni
// la usano senza dipendere da quei due file. Il formato lo scrive
// `tools/replay_barra_fixture.py`.
// ============================================================================
import type { Frame, Market, ReplayData, ScoreEvent } from '@/lib/live';

// riga frame: [1, ts, minute, inplay, status, {selId: [back1|null, lay1|null]}] (Match Odds)
//             [0, ts, minute, inplay]                                         (fantasma)
export type RigaMatchOdds = [1, string, number | null, number, string, Record<string, [[number, number] | null, [number, number] | null]>];
export type RigaFantasma = [0, string, number | null, number];
export type RigaScore = [string, string, number | null, number | null, number | null, string | null, unknown];

export interface FixtureBarra {
    event: ReplayData['event'];
    mo: { market_id: string; selections: [number, string][] };
    frames: (RigaMatchOdds | RigaFantasma)[];
    score_timeline: RigaScore[];
}

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

