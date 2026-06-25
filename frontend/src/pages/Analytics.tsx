// ============================================================================
// /analytics — Centro di controllo: pagella per-motore per-mercato.
// Legge SOLO via RPC aggregati (nessun dato sensibile). Hit-rate + Wilson 95%.
// Drill-down (partite reali), export CSV, ordinamento, filtri avanzati
// (motore/mercato/selezione/lega/stagione/confidenza/concordanza/piazzati/
// ritardo/frequenza/timing). Stesso design system della dashboard.
// ============================================================================
import { Fragment, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, ChevronLeft, Filter, RotateCcw, AlertTriangle, Download, ChevronDown, ChevronUp, ArrowUpDown } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import DecisionsTab from '@/components/dashboard/DecisionsTab';
import CreateStrategy from '@/components/dashboard/CreateStrategy';
import ReportisticheTab from '@/components/dashboard/ReportisticheTab';
import {
    fetchAnalytics, fetchAnalyticsFilters, fetchAnalyticsRows, groupsToCsv, downloadCsv,
    ENGINE_LABEL, MARKET_LABEL, GROUP_BY_OPTIONS, pct,
    type AnalyticsFilters, type AnalyticsResult, type AnalyticsGroup, type AnalyticsQuery, type AnalyticsRow,
} from '@/lib/analytics';

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors';
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const clamp01 = (v: number) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

const SELECTIONS_BY_MARKET: Record<string, string[]> = {
    '1x2': ['H', 'D', 'A'], ht_1x2: ['H', 'D', 'A'],
    over_0_5: ['Over', 'Under'], over_1_5: ['Over', 'Under'], over_2_5: ['Over', 'Under'],
    over_3_5: ['Over', 'Under'], over_4_5: ['Over', 'Under'],
    first_half_over_0_5: ['Over', 'Under'], first_half_over_1_5: ['Over', 'Under'],
    first_half_over_2_5: ['Over', 'Under'], first_half_over_3_5: ['Over', 'Under'],
    home_over_0_5: ['Over', 'Under'], home_over_1_5: ['Over', 'Under'], home_over_2_5: ['Over', 'Under'],
    away_over_0_5: ['Over', 'Under'], away_over_1_5: ['Over', 'Under'], away_over_2_5: ['Over', 'Under'],
    btts: ['Yes', 'No'], first_half_btts: ['Yes', 'No'],
    double_chance: ['1X', 'X2', '12'], first_half_double_chance: ['1X', 'X2', '12'],
    clean_sheet_home: ['Yes', 'No'], clean_sheet_away: ['Yes', 'No'],
};

type SortKey = 'grp' | 'n' | 'hit_rate' | 'calib_gap';

