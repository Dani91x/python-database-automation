// ============================================================================
// LiveControlsPanel — controlli GLOBALI del runner LIVE TRADING (Fase 6).
// Pannello unico (NON per-mercato): kill-switch globale mediato dal DB, form
// impostazioni operative (cap esposizione/ordini + velocità di poll) e viewer del
// registro di audit (ultimi eventi del runner). Tutto via @/lib/liveOrders → RPC
// SECURITY DEFINER; nessuna chiamata diretta al PC. Design system: glass-card,
// amber Betfair, back azzurro / lay rosa.
//
// MONEY-CRITICAL: il kill-switch è GLOBALE — quando ATTIVO il runner NON processa
// alcun ordine (protezione valida da qualunque origine). Difensivo: se le RPC
// falliscono mostra un errore attenuato, non va MAI in crash.
// ============================================================================
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, RefreshCw, ShieldAlert, ShieldCheck, SlidersHorizontal, ScrollText, Save } from 'lucide-react';
import { toast } from 'sonner';
import {
    getLiveSettings, setKillSwitch, setLiveSettings, fetchLiveAudit,
    fetchLiveRiskState, subscribeLiveRiskState,
    type LiveSettings, type LiveAuditRow, type LiveRiskState,
} from '@/lib/liveOrders';

interface Props {
    pollMs?: number;                  // refresh impostazioni + audit (default 4000)
}

const FIELD_LABEL = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';
const AUDIT_LIMIT = 50;

const num = (s: string): number | null => {
    if (s == null || s.trim() === '') return null;
    const v = Number(s);
    return Number.isFinite(v) ? v : null;
};
const money = (v?: number | null) =>
    v == null ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;
// input string da un valore numerico|null (vuoto = nessun limite).
const toField = (v: number | null | undefined) => (v == null ? '' : String(v));
// orario compatto HH:MM:SS dal timestamp ISO (difensivo su valori non parsabili).
const clock = (ts: string): string => {
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString('it-IT');
};

// tono colore per lo stato di una riga di audit (verde = ok, rosso = errore/rifiuto).
function statusTone(status: string | null, hasError: boolean): string {
    if (hasError) return 'text-red-300';
    const s = (status ?? '').toUpperCase();
    if (s === 'DONE' || s === 'OK' || s === 'EXECUTION_COMPLETE') return 'text-emerald-300';
    if (s === 'ERROR' || s === 'VIOLATION' || s === 'REJECTED') return 'text-red-300';
    if (s === 'PENDING' || s === 'PROCESSING' || s === 'EXECUTABLE') return 'text-amber-300';
    return 'text-white/60';
}

