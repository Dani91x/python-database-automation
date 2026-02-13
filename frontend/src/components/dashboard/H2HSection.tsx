import { Card } from "@/components/ui/card";
import { format } from 'date-fns';
import { it } from 'date-fns/locale';

export function H2HSection({ h2h }: { h2h: any[] }) {
    if (!h2h || h2h.length === 0) {
        return (
            <div className="text-center p-8 text-muted-foreground italic border border-white/5 rounded-xl">
                Nessuno storico testa-a-testa disponibile.
            </div>
        );
    }

    return (
        <section className="mb-12">
            <h2 className="text-xl font-display font-bold mb-6 text-foreground">STORICO H2H</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {h2h.slice(0, 6).map((match, i) => (
                    <Card key={i} className="glass-card p-4 hover:bg-white/5 transition-colors">
                        <div className="text-[10px] text-accent uppercase tracking-widest mb-2 font-bold">
                            {format(new Date(match.fixture.date), "dd MMM yyyy", { locale: it })}
                        </div>
                        <div className="flex justify-between items-center">
                            <div className={`text-sm font-bold ${match.teams.home.winner ? 'text-result-win' : 'text-foreground'}`}>
                                {match.teams.home.name}
                            </div>
                            <div className="bg-black/40 px-3 py-1 rounded font-mono font-bold text-foreground border border-white/10">
                                {match.goals.home} - {match.goals.away}
                            </div>
                            <div className={`text-sm font-bold ${match.teams.away.winner ? 'text-result-win' : 'text-foreground'}`}>
                                {match.teams.away.name}
                            </div>
                        </div>
                        <div className="text-[10px] text-muted-foreground text-center mt-2">
                            {match.league.name}
                        </div>
                    </Card>
                ))}
            </div>
        </section>
    );
}
