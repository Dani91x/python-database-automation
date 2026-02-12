'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import { supabase } from '@/lib/supabase';
import {
    Calendar,
    ChevronLeft,
    ChevronRight,
    Filter,
    Trophy,
    Activity,
    Zap
} from 'lucide-react';
import { format, addDays, subDays } from 'date-fns';
import { it } from 'date-fns/locale';

export default function Dashboard() {
    const [date, setDate] = useState(new Date());
    const [loading, setLoading] = useState(true);
    const [predictions, setPredictions] = useState<any[]>([]);

    useEffect(() => {
        fetchPredictions();
    }, [date]);

    const fetchPredictions = async () => {
        setLoading(true);
        const targetDate = format(date, 'yyyy-MM-dd');

        // In un'applicazione reale, useremmo una join o una query più complessa
        // Qui simuliamo il caricamento dal tuo database Supabase reale
        const { data, error } = await supabase
            .table('fixture_predictions')
            .select(`
        *,
        matches!inner (
          home_team_name,
          away_team_name,
          league_name,
          league_id,
          status_short,
          goals_home,
          goals_away
        )
      `)
            .gte('fixture_date', `${targetDate}T00:00:00+00:00`)
            .lte('fixture_date', `${targetDate}T23:59:59+00:00`)
            .order('fixture_date', { ascending: true });

        if (!error && data) {
            setPredictions(data);
        }
        setLoading(false);
    };

    const groupLeagues = () => {
        return predictions.reduce((acc: any, pred: any) => {
            const league = pred.matches.league_name;
            if (!acc[league]) acc[league] = [];
            acc[league].push(pred);
            return acc;
        }, {});
    };

    const grouped = groupLeagues();

    return (
        <div className="min-h-screen bg-black text-white">
            {/* Header */}
            <header className="border-b border-white/5 bg-black/50 backdrop-blur-md sticky top-0 z-50">
                <div className="container mx-auto px-4 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Image src="/logo.jpg" alt="Logo" width={120} height={30} className="object-contain" />
                        <div className="h-4 w-px bg-white/10 hidden md:block" />
                        <span className="text-xs font-bold uppercase tracking-widest text-brand-orange hidden md:block">
                            Insight Engine v1.0
                        </span>
                    </div>

                    <div className="flex items-center gap-4">
                        <div className="flex items-center bg-white/5 rounded-full px-4 py-1 border border-white/10">
                            <button onClick={() => setDate(subDays(date, 1))} className="p-1 hover:text-brand-orange transition-colors">
                                <ChevronLeft className="w-4 h-4" />
                            </button>
                            <div className="px-4 text-xs font-black uppercase flex items-center gap-2">
                                <Calendar className="w-3 h-3 text-brand-orange" />
                                {format(date, 'd MMMM yyyy', { locale: it })}
                            </div>
                            <button onClick={() => setDate(addDays(date, 1))} className="p-1 hover:text-brand-orange transition-colors">
                                <ChevronRight className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            <main className="container mx-auto px-4 py-8">
                {loading ? (
                    <div className="flex flex-col items-center justify-center py-24 space-y-4">
                        <Activity className="w-12 h-12 text-brand-orange animate-pulse" />
                        <p className="text-gray-500 uppercase tracking-widest text-xs font-bold">Analisi Dati in corso...</p>
                    </div>
                ) : predictions.length === 0 ? (
                    <div className="text-center py-24 glass-panel rounded-3xl border-dashed border-white/10">
                        <Trophy className="w-16 h-16 text-white/10 mx-auto mb-4" />
                        <h3 className="text-xl font-bold">Nessun pronostico disponibile</h3>
                        <p className="text-gray-500">I nostri algoritmi non hanno trovato segnali di valore per questa data.</p>
                    </div>
                ) : (
                    <div className="space-y-12">
                        {Object.keys(grouped).map(league => (
                            <section key={league} className="space-y-4">
                                <div className="flex items-center gap-3">
                                    <div className="w-1 h-6 bg-brand-orange rounded-full" />
                                    <h2 className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
                                        {league}
                                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded-md border border-white/10 text-gray-400">
                                            {grouped[league].length} MATCH
                                        </span>
                                    </h2>
                                </div>

                                <div className="grid gap-4">
                                    {grouped[league].map((pred: any) => (
                                        <div
                                            key={pred.fixture_id}
                                            className="glass-panel group p-6 rounded-2xl hover:border-brand-orange/40 transition-all cursor-pointer relative overflow-hidden"
                                        >
                                            <div className="absolute top-0 right-0 p-2 opacity-10">
                                                <Zap className="w-12 h-12 text-brand-orange" />
                                            </div>

                                            <div className="grid md:grid-cols-12 gap-6 items-center">
                                                {/* Match Info */}
                                                <div className="md:col-span-5 flex items-center justify-between md:justify-start gap-6">
                                                    <div className="text-right flex-1">
                                                        <div className="font-bold text-lg">{pred.matches.home_team_name}</div>
                                                    </div>
                                                    <div className="text-brand-orange font-black text-xl italic px-4 bg-brand-orange/10 rounded-lg">VS</div>
                                                    <div className="text-left flex-1">
                                                        <div className="font-bold text-lg">{pred.matches.away_team_name}</div>
                                                    </div>
                                                </div>

                                                {/* Predictions Data */}
                                                <div className="md:col-span-4 grid grid-cols-2 gap-4 border-l border-white/5 pl-6">
                                                    <div>
                                                        <div className="text-[10px] uppercase text-gray-500 font-bold mb-1">CONSIGLIO ESITO</div>
                                                        <div className="flex items-center gap-2">
                                                            <span className="bg-brand-orange/20 text-brand-orange px-2 py-0.5 rounded text-xs font-black">
                                                                {pred.winner_team_id === pred.matches.home_team_id ? '1' : '2'}
                                                            </span>
                                                            <span className="text-xs font-bold text-white/80 uppercase">Vincitore</span>
                                                        </div>
                                                    </div>
                                                    <div>
                                                        <div className="text-[10px] uppercase text-gray-500 font-bold mb-1">MOVIMENTO GOAL</div>
                                                        <div className="flex items-center gap-2">
                                                            <span className="bg-white/10 text-white px-2 py-0.5 rounded text-xs font-black">
                                                                {pred.under_over_line || 'N/D'}
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Result / Probability */}
                                                <div className="md:col-span-3 text-right">
                                                    <div className="text-[10px] bg-white/5 inline-block px-3 py-1 rounded-full border border-white/10 mb-2">
                                                        {pred.matches.status_short === 'FT' ? 'RISULTATO FINALE' : 'DA DISPUTARE'}
                                                    </div>
                                                    {pred.matches.status_short === 'FT' && (
                                                        <div className="text-2xl font-black text-white leading-none">
                                                            {pred.matches.goals_home} - {pred.matches.goals_away}
                                                            {pred.hit_winner && (
                                                                <span className="text-xs text-green-500 ml-2 uppercase font-black">✓ HIT</span>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                            {/* AI Placeholder */}
                                            <div className="mt-4 pt-4 border-t border-white/5">
                                                <div className="flex items-center gap-2 text-[10px] text-brand-orange font-black uppercase mb-2">
                                                    <BrainCircuit className="w-3 h-3" />
                                                    AI Match Insight
                                                </div>
                                                <p className="text-xs text-gray-500 italic">
                                                    L'analisi avanzata del modello neurale per questo match sarà disponibile a breve.
                                                    I dati indicano una forte correlazione con l'andamento delle ultime 5 giornate.
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </section>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
}

function BrainCircuit(props: any) {
    return (
        <svg
            {...props}
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .52 8.242 4.42 4.42 0 0 0 4.003 4.863c.27 0 .5-.21.5-.47V16" />
            <path d="M16 13a2 2 0 1 1 0-4" />
            <path d="M19 13a2 2 0 1 0 0-4" />
            <path d="M16 17a2 2 0 1 1 0-4" />
            <path d="M19 17a2 2 0 1 0 0-4" />
            <path d="M12 16h4" />
            <path d="M12 11h4" />
        </svg>
    );
}
