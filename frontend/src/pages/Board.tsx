// ============================================================================
// /board — "Programma di oggi" (app desktop). Due tab (⚽ calcio / 🎾 tennis)
// alimentate ESCLUSIVAMENTE dai push 'board' dei due canali LOCALI (ws://127.0.0.1):
// nessuna lettura DB per il tabellone. Se un canale è off la tab lo dice onestamente
// ("canale locale non attivo") — mai un tabellone vuoto spacciato per programma vuoto.
//
// Per riga: evento, orario (countdown all'off se pre-match), badge in-play, quote
// back/lay per selezione (1X2 calcio / testa-a-testa tennis) e "Segui live":
//  - tennis → followTennisEvent (RPC dedicata) + link diretto al terminal;
//  - calcio → la registrazione del follow non è esposta via RPC dal frontend
//    (i follow calcio nascono dalla watchlist/runner) → link a /segui-live.
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, Radio, CalendarClock } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { countdownToOff } from '@/lib/matchClock';
import { followTennisEvent } from '@/lib/tennis';
import { getLocalChannel, type LocalSport } from '@/lib/localChannel';
import { useLocalStatus } from '@/lib/localTransport';
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';

// ---- shape del push 'board' (protocollo canale locale, identica per i due sport) ----
interface BoardSelection {
    selection_id: number;
    name: string;
    back: number | null;
    lay: number | null;
    ltp: number | null;
}
interface BoardRow {
    event_id: string;
    event_name: string;
    open_date: string;
    market_id: string;
    status: string | null;
    inplay: boolean;
    total_matched: number | null;
    selections: BoardSelection[];
}

const SPORT_TABS: { key: LocalSport; label: string }[] = [
    { key: 'calcio', label: '⚽ Calcio' },
    { key: 'tennis', label: '🎾 Tennis' },
];

const fmtPrice = (p: number | null): string => (p != null && p > 1 ? p.toFixed(2) : '—');
const fmtTime = (iso: string): string => {
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return '—';
    return new Date(t).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
};

// Cella quote back/lay di una selezione (tabular-nums, colori canonici sky/rose).
function OddsCell({ sel }: { sel: BoardSelection }) {
    return (
        <div className="flex flex-col items-center min-w-[72px]" title={sel.name}>
            <span className="text-[10px] text-slate-400 truncate max-w-[90px]">{sel.name}</span>
            <span className="font-mono tabular-nums text-[11px]">
                <span className="text-sky-300">{fmtPrice(sel.back)}</span>
                <span className="text-slate-600"> / </span>
                <span className="text-rose-300">{fmtPrice(sel.lay)}</span>
            </span>
        </div>
    );
}

