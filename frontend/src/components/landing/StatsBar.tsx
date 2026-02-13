import { motion } from "framer-motion";

const stats = [
    { value: "50.000+", label: "Pronostici Generati" },
    { value: "87%", label: "Accuratezza Media" },
    { value: "120+", label: "Campionati Analizzati" },
    { value: "Real-Time", label: "Aggiornamento Dati" },
];

export function StatsBar() {
    return (
        <section className="py-12 px-4">
            <div className="max-w-6xl mx-auto">
                <div className="glass-card p-8 rounded-2xl">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
                        {stats.map((stat, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.1, duration: 0.5 }}
                                className="text-center"
                            >
                                <div className="stat-value mb-2">{stat.value}</div>
                                <div className="stat-label">{stat.label}</div>
                            </motion.div>
                        ))}
                    </div>
                    <p className="text-center text-xs text-muted-foreground/50 mt-6">* Valori dimostrativi basati su backtesting storico</p>
                </div>
            </div>
        </section>
    );
}
