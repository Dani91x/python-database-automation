// ============================================================================
// TerminalPositionsRail — colonna SINISTRA del trading terminal (stile Bet Angel /
// Fairbot "My Bets"): POSIZIONI/P&L per selezione del mercato attivo + ORDER BOOK
// personale (unmatched con cancel one-click, matched).
//
// SOLA PRESENTAZIONE + cancel: legge lo specchio DB (fetchLiveOrders/fetchLivePositions,
// stesse RPC dell'overlay del ladder) con poll gentile; il cancel passa dalla stessa
// coda mediata di tutto il resto (sendLiveOrderCommand). Nessuna matematica locale:
// i numeri di P&L/esposizione arrivano dal blotter flumine via specchio.
//
// MONEY-CRITICAL:
//  * ogni riga mostra la MODALITÀ dei dati (filtrati sul mode corrente del runner);
//  * se il poll fallisce, lo si DICE (banner rosso + timestamp ultimo dato buono):
//    mai numeri stantii spacciati per freschi (fix M3);
//  * cancel in LIVE chiede conferma; guardia anti-doppio-invio per bet_id.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, X, Wallet, ListOrdered } from 'lucide-react';
import {
    fetchLiveOrders, fetchLivePositions, sendLiveOrderCommand,
    type LiveOrderMode, type LiveOrderRow, type LivePositionRow,
} from '@/lib/liveOrders';

type PanelMode = 'off' | LiveOrderMode;

const POLL_MS = 4000;

const money = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
const tone = (v: number) => (v > 0.004 ? 'text-emerald-300' : v < -0.004 ? 'text-rose-300' : 'text-white/60');

interface Props {
    marketId: string;
    mode: PanelMode;
    /** id → nome selezione (dal tabellone live_now) per etichette leggibili. */
    selections: { selection_id: number; name: string }[];
}

