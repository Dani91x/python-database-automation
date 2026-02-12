// frontend/src/components/dashboard/ComparisonSection.tsx
import { NormalizedComparison, NormalizedTeam } from "@/lib/normalize";
import { BarChart3, Lightbulb, Swords, Shield, Users, Target, Calculator, TrendingUp } from "lucide-react";
import { cn, Progress } from "@/components/ui/shadcn-mini";

interface ComparisonSectionProps {
    comparison: NormalizedComparison;
    home: NormalizedTeam;
    away: NormalizedTeam;
}

export function ComparisonSection({ comparison, home, away }: ComparisonSectionProps) {
    const comparisonItems = [
        { key: 'form', label: 'Form', data: comparison.form, icon: TrendingUp },
        { key: 'att', label: 'Attack', data: comparison.att, icon: Swords },
        { key: 'def', label: 'Defense', data: comparison.def, icon: Shield },
        { key: 'h2h', label: 'Head to Head', data: comparison.h2h, icon: Users },
        { key: 'goals', label: 'Goals', data: comparison.goals, icon: Target },
        { key: 'poissonDistribution', label: 'Poisson', data: comparison.poissonDistribution, icon: Calculator },
    ];

    const generateInsights = () => {
        const insights: string[] = [];
        if (comparison.total.homePercent > comparison.total.awayPercent + 5) {
            insights.push(`${home.name} holds a structural advantage in overall metrics.`);
        } else if (comparison.total.awayPercent > comparison.total.homePercent + 5) {
            insights.push(`${away.name} leads in aggregate statistical data.`);
        }
        if (comparison.form.homePercent > comparison.form.awayPercent + 15) {
            insights.push(`Significant momentum gap favoring ${home.name}.`);
        } else if (comparison.form.awayPercent > comparison.form.homePercent + 15) {
            insights.push(`Momentum strongly favors the away side.`);
        }
        return insights;
    };

    const insights = generateInsights();

    return (
        <section className="container mx-auto px-4 py-12">
            <div className="glass-panel p-10 rounded-[2.5rem] border-white/5 relative overflow-hidden backdrop-blur-3xl">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-brand-orange via-white/20 to-neon-cyan" />

                <div className="flex flex-col md:flex-row justify-between items-center mb-12 gap-6">
                    <h2 className="text-3xl font-black italic tracking-tighter flex items-center gap-4">
                        <BarChart3 className="w-8 h-8 text-brand-orange" />
                        QUANTITATIVE COMPARISON
                    </h2>
                    <div className="flex items-center gap-4 bg-white/5 px-6 py-2 rounded-full border border-white/10">
                        <div className="flex items-center gap-2">
                            <img src={home.logo} className="w-6 h-6 object-contain" />
                            <span className="text-[10px] font-black uppercase text-brand-orange">{home.name}</span>
                        </div>
                        <span className="text-white/20 font-black">VS</span>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] font-black uppercase text-neon-cyan">{away.name}</span>
                            <img src={away.logo} className="w-6 h-6 object-contain" />
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-16 gap-y-10">
                    {comparisonItems.map((item) => {
                        const Icon = item.icon;
                        const homeWins = item.data.homePercent > item.data.awayPercent;
                        const awayWins = item.data.awayPercent > item.data.homePercent;

                        return (
                            <div key={item.key} className="group">
                                <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                        <span className={cn("text-xl font-black italic", homeWins ? "text-brand-orange" : "text-white/40")}>
                                            {item.data.home}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2 opacity-40 group-hover:opacity-100 transition-opacity">
                                        <Icon className="w-3 h-3" />
                                        <span className="text-[9px] font-black uppercase tracking-[0.2em]">{item.label}</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-right">
                                        <span className={cn("text-xl font-black italic", awayWins ? "text-neon-cyan" : "text-white/40")}>
                                            {item.data.away}
                                        </span>
                                    </div>
                                </div>
                                <div className="h-2 rounded-full overflow-hidden bg-white/5 flex p-0.5 border border-white/5">
                                    <div
                                        className={cn("h-full transition-all duration-1000 rounded-l-full", homeWins ? "bg-brand-orange shadow-[0_0_10px_rgba(255,153,0,0.5)]" : "bg-white/10")}
                                        style={{ width: `${item.data.homePercent}%` }}
                                    />
                                    <div
                                        className={cn("h-full transition-all duration-1000 rounded-r-full", awayWins ? "bg-neon-cyan shadow-[0_0_10px_rgba(0,240,255,0.5)]" : "bg-white/10")}
                                        style={{ width: `${item.data.awayPercent}%` }}
                                    />
                                </div>
                            </div>
                        );
                    })}
                </div>

                {insights.length > 0 && (
                    <div className="mt-16 grid grid-cols-1 md:grid-cols-2 gap-4">
                        {insights.map((insight, i) => (
                            <div key={i} className="flex gap-4 p-5 bg-white/5 rounded-2xl border border-white/10 group hover:border-brand-orange/30 transition-colors">
                                <div className="w-10 h-10 rounded-full bg-brand-orange/10 flex items-center justify-center shrink-0 border border-brand-orange/20">
                                    <Lightbulb className="w-5 h-5 text-brand-orange" />
                                </div>
                                <p className="text-sm font-bold leading-snug">{insight}</p>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </section>
    );
}
