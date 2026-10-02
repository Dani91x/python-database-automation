// ============================================================================
// MarchioSoldi.tsx - 30/09, P1_MARCHIO_FONTE. Etichetta in linea che dice DA
// DOVE viene una cifra in euro: «CONTO BETFAIR · 3 s fa». Un'età che non si
// conosce (null) è scritta «età ignota» in arancione: non è zero.
// ============================================================================
import { FONTE_SOLDI, testoEta, type FonteSoldi } from '@/lib/fonteSoldi';

export function MarchioSoldi({
    fonte, etaS, dettaglio, testId, className = '',
}: {
    fonte: FonteSoldi;
    /** undefined = nessuna età mostrata; null = età ignota (in arancione) */
    etaS?: number | null;
    /** si aggiunge al tooltip della fonte */
    dettaglio?: string;
    testId?: string;
    className?: string;
}) {
    const m = FONTE_SOLDI[fonte];
    const eta = testoEta(etaS);
    const ignota = etaS !== undefined && (etaS === null || !Number.isFinite(etaS) || etaS < 0);
    return (
        <span
            data-testid={testId ?? 'marchio-soldi'}
            data-fonte={fonte}
            className={[
                'inline-flex items-center gap-1 rounded border px-1 py-0 font-heading ds-v2-marchio',
                'text-[9px] font-medium uppercase tracking-wide whitespace-nowrap',
                m.cls,
                className,
            ].filter(Boolean).join(' ')}
            title={dettaglio ? `${m.title} — ${dettaglio}` : m.title}
        >
            <span>{m.label}</span>
            {eta !== null && (
                <span data-testid="marchio-soldi-eta" className={ignota ? 'text-orange-400' : ''}>
                    {`· ${eta}`}
                </span>
            )}
        </span>
    );
}

export default MarchioSoldi;
