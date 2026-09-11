// ============================================================================
// InvestAction.tsx — azione "Investi" riusabile (segnali e opportunità).
//
// Stake precompilato dai parametri del bot, importo abbinabile SUBITO sempre
// visibile, e piazzamento tramite la CODA safe_strategy_requests (kind 'place').
// Il feedback (in coda / eseguito / errore) viene dalla riga della richiesta,
// che arriva in realtime: nessun ottimismo, si mostra solo ciò che il DB dice.
// In LIVE serve la doppia conferma (soldi veri).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Send, ShieldAlert, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { fmtMoney } from '@/lib/format';
import { T } from '@/lib/tradeStatus';
import { requestOutcome, type SafeMode, type SafeRequest, type SafeSide } from '@/lib/safeBot';

/** minimo Betfair per una scommessa (il servizio lo pubblica in
 *  params_effective.min_stake): sotto questa cifra l'ordine non e' immettibile
 *  normalmente e va gestito col metodo 1000→cancella→sposta. */
export const BETFAIR_MIN_STAKE = 2;

export interface InvestActionProps {
    mode: SafeMode;
    side: SafeSide;
    price: number | null;
    /** EUR abbinabili al best sul lato da operare (null = fonte senza size) */
    sizeAvailable: number | null;
    defaultStake: number;
    /** size minima ammessa (default: minimo Betfair 2 €) */
    minStake?: number;
    disabled?: boolean;
    /** motivo (tooltip) quando `disabled`: es. quote non aggiornate */
    disabledReason?: string;
    /** richieste note (realtime): serve a leggere lo stato della propria */
    requests: SafeRequest[];
    /** ritorna l'id della richiesta accodata (null = fallita) */
    onPlace: (size: number) => Promise<number | null>;
    /** notifica lo stake corrente (es. combinazioni: scala le gambe) */
    onStakeChange?: (stake: number) => void;
}

/** la conferma LIVE armata decade da sola dopo questo tempo */
export const LIVE_ARM_TIMEOUT_MS = 10_000;

