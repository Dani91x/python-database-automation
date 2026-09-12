// ============================================================================
// EquityCurve.tsx — curva del P&L cumulato regolato (SVG puro, nessuna libreria).
// Stessa resa della curva Omega: gradini sui settlement, linea dello zero,
// colore dal segno finale.
// ============================================================================
import { fmtMoney } from '@/lib/format';

/** 'YYYY-MM-DD' o ISO → «10 set» (asse orizzontale, sempre in UTC: le chiavi
 *  sono già giornate operative Europe/Rome, non istanti da riconvertire). */
function axisDay(iso: string | undefined, t: number): string {
    const ms = typeof iso === 'string' && /^\d{4}-\d{2}-\d{2}/.test(iso)
        ? Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)))
        : t;
    if (!Number.isFinite(ms)) return '';
    try {
        return new Intl.DateTimeFormat('it-IT', { timeZone: 'UTC', day: 'numeric', month: 'short' }).format(new Date(ms));
    } catch { return ''; }
}

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

    // accessibilità: un grafico non leggibile da chi non lo vede è un dato
    // mancante — l'aria-label dice partenza, arrivo e numero di gradini
    // Certificazione 12/09 — l'asse ORIZZONTALE non era etichettato in alcun
    // modo: la curva non diceva a quale giornata corrispondesse un gradino.
    const firstLabel = axisDay(series[0].iso, series[0].t);
    const lastLabel = axisDay(series[series.length - 1].iso, series[series.length - 1].t);
    const aria = `${label}: da ${fmtMoney(0, { signed: true })} a ${fmtMoney(lastV, { signed: true })} in ${series.length} ${series.length === 1 ? 'passo' : 'passi'}`
        + (firstLabel && lastLabel ? ` (${firstLabel} → ${lastLabel})` : '');

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label={aria}>
            <title>{aria}</title>
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
            {/* asse orizzontale = tempo: primo e ultimo passo dell'ambito */}
            <text x={pad.l} y={H - 8} fontSize={10} fill="#94a3b8" textAnchor="start">{firstLabel}</text>
            {lastLabel !== firstLabel && (
                <text x={W - pad.r} y={H - 8} fontSize={10} fill="#94a3b8" textAnchor="end">{lastLabel}</text>
            )}
        </svg>
    );
}

export default EquityCurve;
