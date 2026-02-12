import { useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { normalizePredictionJson, NormalizedData } from '@/lib/normalize';
import { HeroMatch } from '@/components/dashboard/HeroMatch';
import { PredictionsCard } from '@/components/dashboard/PredictionsCard';
import { TeamPanel } from '@/components/dashboard/TeamPanel';
import { ComparisonSection } from '@/components/dashboard/ComparisonSection';
import { H2HSection } from '@/components/dashboard/H2HSection';
import { Button } from '@/components/ui/button';
import { Loader2, LogOut, RefreshCw } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

export default function Dashboard() {
    const [data, setData] = useState<NormalizedData | null>(null);
    const [loading, setLoading] = useState(true);
    const { user } = useAuth();
    const navigate = useNavigate();

    // Fetch Data Logic
    const fetchData = async () => {
        setLoading(true);
        try {
            // 1. Cerchiamo l'ultimo pronostico disponibile
            const { data: fixtures, error } = await supabase
                .from('fixture_predictions')
                .select('raw_json, fixture_id')
                .order('match_date', { ascending: false })
                .limit(1)
                .single();

            if (error) throw error;

            if (fixtures && fixtures.raw_json) {
                const normalized = normalizePredictionJson(fixtures.raw_json, fixtures.fixture_id);
                setData(normalized);
            } else {
                toast("Nessun pronostico trovato.");
            }

        } catch (error: any) {
            console.error(error);
            toast.error("Errore caricamento dashboard", { description: error.message });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleLogout = async () => {
        await supabase.auth.signOut();
        navigate('/');
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Loader2 className="w-12 h-12 text-brand-orange animate-spin" />
            </div>
        );
    }

    if (!data) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center bg-background text-white">
                <p>Nessun dato disponibile.</p>
                <Button onClick={fetchData} variant="outline" className="mt-4">
                    <RefreshCw className="mr-2 h-4 w-4" /> Riprova
                </Button>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background relative pb-24">
            {/* Navbar / Header */}
            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="font-orbitron font-black text-xl tracking-tighter">
                        AI <span className="text-brand-orange">TERMINAL</span>
                    </div>
                    <div className="flex items-center gap-4">
                        <span className="text-xs text-muted-foreground hidden md:inline-block">
                            Logged in as {user?.email}
                        </span>
                        <Button variant="ghost" size="sm" onClick={handleLogout} className="hover:bg-red-500/10 hover:text-red-500">
                            <LogOut className="w-4 h-4 mr-2" />
                            Esci
                        </Button>
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 py-8 max-w-7xl animate-fade-in-up">

                <HeroMatch
                    home={data.home}
                    away={data.away}
                    league={data.league}
                    prediction={data.predictions}
                    matchDate={undefined} // Se avessimo la data grezza
                />

                <PredictionsCard
                    predictions={data.predictions}
                    home={data.home}
                    away={data.away}
                />

                <div className="flex flex-col xl:flex-row gap-8 mb-12">
                    <TeamPanel team={data.home} side="home" />

                    {/* Comparison in Middle on Desktop? Or Full Width below? Let's clean layout */}
                    <div className="w-full xl:w-px xl:bg-white/5 xl:self-stretch hidden xl:block" />

                    <TeamPanel team={data.away} side="away" />
                </div>

                <ComparisonSection comparison={data.comparison} />

                <H2HSection h2h={data.h2h} />

            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>Fixture ID: {data.fixtureId} • Neural Engine v4.0 Output • Generated at {new Date().toLocaleTimeString()}</p>
            </footer>
        </div>
    );
}
