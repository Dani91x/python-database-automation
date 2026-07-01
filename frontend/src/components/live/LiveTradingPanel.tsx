// ============================================================================
// LiveTradingPanel — pannello operativo LIVE TRADING (Fase 1).
// Order entry (back/lay, prezzo, size o liability, persistence, FoK, cap),
// badge modalità (OFF / PAPER / 🔴 LIVE REALE), lista ordini con stato+fill e
// azioni cancel/replace inline, tabella posizioni/P&L. Ogni campo è cablato alle
// RPC giuste via @/lib/liveOrders. Nessuna logica di matematica/esposizione qui:
// i numeri vengono dal backend (blotter.get_exposures). Design system: glass-card,
// amber Betfair, back azzurro / lay rosa.
//
// MONEY-CRITICAL: in modalità LIVE serve conferma esplicita; kill-switch locale
// blocca ogni invio; su timeout l'ordine NON va reinviato (vedi sendLiveOrderCommand).
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, ShieldAlert, X, Pencil, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';
import {
    sendLiveOrderCommand, fetchLiveOrders, fetchLivePositions,
    layLiabilityFromSize, laySizeFromLiability, shouldResetLiveConfirm,
    LIVE_ORDER_STATUS_LABEL,
    type LiveOrderMode, type LiveOrderSide, type LivePersistence,
    type LiveOrderCommand, type LiveOrderRow, type LivePositionRow,
} from '@/lib/liveOrders';

// 'off' = runner senza ordini (zero regressioni): pannello in sola lettura.
export type PanelMode = 'off' | LiveOrderMode;

interface SelectionOption {
    selection_id: number;
    name: string;
    handicap?: number;
}

