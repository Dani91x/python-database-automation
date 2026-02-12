import { TeamLeagueStats } from "@/lib/normalizePrediction";
import { ShieldCheck, AlertTriangle } from "lucide-react";

interface CleanSheetCardProps {
  cleanSheet: TeamLeagueStats['cleanSheet'];
  failedToScore: TeamLeagueStats['failedToScore'];
  side: 'home' | 'away';
}

export function CleanSheetCard({ cleanSheet, failedToScore, side }: CleanSheetCardProps) {
  return (
    <div className="glass-card p-5">
      <div className="grid grid-cols-2 gap-4">
        {/* Clean Sheets */}
        <div>
          <h4 className="font-heading text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-neon-green" />
            Clean Sheets
          </h4>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Home</span>
              <span className="font-display font-bold text-neon-green">{cleanSheet.home}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Away</span>
              <span className="font-display font-bold text-neon-green">{cleanSheet.away}</span>
            </div>
            <div className="flex justify-between items-center pt-2 border-t border-border/50">
              <span className="text-sm font-medium">Total</span>
              <span className="font-display text-lg font-bold text-neon-green">{cleanSheet.total}</span>
            </div>
          </div>
        </div>

        {/* Failed to Score */}
        <div>
          <h4 className="font-heading text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-neon-orange" />
            Failed to Score
          </h4>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Home</span>
              <span className="font-display font-bold text-neon-orange">{failedToScore.home}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Away</span>
              <span className="font-display font-bold text-neon-orange">{failedToScore.away}</span>
            </div>
            <div className="flex justify-between items-center pt-2 border-t border-border/50">
              <span className="text-sm font-medium">Total</span>
              <span className="font-display text-lg font-bold text-neon-orange">{failedToScore.total}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
