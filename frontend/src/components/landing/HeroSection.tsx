import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";

interface HeroSectionProps {
    onCtaClick: () => void;
    onLoginClick: () => void;
}

export function HeroSection({ onCtaClick, onLoginClick }: HeroSectionProps) {
    return (
        <section className="relative min-h-screen flex flex-col justify-center overflow-hidden bg-black text-white">
            {/* Navbar */}
            <nav className="absolute top-0 left-0 w-full z-50 px-6 py-6 md:px-12 flex justify-between items-center bg-transparent">
                <div className="flex items-center gap-2">
                    <img src="/9511045.png" alt="Alpha Score" className="h-12 md:h-16 w-auto" />
                </div>
                <div className="hidden md:flex gap-8 items-center">
                    <button onClick={onLoginClick} className="text-sm font-bold uppercase tracking-widest text-white hover:text-primary transition-colors">
                        Login
                    </button>
                    <button className="text-sm font-bold uppercase tracking-widest text-white hover:text-primary transition-colors">
                        Register
                    </button>
                </div>
            </nav>

            {/* Background Image & Overlay */}
            <div className="absolute inset-0 z-0">
                <div className="absolute inset-0 bg-[url('/futuristic-football-game-ball.jpg')] bg-cover bg-center bg-no-repeat opacity-60"></div>

                {/* Gradient Overlay for Text Readability (Left-to-Right) */}
                <div className="absolute inset-0 bg-gradient-to-r from-black via-black/90 to-transparent"></div>

                {/* Subtle Grid Pattern */}
                <div className="absolute inset-0 grid-pattern opacity-10" />
            </div>

            <div className="relative z-10 container mx-auto px-6 md:px-12 grid grid-cols-1 md:grid-cols-2 gap-12 mt-20 md:mt-0">
                <motion.div
                    initial={{ opacity: 0, x: -30 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.8 }}
                    className="flex flex-col justify-center items-start text-left"
                >
                    <div className="mb-6">
                        <span className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-xs font-bold tracking-wider text-primary uppercase backdrop-blur-md">
                            Data-Driven Football Analysis
                        </span>
                    </div>

                    <h1 className="text-5xl md:text-7xl lg:text-8xl font-display font-black leading-tight mb-6">
                        <span className="text-white">ALPHA</span> <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-emerald-400">SCORE</span>
                    </h1>

                    <h2 className="text-2xl md:text-4xl font-heading font-light mb-8 text-white/90">
                        Don't bet. <span className="font-bold text-secondary">Invest.</span>
                    </h2>

                    <p className="text-lg md:text-xl font-body text-gray-400 max-w-lg mb-10 leading-relaxed">
                        L'unico algoritmo che trasforma le scommesse sportive in <span className="text-white font-medium">investimenti basati sui dati</span>.
                        Analisi predittiva avanzata per chi non cerca fortuna, ma risultati.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center gap-6">
                        <Button
                            onClick={onCtaClick}
                            size="lg"
                            className="text-lg px-10 py-6 font-heading font-bold rounded-xl bg-primary text-black hover:bg-primary/90 transition-all hover:scale-105 shadow-lg shadow-primary/25"
                        >
                            INIZIA ORA
                        </Button>
                        <Button
                            onClick={onLoginClick}
                            variant="ghost"
                            size="lg"
                            className="text-lg font-heading text-white hover:text-primary transition-colors flex items-center gap-2"
                        >
                            Accedi alla Dashboard
                        </Button>
                    </div>
                </motion.div>

                {/* Right side is intentionally empty to let the background image show through */}
                <div className="hidden md:block"></div>
            </div>
        </section>
    );
}
