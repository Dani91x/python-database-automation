import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { TeamLeagueStats } from "@/lib/normalizePrediction";
import { AlertTriangle, Ban } from "lucide-react";

interface CardsByMinuteProps {
  cards: TeamLeagueStats['cards'];
  side: 'home' | 'away';
}

export function CardsByMinute({ cards, side }: CardsByMinuteProps) {
  const hasYellowData = Object.values(cards.yellow).some(v => v.total !== null);
  const hasRedData = Object.values(cards.red).some(v => v.total !== null);

  const renderCardHeatmap = (cardData: Record<string, { total: number | null; percentage: string | null }>, color: string) => {
    const entries = Object.entries(cardData);
    const maxTotal = Math.max(...entries.map(([, v]) => v.total ?? 0));

    if (!entries.some(([, v]) => v.total !== null)) {
      return (
        <div className="text-center py-4 text-muted-foreground text-sm">
          Nessun dato disponibile
        </div>
      );
    }

    return (
      <div className="grid grid-cols-4 gap-2">
        {entries.map(([minute, data]) => {
          const intensity = maxTotal > 0 && data.total !== null ? data.total / maxTotal : 0;
          return (
            <div
              key={minute}
              className="glass-card p-2 rounded-lg text-center transition-all hover:scale-105"
              style={{
                background: data.total !== null 
                  ? `${color}${Math.floor(intensity * 40 + 10).toString(16).padStart(2, '0')}`
                  : 'hsl(var(--muted) / 0.3)',
                borderColor: data.total !== null 
                  ? `${color}60`
                  : 'transparent',
                borderWidth: '1px',
              }}
            >
              <div className="text-[10px] text-muted-foreground">{minute}</div>
              <div className="font-display font-bold text-sm" style={{ color: data.total !== null ? color : 'hsl(var(--muted-foreground))' }}>
                {data.total !== null ? data.total : 'N/D'}
              </div>
              <div className="text-[9px] text-muted-foreground">
                {data.percentage || '-'}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="glass-card p-5">
      <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider">
        Cards by Minute
      </h4>
      
      <Accordion type="single" collapsible className="w-full">
        <AccordionItem value="yellow" className="border-accent/30">
          <AccordionTrigger className="hover:no-underline py-3">
            <div className="flex items-center gap-2">
              <div className="w-5 h-6 bg-accent rounded-sm" />
              <span className="font-heading font-semibold">Yellow Cards</span>
              {hasYellowData && (
                <span className="text-xs text-muted-foreground ml-2">
                  ({Object.values(cards.yellow).reduce((acc, v) => acc + (v.total ?? 0), 0)} total)
                </span>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-2">
            {renderCardHeatmap(cards.yellow, 'hsl(45, 100%, 50%)')}
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="red" className="border-destructive/30">
          <AccordionTrigger className="hover:no-underline py-3">
            <div className="flex items-center gap-2">
              <div className="w-5 h-6 bg-destructive rounded-sm" />
              <span className="font-heading font-semibold">Red Cards</span>
              {hasRedData && (
                <span className="text-xs text-muted-foreground ml-2">
                  ({Object.values(cards.red).reduce((acc, v) => acc + (v.total ?? 0), 0)} total)
                </span>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-2">
            {renderCardHeatmap(cards.red, 'hsl(0, 80%, 55%)')}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
