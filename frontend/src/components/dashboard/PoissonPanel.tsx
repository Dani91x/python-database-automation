// ============================================================================
// Pannello POISSON — probabilita per-partita del motore Dixon-Coles
// (db_json_analisi). Stesso guscio/stile di MarketFrequencyPanel, MA dati
// per-fixture (snapshot) -> grafico a barre, non serie storica.
// MarketFrequencyPanel.tsx NON viene toccato.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, Sigma, AlertTriangle } from 'lucide-react';
import { ProbBarChart, ProbBar } from './ProbBarChart';
import { PoissonData, fetchPoisson, colorForSelection, pctFmt, numFmt } from '@/lib/fixtureModels';

interface Props {
    fixtureId: string;
    leagueName: string;
    homeName: string;
    awayName: string;
}

// mercati noti del motore, in ordine; selezioni con etichette leggibili
const MARKETS: { id: string; label: string; sel: [string, string][] }[] = [
    { id: '1x2', label: '1X2', sel: [['H', '1 (Casa)'], ['D', 'X (Pari)'], ['A', '2 (Trasf.)']] },
    { id: 'over_1_5', label: 'Over 1.5', sel: [['True', 'Over 1.5'], ['False', 'Under 1.5']] },
    { id: 'over_2_5', label: 'Over 2.5', sel: [['True', 'Over 2.5'], ['False', 'Under 2.5']] },
    { id: 'over_3_5', label: 'Over 3.5', sel: [['True', 'Over 3.5'], ['False', 'Under 3.5']] },
    { id: 'btts', label: 'BTTS', sel: [['True', 'Sì'], ['False', 'No']] },
    { id: 'first_half_over_0_5', label: '1°T Over 0.5', sel: [['True', 'Over 0.5'], ['False', 'Under 0.5']] },
    { id: 'ht_1x2', label: 'HT 1X2', sel: [['H', '1 (Casa)'], ['D', 'X (Pari)'], ['A', '2 (Trasf.)']] },
];

const chipCls = (active: boolean) =>
    `px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${active
        ? 'bg-primary/20 text-primary border-primary/40'
        : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10 hover:text-white'}`;

const toNum = (v: any): number | null => {
    const n = typeof v === 'number' ? v : parseFloat(v);
    return Number.isFinite(n) ? n : null;
};

