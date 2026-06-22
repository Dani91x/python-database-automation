// ============================================================================
// Vista DECISIONI — analisi del layer decisionale (analytics_decisions).
// Filtra le scommesse per LOGICA DECISIONALE (decision_logic), stato, motore,
// mercato, motivo scarto → ROI / pnl / hit-rate / "perché scartate".
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Filter, RotateCcw, AlertTriangle, Download } from 'lucide-react';
import {
    fetchDecisions, fetchDecisionsFilters, groupsToCsv, downloadCsv, ENGINE_LABEL, MARKET_LABEL,
    DECISIONS_GROUP_OPTIONS, pct,
    type DecisionsFilters, type DecisionsResult, type DecisionsQuery,
} from '@/lib/analytics';

const SELECT_CLS = 'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary/60 transition-colors';
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';
const eur = (v: number | null | undefined) => v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(0)}€`;

export default function DecisionsView() {
    const [filters, setFilters] = useState<DecisionsFilters | null>(null);
    const [result, setResult] = useState<DecisionsResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [q, setQ] = useState<DecisionsQuery>({ groupBy: 'logic' });
    const set = (p: Partial<DecisionsQuery>) => setQ(prev => ({ ...prev, ...p }));
    const reset = () => setQ({ groupBy: 'logic' });

    useEffect(() => { fetchDecisionsFilters().then(setFilters).catch(e => setError(String(e.message || e))); }, []);
    useEffect(() => {
        let alive = true; setLoading(true); setError(null);
        const t = setTimeout(() => {
            fetchDecisions(q).then(r => { if (alive) setResult(r); })
                .catch(e => { if (alive) setError(String(e.message || e)); })
                .finally(() => { if (alive) setLoading(false); });
        }, 250);
        return () => { alive = false; clearTimeout(t); };
    }, [q]);

    const totals = useMemo(() => {
        const gs = result?.groups ?? [];
        return {
            placed: gs.reduce((s, g) => s + g.placed, 0),
            pnl: gs.reduce((s, g) => s + g.pnl, 0),
            stake: gs.reduce((s, g) => s + g.stake, 0),
        };
    }, [result]);
    const totRoi = totals.stake > 0 ? totals.pnl / totals.stake : null;

    function exportCsv() {
        if (!result) return;
        // CSV completo del layer decisioni
        const head = ['gruppo', 'n', 'piazzate', 'scartate', 'no_signal', 'hit_rate', 'roi', 'pnl', 'stake', 'avg_edge', 'avg_odds'];
        const esc = (s: any) => `"${String(s).replace(/"/g, '""')}"`;
        const rows = [head.join(',')];
        for (const g of result.groups) rows.push([esc(g.grp), g.n, g.placed, g.rejected, g.no_signal, g.hit_rate ?? '', g.roi ?? '', g.pnl, g.stake, g.avg_edge ?? '', g.avg_odds ?? ''].join(','));
        downloadCsv(`decisioni_${result.group_by}_${Date.now()}.csv`, rows.join('\n'));
    }

    return (
        <>
            <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                <div className="flex items-center gap-2 mb-4">
                    <Filter className="w-4 h-4 text-secondary" />
                    <span className="font-heading font-bold text-sm uppercase tracking-wide">Filtri decisioni</span>
                    <Button variant="ghost" size="sm" onClick={reset} className="ml-auto text-xs text-muted-foreground hover:text-white">
                        <RotateCcw className="w-3 h-3 mr-1" /> Reset
                    </Button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    <div>
                        <label className={LABEL_CLS}>Logica decisionale</label>
                        <select className={SELECT_CLS} value={q.logic ?? ''} onChange={e => set({ logic: e.target.value || null })}>
                            <option value="">Tutte</option>
                            {(filters?.logics ?? []).map(l => <option key={l.value} value={l.value}>{l.value} ({l.n.toLocaleString('it')})</option>)}
                        </select>
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Stato</label>
                        <select className={SELECT_CLS} value={q.status ?? ''} onChange={e => set({ status: e.target.value || null })}>
                            <option value="">Tutti</option>
                            {(filters?.statuses ?? []).map(s => <option key={s.value} value={s.value}>{s.value} ({s.n.toLocaleString('it')})</option>)}
                        </select>
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Motore</label>
                        <select className={SELECT_CLS} value={q.engine ?? ''} onChange={e => set({ engine: e.target.value || null })}>
                            <option value="">Tutti</option>
                            {(filters?.engines ?? []).map(e => <option key={e.value} value={e.value}>{ENGINE_LABEL[e.value] ?? e.value} ({e.n.toLocaleString('it')})</option>)}
                        </select>
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Mercato</label>
                        <select className={SELECT_CLS} value={q.market ?? ''} onChange={e => set({ market: e.target.value || null })}>
                            <option value="">Tutti</option>
                            {(filters?.markets ?? []).map(m => <option key={m.value} value={m.value}>{MARKET_LABEL[m.value] ?? m.value}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Motivo scarto</label>
                        <select className={SELECT_CLS} value={q.reject ?? ''} onChange={e => set({ reject: e.target.value || null })}>
                            <option value="">Tutti</option>
                            {(filters?.rejects ?? []).map(r => <option key={r.value} value={r.value}>{r.value} ({r.n.toLocaleString('it')})</option>)}
                        </select>
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Raggruppa per</label>
                        <select className={SELECT_CLS} value={q.groupBy ?? 'logic'} onChange={e => set({ groupBy: e.target.value })}>
                            {DECISIONS_GROUP_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                    </div>
                </div>
            </Card>

            {/* KPI riepilogo */}
            {result && (
                <div className="grid grid-cols-3 gap-3 mb-4">
                    <Card className="glass-card border-white/10 p-3 text-center">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Piazzate</div>
                        <div className="font-display font-black text-xl">{totals.placed.toLocaleString('it')}</div>
                    </Card>
                    <Card className="glass-card border-white/10 p-3 text-center">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">P&L totale</div>
                        <div className={`font-display font-black text-xl ${totals.pnl >= 0 ? 'text-primary' : 'text-red-400'}`}>{eur(totals.pnl)}</div>
                    </Card>
                    <Card className="glass-card border-white/10 p-3 text-center">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">ROI</div>
                        <div className={`font-display font-black text-xl ${(totRoi ?? 0) >= 0 ? 'text-primary' : 'text-red-400'}`}>{totRoi == null ? '—' : pct(totRoi)}</div>
                    </Card>
                </div>
            )}

            {error && <Card className="glass-card border-red-500/30 p-4 mb-4 flex items-center gap-2 text-red-400 text-sm"><AlertTriangle className="w-4 h-4" /> {error}</Card>}

            {loading ? (
                <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full bg-white/5" />)}</div>
            ) : result && result.groups.length > 0 ? (
                <Card className="glass-card border-white/10 overflow-hidden">
                    <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                        <span className="font-heading font-bold text-sm">{result.groups.length} gruppi</span>
                        <Button variant="outline" size="sm" onClick={exportCsv} className="h-7 border-white/10 text-xs text-muted-foreground hover:text-white">
                            <Download className="w-3 h-3 mr-1" /> CSV
                        </Button>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left px-4 py-2 font-medium">Gruppo</th>
                                    <th className="text-right px-3 py-2 font-medium">N</th>
                                    <th className="text-right px-3 py-2 font-medium">Piazz.</th>
                                    <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Scart.</th>
                                    <th className="text-right px-3 py-2 font-medium">Hit piazz.</th>
                                    <th className="text-right px-3 py-2 font-medium">ROI</th>
                                    <th className="text-right px-3 py-2 font-medium">P&L</th>
                                    <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Edge med.</th>
                                    <th className="text-right px-4 py-2 font-medium hidden md:table-cell">Quota med.</th>
                                </tr>
                            </thead>
                            <tbody>
                                {result.groups.map(g => {
                                    const roiColor = g.roi == null ? 'text-muted-foreground' : g.roi >= 0 ? 'text-primary' : 'text-red-400';
                                    const pnlColor = g.pnl > 0 ? 'text-primary' : g.pnl < 0 ? 'text-red-400' : 'text-muted-foreground';
                                    return (
                                        <tr key={g.grp} className="border-b border-white/5 hover:bg-white/[0.02]">
                                            <td className="px-4 py-2.5 font-medium">{g.grp}</td>
                                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{g.n.toLocaleString('it')}</td>
                                            <td className="px-3 py-2.5 text-right tabular-nums">{g.placed.toLocaleString('it')}</td>
                                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell">{g.rejected.toLocaleString('it')}</td>
                                            <td className="px-3 py-2.5 text-right tabular-nums">{g.hit_rate == null ? '—' : pct(g.hit_rate)}</td>
                                            <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${roiColor}`}>{g.roi == null ? '—' : pct(g.roi)}</td>
                                            <td className={`px-3 py-2.5 text-right tabular-nums font-medium ${pnlColor}`}>{eur(g.pnl)}</td>
                                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell">{g.avg_edge == null ? '—' : pct(g.avg_edge)}</td>
                                            <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell">{g.avg_odds == null ? '—' : g.avg_odds.toFixed(2)}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </Card>
            ) : (
                <Card className="glass-card border-white/10 p-8 text-center text-muted-foreground text-sm">Nessuna decisione per questi filtri.</Card>
            )}

            <p className="text-[11px] text-muted-foreground/70 mt-6 leading-relaxed">
                <strong className="text-muted-foreground">Decisioni.</strong> Ogni riga = scelta di una <em>logica decisionale</em>
                (oggi <strong>google_sheets</strong>) di piazzare/scartare un segnale. <em>Hit piazz.</em> = % vinte sulle piazzate
                settlate (a 90'). <em>ROI</em> = P&L / stake. <em>Motivo scarto</em> = perché un segnale non è stato giocato.
                Si potranno aggiungere altre logiche decisionali e confrontarle. Dati storici, non garanzia di risultati futuri.
            </p>
        </>
    );
}