export function TerminalPositionsRail({ marketId, mode, selections }: Props) {
    const [orders, setOrders] = useState<LiveOrderRow[]>([]);
    const [positions, setPositions] = useState<LivePositionRow[]>([]);
    const [lastGoodAt, setLastGoodAt] = useState<number | null>(null);
    const [pollErr, setPollErr] = useState<string | null>(null);
    const [cancelling, setCancelling] = useState<string | null>(null); // bet_id in volo
    const [cancelErr, setCancelErr] = useState<string | null>(null);   // fix audit #13: mai muto
    const cancellingRef = useRef<string | null>(null);

    const nameOf = useMemo(() => {
        const m = new Map(selections.map(s => [s.selection_id, s.name]));
        return (id: number) => m.get(id) ?? String(id);
    }, [selections]);

    // ---- poll specchio (orders + positions), stato di freschezza esplicito ----
    useEffect(() => {
        if (!marketId) return;
        let alive = true;
        let inFlight = false;
        const load = async () => {
            if (inFlight) return;
            inFlight = true;
            try {
                const [o, p] = await Promise.all([fetchLiveOrders(marketId), fetchLivePositions(marketId)]);
                if (!alive) return;
                setOrders(mode === 'off' ? [] : o.filter(r => r.mode === mode));
                setPositions(mode === 'off' ? [] : p.filter(r => r.mode === mode));
                setLastGoodAt(Date.now());
                setPollErr(null);
            } catch (e: any) {
                if (alive) setPollErr(e?.message ?? 'poll fallito');
            } finally {
                inFlight = false;
            }
        };
        load();
        const t = setInterval(load, POLL_MS);
        return () => { alive = false; clearInterval(t); };
    }, [marketId, mode]);

    // ---- cancel one-click (mediato dalla coda, mode-aware) ----
    const cancelOrder = useCallback(async (o: LiveOrderRow) => {
        if (!o.bet_id || mode === 'off') return;
        if (cancellingRef.current) return; // anti-doppio-invio
        if (mode === 'live' && !window.confirm(
            `Annullare l'ordine REALE ${o.side.toUpperCase()} ${o.size ?? ''}@${o.price ?? ''} su "${nameOf(o.selection_id)}"?`,
        )) return;
        cancellingRef.current = o.bet_id;
        setCancelling(o.bet_id);
        setCancelErr(null);
        try {
            const res = await sendLiveOrderCommand({
                action: 'cancel', mode: mode as LiveOrderMode,
                market_id: o.market_id, bet_id: o.bet_id,
            });
            // esito negativo esplicito dal worker: dillo subito, non solo allo specchio.
            if (!res.ok) setCancelErr(res.error ?? 'cancel rifiutato');
        } catch (e: any) {
            // fix audit #13: MAI inghiottire l'errore — l'ordine potrebbe essere ANCORA
            // vivo sul book. Banner esplicito (lo specchio confermerà al prossimo poll).
            setCancelErr(e?.message ?? 'annullamento non riuscito');
        }
        finally {
            cancellingRef.current = null;
            setCancelling(null);
        }
    }, [mode, nameOf]);

    // posizioni con esposizione o P&L ≠ 0 (le piatte a 0 non fanno rumore).
    const activePositions = useMemo(
        () => positions.filter(p =>
            Math.abs(p.matched_if_win) > 0.004 || Math.abs(p.matched_if_lose) > 0.004
            || Math.abs(p.selection_exposure) > 0.004),
        [positions],
    );
    const unmatched = useMemo(
        () => orders.filter(o => o.size_remaining > 0.004 && !['EXECUTION_COMPLETE', 'EXPIRED', 'LAPSED', 'VIOLATION'].includes(o.status)),
        [orders],
    );
    const matched = useMemo(
        () => orders.filter(o => o.size_matched > 0.004),
        [orders],
    );
    const stale = lastGoodAt != null && Date.now() - lastGoodAt > POLL_MS * 3;

    return (
        <div className="space-y-3">
            {/* freschezza dati: MAI numeri vecchi spacciati per vivi */}
            {(pollErr || stale) && (
                <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1.5 text-[10px] font-bold text-rose-200">
                    ⚠ Dati NON aggiornati{lastGoodAt ? ` (ultimo ok ${new Date(lastGoodAt).toLocaleTimeString('it-IT')})` : ''}
                    {pollErr ? ` — ${pollErr}` : ''}
                </div>
            )}
            {/* fix audit #13: errore del cancel SEMPRE visibile (l'ordine può essere ancora vivo) */}
            {cancelErr && (
                <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1.5 text-[10px] font-bold text-rose-200">
                    ⚠ Annullamento NON riuscito: {cancelErr} — verifica gli ordini (potrebbe essere ancora sul book).
                </div>
            )}

            {/* ---------------- POSIZIONI / P&L ---------------- */}
            <div className="rounded-xl border border-white/10 bg-black/40 overflow-hidden">
                <div className="px-3 py-2 border-b border-white/5 flex items-center gap-1.5">
                    <Wallet className="w-3.5 h-3.5 text-amber-400" />
                    <span className="text-[10px] uppercase tracking-widest font-bold text-white/80">Posizioni · P&L</span>
                </div>
                {activePositions.length === 0 ? (
                    <p className="px-3 py-2.5 text-[11px] text-muted-foreground">Nessuna posizione aperta sul mercato.</p>
                ) : (
                    <table className="w-full text-[11px]">
                        <thead>
                            <tr className="text-[9px] uppercase tracking-wider text-muted-foreground/70">
                                <th className="text-left px-3 py-1 font-bold">Selezione</th>
                                <th className="text-right px-1 py-1 font-bold" title="P&L se la selezione VINCE">Vince</th>
                                <th className="text-right px-1 py-1 font-bold" title="P&L se la selezione PERDE">Perde</th>
                                <th className="text-right px-3 py-1 font-bold" title="Esposizione worst-case">Esp.</th>
                            </tr>
                        </thead>
                        <tbody>
                            {activePositions.map(p => (
                                <tr key={`${p.selection_id}:${p.handicap}`} className="border-t border-white/5">
                                    <td className="px-3 py-1.5 text-white/85 truncate max-w-[110px]" title={nameOf(p.selection_id)}>
                                        {nameOf(p.selection_id)}
                                    </td>
                                    <td className={`px-1 py-1.5 text-right font-mono tabular-nums ${tone(p.matched_if_win)}`}>
                                        {money(p.matched_if_win)}
                                    </td>
                                    <td className={`px-1 py-1.5 text-right font-mono tabular-nums ${tone(p.matched_if_lose)}`}>
                                        {money(p.matched_if_lose)}
                                    </td>
                                    <td className="px-3 py-1.5 text-right font-mono tabular-nums text-white/70">
                                        {p.selection_exposure.toFixed(2)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* ---------------- ORDINI (unmatched + matched) ---------------- */}
            <div className="rounded-xl border border-white/10 bg-black/40 overflow-hidden">
                <div className="px-3 py-2 border-b border-white/5 flex items-center gap-1.5">
                    <ListOrdered className="w-3.5 h-3.5 text-amber-400" />
                    <span className="text-[10px] uppercase tracking-widest font-bold text-white/80">
                        Ordini <span className="text-muted-foreground/70 normal-case font-medium">({unmatched.length} attivi)</span>
                    </span>
                </div>

                {unmatched.length === 0 && matched.length === 0 ? (
                    <p className="px-3 py-2.5 text-[11px] text-muted-foreground">Nessun ordine sul mercato.</p>
                ) : (
                    <div className="divide-y divide-white/5">
                        {unmatched.map(o => (
                            <div key={o.id} className="px-3 py-1.5 flex items-center gap-2 text-[11px]">
                                <span className={`px-1.5 py-0.5 rounded font-black text-[9px] ${
                                    o.side === 'back' ? 'bg-sky-500/20 text-sky-300' : 'bg-rose-500/20 text-rose-300'
                                }`}>
                                    {o.side.toUpperCase()}
                                </span>
                                <span className="flex-1 truncate text-white/85" title={nameOf(o.selection_id)}>
                                    {nameOf(o.selection_id)}
                                </span>
                                <span className="font-mono tabular-nums text-white/80">
                                    {(o.size_remaining ?? 0).toFixed(2)}@{o.price ?? '—'}
                                </span>
                                <button
                                    type="button"
                                    onClick={() => cancelOrder(o)}
                                    disabled={mode === 'off' || cancelling === o.bet_id || !o.bet_id}
                                    title="Annulla l'ordine (via coda comandi)"
                                    aria-label={`Annulla ordine ${o.side} su ${nameOf(o.selection_id)}`}
                                    className="p-0.5 rounded text-rose-300 hover:bg-rose-500/20 disabled:opacity-30"
                                >
                                    {cancelling === o.bet_id
                                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                        : <X className="w-3.5 h-3.5" />}
                                </button>
                            </div>
                        ))}
                        {matched.map(o => (
                            <div key={`m${o.id}`} className="px-3 py-1.5 flex items-center gap-2 text-[11px] opacity-75">
                                <span className={`px-1.5 py-0.5 rounded font-black text-[9px] ${
                                    o.side === 'back' ? 'bg-sky-500/10 text-sky-300/80' : 'bg-rose-500/10 text-rose-300/80'
                                }`}>
                                    {o.side.toUpperCase()}
                                </span>
                                <span className="flex-1 truncate text-white/70" title={nameOf(o.selection_id)}>
                                    {nameOf(o.selection_id)}
                                </span>
                                <span className="font-mono tabular-nums text-white/60" title="size abbinata @ prezzo medio">
                                    ✓ {o.size_matched.toFixed(2)}@{o.average_price_matched || o.price || '—'}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
