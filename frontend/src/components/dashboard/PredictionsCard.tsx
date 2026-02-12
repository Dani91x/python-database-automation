/* eslint-disable @next/next/no-img-element */
// frontend/src/components/dashboard/PredictionsCard.tsx
import { NormalizedPredictions, NormalizedTeam } from "@/lib/normalize";
import { BrainCircuit, Trophy, Target, Cpu } from "lucide-react";
import { Badge, Card, Progress, cn } from "@/components/ui/shadcn-mini";

interface PredictionsCardProps {
    predictions: NormalizedPredictions;
    home: NormalizedTeam;
    away: NormalizedTeam;
}

export function PredictionsCard({ predictions, home, away }: PredictionsCardProps) {
    return (
        <section className="container mx-auto px-4 py-12">
            <Card className="p-10 border-brand-orange/20 relative overflow-hidden bg-gradient-to-br from-brand-orange/5 to-transparent backdrop-blur-3xl">
                <div className="absolute top-0 right-0 p-8 opacity-5">
                    <BrainCircuit className="w-40 h-40 text-brand-orange" />
                </div>

                <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-12 gap-6">
                    <h2 className="text-3xl font-black italic tracking-tighter flex items-center gap-4">
                        <BrainCircuit className="w-8 h-8 text-brand-orange" />
                        TERMINALE ALGORITMICO
                    </h2>
                    <div className="flex items-center gap-2 px-4 py-1 bg-brand-orange/10 border border-brand-orange/20 rounded-full text-[10px] font-black uppercase tracking-widest text-brand-orange">
                        Confidenza: Alta Efficienza
                    </div>
                </div>

                {/* Main Advice */}
                <div className="glass-panel p-10 rounded-[2rem] border-white/10 bg-white/5 mb-8 relative group overflow-hidden">
                    <div className="absolute -inset-10 bg-brand-orange/10 blur-3xl opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="relative flex items-start gap-8">
                        <div className="w-16 h-16 rounded-2xl bg-brand-orange/20 flex items-center justify-center shrink-0 border border-brand-orange/30">
                            <Target className="w-8 h-8 text-brand-orange" />
                        </div>
                        <div>
                            <span className="text-[10px] font-black uppercase tracking-widest text-brand-orange mb-2 block">Raccomandazione Primaria</span>
                            <p className="text-2xl md:text-3xl font-black leading-tight tracking-tighter italic">
                                &ldquo;{predictions.advice}&rdquo;
                            </p>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
                    {/* Winner Prediction */}
                    <Card className="p-8 border-white/5 flex items-center gap-8 relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10">
                            <Trophy className="w-12 h-12" />
                        </div>
                        <div className="relative w-24 h-24 rounded-full glass-panel p-4 border-brand-orange/30 shadow-[0_0_20px_rgba(255,153,0,0.2)]">
                            {predictions.winner ? (
                                <img
                                    src={predictions.winner.id === home.id ? home.logo : away.logo}
                                    alt={predictions.winner.name}
                                    className="w-full h-full object-contain"
                                />
                            ) : (
                                <Cpu className="w-full h-full text-brand-orange" />
                            )}
                        </div>
                        <div>
                            <span className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-1 block">Valore Selezionato</span>
                            <h3 className="text-3xl font-black italic tracking-tighter">{predictions.winner?.name || "Nessun Vincitore Chiaro"}</h3>
                            <p className="text-xs text-gray-500 font-bold uppercase mt-1 tracking-wider opacity-60">Confidenza probabilistica attiva</p>
                        </div>
                    </Card>

                    {/* Probabilities */}
                    <Card className="p-8 border-white/5">
                        <h3 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-6">Distribuzione Mercato</h3>
                        <div className="grid grid-cols-3 gap-6">
                            {['Casa', 'Pareggio', 'Ospite'].map((label, idx) => {
                                const percents = [predictions.percent.home, predictions.percent.draw, predictions.percent.away];
                                const fills = [predictions.percent.homePercent, predictions.percent.drawPercent, predictions.percent.awayPercent];
                                const colors = ["text-brand-orange", "text-gray-400", "text-neon-cyan"];
                                const barColors = ["bg-brand-orange", "bg-gray-400", "bg-neon-cyan"];

                                return (
                                    <div key={label} className="text-center">
                                        <div className={cn("text-2xl font-black italic", colors[idx])}>{percents[idx]}</div>
                                        <div className="text-[8px] font-black uppercase tracking-widest text-gray-500 mt-1">{label}</div>
                                        <Progress value={fills[idx]} className="h-1 mt-2" barClassName={barColors[idx]} />
                                    </div>
                                );
                            })}
                        </div>
                    </Card>
                </div>

                {/* Triple Stats */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                    <div className="p-6 bg-white/5 border border-white/10 rounded-2xl flex flex-col items-center">
                        <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Linea Algoritmo</span>
                        <span className="text-3xl font-black italic text-brand-orange">{predictions.underOver}</span>
                    </div>
                    <div className="p-6 bg-white/5 border border-white/10 rounded-2xl flex flex-col items-center">
                        <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Margine Sicurezza</span>
                        <Badge variant={predictions.winOrDraw ? "neon" : "destructive"} className="px-6 py-1 text-[10px] font-black uppercase tracking-[0.2em]">
                            {predictions.winOrDraw ? "PROTETTO" : "ALTA VOLATILITÀ"}
                        </Badge>
                    </div>
                    <div className="p-6 bg-white/5 border border-white/10 rounded-2xl flex flex-col items-center">
                        <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Proiezione Risultato</span>
                        <div className="flex items-center gap-3">
                            <span className="text-xl font-black text-brand-orange">H:{predictions.goals.home}</span>
                            <span className="text-white/20 font-black">/</span>
                            <span className="text-xl font-black text-neon-cyan">A:{predictions.goals.away}</span>
                        </div>
                    </div>
                </div>
            </Card>
        </section>
    );
}
