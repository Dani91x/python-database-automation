import { motion } from "framer-motion";
import { Brain, BarChart3, Shield, Zap } from "lucide-react";

const features = [
    {
        icon: Brain,
        title: "Analisi AI Avanzata",
        description:
            "I nostri algoritmi di machine learning analizzano oltre 200 variabili per partita: forma, statistiche, head-to-head, distribuzione Poisson e molto altro.",
        glow: "neon-glow-cyan",
    },
    {
        icon: BarChart3,
        title: "Dati in Tempo Reale",
        description:
            "Dati aggiornati da 120+ campionati mondiali. Goals by minute, cards heatmap, under/over distribution — tutto visualizzato in una dashboard interattiva.",
        glow: "neon-glow-magenta",
    },
    {
        icon: Shield,
        title: "Confronto Intelligente",
        description:
            "Confronto squadre automatico su attacco, difesa, forma e storico H2H con barre comparative e insight generati dall'AI.",
        glow: "neon-glow-cyan",
    },
    {
        icon: Zap,
        title: "Velocità e Precisione",
        description:
            "Pronostici generati in millisecondi con percentuali 1X2, combo double chance, predicted goals e suggerimenti actionable.",
        glow: "neon-glow-magenta",
    },
];

export function FeaturesGrid() {
    return (
        <section className="py-20 px-4">
            <div className="max-w-6xl mx-auto">
                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    className="text-center mb-14"
                >
                    <h2 className="text-3xl md:text-4xl font-display font-bold text-gradient-primary mb-4">
                        Come Funziona
                    </h2>
                    <p className="text-muted-foreground font-heading text-lg max-w-2xl mx-auto">
                        Tecnologia all'avanguardia al servizio dei tuoi pronostici
                    </p>
                </motion.div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {features.map((f, i) => (
                        <motion.div
                            key={f.title}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.1, duration: 0.5 }}
                            className={`glass-card hover-lift p-8 rounded-2xl`}
                        >
                            <div className={`glass-card p-3 rounded-xl w-fit mb-5 ${f.glow}`}>
                                <f.icon className="w-7 h-7 text-primary" />
                            </div>
                            <h3 className="text-xl font-heading font-bold text-foreground mb-3">{f.title}</h3>
                            <p className="text-muted-foreground leading-relaxed">{f.description}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
