// ============================================================================
// XHedgePanel — analisi CROSS-MARKET dell'evento (x-hedge / correct-score cover).
// SOLA LETTURA: interroga get_live_xhedge(p_event_id) via fetchXhedge (polling ~5s)
// e mostra come le esposizioni correnti (tutti i mercati dell'evento) si combinano
// su OGNI possibile risultato:
//   • RIEPILOGO cross-market: P&L peggiore / medio / migliore + relativo risultato;
//   • MATRICE P&L per RISULTATO ESATTO (heatmap: verde=profitto, rosso=perdita);
//   • SUGGERIMENTO di copertura: se actionable, la gamba Correct Score che migliora
//     il caso peggiore ("BACK h-a size@quota → worst X→Y").
//
// IMPORTANTE (money-critical): questo pannello NON piazza ordini. Non disponiamo lato
// client del market_id / selection_id del mercato Correct Score, quindi il suggerimento
// è puramente INFORMATIVO: va piazzato MANUALMENTE sul mercato Correct Score. In tutte
// le modalità (incl. 'off') il pannello resta in sola lettura.
// ============================================================================
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Loader2, Grid3x3, TrendingUp, TrendingDown, Sigma, Lightbulb, Info } from 'lucide-react';
import { fetchXhedge, type XhedgeRow, type XhedgeAnalysis } from '@/lib/liveOrders';

export type XHedgePanelMode = 'off' | 'paper' | 'live';

interface Props {
    eventId: string;
    mode: XHedgePanelMode;
    pollMs?: number; // refresh analisi (default 5000)
}

const money = (v?: number | null) =>
    v == null || !Number.isFinite(v) ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;
const scoreLabel = (s?: [number, number] | null) =>
    s && Number.isFinite(s[0]) && Number.isFinite(s[1]) ? `${s[0]}-${s[1]}` : '—';

