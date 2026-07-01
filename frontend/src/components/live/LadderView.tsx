// ============================================================================
// LadderView — ladder LIVE per-mercato fedele ai software pro (Betting Toolkit,
// Bet Angel, Geeks Toy). OPERATIVA: profondità back/lay con size, scala tick col
// PREZZO al centro e LTP evidenziato, volume tradato per livello, i TUOI ordini
// non abbinati sui livelli, WOM, P&L-per-livello, PIQ e ONE-CLICK trading.
//
// Per OGNI selezione, 8 colonne (sinistra → destra):
//   1) Tuoi LAY non abbinati        5) Tuoi BACK non abbinati
//   2) Disponibile al BACK (blu)    6) Cash-out/P&L per livello (viola)
//   3) PREZZO (centro) + LTP        7) Volume tradato (EUR) per prezzo
//   4) Disponibile al LAY (rosa)    8) PIQ (coda al tuo livello, stima)
// (convenzione colori STANDARD Betfair/Bet Angel/Geeks Toy: BACK=blu, LAY=rosa)
//
// DATI: la profondità arriva dalla tabella realtime `live_ladder` (subscribeLiveLadder),
// pubblicata dal runner dai soli dati dello stream già sottoscritto → ZERO API Betfair.
// Ordini/posizioni (overlay) dalle RPC di sola lettura con poll gentile.
//
// ONE-CLICK (Fase A) — MEDIATO DAL DB (coda comandi), mode-aware:
//   * OFF   → ladder in sola lettura (nessun ordine possibile).
//   * PAPER → click = ordine SIMULATO immediato (soldi finti).
//   * LIVE  → click = ordine REALE. Per sicurezza: di default ogni click chiede CONFERMA;
//             attivando "1-click" (armato, banner rosso) i click partono diretti come nei
//             tool pro. Click su disp.BACK/LAY = place; click sui tuoi ordini = cancel.
// GREEN-UP / CASH-OUT (Fase B): bottone Cash-out (totale) + slider parziale; il runner
//   calcola l'hedge dalle esposizioni MATCHED reali di flumine (non da numeri pollati).
// ============================================================================
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card } from '@/components/ui/card';
import {
    Loader2, ArrowRight, ArrowLeft, Layers, Zap, ShieldCheck, X, Check,
    Settings2, ChevronUp, ChevronDown, RotateCcw,
} from 'lucide-react';
import { roundToTick, tickUp, tickDown } from '@/lib/matching';
import { lockedPnlAt, piqAhead } from '@/lib/ladderMath';
import {
    loadProfile, saveProfile, resetProfile, defaultProfile, normalizeProfile,
    toggleColumn, reorderColumn, visibleColumns, COLUMN_LABELS,
    type ColumnKey, type LadderProfile,
} from '@/lib/ladderConfig';
import {
    fetchLiveLadder, subscribeLiveLadder,
    type LiveLadderRow, type LiveLadderSelection,
} from '@/lib/live';
import {
    fetchLiveOrders, fetchLivePositions, sendLiveOrderCommand, sendGreenup,
    type LiveOrderRow, type LivePositionRow, type LiveOrderMode, type LiveOrderResult,
    type LivePersistence,
} from '@/lib/liveOrders';

// modalità ordini del runner (per filtrare l'overlay "i tuoi ordini").
type PanelMode = 'off' | LiveOrderMode;
type TradeSide = 'back' | 'lay';

// preset di stake rapidi per il one-click (quick-buttons; lo stake resta LIBERO via input).
const STAKE_PRESETS = [2, 5, 10, 25] as const;

// persistenza ordine (cosa fa Betfair al passaggio in-play), etichette come i tool pro:
//   Keep(PERSIST) = resta a mercato; Lapse(LAPSE) = decade; Take SP(MARKET_ON_CLOSE) = va allo Starting Price.
const PERSISTENCE_OPTIONS: { value: LivePersistence; label: string; title: string }[] = [
    { value: 'PERSIST', label: 'Keep', title: 'Keep: l\'ordine RESTA a mercato al passaggio in-play (PERSIST)' },
    { value: 'LAPSE', label: 'Lapse', title: 'Lapse: l\'ordine DECADE al passaggio in-play (LAPSE, default)' },
    { value: 'MARKET_ON_CLOSE', label: 'Take SP', title: 'Take SP: l\'ordine va allo Starting Price (MARKET_ON_CLOSE)' },
];

// max righe della ladder visibili: oltre, si centra una finestra sul prezzo corrente.
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

// ----------------------------------------------------------- riga della ladder
interface Row {
    price: number;
    backAvail: number;   // disponibile al BACK (col 2, blu)
    layAvail: number;    // disponibile al LAY  (col 4, rosa)
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

    // il RANGE visibile è determinato da back/lay/LTP/ordini (NON dal trd).
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

