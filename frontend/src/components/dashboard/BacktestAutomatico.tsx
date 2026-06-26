// ============================================================================
// Backtest Automatico — backtest UFFICIALE via FlumineSimulation (worker locale).
// Flusso: scegli una o più partite registrate (list_replays) + modalità (Motore
// Live / sandbox) + parametri → request_backtest (inserisce la richiesta) →
// segui lo stato in Realtime (PENDING/RUNNING) → a DONE carica i risultati
// (list_backtest_results) e li mostra con il componente riusato <BacktestResults>.
// Le metriche derivano SOLO dal settlement flumine. Stesso design system.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Play, AlertTriangle, FlaskConical, Loader2, CheckCircle2, History, Cpu, SlidersHorizontal } from 'lucide-react';
import { BacktestResults } from '@/components/dashboard/CreateStrategy';
import { fetchReplayList, type ReplayItem } from '@/lib/live';
import {
    requestBacktest, fetchBacktestRuns, fetchBacktestResults, subscribeBacktestRequest,
    BACKTEST_STATUS_LABEL,
    type BacktestMode, type BacktestStatus, type BacktestRunRequest, type BacktestRow,
} from '@/lib/analytics';

const SELECT_CLS = 'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary/60 transition-colors';
const INPUT_CLS = SELECT_CLS;
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const numOrUndef = (s: string): number | undefined => (s.trim() === '' ? undefined : Number(s));

const STATUS_CLS: Record<BacktestStatus, string> = {
    PENDING: 'text-amber-300',
    RUNNING: 'text-secondary',
    DONE: 'text-primary',
    ERROR: 'text-red-400',
};

