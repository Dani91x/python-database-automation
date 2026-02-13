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
                    <img src="/logo-alphascore.svg" alt="Alpha Score" className="h-10 md:h-12 w-auto" />
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
                    <h1 className="text-5xl md:text-7xl lg:text-8xl font-display font-black leading-tight mb-4">
                        <span className="text-primary">Alpha</span><span className="text-white">-Score</span>
                    </h1>

                    <h2 className="text-2xl md:text-4xl font-heading font-bold mb-6 text-white leading-tight">
                        Forged by <span className="text-primary">Data</span><br />
                        For <span className="text-white">Investors</span>
                    </h2>

                    <p className="text-lg md:text-xl font-body text-gray-400 max-w-lg mb-10 leading-relaxed">
                        Your ultimate destination for cutting-edge sports data and analytics.
                        Smetti di scommettere, inizia a investire.
                    </p>

                    <div className="flex items-center gap-6">
                        <Button
                            onClick={onCtaClick}
                            size="lg"
                            className="text-lg px-10 py-6 font-heading font-bold rounded-xl bg-primary text-black hover:bg-primary/90 transition-all hover:scale-105 shadow-lg shadow-primary/25"
                        >
                            Get Started
                        </Button>
                    </div>
                </motion.div>

                {/* Right side is intentionally empty to let the background image show through */}
                <div className="hidden md:block"></div>
            </div>
        </section>
    );
}
