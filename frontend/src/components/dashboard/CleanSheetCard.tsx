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
                    <div className="flex items-center gap-2 mb-3 text-result-win">
                        <ShieldCheck className="w-4 h-4" />
                        <h4 className="text-xs font-display font-bold uppercase tracking-widest text-muted-foreground">Clean Sheet</h4>
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-center">
                        <div className="p-2 bg-muted/20 rounded">
                            <div className="text-lg font-bold text-foreground">{cleanSheet.home}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Casa</div>
                        </div>
                        <div className="p-2 bg-muted/20 rounded">
                            <div className="text-lg font-bold text-foreground">{cleanSheet.away}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Trasferta</div>
                        </div>
                        <div className="p-2 bg-result-win/10 rounded border border-result-win/20">
                            <div className="text-lg font-bold text-result-win">{cleanSheet.total}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Totale</div>
                        </div>
                    </div>
                </div>

                <div className="border-t border-white/5" />

                {/* Failed to Score */}
                <div>
                    <div className="flex items-center gap-2 mb-3 text-destructive">
                        <ShieldX className="w-4 h-4" />
                        <h4 className="text-xs font-display font-bold uppercase tracking-widest text-muted-foreground">Non ha Segnato</h4>
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-center">
                        <div className="p-2 bg-muted/20 rounded">
                            <div className="text-lg font-bold text-foreground">{failedToScore.home}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Casa</div>
                        </div>
                        <div className="p-2 bg-muted/20 rounded">
                            <div className="text-lg font-bold text-foreground">{failedToScore.away}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Trasferta</div>
                        </div>
                        <div className="p-2 bg-destructive/10 rounded border border-destructive/20">
                            <div className="text-lg font-bold text-destructive">{failedToScore.total}</div>
                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground">Totale</div>
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}
