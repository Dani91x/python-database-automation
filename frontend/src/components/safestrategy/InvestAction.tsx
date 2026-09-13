// ============================================================================
// InvestAction.tsx — azione "Investi" riusabile (segnali e opportunità).
//
// Stake precompilato dai parametri del bot, importo abbinabile SUBITO sempre
// visibile, e piazzamento tramite la CODA safe_strategy_requests (kind 'place').
// Il feedback (in coda / eseguito / errore) viene dalla riga della richiesta,
// che arriva in realtime: nessun ottimismo, si mostra solo ciò che il DB dice.
// In LIVE serve la doppia conferma (soldi veri).
//
// CERT. 12/09 — quattro bugie tolte dallo schermo del trader:
//   · un fill PARZIALE (richiesti 5,00 €, abbinati 0,43 €: richiesta reale #7
//     dell'11/09) veniva mostrato come "eseguito", pieno;
//   · un ordine a ESITO IGNOTO (`result.pending_fill` / `status='pending'`:
//     coda flumine o REST senza risposta) veniva mostrato come "eseguito";
//   · una richiesta DEDUPLICATA (stessa chiave di idempotenza: nessun ordine
//     nuovo a mercato) veniva mostrata come "eseguito";
//   · lo stake poteva superare l'importo abbinabile al miglior prezzo: in LIVE
//     l'ordine parte FILL_OR_KILL (`execution.py`) e viene ANNULLATO per
//     intero, quindi il trader crede di avere una posizione e non ha nulla.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Send, ShieldAlert, Check, X, Clock, CircleSlash } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { fmtMoney } from '@/lib/format';
import { requestOutcome, type SafeMode, type SafeRequest, type SafeSide } from '@/lib/safeBot';

/**
 * Minimo di GIURISDIZIONE Betfair (il servizio lo pubblica in
 * `params_effective.min_stake`): sotto questa cifra l'ordine non entra col
 * piazzamento NORMALE e il servizio usa il metodo 1000→cancella→sposta
 * (place-and-trim). NON è un blocco: è una nota.
 */
export const BETFAIR_MIN_STAKE = 2;

/**
 * CERT. 13/09 — MINIMO REALE PIAZZABILE: 0,01 €.
 *
 * Prima questo componente spegneva «Piazza» sotto 2 € scrivendo «minimo
 * Betfair 2,00 €: sotto questa cifra l'ordine non viene immesso». È FALSO: il
 * backend implementa (ed ha collegato: REST + coda) il place-and-trim, cioè
 * parcheggio a quota 1000 → taglio → riprezzo, con cui QUALSIASI importo fino
 * al centesimo finisce davvero a mercato. Il `CashOutButton` lo faceva già
 * giusto (importo da 0,01 €, nota informativa sotto 2 €): l'unica schermata
 * che impediva l'operazione era questa, e impediva operazioni LEGITTIME.
 */
export const MIN_STAKE_ALLOWED = 0.01;

