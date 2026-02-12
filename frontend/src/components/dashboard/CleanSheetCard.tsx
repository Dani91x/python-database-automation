import { Card } from "@/components/ui/card";
import { ShieldCheck, ShieldX } from "lucide-react";

interface CleanSheetCardProps {
    cleanSheet: { home: number; away: number; total: number };
    failedToScore: { home: number; away: number; total: number };
}

export function CleanSheetCard({ cleanSheet, failedToScore }: CleanSheetCardProps) {
    return (
        <Card className="glass-card p-6">
            <div className="space-y-6">
                {/* Clean Sheet */}
                <div>
                    <div className="flex items-center gap-2 mb-3 text-green-400">
                        <ShieldCheck className="w-4 h-4" />
                        <h4 className="text-xs font-rajdhani font-bold uppercase tracking-widest">Clean Sheet</h4>
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-center">
                        <div className="p-2 bg-white/5 rounded">
                            <div className="text-lg font-bold text-white">{cleanSheet.home}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Casa</div>
                        </div>
                        <div className="p-2 bg-white/5 rounded">
                            <div className="text-lg font-bold text-white">{cleanSheet.away}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Trasferta</div>
                        </div>
                        <div className="p-2 bg-green-500/10 rounded border border-green-500/20">
                            <div className="text-lg font-bold text-green-400">{cleanSheet.total}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Totale</div>
                        </div>
                    </div>
                </div>

                <div className="border-t border-white/5" />

                {/* Failed to Score */}
                <div>
                    <div className="flex items-center gap-2 mb-3 text-red-400">
                        <ShieldX className="w-4 h-4" />
                        <h4 className="text-xs font-rajdhani font-bold uppercase tracking-widest">Non ha Segnato</h4>
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-center">
                        <div className="p-2 bg-white/5 rounded">
                            <div className="text-lg font-bold text-white">{failedToScore.home}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Casa</div>
                        </div>
                        <div className="p-2 bg-white/5 rounded">
                            <div className="text-lg font-bold text-white">{failedToScore.away}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Trasferta</div>
                        </div>
                        <div className="p-2 bg-red-500/10 rounded border border-red-500/20">
                            <div className="text-lg font-bold text-red-400">{failedToScore.total}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Totale</div>
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}
