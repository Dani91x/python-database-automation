import { TeamLeagueStats } from "@/lib/normalize";
import { Card } from "@/components/ui/card";
import { Flame } from "lucide-react";

export function BiggestStreakCard({ biggest }: { biggest: TeamLeagueStats['biggest'] }) {
    return (
        <Card className="glass-card p-6">
            <div className="flex items-center gap-2 mb-4 text-muted-foreground">
                <Flame className="w-4 h-4" />
                <h4 className="text-xs font-display font-bold uppercase tracking-widest">Migliori Serie</h4>
            </div>

            <div className="grid grid-cols-3 gap-4 text-center">
                <div className="p-2 bg-result-win/10 rounded border border-result-win/20">
                    <div className="text-2xl font-black text-result-win">{biggest.streak.wins}</div>
                    <div className="text-[8px] uppercase tracking-wider text-muted-foreground">Wins</div>
                </div>
                <div className="p-2 bg-result-draw/10 rounded border border-result-draw/20">
                    <div className="text-2xl font-black text-result-draw">{biggest.streak.draws}</div>
                    <div className="text-[8px] uppercase tracking-wider text-muted-foreground">Draws</div>
                </div>
                <div className="p-2 bg-destructive/10 rounded border border-destructive/20">
                    <div className="text-2xl font-black text-destructive">{biggest.streak.loses}</div>
                    <div className="text-[8px] uppercase tracking-wider text-muted-foreground">Losses</div>
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-white/5 space-y-2 text-xs">
                <div className="flex justify-between">
                    <span className="text-muted-foreground">Biggest Win (Home)</span>
                    <span className="font-mono font-bold">{biggest.wins.home}</span>
                </div>
                <div className="flex justify-between">
                    <span className="text-muted-foreground">Biggest Lose (Away)</span>
                    <span className="font-mono font-bold">{biggest.loses.away}</span>
                </div>
            </div>
        </Card>
    );
}
