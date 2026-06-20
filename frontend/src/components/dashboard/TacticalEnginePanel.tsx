// ============================================================================
// Pannello TACTICAL ENGINE (GSG) — terzo motore INDIPENDENTE ispirato a TacticAI.
// Forze att/dif INFERITE (Dixon-Coles MLE) + simmetria Z2 + time-decay.
// Dati: letti dal DATABASE Supabase (colonna tactical_engine_json), stesso
// pattern di fetch asincrono del PoissonPanel. Stesso guscio/stile.
// NON modifica PoissonPanel ne' altri componenti.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, Network, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { ProbBarChart, ProbBar } from './ProbBarChart';
import { pctFmt, numFmt } from '@/lib/fixtureModels';
import { fetchTacticalEngine, buildAdvice, TEFixture, TEMarkets } from '@/lib/tacticalEngine';

interface Props {
    fixtureId: string;
    leagueName: string;
    homeName: string;
    awayName: string;
}

const GREEN = 'hsl(155 84% 42%)';
const AMBER = '#f59e0b';
const GRAY = '#94a3b8';

const MARKETS: { id: string; label: string }[] = [
    { id: '1x2', label: '1X2' },
    { id: 'over_1_5', label: 'Over 1.5' },
    { id: 'over_2_5', label: 'Over 2.5' },
    { id: 'over_3_5', label: 'Over 3.5' },
    { id: 'btts', label: 'BTTS' },
    { id: 'ht_1x2', label: 'HT 1X2' },
    { id: 'ht_over_0_5', label: '1°T Over 0.5' },
];

const chipCls = (active: boolean) =>
    `px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${active
        ? 'bg-primary/20 text-primary border-primary/40'
        : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10 hover:text-white'}`;

function barsFor(marketId: string, m: TEMarkets, ht: TEMarkets | null): ProbBar[] {
    switch (marketId) {
        case '1x2':
            return [
                { label: '1 (Casa)', value: m.home, color: GREEN },
                { label: 'X (Pari)', value: m.draw, color: GRAY },
                { label: '2 (Trasf.)', value: m.away, color: AMBER },
            ];
        case 'over_1_5':
            return [{ label: 'Over 1.5', value: m.over_1_5, color: GREEN }, { label: 'Under 1.5', value: m.under_1_5, color: AMBER }];
        case 'over_2_5':
            return [{ label: 'Over 2.5', value: m.over_2_5, color: GREEN }, { label: 'Under 2.5', value: m.under_2_5, color: AMBER }];
        case 'over_3_5':
            return [{ label: 'Over 3.5', value: m.over_3_5, color: GREEN }, { label: 'Under 3.5', value: m.under_3_5, color: AMBER }];
        case 'btts':
            return [{ label: 'Sì', value: m.btts_yes, color: GREEN }, { label: 'No', value: m.btts_no, color: AMBER }];
        case 'ht_1x2':
            return ht ? [
                { label: '1 (Casa)', value: ht.home, color: GREEN },
                { label: 'X (Pari)', value: ht.draw, color: GRAY },
                { label: '2 (Trasf.)', value: ht.away, color: AMBER },
            ] : [];
        case 'ht_over_0_5':
            return ht ? [{ label: 'Over 0.5', value: ht.over_0_5, color: GREEN }, { label: 'Under 0.5', value: ht.under_0_5, color: AMBER }] : [];
        default:
            return [];
    }
}

