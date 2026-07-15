// ============================================================================
// ScalperPanel — pannello SCALPER BOT (per EVENTO, montato una volta come
// XHedgePanel). Flusso:
//   1. "Attiva Scalper Bot" → form: MODALITÀ (Tradizionale = maker neutro
//      validato / Direzionale = solo lato dei motori / Entrambe), stake,
//      parametri (default VALIDATI, modificabili), interruttore ARMATO
//      (dry-run: tutto cablato, nessun ordine reale — default ON).
//   2. La richiesta va in scalper_control (RPC owner-only); il SERVIZIO locale
//      (avvia_scalper_service.bat) arma la sessione flumine e scrive stato,
//      esito del connettore motori (bias), statistiche e log.
//   3. Il pannello mostra tutto in polling (~4s): stato, consenso motori,
//      cicli/scratch/stop/P&L bloccato, feed attività per il debug.
//   Al kickoff il bot chiude tutto da solo (finestre KO validate) → 'done'.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import {
    Bot, Loader2, Play, Square, Activity, ShieldCheck, ShieldAlert,
    Gauge, Brain, TrendingUp, AlertTriangle,
} from 'lucide-react';
import {
    activateScalper, stopScalper, fetchScalperState,
    SCALPER_PARAM_DEFAULTS, SCALPER_PARAM_FIELDS,
    type ScalperMode, type ScalperParams, type ScalperState,
} from '@/lib/scalper';

interface Props {
    eventId: string;
    eventName: string;
    pollMs?: number;
}

const MODES: { key: ScalperMode; label: string; desc: string }[] = [
    { key: 'maker', label: 'Tradizionale', desc: 'Maker neutro validato: cattura lo spread dai due lati' },
    { key: 'bias', label: 'Direzionale', desc: 'Solo il lato indicato dai motori (serve consenso ML+Poisson)' },
    { key: 'both', label: 'Entrambe', desc: 'Maker neutro + direzione sulle selezioni con consenso' },
];

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
    requested: { label: 'RICHIESTO', cls: 'bg-sky-500/20 text-sky-300' },
    arming: { label: 'ARMAMENTO…', cls: 'bg-sky-500/20 text-sky-300' },
    armed: { label: 'ARMATO (in attesa)', cls: 'bg-amber-400/20 text-amber-300' },
    running: { label: 'OPERATIVO', cls: 'bg-emerald-500/20 text-emerald-300' },
    stopping: { label: 'CHIUSURA…', cls: 'bg-amber-400/20 text-amber-300' },
    stopped: { label: 'FERMATO', cls: 'bg-white/10 text-white/60' },
    done: { label: 'COMPLETATO (KO)', cls: 'bg-white/10 text-white/60' },
    error: { label: 'ERRORE', cls: 'bg-red-500/20 text-red-300' },
};

const num = (v: unknown, dflt = 0): number =>
    typeof v === 'number' && Number.isFinite(v) ? v : dflt;

