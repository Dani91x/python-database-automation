// ============================================================================
// /segui-live — "Segui Live". Elenco delle partite attualmente sottoscritte allo
// stream Betfair (get_live_follows, refetch ogni 15s come backup). Clic su una
// card → dettaglio realtime (stessa pagina) sottoscritto a `live_now` per le
// quote che si aggiornano in tempo reale. Stesso design system del resto dell'app.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, Radio, AlertTriangle, History, Banknote, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { LiveMatchCard } from '@/components/live/LiveMatchCard';
import { LiveMarketBoard } from '@/components/live/LiveMarketBoard';
import { LiveSignalPanel } from '@/components/live/LiveSignalPanel';
import { LiveAlertBanner } from '@/components/live/LiveAlertBanner';
import { LiveTradingPanel, type PanelMode } from '@/components/live/LiveTradingPanel';
import { RiskRulesPanel } from '@/components/live/RiskRulesPanel';
import { DutchingPanel } from '@/components/live/DutchingPanel';
import { LiveControlsPanel } from '@/components/live/LiveControlsPanel';
import { sendCashoutAll, type LiveOrderMode } from '@/lib/liveOrders';
import {
    fetchLiveFollows, fetchLiveNow, subscribeLiveNow,
    type LiveFollow, type LiveNowRow, type LiveNowMarket,
} from '@/lib/live';

// chiave localStorage per ricordare il mercato attivo per-evento (cockpit multi-mercato).
const ACTIVE_MARKET_KEY = 'segui-live:active-market';

