// ============================================================================
// Crea Strategia — imposta i filtri, esegui il BACKTEST (backtest_strategy) e
// salva la strategia (nome + filtri). Money-critical: i numeri vengono dall'RPC
// certificato (ROI netto back/lay, hit-rate Wilson, catena quote Betfair→book).
// Esporta anche BacktestResults, riusato dal monitor nel tab Decisioni.
// ============================================================================
import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Play, Save, AlertTriangle, FlaskConical } from 'lucide-react';
import {
    fetchBacktest, saveStrategy, STRATEGY_GROUP_OPTIONS, MARKET_LABEL, pct,
    type StrategyFilters, type BacktestRow, type AnalyticsFilters,
} from '@/lib/analytics';

const SELECT_CLS = 'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary/60 transition-colors';
const INPUT_CLS = SELECT_CLS;
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const MARKETS = ['1x2', 'ht_1x2', 'over_1_5', 'over_2_5', 'over_3_5', 'btts', 'first_half_over_0_5'];
const SELS: Record<string, string[]> = {
    '1x2': ['H', 'D', 'A'], ht_1x2: ['H', 'D', 'A'],
    over_1_5: ['Over', 'Under'], over_2_5: ['Over', 'Under'], over_3_5: ['Over', 'Under'],
    btts: ['Yes', 'No'], first_half_over_0_5: ['Over', 'Under'],
};

// numero da input (stringa) → number|null ; pct: divide per 100
const numOrNull = (s: string): number | null => (s.trim() === '' ? null : Number(s));
const pctToFrac = (s: string): number | null => { const v = numOrNull(s); return v == null ? null : v / 100; };
const fracToPct = (v: number | null | undefined): string => (v == null ? '' : String(Math.round(v * 1000) / 10));

