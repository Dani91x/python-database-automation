// ============================================================================
// BetfairMediaButtons.tsx — pulsante UNICO diviso in due metà, stile Betfair:
//   [ 📺 Video | 📊 Stats ]
// Entrambe le metà aprono il pop-out live UFFICIALE dell'Exchange
// (lib/betfairMedia.ts) con tutte le funzionalità Betfair:
//   · Video → stream live vero (feedType=liveVideo, dove disponibile; senza
//     diritti video il popout ripiega da solo sull'animazione);
//   · Stats → "Statistiche partita" (feedType=matchStats), con l'altra tab del
//     popup ufficiale ("Visualizzazione partita") a un click.
// Disponibilità (prop `media`, dall'IPS Betfair scoresAndBroadcast — lo stesso
// dato con cui il sito mostra/nasconde le icone): quando Betfair dichiara che
// per l'evento NON c'è video (o animazione/statistiche) la metà corrispondente
// resta cliccabile ma attenuata, col motivo nel tooltip. Niente falsi "Video".
// Stessa finestra per evento+feed: un secondo click la riporta davanti, non ne
// apre un'altra. Componente unico per tutte le sezioni. stopPropagation/
// preventDefault: molte righe che lo ospitano hanno click propri (apertura
// terminal, Link) che NON devono scattare.
// ============================================================================
import type { MouseEvent } from 'react';
import { toast } from 'sonner';
import { openBetfairPopout, type BetfairFeedType } from '@/lib/betfairMedia';

export interface BetfairMediaAvailability {
    /** video live Betfair disponibile (null = ignoto) */
    video: boolean | null;
    /** animazione + statistiche disponibili (null = ignoto) */
    viz: boolean | null;
}

interface Props {
    eventId: string;
    /** icone compatte per righe di lista */
    compact?: boolean;
    className?: string;
    /** disponibilità dichiarata da Betfair per l'evento; assente = ignota */
    media?: BetfairMediaAvailability | null;
}

export function BetfairMediaButtons({ eventId, compact = false, className, media }: Props) {
    const open = (e: MouseEvent, feed: BetfairFeedType) => {
        e.stopPropagation();
        e.preventDefault();
        if (!openBetfairPopout(eventId, feed)) {
            toast.error('Popup bloccato dal browser', {
                description: 'Consenti i popup per questo sito per aprire video e statistiche Betfair.',
            });
        }
    };

    const videoOff = media?.video === false;
    const vizOff = media?.viz === false;
    const videoTitle = videoOff
        ? 'Betfair non offre il video live per questo evento: il popup apre animazione/statistiche'
        : media?.video === true
            ? 'Video live Betfair disponibile (stream ufficiale)'
            : 'Video live Betfair (stream ufficiale, dove disponibile)';
    const statsTitle = vizOff
        ? 'Betfair non offre animazione/statistiche per questo evento'
        : 'Statistiche partita Betfair (+ Visualizzazione partita: tutte le tab del popup ufficiale)';

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
                className={`${base} ${half} border-r border-white/10 ${videoOff ? 'opacity-40' : ''}`}
                title={videoTitle}
                aria-label="Apri video live Betfair"
                data-available={media?.video ?? undefined}
                onClick={(e) => open(e, 'liveVideo')}
            >
                📺{!compact && ' Video'}
            </button>
            <button
                type="button"
                className={`${base} ${half} ${vizOff ? 'opacity-40' : ''}`}
                title={statsTitle}
                aria-label="Apri statistiche e visualizzazione partita Betfair"
                data-available={media?.viz ?? undefined}
                onClick={(e) => open(e, 'matchStats')}
            >
                📊{!compact && ' Stats'}
            </button>
        </span>
    );
}
