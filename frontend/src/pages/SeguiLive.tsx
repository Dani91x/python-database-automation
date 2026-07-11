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
import { LadderView, type LadderSource, type LadderOrderApi } from '@/components/live/LadderView';
import { GridView } from '@/components/live/GridView';
import { SelectionChartPanel } from '@/components/live/SelectionChartPanel';
import { DepthPanel } from '@/components/live/DepthPanel';
import { TerminalPositionsRail } from '@/components/live/TerminalPositionsRail';
import {
    sendCashoutAll, sendCashoutEvent, setKillSwitch,
    fetchLiveRiskState, subscribeLiveRiskState, fetchLivePositionsEvent,
    fetchLiveAccount, subscribeLiveAccount, fetchLiveHeartbeat, subscribeLiveHeartbeat,
    sendLiveOrderCommand, fetchLiveOrders, fetchLivePositions, sendGreenup, requestRiskRule,
    type LiveOrderMode, type LiveRiskState, type LiveAccountRow, type LiveHeartbeatRow,
    type LivePositionRow,
} from '@/lib/liveOrders';
import { localLadderSource, localOrderApi, subscribeLocalNow, useLocalStatus } from '@/lib/localTransport';
import { eventExposure, eventMtm } from '@/lib/eventPnl';
import { heartbeatState, heartbeatAgeSec } from '@/lib/runnerHealth';
import { countLapseResting, countdownToOff, formatMinute, formatScore, secondsToOff } from '@/lib/matchClock';
import { preGoalWarning } from '@/lib/preGoal';
import {
    loadLayout, saveLayout, setActiveMarket, setCenterView, resolveHotkey,
    type WorkspaceLayout,
} from '@/lib/workspace';
import {
    fetchLiveFollows, fetchLiveNow, subscribeLiveNow, fetchLiveLadder, subscribeLiveLadder,
    fetchLiveSignals, subscribeLiveSignals,
    type LiveFollow, type LiveNowRow, type LiveNowMarket, type LiveSignalsRow,
} from '@/lib/live';

// ---- CANALE LOCALE (app desktop, latenza ~0) ----
// Wrapper dei DEFAULT calcio (le stesse funzioni di LadderView): quando il canale
// ws://127.0.0.1:47331 è connesso, ladder e ordini viaggiano in locale; quando è
// off NON passiamo i prop → LadderView/GridView usano i default DB (path invariato).
const CALCIO_DB_LADDER_SOURCE: LadderSource = {
    fetch: fetchLiveLadder,
    subscribe: subscribeLiveLadder,
};
const CALCIO_DB_ORDER_API: LadderOrderApi = {
    send: sendLiveOrderCommand,
    fetchOrders: fetchLiveOrders,
    fetchPositions: fetchLivePositions,
    greenup: sendGreenup,
    armRule: requestRiskRule,  // risk rules RESTANO su path DB by design
    supportsFok: true,
};

// "più recente vince": merge tra live_now dal DB (realtime) e push 'now' locale.
// Senza updated_at confrontabile accettiamo il nuovo (mai bloccarsi su dati vecchi).
function newerLiveNow(prev: LiveNowRow | null, next: LiveNowRow): LiveNowRow {
    if (!prev?.updated_at || !next.updated_at) return next;
    return Date.parse(next.updated_at) >= Date.parse(prev.updated_at) ? next : prev;
}

