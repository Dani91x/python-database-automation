import { NormalizedComparison } from "@/lib/normalize";
import { Card } from "@/components/ui/card";
import { motion } from "framer-motion";
import { TrendingUp } from "lucide-react";

function generateInsight(key: string, homeVal: number, awayVal: number): string | null {
    if (homeVal === 0 && awayVal === 0) return null;
    const diff = Math.abs(homeVal - awayVal);
    if (diff < 5) return null;
    const winner = homeVal > awayVal ? 'Home' : 'Away';
    const pct = Math.max(homeVal, awayVal);

    const labels: Record<string, string> = {
        form: 'forma recente',
        att: 'attacco',
        def: 'difesa',
        poissonDistribution: 'Dist. Poisson',
        h2h: 'testa a testa',
        goals: 'gol',
    };

    return `${winner} ha un ${labels[key] || key} superiore al ${pct}%`;
}

export function ComparisonSection({ comparison, homeName, awayName }: {
    comparison: NormalizedComparison;
    homeName?: string;
    awayName?: string;
}) {
    const items = [
        { key: 'form', label: 'Forma Recente' },
        { key: 'att', label: 'Attacco' },
        { key: 'def', label: 'Difesa' },
        { key: 'poissonDistribution', label: 'Dist. Poisson' },
        { key: 'h2h', label: 'Testa a Testa' },
        { key: 'goals', label: 'Goals' },
    ] as const;

    const insights = items
        .map(item => {
            const data = comparison[item.key];
            const raw = generateInsight(item.key, data.home, data.away);
            if (!raw) return null;
            return raw
                .replace('Home', homeName || 'Home')
                .replace('Away', awayName || 'Away');
        })
        .filter(Boolean);

    // Total comparison
    const totalData = comparison.total;

    return (
        <section className="mb-8">
            <h2 className="text-xl font-display font-bold mb-6 flex items-center gap-2">
                <span className="w-1 h-6 bg-gradient-to-b from-primary to-secondary rounded-full" />
                CONFRONTO DIRETTO
            </h2>

            <Card className="glass-card p-6 md:p-10">
                <div className="space-y-8">
                    {items.map((item, i) => {
                        const data = comparison[item.key];
                        const total = (data.home + data.away) || 1;
                        const homePct = (data.home / total) * 100;
                        const awayPct = (data.away / total) * 100;

                        return (
                            <motion.div
                                key={item.key}
                                initial={{ opacity: 0 }}
                                whileInView={{ opacity: 1 }}
                                viewport={{ once: true }}
                                transition={{ duration: 0.4, delay: i * 0.05 }}
                            >
                                <div className="flex justify-between text-[10px] md:text-xs font-bold uppercase tracking-widest mb-2 px-1">
                                    <span className="text-primary">{data.home}%</span>
                                    <span className="text-foreground opacity-50 truncate mx-2">{item.label}</span>
                                    <span className="text-secondary">{data.away}%</span>
                                </div>
                                <div className="h-3 bg-black/40 rounded-full flex overflow-hidden relative">
                                    <div className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-white/20 z-10" />
                                    <motion.div
                                        initial={{ width: 0 }}
                                        whileInView={{ width: `${homePct}%` }}
                                        viewport={{ once: true }}
                                        transition={{ duration: 1, delay: i * 0.05, ease: 'easeOut' }}
                                        className="h-full bg-primary shadow-[0_0_10px_hsl(var(--primary)/0.3)]"
                                    />
                                    <motion.div
                                        initial={{ width: 0 }}
                                        whileInView={{ width: `${awayPct}%` }}
                                        viewport={{ once: true }}
                                        transition={{ duration: 1, delay: i * 0.05, ease: 'easeOut' }}
                                        className="h-full bg-secondary shadow-[0_0_10px_hsl(var(--secondary)/0.3)]"
                                    />
                                </div>
                            </motion.div>
                        );
                    })}

                    {/* Total */}
                    <div className="pt-4 border-t border-white/10">
                        <div className="flex justify-between text-xs font-bold uppercase tracking-widest mb-2 px-1">
                            <span className="text-primary font-mono">{totalData.home}%</span>
                            <span className="text-foreground font-black">TOTALE</span>
                            <span className="text-secondary font-mono">{totalData.away}%</span>
                        </div>
                        <div className="h-4 bg-black/40 rounded-full flex overflow-hidden relative">
                            <div className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-white/20 z-10" />
                            <motion.div
                                initial={{ width: 0 }}
                                whileInView={{ width: `${(totalData.home / ((totalData.home + totalData.away) || 1)) * 100}%` }}
                                viewport={{ once: true }}
                                transition={{ duration: 1.2, ease: 'easeOut' }}
                                className="h-full bg-gradient-to-r from-primary to-emerald-400 shadow-[0_0_15px_hsl(var(--primary)/0.4)]"
                            />
                            <motion.div
                                initial={{ width: 0 }}
                                whileInView={{ width: `${(totalData.away / ((totalData.home + totalData.away) || 1)) * 100}%` }}
                                viewport={{ once: true }}
                                transition={{ duration: 1.2, ease: 'easeOut' }}
                                className="h-full bg-gradient-to-r from-yellow-300 to-secondary shadow-[0_0_15px_hsl(var(--secondary)/0.4)]"
                            />
                        </div>
                    </div>
                </div>

                {/* Insight automatici */}
                {insights.length > 0 && (
                    <div className="mt-8 p-4 bg-muted/10 rounded-xl border border-white/5">
                        <div className="flex items-center gap-2 mb-3 text-accent">
                            <TrendingUp className="w-4 h-4" />
                            <span className="text-xs font-bold uppercase tracking-widest">Insight AI</span>
                        </div>
                        <ul className="space-y-1.5">
                            {insights.map((insight, i) => (
                                <li key={i} className="text-sm text-foreground/70 flex items-center gap-2">
                                    <span className="w-1 h-1 rounded-full bg-accent shrink-0" />
                                    {insight}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </Card>
        </section>
    );
}
