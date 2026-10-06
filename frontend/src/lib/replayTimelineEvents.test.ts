// 06/10 — simboli della barra di avanzamento di Match Replay.
// Dati VERI: score_timeline della partita 35797769 (Spagna, 10/07) come la
// scrive l'uploader (righe timeline IPS + righe punteggio betfair/api_football;
// payload ridotto alle chiavi score.home/away.* che la barra legge).
import { describe, it, expect } from 'vitest';
import type { ScoreEvent } from '@/lib/live';
import { kindDiTipo, timelineEventMarkers } from './replayTimelineEvents';
import righeVere from './__fixtures__/replay_35797769_score_timeline.json';

function ordina(r: ScoreEvent[]): ScoreEvent[] {
    return [...r].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
}
function conta(m: { kind: string; team?: string | null }[]): Record<string, number> {
    const out: Record<string, number> = {};
    for (const x of m) out[`${x.kind}:${x.team ?? '-'}`] = (out[`${x.kind}:${x.team ?? '-'}`] ?? 0) + 1;
    return out;
}

describe('timelineEventMarkers — partita vera 35797769', () => {
    const righe = ordina(righeVere as ScoreEvent[]);
    const timeline = righe.map(r => ({ ts: r.ts }));
    const m = timelineEventMarkers(righe, timeline, 'Spain', 'Rivale', Math.max(1, timeline.length - 1));

    it('gol e gialli come la timeline IPS (2+1 gol, 2+2 gialli), nessun doppione', () => {
        const c = conta(m);
        expect(c['goal:home']).toBe(2);
        expect(c['goal:away']).toBe(1);
        expect(c['yellow:home']).toBe(2);
        expect(c['yellow:away']).toBe(2);
        expect(c['red:home'] ?? 0).toBe(0);
    });

    it('angoli presenti anche con la timeline discreta (5 casa, 1 ospite)', () => {
        const c = conta(m);
        expect(c['corner:home']).toBe(5);
        expect(c['corner:away']).toBe(1);
    });

    it('le fasi di gioco (KickOff, FirstHalfEnd, ...) non hanno simbolo', () => {
        expect(m.every(x => ['goal', 'yellow', 'red', 'corner'].includes(x.kind))).toBe(true);
        expect(m.every(x => x.pctLeft >= 0 && x.pctLeft <= 1)).toBe(true);
    });
});

describe('timelineEventMarkers — punteggio da due fonti (senza timeline)', () => {
    const r = (ts: string, minute: number, h: number, a: number, source: string): ScoreEvent => ({
        ts, minute, score_home: h, score_away: a, event_type: null, source,
        payload: { score: { home: {}, away: {} } },
    });
    it('una fonte in ritardo che fa "tornare indietro" il punteggio non duplica il gol', () => {
        const righe = [
            r('2026-10-06T16:00:00Z', 1, 0, 0, 'betfair'),
            r('2026-10-06T16:10:00Z', 10, 1, 0, 'betfair'),
            r('2026-10-06T16:10:30Z', 10, 0, 0, 'api_football'),   // in ritardo
            r('2026-10-06T16:11:00Z', 11, 1, 0, 'betfair'),
            r('2026-10-06T16:30:00Z', 30, 1, 1, 'betfair'),
        ];
        const m = timelineEventMarkers(righe, righe.map(x => ({ ts: x.ts })), 'A', 'B', 4);
        expect(conta(m)).toEqual({ 'goal:home': 1, 'goal:away': 1 });
        expect(m[0].ts).toBe('2026-10-06T16:10:00Z');
    });
});

describe('kindDiTipo', () => {
    it('tipi Betfair e varianti', () => {
        expect(kindDiTipo('Goal')).toBe('goal');
        expect(kindDiTipo('YellowCard')).toBe('yellow');
        expect(kindDiTipo('yellow_card')).toBe('yellow');
        expect(kindDiTipo('RedCard')).toBe('red');
        expect(kindDiTipo('SecondYellow')).toBe('red');
        expect(kindDiTipo('YellowRedCard')).toBe('red');
        expect(kindDiTipo('Corner')).toBe('corner');
        expect(kindDiTipo('KickOff')).toBeNull();
        expect(kindDiTipo('FirstHalfEnd')).toBeNull();
        expect(kindDiTipo(null)).toBeNull();
    });
});
