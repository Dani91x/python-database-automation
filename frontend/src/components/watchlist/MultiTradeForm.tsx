// ============================================================================
// MultiTradeForm — Scheda Trade MULTIPLA che PIAZZA ORDINI REALI su Betfair.
// Riceve le selezioni spuntate dallo snapshot (1 card per selezione). Order-ticket
// in stile software pro (Bet Angel): lato Back/Lay, quota, stake o responsabilità,
// persistenza a inizio live (Cancel/Keep/Take SP), Fill-or-Kill. Flusso in 3 fasi:
//   1) EDIT     — compili gli ordini.
//   2) CONFIRM  — riepilogo + cap massimo stake (digitato da te) + conferma esplicita.
//   3) RESULTS  — esito reale per ordine (betId, abbinato, runner) o errore.
// Solo gli ordini effettivamente piazzati (matched o resting con betId) vengono
// registrati in personal_trades con i DATI REALI di esecuzione (1 selezione = 1
// giocata). Le legs sono RECORD di copertura (non ordini), allegate alla giocata.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Plus, Trash2, Send, ShieldAlert, CheckCircle2, XCircle, ChevronLeft } from 'lucide-react';
import { toast } from 'sonner';
import {
    addPersonalTrade, addTradeLeg,
    type AddTradePayload, type AddLegPayload, type TradeSide, type LegType,
} from '@/lib/personalReport';
import { placeBetfairOrder, type PlaceOrderPayload, type PlaceOrderResult } from '@/lib/betfair';
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

type Persistence = 'LAPSE' | 'PERSIST' | 'MARKET_ON_CLOSE';
const PERSISTENCE_LABELS: Record<Persistence, string> = {
    LAPSE: 'Cancel (annulla a inizio live)',
    PERSIST: 'Keep (mantieni a inizio live)',
    MARKET_ON_CLOSE: 'Take SP (prezzo di partenza)',
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

// Stato locale di UNA selezione/giocata. Il "contesto congelato" (model_prob, edge,
// affidabilità, concordi/motori) è informativo: la RPC lo ri-congela lato server.
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
    // order-ticket
    side: TradeSide;
    entryOdds: string;
    stakeMode: 'stake' | 'liability';
    stake: string;
    liability: string;
    persistence: Persistence;
    fillOrKill: boolean;
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
        stakeMode: 'stake',
        stake: '',
        liability: '',
        persistence: 'LAPSE',
        fillOrKill: false,
        strategia: row.strategia_ipotizzata ?? '',
        comment: '',
        legs: [],
    };
};

