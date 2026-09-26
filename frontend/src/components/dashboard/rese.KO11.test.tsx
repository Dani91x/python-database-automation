// FIX-B (26/09/2026) KO11: casi limite di resa della scheda partita.
// Partita D del referto (1528882 Turkiye-France): predictions.goals {home:null, away:null},
// last_5.played = 0, league.goals.for.minute[*].total = null.
// Finti con le chiavi/tipi di lib/normalizePrediction.ts (TeamLast5, TeamLeagueStats,
// NormalizedPredictions): stessa forma che normalizePredictionJson produce dal raw_json.
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { NormalizedPredictions, NormalizedTeam, TeamLeagueStats, TeamLast5 } from '@/lib/normalize';
import { PredictionsCard } from './PredictionsCard';
import { Last5Card } from './Last5Card';
import { GoalsTabs } from './GoalsTabs';

const FASCE = ['0-15', '16-30', '31-45', '46-60', '61-75', '76-90', '91-105', '106-120'];
const minuti = (v: number | null) => Object.fromEntries(FASCE.map(k => [k, { total: v, percentage: v === null ? null : '10%' }]));
const uo = { '0.5': { over: 9, under: 1 }, '1.5': { over: 7, under: 3 }, '2.5': { over: 4, under: 6 }, '3.5': { over: 2, under: 8 }, '4.5': { over: 0, under: 10 } };
const t3 = (a: number, b: number) => ({ home: a, away: b, total: a + b });

function stats(min: number | null): TeamLeagueStats {
    return {
        form: 'WDLWW',
        fixtures: { played: t3(5, 5), wins: t3(3, 1), draws: t3(1, 2), loses: t3(1, 2) },
        goals: {
            for: { total: t3(8, 5), average: { home: 1.6, away: 1, total: 1.3 }, minute: minuti(min), under_over: uo },
            against: { total: t3(4, 6), average: { home: 0.8, away: 1.2, total: 1 }, minute: minuti(min), under_over: uo },
        },
        biggest: { streak: { wins: 3, draws: 1, loses: 2 }, wins: { home: '3-0', away: '1-2' }, loses: { home: '0-2', away: '3-1' },
                   goals: { for: { home: 3, away: 2 }, against: { home: 2, away: 3 } } },
        cleanSheet: t3(2, 1), failedToScore: t3(1, 2),
        penalty: { scored: { total: 2, percentage: '100%' }, missed: { total: 0, percentage: '0%' }, total: 2 },
        lineups: [], cards: { yellow: minuti(null), red: minuti(null) },
    };
}
const last5 = (played: number, gf: number, ga: number): TeamLast5 => ({ form: 60, att: 50, def: 40, goalsFor: gf, goalsAgainst: ga, played });
const team = (l5: TeamLast5): NormalizedTeam => ({ id: 777, name: 'Turkiye', logo: '', last5: l5, league: stats(null) });
function pred(home: string | null, away: string | null): NormalizedPredictions {
    return {
        winner: null, winOrDraw: false, underOver: null, goals: { home, away }, advice: 'No predictions available',
        percent: { home: '35%', draw: '35%', away: '30%', homePercent: 35, drawPercent: 35, awayPercent: 30 },
    };
}

describe('PredictionsCard - gol previsti (U0022)', () => {
    it('NULL -> "—", mai "0"', () => {
        const s = render(<PredictionsCard predictions={pred(null, null)} home={team(last5(5, 1, 1))} away={team(last5(5, 1, 1))} />);
        expect(s.container.textContent).toContain('Predicted: Home — / Away —');
        expect(s.container.textContent).not.toContain('Home 0 / Away 0');
    });
    it('valori veri invariati (partita A: -2.5 / -2.5)', () => {
        const s = render(<PredictionsCard predictions={pred('-2.5', '-2.5')} home={team(last5(5, 1, 1))} away={team(last5(5, 1, 1))} />);
        expect(s.container.textContent).toContain('Predicted: Home -2.5 / Away -2.5');
    });
});

describe('Last5Card - medie (U0026)', () => {
    it('played=0 -> nessun NaN a video', () => {
        const s = render(<Last5Card last5={last5(0, 0, 0)} />);
        expect(s.container.textContent).not.toContain('NaN');
    });
    it('partita A: 10 gol in 5 = 2.0, 9 in 5 = 1.8', () => {
        const s = render(<Last5Card last5={last5(5, 10, 9)} />);
        expect(s.container.textContent).toContain('2.0');
        expect(s.container.textContent).toContain('1.8');
    });
});

describe('GoalsTabs - gol per minuto (U0029)', () => {
    it('tutti i minuti NULL: avviso "dato assente", non un grafico di zeri', () => {
        const s = render(<GoalsTabs stats={stats(null)} />);
        expect(s.getByTestId('minuti-assenti').textContent).toMatch(/assente/i);
    });
    it('minuti presenti: nessun avviso', () => {
        const s = render(<GoalsTabs stats={stats(2)} />);
        expect(s.queryByTestId('minuti-assenti')).toBeNull();
    });
});
