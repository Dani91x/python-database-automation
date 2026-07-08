// ============================================================================
// TennisBotEquityChart — grafico equity/PnL aggregato dei bot tennis ARMATI.
//
// Riceve l'array `controls` (uno per bot) dal TennisBotPanel e mantiene una
// serie temporale ROLLING interna (max ~120 campioni). Ad ogni cambio di
// `controls` (il pannello fa polling ~4s) aggiunge un campione:
//   total  = Σ (stats.pnl_locked ?? 0) + (stats.pnl_open ?? 0)   → equity mark-to-market
//   locked = Σ (stats.pnl_locked ?? 0)                           → PnL già bloccato
// L'area/linea è verde quando l'equity è ≥ 0, rossa quando è sotto zero.
// Nessun dato ancora → placeholder discreto. Dark theme, sfondo trasparente.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import {
    AreaChart, Area, Line, XAxis, YAxis, ReferenceLine,
    ResponsiveContainer, Tooltip as RechartsTooltip, CartesianGrid,
} from 'recharts';
import { TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TennisBotControl } from '@/lib/tennis';

interface Props {
    controls: TennisBotControl[];
}

interface Sample {
    t: string; // etichetta oraria HH:MM:SS
    total: number; // equity mark-to-market (bloccato + aperto)
    locked: number; // solo PnL bloccato
}

const MAX_POINTS = 120;

const num = (v: unknown): number =>
    typeof v === 'number' && Number.isFinite(v) ? v : 0;

/** Aggrega l'equity corrente dei bot. */
function aggregate(controls: TennisBotControl[]): { total: number; locked: number; hasData: boolean } {
    let total = 0;
    let locked = 0;
    let hasData = false;
    for (const c of controls) {
        const s = c.stats;
        if (!s) continue;
        const l = num(s.pnl_locked);
        const o = num(s.pnl_open);
        if (s.pnl_locked !== undefined || s.pnl_open !== undefined) hasData = true;
        locked += l;
        total += l + o;
    }
    return { total, locked, hasData };
}

const eur = (v: number) => `€${v.toFixed(2)}`;

export function TennisBotEquityChart({ controls }: Props) {
    const [series, setSeries] = useState<Sample[]>([]);
    // Firma dei valori: aggiunge un campione solo quando l'aggregato cambia
    // davvero (evita rumore piatto quando i bot non stampano nulla di nuovo).
    const { total, locked, hasData } = useMemo(() => aggregate(controls), [controls]);
    const lastSigRef = useRef<string>('');

    useEffect(() => {
        if (!hasData) return;
        const sig = `${total.toFixed(4)}|${locked.toFixed(4)}`;
        if (sig === lastSigRef.current) return;
        lastSigRef.current = sig;
        const label = new Date().toLocaleTimeString('it-IT', { hour12: false });
        setSeries((prev) => {
            const next = [...prev, { t: label, total, locked }];
            return next.length > MAX_POINTS ? next.slice(next.length - MAX_POINTS) : next;
        });
    }, [total, locked, hasData]);

    const positive = total >= 0;
    const stroke = positive ? '#34d399' : '#f87171'; // emerald-400 / red-400
    const gradId = 'tennisEquityFill';

    return (
        <div className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                    <TrendingUp className={cn('h-4 w-4', positive ? 'text-emerald-400' : 'text-red-400')} />
                    <span className="font-display font-black text-sm text-white tracking-tight">
                        Equity bot (live)
                    </span>
                </div>
                {series.length > 0 && (
                    <div className="flex items-center gap-3 text-xs font-mono">
                        <span className={cn('font-black', positive ? 'text-emerald-300' : 'text-red-300')}>
                            {eur(total)}
                        </span>
                        <span className="text-white/40">
                            bloccato <b className="text-white/70">{eur(locked)}</b>
                        </span>
                    </div>
                )}
            </div>

            <div className="h-40 w-full">
                {series.length < 2 ? (
                    <div className="h-full w-full flex items-center justify-center rounded-lg border border-dashed border-white/10">
                        <span className="text-xs text-white/35">In attesa di operatività dei bot…</span>
                    </div>
                ) : (
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={series} margin={{ top: 6, right: 6, bottom: 0, left: -18 }}>
                            <defs>
                                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                                    <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-white/5" vertical={false} />
                            <XAxis
                                dataKey="t"
                                tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.35)' }}
                                tickLine={false}
                                axisLine={false}
                                minTickGap={40}
                            />
                            <YAxis
                                tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.35)' }}
                                tickLine={false}
                                axisLine={false}
                                width={44}
                                tickFormatter={(v: number) => `€${v.toFixed(0)}`}
                            />
                            <ReferenceLine y={0} stroke="rgba(255,255,255,0.18)" strokeDasharray="2 2" />
                            <RechartsTooltip
                                contentStyle={{
                                    background: 'rgba(10,12,16,0.92)',
                                    border: '1px solid rgba(255,255,255,0.12)',
                                    borderRadius: 8,
                                    fontSize: 11,
                                }}
                                labelStyle={{ color: 'rgba(255,255,255,0.6)' }}
                                formatter={(value: number | undefined, name) => [
                                    eur(value ?? 0),
                                    name === 'total' ? 'Equity' : 'Bloccato',
                                ]}
                            />
                            <Area
                                type="monotone"
                                dataKey="total"
                                stroke={stroke}
                                strokeWidth={2}
                                fill={`url(#${gradId})`}
                                isAnimationActive={false}
                                dot={false}
                            />
                            <Line
                                type="monotone"
                                dataKey="locked"
                                stroke="rgba(250,204,21,0.85)" // amber
                                strokeWidth={1.4}
                                strokeDasharray="4 3"
                                dot={false}
                                isAnimationActive={false}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                )}
            </div>
        </div>
    );
}
