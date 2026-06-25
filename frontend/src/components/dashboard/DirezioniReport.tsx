// ============================================================================
// DirezioniReport — report "Direzioni" della sezione Reportistiche (/analytics).
// Monitora come performano nel tempo i MIGLIORI SEGNALI della tab Direzione:
// andamento giornaliero, mappa di calore per segnale, classifica leghe, drill
// fino alla singola partita (le 7 direzioni con esito ✓/✗).
// Dati 100% da RPC certificate (get_direction_report*) — math validata da
// _certify_direction_report.py (oracolo == RPC, 0 mismatch). Auto-aggiornante:
// legge analytics_signals, settlata dalla pipeline giornaliera esistente.
// ============================================================================
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Filter, RotateCcw, AlertTriangle, ChevronDown, ChevronRight, Loader2, TrendingUp, Download } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { pct, downloadCsv } from '@/lib/analytics';
import {
    fetchDirReport, fetchDirMatches, fetchDirFixture,
    DIR_MARKETS, DIR_MARKET_SHORT, DIR_MARKET_LABEL,
    type DirReport, type DirMatchRow, type DirFixtureDetail,
} from '@/lib/reportistiche';

// ROI è una frazione (es. -0.05 = -5%). Verde se >0, rosso se <0.
const roiText = (r: number | null) =>
    r == null ? 'text-muted-foreground' : r > 0.0005 ? 'text-emerald-400' : r < -0.0005 ? 'text-red-400' : 'text-muted-foreground';
const signPct = (r: number | null, d = 1) => (r != null && r > 0 ? '+' : '') + pct(r, d);
const oddsFmt = (o: number | null) => (o == null ? '—' : o.toFixed(2));

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors';
const LABEL_CLS = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

// ---- date helpers (fuso locale = Europe/Rome per l'utente) ----
const isoDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const today = () => isoDate(new Date());
const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return isoDate(d); };
const dayShort = (iso: string) => { const [, m, d] = iso.split('-'); return `${d}/${m}`; };

// data minima ragionevole per "tutto lo storico" (la RPC restituisce solo ciò che esiste)
const EARLIEST = '2020-01-01';
const PRESETS = [
    { id: '7', label: '7 giorni', days: 6 },
    { id: '14', label: '14 giorni', days: 13 },
    { id: '30', label: '30 giorni', days: 29 },
    { id: '90', label: '90 giorni', days: 89 },
    { id: 'all', label: 'Tutto lo storico', days: -1 },
    { id: 'custom', label: 'Personalizza', days: 0 },
] as const;

// ---- colori (coerenti col design system: emerald/amber/red) ----
const hitText = (r: number | null) =>
    r == null ? 'text-muted-foreground' : r >= 0.6 ? 'text-emerald-400' : r >= 0.5 ? 'text-amber-400' : 'text-red-400';
const heatCls = (r: number | null) =>
    r == null ? 'bg-white/[0.04] text-muted-foreground/40'
        : r >= 0.75 ? 'bg-emerald-500/30 text-emerald-100'
        : r >= 0.60 ? 'bg-lime-500/25 text-lime-100'
        : r >= 0.50 ? 'bg-amber-500/25 text-amber-100'
        : 'bg-red-500/30 text-red-100';

const fixScore = (h: number | null, a: number | null) =>
    h == null || a == null ? '—' : `${h}-${a}`;

// Gli AGGREGATI (KPI/trend/heatmap/classifica) sono calcolati server-side su TUTTE
// le direzioni del periodo. La LISTA partite si carica a blocchi ("carica altre").
const PAGE_SIZE = 500;

