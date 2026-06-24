// ============================================================================
// WatchlistPanel — lista di card snapshot pre-match (1 per partita in watchlist).
// Mostra: identità match, badge stato, le selezioni dello snapshot (edges) con i
// CONSIGLI evidenziati (model_prob, back/lay Betfair, edge, affidabilità,
// concordi/motori), e le azioni GIOCATA (apre TradeForm) / SCARTATA (Dialog con
// motivo dall'enum §1.5). Tutto lo snapshot è server-side e immutabile.
// Design system: glass-card, badge a colori, emerald positivo / amber Betfair /
// red negativo, framer-motion, sonner.
// ============================================================================
import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
    Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp, Calendar, Trophy, Sparkles,
} from 'lucide-react';
import { toast } from 'sonner';
import {
    setWatchlistDecision, REJECT_REASON_LABELS,
    type WatchlistRow, type RejectReason, type SnapshotEdge, type WatchlistStatus,
} from '@/lib/watchlist';
import { TradeForm } from '@/components/watchlist/TradeForm';

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
function EdgeRow({ e, recommended }: { e: SnapshotEdge; recommended: boolean }) {
    const edgeColor = e.edge > 0.02 ? 'text-emerald-400' : e.edge > 0 ? 'text-amber-400' : 'text-red-400';
    return (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[11px] ${recommended
            ? 'bg-amber-400/5 border-amber-400/30'
            : 'bg-white/[0.02] border-white/10'}`}>
            {recommended && <Sparkles className="w-3 h-3 text-amber-300 shrink-0" />}
            <div className="min-w-0 flex-1">
                <span className="font-bold text-white">{e.market}</span>
                <span className="text-white/60"> · {e.selection}</span>
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
    const [expanded, setExpanded] = useState(false);
    const [tradeOpen, setTradeOpen] = useState(false);
    const [rejectOpen, setRejectOpen] = useState(false);

    // set delle selezioni consigliate (per evidenziare le righe edges)
    const consigliKeys = useMemo(() => {
        const s = new Set<string>();
        (row.consigli ?? []).forEach(c => s.add(`${c.market}|${c.selection}`));
        return s;
    }, [row.consigli]);

    const edges = row.snapshot?.edges ?? [];
    const isDecided = row.status !== 'DA_VALUTARE';

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
                                    <EdgeRow key={`${e.market}-${e.selection}-${i}`} e={e}
                                        recommended={consigliKeys.has(`${e.market}|${e.selection}`)} />
                                ))}
                            </div>
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
                <Button
                    onClick={() => setTradeOpen(true)}
                    size="sm"
                    disabled={row.status === 'SCARTATA'}
                    className="bg-primary text-primary-foreground font-bold hover:bg-primary/90"
                >
                    <CheckCircle2 className="w-4 h-4 mr-2" />
                    {row.status === 'GIOCATA' ? 'Aggiungi trade' : 'Giocata'}
                </Button>
                <Button
                    onClick={() => setRejectOpen(true)}
                    size="sm"
                    variant="outline"
                    disabled={row.status !== 'DA_VALUTARE'}
                    className="border-destructive/40 text-destructive hover:bg-destructive/10"
                >
                    <XCircle className="w-4 h-4 mr-2" /> Scartata
                </Button>
                {isDecided && (
                    <span className="ml-auto text-[10px] text-muted-foreground">
                        Decisa il {fmtKickoff(row.decided_at)}
                    </span>
                )}
            </div>

            <TradeForm open={tradeOpen} onOpenChange={setTradeOpen} row={row} onSaved={onChanged} />
            <RejectDialog open={rejectOpen} onOpenChange={setRejectOpen} row={row} onSaved={onChanged} />
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
