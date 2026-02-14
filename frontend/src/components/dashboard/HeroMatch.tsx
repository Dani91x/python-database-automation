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

                <div className="flex flex-col items-center justify-center gap-8 md:gap-16 w-full max-w-6xl">
                    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 md:gap-12 w-full">
                        {/* Home Team */}
                        <div className="flex flex-col items-center text-center space-y-6">
                            <div className="relative group">
                                <div className="absolute inset-0 bg-emerald-500/20 blur-[60px] rounded-full opacity-60 transition-opacity duration-700 group-hover:opacity-100" />
                                <div className="w-24 h-24 md:w-40 md:h-40 relative z-10 flex items-center justify-center p-4 bg-white/5 backdrop-blur-sm rounded-3xl border border-white/10 shadow-2xl">
                                    <img src={home.logo} alt={home.name} className="w-full h-full object-contain filter drop-shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-transform duration-500 group-hover:scale-110" />
                                </div>
                                <div className="absolute -top-3 -right-3">
                                    <span className="bg-emerald-500 text-black text-[9px] font-black px-3 py-1 rounded-full shadow-[0_0_15px_rgba(16,185,129,0.5)] italic tracking-widest uppercase">HOME</span>
                                </div>
                            </div>
                            <h1 className="text-3xl md:text-6xl font-black text-white font-display tracking-tighter uppercase drop-shadow-[0_4px_20px_rgba(0,0,0,0.5)] leading-none text-glow-emerald">
                                {home.name}
                            </h1>
                        </div>

                        {/* VS Divider */}
                        <div className="flex flex-col items-center justify-center">
                            <div className="w-12 h-12 md:w-20 md:h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center backdrop-blur-xl shadow-[inset_0_0_20px_rgba(255,255,255,0.05)] relative group">
                                <div className="absolute inset-0 bg-emerald-500/10 blur-xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
                                <span className="text-xl md:text-3xl font-black italic text-emerald-400 tracking-tighter relative z-10">VS</span>
                            </div>
                            <p className="text-[8px] font-black uppercase tracking-[0.3em] text-white/10 mt-4 hidden md:block">Match Insight</p>
                        </div>

                        {/* Away Team */}
                        <div className="flex flex-col items-center text-center space-y-6">
                            <div className="relative group">
                                <div className="absolute inset-0 bg-amber-500/20 blur-[60px] rounded-full opacity-60 transition-opacity duration-700 group-hover:opacity-100" />
                                <div className="w-24 h-24 md:w-40 md:h-40 relative z-10 flex items-center justify-center p-4 bg-white/5 backdrop-blur-sm rounded-3xl border border-white/10 shadow-2xl">
                                    <img src={away.logo} alt={away.name} className="w-full h-full object-contain filter drop-shadow-[0_0_15px_rgba(245,158,11,0.3)] transition-transform duration-500 group-hover:scale-110" />
                                </div>
                                <div className="absolute -top-3 -left-3">
                                    <span className="bg-amber-500 text-black text-[9px] font-black px-3 py-1 rounded-full shadow-[0_0_15px_rgba(245,158,11,0.5)] italic tracking-widest uppercase">AWAY</span>
                                </div>
                            </div>
                            <h1 className="text-3xl md:text-6xl font-black text-white font-display tracking-tighter uppercase drop-shadow-[0_4px_20px_rgba(0,0,0,0.5)] leading-none text-glow-amber">
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
