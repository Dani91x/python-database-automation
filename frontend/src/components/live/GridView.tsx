// ============================================================================
// GridView — "Grid one-click" (roadmap D28): vista ALTERNATIVA al ladder in
// stile Bet Angel grid. Una RIGA per selezione: nome + LTP (flash direzionale),
// P&L di posizione, micro-sparkline della storia LTP, 3 best BACK (blu) e
// 3 best LAY (rosa) cliccabili, stake per riga (persistito per sport).
//
// MONEY-CRITICAL — replica ESATTA della semantica di LadderView:
//   * mode: solo 'paper'|'live' piazzano; OFF/ignoto = SOLA LETTURA fail-safe
//     (celle NON-bottone, nessun click possibile).
//   * LIVE non armato: il primo click NON piazza → barra di conferma sticky con
//     i dettagli dell'ordine (liability per i LAY via layLiabilityFromSize) che
//     SCADE dopo CONFIRM_TTL_MS (prezzo stantio = serve un nuovo click).
//     Toggle "armato" (badge rosso ARMATO) = click LIVE diretti come nei tool pro.
//   * PAPER: piazza sempre diretto (soldi finti).
//   * anti-doppio-invio: guardia su inFlightRef (non solo disabled dei bottoni).
//   * il prezzo inviato è quello della CELLA al momento del click → LIMIT esplicito.
//   * esito: successo → riga verde con bet_id (+ reset conferma LIVE via
//     shouldResetLiveConfirm); errore → banner ROSSO esplicito (mai silenzioso),
//     la conferma NON si resetta (l'utente può ritentare senza ri-cliccare).
//   * mercato SUSPENDED/CLOSED → celle disabilitate + badge stato.
//   * stake invalido (NaN/≤0) → celle della riga DISABILITATE (come stakeInvalid
//     di LadderView: mai inviare uno stake diverso da quello visualizzato).
//
// DATI: fetch iniziale + subscribe della sorgente ladder (default: live_ladder
// calcio, identico a LadderView), cleanup su unmount/cambio mercato. Posizioni
// da fetchPositions al mount + refresh dopo ogni ordine (P&L per riga).
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';
import { flashDir, STAKE_MIN, STAKE_STEP } from '@/lib/ladderMath';
import {
    fetchLiveLadder, subscribeLiveLadder,
    type LiveLadderRow, type LiveLadderSelection,
} from '@/lib/live';
import {
    fetchLiveOrders, fetchLivePositions, sendLiveOrderCommand,
    layLiabilityFromSize, shouldResetLiveConfirm,
    type LiveOrderMode, type LivePositionRow,
} from '@/lib/liveOrders';
import type { LadderSource, LadderOrderApi } from '@/components/live/LadderView';

// Default IDENTICI a LadderView (funzioni calcio): comportamento football invariato
// quando i prop non sono passati. Le costanti private di LadderView NON sono
// importabili → ridefinite qui con le stesse funzioni di @/lib/live e @/lib/liveOrders.
const DEFAULT_LADDER_SOURCE: LadderSource = {
    fetch: fetchLiveLadder,
    subscribe: subscribeLiveLadder,
};
const DEFAULT_ORDER_API: LadderOrderApi = {
    send: sendLiveOrderCommand,
    fetchOrders: fetchLiveOrders,
    fetchPositions: fetchLivePositions,
};

// Scadenza della barra di conferma LIVE (stessa semantica del fix M1 del ladder):
// oltre questa finestra il prezzo dell'intent è stantio e serve un nuovo click.
const CONFIRM_TTL_MS = 6000;
// cadenza refresh posizioni (stesso ordine di grandezza di LadderView ORDERS_POLL_MS)
const POSITIONS_POLL_MS = 5000;
const FLASH_MS = 260;          // durata del flash direzionale sull'LTP
const SPARK_MAX = 120;         // max punti della storia LTP per la sparkline
const STAKE_DEFAULT = 2;       // stake di riga di default (min/step da ladderMath)

type TradeSide = 'back' | 'lay';
type PanelMode = 'off' | LiveOrderMode;

