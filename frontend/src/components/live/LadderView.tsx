// ============================================================================
// LadderView — ladder LIVE per-mercato fedele ai software pro (Betting Toolkit,
// Bet Angel, Geeks Toy). SOLA LETTURA (display): mostra profondità back/lay con
// size, scala tick Betfair col PREZZO al centro e LTP evidenziato, volume tradato
// per livello, i TUOI ordini non abbinati sui livelli, WOM e P&L-per-livello.
//
// Per OGNI selezione, 8 colonne (sinistra → destra), come da specifica:
//   1) Tuoi LAY non abbinati        5) Tuoi BACK non abbinati
//   2) Disponibile al BACK (blu)    6) Cash-out/P&L per livello (viola)
//   3) PREZZO (centro) + LTP        7) Volume tradato (EUR) per prezzo
//   4) Disponibile al LAY (rosa)    8) PIQ (posizione in coda) [step successivo]
// (convenzione colori STANDARD Betfair/Bet Angel/Geeks Toy: BACK=blu, LAY=rosa)
//
// DATI: la profondità arriva ESCLUSIVAMENTE dalla tabella realtime `live_ladder`
// (subscribeLiveLadder), pubblicata dal runner dai soli dati dello stream già
// sottoscritto → ZERO chiamate API Betfair. Gli ordini/posizioni (overlay) vengono
// dalle RPC di sola lettura con poll gentile (no martellamento DB).
//
// One-click: NON in questo step. I livelli sono cliccabili (evidenziazione) ma
// nessun ordine viene piazzato; lo stake preset e il bottone Cash-out sono display.
// ============================================================================
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Loader2, ArrowRight, ArrowLeft, Layers } from 'lucide-react';
import { roundToTick, tickUp, tickDown } from '@/lib/matching';
import {
    fetchLiveLadder, subscribeLiveLadder,
    type LiveLadderRow, type LiveLadderSelection,
} from '@/lib/live';
import {
    fetchLiveOrders, fetchLivePositions,
    type LiveOrderRow, type LivePositionRow, type LiveOrderMode,
} from '@/lib/liveOrders';

// modalità ordini del runner (per filtrare l'overlay "i tuoi ordini").
type PanelMode = 'off' | LiveOrderMode;

// preset di stake rapidi (display: il one-click arriva nello step successivo).
const STAKE_PRESETS = [2, 5, 10, 25] as const;

// max righe della ladder visibili: oltre, si centra una finestra sul prezzo corrente
// (evita ladder enormi quando il trd copre un range ampio — comunque il trd non
// determina il range, vedi sotto).
const MAX_ROWS = 42;
const PAD_TICKS = 1; // tick di contesto sopra/sotto il range back/lay/LTP/ordini.

const ORDERS_POLL_MS = 5000; // poll gentile ordini/posizioni (no martellamento DB).

// ------------------------------------------------------------------ formatters
const fmtPrice = (p: number) => (p >= 100 ? p.toFixed(0) : p.toFixed(2));
const fmtSize = (v: number) => {
    if (!Number.isFinite(v) || v <= 0) return '';
    if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
    if (v >= 100) return v.toFixed(0);
    return v.toFixed(v < 10 ? 1 : 0);
};
const fmtVol = (v: number) => {
    if (!Number.isFinite(v) || v <= 0) return '';
    if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
    return v.toFixed(0);
};
const fmtMoney = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;

// somma le size di una lista [prezzo, size][] sul tick arrotondato (robusto a rumore).
function sumByTick(pairs: [number, number][] | undefined): Map<number, number> {
    const m = new Map<number, number>();
    for (const [price, size] of pairs ?? []) {
        if (price == null || !Number.isFinite(price)) continue;
        const t = roundToTick(price);
        m.set(t, (m.get(t) ?? 0) + (Number.isFinite(size) ? size : 0));
    }
    return m;
}