    const lo = tickDown(Math.min(...rng), PAD_TICKS);
    const hi = tickUp(Math.max(...rng), PAD_TICKS);

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
// larghezza px per colonna (replica il layout storico a 8 colonne).
const COL_WIDTH: Record<ColumnKey, string> = {
    my_lay: '34px',
    avail_back: '56px',
    price: '50px',
    avail_lay: '56px',
    my_back: '34px',
    pnl: '50px',
    trd: '42px',
    piq: '34px',
    wom: '0px', // WOM resta nell'header della selezione, non è una colonna per-riga
};

// intestazioni brevi per colonna (come i ladder pro Geeks Toy / Bet Angel).
const COL_HEADER: Record<ColumnKey, { label: string; cls: string; title?: string }> = {
    my_lay: { label: 'L', cls: 'text-rose-300/70', title: 'I tuoi LAY non abbinati (clic per annullare)' },
    avail_back: { label: 'Back', cls: 'text-sky-300/80' },
    price: { label: 'Prezzo', cls: '' },
    avail_lay: { label: 'Lay', cls: 'text-rose-300/80' },
    my_back: { label: 'B', cls: 'text-sky-300/70', title: 'I tuoi BACK non abbinati (clic per annullare)' },
    pnl: { label: 'P&L', cls: 'text-purple-300/70', title: 'P&L se chiudi a questo prezzo' },
    trd: { label: 'Trd', cls: '', title: 'Volume tradato a questo prezzo' },
    piq: { label: 'PIQ', cls: 'text-white/40', title: 'PIQ: coda STIMATA (piqAhead + volume tradato)' },
    wom: { label: 'WOM', cls: '' },
};

// colonne effettivamente renderizzabili nella griglia per-riga (WOM è escluso: è un
// aggregato di selezione mostrato nell'header, non un valore per-prezzo).
export const GRID_KEYS: ReadonlySet<ColumnKey> = new Set<ColumnKey>([
    'my_lay', 'avail_back', 'price', 'avail_lay', 'my_back', 'pnl', 'trd', 'piq',
]);

// stima RAFFINATA della coda usando il volume tradato: la coda davanti a te non può
// superare (coda_iniziale − volume tradato da quando il tuo ordine è entrato) né la coda
// statica attuale (piqAhead). È una STIMA — Betfair non espone la posizione reale in coda,
// ma il denaro passato in trade a quel prezzo è un proxy di quanto la coda è avanzata.
export function refineQueue(
    staticAhead: number,
    baseline: { trd: number; ahead: number } | undefined,
    currentTrd: number,
): number {
    if (!(staticAhead > 0)) return 0;
    if (!baseline) return staticAhead; // appena entrato: nessun volume passato ancora
    const traded = Math.max(0, (Number.isFinite(currentTrd) ? currentTrd : 0) - baseline.trd);
    const fromVol = Math.max(0, baseline.ahead - traded);
    return Math.min(staticAhead, fromVol);
}

// filtra/normalizza le colonne passate a una griglia: solo GRID_KEYS, 'price' garantita.
function gridColumnsOf(columns: ColumnKey[]): ColumnKey[] {
    const cols = columns.filter((k) => GRID_KEYS.has(k));
    return cols.includes('price') ? cols : ['price', ...cols];
}

interface SelectionLadderProps {
    sel: LiveLadderSelection;
    orders: LiveOrderRow[];        // ordini della selezione (già filtrati per selection+mode)
    position: LivePositionRow | null;
    stake: number;
    status: string | null;         // OPEN | SUSPENDED | CLOSED
    canTrade: boolean;             // mode != off && mercato OPEN
    busy: boolean;                 // un comando è in volo (disabilita i click)
    columns: ColumnKey[];          // colonne griglia (ordine + visibilità) dal profilo
    onPlace: (side: TradeSide, price: number, selectionId: number, selName: string) => void;
    onCancel: (betIds: string[], side: TradeSide, price: number, selName: string) => void;
    onGreenup: (fraction: number, selectionId: number, selName: string) => void;
}

const SelectionLadder = memo(function SelectionLadder({
    sel, orders, position, stake, status, canTrade, busy, columns, onPlace, onCancel, onGreenup,
}: SelectionLadderProps) {
    const built = useMemo(() => buildLadder(sel, orders, position), [sel, orders, position]);
    const [armedPrice, setArmedPrice] = useState<number | null>(null); // evidenziazione livello (OFF/non-trade)
    const [fraction, setFraction] = useState(1); // cash-out parziale (1 = totale)

    // colonne griglia effettive (ordine dal profilo, WOM escluso, 'price' garantita).
    const gridCols = useMemo(() => gridColumnsOf(columns), [columns]);
    const colTemplate = useMemo(() => gridCols.map((k) => COL_WIDTH[k]).join(' '), [gridCols]);

    // baseline PIQ per livello+lato: {trd, ahead} catturata quando il tuo ordine ENTRA in
    // coda a quel prezzo, per stimare l'avanzamento dal volume tradato successivo.
    const piqBaseRef = useRef<Map<string, { trd: number; ahead: number }>>(new Map());
    useEffect(() => {
        const map = piqBaseRef.current;
        const active = new Set<string>();
        for (const r of built.rows) {
            if (r.myBack > 0) {
                const k = `back@${r.price}`;
                active.add(k);
                if (!map.has(k)) map.set(k, { trd: r.trd, ahead: piqAhead(r.myBack, r.layAvail) });
            }
            if (r.myLay > 0) {
                const k = `lay@${r.price}`;
                active.add(k);
                if (!map.has(k)) map.set(k, { trd: r.trd, ahead: piqAhead(r.myLay, r.backAvail) });
            }
        }
        for (const k of Array.from(map.keys())) if (!active.has(k)) map.delete(k);
    }, [built]);

    const selName = sel.name ?? `#${sel.selection_id}`;

    // bet_id dei TUOI ordini non abbinati per livello+lato (per il cancel one-click).
    const myOrdersAt = useMemo(() => {
        const m = new Map<string, string[]>();
        for (const o of orders) {
            if (!o.bet_id || (o.size_remaining ?? 0) <= 0 || o.price == null) continue;
            const key = `${o.side}@${roundToTick(o.price)}`;
            const arr = m.get(key) ?? [];
            arr.push(o.bet_id);
            m.set(key, arr);
        }
        return m;
    }, [orders]);

    const onLevel = useCallback((price: number) => {
        setArmedPrice(prev => (prev === price ? null : price));
    }, []);

    const selId = sel.selection_id;
    const clickBack = useCallback((price: number) => {
        if (canTrade && !busy) onPlace('back', price, selId, selName);
        else onLevel(price);
    }, [canTrade, busy, onPlace, onLevel, selId, selName]);

    const clickLay = useCallback((price: number) => {
        if (canTrade && !busy) onPlace('lay', price, selId, selName);
        else onLevel(price);
    }, [canTrade, busy, onPlace, onLevel, selId, selName]);

    const closed = (status ?? '').toUpperCase() === 'CLOSED';
    const suspended = (status ?? '').toUpperCase() === 'SUSPENDED';
    // Preview cash-out al prezzo di ESECUZIONE reale dell'hedge: se vinco di più sul VINCE
    // (win>lose) il runner LAYa al best LAY; altrimenti BACKa al best BACK. Usare il best
    // opposto (non l'LTP) allinea il numero mostrato a ciò che verrà davvero bloccato.
    const greenPrice = built.win > built.lose ? built.bestLay : built.bestBack;
    const cashOut = built.hasPosition && greenPrice != null
        ? lockedPnlAt(greenPrice, built.win, built.lose)
        : (built.hasPosition && built.ltp != null ? lockedPnlAt(built.ltp, built.win, built.lose) : null);
    const canGreen = canTrade && built.hasPosition && !busy;
    const pct = Math.round(fraction * 100);

    return (
        <div className="rounded-xl border border-white/10 bg-black/40 overflow-hidden min-w-[348px]">
            {/* header selezione: nome, matched, WOM, cash-out + slider parziale */}
            <div className="px-2.5 py-2 border-b border-white/10 bg-white/[0.03] space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                    <span className="font-heading font-bold text-sm text-white truncate" title={selName}>
                        {selName}
                    </span>
                    <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
                        Matched <span className="text-white/80 font-mono">{fmtMoney(sel.tv)}</span>
                    </span>
                </div>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                    <WomBar wom={sel.wom} />
                    <div className="flex items-center gap-1.5">
                        {/* slider cash-out parziale: appare solo con posizione + tradabile */}
                        {canGreen && (
                            <div className="flex items-center gap-1" title="Frazione di cash-out (parziale)">
                                <input
                                    type="range" min={10} max={100} step={5}
                                    value={pct}
                                    onChange={e => setFraction(Math.max(0.1, Math.min(1, Number(e.target.value) / 100)))}
                                    className="w-16 accent-purple-400 cursor-pointer"
                                    aria-label="frazione cash-out"
                                />
                                <span className="text-[9px] font-mono tabular-nums text-purple-200/80 w-7 text-right">{pct}%</span>
                            </div>
                        )}
                        <button
                            type="button"
                            disabled={!canGreen}
                            onClick={() => onGreenup(fraction, selId, selName)}
                            title={canGreen
                                ? `Cash-out ${pct < 100 ? `${pct}% ` : ''}al miglior prezzo (hedge dalle esposizioni reali)`
                                : 'Cash-out: richiede una posizione aperta e mercato operabile'}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-purple-400/40 bg-purple-500/15 text-[10px] font-bold text-purple-100 hover:bg-purple-500/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            Cash-out {pct < 100 ? `${pct}%` : (cashOut != null ? <span className="font-mono">{fmtMoney(cashOut)}</span> : '')}
                        </button>
                    </div>
                </div>
            </div>

            {/* intestazione colonne (ordine dal profilo) */}
            <div
                className="grid items-center text-[8px] uppercase tracking-wider text-muted-foreground/70 px-1 py-0.5 border-b border-white/5 bg-black/30"
                style={{ gridTemplateColumns: colTemplate }}
            >
                {gridCols.map((k) => {
                    const h = COL_HEADER[k];
                    return (
                        <span key={k} className={`text-center ${h.cls}`} title={h.title}>{h.label}</span>
                    );
                })}
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
                        const isArmed = armedPrice != null && Math.abs(r.price - armedPrice) < 1e-9;
                        const pnl = built.hasPosition ? lockedPnlAt(r.price, built.win, built.lose) : null;
                        const trdPct = built.maxTrd > 0 ? (r.trd / built.maxTrd) * 100 : 0;
                        // PIQ: un BACK risiede sul lato LAY del book → coda ≈ layAvail − tuoBack; e
                        // viceversa. Base STATICA (snapshot) piqAhead, RAFFINATA col volume tradato
                        // passato a quel prezzo da quando il tuo ordine è entrato in coda (refineQueue).
                        const piqBackStatic = piqAhead(r.myBack, r.layAvail);
                        const piqLayStatic = piqAhead(r.myLay, r.backAvail);
                        const piqStatic = piqBackStatic + piqLayStatic;
                        const piqEst =
                            refineQueue(piqBackStatic, piqBaseRef.current.get(`back@${r.price}`), r.trd) +
                            refineQueue(piqLayStatic, piqBaseRef.current.get(`lay@${r.price}`), r.trd);
                        const layBetIds = myOrdersAt.get(`lay@${r.price}`) ?? [];
                        const backBetIds = myOrdersAt.get(`back@${r.price}`) ?? [];
                        const canCancel = canTrade && !busy;

                        const cell = (k: ColumnKey) => {
                            switch (k) {
                                case 'my_lay':
                                    // tuoi LAY non abbinati — clic = annulla
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            disabled={r.myLay <= 0 || !canCancel}
                                            onClick={() => onCancel(layBetIds, 'lay', r.price, selName)}
                                            title={r.myLay > 0 ? 'Annulla i tuoi LAY a questo prezzo' : undefined}
                                            className="flex items-center justify-center disabled:cursor-default"
                                        >
                                            {r.myLay > 0 && (
                                                <span className="px-1 rounded bg-rose-500/20 text-rose-200 font-bold tabular-nums hover:bg-rose-500/40 hover:line-through">
                                                    {fmtSize(r.myLay)}
                                                </span>
                                            )}
                                        </button>
                                    );
                                case 'avail_back':
                                    // disponibile al BACK (blu) — clic = back one-click
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            onClick={() => clickBack(r.price)}
                                            title={canTrade ? `BACK €${stake.toFixed(2)} @ ${fmtPrice(r.price)}` : 'Back (sola lettura: modalità OFF)'}
                                            className={`flex items-center justify-center font-mono tabular-nums transition-colors ${
                                                r.backAvail > 0
                                                    ? 'bg-sky-500/15 text-sky-200 hover:bg-sky-500/30'
                                                    : 'text-transparent hover:bg-sky-500/10'
                                            } ${isBestBack ? 'ring-1 ring-inset ring-sky-400/50' : ''} ${busy ? 'pointer-events-none opacity-60' : ''}`}
                                        >
                                            {fmtSize(r.backAvail) || '·'}
                                        </button>
                                    );
                                case 'price':
                                    // PREZZO (centro) — LTP evidenziato
                                    return (
                                        <button
                                            key={k}
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
                                    );
                                case 'avail_lay':
                                    // disponibile al LAY (rosa) — clic = lay one-click
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            onClick={() => clickLay(r.price)}
                                            title={canTrade ? `LAY €${stake.toFixed(2)} @ ${fmtPrice(r.price)}` : 'Lay (sola lettura: modalità OFF)'}
                                            className={`flex items-center justify-center font-mono tabular-nums transition-colors ${
                                                r.layAvail > 0
                                                    ? 'bg-rose-500/15 text-rose-200 hover:bg-rose-500/30'
                                                    : 'text-transparent hover:bg-rose-500/10'
                                            } ${isBestLay ? 'ring-1 ring-inset ring-rose-400/50' : ''} ${busy ? 'pointer-events-none opacity-60' : ''}`}
                                        >
                                            {fmtSize(r.layAvail) || '·'}
                                        </button>
                                    );
                                case 'my_back':
                                    // tuoi BACK non abbinati — clic = annulla
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            disabled={r.myBack <= 0 || !canCancel}
                                            onClick={() => onCancel(backBetIds, 'back', r.price, selName)}
                                            title={r.myBack > 0 ? 'Annulla i tuoi BACK a questo prezzo' : undefined}
                                            className="flex items-center justify-center disabled:cursor-default"
                                        >
                                            {r.myBack > 0 && (
                                                <span className="px-1 rounded bg-sky-500/20 text-sky-200 font-bold tabular-nums hover:bg-sky-500/40 hover:line-through">
                                                    {fmtSize(r.myBack)}
                                                </span>
                                            )}
                                        </button>
                                    );
                                case 'pnl':
                                    // P&L per livello (viola)
                                    return (
                                        <div key={k} className={`flex items-center justify-center font-mono tabular-nums ${
                                            pnl == null ? 'text-white/15'
                                                : pnl > 0 ? 'text-emerald-300/90'
                                                    : pnl < 0 ? 'text-rose-300/90' : 'text-purple-200/70'
                                        }`}>
                                            {pnl == null ? '·' : (pnl < 0 ? '−' : '') + Math.abs(pnl).toFixed(2)}
                                        </div>
                                    );
                                case 'trd':
                                    // volume tradato (mini-barra + numero)
                                    return (
                                        <div key={k} className="relative flex items-center justify-end pr-1 overflow-hidden">
                                            {r.trd > 0 && (
                                                <div className="absolute inset-y-0.5 left-0 rounded-sm bg-amber-400/15"
                                                    style={{ width: `${trdPct}%` }} />
                                            )}
                                            <span className="relative font-mono tabular-nums text-amber-200/80">{fmtVol(r.trd)}</span>
                                        </div>
                                    );
                                case 'piq':
                                    // PIQ (coda STIMATA al tuo livello, raffinata col volume tradato)
                                    return (
                                        <div key={k} className="flex items-center justify-center font-mono tabular-nums text-white/35"
                                            title={piqStatic > 0
                                                ? `Coda STIMATA davanti al tuo ordine · statica ~${fmtSize(piqStatic) || '0'} · con volume tradato ~${fmtSize(piqEst) || '0'}`
                                                : undefined}>
                                            {piqStatic > 0 ? `~${fmtSize(piqEst) || '0'}` : '·'}
                                        </div>
                                    );
                                default:
                                    return null;
                            }
                        };

                        return (
                            <div
                                key={r.price}
                                className={`grid items-stretch border-b border-white/[0.04] text-[10px] leading-tight ${
                                    isArmed ? 'ring-1 ring-inset ring-amber-400/60' : ''
                                }`}
                                style={{ gridTemplateColumns: colTemplate }}
                            >
                                {gridCols.map(cell)}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* footer: stake selezionato */}
            <div className="px-2.5 py-1.5 border-t border-white/10 bg-black/30 flex items-center justify-between">
                <span className="text-[9px] uppercase tracking-wider text-muted-foreground/70">Stake</span>
                <span className="text-[11px] font-mono font-bold text-amber-300">€{stake.toFixed(2)}</span>
            </div>
        </div>
    );
});

