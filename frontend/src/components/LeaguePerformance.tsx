"use client";

interface StatsRowProps {
    label: string;
    home: number | string;
    away: number | string;
    total: number | string;
}

const StatsRow = ({ label, home, away, total }: StatsRowProps) => (
    <div className="grid grid-cols-4 py-3 border-b border-white/5 text-[11px]">
        <div className="font-bold text-gray-500 uppercase">{label}</div>
        <div className="text-center font-black">{home}</div>
        <div className="text-center font-black">{away}</div>
        <div className="text-center font-black text-brand-orange">{total}</div>
    </div>
);

export const LeaguePerformance = ({ stats, teamName }: { stats: any, teamName: string }) => {
    if (!stats) return null;

    return (
        <div className="glass-panel p-6 rounded-3xl border-white/5">
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-gray-500 mb-4 flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-brand-orange" />
                Performance: {teamName}
            </h3>

            <div className="grid grid-cols-4 mb-2 text-[9px] font-black text-gray-600 uppercase tracking-widest">
                <div>Metric</div>
                <div className="text-center">Casa</div>
                <div className="text-center">Fuori</div>
                <div className="text-center">Totale</div>
            </div>

            <div className="space-y-0">
                <StatsRow label="Giocate" home={stats.fixtures.played.home} away={stats.fixtures.played.away} total={stats.fixtures.played.total} />
                <StatsRow label="Vittorie" home={stats.fixtures.wins.home} away={stats.fixtures.wins.away} total={stats.fixtures.wins.total} />
                <StatsRow label="Pareggi" home={stats.fixtures.draws.home} away={stats.fixtures.draws.away} total={stats.fixtures.draws.total} />
                <StatsRow label="Sconfitte" home={stats.fixtures.loses.home} away={stats.fixtures.loses.away} total={stats.fixtures.loses.total} />
                <StatsRow label="Gol Fatti" home={stats.goals.for.total.home} away={stats.goals.for.total.away} total={stats.goals.for.total.total} />
                <StatsRow label="Media Gol" home={stats.goals.for.average.home} away={stats.goals.for.average.away} total={stats.goals.for.average.total} />
            </div>
        </div>
    );
};
