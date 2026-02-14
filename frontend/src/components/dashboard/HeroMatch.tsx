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
                {/* Tournament Header */}
                <div className="flex flex-col items-center gap-2 mb-12">
                    <div className="flex items-center gap-3 text-white/40">
                        <img src={league.logo} alt="" className="w-6 h-6 object-contain opacity-50" />
                        <h2 className="text-sm md:text-base font-black tracking-[0.2em] uppercase font-display text-white/80">
                            {league.name} <span className="mx-2 text-white/20">•</span> {league.season} <span className="mx-2 text-white/20">•</span> {league.country}
                        </h2>
                    </div>
                </div>

                <div className="w-full max-w-7xl px-4">
                    <div className="flex flex-col md:flex-row items-center justify-between gap-8 md:gap-0">
                        {/* Home Side: Name then Logo */}
                        <div className="flex items-center gap-6 md:gap-10 flex-1 justify-end group">
                            <h1 className="text-2xl md:text-5xl font-black text-white font-display tracking-tighter uppercase text-right leading-none drop-shadow-2xl text-glow-emerald transition-all group-hover:scale-105">
                                {home.name}
                            </h1>
                            <div className="relative">
                                {/* Glowing Ring */}
                                <div className="absolute -inset-4 bg-emerald-500/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                                <div className="w-24 h-24 md:w-36 md:h-36 rounded-full bg-black/40 border-2 border-emerald-500/30 flex items-center justify-center p-5 relative z-10 shadow-[0_0_30px_rgba(16,185,129,0.2)] backdrop-blur-xl group-hover:border-emerald-500/60 transition-colors">
                                    <img src={home.logo} alt="" className="w-full h-full object-contain filter drop-shadow-[0_0_10px_rgba(16,185,129,0.4)]" />
                                    <div className="absolute -top-2 -left-2">
                                        <span className="bg-emerald-500 text-black text-[8px] font-black px-2 py-0.5 rounded-full shadow-lg">HOME</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* VS Divider */}
                        <div className="px-8 md:px-16 flex flex-col items-center">
                            <div className="w-16 h-10 md:w-20 md:h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center backdrop-blur-xl relative group">
                                <div className="absolute inset-0 bg-white/5 blur-md rounded-full" />
                                <span className="text-xl md:text-2xl font-black italic text-emerald-400/80 tracking-tighter relative z-10">VS</span>
                            </div>
                        </div>

                        {/* Away Side: Logo then Name */}
                        <div className="flex items-center gap-6 md:gap-10 flex-1 justify-start group">
                            <div className="relative">
                                {/* Glowing Ring */}
                                <div className="absolute -inset-4 bg-amber-500/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                                <div className="w-24 h-24 md:w-36 md:h-36 rounded-full bg-black/40 border-2 border-amber-500/30 flex items-center justify-center p-5 relative z-10 shadow-[0_0_30px_rgba(245,158,11,0.2)] backdrop-blur-xl group-hover:border-amber-500/60 transition-colors">
                                    <img src={away.logo} alt="" className="w-full h-full object-contain filter drop-shadow-[0_0_10px_rgba(245,158,11,0.4)]" />
                                    <div className="absolute -top-2 -right-2">
                                        <span className="bg-amber-500 text-black text-[8px] font-black px-2 py-0.5 rounded-full shadow-lg">AWAY</span>
                                    </div>
                                </div>
                            </div>
                            <h1 className="text-2xl md:text-5xl font-black text-white font-display tracking-tighter uppercase text-left leading-none drop-shadow-2xl text-glow-amber transition-all group-hover:scale-105">
                                {away.name}
                            </h1>
                        </div>
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
