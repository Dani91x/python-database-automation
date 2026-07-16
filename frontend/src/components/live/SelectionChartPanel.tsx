// ============================================================================
// SelectionChartPanel (roadmap D29) — charting per SELEZIONE: candele prezzo
// (LTP) + pannello volume (delta del tv cumulato) + VWAP cumulato, con selettore
// di selezione e timeframe. Dati dal ladder live (fetch + subscribe realtime),
// campionati in buffer per-selezione da quando il pannello è aperto.
//
// Design coerente con MiniPriceChart: candele emerald/rose, VWAP amber, superfici
// slate-900/50, testi slate-300/400 (MAI testo colorato col colore della serie).
// Matematica in lib/ladderChart (pushVolumeSample / bucketCandlesV / vwapSeries).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import {
    fetchLiveLadder, subscribeLiveLadder,
    type LiveLadderRow,
} from '@/lib/live';
import type { LadderSource } from '@/components/live/LadderView';
import {
    pushVolumeSample, bucketCandlesV, vwapSeries,
    type VolumeSample, type CandleV,
} from '@/lib/ladderChart';

// stesso default di LadderView: senza props il pannello parla col calcio,
// il tennis (o altri sport) inietta la sua sorgente via `ladderSource`.
const DEFAULT_LADDER_SOURCE: LadderSource = {
    fetch: fetchLiveLadder,
    subscribe: subscribeLiveLadder,
};

// timeframe disponibili (bucket delle candele).
const TIMEFRAMES = [
    { label: '5s', ms: 5_000 },
    { label: '15s', ms: 15_000 },
    { label: '30s', ms: 30_000 },
    { label: '1m', ms: 60_000 },
    { label: '5m', ms: 300_000 },
] as const;
const DEFAULT_BUCKET_MS = 15_000;

// geometria del chart (viewBox fluido: la larghezza CSS è del container).
const VB_W = 480;          // larghezza nominale viewBox
const PRICE_H = 224;       // altezza chart prezzo (≈ h-56)
const VOL_H = 48;          // altezza pannello volume (≈ h-12)
const AXIS_W = 44;         // gutter destro per l'asse Y (prezzi)
const PLOT_W = VB_W - AXIS_W;
const MAX_CANDLES = 48;    // max candele visibili

const COLOR_UP = 'rgb(16 185 129)';    // emerald-500 (c >= o)
const COLOR_DOWN = 'rgb(244 63 94)';   // rose-500    (c <  o)
const COLOR_VWAP = 'rgb(251 191 36)';  // amber-400
const COLOR_VOL = 'rgb(100 116 139)';  // slate-500
const COLOR_AXIS = 'rgb(148 163 184)'; // slate-400
const COLOR_GRID = 'rgb(51 65 85 / 0.5)'; // slate-700/50

const fmtP = (p: number) => (p >= 100 ? p.toFixed(0) : p.toFixed(2));
const fmtEur = (v: number) => (v >= 10_000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0));

// ~3 tick "puliti" (multipli di 1/2/5·10^k) dentro [lo, hi].
function niceTicks(lo: number, hi: number, n = 3): number[] {
    const span = hi - lo;
    if (!(span > 0)) return [];
    const raw = span / (n + 1);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
    const out: number[] = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6 && out.length < n; v += step) {
        out.push(v);
    }
    return out;
}

interface Props {
    marketId: string;
    ladderSource?: LadderSource;
    // timeframe iniziale (l'utente può sempre cambiarlo dai bottoni): il tennis
    // passa 5s — i punti muovono la quota ogni pochi secondi, 15s appiattisce tutto.
    defaultBucketMs?: number;
}

