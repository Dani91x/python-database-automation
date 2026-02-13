import { TeamLeagueStats } from "@/lib/normalize";
import { Card } from "@/components/ui/card";
import { CircleDot } from "lucide-react";

export function PenaltyCard({ penalty }: { penalty: TeamLeagueStats['penalty'] }) {
    return (
        <Card className="glass-card p-6">
            <div className="flex items-center gap-2 mb-4 text-muted-foreground">
                <CircleDot className="w-4 h-4" />
                <h4 className="text-xs font-display font-bold uppercase tracking-widest">Rigori</h4>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="text-center p-4 bg-result-win/10 rounded-xl border border-result-win/20">
                    <div className="text-2xl font-black text-result-win">{penalty.scored.total}</div>
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">Segnati</div>
                    <div className="text-xs text-result-win/60 font-mono mt-1">{penalty.scored.percentage}</div>
                </div>
                <div className="text-center p-4 bg-destructive/10 rounded-xl border border-destructive/20">
                    <div className="text-2xl font-black text-destructive">{penalty.missed.total}</div>
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">Sbagliati</div>
                    <div className="text-xs text-destructive/60 font-mono mt-1">{penalty.missed.percentage}</div>
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-white/5 text-center">
                <span className="text-xs text-muted-foreground">Totale rigori: </span>
                <span className="font-mono font-bold text-white">{penalty.total}</span>
            </div>
        </Card>
    );
}
