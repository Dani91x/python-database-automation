// frontend/src/lib/normalize.ts

// Types for normalized prediction data
export interface NormalizedLeague {
    id: number;
    name: string;
    country: string;
    logo: string;
    flag: string | null;
    season: number;
}

export interface GoalsByMinute {
    [key: string]: {
        total: number | null;
        percentage: string | null;
    };
}

export interface UnderOver {
    [key: string]: {
        over: number;
        under: number;
    };
}

export interface CardsByMinute {
    [key: string]: {
        total: number | null;
        percentage: string | null;
    };
}

export interface TeamLast5 {
    form: string;
    formPercent: number;
    att: string;
    attPercent: number;
    def: string;
    defPercent: number;
    goals: {
        for: { total: number; average: number };
        against: { total: number; average: number };
    };
    played: number;
}

export interface TeamLeagueStats {
    form: string;
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
            minute: GoalsByMinute;
            underOver: UnderOver;
        };
        against: {
            total: { home: number; away: number; total: number };
            average: { home: number; away: number; total: number };
            minute: GoalsByMinute;
            underOver: UnderOver;
        };
    };
    biggest: {
        streak: { wins: number; draws: number; loses: number };
        wins: { home: string | null; away: string | null };
        loses: { home: string | null; away: string | null };
        goals: {
            for: { home: number; away: number };
            against: { home: number; away: number };
        };
    };
    cleanSheet: { home: number; away: number; total: number };
    failedToScore: { home: number; away: number; total: number };
    penalty: {
        scored: { total: number; percentage: number };
        missed: { total: number; percentage: number };
        total: number;
    };
    lineups: Array<{ formation: string; played: number }>;
    cards: {
        yellow: CardsByMinute;
        red: CardsByMinute;
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
    home: string;
    homePercent: number;
    away: string;
    awayPercent: number;
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
    winner: {
        id: number;
        name: string;
        comment: string;
    } | null;
    winOrDraw: boolean;
    underOver: string;
    goals: {
        home: string;
        away: string;
    };
    advice: string;
    percent: {
        home: string;
        homePercent: number;
        draw: string;
        drawPercent: number;
        away: string;
        awayPercent: number;
    };
}

export interface NormalizedMatch {
    fixtureId: string;
    league: NormalizedLeague;
    home: NormalizedTeam;
    away: NormalizedTeam;
    comparison: NormalizedComparison;
    predictions: NormalizedPredictions;
    h2h: any[];
}

// Helpers
const parsePercent = (value: string | null | undefined): number => {
    if (!value) return 0;
    const num = parseFloat(value.replace('%', ''));
    return isNaN(num) ? 0 : num;
};

const parseFloat2 = (value: any): number => {
    if (value === null || value === undefined) return 0;
    const num = parseFloat(String(value));
    return isNaN(num) ? 0 : num;
};

const normalizeComparisonItem = (item: { home: string; away: string } | null): ComparisonItem => {
    if (!item) {
        return { home: "0%", homePercent: 0, away: "0%", awayPercent: 0 };
    }
    return {
        home: item.home || "0%",
        homePercent: parsePercent(item.home),
        away: item.away || "0%",
        awayPercent: parsePercent(item.away),
    };
};

const normalizeTeamLast5 = (last5: any): TeamLast5 => {
    return {
        form: last5?.form || "0%",
        formPercent: parsePercent(last5?.form),
        att: last5?.att || "0%",
        attPercent: parsePercent(last5?.att),
        def: last5?.def || "0%",
        defPercent: parsePercent(last5?.def),
        goals: {
            for: {
                total: last5?.goals?.for?.total ?? 0,
                average: parseFloat2(last5?.goals?.for?.average),
            },
            against: {
                total: last5?.goals?.against?.total ?? 0,
                average: parseFloat2(last5?.goals?.against?.average),
            },
        },
        played: last5?.played ?? 0,
    };
};

const normalizeUnderOver = (underOver: any): UnderOver => {
    if (!underOver) return {};
    const result: UnderOver = {};
    for (const key of Object.keys(underOver)) {
        result[key] = {
            over: underOver[key]?.over ?? 0,
            under: underOver[key]?.under ?? 0,
        };
    }
    return result;
};

const normalizeGoalsStats = (goals: any) => ({
    total: {
        home: goals?.total?.home ?? 0,
        away: goals?.total?.away ?? 0,
        total: goals?.total?.total ?? 0,
    },
    average: {
        home: parseFloat2(goals?.average?.home),
        away: parseFloat2(goals?.average?.away),
        total: parseFloat2(goals?.average?.total),
    },
    minute: goals?.minute || {},
    underOver: normalizeUnderOver(goals?.under_over),
});

