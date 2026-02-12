import { NormalizedPredictions, NormalizedTeam } from "@/lib/normalize";
import { BrainCircuit, Trophy, Target, Cpu } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface PredictionsCardProps {
    predictions: NormalizedPredictions;
    home: NormalizedTeam;
    away: NormalizedTeam;
    fixtureId?: string; // fallback x key
}

export function PredictionsCard({ predictions, home, away }: PredictionsCardProps) {
    return (
        <section className="mb-8">
            <Card className="p-10 border-brand-orange/20 relative overflow-hidden bg-gradient-to-br from-brand-orange/5 to-transparent backdrop-blur-3xl shadow-[0_0_40px_rgba(255,153,0,0.05)]">
                <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
                    <BrainCircuit className="w-40 h-40 text-brand-orange" />
                </div>

                <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-12 gap-6 relative z-10">
                    <h2 className="text-3xl font-orbitron font-black italic tracking-tighter flex items-center gap-4 text-white">
                        <BrainCircuit className="w-8 h-8 text-brand-orange animate-pulse" />
                        TERMINALE ALGORITMICO
                    </h2>
                    <div className="flex items-center gap-2 px-4 py-1 bg-brand-orange/10 border border-brand-orange/20 rounded-full text-[10px] font-black uppercase tracking-widest text-brand-orange">
                        Confidenza: Alta Efficienza
                    </div>
                </div>

                {/* Main Advice */}
                <div className="glass-card p-10 rounded-[2rem] border-white/10 bg-white/5 mb-8 relative group overflow-hidden">
                    <div className="absolute -inset-10 bg-brand-orange/10 blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
                    <div className="relative flex items-start gap-8">
                        <div className="w-16 h-16 rounded-2xl bg-brand-orange/20 flex items-center justify-center shrink-0 border border-brand-orange/30 shadow-[0_0_20px_rgba(255,153,0,0.15)]">
                            <Target className="w-8 h-8 text-brand-orange" />
                        </div>
                        <div>
                            <span className="text-[10px] font-black uppercase tracking-widest text-brand-orange mb-2 block">Raccomandazione Primaria</span>
                            <p className="text-2xl md:text-3xl font-black leading-tight tracking-tighter italic text-white/90">
                                &ldquo;{predictions.advice}&rdquo;
                            </p>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
                    {/* Winner Prediction */}
                    <Card className="p-8 border-white/5 flex items-center gap-8 relative overflow-hidden glass-card hover:bg-white/10 transition-colors">
                        <div className="absolute top-0 right-0 p-4 opacity-10">
                            <Trophy className="w-12 h-12 text-white" />
                        </div>
                        <div className="relative w-24 h-24 rounded-full bg-black/40 p-4 border border-brand-orange/30 shadow-[0_0_20px_rgba(255,153,0,0.2)] shrink-0 flex items-center justify-center">
                            {predictions.winner ? (
                                <img
                                    src={predictions.winner.id === home.id ? home.logo : away.logo}
                                    alt={predictions.winner.name}
                                    className="w-full h-full object-contain"
                                />
                            ) : (
                                <Cpu className="w-full h-full text-brand-orange p-4" />
                            )}
                        </div>
                        <div>
                            <span className="text-[10px] font-black tracking-widest text-muted-foreground mb-1 block">Valore Selezionato</span>
                            <h3 className="text-3xl font-orbitron font-black italic tracking-tighter text-white">
                                {predictions.winner?.name || "Nessun Vincitore Chiaro"}
                            </h3>
                            <p className="text-xs text-brand-orange font-bold uppercase mt-1 tracking-wider opacity-80">
                                Confidenza probabilistica attiva
                            </p>
                        </div>
                    </Card>

                    {/* Probabilities */}
                    <Card className="p-8 border-white/5 glass-card">
                        <h3 className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-6">Distribuzione Mercato</h3>
                        <div className="grid grid-cols-3 gap-6">
                            {['Casa', 'Pareggio', 'Ospite'].map((label, idx) => {
                                const percents = [predictions.percent.home, predictions.percent.draw, predictions.percent.away];
                                const fills = [predictions.percent.homePercent, predictions.percent.drawPercent, predictions.percent.awayPercent];
                                const colors = ["text-neon-cyan", "text-gray-400", "text-neon-magenta"];
                                const barColors = ["bg-neon-cyan", "bg-gray-400", "bg-neon-magenta"];

                                return (
                                    <div key={label} className="text-center group">
                                        <div className={cn("text-2xl font-black italic mb-2 transition-transform group-hover:scale-110", colors[idx])}>
                                            {percents[idx]}
                                        </div>
                                        <div className="text-[8px] font-black uppercase tracking-widest text-muted-foreground mb-3">{label}</div>
                                        <Progress value={fills[idx]} className="h-1.5 bg-white/10" indicatorClassName={barColors[idx]} />
                                    </div>
                                );
                            })}
                        </div>
                    </Card>
                </div>

                {/* Triple Stats */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                    <div className="p-6 bg-white/5 border border-white/10 rounded-2xl flex flex-col items-center hover:bg-white/10 transition-colors">
                        <span className="text-[10px] font-black text-muted-foreground uppercase tracking-widest mb-2">Linea Algoritmo</span>
                        <span className="text-3xl font-orbitron font-black italic text-brand-orange">{predictions.underOver}</span>
                    </div>
                    <div className="p-6 bg-white/5 border border-white/10 rounded-2xl flex flex-col items-center hover:bg-white/10 transition-colors">
                        <span className="text-[10px] font-black text-muted-foreground uppercase tracking-widest mb-2">Margine Sicurezza</span>
                        <Badge variant={predictions.winOrDraw ? "secondary" : "destructive"} className="px-6 py-1 text-xs font-black uppercase rounded-full">
                            {predictions.winOrDraw ? "Win/Draw Coperto" : "Rischio Alto"}
                        </Badge>
                    </div>
                    <div className="p-6 bg-white/5 border border-white/10 rounded-2xl flex flex-col items-center hover:bg-white/10 transition-colors">
                        <span className="text-[10px] font-black text-muted-foreground uppercase tracking-widest mb-2">Predicted Goals</span>
                        <div className="flex items-center gap-4 text-xl font-bold font-mono">
                            <span className="text-neon-cyan">{predictions.goals.home ?? "-"}</span>
                            <span className="text-white/20">:</span>
                            <span className="text-neon-magenta">{predictions.goals.away ?? "-"}</span>
                        </div>
                    </div>
                </div>
            </Card>
        </section>
    );
}
