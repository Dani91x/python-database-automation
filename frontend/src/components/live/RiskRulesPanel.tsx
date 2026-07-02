// ============================================================================
// RiskRulesPanel — automazione del rischio in stile Bet Angel (Fase 3).
// Arma regole SOFTWARE-SIDE su un mercato: offset (presa profitto), stop-loss,
// take-profit e trailing-stop. Selezione, lato (back/lay), prezzo/size d'ingresso
// e i parametri pertinenti (tick / % / importo P&L) con ANTEPRIMA LIVE calcolata
// sul ladder Betfair via @/lib/riskMath. Elenca le regole attive (polling ~4s)
// con badge di stato e un tasto Annulla (disarma) per ciascuna.
//
// MONEY-CRITICAL: in LIVE serve conferma esplicita (spunta one-shot); l'enqueue è
// idempotente (client_ref UUID lato @/lib/liveOrders); su timeout NON reinviare.
// ATTENZIONE: stop/offset sono SOFTWARE — se il runner si ferma NON scattano.
// Il server resta AUTORITATIVO: qui calcoliamo solo le anteprime mostrate.
// ============================================================================
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, ShieldAlert, X, AlertTriangle, Crosshair } from 'lucide-react';
import { toast } from 'sonner';
import {
    requestRiskRule, cancelRiskRule, fetchRiskRules, shouldResetLiveConfirm,
    type LiveOrderMode, type LiveOrderSide, type LivePersistence,
    type RiskRuleType, type RiskRuleParams, type RiskRuleRow,
    type RiskTiming, type RiskOnInplay,
} from '@/lib/liveOrders';
import { nearestTick, offsetTargetPrice, stopTriggerPrice } from '@/lib/riskMath';

// 'off' = risk engine spento (sola lettura, nessun arming).
export type RiskPanelMode = 'off' | LiveOrderMode;

interface SelectionOption {
    selection_id: number;
    name?: string;
}

interface Props {
    marketId: string;
    mode: RiskPanelMode;
    selections?: SelectionOption[];
    pollMs?: number;                  // refresh regole (default 4000)
}

// unità del parametro: tick sul ladder, percentuale sul prezzo, o importo P&L (€).
type ParamUnit = 'ticks' | 'pct' | 'amount';

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors disabled:opacity-40';
const FIELD_LABEL = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const num = (s: string): number | null => {
    if (s == null || s.trim() === '') return null;
    const v = Number(s);
    return Number.isFinite(v) ? v : null;
};
const money = (v?: number | null) =>
    v == null ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;
const price2 = (v: number) => v.toFixed(2);

// entry_price OBBLIGATORIO per offset/stop_loss/trailing_stop (contratto backend).
const ENTRY_PRICE_REQUIRED: ReadonlySet<RiskRuleType> = new Set<RiskRuleType>([
    'offset', 'stop_loss', 'trailing_stop',
]);

// unità ammesse per ciascun tipo di regola (la prima è il default).
const UNITS_BY_RULE: Record<RiskRuleType, ParamUnit[]> = {
    offset: ['ticks', 'pct'],
    stop_loss: ['ticks', 'pct', 'amount'],
    take_profit: ['amount', 'ticks', 'pct'],
    trailing_stop: ['ticks', 'pct'],
    bracket: ['ticks', 'pct'],
};

const RULE_LABEL: Record<RiskRuleType, string> = {
    offset: 'Offset (presa profitto)',
    stop_loss: 'Stop-loss',
    take_profit: 'Take-profit',
    trailing_stop: 'Trailing-stop',
    bracket: 'Bracket (Offset + Stop OCO)',
};
const TIMING_LABEL: Record<RiskTiming, string> = {
    immediate: 'Immediata (arma subito)',
    on_fill: 'Al fill (attende l\'ingresso)',
};
const ONINPLAY_LABEL: Record<RiskOnInplay, string> = {
    keep: 'Mantieni',
    cancel: 'Annulla',
    rebaseline: 'Ricalcola (rebaseline)',
};
const UNIT_LABEL: Record<ParamUnit, string> = {
    ticks: 'Tick',
    pct: 'Percentuale (%)',
    amount: 'Importo P&L (€)',
};

