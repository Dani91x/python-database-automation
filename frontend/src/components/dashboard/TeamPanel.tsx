import { NormalizedTeam } from "@/lib/normalize";
import { FormString } from "./FormString";
import { Last5Card } from "./Last5Card";
import { GoalsTabs } from "./GoalsTabs";
import { LineupsCard } from "./LineupsCard";
import { CardsByMinute } from "./CardsByMinute";
import { BiggestStreakCard } from "./BiggestStreakCard";
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
    const borderColor = isHome ? 'border-neon-cyan/20' : 'border-neon-magenta/20';
    const textColor = isHome ? 'text-neon-cyan' : 'text-neon-magenta';

    return (
        <motion.div
            initial={{ opacity: 0, x: isHome ? -30 : 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: isHome ? 0.1 : 0.2 }}
            className="flex-1 w-full min-w-[300px]"
        >
            {/* Identity Header */}
            <div className={`flex items-center gap-4 mb-6 p-4 rounded-xl border bg-black/20 ${borderColor}`}>
                <div className="w-16 h-16 p-2 bg-white/5 rounded-full shrink-0">
                    <img src={team.logo} alt={team.name} className="w-full h-full object-contain" />
                </div>
                <div>
                    <div className={`text-xs font-black uppercase tracking-widest mb-1 ${textColor}`}>
                        {isHome ? "HOME TEAM" : "AWAY TEAM"}
                    </div>
                    <h3 className="text-2xl font-orbitron font-bold text-white leading-none">{team.name}</h3>
                    <div className="mt-2">
                        <FormString form={team.league.form} />
                    </div>
                </div>
            </div>

            {/* Sub Components Stack */}
            <div className="space-y-6">
                <Last5Card last5={team.last5} />
                <FixturesSummary fixtures={team.league.fixtures} />
                <GoalsTabs stats={team.league} side={side} />
                <BiggestStreakCard biggest={team.league.biggest} />
                <LineupsCard lineups={team.league.lineups} />
                <CardsByMinute cards={team.league.cards} />
                <PenaltyCard penalty={team.league.penalty} />
                <CleanSheetCard
                    cleanSheet={team.league.cleanSheet}
                    failedToScore={team.league.failedToScore}
                />
            </div>
        </motion.div>
    );
}
