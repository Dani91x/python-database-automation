import { TeamLast5 } from "@/lib/normalize";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export function Last5Card({ last5 }: { last5: TeamLast5 }) {
    return (
        <Card className="glass-card p-6 mb-4">
            <h4 className="text-xs font-rajdhani font-bold uppercase tracking-widest text-muted-foreground mb-4">Ultime 5 Partite</h4>

            <div className="space-y-4 font-mono text-sm">
                <div>
                    <div className="flex justify-between mb-1">
                        <span>Forma</span>
                        <span className="font-bold text-white">{last5.form}%</span>
                    </div>
                    <Progress value={last5.form} className="h-1.5" indicatorClassName="bg-brand-orange" />
                </div>

                <div>
                    <div className="flex justify-between mb-1">
                        <span>Attacco</span>
                        <span className="font-bold text-neon-cyan">{last5.att}%</span>
                    </div>
                    <Progress value={last5.att} className="h-1.5" indicatorClassName="bg-neon-cyan" />
                </div>

                <div>
                    <div className="flex justify-between mb-1">
                        <span>Difesa</span>
                        <span className="font-bold text-neon-magenta">{last5.def}%</span>
                    </div>
                    <Progress value={last5.def} className="h-1.5" indicatorClassName="bg-neon-magenta" />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4 mt-6 pt-6 border-t border-white/5">
                <div className="text-center">
                    <div className="text-xs text-muted-foreground uppercase tracking-widest">GF Tot</div>
                    <div className="text-xl font-bold text-white mt-1">{last5.goalsFor}</div>
                    <div className="text-[10px] text-gray-500">{(last5.goalsFor / last5.played).toFixed(1)} avg</div>
                </div>
                <div className="text-center">
                    <div className="text-xs text-muted-foreground uppercase tracking-widest">GS Tot</div>
                    <div className="text-xl font-bold text-white mt-1">{last5.goalsAgainst}</div>
                    <div className="text-[10px] text-gray-500">{(last5.goalsAgainst / last5.played).toFixed(1)} avg</div>
                </div>
            </div>
        </Card>
    );
}
