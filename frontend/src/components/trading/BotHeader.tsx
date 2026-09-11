// ============================================================================
// BotHeader.tsx — HEADER STICKY unico delle tre sezioni di trading.
//
// Struttura (identica per Omega, Safe Strategy e Mike):
//   [AI TERMINAL] [simbolo + nome bot] [stato bot] [salute servizio]
//                                      ... [PAPER|LIVE] [Parametri] [Avvia/Ferma]
//
// L'altezza reale viene misurata e restituita via `onHeight`: le TabsList
// sticky delle pagine si agganciano sotto l'header anche quando va a capo su
// mobile (prima ogni pagina ripeteva la stessa misurazione, e Omega non
// l'aveva affatto).
// ============================================================================
import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Play, Square } from 'lucide-react';
import { botStatusMeta, T } from '@/lib/tradeStatus';
import { ageSeconds, fmtAge } from '@/lib/format';
import { SERVICE_STALE_S } from '@/components/trading/ServiceHealthChip';

/** identità visiva di ciascun bot: simbolo e colore d'accento (mancanza §15) */
export const BOT_IDENTITY = {
    omega: { name: 'OMEGA', symbol: 'Ω', accent: 'text-primary', startCls: 'bg-primary text-black hover:bg-primary/90' },
    safe: { name: 'SAFE STRATEGY', symbol: '🛡️', accent: 'text-secondary', startCls: 'bg-secondary text-black hover:bg-secondary/90' },
    mike: { name: 'MIKE', symbol: '🎯', accent: 'text-teal-300', startCls: 'bg-teal-500 text-black hover:bg-teal-400' },
} as const;

export type BotKey = keyof typeof BOT_IDENTITY;

/**
 * Certificazione 11/09 (dati reali): lo stato del badge è quello che il DB
 * DICHIARA (`omega_control.status`), non quello che il servizio FA. Con i tre
 * servizi fermi da cinque ore i badge dicevano ancora «IN CORSA», perché
 * nessuno aveva fermato il bot dalla UI: la colonna `status` era rimasta
 * 'running' e l'unico indizio era il battito, sepolto nel chip di salute.
 *
 * Qui il badge incrocia i due dati: `status='running'` + battito più vecchio
 * di `SERVICE_STALE_S` = «IN CORSA · SENZA BATTITO», in rosso, con l'età e il
 * cosa fare. Un bot senza battito non sta tradando: dirgli "IN CORSA" è la
 * bugia più costosa dell'header.
 */
export function botStatusWithBeat(
    status: string | null | undefined,
    statusPrefix: string,
    heartbeatAt: string | null | undefined,
    nowMs: number | undefined,
): { label: string; cls: string; title?: string; stale: boolean } {
    const meta = botStatusMeta(status, statusPrefix);
    const live = String(status ?? '').toLowerCase() === 'running';
    // nowMs assente = il chiamante non passa l'orologio: nessun giudizio
    if (!live || nowMs == null) return { ...meta, stale: false };
    const age = ageSeconds(heartbeatAt, nowMs);
    // battito MAI scritto (null) su uno status 'running' è a sua volta anomalo:
    // il servizio non ha mai preso in carico l'attivazione
    const stale = age == null || age > SERVICE_STALE_S;
    if (!stale) return { ...meta, stale: false };
    return {
        label: `${meta.label} · SENZA BATTITO`,
        cls: 'bg-red-500/20 text-red-200 border-red-400/60',
        title: age == null
            ? `il servizio non ha mai battuto da quando è stato avviato: ${T.restartApp}`
            : `il servizio non batte da ${fmtAge(age)}: ${T.restartApp}`,
        stale: true,
    };
}

export function BotHeader({
    bot, status, statusPrefix = '', statusTestId, health, modeToggle, params,
    running, busy, onStart, onStop, startDisabled, onHeight, extra,
    heartbeatAt, nowMs,
}: {
    bot: BotKey;
    /** control.status del bot */
    status: string | null | undefined;
    /** prefisso dell'etichetta di stato ('BOT' per Safe/Mike, '' per Omega) */
    statusPrefix?: string;
    /** testid del badge di stato (i test di pagina usano 'bot-status'/'mike-status') */
    statusTestId?: string;
    /** <ServiceHealthChip/> */
    health?: ReactNode;
    /** <ModeToggle/> */
    modeToggle?: ReactNode;
    /** pannello parametri della sezione (sheet trigger) */
    params?: ReactNode;
    running: boolean;
    busy?: boolean;
    onStart: () => void;
    onStop: () => void;
    startDisabled?: boolean;
    /** altezza reale dell'header, per le TabsList sticky */
    onHeight?: (px: number) => void;
    extra?: ReactNode;
    /**
     * `control.heartbeat_at` + orologio della pagina: con `status='running'` e
     * il battito oltre `SERVICE_STALE_S` il badge diventa rosso «SENZA
     * BATTITO». Omettendoli il badge resta quello del solo `status`
     * (retro-compatibile con chi non li passa ancora).
     */
    heartbeatAt?: string | null;
    nowMs?: number;
}) {
    const id = BOT_IDENTITY[bot];
    const meta = botStatusWithBeat(status, statusPrefix, heartbeatAt, nowMs);
    const ref = useRef<HTMLElement | null>(null);

    useEffect(() => {
        const el = ref.current;
        if (!el || !onHeight) return;
        const measure = () => onHeight(Math.round(el.getBoundingClientRect().height) || 52);
        measure();
        if (typeof ResizeObserver === 'undefined') return;
        const ro = new ResizeObserver(measure);
        ro.observe(el);
        return () => ro.disconnect();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return (
        <nav
            ref={ref}
            className="border-b border-white/5 bg-black/60 backdrop-blur-xl sticky top-0 z-50"
            data-testid="bot-header"
            data-bot={bot}
        >
            <div className="container mx-auto px-4 lg:px-6 py-2 flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-3 flex-wrap">
                    <Link to="/select-sport" className="font-display font-black text-lg tracking-tighter">
                        AI <span className="text-primary">TERMINAL</span>
                    </Link>
                    <span className={`flex items-center gap-2 text-sm font-heading font-bold ${id.accent}`} data-testid="bot-name">
                        <span aria-hidden>{id.symbol}</span><span>{id.name}</span>
                    </span>
                    <Badge
                        variant="outline"
                        className={meta.cls}
                        data-testid={statusTestId ?? 'bot-status'}
                        data-stale={meta.stale ? 'true' : undefined}
                        title={meta.title}
                    >
                        {meta.label}
                    </Badge>
                    {health}
                    {extra}
                </div>
                <div className="flex items-center gap-2">
                    {modeToggle}
                    {params}
                    {running ? (
                        <Button variant="destructive" size="sm" onClick={onStop} disabled={busy} data-testid="bot-stop">
                            <Square className="w-4 h-4 mr-1" aria-hidden />{T.stop}
                        </Button>
                    ) : (
                        <Button size="sm" onClick={onStart} disabled={busy || startDisabled} className={id.startCls} data-testid="bot-start">
                            <Play className="w-4 h-4 mr-1" aria-hidden />{T.start}
                        </Button>
                    )}
                </div>
            </div>
        </nav>
    );
}

export default BotHeader;
