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
import { BetfairMediaButtons } from '@/components/BetfairMediaButtons';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Bot, Info, Loader2, Lock, Pause, ShieldAlert, Square, Zap } from 'lucide-react';
import { requestManual, isReconciling, terminalError, omegaReasonText, type OmegaMode } from '@/lib/omega';
import { fmtMoney, fmtOdds } from '@/lib/format';
import { statusMeta, scalperStatusMeta } from '@/lib/tradeStatus';
import {
    activateScalper, stopScalper, fetchScalperState, SCALPER_PARAM_DEFAULTS,
    type ScalperControl,
} from '@/lib/scalper';
import {
    stopMission, followMission, splitEventName, missionGap, toNum,
    formatAdvisorParts, advisorTooltip,
    type MissionRow, type MissionLegKey, type MissionLeg, type MissionPhase,
} from '@/lib/omegaMissions';
import { csSelection, type CalcioScanPayload } from '@/lib/safeStrategyScan';

// ------------------------------------------------------------------ helpers
const PHASE_ORDER: MissionPhase[] = ['pre', '1t', 'ht', '2t', 'finita'];
function phaseIdx(p: MissionPhase | null | undefined): number {
    const i = PHASE_ORDER.indexOf((p ?? 'pre') as MissionPhase);
    return i < 0 ? 0 : i;
}
// formati UNICI del design system (niente "€12.50" accanto a "12,50 €")
function fmtEur(v: number): string {
    return fmtMoney(v);
}
function fmtSignedEur(v: number): string {
    return fmtMoney(v, { signed: true });
}
function fmtQuote(v: number | null | undefined): string {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? fmtOdds(n) : '—';
}

// Stati scalper attivi (per decidere Avvia vs Ferma)
const SCALPER_ACTIVE = ['requested', 'arming', 'armed', 'running', 'stopping'];

/**
 * M-07 — stato di una gamba della missione: etichetta ITALIANA (prima era la
 * chiave del DB in maiuscolo: "HEDGED", "ERROR") e, sopra tutto, la
 * riconciliazione e le righe terminali, che NON sono un normale "in gioco".
 */
export function missionTradeStatus(t: {
    status: string; meta?: Record<string, unknown> | null;
}): { label: string; cls: string } {
    // §19: la parola e il colore li decide la mappa CONDIVISA (lib/tradeStatus),
    // compresa la precedenza esito certo > terminale > riconciliazione.
    return statusMeta(t.status, {
        reconciling: isReconciling(t.meta),
        terminal: terminalError(t.meta) != null,
    });
}

/**
 * M-07 — cosa scrivere a destra della gamba: una gamba COPERTA ha un P&L
 * bloccato (non è "in gioco"), una in ERRORE non ha nessun rischio vivo.
 */
export function missionTradeValue(t: {
    status: string; pnl?: number | null; liability?: number | null; meta?: Record<string, unknown> | null;
    closes_trade_id?: number | null;
}): { text: string; tone: 'pos' | 'neg' | 'plain' | 'risk' } {
    if (['won', 'lost', 'void'].includes(t.status)) {
        const v = toNum(t.pnl);
        return { text: fmtSignedEur(v), tone: v >= 0 ? 'pos' : 'neg' };
    }
    if (terminalError(t.meta)) return { text: 'nessun ordine reale', tone: 'plain' };
    // audit 12/09: una gamba di CHIUSURA (cash out / green-up) non è un rischio
    // in più — il suo stake copre l'apertura; prima diceva «rischio 24,24 €»
    // accanto all'apertura già coperta (rischio contato due volte)
    // CERT. 12/09 (review) — solo una chiusura ANCORA VIVA e' "in corso": una
    // gamba di chiusura in errore o annullata NON sta coprendo niente, e
    // chiamarla "chiusura in corso" nascondeva che la posizione sotto e'
    // ancora esposta.
    if (t.closes_trade_id != null) {
        if (t.status === 'error' || t.status === 'cancelled') {
            return { text: 'chiusura NON riuscita', tone: 'neg' };
        }
        return { text: 'chiusura in corso', tone: 'plain' };
    }
    const raw = (t.meta ?? {})['locked_pnl'];
    const locked = raw == null || raw === '' ? NaN : Number(raw);
    if (Number.isFinite(locked)) {
        return { text: `bloccato ${fmtSignedEur(locked)}`, tone: locked >= 0 ? 'pos' : 'neg' };
    }
    if (t.status === 'hedged') {
        // 'hedged' senza locked_pnl leggibile: bloccato SÌ, importo ignoto — mai
        // inventare «+0,00 €»
        return { text: 'bloccato (importo non disponibile)', tone: 'plain' };
    }
    return { text: `rischio ${fmtEur(toNum(t.liability))}`, tone: 'risk' };
}

