import { useState } from "react";
import { TeamLeagueStats } from "@/lib/normalize";
import { cn } from "@/lib/utils";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip } from 'recharts';
import { Target, ShieldAlert } from "lucide-react";

interface GoalsTabsProps {
    stats: TeamLeagueStats;
}

export function GoalsTabs({ stats }: GoalsTabsProps) {
    const [activeTab, setActiveTab] = useState<'for' | 'against'>('for');

    const isFor = activeTab === 'for';
    const data = isFor ? stats.goals.for : stats.goals.against;
    const accentColor = isFor ? "emerald" : "red";
    const chartColor = isFor ? "#10b981" : "#ef4444"; // emerald-500 : red-500

    // Transform minute data for chart
    const minuteData = [
        "0-15", "16-30", "31-45", "46-60", "61-75", "76-90", "91-105", "106-120"
    ].map(range => ({
        range,
        count: data.minute[range]?.total || 0
    }));

    const underOverThresholds = ['0.5', '1.5', '2.5', '3.5', '4.5'];

    return (
        <div className="bg-black/40 backdrop-blur-xl rounded-3xl border border-white/5 overflow-hidden">
            {/* Custom Tab Switcher */}
            <div className="p-2 bg-black/40 flex gap-2">
                <button
                    onClick={() => setActiveTab('for')}
                    className={cn(
                        "flex-1 py-3 rounded-2xl flex items-center justify-center gap-2 transition-all duration-300 font-black uppercase tracking-widest text-[10px]",
                        activeTab === 'for'
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-[0_0_20px_rgba(16,185,129,0.1)]"
                            : "text-white/20 hover:text-white/40 border border-transparent"
                    )}
                >
                    <Target className="w-3 h-3" />
                    Goals For
                </button>
                <button
                    onClick={() => setActiveTab('against')}
                    className={cn(
                        "flex-1 py-3 rounded-2xl flex items-center justify-center gap-2 transition-all duration-300 font-black uppercase tracking-widest text-[10px]",
                        activeTab === 'against'
                            ? "bg-red-500/10 text-red-400 border border-red-500/20 shadow-[0_0_20px_rgba(239,68,68,0.1)]"
                            : "text-white/20 hover:text-white/40 border border-transparent"
                    )}
                >
                    <ShieldAlert className="w-3 h-3" />
                    Goals Against
                </button>
            </div>

            <div className="p-6 space-y-8">
                {/* 1. Total Goals Section */}
                <div>
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-4">
                        {isFor ? "Total Goals Scored" : "Total Goals Conceded"}
                    </h4>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="bg-white/5 p-4 rounded-xl border border-white/5 flex flex-col items-center">
                            <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-2">Home</span>
                            <span className={cn("text-2xl font-black italic leading-none", activeTab === 'for' ? "text-emerald-400" : "text-red-400")}>
                                {data.total.home}
                            </span>
                        </div>
                        <div className="bg-white/5 p-4 rounded-xl border border-white/5 flex flex-col items-center">
                            <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-2">Away</span>
                            <span className={cn("text-2xl font-black italic leading-none", activeTab === 'for' ? "text-emerald-400" : "text-red-400")}>
                                {data.total.away}
                            </span>
                        </div>
                        <div className="bg-white/5 p-4 rounded-xl border border-white/5 flex flex-col items-center ring-1 ring-inset ring-white/10">
                            <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-2">Total</span>
                            <span className="text-2xl font-black italic leading-none text-emerald-400/90">
                                {data.total.total}
                            </span>
                        </div>
                    </div>
                </div>

                {/* 2. Average Section */}
                <div>
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-4">Average Per Match</h4>
                    <div className="flex justify-between px-4">
                        <div className="flex flex-col items-center">
                            <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-1">Home</span>
                            <span className="text-lg font-black italic text-white">{data.average.home}</span>
                        </div>
                        <div className="flex flex-col items-center">
                            <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-1">Away</span>
                            <span className="text-lg font-black italic text-white">{data.average.away}</span>
                        </div>
                        <div className="flex flex-col items-center">
                            <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-1">Total</span>
                            <span className="text-lg font-black italic text-white">{data.average.total}</span>
                        </div>
                    </div>
                </div>

                {/* 3. Goals by Minute Chart */}
                <div className="space-y-4">
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-white/40">Goals by Minute</h4>
                    <div className="h-[200px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={minuteData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                <XAxis
                                    dataKey="range"
                                    stroke="rgba(255,255,255,0.2)"
                                    fontSize={8}
                                    tickLine={false}
                                    axisLine={false}
                                    dy={10}
                                />
                                <YAxis
                                    stroke="rgba(255,255,255,0.2)"
                                    fontSize={8}
                                    tickLine={false}
                                    axisLine={false}
                                />
                                <Tooltip
                                    cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                                    content={({ active, payload }) => {
                                        if (active && payload && payload.length) {
                                            return (
                                                <div className="bg-black/90 border border-white/10 px-2 py-1 rounded shadow-xl">
                                                    <p className="text-[10px] font-black text-white">{payload[0].value} goals</p>
                                                </div>
                                            );
                                        }
                                        return null;
                                    }}
                                />
                                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                                    {minuteData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={chartColor} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 4. Under/Over Distribution */}
                <div className="space-y-4">
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-white/40">Under/Over Distribution</h4>
                    <div className="space-y-3">
                        {underOverThresholds.map(threshold => {
                            const uo = data.under_over[threshold] || { over: 0, under: 0 };
                            const total = uo.over + uo.under;
                            const underPct = total ? (uo.under / total) * 100 : 0;
                            const overPct = total ? (uo.over / total) * 100 : 0;

                            return (
                                <div key={threshold} className="group">
                                    <div className="flex items-center gap-3">
                                        <span className="w-6 text-[10px] font-black text-white/30 italic group-hover:text-white/60 transition-colors">
                                            {threshold}
                                        </span>
                                        <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden flex min-w-[50px]">
                                            <div
                                                className="h-full bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.3)] transition-all duration-500"
                                                style={{ width: `${underPct}%` }}
                                            />
                                            <div
                                                className="h-full bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.3)] transition-all duration-500"
                                                style={{ width: `${overPct}%` }}
                                            />
                                        </div>
                                        <div className="w-14 text-right shrink-0">
                                            <span className="text-[8px] md:text-[9px] font-bold text-white/40 tracking-tighter whitespace-nowrap">
                                                U:{uo.under}·O:{uo.over}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </div>
    );
}