export function TacticalEnginePanel({ fixtureId, leagueName, homeName, awayName }: Props) {
    const [open, setOpen] = useState(false);
    const [data, setData] = useState<TEFixture | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [marketId, setMarketId] = useState('1x2');
    const reqRef = useRef(0);

    // fetch all'apertura / cambio fixture
    useEffect(() => {
        if (!open) return;
        const req = ++reqRef.current;
        setLoading(true);
        setError(null);
        fetchTacticalEngine(fixtureId)
            .then(d => { if (req === reqRef.current) setData(d); })
            .catch(e => { if (req === reqRef.current) { setError(e.message || 'Errore di caricamento'); setData(null); } })
            .finally(() => { if (req === reqRef.current) setLoading(false); });
    }, [open, fixtureId]);

    const f = data;

    const available = useMemo(() => {
        if (!f) return [] as typeof MARKETS;
        return MARKETS.filter(mk => (mk.id.startsWith('ht_') ? f.markets_ht != null : true));
    }, [f]);

    const bars = useMemo(() => {
        if (!f) return [] as ProbBar[];
        return barsFor(available.some(a => a.id === marketId) ? marketId : '1x2', f.markets, f.markets_ht);
    }, [f, marketId, available]);

    const topBar = useMemo(
        () => bars.reduce<ProbBar | null>((best, b) => (best && best.value >= b.value ? best : b), null),
        [bars],
    );
    const genDate = f?.generated_at ? new Date(f.generated_at) : null;

    return (
        <>
            <div className="mb-8 flex justify-center">
                <Button
                    onClick={() => setOpen(true)}
                    variant="outline"
                    className="glass-card border-white/10 hover:border-primary/40 text-white font-bold h-12 px-6 rounded-xl gap-2 hover:bg-white/5"
                >
                    <Network className="w-5 h-5 text-primary" />
                    Tactical Engine
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— GSG (forze inferite)</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[92vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Tactical Engine <span className="text-primary">·</span> {homeName} vs {awayName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            Terzo motore (GSG): forze attacco/difesa <strong>inferite</strong> per massima verosimiglianza
                            (Dixon-Coles) con simmetria casa/trasferta. {leagueName}. Probabilità del modello, non quote.
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
                        {!loading && !error && !f && (
                            <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                                <p className="text-amber-400 font-bold">Tactical Engine non disponibile per questa partita</p>
                                <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto">
                                    Il motore richiede storico sufficiente PRECEDENTE alla partita (previsione leakage-free).
                                </p>
                            </div>
                        )}

                        {!loading && !error && f && (
                            <>
                                {/* meta bar diagnostica */}
                                <div className="glass-card rounded-xl border border-white/10 px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                                    <span className="text-sm font-bold text-white">{f.engine_version}</span>
                                    {f.neutral && (
                                        <span className="px-2 py-0.5 rounded-md text-[10px] font-bold border bg-sky-500/15 text-sky-400 border-sky-500/30">campo neutro</span>
                                    )}
                                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold border bg-emerald-500/15 text-emerald-400 border-emerald-500/30">leakage-free</span>
                                    <span>λ casa <span className="text-primary font-mono font-bold">{numFmt(f.lambda_home)}</span></span>
                                    <span>λ trasf. <span className="text-amber-400 font-mono font-bold">{numFmt(f.lambda_away)}</span></span>
                                    <span>ρ DC <span className="font-mono">{numFmt(f.training.rho)}</span></span>
                                    <span>storico <span className="font-mono">{f.training.n_matches}</span> partite</span>
                                    <span className={`font-bold ${f.training.converged ? 'text-emerald-400' : 'text-amber-400'}`}>
                                        {f.training.converged ? '✓ converged' : '⚠ non conv.'}
                                    </span>
                                    {genDate && <span className="text-[11px] text-muted-foreground/70">{genDate.toLocaleString('it-IT')}</span>}
                                </div>

                                {/* gol attesi + forze squadre */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    <div className="glass-card rounded-xl border border-white/10 px-4 py-3">
                                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Gol attesi</div>
                                        <div className="flex items-center justify-between text-sm">
                                            <span className="text-white font-bold">{f.home_name}</span>
                                            <span className="text-primary font-mono font-black text-lg">{numFmt(f.exp_goals_home)}</span>
                                        </div>
                                        <div className="flex items-center justify-between text-sm mt-1">
                                            <span className="text-white font-bold">{f.away_name}</span>
                                            <span className="text-amber-400 font-mono font-black text-lg">{numFmt(f.exp_goals_away)}</span>
                                        </div>
                                    </div>
                                    <div className="glass-card rounded-xl border border-white/10 px-4 py-3">
                                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">
                                            Forze inferite (att &gt;1 forte · dif &lt;1 solida)
                                        </div>
                                        <div className="flex items-center justify-between text-xs">
                                            <span className="text-white font-bold">{f.home_name}</span>
                                            <span className="font-mono">att <span className="text-primary font-bold">{numFmt(f.strength_home.att)}</span> · dif <span className="text-primary font-bold">{numFmt(f.strength_home.def_factor)}</span></span>
                                        </div>
                                        <div className="flex items-center justify-between text-xs mt-1">
                                            <span className="text-white font-bold">{f.away_name}</span>
                                            <span className="font-mono">att <span className="text-amber-400 font-bold">{numFmt(f.strength_away.att)}</span> · dif <span className="text-amber-400 font-bold">{numFmt(f.strength_away.def_factor)}</span></span>
                                        </div>
                                    </div>
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
                                    <div className="mt-2 text-[10px] text-muted-foreground/70 text-center">
                                        Probabilità del modello (non quote). Forze stimate tenendo conto della forza degli avversari.
                                    </div>
                                </div>

                                {/* risultati esatti */}
                                <div className="glass-card rounded-xl border border-white/10 px-4 py-3">
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Risultati esatti più probabili</div>
                                    <div className="flex flex-wrap gap-2">
                                        {f.top_scores.map((s, i) => (
                                            <span key={i} className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-sm font-mono text-white">
                                                {s.h}-{s.a} <span className="text-primary font-bold ml-1">{pctFmt(s.p, 0)}</span>
                                            </span>
                                        ))}
                                    </div>
                                </div>

                                {/* esito reale (trasparenza: dato = realtà) */}
                                {f.actual && (
                                    <div className="glass-card rounded-xl border border-white/10 px-4 py-3 flex flex-wrap items-center gap-3">
                                        <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Esito reale (90')</span>
                                        <span className="text-lg font-mono font-black text-white">{f.actual.home_goals}-{f.actual.away_goals}</span>
                                        {f.predicted_correct_1x2 != null && (
                                            f.predicted_correct_1x2 ? (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                                    <CheckCircle2 className="w-3.5 h-3.5" /> 1X2 azzeccato
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold bg-red-500/10 text-red-400 border border-red-500/30">
                                                    <XCircle className="w-3.5 h-3.5" /> 1X2 sbagliato
                                                </span>
                                            )
                                        )}
                                    </div>
                                )}

                                {/* consiglio parlante */}
                                <div className="glass-card rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
                                    <div className="text-[10px] uppercase tracking-widest text-primary mb-1 font-bold">Consiglio</div>
                                    <p className="text-sm text-white/90 leading-relaxed">{buildAdvice(f)}</p>
                                </div>
                            </>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
