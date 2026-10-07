// ============================================================================
// 07/10 - SALTI DEL CONTEGGIO FRA DUE RIGHE DEL PUNTEGGIO: un simbolo per OGNI
// unita'. Se fra due righe consecutive il feed passa da 1 a 3 angoli (due angoli
// fra un poll e l'altro), la barra deve mostrare DUE simboli, non uno: i simboli
// devono contare quanto il punteggio (standard barra/simboli/tabellone, trovato dal
// verificatore `replayVerificaBarra*` sul replay sintetico).
// Prima della correzione `timelineEventMarkers` disegnava UN simbolo per riga
// anche con un salto di 2 o piu'.
// ============================================================================
import { describe, it, expect } from 'vitest';
import type { ScoreEvent } from '@/lib/live';
import { timelineEventMarkers } from './replayTimelineEvents';

const T0 = Date.parse('2026-10-07T19:00:00.000Z');
const iso = (s: number): string => new Date(T0 + s * 1000).toISOString();
const riga = (s: number, h: number, a: number, c: { hc?: number; ac?: number; hy?: number; ay?: number; hr?: number }): ScoreEvent => ({
    ts: iso(s), minute: Math.floor(s / 60), score_home: h, score_away: a, event_type: null, source: 'betfair',
    payload: { score: {
        home: { numberOfCorners: c.hc ?? 0, numberOfYellowCards: c.hy ?? 0, numberOfRedCards: c.hr ?? 0 },
        away: { numberOfCorners: c.ac ?? 0, numberOfYellowCards: c.ay ?? 0, numberOfRedCards: 0 },
    } },
});
const passi = Array.from({ length: 100 }, (_, i) => ({ ts: iso(i * 10) }));
const marker = (righe: ScoreEvent[]) => timelineEventMarkers(righe, passi, 'Casa', 'Ospiti', passi.length - 1);
const conta = (m: { kind: string; team?: string | null }[], kind: string, team: string) => m.filter(x => x.kind === kind && x.team === team).length;

describe('timelineEventMarkers - salto di piu\' unita\' fra due righe: un simbolo per unita\'', () => {
    it('angoli: da 1 a 3 fra due righe = 2 simboli in piu\' (3 in tutto)', () => {
        const m = marker([riga(0, 0, 0, {}), riga(100, 0, 0, { hc: 1 }), riga(200, 0, 0, { hc: 3 })]);
        expect(conta(m, 'corner', 'home')).toBe(3);
    });

    it('angoli di una squadra che compaiono tutti insieme alla prima riga con il conteggio (1 -> 2 simboli per 2 angoli)', () => {
        const m = marker([riga(0, 0, 0, {}), riga(100, 0, 0, { hc: 2, ac: 1 })]);
        expect(conta(m, 'corner', 'home')).toBe(2);
        expect(conta(m, 'corner', 'away')).toBe(1);
    });

    it('cartellini senza timeline discreta: salto di 2 gialli = 2 simboli', () => {
        const m = marker([riga(0, 0, 0, {}), riga(300, 0, 0, { ay: 2 })]);
        expect(conta(m, 'yellow', 'away')).toBe(2);
    });

    it('gol senza timeline discreta: salto 0-0 -> 2-0 fra due righe = 2 simboli', () => {
        const m = marker([riga(0, 0, 0, {}), riga(300, 2, 0, {})]);
        expect(conta(m, 'goal', 'home')).toBe(2);
    });

    it('nessuna regressione: un salto di 1 resta 1 simbolo, e un conteggio che non cambia non ne aggiunge', () => {
        const m = marker([riga(0, 0, 0, {}), riga(100, 0, 0, { hc: 1 }), riga(200, 0, 0, { hc: 1 }), riga(300, 1, 0, { hc: 1 })]);
        expect(conta(m, 'corner', 'home')).toBe(1);
        expect(conta(m, 'goal', 'home')).toBe(1);
    });

    it('un conteggio che scende e risale per una fonte in ritardo non duplica i simboli', () => {
        const m = marker([riga(0, 0, 0, {}), riga(100, 0, 0, { hc: 2 }), riga(150, 0, 0, { hc: 1 }), riga(200, 0, 0, { hc: 2 })]);
        expect(conta(m, 'corner', 'home')).toBe(2);
    });
});
