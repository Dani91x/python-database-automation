import { NormalizedPredictions, NormalizedTeam } from "@/lib/normalize";
import { Trophy, Target, CircleDot, Info } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface PredictionsCardProps {
    predictions: NormalizedPredictions;
    home: NormalizedTeam;
    away: NormalizedTeam;
}

export function PredictionsCard({ predictions }: PredictionsCardProps) {
    return (
        <section className="mb-12">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* 1. MATCH ODDS */}
                <Card className="glass-card p-6 md:p-8 rounded-2xl border-white/5 bg-white/[0.03] flex flex-col">
                    <div className="flex items-center gap-3 mb-8">
                        <CircleDot className="w-5 h-5 text-emerald-400" />
                        <h3 className="text-lg font-black font-display text-white tracking-tight italic uppercase">% Match Odds</h3>
                    </div>

                    <div className="space-y-6 flex-1 flex flex-col justify-center">
                        <div className="space-y-2">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-widest">
                                <span className="text-white/60">Home</span>
                                <span className="text-white">{predictions.percent.home}</span>
                            </div>
                            <Progress value={predictions.percent.homePercent} className="h-2 bg-white/5" indicatorClassName="bg-emerald-500" />
                        </div>

                        <div className="space-y-2">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-widest">
                                <span className="text-emerald-400">Draw</span>
                                <span className="text-white">{predictions.percent.draw}</span>
                            </div>
                            <Progress value={predictions.percent.drawPercent} className="h-2 bg-white/5" indicatorClassName="bg-emerald-400" />
                        </div>

                        <div className="space-y-2">
                            <div className="flex justify-between text-xs font-bold uppercase tracking-widest">
                                <span className="text-white/60">Away</span>
                                <span className="text-white">{predictions.percent.away}</span>
                            </div>
                            <Progress value={predictions.percent.awayPercent} className="h-2 bg-white/5" indicatorClassName="bg-amber-500" />
                        </div>
                    </div>
                </Card>

                {/* 2. PREDICTION ADVICE */}
                <Card className="glass-card p-6 md:p-8 rounded-2xl border-white/5 bg-white/[0.03] flex flex-col relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none group-hover:scale-110 transition-transform duration-700">
                        <Target className="w-32 h-32 text-white" />
                    </div>

                    <div className="flex items-center gap-3 mb-8">
                        <Target className="w-5 h-5 text-emerald-400" />
                        <h3 className="text-lg font-black font-display text-white tracking-tight italic uppercase">Prediction Advice</h3>
                    </div>

                    <div className="flex-1 flex flex-col justify-center gap-6 relative z-10">
                        <p className="text-xl md:text-2xl font-black text-white italic tracking-tighter leading-tight drop-shadow-md">
                            &ldquo;{predictions.advice}&rdquo;
                        </p>

                        {predictions.winner && (
                            <div className="flex flex-wrap items-center gap-2 pt-4 border-t border-white/5 w-full">
                                <Trophy className="w-4 h-4 text-emerald-400 shrink-0" />
                                <span className="text-sm font-bold text-white/50 whitespace-nowrap">Winner: </span>
                                <span className="text-sm font-black text-emerald-400 uppercase tracking-wider italic break-words flex-1 min-w-0">
                                    {predictions.winner.name} <span className="text-[10px] text-white/40 normal-case font-bold ml-1 inline-block">({predictions.winner.comment})</span>
                                </span>
                            </div>
                        )}
                    </div>
                </Card>

                {/* 3. GOALS & OUTCOME */}
                <Card className="glass-card p-6 md:p-8 rounded-2xl border-white/5 bg-white/[0.03] flex flex-col">
                    <div className="flex items-center gap-3 mb-8">
                        <CircleDot className="w-5 h-5 text-amber-500" />
                        <h3 className="text-lg font-black font-display text-white tracking-tight italic uppercase">Goals & Outcome</h3>
                    </div>

                    <div className="space-y-8 flex-1 flex flex-col justify-center">
                        <div className="flex items-center justify-between border-b border-white/5 pb-4">
                            <span className="text-sm font-bold text-white/60">Under/Over</span>
                            <span className="text-2xl font-black font-display italic text-amber-400 tracking-tighter">{predictions.underOver}</span>
                        </div>

                        <div className="flex items-center justify-between border-b border-white/5 pb-4">
                            <span className="text-sm font-bold text-white/60">Win or Draw</span>
                            <span className="bg-white/5 border border-white/10 px-4 py-1 rounded-lg text-sm font-black text-white italic tracking-widest">
                                {predictions.winOrDraw ? 'YES' : 'NO'}
                            </span>
                        </div>

                        <div className="flex items-center gap-2 text-white/40">
                            <Info className="w-4 h-4" />
                            <span className="text-[10px] font-bold uppercase tracking-wider">
                                Predicted: Home {predictions.goals.home || '0'} / Away {predictions.goals.away || '0'}
                            </span>
                        </div>
                    </div>
                </Card>
            </div>
        </section>
    );
}
