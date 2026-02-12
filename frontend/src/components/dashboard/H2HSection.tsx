// frontend/src/components/dashboard/H2HSection.tsx
import { History, AlertCircle } from "lucide-react";
import { Card, cn } from "@/components/ui/shadcn-mini";

interface H2HSectionProps {
    h2h: any[];
    homeName: string;
    awayName: string;
}

export function H2HSection({ h2h, homeName, awayName }: H2HSectionProps) {
    if (!h2h || h2h.length === 0) {
        return (
            <section className="container mx-auto px-4 py-12">
                <Card className="p-10 border-white/5 text-center">
                    <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-6">
                        <AlertCircle className="w-8 h-8 text-gray-600" />
                    </div>
                    <h3 className="text-xl font-black italic tracking-tighter">DATA UNAVAILABLE</h3>
                    <p className="text-gray-500 text-sm mt-2">Historical head-to-head records for this match are not present in the current feed.</p>
                </Card>
            </section>
        );
    }

    return (
        <section className="container mx-auto px-4 py-12">
            <Card className="p-10 border-white/5 bg-gradient-to-b from-white/[0.02] to-transparent">
                <div className="flex items-center gap-4 mb-10">
                    <History className="w-8 h-8 text-brand-orange" />
                    <h2 className="text-3xl font-black italic tracking-tighter">HISTORICAL SYNERGY (H2H)</h2>
                </div>

                <div className="grid grid-cols-1 gap-4">
                    {h2h.slice(0, 5).map((match: any, index: number) => (
                        <div
                            key={index}
                            className="group p-6 rounded-2xl bg-white/[0.03] border border-white/5 flex flex-col md:flex-row items-center justify-between hover:border-brand-orange/30 transition-all hover:bg-white/[0.05]"
                        >
                            <div className="flex flex-col mb-4 md:mb-0">
                                <span className="text-[10px] font-black uppercase tracking-widest text-brand-orange">{match.league?.name || 'LEAGUE'}</span>
                                <span className="text-xs font-bold text-gray-500">{match.fixture?.date ? new Date(match.fixture.date).toLocaleDateString() : 'N/D'}</span>
                            </div>

                            <div className="flex items-center gap-6 lg:gap-12">
                                <div className="text-right w-32 md:w-48">
                                    <span className="text-sm font-black uppercase tracking-tighter group-hover:text-brand-orange transition-colors">{match.teams?.home?.name}</span>
                                </div>

                                <div className="bg-white/5 px-6 py-2 rounded-xl border border-white/10">
                                    <span className="text-2xl font-black italic">{match.goals?.home ?? '0'} - {match.goals?.away ?? '0'}</span>
                                </div>

                                <div className="text-left w-32 md:w-48">
                                    <span className="text-sm font-black uppercase tracking-tighter group-hover:text-neon-cyan transition-colors">{match.teams?.away?.name}</span>
                                </div>
                            </div>

                            <div className="hidden lg:block text-right">
                                <span className="text-[10px] font-black text-white/20 uppercase tracking-[0.2em]">Validated Result</span>
                            </div>
                        </div>
                    ))}
                </div>
            </Card>
        </section>
    );
}
