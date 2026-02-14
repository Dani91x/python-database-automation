import { TeamLeagueStats } from "@/lib/normalize";
import { Users } from "lucide-react";

interface LineupsCardProps {
    lineups: TeamLeagueStats['lineups'];
}

export function LineupsCard({ lineups }: LineupsCardProps) {
    if (!lineups || lineups.length === 0) return null;

    // Sort by matches played descending
    const sortedLineups = [...lineups].sort((a, b) => b.played - a.played);
    const mostUsed = sortedLineups[0];
    const others = sortedLineups.slice(1);

    const totalMatches = lineups.reduce((acc, curr) => acc + curr.played, 0);
    const getPct = (played: number) => Math.round((played / totalMatches) * 100);

    return (
        <div className="bg-black/40 backdrop-blur-xl rounded-3xl border border-white/5 p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3 text-white/40 mb-2">
                <Users className="w-4 h-4" />
                <h4 className="text-[12px] font-black uppercase tracking-widest text-white/60">Formations</h4>
            </div>

            {/* Most Used Highlight */}
            <div className="bg-emerald-500/5 rounded-2xl border border-emerald-500/10 p-5 relative overflow-hidden group">
                <div className="flex justify-between items-start relative z-10">
                    <div>
                        <p className="text-[8px] font-black uppercase tracking-widest text-emerald-500/60 mb-2">Most Used Formation</p>
                        <h3 className="text-4xl font-black italic text-emerald-400 tracking-tighter leading-none group-hover:scale-105 transition-transform origin-left">
                            {mostUsed.formation}
                        </h3>
                    </div>
                    <div className="text-right">
                        <p className="text-[10px] font-black text-white/40 tracking-widest uppercase">
                            {mostUsed.played} matches <span className="text-emerald-500/60">({getPct(mostUsed.played)}%)</span>
                        </p>
                    </div>
                </div>
                {/* Background Glow */}
                <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-emerald-500/5 blur-3xl rounded-full" />
            </div>

            {/* Others List */}
            <div className="space-y-4 px-2">
                {others.map((l, i) => {
                    const pct = getPct(l.played);
                    return (
                        <div key={i} className="space-y-2 group">
                            <div className="flex justify-between items-center">
                                <span className="text-sm font-black text-white/70 group-hover:text-white transition-colors">
                                    {l.formation}
                                </span>
                                <span className="text-[10px] font-black text-white/20 tabular-nums">
                                    {l.played}
                                </span>
                            </div>
                            <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-white/20 group-hover:bg-emerald-500/40 transition-all duration-500"
                                    style={{ width: `${pct}%` }}
                                />
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