// ----------------------------- badge modalità -----------------------------
function ModeBadge({ mode }: { mode: RiskPanelMode }) {
    if (mode === 'live') {
        return (
            <Badge className="bg-red-600 text-white font-black border-transparent animate-pulse">
                🔴 LIVE REALE
            </Badge>
        );
    }
    if (mode === 'paper') {
        return <Badge className="bg-amber-400 text-black font-black border-transparent">PAPER</Badge>;
    }
    return <Badge variant="secondary" className="font-black">OFF</Badge>;
}

// ----------------------------- badge stato regola -----------------------------
function statusTone(status: RiskRuleRow['status']): string {
    switch (status) {
        case 'armed': return 'text-sky-300 border-sky-500/30 bg-sky-500/10';
        case 'triggered': return 'text-amber-300 border-amber-500/30 bg-amber-500/10';
        case 'done': return 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10';
        case 'error': return 'text-red-300 border-red-500/30 bg-red-500/10';
        default: return 'text-white/50 border-white/10 bg-white/5'; // cancelled
    }
}
const STATUS_LABEL: Record<RiskRuleRow['status'], string> = {
    armed: 'Armata',
    triggered: 'Scattata',
    cancelled: 'Annullata',
    done: 'Completata',
    error: 'Errore',
};

// Prezzo target/trigger per un'anteprima a percentuale (il server è autoritativo).
// kind='profit' = direzione favorevole (offset), kind='adverse' = movimento contro (stop).
function pctTargetPrice(kind: 'profit' | 'adverse', side: LiveOrderSide, entry: number, pct: number): number {
    const frac = Math.abs(pct) / 100;
    const raw = kind === 'profit'
        ? (side === 'back' ? entry * (1 - frac) : entry * (1 + frac))
        : (side === 'back' ? entry * (1 + frac) : entry * (1 - frac));
    return nearestTick(raw);
}

