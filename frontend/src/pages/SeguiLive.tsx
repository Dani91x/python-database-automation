// ============================================================================
// /segui-live — "Segui Live". Elenco delle partite attualmente sottoscritte allo
// stream Betfair (get_live_follows, refetch ogni 15s come backup). Clic su una
// card → dettaglio realtime (stessa pagina) sottoscritto a `live_now` per le
// quote che si aggiornano in tempo reale. Stesso design system del resto dell'app.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { ChevronLeft, Radio, AlertTriangle, History, Banknote, Loader2, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { LiveMatchCard } from '@/components/live/LiveMatchCard';
import { LiveMarketBoard } from '@/components/live/LiveMarketBoard';
import { LiveSignalPanel } from '@/components/live/LiveSignalPanel';
import { LiveAlertBanner } from '@/components/live/LiveAlertBanner';
import { LiveTradingPanel, type PanelMode } from '@/components/live/LiveTradingPanel';
import { RiskRulesPanel } from '@/components/live/RiskRulesPanel';
import { DutchingPanel } from '@/components/live/DutchingPanel';
import { LiveControlsPanel } from '@/components/live/LiveControlsPanel';
import { XHedgePanel } from '@/components/live/XHedgePanel';
import { ScalperPanel } from '@/components/live/ScalperPanel';
import { HabitatCard } from '@/components/live/HabitatCard';
import { LadderView } from '@/components/live/LadderView';
import { TerminalPositionsRail } from '@/components/live/TerminalPositionsRail';
import { sendCashoutAll, sendCashoutEvent, setKillSwitch, type LiveOrderMode } from '@/lib/liveOrders';
import {
    loadLayout, saveLayout, setActiveMarket, resolveHotkey,
    type WorkspaceLayout,
} from '@/lib/workspace';
import {
    fetchLiveFollows, fetchLiveNow, subscribeLiveNow,
    type LiveFollow, type LiveNowRow, type LiveNowMarket,
} from '@/lib/live';

// Strumenti della colonna DESTRA del terminal (UN tab attivo alla volta, stile Bet Angel:
// One-click | Dutching | Bookmaking | ... come tab, mai tutti i pannelli impilati).
type ToolKey = 'trading' | 'dutching' | 'risk' | 'xhedge' | 'scalper';
const TOOL_TABS: { key: ToolKey; label: string }[] = [
    { key: 'trading', label: 'Trading' },
    { key: 'dutching', label: 'Dutching' },
    { key: 'risk', label: 'Risk' },
    { key: 'xhedge', label: 'X-Hedge' },
    { key: 'scalper', label: 'Scalper' },
];
const toolStorageKey = (eventId: string) => `live.terminal.tool.${eventId}`;
function loadTool(eventId: string): ToolKey {
    try {
        const v = localStorage.getItem(toolStorageKey(eventId));
        if (v && TOOL_TABS.some(t => t.key === v)) return v as ToolKey;
    } catch { /* storage non disponibile: default */ }
    return 'trading';
}

// Badge modalità del terminal (fonte: live_now.state.order_mode, fail-safe → OFF).
function TerminalModeBadge({ mode }: { mode: PanelMode }) {
    if (mode === 'live') {
        return <span className="px-2 py-0.5 rounded-md bg-red-600 text-white text-[10px] font-black animate-pulse">🔴 LIVE — SOLDI VERI</span>;
    }
    if (mode === 'paper') {
        return <span className="px-2 py-0.5 rounded-md bg-sky-500/20 text-sky-300 text-[10px] font-black">PAPER</span>;
    }
    return <span className="px-2 py-0.5 rounded-md bg-white/10 text-white/60 text-[10px] font-black">OFF</span>;
}

