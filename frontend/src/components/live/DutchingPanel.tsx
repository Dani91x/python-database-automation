// ============================================================================
// DutchingPanel — calcolatore + piazzamento DUTCHING (stile Bet Angel / Fairbot).
// L'utente sceglie ≥2 selezioni, una puntata TOTALE, il lato back (dutch) o lay
// (bookmaking) e la modalità equal / variable (peso per-selezione). L'ANTEPRIMA
// LIVE mostra il book% (overround) — verde se favorevole — lo stake per gamba e il
// profitto/responsabilità stimati. Alla conferma chiama sendDutch: il SERVER resta
// AUTORITATIVO (ricalcola gli stake a profitto pareggiato e piazza ogni gamba).
//
// Matematica QUI = solo anteprima:
//   book% = Σ(1/quota)·100  (bookPercentage da @/lib/riskMath)
//   equal : peso base_i = 1/quota_i ; stake_i = totale · peso_i / Σpeso
//   variable: IDENTICA a `dutch_variable` del server (profitto ∝ peso utente), vedi
//             `dutchVariablePlan` (solo BACK: sul lato Lay il worker la rifiuta)
//   BACK: profitto_se_vince_i = stake_i·quota_i − totale (equal → uguale per tutte)
//   LAY : responsabilità_i    = stake_i·(quota_i − 1)
//   BACK favorevole se book% < 100 · LAY favorevole se book% > 100.
//
// MONEY-CRITICAL: in LIVE serve conferma esplicita (one-shot, resettata dopo l'invio);
// kill-switch locale blocca ogni invio; sendDutch è idempotente e su timeout NON
// reinvia. In modalità 'off' il pannello è in sola lettura.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Loader2, ShieldAlert, Layers, Scale } from 'lucide-react';
import { toast } from 'sonner';
import { bookPercentage } from '@/lib/riskMath';
import {
    sendDutch, shouldResetLiveConfirm,
    type LiveOrderMode, type LiveOrderSide, type LivePersistence,
    type DutchMode, type DutchPricing, type LiveOrderResult,
} from '@/lib/liveOrders';

// 'off' = runner senza ordini: pannello in sola lettura (zero regressioni).
export type DutchPanelMode = 'off' | LiveOrderMode;

// come il server piazza ogni gamba (nota anteprima + coerenza col worker).
const PRICING_NOTE: Record<DutchPricing, string> = {
    as_given: 'ai prezzi impostati',
    best: 'al best price live',
    in_front: 'un tick davanti al best',
    nominated: 'al prezzo nominato',
};

export interface DutchSelection {
    selection_id: number;
    name?: string;
    back?: number | null;
    lay?: number | null;
}

interface Props {
    marketId: string;
    mode: DutchPanelMode;
    selections: DutchSelection[];
    eventLabel?: string;
    handicap?: number;
    pollMs?: number; // riservato per parità API con gli altri pannelli
    /** fix audit #14: timestamp del book (live_now.updated_at). Se il snapshot è più
     *  vecchio di DUTCH_FRESH_MS il "Piazza" è disabilitato con avviso — mai piazzare
     *  gambe su quote stantie. Assente = nessun guardiano (compat chiamanti legacy). */
    updatedAt?: string | null;
}

// snapshot più vecchio di così = quote stantie: piazzamento bloccato (pattern
// XHEDGE_FRESH_MS di XHedgePanel, ri-verificato AL CLICK oltre che al render).
export const DUTCH_FRESH_MS = 10_000;

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ds-v2-campo ' +
    'focus:outline-none focus:border-primary/60 transition-colors disabled:opacity-40';
const FIELD_LABEL = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const num = (s: string): number | null => {
    if (s == null || s.trim() === '') return null;
    const v = Number(s);
    return Number.isFinite(v) ? v : null;
};
const money = (v?: number | null) =>
    v == null || !Number.isFinite(v) ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;
const r2 = (x: number) => Math.round(x * 100) / 100;

// ------------------- aritmetica IDENTICA al server (dutch_variable) -------------------
// Il server calcola in Python: `round(x, 2)` arrotonda sul valore binario ESATTO e, sui
// pareggi esatti (x = j/8 con j dispari: 0.125, 0.375, ...), va al pari; `sum()` dei float
// e' compensata (Neumaier, da Python 3.12). Math.round(x*100)/100 differisce da entrambi.

