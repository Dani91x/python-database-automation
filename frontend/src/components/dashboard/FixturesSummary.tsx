import { TeamLeagueStats } from "@/lib/normalize";
import { Card } from "@/components/ui/card";
import { TableProperties } from "lucide-react";

export function FixturesSummary({ fixtures }: { fixtures: TeamLeagueStats['fixtures'] }) {
    const rows = [
        { label: "Giocate", data: fixtures.played },
        { label: "Vittorie", data: fixtures.wins },
        { label: "Pareggi", data: fixtures.draws },
        { label: "Sconfitte", data: fixtures.loses },
    ];

    return (
        <Card className="glass-card p-6">
            <div className="flex items-center gap-2 mb-4 text-muted-foreground">
                <TableProperties className="w-4 h-4" />
                <h4 className="text-xs font-display font-bold uppercase tracking-widest">Riepilogo Partite</h4>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-[10px] uppercase tracking-widest text-muted-foreground border-b border-white/10">
                            <th className="text-left py-2 pr-4"></th>
                            <th className="text-center py-2 px-2">Casa</th>
                            <th className="text-center py-2 px-2">Trasferta</th>
                            <th className="text-center py-2 px-2 font-bold text-foreground">Totale</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row) => (
                            <tr key={row.label} className="border-b border-white/10 hover:bg-white/5 transition-colors">
                                <td className="py-2 pr-4 text-muted-foreground font-medium">{row.label}</td>
                                <td className="py-2 px-2 text-center font-mono">{row.data.home}</td>
                                <td className="py-2 px-2 text-center font-mono">{row.data.away}</td>
                                <td className="py-2 px-2 text-center font-mono font-bold text-foreground">{row.data.total}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Card>
    );
}