// Sezione "Live Trading" del dettaglio Segui Live: COCKPIT MULTI-MERCATO stile Bet Angel.
// Una TAB per mercato dell'evento (dai mercati di live_now, STESSA fonte del tabellone);
// il mercato attivo viene ricordato per-evento. Per il mercato attivo montiamo, affiancati:
// LiveTradingPanel (order entry + blotter + P&L), DutchingPanel (dutching multi-selezione)
// e RiskRulesPanel (offset / stop-loss / take-profit / trailing). In più un pulsante
// "Cash-out TUTTO il mercato" (mode-aware: conferma esplicita in LIVE).
// La modalità (OFF/PAPER/LIVE) arriva dal runner via live_now.state.order_mode.
function LiveTradingSection({ markets, orderMode, eventName, eventId }: {
    markets: LiveNowMarket[]; orderMode: string; eventName: string; eventId: string;
}) {
    const defaultId = useMemo(() => {
        const mo = markets.find(m => m.market_type === 'MATCH_ODDS' || /match odds/i.test(m.market_name ?? ''));
        return (mo ?? markets[0])?.market_id ?? '';
    }, [markets]);

    // stato iniziale: ripristina l'ultimo mercato scelto per questo evento, se ancora presente.
    const [marketId, setMarketId] = useState<string>(() => {
        try {
            const saved = localStorage.getItem(`${ACTIVE_MARKET_KEY}:${eventId}`);
            if (saved && markets.some(m => m.market_id === saved)) return saved;
        } catch { /* localStorage non disponibile */ }
        return defaultId;
    });
    const [cashingOut, setCashingOut] = useState(false);

    useEffect(() => {
        // se i mercati cambiano e il selezionato non esiste più, ripiega sul default
        if (marketId && !markets.some(m => m.market_id === marketId)) setMarketId(defaultId);
        else if (!marketId && defaultId) setMarketId(defaultId);
    }, [markets, marketId, defaultId]);

    // persisti il mercato attivo per-evento (memoria della tab).
    useEffect(() => {
        if (!eventId || !marketId) return;
        try { localStorage.setItem(`${ACTIVE_MARKET_KEY}:${eventId}`, marketId); } catch { /* no-op */ }
    }, [eventId, marketId]);

    const market = markets.find(m => m.market_id === marketId) ?? null;
    const mode = (['off', 'paper', 'live'].includes((orderMode || 'off').toLowerCase())
        ? (orderMode || 'off').toLowerCase() : 'off') as PanelMode;

    // memoizzati su `market`: live_now si aggiorna ogni pochi secondi → evita una nuova
    // reference di `selections` ad ogni tick (lavoro inutile nei pannelli).
    // panelSelections: shape minimale per LiveTradingPanel (id+name).
    const panelSelections = useMemo(
        () => (market?.selections ?? []).map(s => ({ selection_id: s.selection_id, name: s.name })),
        [market],
    );
    // richSelections: include quote correnti (back/lay/ltp) per Dutching e Risk (preview prezzi).
    const richSelections = useMemo(
        () => (market?.selections ?? []).map(s => ({
            selection_id: s.selection_id, name: s.name, back: s.back, lay: s.lay, ltp: s.ltp,
        })),
        [market],
    );

    const handleCashoutAll = useCallback(async () => {
        if (!market) return;
        if (mode === 'off') {
            toast.error('Runner in OFF: cash-out non disponibile. Avvia in PAPER o LIVE.');
            return;
        }
        // MONEY-CRITICAL: in LIVE serve conferma esplicita (soldi veri).
        if (mode === 'live' &&
            !window.confirm(`CASH-OUT REALE dell'intero mercato "${market.market_name || market.market_type}"?\nVerranno appiattite TUTTE le selezioni con esposizione aperta (soldi veri).`)) {
            return;
        }
        setCashingOut(true);
        try {
            const res = await sendCashoutAll({ marketId: market.market_id, mode: mode as LiveOrderMode });
            if (res.ok) {
                toast.success('Cash-out mercato inviato', {
                    description: res.status ?? (res.bet_id ? `req ${res.bet_id}` : undefined),
                });
            } else {
                toast.error('Cash-out rifiutato', { description: res.error ?? res.detail ?? 'motivo non noto' });
            }
        } catch (e: any) {
            toast.error('Errore cash-out', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setCashingOut(false);
        }
    }, [market, mode]);

    if (markets.length === 0) return null;
    return (
        <div className="space-y-3">
            {/* header sezione + cash-out totale mercato */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                    Mercati dell'evento
                </span>
                <Button
                    size="sm"
                    onClick={handleCashoutAll}
                    disabled={cashingOut || mode === 'off'}
                    className="bg-amber-500 hover:bg-amber-400 text-black font-black disabled:opacity-40"
                    title="Appiattisce (green-up) ogni selezione del mercato con esposizione aperta"
                >
                    {cashingOut ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Banknote className="w-4 h-4 mr-2" />}
                    Cash-out TUTTO il mercato
                </Button>
            </div>

            {/* TABS multi-mercato (stile Bet Angel) */}
            <div className="flex items-stretch gap-1 flex-wrap border-b border-white/5">
                {markets.map(m => {
                    const active = m.market_id === marketId;
                    return (
                        <button
                            key={m.market_id}
                            type="button"
                            onClick={() => setMarketId(m.market_id)}
                            className={`px-3 py-1.5 -mb-px rounded-t-lg text-xs font-bold border-b-2 transition-colors whitespace-nowrap ${
                                active
                                    ? 'border-primary text-white bg-white/[0.06]'
                                    : 'border-transparent text-muted-foreground hover:text-white hover:bg-white/[0.03]'
                            }`}
                        >
                            {m.market_name || m.market_type || m.market_id}
                        </button>
                    );
                })}
            </div>

            {market && (
                <div className="space-y-4">
                    <LiveTradingPanel
                        marketId={market.market_id}
                        mode={mode}
                        eventLabel={`${eventName} · ${market.market_name || market.market_type}`}
                        selections={panelSelections}
                    />
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
                        <DutchingPanel
                            marketId={market.market_id}
                            mode={mode}
                            selections={richSelections}
                        />
                        <RiskRulesPanel
                            marketId={market.market_id}
                            mode={mode}
                            selections={richSelections}
                        />
                    </div>
                </div>
            )}

            {/* ---- CONTROLLI GLOBALI del runner (kill-switch, limiti, audit) — uno solo per il cockpit ---- */}
            <LiveControlsPanel />
        </div>
    );
}

export default function SeguiLive() {
    const [follows, setFollows] = useState<LiveFollow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [selected, setSelected] = useState<LiveFollow | null>(null);
    const [liveNow, setLiveNow] = useState<LiveNowRow | null>(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const unsubRef = useRef<(() => void) | null>(null);

    // --- lista: caricamento + refetch ogni 15s come backup al realtime ---
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchLiveFollows()
                .then(rows => { if (alive) { setFollows(rows); setError(null); } })
                .catch(e => { if (alive) setError(e?.message ?? 'errore sconosciuto'); })
                .finally(() => { if (alive) setLoading(false); });
        };
        load();
        const id = setInterval(load, 15000);
        return () => { alive = false; clearInterval(id); };
    }, []);

    // --- dettaglio: snapshot iniziale + sottoscrizione realtime a live_now ---
    useEffect(() => {
        // pulizia eventuale sottoscrizione precedente
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        setLiveNow(null);
        if (!selected) { setDetailLoading(false); return; }

        let alive = true;
        setDetailLoading(true);
        fetchLiveNow(selected.event_id)
            .then(row => { if (alive) setLiveNow(row); })
            .catch((e: any) => {
                // PGRST116 = nessuna riga (live_now non ancora popolata): atteso, non logghiamo.
                if (e?.code !== 'PGRST116') console.warn('[SeguiLive] fetchLiveNow:', e);
            })
            .finally(() => { if (alive) setDetailLoading(false); });

        unsubRef.current = subscribeLiveNow(selected.event_id, (row) => {
            // payload DELETE → row null: manteniamo l'ultimo stato noto
            if (row) setLiveNow(row);
        });

        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [selected]);

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet><title>Segui Live | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">AI <span className="text-primary">TERMINAL</span></Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-primary font-heading font-bold ml-4">
                            <Radio className="w-4 h-4" /> SEGUI LIVE
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/match-replay">
                            <Button variant="outline" size="sm" className="border-secondary/30 text-secondary hover:bg-secondary/10">
                                <History className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Match Replay</span>
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

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-6xl relative z-10">
                {/* Avvisi limiti Betfair / sistema (Realtime), in cima alla pagina */}
                <LiveAlertBanner />

                <div className="mb-6 flex items-start justify-between gap-4">
                    <div>
                        <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                            Segui <span className="text-primary">Live</span>
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Partite sottoscritte allo stream Betfair. Clic su una partita per le quote in tempo reale.
                        </p>
                    </div>
                    {selected && (
                        <Button variant="outline" size="sm" onClick={() => setSelected(null)}
                            className="shrink-0 border-white/10 text-muted-foreground hover:text-white">
                            <ChevronLeft className="w-4 h-4 mr-1" /> Tutte le partite
                        </Button>
                    )}
                </div>

                {error && (
                    <Card className="glass-card border-red-500/30 p-4 mb-4 flex items-center gap-2 text-red-400 text-sm">
                        <AlertTriangle className="w-4 h-4" /> {error}
                    </Card>
                )}

                {loading ? (
                    <div className="space-y-3">
                        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full bg-white/5" />)}
                    </div>
                ) : selected ? (
                    /* ---- DETTAGLIO realtime ---- */
                    <div className="space-y-4">
                        <LiveMatchCard follow={selected} selected onClick={() => { /* già aperto */ }} />
                        {detailLoading && !liveNow ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40 w-full bg-white/5" />)}
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
                                <div className="lg:col-span-2">
                                    <LiveMarketBoard
                                        state={liveNow?.state ?? null}
                                        updatedAt={liveNow?.updated_at ?? null}
                                        orderMode={liveNow?.state?.order_mode ?? 'off'}
                                    />
                                </div>
                                <div className="lg:col-span-1">
                                    <LiveSignalPanel eventId={selected.event_id} state={liveNow?.state ?? null} />
                                </div>
                            </div>
                        )}

                        {/* ---- LIVE TRADING (stessa fonte: live_now) ---- */}
                        {liveNow?.state?.markets && liveNow.state.markets.length > 0 && (
                            <LiveTradingSection
                                markets={liveNow.state.markets}
                                orderMode={liveNow.state.order_mode ?? 'OFF'}
                                eventName={`${selected.home_name} vs ${selected.away_name}`}
                                eventId={selected.event_id}
                            />
                        )}
                    </div>
                ) : follows.length === 0 ? (
                    <Card className="glass-card border-white/10 p-10 text-center">
                        <Radio className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
                        <p className="text-sm text-muted-foreground">Nessuna partita in streaming.</p>
                    </Card>
                ) : (
                    /* ---- LISTA ---- */
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        {follows.map(f => (
                            <LiveMatchCard key={f.event_id} follow={f} onClick={() => setSelected(f)} />
                        ))}
                    </div>
                )}
            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