/** `round(x, 2)` di Python: sul valore binario esatto, pareggi esatti al centesimo pari. */
export function pyRound2(x: number): number {
    if (!Number.isFinite(x)) return x;
    const a = Math.abs(x);
    const e = a * 8; // moltiplicare per 2^k e' esatto
    if (Number.isInteger(e) && e % 2 === 1) { // pareggio esatto: a*100 = n + 0.5
        const lo = Math.floor(a * 100);
        const n = lo % 2 === 0 ? lo : lo + 1;
        return Math.sign(x) * (n / 100);
    }
    return Number(x.toFixed(2)); // toFixed e' corretto sul valore binario esatto
}

/** `sum()` di Python sui float (3.12+): somma compensata alla Neumaier. */
function pySum(xs: readonly number[]): number {
    let acc = 0;
    let c = 0;
    for (const x of xs) {
        const t = acc + x;
        if (!Number.isFinite(t)) { acc = t; continue; }
        if (Math.abs(acc) >= Math.abs(x)) c += (acc - t) + x; else c += (x - t) + acc;
        acc = t;
    }
    return c !== 0 && Number.isFinite(c) ? acc + c : acc;
}

// [limite superiore, passo in centesimi] — scala dei tick Betfair (flumine CUTOFFS)
const TICK_CUTOFFS: ReadonlyArray<readonly [number, number]> = [
    [2, 1], [3, 2], [4, 5], [6, 10], [10, 20], [20, 50], [30, 100], [50, 200], [100, 500], [1000, 1000],
];

/** `get_nearest_price` di flumine (quanto usa il server): tick piu' vicino, mezzo tick in su. */
export function nearestTickPrice(price: number): number {
    if (price <= 1.01) return 1.01;
    if (price > 1000) return 1000;
    let stepCents = 1000;
    for (const [cutoff, st] of TICK_CUTOFFS) {
        if (price < cutoff) { stepCents = st; break; }
    }
    // aritmetica intera su price*1e8 (i pareggi tipo 2.01 -> 2.02 non dipendono dal float)
    const x = Math.round(price * 1e8);
    const k = 1e6 * stepCents;
    const n = Math.floor((2 * x + k) / (2 * k));
    return (n * stepCents) / 100;
}

export interface VariablePlanLeg { price: number; stake: number; profit: number }
export interface VariablePlan {
    legs: VariablePlanLeg[];
    total: number;
    bookPct: number;
    /** indice (in `input`) della prima gamba con stake negativo = pesi irrealizzabili; -1 = ok */
    negativeIndex: number;
}

/**
 * Stessa matematica di `dutch_variable` (Betfair/stream/trading/dutching.py): profitto
 * proporzionale al peso, k = T(1−Σ1/p)/Σ(w/p), s_i = round((T + k·w_i)/p_i, 2),
 * totale = round(Σs, 2), profitto_i = round(s_i·p_i − totale, 2). I prezzi sono portati al
 * tick come fa il server. `input` e' GIA' filtrato (quota > 1, peso > 0).
 */
export function dutchVariablePlan(
    input: readonly { price: number; weight: number }[],
    totalStake: number,
): VariablePlan {
    const prices = input.map(l => nearestTickPrice(l.price));
    const invSum = pySum(prices.map(p => 1 / p));
    const wpSum = pySum(input.map((l, i) => l.weight / prices[i]));
    const k = totalStake * (1 - invSum) / wpSum;
    const bookPct = pyRound2(invSum * 100);
    const stakes = input.map((l, i) => pyRound2((totalStake + k * l.weight) / prices[i]));
    const negativeIndex = stakes.findIndex(s => s < 0);
    if (negativeIndex >= 0) return { legs: [], total: 0, bookPct, negativeIndex };
    const total = pyRound2(pySum(stakes));
    return {
        legs: stakes.map((stake, i) => ({
            price: prices[i], stake, profit: pyRound2(stake * prices[i] - total),
        })),
        total, bookPct, negativeIndex: -1,
    };
}