// Una tab sport: righe dal push 'board' del canale corrispondente.
function SportBoard({ sport }: { sport: LocalSport }) {
    const status = useLocalStatus(sport);
    const [rows, setRows] = useState<BoardRow[] | null>(null);
    const [following, setFollowing] = useState<Record<string, 'pending' | 'done'>>({});

    // orologio per il countdown all'off (1s).
    const [nowTick, setNowTick] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setNowTick(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        const unsub = getLocalChannel(sport).subscribe('board', (d) => {
            const payload = d as { rows?: BoardRow[] } | null;
            if (payload?.rows) setRows(payload.rows);
        });
        return unsub;
    }, [sport]);

    // canale giù → il tabellone in memoria non è più affidabile.
    useEffect(() => {
        if (status === 'off') setRows(null);
    }, [status]);

    const sorted = useMemo(
        () => (rows ? [...rows].sort((a, b) => Date.parse(a.open_date) - Date.parse(b.open_date)) : null),
        [rows],
    );

    const handleFollowTennis = async (row: BoardRow) => {
        if (following[row.event_id]) return;
        setFollowing(f => ({ ...f, [row.event_id]: 'pending' }));
        try {
            await followTennisEvent(row.event_id, row.market_id);
            setFollowing(f => ({ ...f, [row.event_id]: 'done' }));
            toast.success('Evento registrato al follow tennis', { description: row.event_name });
        } catch (e: unknown) {
            setFollowing(f => { const rest = { ...f }; delete rest[row.event_id]; return rest; });
            toast.error('Follow tennis non riuscito', {
                description: e instanceof Error ? e.message : 'errore sconosciuto',
            });
        }
    };

    if (status === 'off') {
        return (
            <Card className="glass-card border-white/10 bg-slate-900 p-8 text-center">
                <Radio className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-[11px] text-slate-400">
                    Canale locale {sport} non attivo (ws://127.0.0.1:{sport === 'calcio' ? 47331 : 47332}).
                    Avvia l'app desktop / il runner {sport} per il programma in tempo reale.
                </p>
            </Card>
        );
    }

    if (!sorted) {
        return (
            <Card className="glass-card border-white/10 bg-slate-900 p-8 text-center">
                <p className="text-[11px] text-slate-400">Canale connesso: in attesa del primo tabellone…</p>
            </Card>
        );
    }

    if (sorted.length === 0) {
        return (
            <Card className="glass-card border-white/10 bg-slate-900 p-8 text-center">
                <p className="text-[11px] text-slate-400">Nessun evento nel programma di oggi.</p>
            </Card>
        );
    }

    return (
        <div className="space-y-1.5">
            {sorted.map(row => {
                const countdown = !row.inplay ? countdownToOff(row.open_date, nowTick) : null;
                const p1 = row.selections[0]?.name ?? '';
                const p2 = row.selections[1]?.name ?? '';
                const terminalHref = `/tennis/terminal?event=${encodeURIComponent(row.event_id)}`
                    + `&market=${encodeURIComponent(row.market_id)}&name=${encodeURIComponent('Match Odds')}`
                    + `&p1=${encodeURIComponent(p1)}&p2=${encodeURIComponent(p2)}`;
                return (
                    <div
                        key={row.event_id}
                        className="rounded-lg border border-white/10 bg-slate-900 px-3 py-2 flex items-center gap-3 flex-wrap text-[11px]"
                    >
                        {/* orario + countdown / badge in-play */}
                        <div className="flex flex-col min-w-[64px]">
                            <span className="font-mono tabular-nums text-slate-200">{fmtTime(row.open_date)}</span>
                            {row.inplay ? (
                                <span className="text-[9px] font-black text-emerald-300 animate-pulse">● IN-PLAY</span>
                            ) : countdown != null ? (
                                <span className="text-[9px] font-mono tabular-nums text-amber-300" title="Countdown all'off">
                                    OFF in {countdown}
                                </span>
                            ) : null}
                        </div>

                        {/* evento + stato mercato */}
                        <div className="flex-1 min-w-[180px]">
                            <div className="font-bold text-slate-100 truncate" title={row.event_name}>{row.event_name}</div>
                            <div className="text-[9px] text-slate-500 font-mono">
                                {row.status ?? ''}{row.total_matched != null ? ` · €${Math.round(row.total_matched).toLocaleString('it-IT')}` : ''}
                            </div>
                        </div>

                        {/* quote 1X2 / testa-a-testa (back/lay) */}
                        <div className="flex items-center gap-2">
                            {row.selections.slice(0, 3).map(sel => <OddsCell key={sel.selection_id} sel={sel} />)}
                        </div>

                        {/* azione: Segui live */}
                        {sport === 'tennis' ? (
                            <div className="flex items-center gap-1.5">
                                <Button
                                    size="sm"
                                    disabled={following[row.event_id] === 'pending'}
                                    onClick={() => void handleFollowTennis(row)}
                                    className="h-6 px-2 text-[10px] font-black bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40"
                                    title="Registra l'evento al follow tennis (tennis_follow_event): il runner lo prende in carico"
                                >
                                    {following[row.event_id] === 'done' ? '✓ Seguito' : 'Segui live'}
                                </Button>
                                <Link
                                    to={terminalHref}
                                    className="h-6 px-2 inline-flex items-center rounded-md border border-white/15 text-[10px] font-bold text-slate-300 hover:text-white hover:border-emerald-400/40"
                                    title="Apri il Tennis Trading Terminal su questo match"
                                >
                                    Terminal →
                                </Link>
                            </div>
                        ) : (
                            <Link
                                to="/segui-live"
                                className="h-6 px-2 inline-flex items-center rounded-md border border-white/15 text-[10px] font-bold text-slate-300 hover:text-white hover:border-emerald-400/40"
                                title="La registrazione del follow calcio non è esposta da questa pagina: apri Segui Live (i follow nascono da watchlist/runner)"
                            >
                                Segui live →
                            </Link>
                        )}
                        {/* video live + statistiche Betfair (sessione web utente) */}
                        <BetfairMediaButtons
                            compact
                            eventId={row.event_id}
                            marketId={row.market_id}
                            sport={sport === 'tennis' ? 'tennis' : 'calcio'}
                        />
                    </div>
                );
            })}
        </div>
    );
}

export default function Board() {
    const [sport, setSport] = useState<LocalSport>('calcio');
    const calcioStatus = useLocalStatus('calcio');
    const tennisStatus = useLocalStatus('tennis');

    return (
        <div className="min-h-screen bg-background relative pb-16">
            <Helmet><title>Programma di oggi | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">
                            AI <span className="text-primary">TERMINAL</span>
                        </Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-primary font-heading font-bold ml-4">
                            <CalendarClock className="w-4 h-4" /> PROGRAMMA
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/safe-strategy">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                🛡️ Safe Strategy
                            </Button>
                        </Link>
                        <Link to="/segui-live">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                Segui Live
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

            <main className="container mx-auto px-4 lg:px-6 py-8 relative z-10 max-w-5xl">
                <div className="mb-4">
                    <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                        Programma di <span className="text-primary">oggi</span>
                    </h1>
                    <p className="text-[11px] text-muted-foreground mt-1">
                        Tabellone in tempo reale dal canale locale del runner (push 'board', nessuna lettura DB).
                    </p>
                </div>

                {/* tab sport + stato canale per-sport */}
                <div className="flex items-stretch gap-1 border-b border-white/5 mb-3">
                    {SPORT_TABS.map(t => {
                        const st = t.key === 'calcio' ? calcioStatus : tennisStatus;
                        return (
                            <button
                                key={t.key}
                                type="button"
                                onClick={() => setSport(t.key)}
                                aria-pressed={sport === t.key}
                                className={`px-3 py-1.5 -mb-px rounded-t-lg text-xs font-bold border-b-2 transition-colors ${
                                    sport === t.key
                                        ? 'border-primary text-white bg-white/[0.06]'
                                        : 'border-transparent text-muted-foreground hover:text-white hover:bg-white/[0.03]'
                                }`}
                            >
                                {t.label}
                                <span
                                    className={`ml-1.5 inline-block w-1.5 h-1.5 rounded-full align-middle ${
                                        st === 'connected' ? 'bg-emerald-400' : 'bg-slate-600'
                                    }`}
                                    title={st === 'connected' ? 'Canale locale connesso' : 'Canale locale non attivo'}
                                />
                            </button>
                        );
                    })}
                </div>

                <SportBoard key={sport} sport={sport} />
            </main>
        </div>
    );
}
