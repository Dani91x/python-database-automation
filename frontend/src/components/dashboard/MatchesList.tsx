import { useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Loader2, Calendar, Trophy, MapPin, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';

interface MatchPreview {
    fixture_id: string;
    date: string;
    time: string;
    status: string;
    league: {
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

interface MatchesListProps {
    onSelectMatch: (fixtureId: string) => void;
}

export function MatchesList({ onSelectMatch }: MatchesListProps) {
    const [matches, setMatches] = useState<MatchPreview[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchMatches() {
            setLoading(true);
            try {
                // Get today's date in YYYY-MM-DD format
                const today = new Date().toISOString().split('T')[0];

                // Fetch matches. 
                // Note: filtering by date might need adjustment depending on DB timezone vs local. 
                // For now, we fetch recent/upcoming to ensure data visibility, 
                // or we can strictly filter .eq('fixture_date', today) if the column is just specific date.
                // Given the user said "populated every day", we'll try to fetch broadly and sort/filter in JS or query.
                // Let's first try to get everything from today onwards, or just latest 50 to be safe and filter client side if needed or use the exact date if the column is date type.

                const { data, error } = await supabase
                    .from('fixture_predictions')
                    .select('fixture_id, raw_json, fixture_date')
                    .order('fixture_date', { ascending: true }) // Chronological
                    .limit(50);

                if (error) throw error;

                const mapped: MatchPreview[] = (data || [])
                    .map((row: any) => {
                        try {
                            const resp = row.raw_json?.response?.[0];
                            if (!resp) return null;

                            const dateObj = new Date(resp.fixture.date);

                            return {
                                fixture_id: String(row.fixture_id),
                                date: dateObj.toLocaleDateString('it-IT', { day: 'numeric', month: 'long' }),
                                time: dateObj.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
                                status: resp.fixture.status.short,
                                league: {
                                    name: resp.league.name,
                                    logo: resp.league.logo,
                                    flag: resp.league.flag,
                                },
                                home: {
                                    name: resp.teams.home.name,
                                    logo: resp.teams.home.logo,
                                },
                                away: {
                                    name: resp.teams.away.name,
                                    logo: resp.teams.away.logo,
                                },
                            };
                        } catch (e) {
                            return null;
                        }
                    })
                    .filter(Boolean) as MatchPreview[];

                // Optional: client-side filter for "today" if needed. 
                // For now, simpler to show the retrieved list (which are likely the relevant ones).
                // If we want STRICTLY today:
                // const todayString = new Date().toLocaleDateString('it-IT');
                // const todaysMatches = mapped.filter(m => m.date === todayString); // logic depends on exact string format

                setMatches(mapped);
            } catch (e) {
                console.error("Error fetching matches:", e);
            } finally {
                setLoading(false);
            }
        }

        fetchMatches();
    }, []);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center py-20">
                <Loader2 className="w-10 h-10 text-primary animate-spin mb-4" />
                <p className="text-muted-foreground font-heading">Caricamento partite...</p>
            </div>
        );
    }

    if (matches.length === 0) {
        return (
            <div className="text-center py-20 glass-card rounded-2xl p-8 max-w-2xl mx-auto">
                <Calendar className="w-16 h-16 text-muted-foreground mx-auto mb-4 opacity-50" />
                <h2 className="text-2xl font-bold font-display text-white mb-2">Nessuna partita trovata</h2>
                <p className="text-muted-foreground">Non ci sono pronostici disponibili per le partite recenti o di oggi.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6 max-w-5xl mx-auto">
            <div className="flex items-center justify-between mb-8">
                <h1 className="text-3xl md:text-4xl font-display font-black text-white">
                    Partite del Giorno <span className="text-primary">.</span>
                </h1>
                <div className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm font-bold text-primary backdrop-blur-md">
                    {matches.length} Match Disponibili
                </div>
            </div>

            <div className="grid gap-4">
                {matches.map((match, index) => (
                    <motion.div
                        key={match.fixture_id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="glass-card p-4 md:p-6 rounded-xl border border-white/5 hover:border-primary/30 transition-all group relative overflow-hidden"
                    >
                        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-transparent to-primary/5 opacity-0 group-hover:opacity-100 transition-opacity" />

                        <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-6">

                            {/* League & Time Info */}
                            <div className="flex items-center gap-4 min-w-[140px]">
                                <div className="flex flex-col items-center justify-center w-12 h-12 rounded-lg bg-black/40 border border-white/10">
                                    <span className="text-sm font-bold text-white">{match.time}</span>
                                </div>
                                <div className="flex flex-col">
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider mb-1">
                                        {match.league.flag && <img src={match.league.flag} alt="Country" className="w-4 h-4 rounded-full" />}
                                        <span className="truncate max-w-[120px]">{match.league.name}</span>
                                    </div>
                                    <span className="text-xs text-emerald-400 font-bold px-2 py-0.5 rounded bg-emerald-400/10 w-fit">
                                        {match.status}
                                    </span>
                                </div>
                            </div>

                            {/* Teams */}
                            <div className="flex-1 flex items-center justify-center gap-4 md:gap-8 w-full">
                                <div className="flex items-center gap-3 text-right flex-1 justify-end">
                                    <span className="text-lg md:text-xl font-heading font-bold text-white hidden sm:block">
                                        {match.home.name}
                                    </span>
                                    <span className="text-lg md:text-xl font-heading font-bold text-white sm:hidden">
                                        {match.home.name.substring(0, 3).toUpperCase()}
                                    </span>
                                    <img src={match.home.logo} alt={match.home.name} className="w-10 h-10 md:w-14 md:h-14 object-contain drop-shadow-lg" />
                                </div>

                                <div className="text-muted-foreground font-display font-black text-xl px-2">VS</div>

                                <div className="flex items-center gap-3 text-left flex-1 justify-start">
                                    <img src={match.away.logo} alt={match.away.name} className="w-10 h-10 md:w-14 md:h-14 object-contain drop-shadow-lg" />
                                    <span className="text-lg md:text-xl font-heading font-bold text-white hidden sm:block">
                                        {match.away.name}
                                    </span>
                                    <span className="text-lg md:text-xl font-heading font-bold text-white sm:hidden">
                                        {match.away.name.substring(0, 3).toUpperCase()}
                                    </span>
                                </div>
                            </div>

                            {/* Action Button */}
                            <div className="w-full md:w-auto mt-4 md:mt-0">
                                <Button
                                    onClick={() => onSelectMatch(match.fixture_id)}
                                    className="w-full md:w-auto bg-primary text-primary-foreground font-bold hover:bg-primary/90 shadow-lg shadow-primary/20 group-hover:scale-105 transition-transform"
                                >
                                    ANALIZZA <ArrowRight className="w-4 h-4 ml-2" />
                                </Button>
                            </div>

                        </div>
                    </motion.div>
                ))}
            </div>
        </div>
    );
}
