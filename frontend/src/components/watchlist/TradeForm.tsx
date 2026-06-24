// ============================================================================
// TradeForm — Dialog "scheda trade" pre-compilata dallo snapshot watchlist.
// Tutti i campi entry §1.2 + possibilità di aggiungere legs (coperture/hedge/
// cashout/adjust). Al submit chiama addPersonalTrade (RPC §2.4) che congela il
// contesto snapshot e calcola followed_advice; le legs vengono inviate dopo con
// addTradeLeg (RPC §2.5). Design system: Dialog shadcn, glass-card, amber Betfair.
// ============================================================================
import { useMemo, useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Plus, Trash2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import {
    addPersonalTrade, addTradeLeg,
    type AddTradePayload, type AddLegPayload, type TradeSide, type TradeTiming, type LegType,
} from '@/lib/personalReport';
import type { WatchlistRow, SnapshotEdge } from '@/lib/watchlist';

interface Props {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    row: WatchlistRow;
    onSaved?: () => void;
}

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors';
const FIELD_LABEL = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const LEG_TYPE_LABELS: Record<LegType, string> = {
    hedge: 'Hedge',
    cashout: 'Cash-out',
    coverage: 'Copertura',
    adjust: 'Aggiustamento',
};

// Stato locale di una leg in compilazione (prima dell'invio).
interface DraftLeg {
    leg_type: LegType;
    side: TradeSide | '';
    market: string;
    selection: string;
    odds: string;
    stake: string;
    timing: TradeTiming;
    minute: string;
    net_pnl: string;
    note: string;
}

const emptyLeg = (): DraftLeg => ({
    leg_type: 'hedge', side: '', market: '', selection: '', odds: '', stake: '',
    timing: 'live', minute: '', net_pnl: '', note: '',
});

const num = (s: string): number | null => {
    if (s == null || s.trim() === '') return null;
    const v = Number(s);
    return Number.isFinite(v) ? v : null;
};

export function TradeForm({ open, onOpenChange, row, onSaved }: Props) {
    // selezioni consigliate dallo snapshot (per il pre-fill rapido)
    const consigli: SnapshotEdge[] = row.consigli ?? [];

    // ---- campi entry §1.2 ----
    const [strategia, setStrategia] = useState(row.strategia_ipotizzata ?? '');
    const [side, setSide] = useState<TradeSide>('back');
    const [market, setMarket] = useState('');
    const [selection, setSelection] = useState('');
    const [line, setLine] = useState('');
    const [entryOdds, setEntryOdds] = useState('');
    const [stake, setStake] = useState('');
    const [timing, setTiming] = useState<TradeTiming>('prematch');
    const [entryMinute, setEntryMinute] = useState('');
    const [entryScore, setEntryScore] = useState('');
    const [commission, setCommission] = useState('0.05');
    const [comment, setComment] = useState('');

    const [legs, setLegs] = useState<DraftLeg[]>([]);
    const [saving, setSaving] = useState(false);

    // liability calcolata per lay (informativa: la RPC la ricalcola comunque)
    const liability = useMemo(() => {
        const o = num(entryOdds), s = num(stake);
        if (side === 'lay' && o && s && o > 1) return s * (o - 1);
        return null;
    }, [side, entryOdds, stake]);

    // Pre-compila i campi dal consiglio scelto. La quota e il lato devono essere
    // COERENTI: se c'è il back lo uso (lato back), altrimenti ripiego sul lay (lato lay).
    const applyConsiglio = (e: SnapshotEdge) => {
        setMarket(e.market);
        setSelection(e.selection);
        if (e.best_back != null) {
            setSide('back');
            setEntryOdds(String(e.best_back));
        } else if (e.best_lay != null) {
            setSide('lay');
            setEntryOdds(String(e.best_lay));
        }
    };

    const addLeg = () => setLegs(prev => [...prev, emptyLeg()]);
    const removeLeg = (i: number) => setLegs(prev => prev.filter((_, idx) => idx !== i));
    const patchLeg = (i: number, patch: Partial<DraftLeg>) =>
        setLegs(prev => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

    const reset = () => {
        setStrategia(row.strategia_ipotizzata ?? '');
        setSide('back'); setMarket(''); setSelection(''); setLine(''); setEntryOdds('');
        setStake(''); setTiming('prematch'); setEntryMinute(''); setEntryScore('');
        setCommission('0.05'); setComment(''); setLegs([]);
    };

    const handleSubmit = async () => {
        const o = num(entryOdds), s = num(stake);
        if (!strategia.trim()) { toast.error('Inserisci la strategia.'); return; }
        if (o == null || o <= 1) { toast.error('Quota di ingresso non valida (deve essere > 1).'); return; }
        if (s == null || s < 0) { toast.error('Stake non valido.'); return; }

        setSaving(true);
        try {
            const payload: AddTradePayload = {
                watchlist_id: row.id,
                fixture_id: row.fixture_id,
                league_id: row.league_id,
                league_name: row.league_name,
                home_team: row.home_team,
                away_team: row.away_team,
                kickoff: row.kickoff,
                strategia: strategia.trim(),
                side,
                market: market.trim() || null,
                selection: selection.trim() || null,
                line: num(line),
                entry_odds: o,
                stake: s,
                timing,
                entry_minute: num(entryMinute),
                entry_score: entryScore.trim() || null,
                commission: num(commission) ?? 0.05,
                comment: comment.trim() || null,
                tags: row.tags && row.tags.length ? row.tags : null,
            };
            // 1) crea il trade. Se fallisce QUI, nulla è stato salvato → si può ritentare.
            const trade = await addPersonalTrade(payload);

            // 2) invia le legs. Il trade è GIÀ persistito: un fallimento di una leg
            //    NON deve far credere che il trade non esista (evita reinvio duplicato).
            let legFail = 0;
            for (const l of legs) {
                const legPayload: AddLegPayload = {
                    trade_id: trade.id,
                    leg_type: l.leg_type,
                    side: l.side || null,
                    market: l.market.trim() || null,
                    selection: l.selection.trim() || null,
                    odds: num(l.odds),
                    stake: num(l.stake),
                    timing: l.timing,
                    minute: num(l.minute),
                    net_pnl: num(l.net_pnl),
                    note: l.note.trim() || null,
                };
                try {
                    await addTradeLeg(legPayload);
                } catch (le: any) {
                    legFail++;
                    console.error('add_trade_leg', le);
                }
            }

            if (legFail > 0) {
                toast.warning('Trade salvato, ma alcune coperture non registrate', {
                    description: `${legFail}/${legs.length} leg fallite — aggiungile dalla scheda del trade. NON reinviare il trade (sarebbe duplicato).`,
                });
            } else {
                toast.success('Trade registrato', {
                    description: `${row.home_team} vs ${row.away_team} · ${strategia.trim()}${legs.length ? ` · ${legs.length} leg` : ''}.`,
                });
            }
            reset();
            onOpenChange(false);
            onSaved?.();
        } catch (e: any) {
            // solo addPersonalTrade fallito → nessun trade creato, retry sicuro
            toast.error('Errore registrazione trade', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="glass-card bg-black/95 border-white/10 backdrop-blur-2xl max-w-2xl max-h-[92vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-xl text-white">
                        Scheda Trade <span className="text-primary">·</span> {row.home_team} vs {row.away_team}
                    </DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        {row.league_name ?? 'Lega n/d'} · pre-compilata dallo snapshot pre-match. Il contesto (edge,
                        affidabilità, concordi) viene congelato dal sistema per la selezione scelta.
                    </DialogDescription>
                </DialogHeader>

                {/* Consigli rapidi dallo snapshot */}
                {consigli.length > 0 && (
                    <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 px-3 py-3">
                        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-amber-300 font-bold mb-2">
                            <Sparkles className="w-3 h-3" /> Selezioni consigliate (clic per pre-compilare)
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                            {consigli.map((e, i) => (
                                <button
                                    key={`${e.market}-${e.selection}-${i}`}
                                    type="button"
                                    onClick={() => applyConsiglio(e)}
                                    className="px-2.5 py-1 rounded-lg border border-amber-400/30 bg-black/40 text-[11px] text-white/80 hover:bg-amber-400/10 hover:border-amber-400/50 transition-colors"
                                >
                                    <span className="font-bold text-white">{e.market}</span> · {e.selection}{' '}
                                    <span className="font-mono text-amber-300">edge {(e.edge * 100).toFixed(1)}%</span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* ---- campi entry ---- */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <div className="col-span-2 md:col-span-1">
                        <Label className={FIELD_LABEL}>Strategia *</Label>
                        <Input value={strategia} onChange={e => setStrategia(e.target.value)} placeholder="es. Lay the Draw"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Lato *</Label>
                        <select className={SELECT_CLS} value={side} onChange={e => setSide(e.target.value as TradeSide)}>
                            <option value="back">Back (punta)</option>
                            <option value="lay">Lay (banca)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Timing</Label>
                        <select className={SELECT_CLS} value={timing} onChange={e => setTiming(e.target.value as TradeTiming)}>
                            <option value="prematch">Pre-match</option>
                            <option value="live">Live</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Mercato</Label>
                        <Input value={market} onChange={e => setMarket(e.target.value)} placeholder="es. over_2_5"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Selezione</Label>
                        <Input value={selection} onChange={e => setSelection(e.target.value)} placeholder="es. Under"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Linea</Label>
                        <Input type="number" step="0.25" value={line} onChange={e => setLine(e.target.value)} placeholder="es. 2.5"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Quota ingresso *</Label>
                        <Input type="number" step="0.01" min="1.01" value={entryOdds} onChange={e => setEntryOdds(e.target.value)}
                            placeholder="es. 1.85" className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Stake (€) *</Label>
                        <Input type="number" step="0.01" min="0" value={stake} onChange={e => setStake(e.target.value)}
                            placeholder="es. 10" className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Commissione</Label>
                        <Input type="number" step="0.01" min="0" max="1" value={commission} onChange={e => setCommission(e.target.value)}
                            className="bg-black/60 border-white/10" />
                    </div>
                    {timing === 'live' && (
                        <>
                            <div>
                                <Label className={FIELD_LABEL}>Minuto ingresso</Label>
                                <Input type="number" min="0" max="130" value={entryMinute} onChange={e => setEntryMinute(e.target.value)}
                                    placeholder="es. 55" className="bg-black/60 border-white/10" />
                            </div>
                            <div>
                                <Label className={FIELD_LABEL}>Punteggio ingresso</Label>
                                <Input value={entryScore} onChange={e => setEntryScore(e.target.value)} placeholder="es. 1-0"
                                    className="bg-black/60 border-white/10" />
                            </div>
                        </>
                    )}
                    <div className="col-span-2 md:col-span-3">
                        <Label className={FIELD_LABEL}>Nota</Label>
                        <Input value={comment} onChange={e => setComment(e.target.value)} placeholder="commento libero"
                            className="bg-black/60 border-white/10" />
                    </div>
                </div>

                {liability != null && (
                    <p className="text-[11px] text-muted-foreground -mt-1">
                        Responsabilità (lay) stimata: <span className="font-mono text-rose-300">€{liability.toFixed(2)}</span>
                    </p>
                )}

                {/* ---- legs (coperture/hedge) ---- */}
                <div className="border-t border-white/5 pt-3">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                            Coperture / Hedge / Cash-out (opzionali)
                        </span>
                        <Button type="button" variant="ghost" size="sm" onClick={addLeg}
                            className="text-xs text-primary hover:bg-primary/10">
                            <Plus className="w-3 h-3 mr-1" /> Aggiungi leg
                        </Button>
                    </div>

                    <div className="space-y-3">
                        {legs.map((l, i) => (
                            <div key={i} className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-[10px] uppercase font-bold text-white/60">Leg {i + 1}</span>
                                    <button type="button" onClick={() => removeLeg(i)}
                                        className="text-red-400/70 hover:text-red-400" title="Rimuovi leg">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                    <div>
                                        <Label className={FIELD_LABEL}>Tipo</Label>
                                        <select className={SELECT_CLS} value={l.leg_type}
                                            onChange={e => patchLeg(i, { leg_type: e.target.value as LegType })}>
                                            {(Object.keys(LEG_TYPE_LABELS) as LegType[]).map(t => (
                                                <option key={t} value={t}>{LEG_TYPE_LABELS[t]}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <Label className={FIELD_LABEL}>Lato</Label>
                                        <select className={SELECT_CLS} value={l.side}
                                            onChange={e => patchLeg(i, { side: e.target.value as TradeSide | '' })}>
                                            <option value="">—</option>
                                            <option value="back">Back</option>
                                            <option value="lay">Lay</option>
                                        </select>
                                    </div>
                                    <div>
                                        <Label className={FIELD_LABEL}>Quota</Label>
                                        <Input type="number" step="0.01" value={l.odds}
                                            onChange={e => patchLeg(i, { odds: e.target.value })}
                                            className="bg-black/60 border-white/10 h-9" />
                                    </div>
                                    <div>
                                        <Label className={FIELD_LABEL}>Stake (€)</Label>
                                        <Input type="number" step="0.01" value={l.stake}
                                            onChange={e => patchLeg(i, { stake: e.target.value })}
                                            className="bg-black/60 border-white/10 h-9" />
                                    </div>
                                    <div>
                                        <Label className={FIELD_LABEL}>Timing</Label>
                                        <select className={SELECT_CLS} value={l.timing}
                                            onChange={e => patchLeg(i, { timing: e.target.value as TradeTiming })}>
                                            <option value="prematch">Pre-match</option>
                                            <option value="live">Live</option>
                                        </select>
                                    </div>
                                    <div>
                                        <Label className={FIELD_LABEL}>Minuto</Label>
                                        <Input type="number" value={l.minute}
                                            onChange={e => patchLeg(i, { minute: e.target.value })}
                                            className="bg-black/60 border-white/10 h-9" />
                                    </div>
                                    <div>
                                        <Label className={FIELD_LABEL}>P&L netto (€)</Label>
                                        <Input type="number" step="0.01" value={l.net_pnl}
                                            onChange={e => patchLeg(i, { net_pnl: e.target.value })}
                                            placeholder="se noto" className="bg-black/60 border-white/10 h-9" />
                                    </div>
                                    <div className="col-span-2 md:col-span-1">
                                        <Label className={FIELD_LABEL}>Nota</Label>
                                        <Input value={l.note} onChange={e => patchLeg(i, { note: e.target.value })}
                                            className="bg-black/60 border-white/10 h-9" />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <DialogFooter className="mt-2">
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}
                        className="text-muted-foreground hover:text-white">
                        Annulla
                    </Button>
                    <Button onClick={handleSubmit} disabled={saving}
                        className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        Registra Trade
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