export function SelectionChartPanel({ marketId, ladderSource, defaultBucketMs }: Props) {
    const source = ladderSource ?? DEFAULT_LADDER_SOURCE;

    // buffer campioni per-selezione (mutati in place: la "storia" vive qui, da
    // quando il pannello è aperto). `ver` forza il ricalcolo dei memo a ogni update.
    const buffersRef = useRef<Map<number, VolumeSample[]>>(new Map());
    const [row, setRow] = useState<LiveLadderRow | null>(null);
    const [ver, setVer] = useState(0);
    const [selId, setSelId] = useState<number | null>(null);
    const [bucketMs, setBucketMs] = useState<number>(defaultBucketMs ?? DEFAULT_BUCKET_MS);
    const [hoverI, setHoverI] = useState<number | null>(null);

    useEffect(() => {
        // mercato diverso = storia diversa: svuota i buffer e riparti.
        buffersRef.current = new Map();
        setRow(null);
        setSelId(null);
        setHoverI(null);
        setVer(0);
        let cancelled = false;

        const handle = (r: LiveLadderRow | null) => {
            if (cancelled || !r) return;
            const lad = r.ladder;
            if (lad) {
                const t = lad.updated_ms ?? Date.now();
                for (const s of lad.selections) {
                    if (s.ltp == null) continue; // nessun trade ancora: niente campione
                    let buf = buffersRef.current.get(s.selection_id);
                    if (!buf) {
                        buf = [];
                        buffersRef.current.set(s.selection_id, buf);
                    }
                    pushVolumeSample(buf, t, s.ltp, s.tv);
                }
            }
            setRow(r);
            setVer((n) => n + 1);
        };

        source.fetch(marketId).then(handle).catch(() => { /* snapshot assente: si popola col realtime */ });
        const unsubscribe = source.subscribe(marketId, handle);
        return () => {
            cancelled = true;
            unsubscribe();
        };
    }, [marketId, source.fetch, source.subscribe]); // eslint-disable-line react-hooks/exhaustive-deps

    const selections = row?.ladder?.selections ?? [];
    const effSelId = selId ?? selections[0]?.selection_id ?? null;

    const candles: CandleV[] = useMemo(() => {
        const buf = effSelId != null ? buffersRef.current.get(effSelId) ?? [] : [];
        return bucketCandlesV(buf, bucketMs, MAX_CANDLES);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ver, effSelId, bucketMs]);

    const vwap = useMemo(() => vwapSeries(candles), [candles]);

    // ---- scala e geometria (solo se abbiamo abbastanza candele) ----
    const hasChart = candles.length >= 2;
    let lo = Infinity;
    let hi = -Infinity;
    for (const c of candles) {
        if (c.l < lo) lo = c.l;
        if (c.h > hi) hi = c.h;
    }
    for (const w of vwap) {
        if (w != null) { if (w < lo) lo = w; if (w > hi) hi = w; }
    }
    const pad = Math.max((hi - lo) * 0.08, 0.005);
    lo -= pad;
    hi += pad;
    const y = (p: number) => ((hi - p) / (hi - lo)) * (PRICE_H - 16) + 8;

    const slot = PLOT_W / MAX_CANDLES;
    const bodyW = Math.max(2, Math.floor(slot * 0.55));
    const volW = Math.max(1.5, slot * 0.45); // barre sottili con gap
    const x0 = PLOT_W - candles.length * slot; // le candele si accodano a destra
    const cxOf = (i: number) => x0 + i * slot + slot / 2;
    const ticks = hasChart ? niceTicks(lo, hi, 3) : [];
    const maxV = candles.reduce((m, c) => Math.max(m, c.v), 0);

    // hover valido solo dentro la finestra corrente (timeframe/selezione possono cambiarla).
    const hover = hoverI != null && hoverI >= 0 && hoverI < candles.length ? hoverI : null;
    const hc = hover != null ? candles[hover] : null;
    const hvwap = hover != null ? vwap[hover] : null;

    // mouse → coordinate viewBox → candela più vicina (snap).
    const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
        if (!hasChart) return;
        const rect = e.currentTarget.getBoundingClientRect();
        if (!(rect.width > 0)) return;
        const xv = ((e.clientX - rect.left) / rect.width) * VB_W;
        let best = 0;
        let bestD = Infinity;
        for (let i = 0; i < candles.length; i++) {
            const d = Math.abs(cxOf(i) - xv);
            if (d < bestD) { bestD = d; best = i; }
        }
        setHoverI(best);
    };

    // tooltip: posizione in % del container, con clamp per non uscire dai bordi.
    const hoverPct = hover != null ? (cxOf(hover) / VB_W) * 100 : 0;
    const tipTransform = hoverPct < 22 ? 'translateX(0)' : hoverPct > 78 ? 'translateX(-100%)' : 'translateX(-50%)';

    return (
        <div className="rounded-md border border-slate-800 bg-slate-900/50">
            {/* header: selezione + timeframe */}
            <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-800">
                <select
                    aria-label="Selezione"
                    className="bg-slate-900 border border-slate-800 rounded px-1.5 py-0.5 text-[11px] text-slate-300 outline-none"
                    value={effSelId ?? ''}
                    onChange={(e) => { setSelId(Number(e.target.value)); setHoverI(null); }}
                >
                    {selections.map((s) => (
                        <option key={s.selection_id} value={s.selection_id}>
                            {s.name ?? `Sel ${s.selection_id}`}
                        </option>
                    ))}
                </select>
                <div className="ml-auto flex gap-1" role="group" aria-label="Timeframe">
                    {TIMEFRAMES.map((tf) => (
                        <button
                            key={tf.label}
                            type="button"
                            onClick={() => { setBucketMs(tf.ms); setHoverI(null); }}
                            className={`px-1.5 py-0.5 rounded border text-[11px] leading-none ${
                                bucketMs === tf.ms
                                    ? 'bg-slate-700 border-slate-600 text-slate-100'
                                    : 'bg-slate-900/50 border-slate-800 text-slate-400 hover:text-slate-200'
                            }`}
                        >
                            {tf.label}
                        </button>
                    ))}
                </div>
            </div>

            {!hasChart ? (
                <div className="h-56 flex items-center justify-center px-4">
                    <span className="text-[11px] text-slate-400 text-center">
                        raccolgo prezzi… (campioni dal vivo da quando il pannello è aperto)
                    </span>
                </div>
            ) : (
                <div className="relative px-1 pt-1 pb-1.5">
                    {/* chart prezzo: candele + VWAP + asse Y destro + crosshair */}
                    <svg
                        viewBox={`0 0 ${VB_W} ${PRICE_H}`}
                        preserveAspectRatio="none"
                        className="block w-full h-56"
                        role="img"
                        aria-label="Candele prezzo della selezione con VWAP"
                        onMouseMove={onMove}
                        onMouseLeave={() => setHoverI(null)}
                    >
                        {/* griglia + asse Y (3 tick puliti, testo slate-400) */}
                        {ticks.map((tk) => (
                            <g key={tk}>
                                <line x1={0} x2={PLOT_W} y1={y(tk)} y2={y(tk)} stroke={COLOR_GRID} strokeWidth={1} />
                                <text
                                    x={VB_W - 2} y={y(tk) + 3}
                                    textAnchor="end" fontSize={10} fill={COLOR_AXIS} fontFamily="monospace"
                                >
                                    {fmtP(tk)}
                                </text>
                            </g>
                        ))}
                        {/* crosshair verticale (snap alla candela più vicina) */}
                        {hover != null && (
                            <line
                                x1={cxOf(hover)} x2={cxOf(hover)} y1={0} y2={PRICE_H}
                                stroke="rgb(148 163 184 / 0.45)" strokeWidth={1} strokeDasharray="3 3"
                            />
                        )}
                        {/* candele: wick + body (emerald-500 su, rose-500 giù) */}
                        {candles.map((c, i) => {
                            const cx = cxOf(i);
                            const up = c.c >= c.o;
                            const color = up ? COLOR_UP : COLOR_DOWN;
                            const top = y(Math.max(c.o, c.c));
                            const bot = y(Math.min(c.o, c.c));
                            return (
                                <g key={c.t0}>
                                    <line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth={1} />
                                    <rect
                                        x={cx - bodyW / 2}
                                        y={top}
                                        width={bodyW}
                                        height={Math.max(2, bot - top)}
                                        rx={1}
                                        fill={color}
                                        fillOpacity={0.9}
                                    />
                                </g>
                            );
                        })}
                        {/* VWAP amber-400, linea CONTINUA che skippa i punti null */}
                        {(() => {
                            const pts: string[] = [];
                            for (let i = 0; i < candles.length; i++) {
                                const w = vwap[i];
                                if (w == null) continue;
                                pts.push(`${pts.length === 0 ? 'M' : 'L'}${cxOf(i).toFixed(1)},${y(w).toFixed(1)}`);
                            }
                            return pts.length >= 2
                                ? <path d={pts.join(' ')} fill="none" stroke={COLOR_VWAP} strokeWidth={2} strokeLinejoin="round" />
                                : null;
                        })()}
                    </svg>

                    {/* pannello volume separato (stessa scala X) */}
                    <svg
                        viewBox={`0 0 ${VB_W} ${VOL_H}`}
                        preserveAspectRatio="none"
                        className="block w-full h-12 mt-0.5"
                        role="img"
                        aria-label="Volume tradato per candela"
                    >
                        {hover != null && (
                            <line
                                x1={cxOf(hover)} x2={cxOf(hover)} y1={0} y2={VOL_H}
                                stroke="rgb(148 163 184 / 0.45)" strokeWidth={1} strokeDasharray="3 3"
                            />
                        )}
                        {candles.map((c, i) => {
                            const h = maxV > 0 ? (c.v / maxV) * (VOL_H - 6) : 0;
                            return (
                                <rect
                                    key={c.t0}
                                    x={cxOf(i) - volW / 2}
                                    y={VOL_H - 2 - h}
                                    width={volW}
                                    height={Math.max(1, h)}
                                    fill={COLOR_VOL}
                                    fillOpacity={0.85}
                                />
                            );
                        })}
                        <line x1={0} x2={PLOT_W} y1={VOL_H - 1.5} y2={VOL_H - 1.5} stroke={COLOR_GRID} strokeWidth={1} />
                    </svg>

                    {/* tooltip: div assoluto clampato dentro il container */}
                    {hc != null && (
                        <div
                            className="pointer-events-none absolute top-2 z-10 rounded border border-slate-700 bg-slate-900/95 px-2 py-1 text-[11px] leading-4 text-slate-300 shadow-lg"
                            style={{
                                left: `${Math.min(100, Math.max(0, hoverPct))}%`,
                                transform: tipTransform,
                            }}
                        >
                            <div className="text-slate-400">{new Date(hc.t0).toLocaleTimeString('it')}</div>
                            <div className="font-mono">
                                O {fmtP(hc.o)} · H {fmtP(hc.h)} · L {fmtP(hc.l)} · C {fmtP(hc.c)}
                            </div>
                            <div className="font-mono">Vol € {fmtEur(hc.v)}</div>
                            <div className="font-mono">VWAP {hvwap != null ? fmtP(hvwap) : '—'}</div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default SelectionChartPanel;