// ---------------------------------------------------- tipi azione/conferma
type Intent =
    | { kind: 'place'; selName: string; side: TradeSide; price: number; size: number; selectionId: number; persistence: LivePersistence }
    | { kind: 'cancel'; selName: string; betIds: string[]; side: TradeSide; price: number }
    | { kind: 'greenup'; selName: string; selectionId: number; fraction: number };

interface StatusMsg { tone: 'pending' | 'ok' | 'err'; text: string; }

function intentLabel(it: Intent): string {
    if (it.kind === 'place') {
        const persLabel = PERSISTENCE_OPTIONS.find(o => o.value === it.persistence)?.label ?? it.persistence;
        return `${it.side === 'back' ? 'BACK' : 'LAY'} €${it.size.toFixed(2)} @ ${fmtPrice(it.price)} · ${persLabel} · ${it.selName}`;
    }
    if (it.kind === 'cancel') return `Annulla ${it.betIds.length} ordine/i ${it.side.toUpperCase()} @ ${fmtPrice(it.price)} · ${it.selName}`;
    const pct = Math.round(it.fraction * 100);
    return `Cash-out ${pct < 100 ? `${pct}% ` : ''}· ${it.selName}`;
}

// --------------------------------------------------------------- LadderView
interface Props {
    marketId: string;
    marketName?: string | null;
    orderMode?: string;            // OFF | PAPER | LIVE (da live_now.state.order_mode)
    handicap?: number;             // handicap di mercato (default 0)
    sport?: string;                // sport-key del profilo colonne (persistito per-sport)
    // selezioni note dal tabellone (live_now): per nome/ordine quando la ladder è ancora vuota.
    fallbackSelections?: { selection_id: number; name: string }[];
}

