// ============================================================================
// /live-pnl — D33: Dashboard P&L di giornata. Fonti TRACCIABILI (specchio DB):
//   • get_live_settled (P&L REALIZZATO per mercato, scritto dal runner)
//   • betfair_live_risk_state (MTM aperto / totale / stop giornaliero, realtime)
//   • get_live_positions_all (posizioni aperte calcio)
//   • get_tennis_live_positions_all (posizioni aperte TENNIS — sezione separata)
// MONEY-CRITICAL: nessun numero ricalcolato a mano se non con matematica pura
// testata (eventExposure). Il MTM/totale di giornata esiste SOLO per OGGI
// (il worker pubblica lo stato corrente): per giorni passati si mostra "—".
// ============================================================================
import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { Card } from '@/components/ui/card';
import { ArrowLeft, Loader2, TrendingUp } from 'lucide-react';
import {
    fetchLiveSettled, fetchLiveRiskState, subscribeLiveRiskState, fetchLivePositionsAll,
    type LiveSettledRow, type LiveRiskState, type LivePositionRow,
} from '@/lib/liveOrders';
import { fetchTennisPositionsAll } from '@/lib/tennis';
import { eventExposure } from '@/lib/eventPnl';

// ---------------------------------------------------------------- helper puri UI
function fmtEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}
// YYYY-MM-DD in ORA LOCALE (input type=date).
function toLocalDay(d: Date): string {
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
// Intervallo [mezzanotte locale, +24h) del giorno scelto, in ISO UTC per la RPC.
function dayRangeIso(day: string): { fromIso: string; toIso: string } {
    const [y, m, d] = day.split('-').map(Number);
    return {
        fromIso: new Date(y, m - 1, d).toISOString(),
        toIso: new Date(y, m - 1, d + 1).toISOString(),
    };
}
function timeLabel(iso: string): string {
    return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

// KPI tile: label piccola sopra, valore grande sotto, colore per segno.
function StatTile({ label, value, tone, title, extra }: {
    label: string;
    value: string;
    tone?: 'pos' | 'neg' | 'plain';
    title?: string;
    extra?: ReactNode;
}) {
    const color = tone === 'pos' ? 'text-emerald-400' : tone === 'neg' ? 'text-red-400' : 'text-white/90';
    return (
        <Card className="glass-card border-white/10 p-3 min-w-[160px] flex-1" title={title}>
            <div className="text-[11px] text-slate-400">{label}</div>
            <div className={`text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
            {extra}
        </Card>
    );
}

// ---------------------------------------------------------------- equity curve
// Curva a GRADINI del P&L realizzato cumulato (SVG puro, nessuna libreria).
// x = ora del settlement, y = cumulato. Punto finale ambra = totale con MTM (solo oggi).
function EquityCurve({ settled, finalWithMtm }: {
    settled: LiveSettledRow[];
    /** totale di giornata (realizzato+MTM) da risk_state — SOLO se il giorno è oggi. */
    finalWithMtm: number | null;
}) {
    const [hover, setHover] = useState<{ px: number; label: string } | null>(null);
    const svgRef = useRef<SVGSVGElement | null>(null);

    const pts = useMemo(() => {
        const sorted = [...settled].sort(
            (a, b) => new Date(a.settled_at).getTime() - new Date(b.settled_at).getTime(),
        );
        let cum = 0;
        return sorted.map(s => { cum += s.profit; return { t: new Date(s.settled_at).getTime(), v: cum, iso: s.settled_at }; });
    }, [settled]);

    if (pts.length === 0) {
        return (
            <div className="text-sm text-muted-foreground py-8 text-center">
                nessun mercato regolato nella giornata
            </div>
        );
    }

    const W = 760, H = 220;
    const pad = { l: 10, r: 58, t: 16, b: 24 };
    const finalT = finalWithMtm != null ? Math.max(pts[pts.length - 1].t, Date.now()) : pts[pts.length - 1].t;
    let t0 = pts[0].t;
    let t1 = Math.max(finalT, pts[pts.length - 1].t);
    if (t1 - t0 < 60_000) { t0 -= 15 * 60_000; t1 += 15 * 60_000; } // dominio minimo 30'
    const vals = pts.map(p => p.v).concat(finalWithMtm != null ? [finalWithMtm] : []).concat([0]);
    let vMin = Math.min(...vals), vMax = Math.max(...vals);
    const span = Math.max(vMax - vMin, 0.01);
    vMin -= span * 0.08; vMax += span * 0.08;

    const x = (t: number) => pad.l + ((t - t0) / (t1 - t0)) * (W - pad.l - pad.r);
    const y = (v: number) => pad.t + ((vMax - v) / (vMax - vMin)) * (H - pad.t - pad.b);

    // path a gradini: parte da 0 al primo settlement, poi H/V per ogni punto.
    let d = `M ${x(pts[0].t)} ${y(0)}`;
    let prevV = 0;
    for (const p of pts) {
        d += ` L ${x(p.t)} ${y(prevV)} L ${x(p.t)} ${y(p.v)}`;
        prevV = p.v;
    }
    d += ` L ${x(t1)} ${y(prevV)}`;
    const lastV = pts[pts.length - 1].v;
    const color = lastV >= 0 ? '#34d399' : '#f87171';
    const area = `${d} L ${x(t1)} ${y(0)} L ${x(pts[0].t)} ${y(0)} Z`;

    const yTicks = [vMin + span * 0.08, (vMin + vMax) / 2, vMax - span * 0.08];
    const xTicks = [t0, (t0 + t1) / 2, t1];

    const onMove = (e: MouseEvent<SVGSVGElement>) => {
        const rect = svgRef.current?.getBoundingClientRect();
        if (!rect) return;
        const px = ((e.clientX - rect.left) / rect.width) * W;
        // punto più vicino sull'asse x
        let best = pts[0];
        for (const p of pts) if (Math.abs(x(p.t) - px) < Math.abs(x(best.t) - px)) best = p;
        setHover({ px: x(best.t), label: `${timeLabel(best.iso)} · ${fmtEur(best.v)}` });
    };

    return (
        <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="w-full h-auto select-none"
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
            role="img"
            aria-label="Equity curve intraday del P&L realizzato"
        >
            {/* griglia hairline + tick asse y a destra */}
            {yTicks.map((v, i) => (
                <g key={i}>
                    <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#1e293b" strokeWidth={1} />
                    <text x={W - pad.r + 6} y={y(v) + 3} fontSize={10} fill="#94a3b8" className="tabular-nums">
                        {fmtEur(v)}
                    </text>
                </g>
            ))}
            {/* linea dello zero (riferimento) */}
            <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} stroke="#334155" strokeWidth={1} strokeDasharray="3 3" />
            {/* tick asse x (ore locali) */}
            {xTicks.map((t, i) => (
                <text
                    key={i}
                    x={x(t)}
                    y={H - 6}
                    fontSize={10}
                    fill="#94a3b8"
                    textAnchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'}
                >
                    {new Date(t).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}
                </text>
            ))}
            {/* area sotto la curva (~10% opacità) + linea a gradini 2px */}
            <path d={area} fill={color} opacity={0.1} />
            <path d={d} fill="none" stroke={color} strokeWidth={2} />
            {/* punto finale ambra = totale con MTM (solo giornata corrente) */}
            {finalWithMtm != null && (
                <circle cx={x(finalT)} cy={y(finalWithMtm)} r={4} fill="#fbbf24">
                    <title>{`Totale con MTM: ${fmtEur(finalWithMtm)}`}</title>
                </circle>
            )}
            {/* crosshair + tooltip testuale */}
            {hover && (
                <g>
                    <line x1={hover.px} x2={hover.px} y1={pad.t} y2={H - pad.b} stroke="#64748b" strokeWidth={1} strokeDasharray="2 2" />
                    <text
                        x={hover.px > W / 2 ? hover.px - 6 : hover.px + 6}
                        y={pad.t + 2}
                        fontSize={11}
                        fill="#e2e8f0"
                        textAnchor={hover.px > W / 2 ? 'end' : 'start'}
                    >
                        {hover.label}
                    </text>
                </g>
            )}
        </svg>
    );
}

type ModeFilter = 'all' | 'paper' | 'live';

export default function LivePnl() {
    const [day, setDay] = useState(() => toLocalDay(new Date()));
    const [modeF, setModeF] = useState<ModeFilter>('all');
    const [settled, setSettled] = useState<LiveSettledRow[] | null>(null);
    const [risk, setRisk] = useState<LiveRiskState | null>(null);
    const [positions, setPositions] = useState<LivePositionRow[]>([]);
    const [tPositions, setTPositions] = useState<LivePositionRow[] | null>(null);

    const isToday = day === toLocalDay(new Date());

    // settled del giorno scelto (refetch al cambio giorno + backup 30s).
    useEffect(() => {
        let alive = true;
        const { fromIso, toIso } = dayRangeIso(day);
        const load = () => {
            fetchLiveSettled(fromIso, toIso)
                .then(rows => { if (alive) setSettled(rows); })
                .catch(e => { console.warn('[LivePnl] settled:', e); if (alive) setSettled(prev => prev ?? []); });
        };
        setSettled(null);
        load();
        const t = setInterval(load, 30_000);
        return () => { alive = false; clearInterval(t); };
    }, [day]);

    // stato rischio giornaliero: snapshot + realtime.
    useEffect(() => {
        let alive = true;
        fetchLiveRiskState()
            .then(row => { if (alive) setRisk(row); })
            .catch(e => console.warn('[LivePnl] risk state:', e));
        const unsub = subscribeLiveRiskState(row => { if (alive && row) setRisk(row); });
        return () => { alive = false; unsub(); };
    }, []);

    // posizioni aperte calcio (contesto del MTM) — poll 15s.
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchLivePositionsAll()
                .then(rows => { if (alive) setPositions(rows); })
                .catch(e => console.warn('[LivePnl] positions:', e));
        };
        load();
        const t = setInterval(load, 15_000);
        return () => { alive = false; clearInterval(t); };
    }, []);

    // posizioni aperte TENNIS (sezione separata, fetcher tennis_* dedicato) — poll 15s.
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchTennisPositionsAll()
                .then(rows => { if (alive) setTPositions(rows); })
                .catch(e => { console.warn('[LivePnl] tennis positions:', e); if (alive) setTPositions(prev => prev ?? []); });
        };
        load();
        const t = setInterval(load, 15_000);
        return () => { alive = false; clearInterval(t); };
    }, []);

    // filtro mode client-side (la RPC filtra solo per intervallo temporale).
    const filtered = useMemo(
        () => (settled ?? []).filter(s => modeF === 'all' || s.mode === modeF),
        [settled, modeF],
    );
    const realized = useMemo(() => filtered.reduce((acc, s) => acc + s.profit, 0), [filtered]);

    // aggregato per evento (Σ profit per event_id).
    const byEvent = useMemo(() => {
        const m = new Map<string, { profit: number; n: number }>();
        for (const s of filtered) {
            const k = s.event_id ?? '(senza evento)';
            const cur = m.get(k) ?? { profit: 0, n: 0 };
            cur.profit += s.profit;
            cur.n += 1;
            m.set(k, cur);
        }
        return [...m.entries()].sort((a, b) => b[1].profit - a[1].profit);
    }, [filtered]);

    // aggregato posizioni tennis per evento (Σ selection_exposure, Σ net_position).
    const tByEvent = useMemo(() => {
        const m = new Map<string, LivePositionRow[]>();
        for (const p of tPositions ?? []) {
            const k = p.event_id ?? '(senza evento)';
            (m.get(k) ?? m.set(k, []).get(k)!).push(p);
        }
        return [...m.entries()];
    }, [tPositions]);

    const openMtm = isToday ? risk?.open_mtm ?? null : null;
    const total = isToday ? risk?.total ?? null : null;
    // fix review MEDIUM: risk_state è un SINGLETON del mode ATTIVO sul runner — se il
    // filtro Mode selezionato è diverso, le tile di rischio vanno dichiarate come tali
    // (mai un numero che sembra filtrato ma non lo è).
    const riskMode = risk?.mode ?? null;
    const riskModeMismatch = riskMode != null && modeF !== 'all' && modeF !== riskMode;
    const riskModeNote = riskMode != null
        ? ` — runner in ${riskMode.toUpperCase()}${riskModeMismatch ? ` (≠ filtro ${modeF.toUpperCase()}: le tile di rischio NON seguono il filtro)` : ''}`
        : '';

    return (
        <div className="min-h-screen bg-background text-foreground">
            <Helmet><title>P&L di giornata | Alpha Score</title></Helmet>

            {/* top bar + filtri */}
            <div className="sticky top-0 z-40 px-3 py-2 border-b border-white/10 bg-black/80 backdrop-blur flex items-center gap-3 flex-wrap">
                <Link to="/segui-live" className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-white">
                    <ArrowLeft className="w-3.5 h-3.5" /> Terminal
                </Link>
                <span className="inline-flex items-center gap-1.5 font-heading font-bold text-sm text-white">
                    <TrendingUp className="w-4 h-4 text-amber-400" /> P&amp;L di giornata
                </span>
                <div className="flex-1" />
                <label className="text-[11px] text-slate-400 inline-flex items-center gap-1.5">
                    Giorno
                    <input
                        type="date"
                        value={day}
                        onChange={e => e.target.value && setDay(e.target.value)}
                        className="bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-[11px] text-white"
                    />
                </label>
                <label className="text-[11px] text-slate-400 inline-flex items-center gap-1.5">
                    Mode
                    <select
                        value={modeF}
                        onChange={e => setModeF(e.target.value as ModeFilter)}
                        className="bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-[11px] text-white"
                    >
                        <option value="all">tutte</option>
                        <option value="paper">paper</option>
                        <option value="live">live</option>
                    </select>
                </label>
            </div>

            <div className="p-3 space-y-4 max-w-[1200px] mx-auto">
                {/* ------------------------------------------------------ KPI row */}
                <div className="flex gap-3 flex-wrap">
                    <StatTile
                        label="P&L realizzato"
                        value={settled == null ? '…' : fmtEur(realized)}
                        tone={realized >= 0 ? 'pos' : 'neg'}
                        title={`Σ profit dei mercati regolati (${filtered.length} mercati, fonte get_live_settled)`}
                    />
                    <StatTile
                        label={`MTM aperto${riskMode ? ` (${riskMode})` : ''}${riskModeMismatch ? ' ⚠' : ''}`}
                        value={openMtm != null ? fmtEur(openMtm) : '—'}
                        tone={openMtm != null ? (openMtm >= 0 ? 'pos' : 'neg') : 'plain'}
                        title={(isToday ? 'MTM delle posizioni aperte (risk_state.open_mtm)' : 'solo per la giornata corrente') + riskModeNote}
                        extra={
                            <div className="text-[10px] text-slate-500 tabular-nums">
                                {positions.length} posizioni aperte · rischio €{eventExposure(positions).toFixed(2)}
                            </div>
                        }
                    />
                    <StatTile
                        label={`Totale giornata${riskMode ? ` (${riskMode})` : ''}${riskModeMismatch ? ' ⚠' : ''}`}
                        value={total != null ? fmtEur(total) : '—'}
                        tone={total != null ? (total >= 0 ? 'pos' : 'neg') : 'plain'}
                        title={(isToday ? 'Realizzato + MTM (risk_state.total)' : 'solo per la giornata corrente') + riskModeNote}
                    />
                    <StatTile
                        label="Stop giornaliero"
                        value={risk?.limit_value != null ? `€${Math.abs(risk.limit_value).toFixed(2)}` : '—'}
                        tone="plain"
                        title="Limite di perdita giornaliera (daily_loss_limit)"
                        extra={risk?.stop_fired ? (
                            <span className="inline-block mt-1 px-1.5 py-0.5 rounded bg-red-600 text-white text-[10px] font-black animate-pulse">
                                SCATTATO
                            </span>
                        ) : (
                            <span className="text-[10px] text-slate-500">non scattato</span>
                        )}
                    />
                </div>

                {/* --------------------------------------------- equity curve */}
                <Card className="glass-card border-white/10 p-3">
                    <div className="text-[11px] text-slate-400 mb-1">
                        Equity intraday (P&amp;L realizzato cumulato{isToday ? ' · punto ambra = totale con MTM' : ''})
                    </div>
                    {settled == null ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-6 justify-center">
                            <Loader2 className="w-4 h-4 animate-spin" /> Carico i mercati regolati…
                        </div>
                    ) : (
                        <EquityCurve settled={filtered} finalWithMtm={total} />
                    )}
                </Card>

                {/* --------------------------------------------- tabelle settled */}
                <div className="grid md:grid-cols-2 gap-3 items-start">
                    <Card className="glass-card border-white/10 p-3 overflow-x-auto">
                        <div className="text-[11px] font-bold text-white mb-2">Per mercato</div>
                        {filtered.length === 0 ? (
                            <div className="text-[11px] text-muted-foreground">Nessun mercato regolato.</div>
                        ) : (
                            <table className="w-full text-[11px]">
                                <thead>
                                    <tr className="text-slate-400 text-left">
                                        <th className="py-1 pr-2 font-normal">Mercato</th>
                                        <th className="py-1 pr-2 font-normal">Evento</th>
                                        <th className="py-1 pr-2 font-normal text-right">P&amp;L</th>
                                        <th className="py-1 pr-2 font-normal">Fonte</th>
                                        <th className="py-1 font-normal text-right">Ora</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {[...filtered]
                                        .sort((a, b) => new Date(b.settled_at).getTime() - new Date(a.settled_at).getTime())
                                        .map(s => (
                                            <tr key={s.id} className="border-t border-white/5">
                                                <td className="py-1 pr-2 text-white/85" title={s.market_id}>
                                                    {s.market_name ?? s.market_id}
                                                </td>
                                                <td className="py-1 pr-2 text-slate-400 font-mono">{s.event_id ?? '—'}</td>
                                                <td className={`py-1 pr-2 text-right tabular-nums font-semibold ${s.profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                    {fmtEur(s.profit)}
                                                </td>
                                                <td className="py-1 pr-2">
                                                    {s.source === 'simulated' ? (
                                                        <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 text-[10px] font-bold">simulato</span>
                                                    ) : (
                                                        <span className="px-1.5 py-0.5 rounded bg-red-500/15 text-red-300 text-[10px] font-bold">reale</span>
                                                    )}
                                                </td>
                                                <td className="py-1 text-right text-slate-400 tabular-nums">{timeLabel(s.settled_at)}</td>
                                            </tr>
                                        ))}
                                </tbody>
                            </table>
                        )}
                    </Card>

                    <Card className="glass-card border-white/10 p-3 overflow-x-auto">
                        <div className="text-[11px] font-bold text-white mb-2">Per evento</div>
                        {byEvent.length === 0 ? (
                            <div className="text-[11px] text-muted-foreground">Nessun mercato regolato.</div>
                        ) : (
                            <table className="w-full text-[11px]">
                                <thead>
                                    <tr className="text-slate-400 text-left">
                                        <th className="py-1 pr-2 font-normal">Evento</th>
                                        <th className="py-1 pr-2 font-normal text-right">Mercati</th>
                                        <th className="py-1 font-normal text-right">P&amp;L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {byEvent.map(([eventId, agg]) => (
                                        <tr key={eventId} className="border-t border-white/5">
                                            <td className="py-1 pr-2 text-white/85 font-mono">{eventId}</td>
                                            <td className="py-1 pr-2 text-right text-slate-400 tabular-nums">{agg.n}</td>
                                            <td className={`py-1 text-right tabular-nums font-semibold ${agg.profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                {fmtEur(agg.profit)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </div>

                {/* --------------------------------------- sezione TENNIS separata */}
                <Card className="glass-card border-white/10 p-3 overflow-x-auto">
                    <div className="text-[11px] font-bold text-white mb-1">🎾 Tennis (posizioni aperte)</div>
                    <div className="text-[10px] text-amber-400/90 mb-2">
                        il settled tennis non è ancora storicizzato — qui SOLO le esposizioni aperte (get_tennis_live_positions_all)
                    </div>
                    {tPositions == null ? (
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground py-2">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Carico le posizioni tennis…
                        </div>
                    ) : tByEvent.length === 0 ? (
                        <div className="text-[11px] text-muted-foreground">Nessuna posizione tennis aperta.</div>
                    ) : (
                        <table className="w-full text-[11px]">
                            <thead>
                                <tr className="text-slate-400 text-left">
                                    <th className="py-1 pr-2 font-normal">Evento</th>
                                    <th className="py-1 pr-2 font-normal text-right">Posizioni</th>
                                    <th className="py-1 pr-2 font-normal text-right">Σ esposizione</th>
                                    <th className="py-1 font-normal text-right">Σ net</th>
                                </tr>
                            </thead>
                            <tbody>
                                {tByEvent.map(([eventId, rows]) => {
                                    const net = rows.reduce((a, p) => a + (Number.isFinite(p.net_position) ? p.net_position : 0), 0);
                                    return (
                                        <tr key={eventId} className="border-t border-white/5">
                                            <td className="py-1 pr-2 text-white/85 font-mono">{eventId}</td>
                                            <td className="py-1 pr-2 text-right text-slate-400 tabular-nums">{rows.length}</td>
                                            <td className="py-1 pr-2 text-right tabular-nums text-white/85">€{eventExposure(rows).toFixed(2)}</td>
                                            <td className={`py-1 text-right tabular-nums ${net >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                {net.toFixed(2)}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </Card>
            </div>
        </div>
    );
}
