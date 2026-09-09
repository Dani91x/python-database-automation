// ============================================================================
// BetfairMediaButtons.tsx — pulsante UNICO diviso in due metà, stile Betfair:
//   [ 📺 Video | 📊 Stats ]
// Entrambe le metà aprono il pop-out live UFFICIALE dell'Exchange
// (lib/betfairMedia.ts) con tutte le funzionalità Betfair:
//   · Video → stream live vero (feedType=liveVideo, dove disponibile);
//   · Stats → "Statistiche partita" (feedType=matchStats), con l'altra tab del
//     popup ufficiale ("Visualizzazione partita") a un click.
// Stessa finestra per evento+feed: un secondo click la riporta davanti, non ne
// apre un'altra. Componente unico per tutte le sezioni. stopPropagation/
// preventDefault: molte righe che lo ospitano hanno click propri (apertura
// terminal, Link) che NON devono scattare.
// ============================================================================
import type { MouseEvent } from 'react';
import { toast } from 'sonner';
import { openBetfairPopout, type BetfairFeedType } from '@/lib/betfairMedia';

interface Props {
    eventId: string;
    /** icone compatte per righe di lista */
    compact?: boolean;
    className?: string;
}

export function BetfairMediaButtons({ eventId, compact = false, className }: Props) {
    const open = (e: MouseEvent, feed: BetfairFeedType) => {
        e.stopPropagation();
        e.preventDefault();
        if (!openBetfairPopout(eventId, feed)) {
            toast.error('Popup bloccato dal browser', {
                description: 'Consenti i popup per questo sito per aprire video e statistiche Betfair.',
            });
        }
    };

    const half = compact
        ? 'px-1.5 h-6 text-[11px]'
        : 'px-2.5 h-7 text-xs gap-1';
    const base =
        'inline-flex items-center justify-center font-medium text-muted-foreground ' +
        'hover:text-white hover:bg-white/10 transition-colors cursor-pointer select-none';

    return (
        <span
            className={[
                'inline-flex items-stretch rounded-md overflow-hidden border border-white/10 bg-black/30',
                className ?? '',
            ].join(' ')}
        >
            <button
                type="button"
                className={`${base} ${half} border-r border-white/10`}
                title="Video live Betfair (stream ufficiale, dove disponibile)"
                aria-label="Apri video live Betfair"
                onClick={(e) => open(e, 'liveVideo')}
            >
                📺{!compact && ' Video'}
            </button>
            <button
                type="button"
                className={`${base} ${half}`}
                title="Statistiche partita Betfair (+ Visualizzazione partita: tutte le tab del popup ufficiale)"
                aria-label="Apri statistiche e visualizzazione partita Betfair"
                onClick={(e) => open(e, 'matchStats')}
            >
                📊{!compact && ' Stats'}
            </button>
        </span>
    );
}
