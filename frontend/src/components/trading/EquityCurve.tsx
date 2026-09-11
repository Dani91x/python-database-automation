// ============================================================================
// EquityCurve.tsx — curva del P&L cumulato regolato (SVG puro, nessuna libreria).
// Stessa resa della curva Omega: gradini sui settlement, linea dello zero,
// colore dal segno finale.
// ============================================================================
import { fmtMoney } from '@/lib/format';

export interface EquityPoint { t: number; v: number; iso: string }

export function EquityCurve({ series, emptyLabel = 'nessun trade ancora regolato — la curva compare al primo incasso', label = 'Equity curve' }: {
    series: EquityPoint[]; emptyLabel?: string; label?: string;
}) {
    if (series.length === 0) {
        return <div className="text-sm text-muted-foreground py-16 text-center">{emptyLabel}</div>;
    }
    const W = 820, H = 240;
    const pad = { l: 10, r: 60, t: 18, b: 26 };
    let t0 = series[0].t;
    let t1 = series[series.length - 1].t;
    if (t1 - t0 < 60_000) { t0 -= 15 * 60_000; t1 += 15 * 60_000; }
    const vals = series.map((p) => p.v).concat([0]);
    let vMin = Math.min(...vals), vMax = Math.max(...vals);
    const span = Math.max(vMax - vMin, 0.01);
    vMin -= span * 0.1; vMax += span * 0.1;
    const x = (t: number) => pad.l + ((t - t0) / (t1 - t0 || 1)) * (W - pad.l - pad.r);
    const y = (v: number) => pad.t + ((vMax - v) / (vMax - vMin)) * (H - pad.t - pad.b);

    let d = `M ${x(series[0].t)} ${y(0)}`;
    let prevV = 0;
    for (const p of series) { d += ` L ${x(p.t)} ${y(prevV)} L ${x(p.t)} ${y(p.v)}`; prevV = p.v; }
    const lastV = series[series.length - 1].v;
    const color = lastV >= 0 ? '#34d399' : '#f87171';
    const area = `${d} L ${x(t1)} ${y(0)} L ${x(series[0].t)} ${y(0)} Z`;
    const yTicks = [vMin + span * 0.1, (vMin + vMax) / 2, vMax - span * 0.1];

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label={label}>
            {yTicks.map((v, i) => (
                <g key={i}>
                    <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#1e293b" strokeWidth={1} />
                    <text x={W - pad.r + 6} y={y(v) + 3} fontSize={10} fill="#94a3b8" className="tabular-nums">{fmtMoney(v, { signed: true })}</text>
                </g>
            ))}
            <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} stroke="#334155" strokeWidth={1} strokeDasharray="3 3" />
            <path d={area} fill={color} opacity={0.12} />
            <path d={d} fill="none" stroke={color} strokeWidth={2.5} />
            <circle cx={x(series[series.length - 1].t)} cy={y(lastV)} r={4} fill={color} />
        </svg>
    );
}

export default EquityCurve;
