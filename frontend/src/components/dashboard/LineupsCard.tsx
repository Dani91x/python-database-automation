import { TeamLeagueStats } from "@/lib/normalize";
import { Card } from "@/components/ui/card";
import { Users } from "lucide-react";

export function LineupsCard({ lineups }: { lineups: TeamLeagueStats['lineups'] }) {
    if (!lineups || lineups.length === 0) return null;

    const maxPlayed = Math.max(...lineups.map(l => l.played));

    return (
        <Card className="glass-card p-6">
            <div className="flex items-center gap-2 mb-4 text-muted-foreground">
                <Users className="w-4 h-4" />
                <h4 className="text-xs font-rajdhani font-bold uppercase tracking-widest">Formazioni Utilizzate</h4>
            </div>

            <div className="space-y-3">
                {lineups.map((lineup, i) => (
                    <div key={i} className="flex flex-col gap-1">
                        <div className="flex justify-between text-sm font-mono text-white">
                            <span>{lineup.formation}</span>
                            <span className="opacity-50">{lineup.played} part.</span>
                        </div>
                        <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-white/50"
                                style={{ width: `${(lineup.played / maxPlayed) * 100}%` }}
                            />
                        </div>
                    </div>
                ))}
            </div>
        </Card>
    );
}