// P&L "what-if" bloccato chiudendo l'intera posizione (greenup) a `price`:
//   locked = L + (W - L)/price        con W = profit se vince, L = profit se perde.
// Vale identico sia che si chiuda con BACK sia con LAY (formula di hedge standard).
function lockedPnlAt(price: number, win: number, lose: number): number {
    if (!Number.isFinite(price) || price <= 1) return lose;
    return lose + (win - lose) / price;
}

// ----------------------------------------------------------- riga della ladder
interface Row {
    price: number;
    backAvail: number;   // disponibile al BACK (col 2, rosa)
    layAvail: number;    // disponibile al LAY  (col 4, blu)
    trd: number;         // volume tradato a questo prezzo (col 7)
    myLay: number;       // tuoi LAY non abbinati (col 1)
    myBack: number;      // tuoi BACK non abbinati (col 5)
}
interface BuiltLadder {
    rows: Row[];         // dall'alto (prezzo alto) verso il basso (prezzo basso)
    maxTrd: number;
    bestBack: number | null;
    bestLay: number | null;
    ltp: number | null;
    hasPosition: boolean;
    win: number;
    lose: number;
}

function buildLadder(
    sel: LiveLadderSelection,
    orders: LiveOrderRow[],
    position: LivePositionRow | null,
): BuiltLadder {
    const backMap = sumByTick(sel.back);
    const layMap = sumByTick(sel.lay);
    const trdMap = sumByTick(sel.trd);

    // i TUOI ordini non abbinati (size_remaining) per prezzo+lato.
    const myLay = new Map<number, number>();
    const myBack = new Map<number, number>();
    for (const o of orders) {
        const rem = o.size_remaining ?? 0;
        if (rem <= 0 || o.price == null || !Number.isFinite(o.price)) continue;
        const t = roundToTick(o.price);
        if (o.side === 'lay') myLay.set(t, (myLay.get(t) ?? 0) + rem);
        else myBack.set(t, (myBack.get(t) ?? 0) + rem);
    }

    // il RANGE visibile è determinato da back/lay/LTP/ordini (NON dal trd, che può
    // coprire un intervallo amplissimo). Il trd viene sovrapposto dove cade dentro.
    const rng: number[] = [];
    for (const p of backMap.keys()) rng.push(p);
    for (const p of layMap.keys()) rng.push(p);
    for (const p of myLay.keys()) rng.push(p);
    for (const p of myBack.keys()) rng.push(p);
    const ltp = sel.ltp != null && Number.isFinite(sel.ltp) ? roundToTick(sel.ltp) : null;
    if (ltp != null) rng.push(ltp);

    const bestBack = sel.back?.[0]?.[0] != null ? roundToTick(sel.back[0][0]) : null;
    const bestLay = sel.lay?.[0]?.[0] != null ? roundToTick(sel.lay[0][0]) : null;

    if (rng.length === 0) {
        return { rows: [], maxTrd: 0, bestBack, bestLay, ltp, hasPosition: false, win: 0, lose: 0 };
    }

    let lo = tickDown(Math.min(...rng), PAD_TICKS);
    let hi = tickUp(Math.max(...rng), PAD_TICKS);

    // costruzione contigua dei tick lo..hi (ascendente).
    const asc: number[] = [];
    let p = lo;
    let guard = 0;
    while (p <= hi + 1e-9 && guard < 400) {
        asc.push(p);
        const nx = tickUp(p, 1);
        if (nx <= p) break;
        p = nx;
        guard++;
    }

    // se troppe righe, centra una finestra MAX_ROWS sul prezzo corrente.
    let ticks = asc;
    if (asc.length > MAX_ROWS) {
        const center = ltp ?? bestBack ?? bestLay ?? asc[Math.floor(asc.length / 2)];
        const half = Math.floor(MAX_ROWS / 2);
        const wlo = tickDown(center, half);
        const whi = tickUp(center, half);
        ticks = asc.filter(t => t >= wlo - 1e-9 && t <= whi + 1e-9);
    }

    let maxTrd = 0;
    const rows: Row[] = ticks.map(t => {
        const trd = trdMap.get(t) ?? 0;
        if (trd > maxTrd) maxTrd = trd;
        return {
            price: t,
            backAvail: backMap.get(t) ?? 0,
            layAvail: layMap.get(t) ?? 0,
            trd,
            myLay: myLay.get(t) ?? 0,
            myBack: myBack.get(t) ?? 0,
        };
    });
    rows.reverse(); // prezzo alto in cima (default Geeks Toy).

    const win = position?.matched_if_win ?? 0;
    const lose = position?.matched_if_lose ?? 0;
    const hasPosition = win !== 0 || lose !== 0;

    return { rows, maxTrd, bestBack, bestLay, ltp, hasPosition, win, lose };
}

