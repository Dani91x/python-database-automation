import { TeamLeagueStats } from "@/lib/normalize";
import { Card } from "@/components/ui/card";
import { CircleDot } from "lucide-react";

export function PenaltyCard({ penalty }: { penalty: TeamLeagueStats['penalty'] }) {
    return (
        <Card className="glass-card p-6">
            <div className="flex items-center gap-2 mb-4 text-muted-foreground">
                <CircleDot className="w-4 h-4" />
                <h4 className="text-xs font-rajdhani font-bold uppercase tracking-widest">Rigori</h4>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="text-center p-4 bg-green-500/10 rounded-xl border border-green-500/20">
                    <div className="text-2xl font-black text-green-400">{penalty.scored.total}</div>
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">Segnati</div>
                    <div className="text-xs text-green-400/60 font-mono mt-1">{penalty.scored.percentage}</div>
                </div>
                <div className="text-center p-4 bg-red-500/10 rounded-xl border border-red-500/20">
                    <div className="text-2xl font-black text-red-400">{penalty.missed.total}</div>
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">Sbagliati</div>
                    <div className="text-xs text-red-400/60 font-mono mt-1">{penalty.missed.percentage}</div>
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-white/5 text-center">
                <span className="text-xs text-muted-foreground">Totale rigori: </span>
                <span className="font-mono font-bold text-white">{penalty.total}</span>
            </div>
        </Card>
    );
}