const VALUE_CLS: Record<'pos' | 'neg' | 'plain' | 'risk', string> = {
    pos: 'text-emerald-400', neg: 'text-red-400', plain: 'text-slate-400', risk: 'text-orange-300',
};

// Bozza d'ordine: SNAPSHOT immutabile di mercato/selezione/size al momento del
// click. Il dialog conferma ESATTAMENTE questi id (mai rimappati). Il PREZZO
// (09/09 sera) è quello LIVE del feed scanner al momento della CONFERMA quando
// la selezione è nel feed (Correct Score in stream), altrimenti quello della
// suggestion: mai un prezzo più vecchio di quello mostrato nel dialog.
interface PlaceDraft {
    label: string;
    phase: 'ht_cs' | 'ft_cs' | 'scalp';
    side: 'lay' | 'back';
    market_id: string;
    market_name: string | null;
    selection_id: number;
    runner_name: string | null;
    /** prezzo della suggestion al click (riferimento se il feed non copre la selezione) */
    price: number;
    size: number;
}

// Rischio massimo dell'ordine: lay = size×(quota−1); back = size.
function draftRisk(d: PlaceDraft, price: number): number {
    return d.side === 'lay' ? d.size * Math.max(price - 1, 0) : d.size;
}

interface Props {
    mission: MissionRow;
    mode: OmegaMode;                 // dal toggle globale della pagina
    onChanged: () => void;           // ricarica dati dopo un'azione
    /** payload live dello scanner per l'evento (punteggio 2s, CS in stream); null = assente */
    live?: CalcioScanPayload | null;
    /**
     * CERT. 12/09 — `updated_at` della riga del feed dell'evento: e' l'unico
     * modo per sapere se la "quota live" mostrata e' davvero di adesso.
     * `useScanLiveFeed` butta via questo campo, quindi la card lo riceve dal
     * pannello (`useScanLiveFeedRows`). `undefined`/null = eta' NON verificabile:
     * la card smette di dichiarare "live" un prezzo che non puo' datare.
     */
    liveAt?: string | null;
    /**
     * §18 — stato del bot SCALPER dell'evento, letto dal PANNELLO con un solo
     * poll per tutte le card. `undefined` = nessuno lo gestisce (la card usa un
     * poll proprio, più lento); `null` = letto e assente.
     */
    scalper?: ScalperControl | null;
}

/** oltre questa eta' la quota del feed NON e' piu' "di adesso" (come Safe/Mike) */
export const MISSION_LIVE_STALE_S = 20;

/** aliquota Betfair usata SOLO per l'anteprima dell'incasso nel dialog */
export const MISSION_COMMISSION = 0.05;

/** minimo REALE dell'Exchange italiano per una BANCATA (lay) */
export const MISSION_MIN_LAY_STAKE = 0.5;

