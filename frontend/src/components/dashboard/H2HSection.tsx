import { History, AlertCircle } from "lucide-react";

interface H2HSectionProps {
  h2h: any[];
  homeName: string;
  awayName: string;
}

export function H2HSection({ h2h, homeName, awayName }: H2HSectionProps) {
  if (!h2h || h2h.length === 0) {
    return (
      <section className="container mx-auto px-4 py-8">
        <div className="glass-card p-6 lg:p-8 animate-fade-in">
          <h2 className="font-display text-xl lg:text-2xl font-bold mb-6 flex items-center gap-3">
            <History className="w-6 h-6 text-muted-foreground" />
            <span>Head to Head</span>
          </h2>
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-16 h-16 rounded-full bg-muted/30 flex items-center justify-center mb-4">
              <AlertCircle className="w-8 h-8 text-muted-foreground" />
            </div>
            <h3 className="font-heading text-lg font-semibold text-muted-foreground mb-2">
              H2H non disponibile
            </h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Non ci sono dati storici disponibili per gli scontri diretti tra {homeName} e {awayName}.
            </p>
          </div>
        </div>
      </section>
    );
  }

  // If h2h data is available, render the matches
  return (
    <section className="container mx-auto px-4 py-8">
      <div className="glass-card p-6 lg:p-8 animate-fade-in">
        <h2 className="font-display text-xl lg:text-2xl font-bold mb-6 flex items-center gap-3">
          <History className="w-6 h-6 text-primary" />
          <span className="text-gradient-primary">Head to Head</span>
        </h2>
        <div className="space-y-3">
          {h2h.map((match: any, index: number) => (
            <div 
              key={index}
              className="glass-card p-4 rounded-lg flex items-center justify-between"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">
                  {match.fixture?.date ? new Date(match.fixture.date).toLocaleDateString() : 'N/D'}
                </span>
              </div>
              <div className="flex items-center gap-4">
                <span className="font-heading font-semibold">{match.teams?.home?.name || 'N/D'}</span>
                <span className="font-display text-xl font-bold text-primary">
                  {match.goals?.home ?? '-'} - {match.goals?.away ?? '-'}
                </span>
                <span className="font-heading font-semibold">{match.teams?.away?.name || 'N/D'}</span>
              </div>
              <div className="text-sm text-muted-foreground">
                {match.league?.name || 'N/D'}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
