import { motion } from "framer-motion";
import { Database, TrendingUp, Sparkles, ArrowRight, ArrowDown } from "lucide-react";

const steps = [
    {
        id: 1,
        title: "Deep Data Analysis",
        subtitle: "Livello 1: L'Algoritmo",
        description: "Analisi grezza di 200+ metriche: xG, Poisson, Form State e trend statistici puri.",
        icon: Database,
        color: "text-blue-400",
        glow: "neon-glow-primary", // mapped to blue-ish primary usually
        borderColor: "border-blue-500/30"
    },
    {
        id: 2,
        title: "Historical Validation",
        subtitle: "Livello 2: La Storia",
        description: "Il database confronta il pronostico con 10 anni di storico: è già successo? Con che esito?",
        icon: TrendingUp,
        color: "text-emerald-400",
        glow: "neon-glow-secondary", // mapped to green-ish often
        borderColor: "border-emerald-500/30"
    },
    {
        id: 3,
        title: "Context Synthesis",
        subtitle: "Livello 3: Il Contesto",
        description: "L'LLM finale incrocia i dati con news, meteo e infortuni dell'ultimo minuto.",
        icon: Sparkles,
        color: "text-purple-400",
        glow: "shadow-[0_0_20px_rgba(168,85,247,0.4)]", // Custom purple glow
        borderColor: "border-purple-500/30"
    }
];

export function SystemWorkflow() {
    return (
        <section className="py-24 px-4 relative overflow-hidden">
            {/* Background elements */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-primary/20 blur-[120px] rounded-full opacity-20 pointer-events-none" />

            <div className="max-w-7xl mx-auto relative z-10">
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    className="text-center mb-16"
                >
                    <h2 className="text-3xl md:text-5xl font-display font-black text-white mb-6">
                        Il Protocollo <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-emerald-400">Alpha</span>
                    </h2>
                    <p className="text-xl text-gray-400 max-w-2xl mx-auto font-light leading-relaxed">
                        Non ci fidiamo di un solo modello. <br />
                        Processiamo ogni partita attraverso <span className="text-white font-bold">3 livelli di validazione</span> prima di darti un consiglio.
                    </p>
                </motion.div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 relative">
                    {/* Connecting Lines for Desktop */}
                    <div className="hidden lg:block absolute top-1/2 left-0 w-full h-1 bg-gradient-to-r from-blue-500/20 via-emerald-500/20 to-purple-500/20 -translate-y-1/2 z-0" />

                    {steps.map((step, index) => (
                        <motion.div
                            key={step.id}
                            initial={{ opacity: 0, y: 30 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: index * 0.2 }}
                            className="relative z-10"
                        >
                            <div className={`glass-card p-8 rounded-3xl border ${step.borderColor} h-full hover:scale-105 transition-transform duration-300 group`}>
                                {/* Step Number Badge */}
                                <div className="absolute -top-4 -right-4 w-12 h-12 rounded-full bg-black/90 border border-white/10 flex items-center justify-center font-display font-bold text-xl text-white shadow-xl">
                                    {step.id}
                                </div>

                                {/* Icon */}
                                <div className={`w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-6 group-hover:${step.glow} transition-all duration-500`}>
                                    <step.icon className={`w-8 h-8 ${step.color}`} />
                                </div>

                                <h4 className={`text-sm font-bold uppercase tracking-widest mb-2 ${step.color}`}>
                                    {step.subtitle}
                                </h4>
                                <h3 className="text-2xl font-display font-bold text-white mb-4">
                                    {step.title}
                                </h3>
                                <p className="text-gray-400 leading-relaxed">
                                    {step.description}
                                </p>
                            </div>

                            {/* Mobile Arrow Connector */}
                            {index < steps.length - 1 && (
                                <div className="flex lg:hidden justify-center py-4">
                                    <ArrowDown className="text-gray-600 w-8 h-8 animate-bounce" />
                                </div>
                            )}

                            {/* Desktop Arrow Connector Overlay */}
                            {index < steps.length - 1 && (
                                <div className="hidden lg:flex absolute top-1/2 -right-4 -translate-y-1/2 z-20 text-gray-500/50">
                                    <ArrowRight className="w-8 h-8" />
                                </div>
                            )}
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
