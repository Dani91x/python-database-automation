import { NormalizedComparison } from "@/lib/normalize";
import { Card } from "@/components/ui/card";

export function ComparisonSection({ comparison }: { comparison: NormalizedComparison }) {
    const items = [
        { key: 'form', label: 'Forma Recente' },
        { key: 'att', label: 'Attacco' },
        { key: 'def', label: 'Difesa' },
        { key: 'poissonDistribution', label: 'Poisson Dist.' },
        { key: 'h2h', label: 'Testa a Testa' },
        { key: 'goals', label: 'Goals' },
    ] as const;

    return (
        <section className="mb-8">
            <h2 className="text-xl font-orbitron font-bold mb-6 flex items-center gap-2">
                <span className="w-1 h-6 bg-gradient-to-b from-neon-cyan to-neon-magenta rounded-full" />
                CONFRONTO DIRETTO
            </h2>

            <Card className="glass-card p-6 md:p-10">
                <div className="space-y-8">
                    {items.map((item) => {
                        const data = comparison[item.key];
                        // Avoid division by zero
                        const total = (data.home + data.away) || 1;
                        const homePct = (data.home / total) * 100;
                        const awayPct = (data.away / total) * 100; // or 100 - homePct

                        return (
                            <div key={item.key}>
                                <div className="flex justify-between text-xs font-bold uppercase tracking-widest mb-2 px-1">
                                    <span className="text-neon-cyan">{data.home}%</span>
                                    <span className="text-white opacity-50">{item.label}</span>
                                    <span className="text-neon-magenta">{data.away}%</span>
                                </div>
                                <div className="h-3 bg-black/40 rounded-full flex overflow-hidden relative">
                                    {/* Center marker */}
                                    <div className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-white/20 z-10" />

                                    <div
                                        className="h-full bg-neon-cyan transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(0,240,255,0.3)]"
                                        style={{ width: `${homePct}%` }}
                                    />
                                    <div
                                        className="h-full bg-neon-magenta transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(255,0,110,0.3)]"
                                        style={{ width: `${awayPct}%` }}
                                    />
                                </div>
                            </div>
                        );
                    })}
                </div>
            </Card>
        </section>
    );
}
