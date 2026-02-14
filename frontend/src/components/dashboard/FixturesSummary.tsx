import { TeamLeagueStats } from "@/lib/normalize";
import { Calendar, Trophy, Minus, X } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Label } from "recharts";
import { cn } from "@/lib/utils";

export function FixturesSummary({ fixtures }: { fixtures: TeamLeagueStats['fixtures'] }) {
    const data = [
        { name: 'Wins', value: fixtures.wins.total, color: '#10b981' },
        { name: 'Draws', value: fixtures.draws.total, color: '#f59e0b' },
        { name: 'Losses', value: fixtures.loses.total, color: '#ef4444' },
    ];

    const rows = [
        { label: "Wins", data: fixtures.wins, icon: <Trophy className="w-3 h-3 text-emerald-400" />, color: "text-emerald-400" },
        { label: "Draws", data: fixtures.draws, icon: <Minus className="w-3 h-3 text-amber-500" />, color: "text-amber-500" },
        { label: "Losses", data: fixtures.loses, icon: <X className="w-3 h-3 text-red-500" />, color: "text-red-500" },
    ];

    return (
        <div className="bg-black/40 backdrop-blur-xl rounded-3xl border border-white/5 p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3 text-white/40 mb-2">
                <Calendar className="w-4 h-4" />
                <h4 className="text-[12px] font-black uppercase tracking-widest text-white/60">Season Fixtures</h4>
            </div>

            <div className="flex flex-col md:flex-row items-center gap-8">
                {/* Donut Chart */}
                <div className="w-full md:w-1/3 aspect-square relative max-w-[160px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={data}
                                innerRadius="70%"
                                outerRadius="100%"
                                paddingAngle={5}
                                dataKey="value"
                                stroke="none"
                            >
                                {data.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                                <Label
                                    content={({ viewBox }) => {
                                        const { cx, cy } = viewBox as any;
                                        return (
                                            <g>
                                                <text x={cx} y={cy - 5} textAnchor="middle" dominantBaseline="middle" className="fill-white font-black text-xl italic">
                                                    {fixtures.played.total}
                                                </text>
                                                <text x={cx} y={cy + 15} textAnchor="middle" dominantBaseline="middle" className="fill-white/20 font-black text-[8px] uppercase tracking-widest">
                                                    Played
                                                </text>
                                            </g>
                                        );
                                    }}
                                />
                            </Pie>
                        </PieChart>
                    </ResponsiveContainer>
                </div>

                <div className="flex-1 w-full space-y-4">
                    {rows.map((row) => (
                        <div key={row.label} className="grid grid-cols-[1fr_repeat(3,auto)] items-center gap-4 md:gap-6">
                            <div className="flex items-center gap-2">
                                {row.icon}
                                <span className="text-[10px] md:text-[11px] font-black uppercase tracking-wider text-white">
                                    {row.label}
                                </span>
                            </div>
                            <div className="text-right">
                                <span className="text-[8px] md:text-[9px] font-black text-white/20 mr-1">H:</span>
                                <span className="text-[10px] md:text-[11px] font-black text-white/40">{row.data.home}</span>
                            </div>
                            <div className="text-right">
                                <span className="text-[8px] md:text-[9px] font-black text-white/20 mr-1">A:</span>
                                <span className="text-[10px] md:text-[11px] font-black text-white/40">{row.data.away}</span>
                            </div>
                            <div className="text-right w-6">
                                <span className={cn("text-[12px] md:text-[14px] font-black italic", row.color)}>{row.data.total}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Performance Footer */}
            <div className="grid grid-cols-3 gap-2 pt-4 border-t border-white/5">
                <div className="flex flex-col items-center">
                    <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-1">Home</span>
                    <span className="text-lg font-black italic text-white/70 tracking-tighter">{fixtures.played.home}</span>
                </div>
                <div className="flex flex-col items-center">
                    <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-1">Away</span>
                    <span className="text-lg font-black italic text-white/70 tracking-tighter">{fixtures.played.away}</span>
                </div>
                <div className="flex flex-col items-center">
                    <span className="text-[8px] font-black uppercase tracking-widest text-white/20 mb-1">Total</span>
                    <span className="text-lg font-black italic text-emerald-400 tracking-tighter">{fixtures.played.total}</span>
                </div>
            </div>
        </div>
    );
}
