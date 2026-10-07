// ============================================================================
// MUTANTI per falsificare il verificatore della barra (07/10/2026): versioni
// DIFETTOSE di proposito delle funzioni della pagina, che il verificatore deve
// riconoscere. Mai importarle da codice di produzione.
//   D1  `punteggioAlTsD1`          tabellone: ultima riga di QUALUNQUE tipo, `?? 0`
//   D2  `buildSnapshotsD2`         motore: stesso difetto sul punteggio dello snapshot
//   D3+D4 `timelineEventMarkersD3D4` = la funzione vera prima di 94af2eb
//   altri: simboli spostati / fuori ordine / senza clamp
// ============================================================================
import type { ReplayData, ScoreEvent } from '@/lib/live';
import { buildSnapshots } from '@/lib/opportunities/snapshot';
import type { Snapshot } from '@/lib/opportunities/types';
import type { FunzioniPagina } from '@/lib/replayVerificaBarraCalcio';
import { timelineEventMarkers as timelineEventMarkersLegacy } from './replayTimelineEventsLegacy';

/** D1: com'era il blocco di `MatchReplay.tsx` prima di 94af2eb. */
export function punteggioAlTsD1(
    sortedScoreTimeline: ReadonlyArray<ScoreEvent>,
    ts: string,
): { home: number; away: number; minute: number | null } {
    let best: ScoreEvent | null = null;
    for (const ev of sortedScoreTimeline) {
        if (ev.ts <= ts) best = ev; else break;
    }
    return best
        ? { home: best.score_home ?? 0, away: best.score_away ?? 0, minute: best.minute }
        : { home: 0, away: 0, minute: null };
}

/** D2: com'era `lib/opportunities/snapshot.ts` prima di 94af2eb (punteggio dall'ultima riga di qualunque tipo). */
export function buildSnapshotsD2(replay: ReplayData, bucketMs = 10_000): Snapshot[] {
    const righe = [...replay.score_timeline]
        .filter(r => Number.isFinite(Date.parse(r.ts)))
        .sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));
    return buildSnapshots(replay, bucketMs).map(s => {
        const fine = Date.parse(s.ts) + bucketMs - 1;
        let ultima: ScoreEvent | null = null;
        for (const r of righe) { if (Date.parse(r.ts) <= fine) ultima = r; else break; }
        return ultima ? { ...s, scoreHome: ultima.score_home ?? 0, scoreAway: ultima.score_away ?? 0 } : s;
    });
}

/** D3+D4: la funzione dei simboli com'era prima di 94af2eb. */
export const timelineEventMarkersD3D4: FunzioniPagina['timelineEventMarkers'] = timelineEventMarkersLegacy;

/** simboli tutti spostati di `passi` passi (positivo = in ritardo, negativo = prima del loro istante) */
export function spostaSimboli(base: FunzioniPagina['timelineEventMarkers'], passi: number): FunzioniPagina['timelineEventMarkers'] {
    return (righe, timeline, casa, ospiti, span) =>
        base(righe, timeline, casa, ospiti, span).map(m => ({ ...m, pctLeft: Math.min(1, Math.max(0, m.pctLeft + passi / span)) }));
}