const fmtPct = (v: number | null | undefined, d = 1) =>
    v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`;

// Stake effettivo dell'ordine: diretto ('stake') o derivato dalla liability ('lay').
const computeSize = (d: SelDraft): number | null => {
    const price = num(d.entryOdds);
    if (d.stakeMode === 'liability') {
        const liab = num(d.liability);
        if (liab == null || liab <= 0 || price == null || price <= 1) return null;
        return Math.round((liab / (price - 1)) * 100) / 100;
    }
    return num(d.stake);
};

// Esito d'esecuzione mostrato nella fase RESULTS.
interface OrderOutcome {
    label: string;
    ok: boolean;
    placed: boolean;
    recorded: boolean;
    betId?: string | null;
    orderStatus?: string | null;
    sizeMatched?: number;
    avgPrice?: number | null;
    runner?: string | null;
    error?: string;
}

type Stage = 'edit' | 'confirm' | 'results';

export function MultiTradeForm({ open, onOpenChange, row, selections, onSaved }: Props) {
    const [drafts, setDrafts] = useState<SelDraft[]>([]);
    const [stage, setStage] = useState<Stage>('edit');
    const [placing, setPlacing] = useState(false);
    const [capStr, setCapStr] = useState('');
    const [results, setResults] = useState<OrderOutcome[]>([]);

    // tutti gli edge dello snapshot: sorgente per la pre-compilazione delle legs.
    const allEdges = row.snapshot?.edges ?? [];

    // Costruisci i draft SOLO alla transizione chiuso→aperto del dialog. Reagire a
    // `selections`/`row` (reference instabili) resetterebbe ciò che l'utente compila.
    const prevOpenRef = useRef(false);
    useEffect(() => {
        if (open && !prevOpenRef.current) {
            setDrafts(selections.map(e => buildDraft(row, e)));
            setStage('edit');
            setResults([]);
            setCapStr('');
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

    // EDIT → CONFIRM: valida tutto (niente piazzamento se l'input è incompleto).
    const goToConfirm = () => {
        if (drafts.length === 0) { toast.error('Nessuna selezione da piazzare.'); return; }
        for (const d of drafts) {
            const label = `${d.market} · ${d.selection}`;
            if (!d.strategia.trim()) { toast.error(`Strategia mancante per ${label}.`); return; }
            const o = num(d.entryOdds);
            if (o == null || o <= 1) { toast.error(`Quota non valida per ${label} (> 1).`); return; }
            const sz = computeSize(d);
            if (sz == null || sz < 2) { toast.error(`Stake di ${label} sotto il minimo Betfair (€2).`); return; }
        }
        setStage('confirm');
    };

    const totalStake = drafts.reduce((acc, d) => acc + (computeSize(d) ?? 0), 0);

    // CONFIRM → piazza gli ordini REALI, poi registra solo quelli effettivamente piazzati.
    const handlePlace = async () => {
        const cap = num(capStr);
        if (cap == null || cap <= 0) { toast.error('Inserisci un cap massimo per ordine (> 0).'); return; }
        for (const d of drafts) {
            const sz = computeSize(d) ?? 0;
            if (sz > cap + 1e-9) {
                toast.error(`Stake €${sz.toFixed(2)} di ${d.market} · ${d.selection} supera il cap €${cap.toFixed(2)}.`);
                return;
            }
        }

        setPlacing(true);
        const out: OrderOutcome[] = [];
        try {
            for (const d of drafts) {
                const label = `${d.market} · ${d.selection}`;
                const price = num(d.entryOdds) as number;
                const orderPayload: PlaceOrderPayload = {
                    fixture_id: row.fixture_id,
                    market: d.market,
                    selection: d.selection,
                    side: d.side,
                    price,
                    size: d.stakeMode === 'stake' ? num(d.stake) : null,
                    liability: d.stakeMode === 'liability' ? num(d.liability) : null,
                    persistence: d.persistence,
                    fill_or_kill: d.fillOrKill,
                    max_stake: cap,
                };

                let res: PlaceOrderResult;
                try {
                    res = await placeBetfairOrder(orderPayload);
                } catch (e: unknown) {
                    out.push({ label, ok: false, placed: false, recorded: false,
                        error: e instanceof Error ? e.message : 'errore sconosciuto' });
                    continue;
                }

                const matched = Number(res.size_matched) || 0;
                // "piazzato" = c'è un betId e o è stato abbinato qualcosa o l'ordine
                // resta sul book (EXECUTABLE). FoK non riempito / FAILURE → NON registro.
                const placed = !!res.bet_id && res.ok && (matched > 0 || res.order_status === 'EXECUTABLE');

                let recorded = false;
                if (placed) {
                    const entryOdds = matched > 0 && res.average_price_matched
                        ? Number(res.average_price_matched)
                        : Number(res.price ?? price);
                    const recordStake = matched > 0 ? matched : Number(res.size ?? num(d.stake) ?? computeSize(d) ?? 0);
                    const execNote = `[Betfair] betId=${res.bet_id} ${res.order_status ?? ''} abbinato €${matched.toFixed(2)}`
                        + `${res.average_price_matched ? `@${Number(res.average_price_matched).toFixed(2)}` : ''}`
                        + ` ${res.persistence ?? d.persistence}${res.fill_or_kill ? ' FoK' : ''}`;
                    const comment = [d.comment.trim(), execNote].filter(Boolean).join(' · ');
                    try {
                        const trade = await addPersonalTrade({
                            watchlist_id: row.id,
                            fixture_id: row.fixture_id,
                            league_id: row.league_id,
                            league_name: row.league_name,
                            home_team: row.home_team,
                            away_team: row.away_team,
                            kickoff: row.kickoff,
                            strategia: d.strategia.trim(),
                            side: d.side,
                            market: d.market,        // ESATTO come snapshot → la RPC congela il contesto
                            selection: d.selection,
                            line: d.line,
                            entry_odds: entryOdds,
                            stake: recordStake,
                            timing: 'prematch',
                            commission: 0.05,
                            comment,
                            tags: row.tags && row.tags.length ? row.tags : undefined,
                        } as AddTradePayload);
                        recorded = true;

                        // legs (record di copertura, non ordini piazzati)
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
                                timing: 'live',
                                minute: null,
                                net_pnl: null,
                                note: l.note.trim() || null,
                            };
                            try {
                                await addTradeLeg(legPayload);
                            } catch (le: unknown) {
                                console.error('add_trade_leg', le);
                            }
                        }
                    } catch (re: unknown) {
                        // soldi REALI già impegnati ma record fallito: avviso PROMINENTE
                        // (oltre all'indicatore ambra nei risultati) per non perderlo.
                        console.error('add_personal_trade (post-piazzamento)', re);
                        toast.error('Ordine piazzato ma NON registrato', {
                            description: `betId ${res.bet_id}: annotalo a mano nel Report. ${re instanceof Error ? re.message : ''}`.trim(),
                        });
                    }
                }

                out.push({
                    label,
                    ok: !!res.ok,
                    placed,
                    recorded,
                    betId: res.bet_id,
                    orderStatus: res.order_status,
                    sizeMatched: matched,
                    avgPrice: res.average_price_matched ?? null,
                    runner: res.runner ?? null,
                    error: res.ok ? undefined : (res.error || res.error_code || 'ordine non piazzato'),
                });
            }
        } finally {
            setPlacing(false);
        }

        setResults(out);
        setStage('results');
        // se almeno un ordine è stato registrato, ricarica watchlist/report.
        if (out.some(o => o.recorded)) onSaved?.();
    };

    const closeDialog = () => { if (!placing) onOpenChange(false); };

    return (
        <Dialog open={open} onOpenChange={(o) => { if (!placing) onOpenChange(o); }}>
            <DialogContent className="glass-card bg-black/95 border-white/10 backdrop-blur-2xl max-w-3xl max-h-[92vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-xl text-white">
                        Scheda Trade <span className="text-primary">·</span> {row.home_team} vs {row.away_team}
                    </DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        {row.league_name ?? 'Lega n/d'} · {stage === 'edit'
                            ? 'order-ticket pre-compilato dallo snapshot. Gli ordini diventano operazioni REALI su Betfair.'
                            : stage === 'confirm'
                                ? 'Conferma: stai per piazzare ordini REALI con soldi veri.'
                                : 'Esito del piazzamento.'}
                    </DialogDescription>
                </DialogHeader>

                {/* ---------- FASE EDIT ---------- */}
                {stage === 'edit' && (
                    <div className="space-y-3">
                        {drafts.map(d => (
                            <div key={d.key} className="rounded-xl border border-primary/20 bg-white/[0.02] p-3">
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

                                {/* riga 1: strategia / lato / quota */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                    <div className="col-span-2">
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
                                        <Label className={FIELD_LABEL}>Quota *</Label>
                                        <Input type="number" step="0.01" min="1.01" value={d.entryOdds}
                                            onChange={e => patch(d.key, { entryOdds: e.target.value })}
                                            placeholder="es. 1.85" className="bg-black/60 border-white/10 h-9" />
                                    </div>
                                </div>

                                {/* riga 2: stake/responsabilità + persistenza + FoK */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
                                    <div>
                                        <Label className={FIELD_LABEL}>Importo</Label>
                                        <select className={SELECT_CLS} value={d.stakeMode}
                                            onChange={e => patch(d.key, { stakeMode: e.target.value as 'stake' | 'liability' })}>
                                            <option value="stake">Stake (€)</option>
                                            <option value="liability" disabled={d.side !== 'lay'}>Responsabilità (lay)</option>
                                        </select>
                                    </div>
                                    {d.stakeMode === 'stake' ? (
                                        <div>
                                            <Label className={FIELD_LABEL}>Stake (€) *</Label>
                                            <Input type="number" step="0.01" min="2" value={d.stake}
                                                onChange={e => patch(d.key, { stake: e.target.value })}
                                                placeholder="min 2" className="bg-black/60 border-white/10 h-9" />
                                        </div>
                                    ) : (
                                        <div>
                                            <Label className={FIELD_LABEL}>Responsabilità (€) *</Label>
                                            <Input type="number" step="0.01" min="0" value={d.liability}
                                                onChange={e => patch(d.key, { liability: e.target.value })}
                                                placeholder="es. 10" className="bg-black/60 border-white/10 h-9" />
                                        </div>
                                    )}
                                    <div>
                                        <Label className={FIELD_LABEL}>A inizio live</Label>
                                        {/* FoK sovrascrive la persistenza lato Betfair → bloccata su Cancel (LAPSE) */}
                                        <select className={SELECT_CLS} value={d.persistence} disabled={d.fillOrKill}
                                            title={d.fillOrKill ? 'Con Fill or Kill la persistenza è forzata a Cancel' : undefined}
                                            onChange={e => patch(d.key, { persistence: e.target.value as Persistence })}>
                                            {(Object.keys(PERSISTENCE_LABELS) as Persistence[]).map(p => (
                                                <option key={p} value={p}>{PERSISTENCE_LABELS[p]}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="flex items-end pb-1">
                                        <label className="flex items-center gap-2 text-[11px] text-white/80 cursor-pointer">
                                            <input type="checkbox" checked={d.fillOrKill}
                                                onChange={e => patch(d.key, e.target.checked
                                                    ? { fillOrKill: true, persistence: 'LAPSE' }
                                                    : { fillOrKill: false })}
                                                className="accent-primary w-4 h-4" />
                                            Fill or Kill
                                        </label>
                                    </div>
                                </div>

                                {/* riepilogo importo derivato */}
                                <p className="text-[10px] text-muted-foreground mt-1.5">
                                    Stake effettivo: <span className="font-mono text-white">€{(computeSize(d) ?? 0).toFixed(2)}</span>
                                    {d.side === 'lay' && computeSize(d) != null && num(d.entryOdds) != null && (
                                        <> · responsabilità <span className="font-mono text-rose-300">€{((computeSize(d) as number) * ((num(d.entryOdds) as number) - 1)).toFixed(2)}</span></>
                                    )}
                                </p>

                                <div className="mt-2">
                                    <Label className={FIELD_LABEL}>Nota</Label>
                                    <Input value={d.comment} onChange={e => patch(d.key, { comment: e.target.value })}
                                        placeholder="commento libero" className="bg-black/60 border-white/10 h-9" />
                                </div>

                                {/* legs (record di copertura, non ordini) */}
                                <div className="mt-2 pt-2 border-t border-white/5">
                                    <div className="flex items-center justify-between mb-1.5">
                                        <span className="text-[9px] uppercase tracking-widest text-muted-foreground font-bold">
                                            Coperture / Hedge / Cash-out (record, non piazzate)
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
                )}

                {/* ---------- FASE CONFIRM ---------- */}
                {stage === 'confirm' && (
                    <div className="space-y-3">
                        <div className="rounded-xl border border-amber-400/40 bg-amber-400/10 p-3 flex items-start gap-2">
                            <ShieldAlert className="w-5 h-5 text-amber-300 shrink-0 mt-0.5" />
                            <div className="text-[12px] text-amber-100">
                                Stai per piazzare <span className="font-bold">{drafts.length} ordine{drafts.length > 1 ? 'i' : ''} REALE{drafts.length > 1 ? 'I' : ''}</span> su
                                Betfair con soldi veri, per un totale stake di <span className="font-mono font-bold">€{totalStake.toFixed(2)}</span>.
                                Controlla ogni riga: partita, mercato, selezione, lato, quota e importo.
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            {drafts.map(d => {
                                const sz = computeSize(d) ?? 0;
                                const price = num(d.entryOdds) ?? 0;
                                return (
                                    <div key={d.key} className="rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-[12px]">
                                        <div className="flex items-center justify-between gap-2 flex-wrap">
                                            <span className="font-bold text-white">
                                                {d.market} <span className="text-white/50 font-normal">· {d.selection}</span>
                                            </span>
                                            <span className={`font-mono uppercase text-[11px] ${d.side === 'back' ? 'text-sky-300' : 'text-rose-300'}`}>
                                                {d.side}
                                            </span>
                                        </div>
                                        <div className="text-[11px] text-muted-foreground mt-0.5 flex flex-wrap gap-x-3">
                                            <span>quota <span className="font-mono text-white">{price.toFixed(2)}</span></span>
                                            <span>stake <span className="font-mono text-white">€{sz.toFixed(2)}</span></span>
                                            {d.side === 'lay' && <span>resp. <span className="font-mono text-rose-300">€{(sz * (price - 1)).toFixed(2)}</span></span>}
                                            <span>{PERSISTENCE_LABELS[d.persistence]}</span>
                                            {d.fillOrKill && <span className="text-amber-300">Fill or Kill</span>}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        <div>
                            <Label className={FIELD_LABEL}>Cap massimo stake per ordine (€) *</Label>
                            <Input type="number" step="0.01" min="2" value={capStr}
                                onChange={e => setCapStr(e.target.value)}
                                placeholder="tripwire anti-errore: es. 25"
                                className="bg-black/60 border-amber-400/30 h-9 max-w-[200px]" />
                            <p className="text-[10px] text-muted-foreground mt-1">
                                Nessun ordine sopra questo importo verrà piazzato.
                            </p>
                        </div>
                    </div>
                )}

                {/* ---------- FASE RESULTS ---------- */}
                {stage === 'results' && (
                    <div className="space-y-1.5">
                        {results.map((o, i) => (
                            <div key={i} className={`rounded-lg border px-3 py-2 text-[12px] ${o.placed
                                ? 'border-emerald-400/30 bg-emerald-400/5'
                                : 'border-destructive/30 bg-destructive/5'}`}>
                                <div className="flex items-center gap-2">
                                    {o.placed
                                        ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                                        : <XCircle className="w-4 h-4 text-red-400 shrink-0" />}
                                    <span className="font-bold text-white">{o.label}</span>
                                    {o.runner && <span className="text-white/40 text-[11px]">→ {o.runner}</span>}
                                </div>
                                <div className="text-[11px] text-muted-foreground mt-0.5 ml-6 flex flex-wrap gap-x-3">
                                    {o.placed ? (
                                        <>
                                            <span>betId <span className="font-mono text-white">{o.betId}</span></span>
                                            <span>{o.orderStatus}</span>
                                            <span>abbinato <span className="font-mono text-white">€{(o.sizeMatched ?? 0).toFixed(2)}</span>{o.avgPrice ? `@${Number(o.avgPrice).toFixed(2)}` : ''}</span>
                                            <span className={o.recorded ? 'text-emerald-400' : 'text-amber-400'}>
                                                {o.recorded ? 'registrato nel report' : 'piazzato ma NON registrato (controlla il report)'}
                                            </span>
                                        </>
                                    ) : (
                                        <span className="text-red-300">{o.error ?? 'non piazzato'}</span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* ---------- FOOTER per fase ---------- */}
                <DialogFooter className="mt-2">
                    {stage === 'edit' && (
                        <>
                            <Button variant="ghost" onClick={closeDialog} className="text-muted-foreground hover:text-white">
                                Annulla
                            </Button>
                            <Button onClick={goToConfirm} disabled={drafts.length === 0}
                                className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                                <Send className="w-4 h-4 mr-2" />
                                Rivedi e piazza{drafts.length ? ` (${drafts.length})` : ''}
                            </Button>
                        </>
                    )}
                    {stage === 'confirm' && (
                        <>
                            <Button variant="ghost" onClick={() => setStage('edit')} disabled={placing}
                                className="text-muted-foreground hover:text-white">
                                <ChevronLeft className="w-4 h-4 mr-1" /> Indietro
                            </Button>
                            <Button onClick={handlePlace} disabled={placing}
                                className="bg-destructive text-destructive-foreground font-bold hover:bg-destructive/90">
                                {placing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ShieldAlert className="w-4 h-4 mr-2" />}
                                Conferma e piazza ordini REALI
                            </Button>
                        </>
                    )}
                    {stage === 'results' && (
                        <Button onClick={() => onOpenChange(false)}
                            className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                            Chiudi
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
