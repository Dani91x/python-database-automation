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
        <header className="relative pt-40 pb-24 overflow-hidden">
            {/* Background Gradients */}
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-brand-orange/[0.07] blur-[150px] rounded-full animate-pulse" />
                <div className="absolute bottom-[-5%] right-[-5%] w-[40%] h-[40%] bg-brand-orange/[0.05] blur-[120px] rounded-full animate-pulse" style={{ animationDelay: '2s' }} />
            </div>

            <div className="container mx-auto px-6 relative z-10 text-center">
                {/* Badge */}
                <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[10px] font-black uppercase tracking-[0.2em] text-brand-orange mb-8 animate-fade-in mx-auto">
                    <Cpu className="w-3 h-3" />
                    Proprietary Neural Engine v4.0 is Live
                </div>

                {/* Headline */}
                <h1 className="text-6xl md:text-8xl lg:text-9xl font-black tracking-tighter uppercase italic leading-[0.85] mb-8 animate-fade-in-up">
                    Il Profitto è <br />
                    <span className="text-brand-orange">Calcolabile.</span>
                </h1>

                {/* Subtitle */}
                <p className="max-w-2xl mx-auto text-lg md:text-xl text-muted-foreground font-medium leading-relaxed mb-12 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
                    Il primo terminale di investimento sportivo potenziato da modelli di deep-learning.
                    Non scommettiamo. Arbitriamo discrepanze statistiche nei campionati competitivi.
                </p>

                {/* CTAs */}
                <div className="flex flex-col sm:flex-row items-center justify-center gap-6 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
                    <Button
                        size="lg"
                        onClick={scrollToAuth}
                        className="w-full sm:w-auto bg-brand-orange text-black font-black uppercase tracking-[0.1em] hover:bg-white transition-all neon-glow"
                    >
                        Inizia la Prova Gratuita — 7 Giorni
                        <ArrowRight className="ml-2 w-4 h-4" />
                    </Button>

                    <button
                        onClick={scrollToAuth}
                        className="text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-white transition-colors border-b border-transparent hover:border-brand-orange"
                    >
                        Hai già un account? Accedi
                    </button>
                </div>
            </div>
        </header>
    );
}
