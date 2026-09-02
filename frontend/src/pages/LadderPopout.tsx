// ============================================================================
// LadderPopout — finestra POPOUT dedicata a UN ladder (B19, multi-monitor):
// /ladder-popout?sport=calcio|tennis&market=1.234&event=EV&name=Match%20Odds
// Aperta dal bottone "stacca" del LadderView. Lo StandaloneLadder risolve da solo
// modalità ordini (fail-safe OFF) e selezioni; qui solo chrome minimale scuro.
// ============================================================================
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import StandaloneLadder from '@/components/live/StandaloneLadder';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';

export default function LadderPopout() {
    const [params] = useSearchParams();
    const slot = useMemo(() => {
        const sport = params.get('sport') ?? 'calcio';
        const marketId = params.get('market') ?? '';
        const eventId = params.get('event') ?? '';
        const marketName = params.get('name') ?? marketId;
        return {
            sport, eventId, marketId, marketName,
            eventName: params.get('eventName') ?? '',
            p1: params.get('p1') ?? '',
            p2: params.get('p2') ?? '',
        };
    }, [params]);

    return (
        <div className="min-h-screen bg-background text-foreground p-2">
            <Helmet>
                <title>{`Ladder · ${slot.marketName}`}</title>
            </Helmet>
            {!slot.marketId || !slot.eventId ? (
                <div className="p-6 text-center text-sm text-muted-foreground">
                    Parametri mancanti: servono <code>market</code> ed <code>event</code>.
                </div>
            ) : (
                <>
                    {/* barra minima: video live + statistiche Betfair del match */}
                    <div className="flex items-center justify-between px-1 pb-1">
                        <span className="text-[11px] text-muted-foreground truncate">
                            {slot.eventName || slot.marketName}
                        </span>
                        <BetfairMediaButtons compact eventId={slot.eventId} />
                    </div>
                    <StandaloneLadder slot={slot} />
                </>
            )}
        </div>
    );
}
