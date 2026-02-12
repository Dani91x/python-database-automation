import { motion } from "framer-motion";
import { Brain, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";

interface HeroSectionProps {
    onCtaClick: () => void;
    onLoginClick: () => void;
}

export function HeroSection({ onCtaClick, onLoginClick }: HeroSectionProps) {
    return (
        <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
            {/* Background effects */}
            <div className="absolute inset-0 bg-gradient-hero" />
            <div className="absolute inset-0 grid-pattern opacity-30" />
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-primary/5 blur-[120px]" />
            <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full bg-secondary/5 blur-[100px]" />

            <div className="relative z-10 max-w-5xl mx-auto px-4 text-center">
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                >
                    <div className="flex items-center justify-center gap-3 mb-6">
                        <div className="glass-card p-3 rounded-xl neon-glow-cyan">
                            <Brain className="w-8 h-8 text-primary" />
                        </div>
                        <span className="home-badge text-sm">AI-POWERED</span>
                    </div>

                    <h1 className="text-4xl md:text-6xl lg:text-7xl font-display font-bold leading-tight mb-6">
                        <span className="text-gradient-primary">Pronostici Calcistici</span>
                        <br />
                        <span className="text-foreground">Potenziati dall'</span>
                        <span className="text-gradient-secondary">Intelligenza Artificiale</span>
                    </h1>

                    <p className="text-lg md:text-xl font-heading text-muted-foreground max-w-3xl mx-auto mb-10 leading-relaxed">
                        Algoritmi avanzati analizzano <span className="text-primary font-semibold">migliaia di dati in tempo reale</span> —
                        forma, head-to-head, distribuzione Poisson, goals by minute — per darti il{" "}
                        <span className="text-secondary font-semibold">vantaggio decisivo</span> su ogni partita.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                        <Button
                            onClick={onCtaClick}
                            size="lg"
                            className="text-lg px-10 py-6 font-heading font-bold pulse-glow neon-glow-cyan rounded-xl bg-primary text-primary-foreground hover:bg-primary/90"
                        >
                            Inizia la Prova Gratuita — 7 Giorni
                        </Button>
                        <Button
                            onClick={onLoginClick}
                            variant="ghost"
                            size="lg"
                            className="text-lg font-heading text-muted-foreground hover:text-primary"
                        >
                            Hai già un account? Accedi →
                        </Button>
                    </div>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 1.2, duration: 0.8 }}
                    className="absolute bottom-8 left-1/2 -translate-x-1/2"
                >
                    <ChevronDown className="w-6 h-6 text-muted-foreground animate-bounce" />
                </motion.div>
            </div>
        </section>
    );
}