export interface InvestActionProps {
    mode: SafeMode;
    side: SafeSide;
    price: number | null;
    /** EUR abbinabili al best sul lato da operare (null = fonte senza size) */
    sizeAvailable: number | null;
    defaultStake: number;
    /** minimo di GIURISDIZIONE dichiarato dal servizio (`params_effective.min_stake`,
     *  default 2 €): sotto si entra lo stesso col place-and-trim, si mostra solo
     *  una NOTA. Non è mai una soglia che spegne il bottone. */
    minStake?: number;
    /** cap di responsabilità per singola operazione (params.max_liability_per_trade):
     *  oltre questo il servizio RIFIUTA ("max_liability_per_trade_superato"), quindi
     *  il bottone si spegne prima invece di far scoprire il rifiuto dopo il click. */
    maxLiability?: number | null;
    /** etichetta dell'importo abbinabile (le combinazioni ne hanno una propria:
     *  lì il numero è lo stake TOTALE massimo che entra su TUTTE le gambe) */
    sizeLabel?: string;
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

/** tolleranza sui centesimi: il servizio arrotonda, non è una differenza vera */
const CENT = 0.005;

export type PlacementTone = 'pending' | 'awaiting' | 'partial' | 'duplicate' | 'ok' | 'rejected' | 'error';

export interface PlacementOutcome {
    tone: PlacementTone;
    /** etichetta corta in ITALIANO per il badge */
    label: string;
    /** spiegazione (sempre in italiano) di cosa è successo davvero */
    message: string | null;
    /** true = nessun ordine NUOVO è finito a mercato con questo click */
    noNewOrder: boolean;
}

function num(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}

/**
 * Esito di UN piazzamento, come lo deve leggere un trader.
 *
 * `requestOutcome` (lib) dice solo se la RICHIESTA è andata a buon fine: per
 * il servizio "done" vuol dire "ho fatto quello che mi hai chiesto", e ci
 * finiscono dentro tre casi molto diversi fra loro che non sono "eseguito":
 *   · `deduplicated` → la stessa chiave era già stata usata: nessun ordine nuovo;
 *   · `pending_fill` / `status='pending'` → ordine a mercato, abbinamento IGNOTO;
 *   · `size` < size richiesta → abbinato solo in parte (il resto non esiste).
 * Tutto il resto (rifiutato / errore / in coda) passa invariato dalla lib.
 */
export function placementOutcome(req: SafeRequest | null | undefined): PlacementOutcome | null {
    const base = requestOutcome(req);
    if (!base) return null;
    if (base.tone !== 'ok') {
        return {
            tone: base.tone, label: base.label, message: base.message,
            noNewOrder: base.tone !== 'pending',
        };
    }
    const res = (req?.result ?? {}) as Record<string, unknown>;
    const asked = num((req?.payload ?? {})['size']);
    const got = num(res['size']);
    const status = String(res['status'] ?? '').trim().toLowerCase();
    if (res['deduplicated'] === true) {
        return {
            tone: 'duplicate', label: 'già piazzato',
            message: 'ordine già inviato in precedenza: NON ne è stato piazzato uno nuovo',
            noNewOrder: true,
        };
    }
    if (res['pending_fill'] === true || status === 'pending') {
        return {
            tone: 'awaiting', label: 'in attesa di abbinamento',
            message: "ordine a mercato: l'abbinamento non è ancora confermato, la posizione potrebbe non esserci",
            noNewOrder: false,
        };
    }
    if (asked != null && got != null && got < asked - CENT) {
        const rest = Math.round((asked - got) * 100) / 100;
        return {
            tone: 'partial', label: 'abbinato in parte',
            message: `abbinati ${fmtMoney(got)} dei ${fmtMoney(asked)} richiesti: ${fmtMoney(rest)} NON sono entrati`,
            noNewOrder: false,
        };
    }
    return {
        tone: 'ok', label: 'eseguito',
        message: got != null ? `abbinati ${fmtMoney(got)}` : base.message,
        noNewOrder: false,
    };
}

const TONE_CLASS: Record<PlacementTone, string> = {
    ok: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    partial: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    awaiting: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
    duplicate: 'bg-slate-500/15 text-slate-300 border-slate-500/40',
    pending: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    rejected: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    error: 'bg-red-500/15 text-red-300 border-red-500/40',
};

function ToneIcon({ tone }: { tone: PlacementTone }) {
    if (tone === 'ok') return <Check className="w-3 h-3 mr-1" aria-hidden />;
    if (tone === 'error' || tone === 'rejected') return <X className="w-3 h-3 mr-1" aria-hidden />;
    if (tone === 'duplicate') return <CircleSlash className="w-3 h-3 mr-1" aria-hidden />;
    if (tone === 'awaiting' || tone === 'partial') return <Clock className="w-3 h-3 mr-1" aria-hidden />;
    return null;
}

export function InvestAction({
    mode, side, price, sizeAvailable, defaultStake, minStake, maxLiability, sizeLabel,
    disabled = false, disabledReason, requests, onPlace, onStakeChange,
}: InvestActionProps) {
    // soglia di GIURISDIZIONE (nota), NON soglia di blocco: il minimo che il
    // bottone impone è MIN_STAKE_ALLOWED (0,01 €), sempre.
    const jurisdictionMin = Number.isFinite(Number(minStake)) && Number(minStake) > 0
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
    const outcome = placementOutcome(req);
    // 'pending' = richiesta ancora in coda; 'awaiting' = ordine a mercato con
    // abbinamento ignoto. In entrambi i casi ri-cliccare significherebbe
    // rischiare una SECONDA posizione: il bottone resta spento.
    const pending = busy || outcome?.tone === 'pending' || outcome?.tone === 'awaiting';
    // CERT. 13/09 — sotto il minimo di giurisdizione l'ordine entra COMUNQUE
    // (place-and-trim del servizio): `belowMin` è una NOTA informativa, non
    // partecipa più a `invalid` e non spegne più il bottone.
    const belowMin = stake > 0 && stake < jurisdictionMin;
    // CERT. 12/09 — LIQUIDITA': `sizeAvailable` e' l'importo abbinabile al
    // MIGLIOR prezzo, cioe' l'unico prezzo a cui questo ordine puo' entrare.
    // In live il servizio manda FILL_OR_KILL: sopra questa cifra l'ordine
    // viene annullato TUTTO (niente posizione); in paper entrerebbe solo in
    // parte. In entrambi i casi non e' quello che il trader sta chiedendo.
    const matchable = sizeAvailable != null && Number.isFinite(Number(sizeAvailable))
        ? Number(sizeAvailable) : null;
    const noBook = matchable != null && matchable <= 0;
    const overBook = matchable != null && matchable > 0 && stake > matchable + CENT;
    const overCap = maxLiability != null && Number(maxLiability) > 0 && liability != null
        && liability > Number(maxLiability) + CENT;
    const liquidityReason = noBook
        ? 'nessun importo abbinabile al miglior prezzo in questo momento'
        : overBook
            ? `abbinabili solo ${fmtMoney(matchable)} al miglior prezzo: uno stake di ${fmtMoney(stake)} `
              + "non entra (in LIVE l'ordine è FILL_OR_KILL e verrebbe annullato per intero)"
            : undefined;
    const capReason = overCap
        ? `responsabilità ${fmtMoney(liability)} oltre il cap per operazione (${fmtMoney(Number(maxLiability))}): il servizio rifiuterebbe`
        : undefined;
    const blockReason = disabled ? disabledReason : (liquidityReason ?? capReason);
    const blocked = disabled || noBook || overBook || overCap;
    // l'UNICO minimo che blocca è 0,01 €: sotto non esiste un ordine Betfair.
    const invalid = stake < MIN_STAKE_ALLOWED || price == null || price <= 1;
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
        if (invalid || pending || blocked || inFlight.current) return;
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
                    // passo al CENTESIMO: qualsiasi importo fino a 0,01 € è
                    // piazzabile, quindi anche digitabile con le frecce.
                    step={0.01}
                    min={MIN_STAKE_ALLOWED}
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
                disabled={invalid || pending || blocked}
                title={blocked ? blockReason : undefined}
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
                    {sizeLabel ?? 'abbinabile subito'}{' '}
                    <b
                        className={overBook || noBook ? 'text-amber-300 tabular-nums' : 'text-emerald-300 tabular-nums'}
                        data-testid="invest-matchable"
                    >
                        {matchable != null ? fmtMoney(matchable) : 'n/d'}
                    </b>
                    {matchable == null && (
                        <span className="ml-1 text-slate-500" title="la fonte non pubblica la size al miglior prezzo: non è verificabile quanto entra davvero">
                            (non verificabile)
                        </span>
                    )}
                </div>
                {liability != null && (
                    // NON è "liability aperta": la posizione non esiste ancora.
                    <div title="quanto metteresti a rischio SE l'ordine venisse abbinato tutto: stake × (quota − 1)">
                        responsabilità se abbinato{' '}
                        <b className={overCap ? 'text-red-300 tabular-nums' : 'text-orange-300 tabular-nums'}>
                            {fmtMoney(liability)}
                        </b>
                    </div>
                )}
            </div>

            {disabled && disabledReason && (
                <span className="text-[11px] text-amber-300/90" data-testid="invest-disabled-reason">{disabledReason}</span>
            )}

            {!disabled && liquidityReason && (
                <span className="text-[11px] text-amber-300/90" data-testid="invest-liquidity">{liquidityReason}</span>
            )}

            {!disabled && !liquidityReason && capReason && (
                <span className="text-[11px] text-red-300/90" data-testid="invest-cap">{capReason}</span>
            )}

            {belowMin && (
                // NOTA, non blocco — stesso tono di CashOutButton («cashout-min-note»)
                // e stesse parole di BotParamsSheet («Size minima Betfair €»).
                <span className="text-[11px] text-amber-300/90" data-testid="invest-min-stake">
                    sotto {fmtMoney(jurisdictionMin)} il servizio usa il metodo 1000→cancella→sposta:
                    l&apos;ordine viene immesso lo stesso (parcheggio a quota 1000, taglio, riprezzo)
                </span>
            )}

            {outcome && (
                <span className="flex items-center gap-1.5">
                    <Badge
                        variant="outline"
                        data-testid="invest-status"
                        data-tone={outcome.tone}
                        className={TONE_CLASS[outcome.tone]}
                        title={outcome.message ?? undefined}
                    >
                        <ToneIcon tone={outcome.tone} />
                        {outcome.label}
                    </Badge>
                    {/* ogni richiesta deve dire PERCHE', non solo "errore" (L-07) */}
                    {outcome.message && (
                        <span
                            className={`text-[11px] ${outcome.tone === 'ok' ? 'text-emerald-300/90' : outcome.tone === 'error' ? 'text-red-300/90' : 'text-amber-300/90'}`}
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
