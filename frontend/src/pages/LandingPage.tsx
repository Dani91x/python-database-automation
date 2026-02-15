import { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { HeroSection } from '@/components/landing/HeroSection';
import { StatsBar } from '@/components/landing/StatsBar';
import { FeaturesGrid } from '@/components/landing/FeaturesGrid';
import { SystemWorkflow } from '@/components/landing/SystemWorkflow';
import { DashboardPreview } from '@/components/landing/DashboardPreview';
import { PricingCard } from '@/components/landing/PricingCard';
import { AuthSection } from '@/components/landing/AuthSection';
import { LandingFooter } from '@/components/landing/LandingFooter';

export default function LandingPage() {
    const authRef = useRef<HTMLDivElement>(null);
    const { user, loading } = useAuth();
    const navigate = useNavigate();

    useEffect(() => {
        if (!loading && user) {
            navigate('/dashboard', { replace: true });
        }
    }, [user, loading, navigate]);

    const scrollToAuth = () => {
        authRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    if (loading) return null;

    return (
        <div className="min-h-screen bg-background">
            <HeroSection
                onCtaClick={() => scrollToAuth()}
                onLoginClick={() => scrollToAuth()}
            />
            <StatsBar />
            <SystemWorkflow />
            <FeaturesGrid />
            <DashboardPreview />
            <PricingCard onCtaClick={() => scrollToAuth()} />
            <AuthSection ref={authRef} />
            <LandingFooter />
        </div>
    );
}
