// ============================================================================
// /watchlist — Watchlist personale. Tre tab (Da valutare / Giocate / Scartate)
// + analisi delle scartate (conteggio per motivo). Ogni partita è una card con
// lo snapshot pre-match immutabile e le azioni GIOCATA / SCARTATA (WatchlistPanel).
// Stesso guscio della Dashboard (navbar/footer/grid-pattern). ProtectedRoute.
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, Bookmark, AlertTriangle, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { WatchlistPanel } from '@/components/watchlist/WatchlistPanel';
import {
    getWatchlist, REJECT_REASON_LABELS,
    type WatchlistRow, type WatchlistStatus, type RejectReason,
} from '@/lib/watchlist';

type TabKey = 'DA_VALUTARE' | 'GIOCATA' | 'SCARTATA';

const TAB_LABEL: Record<TabKey, string> = {
    DA_VALUTARE: 'Da valutare',
    GIOCATA: 'Giocate',
    SCARTATA: 'Scartate',
};

export default function Watchlist() {
    const [tab, setTab] = useState<TabKey>('DA_VALUTARE');
    const [rows, setRows] = useState<WatchlistRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = async (status: WatchlistStatus) => {
        setLoading(true);
        setError(null);
        try {
            const data = await getWatchlist(status);
            setRows(data);
        } catch (e: any) {
            setError(e?.message ?? 'errore sconosciuto');
            setRows([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load(tab);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [tab]);

    // analisi scartate: conteggio per motivo (mostrato nel tab Scartate)
    const discardedByReason = useMemo(() => {
        if (tab !== 'SCARTATA') return [];
        const counts = new Map<string, number>();
        rows.forEach(r => {
            const key = r.reject_reason ?? 'altro';
            counts.set(key, (counts.get(key) ?? 0) + 1);
        });
        return Array.from(counts.entries())
            .map(([reason, n]) => ({ reason, n }))
            .sort((a, b) => b.n - a.n);
    }, [rows, tab]);

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet><title>Watchlist | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            {/* navbar */}
            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">AI <span className="text-primary">TERMINAL</span></Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-amber-300 font-heading font-bold ml-4">
                            <Bookmark className="w-4 h-4" /> WATCHLIST
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/report-personale">
                            <Button variant="outline" size="sm" className="border-primary/30 text-primary hover:bg-primary/10">
                                <Wallet className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Report</span>
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

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-4xl relative z-10">
                <div className="mb-6">
                    <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                        La mia <span className="text-amber-300">Watchlist</span>
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Snapshot pre-match congelati. Decidi se giocare o scartare — il sistema traccia consiglio e scelta.
                    </p>
                </div>

                <Tabs value={tab} onValueChange={v => setTab(v as TabKey)}>
                    <TabsList className="bg-black/40 border border-white/10">
                        {(Object.keys(TAB_LABEL) as TabKey[]).map(k => (
                            <TabsTrigger key={k} value={k}
                                className="data-[state=active]:bg-amber-400/20 data-[state=active]:text-amber-300">
                                {TAB_LABEL[k]}
                            </TabsTrigger>
                        ))}
                    </TabsList>

                    {(Object.keys(TAB_LABEL) as TabKey[]).map(k => (
                        <TabsContent key={k} value={k} className="mt-5 space-y-4">
                            {error && (
                                <Card className="glass-card border-red-500/30 p-4 flex items-center gap-2 text-red-400 text-sm">
                                    <AlertTriangle className="w-4 h-4" /> {error}
                                </Card>
                            )}

                            {/* analisi scartate */}
                            {k === 'SCARTATA' && !loading && discardedByReason.length > 0 && (
                                <Card className="glass-card border-white/10 p-4">
                                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mb-3">
                                        Analisi scartate · perché le scarti
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {discardedByReason.map(d => (
                                            <div key={d.reason}
                                                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/10 bg-white/[0.02]">
                                                <span className="text-xs text-white/80">
                                                    {REJECT_REASON_LABELS[d.reason as RejectReason] ?? d.reason}
                                                </span>
                                                <span className="text-sm font-mono font-bold text-red-400">{d.n}</span>
                                            </div>
                                        ))}
                                    </div>
                                </Card>
                            )}

                            <WatchlistPanel rows={rows} loading={loading} onChanged={() => load(tab)} />
                        </TabsContent>
                    ))}
                </Tabs>
            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
