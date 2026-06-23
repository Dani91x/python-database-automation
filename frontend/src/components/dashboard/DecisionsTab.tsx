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
    listStrategies, runStrategy, deleteStrategy, STRATEGY_GROUP_OPTIONS,
    type Strategy, type BacktestRow,
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

    const loadStrategies = () => listStrategies().then(setStrategies).catch(e => setError(String(e.message || e)));
    useEffect(() => { loadStrategies(); }, []);

    useEffect(() => {
        if (sel === 'google_sheets') { setRows(null); return; }
        let alive = true; setLoading(true); setError(null);
        runStrategy(sel, groupBy)
            .then(r => { if (alive) setRows(r); })
            .catch(e => { if (alive) setError(String(e.message || e)); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, [sel, groupBy]);

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
                </Card>
            )}
        </>
    );
}
