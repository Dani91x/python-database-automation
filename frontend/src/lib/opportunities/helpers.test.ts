import { describe, it, expect } from 'vitest';
import {
    lineFromType,
    isDraw, isYes, isNo, isOver, isUnder,
    matchOddsTriple,
    correctScoreKey, selectionMatchesScore,
    isMatchOdds, isOverUnder, isBtts, isCorrectScore,
    decideWinner,
} from './helpers';
import type { SelLite } from './types';

describe('lineFromType', () => {
    it('parses OVER_UNDER lines', () => {
        expect(lineFromType('OVER_UNDER_25')).toBe(2.5);
        expect(lineFromType('OVER_UNDER_05')).toBe(0.5);
        expect(lineFromType('OVER_UNDER_35')).toBe(3.5);
    });
    it('returns null when no line', () => {
        expect(lineFromType('MATCH_ODDS')).toBeNull();
    });
});

describe('selection predicates (identical to replay-pnl)', () => {
    it('isDraw', () => {
        expect(isDraw('The Draw')).toBe(true);
        expect(isDraw('Pareggio')).toBe(true);
        expect(isDraw('Team A')).toBe(false);
        expect(isDraw(null)).toBe(false);
    });
    it('isYes / isNo', () => {
        expect(isYes('Yes')).toBe(true);
        expect(isYes('Sì')).toBe(true);
        expect(isYes('Si')).toBe(true);
        expect(isNo('No')).toBe(true);
        expect(isNo('Yes')).toBe(false);
    });
    it('isOver / isUnder', () => {
        expect(isOver('Over 2.5 Goals')).toBe(true);
        expect(isUnder('Under 2.5 Goals')).toBe(true);
        expect(isOver('Under 2.5 Goals')).toBe(false);
    });
});

describe('matchOddsTriple', () => {
    const sels: SelLite[] = [
        { selection_id: 2, name: 'Team B', sort_priority: 2 },
        { selection_id: 1, name: 'Team A', sort_priority: 1 },
        { selection_id: 3, name: 'The Draw', sort_priority: 3 },
    ];
    it('home=lowest sort_priority non-draw, away=next, draw=draw', () => {
        const t = matchOddsTriple(sels);
        expect(t.home?.selection_id).toBe(1);
        expect(t.away?.selection_id).toBe(2);
        expect(t.draw?.selection_id).toBe(3);
    });
});

describe('correct score key', () => {
    it('builds h-a key', () => {
        expect(correctScoreKey(2, 1)).toBe('2-1');
    });
    it('matches selection names ignoring whitespace', () => {
        expect(selectionMatchesScore({ selection_id: 9, name: '2 - 1' }, 2, 1)).toBe(true);
        expect(selectionMatchesScore({ selection_id: 9, name: '2-0' }, 2, 1)).toBe(false);
    });
});

describe('market type guards', () => {
    it('classifies market types', () => {
        expect(isMatchOdds({ market_type: 'MATCH_ODDS' })).toBe(true);
        expect(isOverUnder({ market_type: 'OVER_UNDER_25' })).toBe(true);
        expect(isBtts({ market_type: 'BOTH_TEAMS_TO_SCORE' })).toBe(true);
        expect(isCorrectScore({ market_type: 'CORRECT_SCORE' })).toBe(true);
        expect(isMatchOdds({ market_type: 'CORRECT_SCORE' })).toBe(false);
    });
});

describe('decideWinner re-export stays consistent with replay-pnl', () => {
    const mo = {
        market_type: 'MATCH_ODDS',
        selections: [
            { selection_id: 1, name: 'Team A', sort_priority: 1 },
            { selection_id: 2, name: 'Team B', sort_priority: 2 },
            { selection_id: 3, name: 'The Draw', sort_priority: 3 },
        ],
    };
    it('home wins → home id (lower sort_priority)', () => {
        expect(decideWinner(mo, { home: 2, away: 1, finished: true })).toBe(1);
    });
    it('away wins → away id', () => {
        expect(decideWinner(mo, { home: 0, away: 2, finished: true })).toBe(2);
    });
    it('draw → draw id', () => {
        expect(decideWinner(mo, { home: 1, away: 1, finished: true })).toBe(3);
    });
    it('not finished → null', () => {
        expect(decideWinner(mo, { home: 1, away: 0, finished: false })).toBeNull();
    });
    it('OVER_UNDER_25 over the line decided early', () => {
        const ou = {
            market_type: 'OVER_UNDER_25',
            selections: [
                { selection_id: 10, name: 'Over 2.5 Goals' },
                { selection_id: 11, name: 'Under 2.5 Goals' },
            ],
        };
        expect(decideWinner(ou, { home: 2, away: 1, finished: false })).toBe(10);
    });
});
