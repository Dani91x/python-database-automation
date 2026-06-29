// ============================================================================
// MultiTradeForm — Scheda Trade MULTIPLA pre-compilata dallo snapshot watchlist.
// Riceve le selezioni spuntate dallo snapshot (1 card per selezione) e, al submit,
// crea UNA GIOCATA SEPARATA per ciascuna (1 selezione = 1 giocata) via
// addPersonalTrade (RPC §2.4) che congela il contesto snapshot (edge, affidabilità,
// motori concordi) abbinando market+selection. Le legs (coperture/hedge/cashout)
// sono opzionali e pre-compilate dal mercato Betfair scelto.
// I SOLI campi che l'utente tocca: lato (back/lay), strategia, stake, nota — il
// resto (timing pre-match, mercato, selezione, linea, quota = ultima aggiornata,
// commissione) è pre-compilato dallo snapshot. Design system: Dialog shadcn,
// glass-card, amber Betfair.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Plus, Trash2, Send } from 'lucide-react';
import { toast } from 'sonner';
import {
    addPersonalTrade, addTradeLeg,
    type AddTradePayload, type AddLegPayload, type TradeSide, type LegType,
} from '@/lib/personalReport';
import type { WatchlistRow, SnapshotEdge } from '@/lib/watchlist';

interface Props {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    row: WatchlistRow;
    selections: SnapshotEdge[];   // selezioni spuntate dallo snapshot (≥1)
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

// chiave stabile di una selezione: market + selection (come nel resto del flusso).
export const edgeKey = (e: { market: string; selection: string }) => `${e.market}|${e.selection}`;

// Linea derivata dalla chiave-mercato (over_1_5 → 1.5, first_half_over_0_5 → 0.5,
// btts/1x2/ht_1x2 → nessuna linea). Gestisce anche linee negative (es. handicap
// -0_5 → -0.5). Solo il PRIMO pattern <segno?cifre>_<cifre>.
const deriveLine = (market: string): number | null => {
    const m = market.match(/(-?\d+)_(\d+)/);
    return m ? Number(`${m[1]}.${m[2]}`) : null;
};

const num = (s: string): number | null => {
    if (s == null || s.trim() === '') return null;
    const v = Number(s);
    return Number.isFinite(v) ? v : null;
};

// Stato locale di una leg in compilazione (pre-invio).
interface LegDraft {
    uid: string;                  // chiave React stabile (immune a rimozioni intermedie)
    leg_type: LegType;
    sourceKey: string;            // edge dello snapshot da cui è pre-compilata ('' = manuale)
    side: TradeSide | '';
    market: string;
    selection: string;
    odds: string;
    stake: string;
    note: string;
}

const emptyLeg = (): LegDraft => ({
    uid: crypto.randomUUID(),
    leg_type: 'hedge', sourceKey: '', side: '', market: '', selection: '', odds: '', stake: '', note: '',
});

// Stato locale di UNA selezione/giocata in compilazione. Il "contesto congelato"
// (model_prob, edge, affidabilità, concordi/motori) è informativo: la RPC lo
// ri-congela lato server abbinando market+selection allo snapshot.
interface SelDraft {
    key: string;
    market: string;
    selection: string;
    line: number | null;
    // contesto (display-only)
    model_prob: number | null;
    edge: number;
    affidabilita: number | null;
    concordi: number;
    motori_totali: number;
    best_back: number | null;
    best_lay: number | null;
    // editabili dall'utente
    side: TradeSide;
    entryOdds: string;
    stake: string;
    strategia: string;
    comment: string;
    legs: LegDraft[];
}

const buildDraft = (row: WatchlistRow, e: SnapshotEdge): SelDraft => {
    // lato coerente con la quota disponibile: se c'è il back lo uso (punta),
    // altrimenti ripiego sul lay (banca).
    const defaultSide: TradeSide = e.best_back != null ? 'back' : e.best_lay != null ? 'lay' : 'back';
    const odds = defaultSide === 'back' ? e.best_back : e.best_lay;
    return {
        key: edgeKey(e),
        market: e.market,
        selection: e.selection,
        line: deriveLine(e.market),
        model_prob: e.model_prob,
        edge: e.edge,
        affidabilita: e.affidabilita,
        concordi: e.concordi?.length ?? 0,
        motori_totali: e.motori_totali,
        best_back: e.best_back,
        best_lay: e.best_lay,
        side: defaultSide,
        entryOdds: odds != null ? String(odds) : '',
        stake: '',
        strategia: row.strategia_ipotizzata ?? '',
        comment: '',
        legs: [],
    };
};

const fmtPct = (v: number | null | undefined, d = 1) =>
    v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`;

export function MultiTradeForm({ open, onOpenChange, row, selections, onSaved }: Props) {
    const [drafts, setDrafts] = useState<SelDraft[]>([]);
    const [saving, setSaving] = useState(false);

    // tutti gli edge dello snapshot: sorgente per la pre-compilazione delle legs.
    const allEdges = row.snapshot?.edges ?? [];

    // Costruisci i draft SOLO alla transizione chiuso→aperto del dialog. Reagire a
    // `selections`/`row` (reference instabili: memo su selectedKeys, realtime sulle
    // righe) resetterebbe ciò che l'utente sta compilando. Lo snapshot all'apertura
    // basta: le selezioni non cambiano mentre il modal copre la card.
    const prevOpenRef = useRef(false);
    useEffect(() => {
        if (open && !prevOpenRef.current) {
            setDrafts(selections.map(e => buildDraft(row, e)));
        }
        prevOpenRef.current = open;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const patch = (key: string, p: Partial<SelDraft>) =>
        setDrafts(prev => prev.map(d => (d.key === key ? { ...d, ...p } : d)));

    // cambio lato: aggiorna la quota all'ultima disponibile per quel lato.
    const setSide = (key: string, side: TradeSide) =>
        setDrafts(prev => prev.map(d => {
            if (d.key !== key) return d;
            const odds = side === 'back' ? d.best_back : d.best_lay;
            return { ...d, side, entryOdds: odds != null ? String(odds) : d.entryOdds };
        }));

    const addLeg = (selKey: string) =>
        setDrafts(prev => prev.map(d => (d.key === selKey ? { ...d, legs: [...d.legs, emptyLeg()] } : d)));
    const removeLeg = (selKey: string, i: number) =>
        setDrafts(prev => prev.map(d => (d.key === selKey ? { ...d, legs: d.legs.filter((_, idx) => idx !== i) } : d)));
    const patchLeg = (selKey: string, i: number, p: Partial<LegDraft>) =>
        setDrafts(prev => prev.map(d => (d.key === selKey
            ? { ...d, legs: d.legs.map((l, idx) => (idx === i ? { ...l, ...p } : l)) }
            : d)));

    // pre-compila una leg dal mercato Betfair scelto (lato/quota coerenti).
    const applyLegSource = (selKey: string, i: number, sourceKey: string) => {
        if (!sourceKey) {
            patchLeg(selKey, i, { sourceKey: '', market: '', selection: '', odds: '', side: '' });
            return;
        }
        const e = allEdges.find(x => edgeKey(x) === sourceKey);
        if (!e) return;
        const side: TradeSide = e.best_back != null ? 'back' : 'lay';
        const odds = side === 'back' ? e.best_back : e.best_lay;
        patchLeg(selKey, i, {
            sourceKey,
            market: e.market,
            selection: e.selection,
            side,
            odds: odds != null ? String(odds) : '',
        });
    };

    const handleSubmit = async () => {
        if (drafts.length === 0) { toast.error('Nessuna selezione da inviare.'); return; }

        // 1) VALIDA TUTTO prima di scrivere: niente invio parziale per errore di input.
        for (const d of drafts) {
            const label = `${d.market} · ${d.selection}`;
            if (!d.strategia.trim()) { toast.error(`Strategia mancante per ${label}.`); return; }
            const o = num(d.entryOdds), s = num(d.stake);
            if (o == null || o <= 1) { toast.error(`Quota non valida per ${label} (deve essere > 1).`); return; }
            if (s == null || s < 0) { toast.error(`Stake non valido per ${label}.`); return; }
        }

        setSaving(true);
        let ok = 0, legFail = 0;
        const failed: string[] = [];
        // 2) Una GIOCATA per selezione (1 selezione = 1 giocata). Sequenziale: ogni
        //    trade è indipendente; un fallimento non annulla i precedenti (già scritti).
        //    try/finally garantisce sempre il reset di `saving` (no spinner bloccato).
        try {
          for (const d of drafts) {
            const o = num(d.entryOdds) as number, s = num(d.stake) as number;
            try {
                const payload: AddTradePayload = {
                    watchlist_id: row.id,
                    fixture_id: row.fixture_id,
                    league_id: row.league_id,
                    league_name: row.league_name,
                    home_team: row.home_team,
                    away_team: row.away_team,
                    kickoff: row.kickoff,
                    strategia: d.strategia.trim(),
                    side: d.side,
                    market: d.market,         // ESATTO come snapshot → la RPC congela il contesto
                    selection: d.selection,
                    line: d.line,
                    entry_odds: o,
                    stake: s,
                    timing: 'prematch',
                    commission: 0.05,
                    comment: d.comment.trim() || null,
                    // vedi nota in TradeForm: NON inviare null nel jsonb (chiave omessa = SQL NULL)
                    tags: row.tags && row.tags.length ? row.tags : undefined,
                };
                const trade = await addPersonalTrade(payload);
                ok++;

                // legs: salta quelle del tutto vuote; invia le compilate.
                for (const l of d.legs) {
                    const hasContent = l.market.trim() || num(l.odds) != null || num(l.stake) != null;
                    if (!hasContent) continue;
                    const legPayload: AddLegPayload = {
                        trade_id: trade.id,
                        leg_type: l.leg_type,
                        side: l.side || null,
                        market: l.market.trim() || null,
                        selection: l.selection.trim() || null,
                        odds: num(l.odds),
                        stake: num(l.stake),
                        timing: 'live',          // le coperture sono tipicamente in-play
                        minute: null,
                        net_pnl: null,
                        note: l.note.trim() || null,
                    };
                    try {
                        await addTradeLeg(legPayload);
                    } catch (le: unknown) {
                        legFail++;
                        console.error('add_trade_leg', le);
                    }
                }
            } catch (e: unknown) {
                failed.push(`${d.market} · ${d.selection}`);
                console.error('add_personal_trade', e);
            }
          }
        } catch (unexpected: unknown) {
            // imprevisto fuori dai catch interni: NON chiudo il dialog (l'utente
            // valuta cosa è stato scritto) e segnalo dove controllare.
            console.error('invia giocate (inatteso)', unexpected);
            toast.error("Errore inaspettato durante l'invio", {
                description: 'Controlla le giocate nel Report Personale prima di reinviarle.',
            });
            return;
        } finally {
            setSaving(false);
        }

        if (failed.length === 0) {
            toast.success(`${ok} giocat${ok === 1 ? 'a inviata' : 'e inviate'}`, {
                description: `${row.home_team} vs ${row.away_team}${legFail ? ` · ${legFail} leg non registrate` : ''}.`,
            });
        } else {
            toast.warning(`${ok} inviate, ${failed.length} fallite`, {
                description: `Fallite: ${failed.join(', ')}. Le inviate sono salvate — NON reinviarle (sarebbero duplicate).`,
            });
        }
        // chiudo e ricarico: le giocate riuscite spariscono dalla selezione al refresh.
        onOpenChange(false);
        onSaved?.();
    };

    return (
        <Dialog open={open} onOpenChange={(o) => { if (!saving) onOpenChange(o); }}>
            <DialogContent className="glass-card bg-black/95 border-white/10 backdrop-blur-2xl max-w-3xl max-h-[92vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-xl text-white">
                        Scheda Trade <span className="text-primary">·</span> {row.home_team} vs {row.away_team}
                    </DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        {row.league_name ?? 'Lega n/d'} · pre-compilata dallo snapshot pre-match. Il contesto (edge,
                        affidabilità, concordi) viene congelato dal sistema per ogni selezione scelta.
                        {' '}1 selezione = 1 giocata.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-3">
                    {drafts.map(d => (
                        <div key={d.key} className="rounded-xl border border-primary/20 bg-white/[0.02] p-3">
                            {/* intestazione selezione + contesto congelato (read-only) */}
                            <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                                <div className="font-bold text-white text-sm">
                                    {d.market} <span className="text-white/50 font-normal">· {d.selection}</span>
                                    {d.line != null && <span className="text-white/40 font-normal"> · linea {d.line}</span>}
                                </div>
                                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                                    <span>prob <span className="font-mono text-white">{fmtPct(d.model_prob, 0)}</span></span>
                                    <span>edge <span className={`font-mono ${d.edge >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{d.edge >= 0 ? '+' : ''}{fmtPct(d.edge, 1)}</span></span>
                                    {d.affidabilita != null && <span>affid. <span className="font-mono text-white">{fmtPct(d.affidabilita, 0)}</span></span>}
                                    <span>motori <span className="font-mono text-white">{d.concordi}/{d.motori_totali}</span></span>
                                </div>
                            </div>

                            {/* campi editabili (+ quota pre-compilata) */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                <div className="col-span-2 md:col-span-2">
                                    <Label className={FIELD_LABEL}>Strategia *</Label>
                                    <Input value={d.strategia} onChange={e => patch(d.key, { strategia: e.target.value })}
                                        placeholder="es. Lay the Draw" className="bg-black/60 border-white/10 h-9" />
                                </div>
                                <div>
                                    <Label className={FIELD_LABEL}>Lato *</Label>
                                    <select className={SELECT_CLS} value={d.side}
                                        onChange={e => setSide(d.key, e.target.value as TradeSide)}>
                                        <option value="back">Back (punta)</option>
                                        <option value="lay">Lay (banca)</option>
                                    </select>
                                </div>
                                <div>
                                    <Label className={FIELD_LABEL}>Quota ingresso *</Label>
                                    <Input type="number" step="0.01" min="1.01" value={d.entryOdds}
                                        onChange={e => patch(d.key, { entryOdds: e.target.value })}
                                        placeholder="es. 1.85" className="bg-black/60 border-white/10 h-9" />
                                </div>
                                <div>
                                    <Label className={FIELD_LABEL}>Stake (€) *</Label>
                                    <Input type="number" step="0.01" min="0" value={d.stake}
                                        onChange={e => patch(d.key, { stake: e.target.value })}
                                        placeholder="es. 10" className="bg-black/60 border-white/10 h-9" />
                                </div>
                                <div className="col-span-2 md:col-span-3">
                                    <Label className={FIELD_LABEL}>Nota</Label>
                                    <Input value={d.comment} onChange={e => patch(d.key, { comment: e.target.value })}
                                        placeholder="commento libero" className="bg-black/60 border-white/10 h-9" />
                                </div>
                            </div>

                            {/* legs (coperture/hedge/cashout) opzionali, pre-compilate dal mercato scelto */}
                            <div className="mt-2 pt-2 border-t border-white/5">
                                <div className="flex items-center justify-between mb-1.5">
                                    <span className="text-[9px] uppercase tracking-widest text-muted-foreground font-bold">
                                        Coperture / Hedge / Cash-out (opzionali)
                                    </span>
                                    <Button type="button" variant="ghost" size="sm" onClick={() => addLeg(d.key)}
                                        className="text-[11px] h-7 text-primary hover:bg-primary/10">
                                        <Plus className="w-3 h-3 mr-1" /> Aggiungi leg
                                    </Button>
                                </div>
                                <div className="space-y-2">
                                    {d.legs.map((l, i) => (
                                        <div key={l.uid} className="rounded-lg border border-white/10 bg-black/30 p-2">
                                            <div className="flex items-center justify-between mb-1.5">
                                                <span className="text-[9px] uppercase font-bold text-white/50">Leg {i + 1}</span>
                                                <button type="button" onClick={() => removeLeg(d.key, i)}
                                                    className="text-red-400/70 hover:text-red-400" title="Rimuovi leg"
                                                    aria-label={`Rimuovi leg ${i + 1}`}>
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                                <div>
                                                    <Label className={FIELD_LABEL}>Tipo</Label>
                                                    <select className={SELECT_CLS} value={l.leg_type}
                                                        onChange={e => patchLeg(d.key, i, { leg_type: e.target.value as LegType })}>
                                                        {(Object.keys(LEG_TYPE_LABELS) as LegType[]).map(t => (
                                                            <option key={t} value={t}>{LEG_TYPE_LABELS[t]}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                                <div className="col-span-2 md:col-span-1">
                                                    <Label className={FIELD_LABEL}>Mercato (da snapshot)</Label>
                                                    <select className={SELECT_CLS} value={l.sourceKey}
                                                        onChange={e => applyLegSource(d.key, i, e.target.value)}>
                                                        <option value="">— scegli —</option>
                                                        {allEdges.map((e, idx) => (
                                                            <option key={`${edgeKey(e)}-${idx}`} value={edgeKey(e)}>
                                                                {e.market} · {e.selection}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </div>
                                                <div>
                                                    <Label className={FIELD_LABEL}>Lato</Label>
                                                    <select className={SELECT_CLS} value={l.side}
                                                        onChange={e => patchLeg(d.key, i, { side: e.target.value as TradeSide | '' })}>
                                                        <option value="">—</option>
                                                        <option value="back">Back</option>
                                                        <option value="lay">Lay</option>
                                                    </select>
                                                </div>
                                                <div>
                                                    <Label className={FIELD_LABEL}>Quota</Label>
                                                    <Input type="number" step="0.01" value={l.odds}
                                                        onChange={e => patchLeg(d.key, i, { odds: e.target.value })}
                                                        className="bg-black/60 border-white/10 h-9" />
                                                </div>
                                                <div>
                                                    <Label className={FIELD_LABEL}>Stake (€)</Label>
                                                    <Input type="number" step="0.01" value={l.stake}
                                                        onChange={e => patchLeg(d.key, i, { stake: e.target.value })}
                                                        className="bg-black/60 border-white/10 h-9" />
                                                </div>
                                                <div className="col-span-2 md:col-span-3">
                                                    <Label className={FIELD_LABEL}>Nota</Label>
                                                    <Input value={l.note} onChange={e => patchLeg(d.key, i, { note: e.target.value })}
                                                        className="bg-black/60 border-white/10 h-9" />
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                <DialogFooter className="mt-2">
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}
                        className="text-muted-foreground hover:text-white">
                        Annulla
                    </Button>
                    <Button onClick={handleSubmit} disabled={saving || drafts.length === 0}
                        className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                        Invia Giocate{drafts.length ? ` (${drafts.length})` : ''}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
