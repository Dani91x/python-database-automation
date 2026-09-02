// ============================================================================
// /market-watch — D30: Market Watch multi-evento stile Fairbot. Una riga per
// evento seguito con badge stato, P&L MTM (eventPnl, prezzi da live_now.state),
// esposizione worst-case e cash-out EVENTO (SOLO calcio: il worker tennis non
// supporta il cash-out → capability gating, MAI promesse bugiarde).
// Regola d'oro: TENNIS E CALCIO NON CONDIVIDONO MAI DATI → due sezioni separate
// con fetcher dedicati (live_* vs tennis_*).
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { Card } from '@/components/ui/card';
import { ArrowLeft, Eye, AlertTriangle, Loader2 } from 'lucide-react';
import {
    fetchLiveFollows, fetchLiveNow, subscribeLiveNow,
    type LiveFollow, type LiveNowRow, type LiveNowState,
} from '@/lib/live';
import {
    fetchLivePositionsEvent, sendCashoutEvent,
    type LivePositionRow, type LiveOrderMode,
} from '@/lib/liveOrders';
import {
    fetchTennisFollows, fetchTennisNow, subscribeTennisNow, fetchTennisPositionsAll,
    type TennisFollow, type TennisLiveNowRow, type TennisLiveNowState,
} from '@/lib/tennis';
import { eventMtm, eventExposure } from '@/lib/eventPnl';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';

// ---------------------------------------------------------------- helper puri UI
// Mappa selection_id → best back/lay dai mercati pubblicati in *_live_now.state.
// (glue di pagina: la matematica MONEY-CRITICAL sta in lib/eventPnl, testata.)
function buildPriceMap(
    state: LiveNowState | TennisLiveNowState | null | undefined,
): Map<number, { back: number | null; lay: number | null }> {
    const m = new Map<number, { back: number | null; lay: number | null }>();
    for (const mk of state?.markets ?? []) {
        for (const s of mk.selections ?? []) {
            if (!m.has(s.selection_id)) m.set(s.selection_id, { back: s.back ?? null, lay: s.lay ?? null });
        }
    }
    return m;
}

function fmtEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}

