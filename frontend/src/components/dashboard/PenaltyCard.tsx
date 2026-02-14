import { Target, CheckCircle2, XCircle } from "lucide-react";

export function PenaltyCard({ penalty }: { penalty: TeamLeagueStats['penalty'] }) {
    return (
        <div className="bg-black/40 backdrop-blur-xl rounded-3xl border border-white/5 p-6 space-y-6 overflow-hidden relative">
            {/* Header */}
            <div className="flex items-center gap-3 text-white/40">
                <Target className="w-4 h-4 text-red-500/50" />
                <h4 className="text-[12px] font-black uppercase tracking-widest text-white/60">Penalty Stats</h4>
            </div>

            {/* Total Highlight */}
            <div className="flex flex-col items-center py-4">
                <span className="text-5xl font-black italic text-white leading-none mb-2">{penalty.total}</span>
                <span className="text-[9px] font-black uppercase tracking-widest text-white/30">Total Penalties</span>
            </div>

            {/* Decorative Red Bar (as per screenshot) */}
            <div className="h-6 w-[120%] -mx-[10%] bg-red-500/80 shadow-[0_0_30px_rgba(239,68,68,0.3)] rounded-full skew-x-[-12deg]" />

            {/* Detail Boxes */}
            <div className="grid grid-cols-2 gap-4">
                <div className="bg-white/[0.03] p-5 rounded-2xl border border-white/5 flex flex-col items-center group hover:bg-white/[0.05] transition-all">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 mb-3 group-hover:scale-110 transition-transform" />
                    <span className="text-[9px] font-black uppercase tracking-widest text-white/20 mb-1">Scored</span>
                    <span className="text-2xl font-black italic text-white leading-none mb-1">{penalty.scored.total}</span>
                    <span className="text-[10px] font-bold text-emerald-500/60">{penalty.scored.percentage}</span>
                </div>
                <div className="bg-white/[0.03] p-5 rounded-2xl border border-white/5 flex flex-col items-center group hover:bg-white/[0.05] transition-all">
                    <XCircle className="w-4 h-4 text-red-500 mb-3 group-hover:scale-110 transition-transform" />
                    <span className="text-[9px] font-black uppercase tracking-widest text-white/20 mb-1">Missed</span>
                    <span className="text-2xl font-black italic text-white leading-none mb-1">{penalty.missed.total}</span>
                    <span className="text-[10px] font-bold text-red-500/60">{penalty.missed.percentage}</span>
                </div>
            </div>
        </div>
    );
}
