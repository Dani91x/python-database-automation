// ============================================================================
// CashOutButton.tsx — controllo CASH OUT professionale, riusabile.
//
// Mostra sul bottone il P&L che verrebbe BLOCCATO chiudendo tutta la posizione
// ai prezzi correnti (come il "Cash out" di Betfair): il numero si aggiorna a
// ogni render, cioè a ogni tick del book.
//
// Matematica (identica a lib/ladderMath.ts `lockedPnlAt`, mirror del backend
// trading/greenup.py):
//   posizione: W = P&L se la selezione VINCE, L = P&L se PERDE
//   · W > L  → si copre BANCANDO (LAY) al miglior lay
//   · W ≤ L  → si copre PUNTANDO (BACK) al miglior back
//   stake per il green PIENO:  s = |W − L| / p
//   P&L bloccato:              locked = L + (W − L)/p
//   PARZIALE (ordine di copertura di stake s < pieno): la posizione NON e'
//   bilanciata, restano DUE esiti — si mostrano entrambi e il titolo e' il
//   PEGGIORE (il backend registra locked_pnl = min dei due):
//     copertura BACK s @ p:  W' = W + s(p−1) · L' = L − s
//     copertura LAY  s @ p:  W' = W − s(p−1) · L' = L + s
//
// Nessun I/O qui dentro: l'ordine vero lo piazza il chiamante via `onCashOut`.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Coins, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { lockedPnlAt } from '@/lib/ladderMath';
import { fmtMoney, fmtOdds } from '@/lib/format';

// --------------------------------------------------------------- matematica
/** Lato dell'ordine di copertura: W > L → LAY (bancare), altrimenti BACK. */
export function hedgeSide(win: number, lose: number): 'back' | 'lay' {
    return win > lose ? 'lay' : 'back';
}

/** Prezzo a cui si chiude (il best del lato di copertura); null = non chiudibile. */
export function greenPrice(
    win: number, lose: number, bestBack: number | null, bestLay: number | null,
): number | null {
    const p = hedgeSide(win, lose) === 'lay' ? bestLay : bestBack;
    return Number.isFinite(p as number) && (p as number) > 1 ? (p as number) : null;
}

/** Stake dell'ordine di copertura per il green PIENO (centesimi). */
export function fullGreenStake(win: number, lose: number, price: number): number {
    if (!Number.isFinite(price) || price <= 1) return 0;
    return Math.round((Math.abs(win - lose) / price) * 100) / 100;
}

/** I DUE esiti della posizione dopo un ordine di copertura di stake `stake`
 *  a prezzo `price` (lato = hedgeSide). Con lo stake pieno coincidono. */
export function partialOutcomes(
    price: number, win: number, lose: number, stake: number,
): { win: number; lose: number } {
    const s = Number.isFinite(stake) && stake > 0 ? stake : 0;
    if (!Number.isFinite(price) || price <= 1 || s === 0) return { win, lose };
    const r2 = (x: number) => Math.round(x * 100) / 100;
    return hedgeSide(win, lose) === 'lay'
        ? { win: r2(win - s * (price - 1)), lose: r2(lose + s) }
        : { win: r2(win + s * (price - 1)), lose: r2(lose - s) };
}

/** P&L GARANTITO coprendo la quota `fraction` (0..1) della posizione: il
 *  PEGGIORE dei due esiti residui (= locked_pnl del backend). */
export function partialLockedPnl(
    price: number, win: number, lose: number, fraction: number,
): number {
    const f = Number.isFinite(fraction) ? Math.max(0, Math.min(1, fraction)) : 0;
    const stake = Math.round(fullGreenStake(win, lose, price) * f * 100) / 100;
    const o = partialOutcomes(price, win, lose, stake);
    return Math.min(o.win, o.lose);
}

/** Commissione Betfair sul P&L POSITIVO. `commission` accetta la frazione
 *  (0.05) o la percentuale (5): sopra 1 viene letta come percentuale. */
export function netAfterCommission(pnl: number, commission?: number): number {
    const raw = Number(commission);
    if (!Number.isFinite(raw) || raw <= 0) return Math.round(pnl * 100) / 100;
    const c = raw > 1 ? raw / 100 : raw;
    const net = pnl > 0 ? pnl * (1 - c) : pnl;
    return Math.round(net * 100) / 100;
}