// =================== TREND CHART (hit% vs atteso, per giorno) ===================
function TrendChart({ daily }: { daily: DirReport['daily'] }) {
    const vals = daily.flatMap(d => [d.hit_rate, d.avg_prob].filter((v): v is number => v != null));
    if (daily.length === 0 || vals.length === 0)
        return <div className="text-xs text-muted-foreground/60 py-10 text-center">Nessun dato nel periodo.</div>;
    const W = 640, H = 200, PL = 32, PR = 12, PT = 14, PB = 26;
    const xs = daily.map((_, i) => daily.length === 1 ? (PL + (W - PL - PR) / 2) : PL + i * (W - PL - PR) / (daily.length - 1));
    const lo = Math.max(0, Math.min(...vals) - 0.06);
    const hi = Math.min(1, Math.max(...vals) + 0.06);
    const sy = (v: number) => H - PB - ((v - lo) / Math.max(1e-9, hi - lo)) * (H - PT - PB);
    const ticks = [lo, (lo + hi) / 2, hi];
    const linePts = (key: 'hit_rate' | 'avg_prob') =>
        daily.map((d, i) => d[key] == null ? null : `${xs[i]},${sy(d[key] as number)}`).filter(Boolean).join(' ');
    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            {ticks.map((t, i) => (
                <g key={i}>
                    <line x1={PL} y1={sy(t)} x2={W - PR} y2={sy(t)} stroke="white" strokeOpacity={0.06} />
                    <text x={PL - 5} y={sy(t) + 3} fill="currentColor" className="text-muted-foreground" fontSize={9} textAnchor="end">{Math.round(t * 100)}%</text>
                </g>
            ))}
            {/* atteso (prob media) — tratteggiato */}
            <polyline points={linePts('avg_prob')} fill="none" stroke="hsl(45 90% 55%)" strokeOpacity={0.7} strokeWidth={1.5} strokeDasharray="4 3" />
            {/* hit reale — pieno */}
            <polyline points={linePts('hit_rate')} fill="none" stroke="hsl(155 84% 45%)" strokeWidth={2} />
            {daily.map((d, i) => d.hit_rate == null ? null : (
                <circle key={i} cx={xs[i]} cy={sy(d.hit_rate)} r={3} fill="hsl(155 84% 45%)">
                    <title>{`${d.giorno}: reale ${pct(d.hit_rate)} · atteso ${pct(d.avg_prob)} · N=${d.n}`}</title>
                </circle>
            ))}
            {daily.map((d, i) => (i % Math.ceil(daily.length / 12 || 1) === 0 || daily.length <= 12) ? (
                <text key={i} x={xs[i]} y={H - 8} fill="currentColor" className="text-muted-foreground" fontSize={8} textAnchor="middle">{dayShort(d.giorno)}</text>
            ) : null)}
        </svg>
    );
}

