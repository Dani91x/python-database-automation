// ============================================================================
// MissionCard — scheda operativa di UNA missione (partita): 4 righe.
//   PRE-MATCH: scalper (v1 SEMPRE dry_run) · 1T: lay CS da suggestion_ht ·
//   2T: lay CS da suggestion_ft (bloccata fino all'intervallo) · SCALP: back
//   Under per coprire il gap residuo. Footer: pausa/chiudi + trade compatti.
// MONEY-CRITICAL: ogni bottone piazza ESATTAMENTE market_id+selection_id della
// suggestion mostrata (snapshot al click, MAI derivati da indici o rimappati);
// sempre dialog di conferma; mode paper/live arriva dal toggle globale pagina.
// ============================================================================
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Bot, Info, Loader2, Lock, Pause, ShieldAlert, Square, Zap } from 'lucide-react';
import { requestManual, type OmegaMode } from '@/lib/omega';
import {
    activateScalper, stopScalper, fetchScalperState, SCALPER_PARAM_DEFAULTS,
    type ScalperControl,
} from '@/lib/scalper';
import {
    stopMission, followMission, splitEventName, missionGap, toNum,
    formatAdvisorParts, advisorTooltip,
    type MissionRow, type MissionLegKey, type MissionLeg, type MissionPhase,
} from '@/lib/omegaMissions';

