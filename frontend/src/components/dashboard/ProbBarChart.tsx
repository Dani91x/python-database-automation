// Grafico a barre orizzontali di probabilita (0..1) per le selezioni di un mercato.
// Usato da PoissonPanel e MLPanel. Stile coerente col design system scuro.
import {
    BarChart, Bar, XAxis, YAxis, Cell, LabelList, ResponsiveContainer, Tooltip, CartesianGrid,
} from 'recharts';

export interface ProbBar {
    label: string;
    value: number; // probabilita 0..1
    color: string;
}

export function ProbBarChart({ bars, height }: { bars: ProbBar[]; height?: number }) {
    const data = bars.map(b => ({ ...b, pct: Number((b.value * 100).toFixed(2)) }));
    const h = height ?? Math.max(140, 56 + data.length * 38);
    return (
        <div style={{ height: h }}>
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} layout="vertical" margin={{ top: 4, right: 52, left: 8, bottom: 4 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.05)" horizontal={false} />
                    <XAxis
                        type="number" domain={[0, 100]}
                        tickFormatter={(v: number) => `${v}%`}
                        tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                        axisLine={false} tickLine={false}
                    />
                    <YAxis
                        type="category" dataKey="label" width={120}
                        tick={{ fill: 'rgba(255,255,255,0.7)', fontSize: 11 }}
                        axisLine={false} tickLine={false}
                    />
                    <Tooltip
                        cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                        contentStyle={{ background: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }}
                        formatter={(v: number) => [`${v.toFixed(1)}%`, 'probabilità']}
                    />
                    <Bar dataKey="pct" radius={[0, 4, 4, 0]} isAnimationActive={data.length <= 40}>
                        {data.map((d, i) => <Cell key={i} fill={d.color} />)}
                        <LabelList
                            dataKey="pct" position="right"
                            formatter={(v: number) => `${v.toFixed(1)}%`}
                            fill="rgba(255,255,255,0.85)" fontSize={11} fontWeight={700}
                        />
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}
