import { NormalizedPredictions, NormalizedTeam } from "@/lib/normalizePrediction";
import { Brain, Trophy, Target, Percent, Share2, Bookmark, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "@/hooks/use-toast";

interface PredictionsCardProps {
  predictions: NormalizedPredictions;
  home: NormalizedTeam;
  away: NormalizedTeam;
}

export function PredictionsCard({ predictions, home, away }: PredictionsCardProps) {
  const handleSave = () => {
    toast({
      title: "Pronostico salvato",
      description: "Il pronostico è stato salvato con successo.",
    });
  };

  const handleWatchlist = () => {
    toast({
      title: "Aggiunto alla watchlist",
      description: "La partita è stata aggiunta alla tua watchlist.",
    });
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: `${home.name} vs ${away.name} - Prediction`,
        text: predictions.advice,
        url: window.location.href,
      });
    } else {
      navigator.clipboard.writeText(window.location.href);
      toast({
        title: "Link copiato",
        description: "Il link è stato copiato negli appunti.",
      });
    }
  };

  return (
    <section className="container mx-auto px-4 py-8">
      <div className="glass-card p-6 lg:p-8 animated-border animate-fade-in">
        <h2 className="font-display text-xl lg:text-2xl font-bold mb-6 flex items-center gap-3">
          <Brain className="w-6 h-6 text-secondary animate-pulse-subtle" />
          <span className="text-gradient-secondary">Prediction Engine</span>
        </h2>

        {/* Main Advice */}
        <div className="glass-card p-6 rounded-xl bg-gradient-to-r from-primary/5 to-secondary/5 border-primary/20 mb-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
              <Target className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h3 className="font-heading text-lg font-semibold text-muted-foreground mb-2">Consiglio</h3>
              <p className="font-display text-xl lg:text-2xl font-bold leading-relaxed">
                {predictions.advice}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Winner Suggestion */}
          <div className="glass-card p-5 rounded-xl">
            <h3 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
              <Trophy className="w-4 h-4 text-accent" />
              Vincitore Suggerito
            </h3>
            {predictions.winner ? (
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full glass-card p-2 pulse-glow">
                  <img 
                    src={predictions.winner.id === home.id ? home.logo : away.logo}
                    alt={predictions.winner.name}
                    className="w-full h-full object-contain"
                  />
                </div>
                <div>
                  <div className="font-display text-2xl font-bold text-accent">
                    {predictions.winner.name}
                  </div>
                  {predictions.winner.comment && (
                    <div className="text-sm text-muted-foreground mt-1">
                      {predictions.winner.comment}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground">N/D</p>
            )}
          </div>

          {/* 1X2 Percent */}
          <div className="glass-card p-5 rounded-xl">
            <h3 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
              <Percent className="w-4 h-4" />
              Probabilità 1X2
            </h3>
            <div className="grid grid-cols-3 gap-3">
              <div className="text-center">
                <div className="font-display text-2xl font-bold text-team-home">{predictions.percent.home}</div>
                <div className="stat-label mt-1">Home</div>
                <div className="progress-bar mt-2">
                  <div 
                    className="progress-bar-fill progress-bar-fill-primary"
                    style={{ width: `${predictions.percent.homePercent}%` }}
                  />
                </div>
              </div>
              <div className="text-center">
                <div className="font-display text-2xl font-bold text-accent">{predictions.percent.draw}</div>
                <div className="stat-label mt-1">Draw</div>
                <div className="progress-bar mt-2">
                  <div 
                    className="progress-bar-fill progress-bar-fill-accent"
                    style={{ width: `${predictions.percent.drawPercent}%` }}
                  />
                </div>
              </div>
              <div className="text-center">
                <div className="font-display text-2xl font-bold text-neon-magenta">{predictions.percent.away}</div>
                <div className="stat-label mt-1">Away</div>
                <div className="progress-bar mt-2">
                  <div 
                    className="progress-bar-fill progress-bar-fill-secondary"
                    style={{ width: `${predictions.percent.awayPercent}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Under/Over & Win or Draw & Predicted Goals */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <div className="glass-card p-4 rounded-xl text-center">
            <div className="stat-label mb-2">Under/Over</div>
            <div className="font-display text-3xl font-bold text-gradient-primary">{predictions.underOver}</div>
          </div>
          <div className="glass-card p-4 rounded-xl text-center">
            <div className="stat-label mb-2">Win or Draw</div>
            <div className={`inline-flex px-4 py-2 rounded-full text-lg font-bold ${
              predictions.winOrDraw 
                ? 'bg-neon-green/20 text-neon-green border border-neon-green/50' 
                : 'bg-destructive/20 text-destructive border border-destructive/50'
            }`}>
              {predictions.winOrDraw ? 'TRUE' : 'FALSE'}
            </div>
          </div>
          <div className="glass-card p-4 rounded-xl text-center">
            <div className="stat-label mb-2">Predicted Goals</div>
            <div className="flex items-center justify-center gap-3">
              <span className="font-display text-xl font-bold text-team-home">H: {predictions.goals.home}</span>
              <span className="text-muted-foreground">/</span>
              <span className="font-display text-xl font-bold text-neon-magenta">A: {predictions.goals.away}</span>
            </div>
          </div>
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-wrap justify-center gap-4">
          <Button 
            onClick={handleSave}
            className="bg-gradient-to-r from-primary to-neon-blue hover:opacity-90 text-primary-foreground font-heading font-semibold px-6"
          >
            <Save className="w-4 h-4 mr-2" />
            Salva Pronostico
          </Button>
          <Button 
            onClick={handleWatchlist}
            variant="outline"
            className="border-accent/50 text-accent hover:bg-accent/10 font-heading font-semibold px-6"
          >
            <Bookmark className="w-4 h-4 mr-2" />
            Aggiungi a Watchlist
          </Button>
          <Button 
            onClick={handleShare}
            variant="outline"
            className="border-secondary/50 text-secondary hover:bg-secondary/10 font-heading font-semibold px-6"
          >
            <Share2 className="w-4 h-4 mr-2" />
            Condividi
          </Button>
        </div>
      </div>
    </section>
  );
}
