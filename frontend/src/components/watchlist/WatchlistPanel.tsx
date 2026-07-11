// ============================================================================
// WatchlistPanel — lista di card snapshot pre-match (1 per partita in watchlist).
// Mostra: identità match, badge stato, le selezioni dello snapshot (edges) con i
// CONSIGLI evidenziati (model_prob, back/lay Betfair, edge, affidabilità,
// concordi/motori), e le azioni GIOCATA (apre TradeForm) / SCARTATA (Dialog con
// motivo dall'enum §1.5). Tutto lo snapshot è server-side e immutabile.
// Design system: glass-card, badge a colori, emerald positivo / amber Betfair /
// red negativo, framer-motion, sonner.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
    Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp, Calendar, Trophy, Sparkles, Trash2, BarChart3,
    Circle, Send, RefreshCw, Radio,
} from 'lucide-react';
import { toast } from 'sonner';
import {
    setWatchlistDecision, deleteFromWatchlist, setWatchlistFollowLive, REJECT_REASON_LABELS,
    type WatchlistRow, type RejectReason, type SnapshotEdge, type WatchlistStatus,
} from '@/lib/watchlist';
import { refreshBetfairOdds, fetchBetfairDirectionOdds } from '@/lib/betfair';
import { fetchLiveFollows } from '@/lib/live';
import { TradeForm } from '@/components/watchlist/TradeForm';
import { MultiTradeForm, edgeKey } from '@/components/watchlist/MultiTradeForm';
import { PlacedOrdersPanel } from '@/components/watchlist/PlacedOrdersPanel';

// overlay quote aggiornate on-demand: per chiave (market|selection) → ultime back/lay.
type OddsOverlay = Record<string, { best_back: number | null; best_lay: number | null }>;

interface Props {
    rows: WatchlistRow[];
    loading?: boolean;
    onChanged?: () => void;   // ricarica la lista dopo una decisione/trade
}

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors';

// badge stato a colori
function StatusBadge({ status }: { status: WatchlistStatus }) {
    if (status === 'GIOCATA') return <Badge className="bg-primary/20 text-primary border border-primary/40">Giocata</Badge>;
    if (status === 'SCARTATA') return <Badge variant="destructive" className="bg-destructive/20 text-destructive border border-destructive/40">Scartata</Badge>;
    return <Badge className="bg-amber-400/20 text-amber-300 border border-amber-400/40">Da valutare</Badge>;
}