// intent di piazzamento: chiusura sul prezzo della CELLA al momento del click.
interface PlaceIntent {
    side: TradeSide;
    price: number;
    size: number;
    selectionId: number;
    selName: string;
}
interface StatusMsg {
    tone: 'ok' | 'err' | 'pending';
    text: string;
}

interface Props {
    marketId: string;
    marketName?: string | null;
    orderMode?: string;              // OFF | PAPER | LIVE (fail-safe: assente/ignoto = off)
    handicap?: number;               // default 0
    sport?: string;                  // 'calcio' | 'tennis' (solo per chiavi localStorage)
    ladderSource?: LadderSource;     // default: fetch/subscribe live_ladder calcio
    orderApi?: LadderOrderApi;       // default: DEFAULT calcio
}

// ------------------------------------------------------------------ formatters
const fmtPrice = (p: number) => (p >= 100 ? p.toFixed(0) : p.toFixed(2));
const fmtSize = (v: number) => {
    if (!Number.isFinite(v) || v <= 0) return '';
    if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
    if (v >= 100) return v.toFixed(0);
    return v.toFixed(v < 10 ? 1 : 0);
};
// P&L con segno esplicito (− unicode come fmtMoney del ladder).
const fmtPnl = (v: number) => `${v < 0 ? '−' : v > 0 ? '+' : ''}€${Math.abs(v).toFixed(2)}`;
const pnlCls = (v: number) =>
    v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-slate-400';

// title della cella: identifica lato/prezzo/selezione e lo stake che verrebbe inviato.
function cellTitle(
    side: TradeSide, price: number, selName: string,
    stake: number | null, readOnly: boolean,
): string {
    const s = side === 'back' ? 'BACK' : 'LAY';
    if (readOnly) return `${s} @ ${fmtPrice(price)} · ${selName} — sola lettura`;
    if (stake == null) return `${s} @ ${fmtPrice(price)} · ${selName} — stake non valido`;
    return `${s} €${stake.toFixed(2)} @ ${fmtPrice(price)} · ${selName}`;
}

// ---------------------------------------------------------- stake persistiti
// UNA mappa {selection_id: stake} per sport (indipendente dal mercato), chiave
// `gridStake:${sport}`. Su disco vanno SOLO valori validi (mai NaN persistiti).
function loadStakes(key: string): Record<number, string> {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return {};
        const obj = JSON.parse(raw) as Record<string, unknown>;
        const out: Record<number, string> = {};
        for (const [k, v] of Object.entries(obj)) {
            const n = Number(v);
            if (Number.isFinite(n) && n > 0) out[Number(k)] = String(n);
        }
        return out;
    } catch {
        return {};
    }
}

