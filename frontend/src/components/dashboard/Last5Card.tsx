import { TeamLast5 } from "@/lib/normalize";
import { Progress } from "@/components/ui/progress";
import { Activity, Shield, Swords } from "lucide-react";

export function Last5Card({ last5 }: { last5: TeamLast5 }) {
    const avgFor = (last5.goalsFor / last5.played).toFixed(1);
    const avgAgainst = (last5.goalsAgainst / last5.played).toFixed(1);

    return (
        <div className="glass-card p-6 space-y-8">
            {/* 1. Percentage Summary */}
            <div className="relative">
                <div className="flex items-center gap-2 mb-6 text-white/40">
                    <Activity className="w-3 h-3" />
                    <h4 className="text-[10px] font-black uppercase tracking-widest">Last 5 Matches Summary</h4>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Form */}
                    <div className="flex flex-col items-center">
                        <span className="text-2xl font-black italic text-white tracking-widest leading-none mb-1">{last5.form}%</span>
                        <span className="text-[8px] font-black uppercase tracking-widest text-white/40 mb-3">Form</span>
                        <Progress value={last5.form} className="h-1 bg-white/5" indicatorClassName="bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]" />
                    </div>
                    {/* Attack */}
                    <div className="flex flex-col items-center">
                        <div className="flex items-center gap-1 mb-1">
                            <Swords className="w-3 h-3 text-white/20" />
                            <span className="text-2xl font-black italic text-white tracking-widest leading-none">{last5.att}%</span>
                        </div>
                        <span className="text-[8px] font-black uppercase tracking-widest text-white/40 mb-3">Attack</span>
                        <Progress value={last5.att} className="h-1 bg-white/5" indicatorClassName="bg-emerald-400" />
                    </div>
                    {/* Defense */}
                    <div className="flex flex-col items-center">
                        <div className="flex items-center gap-1 mb-1">
                            <Shield className="w-3 h-3 text-white/20" />
                            <span className="text-2xl font-black italic text-white tracking-widest leading-none">{last5.def}%</span>
                        </div>
                        <span className="text-[8px] font-black uppercase tracking-widest text-white/40 mb-3">Defense</span>
                        <Progress value={last5.def} className="h-1 bg-white/5" indicatorClassName="bg-white/20" />
                    </div>
                </div>
            </div>

            {/* 2. Goals Boxes */}
            <div className="space-y-4">
                <h4 className="text-[10px] font-black uppercase tracking-widest text-white/40">Goals (Last 5)</h4>
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white/[0.03] p-4 rounded-xl border border-white/5 flex flex-col items-center group hover:bg-white/[0.05] transition-colors">
                        <span className="text-[9px] font-black uppercase tracking-widest text-white/30 mb-2">Goals For</span>
                        <span className="text-4xl font-black italic text-white leading-none mb-2">{last5.goalsFor}</span>
                        <span className="text-[10px] font-bold text-white/40">Avg: <span className="text-emerald-400">{avgFor}</span> per match</span>
                    </div>
                    <div className="bg-white/[0.03] p-4 rounded-xl border border-white/5 flex flex-col items-center group hover:bg-white/[0.05] transition-colors">
                        <span className="text-[9px] font-black uppercase tracking-widest text-white/30 mb-2">Goals Against</span>
                        <span className="text-4xl font-black italic text-red-500/80 leading-none mb-2">{last5.goalsAgainst}</span>
                        <span className="text-[10px] font-bold text-white/40">Avg: <span className="text-red-400">{avgAgainst}</span> per match</span>
                    </div>
                </div>
                <div className="flex justify-center">
                    <div className="text-[9px] font-black uppercase tracking-widest text-white/20 bg-white/5 px-3 py-1 rounded-full border border-white/5">
                        Played: {last5.played} matches
                    </div>
                </div>
            </div>
        </div>
    );
}
