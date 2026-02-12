import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { HeroSection } from '@/components/landing/HeroSection';
import { StatsBar } from '@/components/landing/StatsBar';
import { FeaturesGrid } from '@/components/landing/FeaturesGrid';
import { DashboardPreview } from '@/components/landing/DashboardPreview';
import { PricingCard } from '@/components/landing/PricingCard';
import { AuthSection } from '@/components/landing/AuthSection';
import { LandingFooter } from '@/components/landing/LandingFooter';
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
            {/* Grid Pattern Background */}
            <div className="fixed inset-0 pointer-events-none z-0 opacity-[0.03]"
                style={{
                    backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
                                       linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
                    backgroundSize: '40px 40px',
                }}
            />
            {/* Radial gradient overlay */}
            <div className="fixed inset-0 bg-gradient-radial from-transparent via-transparent to-background pointer-events-none z-0" />

            {/* Content */}
            <main className="relative z-10">
                <header>
                    <HeroSection />
                </header>

                <StatsBar />

                <section aria-label="Funzionalità">
                    <FeaturesGrid />
                </section>

                <section aria-label="Preview Dashboard">
                    <DashboardPreview />
                </section>

                <section aria-label="Pricing">
                    <PricingCard />
                </section>

                <section id="auth" aria-label="Registrazione e Login">
                    <AuthSection />
                </section>

                <LandingFooter />
            </main>
        </div>
    );
}