export function LiveControlsPanel({ pollMs = 4000 }: Props) {
    // -------------------- stato impostazioni --------------------
    const [settings, setSettings] = useState<LiveSettings | null>(null);
    const [audit, setAudit] = useState<LiveAuditRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState<string | null>(null);
    // fix audit #27: errore del registro audit SEPARATO e visibile (prima veniva
    // inghiottito in una lista vuota silenziosa).
    const [auditErr, setAuditErr] = useState<string | null>(null);
    const [toggling, setToggling] = useState(false);
    const [saving, setSaving] = useState(false);
    const busyRef = useRef(false);

    // -------------------- form impostazioni (stringhe: vuoto = nessun limite) --------------------
    const [maxExposure, setMaxExposure] = useState('');
    const [maxOrdersPerMin, setMaxOrdersPerMin] = useState('');
    const [orderPollSec, setOrderPollSec] = useState('');
    const [riskPollSec, setRiskPollSec] = useState('');
    // E34/E35: stop giornaliero di conto + limiti aggregati evento/campionato.
    const [dailyLossLimit, setDailyLossLimit] = useState('');
    const [maxExpEvent, setMaxExpEvent] = useState('');
    const [maxExpLeague, setMaxExpLeague] = useState('');
    // true finché l'utente non ha toccato il form: allora i poll non sovrascrivono le sue modifiche.
    const dirtyRef = useRef(false);

    // E34: stato rischio giornaliero pubblicato dal runner (realtime).
    const [riskState, setRiskState] = useState<LiveRiskState | null>(null);
    useEffect(() => {
        let alive = true;
        fetchLiveRiskState().then(r => { if (alive) setRiskState(r); }).catch(() => {});
        const unsub = subscribeLiveRiskState(r => { if (r) setRiskState(r); });
        return () => { alive = false; unsub(); };
    }, []);

    // riempi il form dalle impostazioni correnti (solo se l'utente non sta editando).
    const syncForm = useCallback((s: LiveSettings) => {
        if (dirtyRef.current) return;
        setMaxExposure(toField(s.max_exposure_per_selection));
        setMaxOrdersPerMin(toField(s.max_orders_per_min));
        setOrderPollSec(toField(s.order_poll_sec));
        setRiskPollSec(toField(s.risk_poll_sec));
        setDailyLossLimit(toField(s.daily_loss_limit));
        setMaxExpEvent(toField(s.max_exposure_per_event));
        setMaxExpLeague(toField(s.max_exposure_per_league));
    }, []);

    const reload = useCallback(async () => {
        if (busyRef.current) return;
        busyRef.current = true;
        setLoading(true);
        try {
            // difensivo: le due letture sono indipendenti, un fallimento non azzera l'altra.
            // fix audit #27: un fallimento dell'audit NON è una lista vuota silenziosa —
            // si mantiene l'ultima lista buona e si mostra l'errore.
            const [s, a] = await Promise.all([
                getLiveSettings().catch(() => null),
                fetchLiveAudit(AUDIT_LIMIT).catch((e: any) => {
                    setAuditErr(e?.message ?? 'registro eventi non disponibile');
                    return null;
                }),
            ]);
            if (s) { setSettings(s); syncForm(s); setErr(null); }
            else setErr('Impostazioni non disponibili (runner/DB non raggiungibile).');
            if (a) { setAudit(a); setAuditErr(null); }
        } catch (e: any) {
            setErr(e?.message ?? 'errore di caricamento');
        } finally {
            setLoading(false);
            busyRef.current = false;
        }
    }, [syncForm]);

    useEffect(() => {
        reload();
        if (pollMs <= 0) return;
        const t = setInterval(reload, pollMs);
        return () => clearInterval(t);
    }, [reload, pollMs]);

    // -------------------- kill-switch globale --------------------
    const killOn = settings?.kill_switch === true;

    const toggleKill = useCallback(async () => {
        const next = !killOn;
        // in attivazione nessuna conferma (è una protezione); in disattivazione sì (riabilita gli ordini).
        if (!next && !window.confirm('Disattivare il KILL-SWITCH globale?\nIl runner tornerà a processare gli ordini.')) {
            return;
        }
        setToggling(true);
        try {
            const s = await setKillSwitch(next);
            if (s) { setSettings(s); syncForm(s); }
            toast.success(next ? 'Kill-switch ATTIVATO' : 'Kill-switch disattivato', {
                description: next
                    ? 'Aperture rifiutate; cancel e chiusure passano. Gli stop SOFTWARE non scattano.'
                    : 'Il runner torna operativo.',
            });
            await reload();
        } catch (e: any) {
            toast.error('Errore kill-switch', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setToggling(false);
        }
    }, [killOn, reload, syncForm]);

    // -------------------- salvataggio impostazioni --------------------
    const handleSave = useCallback(async () => {
        // E34/E35 + fix audit #27: TUTTI i limiti/velocità, se presenti, devono essere > 0
        // (un cap a 0/negativo bloccherebbe tutto o non avrebbe senso; il DB li rifiuterebbe
        // comunque — meglio dirlo subito e non salvare nulla).
        for (const [label, raw] of [
            ['Stop giornaliero', dailyLossLimit],
            ['Max esposizione / evento', maxExpEvent],
            ['Max esposizione / campionato', maxExpLeague],
            ['Max esposizione / selezione', maxExposure],
            ['Max ordini / min', maxOrdersPerMin],
            ['Poll ordini (s)', orderPollSec],
            ['Poll rischio (s)', riskPollSec],
        ] as const) {
            const v = num(raw);
            if (raw.trim() !== '' && (v == null || v <= 0)) {
                toast.error(`${label}: valore non valido`, { description: 'Inserisci un valore > 0, oppure lascia vuoto per disattivare.' });
                return;
            }
        }
        setSaving(true);
        try {
            const patch = {
                max_exposure_per_selection: num(maxExposure),
                max_orders_per_min: num(maxOrdersPerMin),
                order_poll_sec: num(orderPollSec),
                risk_poll_sec: num(riskPollSec),
                daily_loss_limit: num(dailyLossLimit),
                max_exposure_per_event: num(maxExpEvent),
                max_exposure_per_league: num(maxExpLeague),
            };
            const s = await setLiveSettings(patch);
            dirtyRef.current = false;      // dopo il salvataggio i poll possono riallineare il form
            if (s) { setSettings(s); syncForm(s); }
            toast.success('Impostazioni salvate', {
                description: 'Le velocità di poll si applicano al riavvio del runner.',
            });
            await reload();
        } catch (e: any) {
            toast.error('Errore salvataggio', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSaving(false);
        }
    }, [maxExposure, maxOrdersPerMin, orderPollSec, riskPollSec,
        dailyLossLimit, maxExpEvent, maxExpLeague, reload, syncForm]);

    // segna il form come "sporco" al primo edit → i poll non sovrascrivono più i campi.
    const onEdit = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
        dirtyRef.current = true;
        setter(e.target.value);
    };

    const audCell = (v: string | number | null | undefined) => (v == null || v === '' ? '—' : String(v));

    return (
        <div className="glass-card rounded-2xl border border-white/10 bg-black/40 p-4 md:p-5 space-y-5">
            {/* header */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <div className="flex items-center gap-2">
                        <SlidersHorizontal className="w-5 h-5 text-amber-400" />
                        <h3 className="font-display font-black text-lg text-white">Controlli Runner</h3>
                        <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold px-2 py-0.5 rounded bg-white/5 border border-white/10">
                            Globale
                        </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        Kill-switch, limiti operativi e registro eventi — validi per <b>tutti</b> i mercati.
                    </p>
                </div>
                <Button variant="ghost" size="sm" onClick={reload} disabled={loading}
                    className="text-muted-foreground hover:text-white">
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                </Button>
            </div>

            {err && (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground">
                    {err}
                </div>
            )}

            {/* ---------------- kill-switch globale (prominente) ---------------- */}
            <button
                type="button"
                onClick={toggleKill}
                disabled={toggling}
                className={`w-full rounded-2xl border px-4 py-4 flex items-center justify-between gap-3 transition-colors text-left ${
                    killOn
                        ? 'bg-red-600 border-red-400/50 text-white animate-pulse hover:bg-red-500'
                        : 'bg-white/5 border-white/10 text-white/80 hover:border-red-500/40'
                }`}
                title={killOn ? 'Clic per disattivare il kill-switch' : 'Clic per attivare il kill-switch globale'}
            >
                <div className="flex items-center gap-3">
                    {killOn
                        ? <ShieldAlert className="w-7 h-7 shrink-0" />
                        : <ShieldCheck className="w-7 h-7 shrink-0 text-emerald-400" />}
                    <div>
                        {/* fix audit #27: copy ONESTA — il kill-switch rifiuta le APERTURE ma
                            lascia passare cancel e chiusure; gli stop SOFTWARE non scattano. */}
                        <div className="font-display font-black text-base md:text-lg">
                            {killOn
                                ? '🔴 KILL-SWITCH ATTIVO — aperture rifiutate, chiusure permesse'
                                : 'Kill-switch disattivato — runner operativo'}
                        </div>
                        <div className={`text-[11px] mt-0.5 ${killOn ? 'text-white/80' : 'text-muted-foreground'}`}>
                            {killOn
                                ? 'Il runner rifiuta le APERTURE; cancel e chiusure (green-up/cash-out) passano. ⚠ Gli stop/offset SOFTWARE NON scattano finché è attivo.'
                                : 'Clic per bloccare immediatamente le aperture (globale); chiusure e cancel restano permessi.'}
                        </div>
                    </div>
                </div>
                <span className={`shrink-0 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-black border ${
                    killOn ? 'bg-black/30 border-white/20' : 'bg-white/5 border-white/10'
                }`}>
                    {toggling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                    {killOn ? 'ATTIVO' : 'OFF'}
                </span>
            </button>

            {/* ---------------- E34: stato stop giornaliero (dal runner, realtime) ---------------- */}
            {riskState?.day && (
                <div className={`rounded-xl border px-3 py-2.5 flex items-center justify-between gap-3 flex-wrap ${
                    riskState.stop_fired
                        ? 'border-red-400/60 bg-red-950/40'
                        : 'border-white/10 bg-white/[0.03]'
                }`}>
                    <div className="text-[11px]">
                        <span className="uppercase tracking-wider text-muted-foreground font-bold mr-2">
                            P&amp;L giornata ({riskState.day})
                        </span>
                        <span className={`font-mono font-bold ${
                            (riskState.total ?? 0) < 0 ? 'text-red-300' : 'text-emerald-300'
                        }`}>
                            {money(riskState.total)}
                        </span>
                        <span className="text-muted-foreground ml-2">
                            settled {money(riskState.realized)} · MTM {money(riskState.open_mtm)}
                            {riskState.detail?.degraded ? ' · ⚠ stima worst-case' : ''}
                        </span>
                    </div>
                    {riskState.stop_fired ? (
                        <span className="text-[11px] font-black text-red-200 bg-red-600/60 border border-red-400/60 rounded-lg px-2 py-1">
                            🛑 STOP GIORNALIERO SCATTATO — solo chiusure
                        </span>
                    ) : riskState.limit_value != null ? (
                        <span className="text-[10px] text-muted-foreground">
                            stop a −{money(riskState.limit_value)}
                        </span>
                    ) : (
                        <span className="text-[10px] text-muted-foreground">stop giornaliero spento</span>
                    )}
                </div>
            )}

            {/* ---------------- impostazioni operative ---------------- */}
            <div className="border-t border-white/5 pt-4 space-y-3">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                    Limiti &amp; velocità
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div>
                        <Label className={FIELD_LABEL}>Max esposizione / selezione (€)</Label>
                        <Input type="number" step="0.5" min="0" value={maxExposure}
                            onChange={onEdit(setMaxExposure)} placeholder="nessun limite"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Max ordini / min</Label>
                        <Input type="number" step="1" min="0" value={maxOrdersPerMin}
                            onChange={onEdit(setMaxOrdersPerMin)} placeholder="nessun limite"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Poll ordini (s)</Label>
                        <Input type="number" step="0.5" min="0" value={orderPollSec}
                            onChange={onEdit(setOrderPollSec)} placeholder="default"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Poll rischio (s)</Label>
                        <Input type="number" step="0.5" min="0" value={riskPollSec}
                            onChange={onEdit(setRiskPollSec)} placeholder="default"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Stop giornaliero (€ perdita max)</Label>
                        <Input type="number" step="1" min="0" value={dailyLossLimit}
                            onChange={onEdit(setDailyLossLimit)} placeholder="spento"
                            title="E34: raggiunta questa perdita di GIORNATA (settled + MTM) il runner attiva da solo il kill-switch (solo chiusure)."
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Max esposizione / evento (€)</Label>
                        <Input type="number" step="1" min="0" value={maxExpEvent}
                            onChange={onEdit(setMaxExpEvent)} placeholder="nessun limite"
                            title="E35: esposizione worst-case aggregata sui mercati di UN evento; oltre, i nuovi PLACE sono rifiutati (le chiusure passano sempre)."
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Max esposizione / campionato (€)</Label>
                        <Input type="number" step="1" min="0" value={maxExpLeague}
                            onChange={onEdit(setMaxExpLeague)} placeholder="nessun limite"
                            title="E35: come per evento, ma sommata su tutti gli eventi dello stesso campionato (mappa live_follow)."
                            className="bg-black/60 border-white/10" />
                    </div>
                </div>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                    <p className="text-[11px] text-muted-foreground">
                        Le velocità (poll) si applicano al <b>RIAVVIO</b> del runner (come <span className="font-mono">LIVE_ORDER_MODE</span>).
                        Campo vuoto = nessun limite.
                    </p>
                    <Button onClick={handleSave} disabled={saving}
                        className="bg-amber-500 hover:bg-amber-400 text-black font-black disabled:opacity-40">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                        Salva
                    </Button>
                </div>
                {settings && (
                    <p className="text-[10px] text-muted-foreground">
                        Attivi: esposizione {money(settings.max_exposure_per_selection)} · ordini{' '}
                        {settings.max_orders_per_min ?? '∞'}/min · poll ordini{' '}
                        {settings.order_poll_sec ?? '—'}s · poll rischio {settings.risk_poll_sec ?? '—'}s
                    </p>
                )}
            </div>

            {/* ---------------- registro audit ---------------- */}
            <div className="border-t border-white/5 pt-4">
                <div className="flex items-center gap-2 mb-2">
                    <ScrollText className="w-4 h-4 text-muted-foreground" />
                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
                        Registro eventi ({audit.length})
                    </span>
                    {pollMs > 0 && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400/80"
                            title={`Aggiornamento automatico ogni ${(pollMs / 1000).toFixed(0)}s`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> LIVE
                        </span>
                    )}
                </div>
                {/* fix audit #27: errore del registro SEMPRE visibile (mai lista vuota muta) */}
                {auditErr && (
                    <p className="text-xs text-red-400 mb-2">
                        ⚠ Registro eventi NON aggiornato: {auditErr}
                    </p>
                )}
                {audit.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Nessun evento registrato.</p>
                ) : (
                    <div className="overflow-x-auto max-h-80 overflow-y-auto">
                        <table className="w-full text-xs">
                            <thead className="sticky top-0 bg-black/80 backdrop-blur">
                                <tr className="text-[10px] uppercase tracking-wider text-muted-foreground border-b border-white/5">
                                    <th className="text-left py-1.5 pr-2">Ora</th>
                                    <th className="text-left py-1.5 px-2">Modo</th>
                                    <th className="text-left py-1.5 px-2">Azione</th>
                                    <th className="text-left py-1.5 px-2">Mercato / sel.</th>
                                    <th className="text-left py-1.5 px-2">Lato</th>
                                    <th className="text-right py-1.5 px-2">Prezzo</th>
                                    <th className="text-right py-1.5 px-2">Size</th>
                                    <th className="text-left py-1.5 px-2">Stato</th>
                                    <th className="text-left py-1.5 pl-2">Errore</th>
                                </tr>
                            </thead>
                            <tbody>
                                {audit.map(r => (
                                    <tr key={r.id} className="border-b border-white/[0.04]">
                                        <td className="py-1.5 pr-2 font-mono text-white/60 whitespace-nowrap">{clock(r.ts)}</td>
                                        <td className="py-1.5 px-2 text-white/70 uppercase">{audCell(r.mode)}</td>
                                        <td className="py-1.5 px-2 text-white/80">{audCell(r.action)}</td>
                                        <td className="py-1.5 px-2 font-mono text-white/50 truncate max-w-[140px]">
                                            {r.market_id ? `${r.market_id}${r.selection_id != null ? ` · ${r.selection_id}` : ''}` : '—'}
                                        </td>
                                        <td className="py-1.5 px-2">
                                            {r.side
                                                ? <span className={r.side === 'back' ? 'text-sky-300' : 'text-rose-300'}>
                                                    {r.side === 'back' ? 'Back' : r.side === 'lay' ? 'Lay' : r.side}
                                                </span>
                                                : <span className="text-white/40">—</span>}
                                        </td>
                                        <td className="py-1.5 px-2 text-right font-mono text-white/70">{r.price ?? '—'}</td>
                                        <td className="py-1.5 px-2 text-right font-mono text-white/70">{r.size ?? '—'}</td>
                                        <td className={`py-1.5 px-2 font-bold ${statusTone(r.status, !!r.error)}`}>
                                            {audCell(r.status)}
                                        </td>
                                        <td className="py-1.5 pl-2 text-red-300/90 truncate max-w-[180px]" title={r.error ?? undefined}>
                                            {r.error ?? '—'}
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

export default LiveControlsPanel;