// Grafico di calibrazione: ogni gruppo è un punto (prob media detta vs hit-rate
// reale). La diagonale = calibrazione perfetta. Sopra = sottostima, sotto =
// sovrastima. Raggio del punto ∝ √N (più dati = più affidabile).
function CalibrationChart({ groups }: { groups: AnalyticsGroup[] }) {
    const W = 320, H = 320, P = 34;
    const sx = (v: number) => P + clamp01(v) * (W - 2 * P);
    const sy = (v: number) => H - P - clamp01(v) * (H - 2 * P);
    const maxN = Math.max(1, ...groups.map(g => g.n));
    const ticks = [0, 0.25, 0.5, 0.75, 1];
    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[340px] mx-auto">
            {ticks.map(t => (
                <g key={t}>
                    <line x1={sx(t)} y1={sy(0)} x2={sx(t)} y2={sy(1)} stroke="white" strokeOpacity={0.05} />
                    <line x1={sx(0)} y1={sy(t)} x2={sx(1)} y2={sy(t)} stroke="white" strokeOpacity={0.05} />
                    <text x={sx(t)} y={H - P + 14} fill="currentColor" className="text-muted-foreground" fontSize={8} textAnchor="middle">{Math.round(t * 100)}</text>
                    <text x={P - 6} y={sy(t) + 3} fill="currentColor" className="text-muted-foreground" fontSize={8} textAnchor="end">{Math.round(t * 100)}</text>
                </g>
            ))}
            {/* diagonale calibrazione perfetta */}
            <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="hsl(45 90% 55%)" strokeOpacity={0.5} strokeDasharray="4 3" />
            {groups.map(g => {
                const r = 3 + 7 * Math.sqrt(g.n / maxN);
                const over = g.hit_rate >= g.avg_prob; // sottostima (punto sopra diagonale)
                return <circle key={g.grp} cx={sx(g.avg_prob)} cy={sy(g.hit_rate)} r={r}
                    fill={over ? 'hsl(155 84% 42%)' : 'hsl(0 80% 55%)'} fillOpacity={0.55}
                    stroke={over ? 'hsl(155 84% 42%)' : 'hsl(0 80% 55%)'} strokeOpacity={0.9}>
                    <title>{`${g.grp}: detto ${pct(g.avg_prob)} · reale ${pct(g.hit_rate)} · N=${g.n}`}</title>
                </circle>;
            })}
            <text x={W / 2} y={H - 4} fill="currentColor" className="text-muted-foreground" fontSize={8} textAnchor="middle">prob. detta dal motore (%)</text>
            <text x={10} y={H / 2} fill="currentColor" className="text-muted-foreground" fontSize={8} textAnchor="middle" transform={`rotate(-90 10 ${H / 2})`}>hit-rate reale (%)</text>
        </svg>
    );
}

