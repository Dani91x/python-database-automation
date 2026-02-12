import { motion } from 'framer-motion';
import { ArrowRight, Cpu } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function HeroSection() {
    const scrollToAuth = () => {
        const authSection = document.getElementById('auth');
        if (authSection) {
            authSection.scrollIntoView({ behavior: 'smooth' });
        }
    };

    return (
        <div className="relative pt-40 pb-24 overflow-hidden">
            {/* Background Gradients */}
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-brand-orange/[0.07] blur-[150px] rounded-full animate-pulse" />
                <div className="absolute bottom-[-5%] right-[-5%] w-[40%] h-[40%] bg-brand-orange/[0.05] blur-[120px] rounded-full animate-pulse" style={{ animationDelay: '2s' }} />
            </div>

            <div className="container mx-auto px-6 relative z-10 text-center">
                {/* Badge */}
                <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[10px] font-black uppercase tracking-[0.2em] text-brand-orange mb-8 mx-auto"
                >
                    <Cpu className="w-3 h-3" />
                    Proprietary Neural Engine v4.0 is Live
                </motion.div>

                {/* Headline */}
                <motion.h1
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, delay: 0.1 }}
                    className="text-4xl md:text-6xl lg:text-7xl font-orbitron font-black tracking-tighter leading-[0.9] mb-8"
                >
                    Pronostici Calcistici{' '}
                    <span className="text-gradient-primary">Potenziati dall'AI</span>
                </motion.h1>

                {/* Subtitle */}
                <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.2 }}
                    className="max-w-2xl mx-auto text-lg md:text-xl text-muted-foreground font-rajdhani font-medium leading-relaxed mb-12"
                >
                    Algoritmi avanzati analizzano migliaia di dati in tempo reale per darti il vantaggio decisivo
                </motion.p>

                {/* CTAs */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.3 }}
                    className="flex flex-col sm:flex-row items-center justify-center gap-6"
                >
                    <Button
                        size="lg"
                        onClick={scrollToAuth}
                        className="w-full sm:w-auto bg-brand-orange text-black font-black uppercase tracking-[0.1em] hover:bg-white transition-all neon-glow pulse-glow"
                        aria-label="Inizia la prova gratuita di 7 giorni"
                    >
                        Inizia la Prova Gratuita — 7 Giorni
                        <ArrowRight className="ml-2 w-4 h-4" />
                    </Button>

                    <button
                        onClick={scrollToAuth}
                        className="text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-white transition-colors border-b border-transparent hover:border-brand-orange"
                        aria-label="Vai al form di login"
                    >
                        Hai già un account? Accedi
                    </button>
                </motion.div>
            </div>
        </div>
    );
}
