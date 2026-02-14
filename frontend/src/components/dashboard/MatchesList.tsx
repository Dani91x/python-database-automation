import { useEffect, useState, useMemo } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Loader2, Calendar, ArrowRight, Trophy } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import { toast } from 'sonner';
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";

interface MatchPreview {
    fixture_id: string;
    date: string;
    time: string;
    status: string;
    league: {
        id: number;
        name: string;
        logo: string;
        flag: string;
    };
    home: {
        name: string;
        logo: string;
    };
    away: {
        name: string;
        logo: string;
    };
}

interface GroupedMatches {
    [key: string]: {
        league: MatchPreview['league'];
        matches: MatchPreview[];
    };
}

interface MatchesListProps {
    onSelectMatch: (fixtureId: string) => void;
}

export function MatchesList({ onSelectMatch }: MatchesListProps) {
    const [matches, setMatches] = useState<MatchPreview[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [page, setPage] = useState(0);
    const [hasMore, setHasMore] = useState(true);
    const PAGE_SIZE = 100;

    const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
    const [isFilterOpen, setIsFilterOpen] = useState(false);

    // Top Leagues Configuration
    const TOP_LEAGUES = [
        { id: 135, name: 'Serie A', flag: '🇮🇹' },
        { id: 136, name: 'Serie B', flag: '🇮🇹' },
        { id: 39, name: 'Premier League', flag: '🇬🇧' },
        { id: 140, name: 'La Liga', flag: '🇪🇸' },
        { id: 78, name: 'Bundesliga', flag: '🇩🇪' },
        { id: 61, name: 'Ligue 1', flag: '🇫🇷' },
    ];

    const fetchMatches = async (pageNum: number, isInitial: boolean = false, leagueId: number | null = null) => {
        if (isInitial) setLoading(true);
        else setLoadingMore(true);

        try {
            const today = format(new Date(), 'yyyy-MM-dd');
            // If filtering by league, fetch ALL matches (increase limit), otherwise use pagination
            const currentLimit = leagueId ? 100 : PAGE_SIZE;
            const from = pageNum * currentLimit;
            const to = from + currentLimit - 1;

            let query = supabase
                .from('fixture_predictions')
                .select('fixture_id, fixture_date, home_team_name, away_team_name, league_name, league_id, status, raw_json')
                .eq('status', 'ok')
                .gte('fixture_date', `${today}T00:00:00Z`)
                .order('fixture_date', { ascending: true });

            // Apply League Filter if selected
            if (leagueId) {
                query = query.eq('league_id', leagueId);
            }

            const { data, error } = await query.range(from, to);

            if (error) {
                console.error("Supabase Error:", error);
                toast.error("Errore database: " + error.message);
                return;
            }

            const mapped: MatchPreview[] = (data || []).map((row: any) => {
                try {
                    const dateObj = new Date(row.fixture_date);
                    const prediction = row.raw_json?.response?.[0];
                    return {
                        fixture_id: String(row.fixture_id),
                        date: dateObj.toLocaleDateString('it-IT', { day: 'numeric', month: 'long' }),
                        time: dateObj.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
                        status: row.status,
                        league: {
                            id: row.league_id,
                            name: row.league_name || 'N/A',
                            logo: prediction?.league?.logo || '',
                            flag: prediction?.league?.flag || '',
                        },
                        home: {
                            name: row.home_team_name || 'N/A',
                            logo: prediction?.teams?.home?.logo || '',
                        },
                        away: {
                            name: row.away_team_name || 'N/A',
                            logo: prediction?.teams?.away?.logo || '',
                        },
                    };
                } catch (e) { return null; }
            }).filter(Boolean) as MatchPreview[];

            if (isInitial) {
                setMatches(mapped);
            } else {
                setMatches(prev => [...prev, ...mapped]);
            }

            // Update hasMore based on the returned count and limit
            setHasMore(data.length === currentLimit);
        } catch (e) {
            console.error("Error fetching matches:", e);
        } finally {
            setLoading(false);
            setLoadingMore(false);
        }
    };

    useEffect(() => {
        fetchMatches(0, true, selectedLeague);
    }, [selectedLeague]);

    const loadMore = () => {
        const nextPage = page + 1;
        setPage(nextPage);
        fetchMatches(nextPage, false, selectedLeague);
    };

    // Handle filter selection
    const handleLeagueSelect = (leagueId: number | null) => {
        setSelectedLeague(leagueId);
        setPage(0);
        setIsFilterOpen(false);
    };

    const groupedMatches = useMemo(() => {
        const groups: GroupedMatches = {};
        matches.forEach(match => {
            const key = `${match.league.id}-${match.league.name}`;
            if (!groups[key]) {
                groups[key] = {
                    league: match.league,
                    matches: []
                };
            }
            groups[key].matches.push(match);
        });
        return Object.values(groups);
    }, [matches]);

    return (
        <div className="space-y-4 md:space-y-6 max-w-5xl mx-auto px-4">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6 md:mb-8">
                <div>
                    <h1 className="text-2xl md:text-4xl font-display font-black text-white">
                        Partite del Giorno <span className="text-primary">.</span>
                    </h1>
                    <p className="text-muted-foreground text-sm mt-1">
                        {selectedLeague
                            ? `Visualizzazione filtrata: ${TOP_LEAGUES.find(l => l.id === selectedLeague)?.name}`
                            : 'Tutte le partite in programma oggi'}
                    </p>
                </div>

                <div className="flex items-center gap-3 w-full md:w-auto relative">
                    <div className="relative z-50 w-full md:w-64">
                        <Button
                            variant="outline"
                            className="w-full justify-between bg-black/40 border-white/10 text-white hover:bg-white/5 hover:text-primary"
                            onClick={() => setIsFilterOpen(!isFilterOpen)}
                        >
                            <span className="flex items-center gap-2">
                                <Trophy className="w-4 h-4 text-primary" />
                                {selectedLeague
                                    ? TOP_LEAGUES.find(l => l.id === selectedLeague)?.name
                                    : "Filtra per Campionato"}
                            </span>
                            <ArrowRight className={`w-4 h-4 transition-transform ${isFilterOpen ? 'rotate-90' : 'rotate-0'}`} />
                        </Button>

                        <AnimatePresence>
                            {isFilterOpen && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: 10 }}
                                    className="absolute top-full right-0 left-0 mt-2 p-2 glass-card rounded-xl border border-white/10 bg-black/90 shadow-2xl flex flex-col gap-1 z-50"
                                >
                                    <button
                                        onClick={() => handleLeagueSelect(null)}
                                        className={`w-full text-left px-3 py-2 rounded-lg text-sm font-bold transition-colors ${!selectedLeague ? 'bg-primary/20 text-primary' : 'text-white/60 hover:bg-white/5 hover:text-white'}`}
                                    >
                                        🌍 Tutti i Campionati
                                    </button>
                                    <div className="h-px bg-white/10 my-1" />
                                    {TOP_LEAGUES.map(league => (
                                        <button
                                            key={league.id}
                                            onClick={() => handleLeagueSelect(league.id)}
                                            className={`w-full text-left px-3 py-2 rounded-lg text-sm font-bold transition-colors flex items-center justify-between group ${selectedLeague === league.id ? 'bg-primary/20 text-primary' : 'text-white/60 hover:bg-white/5 hover:text-white'}`}
                                        >
                                            <span className="flex items-center gap-2">
                                                <span>{league.flag}</span>
                                                {league.name}
                                            </span>
                                            {selectedLeague === league.id && <div className="w-1.5 h-1.5 rounded-full bg-primary" />}
                                        </button>
                                    ))}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>

                    <div className="text-xs font-bold text-muted-foreground bg-white/5 px-3 py-2 rounded-lg border border-white/5 whitespace-nowrap hidden md:block">
                        {matches.length} Match
                    </div>
                </div>
            </div>

            {loading ? (
                <div className="flex flex-col items-center justify-center py-20 px-4">
                    <Loader2 className="w-10 h-10 text-primary animate-spin mb-4" />
                    <p className="text-muted-foreground font-heading text-center">Caricamento partite...</p>
                </div>
            ) : matches.length === 0 ? (
                <div className="text-center py-12 md:py-20 glass-card rounded-2xl p-6 md:p-8 max-w-2xl mx-auto mx-4">
                    <Calendar className="w-12 h-12 md:w-16 md:h-16 text-muted-foreground mx-auto mb-4 opacity-50" />
                    <h2 className="text-xl md:text-2xl font-bold font-display text-white mb-2">Nessuna partita trovata</h2>
                    <p className="text-muted-foreground text-sm md:text-base">
                        {selectedLeague
                            ? "Non ci sono partite in programma oggi per questo campionato."
                            : "Non ci sono pronostici disponibili per oggi."}
                    </p>
                    {selectedLeague && (
                        <Button variant="link" onClick={() => handleLeagueSelect(null)} className="mt-4 text-primary">
                            Vedi tutte le partite
                        </Button>
                    )}
                </div>
            ) : (
                <>
                    <Accordion type="multiple" className="space-y-4" defaultValue={selectedLeague ? matches.map((_, i) => `${selectedLeague}-${i}`) : undefined}>
                        <AnimatePresence>
                            {groupedMatches.map((group, groupIndex) => (
                                <motion.div
                                    key={`${group.league.id}-${groupIndex}`}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: groupIndex * 0.05 }}
                                >
                                    <AccordionItem value={`${group.league.id}-${groupIndex}`} className="border-none">
                                        <AccordionTrigger className="glass-card hover:no-underline px-4 md:px-6 py-4 rounded-xl border border-white/5 hover:border-primary/20 transition-all [&[data-state=open]]:rounded-b-none [&[data-state=open]]:border-primary/30">
                                            <div className="flex items-center gap-3 md:gap-4 text-left">
                                                <div className="w-8 h-8 md:w-10 md:h-10 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center overflow-hidden flex-shrink-0">
                                                    {group.league.logo ? (
                                                        <img src={group.league.logo} alt={group.league.name} className="w-6 h-6 md:w-8 md:h-8 object-contain" />
                                                    ) : (
                                                        <Trophy className="w-4 h-4 md:w-5 md:h-5 text-primary/60" />
                                                    )}
                                                </div>
                                                <div className="flex flex-col">
                                                    <span className="text-sm md:text-base font-bold text-white line-clamp-1">{group.league.name}</span>
                                                    <span className="text-[10px] md:text-xs text-muted-foreground font-medium uppercase tracking-tight">
                                                        {group.matches.length} {group.matches.length === 1 ? 'partita' : 'partite'}
                                                    </span>
                                                </div>
                                            </div>
                                        </AccordionTrigger>
                                        <AccordionContent className="glass-card rounded-t-none rounded-b-xl border-x border-b border-white/5 bg-white/[0.02] p-2 md:p-4">
                                            <div className="space-y-3">
                                                {group.matches.map((match) => (
                                                    <div
                                                        key={match.fixture_id}
                                                        className="p-3 md:p-4 rounded-lg bg-white/5 border border-white/5 hover:bg-white/10 transition-colors"
                                                    >
                                                        <div className="flex flex-col md:flex-row items-center justify-between gap-4">

                                                            {/* Mobile Header: Time + Status */}
                                                            <div className="flex md:hidden items-center justify-between w-full border-b border-white/5 pb-2 mb-1">
                                                                <span className="text-xs font-bold text-primary">{match.time}</span>
                                                                <span className="text-[10px] text-emerald-400 font-bold px-1.5 py-0.5 rounded bg-emerald-400/10">
                                                                    {match.status}
                                                                </span>
                                                            </div>

                                                            {/* Content Wrapper */}
                                                            <div className="flex items-center justify-between w-full gap-4">
                                                                {/* Time - Desktop */}
                                                                <div className="hidden md:flex items-center justify-center w-12 h-12 rounded-lg bg-black/40 border border-white/10 flex-shrink-0">
                                                                    <span className="text-xs font-bold text-white">{match.time}</span>
                                                                </div>

                                                                {/* Teams */}
                                                                <div className="flex-1 flex items-center justify-center gap-2 md:gap-6">
                                                                    <div className="flex items-center gap-2 md:gap-3 text-right flex-1 justify-end">
                                                                        <span className="text-sm md:text-lg font-bold text-white">
                                                                            {match.home.name}
                                                                        </span>
                                                                        <img src={match.home.logo} alt="" className="w-6 h-6 md:w-10 md:h-10 object-contain shrink-0" />
                                                                    </div>

                                                                    <div className="text-muted-foreground font-display font-black text-xs md:text-sm shrink-0">VS</div>

                                                                    <div className="flex items-center gap-2 md:gap-3 text-left flex-1 justify-start">
                                                                        <img src={match.away.logo} alt="" className="w-6 h-6 md:w-10 md:h-10 object-contain shrink-0" />
                                                                        <span className="text-sm md:text-lg font-bold text-white">
                                                                            {match.away.name}
                                                                        </span>
                                                                    </div>
                                                                </div>

                                                                {/* Button */}
                                                                <Button
                                                                    size="sm"
                                                                    onClick={() => onSelectMatch(match.fixture_id)}
                                                                    className="bg-primary text-primary-foreground font-bold hover:bg-primary/90 h-8 md:h-10 px-3 md:px-4"
                                                                >
                                                                    <span className="hidden sm:inline">ANALIZZA</span>
                                                                    <ArrowRight className="w-4 h-4 sm:ml-2" />
                                                                </Button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </AccordionContent>
                                    </AccordionItem>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    </Accordion>

                    {hasMore && (
                        <div className="py-6 flex justify-center">
                            <Button
                                onClick={loadMore}
                                disabled={loadingMore}
                                variant="outline"
                                className="bg-white/5 border-white/10 hover:bg-white/10 text-white font-bold h-12 px-8 rounded-xl transition-all"
                            >
                                {loadingMore ? (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                ) : (
                                    "VEDI ALTRE LEGHE"
                                )}
                            </Button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