export function ScalperPanel({ eventId, eventName, pollMs = 4000 }: Props) {
    const [state, setState] = useState<ScalperState | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [showForm, setShowForm] = useState(false);

    // ---- form di attivazione (default VALIDATI) ----
    const [mode, setMode] = useState<ScalperMode>('maker');
    const [dryRun, setDryRun] = useState(true);
    const [htMode, setHtMode] = useState(false);
    // MISSIONE "2 Tick" (il prodotto): 1 verde pre-match + 1 nell'intervallo,
    // poi stop di fase. Default ON; quando ON forza anche ht_mode (il tick
    // in-play si fa SOLO nella finestra intervallo certificata).
    const [missionTwoTicks, setMissionTwoTicks] = useState(
        SCALPER_PARAM_DEFAULTS.one_green_per_phase);
    // SNIPER in-play (bibbia §6, config S16): 1 tick sull'Under al momento
    // letto dal book (cadenza+coda+spread), poi stop. Alternativo a ht_mode.
    const [sniperMode, setSniperMode] = useState(false);
    const [sniperStake, setSniperStake] = useState(10);
    // CACCIA MULTI-LINEA (F4, 11/07): canne parallele (dinamica +2) +
    // multi-colpo (cap 10, cooldown 120s) + nessun tetto profitto. Conteggio
    // 10/07: +1.28 €/partita vs +0.10 mono (n=1) — da VALIDARE in paper
    // prima dei soldi veri (registro ipotesi §11 bibbia).
    const [sniperHunt, setSniperHunt] = useState(false);
    // THETA in-play (dossier 15/07, verdetto S4 16/07): scalping post-gol
    // guidato dall'Atlante hazard. NON validato out-of-sample → v1 SOLO PAPER
    // (dry_run obbligatorio, gate in handleActivate). Mutuamente esclusivo
    // con sniper/HT. theta_confirm_mode NON esposto: si manda SEMPRE 'auto'
    // (la UI delle conferme manuali non esiste: 'manual' bloccherebbe il bot).
    const [thetaMode, setThetaMode] = useState(false);
    const [thetaStake, setThetaStake] = useState(25);
    const [thetaPreset, setThetaPreset] = useState<'classico' | 'overshoot'>('classico');
    // stringa vuota = "usa il default del backend" (max_shots 10, loss_cap 5)
    const [thetaMaxShots, setThetaMaxShots] = useState<string>('');
    const [thetaLossCap, setThetaLossCap] = useState<string>('');
    const [stake, setStake] = useState(25);
    const [params, setParams] = useState<ScalperParams>({ ...SCALPER_PARAM_DEFAULTS });
    const busyRef = useRef(false);

    const refresh = useCallback(async () => {
        try {
            const s = await fetchScalperState(eventId);
            setState(s);
        } catch {
            /* transitorio: il polling riprova */
        } finally {
            setLoading(false);
        }
    }, [eventId]);

    useEffect(() => {
        setLoading(true);
        void refresh();
        const t = setInterval(() => void refresh(), pollMs);
        return () => clearInterval(t);
    }, [refresh, pollMs]);

    const ctrl = state?.control ?? null;
    const active = !!ctrl && ['requested', 'arming', 'armed', 'running', 'stopping'].includes(ctrl.status);
    const heartbeatFresh = useMemo(() => {
        if (!ctrl?.heartbeat_at) return false;
        return Date.now() - new Date(ctrl.heartbeat_at).getTime() < 30_000;
    }, [ctrl?.heartbeat_at]);

    const handleActivate = useCallback(async () => {
        if (busyRef.current) return;
        // Gate THETA (v1): NON validato out-of-sample → può armarsi SOLO in
        // paper. Con dry_run spento si blocca qui, prima di ogni conferma.
        if (thetaMode && !dryRun) {
            toast.error(
                'THETA solo PAPER: non validato out-of-sample (verdetto S4). ' +
                'Riattiva "Solo ARMATO (nessun ordine reale)" per armarlo.',
            );
            return;
        }
        // Gate money-critical: armare con ORDINI REALI attiva un agente
        // autonomo che piazza scommesse vere non presidiato → conferma
        // esplicita (stessa asimmetria del bot tennis / 1-click LIVE).
        if (!dryRun) {
            const huntWarn = (sniperMode && sniperHunt)
                ? '\n⚠️ CACCIA MULTI-LINEA ATTIVA: cella NON ancora validata ' +
                  'out-of-sample (n=1) — la bibbia prescrive prima il PAPER.\n'
                : '';
            const ok = window.confirm(
                `⚠️ ATTIVARE LO SCALPER CON ORDINI REALI su "${eventName}"?\n\n` +
                    `Il bot piazzerà scommesse REALI su Betfair in autonomia (stake €${stake}).\n` +
                    huntWarn +
                    `Confermi?`,
            );
            if (!ok) return;
        }
        busyRef.current = true;
        setBusy(true);
        try {
            // missione ON → one_green_per_phase=true. La gamba HT NON è più
            // forzata dalla missione (backtest di validazione 11/07: 3/13
            // intervalli con verde, aggregato −1.74€): resta OPT-IN esplicito.
            await activateScalper(eventId, mode, dryRun, stake, {
                ...params,
                one_green_per_phase: missionTwoTicks,
                ht_mode: htMode,
                sniper_mode: sniperMode,
                sniper_stake: sniperStake,
                // caccia multi-linea: parametri del conteggio 10/07 (F6);
                // assenti = S16 mono certificata, nessun cambio di default
                ...(sniperMode && sniperHunt ? {
                    sniper_parallel_lines: 2,
                    sniper_max_shots: 10,
                    sniper_cooldown_s: 120,
                    sniper_profit_target: 0,
                } : {}),
                // THETA in-play: chiavi presenti SOLO col toggle acceso.
                // confirm_mode SEMPRE 'auto' (niente UI conferme → 'manual'
                // lascerebbe il bot in attesa di conferme che nessuno dà).
                // max_shots/loss_cap vuoti = default del backend (10 / 5€).
                ...(thetaMode ? {
                    theta_mode: true,
                    theta_stake: thetaStake,
                    theta_preset: thetaPreset,
                    theta_confirm_mode: 'auto' as const,
                    ...(thetaMaxShots !== '' && Number.isFinite(Number(thetaMaxShots))
                        ? { theta_max_shots: Number(thetaMaxShots) } : {}),
                    ...(thetaLossCap !== '' && Number.isFinite(Number(thetaLossCap))
                        ? { theta_loss_cap: Number(thetaLossCap) } : {}),
                } : {}),
            } as Partial<ScalperParams> & {
                ht_mode: boolean; sniper_mode: boolean; sniper_stake: number;
            });
            toast.success(`Scalper ${dryRun ? 'ARMATO (nessun ordine)' : 'ATTIVATO'} — ${eventName}`);
            setShowForm(false);
            void refresh();
        } catch (e) {
            toast.error(`Attivazione fallita: ${e instanceof Error ? e.message : e}`);
        } finally {
            busyRef.current = false;
            setBusy(false);
        }
    }, [eventId, eventName, mode, dryRun, stake, params, htMode, missionTwoTicks,
        sniperMode, sniperStake, sniperHunt, thetaMode, thetaStake, thetaPreset,
        thetaMaxShots, thetaLossCap, refresh]);

    const handleStop = useCallback(async () => {
        if (busyRef.current) return;
        busyRef.current = true;
        setBusy(true);
        try {
            await stopScalper(eventId);
            // niente promesse: la chiusura è in corso, l'esito lo dice lo stato
            toast.success('Stop richiesto: chiusura flat in corso… se una posizione resta aperta comparirà un errore');
            void refresh();
        } catch (e) {
            toast.error(`Stop fallito: ${e instanceof Error ? e.message : e}`);
        } finally {
            busyRef.current = false;
            setBusy(false);
        }
    }, [eventId, refresh]);

    // ------------------------------------------------------------------ UI
    if (loading) {
        return (
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 flex items-center gap-2 text-white/50 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" /> Scalper Bot…
            </div>
        );
    }

    const st = ctrl ? STATUS_STYLE[ctrl.status] ?? STATUS_STYLE.stopped : null;
    const stats = ctrl?.stats ?? null;
    const meta = ctrl?.bias_meta ?? null;

    return (
        <div className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-3">
            {/* intestazione */}
            <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                    <Bot className="h-5 w-5 text-emerald-400" />
                    <span className="font-bold text-white">Scalper Bot</span>
                    <span className="text-xs text-white/40">pre-match · stop automatico al KO</span>
                </div>
                <div className="flex items-center gap-2">
                    {ctrl && st && <Badge className={`${st.cls} border-transparent font-bold`}>{st.label}</Badge>}
                    {ctrl && ctrl.status === 'running' && (
                        heartbeatFresh
                            ? <Badge className="bg-emerald-500/15 text-emerald-300 border-transparent">servizio ✓</Badge>
                            : <Badge className="bg-red-500/15 text-red-300 border-transparent">servizio assente?</Badge>
                    )}
                    {ctrl?.dry_run && active && (
                        <Badge className="bg-amber-400/20 text-amber-300 border-transparent font-bold">
                            ARMATO — nessun ordine
                        </Badge>
                    )}
                </div>
            </div>

            {/* CTA principale */}
            {!active && !showForm && (
                <Button
                    onClick={() => setShowForm(true)}
                    className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-black"
                >
                    <Play className="h-4 w-4 mr-2" /> Attiva Scalper Bot
                </Button>
            )}

            {/* form di attivazione */}
            {!active && showForm && (
                <div className="space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                        {MODES.map(m => (
                            <button
                                key={m.key}
                                type="button"
                                onClick={() => setMode(m.key)}
                                className={`rounded-lg border p-2 text-left transition ${
                                    mode === m.key
                                        ? 'border-emerald-400 bg-emerald-500/10'
                                        : 'border-white/10 bg-white/5 hover:bg-white/10'
                                }`}
                            >
                                <div className="text-sm font-bold text-white">{m.label}</div>
                                <div className="text-[11px] text-white/50 leading-tight">{m.desc}</div>
                            </button>
                        ))}
                    </div>

                    <div className="flex items-center gap-3 flex-wrap">
                        <label className="flex items-center gap-2 text-sm text-white/80">
                            <span className="text-white/50">Stake €</span>
                            <Input
                                type="number" min={2} max={500} step={1} value={stake}
                                onChange={e => setStake(Math.max(2, Math.min(500, Number(e.target.value) || 2)))}
                                className="w-24 h-8 bg-white/5 border-white/10 text-white"
                            />
                        </label>
                        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                            <Checkbox checked={dryRun} onCheckedChange={v => setDryRun(v === true)} />
                            <span className={dryRun ? 'text-amber-300 font-semibold' : 'text-white/60'}>
                                Solo ARMATO (nessun ordine reale)
                            </span>
                        </label>
                        <label className="flex items-center gap-2 text-xs cursor-pointer">
                            <Checkbox
                                checked={missionTwoTicks}
                                onCheckedChange={v => setMissionTwoTicks(v === true)}
                            />
                            <span className={missionTwoTicks ? 'text-emerald-300 font-semibold' : 'text-white/60'}>
                                Missione Tick Pre-Match: al primo ciclo verde il bot smette di aprire
                                (validato: 5/6 eventi col tick in 3-27 min, zero eventi rossi).
                            </span>
                        </label>
                        <label className="flex items-center gap-2 text-xs cursor-pointer">
                            <Checkbox
                                checked={htMode}
                                onCheckedChange={v => {
                                    setHtMode(v === true);
                                    if (v === true) { setSniperMode(false); setThetaMode(false); }
                                }}
                            />
                            <span className={htMode ? 'text-amber-300 font-semibold' : 'text-white/60'}>
                                ⚠️ Gamba INTERVALLO (HT, sperimentale): il backtest di validazione la boccia
                                (3/13 intervalli col verde, aggregato −1.74€). Solo nazionali liquide, mai elite.
                            </span>
                        </label>
                        <label className="flex items-center gap-2 text-xs cursor-pointer">
                            <Checkbox
                                checked={sniperMode}
                                onCheckedChange={v => {
                                    setSniperMode(v === true);
                                    if (v === true) { setHtMode(false); setThetaMode(false); }
                                }}
                            />
                            <span className={sniperMode ? 'text-sky-300 font-semibold' : 'text-white/60'}>
                                🎯 SNIPER in-play (S16): 1 tick sull&apos;Under al momento letto dal book
                                (cadenza+coda+spread), poi stop. Backtest: +0.99€/14 eventi, worst −0.49.
                                In dry-run mostra solo i trigger. Alternativo alla gamba HT.
                            </span>
                        </label>
                        {sniperMode && (
                            <label className="flex items-center gap-2 text-sm text-white/80">
                                <span className="text-white/50">Stake sniper €</span>
                                <Input
                                    type="number" min={2} max={100} step={1} value={sniperStake}
                                    onChange={e => setSniperStake(Math.max(2, Math.min(100, Number(e.target.value) || 2)))}
                                    className="w-20 h-8 bg-white/5 border-white/10 text-white"
                                />
                            </label>
                        )}
                        {sniperMode && (
                            <label className="flex items-center gap-2 text-xs cursor-pointer">
                                <Checkbox
                                    checked={sniperHunt}
                                    onCheckedChange={v => setSniperHunt(v === true)}
                                />
                                <span className={sniperHunt ? 'text-emerald-300 font-semibold' : 'text-white/60'}>
                                    🔫 CACCIA MULTI-LINEA: spara su dinamica +2 linee sopra,
                                    multi-colpo PER LINEA (cap 10/linea, cooldown 120s/linea),
                                    nessun tetto profitto. Conteggio 10/07: +1.28 vs +0.10
                                    €/partita (n=1) — VALIDARE IN PAPER prima dei soldi veri.
                                    Semaforo post-gol e cap globale evento sempre attivi.
                                </span>
                            </label>
                        )}
                        <label className="flex items-center gap-2 text-xs cursor-pointer">
                            <Checkbox
                                checked={thetaMode}
                                onCheckedChange={v => {
                                    setThetaMode(v === true);
                                    if (v === true) { setSniperMode(false); setHtMode(false); }
                                }}
                            />
                            <span className={thetaMode ? 'text-violet-300 font-semibold' : 'text-white/60'}>
                                🔬 THETA in-play (sperimentale): scalp post-gol sull&apos;Under
                                guidato dall&apos;Atlante hazard (coppia atomica entry+green,
                                scratch a tempo). Alternativo a Sniper e gamba HT.
                                ⚠️ Theta NON validato out-of-sample (verdetto S4: classico EV−,
                                overshoot da campionare) — SOLO PAPER: armalo esclusivamente
                                con dry_run attivo.
                            </span>
                        </label>
                        {thetaMode && (
                            <>
                                <label className="flex items-center gap-2 text-sm text-white/80">
                                    <span className="text-white/50">Stake theta €</span>
                                    <Input
                                        type="number" min={2} max={500} step={1} value={thetaStake}
                                        onChange={e => setThetaStake(Math.max(2, Math.min(500, Number(e.target.value) || 2)))}
                                        className="w-20 h-8 bg-white/5 border-white/10 text-white"
                                    />
                                </label>
                                <label className="flex items-center gap-2 text-sm text-white/80">
                                    <span className="text-white/50">Preset</span>
                                    <select
                                        value={thetaPreset}
                                        onChange={e => setThetaPreset(e.target.value === 'overshoot' ? 'overshoot' : 'classico')}
                                        className="h-8 rounded-md border border-white/10 bg-white/5 px-2 text-sm text-white [&>option]:bg-slate-900"
                                    >
                                        <option value="classico">classico (C7)</option>
                                        <option value="overshoot">overshoot (C17)</option>
                                    </select>
                                </label>
                                <label className="flex items-center gap-2 text-sm text-white/80">
                                    <span className="text-white/50">Max colpi</span>
                                    <Input
                                        type="number" min={1} max={50} step={1} placeholder="10"
                                        value={thetaMaxShots}
                                        onChange={e => setThetaMaxShots(e.target.value)}
                                        className="w-20 h-8 bg-white/5 border-white/10 text-white"
                                    />
                                </label>
                                <label className="flex items-center gap-2 text-sm text-white/80">
                                    <span className="text-white/50">Tetto perdita €</span>
                                    <Input
                                        type="number" min={0} max={100} step={0.5} placeholder="5"
                                        value={thetaLossCap}
                                        onChange={e => setThetaLossCap(e.target.value)}
                                        className="w-20 h-8 bg-white/5 border-white/10 text-white"
                                    />
                                </label>
                            </>
                        )}
                        {!dryRun && (
                            <span className="flex items-center gap-1 text-xs text-red-300 font-bold">
                                <ShieldAlert className="h-4 w-4" /> ORDINI REALI
                            </span>
                        )}
                    </div>

                    {/* parametri: default VALIDATI, modificabili */}
                    <details className="rounded-lg border border-white/10 bg-black/20 p-2">
                        <summary className="text-xs font-bold text-white/70 cursor-pointer">
                            Parametri (default validati in backtest)
                        </summary>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
                            {SCALPER_PARAM_FIELDS.map(f => (
                                <label key={f.key} className="text-[11px] text-white/50" title={f.hint}>
                                    {f.label}
                                    <Input
                                        type="number" step={f.step} min={f.min} max={f.max}
                                        value={params[f.key]}
                                        onChange={e => {
                                            const v = Number(e.target.value);
                                            if (Number.isFinite(v)) {
                                                setParams(p => ({ ...p, [f.key]: v }));
                                            }
                                        }}
                                        className="h-8 mt-0.5 bg-white/5 border-white/10 text-white"
                                    />
                                </label>
                            ))}
                        </div>
                        <button
                            type="button"
                            onClick={() => setParams({ ...SCALPER_PARAM_DEFAULTS })}
                            className="mt-2 text-[11px] text-emerald-300 hover:underline"
                        >
                            Ripristina i default validati
                        </button>
                    </details>

                    <div className="flex gap-2">
                        <Button
                            onClick={handleActivate}
                            disabled={busy}
                            className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-black"
                        >
                            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4 mr-2" />}
                            {dryRun ? 'Arma il bot (dry-run)' : 'Attiva ORDINI REALI'}
                        </Button>
                        <Button variant="secondary" onClick={() => setShowForm(false)} disabled={busy}>
                            Annulla
                        </Button>
                    </div>
                </div>
            )}

            {/* stato attivo: connettore + statistiche + stop */}
            {active && ctrl && (
                <div className="space-y-3">
                    <div className="flex items-center gap-2 text-xs text-white/60 flex-wrap">
                        <Badge variant="secondary" className="font-bold">
                            {MODES.find(m => m.key === ctrl.mode)?.label ?? ctrl.mode}
                        </Badge>
                        <span>stake €{ctrl.stake}</span>
                        {ctrl.error && (
                            <span className="flex items-center gap-1 text-red-300">
                                <AlertTriangle className="h-3.5 w-3.5" /> {ctrl.error}
                            </span>
                        )}
                    </div>

                    {/* esito del connettore motori (solo bias/both) */}
                    {ctrl.mode !== 'maker' && (
                        <div className="rounded-lg border border-white/10 bg-black/20 p-2 text-xs">
                            <div className="flex items-center gap-1.5 font-bold text-white/80 mb-1">
                                <Brain className="h-4 w-4 text-violet-300" /> Motori
                                {meta?.consenso
                                    ? <Badge className="bg-violet-500/20 text-violet-300 border-transparent">consenso: {meta?.direzione}</Badge>
                                    : <Badge variant="secondary">nessun consenso → neutro</Badge>}
                                {typeof meta?.edge === 'number' && (
                                    <span className="text-white/50">edge {(meta.edge * 100).toFixed(1)}%</span>
                                )}
                            </div>
                            {(meta?.motivi ?? []).map((r, i) => (
                                <div key={i} className="text-white/50">• {r}</div>
                            ))}
                        </div>
                    )}

                    {/* statistiche */}
                    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-center">
                        {[
                            { l: ctrl.dry_run ? 'Quote (dry)' : 'Ordini', v: ctrl.dry_run ? num(stats?.dry_quotes) : num(stats?.orders_placed), i: Activity },
                            { l: 'Cicli', v: num(stats?.cycles) + num(stats?.flattens), i: Gauge },
                            { l: 'Catture', v: num(stats?.scalps) + num(stats?.roundtrips), i: TrendingUp },
                            { l: 'Scratch', v: num(stats?.scratches), i: Activity },
                            { l: 'Stop', v: num(stats?.stops), i: Square },
                            { l: 'P&L bloccato', v: `€${num(stats?.pnl_locked).toFixed(2)}`, i: TrendingUp },
                        ].map((s, i) => (
                            <div key={i} className="rounded-lg bg-white/5 border border-white/10 p-2">
                                <div className="text-[10px] uppercase text-white/40">{s.l}</div>
                                <div className="text-sm font-black text-white">{s.v}</div>
                            </div>
                        ))}
                    </div>

                    {/* missione "2 Tick": contabilità per fase (se il bot la espone) */}
                    {stats && (stats.greens_prematch !== undefined || stats.greens_inplay !== undefined) && (
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                            {[
                                {
                                    l: 'Tick pre-match',
                                    v: num(stats.greens_prematch) >= 1 ? '✓' : '—',
                                    ok: num(stats.greens_prematch) >= 1,
                                },
                                {
                                    l: 'Tick intervallo',
                                    v: num(stats.greens_inplay) >= 1 ? '✓' : '—',
                                    ok: num(stats.greens_inplay) >= 1,
                                },
                                {
                                    l: 'P&L pre-match',
                                    v: `€${num(stats.pnl_prematch).toFixed(2)}`,
                                    ok: num(stats.pnl_prematch) > 0,
                                },
                                {
                                    l: 'P&L intervallo',
                                    v: `€${num(stats.pnl_inplay).toFixed(2)}`,
                                    ok: num(stats.pnl_inplay) > 0,
                                },
                            ].map((s, i) => (
                                <div key={i} className="rounded-lg bg-white/5 border border-white/10 p-2">
                                    <div className="text-[10px] uppercase text-white/40">{s.l}</div>
                                    <div className={`text-sm font-black ${s.ok ? 'text-emerald-300' : 'text-white'}`}>{s.v}</div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* THETA in-play: contatori dedicati (scalper_session riversa
                        theta.stats nel control con prefisso theta_*) — visibili
                        SOLO se il theta è armato e il bot li espone */}
                    {stats && (stats.theta_shots !== undefined || stats.theta_pnl_locked !== undefined) && (
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center">
                            {[
                                { l: 'Theta colpi', v: num(stats.theta_shots) },
                                { l: 'Theta verdi', v: num(stats.theta_greens) },
                                { l: 'Theta scratch', v: num(stats.theta_scratches) },
                                { l: 'Theta dry-fire', v: num(stats.theta_dry_fires) },
                                { l: 'P&L theta', v: `€${num(stats.theta_pnl_locked).toFixed(2)}` },
                            ].map((s, i) => (
                                <div key={i} className="rounded-lg bg-violet-500/5 border border-violet-400/20 p-2">
                                    <div className="text-[10px] uppercase text-violet-300/60">{s.l}</div>
                                    <div className="text-sm font-black text-white">{s.v}</div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* feed attività (debug veloce) */}
                    <div className="max-h-40 overflow-y-auto rounded-lg border border-white/10 bg-black/30 p-2 space-y-1">
                        {(state?.activity ?? []).length === 0 && (
                            <div className="text-xs text-white/40">Nessuna attività ancora…</div>
                        )}
                        {(state?.activity ?? []).map(a => (
                            <div key={a.id} className="text-[11px] font-mono text-white/60">
                                <span className="text-white/35">{new Date(a.ts).toLocaleTimeString('it-IT')}</span>{' '}
                                <span className={
                                    a.kind === 'error' ? 'text-red-300 font-bold'
                                    : a.kind === 'cycle' ? 'text-emerald-300 font-bold'
                                    : a.kind === 'stop' ? 'text-amber-300'
                                    : 'text-white/70'
                                }>{a.kind}</span>{' '}
                                {JSON.stringify(a.payload)}
                            </div>
                        ))}
                    </div>

                    <Button
                        onClick={handleStop}
                        disabled={busy || ctrl.status === 'stopping'}
                        variant="destructive"
                        className="w-full font-black"
                    >
                        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4 mr-2" />}
                        Ferma lo scalper (chiude flat)
                    </Button>
                </div>
            )}

            {/* esito ultima sessione (fermato/completato/errore) */}
            {!active && ctrl && ['stopped', 'done', 'error'].includes(ctrl.status) && !showForm && (
                <div className="text-xs text-white/50">
                    Ultima sessione: <b className="text-white/80">{STATUS_STYLE[ctrl.status]?.label}</b>
                    {ctrl.stats && (
                        <> — cicli {num(ctrl.stats.cycles) + num(ctrl.stats.flattens)},
                        catture {num(ctrl.stats.scalps) + num(ctrl.stats.roundtrips)},
                        P&L bloccato €{num(ctrl.stats.pnl_locked).toFixed(2)}</>
                    )}
                    {ctrl.error && <span className="text-red-300"> — {ctrl.error}</span>}
                </div>
            )}
        </div>
    );
}