// profilo iniziale delle colonne: se non c'è nulla salvato per lo sport, usa il layout
// storico a 8 colonne (con PIQ visibile); altrimenti il profilo salvato dall'utente.
const LADDER_DEFAULT_ORDER: ColumnKey[] = [
    'my_lay', 'avail_back', 'price', 'avail_lay', 'my_back', 'pnl', 'trd', 'piq',
];
function eightColProfile(sport: string): LadderProfile {
    return normalizeProfile(sport, {
        sport,
        columns: LADDER_DEFAULT_ORDER.map((key) => ({ key, visible: true })),
    });
}
function initLadderProfile(sport: string): LadderProfile {
    const loaded = loadProfile(sport);
    const pristine = JSON.stringify(loaded) === JSON.stringify(defaultProfile(sport));
    return pristine ? eightColProfile(sport) : loaded;
}

export function LadderView({ marketId, marketName, orderMode = 'off', handicap = 0, sport = 'calcio', fallbackSelections = [] }: Props) {
    const [row, setRow] = useState<LiveLadderRow | null>(null);
    const [loading, setLoading] = useState(true);
    const [orders, setOrders] = useState<LiveOrderRow[]>([]);
    const [positions, setPositions] = useState<LivePositionRow[]>([]);
    const [activeSel, setActiveSel] = useState<number | null>(null);
    const unsubRef = useRef<(() => void) | null>(null);

    // ---- profilo COLONNE configurabile (per-sport, persistito in localStorage) ----
    const [profile, setProfile] = useState<LadderProfile>(() => initLadderProfile(sport));
    const [showCols, setShowCols] = useState(false);
    useEffect(() => { setProfile(initLadderProfile(sport)); }, [sport]);
    // colonne griglia effettive (visibili, WOM escluso: resta nell'header selezione).
    const gridColumns = useMemo(
        () => visibleColumns(profile).filter((k) => k !== 'wom'),
        [profile],
    );
    const applyProfile = useCallback((next: LadderProfile) => {
        setProfile(next);
        saveProfile(next); // persisti subito la scelta per lo sport
    }, []);
    const onToggleCol = useCallback((k: ColumnKey) => {
        applyProfile(toggleColumn(profile, k));
    }, [profile, applyProfile]);
    const onMoveCol = useCallback((k: ColumnKey, dir: -1 | 1) => {
        // muovi rispetto ai vicini VISIBILI-nel-picker (WOM escluso), traducendo l'indice
        // nell'array completo del profilo per reorderColumn.
        const list = profile.columns.filter((c) => c.key !== 'wom');
        const pos = list.findIndex((c) => c.key === k);
        const neighbor = list[pos + dir];
        if (!neighbor) return;
        const dest = profile.columns.findIndex((c) => c.key === neighbor.key);
        applyProfile(reorderColumn(profile, k, dest));
    }, [profile, applyProfile]);
    const onResetCols = useCallback(() => {
        resetProfile(sport);
        setProfile(initLadderProfile(sport));
    }, [sport]);

    const mode: PanelMode = useMemo(() => {
        const m = (orderMode || 'off').toLowerCase();
        return (m === 'paper' || m === 'live') ? m : 'off';
    }, [orderMode]);
    const isLive = mode === 'live';

    // stake preset condiviso tra tutte le ladder del mercato (nessun cap: importo LIBERO).
    const [stake, setStake] = useState<number>(5);
    const [customStake, setCustomStake] = useState('');

    // persistenza ordine condivisa (default LAPSE, come i tool pro).
    const [persistence, setPersistence] = useState<LivePersistence>('LAPSE');

    // ---- one-click trading: armamento (LIVE), in-volo, esito, conferma ----
    const [armed, setArmed] = useState(false);   // 1-click LIVE attivo (banner rosso)
    const [busy, setBusy] = useState(false);
    const [statusMsg, setStatusMsg] = useState<StatusMsg | null>(null);
    const [confirm, setConfirm] = useState<Intent | null>(null);
    const busyRef = useRef(false);
    const [refreshTick, setRefreshTick] = useState(0);

    // se la modalità non è LIVE, l'armamento non ha senso: tienilo spento.
    useEffect(() => { if (!isLive) setArmed(false); }, [isLive]);

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
                if (e?.code !== 'PGRST116') console.warn('[LadderView] fetchLiveLadder:', e);
            })
            .finally(() => { if (alive) setLoading(false); });

        unsubRef.current = subscribeLiveLadder(marketId, (r) => {
            if (r) setRow(r);
        });

        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [marketId]);

    // ---- overlay ordini/posizioni: fetch + poll gentile (+ refresh dopo azioni) ----
    useEffect(() => {
        if (!marketId) return;
        let alive = true;
        let inFlight = false;
        const load = async () => {
            if (inFlight) return;
            inFlight = true;
            try {
                const [o, p] = await Promise.all([fetchLiveOrders(marketId), fetchLivePositions(marketId)]);
                if (!alive) return;
                const o2 = mode === 'off' ? [] : o.filter(r => r.mode === mode);
                const p2 = mode === 'off' ? [] : p.filter(r => r.mode === mode);
                setOrders(o2);
                setPositions(p2);
            } catch (e) {
                if (alive) console.warn('[LadderView] orders/positions:', e);
            } finally {
                inFlight = false;
            }
        };
        load();
        const t = setInterval(load, ORDERS_POLL_MS);
        return () => { alive = false; clearInterval(t); };
    }, [marketId, mode, refreshTick]);

    // ---- esecuzione comando (mediato dal DB) ----
    const submit = useCallback(async (factory: () => Promise<LiveOrderResult>, label: string) => {
        if (busyRef.current) return;
        busyRef.current = true;
        setBusy(true);
        setStatusMsg({ tone: 'pending', text: `${label}…` });
        try {
            const res = await factory();
            if (res.ok) {
                const extra = res.detail || (res.status ? `stato ${res.status}` : '');
                setStatusMsg({ tone: 'ok', text: `✓ ${label}${extra ? ` — ${extra}` : ''}` });
            } else {
                setStatusMsg({ tone: 'err', text: `✗ ${label}: ${res.error ?? 'non eseguito'}` });
            }
        } catch (e: any) {
            setStatusMsg({ tone: 'err', text: `✗ ${label}: ${e?.message ?? 'errore'}` });
        } finally {
            busyRef.current = false;
            setBusy(false);
            setRefreshTick(t => t + 1); // riallinea subito ordini/posizioni
        }
    }, []);

    const execute = useCallback((it: Intent) => {
        const label = intentLabel(it);
        if (it.kind === 'place') {
            submit(() => sendLiveOrderCommand({
                action: 'place', mode: mode as LiveOrderMode, market_id: marketId,
                selection_id: it.selectionId, handicap, side: it.side,
                order_type: 'LIMIT', price: it.price, size: it.size, persistence: it.persistence,
            }), label);
        } else if (it.kind === 'cancel') {
            const ids = it.betIds;
            submit(async () => {
                let last: LiveOrderResult = { ok: true, action: 'cancel', mode };
                let done = 0;
                for (const bet_id of ids) {
                    last = await sendLiveOrderCommand({ action: 'cancel', mode: mode as LiveOrderMode, market_id: marketId, bet_id });
                    if (!last.ok) break;
                    done++;
                }
                // successo parziale: dillo chiaramente (quali ordini restano da verificare).
                if (!last.ok && done > 0) {
                    last = { ...last, error: `${done}/${ids.length} annullati — verifica gli ordini residui. ${last.error ?? ''}`.trim() };
                }
                return last;
            }, label);
        } else {
            submit(() => sendGreenup({
                marketId, selectionId: it.selectionId, mode: mode as LiveOrderMode,
                handicap, fraction: it.fraction,
            }), label);
        }
    }, [submit, mode, marketId, handicap]);

    // richiesta azione: in LIVE non-armato chiede conferma; altrimenti esegue subito.
    const requestAction = useCallback((it: Intent) => {
        if (mode === 'off') return;
        if (busyRef.current) return;
        if (isLive && !armed) { setConfirm(it); return; }
        execute(it);
    }, [mode, isLive, armed, execute]);

    const onPlace = useCallback((side: TradeSide, price: number, selectionId: number, selName: string) => {
        requestAction({ kind: 'place', selName, side, price, size: stakeRef.current, selectionId, persistence: persistenceRef.current });
    }, [requestAction]);

    const onCancel = useCallback((betIds: string[], side: TradeSide, price: number, selName: string) => {
        if (!betIds.length) return;
        requestAction({ kind: 'cancel', selName, betIds, side, price });
    }, [requestAction]);

    const onGreenup = useCallback((fraction: number, selectionId: number, selName: string) => {
        requestAction({ kind: 'greenup', selName, selectionId, fraction });
    }, [requestAction]);

    // toggle armamento 1-click (LIVE): conferma esplicita all'attivazione.
    const toggleArmed = useCallback(() => {
        setArmed(prev => {
            if (!prev) {
                const ok = window.confirm(
                    '1-CLICK REALE: ogni clic su BACK/LAY o sui tuoi ordini piazzerà/annullerà un ordine ' +
                    'con SOLDI VERI SENZA ulteriore conferma. Attivare?'
                );
                return ok ? true : false;
            }
            return false;
        });
    }, []);

    // selezioni da mostrare: quelle della ladder (full-depth) o, in attesa, le fallback.
    const selections: LiveLadderSelection[] = useMemo(() => {
        const fromLadder = row?.ladder?.selections ?? [];
        if (fromLadder.length > 0) return fromLadder;
        return fallbackSelections.map(s => ({
            selection_id: s.selection_id, name: s.name, ltp: null, tv: null,
            back: [], lay: [], trd: [], wom: { back_pct: 0, lay_pct: 0 },
        }));
    }, [row, fallbackSelections]);

    // ref a stake/persistenza per i callback stabili (evita di rigenerarli a ogni cambio).
    const stakeRef = useRef(stake);
    stakeRef.current = stake;
    const persistenceRef = useRef(persistence);
    persistenceRef.current = persistence;

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
        for (const p of positions) m.set(p.selection_id, p);
        return m;
    }, [positions]);

    const status = row?.status ?? null;
    const updatedMs = row?.ladder?.updated_ms ?? null;
    const isOpen = (status ?? '').toUpperCase() === 'OPEN';
    const canTrade = mode !== 'off' && isOpen;

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
            {/* header mercato: nome + modalità + stake preset + 1-click + stato */}
            <div className="px-3 py-2.5 border-b border-white/10 bg-white/[0.03] flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 min-w-0">
                    <Layers className="w-4 h-4 text-amber-400 shrink-0" />
                    <span className="font-heading font-bold text-sm text-white truncate">
                        {marketName || row?.market_name || row?.market_type || marketId}
                    </span>
                    {/* badge modalità ordini */}
                    <span className={`text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded shrink-0 ${
                        mode === 'live' ? 'bg-red-500/20 text-red-300'
                            : mode === 'paper' ? 'bg-emerald-500/15 text-emerald-300'
                                : 'bg-white/10 text-muted-foreground'
                    }`}>
                        {mode === 'live' ? '🔴 LIVE' : mode === 'paper' ? 'PAPER' : 'OFF'}
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

                <div className="flex items-center gap-1.5 flex-wrap">
                    {/* stake preset rapidi 2/5/10/25 + custom */}
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
                    {/* persistenza ordine (solo se operabile): Keep / Lapse / Take SP, default Lapse */}
                    {mode !== 'off' && (
                        <div className="flex items-center gap-1 ml-1" title="Cosa fa l'ordine al passaggio in-play">
                            <span className="text-[9px] uppercase tracking-wider text-muted-foreground/70 mr-0.5">Persist</span>
                            {PERSISTENCE_OPTIONS.map(o => (
                                <button
                                    key={o.value}
                                    type="button"
                                    onClick={() => setPersistence(o.value)}
                                    title={o.title}
                                    className={`px-2 py-0.5 rounded-md text-[11px] font-bold border transition-colors ${
                                        persistence === o.value
                                            ? 'bg-white/90 text-black border-white/90'
                                            : 'border-white/10 text-white/70 hover:border-white/40'
                                    }`}
                                >
                                    {o.label}
                                </button>
                            ))}
                        </div>
                    )}
                    {/* toggle 1-click (solo LIVE): armato = niente conferma per clic */}
                    {isLive && (
                        <button
                            type="button"
                            onClick={toggleArmed}
                            title={armed
                                ? '1-click REALE ATTIVO: i clic partono diretti. Clic per disattivare.'
                                : 'Attiva 1-click REALE (niente conferma per clic).'}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-black border transition-colors ${
                                armed
                                    ? 'bg-red-500 text-white border-red-500 animate-pulse'
                                    : 'border-red-400/40 text-red-300 hover:bg-red-500/15'
                            }`}
                        >
                            <Zap className="w-3 h-3" /> 1-CLICK
                        </button>
                    )}
                    {/* column-picker: mostra/nascondi e riordina le colonne del ladder (per-sport) */}
                    <div className="relative">
                        <button
                            type="button"
                            onClick={() => setShowCols(s => !s)}
                            title="Colonne del ladder (per-sport, salvate)"
                            aria-label="Configura colonne del ladder"
                            aria-expanded={showCols}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold border transition-colors ${
                                showCols
                                    ? 'bg-white/90 text-black border-white/90'
                                    : 'border-white/10 text-white/70 hover:border-white/40'
                            }`}
                        >
                            <Settings2 className="w-3 h-3" /> Colonne
                        </button>
                        {showCols && (
                            <div className="absolute right-0 top-full mt-1 z-30 w-56 rounded-lg border border-white/15 bg-black/95 backdrop-blur p-2 shadow-xl">
                                <div className="flex items-center justify-between mb-1.5">
                                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground/80 font-bold">
                                        Colonne · {sport}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={onResetCols}
                                        title="Ripristina layout predefinito"
                                        aria-label="Ripristina colonne predefinite"
                                        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold text-white/60 hover:text-white hover:bg-white/10"
                                    >
                                        <RotateCcw className="w-3 h-3" /> Reset
                                    </button>
                                </div>
                                <ul className="space-y-0.5">
                                    {profile.columns.filter(c => c.key !== 'wom').map((c, i, arr) => (
                                        <li key={c.key} className="flex items-center gap-1.5 px-1 py-0.5 rounded hover:bg-white/5">
                                            <input
                                                type="checkbox"
                                                checked={c.visible}
                                                disabled={c.key === 'price'}
                                                onChange={() => onToggleCol(c.key)}
                                                aria-label={`Mostra colonna ${COLUMN_LABELS[c.key]}`}
                                                className="accent-amber-400 cursor-pointer disabled:cursor-not-allowed"
                                            />
                                            <span className={`flex-1 text-[11px] ${c.visible ? 'text-white/85' : 'text-white/40'}`}>
                                                {COLUMN_LABELS[c.key]}
                                                {c.key === 'price' && <span className="ml-1 text-[8px] text-muted-foreground/70">(fissa)</span>}
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => onMoveCol(c.key, -1)}
                                                disabled={i === 0}
                                                aria-label={`Sposta ${COLUMN_LABELS[c.key]} su`}
                                                className="p-0.5 rounded text-white/60 hover:text-white hover:bg-white/10 disabled:opacity-25 disabled:cursor-default"
                                            >
                                                <ChevronUp className="w-3 h-3" />
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => onMoveCol(c.key, 1)}
                                                disabled={i === arr.length - 1}
                                                aria-label={`Sposta ${COLUMN_LABELS[c.key]} giù`}
                                                className="p-0.5 rounded text-white/60 hover:text-white hover:bg-white/10 disabled:opacity-25 disabled:cursor-default"
                                            >
                                                <ChevronDown className="w-3 h-3" />
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* banner armamento LIVE */}
            {isLive && armed && (
                <div className="px-3 py-1 bg-red-500/15 border-b border-red-500/30 flex items-center gap-2 text-[10px] font-bold text-red-200">
                    <Zap className="w-3 h-3" /> 1-CLICK REALE ATTIVO — ogni clic piazza/annulla con SOLDI VERI senza conferma.
                </div>
            )}

            {/* barra di CONFERMA (LIVE non-armato): money-critical, esplicita */}
            {confirm && (
                <div className="px-3 py-2 bg-red-500/15 border-b border-red-500/40 flex items-center justify-between gap-3 flex-wrap">
                    <span className="text-[11px] font-bold text-red-100 flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5" /> Confermi <span className="font-mono">{intentLabel(confirm)}</span> <span className="text-red-300">(REALE)</span>?
                    </span>
                    <div className="flex items-center gap-1.5">
                        <button
                            type="button"
                            onClick={() => { const it = confirm; setConfirm(null); if (it) execute(it); }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-red-500 text-white text-[11px] font-bold hover:bg-red-600"
                        >
                            <Check className="w-3 h-3" /> Conferma
                        </button>
                        <button
                            type="button"
                            onClick={() => setConfirm(null)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-white/15 text-white/80 text-[11px] font-bold hover:bg-white/10"
                        >
                            <X className="w-3 h-3" /> Annulla
                        </button>
                    </div>
                </div>
            )}

            {/* esito ultimo comando */}
            {statusMsg && (
                <div className={`px-3 py-1 border-b text-[10px] font-medium flex items-center gap-1.5 ${
                    statusMsg.tone === 'ok' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-200'
                        : statusMsg.tone === 'err' ? 'bg-red-500/10 border-red-500/20 text-red-200'
                            : 'bg-white/5 border-white/10 text-muted-foreground'
                }`}>
                    {statusMsg.tone === 'pending' && <Loader2 className="w-3 h-3 animate-spin" />}
                    {statusMsg.text}
                </div>
            )}

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
                                canTrade={canTrade}
                                busy={busy}
                                columns={gridColumns}
                                onPlace={onPlace}
                                onCancel={onCancel}
                                onGreenup={onGreenup}
                            />
                        ))}
                    </div>
                )}
            </div>

            <div className="px-3 pb-2 -mt-1 flex items-center justify-between text-[9px] text-muted-foreground/70">
                <span>
                    {mode === 'off'
                        ? 'Sola lettura (modalità OFF) · per operare avvia il runner in PAPER/LIVE'
                        : isLive
                            ? (armed ? '1-click REALE attivo' : 'Clic = ordine REALE con conferma')
                            : 'Clic = ordine simulato (paper) immediato'}
                </span>
                {updatedMs && <span className="tabular-nums">Aggiornato: {new Date(updatedMs).toLocaleTimeString('it')}</span>}
            </div>
        </Card>
    );
}

// reference stabile per selezioni senza ordini (evita nuove array a ogni render → no re-render del memo).
const EMPTY_ORDERS: LiveOrderRow[] = [];

export default LadderView;
