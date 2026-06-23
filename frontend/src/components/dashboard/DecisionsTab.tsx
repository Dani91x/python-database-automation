// ============================================================================
// Tab DECISIONI — selettore della LOGICA DECISIONALE monitorata:
//   - 'google_sheets' (reale)  → DecisionsView (layer decisioni)
//   - una STRATEGIA salvata     → monitor virtuale (run_strategy → BacktestResults)
// La performance della strategia si ricalcola al volo: si aggiorna da sola ogni
// giorno appena arrivano dati nuovi (architettura virtuale).
// ============================================================================
import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Trash2, AlertTriangle, LineChart } from 'lucide-react';
import DecisionsView from '@/components/dashboard/DecisionsView';
import { BacktestResults } from '@/components/dashboard/CreateStrategy';
import {
    listStrategies, runStrategy, runStrategyRows, deleteStrategy, STRATEGY_GROUP_OPTIONS, pct,
    type Strategy, type BacktestRow, type StrategyBetRow,
} from '@/lib/analytics';

const SELECT_CLS = 'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary/60 transition-colors';
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

export default function DecisionsTab() {
    const [strategies, setStrategies] = useState<Strategy[]>([]);
    const [sel, setSel] = useState<string>('google_sheets');
    const [groupBy, setGroupBy] = useState<string>('market_league');
    const [rows, setRows] = useState<BacktestRow[] | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [bets, setBets] = useState<StrategyBetRow[] | null>(null);
    const [betsLoading, setBetsLoading] = useState(false);

    const loadStrategies = () => listStrategies().then(setStrategies).catch(e => setError(String(e.message || e)));
    useEffect(() => { loadStrategies(); }, []);

    useEffect(() => {
        setBets(null);
        if (sel === 'google_sheets') { setRows(null); return; }
        let alive = true; setLoading(true); setError(null);
        runStrategy(sel, groupBy)
            .then(r => { if (alive) setRows(r); })
            .catch(e => { if (alive) setError(String(e.message || e)); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, [sel, groupBy]);

    function loadBets() {
        if (sel === 'google_sheets') return;
        setBetsLoading(true);
        runStrategyRows(sel, 500, 0)
            .then(setBets)
            .catch(e => setError(String(e.message || e)))
            .finally(() => setBetsLoading(false));
    }

    const current = strategies.find(s => s.id === sel);

    async function removeStrategy() {
        if (!current) return;
        if (!window.confirm(`Eliminare la strategia "${current.name}"?`)) return;
        try {
            await deleteStrategy(current.id);
            setSel('google_sheets');
            loadStrategies();
        } catch (e: any) {
            setError('Errore eliminazione: ' + String(e.message || e));
        }
    }

    return (
        <>
            <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                    <div>
                        <label className={LABEL_CLS}>Logica decisionale monitorata</label>
                        <select className={SELECT_CLS} value={sel} onChange={e => setSel(e.target.value)}>
                            <option value="google_sheets">Google Sheets (reale)</option>
                            {strategies.length > 0 && <optgroup label="Strategie salvate">
                                {strategies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </optgroup>}
                        </select>
                    </div>
                    {sel !== 'google_sheets' && (
                        <>
                            <div>
                                <label className={LABEL_CLS}>Raggruppa per</label>
                                <select className={SELECT_CLS} value={groupBy} onChange={e => setGroupBy(e.target.value)}>
                                    {STRATEGY_GROUP_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                            </div>
                            <div className="flex">
                                <Button variant="ghost" size="sm" onClick={removeStrategy} className="text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10">
                                    <Trash2 className="w-3 h-3 mr-1" /> Elimina strategia
                                </Button>
                            </div>
                        </>
                    )}
                </div>
            </Card>

            {error && (
                <Card className="glass-card border-red-500/30 p-4 mb-6">
                    <p className="text-sm text-red-400 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> {error}</p>
                </Card>
            )}

            {sel === 'google_sheets' && <DecisionsView />}

            {sel !== 'google_sheets' && (
                <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                    <div className="flex items-center gap-2 mb-4">
                        <LineChart className="w-4 h-4 text-secondary" />
                        <span className="font-heading font-bold text-sm uppercase tracking-wide">
                            Andamento strategia{current ? ` · ${current.name}` : ''}
                        </span>
                    </div>
                    {loading ? <Skeleton className="h-40 w-full bg-white/5" /> : rows && <BacktestResults rows={rows} />}

                    <div className="mt-4 pt-4 border-t border-white/10">
                        <Button variant="outline" size="sm" onClick={loadBets} disabled={betsLoading}
                            className="border-secondary/40 text-secondary hover:bg-secondary/10">
                            {betsLoading ? 'Carico partite…' : (bets ? 'Ricarica partite' : 'Mostra tutte le partite (certifica i filtri)')}
                        </Button>
                        {bets && <span className="ml-3 text-xs text-muted-foreground">{bets.length} partite (max 500, ordinate per data)</span>}
                    </div>

                    {bets && bets.length > 0 && (
                        <div className="overflow-x-auto mt-3">
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/10">
                                        <th className="text-left px-2 py-1">Data</th>
                                        <th className="text-left px-2 py-1">Lega</th>
                                        <th className="text-left px-2 py-1">Partita</th>
                                        <th className="text-left px-2 py-1">Mercato</th>
                                        <th className="text-right px-2 py-1">Pois</th>
                                        <th className="text-right px-2 py-1">ML</th>
                                        <th className="text-right px-2 py-1">Tac</th>
                                        <th className="text-right px-2 py-1">API+</th>
                                        <th className="text-right px-2 py-1" title="motori concordi">Conc</th>
                                        <th className="text-right px-2 py-1">Rit</th>
                                        <th className="text-right px-2 py-1">FreqΔ</th>
                                        <th className="text-right px-2 py-1">Quota</th>
                                        <th className="text-left px-2 py-1">Fonte</th>
                                        <th className="text-right px-2 py-1">Edge</th>
                                        <th className="text-left px-2 py-1">Stato</th>
                                        <th className="text-center px-2 py-1">Esito</th>
                                        <th className="text-right px-2 py-1">Gol</th>
                                        <th className="text-right px-2 py-1">1°gol</th>
                                        <th className="text-right px-2 py-1">P&L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {bets.map((b, i) => (
                                        <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                                            <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">{b.kickoff ? b.kickoff.slice(0, 10) : '—'}</td>
                                            <td className="px-2 py-1 text-muted-foreground max-w-[120px] truncate">{b.league_name ?? '—'}</td>
                                            <td className="px-2 py-1 whitespace-nowrap">{b.home_team} <span className="text-muted-foreground">v</span> {b.away_team}</td>
                                            <td className="px-2 py-1 text-muted-foreground">{b.market} {b.selection}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.poisson_prob != null ? pct(b.poisson_prob, 0) : '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.ml_prob != null ? pct(b.ml_prob, 0) : '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.tacticai_prob != null ? pct(b.tacticai_prob, 0) : '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.api_over_line != null ? `+${b.api_over_line}` : '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.n_engines_agree ?? '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.delay_current ?? '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.freq_deviation != null ? (b.freq_deviation > 0 ? '+' : '') + pct(b.freq_deviation, 0) : '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.odds != null ? b.odds.toFixed(2) : '—'}</td>
                                            <td className="px-2 py-1 text-muted-foreground">{b.odds_src ?? '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.edge != null ? pct(b.edge, 1) : '—'}</td>
                                            <td className="px-2 py-1 text-muted-foreground">{b.status ?? '—'}</td>
                                            <td className="px-2 py-1 text-center">{!b.settled ? '—' : b.hit ? <span className="text-emerald-400">✓</span> : <span className="text-red-400">✗</span>}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.total_goals != null ? `${b.goals_home}-${b.goals_away}` : '—'}</td>
                                            <td className="px-2 py-1 text-right tabular-nums">{b.first_goal_minute != null ? `${b.first_goal_minute}'` : '—'}</td>
                                            <td className={`px-2 py-1 text-right tabular-nums font-medium ${b.pnl == null ? 'text-muted-foreground' : b.pnl > 0 ? 'text-emerald-400' : b.pnl < 0 ? 'text-red-400' : 'text-amber-300'}`}>
                                                {b.pnl == null ? '—' : (b.pnl > 0 ? '+' : '') + b.pnl.toFixed(2)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </Card>
            )}
        </>
    );
}
