// frontend/src/components/dashboard/HeroMatch.tsx
import { NormalizedLeague, NormalizedTeam, NormalizedPredictions } from "@/lib/normalize";
import { TrendingUp, Target, Percent, Trophy, AlertCircle, Cpu } from "lucide-react";
import { Progress, cn } from "@/components/ui/shadcn-mini";

interface HeroMatchProps {
    league: NormalizedLeague;
    home: NormalizedTeam;
    away: NormalizedTeam;
    predictions: NormalizedPredictions;
    fixtureId: string;
}

export function HeroMatch({ league, home, away, predictions, fixtureId }: HeroMatchProps) {
    return (
        <section className="relative overflow-hidden pt-12 pb-20">
            {/* Background effects */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(255,153,0,0.1)_0%,transparent_50%)]" />

            <div className="relative container mx-auto px-4">
                {/* League Strip */}
                <div className="flex flex-col items-center mb-12">
                    <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[10px] font-black uppercase tracking-[0.2em] text-white/60 mb-6">
                        <Cpu className="w-3 h-3 text-brand-orange" />
                        Live Deep Analysis
                    </div>

                    <div className="flex items-center justify-center gap-3">
                        {league.logo && (
                            <img
                                src={league.logo}
                                alt={league.name}
                                className="w-10 h-10 object-contain brightness-110"
                            />
                        )}
                        <div className="flex items-center gap-2">
                            <span className="text-xl lg:text-2xl font-black text-white uppercase tracking-tighter">
                                {league.name}
                            </span>
                            <span className="text-white/20">•</span>
                            <span className="text-brand-orange font-bold italic">{league.season}</span>
                            {league.flag && (
                                <img
                                    src={league.flag}
                                    alt={league.country}
                                    className="w-5 h-4 object-cover rounded-sm ml-2 grayscale opacity-50"
                                />
                            )}
                        </div>
                    </div>
                </div>

                {/* Match Row */}
                <div className="flex flex-col lg:flex-row items-center justify-center gap-8 lg:gap-20 mb-16">
                    {/* Home Team */}
                    <div className="flex flex-row-reverse lg:flex-row items-center gap-6 group">
                        <div className="text-right">
                            <span className="text-[10px] font-black tracking-widest text-brand-orange uppercase mb-1 block opacity-60">Home</span>
                            <h2 className="text-3xl lg:text-5xl font-black tracking-tighter group-hover:text-brand-orange transition-colors">
                                {home.name}
                            </h2>
                        </div>
                        <div className="relative">
                            <div className="absolute -inset-4 bg-brand-orange/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
                            <div className="w-24 h-24 lg:w-32 lg:h-32 rounded-full glass-panel p-4 flex items-center justify-center relative border-brand-orange/20">
                                <img
                                    src={home.logo}
                                    alt={home.name}
                                    className="w-full h-full object-contain"
                                />
                            </div>
                        </div>
                    </div>

                    {/* VS */}
                    <div className="relative">
                        <div className="text-4xl lg:text-5xl font-black italic opacity-10 tracking-tighter absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">VS</div>
                        <div className="glass-panel px-8 py-3 rounded-full border-white/10">
                            <span className="text-xl font-black text-brand-orange tracking-widest">ANALYSIS</span>
                        </div>
                    </div>

                    {/* Away Team */}
                    <div className="flex items-center gap-6 group">
                        <div className="relative">
                            <div className="absolute -inset-4 bg-neon-cyan/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
                            <div className="w-24 h-24 lg:w-32 lg:h-32 rounded-full glass-panel p-4 flex items-center justify-center relative border-neon-cyan/20">
                                <img
                                    src={away.logo}
                                    alt={away.name}
                                    className="w-full h-full object-contain"
                                />
                            </div>
                        </div>
                        <div className="text-left">
                            <span className="text-[10px] font-black tracking-widest text-neon-cyan uppercase mb-1 block opacity-60">Away</span>
                            <h2 className="text-3xl lg:text-5xl font-black tracking-tighter group-hover:text-neon-cyan transition-colors">
                                {away.name}
                            </h2>
                        </div>
                    </div>
                </div>

                {/* KPI Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-6xl mx-auto">
                    {/* Win Probability */}
                    <div className="glass-panel p-8 rounded-[2rem] border-white/5 relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform">
                            <Percent className="w-12 h-12" />
                        </div>
                        <h3 className="text-xs font-black uppercase tracking-widest text-gray-500 mb-6">Win Probability</h3>
                        <div className="space-y-6">
                            <div>
                                <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest mb-2">
                                    <span className="text-brand-orange">Home: {predictions.percent.home}</span>
                                </div>
                                <Progress value={predictions.percent.homePercent} className="h-1.5" barClassName="bg-brand-orange" />
                            </div>
                            <div>
                                <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest mb-2 text-gray-400">
                                    <span>Draw: {predictions.percent.draw}</span>
                                </div>
                                <Progress value={predictions.percent.drawPercent} className="h-1.5 bg-white/5" barClassName="bg-gray-400" />
                            </div>
                            <div>
                                <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest mb-2 text-neon-cyan">
                                    <span>Away: {predictions.percent.away}</span>
                                </div>
                                <Progress value={predictions.percent.awayPercent} className="h-1.5 bg-white/5" barClassName="bg-neon-cyan" />
                            </div>
                        </div>
                    </div>

                    {/* AI Advice */}
                    <div className="glass-panel p-8 rounded-[2rem] border-brand-orange/20 relative overflow-hidden group bg-gradient-to-br from-brand-orange/5 to-transparent">
                        <div className="absolute top-0 right-0 p-4 opacity-10">
                            <BrainCircuit className="w-12 h-12 text-brand-orange" />
                        </div>
                        <h3 className="text-xs font-black uppercase tracking-widest text-brand-orange mb-6">Algorithm Feedback</h3>
                        <p className="text-xl font-black leading-tight mb-6">
                            "{predictions.advice}"
                        </p>
                        {predictions.winner && (
                            <div className="flex items-center gap-3 bg-white/5 p-4 rounded-2xl border border-white/10">
                                <Trophy className="w-5 h-5 text-brand-orange" />
                                <div className="text-sm">
                                    <span className="text-gray-500 uppercase font-black text-[10px] tracking-widest block">Value Target</span>
                                    <span className="font-bold">{predictions.winner.name}</span>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Goals & Market */}
                    <div className="glass-panel p-8 rounded-[2rem] border-white/5 relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10">
                            <Target className="w-12 h-12" />
                        </div>
                        <h3 className="text-xs font-black uppercase tracking-widest text-gray-500 mb-6">Market Metrics</h3>
                        <div className="space-y-6">
                            <div className="flex items-center justify-between p-4 rounded-2xl bg-white/5 border border-white/10">
                                <span className="text-[10px] font-black uppercase tracking-widest text-gray-500">U/O Line</span>
                                <span className="text-2xl font-black italic">{predictions.underOver}</span>
                            </div>
                            <div className="flex items-center justify-between p-4 rounded-2xl bg-white/5 border border-white/10">
                                <span className="text-[10px] font-black uppercase tracking-widest text-gray-500">Win/Draw Strategy</span>
                                <div className={cn(
                                    "px-4 py-1 rounded-full text-[10px] font-black uppercase tracking-widest",
                                    predictions.winOrDraw ? "bg-brand-orange/20 text-brand-orange" : "bg-red-500/20 text-red-500"
                                )}>
                                    {predictions.winOrDraw ? "Approved" : "High Risk"}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