// Sezione "Live Trading" del dettaglio Segui Live: COCKPIT MULTI-MERCATO stile Bet Angel.
// Una TAB per mercato dell'evento (dai mercati di live_now, STESSA fonte del tabellone);
// il mercato attivo viene ricordato per-evento (WORKSPACE: '@/lib/workspace' — tab attivo +
// quali pannelli sono aperti/collassati, salvati in localStorage per-evento). Per il mercato
// attivo montiamo, affiancati: LiveTradingPanel (order entry + blotter + P&L), DutchingPanel
// (dutching multi-selezione) e RiskRulesPanel (offset / stop-loss / take-profit / trailing /
// bracket). L'XHedgePanel (analisi cross-market) è montato UNA sola volta per EVENTO. Due
// pulsanti di cash-out DISTINTI: "Cash-out MERCATO" (solo il mercato attivo → sendCashoutAll)
// e "Cash-out EVENTO" (tutti i mercati dell'evento → sendCashoutEvent, conferma rafforzata in
// LIVE). Scorciatoie da tastiera (attive solo in PAPER/LIVE, disattivate mentre si digita).
// La modalità (OFF/PAPER/LIVE) arriva dal runner via live_now.state.order_mode.
function LiveTradingSection({ markets, orderMode, eventName, eventId, updatedAt }: {
    markets: LiveNowMarket[]; orderMode: string; eventName: string; eventId: string;
    updatedAt: string | null;
}) {
    const defaultId = useMemo(() => {
        const mo = markets.find(m => m.market_type === 'MATCH_ODDS' || /match odds/i.test(m.market_name ?? ''));
        return (mo ?? markets[0])?.market_id ?? '';
    }, [markets]);

    // ---- WORKSPACE: layout per-evento (tab mercato attivo + pannelli aperti/collassati) ----
    const [layout, setLayout] = useState<WorkspaceLayout>(() => loadLayout(eventId));
    // ricarica il layout quando cambia l'evento selezionato.
    useEffect(() => { setLayout(loadLayout(eventId)); }, [eventId]);
    // persisti il layout ad ogni modifica (normalizzato dentro saveLayout).
    useEffect(() => { saveLayout(layout); }, [layout]);

    const [cashingMarket, setCashingMarket] = useState(false);
    const [cashingEvent, setCashingEvent] = useState(false);
    // MONEY-CRITICAL (fix review MEDIUM): guardia anti-doppio-invio a livello di REF. I bottoni sono
    // disabilitati durante l'attesa, ma il percorso SCORCIATOIA DA TASTIERA chiama gli handler
    // direttamente bypassando il disabled: senza questo ref una seconda pressione accoderebbe un
    // SECONDO cash-out reale (client_ref nuovo → non deduplicato) → over-hedge/posizione opposta.
    const cashingMarketRef = useRef(false);
    const cashingEventRef = useRef(false);

    // mercato attivo: dal layout, validato contro i mercati correnti; fallback al default.
    const marketId = useMemo(() => {
        const a = layout.activeMarketId;
        if (a && markets.some(m => m.market_id === a)) return a;
        return defaultId;
    }, [layout.activeMarketId, markets, defaultId]);

    // allinea il layout al mercato effettivo (se assente/non più valido) — persistito dall'effetto sopra.
    useEffect(() => {
        if (marketId && layout.activeMarketId !== marketId) {
            setLayout(l => setActiveMarket(l, marketId));
        }
    }, [marketId, layout.activeMarketId]);

    const selectMarket = useCallback((id: string) => setLayout(l => setActiveMarket(l, id)), []);

    // strumento attivo nella colonna destra (UN tab alla volta), persistito per-evento.
    const [tool, setTool] = useState<ToolKey>(() => loadTool(eventId));
    useEffect(() => { setTool(loadTool(eventId)); }, [eventId]);
    const selectTool = useCallback((k: ToolKey) => {
        setTool(k);
        try { localStorage.setItem(toolStorageKey(eventId), k); } catch { /* best-effort */ }
    }, [eventId]);

    // "aggiornato Xs fa" che TICCHETTA (fix M3): l'età dei dati è visibile e diventa
    // rossa oltre la soglia — mai un badge verde su dati congelati.
    const [nowTick, setNowTick] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setNowTick(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);
    const ageSec = updatedAt ? Math.max(0, Math.round((nowTick - new Date(updatedAt).getTime()) / 1000)) : null;
    const staleData = ageSec != null && ageSec > 15;

    const market = markets.find(m => m.market_id === marketId) ?? null;
    const mode = (['off', 'paper', 'live'].includes((orderMode || 'off').toLowerCase())
        ? (orderMode || 'off').toLowerCase() : 'off') as PanelMode;

    // book % back/lay del mercato attivo (over-round, come la barra mercato dei tool pro).
    const bookPct = useMemo(() => {
        const sels = market?.selections ?? [];
        let backSum = 0; let laySum = 0; let nB = 0; let nL = 0;
        for (const s of sels) {
            if (s.back && s.back > 1) { backSum += 1 / s.back; nB++; }
            if (s.lay && s.lay > 1) { laySum += 1 / s.lay; nL++; }
        }
        return {
            back: nB === sels.length && nB > 0 ? backSum * 100 : null,
            lay: nL === sels.length && nL > 0 ? laySum * 100 : null,
        };
    }, [market]);

    // memoizzati su `market`: live_now si aggiorna ogni pochi secondi → evita una nuova
    // reference di `selections` ad ogni tick (lavoro inutile nei pannelli).
    // panelSelections: shape minimale per LiveTradingPanel (id+name).
    const panelSelections = useMemo(
        () => (market?.selections ?? []).map(s => ({ selection_id: s.selection_id, name: s.name })),
        [market],
    );
    // richSelections: include quote correnti (back/lay/ltp) per Dutching e Risk (preview prezzi).
    const richSelections = useMemo(
        () => (market?.selections ?? []).map(s => ({
            selection_id: s.selection_id, name: s.name, back: s.back, lay: s.lay, ltp: s.ltp,
        })),
        [market],
    );

    // ---- Cash-out MERCATO (solo il mercato attivo) — sendCashoutAll ----
    const handleCashoutMarket = useCallback(async () => {
        if (!market) return;
        if (cashingMarketRef.current) return;   // già in corso (protegge anche il percorso hotkey)
        if (mode === 'off') {
            toast.error('Runner in OFF: cash-out non disponibile. Avvia in PAPER o LIVE.');
            return;
        }
        // MONEY-CRITICAL: in LIVE serve conferma esplicita (soldi veri).
        if (mode === 'live' &&
            !window.confirm(`CASH-OUT REALE del SOLO mercato "${market.market_name || market.market_type}"?\nAppiattisce TUTTE le selezioni con esposizione aperta di QUESTO mercato (soldi veri).`)) {
            return;
        }
        cashingMarketRef.current = true;
        setCashingMarket(true);
        try {
            const res = await sendCashoutAll({ marketId: market.market_id, mode: mode as LiveOrderMode });
            if (res.ok) {
                toast.success('Cash-out MERCATO inviato', {
                    description: res.status ?? (res.bet_id ? `req ${res.bet_id}` : undefined),
                });
            } else {
                toast.error('Cash-out mercato rifiutato', { description: res.error ?? res.detail ?? 'motivo non noto' });
            }
        } catch (e: any) {
            toast.error('Errore cash-out mercato', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            cashingMarketRef.current = false;
            setCashingMarket(false);
        }
    }, [market, mode]);

    // ---- Cash-out EVENTO (tutti i mercati dell'evento) — sendCashoutEvent ----
    // Conferma RAFFORZATA in LIVE: tocca TUTTI i mercati → doppia conferma.
    const handleCashoutEvent = useCallback(async () => {
        if (!market) return;
        if (cashingEventRef.current) return;   // già in corso (protegge anche il percorso hotkey)
        if (mode === 'off') {
            toast.error('Runner in OFF: cash-out non disponibile. Avvia in PAPER o LIVE.');
            return;
        }
        if (mode === 'live') {
            if (!window.confirm(`CASH-OUT REALE dell'INTERO EVENTO "${eventName}"?\nAppiattisce TUTTE le selezioni con esposizione aperta su TUTTI i mercati dell'evento (non solo quello attivo). SOLDI VERI.`)) {
                return;
            }
            if (!window.confirm('Conferma DEFINITIVA: green-up di TUTTI i mercati dell\'evento. Procedere?')) {
                return;
            }
        }
        cashingEventRef.current = true;
        setCashingEvent(true);
        try {
            const res = await sendCashoutEvent({ marketId: market.market_id, mode: mode as LiveOrderMode });
            if (res.ok) {
                toast.success('Cash-out EVENTO inviato', {
                    description: res.status ?? (res.bet_id ? `req ${res.bet_id}` : undefined),
                });
            } else {
                toast.error('Cash-out evento rifiutato', { description: res.error ?? res.detail ?? 'motivo non noto' });
            }
        } catch (e: any) {
            toast.error('Errore cash-out evento', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            cashingEventRef.current = false;
            setCashingEvent(false);
        }
    }, [market, mode, eventName]);

    // ---- Kill-switch (panico) — blocca ogni invio ordini del runner ----
    const handleKillSwitch = useCallback(async () => {
        if (!window.confirm('KILL-SWITCH: blocca immediatamente ogni invio ordini del runner. Attivare?')) return;
        try {
            await setKillSwitch(true);
            toast.warning('Kill-switch ATTIVATO', { description: 'Invio ordini bloccato.' });
        } catch (e: any) {
            toast.error('Errore kill-switch', { description: e?.message ?? 'errore sconosciuto' });
        }
    }, []);

    // ---- SCORCIATOIE DA TASTIERA (solo in PAPER/LIVE; non mentre si digita) ----
    // Mappa tasto→azione da '@/lib/workspace' (resolveHotkey). Wiriamo le azioni whole-market/
    // evento disponibili su questa pagina: G = green-up mercato, X = cash-out evento, Esc = kill.
    useEffect(() => {
        if (mode !== 'paper' && mode !== 'live') return;
        const onKey = (e: KeyboardEvent) => {
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            const t = e.target as HTMLElement | null;
            if (t) {
                const tag = t.tagName;
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable) return;
            }
            const action = resolveHotkey(e.key);
            if (action === 'greenup') { e.preventDefault(); void handleCashoutMarket(); }
            else if (action === 'cashout_event') { e.preventDefault(); void handleCashoutEvent(); }
            else if (action === 'kill_switch') { e.preventDefault(); void handleKillSwitch(); }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [mode, handleCashoutMarket, handleCashoutEvent, handleKillSwitch]);

    if (markets.length === 0) return null;
    const busy = cashingMarket || cashingEvent;
    return (
        <div className="space-y-2">
            {/* ================= TOP BAR STICKY del terminal =================
                Canone dei tool pro (Bet Angel/Fairbot): badge modalità, book% back/lay,
                freschezza dati, azioni d'emergenza SEMPRE visibili (cash-out + kill). */}
            <div className="sticky top-16 z-40 rounded-xl border border-white/10 bg-black/80 backdrop-blur-xl px-3 py-2 flex items-center gap-3 flex-wrap">
                <TerminalModeBadge mode={mode} />
                {bookPct.back != null && bookPct.lay != null && (
                    <span className="text-[10px] font-mono tabular-nums text-white/70" title="Over-round: book back / book lay del mercato attivo">
                        <span className="text-sky-300">{bookPct.back.toFixed(1)}%</span>
                        {' / '}
                        <span className="text-rose-300">{bookPct.lay.toFixed(1)}%</span>
                    </span>
                )}
                <span
                    className={`text-[10px] font-mono tabular-nums ${staleData ? 'text-rose-300 font-black' : 'text-muted-foreground'}`}
                    title="Età dell'ultimo aggiornamento di live_now (quote e stato)"
                >
                    {ageSec == null ? 'dati: n/d' : staleData ? `⚠ DATI VECCHI ${ageSec}s` : `agg. ${ageSec}s fa`}
                </span>
                <span className="flex-1" />
                <div className="flex items-center gap-2 flex-wrap">
                    <Button
                        size="sm"
                        onClick={handleCashoutMarket}
                        disabled={busy || mode === 'off'}
                        className="h-7 bg-amber-500 hover:bg-amber-400 text-black font-black disabled:opacity-40"
                        title="Green-up di TUTTE le selezioni del SOLO mercato attivo (hotkey G)"
                    >
                        {cashingMarket ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Banknote className="w-3.5 h-3.5 mr-1.5" />}
                        Cash-out MERCATO
                    </Button>
                    <Button
                        size="sm"
                        onClick={handleCashoutEvent}
                        disabled={busy || mode === 'off'}
                        className="h-7 bg-rose-600 hover:bg-rose-500 text-white font-black disabled:opacity-40"
                        title="Green-up di TUTTI i mercati dell'evento — conferma rafforzata in LIVE (hotkey X)"
                    >
                        {cashingEvent ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <ShieldAlert className="w-3.5 h-3.5 mr-1.5" />}
                        Cash-out EVENTO
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={handleKillSwitch}
                        className="h-7 border-red-500/50 text-red-300 hover:bg-red-500/15 font-black"
                        title="KILL-SWITCH GLOBALE del runner: blocca le APERTURE (le chiusure restano possibili) — hotkey Esc"
                    >
                        KILL
                    </Button>
                    {mode !== 'off' && (
                        <span
                            className="w-5 h-5 inline-flex items-center justify-center rounded-full border border-white/15 text-[10px] text-muted-foreground cursor-help select-none"
                            title={'Scorciatoie tastiera:\nG = cash-out mercato attivo\nX = cash-out intero evento\nEsc = kill-switch globale\n(attive solo in PAPER/LIVE, non mentre digiti)'}
                        >
                            ?
                        </span>
                    )}
                </div>
            </div>

            {/* TABS multi-mercato (stile Bet Angel) */}
            <div className="flex items-stretch gap-1 flex-wrap border-b border-white/5 overflow-x-auto">
                {markets.map(m => {
                    const active = m.market_id === marketId;
                    return (
                        <button
                            key={m.market_id}
                            type="button"
                            onClick={() => selectMarket(m.market_id)}
                            className={`px-3 py-1.5 -mb-px rounded-t-lg text-xs font-bold border-b-2 transition-colors whitespace-nowrap ${
                                active
                                    ? 'border-primary text-white bg-white/[0.06]'
                                    : 'border-transparent text-muted-foreground hover:text-white hover:bg-white/[0.03]'
                            }`}
                        >
                            {m.market_name || m.market_type || m.market_id}
                        </button>
                    );
                })}
            </div>

            {/* ================= GRIGLIA 3 ZONE del terminal =================
                sinistra: posizioni/P&L + order book · centro: LADDER (strumento primario,
                dominante) · destra: strumenti a TAB (uno alla volta).
                MONEY-CRITICAL (fix H1): key={market_id} su ladder e pannelli → remount pulito
                al cambio tab mercato (nessuno stato form/conferma riusato tra mercati con
                selection id che si ripetono). */}
            {market && (
                <div className="grid grid-cols-1 xl:grid-cols-[290px_minmax(0,1fr)_400px] gap-3 items-start">
                    {/* -------- SINISTRA: posizioni + ordini -------- */}
                    <div className="order-2 xl:order-1">
                        <TerminalPositionsRail
                            key={market.market_id}
                            marketId={market.market_id}
                            mode={mode}
                            selections={panelSelections}
                        />
                    </div>

                    {/* -------- CENTRO: LADDER dominante -------- */}
                    <div className="order-1 xl:order-2 min-w-0">
                        <LadderView
                            key={market.market_id}
                            marketId={market.market_id}
                            marketName={market.market_name || market.market_type}
                            orderMode={mode}
                            fallbackSelections={panelSelections}
                        />
                    </div>

                    {/* -------- DESTRA: strumenti a TAB (uno alla volta) -------- */}
                    <div className="order-3 space-y-2 min-w-0">
                        <div className="flex items-stretch gap-1 flex-wrap border-b border-white/5">
                            {TOOL_TABS.map(t => (
                                <button
                                    key={t.key}
                                    type="button"
                                    onClick={() => selectTool(t.key)}
                                    aria-pressed={tool === t.key}
                                    className={`px-2.5 py-1 -mb-px rounded-t-lg text-[11px] font-bold border-b-2 transition-colors ${
                                        tool === t.key
                                            ? 'border-amber-400 text-white bg-white/[0.06]'
                                            : 'border-transparent text-muted-foreground hover:text-white hover:bg-white/[0.03]'
                                    }`}
                                >
                                    {t.label}
                                </button>
                            ))}
                        </div>
                        {tool === 'trading' && (
                            <LiveTradingPanel
                                key={market.market_id}
                                marketId={market.market_id}
                                mode={mode}
                                eventLabel={`${eventName} · ${market.market_name || market.market_type}`}
                                selections={panelSelections}
                            />
                        )}
                        {tool === 'dutching' && (
                            <DutchingPanel
                                key={market.market_id}
                                marketId={market.market_id}
                                mode={mode}
                                selections={richSelections}
                            />
                        )}
                        {tool === 'risk' && (
                            <RiskRulesPanel
                                key={market.market_id}
                                marketId={market.market_id}
                                mode={mode}
                                selections={richSelections}
                            />
                        )}
                        {tool === 'xhedge' && (
                            <XHedgePanel eventId={eventId} mode={mode} />
                        )}
                        {tool === 'scalper' && (
                            <ScalperPanel eventId={eventId} eventName={eventName} />
                        )}
                    </div>
                </div>
            )}

            {/* ---- CONTROLLI GLOBALI del runner (kill-switch, limiti, audit) — collassabili ---- */}
            <details className="group rounded-xl border border-white/10 bg-black/30">
                <summary className="cursor-pointer select-none px-3 py-2 text-[10px] uppercase tracking-widest font-bold text-muted-foreground hover:text-white list-none flex items-center gap-1.5">
                    <span className="transition-transform group-open:rotate-90">▸</span>
                    Controlli runner · limiti · audit
                </summary>
                <div className="p-2 pt-0">
                    <LiveControlsPanel />
                </div>
            </details>
        </div>
    );
}

export default function SeguiLive() {
    const [follows, setFollows] = useState<LiveFollow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [selected, setSelected] = useState<LiveFollow | null>(null);
    const [liveNow, setLiveNow] = useState<LiveNowRow | null>(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const unsubRef = useRef<(() => void) | null>(null);

    // --- lista: caricamento + refetch ogni 15s come backup al realtime ---
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchLiveFollows()
                .then(rows => { if (alive) { setFollows(rows); setError(null); } })
                .catch(e => { if (alive) setError(e?.message ?? 'errore sconosciuto'); })
                .finally(() => { if (alive) setLoading(false); });
        };
        load();
        const id = setInterval(load, 15000);
        return () => { alive = false; clearInterval(id); };
    }, []);

    // --- dettaglio: snapshot iniziale + sottoscrizione realtime a live_now ---
    useEffect(() => {
        // pulizia eventuale sottoscrizione precedente
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        setLiveNow(null);
        if (!selected) { setDetailLoading(false); return; }

        let alive = true;
        setDetailLoading(true);
        fetchLiveNow(selected.event_id)
            .then(row => { if (alive) setLiveNow(row); })
            .catch((e: any) => {
                // PGRST116 = nessuna riga (live_now non ancora popolata): atteso, non logghiamo.
                if (e?.code !== 'PGRST116') console.warn('[SeguiLive] fetchLiveNow:', e);
            })
            .finally(() => { if (alive) setDetailLoading(false); });

        unsubRef.current = subscribeLiveNow(selected.event_id, (row) => {
            // payload DELETE → row null: manteniamo l'ultimo stato noto
            if (row) setLiveNow(row);
        });

        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [selected]);

    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet><title>Segui Live | Alpha Score</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link to="/dashboard" className="font-display font-black text-xl tracking-tighter">AI <span className="text-primary">TERMINAL</span></Link>
                        <span className="hidden md:flex items-center gap-2 text-sm text-primary font-heading font-bold ml-4">
                            <Radio className="w-4 h-4" /> SEGUI LIVE
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <Link to="/match-replay">
                            <Button variant="outline" size="sm" className="border-secondary/30 text-secondary hover:bg-secondary/10">
                                <History className="w-4 h-4 md:mr-2" /> <span className="hidden md:inline">Match Replay</span>
                            </Button>
                        </Link>
                        <Link to="/dashboard">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                <ChevronLeft className="w-4 h-4 mr-1" /> Dashboard
                            </Button>
                        </Link>
                    </div>
                </div>
            </nav>

            {/* nel dettaglio il terminal ha 3 colonne (ladder centrale + rail): serve
                larghezza piena; la lista resta compatta a 6xl. */}
            <main className={`container mx-auto px-4 lg:px-6 py-8 relative z-10 ${selected ? 'max-w-[1800px]' : 'max-w-6xl'}`}>
                {/* Avvisi limiti Betfair / sistema (Realtime), in cima alla pagina */}
                <LiveAlertBanner />

                <div className="mb-6 flex items-start justify-between gap-4">
                    <div>
                        <h1 className="font-display font-black text-2xl md:text-3xl tracking-tight">
                            Segui <span className="text-primary">Live</span>
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Partite sottoscritte allo stream Betfair. Clic su una partita per le quote in tempo reale.
                        </p>
                    </div>
                    {selected && (
                        <Button variant="outline" size="sm" onClick={() => setSelected(null)}
                            className="shrink-0 border-white/10 text-muted-foreground hover:text-white">
                            <ChevronLeft className="w-4 h-4 mr-1" /> Tutte le partite
                        </Button>
                    )}
                </div>

                {error && (
                    <Card className="glass-card border-red-500/30 p-4 mb-4 flex items-center gap-2 text-red-400 text-sm">
                        <AlertTriangle className="w-4 h-4" /> {error}
                    </Card>
                )}

                {loading ? (
                    <div className="space-y-3">
                        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full bg-white/5" />)}
                    </div>
                ) : selected ? (
                    /* ---- DETTAGLIO realtime: TERMINAL prima (strumento primario),
                           tabellone completo + segnali sotto come overview ---- */
                    <div className="space-y-4">
                        <LiveMatchCard follow={selected} selected onClick={() => { /* già aperto */ }} />
                        {detailLoading && !liveNow ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40 w-full bg-white/5" />)}
                            </div>
                        ) : (
                            <>
                                {/* ---- TRADING TERMINAL (stessa fonte: live_now) ---- */}
                                {liveNow?.state?.markets && liveNow.state.markets.length > 0 && (
                                    <LiveTradingSection
                                        markets={liveNow.state.markets}
                                        orderMode={liveNow.state.order_mode ?? 'OFF'}
                                        eventName={`${selected.home_name} vs ${selected.away_name}`}
                                        eventId={selected.event_id}
                                        updatedAt={liveNow.updated_at ?? null}
                                    />
                                )}

                                {/* ---- overview: tabellone tutti i mercati + segnali ---- */}
                                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
                                    <div className="lg:col-span-2">
                                        <LiveMarketBoard
                                            state={liveNow?.state ?? null}
                                            updatedAt={liveNow?.updated_at ?? null}
                                            orderMode={liveNow?.state?.order_mode ?? 'off'}
                                        />
                                    </div>
                                    <div className="lg:col-span-1">
                                        <LiveSignalPanel eventId={selected.event_id} state={liveNow?.state ?? null} />
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                ) : follows.length === 0 ? (
                    <div className="space-y-3">
                        <HabitatCard />
                        <Card className="glass-card border-white/10 p-10 text-center">
                            <Radio className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
                            <p className="text-sm text-muted-foreground">Nessuna partita in streaming.</p>
                        </Card>
                    </div>
                ) : (
                    /* ---- LISTA ---- */
                    <div className="space-y-3">
                        {/* Habitat scan: dove accendere lo SCALPER oggi (dal servizio) */}
                        <HabitatCard />
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                            {follows.map(f => (
                                <LiveMatchCard key={f.event_id} follow={f} onClick={() => setSelected(f)} />
                            ))}
                        </div>
                    </div>
                )}
            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
