import Image from 'next/image';
import { supabase } from '@/lib/supabase';
import {
    Calendar,
    ChevronLeft,
    ChevronRight,
    Trophy,
    Activity,
    Zap,
    BrainCircuit
} from 'lucide-react';
import { format, addDays, subDays, parseISO } from 'date-fns';
import { it } from 'date-fns/locale';
import Link from 'next/link';

import { MatchCard } from "@/components/MatchCard";

async function getPredictions(dateStr: string) {
    const { data, error } = await supabase
        .from('fixture_predictions')
        .select('*')
        .gte('fixture_date', `${dateStr}T00:00:00+00:00`)
        .lte('fixture_date', `${dateStr}T23:59:59+00:00`)
        .order('fixture_date', { ascending: true });

    if (error) {
        console.error('Fetch error:', error);
        return [];
    }
    return data || [];
}

export default async function DashboardPage({
    searchParams,
}: {
    searchParams: Promise<{ date?: string }>;
}) {
    const { date: dateParam } = await searchParams;
    const today = format(new Date(), 'yyyy-MM-dd');
    const currentDateStr = dateParam || today;
    const currentDate = parseISO(currentDateStr);

    const predictions = await getPredictions(currentDateStr);

    const groupLeagues = (preds: any[]) => {
        return preds.reduce((acc: any, pred: any) => {
            const league = pred.league_name;
            if (!acc[league]) acc[league] = [];
            acc[league].push(pred);
            return acc;
        }, {});
    };

    const grouped = groupLeagues(predictions);
    const prevDate = format(subDays(currentDate, 1), 'yyyy-MM-dd');
    const nextDate = format(addDays(currentDate, 1), 'yyyy-MM-dd');

    return (
        <div className="min-h-screen bg-zinc-950 text-white selection:bg-brand-orange/30">
            {/* Glossy Background Effect */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-brand-orange/5 blur-[120px] rounded-full" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-brand-orange/5 blur-[100px] rounded-full" />
            </div>

            {/* Header */}
            <header className="border-b border-white/5 bg-black/40 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-20 flex items-center justify-between">
                    <div className="flex items-center gap-6">
                        <Link href="/" className="hover:opacity-80 transition-opacity">
                            <Image src="/logo.jpg" alt="Logo" width={140} height={35} className="object-contain" />
                        </Link>
                        <div className="h-6 w-px bg-white/10 hidden md:block" />
                        <div className="hidden md:flex flex-col">
                            <span className="text-[10px] font-black uppercase tracking-[0.3em] text-brand-orange leading-none mb-1">
                                Insight Engine
                            </span>
                            <span className="text-[10px] font-black uppercase tracking-[0.1em] text-gray-500 leading-none">
                                Quantitative Betting System
                            </span>
                        </div>
                    </div>

                    <div className="flex items-center gap-6">
                        <div className="flex items-center bg-white/5 rounded-2xl p-1 border border-white/10">
                            <Link href={`/dashboard?date=${prevDate}`} className="p-2 hover:bg-white/10 rounded-xl transition-all">
                                <ChevronLeft className="w-5 h-5" />
                            </Link>
                            <div className="px-6 text-xs font-black uppercase tracking-widest flex items-center gap-3 min-w-[200px] justify-center text-center">
                                <Calendar className="w-4 h-4 text-brand-orange" />
                                {format(currentDate, 'd MMMM yyyy', { locale: it })}
                            </div>
                            <Link href={`/dashboard?date=${nextDate}`} className="p-2 hover:bg-white/10 rounded-xl transition-all">
                                <ChevronRight className="w-5 h-5" />
                            </Link>
                        </div>
                    </div>
                </div>
            </header>

            <main className="container mx-auto px-6 py-12 relative z-10">
                {predictions.length === 0 ? (
                    <div className="text-center py-32 glass-panel rounded-[2rem] border-dashed border-white/10 max-w-2xl mx-auto">
                        <div className="w-20 h-20 bg-white/5 rounded-3xl flex items-center justify-center mx-auto mb-6 border border-white/10">
                            <Trophy className="w-10 h-10 text-white/20" />
                        </div>
                        <h3 className="text-2xl font-black uppercase tracking-tight mb-2">Segnale in attesa</h3>
                        <p className="text-gray-500 max-w-xs mx-auto text-sm leading-relaxed">
                            I nostri algoritmi stanno analizzando i mercati. Torna a breve per nuovi segnali ad alta probabilità.
                        </p>
                    </div>
                ) : (
                    <div className="space-y-16">
                        {Object.keys(grouped).map(league => (
                            <section key={league} className="space-y-6">
                                <div className="flex items-center justify-between border-b border-white/5 pb-4">
                                    <div className="flex items-center gap-4">
                                        <div className="w-1.5 h-8 bg-brand-orange rounded-full shadow-[0_0_15px_rgba(255,165,0,0.5)]" />
                                        <div className="flex flex-col">
                                            <h2 className="text-xl font-black uppercase tracking-tighter leading-none">
                                                {league}
                                            </h2>
                                            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mt-1">
                                                Competitive Division
                                            </span>
                                        </div>
                                    </div>
                                    <div className="bg-brand-orange/10 text-brand-orange border border-brand-orange/20 px-3 py-1 rounded-full text-[10px] font-black uppercase">
                                        {grouped[league].length} Partite
                                    </div>
                                </div>

                                <div className="grid gap-6">
                                    {grouped[league].map((pred: any) => (
                                        <MatchCard key={pred.fixture_id} pred={pred} />
                                    ))}
                                </div>
                            </section>
                        ))}
                    </div>
                )}
            </main>

            {/* Market Status Footer */}
            <footer className="border-t border-white/5 bg-black/20 mt-20">
                <div className="container mx-auto px-6 py-8 flex flex-col md:flex-row justify-between items-center gap-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                    <div className="flex items-center gap-6">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                            Feed Dati: Operativo
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                            Neural Model: Online
                        </div>
                    </div>
                    <div>© 2026 Sport Investing • Insight Engine v1.4.2</div>
                </div>
            </footer>
        </div>
    );
}