// ------------------------------------------------------------------ helpers
const PHASE_ORDER: MissionPhase[] = ['pre', '1t', 'ht', '2t', 'finita'];
function phaseIdx(p: MissionPhase | null | undefined): number {
    const i = PHASE_ORDER.indexOf((p ?? 'pre') as MissionPhase);
    return i < 0 ? 0 : i;
}
function fmtEur(v: number): string {
    return `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;
}
function fmtSignedEur(v: number): string {
    return `${v < 0 ? '−' : '+'}€${Math.abs(v).toFixed(2)}`;
}
function fmtQuote(v: number | null | undefined): string {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n.toFixed(2) : '—';
}

// Stati scalper attivi (per decidere Avvia vs Ferma)
const SCALPER_ACTIVE = ['requested', 'arming', 'armed', 'running', 'stopping'];

const TRADE_BADGE: Record<string, string> = {
    pending: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    open: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
    won: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    lost: 'bg-red-500/15 text-red-300 border-red-500/40',
    void: 'bg-slate-500/15 text-slate-300 border-slate-500/40',
};
function tradeBadgeCls(status: string): string {
    return TRADE_BADGE[status] ?? 'bg-orange-500/15 text-orange-300 border-orange-500/40';
}

// Bozza d'ordine: SNAPSHOT immutabile della suggestion al momento del click.
// Il dialog conferma ESATTAMENTE questi id/prezzi (mai ricalcolati dopo).
interface PlaceDraft {
    label: string;
    phase: 'ht_cs' | 'ft_cs' | 'scalp';
    side: 'lay' | 'back';
    market_id: string;
    market_name: string | null;
    selection_id: number;
    runner_name: string | null;
    price: number;
    size: number;
}

// Rischio massimo dell'ordine: lay = size×(quota−1); back = size.
function draftRisk(d: PlaceDraft): number {
    return d.side === 'lay' ? d.size * Math.max(d.price - 1, 0) : d.size;
}

interface Props {
    mission: MissionRow;
    mode: OmegaMode;                 // dal toggle globale della pagina
    onChanged: () => void;           // ricarica dati dopo un'azione
}

export default function MissionCard({ mission, mode, onChanged }: Props) {
    const [busy, setBusy] = useState<string | null>(null);
    const [laySizeHt, setLaySizeHt] = useState(1);    // default €1 (editabile)
    const [laySizeFt, setLaySizeFt] = useState(1);
    const [draft, setDraft] = useState<PlaceDraft | null>(null);
    // preset del bot scalper:
    //   'cecchino'  = i 3 momenti (pre-match PERSIST + quiete + post-gol,
    //                 si ferma a 3 verdi) — spec utente 16/07, DEFAULT
    //   'classico'  = solo quiete pre-gol (C7)
    //   'overshoot' = solo post-gol 30-90s sul riprezzo gonfiato (C17)
    const [thetaPreset, setThetaPreset] = useState<'cecchino' | 'classico' | 'overshoot'>('cecchino');

    const phase = phaseIdx(mission.phase_now);
    const legs = mission.legs ?? {};
    const gap = missionGap(mission);

    // stato del BOT SCALPER (theta 1-tick) letto DIRETTO da scalper_control:
    // la RPC missioni espone solo pnl_locked del maker — qui servono i numeri
    // theta (colpi/green/scratch/pnl) in tempo quasi reale (poll 5s).
    const [scalperCtl, setScalperCtl] = useState<ScalperControl | null>(null);
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchScalperState(mission.event_id, 0)
                .then(s => { if (alive) setScalperCtl(s.control); })
                .catch(() => { /* servizio spento: il poll riprova */ });
        };
        load();
        const t = setInterval(load, 5_000);
        return () => { alive = false; clearInterval(t); };
    }, [mission.event_id]);
    const scalperActive = !!scalperCtl && SCALPER_ACTIVE.includes(scalperCtl.status);
    const thetaStats = (scalperCtl?.stats ?? {}) as Record<string, number | undefined>;

    // INVALIDAZIONE del dialog (review 15/07, money-critical): se mentre il
    // dialog è aperto la suggestion di riferimento cambia mercato/selezione/
    // prezzo o sparisce (fase avanzata, gamba chiusa), la bozza congelata è
    // STANTIA → si chiude il dialog e si chiede di ricontrollare. Mai lasciare
    // cliccabile un ordine basato su una fotografia superata.
    useEffect(() => {
        if (!draft) return;
        const current = draft.phase === 'ht_cs' ? mission.suggestion_ht
            : draft.phase === 'ft_cs' ? mission.suggestion_ft
            : mission.suggestion_scalp;
        const price = draft.side === 'lay'
            ? toNum((current as { lay_price?: unknown } | null)?.lay_price)
            : toNum((current as { back_price?: unknown } | null)?.back_price);
        const stale = !current
            || current.market_id !== draft.market_id
            || Number(current.selection_id) !== draft.selection_id
            || price !== draft.price;
        if (stale) {
            setDraft(null);
            toast.warning('Suggerimento aggiornato', {
                description: 'Quota o selezione cambiate mentre confermavi: ricontrolla e riprova.',
            });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mission.suggestion_ht, mission.suggestion_ft, mission.suggestion_scalp]);

    // ---------- azioni --------------------------------------------------
    // Conferma del dialog: accoda la richiesta 'place' (esegue il servizio
    // locale). Payload ESATTO dallo snapshot — money-critical.
    async function confirmPlace() {
        if (!draft) return;
        setBusy('place');
        try {
            await requestManual('place', {
                event_id: mission.event_id,
                event_name: mission.event_name,
                market_id: draft.market_id,
                selection_id: draft.selection_id,
                runner_name: draft.runner_name,
                side: draft.side,
                mode,
                price: draft.price,
                size: draft.size,
                phase: draft.phase,
            });
            // "richiesto": il servizio può ridurre la size alla liquidità reale
            // al momento dell'esecuzione — la size effettiva si vede sul trade.
            toast.success('Ordine RICHIESTO (in coda al servizio)', {
                description: `${draft.side.toUpperCase()} ${draft.runner_name ?? '—'} @ ${draft.price.toFixed(2)} · €${draft.size.toFixed(2)} richiesti · ${mode.toUpperCase()} — la size effettiva può scendere alla liquidità disponibile`,
            });
            setDraft(null);
            onChanged();
        } catch (e) {
            toast.error('Piazzamento fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(null); }
    }

    // Avvia il BOT SCALPER 1-TICK (theta, stream sub-secondo): entra quando il
    // suo semaforo dà il via, GREEN a 1 tick spalmato sui due lati, scratch,
    // gestione post-gol, poi rientra se le condizioni tornano — fino ai suoi
    // kill-switch. v1: SEMPRE paper da questa UI (gate come ScalperPanel).
    // Prerequisito: follow dell'evento (stream dedicato).
    async function handleStartScalper() {
        setBusy('scalper');
        try {
            if (!mission.followed) {
                const { home, away } = splitEventName(mission.event_name);
                await followMission(mission.event_id, home, away, mission.kickoff);
            }
            await activateScalper(mission.event_id, 'maker', true, 25, {
                ...SCALPER_PARAM_DEFAULTS,
                // stesso payload del pannello Scalper (theta_only: NON armare il maker)
                theta_mode: true,
                theta_only: true,
                theta_stake: 25,
                theta_preset: thetaPreset,
                theta_confirm_mode: 'auto',
            } as Parameters<typeof activateScalper>[4]);
            toast.success(`SCALPER 1-TICK avviato (paper, ${thetaPreset})`, {
                description: thetaPreset === 'cecchino'
                    ? `${mission.event_name ?? mission.event_id} — 3 momenti: pre-match a KO−5', quiete, post-gol · stop a 3 verdi`
                    : thetaPreset === 'overshoot'
                        ? `${mission.event_name ?? mission.event_id} — entra 30-90s DOPO il gol sul riprezzo`
                        : `${mission.event_name ?? mission.event_id} — entra nella quiete, green a 1 tick`,
            });
            onChanged();
        } catch (e) {
            toast.error('Avvio scalper fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(null); }
    }

    async function handleStopScalper() {
        setBusy('scalper');
        try {
            await stopScalper(mission.event_id);
            toast('Scalper in arresto…');
            onChanged();
        } catch (e) {
            toast.error('Stop scalper fallito', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(null); }
    }

    async function handleStopMission(close: boolean) {
        // CHIUDI è definitivo: chiedi conferma esplicita.
        if (close && !window.confirm(`Chiudere DEFINITIVAMENTE la missione su "${mission.event_name ?? mission.event_id}"?`)) return;
        setBusy('mission');
        try {
            await stopMission(mission.event_id, close);
            toast(close ? 'Missione chiusa' : 'Missione in pausa');
            onChanged();
        } catch (e) {
            toast.error('Operazione fallita', { description: String((e as Error)?.message ?? e) });
        } finally { setBusy(null); }
    }

    // ---------- righe ----------------------------------------------------
    // Riga 1T/2T: suggestion lay + bottone piazza + trade della gamba.
    function layRow(
        key: 'ht' | 'ft', title: string,
        sugg: MissionRow['suggestion_ht'], legKey: MissionLegKey,
        size: number, setSize: (n: number) => void,
    ) {
        const leg = legs[legKey] ?? null;
        const price = toNum(sugg?.lay_price);
        const canPlace = !!sugg && price > 1 && size > 0;
        // CONSULENTE DATI: segnali informativi (Poisson/lega/H2H) del punteggio
        // proposto. SOLO display: mai usato nei payload degli ordini.
        const advisorParts = formatAdvisorParts(sugg?.advisor);
        return (
            <div className="px-4 py-3 border-t border-white/5">
                <div className="flex flex-wrap items-center gap-3">
                    <span className="text-[11px] uppercase tracking-wide text-slate-400 w-16">{title}</span>
                    {sugg ? (
                        <>
                            <span className="text-sm font-bold text-rose-300">{sugg.runner_name ?? '—'}</span>
                            <span className="text-sm tabular-nums">lay @ <b>{fmtQuote(sugg.lay_price)}</b></span>
                            <span className="text-xs text-slate-400 tabular-nums">liq. €{toNum(sugg.lay_size).toFixed(0)}</span>
                            <span className="text-xs text-slate-500 truncate max-w-[180px]" title={sugg.market_name ?? ''}>{sugg.market_name ?? ''}</span>
                            <span className="ml-auto flex items-center gap-2">
                                <input
                                    type="number" min={0.5} step={0.5} value={size}
                                    onChange={e => setSize(toNum(e.target.value))}
                                    className="w-20 rounded-md bg-black/50 border border-white/10 px-2 py-1 text-sm tabular-nums"
                                    aria-label={`Size lay ${title}`}
                                />
                                <Button
                                    size="sm" disabled={!canPlace || busy === 'place'}
                                    className="bg-rose-600 hover:bg-rose-500 text-white"
                                    onClick={() => setDraft({
                                        label: title,
                                        phase: key === 'ht' ? 'ht_cs' : 'ft_cs',
                                        side: 'lay',
                                        // snapshot ESATTO della suggestion mostrata
                                        market_id: sugg.market_id,
                                        market_name: sugg.market_name,
                                        selection_id: sugg.selection_id,
                                        runner_name: sugg.runner_name,
                                        price,
                                        size: toNum(size),
                                    })}
                                >
                                    <Zap className="w-3.5 h-3.5 mr-1" />PIAZZA LAY €{toNum(size).toFixed(0)}
                                </Button>
                            </span>
                        </>
                    ) : (
                        <span className="text-xs text-slate-500 italic">nessun candidato (liquidità?)</span>
                    )}
                </div>
                {/* riga CONSULENTE DATI: piccola, sotto la proposta, tooltip con le
                    fonti. Informativa: non tocca bottoni né payload (money-critical). */}
                {sugg && advisorParts.length > 0 && (
                    <div
                        className="mt-1 flex items-center gap-1 text-[11px] text-slate-500"
                        title={advisorTooltip(sugg.advisor)}
                    >
                        <Info className="w-3 h-3 shrink-0" />
                        <span>{advisorParts.join(' · ')}</span>
                        <span className="italic text-slate-600">— dati nostri, decidi tu</span>
                    </div>
                )}
                {leg && leg.trades.length > 0 && (
                    <div className="mt-2 space-y-1">
                        {leg.trades.map(t => (
                            <div key={t.id} className="flex items-center gap-2 text-xs text-slate-300">
                                <Badge variant="outline" className={tradeBadgeCls(t.status)}>{t.status.toUpperCase()}</Badge>
                                <span className="font-medium">{t.runner_name ?? '—'}</span>
                                <span className="tabular-nums">{String(t.side).toUpperCase()} @ {fmtQuote(t.price)} · €{toNum(t.size).toFixed(2)}</span>
                                {t.mode === 'live' && <Badge variant="outline" className="bg-red-500/15 text-red-300 border-red-500/40">LIVE</Badge>}
                                <span className={`ml-auto tabular-nums font-bold ${toNum(t.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    {['won', 'lost', 'void'].includes(t.status) ? fmtSignedEur(toNum(t.pnl)) : `liab. ${fmtEur(toNum(t.liability))}`}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        );
    }

    // trade compatti di TUTTE le gambe per il footer
    const allTrades = (Object.keys(legs) as MissionLegKey[])
        .flatMap(k => ((legs[k] as MissionLeg | null)?.trades ?? []).map(t => ({ ...t, legKey: k })));

    return (
        <div className="rounded-lg border border-white/10 bg-black/30 overflow-hidden">
            {/* riga SCALP: il BOT LIVE 1-TICK (theta, stream sub-secondo).
                Entra e esce DA SOLO: green a 1 tick spalmato sui due lati,
                scratch, post-gol; rientra se le condizioni tornano. Sostituisce
                il vecchio back manuale nudo (16/07: posizione senza uscita). */}
            <div className="px-4 py-3 flex flex-wrap items-center gap-3">
                <span className="text-[11px] uppercase tracking-wide text-slate-400 w-16">Scalp</span>
                <Bot className="w-4 h-4 text-primary" />
                <span className="text-xs text-slate-400">gap</span>
                <span className={`text-sm tabular-nums font-bold ${gap <= 0 ? 'text-emerald-400' : 'text-secondary'}`}>{fmtEur(gap)}</span>
                {scalperCtl ? (
                    <>
                        <Badge variant="outline" className={scalperActive
                            ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                            : 'bg-slate-500/15 text-slate-300 border-slate-500/40'}>
                            {scalperCtl.status.toUpperCase()}
                        </Badge>
                        {scalperCtl.dry_run && <Badge variant="outline" className="bg-sky-500/15 text-sky-300 border-sky-500/40">PAPER</Badge>}
                        {/* numeri del theta: colpi/green/scratch + P&L bloccato */}
                        <span className="text-[11px] text-slate-400 tabular-nums">
                            {toNum(thetaStats.theta_shots)} colpi · {toNum(thetaStats.theta_greens)} green · {toNum(thetaStats.theta_scratches)} scratch
                        </span>
                        <span
                            className={`text-sm tabular-nums font-bold ${scalperCtl.dry_run ? 'text-slate-400' : (toNum(thetaStats.theta_pnl_locked) >= 0 ? 'text-emerald-400' : 'text-red-400')}`}
                            title={scalperCtl.dry_run ? 'P&L simulato (paper): non conta nel target' : 'P&L bloccato dallo scalper'}
                        >
                            {fmtSignedEur(toNum(thetaStats.theta_pnl_locked))}{scalperCtl.dry_run && <span className="text-[10px] font-normal"> sim</span>}
                        </span>
                    </>
                ) : (
                    <span className="text-xs text-slate-500 italic">bot non attivo su questa partita</span>
                )}
                <span className="ml-auto flex items-center gap-2">
                    {scalperActive ? (
                        <Button variant="outline" size="sm" onClick={handleStopScalper} disabled={busy === 'scalper'}>
                            {busy === 'scalper' ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Square className="w-3.5 h-3.5 mr-1" />}
                            Ferma scalper
                        </Button>
                    ) : (
                        <>
                            <select
                                value={thetaPreset}
                                onChange={e => setThetaPreset(e.target.value as 'cecchino' | 'classico' | 'overshoot')}
                                className="rounded-md bg-black/50 border border-white/10 px-2 py-1.5 text-xs"
                                aria-label="Preset scalper"
                                title="cecchino = 3 momenti: pre-match PERSIST a KO−5', quiete in-play, post-gol; stop a 3 verdi · classico = solo quiete · overshoot = solo post-gol"
                            >
                                <option value="cecchino">🎯 cecchino (3 step)</option>
                                <option value="classico">quiete (classico)</option>
                                <option value="overshoot">post-gol (overshoot)</option>
                            </select>
                            <Button size="sm" className="bg-sky-600 hover:bg-sky-500 text-white"
                                onClick={handleStartScalper} disabled={busy === 'scalper'}>
                                {busy === 'scalper' ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Zap className="w-3.5 h-3.5 mr-1" />}
                                AVVIA SCALPER 1-TICK
                            </Button>
                        </>
                    )}
                </span>
            </div>

            {/* riga 1T: visibile in pre/1t, o comunque se la gamba esiste */}
            {(phase <= phaseIdx('1t') || !!legs.ht_cs) &&
                layRow('ht', '1T', mission.suggestion_ht, 'ht_cs', laySizeHt, setLaySizeHt)}

            {/* riga 2T: bloccata fino all'intervallo */}
            {phase < phaseIdx('ht') ? (
                <div className="px-4 py-3 border-t border-white/5 flex items-center gap-3 text-xs text-slate-500">
                    <span className="text-[11px] uppercase tracking-wide text-slate-400 w-16">2T</span>
                    <Lock className="w-3.5 h-3.5" /> all'intervallo
                </div>
            ) : (
                layRow('ft', '2T', mission.suggestion_ft, 'ft_cs', laySizeFt, setLaySizeFt)
            )}

            {/* footer: pausa/chiudi + trade compatti */}
            <div className="px-4 py-3 border-t border-white/5 space-y-2">
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => handleStopMission(false)} disabled={busy === 'mission'}>
                        <Pause className="w-3.5 h-3.5 mr-1" />Pausa
                    </Button>
                    <Button variant="destructive" size="sm" onClick={() => handleStopMission(true)} disabled={busy === 'mission'}>
                        <Square className="w-3.5 h-3.5 mr-1" />Chiudi missione
                    </Button>
                    {mission.error && (
                        <span className="text-xs text-red-400 truncate" title={mission.error}>⚠ {mission.error}</span>
                    )}
                </div>
                {allTrades.length > 0 && (
                    <div className="space-y-1">
                        {allTrades.map(t => (
                            <div key={`${t.legKey}-${t.id}`} className="flex items-center gap-2 text-xs text-slate-400">
                                <span className="uppercase text-[10px] text-slate-500 w-10">{t.legKey === 'ht_cs' ? '1T' : t.legKey === 'ft_cs' ? '2T' : 'SCALP'}</span>
                                <span>{String(t.side).toUpperCase()} {t.runner_name ?? '—'} @ {fmtQuote(t.price)}</span>
                                <Badge variant="outline" className={tradeBadgeCls(t.status)}>{t.status.toUpperCase()}</Badge>
                                <span className={`ml-auto tabular-nums ${['won', 'lost', 'void'].includes(t.status)
                                    ? (toNum(t.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400')
                                    : 'text-sky-300'}`}>
                                    {['won', 'lost', 'void'].includes(t.status)
                                        ? fmtSignedEur(toNum(t.pnl))
                                        : `in gioco · rischio ${fmtEur(toNum(t.liability))}`}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* dialog conferma piazzamento — verde PAPER, ROSSO LIVE */}
            <Dialog open={!!draft} onOpenChange={o => { if (!o) setDraft(null); }}>
                <DialogContent className={`glass-card ${mode === 'live' ? 'border-red-500/40' : 'border-emerald-500/30'}`}>
                    {draft && (
                        <>
                            <DialogHeader>
                                <DialogTitle className={`flex items-center gap-2 ${mode === 'live' ? 'text-red-400' : 'text-emerald-400'}`}>
                                    {mode === 'live' ? <><ShieldAlert className="w-5 h-5" />SOLDI VERI — conferma ordine LIVE</> : <>Conferma ordine (PAPER)</>}
                                </DialogTitle>
                                <DialogDescription className="space-y-2 text-sm">
                                    <span className="block">
                                        {draft.label} · <b>{draft.side.toUpperCase()}</b> su <b>{draft.runner_name ?? '—'}</b>
                                        {draft.market_name ? <> — {draft.market_name}</> : null}
                                    </span>
                                    <span className="block tabular-nums">
                                        quota <b>{draft.price.toFixed(2)}</b> · importo <b>€{draft.size.toFixed(2)}</b>
                                    </span>
                                    <span className={`block font-bold tabular-nums ${mode === 'live' ? 'text-red-300 text-xl' : 'text-orange-300'}`}>
                                        Rischio massimo: €{draftRisk(draft).toFixed(2)}
                                    </span>
                                    {mode === 'live' && (
                                        <span className="block text-orange-300">Ordine REALE su Betfair: denaro vero.</span>
                                    )}
                                </DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                                <Button variant="ghost" onClick={() => setDraft(null)}>Annulla</Button>
                                <Button
                                    variant={mode === 'live' ? 'destructive' : 'default'}
                                    className={mode === 'live' ? '' : 'bg-emerald-600 hover:bg-emerald-500 text-white'}
                                    disabled={busy === 'place'}
                                    onClick={() => void confirmPlace()}
                                >
                                    {busy === 'place' && <Loader2 className="w-4 h-4 animate-spin mr-1" />}
                                    {mode === 'live' ? 'Sì, piazza LIVE' : 'Piazza (paper)'}
                                </Button>
                            </DialogFooter>
                        </>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