export function RiskRulesPanel({
    marketId,
    mode,
    selections = [],
    pollMs = 4000,
}: Props) {
    const readOnly = mode === 'off';
    const isLive = mode === 'live';

    // -------------------- form arming --------------------
    const [selectionId, setSelectionId] = useState<string>(
        selections[0]?.selection_id != null ? String(selections[0].selection_id) : '',
    );
    const [handicap, setHandicap] = useState('0');
    const [ruleType, setRuleType] = useState<RiskRuleType>('offset');
    const [entrySide, setEntrySide] = useState<LiveOrderSide>('back');
    const [entryPrice, setEntryPrice] = useState('');
    const [entrySize, setEntrySize] = useState('');
    const [unit, setUnit] = useState<ParamUnit>('ticks');
    const [paramValue, setParamValue] = useState('');       // valore tick / % / € a seconda di `unit`
    const [greening, setGreening] = useState(true);         // offset / bracket
    const [timing, setTiming] = useState<RiskTiming>('immediate');
    const [entryBetId, setEntryBetId] = useState('');       // ordine di ingresso da sorvegliare (on_fill/bracket)
    const [placeAtTicks, setPlaceAtTicks] = useState('');   // stop_loss / bracket: tick oltre per fill sicuro
    const [onInplay, setOnInplay] = useState<RiskOnInplay>('keep');
    const [persistence, setPersistence] = useState<LivePersistence>('LAPSE');
    const [confirmLive, setConfirmLive] = useState(false);
    const [killSwitch, setKillSwitch] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    // -------------------- lista regole --------------------
    const [rules, setRules] = useState<RiskRuleRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [listErr, setListErr] = useState<string | null>(null);

    // quando cambia il tipo di regola, se l'unità corrente non è ammessa → resetta al default.
    useEffect(() => {
        const allowed = UNITS_BY_RULE[ruleType];
        if (!allowed.includes(unit)) setUnit(allowed[0]);
    }, [ruleType, unit]);

    const allowedUnits = UNITS_BY_RULE[ruleType];
    // bracket e timing 'on_fill' derivano il riferimento dall'ABBINAMENTO reale
    // dell'ordine di ingresso (entry_bet_id) → niente gamba nuda, entry_price non richiesto.
    const derivesFromFill = ruleType === 'bracket' || timing === 'on_fill';
    const showGreening = ruleType === 'offset' || ruleType === 'bracket';
    const showPlaceAt = ruleType === 'stop_loss' || ruleType === 'bracket';
    // serve un prezzo d'ingresso se il tipo lo impone O se l'unità è basata sul prezzo (tick/%),
    // ma MAI quando il riferimento è derivato dal fill dell'ordine di ingresso.
    const needsEntryPrice =
        !derivesFromFill && (ENTRY_PRICE_REQUIRED.has(ruleType) || unit === 'ticks' || unit === 'pct');

    // -------------------- anteprima LIVE --------------------
    const preview = useMemo<string | null>(() => {
        const v = num(paramValue);
        const ep = num(entryPrice);
        if (v == null || v <= 0) return null;

        if (unit === 'amount') {
            if (ruleType === 'take_profit') return `chiude quando il P&L ≥ ${money(v)}`;
            if (ruleType === 'stop_loss') return `chiude quando il P&L ≤ ${money(-v)}`;
            return null;
        }
        if (ep == null || ep < 1.01 || ep > 1000) return null;

        if (unit === 'ticks') {
            if (ruleType === 'offset' || ruleType === 'take_profit' || ruleType === 'bracket') {
                const t = offsetTargetPrice(entrySide, ep, v);
                const suffix = ruleType === 'bracket' ? ' + stop OCO' : '';
                return `target offset a ${price2(t)} (${v} tick di profitto)${suffix}`;
            }
            // stop_loss / trailing_stop → trigger avverso
            const t = stopTriggerPrice(entrySide, ep, v);
            const kind = ruleType === 'trailing_stop' ? 'trailing (iniziale) scatta' : 'stop scatta';
            return `${kind} a ${price2(t)} (${v} tick contro)`;
        }
        // unit === 'pct'
        if (ruleType === 'offset' || ruleType === 'take_profit' || ruleType === 'bracket') {
            const t = pctTargetPrice('profit', entrySide, ep, v);
            const suffix = ruleType === 'bracket' ? ' + stop OCO' : '';
            return `target offset a ${price2(t)} (${v}%)${suffix}`;
        }
        const t = pctTargetPrice('adverse', entrySide, ep, v);
        const kind = ruleType === 'trailing_stop' ? 'trailing (iniziale) scatta' : 'stop scatta';
        return `${kind} a ${price2(t)} (${v}%)`;
    }, [paramValue, entryPrice, entrySide, unit, ruleType]);

    // -------------------- caricamento regole --------------------
    const reload = useCallback(async () => {
        if (!marketId) return;
        setLoading(true);
        setListErr(null);
        try {
            const rows = await fetchRiskRules(marketId);
            // mostra solo le regole della modalità attiva (in OFF mostra tutto, sola lettura).
            const m = readOnly ? null : (mode as LiveOrderMode);
            setRules(m ? rows.filter(r => r.mode === m) : rows);
        } catch (e: any) {
            setListErr(e?.message ?? 'errore di caricamento');
        } finally {
            setLoading(false);
        }
    }, [marketId, mode, readOnly]);

    useEffect(() => {
        reload();
        if (pollMs <= 0) return;
        const t = setInterval(reload, pollMs);
        return () => clearInterval(t);
    }, [reload, pollMs]);

    // -------------------- costruzione params (contratto backend) --------------------
    const buildParams = (v: number): RiskRuleParams => {
        const params: RiskRuleParams = {};
        if (ruleType === 'offset') {
            if (unit === 'ticks') params.offset_ticks = v; else params.offset_pct = v;
            params.greening = greening;
        } else if (ruleType === 'bracket') {
            // OCO: gamba di presa profitto (offset) + stop; il primo che scatta annulla l'altro.
            if (unit === 'ticks') params.offset_ticks = v; else params.offset_pct = v;
            params.greening = greening;
        } else if (ruleType === 'stop_loss') {
            if (unit === 'ticks') params.trigger_ticks = v;
            else if (unit === 'pct') params.trigger_pct = v;
            else params.stop_amount = v;
        } else if (ruleType === 'take_profit') {
            if (unit === 'ticks') params.trigger_ticks = v;
            else if (unit === 'pct') params.trigger_pct = v;
            else params.target_amount = v;
        } else { // trailing_stop
            if (unit === 'ticks') params.trail_ticks = v; else params.trail_pct = v;
        }
        // place_at_ticks: dove piazzare l'ordine di uscita (stop_loss / bracket) per fill sicuro.
        if (showPlaceAt) {
            const pat = num(placeAtTicks);
            if (pat != null) params.place_at_ticks = pat;
        }
        params.timing = timing;
        params.on_inplay = onInplay;
        params.persistence = persistence;
        return params;
    };

    // -------------------- arming --------------------
    const guardBeforeSend = (): string | null => {
        if (readOnly) return 'Modalità OFF: il risk engine è spento, nessuna regola armabile.';
        if (killSwitch) return 'Blocco pannello attivo: arming bloccato. Disattivalo per operare.';
        if (isLive && !confirmLive) return 'Spunta "Confermo regola REALE" prima di armare in LIVE.';
        return null;
    };

    const handleArm = async () => {
        const blocked = guardBeforeSend();
        if (blocked) { toast.error(blocked); return; }

        const sel = num(selectionId);
        const v = num(paramValue);
        const ep = num(entryPrice);
        const es = num(entrySize);
        if (sel == null) { toast.error('Seleziona la selezione (selection_id).'); return; }
        if (v == null || v <= 0) { toast.error(`Valore ${UNIT_LABEL[unit].toLowerCase()} non valido.`); return; }
        if (needsEntryPrice && (ep == null || ep < 1.01 || ep > 1000)) {
            toast.error('Prezzo d\'ingresso non valido (1.01–1000): obbligatorio per questa regola.');
            return;
        }
        const betId = entryBetId.trim();
        // no gamba nuda: bracket / timing on_fill devono sorvegliare un ordine d'ingresso.
        if (derivesFromFill && !betId) {
            toast.error('entry_bet_id obbligatorio per bracket / timing "al fill": attende il fill dell\'ingresso, niente gamba nuda.');
            return;
        }

        setSubmitting(true);
        try {
            const id = await requestRiskRule({
                mode: mode as LiveOrderMode,
                ruleType,
                marketId,
                selectionId: sel,
                handicap: num(handicap) ?? 0,
                entrySide,
                ...(ep != null ? { entryPrice: ep } : {}),
                ...(es != null ? { entrySize: es } : {}),
                ...(betId ? { entryBetId: betId } : {}),
                params: buildParams(v),
            });
            toast.success('Regola armata', {
                description: `${RULE_LABEL[ruleType]} · #${id}${preview ? ` · ${preview}` : ''}`,
            });
            // MONEY-CRITICAL: conferma LIVE one-shot → resetta dopo arming riuscito.
            if (shouldResetLiveConfirm(isLive, true)) setConfirmLive(false);
            await reload();
        } catch (e: any) {
            toast.error('Errore arming regola', { description: e?.message ?? 'errore sconosciuto' });
            // MONEY-CRITICAL (fix review): su fallimento AMBIGUO (regola forse committata lato server
            // ma risposta persa) resetta la conferma LIVE — requestRiskRule conia un client_ref nuovo
            // ad ogni chiamata, quindi un re-click armerebbe una regola LIVE DUPLICATA (ordine di uscita
            // duplicato). Richiedere una nuova spunta esplicita prima di ri-armare. (Come DutchingPanel.)
            if (isLive) setConfirmLive(false);
        } finally {
            setSubmitting(false);
        }
    };

    const handleCancel = async (row: RiskRuleRow) => {
        if (readOnly) return;
        setSubmitting(true);
        try {
            await cancelRiskRule(row.id);
            toast.success('Regola disarmata', { description: `#${row.id}` });
            await reload();
        } catch (e: any) {
            toast.error('Errore disarmo', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSubmitting(false);
        }
    };

    const selName = (id: number) => selections.find(s => s.selection_id === id)?.name ?? `#${id}`;

    // testo sintetico del parametro di una riga (per la tabella).
    const ruleParamText = (r: RiskRuleRow): string => {
        const p = r.params as RiskRuleParams;
        const bits: string[] = [];
        if (p.offset_ticks != null) bits.push(`${p.offset_ticks} tick`);
        if (p.offset_pct != null) bits.push(`${p.offset_pct}%`);
        if (p.trigger_ticks != null) bits.push(`${p.trigger_ticks} tick`);
        if (p.trigger_pct != null) bits.push(`${p.trigger_pct}%`);
        if (p.trail_ticks != null) bits.push(`trail ${p.trail_ticks} tick`);
        if (p.trail_pct != null) bits.push(`trail ${p.trail_pct}%`);
        if (p.stop_amount != null) bits.push(`stop ${money(-Math.abs(p.stop_amount))}`);
        if (p.target_amount != null) bits.push(`target ${money(Math.abs(p.target_amount))}`);
        if (p.place_at_ticks != null) bits.push(`@${p.place_at_ticks} tick`);
        if (p.greening) bits.push('greening');
        if (p.timing === 'on_fill') bits.push('on-fill');
        if (p.on_inplay && p.on_inplay !== 'keep') bits.push(`in-play: ${p.on_inplay}`);
        return bits.join(' · ') || '—';
    };

    return (
        <div className="glass-card rounded-2xl border border-white/10 bg-black/40 p-4 md:p-5 space-y-5">
            {/* header + badge modalità */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <div className="flex items-center gap-2">
                        <Crosshair className="w-5 h-5 text-amber-400" />
                        <h3 className="font-display font-black text-lg text-white">Automazione Rischio</h3>
                        <ModeBadge mode={mode} />
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        offset · stop-loss · take-profit · trailing · bracket (OCO) — mercato{' '}
                        <span className="font-mono text-white/70">{marketId}</span>
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={() => setKillSwitch(k => !k)}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors ${
                            killSwitch
                                ? 'bg-red-600 text-white border-transparent'
                                : 'bg-white/5 text-white/70 border-white/10 hover:border-red-500/40'
                        }`}
                        title="Blocca SOLO l'arming da questo pannello (il Kill-switch GLOBALE del runner è nei Controlli)"
                    >
                        <ShieldAlert className="w-3.5 h-3.5" />
                        Blocco pannello {killSwitch ? 'ON' : 'OFF'}
                    </button>
                    <Button variant="ghost" size="sm" onClick={reload} disabled={loading}
                        className="text-muted-foreground hover:text-white">
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                    </Button>
                </div>
            </div>

            {/* warning SOFTWARE-SIDE (sempre visibile, money-critical) */}
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-300 mt-0.5 shrink-0" />
                <p className="text-[11px] text-amber-200 leading-relaxed">
                    Stop/offset <b>SOFTWARE-SIDE</b>: se il runner si ferma <b>NON sono attivi</b>. Nessuna
                    protezione lato Betfair — servono runner e connessione vivi.
                </p>
            </div>

            {readOnly && (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground">
                    Risk engine in <b>OFF</b>: arming disabilitato. Avvia il runner in PAPER o LIVE per armare regole.
                </div>
            )}

            {/* ---------------- form arming ---------------- */}
            <fieldset disabled={readOnly} className="space-y-3">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="col-span-2">
                        <Label className={FIELD_LABEL}>Selezione</Label>
                        {selections.length > 0 ? (
                            <select className={SELECT_CLS} value={selectionId}
                                onChange={e => setSelectionId(e.target.value)}>
                                {selections.map(s => (
                                    <option key={s.selection_id} value={s.selection_id}>
                                        {s.name ?? `#${s.selection_id}`} (#{s.selection_id})
                                    </option>
                                ))}
                            </select>
                        ) : (
                            <Input type="number" value={selectionId} onChange={e => setSelectionId(e.target.value)}
                                placeholder="selection_id" className="bg-black/60 border-white/10" />
                        )}
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Handicap</Label>
                        <Input type="number" step="0.25" value={handicap} onChange={e => setHandicap(e.target.value)}
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Tipo regola</Label>
                        <select className={SELECT_CLS} value={ruleType}
                            aria-label="Tipo regola"
                            onChange={e => setRuleType(e.target.value as RiskRuleType)}>
                            {(Object.keys(RULE_LABEL) as RiskRuleType[]).map(rt => (
                                <option key={rt} value={rt}>{RULE_LABEL[rt]}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Lato ingresso</Label>
                        <select className={SELECT_CLS} value={entrySide}
                            onChange={e => setEntrySide(e.target.value as LiveOrderSide)}>
                            <option value="back">Back (punta)</option>
                            <option value="lay">Lay (banca)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>
                            Prezzo ingresso{needsEntryPrice ? ' *' : ' (opz.)'}
                        </Label>
                        <Input type="number" step="0.01" min="1.01" max="1000" value={entryPrice}
                            onChange={e => setEntryPrice(e.target.value)} placeholder="es. 2.10"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Size ingresso (€, opz.)</Label>
                        <Input type="number" step="0.01" min="0" value={entrySize}
                            onChange={e => setEntrySize(e.target.value)} placeholder="es. 5.00"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Unità parametro</Label>
                        <select className={SELECT_CLS} value={unit}
                            onChange={e => setUnit(e.target.value as ParamUnit)}>
                            {allowedUnits.map(u => (
                                <option key={u} value={u}>{UNIT_LABEL[u]}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>
                            {unit === 'ticks' ? 'Tick' : unit === 'pct' ? 'Percentuale (%)' : 'Importo (€)'}
                        </Label>
                        <Input type="number" step={unit === 'ticks' ? '1' : '0.01'} min="0" value={paramValue}
                            onChange={e => setParamValue(e.target.value)}
                            placeholder={unit === 'ticks' ? 'es. 3' : unit === 'pct' ? 'es. 2.5' : 'es. 5.00'}
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Persistenza</Label>
                        <select className={SELECT_CLS} value={persistence}
                            onChange={e => setPersistence(e.target.value as LivePersistence)}>
                            <option value="LAPSE">LAPSE (decade in-play)</option>
                            <option value="PERSIST">PERSIST (resta)</option>
                            <option value="MARKET_ON_CLOSE">MARKET_ON_CLOSE</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Attivazione (timing)</Label>
                        <select className={SELECT_CLS} value={timing}
                            aria-label="Attivazione (timing)"
                            onChange={e => setTiming(e.target.value as RiskTiming)}>
                            {(Object.keys(TIMING_LABEL) as RiskTiming[]).map(t => (
                                <option key={t} value={t}>{TIMING_LABEL[t]}</option>
                            ))}
                        </select>
                    </div>
                    {showPlaceAt && (
                        <div>
                            <Label className={FIELD_LABEL}>Piazza a (tick oltre)</Label>
                            <Input type="number" step="1" min="0" value={placeAtTicks}
                                aria-label="Piazza a (tick oltre)"
                                onChange={e => setPlaceAtTicks(e.target.value)} placeholder="es. 1"
                                className="bg-black/60 border-white/10" />
                            <p className="text-[10px] text-muted-foreground mt-1">
                                a quanti tick oltre chiude, per fill sicuro
                            </p>
                        </div>
                    )}
                    <div>
                        <Label className={FIELD_LABEL}>Al calcio d'inizio (in-play)</Label>
                        <select className={SELECT_CLS} value={onInplay}
                            aria-label="Al calcio d'inizio (in-play)"
                            onChange={e => setOnInplay(e.target.value as RiskOnInplay)}>
                            {(Object.keys(ONINPLAY_LABEL) as RiskOnInplay[]).map(o => (
                                <option key={o} value={o}>{ONINPLAY_LABEL[o]}</option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* entry_bet_id: obbligatorio per bracket / on_fill (niente gamba nuda) */}
                {(timing === 'on_fill' || ruleType === 'bracket') && (
                    <div>
                        <Label className={FIELD_LABEL}>
                            Ordine d'ingresso (entry_bet_id){derivesFromFill ? ' *' : ''}
                        </Label>
                        <Input value={entryBetId} onChange={e => setEntryBetId(e.target.value)}
                            aria-label="Ordine d'ingresso (entry_bet_id)"
                            placeholder="es. 3.11223344 (bet id Betfair)"
                            className="bg-black/60 border-white/10 font-mono" />
                        <p className="text-[10px] text-muted-foreground mt-1">
                            attende il fill dell'ingresso, niente gamba nuda
                        </p>
                    </div>
                )}

                {/* greening (offset / bracket) */}
                {showGreening && (
                    <label className="inline-flex items-center gap-2 text-xs text-white/80 cursor-pointer">
                        <input type="checkbox" checked={greening} onChange={e => setGreening(e.target.checked)}
                            className="accent-amber-400" />
                        Greening (chiudi pareggiando il profitto su tutte le uscite)
                    </label>
                )}

                {/* anteprima LIVE */}
                <div className={`rounded-xl border px-3 py-2 text-xs ${
                    preview
                        ? 'border-sky-500/30 bg-sky-500/10 text-sky-200'
                        : 'border-white/10 bg-white/[0.03] text-muted-foreground'
                }`}>
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-2">Anteprima</span>
                    <span className={entrySide === 'back' ? 'text-sky-300' : 'text-rose-300'}>
                        {entrySide === 'back' ? 'Back' : 'Lay'}
                    </span>{' '}
                    {preview ?? 'inserisci prezzo/valore per l\'anteprima…'}
                    <span className="text-white/40"> (stima; il server è autoritativo)</span>
                </div>

                {/* conferma LIVE + arma */}
                <div className="flex items-center justify-between gap-3 flex-wrap pt-1">
                    {isLive ? (
                        <label className="inline-flex items-center gap-2 text-xs font-bold text-red-300 cursor-pointer">
                            <input type="checkbox" checked={confirmLive} onChange={e => setConfirmLive(e.target.checked)}
                                className="accent-red-500" />
                            Confermo regola REALE (soldi veri)
                        </label>
                    ) : (
                        <span className="text-[11px] text-muted-foreground">
                            Modalità PAPER: nessun denaro reale.
                        </span>
                    )}

                    <Button
                        onClick={handleArm}
                        disabled={submitting || killSwitch || (isLive && !confirmLive)}
                        className={`font-black ${
                            entrySide === 'back'
                                ? 'bg-sky-500 hover:bg-sky-400 text-black'
                                : 'bg-rose-500 hover:bg-rose-400 text-black'
                        }`}
                    >
                        {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        Arma {RULE_LABEL[ruleType]}
                    </Button>
                </div>
            </fieldset>

            {/* ---------------- lista regole ---------------- */}
            <div className="border-t border-white/5 pt-4">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mb-2">
                    Regole attive ({rules.length})
                </div>
                {listErr && <p className="text-xs text-red-400 mb-2">Errore: {listErr}</p>}
                {rules.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Nessuna regola su questo mercato.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead>
                                <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left py-1.5 pr-2">Selezione</th>
                                    <th className="text-left py-1.5 px-2">Tipo</th>
                                    <th className="text-left py-1.5 px-2">Lato</th>
                                    <th className="text-right py-1.5 px-2">Ingresso</th>
                                    <th className="text-left py-1.5 px-2">Parametri</th>
                                    <th className="text-left py-1.5 px-2">Stato</th>
                                    <th className="text-right py-1.5 pl-2">Azioni</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rules.map(r => (
                                    <tr key={r.id} className="border-b border-white/[0.04]">
                                        <td className="py-1.5 pr-2 text-white/80 truncate max-w-[140px]">
                                            {selName(r.selection_id)}
                                        </td>
                                        <td className="py-1.5 px-2 text-white/80">{RULE_LABEL[r.rule_type]}</td>
                                        <td className="py-1.5 px-2">
                                            <span className={r.entry_side === 'back' ? 'text-sky-300' : 'text-rose-300'}>
                                                {r.entry_side === 'back' ? 'Back' : 'Lay'}
                                            </span>
                                        </td>
                                        <td className="py-1.5 px-2 text-right font-mono text-white/70">
                                            {r.entry_price != null ? price2(r.entry_price) : '—'}
                                        </td>
                                        <td className="py-1.5 px-2 text-white/70">{ruleParamText(r)}</td>
                                        <td className="py-1.5 px-2">
                                            <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-bold ${statusTone(r.status)}`}>
                                                {STATUS_LABEL[r.status] ?? r.status}
                                            </span>
                                        </td>
                                        <td className="py-1.5 pl-2 text-right whitespace-nowrap">
                                            {r.status === 'armed' && !readOnly && (
                                                <button onClick={() => handleCancel(r)} disabled={submitting}
                                                    className="inline-flex items-center gap-1 text-red-400/80 hover:text-red-400 p-1"
                                                    title="Disarma (annulla regola)">
                                                    <X className="w-4 h-4" />
                                                    <span className="text-[11px] font-bold">Disarma</span>
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

export default RiskRulesPanel;
