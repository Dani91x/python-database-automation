// ============================================================================
// Frequenze Mercati — pannello di analisi "frequenza storica + media mobile"
// Baseline piatta (frequenza dell'intervallo) + MM5/MM10/MM15 cronologiche
// che oscillano attorno alla baseline, bande ±1σ/±2σ e z-score (MM10).
// Tutta la matematica è server-side (RPC get_market_frequency, verificata
// punto-per-punto contro ricalcolo indipendente): qui solo rendering.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import {
    LineChart, Line, XAxis, YAxis, ReferenceLine, ReferenceArea,
    ResponsiveContainer, Tooltip, CartesianGrid,
} from 'recharts';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, LineChart as LineChartIcon, AlertTriangle, Ban } from 'lucide-react';
import {
    MARKETS, MarketDef, FrequencySeries, LeagueSeason,
    fetchMarketFrequency, fetchLeagueSeasons, formatSeason,
    HT_WARN_THRESHOLD, HT_HARD_THRESHOLD,
} from '@/lib/marketFrequency';

// ---------------------------------------------------------------- costanti UI
const MM_COLORS: Record<'mm5' | 'mm10' | 'mm15', string> = {
    mm5: '#f59e0b',                 // ambra
    mm10: 'hsl(155 84% 42%)',       // primary verde del design system
    mm15: '#60a5fa',                // azzurro
};
const SEASON_B_COLOR = '#f59e0b';
const N_PRESETS = [50, 100, 200, 300, 500, 1000];

