// ============================================================================
// Quote Betfair — pannello per-partita che riporta TUTTE le quote di TUTTI i
// mercati Betfair (back + lay), stile Betfair applicato al nostro design system.
// Dati da betfair_market_odds (popolata da betfair_full_odds.py), via RPC.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, Coins, AlertTriangle } from 'lucide-react';
import { fetchBetfairFullOdds, BetfairMarket, OddLevel } from '@/lib/betfair';
import { numFmt } from '@/lib/fixtureModels';

interface Props {
    fixtureId: string;
    leagueName: string;
    homeName: string;
    awayName: string;
}

// ordine di visualizzazione dei mercati (i principali in cima, il resto alfabetico)
const MARKET_ORDER = [
    'Match Odds', 'Double Chance', 'Half Time', 'Both teams to Score?',
    'Over/Under 0.5 Goals', 'Over/Under 1.5 Goals', 'Over/Under 2.5 Goals', 'Over/Under 3.5 Goals',
    'Over/Under 4.5 Goals', 'Over/Under 5.5 Goals', 'Over/Under 6.5 Goals',
    'First Half Goals 0.5', 'First Half Goals 1.5', 'First Half Goals 2.5',
    'Half Time/Full Time', 'Correct Score', 'Half Time Score', 'First Goalscorer',
];
const fmtSize = (s?: number | null) =>
    s == null ? '' : s >= 1000 ? `${(s / 1000).toFixed(1)}k` : `${Math.round(s)}`;

// cella prezzo stile Betfair: back = azzurro, lay = rosa
function PriceCell({ lvl, kind }: { lvl?: OddLevel; kind: 'back' | 'lay' }) {
    const base = 'w-[52px] h-10 rounded flex flex-col items-center justify-center border shrink-0';
    if (!lvl || lvl.price == null) return <div className={`${base} bg-white/[0.02] border-white/5`} />;
    const cls = kind === 'back'
        ? 'bg-sky-500/15 border-sky-500/30 text-sky-300'
        : 'bg-rose-500/15 border-rose-500/30 text-rose-300';
    return (
        <div className={`${base} ${cls}`}>
            <span className="text-xs font-mono font-bold leading-none">{numFmt(lvl.price, 2)}</span>
            {lvl.size != null && <span className="text-[8px] text-white/40 leading-none mt-0.5">€{fmtSize(lvl.size)}</span>}
        </div>
    );
}

export function BetfairOddsPanel({ fixtureId, leagueName, homeName, awayName }: Props) {
    const [open, setOpen] = useState(false);
    const [markets, setMarkets] = useState<BetfairMarket[] | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const reqRef = useRef(0);

    useEffect(() => {
        if (!open) return;
        const req = ++reqRef.current;
        setLoading(true);
        setError(null);
        setMarkets(null);
        fetchBetfairFullOdds(fixtureId)
            .then(d => { if (req === reqRef.current) setMarkets(d); })
            .catch(e => { if (req === reqRef.current) { setError(e.message || 'Errore di caricamento'); setMarkets(null); } })
            .finally(() => { if (req === reqRef.current) setLoading(false); });
    }, [open, fixtureId]);

    const ordered = useMemo(() => {
        const list = [...(markets ?? [])];
        const rank = (m: string) => { const i = MARKET_ORDER.indexOf(m); return i < 0 ? 999 : i; };
        return list.sort((a, b) => rank(a.market) - rank(b.market) || a.market.localeCompare(b.market));
    }, [markets]);

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
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— back / lay</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[92vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Quote Betfair <span className="text-amber-400">·</span> {homeName} vs {awayName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            Tutti i mercati Betfair pre-partita, <span className="text-sky-300 font-bold">back</span> e <span className="text-rose-300 font-bold">lay</span>. {leagueName}.
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
                        {!loading && !error && ordered.length === 0 && (
                            <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                                <p className="text-amber-400 font-bold">Nessuna quota Betfair per questa partita</p>
                                <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto">
                                    Le quote compaiono dopo aver eseguito la fetch Betfair (<span className="font-mono">betfair_full_odds.py</span>).
                                </p>
                            </div>
                        )}
                        {!loading && !error && ordered.length > 0 && (
                            <>
                                {/* legenda colonne */}
                                <div className="flex items-center justify-end gap-1 pr-1 text-[9px] uppercase tracking-widest font-bold">
                                    <span className="w-[164px] text-center text-sky-300">Back</span>
                                    <span className="w-[164px] text-center text-rose-300">Lay</span>
                                </div>
                                {ordered.map(mk => (
                                    <div key={mk.market} className="glass-card rounded-xl border border-white/10 px-3 py-3">
                                        <div className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">{mk.market}</div>
                                        <div className="space-y-1">
                                            {mk.runners.map((r, i) => (
                                                <div key={`${r.selection}-${i}`} className="flex items-center gap-1">
                                                    <span className="flex-1 text-xs text-white/80 truncate min-w-0 pr-1">{r.selection}</span>
                                                    {/* back: migliore vicino allo spread (indici 2,1,0) */}
                                                    <div className="flex gap-1">
                                                        {[2, 1, 0].map(k => <PriceCell key={`b${k}`} lvl={r.back?.[k]} kind="back" />)}
                                                    </div>
                                                    {/* lay: migliore subito a sinistra (indici 0,1,2) */}
                                                    <div className="flex gap-1">
                                                        {[0, 1, 2].map(k => <PriceCell key={`l${k}`} lvl={r.lay?.[k]} kind="lay" />)}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