const fmtPct = (v: number | null | undefined, d = 1) =>
    v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`;
const fmtOdds = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? '—' : v.toFixed(2);
const fmtKickoff = (iso: string | null) => {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleString('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    } catch { return '—'; }
};

// Riga selezione dello snapshot. `recommended` = presente nei consigli.
// `selectable` mostra il cerchietto per spuntare la selezione → Scheda Trade.
// `updated` = quota rinfrescata on-demand (overlay): mostra un indicatore.
function EdgeRow({ e, recommended, selectable, selected, onToggle, updated }: {
    e: SnapshotEdge; recommended: boolean;
    selectable?: boolean; selected?: boolean; onToggle?: () => void; updated?: boolean;
}) {
    const edgeColor = e.edge > 0.02 ? 'text-emerald-400' : e.edge > 0 ? 'text-amber-400' : 'text-red-400';
    return (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[11px] ${selected
            ? 'bg-primary/10 border-primary/40'
            : recommended
                ? 'bg-amber-400/5 border-amber-400/30'
                : 'bg-white/[0.02] border-white/10'}`}>
            {selectable && (
                <button
                    type="button"
                    onClick={onToggle}
                    className="shrink-0"
                    aria-pressed={selected}
                    aria-label={selected ? `Deseleziona ${e.market} ${e.selection}` : `Seleziona ${e.market} ${e.selection}`}
                    title={selected ? 'Deseleziona' : 'Seleziona per la giocata'}
                >
                    {selected
                        ? <CheckCircle2 className="w-4 h-4 text-primary" />
                        : <Circle className="w-4 h-4 text-muted-foreground/50 hover:text-white transition-colors" />}
                </button>
            )}
            {recommended && <Sparkles className="w-3 h-3 text-amber-300 shrink-0" />}
            <div className="min-w-0 flex-1">
                <span className="font-bold text-white">{e.market}</span>
                <span className="text-white/60"> · {e.selection}</span>
                {updated && (
                    <span className="ml-1.5 text-emerald-400" title="quota aggiornata da Betfair" aria-label="quota aggiornata">●</span>
                )}
            </div>
            <div className="text-right shrink-0 w-14">
                <div className="font-mono text-white">{fmtPct(e.model_prob, 0)}</div>
                <div className="text-[9px] uppercase text-muted-foreground/60">prob</div>
            </div>
            <div className="text-right shrink-0 w-20 hidden sm:block">
                <div className="font-mono">
                    <span className="text-sky-300">{fmtOdds(e.best_back)}</span>
                    <span className="text-white/20"> / </span>
                    <span className="text-rose-300">{fmtOdds(e.best_lay)}</span>
                </div>
                <div className="text-[9px] uppercase text-muted-foreground/60">back / lay</div>
            </div>
            <div className="text-right shrink-0 w-14">
                <div className={`font-mono font-bold ${edgeColor}`}>{e.edge >= 0 ? '+' : ''}{fmtPct(e.edge, 1)}</div>
                <div className="text-[9px] uppercase text-muted-foreground/60">edge</div>
            </div>
            <div className="text-right shrink-0 w-12 hidden md:block">
                <div className="font-mono text-white">{e.concordi?.length ?? 0}/{e.motori_totali}</div>
                <div className="text-[9px] uppercase text-muted-foreground/60">motori</div>
            </div>
        </div>
    );
}

