import { NormalizedPredictions, NormalizedLeague, NormalizedTeam } from '@/lib/normalize';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { format } from 'date-fns';
import { it } from 'date-fns/locale';

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
            {/* Background Glows */}
            <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-r from-neon-cyan/5 via-transparent to-neon-magenta/5 pointer-events-none" />

            <div className="p-8 relative z-10">
                {/* Header League */}
                <div className="flex justify-between items-center mb-12 border-b border-white/5 pb-4">
                    <div className="flex items-center gap-4">
                        <img src={league.logo} alt={league.name} className="w-10 h-10 object-contain drop-shadow-md" />
                        <div>
                            <h2 className="text-xl font-orbitron font-bold uppercase tracking-wider text-white">{league.name}</h2>
                            <p className="text-sm text-muted-foreground font-rajdhani font-semibold">{league.country} • Stagione {league.season}</p>
                        </div>
                    </div>
                    <Badge variant="outline" className="font-mono text-xs border-brand-orange/30 text-brand-orange bg-brand-orange/5 animate-pulse">
                        LIVE ANALYSIS
                    </Badge>
                </div>

                {/* Teams Layout */}
                <div className="flex flex-col md:flex-row items-center justify-between gap-8 md:gap-16">

                    {/* HOME TEAM */}
                    <div className="flex flex-col items-center flex-1 text-center w-full">
                        <div className="relative mb-6 group">
                            <div className="absolute inset-0 bg-neon-cyan/20 blur-[40px] rounded-full opacity-50 group-hover:opacity-80 transition-opacity duration-500" />
                            <div className="w-32 h-32 relative z-10 p-4 glass-card rounded-full border-neon-cyan/30 flex items-center justify-center">
                                <img src={home.logo} alt={home.name} className="w-full h-full object-contain" />
                            </div>
                            <Badge className="absolute -bottom-3 left-1/2 -translate-x-1/2 bg-neon-cyan text-black hover:bg-neon-cyan font-bold shadow-[0_0_15px_rgba(0,240,255,0.4)]">
                                HOME
                            </Badge>
                        </div>
                        <h1 className="text-3xl md:text-4xl font-orbitron font-black uppercase text-transparent bg-clip-text bg-gradient-to-br from-white to-gray-400">
                            {home.name}
                        </h1>
                    </div>

                    {/* VS / INFO */}
                    <div className="flex flex-col items-center justify-center shrink-0">
                        <div className="text-4xl font-black font-orbitron text-white/20 mb-2">VS</div>
                        <div className="text-sm font-rajdhani font-semibold text-brand-orange uppercase tracking-widest bg-brand-orange/10 px-4 py-1 rounded-full border border-brand-orange/20">
                            {formattedDate}
                        </div>
                    </div>

                    {/* AWAY TEAM */}
                    <div className="flex flex-col items-center flex-1 text-center w-full">
                        <div className="relative mb-6 group">
                            <div className="absolute inset-0 bg-neon-magenta/20 blur-[40px] rounded-full opacity-50 group-hover:opacity-80 transition-opacity duration-500" />
                            <div className="w-32 h-32 relative z-10 p-4 glass-card rounded-full border-neon-magenta/30 flex items-center justify-center">
                                <img src={away.logo} alt={away.name} className="w-full h-full object-contain" />
                            </div>
                            <Badge className="absolute -bottom-3 left-1/2 -translate-x-1/2 bg-neon-magenta text-white hover:bg-neon-magenta font-bold shadow-[0_0_15px_rgba(255,0,110,0.4)]">
                                AWAY
                            </Badge>
                        </div>
                        <h1 className="text-3xl md:text-4xl font-orbitron font-black uppercase text-transparent bg-clip-text bg-gradient-to-bl from-white to-gray-400">
                            {away.name}
                        </h1>
                    </div>
                </div>
            </div>
        </Card>
    );
}
