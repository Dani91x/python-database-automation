// ============================================================================
// ManualPanel — modalità MANUALE di Omega: scegli evento → mercato → selezione
// → target/importo/quota/mode e piazza UN lay (o back). DB-as-bus: le richieste
// vanno in coda e le esegue il servizio locale (avvia_omega_service.bat).
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { RefreshCw, Download, Zap, Target, Loader2, ShieldAlert } from 'lucide-react';
import { useScanLiveFeed, liveScoreLabel } from '@/lib/useScanLiveFeed';
import {
    requestManual, fetchOmegaEvents, fetchOmegaMarket, fetchManualRequests,
    filterEventsInWindow, eventsCacheUpdatedAt,
    omegaReasonText,
    type OmegaEvent, type OmegaMarketSnapshot, type OmegaMarketRunner,
    type OmegaMode, type OmegaSide, type OmegaManualRequest,
} from '@/lib/omega';
import { fmtMoney, fmtOdds, fmtTime, fmtDateTime, fmtAge, ageSeconds, DASH } from '@/lib/format';
import { romeDay } from '@/lib/dailyHistory';

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

/** oltre questa età le quote del book NON si usano per piazzare */
export const MANUAL_BOOK_STALE_S = 20;

/** CERT. 12/09 — minimi REALI dell'Exchange italiano, per lato: una puntata
 *  (back) sotto 2,00 € viene rifiutata da Betfair anche se Omega la accetta
 *  (`omega_config.min_stake` vale 0,50 e non distingue il lato). Sotto il
 *  minimo l'ordine LIVE non entra e la riserva resta da riconciliare. */
export const OMEGA_MIN_STAKE: Record<OmegaSide, number> = { back: 2, lay: 0.5 };

/** stato Betfair di una selezione, in italiano: mai la costante inglese nuda */
export function runnerStatusLabel(status: unknown): string {
    const s = String(status ?? '').trim().toUpperCase();
    if (s === 'REMOVED') return 'RITIRATA';
    if (s === 'WINNER') return 'VINCENTE';
    if (s === 'LOSER') return 'PERDENTE';
    if (s === '' || s === 'ACTIVE') return 'ATTIVA';
    return 'NON ATTIVA';
}

function fmtQuote(v: number | null): string {
    return fmtOdds(v);
}

/** stato di una richiesta in coda, in ITALIANO (prima era la chiave del DB) */
export const MANUAL_STATUS_LABEL: Record<string, string> = {
    pending: 'IN CODA', processing: 'IN CORSO', done: 'ESEGUITA', error: 'FALLITA',
};
/** tipo di richiesta, in ITALIANO */
export const MANUAL_KIND_LABEL: Record<string, string> = {
    refresh_events: 'aggiorna eventi',
    load_markets: 'carica mercati',
    load_book: 'carica quote',
    place: 'piazza ordine',
    cashout: 'cash out',
};
const CLS_OK = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40';
const CLS_WARN = 'bg-amber-500/15 text-amber-300 border-amber-500/40';
const CLS_ERR = 'bg-red-500/15 text-red-300 border-red-500/40';
const CLS_IDLE = 'bg-slate-500/15 text-slate-300 border-slate-500/40';

function num(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}

/**
 * Stato ed esito di una richiesta della coda, come lo deve leggere un trader.
 *
 * CERT. 12/09 — `done` del servizio NON vuol dire "ordine eseguito": Omega
 * chiude `done` anche quando l'ordine e' solo ACCODATO su flumine
 * (`result.pending_fill=true`, esito IGNOTO) e quando la size e' stata TAGLIATA
 * alla liquidita' disponibile. Mostrare "ESEGUITA" verde in quei casi fa
 * credere di avere una posizione che potrebbe non esserci (o essere piu'
 * piccola), e invita a ripiazzare raddoppiando l'esposizione.
 */
