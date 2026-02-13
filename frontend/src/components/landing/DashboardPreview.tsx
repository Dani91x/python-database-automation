import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";

const bullets = [
    "Pronostico AI con advice e percentuali 1X2",
    "Statistiche dettagliate Home vs Away",
    "Grafici goals by minute e cards heatmap",
    "Confronto squadre con matrice comparativa",
    "Distribuzione Under/Over per soglia",
    "Head-to-Head e ultimi 5 match",
];

export function DashboardPreview() {
    return (
        <section className="py-20 px-4">
            <div className="max-w-6xl mx-auto">
                <div className="glass-card animated-border rounded-2xl p-8 md:p-12">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-10 items-center">
                        {/* Text side */}
                        <motion.div
                            initial={{ opacity: 0, x: -30 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            viewport={{ once: true }}
                            transition={{ duration: 0.6 }}
                        >
                            <h2 className="text-3xl md:text-4xl font-display font-bold text-foreground mb-6">
                                Una Dashboard Completa
                                <br />
                                <span className="text-gradient-primary">Per Ogni Partita</span>
                            </h2>

                            <ul className="space-y-4">
                                {bullets.map((b) => (
                                    <li key={b} className="flex items-start gap-3">
                                        <CheckCircle2 className="w-5 h-5 text-primary mt-0.5 shrink-0" />
                                        <span className="text-muted-foreground font-heading">{b}</span>
                                    </li>
                                ))}
                            </ul>
                        </motion.div>

                        {/* Visual mock side */}
                        <motion.div
                            initial={{ opacity: 0, x: 30 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            viewport={{ once: true }}
                            transition={{ duration: 0.6, delay: 0.2 }}
                            className="glass-card rounded-xl p-6 neon-glow-primary"
                        >
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <span className="home-badge">HOME</span>
                                    <span className="font-display text-2xl font-bold text-foreground">VS</span>
                                    <span className="away-badge">AWAY</span>
                                </div>
                                <div className="grid grid-cols-3 gap-3 text-center">
                                    {[
                                        { label: "1", val: "45%" },
                                        { label: "X", val: "28%" },
                                        { label: "2", val: "27%" },
                                    ].map((p) => (
                                        <div key={p.label} className="glass-card rounded-lg p-3">
                                            <div className="stat-label mb-1">{p.label}</div>
                                            <div className="stat-value text-xl">{p.val}</div>
                                        </div>
                                    ))}
                                </div>
                                <div className="space-y-2">
                                    {[75, 60, 85].map((w, i) => (
                                        <div key={i} className="progress-bar">
                                            <div
                                                className={`progress-bar-fill ${i % 2 === 0 ? "progress-bar-fill-primary" : "progress-bar-fill-secondary"}`}
                                                style={{ width: `${w}%` }}
                                            />
                                        </div>
                                    ))}
                                </div>
                                <div className="text-center">
                                    <span className="text-xs text-muted-foreground/50">Preview dimostrativa</span>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                </div>
            </div>
        </section>
    );
}
