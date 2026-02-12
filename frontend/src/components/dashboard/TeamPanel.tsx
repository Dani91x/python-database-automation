/* eslint-disable @next/next/no-img-element */
// frontend/src/components/dashboard/TeamPanel.tsx
import { NormalizedTeam } from "@/lib/normalize";
import {
    Last5Card,
    GoalsTabs,
    CardsByMinute,
    BiggestStreakCard,
    LineupsCard,
    FixturesSummary,
    PenaltyCard,
    FormString
} from "./sub-components";
import { cn } from "@/components/ui/shadcn-mini";

interface TeamPanelProps {
    team: NormalizedTeam;
    side: 'home' | 'away';
}

export function TeamPanel({ team, side }: TeamPanelProps) {
    const isHome = side === 'home';

    return (
        <div className={cn(
            "space-y-6 flex flex-col",
            isHome ? "lg:pr-4" : "lg:pl-4"
        )}>
            {/* Team Identity Card */}
            <div className={cn(
                "glass-panel p-8 rounded-[2rem] border-white/10 relative overflow-hidden group",
                isHome ? "hover:border-brand-orange/30" : "hover:border-neon-cyan/30"
            )}>
                <div className="flex items-center gap-6">
                    <div className={cn(
                        "w-20 h-20 rounded-2xl glass-panel p-4 flex items-center justify-center relative",
                        isHome ? "border-brand-orange/20" : "border-neon-cyan/20"
                    )}>
                        <img
                            src={team.logo}
                            alt={team.name}
                            className="w-full h-full object-contain"
                        />
                    </div>
                    <div className="flex-1">
                        <span className={cn(
                            "text-[10px] font-black tracking-[0.2em] uppercase px-2 py-0.5 rounded-full",
                            isHome ? "bg-brand-orange/10 text-brand-orange" : "bg-neon-cyan/10 text-neon-cyan"
                        )}>
                            {isHome ? 'Host' : 'Visitor'}
                        </span>
                        <h3 className="text-3xl font-black mt-2 tracking-tighter">
                            {team.name}
                        </h3>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest mt-1 opacity-50">SQUAD ID: {team.id}</p>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-1 gap-4">
                {/* Row 1: Form & Overview */}
                <div className="grid grid-cols-1 gap-4">
                    <FormString form={team.league.form} side={side} />
                    <Last5Card last5={team.last5} side={side} />
                </div>

                {/* Row 2: Goals & Cards */}
                <div className="grid grid-cols-1 gap-4">
                    <GoalsTabs goals={team.league.goals} side={side} />
                    <CardsByMinute cards={team.league.cards} side={side} />
                </div>

                {/* Row 3: History & Context */}
                <div className="grid grid-cols-1 gap-4">
                    <FixturesSummary fixtures={team.league.fixtures} />
                    <BiggestStreakCard biggest={team.league.biggest} side={side} />
                </div>

                {/* Row 4: Tactical */}
                <div className="grid grid-cols-1 gap-4">
                    <LineupsCard lineups={team.league.lineups} />
                    <PenaltyCard penalty={team.league.penalty} />
                </div>
            </div>
        </div>
    );
}
