import { TeamLeagueStats } from "@/lib/normalize";
import { Flame, ArrowUpRight, ArrowDownRight, Trophy, Skull } from "lucide-react";
import { cn } from "@/lib/utils";

export function BiggestStreakCard({ biggest }: { biggest: TeamLeagueStats['biggest'] }) {
    return (
        <div className="bg-black/40 backdrop-blur-xl rounded-3xl border border-white/5 p-6 space-y-8 overflow-hidden relative">
            {/* 1. Records & Streaks Header */}
            <div className="flex items-center gap-3 text-white/40">
                <Trophy className="w-4 h-4 text-emerald-500/50" />
                <h4 className="text-[12px] font-black uppercase tracking-widest">Records & Streaks</h4>
            </div>

            {/* 2. Streak Summary Boxes */}
            <div className="grid grid-cols-3 gap-3">
                {/* Win Streak */}
                <div className="bg-emerald-500/5 p-4 rounded-2xl border border-emerald-500/10 flex flex-col items-center group hover:bg-emerald-500/10 transition-all duration-300">
                    <Flame className="w-4 h-4 text-emerald-500 mb-2 group-hover:scale-125 transition-transform" />
                    <span className="text-2xl font-black italic text-white leading-none mb-1">{biggest.streak.wins}</span>
                    <span className="text-[8px] font-black uppercase tracking-widest text-emerald-500">Win Streak</span>
                </div>
                {/* Draw Streak */}
                <div className="bg-amber-500/5 p-4 rounded-2xl border border-amber-500/10 flex flex-col items-center group hover:bg-amber-500/10 transition-all duration-300">
                    <ArrowUpRight className="w-4 h-4 text-amber-500 mb-2 group-hover:scale-125 transition-transform" />
                    <span className="text-2xl font-black italic text-white leading-none mb-1">{biggest.streak.draws}</span>
                    <span className="text-[8px] font-black uppercase tracking-widest text-amber-400">Draw Streak</span>
                </div>
                {/* Loss Streak */}
                <div className="bg-red-500/5 p-4 rounded-2xl border border-red-500/10 flex flex-col items-center group hover:bg-red-500/10 transition-all duration-300">
                    <ArrowDownRight className="w-4 h-4 text-red-500 mb-2 group-hover:scale-125 transition-transform" />
                    <span className="text-2xl font-black italic text-white leading-none mb-1">{biggest.streak.loses}</span>
                    <span className="text-[8px] font-black uppercase tracking-widest text-red-500">Loss Streak</span>
                </div>
            </div>

            {/* 3. Comparisons Table */}
            <div className="grid grid-cols-2 gap-8 px-2">
                {/* Biggest Wins */}
                <div className="space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Trophy className="w-3 h-3 text-emerald-400" />
                        <span className="text-[9px] font-black uppercase tracking-widest text-white/40">Biggest Wins</span>
                    </div>
                    <div className="space-y-2">
                        <div className="flex justify-between items-center bg-white/[0.02] p-2 rounded-lg border border-white/5">
                            <span className="text-[10px] font-bold text-white/30 uppercase">Home</span>
                            <span className="text-sm font-black text-emerald-400 tabular-nums italic">{biggest.wins.home}</span>
                        </div>
                        <div className="flex justify-between items-center bg-white/[0.02] p-2 rounded-lg border border-white/5">
                            <span className="text-[10px] font-bold text-white/30 uppercase">Away</span>
                            <span className="text-sm font-black text-emerald-400 tabular-nums italic">{biggest.wins.away}</span>
                        </div>
                    </div>
                </div>

                {/* Biggest Losses */}
                <div className="space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Skull className="w-3 h-3 text-red-500" />
                        <span className="text-[9px] font-black uppercase tracking-widest text-white/40">Biggest Losses</span>
                    </div>
                    <div className="space-y-2">
                        <div className="flex justify-between items-center bg-white/[0.02] p-2 rounded-lg border border-white/5">
                            <span className="text-[10px] font-bold text-white/30 uppercase">Home</span>
                            <span className="text-sm font-black text-red-500 tabular-nums italic">{biggest.loses.home}</span>
                        </div>
                        <div className="flex justify-between items-center bg-white/[0.02] p-2 rounded-lg border border-white/5">
                            <span className="text-[10px] font-bold text-white/30 uppercase">Away</span>
                            <span className="text-sm font-black text-red-500 tabular-nums italic">{biggest.loses.away}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* 4. Most Goals Section */}
            <div className="pt-4 border-t border-white/5 space-y-4">
                <span className="text-[9px] font-black uppercase tracking-widest text-white/30 ml-2">Most Goals in a Match</span>
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white/5 p-3 rounded-xl border border-white/5 flex flex-col items-center">
                        <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-2 text-emerald-400/50">Scored</span>
                        <div className="flex gap-4">
                            <div className="text-center">
                                <p className="text-[7px] font-black uppercase text-white/20 pb-1">Home</p>
                                <p className="text-lg font-black italic leading-none">{biggest.goals.for.home}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-[7px] font-black uppercase text-white/20 pb-1">Away</p>
                                <p className="text-lg font-black italic leading-none">{biggest.goals.for.away}</p>
                            </div>
                        </div>
                    </div>
                    <div className="bg-white/5 p-3 rounded-xl border border-white/5 flex flex-col items-center">
                        <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-2 text-red-400/50">Conceded</span>
                        <div className="flex gap-4">
                            <div className="text-center">
                                <p className="text-[7px] font-black uppercase text-white/20 pb-1 text-red-400/20">Home</p>
                                <p className="text-lg font-black italic leading-none text-red-500/80">{biggest.goals.against.home}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-[7px] font-black uppercase text-white/20 pb-1 text-red-400/20">Away</p>
                                <p className="text-lg font-black italic leading-none text-red-500/80">{biggest.goals.against.away}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