function WatchlistCard({ row, onChanged }: { row: WatchlistRow; onChanged?: () => void }) {
    const navigate = useNavigate();
    const [expanded, setExpanded] = useState(false);
    const [tradeOpen, setTradeOpen] = useState(false);
    const [multiOpen, setMultiOpen] = useState(false);
    const [rejectOpen, setRejectOpen] = useState(false);
    const [delOpen, setDelOpen] = useState(false);
    // chiavi (market|selection) delle selezioni spuntate per la giocata multipla
    const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
    // "Aggiorna quote": overlay delle ultime back/lay (non muta lo snapshot congelato)
    const [refreshing, setRefreshing] = useState(false);
    const [oddsOverlay, setOddsOverlay] = useState<OddsOverlay>({});
    // "Segui live": toggle del flag follow_live (iscrizione stream, nessun ordine)
    const [followBusy, setFollowBusy] = useState(false);
    // ACK REGISTRAZIONE (fix 11/07 — danno 10/07: 2 partite cliccate durante
    // un crash UI, follow MAI registrato, dati persi per sempre): dopo
    // l'attivazione si VERIFICA che il runner prenda in carico il follow
    // (get_live_follows → PENDING/STREAMING) e lo stato è mostrato accanto al
    // bottone. Il silenzio NON è una conferma di registrazione.
    const [followAck, setFollowAck] = useState<'idle' | 'waiting' | 'pending' | 'streaming' | 'timeout'>('idle');
    const ackTimer = useRef<number | null>(null);
    const stopAckWatch = useCallback(() => {
        if (ackTimer.current != null) { window.clearInterval(ackTimer.current); ackTimer.current = null; }
    }, []);
    useEffect(() => () => stopAckWatch(), [stopAckWatch]);
    const startAckWatch = useCallback(() => {
        stopAckWatch();
        setFollowAck('waiting');
        const t0 = Date.now();
        const tick = async () => {
            try {
                const follows = await fetchLiveFollows();
                const f = follows.find(x => x.fixture_id === row.fixture_id);
                if (f?.status === 'STREAMING') {
                    setFollowAck('streaming');
                    toast.success('Registrazione CONFERMATA ●', {
                        description: 'Il runner sta registrando lo stream della partita.',
                    });
                    stopAckWatch();
                    return;
                }
                if (f?.status === 'ERROR') {
                    setFollowAck('timeout');
                    toast.error('Follow in ERRORE', { description: f.error_detail ?? 'vedi log runner' });
                    stopAckWatch();
                    return;
                }
                if (f?.status === 'PENDING') setFollowAck('pending');
            } catch { /* transitorio: riprova al prossimo giro */ }
            if (Date.now() - t0 > 4 * 60_000) {
                setFollowAck('timeout');
                toast.warning('Registrazione NON confermata', {
                    description: 'Nessuna presa in carico dal runner in 4 minuti: la partita NON si sta registrando. Verificare che il runner sia acceso.',
                });
                stopAckWatch();
            }
        };
        void tick();
        ackTimer.current = window.setInterval(tick, 20_000);
    }, [row.fixture_id, stopAckWatch]);
    // bump per forzare il refresh immediato del pannello "Ordini piazzati" dopo una giocata
    const [orderRefresh, setOrderRefresh] = useState(0);
    // dopo un piazzamento: aggiorna subito il pannello ordini E ricarica la lista
    const handleTradeSaved = useCallback(() => { setOrderRefresh(x => x + 1); onChanged?.(); }, [onChanged]);

    // set delle selezioni consigliate (per evidenziare le righe edges)
    const consigliKeys = useMemo(() => {
        const s = new Set<string>();
        (row.consigli ?? []).forEach(c => s.add(`${c.market}|${c.selection}`));
        return s;
    }, [row.consigli]);

    const edges = useMemo(() => row.snapshot?.edges ?? [], [row.snapshot?.edges]);
    const isDecided = row.status !== 'DA_VALUTARE';
    // le scartate non sono giocabili → niente spunte. Le da-valutare/giocate sì.
    const selectable = row.status !== 'SCARTATA';

    const toggleKey = (k: string) => setSelectedKeys(prev => {
        const n = new Set(prev);
        if (n.has(k)) n.delete(k); else n.add(k);
        return n;
    });

    // Applica l'overlay quote (se presente) a un edge: aggiorna back/lay e RICALCOLA
    // l'edge = model_prob - 1/back con la quota fresca. Non muta lo snapshot congelato.
    const applyOverlay = useCallback((e: SnapshotEdge): SnapshotEdge => {
        const o = oddsOverlay[edgeKey(e)];
        if (!o) return e;
        const edge = (e.model_prob != null && o.best_back != null && o.best_back > 1)
            ? e.model_prob - 1 / o.best_back
            : e.edge;
        return { ...e, best_back: o.best_back, best_lay: o.best_lay, edge };
    }, [oddsOverlay]);

    // selezioni spuntate, con quote aggiornate applicate (prefill = ultima quota).
    const selectedEdges = useMemo(
        () => edges.filter(e => selectedKeys.has(edgeKey(e))).map(applyOverlay),
        [edges, selectedKeys, applyOverlay],
    );

    // Aggiorna quote Betfair on-demand di QUESTA partita (via runner locale), poi
    // ricalcola gli edge mostrati. Funziona anche pre-match (semplice chiamata API).
    const handleRefreshOdds = async () => {
        setRefreshing(true);
        try {
            const res = await refreshBetfairOdds(row.fixture_id);
            if (!res.ok) {
                toast.error('Quote non aggiornate', {
                    description: res.error ?? res.reason ?? 'nessuna quota disponibile per questa partita.',
                });
                return;
            }
            const dir = await fetchBetfairDirectionOdds(String(row.fixture_id));
            const overlay: OddsOverlay = {};
            for (const e of edges) {
                const node = dir[e.market]?.[e.selection];
                if (node) {
                    overlay[edgeKey(e)] = {
                        best_back: node.back?.[0]?.price ?? null,
                        best_lay: node.lay?.[0]?.price ?? null,
                    };
                }
            }
            const overlaySize = Object.keys(overlay).length;
            setOddsOverlay(overlay);
            if (overlaySize > 0) {
                toast.success('Quote aggiornate da Betfair', {
                    description: `${res.markets ?? 0} mercati · ${overlaySize} edge ricalcolati.`,
                });
            } else {
                toast.success('Quote scritte nel DB', {
                    description: `${res.markets ?? 0} mercati aggiornati. Nessun edge da ricalcolare nello snapshot.`,
                });
            }
        } catch (err: unknown) {
            toast.error('Aggiorna quote fallito', {
                description: err instanceof Error ? err.message : 'errore sconosciuto',
            });
        } finally {
            setRefreshing(false);
        }
    };

    // Accende/spegne "Segui live" (iscrizione allo stream; NESSUN ordine reale).
    const handleToggleFollow = async () => {
        const next = !row.follow_live;
        setFollowBusy(true);
        try {
            await setWatchlistFollowLive(row.id, next);
            toast.success(next ? 'Segui live attivato' : 'Segui live disattivato', {
                description: next
                    ? 'Richiesta scritta. In attesa della PRESA IN CARICO del runner (ack entro ~90s)…'
                    : undefined,
            });
            if (next) startAckWatch();
            else { stopAckWatch(); setFollowAck('idle'); }
            onChanged?.();
        } catch (err: unknown) {
            toast.error('Errore Segui live', {
                description: err instanceof Error ? err.message : 'errore sconosciuto',
            });
        } finally {
            setFollowBusy(false);
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-2xl border border-white/10 overflow-hidden"
        >
            {/* header card */}
            <div className="px-4 py-3 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm md:text-base font-bold text-white truncate">
                            {row.home_team} <span className="text-muted-foreground font-normal">vs</span> {row.away_team}
                        </span>
                        <StatusBadge status={row.status} />
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-0.5">
                        <span className="flex items-center gap-1"><Trophy className="w-3 h-3" /> {row.league_name ?? 'Lega n/d'}</span>
                        <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> {fmtKickoff(row.kickoff)}</span>
                        {row.n_trades > 0 && <span className="text-primary">{row.n_trades} trade</span>}
                    </div>
                </div>
                {/* azioni rapide di riga: statistiche (deep-link Dashboard) + aggiorna quote */}
                <div className="shrink-0 flex items-center gap-1.5">
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => navigate(`/dashboard?fixture=${row.fixture_id}&from=watchlist`)}
                        className="h-8 border-primary/30 text-primary hover:bg-primary/10"
                        title="Apri la scheda statistiche di questa partita"
                        aria-label="Vai alle statistiche di questa partita"
                    >
                        <BarChart3 className="w-3.5 h-3.5 md:mr-1.5" />
                        <span className="hidden md:inline">Vai alle statistiche</span>
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={handleRefreshOdds}
                        disabled={refreshing}
                        className="h-8 border-amber-400/30 text-amber-300 hover:bg-amber-400/10"
                        title="Aggiorna le quote Betfair di questa partita"
                        aria-label="Aggiorna le quote Betfair di questa partita"
                    >
                        {refreshing
                            ? <Loader2 className="w-3.5 h-3.5 md:mr-1.5 animate-spin" />
                            : <RefreshCw className="w-3.5 h-3.5 md:mr-1.5" />}
                        <span className="hidden md:inline">Aggiorna quote</span>
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={handleToggleFollow}
                        disabled={followBusy}
                        aria-pressed={row.follow_live}
                        className={row.follow_live
                            ? 'h-8 border-emerald-400/50 text-emerald-300 bg-emerald-400/10 hover:bg-emerald-400/20'
                            : 'h-8 border-white/15 text-muted-foreground hover:text-white'}
                        title={row.follow_live
                            ? 'Segui live ATTIVO — clic per disattivare (nessun ordine)'
                            : 'Segui live — iscrivi la partita allo stream (solo dati, nessun ordine)'}
                        aria-label={row.follow_live ? 'Segui live attivo' : 'Segui live inattivo'}
                    >
                        {followBusy
                            ? <Loader2 className="w-3.5 h-3.5 md:mr-1.5 animate-spin" />
                            : <Radio className="w-3.5 h-3.5 md:mr-1.5" />}
                        <span className="hidden md:inline">{row.follow_live ? 'Segui live ✓' : 'Segui live'}</span>
                    </Button>
                    {row.follow_live && followAck !== 'idle' && (
                        <span
                            className={
                                followAck === 'streaming'
                                    ? 'text-[10px] font-semibold text-red-400 animate-pulse'
                                    : followAck === 'timeout'
                                        ? 'text-[10px] font-semibold text-amber-400'
                                        : 'text-[10px] text-muted-foreground'
                            }
                            title={
                                followAck === 'streaming'
                                    ? 'Il runner sta registrando lo stream'
                                    : followAck === 'timeout'
                                        ? 'Presa in carico NON confermata: la partita non si sta registrando'
                                        : 'In attesa della presa in carico del runner'
                            }
                        >
                            {followAck === 'streaming' ? '● REC'
                                : followAck === 'pending' ? 'in coda…'
                                    : followAck === 'waiting' ? 'verifica…'
                                        : '⚠ non confermata'}
                        </span>
                    )}
                </div>
                <button
                    onClick={() => setExpanded(v => !v)}
                    className="shrink-0 text-muted-foreground hover:text-white p-1"
                    aria-label={expanded ? 'Comprimi' : 'Espandi'}
                >
                    {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>
            </div>

            {/* consigli rapidi (sempre visibili come riepilogo) */}
            {(row.consigli ?? []).length > 0 && (
                <div className="px-4 pb-2 flex flex-wrap gap-1.5">
                    {(row.consigli ?? []).slice(0, 5).map((c, i) => (
                        <span key={`${c.market}-${c.selection}-${i}`}
                            className="px-2 py-0.5 rounded-md border border-amber-400/30 bg-amber-400/5 text-[10px] text-amber-200">
                            {c.market} · {c.selection} <span className="font-mono">{c.edge >= 0 ? '+' : ''}{fmtPct(c.edge, 1)}</span>
                        </span>
                    ))}
                </div>
            )}

            {/* Ordini piazzati (reali) di questa partita — visibile quando ci sono trade
                o quando la card è espansa; si auto-aggiorna e si nasconde se vuoto. */}
            {(row.n_trades > 0 || expanded) && (
                <div className="px-4 pb-2">
                    <PlacedOrdersPanel fixtureId={row.fixture_id} refreshTrigger={orderRefresh} />
                </div>
            )}

            {/* dettaglio snapshot */}
            {expanded && (
                <div className="px-4 pb-4 border-t border-white/5 pt-3 space-y-3">
                    {edges.length > 0 ? (
                        <div>
                            <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1.5 font-bold">
                                Selezioni snapshot <span className="text-amber-300">· consigli evidenziati</span>
                            </div>
                            <div className="space-y-1.5">
                                {edges.map((e, i) => (
                                    <EdgeRow key={`${e.market}-${e.selection}-${i}`} e={applyOverlay(e)}
                                        recommended={consigliKeys.has(`${e.market}|${e.selection}`)}
                                        selectable={selectable}
                                        selected={selectedKeys.has(edgeKey(e))}
                                        onToggle={() => toggleKey(edgeKey(e))}
                                        updated={Boolean(oddsOverlay[edgeKey(e)])} />
                                ))}
                            </div>
                            {selectable && edges.length > 0 && (
                                <p className="text-[10px] text-muted-foreground/70 mt-1.5">
                                    Spunta una o più selezioni per pre-compilare la Scheda Trade · 1 selezione = 1 giocata.
                                </p>
                            )}
                        </div>
                    ) : (
                        <p className="text-[11px] text-white/40">
                            Nessun edge nello snapshot (motori o quote Betfair non disponibili al momento del congelamento).
                        </p>
                    )}

                    {row.snapshot?.full_odds_markets && row.snapshot.full_odds_markets.length > 0 && (
                        <p className="text-[10px] text-muted-foreground/70">
                            Mercati Betfair disponibili: {row.snapshot.full_odds_markets.length}.
                        </p>
                    )}

                    {/* dettaglio decisione presa */}
                    {row.status === 'SCARTATA' && (
                        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11px] text-red-300">
                            <span className="font-bold">Scartata</span>
                            {row.reject_reason && <> · {REJECT_REASON_LABELS[row.reject_reason] ?? row.reject_reason}</>}
                            {row.reject_note && <div className="text-red-300/70 mt-0.5">"{row.reject_note}"</div>}
                        </div>
                    )}
                    {row.user_note && (
                        <p className="text-[11px] text-muted-foreground">Nota: {row.user_note}</p>
                    )}
                </div>
            )}

            {/* azioni */}
            <div className="px-4 py-3 border-t border-white/5 flex items-center gap-2">
                {selectedKeys.size > 0 ? (
                    <>
                        <Button
                            onClick={() => setMultiOpen(true)}
                            size="sm"
                            disabled={row.status === 'SCARTATA'}
                            className="bg-primary text-primary-foreground font-bold hover:bg-primary/90"
                        >
                            <Send className="w-4 h-4 mr-2" />
                            Invia Giocate ({selectedKeys.size})
                        </Button>
                        <Button
                            onClick={() => setSelectedKeys(new Set())}
                            size="sm"
                            variant="ghost"
                            className="text-muted-foreground hover:text-white"
                        >
                            Deseleziona
                        </Button>
                    </>
                ) : (
                    <Button
                        onClick={() => setTradeOpen(true)}
                        size="sm"
                        disabled={row.status === 'SCARTATA'}
                        className="bg-primary text-primary-foreground font-bold hover:bg-primary/90"
                    >
                        <CheckCircle2 className="w-4 h-4 mr-2" />
                        {row.status === 'GIOCATA' ? 'Aggiungi trade' : 'Giocata'}
                    </Button>
                )}
                <Button
                    onClick={() => setRejectOpen(true)}
                    size="sm"
                    variant="outline"
                    disabled={row.status !== 'DA_VALUTARE'}
                    className="border-destructive/40 text-destructive hover:bg-destructive/10"
                >
                    <XCircle className="w-4 h-4 mr-2" /> Scartata
                </Button>
                {/* Elimina: solo da "Da valutare" (snapshot di prova). Le giocate/scartate
                    NON sono eliminabili (P&L e analisi scartate ne dipendono). */}
                {row.status === 'DA_VALUTARE' && (
                    <Button
                        onClick={() => setDelOpen(true)}
                        size="sm"
                        variant="ghost"
                        title="Elimina dalla watchlist"
                        className="ml-auto text-muted-foreground hover:text-red-400 hover:bg-red-400/10"
                    >
                        <Trash2 className="w-4 h-4" />
                    </Button>
                )}
                {isDecided && (
                    <span className="ml-auto text-[10px] text-muted-foreground">
                        Decisa il {fmtKickoff(row.decided_at)}
                    </span>
                )}
            </div>

            <TradeForm open={tradeOpen} onOpenChange={setTradeOpen} row={row} onSaved={handleTradeSaved} />
            <MultiTradeForm
                open={multiOpen}
                onOpenChange={setMultiOpen}
                row={row}
                selections={selectedEdges}
                onSaved={() => { setSelectedKeys(new Set()); handleTradeSaved(); }}
            />
            <RejectDialog open={rejectOpen} onOpenChange={setRejectOpen} row={row} onSaved={onChanged} />
            <DeleteDialog open={delOpen} onOpenChange={setDelOpen} row={row} onSaved={onChanged} />
        </motion.div>
    );
}

