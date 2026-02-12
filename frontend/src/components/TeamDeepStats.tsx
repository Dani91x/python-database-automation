"use client";

import { AlertTriangle, Trophy, Zap } from "lucide-react";

export const TeamDeepStats = ({ team }: { team: any }) => {
    if (!team) return null;

    const penalty = team.penalty || { scored: { total: 0 }, missed: { total: 0 } };
    const biggest = team.biggest || { streak: { wins: 0 }, goals: { for: { home: 0 } } };

    return (
        <div className="grid grid-cols-2 gap-4">
            <div className="glass-panel p-6 rounded-3xl border-white/5 space-y-4">
                <div className="flex items-center gap-2 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                    <Trophy className="w-3 h-3 text-brand-orange" />
                    Record & Streak
                </div>
                <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold text-gray-400 uppercase">Max Vittorie</span>
                    <span className="text-sm font-black text-white">{biggest.streak.wins}</span>
                </div>
                <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold text-gray-400 uppercase">Max Gol (Casa)</span>
                    <span className="text-sm font-black text-white">{biggest.goals.for.home}</span>
                </div>
            </div>

            <div className="glass-panel p-6 rounded-3xl border-white/5 space-y-4">
                <div className="flex items-center gap-2 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                    <Zap className="w-3 h-3 text-yellow-500" />
                    Rigori
                </div>
                <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold text-gray-400 uppercase">Segnati</span>
                    <span className="text-sm font-black text-green-500">{penalty.scored.total}</span>
                </div>
                <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold text-gray-400 uppercase">Sbagliati</span>
                    <span className="text-sm font-black text-red-500">{penalty.missed.total}</span>
                </div>
            </div>
        </div>
    );
};
