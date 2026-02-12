import { TeamLeagueStats } from "@/lib/normalizePrediction";
import { Target, CheckCircle, XCircle } from "lucide-react";

interface PenaltyCardProps {
  penalty: TeamLeagueStats['penalty'];
  side: 'home' | 'away';
}

export function PenaltyCard({ penalty, side }: PenaltyCardProps) {
  const isHome = side === 'home';
  const successRate = penalty.total > 0 ? (penalty.scored.total / penalty.total) * 100 : 0;

  return (
    <div className="glass-card p-5">
      <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
        <Target className="w-4 h-4" />
        Penalty Stats
      </h4>

      {/* Total */}
      <div className="text-center mb-4">
        <div className="font-display text-3xl font-bold">{penalty.total}</div>
        <div className="stat-label">Total Penalties</div>
      </div>

      {/* Success Rate Arc */}
      <div className="relative h-4 rounded-full overflow-hidden bg-muted/30 mb-4">
        <div 
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-neon-green to-neon-green/70"
          style={{ width: `${successRate}%` }}
        />
        <div 
          className="absolute inset-y-0 right-0 rounded-full bg-gradient-to-l from-destructive to-destructive/70"
          style={{ width: `${100 - successRate}%` }}
        />
      </div>

      {/* Scored vs Missed */}
      <div className="grid grid-cols-2 gap-4">
        <div className="glass-card p-3 rounded-lg text-center bg-neon-green/5 border-neon-green/20">
          <CheckCircle className="w-5 h-5 text-neon-green mx-auto mb-1" />
          <div className="font-display text-xl font-bold text-neon-green">{penalty.scored.total}</div>
          <div className="stat-label">Scored</div>
          <div className="text-xs text-neon-green mt-1">{penalty.scored.percentage}%</div>
        </div>
        <div className="glass-card p-3 rounded-lg text-center bg-destructive/5 border-destructive/20">
          <XCircle className="w-5 h-5 text-destructive mx-auto mb-1" />
          <div className="font-display text-xl font-bold text-destructive">{penalty.missed.total}</div>
          <div className="stat-label">Missed</div>
          <div className="text-xs text-destructive mt-1">{penalty.missed.percentage}%</div>
        </div>
      </div>
    </div>
  );
}