export function InvestAction({
    mode, side, price, sizeAvailable, defaultStake, minStake, disabled = false, disabledReason,
    requests, onPlace, onStakeChange,
}: InvestActionProps) {
    const minAllowed = Number.isFinite(Number(minStake)) && Number(minStake) > 0
        ? Number(minStake)
        : BETFAIR_MIN_STAKE;
    const [stakeStr, setStakeStr] = useState(() => String(defaultStake ?? 5));
    // lo stake segue i parametri del bot finche' l'utente non lo tocca: al primo
    // render i parametri del server non sono ancora arrivati (default locali).
    const [touched, setTouched] = useState(false);
    const lastDefault = useRef(defaultStake);
    useEffect(() => {
        if (defaultStake === lastDefault.current) return;
        lastDefault.current = defaultStake;
        if (!touched) setStakeStr(String(defaultStake));
    }, [defaultStake, touched]);
    const [reqId, setReqId] = useState<number | null>(null);
    const [armed, setArmed] = useState(false);
    const [busy, setBusy] = useState(false);

    const stake = useMemo(() => {
        const v = Number(String(stakeStr).replace(',', '.'));
        return Number.isFinite(v) && v > 0 ? Math.round(v * 100) / 100 : 0;
    }, [stakeStr]);

    const liability = side === 'lay' && price != null ? Math.round(stake * (price - 1) * 100) / 100 : null;
    const req = reqId != null ? requests.find((r) => r.id === reqId) ?? null : null;
    const outcome = requestOutcome(req);
    const pending = busy || outcome?.tone === 'pending';
    // L-07: il minimo Betfair e' 2 EUR, non 0,50 — sotto, l'ordine non entra
    const belowMin = stake > 0 && stake < minAllowed;
    const invalid = stake <= 0 || belowMin || price == null || price <= 1;
    // guardia anti doppio click: ref, non stato (lo stato e' una closure del render)
    const inFlight = useRef(false);

    // la conferma LIVE armata decade se cambiano stake/prezzo/abbinabile…
    useEffect(() => { setArmed(false); }, [stake, price, sizeAvailable]);
    const onStakeRef = useRef(onStakeChange);
    onStakeRef.current = onStakeChange;
    useEffect(() => { onStakeRef.current?.(stake); }, [stake]);
    // …e comunque dopo LIVE_ARM_TIMEOUT_MS
    useEffect(() => {
        if (!armed) return;
        const t = window.setTimeout(() => setArmed(false), LIVE_ARM_TIMEOUT_MS);
        return () => window.clearTimeout(t);
    }, [armed]);

    async function submit() {
        if (invalid || pending || disabled || inFlight.current) return;
        if (mode === 'live' && !armed) { setArmed(true); return; }
        inFlight.current = true;
        setBusy(true);
        try {
            const id = await onPlace(stake);
            setReqId(id);
        } finally {
            inFlight.current = false;
            setBusy(false);
            setArmed(false);
        }
    }

    return (
        <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="block">
                <span className="text-[10px] uppercase tracking-wide text-slate-400">
                    Stake € {side === 'lay' ? '(da bancare)' : '(da puntare)'}
                </span>
                <input
                    type="number"
                    inputMode="decimal"
                    step={0.5}
                    min={minAllowed}
                    value={stakeStr}
                    aria-label="Stake"
                    onChange={(e) => { setTouched(true); setStakeStr(e.target.value); }}
                    className="mt-0.5 w-24 rounded-md bg-black/50 border border-white/10 px-2 py-1.5 text-sm tabular-nums"
                />
            </label>

            <Button
                type="button"
                size="sm"
                data-testid="invest-place"
                disabled={invalid || pending || disabled}
                title={disabled ? disabledReason : undefined}
                onClick={() => { void submit(); }}
                variant={mode === 'live' ? 'destructive' : 'default'}
                className="font-bold"
            >
                {pending ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" aria-hidden />
                    : mode === 'live' ? <ShieldAlert className="w-3.5 h-3.5 mr-1" aria-hidden />
                        : <Send className="w-3.5 h-3.5 mr-1" aria-hidden />}
                {mode === 'live' && armed ? 'Confermi? soldi veri' : `Piazza (${mode.toUpperCase()})`}
            </Button>

            <div className="text-[11px] text-muted-foreground leading-tight">
                <div>
                    abbinabile subito{' '}
                    <b className="text-emerald-300 tabular-nums">
                        {sizeAvailable != null ? fmtMoney(sizeAvailable) : 'n/d'}
                    </b>
                </div>
                {liability != null && (
                    <div>{T.openLiability} <b className="text-orange-300 tabular-nums">{fmtMoney(liability)}</b></div>
                )}
            </div>

            {disabled && disabledReason && (
                <span className="text-[11px] text-amber-300/90" data-testid="invest-disabled-reason">{disabledReason}</span>
            )}

            {belowMin && (
                <span className="text-[11px] text-amber-300/90" data-testid="invest-min-stake">
                    minimo Betfair {fmtMoney(minAllowed)}: sotto questa cifra l'ordine non viene immesso
                </span>
            )}

            {outcome && (
                <span className="flex items-center gap-1.5">
                    <Badge
                        variant="outline"
                        data-testid="invest-status"
                        data-tone={outcome.tone}
                        className={
                            outcome.tone === 'ok' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                                : outcome.tone === 'rejected' ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                                    : outcome.tone === 'error' ? 'bg-red-500/15 text-red-300 border-red-500/40'
                                        : 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                        }
                        title={outcome.message ?? undefined}
                    >
                        {outcome.tone === 'ok' ? <><Check className="w-3 h-3 mr-1" aria-hidden />eseguito</>
                            : outcome.tone === 'error' ? <><X className="w-3 h-3 mr-1" aria-hidden />errore</>
                                : outcome.tone === 'rejected' ? <><X className="w-3 h-3 mr-1" aria-hidden />rifiutato</>
                                    : 'in coda'}
                    </Badge>
                    {/* ogni richiesta deve dire PERCHE', non solo "errore" (L-07) */}
                    {outcome.message && (
                        <span
                            className={`text-[11px] ${outcome.tone === 'ok' ? 'text-emerald-300/90' : 'text-amber-300/90'}`}
                            data-testid="invest-status-message"
                        >
                            {outcome.message}
                        </span>
                    )}
                </span>
            )}
        </div>
    );
}

export default InvestAction;
