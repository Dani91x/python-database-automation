import { NormalizedTeam } from "@/lib/normalize";
import { FormString } from "./FormString";
import { Last5Card } from "./Last5Card";
import { GoalsTabs } from "./GoalsTabs";
import { CardsByMinute } from "./CardsByMinute";
import { BiggestStreakCard } from "./BiggestStreakCard";
import { LineupsCard } from "./LineupsCard";
import { FixturesSummary } from "./FixturesSummary";
import { PenaltyCard } from "./PenaltyCard";
import { CleanSheetCard } from "./CleanSheetCard";
import { motion } from "framer-motion";

interface TeamPanelProps {
    team: NormalizedTeam;
    side: 'home' | 'away';
}

export function TeamPanel({ team, side }: TeamPanelProps) {
    const isHome = side === 'home';
    const accentColor = isHome ? 'emerald' : 'amber';
    const borderClass = isHome ? 'border-emerald-500/20' : 'border-amber-500/20';
    const badgeClass = isHome ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400';

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: isHome ? 0.1 : 0.2 }}
            className="flex-1 w-full space-y-6"
        >
            {/* 1. Identity Header Card */}
            <div className={`p-4 md:p-6 rounded-2xl border bg-black/40 backdrop-blur-md relative overflow-hidden group ${borderClass}`}>
                {/* Accent Glow */}
                <div className={`absolute -inset-1 bg-${accentColor}-500/5 blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-700`} />

                <div className="relative flex items-center gap-4 md:gap-6">
                    <div className="w-16 h-16 md:w-20 md:h-20 p-2 bg-white/5 rounded-2xl shrink-0 flex items-center justify-center border border-white/5">
                        <img src={team.logo} alt={team.name} className="w-full h-full object-contain filter drop-shadow-md" />
                    </div>
                    <div className="min-w-0">
                        <div className="mb-1 md:mb-2 text-left">
                            <span className={`${badgeClass} text-[8px] md:text-[9px] font-black px-2 md:px-3 py-0.5 md:py-1 rounded-full border border-current/20 italic tracking-widest`}>
                                {isHome ? "HOME" : "AWAY"}
                            </span>
                        </div>
                        <h3 className="text-xl md:text-3xl font-black font-display text-white uppercase tracking-tighter drop-shadow-sm leading-none truncate">
                            {team.name}
                        </h3>
                        <div className="text-[9px] md:text-[10px] font-black text-white/20 mt-1 md:mt-2 tracking-widest uppercase text-left">
                            ID: <span className="text-white/40">{team.id}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* 2. League Form */}
            <FormString form={team.league.form} />

            {/* 3. Last 5 Summary & Goals */}
            <Last5Card last5={team.last5} />

            {/* 4. Advanced Goals Analytics */}
            <GoalsTabs stats={team.league} />

            {/* 5. Cards Breakdown */}
            <CardsByMinute cards={team.league.cards} />

            {/* 6. Records & Streaks */}
            <BiggestStreakCard biggest={team.league.biggest} />

            {/* 7. Tactical Summary */}
            <LineupsCard lineups={team.league.lineups} />

            {/* 8. Season Fixtures Overview */}
            <FixturesSummary fixtures={team.league.fixtures} />

            {/* 9. Penalty Stats */}
            <PenaltyCard penalty={team.league.penalty} />

            {/* 10. Defensive Consistency */}
            <CleanSheetCard
                cleanSheet={team.league.cleanSheet}
                failedToScore={team.league.failedToScore}
            />
        </motion.div>
    );
}