// ------------------------------------------------------------------- WOM bar
function WomBar({ wom }: { wom: { back_pct: number; lay_pct: number } | null | undefined }) {
    const back = Math.max(0, Math.min(100, wom?.back_pct ?? 0));
    const lay = Math.max(0, Math.min(100, wom?.lay_pct ?? 0));
    const total = back + lay;
    // normalizza in percentuali della barra (fallback 50/50 se assente).
    const bp = total > 0 ? (back / total) * 100 : 50;
    const lp = 100 - bp;
    const lean = bp - lp; // >0 pressione BACK (blu), <0 pressione LAY (rosa)
    return (
        <div className="flex items-center gap-1.5 min-w-[92px]" title="Weight of Money: pressione vicino al best">
            <span className="text-[9px] uppercase tracking-wider text-muted-foreground/70 font-bold">WOM</span>
            <div className="relative flex-1 h-2.5 rounded-full overflow-hidden bg-white/5 border border-white/10">
                <div className="absolute inset-y-0 left-0 bg-sky-500/70" style={{ width: `${bp}%` }} />
                <div className="absolute inset-y-0 right-0 bg-rose-500/70" style={{ width: `${lp}%` }} />
            </div>
            {lean >= 0
                ? <ArrowLeft className="w-3 h-3 text-sky-300 shrink-0" aria-label="pressione back" />
                : <ArrowRight className="w-3 h-3 text-rose-300 shrink-0" aria-label="pressione lay" />}
            <span className="text-[9px] font-mono tabular-nums text-white/60 w-7 text-right">
                {Math.abs(Math.round(lean))}%
            </span>
        </div>
    );
}

// ----------------------------------------------------- ladder di UNA selezione
const COL_TEMPLATE = '34px 56px 50px 56px 34px 50px 42px 26px'; // 8 colonne

interface SelectionLadderProps {
    sel: LiveLadderSelection;
    orders: LiveOrderRow[];        // ordini della selezione (già filtrati per selection+mode)
    position: LivePositionRow | null;
    stake: number;
    status: string | null;         // OPEN | SUSPENDED | CLOSED
}

