import { NormalizedTeam } from "@/lib/normalizePrediction";
import { Last5Card } from "./Last5Card";
import { GoalsTabs } from "./GoalsTabs";
import { CardsByMinute } from "./CardsByMinute";
import { BiggestStreakCard } from "./BiggestStreakCard";
import { LineupsCard } from "./LineupsCard";
import { FixturesSummary } from "./FixturesSummary";
import { PenaltyCard } from "./PenaltyCard";
import { CleanSheetCard } from "./CleanSheetCard";
import { FormString } from "./FormString";

interface TeamPanelProps {
  team: NormalizedTeam;
  side: 'home' | 'away';
}

export function TeamPanel({ team, side }: TeamPanelProps) {
  const isHome = side === 'home';
  
  return (
    <div className={`space-y-4 animate-fade-in ${isHome ? 'animate-slide-in-left' : 'animate-slide-in-right'}`}>
      {/* Team Identity Card */}
      <div className={`glass-card p-6 ${isHome ? 'neon-glow-cyan' : 'neon-glow-magenta'}`}>
        <div className="flex items-center gap-4">
          <div className={`w-16 h-16 rounded-xl glass-card p-2 ${isHome ? 'border-team-home/30' : 'border-neon-magenta/30'}`}>
            <img 
              src={team.logo} 
              alt={team.name}
              className="w-full h-full object-contain"
            />
          </div>
          <div className="flex-1">
            <span className={isHome ? 'home-badge' : 'away-badge'}>
              {isHome ? 'HOME' : 'AWAY'}
            </span>
            <h3 className={`font-display text-xl lg:text-2xl font-bold mt-1 ${isHome ? 'neon-text-cyan' : 'neon-text-magenta'}`}>
              {team.name}
            </h3>
            <p className="text-sm text-muted-foreground font-mono">ID: {team.id}</p>
          </div>
        </div>
      </div>

      {/* Form String */}
      <FormString form={team.league.form} side={side} />

      {/* Last 5 Summary */}
      <Last5Card last5={team.last5} side={side} />

      {/* Goals Tabs */}
      <GoalsTabs goals={team.league.goals} side={side} />

      {/* Cards by Minute */}
      <CardsByMinute cards={team.league.cards} side={side} />

      {/* Biggest & Streak */}
      <BiggestStreakCard biggest={team.league.biggest} side={side} />

      {/* Lineups */}
      <LineupsCard lineups={team.league.lineups} side={side} />

      {/* Fixtures Summary */}
      <FixturesSummary fixtures={team.league.fixtures} side={side} />

      {/* Penalty */}
      <PenaltyCard penalty={team.league.penalty} side={side} />

      {/* Clean Sheet & Failed to Score */}
      <CleanSheetCard 
        cleanSheet={team.league.cleanSheet} 
        failedToScore={team.league.failedToScore} 
        side={side} 
      />
    </div>
  );
}