// Countdown breve all'open_date (badge pre-match).
function countdownLabel(openDate: string): string {
    const ms = new Date(openDate).getTime() - Date.now();
    if (!Number.isFinite(ms)) return '';
    if (ms <= 0) return 'in avvio';
    const min = Math.round(ms / 60_000);
    if (min < 60) return `tra ${min}m`;
    const h = Math.floor(min / 60);
    if (h < 24) return `tra ${h}h ${min % 60}m`;
    return new Date(openDate).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// Cella P&L MTM per evento: mostra il valore SOLO se valutabile; unpriced>0 →
// ⚠ SEMPRE visibile (mai nascondere posizioni non valutabili).
function MtmCell({ positions, state }: {
    positions: LivePositionRow[] | undefined;
    state: LiveNowState | TennisLiveNowState | null | undefined;
}) {
    if (positions == null) return <span className="text-white/40" title="posizioni non ancora caricate">…</span>;
    const { mtm, priced, unpriced } = eventMtm(positions, buildPriceMap(state));
    if (priced === 0 && unpriced === 0) {
        return <span className="text-white/40" title="nessuna posizione aperta">—</span>;
    }
    return (
        <span className="inline-flex items-center gap-1">
            {priced > 0 ? (
                <span className={`tabular-nums font-semibold ${mtm >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {fmtEur(mtm)}
                </span>
            ) : (
                <span className="text-white/40">—</span>
            )}
            {unpriced > 0 && (
                <span title={`${unpriced} posizioni non valutabili (prezzo mancante)`} className="text-amber-400">
                    <AlertTriangle className="w-3.5 h-3.5 inline" />
                </span>
            )}
        </span>
    );
}

// Badge stato riga calcio: in-play (minuto+score) / SOSPESO / countdown.
function CalcioBadge({ f, now }: { f: LiveFollow; now: LiveNowRow | null | undefined }) {
    const inplay = now?.inplay ?? f.inplay;
    const suspended = (now?.state?.markets ?? []).some(m => m.status === 'SUSPENDED');
    if (inplay) {
        const minute = now?.minute ?? f.minute;
        const sh = now?.score_home ?? f.score_home;
        const sa = now?.score_away ?? f.score_away;
        return (
            <span className="inline-flex items-center gap-1">
                <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 text-[10px] font-black">
                    LIVE {minute != null ? `${minute}'` : ''}{sh != null && sa != null ? ` · ${sh}–${sa}` : ''}
                </span>
                {suspended && <span className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 text-[10px] font-black">SOSPESO</span>}
            </span>
        );
    }
    if (suspended) {
        return <span className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 text-[10px] font-black">SOSPESO</span>;
    }
    return <span className="px-1.5 py-0.5 rounded bg-white/10 text-white/60 text-[10px] font-bold">{countdownLabel(f.open_date)}</span>;
}

export default function MarketWatch() {
    // ------------------------------------------------------------- ⚽ CALCIO
    const [follows, setFollows] = useState<LiveFollow[] | null>(null);
    const [nowBy, setNowBy] = useState<Record<string, LiveNowRow | null>>({});
    const [posBy, setPosBy] = useState<Record<string, LivePositionRow[]>>({});
    const [busyEvent, setBusyEvent] = useState<string | null>(null);
    const [rowMsg, setRowMsg] = useState<Record<string, string>>({});
    // guardia anti-doppio-invio (MONEY-CRITICAL: un secondo click non deve accodare
    // un secondo cash-out reale).
    const cashingRef = useRef(false);

    // lista eventi seguiti (solo PENDING/STREAMING) + refetch di backup ogni 30s.
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchLiveFollows()
                .then(rows => { if (alive) setFollows(rows.filter(f => f.status === 'PENDING' || f.status === 'STREAMING')); })
                .catch(e => { console.warn('[MarketWatch] follows:', e); if (alive) setFollows(prev => prev ?? []); });
        };
        load();
        const t = setInterval(load, 30_000);
        return () => { alive = false; clearInterval(t); };
    }, []);

    const eventIds = useMemo(() => (follows ?? []).map(f => f.event_id), [follows]);
    const idsKey = eventIds.join(',');

    // snapshot live_now + sottoscrizione realtime per OGNI evento (cleanup rigoroso).
    useEffect(() => {
        const ids = idsKey ? idsKey.split(',') : [];
        if (!ids.length) return;
        let alive = true;
        const unsubs: Array<() => void> = [];
        for (const id of ids) {
            fetchLiveNow(id)
                .then(row => { if (alive) setNowBy(p => ({ ...p, [id]: row })); })
                .catch(e => console.warn('[MarketWatch] liveNow:', e));
            unsubs.push(subscribeLiveNow(id, row => { if (alive && row) setNowBy(p => ({ ...p, [id]: row })); }));
        }
        return () => { alive = false; unsubs.forEach(u => u()); };
    }, [idsKey]);

    // posizioni per evento: polling ogni 10s (nessuna tabella realtime dedicata).
    useEffect(() => {
        const ids = idsKey ? idsKey.split(',') : [];
        if (!ids.length) return;
        let alive = true;
        const load = () => {
            for (const id of ids) {
                fetchLivePositionsEvent(id)
                    .then(rows => { if (alive) setPosBy(p => ({ ...p, [id]: rows })); })
                    .catch(e => console.warn('[MarketWatch] positions:', e));
            }
        };
        load();
        const t = setInterval(load, 10_000);
        return () => { alive = false; clearInterval(t); };
    }, [idsKey]);

    // modalità ordini: dall'order_mode del PRIMO evento attivo che la pubblica
    // (fail-safe 'off': senza runner NIENTE bottoni attivi).
    const mode: LiveOrderMode | 'off' = useMemo(() => {
        for (const id of eventIds) {
            const m = nowBy[id]?.state?.order_mode;
            if (m) {
                const low = m.toLowerCase();
                return low === 'paper' || low === 'live' ? low : 'off';
            }
        }
        return 'off';
    }, [eventIds, nowBy]);

    // Cash-out EVENTO (solo calcio): conferma SEMPRE, doppia conferma in LIVE.
    const onCashout = useCallback(async (f: LiveFollow) => {
        if (mode === 'off' || cashingRef.current) return;
        const marketId = nowBy[f.event_id]?.state?.markets?.[0]?.market_id;
        if (!marketId) return;
        const label = `${f.home_name} — ${f.away_name}`;
        if (!window.confirm(`Cash-out EVENTO su "${label}" (${mode.toUpperCase()}): appiattisce TUTTI i mercati dell'evento. Confermi?`)) return;
        if (mode === 'live' && !window.confirm(`⚠️ MODALITÀ LIVE — SOLDI VERI. Confermi il cash-out TOTALE dell'evento "${label}"?`)) return;
        cashingRef.current = true;
        setBusyEvent(f.event_id);
        try {
            const res = await sendCashoutEvent({ marketId, mode });
            setRowMsg(p => ({ ...p, [f.event_id]: res.ok ? 'Cash-out accodato ✓' : `Errore: ${res.error ?? 'comando non eseguito'}` }));
        } catch (e) {
            setRowMsg(p => ({ ...p, [f.event_id]: `Errore: ${e instanceof Error ? e.message : String(e)}` }));
        } finally {
            cashingRef.current = false;
            setBusyEvent(null);
        }
    }, [mode, nowBy]);

    // ------------------------------------------------------------- 🎾 TENNIS
    const [tFollows, setTFollows] = useState<TennisFollow[] | null>(null);
    const [tNowBy, setTNowBy] = useState<Record<string, TennisLiveNowRow | null>>({});
    const [tPositions, setTPositions] = useState<LivePositionRow[] | null>(null);

    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchTennisFollows()
                .then(rows => { if (alive) setTFollows(rows.filter(f => f.status === 'PENDING' || f.status === 'STREAMING')); })
                .catch(e => { console.warn('[MarketWatch] tennis follows:', e); if (alive) setTFollows(prev => prev ?? []); });
        };
        load();
        const t = setInterval(load, 30_000);
        return () => { alive = false; clearInterval(t); };
    }, []);

    const tIdsKey = useMemo(() => (tFollows ?? []).map(f => f.event_id).join(','), [tFollows]);

    useEffect(() => {
        const ids = tIdsKey ? tIdsKey.split(',') : [];
        if (!ids.length) return;
        let alive = true;
        const unsubs: Array<() => void> = [];
        for (const id of ids) {
            fetchTennisNow(id)
                .then(row => { if (alive) setTNowBy(p => ({ ...p, [id]: row })); })
                .catch(e => console.warn('[MarketWatch] tennisNow:', e));
            unsubs.push(subscribeTennisNow(id, row => { if (alive && row) setTNowBy(p => ({ ...p, [id]: row })); }));
        }
        return () => { alive = false; unsubs.forEach(u => u()); };
    }, [tIdsKey]);

    // posizioni tennis: TUTTE in una chiamata (get_tennis_live_positions_all), poll 10s.
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchTennisPositionsAll()
                .then(rows => { if (alive) setTPositions(rows); })
                .catch(e => console.warn('[MarketWatch] tennis positions:', e));
        };
        load();
        const t = setInterval(load, 10_000);
        return () => { alive = false; clearInterval(t); };
    }, []);

    const tPosBy = useMemo(() => {
        const m: Record<string, LivePositionRow[]> = {};
        for (const p of tPositions ?? []) {
            if (!p.event_id) continue;
            (m[p.event_id] ??= []).push(p);
        }
        return m;
    }, [tPositions]);

    // ------------------------------------------------------------------ render
    return (
        <div className="min-h-screen bg-background text-foreground">
            <Helmet><title>Market Watch | Alpha Score</title></Helmet>

            {/* top bar minimale */}
            <div className="sticky top-0 z-40 px-3 py-2 border-b border-white/10 bg-black/80 backdrop-blur flex items-center gap-2">
                <Link to="/segui-live" className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-white">
                    <ArrowLeft className="w-3.5 h-3.5" /> Terminal
                </Link>
                <span className="inline-flex items-center gap-1.5 font-heading font-bold text-sm text-white">
                    <Eye className="w-4 h-4 text-amber-400" /> Market Watch
                </span>
                <div className="flex-1" />
                <span className="text-[10px] text-muted-foreground">
                    modalità ordini: <span className={`font-black ${mode === 'live' ? 'text-red-400' : mode === 'paper' ? 'text-sky-300' : 'text-white/50'}`}>{mode.toUpperCase()}</span>
                </span>
            </div>

            <div className="p-3 space-y-4 max-w-[1400px] mx-auto">
                {/* ------------------------------------------------ sezione CALCIO */}
                <section className="space-y-2">
                    <h2 className="text-sm font-heading font-bold text-white">⚽ Calcio</h2>
                    {follows == null ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                            <Loader2 className="w-4 h-4 animate-spin" /> Carico gli eventi seguiti…
                        </div>
                    ) : follows.length === 0 ? (
                        <div className="text-sm text-muted-foreground py-2">Nessun evento calcio seguito.</div>
                    ) : follows.map(f => {
                        const now = nowBy[f.event_id];
                        const positions = posBy[f.event_id];
                        const firstMarketId = now?.state?.markets?.[0]?.market_id;
                        const cashDisabled = mode === 'off' || !firstMarketId || busyEvent != null;
                        return (
                            <Card key={f.event_id} className="glass-card border-white/10 px-3 py-2 flex items-center gap-3 flex-wrap">
                                <div className="min-w-[220px] flex-1">
                                    <div className="text-[12px] font-bold text-white truncate">{f.home_name} – {f.away_name}</div>
                                    <div className="text-[10px] text-muted-foreground truncate">{f.league_name ?? '—'}</div>
                                </div>
                                <CalcioBadge f={f} now={now} />
                                <div className="text-[11px] w-28 text-right" title="P&L MTM se si greenasse ORA ai prezzi correnti">
                                    <span className="text-slate-400 mr-1">MTM</span>
                                    <MtmCell positions={positions} state={now?.state} />
                                </div>
                                <div className="text-[11px] w-32 text-right tabular-nums" title="Esposizione worst-case aggregata (Σ selection_exposure)">
                                    <span className="text-slate-400 mr-1">Rischio</span>
                                    <span className="text-white/85">€{eventExposure(positions ?? []).toFixed(2)}</span>
                                </div>
                                <button
                                    type="button"
                                    disabled={cashDisabled}
                                    onClick={() => onCashout(f)}
                                    title={mode === 'off'
                                        ? 'Modalità ordini OFF: nessun comando possibile'
                                        : !firstMarketId
                                            ? 'Nessun mercato pubblicato per l\'evento'
                                            : `Cash-out di TUTTI i mercati dell'evento (${mode.toUpperCase()})`}
                                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-amber-400/40 bg-amber-400/10 text-[11px] font-bold text-amber-200 hover:bg-amber-400/25 disabled:opacity-40"
                                >
                                    {busyEvent === f.event_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                                    Cash-out EVENTO
                                </button>
                                <Link to="/segui-live" className="text-[11px] text-sky-300 hover:underline whitespace-nowrap">
                                    Apri terminal
                                </Link>
                                {/* video live + statistiche Betfair (sessione web utente) */}
                                <BetfairMediaButtons compact eventId={f.event_id} />
                                {rowMsg[f.event_id] && (
                                    <div className={`w-full text-[10px] ${rowMsg[f.event_id].startsWith('Errore') ? 'text-red-400' : 'text-emerald-400'}`}>
                                        {rowMsg[f.event_id]}
                                    </div>
                                )}
                            </Card>
                        );
                    })}
                </section>

                {/* ------------------------------------------------ sezione TENNIS */}
                <section className="space-y-2">
                    <h2 className="text-sm font-heading font-bold text-white">🎾 Tennis</h2>
                    {tFollows == null ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                            <Loader2 className="w-4 h-4 animate-spin" /> Carico i match tennis seguiti…
                        </div>
                    ) : tFollows.length === 0 ? (
                        <div className="text-sm text-muted-foreground py-2">Nessun match tennis seguito.</div>
                    ) : tFollows.map(f => {
                        const now = tNowBy[f.event_id];
                        const score = now?.score ?? f.score;
                        const inplay = now?.inplay ?? f.inplay;
                        const markets = now?.state?.markets ?? [];
                        const mo = markets.find(m => m.market_type === 'MATCH_ODDS') ?? markets[0];
                        const terminalHref = mo
                            ? `/tennis/terminal?${new URLSearchParams({
                                event: f.event_id,
                                market: mo.market_id,
                                name: mo.market_name || mo.market_type,
                                p1: f.player1_name,
                                p2: f.player2_name,
                            }).toString()}`
                            : null;
                        return (
                            <Card key={f.event_id} className="glass-card border-white/10 px-3 py-2 flex items-center gap-3 flex-wrap">
                                <div className="min-w-[220px] flex-1">
                                    <div className="text-[12px] font-bold text-white truncate">{f.player1_name} vs {f.player2_name}</div>
                                    <div className="text-[10px] text-muted-foreground truncate">{f.competition_name ?? '—'}</div>
                                </div>
                                {inplay ? (
                                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 text-[10px] font-black">
                                        LIVE{score?.set_summary ? ` · ${score.set_summary}` : ''}
                                    </span>
                                ) : (
                                    <span className="px-1.5 py-0.5 rounded bg-white/10 text-white/60 text-[10px] font-bold">{countdownLabel(f.open_date)}</span>
                                )}
                                <div className="text-[11px] w-28 text-right" title="P&L MTM se si greenasse ORA ai prezzi correnti">
                                    <span className="text-slate-400 mr-1">MTM</span>
                                    <MtmCell positions={tPositions == null ? undefined : (tPosBy[f.event_id] ?? [])} state={now?.state} />
                                </div>
                                <div className="text-[11px] w-32 text-right tabular-nums" title="Esposizione worst-case aggregata (Σ selection_exposure)">
                                    <span className="text-slate-400 mr-1">Rischio</span>
                                    <span className="text-white/85">€{eventExposure(tPosBy[f.event_id] ?? []).toFixed(2)}</span>
                                </div>
                                {/* CAPABILITY GATING: il worker tennis NON supporta il cash-out →
                                    nessun bottone, mai promesse bugiarde. */}
                                <span
                                    className="px-2.5 py-1 text-[11px] text-white/40 select-none"
                                    title="Cash-out non disponibile: il worker tennis non supporta il cash-out"
                                >
                                    —
                                </span>
                                {terminalHref ? (
                                    <Link to={terminalHref} className="text-[11px] text-sky-300 hover:underline whitespace-nowrap">
                                        Apri terminal tennis
                                    </Link>
                                ) : (
                                    <span className="text-[11px] text-white/40 whitespace-nowrap" title="Nessun mercato pubblicato per il match">
                                        terminal n/d
                                    </span>
                                )}
                                {/* video live + statistiche Betfair (sessione web utente) */}
                                <BetfairMediaButtons compact eventId={f.event_id} />
                            </Card>
                        );
                    })}
                </section>
            </div>
        </div>
    );
}
