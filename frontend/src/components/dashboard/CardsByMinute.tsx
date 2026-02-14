import { useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, AlertCircle } from "lucide-react";

interface CardsByMinuteProps {
    cards: {
        yellow: Record<string, { total: number | null; percentage: string | null }>;
        red: Record<string, { total: number | null; percentage: string | null }>;
    };
}

export function CardsByMinute({ cards }: CardsByMinuteProps) {
    const [yellowOpen, setYellowOpen] = useState(false);
    const [redOpen, setRedOpen] = useState(false);

    const ranges = ["0-15", "16-30", "31-45", "46-60", "61-75", "76-90", "91-105", "106-120"];

    const cardTotal = (stats: Record<string, { total: number | null }>) =>
        Object.values(stats).reduce((acc, curr) => acc + (curr.total || 0), 0);

    const renderGrid = (stats: Record<string, { total: number | null; percentage: string | null }>) => (
        <div className="grid grid-cols-4 gap-3 p-4 bg-black/20 rounded-2xl mt-2 animate-fade-in">
            {ranges.map(range => {
                const data = stats[range];
                const hasData = data && data.total !== null;

                return (
                    <div key={range} className="flex flex-col items-center justify-center p-3 bg-white/[0.03] rounded-xl border border-white/5 group hover:bg-white/[0.06] transition-all">
                        <span className="text-[8px] font-black text-white/20 uppercase tracking-widest mb-1 group-hover:text-white/40">{range}</span>
                        <span className={cn(
                            "text-xl font-black italic leading-none mb-1",
                            hasData ? "text-white" : "text-white/10"
                        )}>
                            {hasData ? data.total : "N/D"}
                        </span>
                        <span className="text-[8px] font-bold text-white/20">
                            {hasData ? (data.percentage || "0.00%") : "-"}
                        </span>
                    </div>
                );
            })}
        </div>
    );

    return (
        <div className="space-y-4">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-white/40 ml-4">Cards by Minute</h4>

            <div className="space-y-2">
                {/* Yellow Cards Accordion */}
                <div className="bg-black/40 rounded-2xl border border-white/5 overflow-hidden">
                    <button
                        onClick={() => setYellowOpen(!yellowOpen)}
                        className="w-full p-4 flex items-center justify-between group"
                    >
                        <div className="flex items-center gap-4">
                            <div className="w-5 h-5 rounded-lg bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.4)]" />
                            <div className="flex items-baseline gap-2">
                                <span className="text-sm font-black text-white uppercase tracking-tighter">Yellow Cards</span>
                                <span className="text-[9px] font-bold text-white/30 tracking-widest uppercase">({cardTotal(cards.yellow)} total)</span>
                            </div>
                        </div>
                        <ChevronDown className={cn(
                            "w-4 h-4 text-white/20 transition-transform duration-300",
                            yellowOpen && "rotate-180"
                        )} />
                    </button>
                    {yellowOpen && renderGrid(cards.yellow)}
                </div>

                {/* Red Cards Accordion */}
                <div className="bg-black/40 rounded-2xl border border-white/5 overflow-hidden">
                    <button
                        onClick={() => setRedOpen(!redOpen)}
                        className="w-full p-4 flex items-center justify-between group"
                    >
                        <div className="flex items-center gap-4">
                            <div className="w-5 h-5 rounded-lg bg-red-500 shadow-[0_0_15px_rgba(239,68,68,0.4)]" />
                            <div className="flex items-baseline gap-2">
                                <span className="text-sm font-black text-white uppercase tracking-tighter">Red Cards</span>
                                <span className="text-[9px] font-bold text-white/30 tracking-widest uppercase">({cardTotal(cards.red)} total)</span>
                            </div>
                        </div>
                        <ChevronDown className={cn(
                            "w-4 h-4 text-white/20 transition-transform duration-300",
                            redOpen && "rotate-180"
                        )} />
                    </button>
                    {redOpen && (
                        cardTotal(cards.red) > 0
                            ? renderGrid(cards.red)
                            : <div className="p-8 text-center text-[10px] font-black text-white/20 uppercase tracking-widest italic animate-fade-in">Nessun dato disponibile</div>
                    )}
                </div>
            </div>
        </div>
    );
}
