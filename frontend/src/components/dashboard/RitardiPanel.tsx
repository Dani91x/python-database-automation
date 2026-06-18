// ============================================================================
// Pannello STUDIO RITARDI — riproduzione 1:1 del file Excel
// "STUDIO RITARDI_BASE_v5.0", per-lega e automatica (DATI MATCH = tutto lo
// storico della competizione). Ogni mercato = un "foglio" con gli STESSI
// blocchi ed etichette del file, vestiti col layout della dashboard.
// Tutta la matematica e' server-side (RPC get_market_delays, certificata
// identica alle formule del foglio): qui solo rendering.
// MarketFrequencyPanel.tsx / PoissonPanel.tsx NON sono toccati.
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import {
    LineChart, Line, XAxis, YAxis, ReferenceLine,
    ResponsiveContainer, Tooltip, CartesianGrid,
} from 'recharts';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Loader2, Hourglass, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import {
    DELAY_MARKETS, DelayMarketDef, DelayResult, LeagueSeason,
    fetchMarketDelays, fetchLeagueSeasons, formatSeason, targetLabel,
} from '@/lib/marketDelays';

// ---------------------------------------------------------------- helpers UI
const N_PRESETS = [100, 200, 300, 500, 1000];

const num = (v: number | null | undefined, d = 2) =>
    v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(d);