const pct = (v: number | null | undefined, digits = 1) =>
    v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`;

const chipCls = (active: boolean) =>
    `px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${active
        ? 'bg-primary/20 text-primary border-primary/40'
        : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10 hover:text-white'}`;

// ---------------------------------------------------------------- tooltip
function FreqTooltip({ active, payload, compare }: any) {
    if (!active || !payload?.length) return null;
    const row = payload[0]?.payload;
    if (!row) return null;
    const block = (p: any, title: string | null) => p ? (
        <div className="mt-1">
            {title && <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{title}</div>}
            <div className="text-xs text-white font-bold">{p.home} – {p.away}</div>
            <div className="text-[11px] text-muted-foreground">
                {new Date(p.date).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' })}
                {' · '}
                <span className={p.out === 1 ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>
                    {p.out === 1 ? '✓ uscito' : '✗ non uscito'}
                </span>
            </div>
            <div className="text-[11px] font-mono mt-0.5 space-x-2">
                {p.mm5 !== null && p.mm5 !== undefined && <span style={{ color: MM_COLORS.mm5 }}>MM5 {pct(p.mm5)}</span>}
                {p.mm10 !== null && p.mm10 !== undefined && <span style={{ color: MM_COLORS.mm10 }}>MM10 {pct(p.mm10)}</span>}
                {p.mm15 !== null && p.mm15 !== undefined && <span style={{ color: MM_COLORS.mm15 }}>MM15 {pct(p.mm15)}</span>}
                {p.z !== null && p.z !== undefined && <span className="text-white/80">z {p.z.toFixed(2)}</span>}
            </div>
        </div>
    ) : null;
    return (
        <div className="rounded-lg border border-white/10 bg-black/90 backdrop-blur-xl px-3 py-2 shadow-2xl max-w-[260px]">
            <div className="text-[10px] text-muted-foreground font-mono">#{row.idx}</div>
            {compare ? (<>{block(row.a, row.aLabel)}{block(row.b, row.bLabel)}</>) : block(row.p, null)}
        </div>
    );
}

// ---------------------------------------------------------------- pannello
interface Props {
    leagueId: number;
    leagueName: string;
}

export function MarketFrequencyPanel({ leagueId, leagueName }: Props) {
    const [open, setOpen] = useState(false);

    // selezione corrente
    const [marketId, setMarketId] = useState<string>('1x2');
    const market: MarketDef = useMemo(() => MARKETS.find(m => m.id === marketId)!, [marketId]);
    const [selection, setSelection] = useState<string>('1');
    const [line, setLine] = useState<number>(2.5);

    // intervallo
    const [mode, setMode] = useState<'last_n' | 'season' | 'all'>('last_n');
    const [lastN, setLastN] = useState<number>(300);
    const [customN, setCustomN] = useState<string>('');
    const [seasonA, setSeasonA] = useState<number | null>(null);
    const [seasonB, setSeasonB] = useState<number | null>(null); // confronto opzionale

    // visualizzazione
    const [showMM, setShowMM] = useState<Record<'mm5' | 'mm10' | 'mm15', boolean>>({ mm5: false, mm10: true, mm15: false });
    const [showBand1, setShowBand1] = useState(true);
    const [showBand2, setShowBand2] = useState(false);
    const compareMM: 'mm5' | 'mm10' | 'mm15' = showMM.mm15 ? 'mm15' : showMM.mm5 ? 'mm5' : 'mm10';

    // dati
    const [seasons, setSeasons] = useState<LeagueSeason[]>([]);
    const [seriesA, setSeriesA] = useState<FrequencySeries | null>(null);
    const [seriesB, setSeriesB] = useState<FrequencySeries | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const reqIdRef = useRef(0);

    const isCompare = mode === 'season' && seasonB !== null && seasonB !== seasonA;

    // cambio mercato → reset selezione/linea coerenti
    const handleMarket = (m: MarketDef) => {
        setMarketId(m.id);
        setSelection(m.selections[0].value);
        if (m.lines && m.lines.length > 0) setLine(m.defaultLine ?? m.lines[0]);
    };

    // stagioni disponibili (al primo open / cambio lega)
    useEffect(() => {
        if (!open) return;
        let stale = false;
        fetchLeagueSeasons(leagueId)
            .then(s => {
                if (stale) return;
                setSeasons(s);
                if (s.length > 0) setSeasonA(prev => (prev !== null && s.some(x => x.season_year === prev)) ? prev : s[0].season_year);
                // seasonB di un'altra lega non è valido qui: resetta se assente
                setSeasonB(prev => (prev !== null && s.some(x => x.season_year === prev)) ? prev : null);
            })
            .catch(() => { if (!stale) setSeasons([]); });
        return () => { stale = true; };
    }, [open, leagueId]);

    // input N custom con debounce (clamp [10, 10000])
    useEffect(() => {
        if (customN === '') return;
        const t = setTimeout(() => {
            const v = parseInt(customN, 10);
            if (!Number.isNaN(v)) setLastN(Math.min(10000, Math.max(10, v)));
        }, 600);
        return () => clearTimeout(t);
    }, [customN]);

    // fetch serie a ogni cambio parametri
    useEffect(() => {
        if (!open) return;
        if (mode === 'season' && seasonA === null) {
            // nessun fetch possibile: pulisci le serie del contesto precedente
            // (evita di mostrare dati di un'altra lega sotto il nuovo titolo)
            setSeriesA(null); setSeriesB(null);
            return;
        }
        const reqId = ++reqIdRef.current;
        setLoading(true);
        setError(null);
        const base = {
            leagueId, market: marketId, selection,
            line: market.lines ? line : null,
            mode, lastN,
        };
        const calls: Promise<FrequencySeries>[] = [
            fetchMarketFrequency({ ...base, seasonYear: mode === 'season' ? seasonA : null }),
        ];
        if (isCompare) calls.push(fetchMarketFrequency({ ...base, seasonYear: seasonB }));
        Promise.all(calls)
            .then(([a, b]) => {
                if (reqId !== reqIdRef.current) return; // risposta superata
                setSeriesA(a);
                setSeriesB(b ?? null);
            })
            .catch(e => {
                if (reqId !== reqIdRef.current) return;
                setError(e.message || 'Errore di caricamento');
                setSeriesA(null); setSeriesB(null);
            })
            .finally(() => { if (reqId === reqIdRef.current) setLoading(false); });
        // deps: isCompare e market.lines sono derivati da mode/seasonA/seasonB/marketId già presenti
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, leagueId, marketId, selection, line, mode, lastN, seasonA, seasonB]);

    // ---- gate HT (informativo: mai nascosto, disabilitato sotto soglia dura)
    const htCov = seriesA?.meta.ht_coverage_pct ?? null;
    const isHt = market.group === 'ht';
    const htHardBlocked = isHt && htCov !== null && htCov < HT_HARD_THRESHOLD;
    const htWarn = isHt && htCov !== null && htCov >= HT_HARD_THRESHOLD && htCov < HT_WARN_THRESHOLD;

    // ---- dataset per il grafico
    const chartData = useMemo(() => {
        if (!seriesA) return [];
        if (!isCompare || !seriesB) {
            return seriesA.points.map(p => ({ idx: p.idx, p, mm5: p.mm5, mm10: p.mm10, mm15: p.mm15 }));
        }
        const len = Math.max(seriesA.points.length, seriesB.points.length);
        const out = [];
        for (let i = 0; i < len; i++) {
            const a = seriesA.points[i] ?? null;
            const b = seriesB.points[i] ?? null;
            out.push({
                idx: i + 1,
                a, b,
                aLabel: formatSeason(seriesA.meta.season_year!), bLabel: formatSeason(seriesB.meta.season_year!),
                aVal: a ? a[compareMM] : null,
                bVal: b ? b[compareMM] : null,
            });
        }
        return out;
    }, [seriesA, seriesB, isCompare, compareMM]);

    // ---- dominio Y dinamico (clampato [0,1], padding 4pt) per leggibilità
    const yDomain = useMemo<[number, number]>(() => {
        if (!seriesA) return [0, 1];
        const vals: number[] = [];
        const collect = (s: FrequencySeries | null) => {
            if (!s) return;
            if (s.meta.baseline !== null) vals.push(s.meta.baseline);
            for (const p of s.points) {
                if (!isCompare) {
                    if (showMM.mm5 && p.mm5 !== null) vals.push(p.mm5);
                    if (showMM.mm10 && p.mm10 !== null) vals.push(p.mm10);
                    if (showMM.mm15 && p.mm15 !== null) vals.push(p.mm15);
                } else if (p[compareMM] !== null) vals.push(p[compareMM]!);
            }
        };
        collect(seriesA); collect(isCompare ? seriesB : null);
        const se = seriesA.meta.se_mm10 ?? 0;
        const b = seriesA.meta.baseline ?? 0.5;
        if (!isCompare && showBand1) { vals.push(b - se, b + se); }
        if (!isCompare && showBand2) { vals.push(b - 2 * se, b + 2 * se); }
        if (vals.length === 0) return [0, 1];
        const lo = Math.max(0, Math.min(...vals) - 0.04);
        const hi = Math.min(1, Math.max(...vals) + 0.04);
        return [Number(lo.toFixed(3)), Number(hi.toFixed(3))];
    }, [seriesA, seriesB, isCompare, showMM, showBand1, showBand2, compareMM]);

    const metaA = seriesA?.meta ?? null;
    const baseline = metaA?.baseline ?? null;
    const seMM10 = metaA?.se_mm10 ?? null;
    const capped = metaA?.mode === 'last_n' && metaA.n_requested !== null && metaA.n_scope < (metaA.n_requested ?? 0);
    const tooShort = (metaA?.n_effective ?? 0) > 0 && (metaA?.n_effective ?? 0) < 15;
    const selLabel = market.selections.find(s => s.value === selection)?.label ?? selection;
    const marketTitle = `${market.label}${market.lines ? ` ${line}` : ''} — ${selLabel}`;

    return (
        <>
            {/* Trigger: subito sotto il blocco Fixture/League ID */}
            <div className="mb-8 flex justify-center">
                <Button
                    onClick={() => setOpen(true)}
                    variant="outline"
                    className="glass-card border-white/10 hover:border-primary/40 text-white font-bold h-12 px-6 rounded-xl gap-2 hover:bg-white/5"
                >
                    <LineChartIcon className="w-5 h-5 text-primary" />
                    Frequenze Mercati
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— {leagueName}</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[92vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Frequenze Mercati <span className="text-primary">·</span> {leagueName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            Frequenza storica del mercato nella lega (baseline) + medie mobili MM5/MM10/MM15 in ordine cronologico di kickoff.
                            Le bande ±σ sono calibrate sull'errore standard della MM10.
                        </SheetDescription>
                    </SheetHeader>

                    <div className="max-w-6xl mx-auto space-y-4">
                        {/* ---- Mercato ---- */}
                        <div>
                            <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Mercato</div>
                            <div className="flex flex-wrap gap-2">
                                {MARKETS.map(m => (
                                    <button key={m.id} onClick={() => handleMarket(m)} className={chipCls(m.id === marketId)}>
                                        {m.label}{m.group === 'ht' && <span className="ml-1 text-[9px] opacity-60">HT</span>}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* ---- Selezione (+ linea per OU) ---- */}
                        <div className="flex flex-col md:flex-row gap-4">
                            <div className="flex-1">
                                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Selezione</div>
                                <div className="flex flex-wrap gap-1.5">
                                    {market.selections.map(s => (
                                        <button key={s.value} onClick={() => setSelection(s.value)} className={chipCls(s.value === selection)}>
                                            {s.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            {market.lines && (
                                <div>
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Linea</div>
                                    <div className="flex flex-wrap gap-1.5">
                                        {market.lines.map(l => (
                                            <button key={l} onClick={() => setLine(l)} className={chipCls(l === line)}>{l}</button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* ---- Intervallo ---- */}
                        <div className="flex flex-col lg:flex-row gap-4">
                            <div>
                                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Intervallo</div>
                                <div className="flex gap-1.5">
                                    {([['last_n', 'Ultime N'], ['season', 'Stagioni'], ['all', 'Tutto lo storico']] as const).map(([v, l]) => (
                                        <button key={v} onClick={() => setMode(v)} className={chipCls(mode === v)}>{l}</button>
                                    ))}
                                </div>
                            </div>
                            {mode === 'last_n' && (
                                <div className="flex-1">
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">N partite</div>
                                    <div className="flex flex-wrap items-center gap-1.5">
                                        {N_PRESETS.map(n => (
                                            <button key={n} onClick={() => { setLastN(n); setCustomN(''); }} className={chipCls(lastN === n)}>{n}</button>
                                        ))}
                                        <input
                                            value={customN}
                                            onChange={e => setCustomN(e.target.value.replace(/[^0-9]/g, ''))}
                                            placeholder="custom"
                                            inputMode="numeric"
                                            className="w-20 px-2 py-1.5 rounded-lg text-xs font-bold bg-white/5 border border-white/10 text-white placeholder:text-white/30 focus:outline-none focus:border-primary/50"
                                        />
                                    </div>
                                </div>
                            )}
                            {mode === 'season' && (
                                <div className="flex-1 flex flex-col md:flex-row gap-4">
                                    <div>
                                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Stagione</div>
                                        <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto pr-1">
                                            {seasons.map(s => (
                                                <button key={s.season_year} onClick={() => { setSeasonA(s.season_year); if (seasonB === s.season_year) setSeasonB(null); }} className={chipCls(seasonA === s.season_year)}>
                                                    {formatSeason(s.season_year)} <span className="opacity-50">({s.n_settled})</span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Confronta con (opzionale)</div>
                                        <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto pr-1">
                                            <button onClick={() => setSeasonB(null)} className={chipCls(seasonB === null)}>Nessuna</button>
                                            {seasons.filter(s => s.season_year !== seasonA).map(s => (
                                                <button key={s.season_year} onClick={() => setSeasonB(s.season_year)} className={chipCls(seasonB === s.season_year)}>
                                                    {formatSeason(s.season_year)}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* ---- Medie mobili e bande ---- */}
                        <div className="flex flex-wrap items-end gap-6">
                            <div>
                                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Medie mobili</div>
                                <div className="flex gap-1.5">
                                    {(['mm5', 'mm10', 'mm15'] as const).map(k => (
                                        <button
                                            key={k}
                                            onClick={() => setShowMM(prev => ({ ...prev, [k]: !prev[k] }))}
                                            className={chipCls(showMM[k])}
                                            style={showMM[k] ? { color: MM_COLORS[k], borderColor: MM_COLORS[k] + '66', background: MM_COLORS[k] + '22' } : undefined}
                                        >
                                            {k.toUpperCase()}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            {!isCompare && (
                                <div>
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-bold">Bande</div>
                                    <div className="flex gap-1.5">
                                        <button onClick={() => setShowBand1(v => !v)} className={chipCls(showBand1)}>±1σ</button>
                                        <button onClick={() => setShowBand2(v => !v)} className={chipCls(showBand2)}>±2σ</button>
                                    </div>
                                </div>
                            )}
                            {isCompare && (
                                <div className="text-[11px] text-muted-foreground">
                                    Confronto stagioni: viene tracciata la <span className="font-bold" style={{ color: MM_COLORS[compareMM] }}>{compareMM.toUpperCase()}</span> di entrambe le serie.
                                </div>
                            )}
                        </div>

                        {/* ---- Meta bar: denominatore reale SEMPRE esposto ---- */}
                        {metaA && !loading && !htHardBlocked && (
                            <div className="glass-card rounded-xl border border-white/10 px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
                                <div className="text-sm font-bold text-white">{marketTitle}</div>
                                <div className="text-xs text-muted-foreground">
                                    Baseline <span className="text-primary font-mono font-bold">{pct(baseline)}</span>
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    Serie su <span className="text-white font-mono font-bold">{metaA.n_effective}</span> esiti validi
                                    {metaA.n_scope !== metaA.n_effective && <> di <span className="font-mono">{metaA.n_scope}</span> partite{marketId === 'dnb' && <> ({metaA.n_scope - metaA.n_effective} void)</>}</>}
                                    {capped && <span className="text-amber-400 font-bold"> · richieste {metaA.n_requested}, disponibili {metaA.n_scope}</span>}
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    σ <span className="font-mono">{metaA.std?.toFixed(3) ?? '—'}</span>
                                    {' · '}se(MM10) <span className="font-mono">{seMM10?.toFixed(3) ?? '—'}</span>
                                </div>
                                {metaA.date_from && metaA.date_to && (
                                    <div className="text-[11px] text-muted-foreground/70">
                                        {new Date(metaA.date_from).toLocaleDateString('it-IT')} → {new Date(metaA.date_to).toLocaleDateString('it-IT')}
                                    </div>
                                )}
                                {isHt && htCov !== null && (
                                    <span className={`text-[10px] font-bold px-2 py-1 rounded-md ${htWarn ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30' : 'bg-emerald-500/10 text-emerald-400'}`}>
                                        {htWarn && <AlertTriangle className="w-3 h-3 inline mr-1 -mt-0.5" />}
                                        copertura HT {htCov.toFixed(1)}%
                                    </span>
                                )}
                                {isCompare && seriesB && (
                                    <div className="text-xs text-muted-foreground">
                                        vs <span style={{ color: SEASON_B_COLOR }} className="font-bold">{formatSeason(seriesB.meta.season_year!)}</span>:
                                        baseline <span className="font-mono" style={{ color: SEASON_B_COLOR }}>{pct(seriesB.meta.baseline)}</span>
                                        {' · '}<span className="font-mono">{seriesB.meta.n_effective}</span> esiti
                                    </div>
                                )}
                            </div>
                        )}

                        {/* ---- Stati ---- */}
                        {loading && (
                            <div className="flex items-center justify-center py-24">
                                <Loader2 className="w-10 h-10 text-primary animate-spin" />
                            </div>
                        )}
                        {error && !loading && (
                            <div className="glass-card rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-6 text-center">
                                <p className="text-red-400 font-bold text-sm">Errore: {error}</p>
                            </div>
                        )}
                        {htHardBlocked && !loading && !error && (
                            <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                <Ban className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                                <p className="text-amber-400 font-bold">Mercato HT disabilitato per questa lega</p>
                                <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto">
                                    Il punteggio del primo tempo è disponibile solo sul {htCov?.toFixed(1)}% delle partite dell'intervallo
                                    (soglia minima {HT_HARD_THRESHOLD}%): una frequenza calcolata su un campione così parziale sarebbe fuorviante.
                                </p>
                                <p className="text-[11px] text-muted-foreground/70 mt-1">Esiti disponibili: {metaA?.n_effective ?? 0} su {metaA?.n_scope ?? 0} partite.</p>
                            </div>
                        )}
                        {!loading && !error && !htHardBlocked && metaA && metaA.n_effective === 0 && (
                            <div className="glass-card rounded-xl border border-white/10 px-4 py-8 text-center">
                                <p className="text-muted-foreground text-sm">Nessun esito disponibile per questo intervallo.</p>
                            </div>
                        )}

                        {/* ---- Grafico ---- */}
                        {!loading && !error && !htHardBlocked && seriesA && metaA && metaA.n_effective > 0 && (
                            <div className="glass-card rounded-xl border border-white/10 p-3 md:p-5">
                                {tooShort && (
                                    <div className="text-[11px] text-amber-400 font-bold mb-2">
                                        <AlertTriangle className="w-3 h-3 inline mr-1 -mt-0.5" />
                                        Serie molto corta ({metaA.n_effective} esiti): MM15 non disponibile e affidabilità ridotta.
                                    </div>
                                )}
                                <div className="h-[380px] md:h-[460px]">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={chartData} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                                            <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                                            <XAxis
                                                dataKey="idx"
                                                tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                                                tickFormatter={(i: number) => {
                                                    const row = chartData[i - 1] as any;
                                                    const d = row?.p?.date ?? row?.a?.date;
                                                    return d ? new Date(d).toLocaleDateString('it-IT', { month: '2-digit', year: '2-digit' }) : String(i);
                                                }}
                                                minTickGap={48}
                                                axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                                                tickLine={false}
                                            />
                                            <YAxis
                                                domain={yDomain}
                                                tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                                                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                                                axisLine={false}
                                                tickLine={false}
                                            />
                                            <Tooltip content={<FreqTooltip compare={isCompare} />} />

                                            {/* bande ±kσ(MM10) attorno alla baseline */}
                                            {!isCompare && baseline !== null && seMM10 !== null && showBand2 && (
                                                <ReferenceArea y1={Math.max(0, baseline - 2 * seMM10)} y2={Math.min(1, baseline + 2 * seMM10)} fill="hsl(155 84% 42%)" fillOpacity={0.05} />
                                            )}
                                            {!isCompare && baseline !== null && seMM10 !== null && showBand1 && (
                                                <ReferenceArea y1={Math.max(0, baseline - seMM10)} y2={Math.min(1, baseline + seMM10)} fill="hsl(155 84% 42%)" fillOpacity={0.08} />
                                            )}

                                            {/* baseline */}
                                            {!isCompare && baseline !== null && (
                                                <ReferenceLine y={baseline} stroke="hsl(155 84% 42%)" strokeDasharray="6 4" strokeWidth={1.5}
                                                    label={{ value: `baseline ${pct(baseline)}`, position: 'insideTopRight', fill: 'hsl(155 84% 42%)', fontSize: 10, fontWeight: 700 }} />
                                            )}
                                            {isCompare && seriesA.meta.baseline !== null && (
                                                <ReferenceLine y={seriesA.meta.baseline} stroke={MM_COLORS.mm10} strokeDasharray="6 4" strokeWidth={1.2} />
                                            )}
                                            {isCompare && seriesB !== null && seriesB.meta.baseline !== null && (
                                                <ReferenceLine y={seriesB.meta.baseline} stroke={SEASON_B_COLOR} strokeDasharray="6 4" strokeWidth={1.2} />
                                            )}

                                            {/* medie mobili */}
                                            {!isCompare && (['mm5', 'mm10', 'mm15'] as const).filter(k => showMM[k]).map(k => (
                                                <Line key={k} type="monotone" dataKey={k} stroke={MM_COLORS[k]}
                                                    strokeWidth={k === 'mm10' ? 2.2 : 1.4} dot={false} connectNulls={false}
                                                    isAnimationActive={chartData.length <= 600} />
                                            ))}
                                            {isCompare && (
                                                <>
                                                    <Line type="monotone" dataKey="aVal" name={`A ${compareMM}`} stroke={MM_COLORS.mm10} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={chartData.length <= 600} />
                                                    <Line type="monotone" dataKey="bVal" name={`B ${compareMM}`} stroke={SEASON_B_COLOR} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={chartData.length <= 600} />
                                                </>
                                            )}
                                        </LineChart>
                                    </ResponsiveContainer>
                                </div>
                                <div className="mt-2 text-[10px] text-muted-foreground/70 text-center">
                                    Asse X: partite della lega in ordine cronologico di kickoff (tiebreaker deterministico fixture_id).
                                    MM tracciate solo a finestra piena. z-score = (MM10 − baseline) / se(MM10).
                                </div>
                            </div>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