// ------------------------------------------------------------- micro-sparkline
// SVG inline 60×16 della storia LTP (polyline slate-400 1.5px, nessuna libreria).
function Sparkline({ points }: { points: number[] }) {
    if (points.length < 2) return <span className="text-[10px] text-slate-600">—</span>;
    const min = Math.min(...points);
    const max = Math.max(...points);
    const span = max - min || 1;
    const pts = points
        .map((v, i) => {
            const x = (i / (points.length - 1)) * 60;
            const y = 15 - ((v - min) / span) * 14;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(' ');
    return (
        <svg width={60} height={16} viewBox="0 0 60 16" className="block" aria-hidden="true">
            <polyline points={pts} fill="none" stroke="#94a3b8" strokeWidth={1.5} />
        </svg>
    );
}

export function GridView({
    marketId, marketName, orderMode = 'off', handicap = 0, sport = 'calcio',
    ladderSource = DEFAULT_LADDER_SOURCE, orderApi = DEFAULT_ORDER_API,
}: Props) {
    const [row, setRow] = useState<LiveLadderRow | null>(null);
    const [loading, setLoading] = useState(true);
    const [positions, setPositions] = useState<LivePositionRow[]>([]);
    const [statusMsg, setStatusMsg] = useState<StatusMsg | null>(null);
    const [confirmIntent, setConfirmIntent] = useState<PlaceIntent | null>(null);
    const [armed, setArmed] = useState(false);       // 1-click LIVE (badge rosso)
    const [busy, setBusy] = useState(false);
    const [flash, setFlash] = useState<Record<number, 'up' | 'down'>>({});
    const [, setLtpTick] = useState(0);              // bump render: la storia LTP vive in ref

    const unsubRef = useRef<(() => void) | null>(null);
    const inFlightRef = useRef(false);               // anti-doppio-invio (MONEY-CRITICAL)
    const histRef = useRef<Map<number, number[]>>(new Map());      // storia LTP per sparkline
    const prevLtpRef = useRef<Map<number, number>>(new Map());     // per flashDir
    const flashTimersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

    // fail-safe: solo 'paper'|'live' possono piazzare; assente/ignoto = off.
    const mode: PanelMode = useMemo(() => {
        const m = (orderMode || '').toLowerCase();
        return m === 'paper' || m === 'live' ? m : 'off';
    }, [orderMode]);
    const isLive = mode === 'live';

    // se la modalità non è LIVE, l'armamento non ha senso: tienilo spento.
    useEffect(() => { if (!isLive) setArmed(false); }, [isLive]);

    // ---- stake per riga: mappa {selection_id: stake} persistita per sport ----
    const stakeKey = `gridStake:${sport}`;
    const [stakes, setStakes] = useState<Record<number, string>>(() => loadStakes(stakeKey));
    useEffect(() => { setStakes(loadStakes(stakeKey)); }, [stakeKey]);
    const setStakeFor = useCallback((selId: number, raw: string) => {
        setStakes(prev => {
            const next = { ...prev, [selId]: raw };
            try {
                const valid: Record<string, number> = {};
                for (const [k, v] of Object.entries(next)) {
                    const n = Number(v);
                    if (v !== '' && Number.isFinite(n) && n > 0) valid[k] = n;
                }
                localStorage.setItem(stakeKey, JSON.stringify(valid));
            } catch { /* storage pieno/negato: la sessione continua senza persistenza */ }
            return next;
        });
    }, [stakeKey]);
    const stakeRawOf = (selId: number): string => stakes[selId] ?? String(STAKE_DEFAULT);
    // MONEY-CRITICAL (come stakeInvalid di LadderView): input NaN/≤0 → null → riga bloccata.
    const stakeOf = (selId: number): number | null => {
        const raw = stakeRawOf(selId);
        const n = Number(raw);
        return raw !== '' && Number.isFinite(n) && n > 0 ? n : null;
    };

    // ---- snapshot iniziale + sottoscrizione realtime (pattern del ladder) ----
    useEffect(() => {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        setRow(null);
        setLoading(true);
        histRef.current = new Map();      // nuova storia prezzi per il nuovo mercato
        prevLtpRef.current = new Map();
        if (!marketId) { setLoading(false); return; }

        let alive = true;
        ladderSource.fetch(marketId)
            .then(r => { if (alive) setRow(r); })
            .catch((e: unknown) => { console.warn('[GridView] fetchLadder:', e); })
            .finally(() => { if (alive) setLoading(false); });

        unsubRef.current = ladderSource.subscribe(marketId, (r) => { if (r) setRow(r); });

        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [marketId, ladderSource]);

    // ---- storia LTP (sparkline) + flash direzionale con flashDir di ladderMath ----
    useEffect(() => {
        const sels = row?.ladder?.selections ?? [];
        if (!sels.length) return;
        for (const s of sels) {
            if (s.ltp == null || !Number.isFinite(s.ltp)) continue;
            // buffer sparkline (max SPARK_MAX punti, mutato in place)
            let buf = histRef.current.get(s.selection_id);
            if (!buf) { buf = []; histRef.current.set(s.selection_id, buf); }
            buf.push(s.ltp);
            if (buf.length > SPARK_MAX) buf.splice(0, buf.length - SPARK_MAX);
            // flash direzionale (timeout FLASH_MS, un timer per selezione)
            const dir = flashDir(prevLtpRef.current.get(s.selection_id), s.ltp);
            prevLtpRef.current.set(s.selection_id, s.ltp);
            if (dir) {
                const selId = s.selection_id;
                setFlash(f => ({ ...f, [selId]: dir }));
                const old = flashTimersRef.current.get(selId);
                if (old) clearTimeout(old);
                flashTimersRef.current.set(selId, setTimeout(() => {
                    setFlash(f => {
                        if (!(selId in f)) return f;
                        const rest = { ...f };
                        delete rest[selId];
                        return rest;
                    });
                }, FLASH_MS));
            }
        }
        setLtpTick(t => t + 1); // il render legge histRef aggiornato
    }, [row]);
    useEffect(() => () => {
        for (const t of flashTimersRef.current.values()) clearTimeout(t);
    }, []);

    // ---- posizioni (P&L per riga): fetch al mount + POLL periodico (fix review HIGH:
    // i fill arrivano ASINCRONI — fill esterni, dutching, cash-out, bot — e senza poll
    // il P&L resterebbe congelato al mount senza alcun segnale) + refresh dopo ogni ordine.
    const posSeqRef = useRef(0);
    const refreshPositions = useCallback(async () => {
        const seq = ++posSeqRef.current;
        if (!marketId || mode === 'off') { setPositions([]); return; }
        try {
            const p = await orderApi.fetchPositions(marketId, mode as LiveOrderMode);
            if (seq === posSeqRef.current) setPositions(p.filter(r => r.mode === mode));
        } catch (e) {
            console.warn('[GridView] positions:', e);
        }
    }, [marketId, mode, orderApi]);
    useEffect(() => {
        void refreshPositions();
        if (mode === 'off') return undefined;
        const t = setInterval(() => { void refreshPositions(); }, POSITIONS_POLL_MS);
        return () => clearInterval(t);
    }, [refreshPositions, mode]);

    // ---- MONEY-CRITICAL: la barra di conferma LIVE SCADE (prezzo stantio) ----
    useEffect(() => {
        if (!confirmIntent) return;
        const t = setTimeout(() => {
            setConfirmIntent(null);
            setStatusMsg({ tone: 'err', text: '✗ Conferma scaduta (mercato mosso): riclicca il prezzo per ripetere.' });
        }, CONFIRM_TTL_MS);
        return () => clearTimeout(t);
    }, [confirmIntent]);

    const status = row?.status ?? null;
    const isOpen = (status ?? '').toUpperCase() === 'OPEN';
    const selections: LiveLadderSelection[] = row?.ladder?.selections ?? [];

    const intentLabel = (it: PlaceIntent) =>
        `${it.side === 'back' ? 'BACK' : 'LAY'} €${it.size.toFixed(2)} @ ${fmtPrice(it.price)} · ${it.selName}`;

    // ---- esecuzione: LIMIT esplicito al prezzo della cella, mediato da orderApi ----
    const execute = async (it: PlaceIntent) => {
        // anti-doppio-invio su ref: se un invio è in corso, ignora OGNI altro click.
        if (inFlightRef.current) return;
        if (mode === 'off') return; // belt & braces: mai piazzare in sola lettura
        inFlightRef.current = true;
        setBusy(true);
        const label = intentLabel(it);
        setStatusMsg({ tone: 'pending', text: `${label}…` });
        try {
            const res = await orderApi.send({
                action: 'place', mode: mode as LiveOrderMode, market_id: marketId,
                selection_id: it.selectionId, handicap, side: it.side,
                order_type: 'LIMIT', price: it.price, size: it.size, persistence: 'LAPSE',
            });
            if (res.ok) {
                setStatusMsg({ tone: 'ok', text: `✓ ${label}${res.bet_id ? ` — bet ${res.bet_id}` : ''}` });
            } else {
                // errore SEMPRE esplicito (banner rosso), mai silenzioso.
                setStatusMsg({ tone: 'err', text: `✗ ${label}: ${res.error ?? 'non eseguito'}` });
            }
            // MONEY-CRITICAL: la conferma LIVE è one-shot — si resetta SOLO su successo;
            // su errore resta aperta (retry senza ri-cliccare la cella).
            if (shouldResetLiveConfirm(isLive, res.ok)) setConfirmIntent(null);
        } catch (e) {
            setStatusMsg({ tone: 'err', text: `✗ ${label}: ${(e as Error)?.message ?? 'errore'}` });
        } finally {
            inFlightRef.current = false;
            setBusy(false);
            void refreshPositions(); // riallinea subito il P&L dopo ogni ordine
        }
    };

    // ---- richiesta dal click su cella: guardie mode/stato/stake, poi conferma o place ----
    const requestPlace = (side: TradeSide, price: number, sel: LiveLadderSelection) => {
        if (mode === 'off') return;                 // fail-safe: sola lettura
        if (inFlightRef.current) return;            // invio già in corso
        if (!isOpen) return;                        // SUSPENDED/CLOSED: mai piazzare
        const size = stakeOf(sel.selection_id);
        if (size == null) {
            setStatusMsg({ tone: 'err', text: '✗ Stake non valido: correggi l\'importo della riga prima di piazzare.' });
            return;
        }
        const it: PlaceIntent = {
            side, price, size,
            selectionId: sel.selection_id,
            selName: sel.name ?? String(sel.selection_id),
        };
        // LIVE non armato → primo click = SOLO conferma (barra sticky con TTL).
        if (isLive && !armed) { setConfirmIntent(it); return; }
        void execute(it);
    };

    // toggle armamento 1-click (LIVE): conferma esplicita all'attivazione, come il ladder.
    const toggleArmed = useCallback(() => {
        setArmed(prev => {
            if (!prev) {
                return window.confirm(
                    '1-CLICK REALE: ogni clic su una cella della griglia piazzerà un ordine ' +
                    'con SOLDI VERI SENZA ulteriore conferma. Attivare?'
                );
            }
            return false;
        });
    }, []);

    // ---- book% back/lay: Σ(100/best); se UN best manca → null (MAI parziale) ----
    const books = useMemo(() => {
        const sels = row?.ladder?.selections ?? [];
        if (!sels.length) return { back: null as number | null, lay: null as number | null };
        let back = 0, lay = 0;
        let backOk = true, layOk = true;
        for (const s of sels) {
            const bb = s.back?.[0]?.[0];
            const bl = s.lay?.[0]?.[0];
            if (bb == null || !Number.isFinite(bb) || bb <= 1) backOk = false; else back += 100 / bb;
            if (bl == null || !Number.isFinite(bl) || bl <= 1) layOk = false; else lay += 100 / bl;
        }
        return { back: backOk ? back : null, lay: layOk ? lay : null };
    }, [row]);

    const posBySel = useMemo(() => {
        const m = new Map<number, LivePositionRow>();
        for (const p of positions) m.set(p.selection_id, p);
        return m;
    }, [positions]);

    // ------------------------------------------------------------------ render
    const readOnly = mode === 'off';

    const renderCell = (side: TradeSide, level: [number, number] | undefined, sel: LiveLadderSelection) => {
        const bg = side === 'back' ? 'bg-sky-950/60 hover:bg-sky-900/60' : 'bg-pink-950/60 hover:bg-pink-900/60';
        if (!level) {
            return <div className="flex h-9 items-center justify-center text-slate-700">—</div>;
        }
        const stake = stakeOf(sel.selection_id);
        const selName = sel.name ?? String(sel.selection_id);
        const title = cellTitle(side, level[0], selName, stake, readOnly);
        const inner = (
            <>
                <div className="font-bold leading-tight text-slate-100">{fmtPrice(level[0])}</div>
                <div className="text-[10px] leading-tight text-slate-400">{fmtSize(level[1])}</div>
            </>
        );
        if (readOnly) {
            // SOLA LETTURA: nessun bottone, cella non cliccabile per costruzione.
            return (
                <div title={title} className={`flex h-9 w-full flex-col items-center justify-center ${bg} opacity-70`}>
                    {inner}
                </div>
            );
        }
        return (
            <button
                type="button"
                title={title}
                disabled={!isOpen || stake == null || busy}
                onClick={() => requestPlace(side, level[0], sel)}
                className={`flex h-9 w-full flex-col items-center justify-center ${bg} transition-colors disabled:cursor-not-allowed disabled:opacity-40`}
            >
                {inner}
            </button>
        );
    };

    return (
        <Card className="space-y-2 border-slate-800 bg-slate-950/60 p-2">
            {/* header: nome mercato, modalità, stato, armamento */}
            <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-slate-200">
                    {marketName ?? row?.market_name ?? marketId}
                </span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                    isLive ? 'bg-red-900/70 text-red-200'
                        : mode === 'paper' ? 'bg-emerald-900/60 text-emerald-200'
                            : 'bg-slate-800 text-slate-400'
                }`}>
                    {mode === 'off' ? 'off · sola lettura' : mode}
                </span>
                {status && !isOpen && (
                    <span className="rounded bg-amber-900/70 px-1.5 py-0.5 text-[10px] font-bold text-amber-200">
                        {status}
                    </span>
                )}
                {isLive && (
                    <button
                        type="button"
                        onClick={toggleArmed}
                        title={armed
                            ? '1-click REALE ATTIVO: ogni clic piazza senza conferma. Clicca per disattivare.'
                            : 'Attiva il 1-click REALE (i clic piazzeranno SENZA conferma)'}
                        className={`rounded border px-1.5 py-0.5 text-[10px] ${
                            armed ? 'border-red-500 bg-red-950/70 text-red-200'
                                : 'border-slate-700 text-slate-400 hover:text-slate-200'
                        }`}
                    >
                        🔓 armato
                    </button>
                )}
                {isLive && armed && (
                    <span className="animate-pulse rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                        ARMATO
                    </span>
                )}
            </div>

            {/* barra di conferma LIVE sticky (scade dopo CONFIRM_TTL_MS) */}
            {confirmIntent && (
                <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded border border-red-600 bg-red-950/90 px-3 py-2">
                    <span className="text-xs font-medium text-red-100">
                        {`Ordine REALE: ${confirmIntent.side === 'back' ? 'BACK' : 'LAY'} €${confirmIntent.size.toFixed(2)} @ ${fmtPrice(confirmIntent.price)} su ${confirmIntent.selName}`
                            + (confirmIntent.side === 'lay'
                                ? ` — responsabilità €${layLiabilityFromSize(confirmIntent.size, confirmIntent.price).toFixed(2)}`
                                : '')}
                    </span>
                    <button
                        type="button"
                        onClick={() => { const it = confirmIntent; if (it) void execute(it); }}
                        disabled={busy}
                        className="rounded bg-red-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-red-500 disabled:opacity-50"
                    >
                        CONFERMA REALE
                    </button>
                    <button
                        type="button"
                        onClick={() => setConfirmIntent(null)}
                        className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-300 hover:text-white"
                    >
                        Annulla
                    </button>
                </div>
            )}

            {/* esito: successo verde / errore ROSSO esplicito / invio in corso */}
            {statusMsg && (
                <div
                    role={statusMsg.tone === 'err' ? 'alert' : 'status'}
                    className={`rounded px-2 py-1 text-xs ${
                        statusMsg.tone === 'ok' ? 'bg-emerald-950/70 text-emerald-300'
                            : statusMsg.tone === 'err' ? 'border border-red-600 bg-red-950/80 font-medium text-red-200'
                                : 'bg-slate-800/70 text-slate-300'
                    }`}
                >
                    {statusMsg.text}
                </div>
            )}

            {loading ? (
                <div className="flex items-center gap-2 p-3 text-xs text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin" /> Caricamento griglia…
                </div>
            ) : selections.length === 0 ? (
                <div className="p-3 text-xs text-slate-500">Nessun dato ladder per questo mercato.</div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-[11px]">
                        <thead>
                            <tr className="text-[10px] uppercase text-slate-500">
                                <th className="px-2 py-1 text-left">Selezione</th>
                                <th className="px-1 py-1">P&L</th>
                                <th className="px-1 py-1">LTP</th>
                                <th colSpan={3} className="px-1 py-1 text-sky-400">Back</th>
                                <th colSpan={3} className="px-1 py-1 text-pink-400">Lay</th>
                                <th className="px-1 py-1">Stake</th>
                            </tr>
                        </thead>
                        <tbody>
                            {selections.map(sel => {
                                const pos = posBySel.get(sel.selection_id);
                                const f = flash[sel.selection_id];
                                const stake = stakeOf(sel.selection_id);
                                // back dal 3° al best (best adiacente al centro), lay dal best al 3°
                                const backLevels = [sel.back?.[2], sel.back?.[1], sel.back?.[0]];
                                const layLevels = [sel.lay?.[0], sel.lay?.[1], sel.lay?.[2]];
                                return (
                                    <tr key={sel.selection_id} className="border-t border-slate-800/60">
                                        <td className="px-2 py-1">
                                            <div className="max-w-[150px] truncate font-medium text-slate-200">
                                                {sel.name ?? sel.selection_id}
                                            </div>
                                            <div className={`text-[10px] tabular-nums transition-colors ${
                                                f === 'up' ? 'font-bold text-emerald-400'
                                                    : f === 'down' ? 'font-bold text-rose-400'
                                                        : 'text-slate-400'
                                            }`}>
                                                LTP {sel.ltp != null && Number.isFinite(sel.ltp) ? fmtPrice(sel.ltp) : '—'}
                                            </div>
                                        </td>
                                        <td className="px-1 py-1 text-center tabular-nums">
                                            {pos ? (
                                                <>
                                                    <div className={`text-[10px] font-semibold ${pnlCls(pos.matched_if_win)}`}>
                                                        {fmtPnl(pos.matched_if_win)}
                                                    </div>
                                                    <div className={`text-[10px] ${pnlCls(pos.matched_if_lose)}`}>
                                                        {fmtPnl(pos.matched_if_lose)}
                                                    </div>
                                                </>
                                            ) : (
                                                <span className="text-slate-600">—</span>
                                            )}
                                        </td>
                                        <td className="px-1 py-1">
                                            <Sparkline points={histRef.current.get(sel.selection_id) ?? []} />
                                        </td>
                                        {backLevels.map((lvl, i) => (
                                            <td key={`b${i}`} className="w-14 p-0">{renderCell('back', lvl, sel)}</td>
                                        ))}
                                        {layLevels.map((lvl, i) => (
                                            <td key={`l${i}`} className="w-14 p-0">{renderCell('lay', lvl, sel)}</td>
                                        ))}
                                        <td className="px-1 py-1">
                                            <input
                                                type="number"
                                                inputMode="decimal"
                                                min={STAKE_MIN}
                                                step={STAKE_STEP}
                                                aria-label={`Stake ${sel.name ?? sel.selection_id}`}
                                                value={stakeRawOf(sel.selection_id)}
                                                onChange={e => setStakeFor(sel.selection_id, e.target.value)}
                                                disabled={readOnly}
                                                className={`w-14 rounded border bg-slate-900 px-1 py-0.5 text-right text-[11px] ${
                                                    stake == null && !readOnly
                                                        ? 'border-red-600 text-red-300'
                                                        : 'border-slate-700 text-slate-200'
                                                } disabled:opacity-50`}
                                            />
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                        <tfoot>
                            <tr className="border-t border-slate-800/60 text-[10px] tabular-nums">
                                <td colSpan={3} className="px-2 py-1 text-right text-slate-500">book%</td>
                                <td colSpan={3} className={`px-1 py-1 text-center ${
                                    books.back != null && books.back < 100 ? 'font-semibold text-amber-400' : 'text-slate-400'
                                }`}>
                                    {books.back == null ? '—' : `${books.back.toFixed(2)}%`}
                                </td>
                                <td colSpan={3} className={`px-1 py-1 text-center ${
                                    books.lay != null && books.lay > 100 ? 'font-semibold text-amber-400' : 'text-slate-400'
                                }`}>
                                    {books.lay == null ? '—' : `${books.lay.toFixed(2)}%`}
                                </td>
                                <td />
                            </tr>
                        </tfoot>
                    </table>
                </div>
            )}
        </Card>
    );
}