// ------------------------------------------------------------------ helpers
// §5 del design system: UN solo formato monetario ("−4,36 €"), mai "−€4.36"
// accanto a "12,50 €" nella stessa vista. `currency` resta un prop (il chiamante
// può passare '' per il numero nudo): lo inoltriamo a fmtMoney.
function fmtSigned(v: number, currency: string): string {
    return fmtMoney(v, { signed: true, currency });
}
function fmtPlain(v: number, currency: string): string {
    return fmtMoney(Math.abs(v), { currency });
}

export interface CashOutButtonProps {
    /** P&L della posizione se la selezione VINCE */
    win: number;
    /** P&L della posizione se la selezione PERDE */
    lose: number;
    bestBack: number | null;
    bestLay: number | null;
    /** aliquota Betfair: 0.05 oppure 5 (percentuale) */
    commission?: number;
    currency?: string;
    disabled?: boolean;
    /** motivo mostrato nel tooltip quando `disabled` (es. quote non aggiornate) */
    disabledReason?: string;
    /** cash out gia' in corso per questa posizione (richiesta in volo o gamba
     *  di chiusura gia' scritta): bottone spento, mai una seconda copertura */
    pending?: boolean;
    /** modalita' del TRADE (non della pagina): decide la doppia conferma */
    mode: 'paper' | 'live';
    onCashOut: (args: { amount?: number; fraction?: number }) => Promise<void> | void;
    /** rendering ridotto per le celle di tabella */
    compact?: boolean;
    /**
     * Posizione già coperta IN PARTE: `win`/`lose` sono l'esposizione RESIDUA e
     * il bottone deve dirlo ("chiudi residuo"), perché il trader non stia
     * chiudendo quello che crede di avere ancora intero. `remaining` = liability
     * ancora a rischio (€), `fraction` = quota già coperta (0-1).
     */
    residual?: { remaining?: number | null; fraction?: number | null } | null;
}

/** la conferma LIVE armata decade da sola dopo questo tempo */
export const LIVE_ARM_TIMEOUT_MS = 10_000;