export function PoissonPanel({ fixtureId, leagueName, homeName, awayName }: Props) {
    const [open, setOpen] = useState(false);
    const [data, setData] = useState<PoissonData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [marketId, setMarketId] = useState<string>('1x2');
    const reqRef = useRef(0);

    // fetch all'apertura / cambio fixture
    useEffect(() => {
        if (!open) return;
        const req = ++reqRef.current;
        setLoading(true);
        setError(null);
        fetchPoisson(fixtureId)
            .then(d => { if (req === reqRef.current) setData(d); })
            .catch(e => { if (req === reqRef.current) { setError(e.message || 'Errore di caricamento'); setData(null); } })
            .finally(() => { if (req === reqRef.current) setLoading(false); });
    }, [open, fixtureId]);

    // mercati realmente presenti nel JSON
    const available = useMemo(() => {
        const m = data?.markets ?? {};
        return MARKETS.filter(def => m[def.id] && typeof m[def.id] === 'object');
    }, [data]);

    // assicura che il mercato selezionato esista
    useEffect(() => {
        if (available.length === 0) return;
        if (!available.some(a => a.id === marketId)) setMarketId(available[0].id);
    }, [available, marketId]);

    const market = available.find(a => a.id === marketId) ?? null;

    const bars: ProbBar[] = useMemo(() => {
        if (!data?.markets || !market) return [];
        const obj = data.markets[market.id] || {};
        return market.sel
            .map(([key, label]) => ({ label, value: toNum(obj[key]) ?? 0, color: colorForSelection(key) }))
            .filter(b => b.value > 0 || true); // mostra anche 0
    }, [data, market]);

    const topBar = useMemo(() => bars.reduce<ProbBar | null>((best, b) => (best && best.value >= b.value ? best : b), null), [bars]);

    const inp = data?.inputs ?? {};
    const fhDetails = market?.id === 'first_half_over_0_5' ? (data?.markets?.first_half_over_0_5?.details ?? null) : null;
    const genDate = data?.generated_at ? new Date(data.generated_at) : null;

    return (
        <>
            <div className="mb-8 flex justify-center">
                <Button
                    onClick={() => setOpen(true)}
                    variant="outline"
                    className="glass-card border-white/10 hover:border-primary/40 text-white font-bold h-12 px-6 rounded-xl gap-2 hover:bg-white/5"
                >
                    <Sigma className="w-5 h-5 text-primary" />
                    Poisson
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— Dixon-Coles</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[92vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Poisson <span className="text-primary">·</span> {homeName} vs {awayName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            Probabilità del motore Dixon-Coles (poisson_xg_hybrid_dc) per questa partita, mercato per mercato. {leagueName}.
                        </SheetDescription>
                    </SheetHeader>

                    <div className="max-w-4xl mx-auto space-y-4">
                        {loading && (
                            <div className="flex items-center justify-center py-24"><Loader2 className="w-10 h-10 text-primary animate-spin" /></div>
                        )}
                        {error && !loading && (
                            <div className="glass-card rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-6 text-center">
                                <p className="text-red-400 font-bold text-sm">Errore: {error}</p>
                            </div>
                        )}
                        {!loading && !error && !data && (
                            <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                                <p className="text-amber-400 font-bold">Poisson non disponibile per questa partita</p>
                                <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto">
                                    Il motore richiede almeno 5 partite giocate per squadra. A inizio stagione o su leghe nuove i dati sono insufficienti.
                                </p>
                            </div>
                        )}

                        {!loading && !error && data && available.length > 0 && (
                            <>
                                {/* meta bar diagnostica */}
                                <div className="glass-card rounded-xl border border-white/10 px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                                    <span className="text-sm font-bold text-white">{data.model ?? 'poisson_xg_hybrid_dc'}</span>
                                    <span>λ casa <span className="text-primary font-mono font-bold">{numFmt(toNum(inp.lambda_home))}</span></span>
                                    <span>λ trasf. <span className="text-amber-400 font-mono font-bold">{numFmt(toNum(inp.lambda_away))}</span></span>
                                    <span>ρ DC <span className="font-mono">{numFmt(toNum(inp.dc_rho))}</span></span>
                                    <span>partite <span className="font-mono">{toNum(inp.home_matches_used) ?? '—'}</span> / <span className="font-mono">{toNum(inp.away_matches_used) ?? '—'}</span></span>
                                    <span>xG <span className={`font-bold ${inp.xg_blend_active ? 'text-emerald-400' : 'text-white/50'}`}>{inp.xg_blend_active ? 'attivo' : 'no'}</span></span>
                                    {genDate && <span className="text-[11px] text-muted-foreground/70">{genDate.toLocaleString('it-IT')}</span>}
                                </div>

                                {/* selettore mercato */}
                                <div>
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Mercato</div>
                                    <div className="flex flex-wrap gap-2">
                                        {available.map(m => (
                                            <button key={m.id} onClick={() => setMarketId(m.id)} className={chipCls(m.id === marketId)}>{m.label}</button>
                                        ))}
                                    </div>
                                </div>

                                {/* grafico */}
                                <div className="glass-card rounded-xl border border-white/10 p-3 md:p-5">
                                    {topBar && (
                                        <div className="flex items-baseline justify-between gap-2 mb-3 pb-3 border-b border-white/5">
                                            <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Più probabile</span>
                                            <span className="text-right">
                                                <span className="text-base md:text-lg font-black text-white">{topBar.label}</span>
                                                <span className="ml-2 text-xl md:text-2xl font-black font-mono" style={{ color: topBar.color }}>{pctFmt(topBar.value, 0)}</span>
                                            </span>
                                        </div>
                                    )}
                                    <ProbBarChart bars={bars} />
                                    {fhDetails && (
                                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                                            <span className="px-2 py-1 rounded-md bg-white/5 border border-white/10">freq empirica <span className="font-mono text-white">{pctFmt(toNum(fhDetails.freq))}</span></span>
                                            <span className="px-2 py-1 rounded-md bg-white/5 border border-white/10">poisson <span className="font-mono text-white">{pctFmt(toNum(fhDetails.poisson))}</span></span>
                                            <span className="px-2 py-1 rounded-md bg-white/5 border border-white/10">peso freq (w) <span className="font-mono text-white">{numFmt(toNum(fhDetails.w_freq))}</span></span>
                                        </div>
                                    )}
                                    <div className="mt-2 text-[10px] text-muted-foreground/70 text-center">
                                        Probabilità del modello (non quote). Le linee disponibili sono solo quelle elaborate dal motore.
                                    </div>
                                </div>
                            </>
                        )}

                        {!loading && !error && data && available.length === 0 && (
                            <div className="glass-card rounded-xl border border-white/10 px-4 py-8 text-center">
                                <p className="text-muted-foreground text-sm">Nessun mercato Poisson elaborato per questa partita.</p>
                            </div>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