// ---------------------------------------------------------------------------
// Tabella risultati backtest (riusata anche dal monitor strategie in Decisioni)
// ---------------------------------------------------------------------------
export function BacktestResults({ rows }: { rows: BacktestRow[] }) {
    if (!rows.length) return <p className="text-sm text-muted-foreground">Nessuna scommessa per questi filtri.</p>;
    const tot = rows.reduce((a, r) => ({
        n: a.n + r.n, ns: a.ns + r.n_settled, nh: a.nh + r.n_hit, np: a.np + r.n_priced, nu: a.nu + r.n_unpriced,
        profit: a.profit + (r.profit ?? 0), turnover: a.turnover + (r.turnover ?? 0),
    }), { n: 0, ns: 0, nh: 0, np: 0, nu: 0, profit: 0, turnover: 0 });
    const totRoi = tot.turnover > 0 ? tot.profit / tot.turnover : null;
    const unpricedPct = tot.ns > 0 ? tot.nu / tot.ns : 0;     // quota scommesse settlate senza prezzo
    // verde solo se profittevole; rosso se in perdita; ambra a break-even (0 NON è profitto)
    const roiCls = (v: number | null) => v == null ? 'text-muted-foreground' : v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-amber-300';
    const roiTxt = (v: number | null) => v == null ? '—' : v === 0 ? 'pari (0%)' : (v > 0 ? '+' : '') + pct(v);

    return (
        <div className="overflow-x-auto">
            <div className="flex flex-wrap gap-4 mb-3 text-sm">
                <span className="text-muted-foreground">Scommesse: <span className="text-white tabular-nums">{tot.n.toLocaleString('it')}</span></span>
                <span className="text-muted-foreground">Settlate: <span className="text-white tabular-nums">{tot.ns.toLocaleString('it')}</span></span>
                <span className="text-muted-foreground">Con quota: <span className="text-white tabular-nums">{tot.np.toLocaleString('it')}</span></span>
                <span className="text-muted-foreground">ROI netto: <span className={`tabular-nums font-bold ${roiCls(totRoi)}`}>{roiTxt(totRoi)}</span></span>
                <span className="text-muted-foreground">Profitto: <span className={`tabular-nums font-bold ${roiCls(tot.profit)}`}>{(tot.profit > 0 ? '+' : '') + tot.profit.toFixed(2)} u</span></span>
            </div>
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/10">
                        <th className="text-left px-3 py-2 font-medium">Gruppo</th>
                        <th className="text-right px-3 py-2 font-medium">N</th>
                        <th className="text-right px-3 py-2 font-medium">Settl.</th>
                        <th className="text-right px-3 py-2 font-medium">Hit-rate</th>
                        <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Wilson 95%</th>
                        <th className="text-right px-3 py-2 font-medium">ROI netto</th>
                        <th className="text-right px-3 py-2 font-medium hidden md:table-cell">CI ROI 95%</th>
                        <th className="text-right px-3 py-2 font-medium">Profitto</th>
                        <th className="text-right px-3 py-2 font-medium hidden lg:table-cell">Q. media</th>
                        <th className="text-right px-3 py-2 font-medium hidden lg:table-cell">No quota</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map(r => (
                        <tr key={r.grp} className="border-b border-white/5 hover:bg-white/5">
                            <td className="px-3 py-2.5 text-white">{r.grp}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{r.n.toLocaleString('it')}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{r.n_settled.toLocaleString('it')}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-medium">{pct(r.hit_rate)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell text-[11px]">{pct(r.wilson_low, 0)}–{pct(r.wilson_high, 0)}</td>
                            <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${roiCls(r.roi)}`}>{roiTxt(r.roi)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell text-[11px]">{r.roi_low == null ? '—' : `${pct(r.roi_low, 1)}–${pct(r.roi_high, 1)}`}</td>
                            <td className={`px-3 py-2.5 text-right tabular-nums ${roiCls(r.profit)}`}>{r.profit == null ? '—' : (r.profit > 0 ? '+' : '') + r.profit.toFixed(2)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden lg:table-cell">{r.avg_odds == null ? '—' : r.avg_odds.toFixed(2)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden lg:table-cell">{r.n_unpriced.toLocaleString('it')}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            {tot.nu > 0 && (
                <p className={`text-[11px] mt-2 flex items-center gap-1 ${unpricedPct > 0.1 ? 'text-red-400' : 'text-muted-foreground'}`}>
                    <AlertTriangle className={`w-3 h-3 ${unpricedPct > 0.1 ? 'text-red-400' : 'text-amber-400'}`} />
                    {tot.nu.toLocaleString('it')} scommesse settlate SENZA quota ({pct(unpricedPct, 1)} delle settlate): contano nel hit-rate ma NON nel ROI.
                    {unpricedPct > 0.1 && <span className="font-bold"> ROI poco affidabile su questo campione.</span>}
                </p>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
export default function CreateStrategy({ filters }: { filters: AnalyticsFilters | null }) {
    const [f, setF] = useState<StrategyFilters>({ direction: 'back', odds_source: 'betfair_book', commission: 0.05, group_by: 'market_league' });
    const set = (p: Partial<StrategyFilters>) => setF(prev => ({ ...prev, ...p }));
    const [rows, setRows] = useState<BacktestRow[] | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [name, setName] = useState('');
    const [saveMsg, setSaveMsg] = useState<string | null>(null);

    async function run() {
        setLoading(true); setError(null); setSaveMsg(null);
        try { setRows(await fetchBacktest(f)); }
        catch (e: any) { setError(String(e.message || e)); }
        finally { setLoading(false); }
    }
    async function save() {
        if (!name.trim()) { setSaveMsg('Inserisci un nome.'); return; }
        try { await saveStrategy(name.trim(), f); setSaveMsg(`Strategia "${name.trim()}" salvata. La trovi nel tab Decisioni.`); }
        catch (e: any) { setSaveMsg('Errore: ' + String(e.message || e)); }
    }

    const sels = f.market ? (SELS[f.market] ?? []) : [];

    return (
        <>
            <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                <div className="flex items-center gap-2 mb-4">
                    <FlaskConical className="w-4 h-4 text-primary" />
                    <span className="font-heading font-bold text-sm uppercase tracking-wide">Crea strategia — filtri</span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {/* Quando */}
                    <div><label className={LABEL_CLS}>Data da</label><input type="date" className={INPUT_CLS} value={f.date_from ?? ''} onChange={e => set({ date_from: e.target.value || null })} /></div>
                    <div><label className={LABEL_CLS}>Data a</label><input type="date" className={INPUT_CLS} value={f.date_to ?? ''} onChange={e => set({ date_to: e.target.value || null })} /></div>
                    {/* Scommessa */}
                    <div><label className={LABEL_CLS}>Mercato</label>
                        <select className={SELECT_CLS} value={f.market ?? ''} onChange={e => set({ market: e.target.value || null, selection: null })}>
                            <option value="">Tutti</option>
                            {MARKETS.map(m => <option key={m} value={m}>{MARKET_LABEL[m] ?? m}</option>)}
                        </select>
                    </div>
                    <div><label className={LABEL_CLS}>Selezione</label>
                        <select className={SELECT_CLS} value={f.selection ?? ''} onChange={e => set({ selection: e.target.value || null })} disabled={!sels.length}>
                            <option value="">Tutte</option>
                            {sels.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </div>
                    <div><label className={LABEL_CLS}>Lega (una)</label>
                        <select className={SELECT_CLS} value={f.leagues?.[0] ?? ''} onChange={e => set({ leagues: e.target.value ? [Number(e.target.value)] : null })}>
                            <option value="">Tutte</option>
                            {(filters?.leagues ?? []).map(l => <option key={l.id} value={l.id}>{l.name ?? l.id} ({l.n.toLocaleString('it')})</option>)}
                        </select>
                    </div>
                    <div><label className={LABEL_CLS}>Direzione</label>
                        <select className={SELECT_CLS} value={f.direction} onChange={e => set({ direction: e.target.value as 'back' | 'lay' })}>
                            <option value="back">Back (punta)</option>
                            <option value="lay">Lay (banca)</option>
                        </select>
                    </div>
                    {/* Motori */}
                    <div><label className={LABEL_CLS}>Poisson ≥ %</label><input type="number" min={0} max={100} className={INPUT_CLS} value={fracToPct(f.poisson_min)} onChange={e => set({ poisson_min: pctToFrac(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>ML ≥ %</label><input type="number" min={0} max={100} className={INPUT_CLS} value={fracToPct(f.ml_min)} onChange={e => set({ ml_min: pctToFrac(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>TacticAI ≥ %</label><input type="number" min={0} max={100} className={INPUT_CLS} value={fracToPct(f.tacticai_min)} onChange={e => set({ tacticai_min: pctToFrac(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>Motori concordi ≥</label><input type="number" min={0} max={3} className={INPUT_CLS} value={f.n_engines_min ?? ''} onChange={e => set({ n_engines_min: numOrNull(e.target.value) })} /></div>
                    {/* Contesto */}
                    <div><label className={LABEL_CLS}>Ritardo =</label><input type="number" min={0} className={INPUT_CLS} value={f.delay_eq ?? ''} onChange={e => set({ delay_eq: numOrNull(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>Ritardo ≥</label><input type="number" min={0} className={INPUT_CLS} value={f.delay_min ?? ''} onChange={e => set({ delay_min: numOrNull(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>Frequenza</label>
                        <select className={SELECT_CLS} value={f.freq_dir ?? ''} onChange={e => set({ freq_dir: (e.target.value || null) as 'below' | 'above' | null })}>
                            <option value="">Indifferente</option>
                            <option value="below">Sotto baseline</option>
                            <option value="above">Sopra baseline</option>
                        </select>
                    </div>
                    {/* Quota / valore */}
                    <div><label className={LABEL_CLS}>Quota min</label><input type="number" step="0.01" className={INPUT_CLS} value={f.min_odds ?? ''} onChange={e => set({ min_odds: numOrNull(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>Quota max</label><input type="number" step="0.01" className={INPUT_CLS} value={f.max_odds ?? ''} onChange={e => set({ max_odds: numOrNull(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>Edge ≥ %</label><input type="number" step="0.1" className={INPUT_CLS} value={fracToPct(f.min_edge)} onChange={e => set({ min_edge: pctToFrac(e.target.value) })} /></div>
                    <div><label className={LABEL_CLS}>Commissione % (def. 5)</label><input type="number" step="0.1" placeholder="5" className={INPUT_CLS} value={fracToPct(f.commission)} onChange={e => set({ commission: pctToFrac(e.target.value) ?? 0.05 })} /></div>
                    {/* Fonte quota / stato / output */}
                    <div><label className={LABEL_CLS}>Fonte quota</label>
                        <select className={SELECT_CLS} value={f.odds_source} onChange={e => set({ odds_source: e.target.value as any })}>
                            <option value="betfair_book">Betfair → bookmaker</option>
                            <option value="betfair">Solo Betfair</option>
                            <option value="book">Solo bookmaker</option>
                        </select>
                    </div>
                    <div><label className={LABEL_CLS}>Stato</label>
                        <select className={SELECT_CLS} value={f.status ?? ''} onChange={e => set({ status: e.target.value || null })}>
                            <option value="">Tutte</option>
                            <option value="PLACED">Solo piazzate</option>
                            <option value="REJECTED">Solo scartate</option>
                            <option value="NO_SIGNAL">No signal</option>
                        </select>
                    </div>
                    <div><label className={LABEL_CLS}>Raggruppa per</label>
                        <select className={SELECT_CLS} value={f.group_by} onChange={e => set({ group_by: e.target.value })}>
                            {STRATEGY_GROUP_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 mt-4">
                    <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer" title="Solo se l'API prevede OVER e la sua linea ≥ linea del mercato. Segnale strutturato ma raro (~2-3% delle partite): può ridurre molto il campione.">
                        <Checkbox checked={!!f.api_over} onCheckedChange={v => set({ api_over: !!v })} /> API dice over (≥ linea) ⓘ
                    </label>
                    <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer" title="Richiede segnale ML certificato no-leak (oos_valid) e affidabile (gate BSS/ECE). Copertura bassa: filtra fortemente.">
                        <Checkbox checked={!!f.ml_clean} onCheckedChange={v => set({ ml_clean: !!v })} /> Solo ML pulito (no-leak + affidabile) ⓘ
                    </label>
                    <Button onClick={run} disabled={loading} size="sm" className="ml-auto bg-primary text-black hover:bg-primary/90">
                        <Play className="w-3 h-3 mr-1" /> {loading ? 'Calcolo…' : 'Esegui backtest'}
                    </Button>
                </div>
            </Card>

            {error && (
                <Card className="glass-card border-red-500/30 p-4 mb-6">
                    <p className="text-sm text-red-400 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> {error}</p>
                </Card>
            )}

            {rows && (
                <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                    <BacktestResults rows={rows} />
                    <div className="flex flex-wrap items-center gap-3 mt-5 pt-4 border-t border-white/10">
                        <input className={INPUT_CLS + ' max-w-xs'} placeholder="Nome strategia…" value={name} onChange={e => setName(e.target.value)} />
                        <Button onClick={save} size="sm" variant="outline" className="border-primary/40 text-primary hover:bg-primary/10">
                            <Save className="w-3 h-3 mr-1" /> Salva strategia
                        </Button>
                        {saveMsg && <span className="text-xs text-muted-foreground">{saveMsg}</span>}
                    </div>
                </Card>
            )}
        </>
    );
}
