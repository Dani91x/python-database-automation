import { NormalizedLeague, NormalizedTeam, NormalizedPredictions } from "@/lib/normalizePrediction";
import { TrendingUp, Target, Percent, Trophy, AlertCircle } from "lucide-react";

interface HeroMatchProps {
  league: NormalizedLeague;
  home: NormalizedTeam;
  away: NormalizedTeam;
  predictions: NormalizedPredictions;
  fixtureId: string;
}

export function HeroMatch({ league, home, away, predictions, fixtureId }: HeroMatchProps) {
  return (
    <section className="relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 bg-gradient-hero" />
      <div className="absolute inset-0 grid-pattern opacity-30" />
      
      <div className="relative container mx-auto px-4 py-8 lg:py-12">
        {/* League Strip */}
        <div className="flex items-center justify-center gap-3 mb-8 animate-fade-in">
          {league.logo && (
            <img 
              src={league.logo} 
              alt={league.name} 
              className="w-10 h-10 object-contain"
            />
          )}
          <div className="flex items-center gap-2">
            <span className="font-heading text-lg lg:text-xl font-semibold text-foreground">
              {league.name}
            </span>
            <span className="text-muted-foreground">•</span>
            <span className="text-muted-foreground font-medium">{league.season}</span>
            <span className="text-muted-foreground">•</span>
            <span className="text-muted-foreground">{league.country}</span>
            {league.flag && (
              <img 
                src={league.flag} 
                alt={league.country} 
                className="w-5 h-4 object-cover rounded-sm ml-1"
              />
            )}
          </div>
        </div>

        {/* Match Row */}
        <div className="flex flex-col lg:flex-row items-center justify-center gap-6 lg:gap-12 mb-10">
          {/* Home Team */}
          <div className="flex items-center gap-4 animate-slide-in-left" style={{ animationDelay: '0.1s' }}>
            <div className="text-right hidden sm:block">
              <span className="home-badge mb-2 inline-block">HOME</span>
              <h2 className="font-display text-2xl lg:text-4xl font-bold neon-text-cyan">
                {home.name}
              </h2>
            </div>
            <div className="relative">
              <div className="w-20 h-20 lg:w-28 lg:h-28 rounded-full glass-card p-3 neon-glow-cyan">
                <img 
                  src={home.logo} 
                  alt={home.name}
                  className="w-full h-full object-contain"
                />
              </div>
            </div>
            <div className="text-left sm:hidden">
              <span className="home-badge mb-1 inline-block text-[10px]">HOME</span>
              <h2 className="font-display text-lg font-bold neon-text-cyan">
                {home.name}
              </h2>
            </div>
          </div>

          {/* VS */}
          <div className="animate-scale-in" style={{ animationDelay: '0.2s' }}>
            <div className="glass-card px-6 py-3 rounded-2xl animated-border">
              <span className="font-display text-2xl lg:text-3xl font-bold text-gradient-primary">
                VS
              </span>
            </div>
          </div>

          {/* Away Team */}
          <div className="flex items-center gap-4 animate-slide-in-right" style={{ animationDelay: '0.1s' }}>
            <div className="relative">
              <div className="w-20 h-20 lg:w-28 lg:h-28 rounded-full glass-card p-3 neon-glow-magenta">
                <img 
                  src={away.logo} 
                  alt={away.name}
                  className="w-full h-full object-contain"
                />
              </div>
            </div>
            <div className="text-left">
              <span className="away-badge mb-2 inline-block">AWAY</span>
              <h2 className="font-display text-2xl lg:text-4xl font-bold neon-text-magenta">
                {away.name}
              </h2>
            </div>
          </div>
        </div>

        {/* Match Info Chips */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-10 animate-fade-in" style={{ animationDelay: '0.3s' }}>
          <div className="glass-card px-4 py-2 rounded-full text-sm">
            <span className="text-muted-foreground">Fixture ID:</span>{" "}
            <span className="font-mono text-primary">{fixtureId}</span>
          </div>
          <div className="glass-card px-4 py-2 rounded-full text-sm">
            <span className="text-muted-foreground">League ID:</span>{" "}
            <span className="font-mono text-primary">{league.id}</span>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 max-w-5xl mx-auto">
          {/* 1X2 Percentages */}
          <div className="glass-card p-6 hover-lift animate-fade-in" style={{ animationDelay: '0.4s' }}>
            <div className="flex items-center gap-2 mb-4">
              <Percent className="w-5 h-5 text-primary" />
              <h3 className="font-heading text-lg font-semibold">Match Odds</h3>
            </div>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-team-home font-medium">Home</span>
                  <span className="font-display font-bold">{predictions.percent.home}</span>
                </div>
                <div className="progress-bar">
                  <div 
                    className="progress-bar-fill progress-bar-fill-primary"
                    style={{ width: `${predictions.percent.homePercent}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-accent font-medium">Draw</span>
                  <span className="font-display font-bold">{predictions.percent.draw}</span>
                </div>
                <div className="progress-bar">
                  <div 
                    className="progress-bar-fill progress-bar-fill-accent"
                    style={{ width: `${predictions.percent.drawPercent}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-neon-magenta font-medium">Away</span>
                  <span className="font-display font-bold">{predictions.percent.away}</span>
                </div>
                <div className="progress-bar">
                  <div 
                    className="progress-bar-fill progress-bar-fill-secondary"
                    style={{ width: `${predictions.percent.awayPercent}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Advice */}
          <div className="glass-card p-6 hover-lift animate-fade-in" style={{ animationDelay: '0.5s' }}>
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="w-5 h-5 text-neon-green" />
              <h3 className="font-heading text-lg font-semibold">Prediction Advice</h3>
            </div>
            <div className="flex flex-col h-[calc(100%-2rem)] justify-center">
              <p className="text-lg font-medium text-foreground leading-relaxed">
                {predictions.advice}
              </p>
              {predictions.winner && (
                <div className="mt-4 flex items-center gap-2">
                  <Trophy className="w-4 h-4 text-accent" />
                  <span className="text-sm text-muted-foreground">
                    Winner: <span className="text-accent font-semibold">{predictions.winner.name}</span>
                    {predictions.winner.comment && (
                      <span className="text-muted-foreground"> ({predictions.winner.comment})</span>
                    )}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Under/Over & Win or Draw */}
          <div className="glass-card p-6 hover-lift animate-fade-in" style={{ animationDelay: '0.6s' }}>
            <div className="flex items-center gap-2 mb-4">
              <Target className="w-5 h-5 text-secondary" />
              <h3 className="font-heading text-lg font-semibold">Goals & Outcome</h3>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Under/Over</span>
                <span className="font-display text-2xl font-bold text-gradient-secondary">
                  {predictions.underOver}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Win or Draw</span>
                <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                  predictions.winOrDraw 
                    ? 'bg-neon-green/20 text-neon-green border border-neon-green/50' 
                    : 'bg-destructive/20 text-destructive border border-destructive/50'
                }`}>
                  {predictions.winOrDraw ? 'YES' : 'NO'}
                </span>
              </div>
              <div className="pt-2 border-t border-border/50">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <AlertCircle className="w-4 h-4" />
                  <span>Predicted: Home {predictions.goals.home} / Away {predictions.goals.away}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
