import { TeamLast5 } from "@/lib/normalizePrediction";
import { Activity, Shield, Swords } from "lucide-react";

interface Last5CardProps {
  last5: TeamLast5;
  side: 'home' | 'away';
}

export function Last5Card({ last5, side }: Last5CardProps) {
  const isHome = side === 'home';
  const accentColor = isHome ? 'primary' : 'secondary';

  return (
    <div className="glass-card p-5">
      <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
        <Activity className="w-4 h-4" />
        Last 5 Matches Summary
      </h4>
      
      <div className="grid grid-cols-3 gap-4 mb-5">
        {/* Form */}
        <div className="text-center">
          <div className={`stat-value text-2xl ${isHome ? 'text-gradient-primary' : 'text-gradient-secondary'}`}>
            {last5.form}
          </div>
          <div className="stat-label mt-1">Form</div>
          <div className="progress-bar mt-2">
            <div 
              className={`progress-bar-fill ${isHome ? 'progress-bar-fill-primary' : 'progress-bar-fill-secondary'}`}
              style={{ width: `${last5.formPercent}%` }}
            />
          </div>
        </div>

        {/* Attack */}
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <Swords className="w-4 h-4 text-neon-orange" />
          </div>
          <div className="stat-value text-2xl">{last5.att}</div>
          <div className="stat-label mt-1">Attack</div>
          <div className="progress-bar mt-2">
            <div 
              className="progress-bar-fill"
              style={{ 
                width: `${last5.attPercent}%`,
                background: 'linear-gradient(90deg, hsl(var(--neon-orange)), hsl(var(--accent)))',
                boxShadow: '0 0 10px hsl(var(--neon-orange) / 0.5)'
              }}
            />
          </div>
        </div>

        {/* Defense */}
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <Shield className="w-4 h-4 text-neon-blue" />
          </div>
          <div className="stat-value text-2xl">{last5.def}</div>
          <div className="stat-label mt-1">Defense</div>
          <div className="progress-bar mt-2">
            <div 
              className="progress-bar-fill"
              style={{ 
                width: `${last5.defPercent}%`,
                background: 'linear-gradient(90deg, hsl(var(--neon-blue)), hsl(var(--primary)))',
                boxShadow: '0 0 10px hsl(var(--neon-blue) / 0.5)'
              }}
            />
          </div>
        </div>
      </div>

      {/* Goals Comparison */}
      <div className="border-t border-border/50 pt-4">
        <h5 className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Goals (Last 5)
        </h5>
        <div className="grid grid-cols-2 gap-4">
          <div className="glass-card p-3 rounded-lg bg-neon-green/5 border-neon-green/20">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-muted-foreground">Goals For</span>
              <span className="font-display text-xl font-bold text-neon-green">{last5.goals.for.total}</span>
            </div>
            <div className="text-xs text-muted-foreground">
              Avg: <span className="text-neon-green font-semibold">{last5.goals.for.average.toFixed(1)}</span> per match
            </div>
          </div>
          <div className="glass-card p-3 rounded-lg bg-destructive/5 border-destructive/20">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-muted-foreground">Goals Against</span>
              <span className="font-display text-xl font-bold text-destructive">{last5.goals.against.total}</span>
            </div>
            <div className="text-xs text-muted-foreground">
              Avg: <span className="text-destructive font-semibold">{last5.goals.against.average.toFixed(1)}</span> per match
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 text-xs text-muted-foreground text-center">
        Played: <span className="font-semibold text-foreground">{last5.played}</span> matches
      </div>
    </div>
  );
}
