// ============================================================================
// ServiceHealthChip.tsx — UN chip di salute per le tre sezioni.
//
// Risponde alle tre domande che un trader si fa prima di premere un bottone:
//   1. il FEED (scanner) è vivo? da quanti secondi non si aggiorna?
//   2. il SERVIZIO del bot batte? (heartbeat, soglia 45 s)
//   3. le quote arrivano in push (STREAM) o in poll (REST)? siamo in DRY?
// Se qualcosa è fermo il chip diventa rosso e DICE cosa fare
// ("riavvia l'app desktop"): mai un pallino muto.
// ============================================================================
import { Radar } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ageSeconds, fmtAge } from '@/lib/format';
import { T } from '@/lib/tradeStatus';

/** soglia oltre la quale il battito del SERVIZIO del bot è considerato morto */
export const SERVICE_STALE_S = 45;

export interface ServiceHealthChipProps {
    /** nome del bot, per il testo del battito ("servizio Omega vivo") */
    botName: string;
    /** ultimo aggiornamento del feed dello scanner (ISO) */
    feedUpdatedAt?: string | null;
    /** soglia di staleness del feed in ms */
    feedStaleMs?: number;
    /** heartbeat del servizio del bot (control.heartbeat_at) */
    heartbeatAt?: string | null;
    /** istante corrente in ms (passato dalla pagina: un solo timer) */
    nowMs: number;
    /** conteggi del feed (payload dello scanner) */
    counts?: { calcio?: number | null; tennis?: number | null } | null;
    /** 'stream' (push) o 'rest' (poll di fallback) */
    source?: string | null;
    streamMarkets?: number | null;
    /** true = servizio in osservazione, nessun ordine */
    dry?: boolean;
    /** ultimo errore pubblicato dallo scanner */
    lastError?: string | null;
    /** true = lo stato del feed non è mai stato letto (nessun heartbeat) */
    feedMissing?: boolean;
    /**
     * Ciclo DEGRADATO: il servizio batte ma una fase è fallita (motivo dal
     * backend). È un AVVISO ambra, non un "servizio morto": il bot sta ancora
     * girando e il trader deve saperlo senza andare nei log.
     */
    degraded?: string | null;
}

export function ServiceHealthChip({
    botName, feedUpdatedAt, feedStaleMs = 45_000, heartbeatAt, nowMs,
    counts, source, streamMarkets, dry, lastError, feedMissing, degraded,
}: ServiceHealthChipProps) {
    const feedAge = ageSeconds(feedUpdatedAt, nowMs);
    const feedAlive = feedAge !== null && feedAge * 1000 <= feedStaleMs;
    const hbAge = ageSeconds(heartbeatAt, nowMs);
    const botAlive = hbAge !== null && hbAge <= SERVICE_STALE_S;
    const bad = !feedAlive;

    return (
        <div
            className={`glass-card rounded-lg border px-3 py-1.5 flex items-center gap-2 flex-wrap text-xs ${bad ? 'border-red-500/40' : degraded ? 'border-amber-500/40' : 'border-emerald-500/30'}`}
            data-testid="service-health"
            data-feed={feedAlive ? 'alive' : 'stale'}
            data-service={botAlive ? 'alive' : 'stale'}
            data-degraded={degraded ? '1' : undefined}
        >
            <Radar className={`w-3.5 h-3.5 ${feedAlive ? 'text-emerald-400' : 'text-red-400'}`} aria-hidden />
            <span className={feedAlive ? 'text-emerald-300' : 'text-red-300'}>
                {feedAlive
                    ? `${T.feedAlive} (${fmtAge(feedAge)})`
                    : feedAge === null
                        ? T.feedNoData
                        : `${T.feedStopped} da ${fmtAge(feedAge)}`}
            </span>
            {feedAlive && counts && (
                <span className="text-muted-foreground tabular-nums">
                    ⚽ <b className="text-white">{counts.calcio ?? 0}</b>
                    <span className="mx-1 text-white/20">·</span>
                    🎾 <b className="text-white">{counts.tennis ?? 0}</b>
                </span>
            )}
            <span className="text-slate-600" aria-hidden>·</span>
            <span className={botAlive ? 'text-emerald-300' : 'text-slate-400'} data-testid="service-beat">
                {botAlive
                    ? `servizio ${botName} vivo (${fmtAge(hbAge)})`
                    : `servizio ${botName}: ${T.serviceNoBeat}`}
            </span>
            {source && (
                <Badge
                    variant="outline"
                    className={source === 'stream'
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 text-[10px]'
                        : 'bg-amber-500/15 text-amber-300 border-amber-500/40 text-[10px]'}
                    title={source === 'stream'
                        ? 'quote in push dalla Exchange Stream API'
                        : 'stream non in salute: quote via poll REST di fallback'}
                >
                    {source === 'stream' ? `⚡ STREAM${streamMarkets ? ` ${streamMarkets}` : ''}` : 'REST'}
                </Badge>
            )}
            {dry && (
                <Badge variant="outline" className="bg-amber-500/15 text-amber-300 border-amber-500/40 text-[10px]">DRY</Badge>
            )}
            {degraded && (
                <Badge
                    variant="outline"
                    className="bg-amber-500/15 text-amber-300 border-amber-500/40 text-[10px]"
                    data-testid="service-degraded"
                    title={`il ciclo continua ma una fase è fallita: ${degraded}`}
                >
                    ⚠ CICLO DEGRADATO: {degraded}
                </Badge>
            )}
            {bad && (
                <span className="text-red-300" data-testid="service-health-action">
                    — {feedMissing ? `nessun heartbeat: ${T.restartApp}` : T.restartApp}
                </span>
            )}
            {lastError && <span className="text-amber-300" title={lastError} aria-label={lastError}>⚠</span>}
        </div>
    );
}

export default ServiceHealthChip;
