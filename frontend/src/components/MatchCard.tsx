"use client";

import { useState } from "react";
import { Zap, BrainCircuit, Activity, ChevronRight } from "lucide-react";
import { MatchDetailOverlay } from "./MatchDetailOverlay";
import { normalizeMatchData } from "@/lib/normalize";

export const MatchCard = ({ pred }: { pred: any }) => {
    const [isOverlayOpen, setIsOverlayOpen] = useState(false);
    const normalizedData = normalizeMatchData(pred.raw_json);

    return (
        <>
            <div
                onClick={() => normalizedData && setIsOverlayOpen(true)}
                className="glass-panel group p-6 rounded-3xl hover:border-brand-orange/40 transition-all cursor-pointer relative overflow-hidden active:scale-[0.98]"
            >
                <div className="absolute top-0 right-0 p-2 opacity-5 group-hover:opacity-10 transition-opacity">
                    <Zap className="w-12 h-12 text-brand-orange" />
                </div>

                <div className="grid md:grid-cols-12 gap-6 items-center">
                    {/* Match Info */}
                    <div className="md:col-span-5 flex items-center justify-between md:justify-start gap-6">
                        <div className="text-right flex-1">
                            <div className="font-black text-lg group-hover:text-brand-orange transition-colors uppercase tracking-tight">
                                {pred.home_team_name}
                            </div>
                        </div>
                        <div className="text-brand-orange font-black text-xs italic px-3 py-1 bg-brand-orange/10 rounded-full border border-brand-orange/20">
                            VS
                        </div>
                        <div className="text-left flex-1">
                            <div className="font-black text-lg group-hover:text-brand-orange transition-colors uppercase tracking-tight">
                                {pred.away_team_name}
                            </div>
                        </div>
                    </div>

                    {/* Predictions Data */}
                    <div className="md:col-span-4 grid grid-cols-2 gap-4 border-l border-white/5 pl-6">
                        <div>
                            <div className="text-[10px] uppercase text-gray-500 font-black mb-1 tracking-widest">CONSIGLIO</div>
                            <div className="flex items-center gap-2">
                                <span className="bg-brand-orange/20 text-brand-orange px-2 py-0.5 rounded text-[10px] font-black border border-brand-orange/20">
                                    {pred.winner_team_id === pred.home_team_id ? '1' : (pred.winner_team_id ? '2' : 'D')}
                                </span>
                                <span className="text-[10px] font-black text-white/80 uppercase">Vincitore</span>
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase text-gray-500 font-black mb-1 tracking-widest">GOAL LINE</div>
                            <div className="flex items-center gap-2">
                                <span className="bg-white/5 text-white px-2 py-0.5 rounded text-[10px] font-black border border-white/10">
                                    {pred.under_over_line || 'N/D'}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Action / Result */}
                    <div className="md:col-span-3 text-right flex items-center justify-end gap-4">
                        <div className="text-right">
                            <div className="text-[10px] bg-white/5 inline-block px-3 py-1 rounded-full border border-white/10 mb-1 font-black uppercase tracking-tighter text-gray-400">
                                {pred.evaluated_at ? 'REPORT PRONTO' : 'ANALISI LIVE'}
                            </div>
                            {pred.evaluated_at && (
                                <div className="flex items-center justify-end gap-2">
                                    {pred.hit_winner ? (
                                        <span className="text-[10px] bg-green-500/10 text-green-500 px-2 py-0.5 rounded border border-green-500/20 font-black uppercase">HIT 🏆</span>
                                    ) : (
                                        <span className="text-[10px] bg-red-500/10 text-red-500 px-2 py-0.5 rounded border border-red-500/20 font-black uppercase">MISS ✘</span>
                                    )}
                                </div>
                            )}
                        </div>
                        <div className="p-2 bg-white/5 rounded-full group-hover:bg-brand-orange group-hover:text-black transition-all">
                            <ChevronRight className="w-4 h-4" />
                        </div>
                    </div>
                </div>

                {/* Quick Insight Footer */}
                <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-[9px] text-brand-orange font-black uppercase tracking-[0.1em]">
                        <BrainCircuit className="w-3 h-3" />
                        Neural Network Signal
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="flex items-center gap-1 text-[9px] text-gray-500 font-bold uppercase">
                            <Activity className="w-3 h-3" />
                            Confidence: <span className="text-white">{pred.percent_home || 50}%</span>
                        </div>
                    </div>
                </div>
            </div>

            <MatchDetailOverlay
                isOpen={isOverlayOpen}
                onClose={() => setIsOverlayOpen(false)}
                data={normalizedData}
            />
        </>
    );
};
