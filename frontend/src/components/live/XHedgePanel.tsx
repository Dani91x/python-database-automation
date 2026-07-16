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
// F39 (money-critical): il piazzamento 1-CLICK della copertura è disponibile SOLO se
// il worker ha scritto nel suggerimento gli ID ESATTI (market_id + selection_id del
// Correct Score, presi dal CATALOGO — mai risolti per nome lato client). Guardie:
// analisi fresca (≤30s), matrice COMPLETA (ignored_orders=0), odds/size validi,
// conferma esplicita one-shot in LIVE, FoK software 10s sul place (una copertura che
// non si abbina subito NON deve restare sul book a un prezzo vecchio). Senza gli ID
// il suggerimento resta informativo: piazzamento manuale.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, Grid3x3, TrendingUp, TrendingDown, Sigma, Lightbulb, Info, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import {
    cancelRiskRule, fetchRiskRules, fetchXhedge, requestRiskRule, sendLiveOrderCommand,
    shouldResetLiveConfirm,
    type RiskRuleRow, type XhedgeRow, type XhedgeAnalysis,
} from '@/lib/liveOrders';

// Analisi più vecchia di così = suggerimento STANTIO: 1-click disabilitato (il book
// CS si muove; il worker riscrive ogni ~5s, 30s = 6 cicli di tolleranza).
const XHEDGE_FRESH_MS = 30_000;
// Sotto il minimo stake .it (€2) il place normale verrebbe rifiutato: si usa il
// flusso place_submin (place-and-trim), che è il path progettato per questi importi.
const MIN_STAKE_IT = 2.0;

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

    // ---------------- F39: piazzamento 1-click della copertura CS ----------------
    const [confirmLive, setConfirmLive] = useState(false);
    const [placing, setPlacing] = useState(false);
    // fix audit #28: guardia SINCRONA anti-doppio-invio (`placing` è stato asincrono:
    // due click ravvicinati passerebbero entrambi). Pattern ScalperPanel.
    const coverBusyRef = useRef(false);
    const isLive = mode === 'live';
    const canTrade = mode === 'paper' || mode === 'live';
    const matrixIncomplete = (analysis?.ignored_orders ?? 0) > 0;
    const rowFresh = row != null && Number.isFinite(Date.parse(row.updated_at))
        && Date.now() - Date.parse(row.updated_at) <= XHEDGE_FRESH_MS;
    // il bottone esiste SOLO con ID esatti dal worker + numeri validi (mai indovinare)
    const coverReady = !!(suggestion?.actionable
        && suggestion.market_id && suggestion.selection_id != null
        && suggestion.odds != null && suggestion.odds > 1.01
        && suggestion.size != null && suggestion.size >= 0.01);

    const handleCover = useCallback(async () => {
        // Guardie MONEY-CRITICAL ri-verificate AL CLICK (non solo al render): il
        // pannello polla ogni 5s e il suggerimento può cambiare sotto il cursore.
        const s = suggestion;
        const r = row;
        if (coverBusyRef.current || placing || !canTrade || !s?.actionable) return;
        if (!s.market_id || s.selection_id == null
            || s.odds == null || !(s.odds > 1.01) || s.size == null || !(s.size >= 0.01)) return;
        if (matrixIncomplete) {
            toast.error('Matrice INCOMPLETA', { description: 'Ordini matched non modellati: la copertura suggerita non è affidabile.' });
            return;
        }
        if (!r || !Number.isFinite(Date.parse(r.updated_at))
            || Date.now() - Date.parse(r.updated_at) > XHEDGE_FRESH_MS) {
            toast.error('Suggerimento stantio', { description: 'Attendi il refresh dell\'analisi (~5s) e riprova.' });
            return;
        }
        if (isLive && !confirmLive) {
            // fix audit #20: mai un return MUTO su un click money-critical.
            toast.error('Conferma REALE richiesta', { description: 'Spunta "Confermo la copertura con DENARO REALE" prima di piazzare.' });
            return;
        }
        coverBusyRef.current = true;
        setPlacing(true);
        try {
            const size = Math.round(s.size * 100) / 100;
            const submin = size < MIN_STAKE_IT;
            const res = await sendLiveOrderCommand({
                action: submin ? 'place_submin' : 'place',
                mode: mode as 'paper' | 'live',
                market_id: s.market_id,
                selection_id: s.selection_id,
                handicap: 0,
                side: 'back',
                order_type: 'LIMIT',
                price: s.odds,
                size,
                persistence: 'LAPSE',
                // FoK software 10s (C22): una copertura non abbinata subito NON deve
                // restare sul book a un prezzo vecchio. Non sul submin (ha la sua
                // macchina a stati place-and-trim).
                ...(submin ? {} : { params: { fok_ttl_sec: 10 } }),
            });
            if (res.ok) {
                const matched = res.size_matched ?? null;
                toast.success('Copertura inviata', {
                    description: `BACK CS ${scoreLabel(s.scoreline)} €${size.toFixed(2)} @ ${s.odds.toFixed(2)}`
                        + (matched != null ? ` · abbinato €${Number(matched).toFixed(2)}` : '')
                        + (submin ? ' · flusso sotto-minimo (place-and-trim)' : ' · FoK 10s se non abbinato')
                        + ' — verifica il blotter: la matrice si aggiorna in ~5s.',
                });
            } else {
                toast.error('Copertura RIFIUTATA', { description: res.error ?? res.detail ?? 'motivo non noto' });
            }
            // fix audit #20: contratto ONESTO di shouldResetLiveConfirm — reset SOLO su
            // successo; su rifiuto ESPLICITO (ordine NON piazzato) la spunta resta e
            // l'utente può ritentare senza ri-confermare.
            if (shouldResetLiveConfirm(isLive, res.ok)) setConfirmLive(false);
        } catch (e: any) {
            toast.error('Errore copertura', { description: e?.message ?? 'errore sconosciuto — NON reinviare senza verificare il blotter' });
            // esito AMBIGUO (timeout/eccezione: la copertura POTREBBE essere piazzata):
            // in LIVE la spunta si resetta — un re-click richiede nuova conferma esplicita.
            if (isLive) setConfirmLive(false);
        } finally {
            coverBusyRef.current = false;
            setPlacing(false);
            void reload();
        }
    }, [suggestion, row, placing, canTrade, matrixIncomplete, isLive, confirmLive, mode, reload]);

    // ---------------- F39: regola AUTO-HEDGE armabile (floor-keeper) ----------------
    const csMarketId = analysis?.cs_market_id ?? null;
    const [ahRules, setAhRules] = useState<RiskRuleRow[]>([]);
    const [floorInput, setFloorInput] = useState('');
    const [maxStakeInput, setMaxStakeInput] = useState('');
    const [armBusy, setArmBusy] = useState(false);
    const [confirmArmLive, setConfirmArmLive] = useState(false);
    const reloadAhRules = useCallback(async () => {
        if (!csMarketId || !canTrade) { setAhRules([]); return; }
        try {
            const rules = await fetchRiskRules(csMarketId);
            setAhRules(rules.filter(r => r.rule_type === 'auto_hedge' && r.mode === mode
                && (r.status === 'armed' || r.status === 'error')));
        } catch { /* best-effort: pannello informativo, riprova al prossimo poll */ }
    }, [csMarketId, canTrade, mode]);
    useEffect(() => {
        void reloadAhRules();
        if (pollMs <= 0) return;
        const t = setInterval(() => { void reloadAhRules(); }, pollMs);
        return () => clearInterval(t);
    }, [reloadAhRules, pollMs]);
    const armedAh = ahRules.find(r => r.status === 'armed') ?? null;
    const errorAh = ahRules.find(r => r.status === 'error') ?? null;

    const handleArmAutoHedge = useCallback(async () => {
        if (armBusy || !canTrade || !csMarketId || armedAh) return;
        const floor = Number(floorInput);
        if (!(Number.isFinite(floor) && floor > 0)) {
            toast.error('Floor non valido', { description: 'Inserisci la perdita worst-case massima tollerata (€ > 0).' });
            return;
        }
        const maxStake = maxStakeInput === '' ? null : Number(maxStakeInput);
        if (maxStake != null && !(Number.isFinite(maxStake) && maxStake > 0)) {
            toast.error('Max stake non valido', { description: 'Lascia vuoto (nessun cap) o inserisci un importo > 0.' });
            return;
        }
        if (isLive && !confirmArmLive) {
            // fix audit #20: mai un return MUTO su un arming money-critical.
            toast.error('Conferma REALE richiesta', { description: 'Spunta la conferma prima di armare l\'auto-hedge in LIVE.' });
            return;
        }
        setArmBusy(true);
        try {
            await requestRiskRule({
                mode: mode as 'paper' | 'live',
                ruleType: 'auto_hedge',
                marketId: csMarketId,
                selectionId: 0,       // la selezione CS varia per copertura (worst scoreline)
                entrySide: 'back',
                params: {
                    floor, event_id: eventId,
                    ...(maxStake != null ? { max_stake: maxStake } : {}),
                },
            });
            toast.success('Auto-hedge ARMATO', {
                description: `Mantiene il worst-case scoreline ≥ −€${floor.toFixed(2)} (max 3 coperture, cooldown 60s). Richiede runner attivo + migrazione risk_rules_v4.`,
            });
            // fix audit #20: reset one-shot SOLO su successo (contratto onesto).
            if (shouldResetLiveConfirm(isLive, true)) setConfirmArmLive(false);
        } catch (e: any) {
            toast.error('Auto-hedge NON armato', { description: e?.message ?? 'errore sconosciuto' });
            // esito AMBIGUO (requestRiskRule conia un client_ref nuovo a ogni chiamata:
            // un re-click armerebbe una regola DUPLICATA) → in LIVE serve nuova spunta.
            if (isLive) setConfirmArmLive(false);
        } finally {
            setArmBusy(false);
            void reloadAhRules();
        }
    }, [armBusy, canTrade, csMarketId, armedAh, floorInput, maxStakeInput, isLive, confirmArmLive, mode, eventId, reloadAhRules]);

    const handleDisarmAutoHedge = useCallback(async (id: number) => {
        if (armBusy) return;
        setArmBusy(true);
        try {
            await cancelRiskRule(id);
            toast.success('Auto-hedge disarmato');
        } catch (e: any) {
            toast.error('Disarmo fallito', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setArmBusy(false);
            void reloadAhRules();
        }
    }, [armBusy, reloadAhRules]);

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

            {/* nota: analisi + 1-click F39 */}
            <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground flex items-start gap-2">
                <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-400/80" />
                <span>
                    Analisi cross-market + copertura <b>1-click</b> (F39): il bottone "Copri" appare solo
                    con gli ID esatti della gamba Correct Score dal runner, analisi fresca e matrice
                    completa. In LIVE serve la conferma esplicita; FoK 10s se non si abbina.
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
                            {/* F39: 1-click SOLO con gli ID esatti dal worker; altrimenti manuale. */}
                            {coverReady && canTrade ? (
                                <div className="mt-2.5 space-y-2">
                                    {isLive && (
                                        <label className="flex items-center gap-2 text-[11px] text-red-200 font-bold cursor-pointer select-none">
                                            <input
                                                type="checkbox"
                                                checked={confirmLive}
                                                onChange={e => setConfirmLive(e.target.checked)}
                                                className="accent-red-500"
                                            />
                                            Confermo la copertura con DENARO REALE (one-shot)
                                        </label>
                                    )}
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <Button
                                            size="sm"
                                            onClick={handleCover}
                                            disabled={placing || !rowFresh || matrixIncomplete || (isLive && !confirmLive)}
                                            className="h-7 bg-amber-500 hover:bg-amber-400 text-black font-black disabled:opacity-40"
                                            title={matrixIncomplete
                                                ? 'Matrice INCOMPLETA (ordini non modellati): 1-click disabilitato'
                                                : !rowFresh
                                                    ? 'Analisi stantia: attendi il refresh (~5s)'
                                                    : `BACK Correct Score ${scoreLabel(suggestion.scoreline)} €${(suggestion.size ?? 0).toFixed(2)} @ ${(suggestion.odds ?? 0).toFixed(2)} — FoK software 10s: se non si abbina viene cancellata (mai una copertura resting a prezzo vecchio).`}
                                        >
                                            {placing
                                                ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                                                : <ShieldCheck className="w-3.5 h-3.5 mr-1.5" />}
                                            Copri (1-click)
                                        </Button>
                                        {!rowFresh && (
                                            <span className="text-[10px] text-amber-300/80 font-bold">analisi stantia — refresh in corso</span>
                                        )}
                                    </div>
                                </div>
                            ) : (
                                <div className="mt-2 text-[11px] font-bold text-amber-300">
                                    ⚠️ {canTrade
                                        ? 'ID selezione CS non disponibili (riga pre-deploy o scoreline fuori catalogo): piazza manualmente sul mercato Correct Score.'
                                        : 'Modalità OFF: piazza manualmente sul mercato Correct Score.'}
                                </div>
                            )}
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

            {/* ---------------- F39: AUTO-HEDGE armabile (floor-keeper) ---------------- */}
            {canTrade && csMarketId && (
                <div className="rounded-xl border border-violet-400/30 bg-violet-400/[0.05] p-3 md:p-4 space-y-2">
                    <div className="flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-violet-300" />
                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                            Auto-hedge (mantieni il worst-case scoreline)
                        </div>
                    </div>
                    {errorAh && (
                        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-200">
                            ⚠ Regola #{errorAh.id} in ERRORE: {errorAh.error ?? 'vedi pannello Risk'}
                        </div>
                    )}
                    {armedAh ? (
                        <div className="flex items-center gap-3 flex-wrap">
                            <span className="text-[12px] font-bold text-violet-200">
                                🛡 ATTIVO: worst-case ≥ −€{Number((armedAh.params as Record<string, unknown>)?.floor ?? 0).toFixed(2)}
                                {(() => {
                                    const done = Number((armedAh.result as Record<string, unknown>)?.hedges_done ?? 0);
                                    return done > 0 ? ` · coperture ${done}/3` : '';
                                })()}
                            </span>
                            <span className="text-[10px] text-white/50"
                                title="Il risk engine (runner attivo) controlla ogni secondo il worst-case cross-market: se sfora il floor, accoda la copertura CS suggerita (mai su matrice incompleta o analisi stantia; max 3 coperture, cooldown 60s).">
                                runner attivo richiesto
                            </span>
                            <span className="flex-1" />
                            <Button size="sm" variant="outline" disabled={armBusy}
                                onClick={() => handleDisarmAutoHedge(armedAh.id)}
                                className="h-6 border-white/20 text-white/80 hover:bg-white/10 text-[11px] font-bold">
                                Disarma
                            </Button>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2 flex-wrap">
                                <label className="text-[11px] text-muted-foreground">
                                    Perdita worst-case max{' '}
                                    <input
                                        type="number" min="0.5" step="0.5" value={floorInput}
                                        onChange={e => setFloorInput(e.target.value)}
                                        placeholder="es. 20"
                                        aria-label="Floor auto-hedge (euro)"
                                        className="w-20 ml-1 px-1.5 py-0.5 rounded-md bg-black/40 border border-white/15 text-white font-mono text-[11px]"
                                    /> €
                                </label>
                                <label className="text-[11px] text-muted-foreground">
                                    Max stake/copertura{' '}
                                    <input
                                        type="number" min="0.5" step="0.5" value={maxStakeInput}
                                        onChange={e => setMaxStakeInput(e.target.value)}
                                        placeholder="nessun cap"
                                        aria-label="Max stake per copertura (euro)"
                                        className="w-20 ml-1 px-1.5 py-0.5 rounded-md bg-black/40 border border-white/15 text-white font-mono text-[11px]"
                                    /> €
                                </label>
                            </div>
                            {isLive && (
                                <label className="flex items-center gap-2 text-[11px] text-red-200 font-bold cursor-pointer select-none">
                                    <input type="checkbox" checked={confirmArmLive}
                                        onChange={e => setConfirmArmLive(e.target.checked)}
                                        className="accent-red-500" />
                                    Confermo: le coperture verranno piazzate con DENARO REALE senza ulteriore conferma
                                </label>
                            )}
                            <div className="flex items-center gap-2">
                                <Button size="sm" onClick={handleArmAutoHedge}
                                    disabled={armBusy || (isLive && !confirmArmLive)}
                                    className="h-7 bg-violet-500 hover:bg-violet-400 text-white font-black disabled:opacity-40"
                                    title="Arma il floor-keeper: quando il P&L peggiore cross-market scende sotto −floor, il risk engine piazza da solo la copertura CS suggerita (guardie: analisi fresca, matrice completa, max 3 coperture, cooldown 60s, FoK 10s). Richiede migrazione betfair_live_risk_rules_v4.sql + runner attivo.">
                                    {armBusy ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5 mr-1.5" />}
                                    Arma auto-hedge
                                </Button>
                                <span className="text-[10px] text-white/50">
                                    copre da solo via coda ordini · mai su matrice incompleta
                                </span>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default XHedgePanel;
