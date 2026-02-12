import { motion } from 'framer-motion';
import { Check } from 'lucide-react';

const features = [
    "Pronostico AI con advice e percentuali 1X2",
    "Statistiche dettagliate Home vs Away",
    "Grafici goals by minute e cards heatmap",
    "Confronto squadre con matrice comparativa",
    "Distribuzione Under/Over per soglia",
    "Formazioni, streak, clean sheet e rigori",
];

export function DashboardPreview() {
    return (
        <section className="py-24 relative">
            <div className="container mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6 }}
                    className="glass-card animated-border p-10 rounded-[2rem] max-w-4xl mx-auto"
                >
                    <h2 className="font-rajdhani text-2xl md:text-3xl font-bold text-center mb-2 text-white">
                        Una dashboard completa per ogni partita
                    </h2>
                    <p className="text-center text-muted-foreground text-sm mb-10">
                        Tutto ciò che ti serve per analizzare, confrontare e decidere.
                    </p>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-10">
                        {features.map((feat, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, x: -10 }}
                                whileInView={{ opacity: 1, x: 0 }}
                                viewport={{ once: true }}
                                transition={{ duration: 0.4, delay: i * 0.08 }}
                                className="flex items-start gap-3"
                            >
                                <div className="w-5 h-5 rounded-full bg-neon-cyan/20 flex items-center justify-center shrink-0 mt-0.5">
                                    <Check className="w-3 h-3 text-neon-cyan" />
                                </div>
                                <span className="text-sm text-white/80">{feat}</span>
                            </motion.div>
                        ))}
                    </div>

                    {/* Mockup stilizzato della dashboard */}
                    <div className="glass-card rounded-xl p-6 bg-gradient-to-br from-white/[0.03] to-transparent border-white/5">
                        <div className="flex items-center gap-2 mb-4">
                            <div className="w-3 h-3 rounded-full bg-red-500/50" />
                            <div className="w-3 h-3 rounded-full bg-yellow-500/50" />
                            <div className="w-3 h-3 rounded-full bg-green-500/50" />
                            <span className="text-[10px] text-muted-foreground ml-2 font-mono">dashboard.ai-predictions.app</span>
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <div className="bg-neon-cyan/5 border border-neon-cyan/10 rounded-lg p-4 col-span-2 h-24 flex items-center justify-center">
                                <span className="text-xs text-neon-cyan/50 font-mono">HERO MATCH — Club Brugge vs Marseille</span>
                            </div>
                            <div className="bg-brand-orange/5 border border-brand-orange/10 rounded-lg p-4 h-24 flex items-center justify-center">
                                <span className="text-xs text-brand-orange/50 font-mono">AI ENGINE</span>
                            </div>
                            <div className="bg-white/5 border border-white/5 rounded-lg p-3 h-16 flex items-center justify-center">
                                <span className="text-[10px] text-white/30 font-mono">HOME STATS</span>
                            </div>
                            <div className="bg-white/5 border border-white/5 rounded-lg p-3 h-16 flex items-center justify-center">
                                <span className="text-[10px] text-white/30 font-mono">COMPARISON</span>
                            </div>
                            <div className="bg-white/5 border border-white/5 rounded-lg p-3 h-16 flex items-center justify-center">
                                <span className="text-[10px] text-white/30 font-mono">AWAY STATS</span>
                            </div>
                        </div>
                    </div>
                </motion.div>
            </div>
        </section>
    );
}
