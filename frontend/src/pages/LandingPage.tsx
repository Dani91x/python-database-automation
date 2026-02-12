import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { HeroSection } from '@/components/landing/HeroSection';
import { StatsBar } from '@/components/landing/StatsBar';
import { FeaturesGrid } from '@/components/landing/FeaturesGrid';
import { AuthSection } from '@/components/landing/AuthSection';
import { Loader2 } from 'lucide-react';

export default function LandingPage() {
    const { user, loading } = useAuth();
    const navigate = useNavigate();

    useEffect(() => {
        if (!loading && user) {
            navigate('/dashboard', { replace: true });
        }
    }, [user, loading, navigate]);

    if (loading) {
        return (
            <div className="h-screen w-full flex items-center justify-center bg-background">
                <Loader2 className="h-10 w-10 animate-spin text-brand-orange" />
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-background relative overflow-x-hidden">
            {/* Global Background Elements */}
            <div className="fixed inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 pointer-events-none z-50 mix-blend-overlay"></div>

            {/* Content */}
            <main className="relative z-10">
                <HeroSection />
                <StatsBar />
                <FeaturesGrid />

                {/* Pricing / Trial Info */}
                <section className="py-12 section-divider relative">
                    <div className="container mx-auto px-6 text-center">
                        <div className="inline-block glass-card p-8 rounded-3xl border-neon-cyan/30 neon-glow max-w-2xl mx-auto">
                            <span className="bg-neon-cyan/20 text-neon-cyan text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest mb-4 inline-block">
                                Offerta Limitata
                            </span>
                            <h2 className="text-4xl md:text-5xl font-orbitron font-black mb-2">
                                €0 <span className="text-lg text-muted-foreground font-rajdhani font-normal">/ 7 giorni</span>
                            </h2>
                            <p className="text-muted-foreground mb-6">Prova la potenza degli algoritmi senza rischi. Nessuna carta richiesta.</p>
                        </div>
                    </div>
                </section>

                <AuthSection />

                <footer className="py-12 text-center text-sm text-muted-foreground border-t border-white/5">
                    <p>© 2025 AI Football Predictions — Powered by Advanced Algorithms</p>
                </footer>
            </main>
        </div>
    );
}