export default function DirezioniReport() {
    const [preset, setPreset] = useState<string>('7');
    const [from, setFrom] = useState<string>(daysAgo(6));
    const [to, setTo] = useState<string>(today());
    const [leagueId, setLeagueId] = useState<number | null>(null);
    const [market, setMarket] = useState<string | null>(null);
    const [onlyGood, setOnlyGood] = useState<boolean>(false);
    const [betfairOnly, setBetfairOnly] = useState<boolean>(false);

    const [report, setReport] = useState<DirReport | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [matches, setMatches] = useState<DirMatchRow[]>([]);
    const [matchTotal, setMatchTotal] = useState(0);
    const [loadingMore, setLoadingMore] = useState(false);
    const matchGenRef = useRef(0);   // generazione filtri: scarta pagine di filtri vecchi

    const [openFix, setOpenFix] = useState<number | null>(null);
    const [fixDetail, setFixDetail] = useState<DirFixtureDetail | null>(null);
    const [fixLoading, setFixLoading] = useState(false);
    const [fixError, setFixError] = useState<string | null>(null);
    const fixReqRef = useRef(0);

    const [minN, setMinN] = useState(14);

    function applyPreset(id: string) {
        setPreset(id);
        if (id === 'all') { setFrom(EARLIEST); setTo(today()); return; }
        const p = PRESETS.find(x => x.id === id);
        if (p && id !== 'custom') { setFrom(daysAgo(p.days)); setTo(today()); }
    }
    function reset() {
        setLeagueId(null); setMarket(null); setOnlyGood(false); setBetfairOnly(false); applyPreset('7'); setMinN(14);
    }

    const query = useMemo(() => ({ from, to, leagueId, market, onlyGood, betfairOnly }),
        [from, to, leagueId, market, onlyGood, betfairOnly]);

    useEffect(() => {
        let alive = true;
        matchGenRef.current += 1;   // invalida eventuali "carica altre" in volo
        setLoading(true); setError(null); setOpenFix(null); setFixDetail(null);
        const t = setTimeout(() => {
            Promise.all([fetchDirReport(query), fetchDirMatches(query, PAGE_SIZE, 0)])
                .then(([rep, m]) => { if (alive) { setReport(rep); setMatches(m.rows); setMatchTotal(m.total); } })
                .catch(e => { if (alive) setError(String(e.message || e)); })
                .finally(() => { if (alive) setLoading(false); });
        }, 250);
        return () => { alive = false; clearTimeout(t); };
    }, [query]);

    function loadMore() {
        const gen = matchGenRef.current;   // se i filtri cambiano, scarta questa pagina
        setLoadingMore(true);
        fetchDirMatches(query, PAGE_SIZE, matches.length)
            .then(m => { if (gen === matchGenRef.current) { setMatches(prev => [...prev, ...m.rows]); setMatchTotal(m.total); } })
            .catch(e => { if (gen === matchGenRef.current) setError(String(e.message || e)); })
            .finally(() => { if (gen === matchGenRef.current) setLoadingMore(false); });
    }

    function exportCsv(kind: 'segnale' | 'partite') {
        if (!report) return;
        const esc = (s: unknown) => `"${String(s ?? '').replace(/"/g, '""')}"`;
        const BOM = '﻿';   // apre bene su Excel IT (accenti squadre)
        if (kind === 'segnale') {
            const head = ['segnale', 'n', 'hit_rate', 'avg_prob', 'good_hit_rate', 'priced_n', 'roi', 'avg_odds'];
            const lines = [head.join(',')];
            for (const m of report.by_market)
                lines.push([esc(DIR_MARKET_LABEL[m.market] ?? m.market), m.n, m.hit_rate ?? '', m.avg_prob ?? '', m.good_hit_rate ?? '', m.priced_n, m.roi ?? '', m.avg_odds ?? ''].join(','));
            downloadCsv(`direzioni_segnali_${from}_${to}.csv`, BOM + lines.join('\n'));
        } else {
            const head = ['giorno', 'lega', 'casa', 'trasferta', 'ft', 'dir_ok', 'dir_tot', 'good_ok', 'good_tot', 'priced_n', 'profit', 'roi'];
            const lines = [head.join(',')];
            for (const mt of matches)
                lines.push([mt.giorno, esc(mt.league_name), esc(mt.home_team), esc(mt.away_team), `${mt.goals_home ?? ''}-${mt.goals_away ?? ''}`, mt.dir_ok, mt.dir_tot, mt.good_ok, mt.good_tot, mt.priced_n, mt.profit ?? '', mt.roi ?? ''].join(','));
            downloadCsv(`direzioni_partite_${from}_${to}.csv`, BOM + lines.join('\n'));
        }
    }

    function openFixture(fid: number) {
        if (openFix === fid) { setOpenFix(null); return; }
        setOpenFix(fid); setFixLoading(true); setFixDetail(null); setFixError(null);
        const req = ++fixReqRef.current;   // scarta risposte di click precedenti
        fetchDirFixture(fid)
            .then(d => { if (req === fixReqRef.current) setFixDetail(d); })
            .catch(e => { if (req === fixReqRef.current) setFixError(String(e.message || e)); })
            .finally(() => { if (req === fixReqRef.current) setFixLoading(false); });
    }

    const leagues = report?.meta.leagues ?? [];
    const heatDays = useMemo(() => Array.from(new Set((report?.by_market_day ?? []).map(d => d.giorno))).sort(), [report]);
    const heatLookup = useMemo(() => {
        const m = new Map<string, { n: number; hit_rate: number | null }>();
        for (const d of report?.by_market_day ?? []) m.set(`${d.market}|${d.giorno}`, { n: d.n, hit_rate: d.hit_rate });
        return m;
    }, [report]);
    const marketsShown = market ? [market] : DIR_MARKETS;
    const rankedLeagues = useMemo(() =>
        [...(report?.by_league ?? [])]
            .filter(l => l.n >= minN)
            .sort((a, b) => {
                if (a.hit_rate == null && b.hit_rate == null) return 0;
                if (a.hit_rate == null) return 1;
                if (b.hit_rate == null) return -1;
                return b.hit_rate - a.hit_rate;
            }),
        [report, minN]);

    const k = report?.kpi;

    return (
        <div className="space-y-5">
            {/* ---------------- FILTRI ---------------- */}
            <Card className="glass-card border-white/10 p-4 md:p-5">
                <div className="flex items-center gap-2 mb-4">
                    <Filter className="w-4 h-4 text-primary" />
                    <span className="font-heading font-bold text-sm uppercase tracking-wide">Filtri</span>
                    <Button variant="ghost" size="sm" onClick={reset} className="ml-auto text-xs text-muted-foreground hover:text-white">
                        <RotateCcw className="w-3 h-3 mr-1" /> Reset
                    </Button>
                </div>

                <div className="flex flex-wrap gap-2 mb-4">
                    {PRESETS.map(p => (
                        <Button key={p.id} variant={preset === p.id ? 'default' : 'outline'} size="sm"
                            onClick={() => applyPreset(p.id)}
                            className={preset === p.id ? 'bg-primary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}>
                            {p.label}
                        </Button>
                    ))}
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div>
                        <label className={LABEL_CLS}>Dal</label>
                        <input type="date" className={SELECT_CLS} value={from} max={to}
                            onChange={e => { setFrom(e.target.value); setPreset('custom'); }} />
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Al</label>
                        <input type="date" className={SELECT_CLS} value={to} min={from} max={today()}
                            onChange={e => { setTo(e.target.value); setPreset('custom'); }} />
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Lega</label>
                        <select className={SELECT_CLS} value={leagueId ?? ''} onChange={e => setLeagueId(e.target.value ? Number(e.target.value) : null)}>
                            <option value="">Tutte</option>
                            {[...leagues].sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '')).map(l => (
                                <option key={String(l.id)} value={l.id ?? ''}>{(l.name ?? `Lega ${l.id}`)} ({l.n})</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className={LABEL_CLS}>Segnale</label>
                        <select className={SELECT_CLS} value={market ?? ''} onChange={e => setMarket(e.target.value || null)}>
                            <option value="">Tutti</option>
                            {DIR_MARKETS.map(m => <option key={m} value={m}>{DIR_MARKET_LABEL[m]}</option>)}
                        </select>
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4">
                    <div className="flex items-center gap-2">
                        <Checkbox id="onlyGood" checked={onlyGood} onCheckedChange={v => setOnlyGood(!!v)} />
                        <label htmlFor="onlyGood" className="text-xs text-muted-foreground cursor-pointer">
                            Solo segnali <span className="text-white">"buoni"</span> (≥ 2 motori concordi)
                        </label>
                    </div>
                    <div className="flex items-center gap-2">
                        <Checkbox id="betfairOnly" checked={betfairOnly} onCheckedChange={v => setBetfairOnly(!!v)} />
                        <label htmlFor="betfairOnly" className="text-xs text-muted-foreground cursor-pointer">
                            Solo partite <span className="text-white">Betfair</span>
                        </label>
                    </div>
                </div>
            </Card>

            {error && (
                <Card className="glass-card border-red-500/30 p-4 flex items-center gap-2 text-red-400 text-sm">
                    <AlertTriangle className="w-4 h-4" /> {error}
                </Card>
            )}

            {loading || !report ? (
                <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24 w-full bg-white/5" />)}</div>
            ) : !k ? (
                <Card className="glass-card border-red-500/30 p-8 text-center text-red-400 text-sm">
                    Risposta del server incompleta (kpi mancante). Riprova o restringi i filtri.
                </Card>
            ) : k.n === 0 ? (
                <Card className="glass-card border-white/10 p-8 text-center text-muted-foreground text-sm">
                    Nessuna direzione settlata per questi filtri.
                </Card>
            ) : (
                <>
                    {/* ---------------- KPI ---------------- */}
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                        <Card className="glass-card border-white/10 p-4">
                            <div className={LABEL_CLS}>Direzioni</div>
                            <div className="font-display font-black text-2xl">{k.n.toLocaleString('it')}</div>
                            <div className="text-[10px] text-muted-foreground mt-1">con esito noto</div>
                        </Card>
                        <Card className="glass-card border-white/10 p-4">
                            <div className={LABEL_CLS}>Hit reale</div>
                            <div className={`font-display font-black text-2xl ${hitText(k.hit_rate)}`}>{pct(k.hit_rate)}</div>
                            <div className="text-[10px] text-muted-foreground mt-1 tabular-nums">IC 95% {pct(k.wilson_low, 0)}–{pct(k.wilson_high, 0)}</div>
                        </Card>
                        <Card className="glass-card border-white/10 p-4">
                            <div className={LABEL_CLS}>Atteso (calibr.)</div>
                            <div className="font-display font-black text-2xl text-white/80">{pct(k.avg_prob)}</div>
                            <div className={`text-[10px] mt-1 tabular-nums ${(k.calib_gap ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                scarto {(k.calib_gap ?? 0) > 0 ? '+' : ''}{pct(k.calib_gap)}
                            </div>
                        </Card>
                        <Card className="glass-card border-white/10 p-4">
                            <div className={LABEL_CLS}>Buone (≥2 conc.)</div>
                            <div className={`font-display font-black text-2xl ${hitText(k.good_hit_rate)}`}>{pct(k.good_hit_rate)}</div>
                            <div className="text-[10px] text-muted-foreground mt-1">{k.good_n.toLocaleString('it')} direzioni</div>
                        </Card>
                        <Card className="glass-card border-white/10 p-4">
                            <div className={LABEL_CLS}>Rendimento (ROI)</div>
                            <div className={`font-display font-black text-2xl ${roiText(k.roi)}`}>{signPct(k.roi)}</div>
                            <div className="text-[10px] text-muted-foreground mt-1 tabular-nums">
                                buone {signPct(k.good_roi, 0)} · q.media {oddsFmt(k.avg_odds)}
                            </div>
                        </Card>
                        <Card className="glass-card border-white/10 p-4">
                            <div className={LABEL_CLS}>Quote Betfair</div>
                            <div className="font-display font-black text-2xl text-white/80">
                                {k.n > 0 ? Math.round(100 * k.priced_n / k.n) : 0}%
                            </div>
                            <div className="text-[10px] text-muted-foreground mt-1 tabular-nums">
                                {k.priced_n.toLocaleString('it')}/{k.n.toLocaleString('it')} prezzate
                            </div>
                        </Card>
                    </div>
                    {k.priced_n === 0 ? (
                        <p className="text-[11px] text-amber-400/80 -mt-2">
                            ⚠ Nessuna direzione con quota Betfair in questo periodo/filtro: il <strong>ROI non è calcolabile</strong>.
                        </p>
                    ) : k.priced_n < k.n && (
                        <p className="text-[11px] -mt-2 text-muted-foreground/80">
                            ℹ Il ROI è calcolato sulle sole <strong>{k.priced_n.toLocaleString('it')}/{k.n.toLocaleString('it')}</strong> direzioni
                            con quota Betfair ({Math.round(100 * k.priced_n / k.n)}%) — le altre non hanno un prezzo su cui calcolarlo.
                            {k.priced_n < k.n * 0.5 && <strong className="text-amber-400"> Copertura bassa, leggi con cautela.</strong>}
                        </p>
                    )}

                    {/* ---------------- ANDAMENTO + HEATMAP ---------------- */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <Card className="glass-card border-white/10 p-4">
                            <div className="flex items-center justify-between mb-2">
                                <span className="font-heading font-bold text-sm uppercase tracking-wide flex items-center gap-1.5">
                                    <TrendingUp className="w-4 h-4 text-primary" /> Andamento
                                </span>
                                <span className="text-[10px] text-muted-foreground">━ reale · ┄ atteso</span>
                            </div>
                            <TrendChart daily={report.daily} />
                        </Card>

                        <Card className="glass-card border-white/10 p-4 overflow-x-auto">
                            <div className="flex items-center justify-between mb-3">
                                <span className="font-heading font-bold text-sm uppercase tracking-wide">Per segnale</span>
                                <span className="text-[10px] text-muted-foreground">🟩 ≥75 · 🟨 60 · 🟧 50 · 🟥 &lt;50</span>
                            </div>
                            <div className="min-w-[360px]">
                                <div className="flex items-center gap-1 mb-1 pl-[88px]">
                                    {heatDays.map(d => <div key={d} className="flex-1 text-center text-[8px] text-muted-foreground">{dayShort(d)}</div>)}
                                </div>
                                {marketsShown.map(m => (
                                    <div key={m} className="flex items-center gap-1 mb-1">
                                        <div className="w-[84px] text-[10px] text-muted-foreground truncate text-right pr-1">{DIR_MARKET_SHORT[m]}</div>
                                        {heatDays.map(d => {
                                            const c = heatLookup.get(`${m}|${d}`);
                                            return (
                                                <div key={d} className={`flex-1 h-7 rounded flex items-center justify-center text-[9px] tabular-nums ${heatCls(c?.hit_rate ?? null)}`}
                                                    title={c ? `${DIR_MARKET_SHORT[m]} ${d}: ${pct(c.hit_rate)} (N=${c.n})` : 'nessun dato'}>
                                                    {c && c.hit_rate != null ? Math.round(c.hit_rate * 100) : ''}
                                                </div>
                                            );
                                        })}
                                    </div>
                                ))}
                            </div>
                        </Card>
                    </div>

                    {/* ---------------- PER SEGNALE (riepilogo) ---------------- */}
                    <Card className="glass-card border-white/10 overflow-hidden">
                        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                            <span className="font-heading font-bold text-sm">Riepilogo per segnale</span>
                            <Button variant="outline" size="sm" onClick={() => exportCsv('segnale')} className="h-7 border-white/10 text-xs text-muted-foreground hover:text-white">
                                <Download className="w-3 h-3 mr-1" /> CSV
                            </Button>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead><tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left px-4 py-2 font-medium">Segnale</th>
                                    <th className="text-right px-3 py-2 font-medium">N</th>
                                    <th className="text-right px-3 py-2 font-medium">Hit</th>
                                    <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Atteso</th>
                                    <th className="text-right px-3 py-2 font-medium">Buone</th>
                                    <th className="text-right px-3 py-2 font-medium">ROI</th>
                                    <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Q.media</th>
                                </tr></thead>
                                <tbody>
                                    {[...report.by_market].sort((a, b) => (b.hit_rate ?? 0) - (a.hit_rate ?? 0)).map(mk => (
                                        <tr key={mk.market} className="border-b border-white/5">
                                            <td className="px-4 py-2.5 font-medium">{DIR_MARKET_LABEL[mk.market] ?? mk.market}</td>
                                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{mk.n.toLocaleString('it')}</td>
                                            <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${hitText(mk.hit_rate)}`}>{pct(mk.hit_rate)}</td>
                                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell">{pct(mk.avg_prob)}</td>
                                            <td className={`px-3 py-2.5 text-right tabular-nums ${hitText(mk.good_hit_rate)}`}>{pct(mk.good_hit_rate)} <span className="text-[10px] text-muted-foreground">({mk.good_n})</span></td>
                                            <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${roiText(mk.roi)}`}>{mk.priced_n > 0 ? signPct(mk.roi) : '—'}<span className="text-[10px] text-muted-foreground"> ({mk.priced_n})</span></td>
                                            <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell">{oddsFmt(mk.avg_odds)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>

                    {/* ---------------- FASCE: CONVINZIONE + QUOTA ---------------- */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <Card className="glass-card border-white/10 overflow-hidden">
                            <div className="px-4 py-3 border-b border-white/5 font-heading font-bold text-sm">Per convinzione (motori concordi)</div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead><tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                        <th className="text-left px-4 py-2 font-medium">Concordi</th>
                                        <th className="text-right px-3 py-2 font-medium">N</th>
                                        <th className="text-right px-3 py-2 font-medium">Hit</th>
                                        <th className="text-right px-3 py-2 font-medium">ROI</th>
                                        <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Q.media</th>
                                    </tr></thead>
                                    <tbody>
                                        {report.by_concordance.map(c => (
                                            <tr key={`conc-${c.agree ?? 'na'}`} className="border-b border-white/5">
                                                <td className="px-4 py-2.5 font-medium">{c.agree ?? '—'}/4 motori</td>
                                                <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{c.n.toLocaleString('it')}</td>
                                                <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${hitText(c.hit_rate)}`}>{pct(c.hit_rate)}</td>
                                                <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${roiText(c.roi)}`}>{c.priced_n > 0 ? signPct(c.roi) : '—'}<span className="text-[10px] text-muted-foreground"> ({c.priced_n})</span></td>
                                                <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell">{oddsFmt(c.avg_odds)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </Card>
                        <Card className="glass-card border-white/10 overflow-hidden">
                            <div className="px-4 py-3 border-b border-white/5 font-heading font-bold text-sm">Per fascia di quota (solo prezzabili)</div>
                            {report.by_odds_band.length === 0 ? (
                                <div className="p-6 text-center text-xs text-muted-foreground">Nessuna direzione con quota Betfair nel periodo.</div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead><tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                            <th className="text-left px-4 py-2 font-medium">Quota</th>
                                            <th className="text-right px-3 py-2 font-medium">Prezzate</th>
                                            <th className="text-right px-3 py-2 font-medium">Hit</th>
                                            <th className="text-right px-3 py-2 font-medium">ROI</th>
                                            <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Q.media</th>
                                        </tr></thead>
                                        <tbody>
                                            {report.by_odds_band.map(bnd => (
                                                <tr key={bnd.ord} className="border-b border-white/5">
                                                    <td className="px-4 py-2.5 font-medium tabular-nums">{bnd.band}</td>
                                                    <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{bnd.priced_n.toLocaleString('it')}</td>
                                                    <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${hitText(bnd.hit_rate)}`}>{pct(bnd.hit_rate)}</td>
                                                    <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${roiText(bnd.roi)}`}>{bnd.priced_n > 0 ? signPct(bnd.roi) : '—'}</td>
                                                    <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground hidden md:table-cell">{oddsFmt(bnd.avg_odds)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Card>
                    </div>

                    {/* ---------------- CLASSIFICA LEGHE ---------------- */}
                    <Card className="glass-card border-white/10 p-4">
                        <div className="flex items-center justify-between mb-3">
                            <span className="font-heading font-bold text-sm uppercase tracking-wide">Classifica leghe</span>
                            <label className="text-[10px] text-muted-foreground flex items-center gap-1">
                                min. direzioni
                                <select className="bg-black/60 border border-white/10 rounded px-1.5 py-0.5 text-white" value={minN} onChange={e => setMinN(Number(e.target.value))}>
                                    {[7, 14, 30, 50].map(v => <option key={v} value={v}>{v}</option>)}
                                </select>
                            </label>
                        </div>
                        {rankedLeagues.length === 0 ? (
                            <div className="text-xs text-muted-foreground py-4 text-center">Nessuna lega con ≥ {minN} direzioni nel periodo.</div>
                        ) : (
                            <div className="space-y-1.5">
                                {rankedLeagues.map(l => (
                                    <div key={String(l.league_id)} className="flex items-center gap-2 text-xs">
                                        <div className="w-40 md:w-52 truncate text-muted-foreground">{l.league_name ?? `Lega ${l.league_id}`}</div>
                                        <div className="flex-1 h-4 bg-white/5 rounded-full overflow-hidden relative">
                                            <div className={`h-full ${(l.hit_rate ?? 0) >= 0.6 ? 'bg-emerald-500/50' : (l.hit_rate ?? 0) >= 0.5 ? 'bg-amber-500/50' : 'bg-red-500/50'}`}
                                                style={{ width: `${(l.hit_rate ?? 0) * 100}%` }} />
                                        </div>
                                        <div className={`w-12 text-right tabular-nums font-bold ${hitText(l.hit_rate)}`}>{pct(l.hit_rate, 0)}</div>
                                        <div className={`w-14 text-right tabular-nums font-bold ${roiText(l.roi)}`} title="ROI alle quote Betfair (sulle prezzate)">{l.priced_n > 0 ? signPct(l.roi, 0) : '—'}</div>
                                        <div className="w-10 text-right tabular-nums text-muted-foreground/60 hidden md:block">{l.n}</div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>

                    {/* ---------------- DETTAGLIO PARTITE (drill) ---------------- */}
                    <Card className="glass-card border-white/10 overflow-hidden">
                        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between gap-2">
                            <span className="font-heading font-bold text-sm">Partite ({matches.length.toLocaleString('it')}{matchTotal > matches.length ? ` di ${matchTotal.toLocaleString('it')}` : ''}) · clic per le direzioni</span>
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] text-muted-foreground hidden md:inline">tutte=prese/tot · ROI alle quote Betfair</span>
                                <Button variant="outline" size="sm" onClick={() => exportCsv('partite')}
                                    title={matchTotal > matches.length
                                        ? `Esporta le ${matches.length.toLocaleString('it')} partite caricate (${matchTotal.toLocaleString('it')} totali — carica le altre prima per un CSV completo)`
                                        : 'Esporta tutte le partite in CSV'}
                                    className="h-7 border-white/10 text-xs text-muted-foreground hover:text-white">
                                    <Download className="w-3 h-3 mr-1" /> CSV{matchTotal > matches.length ? ` (${matches.length})` : ''}
                                </Button>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead><tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left px-4 py-2 font-medium">Giorno</th>
                                    <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Lega</th>
                                    <th className="text-left px-3 py-2 font-medium">Partita</th>
                                    <th className="text-center px-3 py-2 font-medium">FT</th>
                                    <th className="text-right px-3 py-2 font-medium">Tutte</th>
                                    <th className="text-right px-3 py-2 font-medium">Buone</th>
                                    <th className="text-right px-4 py-2 font-medium">ROI</th>
                                </tr></thead>
                                <tbody>
                                    {matches.map(mt => {
                                        const open = openFix === mt.fixture_id;
                                        const allRate = mt.dir_tot ? mt.dir_ok / mt.dir_tot : null;
                                        return (
                                            <Fragment key={mt.fixture_id}>
                                                <tr className={`border-b border-white/5 cursor-pointer hover:bg-white/[0.04] ${open ? 'bg-white/[0.04]' : ''}`} onClick={() => openFixture(mt.fixture_id)}>
                                                    <td className="px-4 py-2.5 text-muted-foreground tabular-nums">
                                                        <span className="inline-flex items-center gap-1">
                                                            {open ? <ChevronDown className="w-3 h-3 text-primary" /> : <ChevronRight className="w-3 h-3 opacity-40" />}
                                                            {dayShort(mt.giorno)}
                                                        </span>
                                                    </td>
                                                    <td className="px-3 py-2.5 text-muted-foreground hidden md:table-cell truncate max-w-[160px]">{mt.league_name ?? '—'}</td>
                                                    <td className="px-3 py-2.5">{mt.home_team} - {mt.away_team}</td>
                                                    <td className="px-3 py-2.5 text-center tabular-nums text-muted-foreground">{fixScore(mt.goals_home, mt.goals_away)}</td>
                                                    <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${hitText(allRate)}`}>{mt.dir_ok}/{mt.dir_tot}</td>
                                                    <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{mt.good_ok}/{mt.good_tot}</td>
                                                    <td className={`px-4 py-2.5 text-right tabular-nums font-bold ${roiText(mt.roi)}`} title={mt.priced_n > 0 ? `${mt.priced_n} prezzate` : 'nessuna quota'}>{mt.priced_n > 0 ? signPct(mt.roi, 0) : '—'}</td>
                                                </tr>
                                                {open && (
                                                    <tr className="bg-black/40">
                                                        <td colSpan={7} className="px-4 py-3">
                                                            {fixLoading ? (
                                                                <div className="text-xs text-muted-foreground flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" /> Carico le direzioni…</div>
                                                            ) : fixError ? (
                                                                <div className="text-xs text-red-400 flex items-center gap-2"><AlertTriangle className="w-3 h-3" /> {fixError}</div>
                                                            ) : !fixDetail || fixDetail.rows.length === 0 ? (
                                                                <div className="text-xs text-muted-foreground">Nessuna direzione.</div>
                                                            ) : (
                                                                <div className="overflow-x-auto">
                                                                    <table className="w-full text-xs">
                                                                        <thead><tr className="text-[10px] uppercase text-muted-foreground/70">
                                                                            <th className="text-left px-2 py-1">Segnale</th>
                                                                            <th className="text-left px-2 py-1">Direzione</th>
                                                                            <th className="text-right px-2 py-1">Prob</th>
                                                                            <th className="text-center px-2 py-1">Concordi</th>
                                                                            <th className="text-right px-2 py-1">Quota</th>
                                                                            <th className="text-center px-2 py-1">Esito</th>
                                                                            <th className="text-right px-2 py-1">P&L</th>
                                                                        </tr></thead>
                                                                        <tbody>
                                                                            {[...fixDetail.rows].sort((a, b) => (b.n_engines_agree ?? 0) - (a.n_engines_agree ?? 0)).map(r => (
                                                                                <tr key={`${r.market}-${r.selection}`} className="border-t border-white/5">
                                                                                    <td className="px-2 py-1">{DIR_MARKET_SHORT[r.market] ?? r.market}</td>
                                                                                    <td className="px-2 py-1 text-white">{r.selection}</td>
                                                                                    <td className="px-2 py-1 text-right tabular-nums">{pct(r.prob)}</td>
                                                                                    <td className="px-2 py-1 text-center tabular-nums text-muted-foreground">{r.n_engines_agree ?? '—'}/4</td>
                                                                                    <td className="px-2 py-1 text-right tabular-nums text-sky-300">{oddsFmt(r.odds)}</td>
                                                                                    <td className={`px-2 py-1 text-center font-bold ${r.hit == null ? 'text-muted-foreground' : r.hit ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                                        {r.hit == null ? '—' : r.hit ? '✓' : '✗'}
                                                                                    </td>
                                                                                    <td className={`px-2 py-1 text-right tabular-nums font-bold ${r.pnl == null ? 'text-muted-foreground' : r.pnl > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                                        {r.pnl == null ? '—' : (r.pnl > 0 ? '+' : '') + r.pnl.toFixed(2)}
                                                                                    </td>
                                                                                </tr>
                                                                            ))}
                                                                        </tbody>
                                                                    </table>
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
                        {matches.length < matchTotal && (
                            <div className="px-4 py-3 border-t border-white/5 flex items-center justify-center">
                                <Button variant="outline" size="sm" onClick={loadMore} disabled={loadingMore}
                                    className="border-white/10 text-muted-foreground hover:text-white">
                                    {loadingMore ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null}
                                    Carica altre {Math.min(PAGE_SIZE, matchTotal - matches.length).toLocaleString('it')} · mostrate {matches.length.toLocaleString('it')} di {matchTotal.toLocaleString('it')}
                                </Button>
                            </div>
                        )}
                    </Card>

                    {/* ---------------- DISCLAIMER ---------------- */}
                    <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                        <strong className="text-muted-foreground">Nota.</strong> "Direzione" = la selezione più probabile (argmax) del
                        motore <strong>Poisson</strong> per ogni mercato, come la tab Direzione. <em>Hit</em> = % direzioni azzeccate
                        sulle partite <em>settlate</em> ai <strong>90'</strong>. Denominatore = solo direzioni con esito noto (HT mancante
                        escluso, mai contato come errore). <em>"Buone"</em> = almeno 2 motori concordi. <em>Atteso</em> = probabilità media
                        dichiarata dai motori: se Hit ≈ Atteso il sistema è ben calibrato. Intervallo di Wilson 95%: con N basso la stima è
                        incerta. <strong>Rendimento (ROI)</strong> = P&amp;L di un <em>back</em> a puntata fissa alla quota Betfair (commissione 5% sulla
                        vincita), calcolato solo sulle direzioni con quota disponibile (la stessa quota mostrata nel resto dell'app, miglior
                        prezzo registrato). Si aggiorna da solo man mano che i risultati entrano. Dati storici, non garanzia di risultati futuri.
                    </p>
                </>
            )}
        </div>
    );
}
