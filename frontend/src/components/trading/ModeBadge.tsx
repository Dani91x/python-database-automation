// ============================================================================
// ModeBadge.tsx — badge PAPER / LIVE di UNA riga (trade, attività, richiesta).
//
// CERT. 13/09 — separazione netta PAPER / LIVE richiesta dall'utente.
// Il backend è già stato corretto: rifiuta una richiesta la cui modalità non
// corrisponde a quella del servizio, etichetta ogni riga con `mode` e tiene
// P&L e rischio separati per modalità. Lato UI mancava il pezzo più semplice e
// più pericoloso: dirlo su OGNI riga. Prima il badge esisteva solo sulle righe
// LIVE (DayDetail) o non esisteva affatto (SafeTradesTable, ActivityFeed), e
// l'assenza di badge poteva significare due cose opposte — «è paper» oppure
// «non lo so».
//
// Regole visive (design system): PAPER neutro, LIVE rosso d'allarme, modalità
// non dichiarata in ambra col motivo. Nessuna logica, nessun I/O: solo il badge.
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { modeMeta } from '@/lib/tradeStatus';

export function ModeBadge({
    mode, className = '', compact = false, testId = 'mode-badge', dimmed = false, title,
}: {
    mode: string | null | undefined;
    className?: string;
    /** rendering minimo per le celle fitte delle tabelle */
    compact?: boolean;
    testId?: string;
    /** riga di una modalità DIVERSA da quella corrente: tono attenuato */
    dimmed?: boolean;
    /** tooltip aggiuntivo (si somma a quello della modalità) */
    title?: string;
}) {
    const m = modeMeta(mode);
    return (
        <Badge
            variant="outline"
            data-testid={testId}
            data-mode={String(mode ?? '').trim().toLowerCase() || 'unknown'}
            data-dimmed={dimmed ? '1' : undefined}
            className={[
                'font-heading whitespace-nowrap',
                compact ? 'px-1 py-0 text-[10px]' : 'px-1.5 py-0 text-[10px]',
                m.cls,
                dimmed ? 'opacity-60' : '',
                className,
            ].filter(Boolean).join(' ')}
            title={title ? `${m.title} — ${title}` : m.title}
        >
            {m.label}
        </Badge>
    );
}

export default ModeBadge;
