// ============================================================================
// /segui-live — "Segui Live". Elenco delle partite attualmente sottoscritte allo
// stream Betfair (get_live_follows, refetch ogni 15s come backup). Clic su una
// card → dettaglio realtime (stessa pagina) sottoscritto a `live_now` per le
// quote che si aggiornano in tempo reale. Stesso design system del resto dell'app.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, Radio, AlertTriangle, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { LiveMatchCard } from '@/components/live/LiveMatchCard';
import { LiveMarketBoard } from '@/components/live/LiveMarketBoard';
import { LiveSignalPanel } from '@/components/live/LiveSignalPanel';
import { LiveAlertBanner } from '@/components/live/LiveAlertBanner';
import {
    fetchLiveFollows, fetchLiveNow, subscribeLiveNow,
    type LiveFollow, type LiveNowRow,
} from '@/lib/live';

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
                                    <LiveMarketBoard state={liveNow?.state ?? null} updatedAt={liveNow?.updated_at ?? null} />
                                </div>
                                <div className="lg:col-span-1">
                                    <LiveSignalPanel eventId={selected.event_id} />
                                </div>
                            </div>
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
