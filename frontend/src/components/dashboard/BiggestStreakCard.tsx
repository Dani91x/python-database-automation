import { TeamLeagueStats } from "@/lib/normalizePrediction";
import { Trophy, TrendingUp, TrendingDown, Flame } from "lucide-react";

interface BiggestStreakCardProps {
  biggest: TeamLeagueStats['biggest'];
  side: 'home' | 'away';
}

export function BiggestStreakCard({ biggest, side }: BiggestStreakCardProps) {
  return (
    <div className="glass-card p-5">
      <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
        <Trophy className="w-4 h-4 text-accent" />
        Records & Streaks
      </h4>

      {/* Streaks */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="glass-card p-3 rounded-lg text-center bg-neon-green/5 border-neon-green/20">
          <Flame className="w-4 h-4 text-neon-green mx-auto mb-1" />
          <div className="font-display text-2xl font-bold text-neon-green">{biggest.streak.wins}</div>
          <div className="stat-label">Win Streak</div>
        </div>
        <div className="glass-card p-3 rounded-lg text-center bg-accent/5 border-accent/20">
          <TrendingUp className="w-4 h-4 text-accent mx-auto mb-1" />
          <div className="font-display text-2xl font-bold text-accent">{biggest.streak.draws}</div>
          <div className="stat-label">Draw Streak</div>
        </div>
        <div className="glass-card p-3 rounded-lg text-center bg-destructive/5 border-destructive/20">
          <TrendingDown className="w-4 h-4 text-destructive mx-auto mb-1" />
          <div className="font-display text-2xl font-bold text-destructive">{biggest.streak.loses}</div>
          <div className="stat-label">Loss Streak</div>
        </div>
      </div>

      {/* Biggest Wins/Loses */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h5 className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
            Biggest Wins
          </h5>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Home</span>
              <span className="font-display font-bold text-neon-green">
                {biggest.wins.home || 'N/D'}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Away</span>
              <span className="font-display font-bold text-neon-green">
                {biggest.wins.away || 'N/D'}
              </span>
            </div>
          </div>
        </div>
        <div>
          <h5 className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
            Biggest Losses
          </h5>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Home</span>
              <span className="font-display font-bold text-destructive">
                {biggest.loses.home || 'N/D'}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Away</span>
              <span className="font-display font-bold text-destructive">
                {biggest.loses.away || 'N/D'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Most Goals */}
      <div className="mt-4 pt-4 border-t border-border/50">
        <h5 className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
          Most Goals in a Match
        </h5>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-muted-foreground mb-1">Scored</div>
            <div className="flex gap-2">
              <span className="text-sm">Home: <span className="font-display font-bold text-neon-green">{biggest.goals.for.home}</span></span>
              <span className="text-sm">Away: <span className="font-display font-bold text-neon-green">{biggest.goals.for.away}</span></span>
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Conceded</div>
            <div className="flex gap-2">
              <span className="text-sm">Home: <span className="font-display font-bold text-destructive">{biggest.goals.against.home}</span></span>
              <span className="text-sm">Away: <span className="font-display font-bold text-destructive">{biggest.goals.against.away}</span></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
