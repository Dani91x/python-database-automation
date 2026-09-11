// ============================================================================
// MikeCashOutButton — CASH OUT di una PARTITA di Mike.
//
// Perché non è il `CashOutButton` condiviso: quello chiude UNA selezione e si
// calcola da solo il P&L bloccabile da win/lose + book. In Mike la chiusura è
// per EVENTO (Under 3.5 + Over 4.5 + eventuale re-ingresso), non è frazionabile
// (il servizio accetta `cashout`/`flatten` interi) e il netto lo calcola SOLO il
// servizio (audit M5: mai lordo ricalcolato in UI). Restano identici al
// componente condiviso: dialog di conferma, doppia conferma in LIVE, bottone
// spento CON MOTIVO, nessun doppio invio.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Coins, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { fmtMoney, fmtPctPoints } from '@/lib/format';
import { T } from '@/lib/tradeStatus';

/** la conferma LIVE armata decade da sola dopo questo tempo */
export const MIKE_LIVE_ARM_TIMEOUT_MS = 10_000;

export interface MikeCashOutButtonProps {
    /** nome della partita (titolo del dialog) */
    eventName: string;
    /** P&L NETTO di chiusura calcolato dal SERVIZIO (null = non calcolabile) */
    net: number | null;
    /** % del netto sulla base e soglia di chiusura automatica */
    pct?: number | null;
    targetPct?: number | null;
    /** base della percentuale (stake Under + copertura) */
    base?: number | null;
    /** il servizio ha prezzi per tutte le selezioni vive */
    complete?: boolean;
    /** motivo che SPEGNE il bottone (feed stantio, linea assente, richiesta in volo…) */
    disabledReason?: string | null;
    /** richiesta già in volo per questa partita */
    pending?: boolean;
    /** modalità del BOT: in live serve la doppia conferma */
    mode: 'paper' | 'live';
    /** dettaglio per gamba, mostrato nel dialog */
    breakdown?: { label: string; value: number | null }[];
    onCashOut: () => Promise<void> | void;
    /** esito dell'ultima richiesta, in italiano (M1) */
    lastOutcome?: string | null;
    testId?: string;
}

export function MikeCashOutButton({
    eventName, net, pct, targetPct, base, complete = true, disabledReason, pending = false,
    mode, breakdown, onCashOut, lastOutcome, testId = 'mike-cashout-btn',
}: MikeCashOutButtonProps) {
    const [open, setOpen] = useState(false);
    const [liveArmed, setLiveArmed] = useState(false);
    const [busy, setBusy] = useState(false);
    const inFlight = useRef(false);

    useEffect(() => { if (!open) setLiveArmed(false); }, [open]);
    useEffect(() => { setLiveArmed(false); }, [net]);
    useEffect(() => {
        if (!liveArmed) return;
        const t = window.setTimeout(() => setLiveArmed(false), MIKE_LIVE_ARM_TIMEOUT_MS);
        return () => window.clearTimeout(t);
    }, [liveArmed]);

    const unavailable = net == null || !complete;
    const isDisabled = Boolean(disabledReason) || pending || unavailable;
    const tone = net == null ? 'text-slate-400' : net >= 0 ? 'text-emerald-300' : 'text-red-300';
    const label = net == null ? 'n/d' : fmtMoney(net, { signed: true });

    async function confirm() {
        if (busy || pending || inFlight.current) return;
        if (mode === 'live' && !liveArmed) { setLiveArmed(true); return; }
        inFlight.current = true;
        setBusy(true);
        try {
            await onCashOut();
            setOpen(false);
        } finally {
            inFlight.current = false;
            setBusy(false);
            setLiveArmed(false);
        }
    }

    const trigger = (
        <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isDisabled}
            onClick={() => setOpen(true)}
            data-testid={testId}
            aria-label={`${T.cashOut} ${label}`}
            className={`h-7 px-2 text-[11px] border-white/15 bg-black/40 hover:bg-white/10 font-bold tabular-nums ${tone}`}
        >
            <Coins className="w-3 h-3 mr-1" aria-hidden />
            {T.cashOut} <span className="ml-1">{label}</span>
        </Button>
    );

    const why = pending
        ? 'Richiesta già inviata: attendi l’esito del servizio.'
        : disabledReason
            ? disabledReason
            : net == null
                ? 'Il servizio non ha ancora un valore di chiusura per questa partita.'
                : 'Prezzi incompleti: senza tutte le linee vive il cash out non è calcolabile.';

    return (
        <>
            {isDisabled ? (
                <TooltipProvider delayDuration={200}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <span className="inline-block" data-testid="mike-cashout-disabled">{trigger}</span>
                        </TooltipTrigger>
                        <TooltipContent>{why}</TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            ) : trigger}

            {isDisabled && (
                <span className="text-[10px] text-amber-200/80" data-testid="mike-cashout-off-reason">{why}</span>
            )}

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="glass-card border-white/10 max-w-md" data-testid="mike-cashout-dialog">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 font-display">
                            <Coins className="w-5 h-5 text-secondary" aria-hidden /> {T.cashOut}
                        </DialogTitle>
                        <DialogDescription>
                            Chiusura di <b className="text-white">{eventName}</b>: il servizio annulla gli ordini sul
                            book e chiude le posizioni nette di Under 3.5 e Over 4.5. La chiusura è intera: Mike non
                            accetta cash out parziali.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-3">
                        <div className="rounded-md border border-white/10 bg-black/40 p-3">
                            <div className="text-[10px] uppercase tracking-wide text-slate-400">
                                {T.lockedPnl} chiudendo ora (netto commissione, dal servizio)
                            </div>
                            <div
                                data-testid="mike-cashout-dialog-net"
                                className={`text-2xl font-display font-black tabular-nums ${net != null && net >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
                            >
                                {label}
                            </div>
                            <div className="text-[11px] text-slate-500 tabular-nums">
                                {pct != null && <>{fmtPctPoints(pct)} della base {fmtMoney(base)}</>}
                                {targetPct != null && <> · soglia automatica {fmtPctPoints(targetPct)}</>}
                            </div>
                        </div>

                        {breakdown && breakdown.length > 0 && (
                            <ul className="text-[11px] space-y-0.5" data-testid="mike-cashout-breakdown">
                                {breakdown.map((b) => (
                                    <li key={b.label} className="flex justify-between tabular-nums">
                                        <span className="text-slate-400">{b.label}</span>
                                        <span className={b.value != null && b.value >= 0 ? 'text-emerald-300' : 'text-red-300'}>
                                            {b.value != null ? fmtMoney(b.value, { signed: true }) : '—'}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        )}

                        {lastOutcome && (
                            <p className="text-[11px] text-slate-400" data-testid="mike-cashout-last">
                                ultima richiesta: {lastOutcome}
                            </p>
                        )}

                        {mode === 'live' && (
                            <p className="text-[11px] text-red-300 flex items-center gap-1">
                                <ShieldAlert className="w-3.5 h-3.5" aria-hidden /> {T.modeLive}: soldi veri.
                            </p>
                        )}
                    </div>

                    <DialogFooter>
                        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Annulla</Button>
                        <Button
                            type="button"
                            data-testid="mike-cashout-confirm"
                            variant={mode === 'live' ? 'destructive' : 'default'}
                            disabled={busy || pending}
                            onClick={() => { void confirm(); }}
                        >
                            {mode === 'live' && liveArmed ? 'Confermi? soldi veri' : `Chiudi tutto (${label})`}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}

export default MikeCashOutButton;