export default function Analytics() {
    const [filters, setFilters] = useState<AnalyticsFilters | null>(null);
    const [result, setResult] = useState<AnalyticsResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [tab, setTab] = useState<'engines' | 'decisions' | 'create' | 'reports'>('engines');
    const [q, setQ] = useState<AnalyticsQuery>({ groupBy: 'confidence' });
    const set = (patch: Partial<AnalyticsQuery>) => setQ(prev => ({ ...prev, ...patch }));
    const reset = () => setQ({ groupBy: 'confidence' });

    const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'n', dir: -1 });
    const toggleSort = (key: SortKey) =>
        setSort(s => (s.key === key ? { key, dir: (s.dir === 1 ? -1 : 1) } : { key, dir: key === 'grp' ? 1 : -1 }));

    // drill-down
    const [drill, setDrill] = useState<string | null>(null);   // grp aperto
    const [drillRows, setDrillRows] = useState<AnalyticsRow[]>([]);
    const [drillLoading, setDrillLoading] = useState(false);

    useEffect(() => {
        fetchAnalyticsFilters().then(setFilters).catch(e => setError(String(e.message || e)));
    }, []);

    useEffect(() => {
        let alive = true;
        setLoading(true); setError(null); setDrill(null);
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

    const sortedGroups = useMemo(() => {
        const gs = [...(result?.groups ?? [])];
        gs.sort((a, b) => {
            const va = a[sort.key] as number | string, vb = b[sort.key] as number | string;
            if (typeof va === 'string') {
                // ordinamento NATURALE: i gruppi con numero iniziale (es. bin "60-65%")
                // ordinano per valore numerico, non lessicale ("100" dopo "5").
                const na = parseFloat(va), nb = parseFloat(String(vb));
                if (!Number.isNaN(na) && !Number.isNaN(nb) && na !== nb) return (na - nb) * sort.dir;
                return va.localeCompare(String(vb)) * sort.dir;
            }
            return ((va as number) - (vb as number)) * sort.dir;
        });
        return gs;
    }, [result, sort]);

    // traduce un gruppo (per la dimensione corrente) in filtri extra per il drill-down
    function drillQuery(g: AnalyticsGroup): AnalyticsQuery {
        const extra: AnalyticsQuery = { ...q };
        const dim = result?.group_by;
        if (dim === 'engine') extra.engine = g.grp;
        else if (dim === 'market') extra.market = g.grp;
        else if (dim === 'selection') {
            const [mk, sel] = g.grp.split(' / ');
            extra.market = mk; extra.selection = sel;
        } else if (dim === 'confidence') {
            // usa il bin esatto (stessa formula dell'aggregato), NON probMin/Max
            // (che includerebbe righe del bin successivo sul bordo).
            const m = g.grp.match(/^(\d+)-\d+%$/);
            if (m) extra.confBin = Number(m[1]);
        } else if (dim === 'league') {
            const lg = (filters?.leagues ?? []).find(l => (l.name ?? `Lega ${l.id}`) === g.grp);
            if (lg) extra.leagueId = lg.id;
        }
        return extra;
    }

    function openDrill(g: AnalyticsGroup) {
        if (drill === g.grp) { setDrill(null); return; }
        setDrill(g.grp); setDrillLoading(true); setDrillRows([]);
        fetchAnalyticsRows(drillQuery(g), 100)
            .then(setDrillRows)
            .catch(e => setError(String(e.message || e)))
            .finally(() => setDrillLoading(false));
    }

    function exportCsv() {
        if (!result) return;
        const csv = groupsToCsv(sortedGroups, result.group_by);
        downloadCsv(`analytics_${result.group_by}_${Date.now()}.csv`, csv);
    }

    const SortHead = ({ k, label, cls }: { k: SortKey; label: string; cls?: string }) => (
        <th className={`px-3 py-2 font-medium cursor-pointer select-none hover:text-white ${cls ?? ''}`} onClick={() => toggleSort(k)}>
            <span className="inline-flex items-center gap-1">
                {label}
                {sort.key === k ? (sort.dir === 1 ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />) : <ArrowUpDown className="w-3 h-3 opacity-30" />}
            </span>
        </th>
    );

    return (
        <div className="min-h-screen bg-black text-white relative">
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">AI <span className="text-primary">TERMINAL</span></Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-secondary font-heading font-bold ml-4">
                            <BarChart3 className="w-4 h-4" /> ANALYTICS
                        </span>
                    </div>
                    <Link to="/dashboard"><Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                        <ChevronLeft className="w-4 h-4 mr-1" /> Dashboard
                    </Button></Link>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10">
                <div className="mb-6">
                    <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">Centro di Controllo <span className="text-primary">Motori</span></h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Pagella per-motore per-mercato sullo storico settlato.
                        {filters && <> {' '}<span className="text-white/70">{filters.total_settled.toLocaleString('it')}</span> segnali settlati.</>}
                    </p>
                </div>

                {/* ---- TAB ---- */}
                <div className="flex gap-2 mb-5">
                    <Button variant={tab === 'engines' ? 'default' : 'outline'} size="sm"
                        onClick={() => setTab('engines')}
                        className={tab === 'engines' ? 'bg-primary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}>
                        Performance Motori
                    </Button>
                    <Button variant={tab === 'decisions' ? 'default' : 'outline'} size="sm"
                        onClick={() => setTab('decisions')}
                        className={tab === 'decisions' ? 'bg-secondary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}>
                        Decisioni
                    </Button>
                    <Button variant={tab === 'create' ? 'default' : 'outline'} size="sm"
                        onClick={() => setTab('create')}
                        className={tab === 'create' ? 'bg-primary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}>
                        Crea Strategia
                    </Button>
                    <Button variant={tab === 'reports' ? 'default' : 'outline'} size="sm"
                        onClick={() => setTab('reports')}
                        className={tab === 'reports' ? 'bg-primary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}>
                        Reportistiche
                    </Button>
                </div>

                {tab === 'decisions' && <DecisionsTab />}
                {tab === 'create' && <CreateStrategy filters={filters} />}
                {tab === 'reports' && <ReportisticheTab />}

                {tab === 'engines' && <>

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
                        <div>
                            <label className={LABEL_CLS}>Motore</label>
                            <select className={SELECT_CLS} value={q.engine ?? ''} onChange={e => set({ engine: e.target.value || null })}>
                                <option value="">Tutti</option>
                                {(filters?.engines ?? []).map(e => <option key={e.value} value={e.value}>{ENGINE_LABEL[e.value] ?? e.value} ({e.n.toLocaleString('it')})</option>)}
                            </select>
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Mercato</label>
                            <select className={SELECT_CLS} value={q.market ?? ''} onChange={e => set({ market: e.target.value || null, selection: null })}>
                                <option value="">Tutti</option>
                                {(filters?.markets ?? []).map(m => <option key={m.value} value={m.value}>{MARKET_LABEL[m.value] ?? m.value}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Selezione</label>
                            <select className={SELECT_CLS} value={q.selection ?? ''} disabled={!q.market} onChange={e => set({ selection: e.target.value || null })}>
                                <option value="">Tutte</option>
                                {selectionOptions.map(s => <option key={s} value={s}>{s}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Lega</label>
                            <select className={SELECT_CLS} value={q.leagueId ?? ''} onChange={e => set({ leagueId: e.target.value ? Number(e.target.value) : null })}>
                                <option value="">Tutte</option>
                                {(filters?.leagues ?? []).map(l => <option key={l.id} value={l.id}>{l.name ?? `Lega ${l.id}`} ({l.n.toLocaleString('it')})</option>)}
                            </select>
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Stagione</label>
                            <select className={SELECT_CLS} value={q.seasonYear ?? ''} onChange={e => set({ seasonYear: e.target.value ? Number(e.target.value) : null })}>
                                <option value="">Tutte</option>
                                {(filters?.seasons ?? []).map(s => <option key={s} value={s}>{s}</option>)}
                            </select>
                        </div>
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
                        <div>
                            <label className={LABEL_CLS}>Concordanza min. motori</label>
                            <select className={SELECT_CLS} value={q.minAgree ?? ''} onChange={e => set({ minAgree: e.target.value ? Number(e.target.value) : null })}>
                                <option value="">Qualsiasi</option>
                                <option value="2">≥ 2 motori</option>
                                <option value="3">≥ 3 motori</option>
                                <option value="4">≥ 4 motori</option>
                            </select>
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Frequenza vs baseline</label>
                            <select className={SELECT_CLS} value={q.freqDev ?? ''} onChange={e => set({ freqDev: e.target.value || null })}>
                                <option value="">Qualsiasi</option>
                                <option value="pos">Sopra (mercato "caldo")</option>
                                <option value="neg">Sotto (mercato "freddo")</option>
                            </select>
                        </div>
                        <div>
                            <label className={LABEL_CLS}>Ritardo mercato ≥</label>
                            <input type="number" min={0} placeholder="qualsiasi" className={SELECT_CLS}
                                value={q.delayMin ?? ''} onChange={e => set({ delayMin: e.target.value === '' ? null : Math.max(0, Number(e.target.value)) })} />
                        </div>
                        <div>
                            <label className={LABEL_CLS} title="ATTENZIONE: il minuto del 1° gol è un ESITO della partita, non noto pre-match. Filtro RETROSPETTIVO / conferma in-play — NON un edge giocabile prima del fischio d'inizio.">
                                1° gol entro min. <span className="text-amber-400" title="Filtro retrospettivo / in-play (esito noto)">⚠ retrosp.</span>
                            </label>
                            <input type="number" min={0} max={130} placeholder="qualsiasi" className={SELECT_CLS}
                                value={q.timingMax ?? ''} onChange={e => set({ timingMax: e.target.value === '' ? null : Math.max(0, Number(e.target.value)) })} />
                        </div>
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

                {!loading && result && result.groups.length > 1 && (
                    <Card className="glass-card border-white/10 p-4 mb-4">
                        <div className="flex items-center justify-between mb-1">
                            <span className="font-heading font-bold text-sm uppercase tracking-wide">Calibrazione</span>
                            <span className="text-[10px] text-muted-foreground hidden md:inline">🟢 sottostima · 🔴 sovrastima · ⟍ perfetta · area ∝ N</span>
                        </div>
                        <CalibrationChart groups={result.groups} />
                    </Card>
                )}

                {loading ? (
                    <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12 w-full bg-white/5" />)}</div>
                ) : result && result.groups.length > 0 ? (
                    <Card className="glass-card border-white/10 overflow-hidden">
                        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between gap-2">
                            <span className="font-heading font-bold text-sm">
                                {result.groups.length} grupp{result.groups.length === 1 ? 'o' : 'i'} · {totalN.toLocaleString('it')} segnali
                            </span>
                            <div className="flex items-center gap-3">
                                <span className="text-[10px] text-muted-foreground uppercase tracking-wider hidden md:inline">CI Wilson 95% · clic = partite</span>
                                <Button variant="outline" size="sm" onClick={exportCsv} className="h-7 border-white/10 text-xs text-muted-foreground hover:text-white">
                                    <Download className="w-3 h-3 mr-1" /> CSV
                                </Button>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                        <SortHead k="grp" label="Gruppo" cls="text-left" />
                                        <SortHead k="n" label="N" cls="text-right" />
                                        <SortHead k="hit_rate" label="Hit-rate" cls="text-right" />
                                        <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Intervallo 95%</th>
                                        <th className="text-right px-3 py-2 font-medium">Prob. media</th>
                                        <SortHead k="calib_gap" label="Scarto calib." cls="text-right" />
                                    </tr>
                                </thead>
                                <tbody>
                                    {sortedGroups.map(g => {
                                        const hr = g.hit_rate;
                                        const hrColor = hr >= 0.6 ? 'text-primary' : hr >= 0.5 ? 'text-secondary' : 'text-red-400';
                                        const gapColor = g.calib_gap > 0.03 ? 'text-primary' : g.calib_gap < -0.03 ? 'text-red-400' : 'text-muted-foreground';
                                        const open = drill === g.grp;
                                        return (
                                            <Fragment key={g.grp}>
                                                <tr className={`border-b border-white/5 cursor-pointer hover:bg-white/[0.04] ${open ? 'bg-white/[0.04]' : ''}`} onClick={() => openDrill(g)}>
                                                    <td className="px-4 py-2.5 font-medium">
                                                        <span className="inline-flex items-center gap-1.5">
                                                            {open ? <ChevronDown className="w-3 h-3 text-primary" /> : <ChevronUp className="w-3 h-3 opacity-30 rotate-180" />}
                                                            {g.grp}
                                                        </span>
                                                    </td>
                                                    <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{g.n.toLocaleString('it')}</td>
                                                    <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${hrColor}`}>{pct(hr)}</td>
                                                    <td className="px-3 py-2.5 hidden md:table-cell">
                                                        <div className="relative h-2 w-40 bg-white/5 rounded-full overflow-hidden">
                                                            <div className="absolute h-full bg-primary/30" style={{ left: `${clamp01(g.wilson_low) * 100}%`, width: `${Math.max(0, (clamp01(g.wilson_high) - clamp01(g.wilson_low)) * 100)}%` }} />
                                                            <div className="absolute h-full w-0.5 bg-primary" style={{ left: `${clamp01(hr) * 100}%` }} />
                                                        </div>
                                                        <span className="text-[10px] text-muted-foreground tabular-nums">{pct(g.wilson_low, 0)}–{pct(g.wilson_high, 0)}</span>
                                                    </td>
                                                    <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{pct(g.avg_prob)}</td>
                                                    <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${gapColor}`}>{g.calib_gap > 0 ? '+' : ''}{pct(g.calib_gap)}</td>
                                                </tr>
                                                {open && (
                                                    <tr className="bg-black/40">
                                                        <td colSpan={6} className="px-4 py-3">
                                                            {drillLoading ? (
                                                                <div className="text-xs text-muted-foreground">Carico partite…</div>
                                                            ) : drillRows.length === 0 ? (
                                                                <div className="text-xs text-muted-foreground">Nessuna partita.</div>
                                                            ) : (
                                                                <div className="overflow-x-auto">
                                                                    <table className="w-full text-xs">
                                                                        <thead><tr className="text-[10px] uppercase text-muted-foreground/70">
                                                                            <th className="text-left px-2 py-1">Partita</th>
                                                                            <th className="text-left px-2 py-1 hidden md:table-cell">Mercato</th>
                                                                            <th className="text-right px-2 py-1">Prob</th>
                                                                            <th className="text-center px-2 py-1">Esito</th>
                                                                            <th className="text-right px-2 py-1 hidden md:table-cell">Freq Δ</th>
                                                                            <th className="text-right px-2 py-1 hidden md:table-cell">Ritardo</th>
                                                                            <th className="text-right px-2 py-1 hidden md:table-cell">1° gol</th>
                                                                        </tr></thead>
                                                                        <tbody>
                                                                            {drillRows.map((r, i) => (
                                                                                <tr key={i} className="border-t border-white/5">
                                                                                    <td className="px-2 py-1">{r.home_team} v {r.away_team}</td>
                                                                                    <td className="px-2 py-1 hidden md:table-cell text-muted-foreground">{r.engine} · {r.market} {r.selection}</td>
                                                                                    <td className="px-2 py-1 text-right tabular-nums">{pct(r.prob)}</td>
                                                                                    <td className={`px-2 py-1 text-center font-bold ${r.hit ? 'text-primary' : 'text-red-400'}`}>{r.hit ? '✓' : '✗'}</td>
                                                                                    <td className="px-2 py-1 text-right tabular-nums hidden md:table-cell text-muted-foreground">{r.freq_deviation != null ? (r.freq_deviation > 0 ? '+' : '') + pct(r.freq_deviation, 0) : '—'}</td>
                                                                                    <td className="px-2 py-1 text-right tabular-nums hidden md:table-cell text-muted-foreground">{r.delay_current ?? '—'}</td>
                                                                                    <td className="px-2 py-1 text-right tabular-nums hidden md:table-cell text-muted-foreground">{r.first_goal_minute != null ? `${r.first_goal_minute}'` : '—'}</td>
                                                                                </tr>
                                                                            ))}
                                                                        </tbody>
                                                                    </table>
                                                                    {drillRows.length >= 100 && <div className="text-[10px] text-muted-foreground/60 mt-1">Prime 100 partite.</div>}
                                                                </div>
                                                            )}
                                                        </td>
                                                    </tr>
                                                )}
                                            </Fragment>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                ) : (
                    <Card className="glass-card border-white/10 p-8 text-center text-muted-foreground text-sm">Nessun segnale settlato per questi filtri.</Card>
                )}

                {/* ---- DISCLAIMER (soldi in gioco) ---- */}
                <p className="text-[11px] text-muted-foreground/70 mt-6 leading-relaxed">
                    <strong className="text-muted-foreground">Nota.</strong> Hit-rate = % direzione azzeccata sulle partite
                    <em> settlate</em>. Motori <strong>Poisson/ML/Tactics</strong> = esito ai <strong>90'</strong> (no
                    supplementari/rigori). Motore <strong>API</strong> = solo 1X2, esito a <strong>tempo pieno</strong> →
                    confrontalo con cautela. Intervallo di Wilson 95%: con N basso la stima è incerta — guarda l'ampiezza.
                    <em> Scarto calib.</em> = hit-rate − prob. media: positivo = il motore <em>sottostima</em>, negativo =
                    <em> sovrastima</em>. Clic su un gruppo per le partite. <strong className="text-amber-400">⚠ Il filtro "1° gol entro min."
                    è RETROSPETTIVO</strong>: il minuto del primo gol è un esito della partita, non noto pre-match — usalo per analisi
                    storica / conferma in-play, NON come edge giocabile prima del fischio. Dati storici, non garanzia di risultati futuri.
                </p>

                </>}
            </main>
        </div>
    );
}
