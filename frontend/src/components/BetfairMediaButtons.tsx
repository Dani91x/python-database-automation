// ============================================================================
// BetfairMediaButtons.tsx — bottoni "📺 Video" e "📊 Stats/Mercato" Betfair.
//
// Componente UNICO per tutte le sezioni (Safe Strategy, Omega, Segui Live,
// Tennis, Multi-Ladder, Market Watch, Board): apre le pagine Betfair in una
// finestra separata con la sessione web dell'utente (vedi lib/betfairMedia.ts).
// Due varianti: bottoni estesi (header/card) e icone compatte (righe di lista).
// stopPropagation/preventDefault: molte righe che li ospitano hanno click
// propri (apertura terminal, Link) che NON devono scattare.
// ============================================================================
import type { MouseEvent } from 'react';
import { Button } from '@/components/ui/button';
import { betfairEventUrl, betfairMarketUrl, betfairVideoUrl, openBetfairWindow } from '@/lib/betfairMedia';

interface Props {
    eventId: string;
    /** market_id per il deep-link mercato/statistiche (null = pagina evento) */
    marketId?: string | null;
    /** sport per il fallback pagina-evento quando manca il market_id */
    sport?: 'calcio' | 'tennis';
    /** icone compatte per righe di lista */
    compact?: boolean;
    className?: string;
}

export function BetfairMediaButtons({ eventId, marketId = null, sport = 'calcio', compact = false, className }: Props) {
    const statsUrl = marketId ? betfairMarketUrl(marketId) : betfairEventUrl(eventId, sport);
    const open = (e: MouseEvent, url: string) => {
        e.stopPropagation();
        e.preventDefault();
        openBetfairWindow(url);
    };

    if (compact) {
        return (
            <span className={`inline-flex items-center gap-0.5 ${className ?? ''}`}>
                <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-muted-foreground hover:text-white"
                    title="Video live Betfair (serve login Betfair nella finestra)"
                    aria-label="Apri video live Betfair"
                    onClick={(e) => open(e, betfairVideoUrl(eventId))}
                >
                    📺
                </Button>
                <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-muted-foreground hover:text-white"
                    title="Statistiche e mercato su Betfair Exchange"
                    aria-label="Apri statistiche e mercato Betfair"
                    onClick={(e) => open(e, statsUrl)}
                >
                    📊
                </Button>
            </span>
        );
    }

    return (
        <span className={`inline-flex items-center gap-2 ${className ?? ''}`}>
            <Button
                variant="outline"
                size="sm"
                className="border-white/10 text-muted-foreground hover:text-white h-7 text-xs"
                title="Video live Betfair (serve login Betfair nella finestra)"
                onClick={(e) => open(e, betfairVideoUrl(eventId))}
            >
                📺 Video
            </Button>
            <Button
                variant="outline"
                size="sm"
                className="border-white/10 text-muted-foreground hover:text-white h-7 text-xs"
                title="Statistiche e mercato su Betfair Exchange"
                onClick={(e) => open(e, statsUrl)}
            >
                📊 Stats · Mercato
            </Button>
        </span>
    );
}