const SelectionLadder = memo(function SelectionLadder({
    sel, orders, position, stake, status,
}: SelectionLadderProps) {
    const built = useMemo(() => buildLadder(sel, orders, position), [sel, orders, position]);
    const [armed, setArmed] = useState<number | null>(null); // prezzo evidenziato (no-op, step successivo)

    const onLevel = useCallback((price: number) => {
        setArmed(prev => (prev === price ? null : price)); // toggle evidenziazione
    }, []);

    const closed = (status ?? '').toUpperCase() === 'CLOSED';
    const suspended = (status ?? '').toUpperCase() === 'SUSPENDED';
    const cashOut = built.hasPosition && built.ltp != null
        ? lockedPnlAt(built.ltp, built.win, built.lose)
        : null;

    return (
        <div className="rounded-xl border border-white/10 bg-black/40 overflow-hidden min-w-[348px]">
            {/* header selezione: nome, matched, stake preset, WOM, cash-out */}
            <div className="px-2.5 py-2 border-b border-white/10 bg-white/[0.03] space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                    <span className="font-heading font-bold text-sm text-white truncate" title={sel.name ?? undefined}>
                        {sel.name ?? `#${sel.selection_id}`}
                    </span>
                    <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
                        Matched <span className="text-white/80 font-mono">{fmtMoney(sel.tv)}</span>
                    </span>
                </div>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                    <WomBar wom={sel.wom} />
                    <button
                        type="button"
                        disabled
                        title="Cash-out one-click: disponibile nello step successivo"
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-purple-400/30 bg-purple-500/10 text-[10px] font-bold text-purple-200 disabled:opacity-70 cursor-not-allowed"
                    >
                        Cash-out {cashOut != null ? <span className="font-mono">{fmtMoney(cashOut)}</span> : ''}
                    </button>
                </div>
            </div>

            {/* intestazione colonne */}
            <div
                className="grid items-center text-[8px] uppercase tracking-wider text-muted-foreground/70 px-1 py-0.5 border-b border-white/5 bg-black/30"
                style={{ gridTemplateColumns: COL_TEMPLATE }}
            >
                <span className="text-center text-rose-300/70" title="I tuoi LAY non abbinati">L</span>
                <span className="text-center text-sky-300/80">Back</span>
                <span className="text-center">Prezzo</span>
                <span className="text-center text-rose-300/80">Lay</span>
                <span className="text-center text-sky-300/70" title="I tuoi BACK non abbinati">B</span>
                <span className="text-center text-purple-300/70" title="P&L se chiudi a questo prezzo">P&L</span>
                <span className="text-center" title="Volume tradato a questo prezzo">Trd</span>
                <span className="text-center text-white/30" title="Posizione in coda — step successivo">PIQ</span>
            </div>

            {/* corpo ladder */}
            {built.rows.length === 0 ? (
                <div className="px-3 py-6 text-center text-[11px] text-muted-foreground">
                    Profondità non ancora disponibile.
                </div>
            ) : (
                <div className={`max-h-[420px] overflow-y-auto scrollbar-thin ${closed || suspended ? 'opacity-60' : ''}`}>
                    {built.rows.map(r => {
                        const isLtp = built.ltp != null && Math.abs(r.price - built.ltp) < 1e-9;
                        const isBestBack = built.bestBack != null && Math.abs(r.price - built.bestBack) < 1e-9;
                        const isBestLay = built.bestLay != null && Math.abs(r.price - built.bestLay) < 1e-9;
                        const isArmed = armed != null && Math.abs(r.price - armed) < 1e-9;
                        const pnl = built.hasPosition ? lockedPnlAt(r.price, built.win, built.lose) : null;
                        const trdPct = built.maxTrd > 0 ? (r.trd / built.maxTrd) * 100 : 0;
                        return (
                            <div
                                key={r.price}
                                className={`grid items-stretch border-b border-white/[0.04] text-[10px] leading-tight ${
                                    isArmed ? 'ring-1 ring-inset ring-amber-400/60' : ''
                                }`}
                                style={{ gridTemplateColumns: COL_TEMPLATE }}
                            >
                                {/* 1) tuoi LAY non abbinati */}
                                <div className="flex items-center justify-center">
                                    {r.myLay > 0 && (
                                        <span className="px-1 rounded bg-rose-500/20 text-rose-200 font-bold tabular-nums">
                                            {fmtSize(r.myLay)}
                                        </span>
                                    )}
                                </div>
                                {/* 2) disponibile al BACK (rosa) — cliccabile (no-op) */}
                                <button
                                    type="button"
                                    onClick={() => onLevel(r.price)}
                                    title="Back a questo prezzo (one-click: step successivo)"
                                    className={`flex items-center justify-center font-mono tabular-nums transition-colors ${
                                        r.backAvail > 0
                                            ? 'bg-sky-500/15 text-sky-200 hover:bg-sky-500/25'
                                            : 'text-transparent hover:bg-white/5'
                                    } ${isBestBack ? 'ring-1 ring-inset ring-sky-400/50' : ''}`}
                                >
                                    {fmtSize(r.backAvail) || '·'}
                                </button>
                                {/* 3) PREZZO (centro) — LTP evidenziato */}
                                <button
                                    type="button"
                                    onClick={() => onLevel(r.price)}
                                    className={`flex items-center justify-center font-bold font-mono tabular-nums border-x border-white/10 transition-colors ${
                                        isLtp
                                            ? 'bg-amber-400/25 text-amber-100 ring-1 ring-inset ring-amber-400/70'
                                            : (isBestBack || isBestLay)
                                                ? 'bg-white/[0.06] text-white'
                                                : 'text-white/70 hover:bg-white/5'
                                    }`}
                                    title={isLtp ? 'Ultimo prezzo tradato (LTP)' : undefined}
                                >
                                    {fmtPrice(r.price)}
                                </button>
                                {/* 4) disponibile al LAY (blu) — cliccabile (no-op) */}
                                <button
                                    type="button"
                                    onClick={() => onLevel(r.price)}
                                    title="Lay a questo prezzo (one-click: step successivo)"
                                    className={`flex items-center justify-center font-mono tabular-nums transition-colors ${
                                        r.layAvail > 0
                                            ? 'bg-rose-500/15 text-rose-200 hover:bg-rose-500/25'
                                            : 'text-transparent hover:bg-white/5'
                                    } ${isBestLay ? 'ring-1 ring-inset ring-rose-400/50' : ''}`}
                                >
                                    {fmtSize(r.layAvail) || '·'}
                                </button>
                                {/* 5) tuoi BACK non abbinati */}
                                <div className="flex items-center justify-center">
                                    {r.myBack > 0 && (
                                        <span className="px-1 rounded bg-sky-500/20 text-sky-200 font-bold tabular-nums">
                                            {fmtSize(r.myBack)}
                                        </span>
                                    )}
                                </div>
                                {/* 6) P&L per livello (viola) */}
                                <div className={`flex items-center justify-center font-mono tabular-nums ${
                                    pnl == null ? 'text-white/15'
                                        : pnl > 0 ? 'text-emerald-300/90'
                                            : pnl < 0 ? 'text-rose-300/90' : 'text-purple-200/70'
                                }`}>
                                    {pnl == null ? '·' : (pnl < 0 ? '−' : '') + Math.abs(pnl).toFixed(2)}
                                </div>
                                {/* 7) volume tradato (mini-barra + numero) */}
                                <div className="relative flex items-center justify-end pr-1 overflow-hidden">
                                    {r.trd > 0 && (
                                        <div className="absolute inset-y-0.5 left-0 rounded-sm bg-amber-400/15"
                                            style={{ width: `${trdPct}%` }} />
                                    )}
                                    <span className="relative font-mono tabular-nums text-amber-200/80">{fmtVol(r.trd)}</span>
                                </div>
                                {/* 8) PIQ (step successivo) */}
                                <div className="flex items-center justify-center text-white/20">·</div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* footer: stake selezionato (display) */}
            <div className="px-2.5 py-1.5 border-t border-white/10 bg-black/30 flex items-center justify-between">
                <span className="text-[9px] uppercase tracking-wider text-muted-foreground/70">Stake</span>
                <span className="text-[11px] font-mono font-bold text-amber-300">€{stake.toFixed(2)}</span>
            </div>
        </div>
    );
});

// --------------------------------------------------------------- LadderView
interface Props {
    marketId: string;
    marketName?: string | null;
    orderMode?: string;            // OFF | PAPER | LIVE (da live_now.state.order_mode)
    // selezioni note dal tabellone (live_now): per nome/ordine quando la ladder è ancora vuota.
    fallbackSelections?: { selection_id: number; name: string }[];
}

export function LadderView({ marketId, marketName, orderMode = 'off', fallbackSelections = [] }: Props) {
    const [row, setRow] = useState<LiveLadderRow | null>(null);
    const [loading, setLoading] = useState(true);
    const [orders, setOrders] = useState<LiveOrderRow[]>([]);
    const [positions, setPositions] = useState<LivePositionRow[]>([]);
    const [activeSel, setActiveSel] = useState<number | null>(null);
    const unsubRef = useRef<(() => void) | null>(null);

    const mode: PanelMode = useMemo(() => {
        const m = (orderMode || 'off').toLowerCase();
        return (m === 'paper' || m === 'live') ? m : 'off';
    }, [orderMode]);

    // stake preset condiviso tra tutte le ladder del mercato (display).
    const [stake, setStake] = useState<number>(5);
    const [customStake, setCustomStake] = useState('');

    // ---- snapshot iniziale + sottoscrizione realtime a live_ladder ----
    useEffect(() => {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        setRow(null);
        setLoading(true);
        if (!marketId) { setLoading(false); return; }

        let alive = true;
        fetchLiveLadder(marketId)
            .then(r => { if (alive) setRow(r); })
            .catch((e: any) => {
                // PGRST116 = nessuna riga (ladder non ancora pubblicata): atteso.
                if (e?.code !== 'PGRST116') console.warn('[LadderView] fetchLiveLadder:', e);
            })
            .finally(() => { if (alive) setLoading(false); });

        unsubRef.current = subscribeLiveLadder(marketId, (r) => {
            if (r) setRow(r); // payload DELETE → null: manteniamo l'ultimo stato noto.
        });

        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [marketId]);

    // ---- overlay ordini/posizioni: fetch + poll gentile (no martellamento DB) ----
    useEffect(() => {
        if (!marketId) return;
        let alive = true;
        let busy = false;
        const load = async () => {
            if (busy) return;
            busy = true;
            try {
                const [o, p] = await Promise.all([fetchLiveOrders(marketId), fetchLivePositions(marketId)]);
                if (!alive) return;
                // mostra solo gli ordini/posizioni della modalità attiva (la RPC ritorna entrambe).
                // In OFF non si opera → nessun overlay ordini.
                const o2 = mode === 'off' ? [] : o.filter(r => r.mode === mode);
                const p2 = mode === 'off' ? [] : p.filter(r => r.mode === mode);
                setOrders(o2);
                setPositions(p2);
            } catch (e) {
                // overlay non critico: in caso di errore non blocchiamo la ladder.
                if (alive) console.warn('[LadderView] orders/positions:', e);
            } finally {
                busy = false;
            }
        };
        load();
        const t = setInterval(load, ORDERS_POLL_MS);
        return () => { alive = false; clearInterval(t); };
    }, [marketId, mode]);

    // selezioni da mostrare: quelle della ladder (full-depth) o, in attesa, le fallback.
    const selections: LiveLadderSelection[] = useMemo(() => {
        const fromLadder = row?.ladder?.selections ?? [];
        if (fromLadder.length > 0) return fromLadder;
        // placeholder dalle selezioni note (ladder ancora vuota) → struttura visibile.
        return fallbackSelections.map(s => ({
            selection_id: s.selection_id, name: s.name, ltp: null, tv: null,
            back: [], lay: [], trd: [], wom: { back_pct: 0, lay_pct: 0 },
        }));
    }, [row, fallbackSelections]);

    // indicizzazioni per selezione (ordini/posizioni).
    const ordersBySel = useMemo(() => {
        const m = new Map<number, LiveOrderRow[]>();
        for (const o of orders) {
            const arr = m.get(o.selection_id) ?? [];
            arr.push(o);
            m.set(o.selection_id, arr);
        }
        return m;
    }, [orders]);
    const posBySel = useMemo(() => {
        const m = new Map<number, LivePositionRow>();
        for (const p of positions) m.set(p.selection_id, p); // una posizione per selezione/mercato
        return m;
    }, [positions]);

    const status = row?.status ?? null;
    const updatedMs = row?.ladder?.updated_ms ?? null;

    // troppe selezioni → selettore (una ladder per volta); altrimenti affiancate.
    const MANY = selections.length > 3;
    const effectiveActive = activeSel != null && selections.some(s => s.selection_id === activeSel)
        ? activeSel
        : (selections[0]?.selection_id ?? null);
    const shown = MANY
        ? selections.filter(s => s.selection_id === effectiveActive)
        : selections;

    if (loading && !row) {
        return (
            <Card className="glass-card border-white/10 p-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" /> Caricamento ladder…
            </Card>
        );
    }

    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            {/* header mercato: nome + stake preset condivisi + stato */}
            <div className="px-3 py-2.5 border-b border-white/10 bg-white/[0.03] flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 min-w-0">
                    <Layers className="w-4 h-4 text-amber-400 shrink-0" />
                    <span className="font-heading font-bold text-sm text-white truncate">
                        {marketName || row?.market_name || row?.market_type || marketId}
                    </span>
                    {status && status.toUpperCase() !== 'OPEN' && (
                        <span className={`text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded ${
                            status.toUpperCase() === 'CLOSED'
                                ? 'bg-white/10 text-muted-foreground'
                                : 'bg-red-500/15 text-red-300'
                        }`}>
                            {status.toUpperCase() === 'CLOSED' ? 'Chiuso' : 'Sospeso'}
                        </span>
                    )}
                </div>

                {/* stake preset rapidi 2/5/10/25 + custom (display: one-click step successivo) */}
                <div className="flex items-center gap-1.5">
                    <span className="text-[9px] uppercase tracking-wider text-muted-foreground/70 mr-0.5">Stake</span>
                    {STAKE_PRESETS.map(v => (
                        <button
                            key={v}
                            type="button"
                            onClick={() => { setStake(v); setCustomStake(''); }}
                            className={`px-2 py-0.5 rounded-md text-[11px] font-bold border transition-colors ${
                                stake === v && customStake === ''
                                    ? 'bg-amber-400 text-black border-amber-400'
                                    : 'border-white/10 text-white/70 hover:border-amber-400/40'
                            }`}
                        >
                            {v}
                        </button>
                    ))}
                    <input
                        type="number"
                        min="0"
                        step="0.5"
                        value={customStake}
                        onChange={e => {
                            setCustomStake(e.target.value);
                            const n = Number(e.target.value);
                            if (Number.isFinite(n) && n > 0) setStake(n);
                        }}
                        placeholder="€"
                        className="w-14 bg-black/60 border border-white/10 rounded-md px-1.5 py-0.5 text-[11px] text-white focus:outline-none focus:border-amber-400/50"
                    />
                </div>
            </div>

            {/* selettore selezione quando sono troppe per affiancarle */}
            {MANY && (
                <div className="flex items-center gap-1.5 overflow-x-auto px-3 py-1.5 border-b border-white/5 scrollbar-thin">
                    {selections.map(s => (
                        <button
                            key={s.selection_id}
                            type="button"
                            onClick={() => setActiveSel(s.selection_id)}
                            className={`shrink-0 px-2.5 py-1 rounded-lg text-[11px] font-bold border whitespace-nowrap transition-colors ${
                                s.selection_id === effectiveActive
                                    ? 'bg-primary text-black border-primary'
                                    : 'border-white/10 text-muted-foreground hover:text-white'
                            }`}
                        >
                            {s.name ?? `#${s.selection_id}`}
                        </button>
                    ))}
                </div>
            )}

            {/* ladder affiancate (scroll orizzontale se necessario) */}
            <div className="p-3">
                {selections.length === 0 ? (
                    <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                        Ladder non disponibile: il runner non sta pubblicando la profondità per questo mercato.
                    </div>
                ) : (
                    <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-thin">
                        {shown.map(s => (
                            <SelectionLadder
                                key={s.selection_id}
                                sel={s}
                                orders={ordersBySel.get(s.selection_id) ?? EMPTY_ORDERS}
                                position={posBySel.get(s.selection_id) ?? null}
                                stake={stake}
                                status={status}
                            />
                        ))}
                    </div>
                )}
            </div>

            <div className="px-3 pb-2 -mt-1 flex items-center justify-between text-[9px] text-muted-foreground/70">
                <span>Sola lettura · il one-click arriva nello step successivo</span>
                {updatedMs && <span className="tabular-nums">Aggiornato: {new Date(updatedMs).toLocaleTimeString('it')}</span>}
            </div>
        </Card>
    );
}

// reference stabile per selezioni senza ordini (evita nuove array a ogni render → no re-render del memo).
const EMPTY_ORDERS: LiveOrderRow[] = [];

export default LadderView;
