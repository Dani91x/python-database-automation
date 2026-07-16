import { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { supabase } from '@/integrations/supabase/client';
import { normalizePredictionJson, NormalizedData } from '@/lib/normalize';
import { HeroMatch } from '@/components/dashboard/HeroMatch';
import { PredictionsCard } from '@/components/dashboard/PredictionsCard';
import { TeamPanel } from '@/components/dashboard/TeamPanel';
import { ComparisonSection } from '@/components/dashboard/ComparisonSection';
import { H2HSection } from '@/components/dashboard/H2HSection';
import { Button } from '@/components/ui/button';
import { Loader2, LogOut, ChevronLeft, BarChart3, Bookmark, Wallet, Radio, History, LayoutGrid } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { MatchesList } from '@/components/dashboard/MatchesList';
import { AnalyticsPanels } from '@/components/dashboard/AnalyticsPanels';

export default function Dashboard() {
    const [viewMode, setViewMode] = useState<'list' | 'detail'>('list');
    const [data, setData] = useState<NormalizedData | null>(null);
    // league_id/season_year letti esplicitamente dalla riga DB (non da raw_json: fragile)
    const [fixtureLeagueId, setFixtureLeagueId] = useState<number | null>(null);
    const [loading, setLoading] = useState(false);

    const { user } = useAuth();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    // se siamo arrivati dalla watchlist (deep-link "Vai alle statistiche") mostriamo
    // un ritorno diretto alla watchlist, oltre al "Torna alle partite" standard.
    // Snapshot UNA SOLA VOLTA al mount: le navigazioni interne (selezione di un'altra
    // partita dalla lista) NON cambiano l'URL, quindi una lettura reattiva di
    // searchParams lascerebbe il bottone "Torna a Watchlist" anche su match aperte
    // dalla lista. Catturare al mount evita questo falso positivo.
    const [cameFromWatchlist] = useState(() => searchParams.get('from') === 'watchlist');
    // idem per Omega: "Vai alle statistiche" da /omega → bottone "Torna a Omega"
    const [cameFromOmega] = useState(() => searchParams.get('from') === 'omega');

    // Fetch a specific fixture by ID
    const loadFixture = async (fixtureId: string) => {
        if (!/^\d+$/.test(fixtureId)) {
            toast.error("ID partita non valido.");
            return;
        }
        setLoading(true);
        try {
            const { data: fixture, error } = await supabase
                .from('fixture_predictions')
                .select('raw_json, fixture_id, league_id')
                .eq('fixture_id', fixtureId)
                .single();

            if (error) throw error;

            if (fixture && fixture.raw_json) {
                const normalized = normalizePredictionJson(fixture.raw_json, String(fixture.fixture_id));
                setData(normalized);
                setFixtureLeagueId(fixture.league_id ?? null);
                setViewMode('detail');
            }
        } catch (error: any) {
            console.error(error);
            toast.error("Errore caricamento partita", { description: error.message });
        } finally {
            setLoading(false);
        }
    };

    // Deep-link dal bot Telegram: /dashboard?fixture=<id> apre direttamente la scheda partita
    useEffect(() => {
        const fx = searchParams.get('fixture');
        if (fx) {
            loadFixture(fx);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleLogout = async () => {
        await supabase.auth.signOut();
        navigate('/');
    };

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet>
                <title>
                    {viewMode === 'list'
                        ? 'Partite del Giorno | Alpha Score'
                        : data
                            ? `${data.home.name} vs ${data.away.name} | Alpha Score Analysis`
                            : 'Dashboard | Alpha Score'}
                </title>
            </Helmet>

            {/* Grid pattern */}
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            {/* Navbar */}
            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50" role="navigation" aria-label="Dashboard navigation">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="font-display font-black text-xl tracking-tighter cursor-pointer" onClick={() => setViewMode('list')}>
                            AI <span className="text-primary">TERMINAL</span>
                        </div>

                        {viewMode === 'detail' && (
                            <>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setViewMode('list')}
                                    className="hidden md:flex items-center gap-2 border-white/10 text-muted-foreground hover:text-white ml-6"
                                >
                                    <ChevronLeft className="w-4 h-4" />
                                    Torna alle partite
                                </Button>
                                {cameFromWatchlist && (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => navigate('/watchlist')}
                                        className="hidden md:flex items-center gap-2 border-amber-400/30 text-amber-300 hover:bg-amber-400/10"
                                    >
                                        <ChevronLeft className="w-4 h-4" />
                                        Torna a Watchlist
                                    </Button>
                                )}
                                {cameFromOmega && (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => navigate('/omega')}
                                        className="hidden md:flex items-center gap-2 border-secondary/30 text-secondary hover:bg-secondary/10"
                                    >
                                        <ChevronLeft className="w-4 h-4" />
                                        Torna a Omega
                                    </Button>
                                )}
                            </>
                        )}
                    </div>

                    <div className="flex items-center gap-4">
                        {/* come TennisNav: ritorno rapido allo Sport Selector */}
                        <Button variant="outline" size="sm" onClick={() => navigate('/select-sport')}
                            className="border-secondary/30 text-secondary hover:bg-secondary/10" aria-label="Cambia sport">
                            <LayoutGrid className="w-4 h-4 md:mr-2" />
                            <span className="hidden md:inline">Cambia sport</span>
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => navigate('/watchlist')}
                            className="border-amber-400/30 text-amber-300 hover:bg-amber-400/10" aria-label="Watchlist">
                            <Bookmark className="w-4 h-4 md:mr-2" />
                            <span className="hidden md:inline">Watchlist</span>
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => navigate('/report-personale')}
                            className="border-primary/30 text-primary hover:bg-primary/10" aria-label="Report Personale">
                            <Wallet className="w-4 h-4 md:mr-2" />
                            <span className="hidden md:inline">Report</span>
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => navigate('/analytics')}
                            className="border-primary/30 text-primary hover:bg-primary/10" aria-label="Analytics">
                            <BarChart3 className="w-4 h-4 md:mr-2" />
                            <span className="hidden md:inline">Analytics</span>
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => navigate('/segui-live')}
                            className="border-primary/30 text-primary hover:bg-primary/10" aria-label="Segui Live">
                            <Radio className="w-4 h-4 md:mr-2" />
                            <span className="hidden md:inline">Segui Live</span>
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => navigate('/match-replay')}
                            className="border-secondary/30 text-secondary hover:bg-secondary/10" aria-label="Match Replay">
                            <History className="w-4 h-4 md:mr-2" />
                            <span className="hidden md:inline">Match Replay</span>
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

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10 w-full overflow-hidden">

                {viewMode === 'list' ? (
                    <MatchesList onSelectMatch={loadFixture} />
                ) : (
                    <>
                        {loading && (
                            <div className="flex items-center justify-center py-20">
                                <Loader2 className="w-12 h-12 text-primary animate-spin" />
                            </div>
                        )}

                        {!loading && data && (
                            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                                <div className="mb-6 flex flex-wrap md:hidden items-center gap-2">
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => setViewMode('list')}
                                        className="gap-2 text-muted-foreground hover:text-white -ml-2"
                                    >
                                        <ChevronLeft className="w-4 h-4" />
                                        Torna alla lista
                                    </Button>
                                    {cameFromWatchlist && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => navigate('/watchlist')}
                                            className="gap-2 text-amber-300 hover:bg-amber-400/10"
                                        >
                                            <ChevronLeft className="w-4 h-4" />
                                            Torna a Watchlist
                                        </Button>
                                    )}
                                </div>

                                <HeroMatch
                                    home={data.home}
                                    away={data.away}
                                    league={data.league}
                                    prediction={data.predictions}
                                    fixtureId={data.fixtureId}
                                    leagueId={fixtureLeagueId ?? data.league.id}
                                />

                                {/* Analisi motori: Frequenze Mercati + Poisson + Modelli ML, subito sotto Fixture/League ID */}
                                <AnalyticsPanels
                                    leagueId={fixtureLeagueId ?? data.league.id ?? null}
                                    leagueName={data.league.name}
                                    fixtureId={data.fixtureId}
                                    homeName={data.home.name}
                                    awayName={data.away.name}
                                />

                                <PredictionsCard
                                    predictions={data.predictions}
                                    home={data.home}
                                    away={data.away}
                                />

                                {/* SEZIONE HOME VS AWAY */}
                                <div className="mb-8">
                                    <div className="flex items-center justify-center gap-4 mb-10">
                                        <div className="h-px bg-white/5 flex-1" />
                                        <h2 className="text-3xl font-black font-display italic tracking-tighter flex items-center gap-4 uppercase">
                                            <span className="text-emerald-400">Home</span>
                                            <span className="text-white/20 text-sm normal-case font-bold mt-1">vs</span>
                                            <span className="text-amber-400">Away</span>
                                        </h2>
                                        <div className="h-px bg-white/5 flex-1" />
                                    </div>

                                    <div className="flex flex-col lg:flex-row gap-8">
                                        <TeamPanel team={data.home} side="home" />
                                        <TeamPanel team={data.away} side="away" />
                                    </div>
                                </div>

                                <ComparisonSection
                                    comparison={data.comparison}
                                    homeName={data.home.name}
                                    awayName={data.away.name}
                                />

                                <H2HSection h2h={data.h2h} />
                            </div>
                        )}
                    </>
                )}

            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>
                    &copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.
                </p>
            </footer>
        </div>
    );
}