export default function MissionCard({ mission, mode, onChanged, live = null, liveAt = null, scalper }: Props) {
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

    // QUOTA LIVE di una selezione lay dal feed scanner (solo mercato CORRECT_SCORE:
    // è quello che lo scanner tiene in stream). null = feed assente per quella
    // selezione → si usa il prezzo della suggestion.
    // CERT. 12/09 — eta' VERA della riga del feed. Senza, la card mostrava un
    // pallino verde pulsante e la scritta "quota live dal feed scanner" su un
    // prezzo che poteva essere fermo da minuti (lo scanner scrive on-change e
    // `CalcioScanPayload` non porta timestamp). `null` = non verificabile.
    const liveAgeS = liveAt ? Math.max(0, Math.round((Date.now() - Date.parse(liveAt)) / 1000)) : null;
    const liveVerified = liveAgeS != null && Number.isFinite(liveAgeS);
    const liveStale = liveVerified && liveAgeS > MISSION_LIVE_STALE_S;
    const liveLay = (marketId: string | null | undefined, selectionId: number | null | undefined): { price: number; size: number } | null => {
        if (!live?.cs || !marketId || selectionId == null) return null;
        if (String(live.cs.market_id ?? '') !== String(marketId)) return null;
        // mercato SOSPESO/CHIUSO: il suo ultimo prezzo non e' un prezzo operabile
        const mkStatus = String((live.cs as { status?: unknown }).status ?? 'OPEN').toUpperCase();
        if (mkStatus && mkStatus !== 'OPEN') return null;
        // feed fermo: meglio nessuna quota "live" che una quota morta col bollino
        if (liveStale) return null;
        const sel = csSelection(live, Number(selectionId));
        const price = toNum(sel?.lay);
        if (!sel || !(price > 1)) return null;
        const selStatus = String((sel as { runner_status?: unknown }).runner_status ?? 'ACTIVE').toUpperCase();
        if (selStatus && selStatus !== 'ACTIVE') return null;
        return { price, size: toNum(sel.lay_size) };
    };
    // prezzo EFFETTIVO della bozza: live se disponibile, altrimenti quello al click
    const draftPrice = (d: PlaceDraft): number =>
        d.side === 'lay' ? (liveLay(d.market_id, d.selection_id)?.price ?? d.price) : d.price;

    // stato del BOT SCALPER (theta 1-tick) letto DIRETTO da scalper_control:
    // la RPC missioni espone solo pnl_locked del maker — qui servono i numeri
    // theta (colpi/green/scratch/pnl) in tempo quasi reale (poll 5s).
    // §18: il poll è UNO SOLO, a livello di PANNELLO (MissionPanel lo passa in
    // `scalper`): prima ogni card aperta teneva il proprio setInterval a 5 s e
    // dieci missioni facevano dieci RPC al secondo non sincronizzate. La card
    // resta usabile da sola (nessun prop) con un poll di cortesia più lento.
    const [ownCtl, setOwnCtl] = useState<ScalperControl | null>(null);
    const managed = scalper !== undefined;
    useEffect(() => {
        if (managed) return;                 // il pannello ci pensa lui
        let alive = true;
        const load = () => {
            fetchScalperState(mission.event_id, 0)
                .then(s => { if (alive) setOwnCtl(s.control); })
                .catch(() => { /* servizio spento: il poll riprova */ });
        };
        load();
        const t = setInterval(load, 15_000);
        return () => { alive = false; clearInterval(t); };
    }, [mission.event_id, managed]);
    const scalperCtl = managed ? (scalper ?? null) : ownCtl;
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
        // con il feed live la quota del dialog segue il mercato in tempo reale:
        // un cambio della sola quota di suggestion NON invalida (sarebbe un
        // dialog che si chiude da solo a ogni tick); mercato/selezione cambiati
        // o suggestion sparita restano invalidanti
        const hasLive = draft.side === 'lay' && liveLay(draft.market_id, draft.selection_id) !== null;
        const stale = !current
            || current.market_id !== draft.market_id
            || Number(current.selection_id) !== draft.selection_id
            || (!hasLive && price !== draft.price);
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
        // prezzo alla CONFERMA = quello mostrato nel dialog in quell'istante (live se
        // il feed copre la selezione): mai un prezzo più vecchio di quello visto
        const price = draftPrice(draft);
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
                price,
                size: draft.size,
                phase: draft.phase,
            });
            // "richiesto": il servizio può ridurre la size alla liquidità reale
            // al momento dell'esecuzione — la size effettiva si vede sul trade.
            toast.success('Ordine RICHIESTO (in coda al servizio)', {
                description: `${draft.side.toUpperCase()} ${draft.runner_name ?? '—'} @ ${fmtOdds(price)} · ${fmtEur(draft.size)} richiesti · ${mode.toUpperCase()} — la size effettiva può scendere alla liquidità disponibile`,
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
        // quota LIVE dal feed scanner (Correct Score in stream): quando c'è,
        // è quella mostrata E quella che verrà confermata nel dialog
        const lv = sugg ? liveLay(sugg.market_id, sugg.selection_id) : null;
        // CERT. 12/09 — LIQUIDITA': il servizio TAGLIA in silenzio la size a
        // quella disponibile (omega_service `_manual_place`). Un lay da 25 € su
        // 3 € di book diventa una copertura che non copre. `null` = size non
        // pubblicata: non si blocca, ma si dichiara che non e' verificabile.
        const rawLiq = lv ? lv.size : sugg?.lay_size;
        const liq = rawLiq == null || !Number.isFinite(Number(rawLiq)) ? null : Number(rawLiq);
        const shownPrice = lv ? lv.price : price;
        const placeBlock = !sugg ? 'nessun candidato'
            : !(shownPrice > 1) ? 'quota non valida'
                : !(size > 0) ? 'importo non valido'
                    : size < MISSION_MIN_LAY_STAKE ? `sotto il minimo Betfair (${fmtEur(MISSION_MIN_LAY_STAKE)})`
                        : liq != null && liq <= 0 ? 'nessuna liquidità al miglior prezzo'
                            : liq != null && size > liq + 0.005
                                ? `liquidità ${fmtEur(liq)} < importo ${fmtEur(size)}: il servizio taglierebbe la size`
                                : liveStale
                                    ? `quote del feed ferme da ${liveAgeS}s: nessun ordine su prezzi fantasma`
                                    : null;
        const canPlace = placeBlock == null;
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
                            <span
                                className="text-sm tabular-nums"
                                data-testid="mission-lay-price"
                                title={lv && liveVerified
                                    ? `quota live dal feed scanner (stream Betfair), riga di ${liveAgeS}s fa`
                                    : lv
                                        ? 'quota dal feed scanner: eta\u2019 della riga NON verificabile, potrebbe non essere quella di adesso'
                                        : liveStale
                                            ? `feed fermo da ${liveAgeS}s: quota dell'ultimo ciclo del servizio`
                                            : 'quota del ciclo del servizio (questa selezione non e\u2019 nel feed in stream)'}
                            >
                                lay @ <b>{fmtQuote(shownPrice)}</b>
                                {/* il bollino verde PULSANTE dichiarava "adesso" anche su un
                                    feed fermo: ora compare solo con l'eta' VERIFICATA e fresca */}
                                {/* il bollino verde e' una DICHIARAZIONE di realtime: senza
                                    l'eta' verificata della riga non si puo' fare. */}
                                {lv && liveVerified
                                    ? <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse align-middle" aria-hidden />
                                    : <span className="ml-1 text-[10px] text-amber-300/80" data-testid="mission-lay-price-age">
                                        {liveStale ? `feed fermo ${liveAgeS}s` : liveVerified ? '' : 'et\u00e0 n/d'}
                                    </span>}
                            </span>
                            <span
                                className={`text-xs tabular-nums ${liq != null && size > liq + 0.005 ? 'text-amber-300' : 'text-slate-400'}`}
                                data-testid="mission-lay-liq"
                                title="importo abbinabile al miglior prezzo lay"
                            >
                                liq. {liq != null ? fmtEur(liq) : '\u2014 (non pubblicata)'}
                            </span>
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
                                    {/* CERT. 12/09 — `decimals: 0` sul bottone che SPENDE:
                                        1,50 € veniva annunciato come "2 €". */}
                                    <Zap className="w-3.5 h-3.5 mr-1" />PIAZZA LAY {fmtEur(toNum(size))}
                                </Button>
                            </span>
                        </>
                    ) : (
                        <span className="text-xs text-slate-500 italic">nessun candidato (liquidità?)</span>
                    )}
                </div>
                {sugg && placeBlock && (
                    <div className="mt-1 text-[11px] text-amber-300" data-testid="mission-place-block">{placeBlock}</div>
                )}
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
                {/* audit 12/09: riepilogo della GAMBA con gli STESSI nomi dei KPI
                    in cima alla pagina (rischio vivo / bloccato / in verifica),
                    così la scheda non racconta una storia diversa. Campi della
                    RPC v6: `open_liability` è già il rischio VIVO (0 a copertura
                    completa), `locked_pnl` il P&L già bloccato. */}
                {leg && (toNum(leg.open_liability) > 0 || leg.locked_pnl != null || toNum(leg.reconciling_liability) > 0) && (
                    <div className="mt-2 text-[11px] text-slate-400 flex flex-wrap gap-x-3 tabular-nums" data-testid="mission-leg-risk">
                        {toNum(leg.open_liability) > 0 && (
                            <span title="quanto perdi se esce il risultato bancato di questa gamba (copertura completa = 0)">
                                rischio vivo <b className="text-orange-300">{fmtEur(toNum(leg.open_liability))}</b>
                            </span>
                        )}
                        {leg.locked_pnl != null && (
                            <span title="P&L già bloccato dalla copertura: non cambia più, si incassa al fischio finale">
                                bloccato <b className={toNum(leg.locked_pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtSignedEur(toNum(leg.locked_pnl))}</b>
                            </span>
                        )}
                        {toNum(leg.reconciling_liability) > 0 && (
                            <span className="text-fuchsia-300" title="ordine reale a esito ancora ignoto: conta nel rischio finché Betfair non risponde">
                                di cui in verifica su Betfair <b>{fmtEur(toNum(leg.reconciling_liability))}</b>
                            </span>
                        )}
                    </div>
                )}
                {leg && leg.trades.length > 0 && (
                    <div className="mt-2 space-y-1">
                        {leg.trades.map(t => {
                            const st = missionTradeStatus(t);
                            const val = missionTradeValue(t);
                            const isClosing = t.closes_trade_id != null;
                            return (
                                <div key={t.id} className={`flex items-center gap-2 text-xs ${isClosing ? 'text-teal-200 pl-3' : 'text-slate-300'}`} data-testid="mission-leg-trade" data-closes={isClosing ? String(t.closes_trade_id) : undefined}>
                                    {isClosing && <span className="text-teal-300" aria-hidden title="gamba di chiusura dell'apertura sopra (cash out / green-up)">↳ chiusura</span>}
                                    <Badge variant="outline" className={st.cls} data-testid="mission-trade-status">{st.label}</Badge>
                                    <span className="font-medium">{t.runner_name ?? '—'}</span>
                                    <span className="tabular-nums">{String(t.side).toUpperCase()} @ {fmtQuote(t.price)} · {fmtEur(toNum(t.size))}</span>
                                    {t.minute_at_entry != null && (
                                        <span className="text-[10px] text-slate-500 tabular-nums" title="minuto e punteggio all'ingresso">
                                            ingr. {t.minute_at_entry}′{t.score_at_entry ? ` · ${t.score_at_entry}` : ''}
                                        </span>
                                    )}
                                    {t.mode === 'live' && <Badge variant="outline" className="bg-red-500/15 text-red-300 border-red-500/40">LIVE</Badge>}
                                    <span className={`ml-auto tabular-nums font-bold ${VALUE_CLS[val.tone]}`} data-testid="mission-trade-value">
                                        {val.text}
                                    </span>
                                </div>
                            );
                        })}
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
                        {/* §5.3: etichetta ITALIANA dello stato (mai la chiave
                            inglese in maiuscolo sotto gli occhi del trader) */}
                        <Badge variant="outline" className={scalperStatusMeta(scalperCtl.status).cls} data-testid="mission-scalper-status">
                            {scalperStatusMeta(scalperCtl.status).label}
                        </Badge>
                        {scalperCtl.dry_run && <Badge variant="outline" className="bg-sky-500/15 text-sky-300 border-sky-500/40">PAPER</Badge>}
                        {/* numeri del theta: colpi/green/scratch + P&L bloccato.
                            In PAPER il bot NON simula i fill: annuncia le
                            decisioni → il contatore che si muove e' SEGNALI.
                            ⚠️ P&L LORDO (flumine non detrae la commissione
                            4,5-5%), a differenza delle gambe Omega (nette). */}
                        <span className="text-[11px] text-slate-400 tabular-nums">
                            {scalperCtl.dry_run && <>{toNum(thetaStats.theta_dry_fires)} segnali · </>}
                            {toNum(thetaStats.theta_shots)} colpi · {toNum(thetaStats.theta_greens)} green · {toNum(thetaStats.theta_scratches)} scratch
                            {thetaStats.theta_pnl_settled !== undefined && (
                                <span title="P&L LORDO dei soli colpi regolati: commissione NON detratta"> · settl. {fmtSignedEur(toNum(thetaStats.theta_pnl_settled))} lordo</span>
                            )}
                        </span>
                        <span
                            className={`text-sm tabular-nums font-bold ${scalperCtl.dry_run ? 'text-slate-400' : (toNum(thetaStats.theta_pnl_locked) >= 0 ? 'text-emerald-400' : 'text-red-400')}`}
                            title={scalperCtl.dry_run
                                ? 'P&L simulato (paper), LORDO (commissione non detratta): non conta nel target'
                                : 'P&L bloccato dallo scalper — LORDO: commissione Betfair (4,5-5%) NON detratta, a differenza delle gambe Omega (nette)'}
                        >
                            {/* CERT. 12/09 — statistica ASSENTE non e' "+0,00 €":
                                lo stesso file vieta di inventare uno zero. */}
                            {thetaStats.theta_pnl_locked === undefined ? '—' : fmtSignedEur(toNum(thetaStats.theta_pnl_locked))}
                            <span className="text-[10px] font-normal"> lordo{scalperCtl.dry_run && ' · sim'}</span>
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
                        <span className="text-xs text-red-400 truncate" title={mission.error} data-testid="mission-error">
                            {/* mai la chiave del servizio in snake_case sotto gli occhi del trader */}
                            ⚠ {omegaReasonText(mission.error) ?? mission.error}
                        </span>
                    )}
                    {/* video live + statistiche Betfair (sessione web utente) */}
                    <BetfairMediaButtons compact eventId={mission.event_id} className="ml-auto" />
                </div>
                {allTrades.length > 0 && (
                    <div className="space-y-1">
                        {allTrades.map(t => {
                            const st = missionTradeStatus(t);
                            const val = missionTradeValue(t);
                            const isClosing = t.closes_trade_id != null;
                            return (
                                <div key={`${t.legKey}-${t.id}`} className="flex items-center gap-2 text-xs text-slate-400" data-testid="mission-footer-trade" data-closes={isClosing ? String(t.closes_trade_id) : undefined}>
                                    <span className="uppercase text-[10px] text-slate-500 w-10">{t.legKey === 'ht_cs' ? '1T' : t.legKey === 'ft_cs' ? '2T' : 'SCALP'}</span>
                                    {isClosing && <span className="text-teal-300" aria-hidden>↳ chiusura</span>}
                                    <span>{String(t.side).toUpperCase()} {t.runner_name ?? '—'} @ {fmtQuote(t.price)}</span>
                                    <Badge variant="outline" className={st.cls} data-testid="mission-trade-status">{st.label}</Badge>
                                    <span className={`ml-auto tabular-nums ${VALUE_CLS[val.tone]}`} data-testid="mission-trade-value">
                                        {val.text}
                                    </span>
                                </div>
                            );
                        })}
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
                                        quota <b>{fmtQuote(draftPrice(draft))}</b>
                                        {draft.side === 'lay' && liveLay(draft.market_id, draft.selection_id) && (
                                            liveVerified
                                                ? <span className="text-emerald-300 text-xs"> (live, {liveAgeS}s fa)</span>
                                                : <span className="text-amber-300 text-xs"> (dal feed, età non verificabile)</span>
                                        )}
                                        {' '}· importo <b>{fmtEur(draft.size)}</b>
                                    </span>
                                    <span className={`block font-bold tabular-nums ${mode === 'live' ? 'text-red-300 text-xl' : 'text-orange-300'}`}>
                                        Rischio massimo: {fmtEur(draftRisk(draft, draftPrice(draft)))}
                                    </span>
                                    {/* CERT. 12/09 — c'era SOLO il lato negativo: il dialog
                                        va letto sapendo anche cosa si incassa, al NETTO della
                                        commissione Betfair del 5% sul vincente. */}
                                    <span className="block tabular-nums text-emerald-300" data-testid="mission-draft-net">
                                        Se vinci incassi ≈ {fmtEur(draft.side === 'lay'
                                            ? draft.size * (1 - MISSION_COMMISSION)
                                            : draft.size * (draftPrice(draft) - 1) * (1 - MISSION_COMMISSION))}
                                        <span className="text-[11px] text-slate-400"> (netto commissione {Math.round(MISSION_COMMISSION * 100)} %)</span>
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
