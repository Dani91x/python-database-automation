import { Users } from "lucide-react";

interface LineupsCardProps {
  lineups: Array<{ formation: string; played: number }>;
  side: 'home' | 'away';
}

export function LineupsCard({ lineups, side }: LineupsCardProps) {
  const isHome = side === 'home';
  const sortedLineups = [...lineups].sort((a, b) => b.played - a.played);
  const totalPlayed = sortedLineups.reduce((acc, l) => acc + l.played, 0);

  if (lineups.length === 0) {
    return (
      <div className="glass-card p-5">
        <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
          <Users className="w-4 h-4" />
          Formations
        </h4>
        <p className="text-muted-foreground text-sm">N/D</p>
      </div>
    );
  }

  return (
    <div className="glass-card p-5">
      <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
        <Users className="w-4 h-4" />
        Formations
      </h4>

      {/* Most Used */}
      {sortedLineups[0] && (
        <div className={`glass-card p-4 rounded-lg mb-4 ${isHome ? 'bg-primary/5 border-primary/30' : 'bg-secondary/5 border-secondary/30'}`}>
          <div className="text-xs text-muted-foreground mb-1">Most Used Formation</div>
          <div className="flex items-center justify-between">
            <span className={`font-display text-2xl font-bold ${isHome ? 'text-primary' : 'text-secondary'}`}>
              {sortedLineups[0].formation}
            </span>
            <span className="text-sm text-muted-foreground">
              {sortedLineups[0].played} matches ({totalPlayed > 0 ? Math.round((sortedLineups[0].played / totalPlayed) * 100) : 0}%)
            </span>
          </div>
        </div>
      )}

      {/* All Formations */}
      <div className="space-y-2">
        {sortedLineups.slice(1).map((lineup, index) => (
          <div key={lineup.formation} className="flex items-center justify-between py-2 border-b border-border/30 last:border-0">
            <span className="font-heading font-semibold">{lineup.formation}</span>
            <div className="flex items-center gap-2">
              <div className="w-20 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                <div 
                  className="h-full rounded-full bg-muted-foreground/50"
                  style={{ width: `${totalPlayed > 0 ? (lineup.played / totalPlayed) * 100 : 0}%` }}
                />
              </div>
              <span className="text-sm text-muted-foreground">{lineup.played}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
