// ============================================================================
// SignalCard.tsx — card di UN segnale SAFE STRATEGY (attivo o scaduto).
//
// Priorità assoluta: leggibilità immediata anche con molti segnali insieme.
// Gerarchia visiva: AZIONE (PUNTA/BANCA chi) → quota → partita → contesto.
// L'ingresso a mercato resta manuale: i bottoni aprono solo Betfair
// (video / mercato) e Segui Live — nessun ordine parte da qui.
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { BetfairMediaButtons, type BetfairMediaAvailability } from '@/components/BetfairMediaButtons';
import { fmtEur, type ActiveSignal } from '@/lib/safeStrategy';
import { VARIANT_STYLE, sideBadgeClass } from './variantStyles';

/** Riga "importo abbinabile SUBITO": la size al miglior prezzo sul lato da
 *  operare, aggiornata live con la quota. Per il LAY l'importo è la puntata da
 *  bancare (denaro in attesa) e si mostra anche la responsabilità = importo ×
 *  (quota − 1); per il BACK è la puntata. Senza size (fonte legacy) → "n/d". */
function MatchableLine({ signal }: { signal: ActiveSignal }) {
    const eur = fmtEur(signal.entrySize);
    if (eur === null) {
        return <span className="text-muted-foreground">Abbinabile subito: n/d</span>;
    }
    const liability =
        signal.side === 'LAY' && signal.entryOdds != null && signal.entrySize != null
            ? fmtEur(Math.round(signal.entrySize * (signal.entryOdds - 1) * 100) / 100)
            : null;
    return (
        <span>
            <span className="text-muted-foreground">Abbinabile subito</span>{' '}
            <span className="font-mono tabular-nums font-bold text-emerald-300">{eur}</span>
            {signal.side === 'LAY' && (
                <span className="text-muted-foreground"> da bancare{liability ? ` · responsabilità ${liability}` : ''}</span>
            )}
            {signal.side === 'BACK' && <span className="text-muted-foreground"> da puntare</span>}
        </span>
    );
}

function fmtClock(ms: number): string {
    const d = new Date(ms);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function fmtAgo(ms: number, nowMs: number): string {
    const s = Math.max(0, Math.round((nowMs - ms) / 1000));
    if (s < 60) return `${s}s fa`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m fa`;
    return `${Math.floor(m / 60)}h ${m % 60}m fa`;
}

interface Props {
    signal: ActiveSignal;
    /** timestamp corrente (dal chiamante, per re-render coerente della lista) */
    nowMs: number;
    /** disponibilità video/animazione Betfair per l'evento (dallo scanner) */
    media?: BetfairMediaAvailability | null;
}

export function SignalCard({ signal, nowMs, media }: Props) {
    const style = VARIANT_STYLE[signal.variant];
    const active = signal.status === 'active';
    return (
        <div
            className={[
                'glass-card rounded-xl border border-white/10 border-l-4 p-4 transition-all',
                style.edge,
                active ? 'pulse-glow' : 'opacity-50',
            ].join(' ')}
        >
            <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className={`font-heading font-bold text-[10px] ${style.badge}`}>
                    {style.chipLabel(signal.subId)}
                </Badge>
                <Badge variant="outline" className={`font-heading font-bold text-[10px] ${sideBadgeClass(signal.side)}`}>
                    {signal.side ?? '—'}
                </Badge>
                <span className="ml-auto text-[11px] text-muted-foreground font-mono tabular-nums">
                    {fmtClock(signal.triggeredAtMs)} · {fmtAgo(signal.triggeredAtMs, nowMs)}
                </span>
            </div>

            <div className="mt-2 flex items-baseline gap-3 flex-wrap">
                <span className="font-display font-black text-lg md:text-xl tracking-tight text-white">
                    {signal.headline}
                </span>
                <span className="font-mono tabular-nums text-2xl font-bold text-primary">
                    {signal.entryOdds != null ? `@${signal.entryOdds.toFixed(2)}` : '@ n/d'}
                </span>
            </div>

            <div className="mt-1 text-sm">
                <MatchableLine signal={signal} />
            </div>

            <div className="mt-1 text-sm text-muted-foreground">
                {signal.matchLabel}
                <span className="mx-2 text-white/20">·</span>
                <span className="font-mono tabular-nums">{signal.contextAtTrigger}</span>
                {!active && (
                    <span className="ml-2 text-[11px] uppercase tracking-wide text-amber-300/80">
                        condizioni non più valide
                    </span>
                )}
            </div>

            <div className="mt-3">
                <BetfairMediaButtons eventId={signal.eventId} media={media} />
            </div>
        </div>
    );
}
