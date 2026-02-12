"use client";

import { format, parseISO } from "date-fns";
import { it } from "date-fns/locale";

export const H2HHistory = ({ h2h }: { h2h: any[] }) => {
    if (!h2h || h2h.length === 0) return null;

    return (
        <div className="glass-panel p-6 rounded-3xl border-white/5">
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-gray-500 mb-4 flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-brand-orange" />
                Scontri Diretti (H2H)
            </h3>

            <div className="space-y-3">
                {h2h.slice(0, 10).map((match: any, i: number) => (
                    <div key={i} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                        <div className="flex flex-col">
                            <span className="text-[9px] text-gray-500 font-bold uppercase">
                                {format(parseISO(match.fixture.date), 'dd MMM yyyy', { locale: it })}
                            </span>
                            <span className="text-[10px] text-gray-400 truncate max-w-[100px]">{match.league.name}</span>
                        </div>

                        <div className="flex items-center gap-3 flex-1 justify-center px-4">
                            <span className="text-[11px] font-bold text-right flex-1 truncate">{match.teams.home.name}</span>
                            <div className="bg-white/5 px-3 py-1 rounded-lg border border-white/10 min-w-[60px] text-center font-black text-xs">
                                {match.goals.home} - {match.goals.away}
                            </div>
                            <span className="text-[11px] font-bold text-left flex-1 truncate">{match.teams.away.name}</span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};
