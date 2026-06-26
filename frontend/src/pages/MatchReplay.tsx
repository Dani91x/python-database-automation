// ============================================================================
// /match-replay — "Match Replay" / Football Trading Simulator.
// Riproduce i dati di mercato registrati e consente di piazzare back/lay simulate
// alle quote storiche, tracciando il P&L (semantica Betfair Exchange).
// È DATA-DRIVEN: rende TUTTI i mercati presenti nel replay (2, 3 o N selezioni).
// La matematica P&L vive in src/lib/replay-pnl.ts (funzioni pure, testabili).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, History, AlertTriangle, Radio, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { PlaybackControls } from '@/components/replay/PlaybackControls';
import { TimelineSlider } from '@/components/replay/TimelineSlider';
import { MarketPanel } from '@/components/replay/MarketPanel';
import { TradesPanel } from '@/components/replay/TradesPanel';
import {
    fetchReplayList, fetchReplay,
    type ReplayItem, type ReplayData, type Frame,
} from '@/lib/live';
import {
    overallPosition, marketCashOut, formatGbp,
    type SimBet, type BetSide, type LadderMap, type MarketEval,
} from '@/lib/replay-pnl';

const PLAY_NORMAL_MS = 1000;
const PLAY_FAST_MS = 300;

// genera un id univoco per le bet simulate
function uid(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function MatchReplay() {
    // ---- selector vs simulatore ----
    const [list, setList] = useState<ReplayItem[]>([]);
    const [listLoading, setListLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [replay, setReplay] = useState<ReplayData | null>(null);
    const [replayLoading, setReplayLoading] = useState(false);

    // ---- stato simulatore ----
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [playDir, setPlayDir] = useState<1 | -1>(1);
    const [playSpeed, setPlaySpeed] = useState(PLAY_NORMAL_MS);
    const [bets, setBets] = useState<SimBet[]>([]);
    const [stakes, setStakes] = useState<Record<string, number>>({});
    // P&L già REALIZZATO da cash-out precedenti (le bet vengono rimosse, ma il
    // valore bloccato al momento del cash-out resta nella posizione complessiva).
    const [realizedPnl, setRealizedPnl] = useState(0);

    // ---- caricamento lista replay ----
    useEffect(() => {
        let alive = true;
        fetchReplayList(50)
            .then(rows => { if (alive) setList(rows); })
            .catch(e => { if (alive) setError(e?.message ?? 'errore sconosciuto'); })
            .finally(() => { if (alive) setListLoading(false); });
        return () => { alive = false; };
    }, []);

    // ---- selezione di un replay ----
    const selectReplay = async (item: ReplayItem) => {
        setReplayLoading(true);
        setError(null);
        try {
            const data = await fetchReplay(item.event_id);
            setReplay(data);
            setCurrentIndex(0);
            setIsPlaying(false);
            setBets([]);
            setStakes({});
            setRealizedPnl(0);
        } catch (e: any) {
            setError(e?.message ?? 'errore sconosciuto');
        } finally {
            setReplayLoading(false);
        }
    };

    const endSimulation = () => {
        setReplay(null);
        setIsPlaying(false);
        setBets([]);
        setStakes({});
        setCurrentIndex(0);
        setRealizedPnl(0);
    };

    // ---- timeline: timestamp distinti dei frame, ordinati ----
    const timeline = useMemo(() => {
        if (!replay) return [] as { ts: string; minute: number | null }[];
        const byTs = new Map<string, number | null>();
        for (const f of replay.frames) {
            if (!byTs.has(f.ts)) byTs.set(f.ts, f.minute);
            else if (byTs.get(f.ts) == null && f.minute != null) byTs.set(f.ts, f.minute);
        }
        return Array.from(byTs.entries())
            .map(([ts, minute]) => ({ ts, minute }))
            .sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
    }, [replay]);

    const maxIndex = Math.max(0, timeline.length - 1);
    const safeIndex = Math.min(currentIndex, maxIndex);
    const current = timeline[safeIndex] ?? { ts: '', minute: null };
    const currentTs = current.ts;
    const currentMinute = current.minute;

    // ---- frame raggruppati per mercato (ordinati per ts) ----
    const framesByMarket = useMemo(() => {
        const map = new Map<string, Frame[]>();
        if (!replay) return map;
        for (const f of replay.frames) {
            const arr = map.get(f.market_id) ?? [];
            arr.push(f);
            map.set(f.market_id, arr);
        }
        for (const arr of map.values()) arr.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
        return map;
    }, [replay]);

    // ladder corrente di un mercato = ultimo frame con ts <= currentTs.
    // bisect-right sui frame ordinati per ts → O(log n) per tick di playback.
    const currentLadder = (marketId: string): LadderMap | undefined => {
        const arr = framesByMarket.get(marketId);
        if (!arr || arr.length === 0 || !currentTs) return undefined;
        let lo = 0, hi = arr.length; // cerchiamo il primo indice con ts > currentTs
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (arr[mid].ts <= currentTs) lo = mid + 1; else hi = mid;
        }
        const found: Frame | undefined = lo > 0 ? arr[lo - 1] : undefined;
        return found?.ladder;
    };

    // ---- score timeline pre-ordinata (calcolata UNA volta per replay, non a ogni tick) ----
    const sortedScoreTimeline = useMemo(() => {
        if (!replay) return [];
        return [...replay.score_timeline].sort((a, b) => {
            const ma = a.minute ?? -1, mb = b.minute ?? -1;
            if (ma !== mb) return ma - mb;
            return a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0;
        });
    }, [replay]);

    // ---- score al minuto corrente (legge l'array già ordinato) ----
    const currentScore = useMemo(() => {
        const minute = currentMinute ?? Number.POSITIVE_INFINITY;
        let best: { home: number; away: number } | null = null;
        for (const ev of sortedScoreTimeline) {
            if ((ev.minute ?? -1) <= minute) {
                best = { home: ev.score_home ?? 0, away: ev.score_away ?? 0 };
            } else break;
        }
        return best ?? { home: 0, away: 0 };
    }, [sortedScoreTimeline, currentMinute]);

    // ---- mercati ordinati per sort_priority ----
    const markets = useMemo(() => {
        if (!replay) return [];
        return [...replay.markets].sort(
            (a, b) => (a.sort_priority ?? Number.MAX_SAFE_INTEGER) - (b.sort_priority ?? Number.MAX_SAFE_INTEGER),
        );
    }, [replay]);

    // ---- overall position = P&L realizzato (da cash-out) + cash-out corrente dei
    // mercati che hanno ancora bet aperte ----
    const overall = useMemo(() => {
        if (!replay) return realizedPnl;
        const evals: MarketEval[] = markets
            .map(m => ({
                bets: bets.filter(b => b.marketId === m.market_id),
                ladder: currentLadder(m.market_id),
                selectionIds: m.selections.map(s => s.selection_id),
            }))
            .filter(e => e.bets.length > 0);
        return realizedPnl + overallPosition(evals);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [bets, markets, safeIndex, framesByMarket, realizedPnl]);

    // ---- loop di riproduzione ----
    const idxRef = useRef(safeIndex);
    idxRef.current = safeIndex;
    useEffect(() => {
        if (!isPlaying) return;
        const id = setInterval(() => {
            const next = idxRef.current + playDir;
            if (next < 0 || next > maxIndex) { setIsPlaying(false); return; }
            idxRef.current = next;
            setCurrentIndex(next);
        }, playSpeed);
        return () => clearInterval(id);
    }, [isPlaying, playDir, playSpeed, maxIndex]);

    // ---- controlli ----
    const togglePlay = () => { setPlayDir(1); setPlaySpeed(PLAY_NORMAL_MS); setIsPlaying(p => !p); };
    const fastForward = () => { setPlayDir(1); setPlaySpeed(PLAY_FAST_MS); setIsPlaying(true); };
    const rewind = () => { setPlayDir(-1); setPlaySpeed(PLAY_FAST_MS); setIsPlaying(true); };
    const stepFwd = () => { setIsPlaying(false); setCurrentIndex(i => Math.min(maxIndex, i + 1)); };
    const stepBack = () => { setIsPlaying(false); setCurrentIndex(i => Math.max(0, i - 1)); };
    const skipStart = () => { setIsPlaying(false); setCurrentIndex(0); };
    const skipEnd = () => { setIsPlaying(false); setCurrentIndex(maxIndex); };

    // ---- gestione bet ----
    const getStake = (marketId: string) => stakes[marketId] ?? 100;
    const placeBet = (m: { market_id: string; market_name: string | null; market_type: string | null }) =>
        (selectionId: number, selectionName: string, side: BetSide, price: number) => {
            const stake = getStake(m.market_id);
            if (stake <= 0 || price <= 1) return;
            setBets(prev => [...prev, {
                id: uid(),
                marketId: m.market_id,
                selectionId,
                selectionName,
                marketName: m.market_name || m.market_type || 'Mercato',
                side,
                odds: price,
                stake,
                minute: currentMinute,
            }]);
        };
    const removeBet = (id: string) => setBets(prev => prev.filter(b => b.id !== id));
    // cash out: BLOCCA il valore corrente del mercato nel P&L realizzato, poi
    // chiude (rimuove) le posizioni del mercato alle quote correnti.
    const cashOutMarket = (marketId: string) => {
        const m = markets.find(mk => mk.market_id === marketId);
        if (!m) return;
        const marketBets = bets.filter(b => b.marketId === marketId);
        if (marketBets.length === 0) return;
        const locked = marketCashOut(marketBets, currentLadder(marketId), m.selections.map(s => s.selection_id));
        setRealizedPnl(p => p + locked);
        setBets(prev => prev.filter(b => b.marketId !== marketId));
    };

    // ---- badge Overall Position ----
    const overallCls = overall > 0
        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
        : overall < 0
            ? 'bg-red-500/15 text-red-300 border-red-500/50'
            : 'bg-secondary/15 text-secondary border-secondary/40';

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet><title>Match Replay | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">AI <span className="text-primary">TERMINAL</span></Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-secondary font-heading font-bold ml-4">
                            <History className="w-4 h-4" /> MATCH REPLAY
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/segui-live">
                            <Button variant="outline" size="sm" className="border-primary/30 text-primary hover:bg-primary/10">
                                <Radio className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Segui Live</span>
                            </Button>
                        </Link>
                        <Link to="/dashboard">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                <ChevronLeft className="w-4 h-4 mr-1" /> Dashboard
                            </Button>
                        </Link>
                    </div>
                </div>
            </nav>

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10">
                <div className="mb-6">
                    <h1 className="font-display font-black text-2xl md:text-4xl tracking-tight">
                        FOOTBALL TRADING <span className="text-secondary">SIMULATOR</span>
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Riproduci i dati di mercato registrati e piazza back/lay simulate alle quote storiche.
                    </p>
                </div>

                {error && (
                    <Card className="glass-card border-red-500/30 p-4 mb-4 flex items-center gap-2 text-red-400 text-sm">
                        <AlertTriangle className="w-4 h-4" /> {error}
                    </Card>
                )}

                {/* ============================ SELECTOR ============================ */}
                {!replay ? (
                    replayLoading || listLoading ? (
                        <div className="space-y-3">
                            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20 w-full bg-white/5" />)}
                        </div>
                    ) : list.length === 0 ? (
                        <Card className="glass-card border-white/10 p-10 text-center">
                            <History className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
                            <p className="text-sm text-muted-foreground">Nessun replay registrato disponibile.</p>
                        </Card>
                    ) : (
                        <div className="space-y-3">
                            {list.map(item => (
                                <Card key={item.event_id} onClick={() => selectReplay(item)}
                                    className="glass-card border-white/10 p-4 cursor-pointer transition-colors hover:bg-white/[0.04]">
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="min-w-0">
                                            <div className="text-[11px] uppercase tracking-wider text-muted-foreground truncate">
                                                {item.league_name ?? 'Lega sconosciuta'}
                                            </div>
                                            <div className="flex items-center gap-2 mt-0.5">
                                                <span className="text-emerald-400 font-bold truncate">{item.home_name}</span>
                                                <span className="text-white/30 text-xs">vs</span>
                                                <span className="text-amber-400 font-bold truncate">{item.away_name}</span>
                                            </div>
                                            <div className="text-[11px] text-muted-foreground mt-1">
                                                {(() => { try { return new Date(item.open_date).toLocaleString('it'); } catch { return item.open_date; } })()}
                                            </div>
                                        </div>
                                        <div className="text-right shrink-0">
                                            <div className="text-sm font-bold tabular-nums text-white">{item.n_markets ?? 0} mercati</div>
                                            <div className="text-[11px] text-muted-foreground tabular-nums">{item.n_snapshots ?? 0} snapshot</div>
                                        </div>
                                    </div>
                                </Card>
                            ))}
                        </div>
                    )
                ) : (
                    /* ============================ SIMULATORE ============================ */
                    <div className="space-y-5">
                        {/* header: overall position + end simulation */}
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                            <span className={`inline-flex items-center px-3 py-1.5 rounded-lg border text-sm font-bold tabular-nums ${overallCls}`}>
                                Overall Position: {formatGbp(overall)}
                            </span>
                            <Button size="sm" onClick={endSimulation}
                                className="bg-secondary text-black font-bold hover:bg-secondary/90">
                                <Square className="w-4 h-4 mr-1.5" /> End Simulation
                            </Button>
                        </div>

                        {/* match header con score al minuto corrente */}
                        <Card className="glass-card border-white/10 p-4">
                            <div className="text-[11px] uppercase tracking-wider text-muted-foreground text-center mb-1">
                                {replay.event.league_name ?? ''}
                            </div>
                            <div className="flex items-center justify-center gap-4">
                                <span className="text-emerald-400 font-bold text-lg truncate max-w-[36%] text-right">{replay.event.home_name}</span>
                                <span className="font-display font-black text-2xl md:text-3xl tabular-nums text-white">
                                    {currentScore.home} - {currentScore.away}
                                </span>
                                <span className="text-amber-400 font-bold text-lg truncate max-w-[36%]">{replay.event.away_name}</span>
                            </div>
                            <div className="text-center text-xs text-muted-foreground mt-1 tabular-nums">
                                {currentMinute != null ? `${currentMinute}'` : '—'}
                            </div>
                        </Card>

                        {/* controlli + timeline */}
                        <Card className="glass-card border-white/10 p-4 space-y-4">
                            <PlaybackControls
                                isPlaying={isPlaying}
                                onSkipStart={skipStart}
                                onRewind={rewind}
                                onStepBack={stepBack}
                                onTogglePlay={togglePlay}
                                onStepForward={stepFwd}
                                onFastForward={fastForward}
                                onSkipEnd={skipEnd}
                            />
                            <TimelineSlider
                                min={0} max={maxIndex} value={safeIndex} minute={currentMinute}
                                onChange={(v) => { setIsPlaying(false); setCurrentIndex(v); }}
                            />
                        </Card>

                        {/* griglia mercati */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            {markets.map(m => (
                                <MarketPanel
                                    key={m.market_id}
                                    market={m}
                                    ladder={currentLadder(m.market_id)}
                                    stake={getStake(m.market_id)}
                                    onStakeChange={(n) => setStakes(prev => ({ ...prev, [m.market_id]: n }))}
                                    bets={bets.filter(b => b.marketId === m.market_id)}
                                    onPlaceBet={placeBet(m)}
                                    onCashOut={() => cashOutMarket(m.market_id)}
                                />
                            ))}
                        </div>

                        {/* trades */}
                        <TradesPanel bets={bets} onRemove={removeBet} />

                        <p className="text-[11px] text-muted-foreground/70 leading-relaxed">
                            <strong className="text-muted-foreground">Nota P&L.</strong> Semantica Betfair Exchange.
                            BACK stake S a quota O: vince → +S·(O-1), perde → -S. LAY stake S a quota O: la selezione vince
                            → -S·(O-1) (liability), perde → +S. <em>Position</em> di una selezione = P&L del mercato se quella
                            selezione fosse l'esito vincente. <em>Cash out</em>/<em>Overall Position</em> = valore atteso del
                            libro sotto le probabilità implicite normalizzate (overround rimosso) alle quote correnti.
                            Simulazione didattica su dati storici.
                        </p>
                    </div>
                )}
            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
