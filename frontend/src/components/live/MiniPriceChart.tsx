// ============================================================================
// MiniPriceChart — candele OHLC del prezzo (LTP) della selezione, laterali al
// ladder (stile BetTrader "matchstick chart"). Dati dal buffer campioni del
// LadderView (un campione per update dello stream), bucketing in lib/ladderChart.
//
// Design (skill dataviz): polarità su/giù = emerald/rose (convenzione del
// terminal), ultimo prezzo = linea amber tratteggiata (come l'LTP del ladder),
// marks sottili, tooltip nativo <title> per candela, superficie scura.
// ============================================================================
import { useMemo } from 'react';
import { bucketCandles, type PriceSample } from '@/lib/ladderChart';

const BUCKET_MS = 15_000;   // una candela ogni 15s (≈ scalping timeframe)
const MAX_BUCKETS = 40;     // ~10 minuti di storia visibile
const W = 96;               // larghezza pannello (px)

const fmtP = (p: number) => (p >= 100 ? p.toFixed(0) : p.toFixed(2));

export function MiniPriceChart({ samples, height = 420 }: {
    samples: PriceSample[] | undefined;
    height?: number;
}) {
    const candles = useMemo(
        () => bucketCandles(samples ?? [], BUCKET_MS, MAX_BUCKETS),
        // il buffer è mutato in place dal parent: la lunghezza cambia a ogni campione e
        // il parent ri-renderizza a ogni update del ladder → il memo si ricalcola quando serve.
        [samples, samples?.length],
    );

    if (candles.length < 2) {
        return (
            <div
                className="shrink-0 border-l border-white/10 bg-black/30 flex items-center justify-center"
                style={{ width: W, maxHeight: height }}
                title="Il mini-chart si popola con lo storico prezzi da quando il ladder è aperto"
            >
                <span className="text-[9px] text-muted-foreground/60 rotate-90 whitespace-nowrap">
                    raccolgo prezzi…
                </span>
            </div>
        );
    }

    // scala y: min/max dei low/high con un piccolo padding (mai scala da zero: è prezzo).
    let lo = Infinity;
    let hi = -Infinity;
    for (const c of candles) {
        if (c.l < lo) lo = c.l;
        if (c.h > hi) hi = c.h;
    }
    const pad = Math.max((hi - lo) * 0.08, 0.005);
    lo -= pad;
    hi += pad;
    const y = (p: number) => ((hi - p) / (hi - lo)) * (height - 18) + 9;

    const slot = W / MAX_BUCKETS;               // larghezza slot per candela
    const bodyW = Math.max(2, Math.floor(slot * 0.55));
    const x0 = W - candles.length * slot;       // le candele si accodano a destra
    const last = candles[candles.length - 1];

    return (
        <div
            className="shrink-0 border-l border-white/10 bg-black/30 overflow-hidden"
            style={{ width: W, maxHeight: height }}
        >
            <svg width={W} height={height} role="img" aria-label="Mini-chart prezzo (candele 15s)">
                {/* ultimo prezzo: linea tratteggiata amber (stessa semantica dell'LTP) */}
                <line
                    x1={0} x2={W} y1={y(last.c)} y2={y(last.c)}
                    stroke="rgb(251 191 36 / 0.55)" strokeWidth={1} strokeDasharray="3 3"
                />
                {candles.map((c, i) => {
                    const cx = x0 + i * slot + slot / 2;
                    const up = c.c >= c.o;
                    const color = up ? 'rgb(52 211 153)' : 'rgb(251 113 133)'; // emerald-400 / rose-400
                    const top = y(Math.max(c.o, c.c));
                    const bot = y(Math.min(c.o, c.c));
                    return (
                        <g key={c.t0}>
                            <title>{`${new Date(c.t0).toLocaleTimeString('it')} · O ${fmtP(c.o)} · H ${fmtP(c.h)} · L ${fmtP(c.l)} · C ${fmtP(c.c)}`}</title>
                            {/* wick */}
                            <line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth={1} />
                            {/* body (min 2px: anche i doji si vedono) */}
                            <rect
                                x={cx - bodyW / 2}
                                y={top}
                                width={bodyW}
                                height={Math.max(2, bot - top)}
                                rx={1}
                                fill={color}
                                fillOpacity={up ? 0.85 : 0.9}
                            />
                        </g>
                    );
                })}
                {/* etichetta ultimo prezzo (testo in ink, non nel colore serie) */}
                <text
                    x={W - 2} y={Math.max(10, Math.min(height - 4, y(last.c) - 3))}
                    textAnchor="end" fontSize={8} fill="rgb(253 230 138)" fontFamily="monospace"
                >
                    {fmtP(last.c)}
                </text>
            </svg>
        </div>
    );
}

export default MiniPriceChart;
