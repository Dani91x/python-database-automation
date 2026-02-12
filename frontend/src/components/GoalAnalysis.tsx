"use client";

import { motion } from "framer-motion";

export const GoalAnalysis = ({ goals, teamName }: { goals: any, teamName: string }) => {
    if (!goals) return null;

    const minuteData = goals.minute || {};
    const buckets = [
        "0-15", "16-30", "31-45", "46-60", "61-75", "76-90", "91-105"
    ];

    return (
        <div className="glass-panel p-6 rounded-3xl border-white/5">
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-gray-500 mb-6 flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-brand-orange" />
                Distribuzione Gol: {teamName}
            </h3>

            <div className="space-y-6">
                {/* Minute Distribution */}
                <div className="space-y-3">
                    <div className="text-[9px] font-black text-gray-600 uppercase tracking-widest">Minuti Segnatura</div>
                    <div className="flex items-end justify-between gap-1 h-32">
                        {buckets.map((bucket) => {
                            const data = minuteData[bucket] || { percentage: "0%" };
                            const percent = parseFloat(data.percentage?.replace('%', '')) || 5;
                            return (
                                <div key={bucket} className="flex-1 flex flex-col items-center gap-2 group">
                                    <div className="w-full relative bg-white/5 rounded-t-sm flex items-end overflow-hidden" style={{ height: '100%' }}>
                                        <motion.div
                                            initial={{ height: 0 }}
                                            animate={{ height: `${percent}%` }}
                                            className="w-full bg-brand-orange/40 group-hover:bg-brand-orange transition-colors rounded-t-sm"
                                        />
                                    </div>
                                    <span className="text-[8px] font-black text-gray-600 rotate-45 mt-2">{bucket}'</span>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Under/Over Stats */}
                <div className="grid grid-cols-2 gap-4 pt-6 border-t border-white/5">
                    <div className="space-y-2">
                        <div className="text-[9px] font-black text-gray-600 uppercase tracking-widest text-center">Under 2.5</div>
                        <div className="bg-white/5 p-3 rounded-xl border border-white/10 text-center">
                            <div className="text-xl font-black">{goals.under_over?.["2.5"]?.under || 0}</div>
                            <div className="text-[9px] text-gray-500 font-bold uppercase">Partite</div>
                        </div>
                    </div>
                    <div className="space-y-2">
                        <div className="text-[9px] font-black text-gray-600 uppercase tracking-widest text-center">Over 2.5</div>
                        <div className="bg-white/5 p-3 rounded-xl border border-white/10 text-center">
                            <div className="text-xl font-black text-brand-orange">{goals.under_over?.["2.5"]?.over || 0}</div>
                            <div className="text-[9px] text-gray-500 font-bold uppercase">Partite</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
