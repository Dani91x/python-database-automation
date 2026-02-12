import { NormalizedComparison, NormalizedTeam } from "@/lib/normalizePrediction";
import { BarChart3, Lightbulb, Swords, Shield, Users, Target, Calculator, TrendingUp } from "lucide-react";

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
    { key: 'poissonDistribution', label: 'Poisson Distribution', data: comparison.poissonDistribution, icon: Calculator },
    { key: 'total', label: 'Overall', data: comparison.total, icon: BarChart3 },
  ];

  // Generate insights based on comparison data
  const generateInsights = () => {
    const insights: string[] = [];
    
    if (comparison.total.homePercent > comparison.total.awayPercent) {
      insights.push(`${home.name} ha un vantaggio complessivo (${comparison.total.home} vs ${comparison.total.away})`);
    } else if (comparison.total.awayPercent > comparison.total.homePercent) {
      insights.push(`${away.name} ha un vantaggio complessivo (${comparison.total.away} vs ${comparison.total.home})`);
    }

    if (comparison.att.homePercent > comparison.att.awayPercent + 10) {
      insights.push(`${home.name} domina in attacco (${comparison.att.home})`);
    } else if (comparison.att.awayPercent > comparison.att.homePercent + 10) {
      insights.push(`${away.name} domina in attacco (${comparison.att.away})`);
    }

    if (comparison.def.homePercent > comparison.def.awayPercent + 10) {
      insights.push(`${home.name} ha una difesa più solida (${comparison.def.home})`);
    } else if (comparison.def.awayPercent > comparison.def.homePercent + 10) {
      insights.push(`${away.name} ha una difesa più solida (${comparison.def.away})`);
    }

    if (comparison.form.homePercent > comparison.form.awayPercent + 10) {
      insights.push(`${home.name} è in forma migliore (${comparison.form.home})`);
    } else if (comparison.form.awayPercent > comparison.form.homePercent + 10) {
      insights.push(`${away.name} è in forma migliore (${comparison.form.away})`);
    }

    if (home.last5.attPercent > 80) {
      insights.push(`${home.name} ha un attacco eccellente nelle ultime 5 (${home.last5.att})`);
    }
    if (away.last5.defPercent > 80) {
      insights.push(`${away.name} ha una difesa eccellente nelle ultime 5 (${away.last5.def})`);
    }

    return insights.slice(0, 6);
  };

  const insights = generateInsights();

  return (
    <section className="container mx-auto px-4 py-8">
      <div className="glass-card p-6 lg:p-8 animate-fade-in">
        <h2 className="font-display text-xl lg:text-2xl font-bold mb-6 flex items-center gap-3">
          <BarChart3 className="w-6 h-6 text-primary" />
          <span className="text-gradient-primary">Confronto Squadre</span>
        </h2>

        {/* Team Headers */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="flex items-center gap-3">
            <img src={home.logo} alt={home.name} className="w-10 h-10 object-contain" />
            <span className="font-heading font-semibold text-team-home">{home.name}</span>
          </div>
          <div className="text-center text-muted-foreground font-heading">VS</div>
          <div className="flex items-center justify-end gap-3">
            <span className="font-heading font-semibold text-neon-magenta">{away.name}</span>
            <img src={away.logo} alt={away.name} className="w-10 h-10 object-contain" />
          </div>
        </div>

        {/* Comparison Bars */}
        <div className="space-y-4">
          {comparisonItems.map((item) => {
            const Icon = item.icon;
            const homeWins = item.data.homePercent > item.data.awayPercent;
            const awayWins = item.data.awayPercent > item.data.homePercent;
            const isDraw = item.data.homePercent === item.data.awayPercent;

            return (
              <div key={item.key} className="group">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`font-display text-lg font-bold ${homeWins ? 'text-team-home' : 'text-muted-foreground'}`}>
                      {item.data.home}
                    </span>
                    {homeWins && <span className="text-xs text-team-home">▲</span>}
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Icon className="w-4 h-4" />
                    <span className="text-sm font-medium uppercase tracking-wider">{item.label}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {awayWins && <span className="text-xs text-neon-magenta">▲</span>}
                    <span className={`font-display text-lg font-bold ${awayWins ? 'text-neon-magenta' : 'text-muted-foreground'}`}>
                      {item.data.away}
                    </span>
                  </div>
                </div>
                <div className="h-3 rounded-full overflow-hidden bg-muted/30 flex">
                  <div 
                    className="h-full transition-all duration-700 ease-out rounded-l-full"
                    style={{ 
                      width: `${item.data.homePercent}%`,
                      background: homeWins 
                        ? 'linear-gradient(90deg, hsl(200, 100%, 55%), hsl(180, 100%, 50%))' 
                        : 'linear-gradient(90deg, hsl(200, 100%, 55% / 0.5), hsl(180, 100%, 50% / 0.5))',
                      boxShadow: homeWins ? '0 0 15px hsl(var(--home-team) / 0.5)' : 'none'
                    }}
                  />
                  <div 
                    className="h-full transition-all duration-700 ease-out rounded-r-full"
                    style={{ 
                      width: `${item.data.awayPercent}%`,
                      background: awayWins 
                        ? 'linear-gradient(90deg, hsl(320, 100%, 60%), hsl(280, 80%, 60%))' 
                        : 'linear-gradient(90deg, hsl(320, 100%, 60% / 0.5), hsl(280, 80%, 60% / 0.5))',
                      boxShadow: awayWins ? '0 0 15px hsl(var(--neon-magenta) / 0.5)' : 'none'
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Insights */}
        {insights.length > 0 && (
          <div className="mt-8 pt-6 border-t border-border/50">
            <h3 className="font-heading text-lg font-semibold mb-4 flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-accent" />
              Insights Automatici
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {insights.map((insight, index) => (
                <div 
                  key={index}
                  className="flex items-start gap-3 p-3 rounded-lg bg-muted/20 border border-border/30"
                >
                  <div className="w-6 h-6 rounded-full bg-accent/20 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-accent">{index + 1}</span>
                  </div>
                  <p className="text-sm text-foreground/90">{insight}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