// ----------------------------- badge modalità -----------------------------
function ModeBadge({ mode }: { mode: DutchPanelMode }) {
    if (mode === 'live') {
        return (
            <Badge className="bg-red-600 text-white font-black border-transparent animate-pulse">
                🔴 LIVE REALE
            </Badge>
        );
    }
    if (mode === 'paper') {
        return <Badge className="bg-amber-400 text-black font-black border-transparent">PAPER</Badge>;
    }
    return <Badge variant="secondary" className="font-black">OFF</Badge>;
}

interface Leg {
    selection_id: number;
    name: string;
    price: number;
    userWeight: number;
    stake: number;
    profitBack: number;   // profitto se questa gamba vince (lato back)
    liability: number;    // responsabilità se questa gamba vince (lato lay)
}

export function DutchingPanel({
    marketId,
    mode,
    selections,
    eventLabel,
    handicap = 0,
    updatedAt,
}: Props) {
    const readOnly = mode === 'off';
    const isLive = mode === 'live';

    // fix audit #14: freschezza del book — tick di rivalutazione (2s) così il bottone
    // si disabilita da solo quando lo snapshot invecchia, senza aspettare un re-render.
    const [nowTick, setNowTick] = useState(() => Date.now());
    useEffect(() => {
        if (updatedAt == null) return;
        const t = setInterval(() => setNowTick(Date.now()), 2000);
        return () => clearInterval(t);
    }, [updatedAt]);
    // null = nessun timestamp fornito (nessun guardiano); true/false = fresco/stantio.
    const bookFresh: boolean | null = updatedAt == null
        ? null
        : Number.isFinite(Date.parse(updatedAt)) && nowTick - Date.parse(updatedAt) <= DUTCH_FRESH_MS;

    // -------------------- form --------------------
    const [side, setSide] = useState<LiveOrderSide>('back');
    const [calcMode, setCalcMode] = useState<DutchMode>('equal');
    const [totalStake, setTotalStake] = useState('10');
    const [targetProfit, setTargetProfit] = useState('5');       // usato solo in calcMode='target'
    const [pricing, setPricing] = useState<DutchPricing>('as_given');
    const [nominatedPrice, setNominatedPrice] = useState('');    // usato solo con pricing='nominated'
    const [persistence, setPersistence] = useState<LivePersistence>('LAPSE');
    // preseleziona le prime due selezioni per un'anteprima immediata.
    const [checked, setChecked] = useState<Record<number, boolean>>(() => {
        const init: Record<number, boolean> = {};
        selections.slice(0, 2).forEach(s => { init[s.selection_id] = true; });
        return init;
    });
    const [priceOverride, setPriceOverride] = useState<Record<number, string>>({});
    const [weightOverride, setWeightOverride] = useState<Record<number, string>>({});
    const [confirmLive, setConfirmLive] = useState(false);
    const [killSwitch, setKillSwitch] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    // fix audit #28: guardia SINCRONA anti-doppio-invio (lo stato `submitting` è
    // asincrono: due click ravvicinati passerebbero entrambi). Pattern ScalperPanel.
    const busyRef = useRef(false);

    const isTargetMode = calcMode === 'target';
    const isNominated = pricing === 'nominated';

    const defaultPrice = (s: DutchSelection): number | null =>
        side === 'back' ? (s.back ?? null) : (s.lay ?? null);

    // -------------------- anteprima (matematica pura) --------------------
    const preview = useMemo(() => {
        const enteredTotal = num(totalStake) ?? 0;
        const target = num(targetProfit) ?? 0;

        // 1) risolvi quota + peso effettivi per ogni selezione spuntata e valida.
        type Raw = { s: DutchSelection; on: boolean; price: number; userWeight: number; valid: boolean };
        const raws: Raw[] = selections.map(s => {
            const on = checked[s.selection_id] === true;
            const ov = priceOverride[s.selection_id];
            const price = ov != null && ov.trim() !== '' ? Number(ov) : (defaultPrice(s) ?? NaN);
            const wv = weightOverride[s.selection_id];
            const userWeight = calcMode === 'variable'
                ? (wv != null && wv.trim() !== '' ? Number(wv) : 1)
                : 1;
            const valid = on
                && Number.isFinite(price) && price > 1
                && (calcMode !== 'variable' || (Number.isFinite(userWeight) && userWeight > 0));
            return { s, on, price, userWeight, valid };
        });

        const validRaws = raws.filter(r => r.valid);
        // VARIABLE: stessa formula e stessi arrotondamenti del server (profitto ∝ peso).
        const variable = calcMode === 'variable' && validRaws.length > 0
            ? dutchVariablePlan(validRaws.map(r => ({ price: r.price, weight: r.userWeight })), enteredTotal)
            : null;
        const negLeg = variable != null && variable.negativeIndex >= 0 ? validRaws[variable.negativeIndex] : null;
        const infeasible: string | null = variable != null && negLeg != null
            ? `Pesi irrealizzabili con book ${variable.bookPct.toFixed(2)}%: stake negativo sulla selezione `
                + `«${negLeg.s.name ?? `#${negLeg.s.selection_id}`}» `
                + '— riduci i pesi o usa Equal (profitto pari). Il server non piazzerebbe nulla.'
            : null;
        const book = variable != null ? variable.bookPct : bookPercentage(validRaws.map(r => r.price));

        // TARGET (equal-profit): il server dimensiona le gambe dal profitto obiettivo.
        // Stima UI del totale per il lato back: S = T·b/(1−b) con b=book/100 (fattibile solo se book<100).
        // Per equal/variable il totale è quello inserito dall'utente.
        const b = book / 100;
        const total = calcMode === 'target'
            ? (side === 'back' && b > 0 && b < 1 ? r2((target * b) / (1 - b)) : 0)
            : enteredTotal;

        // 2) pesi: base 1/quota; variable moltiplica per il peso utente.
        const weighted = validRaws.map(r => ({ r, w: (1 / r.price) * r.userWeight }));
        const sumW = weighted.reduce((a, b) => a + b.w, 0);

        // 3) stake + profitto/responsabilità per gamba.
        const legs: Leg[] = weighted.map(({ r, w }, i) => {
            // variable: stake/profitto = quelli del server; irrealizzabile = nulla da mostrare.
            const stake = variable != null
                ? (variable.legs[i]?.stake ?? 0)
                : (sumW > 0 ? r2(total * w / sumW) : 0);
            return {
                selection_id: r.s.selection_id,
                name: r.s.name ?? `#${r.s.selection_id}`,
                price: r.price,
                userWeight: r.userWeight,
                stake,
                profitBack: variable != null ? (variable.legs[i]?.profit ?? 0) : r2(stake * r.price - total),
                liability: r2(stake * (r.price - 1)),
            };
        });

        const legById = new Map(legs.map(l => [l.selection_id, l]));
        const profits = legs.map(l => l.profitBack);
        const liabilities = legs.map(l => l.liability);
        // favorevole: back → book<100 ; lay → book>100.
        const bookOk = side === 'back' ? (book > 0 && book < 100) : (book > 100);

        return {
            total,
            target,
            book,
            bookOk,
            infeasible,
            legs,
            legById,
            count: legs.length,
            minProfit: profits.length ? Math.min(...profits) : 0,
            maxProfit: profits.length ? Math.max(...profits) : 0,
            totalLiability: liabilities.reduce((a, b) => a + b, 0),
            sumStake: variable != null ? variable.total : r2(legs.reduce((a, b) => a + b.stake, 0)),
        };
        // defaultPrice dipende da `side`: incluso nelle deps sotto.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selections, checked, priceOverride, weightOverride, side, calcMode, totalStake, targetProfit]);

    // -------------------- invio --------------------
    const guardBeforeSend = (): string | null => {
        if (readOnly) return 'Modalità OFF: il runner non accetta ordini.';
        if (killSwitch) return 'Blocco pannello attivo: invio bloccato. Disattivalo per operare.';
        if (isLive && !confirmLive) return 'Spunta "Confermo dutching REALE" prima di inviare in LIVE.';
        // fix audit #14: RI-verifica la freschezza AL CLICK (non solo al render).
        if (updatedAt != null &&
            !(Number.isFinite(Date.parse(updatedAt)) && Date.now() - Date.parse(updatedAt) <= DUTCH_FRESH_MS)) {
            return `Quote stantie (snapshot > ${DUTCH_FRESH_MS / 1000}s): attendi l'aggiornamento del book prima di piazzare.`;
        }
        // fix audit #19: Lay + Target è SEMPRE rifiutato dal worker → blocco client-side.
        if (side === 'lay' && isTargetMode) {
            return 'Modalità Target non disponibile sul lato Lay (il worker la rifiuta): usa Equal/Variable.';
        }
        // A1: dutch_variable e' SOLO back (il worker rifiuta variable + lay): blocco client-side.
        if (side === 'lay' && calcMode === 'variable') {
            return 'Modalità Variable non disponibile sul lato Lay (il worker la rifiuta): usa Equal o passa a Back.';
        }
        if (preview.count < 2) return 'Seleziona almeno 2 selezioni con quota valida.';
        // M11/V3: pesi irrealizzabili = il server non piazzerebbe nulla → non inviare.
        if (preview.infeasible) return preview.infeasible;
        if (isTargetMode) {
            if (preview.target <= 0) return 'Profitto obiettivo non valido (> 0).';
        } else if (preview.total <= 0) {
            return 'Puntata totale non valida.';
        }
        if (isNominated && !((num(nominatedPrice) ?? 0) > 1)) {
            return 'Prezzo nominato non valido (> 1).';
        }
        return null;
    };

    const toggle = (id: number) => setChecked(c => ({ ...c, [id]: !c[id] }));

    const handleDutch = async () => {
        if (busyRef.current) return; // anti-doppio-invio sincrono (fix audit #28)
        const blocked = guardBeforeSend();
        if (blocked) { toast.error(blocked); return; }
        busyRef.current = true;
        setSubmitting(true);
        try {
            const res = await sendDutch({
                marketId,
                mode: mode as LiveOrderMode,
                handicap,
                side,
                dutchMode: calcMode,
                pricing,
                ...(isNominated ? { nominatedPrice: num(nominatedPrice) ?? undefined } : {}),
                ...(isTargetMode
                    ? { targetProfit: preview.target }
                    : { totalStake: preview.total }),
                persistence,
                selections: preview.legs.map(l => ({
                    selection_id: l.selection_id,
                    price: l.price,
                    ...(calcMode === 'variable' ? { weight: l.userWeight } : {}),
                })),
            });
            // V3: il worker risponde ok=True ANCHE quando il piano non e' azionabile (es. pesi
            // irrealizzabili) e non parte alcun ordine: in quel caso `legs` (scritto dal worker
            // solo dopo il piazzamento) manca o e' vuoto → NON dire "inviato".
            const placedLegs = (res as LiveOrderResult & { legs?: unknown }).legs;
            if (res.ok && !(Array.isArray(placedLegs) && placedLegs.length > 0)) {
                toast.error('Dutching NON piazzato', {
                    description: res.detail ?? 'nessun ordine partito (piano non azionabile)',
                });
            } else if (res.ok) {
                toast.success('Dutching inviato', {
                    description: [
                        `${preview.count} gambe`,
                        `book ${preview.book.toFixed(2)}%`,
                        res.status ?? null,
                    ].filter(Boolean).join(' · ') || undefined,
                });
            } else {
                toast.error('Dutching rifiutato', { description: res.error ?? res.detail ?? 'motivo non noto' });
            }
            // MONEY-CRITICAL: conferma LIVE one-shot → reset dopo un invio riuscito.
            if (shouldResetLiveConfirm(isLive, res.ok)) setConfirmLive(false);
        } catch (e: any) {
            // include il caso timeout: messaggio "NON reinviare" già dentro sendDutch.
            toast.error('Errore dutching', { description: e?.message ?? 'errore sconosciuto' });
            // MONEY-CRITICAL (fix review MEDIUM): su timeout/errore il dutching POTREBBE essere
            // già stato piazzato. In LIVE resettiamo la conferma così un re-invio richiede una
            // nuova spunta esplicita → nessun secondo set di ordini reali con un click.
            if (isLive) setConfirmLive(false);
        } finally {
            busyRef.current = false;
            setSubmitting(false);
        }
    };

    const bookTone = preview.bookOk
        ? 'text-emerald-300'
        : preview.book > 0 ? 'text-rose-300' : 'text-white/40';
    const sideIsBack = side === 'back';

    return (
        <div className="glass-card rounded-2xl border border-white/10 bg-black/40 p-4 md:p-5 space-y-5">
            {/* header + badge modalità */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <div className="flex items-center gap-2">
                        <Layers className="w-5 h-5 text-amber-400" />
                        <h3 className="font-display font-black text-lg text-white">Dutching</h3>
                        <ModeBadge mode={mode} />
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        {eventLabel ? `${eventLabel} · ` : ''}
                        {sideIsBack ? 'Punta più esiti (dutch)' : 'Banca più esiti (bookmaking)'} ·{' '}
                        mercato <span className="font-mono text-white/70">{marketId}</span>
                    </p>
                </div>
                <button
                    type="button"
                    onClick={() => setKillSwitch(k => !k)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors ${
                        killSwitch
                            ? 'bg-red-600 text-white border-transparent'
                            : 'bg-white/5 text-white/70 border-white/10 hover:border-red-500/40'
                    }`}
                    title="Blocca SOLO gli invii di questo pannello (il Kill-switch GLOBALE del runner è nei Controlli)"
                >
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Blocco pannello {killSwitch ? 'ON' : 'OFF'}
                </button>
            </div>

            {readOnly && (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground">
                    Runner in <b>OFF</b>: dutching in sola lettura. Avvia il runner in PAPER o LIVE per piazzare.
                </div>
            )}

            <fieldset disabled={readOnly} className="space-y-4">
                {/* ---------------- parametri globali ---------------- */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div>
                        <Label className={FIELD_LABEL}>Lato</Label>
                        <select className={SELECT_CLS} value={side}
                            onChange={e => {
                                const s = e.target.value as LiveOrderSide;
                                setSide(s);
                                // fix audit #19: Lay+Target è sempre rifiutato dal worker →
                                // al passaggio su Lay la modalità Target ripiega su Equal.
                                if (s === 'lay' && calcMode === 'target') setCalcMode('equal');
                            }}>
                            <option value="back">Back (dutch)</option>
                            <option value="lay">Lay (bookmaking)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Modalità</Label>
                        <select className={SELECT_CLS} value={calcMode}
                            onChange={e => setCalcMode(e.target.value as DutchMode)}>
                            <option value="equal">Equal (profitto pari)</option>
                            {/* A1: Variable e' solo Back (il worker rifiuta variable + lay) */}
                            <option value="variable" disabled={side === 'lay'}>
                                Variable (peso{side === 'lay' ? ' — solo Back' : ''})
                            </option>
                            {/* fix audit #19: Target non disponibile sul lato Lay (il worker lo rifiuta) */}
                            <option value="target" disabled={side === 'lay'}>
                                Target (profitto obiettivo{side === 'lay' ? ' — solo Back' : ''})
                            </option>
                        </select>
                    </div>
                    {isTargetMode ? (
                        <div>
                            <Label className={FIELD_LABEL}>Profitto obiettivo (€)</Label>
                            <Input type="number" step="0.5" min="0" value={targetProfit}
                                onChange={e => setTargetProfit(e.target.value)} placeholder="es. 5"
                                className="bg-black/60 border-white/10" />
                        </div>
                    ) : (
                        <div>
                            <Label className={FIELD_LABEL}>Puntata totale (€)</Label>
                            <Input type="number" step="0.5" min="0" value={totalStake}
                                onChange={e => setTotalStake(e.target.value)} placeholder="es. 10"
                                className="bg-black/60 border-white/10" />
                        </div>
                    )}
                    <div>
                        <Label className={FIELD_LABEL}>Persistenza</Label>
                        <select className={SELECT_CLS} value={persistence}
                            onChange={e => setPersistence(e.target.value as LivePersistence)}>
                            <option value="LAPSE">LAPSE (decade in-play)</option>
                            <option value="PERSIST">PERSIST (resta)</option>
                            <option value="MARKET_ON_CLOSE">MARKET_ON_CLOSE</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Prezzo</Label>
                        <select className={SELECT_CLS} value={pricing}
                            onChange={e => setPricing(e.target.value as DutchPricing)}>
                            <option value="as_given">Come impostato</option>
                            <option value="best">Best price live</option>
                            <option value="in_front">Un tick davanti</option>
                            <option value="nominated">Nominato</option>
                        </select>
                    </div>
                    {isNominated && (
                        <div>
                            <Label className={FIELD_LABEL}>Prezzo nominato</Label>
                            <Input type="number" step="0.01" min="1.01" max="1000" value={nominatedPrice}
                                onChange={e => setNominatedPrice(e.target.value)} placeholder="es. 2.50"
                                className="bg-black/60 border-white/10 font-mono" />
                        </div>
                    )}
                </div>

                {/* ---------------- selezioni ---------------- */}
                <div>
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mb-2">
                        Selezioni ({preview.count} attive · min 2)
                    </div>
                    {selections.length === 0 ? (
                        <p className="text-xs text-muted-foreground">Nessuna selezione disponibile su questo mercato.</p>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                        <th className="text-left py-1.5 pr-2 w-8"></th>
                                        <th className="text-left py-1.5 px-2">Selezione</th>
                                        <th className="text-right py-1.5 px-2">Quota ({sideIsBack ? 'back' : 'lay'})</th>
                                        {calcMode === 'variable' && <th className="text-right py-1.5 px-2">Peso</th>}
                                        <th className="text-right py-1.5 px-2">Stake</th>
                                        <th className="text-right py-1.5 pl-2">
                                            {sideIsBack ? 'Se vince' : 'Responsabilità'}
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {selections.map(s => {
                                        const id = s.selection_id;
                                        const on = checked[id] === true;
                                        const leg = preview.legById.get(id);
                                        const dp = defaultPrice(s);
                                        const priceStr = priceOverride[id] ?? (dp != null ? String(dp) : '');
                                        const wStr = weightOverride[id] ?? '';
                                        return (
                                            <tr key={id} className={`border-b border-white/[0.04] ${on ? '' : 'opacity-50'}`}>
                                                <td className="py-1.5 pr-2">
                                                    <input type="checkbox" checked={on}
                                                        onChange={() => toggle(id)}
                                                        className="accent-amber-400" />
                                                </td>
                                                <td className="py-1.5 px-2 text-white/80 truncate max-w-[160px]">
                                                    {s.name ?? `#${id}`}
                                                </td>
                                                <td className="py-1.5 px-2 text-right">
                                                    <Input type="number" step="0.01" min="1.01" max="1000"
                                                        value={priceStr}
                                                        onChange={e => setPriceOverride(o => ({ ...o, [id]: e.target.value }))}
                                                        disabled={!on}
                                                        className="bg-black/60 border-white/10 h-8 w-24 text-right font-mono ml-auto" />
                                                </td>
                                                {calcMode === 'variable' && (
                                                    <td className="py-1.5 px-2 text-right">
                                                        <Input type="number" step="0.1" min="0"
                                                            value={wStr} placeholder="1"
                                                            onChange={e => setWeightOverride(o => ({ ...o, [id]: e.target.value }))}
                                                            disabled={!on}
                                                            className="bg-black/60 border-white/10 h-8 w-20 text-right font-mono ml-auto" />
                                                    </td>
                                                )}
                                                <td className="py-1.5 px-2 text-right font-mono text-white">
                                                    {leg && !preview.infeasible ? money(leg.stake) : '—'}
                                                </td>
                                                <td className={`py-1.5 pl-2 text-right font-mono ${
                                                    !leg || preview.infeasible ? 'text-white/40'
                                                        : sideIsBack
                                                            ? (leg.profitBack >= 0 ? 'text-emerald-300' : 'text-rose-300')
                                                            : 'text-rose-300'
                                                }`}>
                                                    {leg && !preview.infeasible
                                                        ? money(sideIsBack ? leg.profitBack : leg.liability) : '—'}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                {side === 'lay' && calcMode === 'variable' && (
                    <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[11px] font-bold text-amber-300">
                        Variable non disponibile sul lato Lay (il worker la rifiuta): passa a Back o scegli Equal.
                    </div>
                )}
                {preview.infeasible && (
                    <div className="rounded-xl border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-[11px] font-bold text-rose-300">
                        {preview.infeasible}
                    </div>
                )}

                {/* ---------------- ANTEPRIMA LIVE ---------------- */}
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 md:p-4">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-3">
                            <Scale className="w-4 h-4 text-amber-400" />
                            <div>
                                <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                                    Book % (overround)
                                </div>
                                <div className={`font-display font-black text-3xl leading-none ${bookTone}`}>
                                    {preview.book > 0 ? `${preview.book.toFixed(2)}%` : '—'}
                                </div>
                                <div className="text-[10px] mt-0.5">
                                    {preview.book <= 0 ? (
                                        <span className="text-white/40">imposta ≥2 quote valide</span>
                                    ) : preview.bookOk ? (
                                        <span className="text-emerald-300 font-bold">
                                            favorevole ({sideIsBack ? '< 100' : '> 100'})
                                        </span>
                                    ) : (
                                        <span className="text-rose-300 font-bold">
                                            sfavorevole ({sideIsBack ? '≥ 100' : '≤ 100'})
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="text-right space-y-0.5">
                            <div className="text-[11px] text-muted-foreground">
                                {isTargetMode ? 'Profitto obiettivo' : 'Puntata totale'}{' '}
                                <span className="font-mono text-white">
                                    {money(isTargetMode ? preview.target : preview.total)}
                                </span>
                                {' '}· stake sommati{' '}
                                <span className="font-mono text-white/70">{money(preview.sumStake)}</span>
                            </div>
                            {sideIsBack ? (
                                <div className="text-[13px]">
                                    <span className="text-muted-foreground">Profitto se vince </span>
                                    {(isTargetMode || calcMode === 'equal') ? (
                                        <span className={`font-mono font-bold ${preview.minProfit >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                            {money(preview.minProfit)}
                                        </span>
                                    ) : (
                                        <span className="font-mono font-bold text-white">
                                            <span className={preview.minProfit >= 0 ? 'text-emerald-300' : 'text-rose-300'}>{money(preview.minProfit)}</span>
                                            {' … '}
                                            <span className={preview.maxProfit >= 0 ? 'text-emerald-300' : 'text-rose-300'}>{money(preview.maxProfit)}</span>
                                        </span>
                                    )}
                                </div>
                            ) : (
                                <div className="text-[13px]">
                                    <span className="text-muted-foreground">Responsabilità totale </span>
                                    <span className="font-mono font-bold text-rose-300">{money(preview.totalLiability)}</span>
                                </div>
                            )}
                            <div className="text-[10px] text-white/40">
                                stima UI — il server piazza {PRICING_NOTE[pricing]}
                                {isNominated && (num(nominatedPrice) ?? 0) > 1
                                    ? ` (${(num(nominatedPrice) as number).toFixed(2)})`
                                    : ''}
                                , ricalcola a profitto pareggiato e arrotonda al tick
                            </div>
                        </div>
                    </div>
                </div>

                {/* ---------------- conferma + invio ---------------- */}
                <div className="flex items-center justify-between gap-3 flex-wrap pt-1">
                    {isLive ? (
                        <label className="inline-flex items-center gap-2 text-xs font-bold text-red-300 cursor-pointer">
                            <input type="checkbox" checked={confirmLive} onChange={e => setConfirmLive(e.target.checked)}
                                className="accent-red-500" />
                            Confermo dutching REALE (soldi veri)
                        </label>
                    ) : (
                        <span className="text-[11px] text-muted-foreground">
                            {readOnly ? 'Modalità OFF.' : 'Modalità PAPER: nessun denaro reale.'}
                        </span>
                    )}

                    {/* fix audit #14: avviso quote stantie (bottone disabilitato sotto) */}
                    {bookFresh === false && !readOnly && (
                        <span className="text-[11px] font-bold text-amber-300">
                            ⚠ Quote stantie (snapshot &gt; {DUTCH_FRESH_MS / 1000}s): piazzamento bloccato finché il book non si aggiorna.
                        </span>
                    )}
                    <Button
                        onClick={handleDutch}
                        disabled={submitting || killSwitch || preview.count < 2
                            || (isTargetMode ? preview.target <= 0 : preview.total <= 0)
                            || (isNominated && !((num(nominatedPrice) ?? 0) > 1))
                            || bookFresh === false
                            || (side === 'lay' && isTargetMode)
                            || (side === 'lay' && calcMode === 'variable')
                            || preview.infeasible != null
                            || (isLive && !confirmLive)}
                        className={`font-black ${
                            sideIsBack
                                ? 'bg-sky-500 hover:bg-sky-400 text-black'
                                : 'bg-rose-500 hover:bg-rose-400 text-black'
                        }`}
                    >
                        {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        {sideIsBack ? 'Piazza Dutch' : 'Piazza Bookmaking'} ({preview.count})
                    </Button>
                </div>
            </fieldset>
        </div>
    );
}

export default DutchingPanel;
