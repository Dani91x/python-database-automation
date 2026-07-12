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
import {
    requestManual, fetchOmegaEvents, fetchOmegaMarket, fetchManualRequests,
    type OmegaEvent, type OmegaMarketSnapshot, type OmegaMarketRunner,
    type OmegaMode, type OmegaSide, type OmegaManualRequest,
} from '@/lib/omega';

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

function fmtQuote(v: number | null): string {
    return v == null ? '—' : v.toFixed(2);
}

export default function ManualPanel() {
    const [events, setEvents] = useState<OmegaEvent[]>([]);
    const [eventId, setEventId] = useState('');
    const [marketId, setMarketId] = useState('');
    const [snapshot, setSnapshot] = useState<OmegaMarketSnapshot | null>(null);
    const [sel, setSel] = useState<OmegaMarketRunner | null>(null);

    const [side, setSide] = useState<OmegaSide>('lay');
    const [mode, setMode] = useState<OmegaMode>('paper');
    const [sizeMode, setSizeMode] = useState<'target' | 'stake'>('target');
    const [target, setTarget] = useState(5);
    const [stake, setStake] = useState(1);
    const [price, setPrice] = useState<number | ''>('');

    const [busy, setBusy] = useState<string | null>(null);
    const [requests, setRequests] = useState<OmegaManualRequest[]>([]);
    const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);

    const selectedEvent = useMemo(() => events.find(e => e.event_id === eventId) ?? null, [events, eventId]);
    const markets = selectedEvent?.markets ?? [];

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
            const before = events.length;
            for (let i = 0; i < 8; i++) { await sleep(1500); await loadEvents(); if (events.length !== before) break; }
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

    function pickRunner(r: OmegaMarketRunner) {
        setSel(r);
        setPrice(side === 'lay' ? (r.lay_price ?? '') : (r.back_price ?? ''));
    }

    // helper: suggerisci il punteggio MENO probabile (quota lay più alta in [20,120])
    function suggestLeastProbable() {
        if (!snapshot) return;
        const cand = snapshot.runners
            .filter(r => r.lay_price != null && r.lay_price >= 20 && r.lay_price <= 120 && /^\d+\s*-\s*\d+$/.test(r.name))
            .sort((a, b) => (b.lay_price ?? 0) - (a.lay_price ?? 0));
        if (cand.length === 0) { toast('Nessun punteggio in fascia [20,120]'); return; }
        setSide('lay'); pickRunner(cand[0]);
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
                description: `${side.toUpperCase()} ${sel.name} @ ${Number(price).toFixed(2)} · ${mode.toUpperCase()}`,
            });
            await loadRequests();
        } catch (e) { toast.error('Piazzamento fallito', { description: String((e as Error).message) }); }
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
    const previewLiability = side === 'lay' ? previewStake * (pPrice - 1) : previewStake;

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
                        <option value="">— scegli evento ({events.length}) —</option>
                        {events.map(ev => (
                            <option key={ev.event_id} value={ev.event_id}>
                                {ev.name || ev.event_id}{ev.open_date ? ` · ${new Date(ev.open_date).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}` : ''}
                            </option>
                        ))}
                    </select>

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
                            <button onClick={() => setSide('lay')} className={`flex-1 py-1.5 ${side === 'lay' ? 'bg-primary/25 text-primary' : 'text-slate-400'}`}>LAY</button>
                            <button onClick={() => setSide('back')} className={`flex-1 py-1.5 ${side === 'back' ? 'bg-sky-500/25 text-sky-300' : 'text-slate-400'}`}>BACK</button>
                        </div>
                        <div className="flex rounded-md border border-white/10 overflow-hidden text-xs font-bold flex-1">
                            <button onClick={() => setMode('paper')} className={`flex-1 py-1.5 ${mode === 'paper' ? 'bg-emerald-500/25 text-emerald-300' : 'text-slate-400'}`}>PAPER</button>
                            <button onClick={() => setMode('live')} className={`flex-1 py-1.5 ${mode === 'live' ? 'bg-red-500/25 text-red-300' : 'text-slate-400'}`}>LIVE</button>
                        </div>
                    </div>

                    <div className="text-xs text-slate-400">
                        Selezione: {sel ? <span className="text-secondary font-bold">{sel.name}</span> : <span className="italic">nessuna (scegli dal book)</span>}
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
                        <span>Stake ≈ <b className="text-white/90">€{previewStake.toFixed(2)}</b></span>
                        <span className={side === 'lay' ? 'text-orange-400' : 'text-sky-300'}>
                            {side === 'lay' ? 'Liability' : 'Rischio'} ≈ <b>€{(previewLiability || 0).toFixed(2)}</b>
                        </span>
                    </div>

                    <Button onClick={() => { if (mode === 'live') setLiveConfirmOpen(true); else void doPlace(); }}
                        disabled={!sel || busy === 'place'}
                        className={`w-full ${mode === 'live' ? 'bg-red-600 hover:bg-red-500 text-white' : 'bg-primary text-black hover:bg-primary/90'}`}>
                        {busy === 'place' ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Zap className="w-4 h-4 mr-1" />}
                        Piazza {side.toUpperCase()} {mode === 'live' ? '(SOLDI VERI)' : '(paper)'}
                    </Button>
                </Card>
            </div>

            {/* book runners */}
            {snapshot && (
                <Card className="glass-card border-white/10 p-0 overflow-hidden">
                    <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between">
                        <span className="text-sm text-slate-300">
                            {snapshot.market_name || 'Mercato'} · {snapshot.inplay ? <Badge variant="outline" className="bg-emerald-500/15 text-emerald-300 border-emerald-500/40">IN-PLAY</Badge> : 'pre-match'}
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
                                    <th className="text-right px-4 py-2">Liq. lay</th>
                                    <th className="text-center px-4 py-2"></th>
                                </tr>
                            </thead>
                            <tbody>
                                {snapshot.runners.map(r => (
                                    <tr key={r.selection_id} className={`border-t border-white/5 hover:bg-white/5 ${sel?.selection_id === r.selection_id ? 'bg-primary/10' : ''}`}>
                                        <td className="px-4 py-2 font-medium">{r.name}</td>
                                        <td className="px-4 py-2 text-right tabular-nums text-sky-300/90">{fmtQuote(r.back_price)}</td>
                                        <td className="px-4 py-2 text-right tabular-nums text-primary">{fmtQuote(r.lay_price)}</td>
                                        <td className="px-4 py-2 text-right tabular-nums text-slate-400">€{r.lay_size.toFixed(0)}</td>
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
                    <div className="text-xs text-slate-400 mb-2">Ultime richieste</div>
                    <div className="space-y-1">
                        {requests.slice(0, 6).map(r => (
                            <div key={r.id} className="flex items-center justify-between text-xs">
                                <span className="text-slate-300">{r.kind}</span>
                                <Badge variant="outline" className={
                                    r.status === 'done' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                                    : r.status === 'error' ? 'bg-red-500/15 text-red-300 border-red-500/40'
                                    : 'bg-slate-500/15 text-slate-300 border-slate-500/40'}>
                                    {r.status}{r.result?.error ? ` · ${String(r.result.error)}` : ''}
                                </Badge>
                            </div>
                        ))}
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
                                <b> {sel?.name ?? '—'}</b> a quota <b>{Number(price) || '—'}</b>.</span>
                            <span className="block text-orange-300">
                                Stake ≈ €{previewStake.toFixed(2)} · {side === 'lay' ? 'Liability' : 'Rischio'} ≈ €{(previewLiability || 0).toFixed(2)}.
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
