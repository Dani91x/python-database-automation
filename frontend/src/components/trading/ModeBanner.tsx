// ============================================================================
// ModeBanner.tsx — banner della MODALITÀ, identico nelle tre sezioni.
// LIVE = rosso (soldi veri), PAPER = verde (simulazione fedele). Ospita anche
// il flag DRY, l'errore pubblicato dal servizio e l'avviso di migrazione
// mancante: tutto quello che deve essere visibile PRIMA di operare.
// ============================================================================
import type { ReactNode } from 'react';
import { Activity, ShieldAlert } from 'lucide-react';
import { T } from '@/lib/tradeStatus';
import type { TradingMode } from './ModeToggle';

export function ModeBanner({
    mode, liveText, paperText, dry, dryText, error, migrationWarning, extra, testId = 'mode-banner',
}: {
    mode: TradingMode;
    /** spiegazione LIVE specifica del bot (cosa piazza con soldi veri) */
    liveText: ReactNode;
    /** spiegazione PAPER specifica del bot (fedeltà della simulazione) */
    paperText: ReactNode;
    dry?: boolean;
    dryText?: string;
    /** control.error del servizio */
    error?: string | null;
    /** es. "tabelle Mike assenti: applica migrations/mike_bot.sql" */
    migrationWarning?: string | null;
    extra?: ReactNode;
    /** i test di pagina esistenti usano 'mode-banner' / 'mike-mode-banner' */
    testId?: string;
}) {
    const live = mode === 'live';
    return (
        <div
            className={[
                'rounded-lg border px-3 py-2 text-[12px] flex items-center gap-2 flex-wrap',
                live ? 'border-red-500/40 bg-red-500/10 text-red-200' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
            ].join(' ')}
            data-testid={testId}
            data-mode={mode}
            role={live ? 'alert' : undefined}
        >
            {live
                ? <><ShieldAlert className="w-4 h-4" aria-hidden /><b>{T.modeLive}</b> — {liveText}</>
                : <><Activity className="w-4 h-4" aria-hidden /><b>{T.modePaper}</b> — {paperText}</>}
            {dry && <span className="ml-2 text-amber-300">{dryText ?? 'DRY: nessun ordine (osservazione)'}</span>}
            {extra}
            {error && <span className="ml-auto text-amber-300" data-testid="mode-banner-error">⚠ {error}</span>}
            {migrationWarning && <span className="ml-auto text-amber-300" data-testid="mode-banner-migration">⚠ {migrationWarning}</span>}
        </div>
    );
}

export default ModeBanner;