export function manualRequestText(r: {
    kind: string; status: string; result: Record<string, unknown> | null;
    payload?: Record<string, unknown> | null;
}): {
    kind: string; status: string; detail: string | null; cls: string;
} {
    const res = r.result ?? {};
    const raw = [res.error, res.err, res.reason].find((v) => v != null && String(v).trim() !== '');
    // mai la chiave del servizio in inglese/snake_case sotto gli occhi del
    // trader: il dizionario italiano di Omega esiste gia' (omegaReasonText)
    let detail = raw != null ? (omegaReasonText(raw) ?? String(raw)) : null;
    let status = MANUAL_STATUS_LABEL[r.status] ?? 'STATO SCONOSCIUTO';
    let cls = r.status === 'done' ? CLS_OK
        : r.status === 'error' ? CLS_ERR
        : r.status === 'processing' ? CLS_WARN
        : CLS_IDLE;
    if (r.status === 'done' && r.kind === 'place') {
        const asked = num(res.requested_size ?? (res.payload as Record<string, unknown> | undefined)?.size);
        const got = num(res.size ?? res.placed_size);
        if (res.pending_fill === true) {
            status = 'IN ATTESA DI ABBINAMENTO';
            cls = CLS_WARN;
            detail = detail ?? "ordine accodato: l'abbinamento non e' ancora confermato";
        } else if (res.reduced === true || (asked != null && got != null && got < asked - 0.005)) {
            status = 'ABBINATA IN PARTE';
            cls = CLS_WARN;
            detail = got != null && asked != null
                ? `piazzati ${fmtMoney(got)} dei ${fmtMoney(asked)} richiesti`
                : (detail ?? 'importo ridotto alla liquidita disponibile');
        }
    }
    // ⚠️ 17/09 — NON OGNI `cashout` DI QUESTA CODA E' UN COMANDO TUO.
    // Dalla stessa coda passano le USCITE PROPOSTE DAL BOT che hai approvato
    // (la RPC porta la riga da 'proposed' a 'pending' e ci scrive `approved_at`).
    // Chiamarle «cash out» come il bottone farebbe credere di averle decise tu,
    // e nello storico le due cose non si distinguerebbero piu'.
    const kind = eUnaUscitaApprovata(r.payload)
        ? 'uscita proposta dal bot, approvata'
        : MANUAL_KIND_LABEL[r.kind] ?? r.kind;
    return { kind, status, detail, cls };
}

/** La richiesta in coda e' l'APPROVAZIONE di una proposta del bot? */
export function eUnaUscitaApprovata(payload: Record<string, unknown> | null | undefined): boolean {
    if (!payload) return false;
    return payload.approved_at != null || payload.motivo_codice != null
        || payload.approvata_da != null;
}

/**
 * Orario di una richiesta in coda: l'ORA sola basta solo se la richiesta è di
 * OGGI. Audit 12/09: l'elenco mostrava "15:30 cash out" sopra "17:13 piazza
 * ordine" — sembrava fuori ordine, in realtà le 17:13 erano di tre giorni prima.
 */
export function manualRequestWhen(iso: string, today: string = romeDay()): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return fmtTime(iso);
    return romeDay(d) === today ? fmtTime(iso) : fmtDateTime(iso);
}

interface ManualPanelProps {
    /**
     * Modalità della PAGINA (toggle globale PAPER/LIVE). Audit 12/09: il
     * pannello partiva SEMPRE da 'paper' anche con la pagina in LIVE: due
     * modalità diverse nella stessa schermata. Resta scavalcabile qui, ma la
     * differenza va dichiarata.
     */
    pageMode?: OmegaMode;
}

