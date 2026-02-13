import { NormalizedPredictions, NormalizedLeague, NormalizedTeam } from '@/lib/normalize';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { format } from 'date-fns';
import { it } from 'date-fns/locale';
import { TrendingUp, AlertTriangle } from 'lucide-react';

interface HeroMatchProps {
    home: NormalizedTeam;
    away: NormalizedTeam;
    league: NormalizedLeague;
    prediction: NormalizedPredictions;
    matchDate?: string;
}

export function HeroMatch({ home, away, league, prediction, matchDate }: HeroMatchProps) {
    const formattedDate = matchDate
        ? format(new Date(matchDate), "d MMMM yyyy • HH:mm", { locale: it })
        : "Data non disponibile";

    return (
        <Card className="glass-card mb-8 overflow-hidden relative border-none">
            {/* Background Effects */}
            <div className="absolute inset-0 bg-gradient-hero" />
            <div className="absolute inset-0 grid-pattern opacity-30" />

            <div className="p-4 md:p-8 relative z-10">
                {/* Header League */}
                <div className="flex flex-wrap justify-between items-center mb-6 md:mb-10 border-b border-white/5 pb-4 gap-4">
                    <div className="flex items-center gap-3 md:gap-4">
                        <img src={league.logo} alt={league.name} className="w-8 h-8 md:w-10 md:h-10 object-contain drop-shadow-md" />
                        <div>
                            <h2 className="text-sm md:text-xl font-display font-bold uppercase tracking-wider text-foreground line-clamp-1">{league.name}</h2>
                            <p className="text-[10px] md:text-sm text-muted-foreground font-heading font-semibold">{league.country} • {league.season}</p>
                        </div>
                    </div>
                    <Badge variant="outline" className="font-mono text-[10px] md:text-xs border-primary/30 text-primary bg-primary/5 animate-pulse">
                        LIVE ANALYSIS
                    </Badge>
                </div>

                {/* Teams Layout */}
                <div className="flex flex-col md:flex-row items-center justify-between gap-8 md:gap-16 mb-12">

                    {/* HOME TEAM */}
                    <div className="flex flex-col items-center flex-1 text-center w-full">
                        <div className="relative mb-6 group">
                            <div className="absolute inset-0 bg-primary/20 blur-[40px] rounded-full opacity-50 group-hover:opacity-80 transition-opacity duration-500" />
                            <div className="w-32 h-32 relative z-10 p-4 glass-card rounded-full neon-glow-primary flex items-center justify-center">
                                <img src={home.logo} alt={home.name} className="w-full h-full object-contain" />
                            </div>
                            <div className="absolute -bottom-3 left-1/2 -translate-x-1/2">
                                <span className="home-badge">HOME</span>
                            </div>
                        </div>
                        <h1 className="text-3xl md:text-4xl font-display font-bold uppercase neon-text-primary">
                            {home.name}
                        </h1>
                    </div>

                    {/* VS / INFO */}
                    <div className="flex flex-col items-center justify-center shrink-0 order-first md:order-none mb-4 md:mb-0">
                        <div className="glass-card animated-border px-4 py-1.5 md:px-6 md:py-2 rounded-xl mb-3 md:mb-4">
                            <span className="text-2xl md:text-4xl font-black font-display text-gradient-primary">VS</span>
                        </div>
                        <div className="text-[10px] md:text-sm font-heading font-semibold text-muted-foreground uppercase tracking-widest bg-muted/20 px-3 py-1 md:px-4 md:py-1 rounded-full border border-white/5">
                            {formattedDate}
                        </div>
                    </div>

                    {/* AWAY TEAM */}
                    <div className="flex flex-col items-center flex-1 text-center w-full">
                        <div className="relative mb-6 group">
                            <div className="absolute inset-0 bg-secondary/20 blur-[40px] rounded-full opacity-50 group-hover:opacity-80 transition-opacity duration-500" />
                            <div className="w-32 h-32 relative z-10 p-4 glass-card rounded-full neon-glow-gold flex items-center justify-center">
                                <img src={away.logo} alt={away.name} className="w-full h-full object-contain" />
                            </div>
                            <div className="absolute -bottom-3 left-1/2 -translate-x-1/2">
                                <span className="away-badge">AWAY</span>
                            </div>
                        </div>
                        <h1 className="text-3xl md:text-4xl font-display font-bold uppercase neon-text-gold">
                            {away.name}
                        </h1>
                    </div>
                </div>

                {/* Prediction Stats / Progress Bars */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {/* Home Probability */}
                    <div className="glass-card p-4 rounded-xl">
                        <div className="flex justify-between mb-2">
                            <span className="text-team-home font-bold">Win Probability</span>
                            <span className="text-white font-mono">{prediction.percent.home}</span>
                        </div>
                        <div className="progress-bar">
                            <div
                                className="progress-bar-fill progress-bar-fill-primary"
                                style={{ width: prediction.percent.home }}
                            />
                        </div>
                    </div>

                    {/* Win or Draw Indicator */}
                    <div className={`glass-card p-4 rounded-xl flex items-center justify-center gap-3 border ${prediction.winOrDraw ? 'bg-result-win/10 border-result-win/30' : 'bg-destructive/10 border-destructive/30'}`}>
                        {prediction.winOrDraw ? (
                            <>
                                <TrendingUp className="w-5 h-5 text-result-win" />
                                <span className="text-result-win font-heading font-bold uppercase">Win or Draw: YES</span>
                            </>
                        ) : (
                            <>
                                <AlertTriangle className="w-5 h-5 text-destructive" />
                                <span className="text-destructive font-heading font-bold uppercase">Win or Draw: NO</span>
                            </>
                        )}
                    </div>

                    {/* Away Probability */}
                    <div className="glass-card p-4 rounded-xl">
                        <div className="flex justify-between mb-2">
                            <span className="text-team-away font-bold">Win Probability</span>
                            <span className="text-white font-mono">{prediction.percent.away}</span>
                        </div>
                        <div className="progress-bar">
                            <div
                                className="progress-bar-fill progress-bar-fill-secondary"
                                style={{ width: prediction.percent.away }}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}
