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

                <div className="w-full max-w-full lg:max-w-7xl px-4 overflow-hidden">
                    <div className="flex flex-col md:flex-row items-center justify-center gap-8 md:gap-4 lg:gap-12 w-full">
                        {/* Home Side: Name then Logo */}
                        <div className="flex items-center gap-4 md:gap-6 flex-1 justify-end group min-w-0">
                            <h1 className="text-xl md:text-3xl lg:text-5xl font-black text-white font-display tracking-tighter uppercase text-right leading-none drop-shadow-2xl text-glow-emerald transition-all group-hover:scale-105 truncate">
                                {home.name}
                            </h1>
                            <div className="relative shrink-0">
                                {/* Glowing Ring */}
                                <div className="absolute -inset-4 bg-emerald-500/25 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                                <div className="w-20 h-20 md:w-28 md:h-28 lg:w-36 lg:h-36 rounded-full bg-black/60 border-2 border-emerald-500/30 flex items-center justify-center p-4 lg:p-5 relative z-10 shadow-[0_0_30px_rgba(16,185,129,0.2)] backdrop-blur-xl group-hover:border-emerald-500/60 transition-colors">
                                    <img src={home.logo} alt="" className="w-full h-full object-contain filter drop-shadow-[0_0_10px_rgba(16,185,129,0.4)]" />
                                    <div className="absolute -top-1 -left-1 md:-top-2 md:-left-2">
                                        <span className="bg-emerald-500 text-black text-[7px] md:text-[8px] font-black px-1.5 md:px-2 py-0.5 rounded-full shadow-lg">HOME</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* VS Divider */}
                        <div className="px-4 md:px-6 lg:px-12 flex flex-col items-center shrink-0">
                            <div className="w-12 h-8 md:w-16 md:h-10 lg:w-20 lg:h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center backdrop-blur-xl relative group">
                                <div className="absolute inset-0 bg-white/5 blur-md rounded-full" />
                                <span className="text-lg md:text-xl lg:text-2xl font-black italic text-emerald-400/80 tracking-tighter relative z-10">VS</span>
                            </div>
                        </div>

                        {/* Away Side: Logo then Name */}
                        <div className="flex items-center gap-4 md:gap-6 flex-1 justify-start group min-w-0">
                            <div className="relative shrink-0">
                                {/* Glowing Ring */}
                                <div className="absolute -inset-4 bg-amber-500/25 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                                <div className="w-20 h-20 md:w-28 md:h-28 lg:w-36 lg:h-36 rounded-full bg-black/60 border-2 border-amber-500/30 flex items-center justify-center p-4 lg:p-5 relative z-10 shadow-[0_0_30px_rgba(245,158,11,0.2)] backdrop-blur-xl group-hover:border-amber-500/60 transition-colors">
                                    <img src={away.logo} alt="" className="w-full h-full object-contain filter drop-shadow-[0_0_10px_rgba(245,158,11,0.4)]" />
                                    <div className="absolute -top-1 -right-1 md:-top-2 md:-right-2">
                                        <span className="bg-amber-500 text-black text-[7px] md:text-[8px] font-black px-1.5 md:px-2 py-0.5 rounded-full shadow-lg">AWAY</span>
                                    </div>
                                </div>
                            </div>
                            <h1 className="text-xl md:text-3xl lg:text-5xl font-black text-white font-display tracking-tighter uppercase text-left leading-none drop-shadow-2xl text-glow-amber transition-all group-hover:scale-105 truncate">
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
