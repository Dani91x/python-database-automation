// ============================================================================
// Quote Betfair — pannello per-partita che riporta TUTTE le quote Betfair
// disponibili per i mercati (da engine_signals, via RPC get_betfair_odds).
// Stesso guscio/stile degli altri pannelli (Sheet bottom, glass-card).
// Mostra dati per le partite che matchano Betfair (dopo aggiorna_report.bat).
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, Coins, AlertTriangle } from 'lucide-react';
import { fetchBetfairOdds, BetfairOdds } from '@/lib/betfair';
import { marketLabel, selectionLabel } from '@/lib/direzione';
import { numFmt } from '@/lib/fixtureModels';

interface Props {
    fixtureId: string;
    leagueName: string;
    homeName: string;
    awayName: string;
}

// ordine di visualizzazione dei mercati
const MARKET_ORDER = ['1x2', 'ht_1x2', 'over_1_5', 'over_2_5', 'over_3_5', 'btts', 'first_half_over_0_5'];

export function BetfairOddsPanel({ fixtureId, leagueName, homeName, awayName }: Props) {
    const [open, setOpen] = useState(false);
    const [odds, setOdds] = useState<BetfairOdds | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const reqRef = useRef(0);

    useEffect(() => {
        if (!open) return;
        const req = ++reqRef.current;
        setLoading(true);
        setError(null);
        setOdds(null);
        fetchBetfairOdds(fixtureId)
            .then(d => { if (req === reqRef.current) setOdds(d); })
            .catch(e => { if (req === reqRef.current) { setError(e.message || 'Errore di caricamento'); setOdds(null); } })
            .finally(() => { if (req === reqRef.current) setLoading(false); });
    }, [open, fixtureId]);

    const markets = odds ? MARKET_ORDER.filter(m => odds[m] && Object.keys(odds[m]).length > 0) : [];

    return (
        <>
            <div className="mb-8 flex justify-center">
                <Button
                    onClick={() => setOpen(true)}
                    variant="outline"
                    className="glass-card border-white/10 hover:border-amber-400/40 text-white font-bold h-12 px-6 rounded-xl gap-2 hover:bg-white/5"
                >
                    <Coins className="w-5 h-5 text-amber-400" />
                    Quote Betfair
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— mercati</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[92vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Quote Betfair <span className="text-amber-400">·</span> {homeName} vs {awayName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            Quote pre-partita dell'exchange Betfair per questa partita, mercato per mercato. {leagueName}.
                        </SheetDescription>
                    </SheetHeader>

                    <div className="max-w-3xl mx-auto space-y-3">
                        {loading && (
                            <div className="flex items-center justify-center py-24"><Loader2 className="w-10 h-10 text-amber-400 animate-spin" /></div>
                        )}
                        {error && !loading && (
                            <div className="glass-card rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-6 text-center">
                                <p className="text-red-400 font-bold text-sm">Errore: {error}</p>
                            </div>
                        )}
                        {!loading && !error && markets.length === 0 && (
                            <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                                <p className="text-amber-400 font-bold">Nessuna quota Betfair per questa partita</p>
                                <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto">
                                    Le quote compaiono dopo aver lanciato <span className="font-mono">aggiorna_report.bat</span>, che le recupera dall'exchange Betfair.
                                </p>
                            </div>
                        )}
                        {!loading && !error && markets.map(m => (
                            <div key={m} className="glass-card rounded-xl border border-white/10 px-4 py-3">
                                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">{marketLabel(m)}</div>
                                <div className="flex flex-wrap gap-2">
                                    {Object.entries(odds?.[m] ?? {}).map(([sel, odd]) => (
                                        <div key={sel} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10">
                                            <span className="text-xs text-white/70">{selectionLabel(m, sel)}</span>
                                            <span className="text-sm font-mono font-bold text-amber-300">{numFmt(Number(odd), 2)}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
