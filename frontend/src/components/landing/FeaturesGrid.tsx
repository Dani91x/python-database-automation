import { motion } from "framer-motion";
import { Brain, BarChart3, Shield, Zap } from "lucide-react";

const features = [
    {
        icon: Brain,
        title: "Edge Matematico",
        description:
            "Sfrutta le inefficienze dei bookmaker. Il nostro modello identifica le quote che hanno un valore attesa positivo (EV+).",
        glow: "neon-glow-primary",
    },
    {
        icon: BarChart3,
        title: "Copertura Globale",
        description:
            "120+ Campionati monitorati H24. Dalla Premier League alla Serie B brasiliana, non ti perdi mai un'occasione di profitto.",
        glow: "neon-glow-gold",
    },
    {
        icon: Shield,
        title: "Gestione del Rischio",
        description:
            "Il sistema a 3 livelli filtra i falsi positivi. Non cerchiamo di indovinare tutto, ma di proteggere il tuo capitale nel lungo periodo.",
        glow: "neon-glow-primary",
    },
    {
        icon: Zap,
        title: "Risparmio di Tempo",
        description:
            "Da 4 ore di studio a 30 secondi. Tu devi solo decidere l'investimento, a tutta l'analisi complessa ci pensiamo noi.",
        glow: "neon-glow-gold",
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
                        Perché Alpha Score?
                    </h2>
                    <p className="text-muted-foreground font-heading text-lg max-w-2xl mx-auto">
                        Non siamo un altro sito di statistiche. Siamo il tuo vantaggio competitivo.
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
