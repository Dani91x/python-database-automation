import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";

interface HeroSectionProps {
    onCtaClick: () => void;
    onLoginClick: () => void;
}

export function HeroSection({ onCtaClick, onLoginClick }: HeroSectionProps) {
    return (
        <section className="relative min-h-screen flex flex-col overflow-hidden bg-black text-white">
            {/* Navbar */}
            <nav className="absolute top-0 left-0 w-full z-50 px-6 py-6 md:px-12 flex justify-between items-center">
                <div className="flex items-center gap-2">
                    <img src="/logo-alphascore-new.svg" alt="Alpha Score" className="h-10 md:h-12 w-auto" />
                </div>
                <div className="hidden md:flex gap-6">
                    {/* Placeholder links for credibility */}
                    <button onClick={onLoginClick} className="text-sm font-medium text-muted-foreground hover:text-primary transition-colors">
                        Login
                    </button>
                    <Button onClick={onCtaClick} variant="default" size="sm" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold rounded-full px-6">
                        Get Started
                    </Button>
                </div>
            </nav>

            {/* Cinematic Background Fallback (CSS) */}
            <div className="absolute inset-0 z-0">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/20 via-black to-black opacity-60"></div>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom_left,_var(--tw-gradient-stops))] from-secondary/10 via-black to-black opacity-40"></div>
                <div className="absolute inset-0 grid-pattern opacity-10" />
            </div>

            <div className="relative z-10 container mx-auto px-4 flex-1 flex flex-col justify-center items-start mt-20 md:mt-0">
                <motion.div
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    className="max-w-4xl"
                >
                    <div className="mb-6">
                        <span className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-xs font-bold tracking-wider text-primary uppercase backdrop-blur-md">
                            Data-Driven Football Analysis
                        </span>
                    </div>

                    <h1 className="text-5xl md:text-7xl lg:text-8xl font-display font-black leading-tight mb-6">
                        <span className="text-white">ALPHA</span> <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-emerald-400">SCORE</span>
                    </h1>

                    <p className="text-2xl md:text-4xl font-heading font-light mb-8 text-white/90">
                        Don't bet. <span className="font-bold text-secondary">Invest.</span>
                    </p>

                    <p className="text-lg md:text-xl font-body text-muted-foreground max-w-2xl mb-10 leading-relaxed">
                        L'unico algoritmo che trasforma le scommesse sportive in <span className="text-white font-medium">investimenti basati sui dati</span>.
                        Analisi predittiva avanzata per chi non cerca fortuna, ma risultati.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center gap-6">
                        <Button
                            onClick={onCtaClick}
                            size="lg"
                            className="text-lg px-12 py-8 font-heading font-bold pulse-glow neon-glow-primary rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-all hover:scale-105"
                        >
                            INIZIA ORA
                        </Button>
                        <Button
                            onClick={onLoginClick}
                            variant="ghost"
                            size="lg"
                            className="text-lg font-heading text-white hover:text-primary transition-colors flex items-center gap-2"
                        >
                            Accedi alla Dashboard <ChevronDown className="w-4 h-4 -rotate-90" />
                        </Button>
                    </div>
                </motion.div>
            </div>
        </section>
    );
}