// Strumenti della colonna DESTRA del terminal (UN tab attivo alla volta, stile Bet Angel:
// One-click | Dutching | Bookmaking | ... come tab, mai tutti i pannelli impilati).
type ToolKey = 'trading' | 'dutching' | 'risk' | 'xhedge' | 'scalper' | 'chart' | 'depth';
const TOOL_TABS: { key: ToolKey; label: string }[] = [
    { key: 'trading', label: 'Trading' },
    { key: 'dutching', label: 'Dutching' },
    { key: 'risk', label: 'Risk' },
    { key: 'xhedge', label: 'X-Hedge' },
    { key: 'scalper', label: 'Scalper' },
    { key: 'chart', label: 'Chart' },
    { key: 'depth', label: 'Depth' },
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
function LiveTradingSection({ markets, orderMode, eventName, eventId, updatedAt, clock }: {
    markets: LiveNowMarket[]; orderMode: string; eventName: string; eventId: string;
    updatedAt: string | null;
    // D32: dati orologio/score dalla pagina (live_now + live_follow — già nel DB).
    clock?: {
        openDate: string | null;
        minute: number | null;
        scoreHome: number | null;
        scoreAway: number | null;
        inplay: boolean | null;
    };
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

    // ---- CANALE LOCALE (desktop): stato reattivo + sorgenti wrappate ----
    // Connesso → ladder/ordini via ws://127.0.0.1 (latenza ~0). Off → prop NON passati
    // ai componenti: usano i loro default DB, comportamento byte-identico a prima.
    const localStatus = useLocalStatus('calcio');
    const localLadder = useMemo(() => localLadderSource('calcio', CALCIO_DB_LADDER_SOURCE), []);
    const localOrders = useMemo(() => localOrderApi('calcio', CALCIO_DB_ORDER_API), []);
    const isLocal = localStatus === 'connected';

    // DICHIARATE IN CIMA (fix pagina bianca 10/07): market/mode sono usate dagli
    // effect sottostanti (dep array valutati AL RENDER) — dichiararle dopo = TDZ
    // ReferenceError a runtime che tsc NON rileva. Mai spostarle sotto gli effect.
    const market = markets.find(m => m.market_id === marketId) ?? null;
    const mode = (['off', 'paper', 'live'].includes((orderMode || 'off').toLowerCase())
        ? (orderMode || 'off').toLowerCase() : 'off') as PanelMode;

    // E36: segnali del motore per l'evento (fetch + realtime) → chip Kelly nel ladder.
    const [signalsRow, setSignalsRow] = useState<LiveSignalsRow | null>(null);
    useEffect(() => {
        let alive = true;
        setSignalsRow(null);
        fetchLiveSignals(eventId).then(r => { if (alive) setSignalsRow(r); }).catch(() => {});
        const unsub = subscribeLiveSignals(eventId, r => { if (r) setSignalsRow(r); });
        return () => { alive = false; unsub(); };
    }, [eventId]);

    // E34: stato dello stop giornaliero (P&L di giornata dal runner, realtime → top bar).
    const [riskState, setRiskState] = useState<LiveRiskState | null>(null);
    useEffect(() => {
        let alive = true;
        fetchLiveRiskState().then(r => { if (alive) setRiskState(r); }).catch(() => {});
        const unsub = subscribeLiveRiskState(r => { if (r) setRiskState(r); });
        return () => { alive = false; unsub(); };
    }, []);

    // E35/A3: posizioni dell'EVENTO (specchio, poll 10s) — alimentano l'esposizione
    // aggregata in top bar E il P&L bloccabile mostrato sui bottoni di cash-out.
    const [eventPositions, setEventPositions] = useState<LivePositionRow[] | null>(null);
    useEffect(() => {
        let alive = true;
        const load = () => {
            fetchLivePositionsEvent(eventId)
                .then(rows => { if (alive) setEventPositions(rows.filter(r => r.mode === mode)); })
                .catch(() => { if (alive) setEventPositions(null); });
        };
        load();
        const t = setInterval(load, 10_000);
        return () => { alive = false; clearInterval(t); };
    }, [eventId, mode]);
    const eventExp = useMemo(
        () => (eventPositions == null ? null : eventExposure(eventPositions)),
        [eventPositions],
    );

    // A2: saldo del conto Betfair (reconcile_worker → betfair_live_account, realtime).
    const [account, setAccount] = useState<LiveAccountRow | null>(null);
    useEffect(() => {
        let alive = true;
        fetchLiveAccount().then(r => { if (alive) setAccount(r); }).catch(() => {});
        const unsub = subscribeLiveAccount(r => { if (r) setAccount(r); });
        return () => { alive = false; unsub(); };
    }, []);

    // A5: heartbeat del runner (chip "runner vivo" in top bar, rosso se stantio).
    const [heartbeat, setHeartbeat] = useState<LiveHeartbeatRow | null>(null);
    useEffect(() => {
        let alive = true;
        fetchLiveHeartbeat().then(r => { if (alive) setHeartbeat(r); }).catch(() => {});
        const unsub = subscribeLiveHeartbeat(r => { if (r) setHeartbeat(r); });
        return () => { alive = false; unsub(); };
    }, []);

    // A9: warning persistenza pre-kickoff — resting EXECUTABLE con persistence LAPSE
    // che DECADRANNO al passaggio in-play (visto in cert: resting dimenticati che
    // spariscono all'off). Poll 15s SOLO pre-match e con modalità ordini attiva;
    // in-play o dopo l'off il warning non ha più senso (i LAPSE sono già decaduti).
    // Best-effort dichiarato: fetch KO → conteggio invariato, mai un warning inventato.
    const [lapseCount, setLapseCount] = useState(0);
    const marketsKey = useMemo(() => markets.map(m => m.market_id).join(','), [markets]);
    const clockInplay = clock?.inplay ?? null;
    const clockOpenDate = clock?.openDate ?? null;
    useEffect(() => {
        if (mode === 'off' || clockInplay === true || !clockOpenDate) { setLapseCount(0); return; }
        let alive = true;
        const api = isLocal ? localOrders : CALCIO_DB_ORDER_API;
        const ids = marketsKey ? marketsKey.split(',') : [];
        const load = async () => {
            if (secondsToOff(clockOpenDate, Date.now()) == null) { if (alive) setLapseCount(0); return; }
            try {
                const lists = await Promise.all(ids.map(id => api.fetchOrders(id)));
                if (alive) setLapseCount(countLapseResting(lists.flat(), mode));
            } catch { /* best-effort: niente warning nuovo su fetch KO */ }
        };
        void load();
        const t = setInterval(() => { void load(); }, 15_000);
        return () => { alive = false; clearInterval(t); };
    }, [mode, isLocal, localOrders, marketsKey, clockInplay, clockOpenDate]);

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
    // A9: secondi all'off (ticchetta con nowTick) — sotto i 5 minuti il warning LAPSE è rosso.
    const offSec = secondsToOff(clockOpenDate, nowTick);
    // F40: pre-goal warning dal modello (nowTick rivaluta la freschezza ogni secondo).
    const preGoal = useMemo(
        () => preGoalWarning(signalsRow, clockInplay, nowTick),
        [signalsRow, clockInplay, nowTick],
    );

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

    // A3: P&L BLOCCABILE mostrato sui bottoni di cash-out (stile Betfair): MTM delle
    // posizioni (specchio) valutate ai prezzi correnti di live_now (stessa matematica
    // del green-up: eventPnl.positionMtm/lockedPnlAt). unpriced>0 → ⚠ dichiarato.
    const priceMaps = useMemo(() => {
        const maps = new Map<string, Map<number, { back: number | null; lay: number | null }>>();
        for (const m of markets) {
            const pm = new Map<number, { back: number | null; lay: number | null }>();
            for (const sel of m.selections ?? []) {
                pm.set(sel.selection_id, { back: sel.back ?? null, lay: sel.lay ?? null });
            }
            maps.set(m.market_id, pm);
        }
        return maps;
    }, [markets]);
    const marketCashout = useMemo(() => {
        if (!eventPositions || !marketId) return null;
        const rows = eventPositions.filter(r => r.market_id === marketId);
        if (!rows.length) return null;
        return eventMtm(rows, priceMaps.get(marketId) ?? new Map());
    }, [eventPositions, marketId, priceMaps]);
    const eventCashout = useMemo(() => {
        if (!eventPositions?.length) return null;
        let mtm = 0; let priced = 0; let unpriced = 0;
        const byMarket = new Map<string, LivePositionRow[]>();
        for (const r of eventPositions) {
            (byMarket.get(r.market_id) ?? byMarket.set(r.market_id, []).get(r.market_id)!).push(r);
        }
        for (const [mid, rows] of byMarket) {
            const res = eventMtm(rows, priceMaps.get(mid) ?? new Map());
            mtm += res.mtm; priced += res.priced; unpriced += res.unpriced;
        }
        return { mtm, priced, unpriced };
    }, [eventPositions, priceMaps]);
    const fmtCashout = (r: { mtm: number; priced: number; unpriced: number } | null): string => {
        if (!r || (r.priced === 0 && r.unpriced === 0)) return '';
        const sign = r.mtm < 0 ? '−' : '+';
        return ` (${sign}€${Math.abs(r.mtm).toFixed(2)}${r.unpriced > 0 ? ' ⚠' : ''})`;
    };

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
            else if (action === 'prev_market' || action === 'next_market') {
                // B16: PageUp/PageDown = cambio tab mercato (come i tool pro)
                if (markets.length < 2) return;
                e.preventDefault();
                const idx = Math.max(0, markets.findIndex(m => m.market_id === marketId));
                const step = action === 'next_market' ? 1 : markets.length - 1;
                selectMarket(markets[(idx + step) % markets.length].market_id);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [mode, handleCashoutMarket, handleCashoutEvent, handleKillSwitch, markets, marketId, selectMarket]);

    if (markets.length === 0) return null;
    const busy = cashingMarket || cashingEvent;
    return (
        <div className="space-y-2">
            {/* ================= TOP BAR STICKY del terminal =================
                Canone dei tool pro (Bet Angel/Fairbot): badge modalità, book% back/lay,
                freschezza dati, azioni d'emergenza SEMPRE visibili (cash-out + kill). */}
            <div className="sticky top-16 z-40 rounded-xl border border-white/10 bg-black/80 backdrop-blur-xl px-3 py-2 flex items-center gap-3 flex-wrap">
                <TerminalModeBadge mode={mode} />
                {/* chip canale LOCALE: solo quando connesso (off → niente, path DB invariato) */}
                {isLocal && (
                    <span
                        className="px-1.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 text-[10px] font-black"
                        title="Canale LOCALE attivo (ws://127.0.0.1:47331): ladder, quote e ordini direttamente dal runner sul PC — latenza ~0. Se cade, fallback automatico al DB."
                    >
                        ⚡ LOCALE
                    </span>
                )}
                {/* D32: minuto+score in-play, countdown all'off pre-match (dati già nel DB) */}
                {clock && (clock.inplay
                    ? (formatMinute(clock.minute) != null || formatScore(clock.scoreHome, clock.scoreAway) != null) && (
                        <span className="text-[10px] font-mono tabular-nums text-emerald-300 font-black"
                            title="Minuto di gioco e punteggio (live_now)">
                            {formatMinute(clock.minute) ?? ''}{formatMinute(clock.minute) && formatScore(clock.scoreHome, clock.scoreAway) ? ' · ' : ''}{formatScore(clock.scoreHome, clock.scoreAway) ?? ''}
                        </span>
                    )
                    : countdownToOff(clock.openDate, nowTick) != null && (
                        <span className="text-[10px] font-mono tabular-nums text-amber-300"
                            title="Countdown all'off (open_date)">
                            OFF in {countdownToOff(clock.openDate, nowTick)}
                        </span>
                    ))}
                {/* A9: warning persistenza pre-kickoff — resting LAPSE che decadranno all'off.
                    Ambra pre-match, ROSSO lampeggiante sotto i 5 minuti (urgenza reale). */}
                {lapseCount > 0 && offSec != null && (
                    <span
                        className={`px-1.5 py-0.5 rounded-md text-[10px] font-black ${
                            offSec < 300
                                ? 'bg-red-500/20 text-red-300 animate-pulse'
                                : 'bg-amber-500/20 text-amber-300'
                        }`}
                        title={`${lapseCount} ordini resting con persistenza LAPSE su questo evento: al calcio d'inizio DECADRANNO (cancellati da Betfair al turn-in-play). Se li vuoi mantenere in-play, ripiazzali con Keep (PERSIST) o Take SP dal ladder; altrimenti verifica che sia voluto.`}
                    >
                        ⚠ {lapseCount} LAPSE decadono all'off
                    </span>
                )}
                {/* E34: P&L di giornata dal runner (settled + MTM) + stato stop */}
                {riskState?.day != null && riskState?.total != null && (
                    <span
                        className={`text-[10px] font-mono tabular-nums font-black ${
                            riskState.stop_fired ? 'text-red-300' : riskState.total < 0 ? 'text-rose-300' : 'text-emerald-300'
                        }`}
                        title={`P&L di giornata (${riskState.day}): settled €${(riskState.realized ?? 0).toFixed(2)} + MTM €${(riskState.open_mtm ?? 0).toFixed(2)}`
                            + (riskState.limit_value != null ? ` · stop a −€${riskState.limit_value}` : ' · stop giornaliero spento')
                            + (riskState.detail?.degraded ? ' · ⚠ stima worst-case' : '')}
                    >
                        {riskState.stop_fired ? '🛑 STOP ' : ''}oggi {riskState.total < 0 ? '−' : '+'}€{Math.abs(riskState.total).toFixed(2)}
                    </span>
                )}
                {/* A2: saldo disponibile del CONTO Betfair (reconcile_worker, realtime) */}
                {account?.available != null && (
                    <span className="text-[10px] font-mono tabular-nums text-white/80"
                        title={`Saldo disponibile sul conto Betfair (getAccountFunds)${account.exposure != null ? ` · exposure conto €${Math.abs(account.exposure).toFixed(2)}` : ''} — agg. ${account.updated_at ? new Date(account.updated_at).toLocaleTimeString('it-IT') : 'n/d'}`}>
                        saldo €{account.available.toFixed(2)}
                    </span>
                )}
                {/* A5: heartbeat del runner — mai un finto verde (unknown = nessun chip) */}
                {heartbeatState(heartbeat?.ts, nowTick) === 'ok' && (
                    <span className="text-[10px] font-mono tabular-nums text-emerald-400/90"
                        title={`Runner vivo (heartbeat ${Math.round(heartbeatAgeSec(heartbeat?.ts, nowTick) ?? 0)}s fa, pid ${heartbeat?.pid ?? '?'})${heartbeatState(heartbeat?.watchdog_ts, nowTick, 90) === 'ok' ? ' · watchdog ATTIVO' : ''}`}>
                        ♥ runner{heartbeatState(heartbeat?.watchdog_ts, nowTick, 90) === 'ok' ? '+wd' : ''}
                    </span>
                )}
                {heartbeatState(heartbeat?.ts, nowTick) === 'unknown' && (
                    <span className="text-[10px] font-mono tabular-nums text-white/40"
                        title="Nessun heartbeat leggibile dal runner (mai visto, o clock sballato): stato SCONOSCIUTO — richiede la migrazione betfair_live_account_heartbeat.sql e il runner attivo.">
                        runner n/d
                    </span>
                )}
                {heartbeatState(heartbeat?.ts, nowTick) === 'stale' && (
                    <span className="text-[10px] font-mono tabular-nums text-red-300 font-black animate-pulse"
                        title={`Ultimo heartbeat ${Math.round(heartbeatAgeSec(heartbeat?.ts, nowTick) ?? 0)}s fa: runner GIÙ o appeso — stop/regole armate NON esistono più!`}>
                        ⚠ RUNNER GIÙ {Math.round(heartbeatAgeSec(heartbeat?.ts, nowTick) ?? 0)}s
                    </span>
                )}
                {/* E35: esposizione worst-case aggregata dell'evento (specchio posizioni) */}
                {eventExp != null && eventExp > 0 && (
                    <span className="text-[10px] font-mono tabular-nums text-amber-200/90"
                        title="Esposizione worst-case aggregata dell'evento (Σ per selezione dallo specchio posizioni; upper bound onesto). I limiti per evento/campionato si impostano nei Controlli runner.">
                        exp evento €{eventExp.toFixed(2)}
                    </span>
                )}
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
                        title={"Cash-out COMPLETO del mercato attivo: annulla i resting, poi green-up del matched (hotkey G). "
                            + "Il P&L mostrato è l'MTM bloccabile ORA (specchio posizioni + prezzi live, agg. ~10s)."
                            + (marketCashout && marketCashout.unpriced > 0 ? ` ⚠ ${marketCashout.unpriced} posizioni senza prezzo (escluse dal numero).` : '')}
                    >
                        {cashingMarket ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Banknote className="w-3.5 h-3.5 mr-1.5" />}
                        Cash-out MERCATO{fmtCashout(marketCashout)}
                    </Button>
                    <Button
                        size="sm"
                        onClick={handleCashoutEvent}
                        disabled={busy || mode === 'off'}
                        className="h-7 bg-rose-600 hover:bg-rose-500 text-white font-black disabled:opacity-40"
                        title={"Cash-out COMPLETO dell'evento: annulla i resting, poi green-up del matched su TUTTI i mercati — conferma rafforzata in LIVE (hotkey X). "
                            + (eventCashout && eventCashout.unpriced > 0 ? ` ⚠ ${eventCashout.unpriced} posizioni senza prezzo (escluse dal numero).` : '')}
                    >
                        {cashingEvent ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <ShieldAlert className="w-3.5 h-3.5 mr-1.5" />}
                        Cash-out EVENTO{fmtCashout(eventCashout)}
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

            {/* F40: PRE-GOAL WARNING dal modello (hazard in live_signals, keepalive runner).
                Solo in-play, solo se fresco e sopra soglia; il numero è SEMPRE mostrato.
                "Copri ora" riusa il cash-out EVENTO esistente (conferma inclusa): l'utente
                decide, mai un'azione automatica. */}
            {preGoal && (
                <div className={`rounded-xl border px-3 py-2 flex items-center gap-3 flex-wrap ${
                    preGoal.level === 'red'
                        ? 'border-red-500/50 bg-red-500/10'
                        : 'border-amber-500/40 bg-amber-500/10'
                }`}>
                    <span
                        className={`text-[11px] font-black ${
                            preGoal.level === 'red' ? 'text-red-300 animate-pulse' : 'text-amber-300'
                        }`}
                        title={'Hazard dal MODELLO in-play: λ gol residui calibrati per lega '
                            + '(minuto, punteggio, cartellini) × distribuzione empirica dei tempi-gol. '
                            + 'NON vede tiri/corner live. Gol attesi nell\'orizzonte: '
                            + `${preGoal.expGoals.toFixed(2)}.`}
                    >
                        ⚠ RISCHIO GOL: P(gol ≤{Math.round(preGoal.horizonMin)}&apos;) ≈ {(preGoal.p * 100).toFixed(0)}%
                        <span className="font-normal opacity-80"> · modello al {preGoal.minute}&apos;</span>
                    </span>
                    <span className="flex-1" />
                    <Button
                        size="sm"
                        onClick={handleCashoutEvent}
                        disabled={busy || mode === 'off'}
                        className={`h-7 font-black disabled:opacity-40 ${
                            preGoal.level === 'red'
                                ? 'bg-red-600 hover:bg-red-500 text-white'
                                : 'bg-amber-500 hover:bg-amber-400 text-black'
                        }`}
                        title="Copri ORA: cash-out COMPLETO dell'evento (annulla resting + green-up del matched su tutti i mercati) — stessa azione e stesse conferme del bottone in top bar."
                    >
                        {cashingEvent ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <ShieldAlert className="w-3.5 h-3.5 mr-1.5" />}
                        Copri ora{fmtCashout(eventCashout)}
                    </Button>
                </div>
            )}

            {/* TABS multi-mercato (stile Bet Angel) + link al workspace Multi-ladder */}
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
                <a
                    href="/multi-ladder"
                    title="Workspace Multi-ladder: N ladder affiancati anche di eventi/sport diversi"
                    className="ml-auto px-3 py-1.5 -mb-px rounded-t-lg text-xs font-bold border-b-2 border-transparent text-amber-300/80 hover:text-amber-200 hover:bg-white/[0.03] whitespace-nowrap"
                >
                    ⧉ Multi-ladder
                </a>
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

                    {/* -------- CENTRO: LADDER dominante o GRID one-click (D28) -------- */}
                    <div className="order-1 xl:order-2 min-w-0 space-y-1.5">
                        {/* toggle vista centrale (persistito nel workspace per-evento) */}
                        <div className="flex items-center gap-1">
                            {(['ladder', 'grid'] as const).map(v => (
                                <button
                                    key={v}
                                    type="button"
                                    aria-pressed={layout.centerView === v}
                                    onClick={() => setLayout(l => setCenterView(l, v))}
                                    title={v === 'ladder'
                                        ? 'Vista ladder classica (colonne prezzo)'
                                        : 'Vista GRID one-click: righe = selezioni, 3 best back + 3 best lay cliccabili'}
                                    className={`px-2.5 py-0.5 rounded-md text-[10px] font-black border transition-colors ${
                                        layout.centerView === v
                                            ? 'bg-amber-400 text-black border-amber-400'
                                            : 'border-white/10 text-white/60 hover:border-amber-400/40'
                                    }`}
                                >
                                    {v === 'ladder' ? 'Ladder' : 'Grid'}
                                </button>
                            ))}
                        </div>
                        {layout.centerView === 'grid' ? (
                            <GridView
                                key={`grid:${market.market_id}`}
                                marketId={market.market_id}
                                marketName={market.market_name || market.market_type}
                                orderMode={mode}
                                sport="calcio"
                                ladderSource={isLocal ? localLadder : undefined}
                                orderApi={isLocal ? localOrders : undefined}
                            />
                        ) : (
                            <LadderView
                                key={market.market_id}
                                marketId={market.market_id}
                                marketName={market.market_name || market.market_type}
                                orderMode={mode}
                                fallbackSelections={panelSelections}
                                signals={signalsRow}
                                ladderSource={isLocal ? localLadder : undefined}
                                orderApi={isLocal ? localOrders : undefined}
                                popout={{ sport: 'calcio', eventId, eventName }}
                                multiSlot={{
                                    sport: 'calcio',
                                    eventId,
                                    marketId: market.market_id,
                                    marketName: market.market_name || market.market_type,
                                    eventName,
                                }}
                            />
                        )}
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
                            /* key={eventId}: lo stato del pannello (form, flag
                               missione) NON deve sopravvivere al cambio evento */
                            <ScalperPanel key={eventId} eventId={eventId} eventName={eventName} />
                        )}
                        {tool === 'chart' && (
                            <SelectionChartPanel key={`chart:${market.market_id}`} marketId={market.market_id} />
                        )}
                        {tool === 'depth' && (
                            <DepthPanel key={`depth:${market.market_id}`} marketId={market.market_id} />
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
            // payload DELETE → row null: manteniamo l'ultimo stato noto.
            // merge col canale locale: il PIÙ RECENTE vince (mai regredire a dati vecchi).
            if (row) setLiveNow(prev => newerLiveNow(prev, row));
        });

        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [selected]);

    // --- canale LOCALE: push 'now' (riga live_now dal runner, cadenza più alta del
    // realtime DB). Filtrati per evento selezionato; merge "più recente vince" con il
    // path DB sopra (che resta attivo invariato come fallback).
    useEffect(() => {
        if (!selected) return undefined;
        const eventId = selected.event_id;
        const unsub = subscribeLocalNow('calcio', (d) => {
            const row = d as LiveNowRow | null;
            if (!row || row.event_id !== eventId) return;
            setLiveNow(prev => newerLiveNow(prev, row));
        });
        return unsub;
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
                        <Link to="/market-watch">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                <span className="hidden md:inline">Market Watch</span><span className="md:hidden">MW</span>
                            </Button>
                        </Link>
                        <Link to="/live-pnl">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                P&amp;L
                            </Button>
                        </Link>
                        <Link to="/trade-journal">
                            <Button variant="outline" size="sm" className="border-white/10 text-muted-foreground hover:text-white">
                                Journal
                            </Button>
                        </Link>
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
                                        clock={{
                                            openDate: selected.open_date ?? null,
                                            minute: liveNow.minute,
                                            scoreHome: liveNow.score_home,
                                            scoreAway: liveNow.score_away,
                                            inplay: liveNow.inplay,
                                        }}
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
