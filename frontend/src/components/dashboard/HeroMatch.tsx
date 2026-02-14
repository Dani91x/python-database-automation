import { NormalizedPredictions, NormalizedLeague, NormalizedTeam } from '@/lib/normalize';
import { Card } from '@/components/ui/card';

interface HeroMatchProps {
    home: NormalizedTeam;
    away: NormalizedTeam;
    league: NormalizedLeague;
    prediction: NormalizedPredictions;
    fixtureId?: string;
    leagueId?: number | string;
}

export function HeroMatch({ home, away, league, fixtureId, leagueId }: HeroMatchProps) {
    return (
        <Card className="bg-transparent border-none shadow-none mb-12">
            <div className="flex flex-col items-center">
                {/* League Header */}
                <div className="flex items-center gap-3 mb-8 text-white/80">
                    <img src={league.logo} alt="" className="w-8 h-8 object-contain" />
                    <h2 className="text-xl md:text-2xl font-black tracking-tight font-display">
                        {league.name} <span className="mx-2 text-white/20">•</span> {league.season} <span className="mx-2 text-white/20">•</span> {league.country}
                    </h2>
                </div>

                {/* Matchup Section */}
                <div className="flex items-center justify-center gap-8 md:gap-24 w-full max-w-5xl">
                    {/* Home Team */}
                    <div className="flex flex-col items-center text-center flex-1">
                        <div className="mb-4">
                            <span className="bg-emerald-500/10 text-emerald-400 text-[10px] font-black px-3 py-0.5 rounded-full border border-emerald-500/20 italic tracking-widest uppercase">HOME</span>
                        </div>
                        <h1 className="text-2xl md:text-5xl font-black text-white font-display mb-6 tracking-tighter uppercase drop-shadow-[0_0_15px_rgba(255,255,255,0.3)]">
                            {home.name}
                        </h1>
                        <div className="relative group">
                            <div className="absolute inset-0 bg-emerald-500/20 blur-[50px] rounded-full opacity-50 transition-opacity duration-500" />
                            <div className="w-24 h-24 md:w-32 md:h-32 relative z-10 flex items-center justify-center p-4">
                                <img src={home.logo} alt={home.name} className="w-full h-full object-contain filter drop-shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
                            </div>
                        </div>
                    </div>

                    {/* VS */}
                    <div className="flex-shrink-0">
                        <div className="w-16 h-10 md:w-24 md:h-14 rounded-full bg-white/5 border border-white/10 flex items-center justify-center backdrop-blur-md shadow-inner">
                            <span className="text-2xl md:text-3xl font-black italic text-emerald-400 tracking-tighter">VS</span>
                        </div>
                    </div>

                    {/* Away Team */}
                    <div className="flex flex-col items-center text-center flex-1">
                        <div className="mb-4">
                            <span className="bg-amber-500/10 text-amber-400 text-[10px] font-black px-3 py-0.5 rounded-full border border-amber-500/20 italic tracking-widest uppercase">AWAY</span>
                        </div>
                        <div className="relative group">
                            <div className="absolute inset-0 bg-amber-500/20 blur-[50px] rounded-full opacity-50 transition-opacity duration-500" />
                            <div className="w-24 h-24 md:w-32 md:h-32 relative z-10 flex items-center justify-center p-4">
                                <img src={away.logo} alt={away.name} className="w-full h-full object-contain filter drop-shadow-[0_0_10px_rgba(245,158,11,0.5)]" />
                            </div>
                        </div>
                        <h1 className="text-2xl md:text-5xl font-black text-white font-display mt-6 tracking-tighter uppercase drop-shadow-[0_0_15px_rgba(255,255,255,0.3)]">
                            {away.name}
                        </h1>
                    </div>
                </div>

                {/* Metadata Pills */}
                <div className="flex items-center gap-3 mt-12">
                    <div className="px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[11px] font-bold text-white/60 flex items-center gap-2">
                        Fixture ID: <span className="text-emerald-400 font-mono">{fixtureId || 'N/A'}</span>
                    </div>
                    <div className="px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[11px] font-bold text-white/60 flex items-center gap-2">
                        League ID: <span className="text-emerald-400 font-mono">{leagueId || 'N/A'}</span>
                    </div>
                </div>
            </div>
        </Card>
    );
}