const normalizeTeamLeague = (league: any): TeamLeagueStats => {
    return {
        form: league?.form || "",
        fixtures: {
            played: {
                home: league?.fixtures?.played?.home ?? 0,
                away: league?.fixtures?.played?.away ?? 0,
                total: league?.fixtures?.played?.total ?? 0,
            },
            wins: {
                home: league?.fixtures?.wins?.home ?? 0,
                away: league?.fixtures?.wins?.away ?? 0,
                total: league?.fixtures?.wins?.total ?? 0,
            },
            draws: {
                home: league?.fixtures?.draws?.home ?? 0,
                away: league?.fixtures?.draws?.away ?? 0,
                total: league?.fixtures?.draws?.total ?? 0,
            },
            loses: {
                home: league?.fixtures?.loses?.home ?? 0,
                away: league?.fixtures?.loses?.away ?? 0,
                total: league?.fixtures?.loses?.total ?? 0,
            },
        },
        goals: {
            for: normalizeGoalsStats(league?.goals?.for),
            against: normalizeGoalsStats(league?.goals?.against),
        },
        biggest: {
            streak: {
                wins: league?.biggest?.streak?.wins ?? 0,
                draws: league?.biggest?.streak?.draws ?? 0,
                loses: league?.biggest?.streak?.loses ?? 0,
            },
            wins: {
                home: league?.biggest?.wins?.home || null,
                away: league?.biggest?.wins?.away || null,
            },
            loses: {
                home: league?.biggest?.loses?.home || null,
                away: league?.biggest?.loses?.away || null,
            },
            goals: {
                for: {
                    home: league?.biggest?.goals?.for?.home ?? 0,
                    away: league?.biggest?.goals?.for?.away ?? 0,
                },
                against: {
                    home: league?.biggest?.goals?.against?.home ?? 0,
                    away: league?.biggest?.goals?.against?.away ?? 0,
                },
            },
        },
        cleanSheet: {
            home: league?.clean_sheet?.home ?? 0,
            away: league?.clean_sheet?.away ?? 0,
            total: league?.clean_sheet?.total ?? 0,
        },
        failedToScore: {
            home: league?.failed_to_score?.home ?? 0,
            away: league?.failed_to_score?.away ?? 0,
            total: league?.failed_to_score?.total ?? 0,
        },
        penalty: {
            scored: {
                total: league?.penalty?.scored?.total ?? 0,
                percentage: parsePercent(league?.penalty?.scored?.percentage),
            },
            missed: {
                total: league?.penalty?.missed?.total ?? 0,
                percentage: parsePercent(league?.penalty?.missed?.percentage),
            },
            total: league?.penalty?.total ?? 0,
        },
        lineups: (league?.lineups || []).map((l: any) => ({
            formation: l.formation || "N/D",
            played: l.played ?? 0,
        })),
        cards: {
            yellow: league?.cards?.yellow || {},
            red: league?.cards?.red || {},
        },
    };
};

const normalizeTeam = (team: any): NormalizedTeam => {
    return {
        id: team?.id ?? 0,
        name: team?.name || "N/D",
        logo: team?.logo || "",
        last5: normalizeTeamLast5(team?.last_5),
        league: normalizeTeamLeague(team?.league),
    };
};

export function normalizeMatchData(raw: any): NormalizedMatch | null {
    const main = raw?.response?.[0];
    if (!main) return null;

    const fixtureId = String(raw?.parameters?.fixture || "N/D");

    const league: NormalizedLeague = {
        id: main.league?.id ?? 0,
        name: main.league?.name || "N/D",
        country: main.league?.country || "N/D",
        logo: main.league?.logo || "",
        flag: main.league?.flag || null,
        season: main.league?.season ?? 0,
    };

    const home = normalizeTeam(main.teams?.home);
    const away = normalizeTeam(main.teams?.away);

    const comparison: NormalizedComparison = {
        form: normalizeComparisonItem(main.comparison?.form),
        att: normalizeComparisonItem(main.comparison?.att),
        def: normalizeComparisonItem(main.comparison?.def),
        poissonDistribution: normalizeComparisonItem(main.comparison?.poisson_distribution),
        h2h: normalizeComparisonItem(main.comparison?.h2h),
        goals: normalizeComparisonItem(main.comparison?.goals),
        total: normalizeComparisonItem(main.comparison?.total),
    };

    const predictions: NormalizedPredictions = {
        winner: main.predictions?.winner ? {
            id: main.predictions.winner.id ?? 0,
            name: main.predictions.winner.name || "N/D",
            comment: main.predictions.winner.comment || "",
        } : null,
        winOrDraw: main.predictions?.win_or_draw ?? false,
        underOver: main.predictions?.under_over || "N/D",
        goals: {
            home: main.predictions?.goals?.home || "N/D",
            away: main.predictions?.goals?.away || "N/D",
        },
        advice: main.predictions?.advice || "No advice available",
        percent: {
            home: main.predictions?.percent?.home || "0%",
            homePercent: parsePercent(main.predictions?.percent?.home),
            draw: main.predictions?.percent?.draw || "0%",
            drawPercent: parsePercent(main.predictions?.percent?.draw),
            away: main.predictions?.percent?.away || "0%",
            awayPercent: parsePercent(main.predictions?.percent?.away),
        },
    };

    return {
        fixtureId,
        league,
        home,
        away,
        comparison,
        predictions,
        h2h: main.h2h || [],
    };
}
