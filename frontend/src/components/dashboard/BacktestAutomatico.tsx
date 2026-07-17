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
    type SandboxRules, type PersistenceType,
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
    const [minEdge, setMinEdge] = useState('');           // % (UI) → frazione (engine)
    const [kellyFraction, setKellyFraction] = useState('0.25'); // frazione di Kelly (engine)
    // sandbox: regola meccanica semplice
    const [ruleMarket, setRuleMarket] = useState('');     // market_type, es. MATCH_ODDS
    const [ruleSide, setRuleSide] = useState<'BACK' | 'LAY'>('BACK');
    const [ruleEntryMinute, setRuleEntryMinute] = useState(''); // entra dopo minuto
    const [ruleEntryPriceMax, setRuleEntryPriceMax] = useState(''); // prezzo max ingresso
    const [ruleSelectionId, setRuleSelectionId] = useState('');     // selezione specifica
    const [ruleStake, setRuleStake] = useState('');       // stake fisso £
    // --- esecuzione (realismo flumine), entrambe le modalità ---
    const [commissionPct, setCommissionPct] = useState('5');   // % commissione Betfair
    const [persistenceType, setPersistenceType] = useState<PersistenceType>('LAPSE');
    // OFF di default (review 17/07): matchare contro i prezzi DISPONIBILI regala
    // fill che il matcher reale potrebbe non dare → edge gonfiato nel percorso
    // ufficiale. ON solo su scelta esplicita, con avviso ben visibile.
    const [availablePrices, setAvailablePrices] = useState(false);
    const [placeLatency, setPlaceLatency] = useState('0.12');  // s
    const [cancelLatency, setCancelLatency] = useState('0.17'); // s

    // --- esecuzione corrente ---
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [activeStatus, setActiveStatus] = useState<BacktestStatus | null>(null);
    const [activeErr, setActiveErr] = useState<string | null>(null);
    const [results, setResults] = useState<BacktestRow[] | null>(null);
    const [resultsLoading, setResultsLoading] = useState(false);
    // true se la run seguita è stata prodotta col matching sui prezzi disponibili
    // (fill ottimistici) → avviso "NON conservativi" sui risultati mostrati.
    const [activeAvailPrices, setActiveAvailPrices] = useState(false);
    const [workerWarn, setWorkerWarn] = useState(false);   // PENDING troppo a lungo → worker giù?
    const unsubRef = useRef<(() => void) | null>(null);
    const pendingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

    // pulizia della sottoscrizione e del timer a smontaggio
    useEffect(() => () => {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        if (pendingTimerRef.current) { clearTimeout(pendingTimerRef.current); pendingTimerRef.current = null; }
    }, []);

    function toggle(eventId: string) {
        setSelected(prev => {
            const n = new Set(prev);
            if (n.has(eventId)) n.delete(eventId); else n.add(eventId);
            return n;
        });
    }

    // segue una richiesta: realtime → a DONE carica i risultati
    function track(id: string, initialStatus: BacktestStatus = 'PENDING', availPrices = false) {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        if (pendingTimerRef.current) { clearTimeout(pendingTimerRef.current); pendingTimerRef.current = null; }
        setActiveId(id);
        setActiveStatus(initialStatus);
        setActiveErr(null);
        setResults(null);
        setWorkerWarn(false);
        setActiveAvailPrices(availPrices);

        // se entro 15s la richiesta non passa a RUNNING, il worker locale
        // probabilmente non è in esecuzione → mostra come avviarlo.
        if (initialStatus === 'PENDING') {
            pendingTimerRef.current = setTimeout(() => setWorkerWarn(true), 15_000);
        }

        const onStatus = (status: BacktestStatus, errDetail: string | null) => {
            setActiveStatus(status);
            setActiveErr(errDetail);
            if (status !== 'PENDING') {
                setWorkerWarn(false);
                if (pendingTimerRef.current) { clearTimeout(pendingTimerRef.current); pendingTimerRef.current = null; }
            }
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

        // Riga già DONE cliccata dallo storico: il realtime notifica solo i
        // CAMBI futuri della riga (mai lo stato corrente) → senza questo fetch
        // immediato i risultati (e i badge coverage/non-conservativo) non
        // comparirebbero mai per le esecuzioni passate.
        if (initialStatus === 'DONE') {
            setResultsLoading(true);
            fetchBacktestResults(id)
                .then(setResults)
                .catch(e => setActiveErr(String(e.message || e)))
                .finally(() => setResultsLoading(false));
        }

        unsubRef.current = subscribeBacktestRequest(id, (row) => {
            if (row) onStatus(row.status, row.error_detail);
        });
    }

    async function run() {
        if (selected.size === 0) { setError('Seleziona almeno una partita registrata.'); return; }
        setSubmitting(true); setError(null);
        try {
            const rules: SandboxRules | undefined = mode === 'sandbox'
                ? {
                    market_type: ruleMarket || null,
                    side: ruleSide,
                    selection_id: numOrUndef(ruleSelectionId) ?? null,
                    entry_minute: numOrUndef(ruleEntryMinute) ?? null,
                    entry_price_max: numOrUndef(ruleEntryPriceMax) ?? null,
                    stake: numOrUndef(ruleStake) ?? null,
                }
                : undefined;
            const id = await requestBacktest({
                event_ids: Array.from(selected),
                mode,
                bankroll: numOrUndef(bankroll),
                min_edge: minEdge.trim() === '' ? undefined : Number(minEdge) / 100,
                kelly_fraction: mode === 'engine' ? (numOrUndef(kellyFraction) ?? undefined) : undefined,
                rules,
                // esecuzione (realismo flumine)
                commission_rate: commissionPct.trim() === '' ? undefined : Number(commissionPct) / 100,
                persistence_type: persistenceType,
                simulation_available_prices: availablePrices,
                place_latency: numOrUndef(placeLatency) ?? undefined,
                cancel_latency: numOrUndef(cancelLatency) ?? undefined,
            });
            track(id, 'PENDING', availablePrices);
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

                    {mode === 'engine' && <>
                        <div><label className={LABEL_CLS}>Edge min %</label><input type="number" step="0.1" placeholder="nessuno" className={INPUT_CLS} value={minEdge} onChange={e => setMinEdge(e.target.value)} /></div>
                        <div><label className={LABEL_CLS}>Frazione Kelly</label><input type="number" min={0} max={1} step="0.05" placeholder="0.25" className={INPUT_CLS} value={kellyFraction} onChange={e => setKellyFraction(e.target.value)} /></div>
                    </>}

                    {mode === 'sandbox' && <>
                        <div><label className={LABEL_CLS}>Mercato (tipo)</label><input type="text" placeholder="tutti — es. MATCH_ODDS" className={INPUT_CLS} value={ruleMarket} onChange={e => setRuleMarket(e.target.value)} /></div>
                        <div>
                            <label className={LABEL_CLS}>Direzione</label>
                            <select className={SELECT_CLS} value={ruleSide} onChange={e => setRuleSide(e.target.value as 'BACK' | 'LAY')}>
                                <option value="BACK">BACK (punta)</option>
                                <option value="LAY">LAY (banca)</option>
                            </select>
                        </div>
                        <div><label className={LABEL_CLS}>Selezione (id)</label><input type="number" placeholder="tutte" className={INPUT_CLS} value={ruleSelectionId} onChange={e => setRuleSelectionId(e.target.value)} /></div>
                        <div><label className={LABEL_CLS}>Minuto ingresso ≥</label><input type="number" min={0} max={130} placeholder="dal 1°" className={INPUT_CLS} value={ruleEntryMinute} onChange={e => setRuleEntryMinute(e.target.value)} /></div>
                        <div><label className={LABEL_CLS}>Prezzo max ingresso</label><input type="number" min={1} step="0.1" placeholder="qualsiasi" className={INPUT_CLS} value={ruleEntryPriceMax} onChange={e => setRuleEntryPriceMax(e.target.value)} /></div>
                        <div><label className={LABEL_CLS}>Stake fisso (£)</label><input type="number" min={0} step="0.5" placeholder="es. 10" className={INPUT_CLS} value={ruleStake} onChange={e => setRuleStake(e.target.value)} /></div>
                    </>}
                </div>

                {/* ---- ESECUZIONE (realismo flumine) ---- */}
                <div className="mt-5 pt-4 border-t border-white/5">
                    <div className="flex items-center gap-2 mb-3">
                        <SlidersHorizontal className="w-3.5 h-3.5 text-muted-foreground" />
                        <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Esecuzione (realismo)</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div><label className={LABEL_CLS}>Commissione %</label><input type="number" min={0} max={20} step="0.5" placeholder="es. 5" className={INPUT_CLS} value={commissionPct} onChange={e => setCommissionPct(e.target.value)} /></div>
                        <div>
                            <label className={LABEL_CLS}>Inmatchato a fine mercato</label>
                            <select className={SELECT_CLS} value={persistenceType} onChange={e => setPersistenceType(e.target.value as PersistenceType)}>
                                <option value="LAPSE">LAPSE (annulla)</option>
                                <option value="PERSIST">PERSIST (porta in-play)</option>
                                <option value="MARKET_ON_CLOSE">MARKET_ON_CLOSE (SP)</option>
                            </select>
                        </div>
                        <div><label className={LABEL_CLS}>Latenza piazz. (s)</label><input type="number" min={0} step="0.01" placeholder="0.12" className={INPUT_CLS} value={placeLatency} onChange={e => setPlaceLatency(e.target.value)} /></div>
                        <div><label className={LABEL_CLS}>Latenza cancel. (s)</label><input type="number" min={0} step="0.01" placeholder="0.17" className={INPUT_CLS} value={cancelLatency} onChange={e => setCancelLatency(e.target.value)} /></div>
                        <div className="col-span-2 md:col-span-4 mt-1">
                            <div className="flex items-center gap-2">
                                <input id="availPrices" type="checkbox" checked={availablePrices} onChange={e => setAvailablePrices(e.target.checked)} className="accent-primary" />
                                <label htmlFor="availPrices" className="text-xs text-muted-foreground cursor-pointer">
                                    Matcha anche contro i prezzi disponibili — fill OTTIMISTICI: assume di prendere
                                    liquidità visibile che il matcher reale potrebbe non dare (edge gonfiato).
                                    OFF = solo volume inmatchato (conservativo, percorso ufficiale).
                                </label>
                            </div>
                            {availablePrices && (
                                <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-2.5 py-1.5 text-xs text-amber-300 flex items-center gap-2">
                                    <AlertTriangle className="w-4 h-4 shrink-0" />
                                    ⚠️ Risultati NON conservativi (fill contro prezzi disponibili): non usarli per certificare un edge.
                                </p>
                            )}
                        </div>
                    </div>
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

                    {running && !workerWarn && <p className="text-xs text-muted-foreground">Il worker locale sta elaborando la simulazione flumine…</p>}

                    {workerWarn && activeStatus === 'PENDING' && (
                        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                            <p className="text-sm text-amber-300 flex items-center gap-2 mb-2">
                                <AlertTriangle className="w-4 h-4 shrink-0" /> Richiesta in coda da oltre 15s: il worker locale non sembra in esecuzione.
                            </p>
                            <p className="text-xs text-muted-foreground mb-1">Avvialo nel terminale (sul PC che ha le registrazioni) e lascialo aperto:</p>
                            <code className="block text-xs bg-black/60 border border-white/10 rounded px-2 py-1.5 text-primary select-all">python -m Betfair.stream.backtest.worker</code>
                            <p className="text-[11px] text-muted-foreground mt-2">Appena parte, prende automaticamente questa richiesta e le successive.</p>
                        </div>
                    )}

                    {activeStatus === 'DONE' && (
                        resultsLoading ? (
                            <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10 w-full bg-white/5" />)}</div>
                        ) : results ? (
                            <>
                                {activeAvailPrices && (
                                    <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/5 px-2.5 py-1.5 text-xs text-amber-300 flex items-center gap-2">
                                        <AlertTriangle className="w-4 h-4 shrink-0" />
                                        ⚠️ Risultati NON conservativi (fill contro prezzi disponibili): run eseguita
                                        matchando liquidità che il matcher reale potrebbe non dare — edge gonfiato.
                                    </p>
                                )}
                                <BacktestResults rows={results} />
                            </>
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
                                        onClick={() => r.status === 'DONE' && track(r.id, r.status, r.params?.simulation_available_prices === true)}
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