interface Props {
    marketId: string;
    mode?: PanelMode;                 // default 'paper'
    eventLabel?: string;              // es. "Inter vs Milan · Match Odds"
    selections?: SelectionOption[];   // selezioni del mercato (per il menù a tendina)
    maxStakeDefault?: number;         // cap anti-errore prefill (€)
    pollMs?: number;                  // refresh ordini/posizioni (default 3000)
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
    v == null ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;

// ----------------------------- badge modalità -----------------------------
function ModeBadge({ mode }: { mode: PanelMode }) {
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

// ----------------------------- riga ordine -----------------------------
function statusTone(status: string): string {
    switch (status) {
        case 'EXECUTION_COMPLETE': return 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10';
        case 'EXECUTABLE': return 'text-sky-300 border-sky-500/30 bg-sky-500/10';
        case 'VIOLATION': return 'text-red-300 border-red-500/30 bg-red-500/10';
        case 'EXPIRED': return 'text-white/50 border-white/10 bg-white/5';
        default: return 'text-amber-300 border-amber-500/30 bg-amber-500/10'; // PENDING
    }
}

export function LiveTradingPanel({
    marketId,
    mode = 'paper',
    eventLabel,
    selections = [],
    maxStakeDefault = 10,
    pollMs = 3000,
}: Props) {
    const readOnly = mode === 'off';
    const isLive = mode === 'live';

    // -------------------- form order entry --------------------
    const [selectionId, setSelectionId] = useState<string>(
        selections[0]?.selection_id != null ? String(selections[0].selection_id) : '',
    );
    const [handicap, setHandicap] = useState('0');
    const [side, setSide] = useState<LiveOrderSide>('back');
    const [price, setPrice] = useState('');
    const [sizeMode, setSizeMode] = useState<'size' | 'liability'>('size');
    const [amount, setAmount] = useState('');           // size € (back/lay) o liability (lay)
    const [persistence, setPersistence] = useState<LivePersistence>('LAPSE');
    const [fillOrKill, setFillOrKill] = useState(false);
    const [minFill, setMinFill] = useState('');
    const [maxStake, setMaxStake] = useState(String(maxStakeDefault));
    const [submin, setSubmin] = useState(false);        // place-and-trim (sotto-minimo)
    const [confirmLive, setConfirmLive] = useState(false);
    const [killSwitch, setKillSwitch] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    // -------------------- liste --------------------
    const [orders, setOrders] = useState<LiveOrderRow[]>([]);
    const [positions, setPositions] = useState<LivePositionRow[]>([]);
    const [loadingLists, setLoadingLists] = useState(false);
    const [listErr, setListErr] = useState<string | null>(null);
    const busyRef = useRef(false);

    // liability stimata (informativa) per lato lay
    const layInfo = useMemo(() => {
        const p = num(price), a = num(amount);
        if (side !== 'lay' || !p || !a || p <= 1) return null;
        if (sizeMode === 'size') return { size: a, liability: layLiabilityFromSize(a, p) };
        return { size: laySizeFromLiability(a, p), liability: a };
    }, [side, price, amount, sizeMode]);

    // Totale P&L di mercato: per ogni possibile esito (selezione s vincente) il P&L netto
    // è matched_if_win[s] + Σ matched_if_lose[j≠s]. worst/best = scenario peggiore/migliore
    // sul mercato. Più esposizione e netto aggregati. (riga di sintesi del cockpit)
    const pnlTotals = useMemo(() => {
        if (positions.length === 0) return null;
        const outcomes = positions.map(w =>
            positions.reduce(
                (acc, p) => acc + (p.selection_id === w.selection_id ? p.matched_if_win : p.matched_if_lose),
                0,
            ),
        );
        return {
            worst: Math.min(...outcomes),
            best: Math.max(...outcomes),
            exposure: positions.reduce((a, p) => a + (p.selection_exposure ?? 0), 0),
            net: positions.reduce((a, p) => a + (p.net_position ?? 0), 0),
        };
    }, [positions]);

    const reload = useCallback(async () => {
        if (!marketId || busyRef.current) return;
        busyRef.current = true;
        setLoadingLists(true);
        setListErr(null);
        try {
            const [o, p] = await Promise.all([fetchLiveOrders(marketId), fetchLivePositions(marketId)]);
            // mostra solo gli ordini/posizioni della modalità attiva (la RPC ritorna entrambe)
            const m = readOnly ? null : (mode as LiveOrderMode);
            setOrders(m ? o.filter(r => r.mode === m) : o);
            setPositions(m ? p.filter(r => r.mode === m) : p);
        } catch (e: any) {
            setListErr(e?.message ?? 'errore di caricamento');
        } finally {
            setLoadingLists(false);
            busyRef.current = false;
        }
    }, [marketId, mode, readOnly]);

    useEffect(() => {
        reload();
        if (pollMs <= 0) return;
        const t = setInterval(reload, pollMs);
        return () => clearInterval(t);
    }, [reload, pollMs]);

    // -------------------- invio comando --------------------
    const guardBeforeSend = (): string | null => {
        if (readOnly) return 'Modalità OFF: il runner non accetta ordini (LIVE_ORDER_MODE=OFF).';
        if (killSwitch) return 'Kill-switch attivo: invio bloccato. Disattivalo per operare.';
        if (isLive && !confirmLive) return 'Spunta "Confermo ordine REALE" prima di inviare in LIVE.';
        return null;
    };

    const runCommand = async (cmd: LiveOrderCommand, okMsg: string) => {
        const blocked = guardBeforeSend();
        if (blocked) { toast.error(blocked); return; }
        setSubmitting(true);
        try {
            const res = await sendLiveOrderCommand(cmd);
            if (res.ok) {
                toast.success(okMsg, {
                    description: [
                        res.bet_id ? `bet ${res.bet_id}` : null,
                        res.status ? (LIVE_ORDER_STATUS_LABEL[res.status] ?? res.status) : null,
                        res.size_matched ? `abbinato €${res.size_matched}` : null,
                        res.submin_step ? `step ${res.submin_step}` : null,
                    ].filter(Boolean).join(' · ') || undefined,
                });
            } else {
                toast.error('Comando rifiutato', { description: res.error ?? res.detail ?? 'motivo non noto' });
            }
            // MONEY-CRITICAL: la conferma "ordine REALE" è one-shot. Dopo un invio LIVE
            // riuscito la resettiamo, così ogni nuovo ordine LIVE richiede una nuova
            // spunta esplicita. In PAPER non cambia nulla. (CODE-MED-2)
            if (shouldResetLiveConfirm(isLive, res.ok)) setConfirmLive(false);
            await reload();
        } catch (e: any) {
            // include il caso timeout: messaggio "NON reinviare" già dentro
            toast.error('Errore comando', { description: e?.message ?? 'errore sconosciuto' });
            // MONEY-CRITICAL (fix review MEDIUM): su timeout/errore l'ordine POTREBBE essere già
            // stato piazzato (l'enqueue è idempotente ma la conferma di stato può scadere). Se
            // eravamo in LIVE resettiamo la spunta "ordine REALE" così un eventuale re-invio
            // richiede una NUOVA conferma esplicita → nessun secondo ordine reale con un click.
            if (isLive) setConfirmLive(false);
        } finally {
            setSubmitting(false);
        }
    };

    const handlePlace = async () => {
        const sel = num(selectionId), p = num(price), a = num(amount);
        if (sel == null) { toast.error('Seleziona la selezione (selection_id).'); return; }
        if (p == null || p < 1.01 || p > 1000) { toast.error('Prezzo non valido (1.01–1000).'); return; }
        if (a == null || a <= 0) { toast.error(`${sizeMode === 'liability' ? 'Liability' : 'Size'} non valida.`); return; }

        const cmd: LiveOrderCommand = {
            action: submin ? 'place_submin' : 'place',
            mode: mode as LiveOrderMode,
            market_id: marketId,
            selection_id: sel,
            handicap: num(handicap) ?? 0,
            side,
            order_type: 'LIMIT',
            price: p,
            persistence,
            time_in_force: fillOrKill ? 'FILL_OR_KILL' : null,
            min_fill_size: fillOrKill ? num(minFill) : null,
            params: { max_stake: num(maxStake) ?? maxStakeDefault },
        };
        // size vs liability (liability solo per lay)
        if (sizeMode === 'liability' && side === 'lay') cmd.liability = a;
        else cmd.size = a;

        await runCommand(cmd, submin ? 'Place-and-trim avviato' : 'Ordine inviato');
    };

    const handleCancel = async (row: LiveOrderRow) => {
        if (!row.bet_id) { toast.error('bet_id mancante: ordine non ancora confermato.'); return; }
        await runCommand(
            { action: 'cancel', mode: mode as LiveOrderMode, market_id: marketId, bet_id: row.bet_id },
            'Cancellazione inviata',
        );
    };

    const handleReplace = async (row: LiveOrderRow) => {
        if (!row.bet_id) { toast.error('bet_id mancante: ordine non ancora confermato.'); return; }
        const raw = window.prompt(`Nuovo prezzo per bet ${row.bet_id} (1.01–1000):`, String(row.price ?? ''));
        if (raw == null) return;
        const np = Number(raw);
        if (!Number.isFinite(np) || np < 1.01 || np > 1000) { toast.error('Nuovo prezzo non valido.'); return; }
        await runCommand(
            { action: 'replace', mode: mode as LiveOrderMode, market_id: marketId, bet_id: row.bet_id, new_price: np },
            'Replace inviato',
        );
    };

    const selName = (id: number) => selections.find(s => s.selection_id === id)?.name ?? `#${id}`;

    return (
        <div className="glass-card rounded-2xl border border-white/10 bg-black/40 p-4 md:p-5 space-y-5">
            {/* header + badge modalità */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <div className="flex items-center gap-2">
                        <TrendingUp className="w-5 h-5 text-amber-400" />
                        <h3 className="font-display font-black text-lg text-white">Live Trading</h3>
                        <ModeBadge mode={mode} />
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        {eventLabel ? `${eventLabel} · ` : ''}mercato <span className="font-mono text-white/70">{marketId}</span>
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {/* kill-switch locale (blocca ogni invio) */}
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
                    <Button variant="ghost" size="sm" onClick={reload} disabled={loadingLists}
                        className="text-muted-foreground hover:text-white">
                        {loadingLists ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                    </Button>
                </div>
            </div>

            {readOnly && (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground">
                    Runner in <b>OFF</b>: order entry disabilitato. Avvia il runner in PAPER o LIVE per operare.
                </div>
            )}

            {/* ---------------- order entry ---------------- */}
            <fieldset disabled={readOnly} className="space-y-3">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="col-span-2 md:col-span-2">
                        <Label className={FIELD_LABEL}>Selezione</Label>
                        {selections.length > 0 ? (
                            <select className={SELECT_CLS} value={selectionId}
                                onChange={e => setSelectionId(e.target.value)}>
                                {selections.map(s => (
                                    <option key={s.selection_id} value={s.selection_id}>
                                        {s.name} (#{s.selection_id})
                                    </option>
                                ))}
                            </select>
                        ) : (
                            <Input type="number" value={selectionId} onChange={e => setSelectionId(e.target.value)}
                                placeholder="selection_id" className="bg-black/60 border-white/10" />
                        )}
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Handicap</Label>
                        <Input type="number" step="0.25" value={handicap} onChange={e => setHandicap(e.target.value)}
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Lato</Label>
                        <select className={SELECT_CLS} value={side} onChange={e => setSide(e.target.value as LiveOrderSide)}>
                            <option value="back">Back (punta)</option>
                            <option value="lay">Lay (banca)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Prezzo (quota)</Label>
                        <Input type="number" step="0.01" min="1.01" max="1000" value={price}
                            onChange={e => setPrice(e.target.value)} placeholder="es. 2.10"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>{sizeMode === 'liability' ? 'Liability (€)' : 'Size (€)'}</Label>
                        <Input type="number" step="0.01" min="0" value={amount}
                            onChange={e => setAmount(e.target.value)} placeholder="es. 2.00"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Importo come</Label>
                        <select className={SELECT_CLS} value={sizeMode}
                            onChange={e => setSizeMode(e.target.value as 'size' | 'liability')}
                            disabled={side !== 'lay'}>
                            <option value="size">Size</option>
                            <option value="liability">Liability (solo lay)</option>
                        </select>
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
                    <div>
                        <Label className={FIELD_LABEL}>Cap max stake (€)</Label>
                        <Input type="number" step="0.5" min="0" value={maxStake}
                            onChange={e => setMaxStake(e.target.value)} className="bg-black/60 border-white/10" />
                    </div>
                </div>

                {/* opzioni FoK / submin */}
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-white/80">
                    <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={fillOrKill} onChange={e => setFillOrKill(e.target.checked)}
                            className="accent-amber-400" />
                        Fill-or-Kill
                    </label>
                    {fillOrKill && (
                        <div className="inline-flex items-center gap-2">
                            <span className="text-muted-foreground text-[11px]">min fill</span>
                            <Input type="number" step="0.01" min="0" value={minFill}
                                onChange={e => setMinFill(e.target.value)}
                                className="bg-black/60 border-white/10 h-8 w-24" />
                        </div>
                    )}
                    <label className="inline-flex items-center gap-2 cursor-pointer" title="Place-and-trim: piazza al minimo e riduce alla size target (sotto-minimo)">
                        <input type="checkbox" checked={submin} onChange={e => setSubmin(e.target.checked)}
                            className="accent-amber-400" />
                        Place-and-trim (sotto-minimo)
                    </label>
                </div>

                {/* feedback liability lay */}
                {layInfo && (
                    <p className="text-[11px] text-muted-foreground">
                        Lay: size <span className="font-mono text-rose-300">€{layInfo.size.toFixed(2)}</span> ·
                        responsabilità <span className="font-mono text-rose-300"> €{layInfo.liability.toFixed(2)}</span>
                        <span className="text-white/40"> (stima; il server arrotonda al tick e legalizza .it)</span>
                    </p>
                )}

                {/* conferma LIVE + invio */}
                <div className="flex items-center justify-between gap-3 flex-wrap pt-1">
                    {isLive ? (
                        <label className="inline-flex items-center gap-2 text-xs font-bold text-red-300 cursor-pointer">
                            <input type="checkbox" checked={confirmLive} onChange={e => setConfirmLive(e.target.checked)}
                                className="accent-red-500" />
                            Confermo ordine REALE (soldi veri)
                        </label>
                    ) : <span className="text-[11px] text-muted-foreground">Modalità PAPER: nessun denaro reale.</span>}

                    <Button
                        onClick={handlePlace}
                        disabled={submitting || killSwitch || (isLive && !confirmLive)}
                        className={`font-black ${
                            side === 'back'
                                ? 'bg-sky-500 hover:bg-sky-400 text-black'
                                : 'bg-rose-500 hover:bg-rose-400 text-black'
                        }`}
                    >
                        {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        {submin ? 'Place-and-trim' : `Piazza ${side === 'back' ? 'Back' : 'Lay'}`}
                    </Button>
                </div>
            </fieldset>

            {/* ---------------- lista ordini ---------------- */}
            <div className="border-t border-white/5 pt-4">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mb-2">
                    Ordini ({orders.length})
                </div>
                {listErr && <p className="text-xs text-red-400 mb-2">Errore: {listErr}</p>}
                {orders.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Nessun ordine su questo mercato.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead>
                                <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left py-1.5 pr-2">Selezione</th>
                                    <th className="text-left py-1.5 px-2">Lato</th>
                                    <th className="text-right py-1.5 px-2">Prezzo</th>
                                    <th className="text-right py-1.5 px-2">Size</th>
                                    <th className="text-right py-1.5 px-2">Abbinato</th>
                                    <th className="text-left py-1.5 px-2">Stato</th>
                                    <th className="text-right py-1.5 pl-2">Azioni</th>
                                </tr>
                            </thead>
                            <tbody>
                                {orders.map(o => (
                                    <tr key={o.id} className="border-b border-white/[0.04]">
                                        <td className="py-1.5 pr-2 text-white/80 truncate max-w-[140px]">{selName(o.selection_id)}</td>
                                        <td className="py-1.5 px-2">
                                            <span className={o.side === 'back' ? 'text-sky-300' : 'text-rose-300'}>
                                                {o.side === 'back' ? 'Back' : 'Lay'}
                                            </span>
                                        </td>
                                        <td className="py-1.5 px-2 text-right font-mono text-white">{o.price ?? '—'}</td>
                                        <td className="py-1.5 px-2 text-right font-mono text-white/70">{o.size ?? '—'}</td>
                                        <td className="py-1.5 px-2 text-right font-mono text-emerald-300">
                                            {o.size_matched > 0
                                                ? `${o.size_matched}${o.average_price_matched ? ` @${o.average_price_matched}` : ''}`
                                                : '—'}
                                        </td>
                                        <td className="py-1.5 px-2">
                                            <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-bold ${statusTone(o.status)}`}>
                                                {LIVE_ORDER_STATUS_LABEL[o.status] ?? o.status}
                                            </span>
                                        </td>
                                        <td className="py-1.5 pl-2 text-right whitespace-nowrap">
                                            {o.status === 'EXECUTABLE' && !readOnly && (
                                                <>
                                                    <button onClick={() => handleReplace(o)} disabled={submitting}
                                                        className="text-amber-300/80 hover:text-amber-300 p-1" title="Replace (nuovo prezzo)">
                                                        <Pencil className="w-3.5 h-3.5" />
                                                    </button>
                                                    <button onClick={() => handleCancel(o)} disabled={submitting}
                                                        className="text-red-400/80 hover:text-red-400 p-1" title="Cancel">
                                                        <X className="w-4 h-4" />
                                                    </button>
                                                </>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* ---------------- posizioni / P&L ---------------- */}
            <div className="border-t border-white/5 pt-4">
                <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                        Posizioni / P&amp;L ({positions.length})
                    </span>
                    {pollMs > 0 && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400/80" title={`Aggiornamento automatico ogni ${(pollMs / 1000).toFixed(0)}s`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> LIVE
                        </span>
                    )}
                </div>
                {positions.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Nessuna esposizione su questo mercato.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead>
                                <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left py-1.5 pr-2">Selezione</th>
                                    <th className="text-right py-1.5 px-2">Se vince</th>
                                    <th className="text-right py-1.5 px-2">Se perde</th>
                                    <th className="text-right py-1.5 px-2">Worst win</th>
                                    <th className="text-right py-1.5 px-2">Worst lose</th>
                                    <th className="text-right py-1.5 px-2">Esposizione</th>
                                    <th className="text-right py-1.5 pl-2">Netto</th>
                                </tr>
                            </thead>
                            <tbody>
                                {positions.map(p => (
                                    <tr key={p.id} className="border-b border-white/[0.04]">
                                        <td className="py-1.5 pr-2 text-white/80 truncate max-w-[140px]">{selName(p.selection_id)}</td>
                                        <td className={`py-1.5 px-2 text-right font-mono ${p.matched_if_win >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{money(p.matched_if_win)}</td>
                                        <td className={`py-1.5 px-2 text-right font-mono ${p.matched_if_lose >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{money(p.matched_if_lose)}</td>
                                        <td className="py-1.5 px-2 text-right font-mono text-white/60">{money(p.worst_if_win)}</td>
                                        <td className="py-1.5 px-2 text-right font-mono text-white/60">{money(p.worst_if_lose)}</td>
                                        <td className="py-1.5 px-2 text-right font-mono text-amber-300">{money(p.selection_exposure)}</td>
                                        <td className="py-1.5 pl-2 text-right font-mono text-white/70">{p.net_position}</td>
                                    </tr>
                                ))}
                            </tbody>
                            {pnlTotals && (
                                <tfoot>
                                    <tr className="border-t border-white/10 bg-white/[0.03]">
                                        <td className="py-2 pr-2 text-[10px] uppercase tracking-widest text-white/70 font-bold">
                                            Totale mercato
                                        </td>
                                        <td colSpan={4} className="py-2 px-2 text-right">
                                            <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-2">P&amp;L mercato</span>
                                            <span className={`font-mono font-bold ${pnlTotals.worst >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                                                {money(pnlTotals.worst)}
                                            </span>
                                            <span className="text-white/40 mx-1">/</span>
                                            <span className={`font-mono font-bold ${pnlTotals.best >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                                                {money(pnlTotals.best)}
                                            </span>
                                            <span className="text-white/30 text-[10px] ml-1">worst / best</span>
                                        </td>
                                        <td className="py-2 px-2 text-right font-mono font-bold text-amber-300">{money(pnlTotals.exposure)}</td>
                                        <td className="py-2 pl-2 text-right font-mono font-bold text-white/80">{pnlTotals.net.toFixed(2)}</td>
                                    </tr>
                                </tfoot>
                            )}
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

export default LiveTradingPanel;