export default function BacktestAutomatico() {
    // --- partite registrate selezionabili ---
    const [replays, setReplays] = useState<ReplayItem[]>([]);
    const [replaysLoading, setReplaysLoading] = useState(true);
    const [selected, setSelected] = useState<Set<string>>(new Set());

    // --- parametri richiesta ---
    const [mode, setMode] = useState<BacktestMode>('engine');
    const [bankroll, setBankroll] = useState('1000');
    const [minEdge, setMinEdge] = useState('');           // % (UI) → frazione
    // sandbox: regole semplici
    const [ruleMarket, setRuleMarket] = useState('');     // es. MATCH_ODDS
    const [ruleProbMin, setRuleProbMin] = useState('');   // % min prob modello
    const [ruleStake, setRuleStake] = useState('');       // stake fisso £

    // --- esecuzione corrente ---
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [activeStatus, setActiveStatus] = useState<BacktestStatus | null>(null);
    const [activeErr, setActiveErr] = useState<string | null>(null);
    const [results, setResults] = useState<BacktestRow[] | null>(null);
    const [resultsLoading, setResultsLoading] = useState(false);
    const unsubRef = useRef<(() => void) | null>(null);

    // --- esecuzioni recenti ---
    const [runs, setRuns] = useState<BacktestRunRequest[]>([]);

    useEffect(() => {
        let alive = true;
        fetchReplayList(100)
            .then(rows => { if (alive) setReplays(rows); })
            .catch(e => { if (alive) setError(String(e.message || e)); })
            .finally(() => { if (alive) setReplaysLoading(false); });
        loadRuns();
        return () => { alive = false; };
    }, []);

    function loadRuns() {
        fetchBacktestRuns().then(setRuns).catch(e => console.warn('[BacktestAutomatico] fetchBacktestRuns:', e));
    }

    // pulizia della sottoscrizione a smontaggio
    useEffect(() => () => { if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; } }, []);

    function toggle(eventId: string) {
        setSelected(prev => {
            const n = new Set(prev);
            if (n.has(eventId)) n.delete(eventId); else n.add(eventId);
            return n;
        });
    }

    // segue una richiesta: realtime → a DONE carica i risultati
    function track(id: string, initialStatus: BacktestStatus = 'PENDING') {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        setActiveId(id);
        setActiveStatus(initialStatus);
        setActiveErr(null);
        setResults(null);

        const onStatus = (status: BacktestStatus, errDetail: string | null) => {
            setActiveStatus(status);
            setActiveErr(errDetail);
            if (status === 'DONE') {
                setResultsLoading(true);
                fetchBacktestResults(id)
                    .then(setResults)
                    .catch(e => setActiveErr(String(e.message || e)))
                    .finally(() => setResultsLoading(false));
                loadRuns();
            } else if (status === 'ERROR') {
                loadRuns();
            }
        };

        unsubRef.current = subscribeBacktestRequest(id, (row) => {
            if (row) onStatus(row.status, row.error_detail);
        });
    }

    async function run() {
        if (selected.size === 0) { setError('Seleziona almeno una partita registrata.'); return; }
        setSubmitting(true); setError(null);
        try {
            const rules = mode === 'sandbox'
                ? {
                    market: ruleMarket || null,
                    prob_min: ruleProbMin.trim() === '' ? null : Number(ruleProbMin) / 100,
                    stake: numOrUndef(ruleStake) ?? null,
                }
                : undefined;
            const id = await requestBacktest({
                event_ids: Array.from(selected),
                mode,
                bankroll: numOrUndef(bankroll),
                min_edge: minEdge.trim() === '' ? undefined : Number(minEdge) / 100,
                rules,
            });
            track(id, 'PENDING');
            loadRuns();
        } catch (e: any) {
            setError(String(e.message || e));
        } finally {
            setSubmitting(false);
        }
    }

    const running = activeStatus === 'PENDING' || activeStatus === 'RUNNING';

    return (
        <>
            {/* ---- SELEZIONE PARTITE ---- */}
            <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                <div className="flex items-center gap-2 mb-4">
                    <History className="w-4 h-4 text-primary" />
                    <span className="font-heading font-bold text-sm uppercase tracking-wide">Partite registrate</span>
                    <span className="ml-auto text-xs text-muted-foreground">{selected.size} selezionate</span>
                </div>

                {replaysLoading ? (
                    <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full bg-white/5" />)}</div>
                ) : replays.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nessuna partita registrata disponibile.</p>
                ) : (
                    <div className="max-h-64 overflow-y-auto rounded-lg border border-white/5 divide-y divide-white/5">
                        {replays.map(r => {
                            const on = selected.has(r.event_id);
                            return (
                                <button key={r.event_id} onClick={() => toggle(r.event_id)}
                                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${on ? 'bg-primary/10' : 'hover:bg-white/5'}`}>
                                    <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${on ? 'bg-primary border-primary' : 'border-white/20'}`}>
                                        {on && <CheckCircle2 className="w-3 h-3 text-black" />}
                                    </span>
                                    <span className="flex-1 min-w-0">
                                        <span className="block text-sm text-white truncate">{r.home_name} v {r.away_name}</span>
                                        <span className="block text-[11px] text-muted-foreground truncate">
                                            {r.league_name ?? '—'} · {new Date(r.open_date).toLocaleDateString('it')}
                                            {r.n_markets != null && <> · {r.n_markets} mercati</>}
                                            {r.n_snapshots != null && <> · {r.n_snapshots.toLocaleString('it')} snapshot</>}
                                        </span>
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                )}
            </Card>

            {/* ---- PARAMETRI ---- */}
            <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                <div className="flex items-center gap-2 mb-4">
                    <FlaskConical className="w-4 h-4 text-primary" />
                    <span className="font-heading font-bold text-sm uppercase tracking-wide">Configurazione backtest</span>
                </div>

                {/* modalità */}
                <div className="flex gap-2 mb-4">
                    <Button variant={mode === 'engine' ? 'default' : 'outline'} size="sm" onClick={() => setMode('engine')}
                        className={mode === 'engine' ? 'bg-primary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}>
                        <Cpu className="w-3 h-3 mr-1" /> Motore Live
                    </Button>
                    <Button variant={mode === 'sandbox' ? 'default' : 'outline'} size="sm" onClick={() => setMode('sandbox')}
                        className={mode === 'sandbox' ? 'bg-secondary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}>
                        <SlidersHorizontal className="w-3 h-3 mr-1" /> Sandbox (regole)
                    </Button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div><label className={LABEL_CLS}>Bankroll (£)</label><input type="number" min={0} step="1" className={INPUT_CLS} value={bankroll} onChange={e => setBankroll(e.target.value)} /></div>
                    <div><label className={LABEL_CLS}>Edge min %</label><input type="number" step="0.1" placeholder="nessuno" className={INPUT_CLS} value={minEdge} onChange={e => setMinEdge(e.target.value)} /></div>

                    {mode === 'sandbox' && <>
                        <div><label className={LABEL_CLS}>Mercato (tipo)</label><input type="text" placeholder="es. MATCH_ODDS" className={INPUT_CLS} value={ruleMarket} onChange={e => setRuleMarket(e.target.value)} /></div>
                        <div><label className={LABEL_CLS}>Prob. modello ≥ %</label><input type="number" min={0} max={100} placeholder="es. 60" className={INPUT_CLS} value={ruleProbMin} onChange={e => setRuleProbMin(e.target.value)} /></div>
                        <div><label className={LABEL_CLS}>Stake fisso (£)</label><input type="number" min={0} step="0.5" placeholder="es. 10" className={INPUT_CLS} value={ruleStake} onChange={e => setRuleStake(e.target.value)} /></div>
                    </>}
                </div>

                <div className="flex flex-wrap items-center gap-3 mt-4">
                    <span className="text-[11px] text-muted-foreground">
                        {mode === 'engine'
                            ? 'Applica il Motore Live #2 alle partite selezionate.'
                            : 'Applica regole/soglie sandbox configurabili alle partite selezionate.'}
                    </span>
                    <Button onClick={run} disabled={submitting || running || selected.size === 0} size="sm" className="ml-auto bg-primary text-black hover:bg-primary/90">
                        <Play className="w-3 h-3 mr-1" /> {submitting ? 'Invio…' : 'Esegui backtest'}
                    </Button>
                </div>
            </Card>

            {error && (
                <Card className="glass-card border-red-500/30 p-4 mb-6">
                    <p className="text-sm text-red-400 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> {error}</p>
                </Card>
            )}

            {/* ---- STATO ESECUZIONE / RISULTATI ---- */}
            {activeId && (
                <Card className="glass-card border-white/10 p-4 md:p-5 mb-6">
                    <div className="flex items-center gap-2 mb-3">
                        {running ? <Loader2 className="w-4 h-4 text-secondary animate-spin" />
                            : activeStatus === 'DONE' ? <CheckCircle2 className="w-4 h-4 text-primary" />
                            : activeStatus === 'ERROR' ? <AlertTriangle className="w-4 h-4 text-red-400" />
                            : null}
                        <span className="font-heading font-bold text-sm uppercase tracking-wide">
                            Backtest <span className={activeStatus ? STATUS_CLS[activeStatus] : ''}>{activeStatus ? BACKTEST_STATUS_LABEL[activeStatus] : ''}</span>
                        </span>
                        <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">{activeId.slice(0, 8)}</span>
                    </div>

                    {activeErr && (
                        <p className="text-sm text-red-400 flex items-center gap-2 mb-3"><AlertTriangle className="w-4 h-4" /> {activeErr}</p>
                    )}

                    {running && <p className="text-xs text-muted-foreground">Il worker locale sta elaborando la simulazione flumine…</p>}

                    {activeStatus === 'DONE' && (
                        resultsLoading ? (
                            <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10 w-full bg-white/5" />)}</div>
                        ) : results ? (
                            <BacktestResults rows={results} />
                        ) : null
                    )}
                </Card>
            )}

            {/* ---- ESECUZIONI RECENTI ---- */}
            <Card className="glass-card border-white/10 overflow-hidden">
                <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                    <span className="font-heading font-bold text-sm">Esecuzioni recenti</span>
                    <span className="text-[10px] text-muted-foreground uppercase tracking-wider">clic = rivedi risultati</span>
                </div>
                {runs.length === 0 ? (
                    <p className="p-6 text-center text-sm text-muted-foreground">Nessun backtest eseguito.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left px-4 py-2 font-medium">Quando</th>
                                    <th className="text-left px-3 py-2 font-medium">Modalità</th>
                                    <th className="text-right px-3 py-2 font-medium">Partite</th>
                                    <th className="text-left px-3 py-2 font-medium">Stato</th>
                                </tr>
                            </thead>
                            <tbody>
                                {runs.map(r => (
                                    <tr key={r.id}
                                        onClick={() => r.status === 'DONE' && track(r.id, r.status)}
                                        className={`border-b border-white/5 ${r.status === 'DONE' ? 'cursor-pointer hover:bg-white/[0.04]' : ''} ${activeId === r.id ? 'bg-white/[0.04]' : ''}`}>
                                        <td className="px-4 py-2.5 text-muted-foreground tabular-nums">{new Date(r.created_at).toLocaleString('it')}</td>
                                        <td className="px-3 py-2.5 text-white">{r.params?.mode === 'sandbox' ? 'Sandbox' : 'Motore Live'}</td>
                                        <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{r.params?.event_ids?.length ?? 0}</td>
                                        <td className={`px-3 py-2.5 font-medium ${STATUS_CLS[r.status]}`}>{BACKTEST_STATUS_LABEL[r.status]}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
        </>
    );
}
