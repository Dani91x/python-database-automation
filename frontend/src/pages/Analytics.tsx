// ============================================================================
// /analytics — Centro di controllo: pagella per-motore per-mercato.
// Legge SOLO via RPC aggregati (nessun dato sensibile esposto). Hit-rate con
// intervallo di Wilson 95%. Stesso design system della dashboard.
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, ChevronLeft, Filter, RotateCcw, AlertTriangle } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import {
    fetchAnalytics, fetchAnalyticsFilters, ENGINE_LABEL, MARKET_LABEL,
    GROUP_BY_OPTIONS, pct,
    type AnalyticsFilters, type AnalyticsResult, type AnalyticsQuery,
} from '@/lib/analytics';

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors';
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

// clamp di sicurezza in [0,1] (input utente / valori CI da renderizzare)
const clamp01 = (v: number) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

const SELECTIONS_BY_MARKET: Record<string, string[]> = {
    '1x2': ['H', 'D', 'A'], ht_1x2: ['H', 'D', 'A'],
    over_1_5: ['Over', 'Under'], over_2_5: ['Over', 'Under'], over_3_5: ['Over', 'Under'],
    btts: ['Yes', 'No'], first_half_over_0_5: ['Over', 'Under'],
};

export default function Analytics() {
    const [filters, setFilters] = useState<AnalyticsFilters | null>(null);
    const [result, setResult] = useState<AnalyticsResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [q, setQ] = useState<AnalyticsQuery>({ groupBy: 'confidence' });
    const set = (patch: Partial<AnalyticsQuery>) => setQ(prev => ({ ...prev, ...patch }));
    const reset = () => setQ({ groupBy: 'confidence' });

    // carica i valori dei menu una volta
    useEffect(() => {
        fetchAnalyticsFilters().then(setFilters).catch(e => setError(String(e.message || e)));
    }, []);

    // ricarica i risultati ad ogni cambio filtro (debounce leggero)
    useEffect(() => {
        let alive = true;
        setLoading(true); setError(null);
        const t = setTimeout(() => {
            fetchAnalytics(q)
                .then(r => { if (alive) setResult(r); })
                .catch(e => { if (alive) setError(String(e.message || e)); })
                .finally(() => { if (alive) setLoading(false); });
        }, 250);
        return () => { alive = false; clearTimeout(t); };
    }, [q]);

    const selectionOptions = q.market ? (SELECTIONS_BY_MARKET[q.market] ?? []) : [];
    const totalN = useMemo(() => (result?.groups ?? []).reduce((s, g) => s + g.n, 0), [result]);

    return (
        <div className="min-h-screen bg-black text-white relative">
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            {/* Navbar */}
            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">
                            AI <span className="text-primary">TERMINAL</span>
                        </Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-secondary font-heading font-bold ml-4">
                            <BarChart3 className="w-4 h-4" /> ANALYTICS
                        </span>
                    </div>
                    <Link to="/dashboard">
                        <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                            <ChevronLeft className="w-4 h-4 mr-1" /> Dashboard
                        </Button>
                    </Link>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10">
                <div className="mb-6">
                    <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                        Centro di Controllo <span className="text-primary">Motori</span>
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Pagella per-motore per-mercato sullo storico settlato.
                        {filters && <> {' '}<span className="text-white/70">{filters.total_settled.toLocaleString('it')}</span> segnali settlati.</>}
                    </p>
                </div>

                {/* ---- FILTRI ---- */}
                <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                    <div className="flex items-center gap-2 mb-4">
                        <Filter className="w-4 h-4 text-primary" />
                        <span className="font-heading font-bold text-sm uppercase tracking-wide">Filtri</span>
                        <Button variant="ghost" size="sm" onClick={reset} className="ml-auto text-xs text-muted-foreground hover:text-white">
                            <RotateCcw className="w-3 h-3 mr-1" /> Reset
                        </Button>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                        {/* Motore */}
                        <div>
                            <label className={LABEL_CLS}>Motore</label>
                            <select className={SELECT_CLS} value={q.engine ?? ''} onChange={e => set({ engine: e.target.value || null })}>
                                <option value="">Tutti</option>
                                {(filters?.engines ?? []).map(e => (
                                    <option key={e.value} value={e.value}>{ENGINE_LABEL[e.value] ?? e.value} ({e.n.toLocaleString('it')})</option>
                                ))}
                            </select>
                        </div>
                        {/* Mercato */}
                        <div>
                            <label className={LABEL_CLS}>Mercato</label>
                            <select className={SELECT_CLS} value={q.market ?? ''} onChange={e => set({ market: e.target.value || null, selection: null })}>
                                <option value="">Tutti</option>
                                {(filters?.markets ?? []).map(m => (
                                    <option key={m.value} value={m.value}>{MARKET_LABEL[m.value] ?? m.value}</option>
                                ))}
                            </select>
                        </div>
                        {/* Selezione (dipende dal mercato) */}
                        <div>
                            <label className={LABEL_CLS}>Selezione</label>
                            <select className={SELECT_CLS} value={q.selection ?? ''} disabled={!q.market}
                                onChange={e => set({ selection: e.target.value || null })}>
                                <option value="">Tutte</option>
                                {selectionOptions.map(s => <option key={s} value={s}>{s}</option>)}
                            </select>
                        </div>
                        {/* Lega */}
                        <div>
                            <label className={LABEL_CLS}>Lega</label>
                            <select className={SELECT_CLS} value={q.leagueId ?? ''} onChange={e => set({ leagueId: e.target.value ? Number(e.target.value) : null })}>
                                <option value="">Tutte</option>
                                {(filters?.leagues ?? []).map(l => (
                                    <option key={l.id} value={l.id}>{l.name ?? `Lega ${l.id}`} ({l.n.toLocaleString('it')})</option>
                                ))}
                            </select>
                        </div>
                        {/* Stagione */}
                        <div>
                            <label className={LABEL_CLS}>Stagione</label>
                            <select className={SELECT_CLS} value={q.seasonYear ?? ''} onChange={e => set({ seasonYear: e.target.value ? Number(e.target.value) : null })}>
                                <option value="">Tutte</option>
                                {(filters?.seasons ?? []).map(s => <option key={s} value={s}>{s}</option>)}
                            </select>
                        </div>
                        {/* Confidenza min/max */}
                        <div>
                            <label className={LABEL_CLS}>Confidenza % (min–max)</label>
                            <div className="flex items-center gap-2">
                                <input type="number" min={0} max={100} placeholder="0" className={SELECT_CLS}
                                    value={q.probMin != null ? Math.round(q.probMin * 100) : ''}
                                    onChange={e => set({ probMin: e.target.value === '' ? null : clamp01(Number(e.target.value) / 100) })} />
                                <span className="text-muted-foreground text-xs">–</span>
                                <input type="number" min={0} max={100} placeholder="100" className={SELECT_CLS}
                                    value={q.probMax != null ? Math.round(q.probMax * 100) : ''}
                                    onChange={e => set({ probMax: e.target.value === '' ? null : clamp01(Number(e.target.value) / 100) })} />
                            </div>
                        </div>
                        {/* Concordanza minima */}
                        <div>
                            <label className={LABEL_CLS}>Concordanza min. motori</label>
                            <select className={SELECT_CLS} value={q.minAgree ?? ''} onChange={e => set({ minAgree: e.target.value ? Number(e.target.value) : null })}>
                                <option value="">Qualsiasi</option>
                                <option value="2">≥ 2 motori</option>
                                <option value="3">≥ 3 motori</option>
                                <option value="4">≥ 4 motori</option>
                            </select>
                        </div>
                        {/* Raggruppa per */}
                        <div>
                            <label className={LABEL_CLS}>Raggruppa per</label>
                            <select className={SELECT_CLS} value={q.groupBy ?? 'overall'} onChange={e => set({ groupBy: e.target.value })}>
                                {GROUP_BY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 mt-4">
                        <Checkbox id="placed" checked={!!q.placedOnly} onCheckedChange={v => set({ placedOnly: !!v })} />
                        <label htmlFor="placed" className="text-xs text-muted-foreground cursor-pointer">Solo segnali piazzati</label>
                    </div>
                </Card>

                {/* ---- RISULTATI ---- */}
                {error && (
                    <Card className="glass-card border-red-500/30 p-4 mb-4 flex items-center gap-2 text-red-400 text-sm">
                        <AlertTriangle className="w-4 h-4" /> {error}
                    </Card>
                )}

                {loading ? (
                    <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12 w-full bg-white/5" />)}</div>
                ) : result && result.groups.length > 0 ? (
                    <Card className="glass-card border-white/10 overflow-hidden">
                        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                            <span className="font-heading font-bold text-sm">
                                {result.groups.length} grupp{result.groups.length === 1 ? 'o' : 'i'} · {totalN.toLocaleString('it')} segnali
                            </span>
                            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">CI Wilson 95%</span>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                        <th className="text-left px-4 py-2 font-medium">Gruppo</th>
                                        <th className="text-right px-3 py-2 font-medium">N</th>
                                        <th className="text-right px-3 py-2 font-medium">Hit-rate</th>
                                        <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Intervallo 95%</th>
                                        <th className="text-right px-3 py-2 font-medium">Prob. media</th>
                                        <th className="text-right px-4 py-2 font-medium">Scarto calib.</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.groups.map(g => {
                                        const hr = g.hit_rate;
                                        const hrColor = hr >= 0.6 ? 'text-primary' : hr >= 0.5 ? 'text-secondary' : 'text-red-400';
                                        const gapColor = g.calib_gap > 0.03 ? 'text-primary' : g.calib_gap < -0.03 ? 'text-red-400' : 'text-muted-foreground';
                                        return (
                                            <tr key={g.grp} className="border-b border-white/5 hover:bg-white/[0.02]">
                                                <td className="px-4 py-2.5 font-medium">{g.grp}</td>
                                                <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{g.n.toLocaleString('it')}</td>
                                                <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${hrColor}`}>{pct(hr)}</td>
                                                <td className="px-3 py-2.5 hidden md:table-cell">
                                                    {/* barra CI Wilson */}
                                                    <div className="relative h-2 w-40 bg-white/5 rounded-full overflow-hidden">
                                                        <div className="absolute h-full bg-primary/30"
                                                            style={{ left: `${clamp01(g.wilson_low) * 100}%`, width: `${Math.max(0, (clamp01(g.wilson_high) - clamp01(g.wilson_low)) * 100)}%` }} />
                                                        <div className="absolute h-full w-0.5 bg-primary" style={{ left: `${clamp01(hr) * 100}%` }} />
                                                    </div>
                                                    <span className="text-[10px] text-muted-foreground tabular-nums">{pct(g.wilson_low, 0)}–{pct(g.wilson_high, 0)}</span>
                                                </td>
                                                <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{pct(g.avg_prob)}</td>
                                                <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${gapColor}`}>
                                                    {g.calib_gap > 0 ? '+' : ''}{pct(g.calib_gap)}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                ) : (
                    <Card className="glass-card border-white/10 p-8 text-center text-muted-foreground text-sm">
                        Nessun segnale settlato per questi filtri.
                    </Card>
                )}

                {/* ---- DISCLAIMER (soldi in gioco) ---- */}
                <p className="text-[11px] text-muted-foreground/70 mt-6 leading-relaxed">
                    <strong className="text-muted-foreground">Nota.</strong> Hit-rate = % direzione azzeccata sulle partite
                    <em> settlate</em> (esito a 90'). Intervallo di Wilson 95%: con pochi dati (N basso) la stima è incerta —
                    guarda l'ampiezza dell'intervallo. <em>Scarto calib.</em> = hit-rate − probabilità media: positivo = il motore
                    <em> sottostima</em>, negativo = <em>sovrastima</em>. I dati storici non garantiscono risultati futuri.
                </p>
            </main>
        </div>
    );
}