// ----------------------------- badge modalità -----------------------------
function ModeBadge({ mode }: { mode: XHedgePanelMode }) {
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

// Sceglie la riga da mostrare: preferisce quella della modalità attiva, altrimenti
// (es. 'off') la prima disponibile.
function pickRow(rows: XhedgeRow[], mode: XHedgePanelMode): XhedgeRow | null {
    if (rows.length === 0) return null;
    if (mode === 'paper' || mode === 'live') {
        const m = rows.find(r => r.mode === mode);
        if (m) return m;
    }
    return rows[0];
}

// tono heatmap in base al P&L relativizzato al massimo assoluto della griglia.
function cellTone(pnl: number, absMax: number): string {
    if (!Number.isFinite(pnl) || absMax <= 0) return 'bg-white/[0.03] text-white/50';
    const t = Math.min(1, Math.abs(pnl) / absMax); // 0..1 intensità
    if (pnl > 0) {
        if (t > 0.66) return 'bg-emerald-500/40 text-emerald-100';
        if (t > 0.33) return 'bg-emerald-500/25 text-emerald-200';
        return 'bg-emerald-500/10 text-emerald-200/90';
    }
    if (pnl < 0) {
        if (t > 0.66) return 'bg-rose-500/40 text-rose-100';
        if (t > 0.33) return 'bg-rose-500/25 text-rose-200';
        return 'bg-rose-500/10 text-rose-200/90';
    }
    return 'bg-white/[0.05] text-white/70';
}

// --------------------------- matrice risultato esatto ---------------------------
function ScorelineMatrix({ analysis }: { analysis: XhedgeAnalysis }) {
    const grid = analysis.grid ?? [];
    const model = useMemo(() => {
        if (grid.length === 0) return null;
        const homes = Array.from(new Set(grid.map(g => g[0]))).sort((a, b) => a - b);
        const aways = Array.from(new Set(grid.map(g => g[1]))).sort((a, b) => a - b);
        const byKey = new Map<string, number>();
        let absMax = 0;
        for (const [h, a, pnl] of grid) {
            byKey.set(`${h}:${a}`, pnl);
            if (Number.isFinite(pnl)) absMax = Math.max(absMax, Math.abs(pnl));
        }
        return { homes, aways, byKey, absMax };
    }, [grid]);

    if (!model) {
        return (
            <p className="text-xs text-muted-foreground">Nessun risultato in griglia.</p>
        );
    }

    return (
        <div className="overflow-x-auto">
            <table className="border-separate border-spacing-1 text-[11px]" aria-label="Matrice P&L per risultato esatto">
                <thead>
                    <tr>
                        <th className="text-[9px] uppercase tracking-wider text-muted-foreground font-bold px-1 text-left">
                            C↓ / O→
                        </th>
                        {model.aways.map(a => (
                            <th key={a} className="text-[10px] font-mono text-white/60 font-bold px-1.5 text-center">
                                {a}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {model.homes.map(h => (
                        <tr key={h}>
                            <th className="text-[10px] font-mono text-white/60 font-bold px-1 text-right">{h}</th>
                            {model.aways.map(a => {
                                const pnl = model.byKey.get(`${h}:${a}`);
                                const has = pnl != null && Number.isFinite(pnl);
                                return (
                                    <td
                                        key={a}
                                        title={`${h}-${a}: ${has ? money(pnl) : 'n/d'}`}
                                        className={`rounded-md px-1.5 py-1 text-right font-mono tabular-nums whitespace-nowrap ${
                                            has ? cellTone(pnl as number, model.absMax) : 'bg-white/[0.02] text-white/25'
                                        }`}
                                    >
                                        {has ? (pnl as number).toFixed(2) : '·'}
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export function XHedgePanel({ eventId, mode, pollMs = 5000 }: Props) {
    const [rows, setRows] = useState<XhedgeRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState<string | null>(null);
    const [loaded, setLoaded] = useState(false);

    const reload = useCallback(async () => {
        if (!eventId) return;
        setLoading(true);
        setErr(null);
        try {
            const r = await fetchXhedge(eventId);
            setRows(r);
        } catch (e: any) {
            setErr(e?.message ?? 'errore di caricamento');
        } finally {
            setLoading(false);
            setLoaded(true);
        }
    }, [eventId]);

    useEffect(() => {
        reload();
        if (pollMs <= 0) return;
        const t = setInterval(reload, pollMs);
        return () => clearInterval(t);
    }, [reload, pollMs]);

    const row = useMemo(() => pickRow(rows, mode), [rows, mode]);
    const analysis = row?.analysis ?? null;
    const summary = analysis?.summary ?? null;
    const suggestion = analysis?.suggestion ?? null;

    return (
        <div className="glass-card rounded-2xl border border-white/10 bg-black/40 p-4 md:p-5 space-y-5">
            {/* header + badge modalità */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <div className="flex items-center gap-2">
                        <Grid3x3 className="w-5 h-5 text-amber-400" />
                        <h3 className="font-display font-black text-lg text-white">X-Hedge (cross-market)</h3>
                        <ModeBadge mode={mode} />
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        Copertura sull'intero evento{' '}
                        <span className="font-mono text-white/70">{eventId}</span>
                        {analysis ? ` · ${analysis.n_positions} posizioni` : ''}
                        {row ? ` · agg. ${new Date(row.updated_at).toLocaleTimeString('it-IT')}` : ''}
                    </p>
                </div>
                {loading && <Loader2 className="w-4 h-4 animate-spin text-amber-400" />}
            </div>

            {/* nota: sola lettura / analisi */}
            <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground flex items-start gap-2">
                <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-400/80" />
                <span>
                    Solo <b>analisi</b>: questo pannello non piazza ordini. L'eventuale copertura Correct Score
                    va <b>piazzata manualmente</b> sul relativo mercato.
                </span>
            </div>

            {err && (
                <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
                    {err}
                </div>
            )}

            {/* MONEY-CRITICAL: ordini matched NON modellabili (es. "Any Other" del Correct
                Score) = esposizione reale ASSENTE dalla griglia. Senza questo avviso ogni
                cella sarebbe presentata come esatta pur essendo sbagliata di quell'importo. */}
            {(analysis?.ignored_orders ?? 0) > 0 && (
                <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200 font-bold">
                    ⚠ Matrice INCOMPLETA: {analysis?.ignored_orders} ordine/i matched non
                    modellabili (es. "Any Other" del Correct Score) sono ESCLUSI dai P&amp;L mostrati.
                    Non usare il suggerimento di copertura senza verificare quelle posizioni.
                </div>
            )}

            {!analysis && loaded && !err && (
                <p className="text-xs text-muted-foreground">Nessuna analisi x-hedge disponibile per questo evento.</p>
            )}

            {summary && (
                <>
                    {/* ---------------- RIEPILOGO cross-market ---------------- */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                                <TrendingDown className="w-3.5 h-3.5 text-rose-300" /> Peggiore
                            </div>
                            <div className={`font-display font-black text-2xl leading-none mt-1 ${summary.worst >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                {money(summary.worst)}
                            </div>
                            <div className="text-[10px] text-white/50 mt-0.5">
                                risultato <span className="font-mono text-white/70">{scoreLabel(summary.worst_scoreline)}</span>
                            </div>
                        </div>
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                                <Sigma className="w-3.5 h-3.5 text-amber-400" /> Medio
                            </div>
                            <div className={`font-display font-black text-2xl leading-none mt-1 ${summary.mean >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                {money(summary.mean)}
                            </div>
                            <div className="text-[10px] text-white/50 mt-0.5">
                                su <span className="font-mono text-white/70">{summary.n_scorelines}</span> risultati
                            </div>
                        </div>
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                                <TrendingUp className="w-3.5 h-3.5 text-emerald-300" /> Migliore
                            </div>
                            <div className={`font-display font-black text-2xl leading-none mt-1 ${summary.best >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                {money(summary.best)}
                            </div>
                            <div className="text-[10px] text-white/50 mt-0.5">
                                risultato <span className="font-mono text-white/70">{scoreLabel(summary.best_scoreline)}</span>
                            </div>
                        </div>
                    </div>

                    {/* ---------------- MATRICE risultato esatto ---------------- */}
                    <div>
                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mb-2">
                            P&L per risultato esatto (Casa ↓ / Ospite →)
                        </div>
                        <ScorelineMatrix analysis={analysis!} />
                    </div>
                </>
            )}

            {/* ---------------- SUGGERIMENTO copertura ---------------- */}
            {suggestion && (
                <div className={`rounded-xl border p-3 md:p-4 ${
                    suggestion.actionable
                        ? 'border-amber-400/40 bg-amber-400/[0.06]'
                        : 'border-white/10 bg-white/[0.03]'
                }`}>
                    <div className="flex items-center gap-2">
                        <Lightbulb className={`w-4 h-4 ${suggestion.actionable ? 'text-amber-400' : 'text-white/40'}`} />
                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                            Suggerimento copertura
                        </div>
                    </div>
                    {suggestion.actionable ? (
                        <>
                            <div className="mt-2 text-sm font-bold text-white">
                                <span className="text-sky-300 font-black">BACK</span>{' '}
                                Correct Score{' '}
                                <span className="font-mono text-white">{scoreLabel(suggestion.scoreline)}</span>
                                {suggestion.size != null && (
                                    <>
                                        {' '}<span className="font-mono">{money(suggestion.size)}</span>
                                    </>
                                )}
                                {suggestion.odds != null && (
                                    <>
                                        {' @ '}<span className="font-mono text-amber-300">{suggestion.odds.toFixed(2)}</span>
                                    </>
                                )}
                            </div>
                            <div className="mt-1 text-[12px]">
                                <span className="text-muted-foreground">Peggiore </span>
                                <span className={`font-mono ${(summary?.worst ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                    {money(summary?.worst)}
                                </span>
                                <span className="text-muted-foreground"> → </span>
                                <span className={`font-mono font-bold ${suggestion.new_worst >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                    {money(suggestion.new_worst)}
                                </span>
                                <span className="text-muted-foreground"> · migliore </span>
                                <span className={`font-mono ${suggestion.new_best >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                    {money(suggestion.new_best)}
                                </span>
                            </div>
                            <div className="mt-2 text-[11px] font-bold text-amber-300">
                                ⚠️ Piazza manualmente sul mercato Correct Score.
                            </div>
                            {suggestion.note && (
                                <div className="mt-1 text-[10px] text-white/50">{suggestion.note}</div>
                            )}
                        </>
                    ) : (
                        <div className="mt-2 text-[12px] text-muted-foreground">
                            Nessuna copertura utile al momento.
                            {suggestion.note ? <span className="text-white/50"> {suggestion.note}</span> : null}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default XHedgePanel;
