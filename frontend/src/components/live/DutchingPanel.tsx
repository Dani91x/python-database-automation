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
//   peso base_i = 1/quota_i ; variable → base_i·peso_utente_i
//   stake_i = totale · peso_i / Σpeso
//   BACK: profitto_se_vince_i = stake_i·quota_i − totale (equal → uguale per tutte)
//   LAY : responsabilità_i    = stake_i·(quota_i − 1)
//   BACK favorevole se book% < 100 · LAY favorevole se book% > 100.
//
// MONEY-CRITICAL: in LIVE serve conferma esplicita (one-shot, resettata dopo l'invio);
// kill-switch locale blocca ogni invio; sendDutch è idempotente e su timeout NON
// reinvia. In modalità 'off' il pannello è in sola lettura.
// ============================================================================
import { useMemo, useState } from 'react';
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
} from '@/lib/liveOrders';

// 'off' = runner senza ordini: pannello in sola lettura (zero regressioni).
export type DutchPanelMode = 'off' | LiveOrderMode;
type DutchCalcMode = 'equal' | 'variable';

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
}

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
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
}: Props) {
    const readOnly = mode === 'off';
    const isLive = mode === 'live';

    // -------------------- form --------------------
    const [side, setSide] = useState<LiveOrderSide>('back');
    const [calcMode, setCalcMode] = useState<DutchCalcMode>('equal');
    const [totalStake, setTotalStake] = useState('10');
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

    const defaultPrice = (s: DutchSelection): number | null =>
        side === 'back' ? (s.back ?? null) : (s.lay ?? null);

    // -------------------- anteprima (matematica pura) --------------------
    const preview = useMemo(() => {
        const total = num(totalStake) ?? 0;

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
        const book = bookPercentage(validRaws.map(r => r.price));

        // 2) pesi: base 1/quota; variable moltiplica per il peso utente.
        const weighted = validRaws.map(r => ({ r, w: (1 / r.price) * r.userWeight }));
        const sumW = weighted.reduce((a, b) => a + b.w, 0);

        // 3) stake + profitto/responsabilità per gamba.
        const legs: Leg[] = weighted.map(({ r, w }) => {
            const stake = sumW > 0 ? r2(total * w / sumW) : 0;
            return {
                selection_id: r.s.selection_id,
                name: r.s.name ?? `#${r.s.selection_id}`,
                price: r.price,
                userWeight: r.userWeight,
                stake,
                profitBack: r2(stake * r.price - total),
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
            book,
            bookOk,
            legs,
            legById,
            count: legs.length,
            minProfit: profits.length ? Math.min(...profits) : 0,
            maxProfit: profits.length ? Math.max(...profits) : 0,
            totalLiability: liabilities.reduce((a, b) => a + b, 0),
            sumStake: r2(legs.reduce((a, b) => a + b.stake, 0)),
        };
        // defaultPrice dipende da `side`: incluso nelle deps sotto.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selections, checked, priceOverride, weightOverride, side, calcMode, totalStake]);

    // -------------------- invio --------------------
    const guardBeforeSend = (): string | null => {
        if (readOnly) return 'Modalità OFF: il runner non accetta ordini.';
        if (killSwitch) return 'Kill-switch attivo: invio bloccato. Disattivalo per operare.';
        if (isLive && !confirmLive) return 'Spunta "Confermo dutching REALE" prima di inviare in LIVE.';
        if (preview.count < 2) return 'Seleziona almeno 2 selezioni con quota valida.';
        if (preview.total <= 0) return 'Puntata totale non valida.';
        return null;
    };

    const toggle = (id: number) => setChecked(c => ({ ...c, [id]: !c[id] }));

    const handleDutch = async () => {
        const blocked = guardBeforeSend();
        if (blocked) { toast.error(blocked); return; }
        setSubmitting(true);
        try {
            const res = await sendDutch({
                marketId,
                mode: mode as LiveOrderMode,
                handicap,
                totalStake: preview.total,
                side,
                dutchMode: calcMode,
                persistence,
                selections: preview.legs.map(l => ({
                    selection_id: l.selection_id,
                    price: l.price,
                    ...(calcMode === 'variable' ? { weight: l.userWeight } : {}),
                })),
            });
            if (res.ok) {
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
                    title="Kill-switch: blocca ogni invio ordini"
                >
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Kill-switch {killSwitch ? 'ON' : 'OFF'}
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
                            onChange={e => setSide(e.target.value as LiveOrderSide)}>
                            <option value="back">Back (dutch)</option>
                            <option value="lay">Lay (bookmaking)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Modalità</Label>
                        <select className={SELECT_CLS} value={calcMode}
                            onChange={e => setCalcMode(e.target.value as DutchCalcMode)}>
                            <option value="equal">Equal (profitto pari)</option>
                            <option value="variable">Variable (peso)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Puntata totale (€)</Label>
                        <Input type="number" step="0.5" min="0" value={totalStake}
                            onChange={e => setTotalStake(e.target.value)} placeholder="es. 10"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Persistenza</Label>
                        <select className={SELECT_CLS} value={persistence}
                            onChange={e => setPersistence(e.target.value as LivePersistence)}>
                            <option value="LAPSE">LAPSE (decade in-play)</option>
                            <option value="PERSIST">PERSIST (resta)</option>
                            <option value="MARKET_ON_CLOSE">MARKET_ON_CLOSE</option>
                        </select>
                    </div>
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
                                                    {leg ? money(leg.stake) : '—'}
                                                </td>
                                                <td className={`py-1.5 pl-2 text-right font-mono ${
                                                    !leg ? 'text-white/40'
                                                        : sideIsBack
                                                            ? (leg.profitBack >= 0 ? 'text-emerald-300' : 'text-rose-300')
                                                            : 'text-rose-300'
                                                }`}>
                                                    {leg ? money(sideIsBack ? leg.profitBack : leg.liability) : '—'}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

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
                                Puntata totale{' '}
                                <span className="font-mono text-white">{money(preview.total)}</span>
                                {' '}· stake sommati{' '}
                                <span className="font-mono text-white/70">{money(preview.sumStake)}</span>
                            </div>
                            {sideIsBack ? (
                                <div className="text-[13px]">
                                    <span className="text-muted-foreground">Profitto se vince </span>
                                    {calcMode === 'equal' ? (
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
                                stima UI — il server ricalcola a profitto pareggiato e arrotonda al tick
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

                    <Button
                        onClick={handleDutch}
                        disabled={submitting || killSwitch || preview.count < 2 || preview.total <= 0 || (isLive && !confirmLive)}
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