export function CashOutButton({
    win, lose, bestBack, bestLay, commission, currency = '€',
    disabled = false, disabledReason, pending = false, mode, onCashOut, compact = false,
    residual = null,
}: CashOutButtonProps) {
    const [open, setOpen] = useState(false);
    const [stakeStr, setStakeStr] = useState('');
    const [quickFraction, setQuickFraction] = useState<number | null>(1);
    const [liveArmed, setLiveArmed] = useState(false);
    const [busy, setBusy] = useState(false);
    // guardia anti doppio click: ref, non stato (lo stato e' una closure del render)
    const inFlight = useRef(false);

    const side = hedgeSide(win, lose);
    const price = greenPrice(win, lose, bestBack, bestLay);
    const fullStake = price != null ? fullGreenStake(win, lose, price) : 0;
    const lockedFull = price != null ? Math.round(lockedPnlAt(price, win, lose) * 100) / 100 : null;
    const netFull = lockedFull != null ? netAfterCommission(lockedFull, commission) : null;

    const balanced = Math.abs(win - lose) < 0.005;
    const unavailable = price == null || fullStake <= 0 || balanced;
    const isDisabled = disabled || pending || unavailable;

    // stake proposto: green pieno (si risincronizza quando il dialog si apre)
    useEffect(() => {
        if (!open) return;
        setStakeStr(fullStake > 0 ? fullStake.toFixed(2) : '');
        setQuickFraction(1);
        setLiveArmed(false);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const typedAmount = useMemo(() => {
        const v = Number(String(stakeStr).replace(',', '.'));
        return Number.isFinite(v) && v > 0 ? Math.round(v * 100) / 100 : 0;
    }, [stakeStr]);

    const effFraction = useMemo(() => {
        if (quickFraction != null) return quickFraction;
        if (fullStake <= 0) return 0;
        return Math.max(0, Math.min(1, typedAmount / fullStake));
    }, [quickFraction, typedAmount, fullStake]);

    const effAmount = quickFraction != null
        ? Math.round(fullStake * quickFraction * 100) / 100
        : typedAmount;

    // esiti residui dopo la copertura di `effAmount`: con lo stake pieno
    // coincidono (green), altrimenti il titolo e' il PEGGIORE dei due
    const isFull = effFraction >= 0.999;
    const outcomes = price != null ? partialOutcomes(price, win, lose, effAmount) : { win, lose };
    const worst = isFull && lockedFull != null ? lockedFull : Math.min(outcomes.win, outcomes.lose);
    const best = isFull && lockedFull != null ? lockedFull : Math.max(outcomes.win, outcomes.lose);
    const netWorst = netAfterCommission(worst, commission);
    const netBest = netAfterCommission(best, commission);

    const amountInvalid = effAmount < 0.01 || effAmount > fullStake + 0.005;

    // la conferma LIVE armata decade se cambia importo/prezzo/esposizione…
    useEffect(() => { setLiveArmed(false); }, [effAmount, price, win, lose]);
    // …e comunque dopo LIVE_ARM_TIMEOUT_MS
    useEffect(() => {
        if (!liveArmed) return;
        const t = window.setTimeout(() => setLiveArmed(false), LIVE_ARM_TIMEOUT_MS);
        return () => window.clearTimeout(t);
    }, [liveArmed]);

    function pickFraction(f: number) {
        setQuickFraction(f);
        setStakeStr((Math.round(fullStake * f * 100) / 100).toFixed(2));
    }

    async function confirm() {
        if (amountInvalid || busy || pending || inFlight.current) return;
        if (mode === 'live' && !liveArmed) { setLiveArmed(true); return; }
        inFlight.current = true;
        setBusy(true);
        try {
            await onCashOut(quickFraction != null ? { fraction: quickFraction } : { amount: effAmount });
            setOpen(false);
        } finally {
            inFlight.current = false;
            setBusy(false);
            setLiveArmed(false);
        }
    }

    const tone = netFull == null ? 'text-slate-500'
        : netFull >= 0 ? 'text-emerald-300' : 'text-red-300';
    const label = netFull == null ? 'n/d' : fmtSigned(netFull, currency);
    // copertura PARZIALE: il bottone chiude il RESIDUO, non la posizione piena
    const isResidual = residual != null
        && (residual.fraction == null || residual.fraction < 0.999);
    const residualEur = residual?.remaining != null && Number.isFinite(Number(residual.remaining))
        ? fmtPlain(Number(residual.remaining), currency)
        : null;
    const actionWord = isResidual ? 'Chiudi residuo' : 'Cash out';

    const trigger = (
        <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isDisabled}
            onClick={() => setOpen(true)}
            data-testid="cashout-trigger"
            data-residual={isResidual ? '1' : undefined}
            title={isResidual
                ? `posizione coperta${residual?.fraction != null ? ` al ${Math.round(residual.fraction * 100)} %` : ' in parte'}: questo chiude il RESIDUO${residualEur ? ` (liability ${residualEur})` : ''}`
                : undefined}
            aria-label={`${actionWord} ${label}`}
            className={[
                'border-white/15 bg-black/40 hover:bg-white/10 font-bold tabular-nums',
                compact ? 'h-7 px-2 text-[11px]' : 'h-9 px-3 text-xs',
                tone,
            ].join(' ')}
        >
            <Coins className={compact ? 'w-3 h-3 mr-1' : 'w-3.5 h-3.5 mr-1'} aria-hidden />
            {compact
                ? <>{isResidual && <span className="mr-1 font-normal opacity-80">residuo</span>}{label}</>
                : <>{actionWord}{isResidual && residualEur ? ` (${residualEur})` : ''} <span className="ml-1">{label}</span></>}
        </Button>
    );

    return (
        <>
            {isDisabled ? (
                // provider locale: il controllo deve funzionare anche montato
                // fuori dal TooltipProvider globale (App.tsx) — es. nei test.
                <TooltipProvider delayDuration={200}>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <span className="inline-block" data-testid="cashout-disabled-wrap">{trigger}</span>
                    </TooltipTrigger>
                    <TooltipContent>
                        {pending
                            ? 'Cash out già in corso per questa posizione.'
                            : disabled
                                ? (disabledReason ?? 'Cash out non disponibile in questo momento.')
                                : balanced
                                    ? 'Posizione già bilanciata: non c’è nulla da chiudere.'
                                    : `Quote ${side === 'lay' ? 'lay' : 'back'} non disponibili: senza book non si può calcolare la chiusura.`}
                    </TooltipContent>
                </Tooltip>
                </TooltipProvider>
            ) : trigger}

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="glass-card border-white/10 max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 font-display">
                            <Coins className="w-5 h-5 text-secondary" aria-hidden /> {actionWord}
                        </DialogTitle>
                        <DialogDescription>
                            Chiusura {side === 'lay' ? 'BANCANDO (lay)' : 'PUNTANDO (back)'} a{' '}
                            <b className="tabular-nums text-white">{fmtOdds(price)}</b>
                            {' '}· green pieno {fmtPlain(fullStake, currency)} di stake.
                            {isResidual && (
                                <span data-testid="cashout-residual-note">
                                    {' '}Posizione già coperta
                                    {residual?.fraction != null ? ` al ${Math.round(residual.fraction * 100)} %` : ' in parte'}:
                                    qui si chiude il <b>residuo</b>{residualEur ? ` (liability ancora a rischio ${residualEur})` : ''}.
                                </span>
                            )}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4">
                        {/* esposizione corrente */}
                        <div className="grid grid-cols-2 gap-2 text-xs">
                            <div className="rounded-md border border-white/10 bg-black/40 p-2">
                                <div className="text-slate-400 uppercase tracking-wide text-[10px]">Se vince</div>
                                <div className={`tabular-nums font-bold ${win >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                                    {fmtSigned(win, currency)}
                                </div>
                            </div>
                            <div className="rounded-md border border-white/10 bg-black/40 p-2">
                                <div className="text-slate-400 uppercase tracking-wide text-[10px]">Se perde</div>
                                <div className={`tabular-nums font-bold ${lose >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                                    {fmtSigned(lose, currency)}
                                </div>
                            </div>
                        </div>

                        {/* quick % */}
                        <div className="flex gap-2">
                            {[0.25, 0.5, 0.75, 1].map((f) => (
                                <Button
                                    key={f}
                                    type="button"
                                    variant={quickFraction === f ? 'default' : 'outline'}
                                    size="sm"
                                    className="flex-1 text-xs tabular-nums"
                                    onClick={() => pickFraction(f)}
                                >
                                    {Math.round(f * 100)}%
                                </Button>
                            ))}
                        </div>

                        {/* stake */}
                        <label className="block">
                            <span className="text-xs text-slate-400">Importo da chiudere ({currency}, stake dell'ordine)</span>
                            <input
                                type="number"
                                inputMode="decimal"
                                step={0.01}
                                min={0.01}
                                max={fullStake}
                                value={stakeStr}
                                aria-label="Importo cash out"
                                onChange={(e) => { setQuickFraction(null); setStakeStr(e.target.value); }}
                                className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums"
                            />
                        </label>

                        {/* risultato */}
                        <div className="rounded-md border border-white/10 bg-black/40 p-3">
                            <div className="text-[10px] uppercase tracking-wide text-slate-400">
                                {isFull
                                    ? 'P&L bloccato (green pieno)'
                                    : `Peggiore · parziale ${Math.round(effFraction * 100)}%: resta esposto`}
                            </div>
                            <div
                                data-testid="cashout-locked"
                                className={`text-2xl font-display font-black tabular-nums ${netWorst >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
                            >
                                {fmtSigned(netWorst, currency)}
                            </div>
                            {commission != null && Number(commission) > 0 && (
                                <div className="text-[11px] text-slate-500">al netto della commissione</div>
                            )}
                            {!isFull && price != null && (
                                // onestà: con una chiusura PARZIALE la posizione NON e' chiusa —
                                // il P&L finale dipende ancora dall'esito
                                <div className="mt-1 text-[11px] text-slate-400 tabular-nums" data-testid="cashout-residual">
                                    Migliore <b data-testid="cashout-best" className={netBest >= 0 ? 'text-emerald-300' : 'text-red-300'}>{fmtSigned(netBest, currency)}</b>
                                    {' · '}resta aperto: se vince {fmtSigned(outcomes.win, currency)} · se perde {fmtSigned(outcomes.lose, currency)}
                                </div>
                            )}
                        </div>

                        {effAmount > 0 && effAmount < 2 && (
                            <p className="text-[11px] text-amber-300/90" data-testid="cashout-min-note">
                                Sotto 2 {currency} Betfair usa il metodo 1000→cancella→sposta: l'ordine viene
                                immesso a quota 1000, cancellato e riposizionato per aggirare il minimo.
                            </p>
                        )}

                        {amountInvalid && (
                            <p className="text-[11px] text-red-300">
                                Importo fuori range: da 0,01 a {fmtPlain(fullStake, currency)}.
                            </p>
                        )}

                        {mode === 'live' && (
                            <p className="text-[11px] text-red-300 flex items-center gap-1">
                                <ShieldAlert className="w-3.5 h-3.5" aria-hidden /> Modalità LIVE: soldi veri.
                            </p>
                        )}
                    </div>

                    <DialogFooter>
                        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Annulla</Button>
                        <Button
                            type="button"
                            data-testid="cashout-confirm"
                            variant={mode === 'live' ? 'destructive' : 'default'}
                            disabled={amountInvalid || busy || pending}
                            onClick={() => { void confirm(); }}
                        >
                            {mode === 'live' && liveArmed ? 'Confermi? soldi veri' : `Chiudi ${fmtPlain(effAmount, currency)}`}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}

export default CashOutButton;