export default function ManualPanel({ pageMode = 'paper' }: ManualPanelProps) {
    const [events, setEvents] = useState<OmegaEvent[]>([]);
    // minuto/punteggio LIVE dal feed dello scanner accanto a ogni evento in-play
    const liveFeed = useScanLiveFeed(events.map((e) => e.event_id));
    const [eventId, setEventId] = useState('');
    const [marketId, setMarketId] = useState('');
    const [snapshot, setSnapshot] = useState<OmegaMarketSnapshot | null>(null);
    const [sel, setSel] = useState<OmegaMarketRunner | null>(null);

    const [side, setSide] = useState<OmegaSide>('lay');
    const [mode, setMode] = useState<OmegaMode>(pageMode);
    // il toggle globale della pagina comanda anche qui finché l'operatore non
    // sceglie diversamente in questa schermata (poi lo scarto è dichiarato)
    const [modeTouched, setModeTouched] = useState(false);
    useEffect(() => { if (!modeTouched) setMode(pageMode); }, [pageMode, modeTouched]);
    function pickMode(m: OmegaMode) { setModeTouched(true); setMode(m); }
    const [sizeMode, setSizeMode] = useState<'target' | 'stake'>('target');
    const [target, setTarget] = useState(5);
    const [stake, setStake] = useState(1);
    const [price, setPrice] = useState<number | ''>('');

    const [busy, setBusy] = useState<string | null>(null);
    const [requests, setRequests] = useState<OmegaManualRequest[]>([]);
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
    // orologio della pagina: serve per l'ETÀ delle quote (un ordine su un book
    // vecchio si esegue a un prezzo che l'operatore non ha visto)
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        const t = window.setInterval(() => setNowMs(Date.now()), 2000);
        return () => window.clearInterval(t);
    }, []);
    const bookAgeS = ageSeconds(snapshot?.updated_at ?? null, nowMs);
    const bookStale = snapshot != null && (bookAgeS == null || bookAgeS > MANUAL_BOOK_STALE_S);

    const selectedEvent = useMemo(() => events.find(e => e.event_id === eventId) ?? null, [events, eventId]);
    const markets = selectedEvent?.markets ?? [];
    /**
     * Audit 12/09 — SOLO le partite della finestra operativa, la stessa
     * definizione della scheda Missione (lib/omega.eventIsOperable). Il menu
     * offriva 73 partite di tre giorni prima, tutte già finite: un ordine
     * manuale su quei mercati è un ordine su un mercato chiuso.
     */
    const windowEvents = useMemo(() => filterEventsInWindow(events, nowMs), [events, nowMs]);
    const cacheAt = useMemo(() => eventsCacheUpdatedAt(events), [events]);
    const cacheAgeS = ageSeconds(cacheAt, nowMs);
    const cacheStale = events.length > 0 && windowEvents.length === 0;
    const today = romeDay();

    async function loadEvents() {
        try { setEvents(await fetchOmegaEvents()); } catch { /* servizio offline: ok */ }
    }
    async function loadRequests() {
        try { setRequests(await fetchManualRequests(10)); } catch { /* ignore */ }
    }

    useEffect(() => {
        loadEvents(); loadRequests();
        const t = setInterval(() => { loadEvents(); loadRequests(); }, 8000);
        return () => clearInterval(t);
    }, []);

    // ---- azioni (accodano la richiesta; il servizio la esegue) ----
    async function doRefreshEvents() {
        setBusy('events');
        try {
            await requestManual('refresh_events');
            toast('Aggiornamento eventi richiesto', { description: 'Il servizio Omega deve essere in esecuzione.' });
            // confronto su fetch FRESCO (non sullo state React: stale closure →
            // il loop non usciva mai in anticipo e lo spinner durava sempre 12s)
            const before = events.length;
            for (let i = 0; i < 8; i++) {
                await sleep(1500);
                const fresh = await fetchOmegaEvents().catch(() => null);
                if (fresh) { setEvents(fresh); if (fresh.length !== before) break; }
            }
        } catch (e) { toast.error('Richiesta fallita', { description: String((e as Error).message) }); }
        finally { setBusy(null); }
    }

    async function doLoadMarkets() {
        if (!eventId) return;
        setBusy('markets');
        try {
            await requestManual('load_markets', { event_id: eventId });
            toast('Caricamento mercati richiesto');
            for (let i = 0; i < 10; i++) {
                await sleep(1500); await loadEvents();
                const ev = (await fetchOmegaEvents()).find(e => e.event_id === eventId);
                if (ev && ev.markets.length > 0) { setEvents(prev => prev.map(p => p.event_id === eventId ? ev : p)); break; }
            }
        } catch (e) { toast.error('Richiesta fallita', { description: String((e as Error).message) }); }
        finally { setBusy(null); }
    }

    async function doLoadBook() {
        if (!marketId) return;
        setBusy('book');
        setSnapshot(null); setSel(null);
        try {
            await requestManual('load_book', { market_id: marketId, event_id: eventId });
            toast('Caricamento quote richiesto');
            for (let i = 0; i < 12; i++) {
                await sleep(1500);
                const snap = await fetchOmegaMarket(marketId);
                if (snap && snap.runners.length > 0) { setSnapshot(snap); break; }
            }
        } catch (e) { toast.error('Richiesta fallita', { description: String((e as Error).message) }); }
        finally { setBusy(null); }
    }

    function pickRunner(r: OmegaMarketRunner, s: OmegaSide = side) {
        setSel(r);
        setPrice(s === 'lay' ? (r.lay_price ?? '') : (r.back_price ?? ''));
    }

    /** CERT. 12/09 — cambiando BACK/LAY il prezzo DEVE seguire il lato: prima
     *  restava quello dell'altro lato e si finiva per mandare un BACK al prezzo
     *  lay (in live: FOK ucciso; se abbinasse, a un prezzo pessimo). */
    function pickSide(s: OmegaSide) {
        setSide(s);
        if (sel) setPrice(s === 'lay' ? (sel.lay_price ?? '') : (sel.back_price ?? ''));
    }

    // helper: suggerisci il punteggio MENO probabile (quota lay più alta in [20,120])
    function suggestLeastProbable() {
        if (!snapshot) return;
        const cand = snapshot.runners
            .filter(r => r.lay_price != null && r.lay_price >= 20 && r.lay_price <= 120 && /^\d+\s*-\s*\d+$/.test(r.name))
            .sort((a, b) => (b.lay_price ?? 0) - (a.lay_price ?? 0));
        if (cand.length === 0) { toast('Nessun punteggio in fascia [20,120]'); return; }
        setSide('lay'); pickRunner(cand[0], 'lay');
        toast.success(`Suggerito: lay ${cand[0].name} @ ${fmtQuote(cand[0].lay_price)}`);
    }

    async function doPlace() {
        if (!sel || !marketId) { toast.error('Seleziona un runner'); return; }
        if (price === '' || Number(price) <= 0) { toast.error('Imposta una quota valida'); return; }
        setBusy('place');
        try {
            await requestManual('place', {
                event_id: eventId || marketId,
                event_name: selectedEvent?.name ?? snapshot?.event_name ?? null,
                market_id: marketId,
                selection_id: sel.selection_id,
                runner_name: sel.name,
                side, mode,
                price: Number(price),
                size: sizeMode === 'stake' ? Number(stake) : null,
                target: sizeMode === 'target' ? Number(target) : null,
            });
            toast.success('Ordine manuale accodato', {
                description: `${side.toUpperCase()} ${sel.name} @ ${fmtOdds(Number(price))} · ${mode === 'live' ? 'LIVE (soldi veri)' : 'PAPER'} · mercato ${marketId} · selezione ${sel.selection_id}`,
            });
            await loadRequests();
        } catch (e) {
            toast.error('Piazzamento fallito', {
                description: `${String((e as Error).message)} — mercato ${marketId}, selezione ${sel.selection_id}`,
            });
        }
        finally { setBusy(null); }
    }

    // liability stimata mostrata all'utente
    // Anteprima COERENTE col backend (money-critical): LAY e BACK hanno matematica
    // diversa a "target". Commissione indicativa 5% (il backend usa i params reali).
    const PREVIEW_COMM = 0.05;
    const pPrice = Number(price) || 0;
    let previewStake: number;
    if (sizeMode === 'stake') {
        previewStake = Number(stake);
    } else if (side === 'back') {
        const denom = (pPrice - 1) * (1 - PREVIEW_COMM);
        previewStake = denom > 0 ? Number(target) / denom : 0;
    } else {
        previewStake = Number(target) / (1 - PREVIEW_COMM);
    }
    // Rischio massimo: LAY = stake·(quota−1); BACK = stake.
    // CERT. 12/09 — con la quota vuota `pPrice` vale 0 e (pPrice−1) è NEGATIVO:
    // il pannello mostrava "Liability aperta ≈ −5,26 €" (dump reale delle 17:00),
    // cioè un rischio negativo che sembra un credito. Sotto quota 1 non esiste
    // un'anteprima: si dice "—".
    const priceValid = pPrice > 1;
    const previewLiability = side === 'lay'
        ? previewStake * Math.max(pPrice - 1, 0)
        : previewStake;
    const previewOk = priceValid && Number.isFinite(previewStake) && previewStake > 0;
    const previewText = previewOk ? fmtMoney(previewLiability) : DASH;
    const previewStakeText = previewOk ? fmtMoney(previewStake) : DASH;

    // CERT. 12/09 — GUARDIE D'INGRESSO: il bottone che spende non deve accendersi
    // su un ordine che il servizio taglia in silenzio (liquidità) o che Betfair
    // rifiuta (sotto il minimo del lato).
    const minStake = OMEGA_MIN_STAKE[side];
    const availAtBest = sel ? (side === 'lay' ? sel.lay_size : sel.back_size) : null;
    const avail = availAtBest != null && Number.isFinite(Number(availAtBest)) ? Number(availAtBest) : null;
    const belowMin = previewOk && previewStake < minStake - 0.005;
    const overBook = previewOk && avail != null && avail > 0 && previewStake > avail + 0.005;
    const placeBlock = !sel ? 'scegli una selezione dal book'
        : !priceValid ? 'imposta una quota maggiore di 1'
            : bookStale ? 'quote non aggiornate: premi "Carica quote del mercato"'
                : belowMin ? `sotto il minimo Betfair per il ${side.toUpperCase()} (${fmtMoney(minStake)}): l'ordine verrebbe rifiutato`
                    : avail != null && avail <= 0 ? 'nessun importo abbinabile al miglior prezzo'
                        : overBook ? `abbinabili solo ${fmtMoney(avail)} al miglior prezzo: ${fmtMoney(previewStake)} non entrerebbero tutti (il servizio taglia la size alla liquidità)`
                            : null;

    return (
        <div className="space-y-4">
            {/* avviso servizio */}
            <Card className="glass-card border-amber-500/20 p-3 text-xs text-amber-200/90">
                Le azioni qui accodano richieste eseguite dal <b>servizio locale</b> (avvia_omega_service.bat).
                In <b>PAPER</b> è simulato; in <b>LIVE</b> sono soldi veri. Se non vedi eventi/quote, avvia prima il servizio.
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* colonna sinistra: selezione evento/mercato */}
                <Card className="glass-card border-white/10 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-300">1 · Evento</span>
                        <Button variant="outline" size="sm" onClick={doRefreshEvents} disabled={busy === 'events'}>
                            {busy === 'events' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                            <span className="ml-1">Aggiorna eventi</span>
                        </Button>
                    </div>
                    <select value={eventId} onChange={e => { setEventId(e.target.value); setMarketId(''); setSnapshot(null); setSel(null); }}
                        className="w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm">
                        <option value="">— scegli evento ({windowEvents.length}) —</option>
                        {windowEvents.map(ev => (
                            <option key={ev.event_id} value={ev.event_id}>
                                {ev.name || ev.event_id}{ev.open_date ? ` · ${fmtTime(ev.open_date)}` : ''}{liveScoreLabel(liveFeed[ev.event_id]) ? ` · LIVE ${liveScoreLabel(liveFeed[ev.event_id])}` : ''}
                            </option>
                        ))}
                    </select>
                    <div className="text-[11px]" data-testid="manual-events-note">
                        {cacheStale ? (
                            <span className="text-amber-300">
                                nessuna partita nella finestra operativa: l'elenco è fermo
                                {cacheAgeS != null ? ` da ${fmtAge(cacheAgeS)}` : ''} e contiene solo partite finite —
                                premi "Aggiorna eventi" con il servizio acceso
                            </span>
                        ) : (
                            <span className="text-slate-500">
                                solo le partite ancora operabili (non finite)
                                {cacheAgeS != null ? ` · elenco di ${fmtAge(cacheAgeS)} fa` : ''}
                                {' · '}
                                <span title="minuto e punteggio arrivano dal feed Betfair con 2-3 s di ritardo sul campo: controllali prima di piazzare">
                                    minuto e punteggio LIVE con 2-3 s di ritardo
                                </span>
                            </span>
                        )}
                    </div>

                    <div className="flex items-center justify-between pt-1">
                        <span className="text-sm text-slate-300">2 · Mercato</span>
                        <Button variant="outline" size="sm" onClick={doLoadMarkets} disabled={!eventId || busy === 'markets'}>
                            {busy === 'markets' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                            <span className="ml-1">Carica mercati</span>
                        </Button>
                    </div>
                    <select value={marketId} onChange={e => { setMarketId(e.target.value); setSnapshot(null); setSel(null); }}
                        disabled={markets.length === 0}
                        className="w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm disabled:opacity-50">
                        <option value="">— scegli mercato ({markets.length}) —</option>
                        {markets.map(mk => (
                            <option key={mk.market_id} value={mk.market_id}>
                                {mk.market_name}{mk.market_type ? ` [${mk.market_type}]` : ''}
                            </option>
                        ))}
                    </select>

                    <Button variant="outline" size="sm" onClick={doLoadBook} disabled={!marketId || busy === 'book'} className="w-full">
                        {busy === 'book' ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Download className="w-3.5 h-3.5 mr-1" />}
                        3 · Carica quote del mercato
                    </Button>
                </Card>

                {/* colonna destra: parametri ordine */}
                <Card className="glass-card border-white/10 p-4 space-y-3">
                    <span className="text-sm text-slate-300">4 · Ordine</span>

                    <div className="flex gap-2">
                        <div className="flex rounded-md border border-white/10 overflow-hidden text-xs font-bold flex-1">
                            <button onClick={() => pickSide('back')} className={`flex-1 py-1.5 ${side === 'back' ? 'bg-sky-500/25 text-sky-300' : 'text-slate-400'}`}>BACK</button>
                            <button onClick={() => pickSide('lay')} className={`flex-1 py-1.5 ${side === 'lay' ? 'bg-rose-500/25 text-rose-300' : 'text-slate-400'}`}>LAY</button>
                        </div>
                        <div className="flex rounded-md border border-white/10 overflow-hidden text-xs font-bold flex-1">
                            <button onClick={() => pickMode('paper')} className={`flex-1 py-1.5 ${mode === 'paper' ? 'bg-emerald-500/25 text-emerald-300' : 'text-slate-400'}`}>PAPER</button>
                            <button onClick={() => pickMode('live')} className={`flex-1 py-1.5 ${mode === 'live' ? 'bg-red-500/25 text-red-300' : 'text-slate-400'}`}>LIVE</button>
                        </div>
                    </div>
                    {mode !== pageMode && (
                        <div className={`text-[11px] ${mode === 'live' ? 'text-red-300 font-semibold' : 'text-amber-300'}`} data-testid="manual-mode-mismatch">
                            questo ordine parte in <b>{mode.toUpperCase()}</b>, ma la pagina è in <b>{pageMode.toUpperCase()}</b>
                            {mode === 'live' ? ' — sono soldi veri' : ''}
                        </div>
                    )}

                    <div className="text-xs text-slate-400">
                        Selezione: {sel ? <span className={`font-bold ${side === 'lay' ? 'text-rose-300' : 'text-sky-300'}`}>{sel.name}</span> : <span className="italic">nessuna (scegli dal book)</span>}
                    </div>

                    <div className="flex gap-2">
                        <label className="flex-1">
                            <span className="text-[11px] text-slate-400">Quota</span>
                            <input type="number" step={0.5} value={price} onChange={e => setPrice(e.target.value === '' ? '' : Number(e.target.value))}
                                className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums" />
                        </label>
                        <div className="flex-1">
                            <span className="text-[11px] text-slate-400">Dimensiona per</span>
                            <div className="mt-1 flex rounded-md border border-white/10 overflow-hidden text-xs">
                                <button onClick={() => setSizeMode('target')} className={`flex-1 py-2 ${sizeMode === 'target' ? 'bg-white/10 text-white' : 'text-slate-400'}`}>Target €</button>
                                <button onClick={() => setSizeMode('stake')} className={`flex-1 py-2 ${sizeMode === 'stake' ? 'bg-white/10 text-white' : 'text-slate-400'}`}>Stake €</button>
                            </div>
                        </div>
                    </div>

                    {sizeMode === 'target' ? (
                        <label className="block">
                            <span className="text-[11px] text-slate-400">Target profitto € (incasso se NON esce)</span>
                            <input type="number" step={0.5} value={target} onChange={e => setTarget(Number(e.target.value))}
                                className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums" />
                        </label>
                    ) : (
                        <label className="block">
                            <span className="text-[11px] text-slate-400">Stake € (backer stake)</span>
                            <input type="number" step={0.5} value={stake} onChange={e => setStake(Number(e.target.value))}
                                className="mt-1 w-full rounded-md bg-black/50 border border-white/10 px-3 py-2 text-sm tabular-nums" />
                        </label>
                    )}

                    <div className="text-xs text-slate-400 flex items-center justify-between border-t border-white/5 pt-2">
                        <span>Stake ≈ <b className="text-white/90" data-testid="manual-preview-stake">{previewStakeText}</b></span>
                        <span className={side === 'lay' ? 'text-orange-400' : 'text-sky-300'}>
                            {side === 'lay' ? 'Liability aperta' : 'Rischio'} ≈ <b data-testid="manual-preview-liability">{previewText}</b>
                        </span>
                    </div>
                    {bookStale && (
                        <div className="text-[11px] text-red-300" data-testid="manual-book-stale">
                            quote del mercato vecchie{bookAgeS != null ? ` di ${fmtAge(bookAgeS)}` : ''}: ricarica le quote prima di piazzare
                        </div>
                    )}

                    {placeBlock && !bookStale && (
                        <div className="text-[11px] text-amber-300" data-testid="manual-place-block">{placeBlock}</div>
                    )}
                    {sel && (
                        <div className="text-[11px] text-slate-400" data-testid="manual-matchable">
                            abbinabile subito al miglior {side.toUpperCase()}:{' '}
                            <b className={overBook ? 'text-amber-300 tabular-nums' : 'text-emerald-300 tabular-nums'}>
                                {avail != null ? fmtMoney(avail) : 'n/d'}
                            </b>
                        </div>
                    )}

                    <Button onClick={() => { if (mode === 'live') setLiveConfirmOpen(true); else void doPlace(); }}
                        disabled={busy === 'place' || placeBlock != null}
                        title={placeBlock ?? undefined}
                        className={`w-full ${mode === 'live' ? 'bg-red-600 hover:bg-red-500 text-white' : side === 'lay' ? 'bg-rose-600 hover:bg-rose-500 text-white' : 'bg-sky-600 hover:bg-sky-500 text-white'}`}>
                        {busy === 'place' ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Zap className="w-4 h-4 mr-1" />}
                        Piazza {side.toUpperCase()} {mode === 'live' ? '(SOLDI VERI)' : '(paper)'}
                    </Button>
                </Card>
            </div>

            {/* book runners */}
            {snapshot && (
                <Card className="glass-card border-white/10 p-0 overflow-hidden">
                    <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between gap-2 flex-wrap">
                        <span className="text-sm text-slate-300">
                            {snapshot.market_name || 'Mercato'} · {snapshot.inplay ? <Badge variant="outline" className="bg-emerald-500/15 text-emerald-300 border-emerald-500/40">IN CORSO</Badge> : 'pre-partita'}
                            {/* l'ordine deve corrispondere a quello che si vede su Betfair */}
                            <span className="ml-2 text-[10px] text-slate-500 tabular-nums" title="identificativi Betfair del mercato caricato">
                                mercato {snapshot.market_id}
                            </span>
                            <span
                                className={`ml-2 text-[10px] ${bookStale ? 'text-red-300 font-semibold' : 'text-slate-500'}`}
                                data-testid="manual-book-age"
                                data-stale={bookStale ? '1' : undefined}
                                title={bookStale
                                    ? 'quote vecchie: ricarica prima di piazzare'
                                    : 'età dello snapshot delle quote'}
                            >
                                {bookAgeS == null ? 'quote senza orario' : bookStale ? `QUOTE FERME da ${fmtAge(bookAgeS)}` : `quote di ${fmtAge(bookAgeS)}`}
                            </span>
                        </span>
                        <Button variant="outline" size="sm" onClick={suggestLeastProbable}>
                            <Target className="w-3.5 h-3.5 mr-1" />Suggerisci meno probabile
                        </Button>
                    </div>
                    <div className="overflow-x-auto max-h-80">
                        <table className="w-full text-sm">
                            <thead className="text-[11px] uppercase text-slate-500 bg-black/30 sticky top-0">
                                <tr>
                                    <th className="text-left px-4 py-2">Selezione</th>
                                    <th className="text-right px-4 py-2">Back</th>
                                    <th className="text-right px-4 py-2">Lay</th>
                                    <th className={`text-right px-4 py-2 ${side === 'back' ? 'text-sky-300' : ''}`}>Liq. back</th>
                                    <th className={`text-right px-4 py-2 ${side === 'lay' ? 'text-rose-300' : ''}`}>Liq. lay</th>
                                    <th className="text-center px-4 py-2"></th>
                                </tr>
                            </thead>
                            <tbody>
                                {snapshot.runners.map(r => (
                                    <tr key={r.selection_id} className={`border-t border-white/5 hover:bg-white/5 ${sel?.selection_id === r.selection_id ? 'bg-primary/10' : ''}`} data-testid="manual-runner">
                                        <td className="px-4 py-2 font-medium" title={`selezione ${r.selection_id} · mercato ${snapshot.market_id}`}>
                                            {r.name}
                                            {r.status != null && String(r.status).toUpperCase() !== 'ACTIVE' && (
                                                <Badge variant="outline" className="ml-2 text-[10px] bg-amber-500/15 text-amber-300 border-amber-500/40" data-testid="manual-runner-status">
                                                    {runnerStatusLabel(r.status)}
                                                </Badge>
                                            )}
                                        </td>
                                        <td className="px-4 py-2 text-right tabular-nums text-sky-300/90">{fmtQuote(r.back_price)}</td>
                                        <td className="px-4 py-2 text-right tabular-nums text-rose-300">{fmtQuote(r.lay_price)}</td>
                                        {/* CERT. 12/09 — c'era SOLO la liquidità lay: in modalità BACK
                                            si dimensionava l'ordine sulla profondità del lato sbagliato. */}
                                        <td className={`px-4 py-2 text-right tabular-nums ${side === 'back' ? 'text-sky-300' : 'text-slate-500'}`} data-testid="manual-liq-back">
                                            {r.back_size != null ? fmtMoney(r.back_size, { decimals: 0 }) : DASH}
                                        </td>
                                        <td className={`px-4 py-2 text-right tabular-nums ${side === 'lay' ? 'text-rose-300' : 'text-slate-500'}`} data-testid="manual-liq-lay">
                                            {r.lay_size != null ? fmtMoney(r.lay_size, { decimals: 0 }) : DASH}
                                        </td>
                                        <td className="px-4 py-2 text-center">
                                            <Button variant="ghost" size="sm" onClick={() => pickRunner(r)}>usa</Button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}

            {/* stato ultime richieste */}
            {requests.length > 0 && (
                <Card className="glass-card border-white/10 p-3">
                    <div className="text-xs text-slate-400 mb-2">Ultime richieste al servizio</div>
                    <div className="space-y-1">
                        {requests.slice(0, 6).map(r => {
                            const m = manualRequestText(r);
                            return (
                                <div key={r.id} className="flex items-center justify-between gap-2 text-xs" data-testid="manual-request">
                                    <span className="text-slate-300">
                                        <span className="text-slate-500 tabular-nums mr-1" title="ora di Roma (la data compare se non è di oggi)">{manualRequestWhen(r.created_at, today)}</span>
                                        {m.kind}
                                    </span>
                                    <span className="flex items-center gap-1 min-w-0">
                                        {m.detail && (
                                            <span className="text-[11px] text-red-300 truncate max-w-[220px]" title={m.detail} data-testid="manual-request-detail">
                                                {m.detail}
                                            </span>
                                        )}
                                        <Badge variant="outline" className={m.cls}>{m.status}</Badge>
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </Card>
            )}

            {/* conferma LIVE (soldi veri) — coerente con la tab Automatico */}
            <Dialog open={liveConfirmOpen} onOpenChange={setLiveConfirmOpen}>
                <DialogContent className="glass-card border-red-500/30">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-red-400">
                            <ShieldAlert className="w-5 h-5" />Ordine LIVE manuale (soldi veri)?
                        </DialogTitle>
                        <DialogDescription className="space-y-2 text-sm">
                            <span className="block">Stai per piazzare un <b>{side.toUpperCase()}</b> REALE su
                                <b> {sel?.name ?? '—'}</b> a quota <b>{fmtOdds(Number(price) || null)}</b>.</span>
                            <span className="block text-orange-300">
                                Stake ≈ {previewStakeText} · {side === 'lay' ? 'Liability aperta' : 'Rischio'} ≈ {previewText}.
                            </span>
                            {/* l'ordine deve corrispondere a quello che si vede su Betfair */}
                            <span className="block text-[11px] text-slate-400 tabular-nums">
                                mercato {marketId || '—'} · selezione {sel?.selection_id ?? '—'}
                                {snapshot?.market_name ? ` · ${snapshot.market_name}` : ''}
                            </span>
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setLiveConfirmOpen(false)}>Annulla</Button>
                        <Button variant="destructive" disabled={busy === 'place'}
                            onClick={() => { setLiveConfirmOpen(false); void doPlace(); }}>
                            Sì, piazza LIVE
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
