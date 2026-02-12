/* eslint-disable @typescript-eslint/no-explicit-any */

export interface NormalizedLeague {
    id: number;
    name: string;
    country: string;
    logo: string;
    flag: string | null;
    season: number;
}

export interface TeamLast5 {
    form: number; // Converted from "50%" to 50
    att: number;
    def: number;
    goalsFor: number;
    goalsAgainst: number;
    played: number;
}

export interface TeamLeagueStats {
    form: string; // "WWLDD" etc
    fixtures: {
        played: { home: number; away: number; total: number };
        wins: { home: number; away: number; total: number };
        draws: { home: number; away: number; total: number };
        loses: { home: number; away: number; total: number };
    };
    goals: {
        for: {
            total: { home: number; away: number; total: number };
            average: { home: number; away: number; total: number };
            minute: Record<string, { total: number | null; percentage: string | null }>;
            under_over: Record<string, { over: number; under: number }>;
        };
        against: {
            total: { home: number; away: number; total: number };
            average: { home: number; away: number; total: number };
            minute: Record<string, { total: number | null; percentage: string | null }>;
            under_over: Record<string, { over: number; under: number }>;
        };
    };
    biggest: {
        streak: { wins: number; draws: number; loses: number };
        wins: { home: string; away: string };
        loses: { home: string; away: string };
        goals: {
            for: { home: number; away: number };
            against: { home: number; away: number };
        };
    };
    cleanSheet: { home: number; away: number; total: number };
    failedToScore: { home: number; away: number; total: number };
    penalty: {
        scored: { total: number; percentage: string };
        missed: { total: number; percentage: string };
        total: number;
    };
    lineups: { formation: string; played: number }[];
    cards: {
        yellow: Record<string, { total: number | null; percentage: string | null }>;
        red: Record<string, { total: number | null; percentage: string | null }>;
    };
}

export interface NormalizedTeam {
    id: number;
    name: string;
    logo: string;
    last5: TeamLast5;
    league: TeamLeagueStats;
}

export interface ComparisonItem {
    home: number; // Converted from "40%" to 40
    away: number;
}

export interface NormalizedComparison {
    form: ComparisonItem;
    att: ComparisonItem;
    def: ComparisonItem;
    poissonDistribution: ComparisonItem;
    h2h: ComparisonItem;
    goals: ComparisonItem;
    total: ComparisonItem;
}

export interface NormalizedPredictions {
    winner: { id: number; name: string; comment: string } | null;
    winOrDraw: boolean;
    underOver: string | null;
    goals: { home: string | null; away: string | null };
    advice: string;
    percent: {
        home: string; // "10%"
        draw: string; // "45%"
        away: string; // "45%"
        homePercent: number; // 10
        drawPercent: number; // 45
        awayPercent: number; // 45
    };
}

export interface NormalizedData {
    league: NormalizedLeague;
    home: NormalizedTeam;
    away: NormalizedTeam;
    comparison: NormalizedComparison;
    predictions: NormalizedPredictions;
    h2h: any[];
    fixtureId?: string;
}

function parsePercentage(val: string | undefined | null): number {
    if (!val) return 0;
    return parseFloat(val.replace('%', ''));
}

function parseFloatSafe(val: string | number | undefined | null): number {
    if (typeof val === 'number') return val;
    if (!val) return 0;
    return parseFloat(val);
}

export function normalizePredictionJson(raw: any, fixtureId?: string): NormalizedData | null {
    if (!raw || !raw.response || raw.response.length === 0) return null;

    const data = raw.response[0];
    const liga = data.league;
    const home = data.teams.home;
    const away = data.teams.away;
    const comp = data.comparison;
    const pred = data.predictions;
    const h2h = data.h2h || [];

    // 1. Normalize League
    const normalizedLeague: NormalizedLeague = {
        id: liga.id,
        name: liga.name,
        country: liga.country,
        logo: liga.logo,
        flag: liga.flag,
        season: liga.season
    };

    // 2. Helper for Team Stats
    const normalizeTeam = (t: any): NormalizedTeam => {
        return {
            id: t.id,
            name: t.name,
            logo: t.logo,
            last5: {
                form: parsePercentage(t.last_5.form),
                att: parsePercentage(t.last_5.att),
                def: parsePercentage(t.last_5.def),
                goalsFor: t.last_5.goals.for.total,
                goalsAgainst: t.last_5.goals.against.total,
                played: t.last_5.played
            },
            league: {
                form: t.league.form,
                fixtures: t.league.fixtures,
                goals: {
                    for: {
                        ...t.league.goals.for,
                        average: {
                            home: parseFloatSafe(t.league.goals.for.average.home),
                            away: parseFloatSafe(t.league.goals.for.average.away),
                            total: parseFloatSafe(t.league.goals.for.average.total),
                        }
                    },
                    against: {
                        ...t.league.goals.against,
                        average: {
                            home: parseFloatSafe(t.league.goals.against.average.home),
                            away: parseFloatSafe(t.league.goals.against.average.away),
                            total: parseFloatSafe(t.league.goals.against.average.total),
                        }
                    }
                },
                biggest: t.league.biggest,
                cleanSheet: {
                    home: t.league.clean_sheet.home,
                    away: t.league.clean_sheet.away,
                    total: t.league.clean_sheet.total
                },
                failedToScore: {
                    home: t.league.failed_to_score.home,
                    away: t.league.failed_to_score.away,
                    total: t.league.failed_to_score.total
                },
                penalty: t.league.penalty,
                lineups: t.league.lineups,
                cards: t.league.cards
            }
        };
    };

    const normalizedHome = normalizeTeam(home);
    const normalizedAway = normalizeTeam(away);

    // 3. Normalize Comparison
    // Fallbacks to 0 if data missing
    const normalizeCompItem = (c: any): ComparisonItem => {
        return {
            home: parsePercentage(c?.home),
            away: parsePercentage(c?.away)
        };
    };

    const normalizedComparison: NormalizedComparison = {
        form: normalizeCompItem(comp?.form),
        att: normalizeCompItem(comp?.att),
        def: normalizeCompItem(comp?.def),
        poissonDistribution: normalizeCompItem(comp?.poisson_distribution),
        h2h: normalizeCompItem(comp?.h2h),
        goals: normalizeCompItem(comp?.goals),
        total: normalizeCompItem(comp?.total),
    };

    // 4. Normalize Predictions
    const normalizedPredictions: NormalizedPredictions = {
        winner: pred.winner,
        winOrDraw: pred.win_or_draw,
        underOver: pred.under_over,
        goals: pred.goals,
        advice: pred.advice,
        percent: {
            home: pred.percent.home,
            draw: pred.percent.draw,
            away: pred.percent.away,
            homePercent: parsePercentage(pred.percent.home),
            drawPercent: parsePercentage(pred.percent.draw),
            awayPercent: parsePercentage(pred.percent.away),
        }
    };

    return {
        league: normalizedLeague,
        home: normalizedHome,
        away: normalizedAway,
        comparison: normalizedComparison,
        predictions: normalizedPredictions,
        h2h: h2h,
        fixtureId: fixtureId
    };
}