const pct = (v: number | null | undefined, d = 1) =>
    v === null || v === undefined || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`;
const int = (v: number | null | undefined) =>
    v === null || v === undefined ? '—' : String(v);

const chipCls = (active: boolean) =>
    `px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${active
        ? 'bg-primary/20 text-primary border-primary/40'
        : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10 hover:text-white'}`;

// Card etichetta/valore in stile dashboard (riproduce le celle B/C del foglio)
function StatCard({ label, value, sub, accent }: {
    label: string; value: React.ReactNode; sub?: React.ReactNode; accent?: string;
}) {
    return (
        <div className="glass-card rounded-xl border border-white/10 px-4 py-3 min-w-[140px] flex-1">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">{label}</div>
            <div className="mt-1 text-2xl font-black font-mono leading-none" style={accent ? { color: accent } : undefined}>{value}</div>
            {sub && <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>}
        </div>
    );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
    return <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mb-2">{children}</div>;
}

// ---------------------------------------------------------------- tooltip grafico RIT
function RitTooltip({ active, payload }: any) {
    if (!active || !payload?.length) return null;
    const r = payload[0]?.payload;
    if (!r) return null;
    return (
        <div className="rounded-lg border border-white/10 bg-black/90 backdrop-blur-xl px-3 py-2 shadow-2xl max-w-[240px]">
            <div className="text-[10px] text-muted-foreground font-mono">EVENTO #{r.idx}</div>
            <div className="text-xs text-white font-bold">{r.home} – {r.away}</div>
            <div className="text-[11px] text-muted-foreground">
                {r.gc}-{r.ga}
                {r.gcfh !== null && r.gafh !== null && <span> (PT {r.gcfh}-{r.gafh})</span>}
                {' · '}
                <span className={r.out === 1 ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>
                    {r.out === 1 ? '✓ uscito' : '✗ ritardo'}
                </span>
            </div>
            <div className="text-[11px] font-mono mt-0.5">
                <span className="text-primary">RIT {r.rit}</span>
                {r.suc !== null && r.suc !== undefined && <span className="ml-2 text-amber-400">SUC {r.suc}</span>}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------- pannello
interface Props {
    leagueId: number;
    leagueName: string;
}

export function RitardiPanel({ leagueId, leagueName }: Props) {
    const [open, setOpen] = useState(false);

    const [marketId, setMarketId] = useState<string>('sge');
    const market: DelayMarketDef = useMemo(() => DELAY_MARKETS.find(m => m.id === marketId) ?? DELAY_MARKETS[0], [marketId]);
    const [target, setTarget] = useState<string | null>(market.defaultTarget ?? null);

    const [mode, setMode] = useState<'all' | 'last_n' | 'season'>('all');
    const [lastN, setLastN] = useState<number>(500);
    const [seasonYear, setSeasonYear] = useState<number | null>(null);

    const [seasons, setSeasons] = useState<LeagueSeason[]>([]);
    const [data, setData] = useState<DelayResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showDati, setShowDati] = useState(false);
    const DATI_PAGE = 500;
    const [datiLimit, setDatiLimit] = useState(DATI_PAGE);
    const reqRef = useRef(0);

    // cambio lega: azzera i dati per non mostrare lo storico della lega precedente
    useEffect(() => { setData(null); setDatiLimit(DATI_PAGE); }, [leagueId]);

    // cambio mercato -> target di default coerente
    const handleMarket = (m: DelayMarketDef) => {
        setMarketId(m.id);
        setTarget(m.targetKind === 'none' ? null : (m.defaultTarget ?? m.targets?.[0] ?? null));
    };

    // stagioni disponibili (primo open / cambio lega)
    useEffect(() => {
        if (!open) return;
        let stale = false;
        fetchLeagueSeasons(leagueId)
            .then(s => { if (!stale) { setSeasons(s); if (s.length && seasonYear === null) setSeasonYear(s[0].season_year); } })
            .catch(() => { if (!stale) setSeasons([]); });
        return () => { stale = true; };
    }, [open, leagueId]);

    // fetch dati ritardi
    useEffect(() => {
        if (!open) return;
        if (mode === 'season' && seasonYear === null) return;
        const req = ++reqRef.current;
        setLoading(true); setError(null);
        fetchMarketDelays({ leagueId, market: marketId, target, mode, lastN, seasonYear })
            .then(d => { if (req === reqRef.current) { setData(d); setDatiLimit(DATI_PAGE); } })
            .catch(e => { if (req === reqRef.current) { setError(e.message || 'Errore di caricamento'); setData(null); } })
            .finally(() => { if (req === reqRef.current) setLoading(false); });
    }, [open, leagueId, marketId, target, mode, lastN, seasonYear]);

    const st = data?.stats;
    const meta = data?.meta;
    // segnale "intercetta ritardo": ritardo attuale vs media storica
    const ritVs = st?.rit_vs_media ?? null;
    const ritAccent = ritVs == null ? undefined
        : ritVs >= 1.5 ? '#f87171' : ritVs >= 1 ? '#fbbf24' : 'hsl(155 84% 42%)';

    const chartData = useMemo(() => data?.series ?? [], [data]);

    return (
        <>
            <div className="mb-8 flex justify-center">
                <Button
                    onClick={() => setOpen(true)}
                    variant="outline"
                    className="glass-card border-white/10 hover:border-primary/40 text-white font-bold h-12 px-6 rounded-xl gap-2 hover:bg-white/5"
                >
                    <Hourglass className="w-5 h-5 text-primary" />
                    Studio Ritardi
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden sm:inline">— per-lega</span>
                </Button>
            </div>

            <Sheet open={open} onOpenChange={setOpen}>
                <SheetContent side="bottom" className="h-[94vh] overflow-y-auto bg-black/95 border-t border-white/10 backdrop-blur-2xl p-4 md:p-6">
                    <SheetHeader className="text-left mb-4">
                        <SheetTitle className="font-display font-black text-xl text-white">
                            Studio Ritardi <span className="text-primary">·</span> {leagueName}
                        </SheetTitle>
                        <SheetDescription className="text-xs text-muted-foreground">
                            Riproduzione 1:1 del file STUDIO RITARDI. DATI MATCH = tutto lo storico della lega.
                            Ogni mercato è un foglio: ritardo attuale vs media storica del mercato scelto.
                        </SheetDescription>
                    </SheetHeader>

                    <div className="max-w-5xl mx-auto space-y-4">
                        {/* selettore mercato (= foglio) */}
                        <div>
                            <SectionTitle>Mercato (foglio)</SectionTitle>
                            <div className="flex flex-wrap gap-2">
                                {DELAY_MARKETS.map(m => (
                                    <button key={m.id} onClick={() => handleMarket(m)} className={chipCls(m.id === marketId)}>{m.label}</button>
                                ))}
                            </div>
                        </div>

                        {/* selettore target (cella di input C8 del foglio) */}
                        {market.targetKind !== 'none' && (
                            <div>
                                <SectionTitle>
                                    {market.targetKind === 'score' ? 'Risultato' : market.targetKind === 'int' ? 'Somma gol' : 'Linea'}
                                </SectionTitle>
                                <div className="flex flex-wrap gap-2">
                                    {market.targets?.map(t => (
                                        <button key={t} onClick={() => setTarget(t)} className={chipCls(t === target)}>{t}</button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* intervallo DATI MATCH */}
                        <div>
                            <SectionTitle>Storico (DATI MATCH)</SectionTitle>
                            <div className="flex flex-wrap items-center gap-2">
                                <button onClick={() => setMode('all')} className={chipCls(mode === 'all')}>Tutto lo storico</button>
                                <button onClick={() => setMode('season')} className={chipCls(mode === 'season')}>Stagione</button>
                                <button onClick={() => setMode('last_n')} className={chipCls(mode === 'last_n')}>Ultime N</button>
                                {mode === 'season' && seasons.length > 0 && (
                                    <select
                                        value={seasonYear ?? ''}
                                        onChange={e => setSeasonYear(Number(e.target.value))}
                                        className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white font-bold"
                                    >
                                        {seasons.map(s => (
                                            <option key={s.season_year} value={s.season_year} className="bg-black">
                                                {formatSeason(s.season_year)} · {s.n_settled} gare
                                            </option>
                                        ))}
                                    </select>
                                )}
                                {mode === 'last_n' && N_PRESETS.map(n => (
                                    <button key={n} onClick={() => setLastN(n)} className={chipCls(lastN === n)}>{n}</button>
                                ))}
                            </div>
                        </div>

                        {/* stati */}
                        {loading && <div className="flex items-center justify-center py-20"><Loader2 className="w-10 h-10 text-primary animate-spin" /></div>}
                        {error && !loading && (
                            <div className="glass-card rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-6 text-center">
                                <p className="text-red-400 font-bold text-sm">Errore: {error}</p>
                            </div>
                        )}
                        {!loading && !error && data && meta && st && (
                            <>
                                {/* meta bar */}
                                <div className="glass-card rounded-xl border border-white/10 px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                                    <span className="text-sm font-bold text-white">{targetLabel(market, target)}</span>
                                    <span>eventi (DATI MATCH) <span className="text-white font-mono font-bold">{int(meta.n_effective)}</span></span>
                                    <span>occorrenze <span className="text-white font-mono font-bold">{int(st.n_occ)}</span></span>
                                    {meta.date_from && <span className="text-[11px]">{meta.date_from} → {meta.date_to}</span>}
                                    {meta.uses_ht && (
                                        <span className={meta.ht_coverage_pct != null && meta.ht_coverage_pct < 90 ? 'text-amber-400 font-bold' : ''}>
                                            copertura PT <span className="font-mono">{num(meta.ht_coverage_pct, 1)}%</span>
                                        </span>
                                    )}
                                </div>

                                {/* avviso copertura PT bassa: i mercati di primo tempo trattano
                                    le righe senza HT come 0-0 (fedele al foglio) -> possibile distorsione */}
                                {meta.uses_ht && meta.ht_coverage_pct != null && meta.ht_coverage_pct < 90 && (
                                    <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 flex items-start gap-3">
                                        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                                        <p className="text-xs text-amber-300/90">
                                            Copertura primo tempo {num(meta.ht_coverage_pct, 1)}%: come nel foglio, le gare senza
                                            dato di primo tempo sono trattate come 0-0. Su questo mercato le statistiche possono
                                            risultare distorte. Per dati puliti usa il box Frequenze Mercati (che esclude quelle gare).
                                        </p>
                                    </div>
                                )}

                                {st.n_occ === 0 ? (
                                    <div className="glass-card rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-8 text-center">
                                        <AlertTriangle className="w-9 h-9 text-amber-400 mx-auto mb-3" />
                                        <p className="text-amber-400 font-bold">Mai verificato in questo storico</p>
                                        <p className="text-xs text-muted-foreground mt-2">
                                            Ritardo attuale {int(st.ritardo_attuale)} su {int(meta.n_effective)} eventi. Nessuna serie chiusa.
                                        </p>
                                    </div>
                                ) : (
                                    <>
                                        {/* PANNELLO PRINCIPALE (celle B/C del foglio) */}
                                        <div className="flex flex-wrap gap-3">
                                            <StatCard label="Quota Oggettiva" value={num(st.quota_oggettiva, 2)} sub="= media storica" />
                                            <StatCard label="Media Storica" value={`ogni ${num(st.media_storica, 1)}`} sub="partite si verifica" />
                                            <StatCard label="Ritardo Attuale" value={int(st.ritardo_attuale)} accent={ritAccent}
                                                sub={ritVs != null ? `${num(ritVs, 2)}× la media` : undefined} />
                                            <StatCard label="Record" value={int(st.record)} sub="serie storica max" />
                                            <StatCard label="% Mercato" value={pct(st.frequency, 1)} />
                                            <StatCard label="Media Rit." value={num(st.media_ritardi, 2)} sub="AVERAGEIF(RIT;≠0)" />
                                        </div>

                                        {/* GRAFICO RIT NEL TEMPO */}
                                        <div className="glass-card rounded-xl border border-white/10 p-3 md:p-4">
                                            <SectionTitle>Ritardo nel tempo (RIT)</SectionTitle>
                                            <div className="h-56">
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <LineChart data={chartData} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                                                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                                        <XAxis dataKey="idx" tick={{ fontSize: 10, fill: '#9ca3af' }} stroke="rgba(255,255,255,0.1)" />
                                                        <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} stroke="rgba(255,255,255,0.1)" allowDecimals={false} />
                                                        <Tooltip content={<RitTooltip />} />
                                                        {st.media_storica != null && (
                                                            <ReferenceLine y={st.media_storica} stroke="#60a5fa" strokeDasharray="4 4"
                                                                label={{ value: 'media', fill: '#60a5fa', fontSize: 10, position: 'insideTopLeft' }} />
                                                        )}
                                                        {st.record > 0 && (
                                                            <ReferenceLine y={st.record} stroke="#f87171" strokeDasharray="2 2"
                                                                label={{ value: 'record', fill: '#f87171', fontSize: 10, position: 'insideTopLeft' }} />
                                                        )}
                                                        <Line type="stepAfter" dataKey="rit" stroke="hsl(155 84% 42%)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                                                    </LineChart>
                                                </ResponsiveContainer>
                                            </div>
                                        </div>

                                        {/* DISTRIBUZIONE SERIE + ULTIME 10 + < / > MEDIA */}
                                        <div className="grid md:grid-cols-2 gap-3">
                                            {/* DISTRIBUZIONE SERIE (F/G/H) */}
                                            <div className="glass-card rounded-xl border border-white/10 p-3 md:p-4">
                                                <SectionTitle>Distribuzione serie (F/G/H)</SectionTitle>
                                                <div className="max-h-56 overflow-y-auto">
                                                    <table className="w-full text-xs font-mono">
                                                        <thead className="text-muted-foreground text-[10px] uppercase">
                                                            <tr><th className="text-left py-1">Valore</th><th className="text-right">Occ. (SUC)</th><th className="text-right">Cnt (RIT)</th></tr>
                                                        </thead>
                                                        <tbody>
                                                            {data.distribuzione_serie.map(d => (
                                                                <tr key={d.len} className="border-t border-white/5">
                                                                    <td className="py-1 text-white/80">{d.len}</td>
                                                                    <td className="text-right text-white">{d.occ_suc}</td>
                                                                    <td className="text-right text-white/60">{d.cnt_rit}</td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>

                                            {/* STORICO SERIE (% sulla serie) */}
                                            <div className="glass-card rounded-xl border border-white/10 p-3 md:p-4">
                                                <SectionTitle>Storico serie (% sulla serie)</SectionTitle>
                                                <div className="max-h-56 overflow-y-auto">
                                                    <table className="w-full text-xs font-mono">
                                                        <thead className="text-muted-foreground text-[10px] uppercase">
                                                            <tr><th className="text-left py-1">Lung.</th><th className="text-right">Tot</th><th className="text-right">%</th></tr>
                                                        </thead>
                                                        <tbody>
                                                            {data.storico_serie.map(s => (
                                                                <tr key={s.len} className="border-t border-white/5">
                                                                    <td className="py-1 text-white/80">{s.len}</td>
                                                                    <td className="text-right text-white">{s.count}</td>
                                                                    <td className="text-right text-primary">{pct(s.pct, 1)}</td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        </div>

                                        {/* ULTIME 10 SERIE + < / > MEDIA + RUN SOPRA MEDIA */}
                                        <div className="grid md:grid-cols-3 gap-3">
                                            <div className="glass-card rounded-xl border border-white/10 p-3 md:p-4">
                                                <SectionTitle>Ultime 10 serie</SectionTitle>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {data.ultime_10_serie.length === 0 && <span className="text-xs text-muted-foreground">—</span>}
                                                    {data.ultime_10_serie.map((v, i) => (
                                                        <span key={`l10-${i}`} className="px-2 py-1 rounded-md bg-white/5 border border-white/10 text-xs font-mono text-white">{v}</span>
                                                    ))}
                                                </div>
                                            </div>

                                            <div className="glass-card rounded-xl border border-white/10 p-3 md:p-4">
                                                <SectionTitle>Sotto / Sopra media rit.</SectionTitle>
                                                <div className="flex gap-2">
                                                    <div className="flex-1 rounded-lg bg-emerald-500/5 border border-emerald-500/20 px-3 py-2">
                                                        <div className="text-[10px] text-muted-foreground">≤ media</div>
                                                        <div className="text-lg font-black font-mono text-emerald-400">{st.sotto_media}</div>
                                                        <div className="text-[10px] text-muted-foreground">{pct(st.sotto_media_pct, 1)}</div>
                                                    </div>
                                                    <div className="flex-1 rounded-lg bg-red-500/5 border border-red-500/20 px-3 py-2">
                                                        <div className="text-[10px] text-muted-foreground">&gt; media</div>
                                                        <div className="text-lg font-black font-mono text-red-400">{st.sopra_media}</div>
                                                        <div className="text-[10px] text-muted-foreground">{pct(st.sopra_media_pct, 1)}</div>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="glass-card rounded-xl border border-white/10 p-3 md:p-4">
                                                <SectionTitle>&gt; Media ritardi (run)</SectionTitle>
                                                <div className="max-h-40 overflow-y-auto">
                                                    <table className="w-full text-xs font-mono">
                                                        <thead className="text-muted-foreground text-[10px] uppercase">
                                                            <tr><th className="text-left py-1">Run</th><th className="text-right">N</th><th className="text-right">%</th></tr>
                                                        </thead>
                                                        <tbody>
                                                            {data.run_sopra_media.length === 0 && (
                                                                <tr><td className="py-1 text-muted-foreground" colSpan={3}>—</td></tr>
                                                            )}
                                                            {data.run_sopra_media.map(r => (
                                                                <tr key={r.run_len} className="border-t border-white/5">
                                                                    <td className="py-1 text-white/80">{r.run_len}</td>
                                                                    <td className="text-right text-white">{r.count}</td>
                                                                    <td className="text-right text-primary">{pct(r.pct, 1)}</td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        </div>

                                        {/* DATI MATCH grezzo (per confronto cella-per-cella col foglio) */}
                                        <div className="glass-card rounded-xl border border-white/10 p-3 md:p-4">
                                            <button onClick={() => setShowDati(v => !v)} className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground font-bold hover:text-white">
                                                {showDati ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                                                DATI MATCH — {data.series.length} eventi (colonne del foglio + W/L · RIT · SUC)
                                            </button>
                                            {showDati && (
                                                <div className="mt-3 max-h-[60vh] overflow-auto">
                                                    <table className="w-full text-[11px] font-mono whitespace-nowrap">
                                                        <thead className="text-muted-foreground text-[10px] uppercase sticky top-0 bg-black/95">
                                                            <tr className="border-b border-white/10">
                                                                <th className="text-left px-2 py-1">EVENTO</th>
                                                                <th className="text-left px-2">HOME</th>
                                                                <th className="text-left px-2">AWAY</th>
                                                                <th className="text-right px-2">GC</th>
                                                                <th className="text-right px-2">GA</th>
                                                                <th className="text-right px-2">GCFH</th>
                                                                <th className="text-right px-2">GAFH</th>
                                                                <th className="text-right px-2">GCSH</th>
                                                                <th className="text-right px-2">GASH</th>
                                                                <th className="text-right px-2">W/L</th>
                                                                <th className="text-right px-2">RIT</th>
                                                                <th className="text-right px-2">SUC</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {data.series.slice(0, datiLimit).map(r => (
                                                                <tr key={r.idx} className={`border-b border-white/5 ${r.out === 1 ? 'bg-emerald-500/5' : ''}`}>
                                                                    <td className="px-2 py-0.5 text-muted-foreground">{r.idx}</td>
                                                                    <td className="px-2 text-white/80">{r.home}</td>
                                                                    <td className="px-2 text-white/80">{r.away}</td>
                                                                    <td className="px-2 text-right text-white">{r.gc}</td>
                                                                    <td className="px-2 text-right text-white">{r.ga}</td>
                                                                    <td className="px-2 text-right text-white/70">{int(r.gcfh)}</td>
                                                                    <td className="px-2 text-right text-white/70">{int(r.gafh)}</td>
                                                                    <td className="px-2 text-right text-white/70">{r.gcsh}</td>
                                                                    <td className="px-2 text-right text-white/70">{r.gash}</td>
                                                                    <td className={`px-2 text-right font-bold ${r.out === 1 ? 'text-emerald-400' : 'text-white/40'}`}>{r.out}</td>
                                                                    <td className="px-2 text-right text-primary">{r.rit}</td>
                                                                    <td className="px-2 text-right text-amber-400">{r.suc ?? ''}</td>
                                                                </tr>
                                                            ))}
                                                            {datiLimit < data.series.length && (
                                                                <tr>
                                                                    <td colSpan={12} className="px-2 py-2 text-center">
                                                                        <button
                                                                            onClick={() => setDatiLimit(l => l + DATI_PAGE)}
                                                                            className="text-[11px] font-bold text-primary hover:underline"
                                                                        >
                                                                            Carica altri {Math.min(DATI_PAGE, data.series.length - datiLimit)} (mostrati {datiLimit} / {data.series.length})
                                                                        </button>
                                                                    </td>
                                                                </tr>
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            )}
                                        </div>
                                    </>
                                )}
                            </>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </>
    );
}