// Dialog SCARTATA: motivo (enum §1.5) + nota libera.
function RejectDialog({ open, onOpenChange, row, onSaved }: {
    open: boolean; onOpenChange: (o: boolean) => void; row: WatchlistRow; onSaved?: () => void;
}) {
    const [reason, setReason] = useState<RejectReason>('non_mi_fido');
    const [note, setNote] = useState('');
    const [saving, setSaving] = useState(false);

    const handleReject = async () => {
        setSaving(true);
        try {
            await setWatchlistDecision({
                id: row.id,
                status: 'SCARTATA',
                rejectReason: reason,
                rejectNote: note.trim() || null,
            });
            toast.success('Partita scartata', {
                description: `${row.home_team} vs ${row.away_team} · ${REJECT_REASON_LABELS[reason]}.`,
            });
            setNote('');
            onOpenChange(false);
            onSaved?.();
        } catch (e: any) {
            toast.error('Errore', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="glass-card bg-black/95 border-white/10 backdrop-blur-2xl max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-lg text-white">
                        Scarta partita
                    </DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        {row.home_team} vs {row.away_team}. Il motivo viene tracciato per l'analisi delle scartate.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block">Motivo *</Label>
                        <select className={SELECT_CLS} value={reason} onChange={e => setReason(e.target.value as RejectReason)}>
                            {(Object.keys(REJECT_REASON_LABELS) as RejectReason[]).map(r => (
                                <option key={r} value={r}>{REJECT_REASON_LABELS[r]}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <Label className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block">Nota (opzionale)</Label>
                        <Input value={note} onChange={e => setNote(e.target.value)} placeholder="dettaglio…"
                            className="bg-black/60 border-white/10" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}
                        className="text-muted-foreground hover:text-white">Annulla</Button>
                    <Button onClick={handleReject} disabled={saving}
                        className="bg-destructive text-destructive-foreground font-bold hover:bg-destructive/90">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        Scarta
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// Dialog ELIMINA: conferma rimozione di una partita DA_VALUTARE dalla watchlist.
function DeleteDialog({ open, onOpenChange, row, onSaved }: {
    open: boolean; onOpenChange: (o: boolean) => void; row: WatchlistRow; onSaved?: () => void;
}) {
    const [saving, setSaving] = useState(false);

    const handleDelete = async () => {
        setSaving(true);
        try {
            await deleteFromWatchlist(row.id);
            toast.success('Partita eliminata dalla watchlist', {
                description: `${row.home_team} vs ${row.away_team}.`,
            });
            onOpenChange(false);
            onSaved?.();
        } catch (e: any) {
            toast.error('Errore eliminazione', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="glass-card bg-black/95 border-white/10 backdrop-blur-2xl max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-lg text-white">
                        Elimina partita
                    </DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        {row.home_team} vs {row.away_team}. Rimuove definitivamente lo snapshot dalla watchlist.
                        Consentito solo per le partite “Da valutare” senza trade collegati. Operazione non reversibile.
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}
                        className="text-muted-foreground hover:text-white">Annulla</Button>
                    <Button onClick={handleDelete} disabled={saving}
                        className="bg-destructive text-destructive-foreground font-bold hover:bg-destructive/90">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Trash2 className="w-4 h-4 mr-2" />}
                        Elimina
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export function WatchlistPanel({ rows, loading, onChanged }: Props) {
    if (loading) {
        return (
            <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="glass-card rounded-2xl border border-white/10 h-28 animate-pulse bg-white/[0.02]" />
                ))}
            </div>
        );
    }
    if (!rows.length) {
        return (
            <div className="text-center py-16 glass-card rounded-2xl border border-white/10">
                <Calendar className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-bold font-display text-white mb-1">Nessuna partita in watchlist</h3>
                <p className="text-sm text-muted-foreground">
                    Spunta le partite dalla Dashboard e premi "Aggiungi a Watchlist" per congelarne lo snapshot.
                </p>
            </div>
        );
    }
    return (
        <div className="space-y-3">
            {rows.map(row => <WatchlistCard key={row.id} row={row} onChanged={onChanged} />)}
        </div>
    );
}
