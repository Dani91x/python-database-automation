import { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { supabase } from '@/integrations/supabase/client';
import { normalizePredictionJson, NormalizedData } from '@/lib/normalize';
import { MOCK_RAW_JSON } from '@/lib/mockData';
import { HeroMatch } from '@/components/dashboard/HeroMatch';
import { PredictionsCard } from '@/components/dashboard/PredictionsCard';
import { TeamPanel } from '@/components/dashboard/TeamPanel';
import { ComparisonSection } from '@/components/dashboard/ComparisonSection';
import { H2HSection } from '@/components/dashboard/H2HSection';
import { FixtureSelector } from '@/components/dashboard/FixtureSelector';
import { Button } from '@/components/ui/button';
import { Loader2, LogOut, RefreshCw } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

export default function Dashboard() {
    const [data, setData] = useState<NormalizedData | null>(null);
    const [loading, setLoading] = useState(true);
    const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(null);
    const { user } = useAuth();
    const navigate = useNavigate();

    // Fetch latest fixture (initial load)
    const fetchLatest = async () => {
        setLoading(true);
        try {
            const { data: fixtures, error } = await supabase
                .from('fixture_predictions')
                .select('raw_json, fixture_id')
                .order('fixture_id', { ascending: false })
                .limit(1)
                .single();

            if (error) throw error;

            if (fixtures && fixtures.raw_json) {
                const fid = String(fixtures.fixture_id);
                const normalized = normalizePredictionJson(fixtures.raw_json, fid);
                setData(normalized);
                setSelectedFixtureId(fid);
            } else {
                toast("Nessun pronostico trovato. Uso dati demo.");
                const normalized = normalizePredictionJson(MOCK_RAW_JSON, 'DEMO');
                setData(normalized);
                setSelectedFixtureId('DEMO');
            }
        } catch (error: any) {
            console.error(error);
            toast.error("Errore caricamento — uso dati demo", { description: error.message });
            const normalized = normalizePredictionJson(MOCK_RAW_JSON, 'DEMO');
            setData(normalized);
            setSelectedFixtureId('DEMO');
        } finally {
            setLoading(false);
        }
    };

    // Fetch a specific fixture by ID
    const loadFixture = async (fixtureId: string) => {
        setLoading(true);
        try {
            const { data: fixture, error } = await supabase
                .from('fixture_predictions')
                .select('raw_json, fixture_id')
                .eq('fixture_id', fixtureId)
                .single();

            if (error) throw error;

            if (fixture && fixture.raw_json) {
                const normalized = normalizePredictionJson(fixture.raw_json, String(fixture.fixture_id));
                setData(normalized);
                setSelectedFixtureId(String(fixture.fixture_id));
            }
        } catch (error: any) {
            console.error(error);
            toast.error("Errore caricamento partita", { description: error.message });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLatest();
    }, []);

    const handleLogout = async () => {
        await supabase.auth.signOut();
        navigate('/');
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Loader2 className="w-12 h-12 text-primary animate-spin" />
            </div>
        );
    }

    if (!data) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center bg-background text-foreground">
                <div className="glass-card p-8 text-center">
                    <h1 className="font-display text-2xl font-bold text-destructive mb-2">
                        Nessun dato disponibile
                    </h1>
                    <p className="text-muted-foreground mb-4">Impossibile caricare i dati del pronostico.</p>
                    <Button onClick={fetchLatest} variant="outline" className="mt-4" aria-label="Ricarica dati">
                        <RefreshCw className="mr-2 h-4 w-4" /> Riprova
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet>
                <title>{data.home.name} vs {data.away.name} | Alpha Score Analysis</title>
                <meta name="description" content={`Pronostico dettagliato per ${data.home.name} vs ${data.away.name} in ${data.league.name}. Scopri le probabilità di vittoria, statistiche e insight dell'AI.`} />
            </Helmet>

            {/* Grid pattern */}
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            {/* Navbar */}
            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50" role="navigation" aria-label="Dashboard navigation">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="font-display font-black text-xl tracking-tighter">
                        AI <span className="text-primary">TERMINAL</span>
                    </div>
                    <div className="flex items-center gap-4">
                        <Button variant="ghost" size="sm" onClick={fetchLatest} className="text-muted-foreground hover:text-white" aria-label="Aggiorna dati">
                            <RefreshCw className="w-4 h-4" />
                        </Button>
                        <span className="text-xs text-muted-foreground hidden md:inline-block">
                            {user?.email}
                        </span>
                        <Button variant="ghost" size="sm" onClick={handleLogout} className="hover:bg-red-500/10 hover:text-red-500" aria-label="Logout">
                            <LogOut className="w-4 h-4 mr-2" />
                            Esci
                        </Button>
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 py-8 max-w-7xl relative z-10">

                {/* Fixture Selector */}
                <div className="mb-8">
                    <FixtureSelector
                        currentFixtureId={selectedFixtureId || undefined}
                        onSelect={loadFixture}
                    />
                </div>

                <HeroMatch
                    home={data.home}
                    away={data.away}
                    league={data.league}
                    prediction={data.predictions}
                    matchDate={undefined}
                />

                <PredictionsCard
                    predictions={data.predictions}
                    home={data.home}
                    away={data.away}
                />

                <div className="flex flex-col xl:flex-row gap-8 mb-12">
                    <TeamPanel team={data.home} side="home" />
                    <div className="w-full xl:w-px xl:bg-white/5 xl:self-stretch hidden xl:block" />
                    <TeamPanel team={data.away} side="away" />
                </div>

                <ComparisonSection
                    comparison={data.comparison}
                    homeName={data.home.name}
                    awayName={data.away.name}
                />

                <H2HSection h2h={data.h2h} />

            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>
                    Dati aggiornati • Fixture ID: {data.fixtureId} • {data.league.name} {data.league.season}
                </p>
            </footer>
        </div>
    );
}
