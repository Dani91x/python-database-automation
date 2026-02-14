import { ShieldCheck, TriangleAlert } from "lucide-react";

interface CleanSheetCardProps {
    cleanSheet: { home: number; away: number; total: number };
    failedToScore: { home: number; away: number; total: number };
}

export function CleanSheetCard({ cleanSheet, failedToScore }: CleanSheetCardProps) {
    return (
        <div className="bg-black/40 backdrop-blur-xl rounded-3xl border border-white/5 p-6 shadow-2xl overflow-hidden">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:divide-x md:divide-white/5">
                {/* Left: Clean Sheets */}
                <div className="space-y-6">
                    <div className="flex items-center gap-3 text-white/40">
                        <ShieldCheck className="w-4 h-4 text-emerald-500/50" />
                        <h4 className="text-[11px] font-black uppercase tracking-widest">Clean Sheets</h4>
                    </div>
                    <div className="space-y-4 px-2">
                        <div className="flex justify-between items-center group">
                            <span className="text-[10px] font-black text-white/30 uppercase tracking-tighter group-hover:text-white/50 transition-colors">Home</span>
                            <span className="text-lg font-black italic text-white/90">{cleanSheet.home}</span>
                        </div>
                        <div className="flex justify-between items-center group">
                            <span className="text-[10px] font-black text-white/30 uppercase tracking-tighter group-hover:text-white/50 transition-colors">Away</span>
                            <span className="text-lg font-black italic text-white/90">{cleanSheet.away}</span>
                        </div>
                        <div className="flex justify-between items-center pt-2 border-t border-white/5 group">
                            <span className="text-[11px] font-black text-white uppercase tracking-widest transition-colors">Total</span>
                            <span className="text-2xl font-black italic text-emerald-400">{cleanSheet.total}</span>
                        </div>
                    </div>
                </div>

                {/* Right: Failed to Score */}
                <div className="space-y-6 md:pl-8 pt-6 md:pt-0 border-t md:border-t-0 border-white/5">
                    <div className="flex items-center gap-3 text-white/40">
                        <TriangleAlert className="w-4 h-4 text-red-500/50" />
                        <h4 className="text-[11px] font-black uppercase tracking-widest">Failed to Score</h4>
                    </div>
                    <div className="space-y-4 px-2">
                        <div className="flex justify-between items-center group">
                            <span className="text-[10px] font-black text-white/30 uppercase tracking-tighter group-hover:text-white/50 transition-colors">Home</span>
                            <span className="text-lg font-black italic text-white/90">{failedToScore.home}</span>
                        </div>
                        <div className="flex justify-between items-center group">
                            <span className="text-[10px] font-black text-white/30 uppercase tracking-tighter group-hover:text-white/50 transition-colors">Away</span>
                            <span className="text-lg font-black italic text-white/90">{failedToScore.away}</span>
                        </div>
                        <div className="flex justify-between items-center pt-2 border-t border-white/5 group">
                            <span className="text-[11px] font-black text-white uppercase tracking-widest transition-colors">Total</span>
                            <span className="text-2xl font-black italic text-red-500">{failedToScore.total}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
