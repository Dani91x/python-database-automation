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
import { memo, useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { Card } from '@/components/ui/card';
import {
    Loader2, ArrowRight, ArrowLeft, Layers, Zap, ShieldCheck, X, Check,
    Settings2, ChevronUp, ChevronDown, RotateCcw, Crosshair, LineChart, Ruler,
    Keyboard, ExternalLink,
} from 'lucide-react';
import { roundToTick, tickUp, tickDown } from '@/lib/matching';
import {
    lockedPnlAt, piqAhead, windowAround, flashDir, stepStake, nextPreset,
} from '@/lib/ladderMath';
import { tickWindow } from '@/lib/priceAxis';
import { pushSample, type PriceSample } from '@/lib/ladderChart';
import { resolveHotkey } from '@/lib/workspace';
import { addSlot, loadSlots, saveSlots, type LadderSlot } from '@/lib/multiLadder';
import { MiniPriceChart } from './MiniPriceChart';
import { PriceAxisBar } from './PriceAxisBar';
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
    type LivePersistence, type LiveOrderCommand,
} from '@/lib/liveOrders';

// ---------------------------------------------------------------------------
// Dependency injection: sorgente DATI (ladder) e API ORDINI iniettabili. I DEFAULT
// sono ESATTAMENTE le funzioni del calcio → il comportamento football è INVARIATO
// (byte-identico) quando i prop non sono passati. Il tennis inietta le sue funzioni
// dedicate (tabelle `tennis_*`), senza MAI toccare i dati del calcio.
export interface LadderSource {
    fetch: (marketId: string) => Promise<LiveLadderRow | null>;
    subscribe: (marketId: string, cb: (row: LiveLadderRow | null) => void) => () => void;
}
export interface LadderGreenupArgs {
    marketId: string;
    selectionId: number;
    mode: LiveOrderMode;
    handicap?: number;
    fraction?: number;
    // "greening column" (Bet Angel): chiudi la posizione A QUESTO prezzo assoluto invece
    // che al best opposto — l'ordine può restare sul book come take-profit resting.
    targetPrice?: number;
}
export interface LadderOrderApi {
    send: (cmd: LiveOrderCommand) => Promise<LiveOrderResult>;
    // mode è passato per le sorgenti che filtrano lato RPC (tennis); i default calcio lo ignorano.
    fetchOrders: (marketId: string, mode: LiveOrderMode) => Promise<LiveOrderRow[]>;
    fetchPositions: (marketId: string, mode: LiveOrderMode) => Promise<LivePositionRow[]>;
    // opzionale: se assente, il pulsante Cash-out (green-up) non viene mostrato.
    greenup?: (args: LadderGreenupArgs) => Promise<LiveOrderResult>;
}

const DEFAULT_LADDER_SOURCE: LadderSource = {
    fetch: fetchLiveLadder,
    subscribe: subscribeLiveLadder,
};
const DEFAULT_ORDER_API: LadderOrderApi = {
    send: sendLiveOrderCommand,
    fetchOrders: fetchLiveOrders,
    fetchPositions: fetchLivePositions,
    greenup: sendGreenup,
};

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

// Scadenza della barra di conferma LIVE (fix M1): oltre questa finestra il prezzo
// dell'intent è considerato stantio e serve un nuovo clic.
const CONFIRM_TTL_MS = 6000;

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
    centerOverride: number | null = null,
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

    const win0 = position?.matched_if_win ?? 0;
    const lose0 = position?.matched_if_lose ?? 0;

    let ticks: number[];
    if (centerOverride != null && Number.isFinite(centerOverride)) {
        // NAVIGAZIONE MANUALE (auto-center OFF / price bar / frecce): la finestra è
        // costruita dalla SCALA TICK PURA attorno al centro scelto — navigabile su tutto
        // il range 1.01–1000 anche dove il book non ha (ancora) denaro, come i tool pro.
        // tickWindow clampa ai bordi SENZA restringersi (fix review: vicino a 1000 il
        // vecchio loop tickUp troncava la finestra).
        ticks = tickWindow(centerOverride, MAX_ROWS);
    } else {
        if (rng.length === 0) {
            return {
                rows: [], maxTrd: 0, bestBack, bestLay, ltp,
                hasPosition: win0 !== 0 || lose0 !== 0, win: win0, lose: lose0,
            };
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

        // se troppe righe, finestra MAX_ROWS centrata sul prezzo corrente (clampata ai
        // bordi: mai meno di MAX_ROWS righe quando la scala ne ha abbastanza).
        const center = ltp ?? bestBack ?? bestLay ?? asc[Math.floor(asc.length / 2)];
        ticks = windowAround(asc, center, MAX_ROWS);
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

    const hasPosition = win0 !== 0 || lose0 !== 0;

    return { rows, maxTrd, bestBack, bestLay, ltp, hasPosition, win: win0, lose: lose0 };
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

// payload di un drag-to-move in corso (una selezione): quali bet_id/lato/prezzo/size
// stiamo trascinando da un livello all'altro (cancel-then-replace al rilascio).
interface DragPayload {
    side: TradeSide;
    fromPrice: number;
    betIds: string[];
    size: number;
}

// informazioni della riga sotto il cursore (per le hotkey B/L/C/frecce del terminal).
export interface HoverInfo {
    selectionId: number;
    selName: string;
    price: number;
    backIds: string[];
    layIds: string[];
}

interface SelectionLadderProps {
    sel: LiveLadderSelection;
    orders: LiveOrderRow[];        // ordini della selezione (già filtrati per selection+mode)
    position: LivePositionRow | null;
    stake: number;
    stakeMode: 'stake' | 'liability'; // interpreta lo stake dei LAY come puntata o responsabilità
    status: string | null;         // OPEN | SUSPENDED | CLOSED
    canTrade: boolean;             // mode != off && mercato OPEN
    busy: boolean;                 // un comando è in volo (disabilita i click)
    columns: ColumnKey[];          // colonne griglia (ordine + visibilità) dal profilo
    greenupSupported: boolean;     // se false, il Cash-out non è mostrato (orderApi.greenup assente)
    enableDragMove: boolean;       // se true, i tuoi ordini si trascinano tra livelli (cancel→replace)
    recenterSeq: number;           // segnale globale "ricentra sul prezzo corrente" (hotkey Spazio)
    nudge: { seq: number; selId: number; dir: 1 | -1 } | null; // frecce: sposta la vista di 1 tick
    samples: PriceSample[] | undefined; // serie LTP per il mini-chart (buffer del parent, mutato in place)
    onPlace: (side: TradeSide, price: number, selectionId: number, selName: string) => void;
    onCancel: (betIds: string[], side: TradeSide, price: number, selName: string) => void;
    onGreenup: (fraction: number, selectionId: number, selName: string) => void;
    onGreenupAt: (price: number, selectionId: number, selName: string) => void; // greening column
    onCancelSide: (side: TradeSide, betIds: string[], selectionId: number, selName: string) => void;
    onMoveOrder: (betIds: string[], side: TradeSide, toPrice: number, size: number, selectionId: number, selName: string) => void;
    onHoverRow: (info: HoverInfo | null) => void;
    // MONEY-CRITICAL: il contenuto è scivolato sotto il cursore FERMO (auto-scroll/shift
    // della finestra) → il parent invalida l'hover di questa selezione (hotkey sospese
    // fino al prossimo movimento reale del mouse: mai ordini a un prezzo "vecchio").
    onWindowShift: (selectionId: number) => void;
}

// mappa flash vuota, referenza stabile (nessun re-render quando non c'è nulla da lampeggiare).
const EMPTY_FLASHES: ReadonlyMap<string, 'up' | 'down'> = new Map();

const SelectionLadder = memo(function SelectionLadder({
    sel, orders, position, stake, stakeMode, status, canTrade, busy, columns, greenupSupported, enableDragMove,
    recenterSeq, nudge, samples,
    onPlace, onCancel, onGreenup, onGreenupAt, onCancelSide, onMoveOrder, onHoverRow, onWindowShift,
}: SelectionLadderProps) {
    // ---- navigazione/centraggio (B11/B18): auto-center sul LTP (default, come Bet Angel)
    // o centro MANUALE (click su prezzo/price bar/frecce). localSeq forza lo scroll one-shot.
    const [autoCenter, setAutoCenter] = useState(true);
    const [manualCenter, setManualCenter] = useState<number | null>(null);
    const [localSeq, setLocalSeq] = useState(0);
    const [showChart, setShowChart] = useState(false);
    const [showAxis, setShowAxis] = useState(false);

    const built = useMemo(
        () => buildLadder(sel, orders, position, autoCenter ? null : manualCenter),
        [sel, orders, position, autoCenter, manualCenter],
    );
    const builtRef = useRef(built);
    builtRef.current = built;
    const [armedPrice, setArmedPrice] = useState<number | null>(null); // evidenziazione livello (OFF/non-trade)
    const [fraction, setFraction] = useState(1); // cash-out parziale (1 = totale)

    // ---- flash direzionale (B12): confronto disponibilità back/lay per livello tra due
    // update del book; il LTP lampeggia col colore della direzione dell'ultimo trade.
    const [flashes, setFlashes] = useState<ReadonlyMap<string, 'up' | 'down'>>(EMPTY_FLASHES);
    const [ltpPulse, setLtpPulse] = useState<'up' | 'down' | null>(null);
    const prevAvailRef = useRef<Map<number, { back: number; lay: number }>>(new Map());
    const prevLtpRef = useRef<number | null>(null);
    useEffect(() => {
        const prev = prevAvailRef.current;
        const next = new Map<number, { back: number; lay: number }>();
        const fl = new Map<string, 'up' | 'down'>();
        for (const r of built.rows) {
            next.set(r.price, { back: r.backAvail, lay: r.layAvail });
            const p = prev.get(r.price);
            const db = flashDir(p?.back, r.backAvail);
            const dl = flashDir(p?.lay, r.layAvail);
            if (db) fl.set(`b@${r.price}`, db);
            if (dl) fl.set(`l@${r.price}`, dl);
        }
        prevAvailRef.current = next;
        let pulse: 'up' | 'down' | null = null;
        if (built.ltp != null && prevLtpRef.current != null && built.ltp !== prevLtpRef.current) {
            pulse = built.ltp > prevLtpRef.current ? 'up' : 'down';
        }
        if (built.ltp != null) prevLtpRef.current = built.ltp;
        if (fl.size === 0 && pulse == null) return;
        if (fl.size) setFlashes(fl);
        if (pulse) setLtpPulse(pulse);
        const t = setTimeout(() => { setFlashes(EMPTY_FLASHES); setLtpPulse(null); }, 260);
        return () => clearTimeout(t);
    }, [built]);

    // ---- scroll del corpo ladder: con auto-center segue il prezzo a ogni update; con
    // centro manuale scrolla SOLO sui segnali espliciti (click prezzo / Spazio / frecce).
    const scrollRef = useRef<HTMLDivElement | null>(null);
    const centerRowRef = useRef<HTMLDivElement | null>(null);
    const lastSeqRef = useRef(-1);
    useEffect(() => {
        const seq = recenterSeq * 100_000 + localSeq; // combinazione monotona dei due segnali
        const seqChanged = seq !== lastSeqRef.current;
        lastSeqRef.current = seq;
        if (!autoCenter && !seqChanged) return;
        const el = scrollRef.current;
        const rowEl = centerRowRef.current;
        if (!el || !rowEl) return;
        const target = Math.max(0, rowEl.offsetTop - el.clientHeight / 2 + rowEl.clientHeight / 2);
        if (Math.abs(el.scrollTop - target) > 2) {
            el.scrollTop = target;
            // MONEY-CRITICAL (fix review HIGH): lo scroll programmatico sposta il contenuto
            // sotto un cursore fermo senza generare mouseenter → l'hover memorizzato
            // punterebbe a un prezzo NON più sotto il mouse. Invalidalo.
            onWindowShift(sel.selection_id);
        }
    }, [built, autoCenter, recenterSeq, localSeq, onWindowShift, sel.selection_id]);

    // MONEY-CRITICAL (fix review HIGH): anche uno SHIFT della finestra di righe a parità
    // di scrollTop (book che si muove con auto-center) cambia cosa sta sotto il cursore.
    // Firma = primo/ultimo prezzo + numero righe: se cambia, hover di questa selezione via.
    const winSigRef = useRef<string | null>(null);
    useEffect(() => {
        const rows = built.rows;
        const sig = rows.length ? `${rows[0].price}|${rows[rows.length - 1].price}|${rows.length}` : '';
        if (winSigRef.current != null && winSigRef.current !== sig) onWindowShift(sel.selection_id);
        winSigRef.current = sig;
    }, [built, onWindowShift, sel.selection_id]);

    // segnale globale "ricentra" (Spazio): torna sul prezzo corrente.
    useEffect(() => {
        if (recenterSeq > 0) setManualCenter(null);
    }, [recenterSeq]);

    // frecce ↑/↓ (hotkey): sposta la vista di 1 tick (passa in navigazione manuale).
    const lastNudgeRef = useRef(0);
    useEffect(() => {
        if (!nudge || nudge.selId !== sel.selection_id || nudge.seq === lastNudgeRef.current) return;
        lastNudgeRef.current = nudge.seq;
        setAutoCenter(false);
        setManualCenter(prev => {
            const b = builtRef.current;
            const base = prev ?? b.ltp ?? b.bestBack ?? b.bestLay;
            if (base == null) return prev;
            return nudge.dir > 0 ? tickUp(base, 1) : tickDown(base, 1);
        });
        setLocalSeq(s => s + 1);
    }, [nudge, sel.selection_id]);

    // click sulla colonna PREZZO (B11): ricentra la vista sul prezzo corrente.
    const recenterHere = useCallback(() => {
        setManualCenter(null);
        setLocalSeq(s => s + 1);
    }, []);

    // navigazione dalla price bar (B18): centro manuale sul prezzo scelto.
    const navigateTo = useCallback((price: number) => {
        setAutoCenter(false);
        setManualCenter(price);
        setLocalSeq(s => s + 1);
    }, []);

    // bet_id NON abbinati per lato (B14: cancel di un intero lato con un click).
    const sideBets = useMemo(() => {
        const lay: string[] = [];
        const back: string[] = [];
        for (const o of orders) {
            if (!o.bet_id || (o.size_remaining ?? 0) <= 0) continue;
            (o.side === 'lay' ? lay : back).push(o.bet_id);
        }
        return { lay, back };
    }, [orders]);

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

    // ---- drag-to-move (gated da enableDragMove): trascina un TUO ordine da un livello
    // all'altro → cancel-then-replace (mai un singolo replaceOrders, per il delay in-play).
    const dragRef = useRef<DragPayload | null>(null);
    const [dragOverPrice, setDragOverPrice] = useState<number | null>(null);
    const canDrag = enableDragMove && canTrade && !busy;
    const startDrag = useCallback((e: DragEvent, payload: DragPayload) => {
        if (!canDrag || !payload.betIds.length || !(payload.size > 0)) { e.preventDefault(); return; }
        dragRef.current = payload;
        e.dataTransfer.effectAllowed = 'move';
        // alcuni browser richiedono dei dati per avviare il drag.
        try { e.dataTransfer.setData('text/plain', `${payload.side}@${payload.fromPrice}`); } catch { /* noop */ }
    }, [canDrag]);
    const overRow = useCallback((e: DragEvent, price: number) => {
        if (!dragRef.current) return;
        e.preventDefault(); // consenti il drop
        e.dataTransfer.dropEffect = 'move';
        if (dragOverPrice !== price) setDragOverPrice(price);
    }, [dragOverPrice]);
    const dropRow = useCallback((e: DragEvent, toPrice: number) => {
        const p = dragRef.current;
        dragRef.current = null;
        setDragOverPrice(null);
        if (!p) return;
        e.preventDefault();
        if (Math.abs(toPrice - p.fromPrice) < 1e-9) return; // stesso livello: no-op
        onMoveOrder(p.betIds, p.side, toPrice, p.size, selId, selName);
    }, [onMoveOrder, selId, selName]);
    const endDrag = useCallback(() => { dragRef.current = null; setDragOverPrice(null); }, []);

    const closed = (status ?? '').toUpperCase() === 'CLOSED';
    const suspended = (status ?? '').toUpperCase() === 'SUSPENDED';
    // riga su cui la vista è (o va) centrata: LTP in auto-center, altrimenti il centro manuale.
    const centerTargetPrice = (!autoCenter && manualCenter != null)
        ? roundToTick(manualCenter)
        : (built.ltp ?? built.bestBack ?? built.bestLay);
    // Preview cash-out al prezzo di ESECUZIONE reale dell'hedge: se vinco di più sul VINCE
    // (win>lose) il runner LAYa al best LAY; altrimenti BACKa al best BACK. Usare il best
    // opposto (non l'LTP) allinea il numero mostrato a ciò che verrà davvero bloccato.
    const greenPrice = built.win > built.lose ? built.bestLay : built.bestBack;
    const cashOut = built.hasPosition && greenPrice != null
        ? lockedPnlAt(greenPrice, built.win, built.lose)
        : (built.hasPosition && built.ltp != null ? lockedPnlAt(built.ltp, built.win, built.lose) : null);
    const canGreen = canTrade && built.hasPosition && !busy && greenupSupported;
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
                        {/* toggle vista: auto-center LTP (B11), price bar navigabile (B18), mini-chart (B17) */}
                        <button
                            type="button"
                            aria-pressed={autoCenter}
                            onClick={() => setAutoCenter(a => {
                                const nx = !a;
                                if (nx) { setManualCenter(null); setLocalSeq(s => s + 1); }
                                return nx;
                            })}
                            title={autoCenter
                                ? 'Auto-center ATTIVO: la vista segue il LTP a ogni update. Clic per navigare liberamente.'
                                : 'Auto-center SPENTO: vista libera (frecce/price bar/scroll). Clic per riagganciare il LTP.'}
                            className={`p-1 rounded-md border transition-colors ${
                                autoCenter ? 'bg-amber-400/20 border-amber-400/50 text-amber-200' : 'border-white/10 text-white/50 hover:text-white'
                            }`}
                        >
                            <Crosshair className="w-3 h-3" />
                        </button>
                        <button
                            type="button"
                            aria-pressed={showAxis}
                            onClick={() => setShowAxis(s => !s)}
                            title="Price bar navigabile 1.01–1000 (heat = concentrazione del denaro); trascina per scorrere il ladder"
                            className={`p-1 rounded-md border transition-colors ${
                                showAxis ? 'bg-white/90 border-white/90 text-black' : 'border-white/10 text-white/50 hover:text-white'
                            }`}
                        >
                            <Ruler className="w-3 h-3" />
                        </button>
                        <button
                            type="button"
                            aria-pressed={showChart}
                            onClick={() => setShowChart(s => !s)}
                            title="Mini-chart candele del prezzo (LTP) della selezione"
                            className={`p-1 rounded-md border transition-colors ${
                                showChart ? 'bg-white/90 border-white/90 text-black' : 'border-white/10 text-white/50 hover:text-white'
                            }`}
                        >
                            <LineChart className="w-3 h-3" />
                        </button>
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
                        {greenupSupported && (
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
                        )}
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
                    // B14: click sull'intestazione dei TUOI ordini = annulla TUTTO quel lato
                    // con un click (stile BetTrader "K"). Visibile solo quando ci sono ordini.
                    if (k === 'my_lay' || k === 'my_back') {
                        const side: TradeSide = k === 'my_lay' ? 'lay' : 'back';
                        const ids = side === 'lay' ? sideBets.lay : sideBets.back;
                        if (ids.length > 0 && canTrade) {
                            return (
                                <button
                                    key={k}
                                    type="button"
                                    disabled={busy}
                                    onClick={() => onCancelSide(side, ids, selId, selName)}
                                    title={`Annulla TUTTI i ${ids.length} ordini ${side.toUpperCase()} di ${selName} (un click)`}
                                    className={`text-center font-black rounded-sm ${h.cls} ${
                                        side === 'lay' ? 'bg-rose-500/20 hover:bg-rose-500/40' : 'bg-sky-500/20 hover:bg-sky-500/40'
                                    } ${busy ? 'opacity-50' : ''}`}
                                >
                                    {h.label}✕{ids.length}
                                </button>
                            );
                        }
                    }
                    return (
                        <span key={k} className={`text-center ${h.cls}`} title={h.title}>{h.label}</span>
                    );
                })}
            </div>

            {/* corpo ladder (+ price bar navigabile a sinistra, mini-chart a destra) */}
            {built.rows.length === 0 ? (
                <div className="px-3 py-6 text-center text-[11px] text-muted-foreground">
                    Profondità non ancora disponibile.
                </div>
            ) : (
                <div className="flex items-stretch">
                    {showAxis && (
                        <PriceAxisBar
                            back={sel.back}
                            lay={sel.lay}
                            trd={sel.trd}
                            center={centerTargetPrice}
                            onNavigate={navigateTo}
                        />
                    )}
                <div
                    ref={scrollRef}
                    onMouseLeave={() => onHoverRow(null)}
                    className={`flex-1 min-w-0 max-h-[420px] overflow-y-auto scrollbar-thin ${closed || suspended ? 'opacity-60' : ''}`}
                >
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
                                case 'my_lay': {
                                    // tuoi LAY non abbinati — clic = annulla; drag = sposta (cancel→replace)
                                    const draggableLay = canDrag && r.myLay > 0 && layBetIds.length > 0;
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            disabled={r.myLay <= 0 || !canCancel}
                                            draggable={draggableLay}
                                            onDragStart={draggableLay
                                                ? (e) => startDrag(e, { side: 'lay', fromPrice: r.price, betIds: layBetIds, size: r.myLay })
                                                : undefined}
                                            onDragEnd={draggableLay ? endDrag : undefined}
                                            onClick={() => onCancel(layBetIds, 'lay', r.price, selName)}
                                            title={r.myLay > 0
                                                ? (draggableLay ? 'Trascina per SPOSTARE (cancel→replace) · clic per annullare i tuoi LAY' : 'Annulla i tuoi LAY a questo prezzo')
                                                : undefined}
                                            className={`flex items-center justify-center disabled:cursor-default ${draggableLay ? 'cursor-grab active:cursor-grabbing' : ''}`}
                                        >
                                            {r.myLay > 0 && (
                                                <span className="px-1 rounded bg-rose-500/20 text-rose-200 font-bold tabular-nums hover:bg-rose-500/40 hover:line-through">
                                                    {fmtSize(r.myLay)}
                                                </span>
                                            )}
                                        </button>
                                    );
                                }
                                case 'avail_back': {
                                    // disponibile al BACK (blu) — clic = back one-click; flash
                                    // direzionale (B12) quando il denaro al livello cambia.
                                    const fb = flashes.get(`b@${r.price}`);
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            onClick={() => clickBack(r.price)}
                                            title={canTrade ? `BACK €${stake.toFixed(2)} @ ${fmtPrice(r.price)}` : 'Back (sola lettura: modalità OFF)'}
                                            style={fb ? { backgroundColor: fb === 'up' ? 'rgba(52,211,153,0.30)' : 'rgba(244,63,94,0.30)' } : undefined}
                                            className={`flex items-center justify-center font-mono tabular-nums transition-colors duration-200 ${
                                                r.backAvail > 0
                                                    ? 'bg-sky-500/15 text-sky-200 hover:bg-sky-500/30'
                                                    : 'text-transparent hover:bg-sky-500/10'
                                            } ${isBestBack ? 'ring-1 ring-inset ring-sky-400/50' : ''} ${busy ? 'pointer-events-none opacity-60' : ''}`}
                                        >
                                            {fmtSize(r.backAvail) || '·'}
                                        </button>
                                    );
                                }
                                case 'price':
                                    // PREZZO (centro) — LTP evidenziato; clic = RICENTRA la vista
                                    // sul prezzo corrente (B11); pulse direzionale al trade (B12).
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            onClick={recenterHere}
                                            style={isLtp && ltpPulse
                                                ? { backgroundColor: ltpPulse === 'up' ? 'rgba(52,211,153,0.40)' : 'rgba(244,63,94,0.40)' }
                                                : undefined}
                                            className={`flex items-center justify-center font-bold font-mono tabular-nums border-x border-white/10 transition-colors duration-200 ${
                                                isLtp
                                                    ? `bg-amber-400/25 text-amber-100 ring-1 ring-inset ring-amber-400/70 ${ltpPulse ? 'animate-pulse' : ''}`
                                                    : (isBestBack || isBestLay)
                                                        ? 'bg-white/[0.06] text-white'
                                                        : 'text-white/70 hover:bg-white/5'
                                            }`}
                                            title={isLtp
                                                ? 'Ultimo prezzo tradato (LTP) · clic = ricentra'
                                                : 'Clic = ricentra il ladder sul prezzo corrente'}
                                        >
                                            {fmtPrice(r.price)}
                                        </button>
                                    );
                                case 'avail_lay': {
                                    // disponibile al LAY (rosa) — clic = lay one-click; flash B12.
                                    const flsh = flashes.get(`l@${r.price}`);
                                    const layTitle = stakeMode === 'liability'
                                        ? `LAY resp. €${stake.toFixed(2)} @ ${fmtPrice(r.price)}`
                                        : `LAY €${stake.toFixed(2)} @ ${fmtPrice(r.price)}`;
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            onClick={() => clickLay(r.price)}
                                            title={canTrade ? layTitle : 'Lay (sola lettura: modalità OFF)'}
                                            style={flsh ? { backgroundColor: flsh === 'up' ? 'rgba(52,211,153,0.30)' : 'rgba(244,63,94,0.30)' } : undefined}
                                            className={`flex items-center justify-center font-mono tabular-nums transition-colors duration-200 ${
                                                r.layAvail > 0
                                                    ? 'bg-rose-500/15 text-rose-200 hover:bg-rose-500/30'
                                                    : 'text-transparent hover:bg-rose-500/10'
                                            } ${isBestLay ? 'ring-1 ring-inset ring-rose-400/50' : ''} ${busy ? 'pointer-events-none opacity-60' : ''}`}
                                        >
                                            {fmtSize(r.layAvail) || '·'}
                                        </button>
                                    );
                                }
                                case 'my_back': {
                                    // tuoi BACK non abbinati — clic = annulla; drag = sposta (cancel→replace)
                                    const draggableBack = canDrag && r.myBack > 0 && backBetIds.length > 0;
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            disabled={r.myBack <= 0 || !canCancel}
                                            draggable={draggableBack}
                                            onDragStart={draggableBack
                                                ? (e) => startDrag(e, { side: 'back', fromPrice: r.price, betIds: backBetIds, size: r.myBack })
                                                : undefined}
                                            onDragEnd={draggableBack ? endDrag : undefined}
                                            onClick={() => onCancel(backBetIds, 'back', r.price, selName)}
                                            title={r.myBack > 0
                                                ? (draggableBack ? 'Trascina per SPOSTARE (cancel→replace) · clic per annullare i tuoi BACK' : 'Annulla i tuoi BACK a questo prezzo')
                                                : undefined}
                                            className={`flex items-center justify-center disabled:cursor-default ${draggableBack ? 'cursor-grab active:cursor-grabbing' : ''}`}
                                        >
                                            {r.myBack > 0 && (
                                                <span className="px-1 rounded bg-sky-500/20 text-sky-200 font-bold tabular-nums hover:bg-sky-500/40 hover:line-through">
                                                    {fmtSize(r.myBack)}
                                                </span>
                                            )}
                                        </button>
                                    );
                                }
                                case 'pnl': {
                                    // P&L per livello (viola). B13 "greening column" (Bet Angel):
                                    // CLIC sul valore = chiudi la posizione A QUEL prezzo (l'ordine
                                    // di hedge può restare sul book come take-profit resting).
                                    const pnlCls = pnl == null ? 'text-white/15'
                                        : pnl > 0 ? 'text-emerald-300/90'
                                            : pnl < 0 ? 'text-rose-300/90' : 'text-purple-200/70';
                                    const pnlTxt = pnl == null ? '·' : (pnl < 0 ? '−' : '') + Math.abs(pnl).toFixed(2);
                                    const canGreenHere = pnl != null && canTrade && !busy && greenupSupported && built.hasPosition;
                                    if (!canGreenHere) {
                                        return (
                                            <div key={k} className={`flex items-center justify-center font-mono tabular-nums ${pnlCls}`}>
                                                {pnlTxt}
                                            </div>
                                        );
                                    }
                                    return (
                                        <button
                                            key={k}
                                            type="button"
                                            onClick={() => onGreenupAt(r.price, selId, selName)}
                                            title={`Chiudi QUI: blocca ${fmtMoney(pnl)} chiudendo a ${fmtPrice(r.price)} (l'ordine può restare sul book)`}
                                            className={`flex items-center justify-center font-mono tabular-nums transition-colors hover:bg-purple-500/25 hover:ring-1 hover:ring-inset hover:ring-purple-400/60 ${pnlCls}`}
                                        >
                                            {pnlTxt}
                                        </button>
                                    );
                                }
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

                        const isDropTarget = dragOverPrice != null && Math.abs(r.price - dragOverPrice) < 1e-9;
                        const isCenterTarget = centerTargetPrice != null && Math.abs(r.price - centerTargetPrice) < 1e-9;
                        return (
                            <div
                                key={r.price}
                                ref={isCenterTarget ? centerRowRef : undefined}
                                onMouseEnter={() => onHoverRow({
                                    selectionId: selId, selName, price: r.price,
                                    backIds: backBetIds, layIds: layBetIds,
                                })}
                                onDragOver={enableDragMove ? (e) => overRow(e, r.price) : undefined}
                                onDrop={enableDragMove ? (e) => dropRow(e, r.price) : undefined}
                                className={`grid items-stretch border-b border-white/[0.04] text-[10px] leading-tight ${
                                    isArmed ? 'ring-1 ring-inset ring-amber-400/60' : ''
                                } ${isDropTarget ? 'ring-1 ring-inset ring-emerald-400/70 bg-emerald-400/5' : ''}`}
                                style={{ gridTemplateColumns: colTemplate }}
                            >
                                {gridCols.map(cell)}
                            </div>
                        );
                    })}
                </div>
                    {showChart && <MiniPriceChart samples={samples} height={420} />}
                </div>
            )}

            {/* footer: stake selezionato + net-stake box (B15: posizione netta ed esposizione) */}
            <div className="px-2.5 py-1.5 border-t border-white/10 bg-black/30 flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1.5">
                    <span className="text-[9px] uppercase tracking-wider text-muted-foreground/70">
                        {stakeMode === 'liability' ? 'Resp.' : 'Stake'}
                    </span>
                    <span className="text-[11px] font-mono font-bold text-amber-300">€{stake.toFixed(2)}</span>
                </div>
                {position && (
                    <div
                        className="flex items-center gap-2 text-[9px] uppercase tracking-wider text-muted-foreground/70"
                        title="Net = stake netto della selezione (positivo: posizione da BACK; negativo: da LAY) · Exp = esposizione (peggior perdita) della selezione"
                    >
                        <span>Net{' '}
                            <span className={`normal-case font-mono font-bold ${
                                position.net_position > 0 ? 'text-sky-300' : position.net_position < 0 ? 'text-rose-300' : 'text-white/70'
                            }`}>{fmtMoney(position.net_position)}</span>
                        </span>
                        <span>Exp{' '}
                            <span className="normal-case font-mono font-bold text-white/80">{fmtMoney(position.selection_exposure)}</span>
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
});

// ---------------------------------------------------- tipi azione/conferma
type Intent =
    | { kind: 'place'; selName: string; side: TradeSide; price: number; size: number; selectionId: number; persistence: LivePersistence; asLiability: boolean }
    | { kind: 'cancel'; selName: string; betIds: string[]; side: TradeSide | 'both'; price: number }
    | { kind: 'cancel_side'; selName: string; selectionId: number; side: TradeSide; betIds: string[] }
    | { kind: 'move'; selName: string; betIds: string[]; side: TradeSide; toPrice: number; size: number; selectionId: number; persistence: LivePersistence }
    | { kind: 'greenup'; selName: string; selectionId: number; fraction: number }
    | { kind: 'greenup_at'; selName: string; selectionId: number; price: number };

interface StatusMsg { tone: 'pending' | 'ok' | 'err'; text: string; }

function intentLabel(it: Intent): string {
    if (it.kind === 'place') {
        const persLabel = PERSISTENCE_OPTIONS.find(o => o.value === it.persistence)?.label ?? it.persistence;
        const amount = it.asLiability ? `resp. €${it.size.toFixed(2)}` : `€${it.size.toFixed(2)}`;
        return `${it.side === 'back' ? 'BACK' : 'LAY'} ${amount} @ ${fmtPrice(it.price)} · ${persLabel} · ${it.selName}`;
    }
    if (it.kind === 'cancel') {
        const sideTxt = it.side === 'both' ? '' : `${it.side.toUpperCase()} `;
        return `Annulla ${it.betIds.length} ordine/i ${sideTxt}@ ${fmtPrice(it.price)} · ${it.selName}`;
    }
    if (it.kind === 'cancel_side') return `Annulla TUTTI i ${it.betIds.length} ordini ${it.side.toUpperCase()} · ${it.selName}`;
    if (it.kind === 'move') return `Sposta ${it.side.toUpperCase()} €${it.size.toFixed(2)} → ${fmtPrice(it.toPrice)} (cancel→replace) · ${it.selName}`;
    if (it.kind === 'greenup_at') return `Chiudi @ ${fmtPrice(it.price)} (greening al livello) · ${it.selName}`;
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
    // ---- dependency injection (default = funzioni calcio → football INVARIATO) ----
    ladderSource?: LadderSource;   // sorgente ladder (fetch/subscribe); default live_ladder calcio
    orderApi?: LadderOrderApi;     // API ordini (send/fetchOrders/fetchPositions/greenup); default calcio
    enableDragMove?: boolean;      // drag-to-move dei tuoi ordini (cancel→replace); default true (parità tool pro)
    // "stacca in finestra": se presente, mostra il bottone che apre questo mercato in una
    // finestra popout dedicata (multi-monitor). sport seleziona le sorgenti dati del popout;
    // eventName/p1/p2 arricchiscono l'header del popout (tennis: nomi giocatori).
    popout?: { sport: string; eventId?: string; eventName?: string; p1?: string; p2?: string };
    // "aggiungi al multi-ladder": slot precostruito dall'host (che conosce i nomi evento);
    // se presente, mostra il bottone che salva questo mercato nel workspace /multi-ladder.
    multiSlot?: Omit<LadderSlot, 'id'>;
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

export function LadderView({
    marketId, marketName, orderMode = 'off', handicap = 0, sport = 'calcio', fallbackSelections = [],
    ladderSource = DEFAULT_LADDER_SOURCE, orderApi = DEFAULT_ORDER_API, enableDragMove = true,
    popout, multiSlot,
}: Props) {
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
    // MONEY-CRITICAL (fix M4): input custom NON parsabile/≤0 → la casella mostra un valore ma
    // `stake` resta quello PRECEDENTE. Senza blocco, il clic one-click invierebbe uno stake
    // diverso da quello visualizzato. Finché l'input è invalido i place sono bloccati.
    const stakeInvalid = customStake !== ''
        && !(Number.isFinite(Number(customStake)) && Number(customStake) > 0);
    const stakeInvalidRef = useRef(stakeInvalid);
    stakeInvalidRef.current = stakeInvalid;

    // persistenza ordine condivisa (default LAPSE, come i tool pro).
    const [persistence, setPersistence] = useState<LivePersistence>('LAPSE');

    // B15: interpreta lo stake dei LAY come PUNTATA (stake, default) o come RESPONSABILITÀ
    // (liability: il runner deriva size = liability/(price−1)). I BACK non cambiano.
    const [stakeMode, setStakeMode] = useState<'stake' | 'liability'>('stake');
    const stakeModeRef = useRef(stakeMode);
    stakeModeRef.current = stakeMode;

    // B11/B16: segnale globale di ricentraggio (Spazio/click) e nudge frecce per-selezione.
    const [recenterSeq, setRecenterSeq] = useState(0);
    const [nudge, setNudge] = useState<{ seq: number; selId: number; dir: 1 | -1 } | null>(null);

    // B16: riga sotto il cursore (ref: nessun re-render sul movimento del mouse).
    const hoverRef = useRef<HoverInfo | null>(null);
    const onHoverRow = useCallback((h: HoverInfo | null) => { hoverRef.current = h; }, []);
    // fix review HIGH: la selezione segnala che il contenuto è scivolato sotto il cursore
    // fermo → se l'hover apparteneva a lei, va invalidato (hotkey sospese fino al prossimo
    // movimento reale del mouse).
    const onWindowShift = useCallback((selectionId: number) => {
        if (hoverRef.current?.selectionId === selectionId) hoverRef.current = null;
    }, []);

    // B17: buffer campioni LTP per selezione (mutati in place, azzerati al cambio mercato).
    const samplesRef = useRef<Map<number, PriceSample[]>>(new Map());

    // ---- one-click trading: armamento (LIVE), in-volo, esito, conferma ----
    const [armed, setArmed] = useState(false);   // 1-click LIVE attivo (banner rosso)
    const [busy, setBusy] = useState(false);
    const [statusMsg, setStatusMsg] = useState<StatusMsg | null>(null);
    const [confirm, setConfirm] = useState<Intent | null>(null);
    const busyRef = useRef(false);
    const [refreshTick, setRefreshTick] = useState(0);

    // se la modalità non è LIVE, l'armamento non ha senso: tienilo spento.
    useEffect(() => { if (!isLive) setArmed(false); }, [isLive]);

    // MONEY-CRITICAL (fix M1): la barra di conferma LIVE SCADE. Un intent "BACK €25 @ 2.40"
    // lasciato lì può essere confermato minuti dopo con il mercato mosso: prezzo stantio che
    // si abbina o resta sul book come posizione inattesa. Dopo la scadenza serve un nuovo clic.
    useEffect(() => {
        if (!confirm) return;
        const t = setTimeout(() => {
            setConfirm(null);
            setStatusMsg({ tone: 'err', text: '✗ Conferma scaduta (mercato mosso): riclicca il prezzo per ripetere.' });
        }, CONFIRM_TTL_MS);
        return () => clearTimeout(t);
    }, [confirm]);

    // ---- snapshot iniziale + sottoscrizione realtime a live_ladder ----
    useEffect(() => {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        setRow(null);
        setLoading(true);
        samplesRef.current = new Map(); // nuova storia prezzi per il nuovo mercato
        if (!marketId) { setLoading(false); return; }

        let alive = true;
        ladderSource.fetch(marketId)
            .then(r => { if (alive) setRow(r); })
            .catch((e: any) => {
                if (e?.code !== 'PGRST116') console.warn('[LadderView] fetchLadder:', e);
            })
            .finally(() => { if (alive) setLoading(false); });

        unsubRef.current = ladderSource.subscribe(marketId, (r) => {
            if (r) setRow(r);
        });
        // NB: il campionamento LTP per il mini-chart avviene nell'effetto su `row` qui sotto.

        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [marketId, ladderSource]);

    // ---- campionamento LTP per il mini-chart (B17): un campione per update del ladder ----
    useEffect(() => {
        const sels = row?.ladder?.selections ?? [];
        if (!sels.length) return;
        const ts = row?.ladder?.updated_ms ?? Date.now();
        for (const s of sels) {
            if (s.ltp == null || !Number.isFinite(s.ltp)) continue;
            let buf = samplesRef.current.get(s.selection_id);
            if (!buf) { buf = []; samplesRef.current.set(s.selection_id, buf); }
            pushSample(buf, ts, s.ltp);
        }
    }, [row]);

    // ---- overlay ordini/posizioni: fetch + poll gentile (+ refresh dopo azioni) ----
    useEffect(() => {
        if (!marketId) return;
        let alive = true;
        let inFlight = false;
        const load = async () => {
            if (inFlight) return;
            inFlight = true;
            try {
                // il mode è passato alle sorgenti che filtrano lato RPC (tennis); i default
                // calcio lo IGNORANO → comportamento football invariato. In OFF si scarta comunque.
                const m = mode as LiveOrderMode;
                const [o, p] = await Promise.all([
                    orderApi.fetchOrders(marketId, m),
                    orderApi.fetchPositions(marketId, m),
                ]);
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
    }, [marketId, mode, refreshTick, orderApi]);

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
            // B15: in modalità liability i LAY inviano la RESPONSABILITÀ; il runner deriva
            // size = liability/(price−1) e valida. I BACK inviano sempre size (=liability).
            const sizing = it.asLiability && it.side === 'lay'
                ? { liability: it.size }
                : { size: it.size };
            submit(() => orderApi.send({
                action: 'place', mode: mode as LiveOrderMode, market_id: marketId,
                selection_id: it.selectionId, handicap, side: it.side,
                order_type: 'LIMIT', price: it.price, persistence: it.persistence,
                ...sizing,
            }), label);
        } else if (it.kind === 'cancel' || it.kind === 'cancel_side') {
            const ids = it.betIds;
            submit(async () => {
                let last: LiveOrderResult = { ok: true, action: 'cancel', mode };
                let done = 0;
                for (const bet_id of ids) {
                    last = await orderApi.send({ action: 'cancel', mode: mode as LiveOrderMode, market_id: marketId, bet_id });
                    if (!last.ok) break;
                    done++;
                }
                // successo parziale: dillo chiaramente (quali ordini restano da verificare).
                if (!last.ok && done > 0) {
                    last = { ...last, error: `${done}/${ids.length} annullati — verifica gli ordini residui. ${last.error ?? ''}`.trim() };
                }
                return last;
            }, label);
        } else if (it.kind === 'move') {
            // MOVE = cancel-then-replace: MAI un singolo replaceOrders (in-play bet delay del
            // tennis). Prima si annullano gli ordini di origine, poi si PIAZZA al prezzo target.
            // Se un cancel fallisce si INTERROMPE e NON si ripiazza (niente ordine duplicato).
            const ids = it.betIds;
            submit(async () => {
                let last: LiveOrderResult = { ok: true, action: 'cancel', mode };
                let done = 0;
                for (const bet_id of ids) {
                    last = await orderApi.send({ action: 'cancel', mode: mode as LiveOrderMode, market_id: marketId, bet_id });
                    if (!last.ok) break;
                    done++;
                }
                if (done < ids.length) {
                    return {
                        ...last, ok: false,
                        error: `Spostamento interrotto: ${done}/${ids.length} annullati; ordine NON ripiazzato (nessun duplicato). ${last.error ?? ''}`.trim(),
                    };
                }
                // 2) piazza il nuovo ordine al prezzo target con la size spostata.
                return orderApi.send({
                    action: 'place', mode: mode as LiveOrderMode, market_id: marketId,
                    selection_id: it.selectionId, handicap, side: it.side,
                    order_type: 'LIMIT', price: it.toPrice, size: it.size, persistence: it.persistence,
                });
            }, label);
        } else if ((it.kind === 'greenup' || it.kind === 'greenup_at') && orderApi.greenup) {
            const greenup = orderApi.greenup;
            // greenup_at = "greening column" (B13): chiusura TOTALE al prezzo del livello
            // cliccato (il runner valida target_price e piazza l'hedge a QUEL tick).
            const args = it.kind === 'greenup'
                ? { fraction: it.fraction }
                : { fraction: 1, targetPrice: it.price };
            submit(() => greenup({
                marketId, selectionId: it.selectionId, mode: mode as LiveOrderMode,
                handicap, ...args,
            }), label);
        }
    }, [submit, mode, marketId, handicap, orderApi]);

    // richiesta azione: in LIVE non-armato chiede conferma; altrimenti esegue subito.
    const requestAction = useCallback((it: Intent) => {
        if (mode === 'off') return;
        if (busyRef.current) return;
        // fix M4: con stake custom invalido, lo stake effettivo ≠ quello mostrato → blocca i place.
        if (it.kind === 'place' && stakeInvalidRef.current) {
            setStatusMsg({ tone: 'err', text: '✗ Stake non valido: correggi l\'importo prima di piazzare.' });
            return;
        }
        if (isLive && !armed) { setConfirm(it); return; }
        execute(it);
    }, [mode, isLive, armed, execute]);

    const onPlace = useCallback((side: TradeSide, price: number, selectionId: number, selName: string) => {
        requestAction({
            kind: 'place', selName, side, price, size: stakeRef.current, selectionId,
            persistence: persistenceRef.current,
            asLiability: stakeModeRef.current === 'liability' && side === 'lay',
        });
    }, [requestAction]);

    const onCancel = useCallback((betIds: string[], side: TradeSide, price: number, selName: string) => {
        if (!betIds.length) return;
        requestAction({ kind: 'cancel', selName, betIds, side, price });
    }, [requestAction]);

    const onGreenup = useCallback((fraction: number, selectionId: number, selName: string) => {
        requestAction({ kind: 'greenup', selName, selectionId, fraction });
    }, [requestAction]);

    // B13: greening column — chiudi la posizione della selezione A QUEL prezzo.
    const onGreenupAt = useCallback((price: number, selectionId: number, selName: string) => {
        requestAction({ kind: 'greenup_at', selName, selectionId, price });
    }, [requestAction]);

    // B14: annulla TUTTI gli ordini di un lato della selezione con un click.
    const onCancelSide = useCallback((side: TradeSide, betIds: string[], selectionId: number, selName: string) => {
        if (!betIds.length) return;
        requestAction({ kind: 'cancel_side', selName, selectionId, side, betIds });
    }, [requestAction]);

    // drag-to-move: sposta i tuoi ordini di origine (betIds) al prezzo target via
    // cancel-then-replace. In LIVE non-armato passa dalla barra di CONFERMA come i place.
    const onMoveOrder = useCallback((betIds: string[], side: TradeSide, toPrice: number, size: number, selectionId: number, selName: string) => {
        if (!enableDragMove) return;
        if (!betIds.length || !(size > 0)) return;
        requestAction({ kind: 'move', selName, betIds, side, toPrice, size, selectionId, persistence: persistenceRef.current });
    }, [requestAction, enableDragMove]);

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
    const canTradeRef = useRef(canTrade);
    canTradeRef.current = canTrade;
    const confirmOpenRef = useRef(false);
    confirmOpenRef.current = confirm != null;

    // ---- B16: hotkey complete del ladder (B/L/C, frecce, +/−, S, Spazio) ----
    // Attive solo in PAPER/LIVE, MAI mentre si digita in un campo o con la barra di
    // conferma LIVE aperta. B/L/C/frecce/stake agiscono sul ladder SOTTO IL CURSORE
    // (hoverRef): con più ladder montati (multi-ladder) risponde solo quello puntato.
    // G/X/Escape/PageUp/PageDown restano all'host (cash-out, kill-switch, cambio mercato).
    useEffect(() => {
        if (mode === 'off') return;
        const onKey = (e: KeyboardEvent) => {
            if (e.ctrlKey || e.metaKey || e.altKey) return;
            const t = e.target as HTMLElement | null;
            if (t && t.closest('input, textarea, select, [contenteditable="true"]')) return;
            if (confirmOpenRef.current) return;
            const action = resolveHotkey(e.key);
            if (!action) return;
            const h = hoverRef.current;
            switch (action) {
                case 'back_preset':
                case 'lay_preset': {
                    if (!h || !canTradeRef.current || busyRef.current) return;
                    e.preventDefault();
                    onPlace(action === 'back_preset' ? 'back' : 'lay', h.price, h.selectionId, h.selName);
                    return;
                }
                case 'cancel_under_cursor': {
                    if (!h || !canTradeRef.current || busyRef.current) return;
                    const ids = [...h.backIds, ...h.layIds];
                    if (!ids.length) return;
                    e.preventDefault();
                    const side = h.backIds.length && h.layIds.length
                        ? 'both' as const
                        : (h.backIds.length ? 'back' as const : 'lay' as const);
                    requestAction({ kind: 'cancel', selName: h.selName, betIds: ids, side, price: h.price });
                    return;
                }
                case 'stake_up':
                case 'stake_down': {
                    if (!h) return; // solo sul ladder puntato (multi-ladder safe)
                    e.preventDefault();
                    setStake(s => stepStake(s, action === 'stake_up' ? 1 : -1));
                    setCustomStake('');
                    return;
                }
                case 'cycle_preset': {
                    if (!h) return;
                    e.preventDefault();
                    setStake(s => nextPreset(STAKE_PRESETS, s));
                    setCustomStake('');
                    return;
                }
                case 'center_ladder': {
                    // fix review: gated sull'hover come le altre — in multi-ladder risponde
                    // SOLO il ladder puntato, non tutti quelli montati.
                    if (!h) return;
                    e.preventDefault();
                    setRecenterSeq(s => s + 1);
                    return;
                }
                case 'move_up':
                case 'move_down': {
                    if (!h) return;
                    e.preventDefault();
                    const dir = action === 'move_up' ? 1 : -1;
                    setNudge(n => ({ seq: (n?.seq ?? 0) + 1, selId: h.selectionId, dir: dir as 1 | -1 }));
                    return;
                }
                default:
                    return;
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [mode, onPlace, requestAction]);

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
                        title={stakeInvalid ? 'Stake non valido: i clic di piazzamento sono bloccati' : 'Stake custom (€)'}
                        className={`w-14 bg-black/60 border rounded-md px-1.5 py-0.5 text-[11px] text-white focus:outline-none ${
                            stakeInvalid
                                ? 'border-red-500 focus:border-red-400'
                                : 'border-white/10 focus:border-amber-400/50'
                        }`}
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
                    {/* B15: toggle Stake/Liability — nei LAY lo stake diventa RESPONSABILITÀ
                        (il runner deriva size = liability/(price−1)); i BACK non cambiano. */}
                    {mode !== 'off' && (
                        <div className="flex items-center gap-1 ml-1"
                            title="LAY: interpreta l'importo come puntata (Stake) o come responsabilità (Liab). I BACK non cambiano.">
                            {(['stake', 'liability'] as const).map(m => (
                                <button
                                    key={m}
                                    type="button"
                                    onClick={() => setStakeMode(m)}
                                    aria-pressed={stakeMode === m}
                                    className={`px-2 py-0.5 rounded-md text-[11px] font-bold border transition-colors ${
                                        stakeMode === m
                                            ? 'bg-rose-300 text-black border-rose-300'
                                            : 'border-white/10 text-white/70 hover:border-rose-300/50'
                                    }`}
                                >
                                    {m === 'stake' ? 'Stake' : 'Liab'}
                                </button>
                            ))}
                        </div>
                    )}
                    {/* B16: legenda hotkey (tooltip) */}
                    {mode !== 'off' && (
                        <span
                            className="p-1 rounded-md border border-white/10 text-white/40 cursor-help"
                            title={'Hotkey (sul ladder puntato dal mouse):\nB = BACK al livello · L = LAY al livello · C = annulla ordini al livello\n↑/↓ = vista su/giù di 1 tick · Spazio = ricentra sul prezzo\n+/− = stake ±0,50€ · S = prossimo preset\nG = cash-out mercato · X = cash-out evento · Esc = kill-switch (dal terminal)'}
                        >
                            <Keyboard className="w-3 h-3" />
                        </span>
                    )}
                    {/* B19: aggiungi questo mercato al workspace /multi-ladder */}
                    {multiSlot && (
                        <button
                            type="button"
                            onClick={() => {
                                const cur = loadSlots();
                                const next = addSlot(cur, multiSlot);
                                if (next === cur) {
                                    setStatusMsg({ tone: 'err', text: '✗ Già nel Multi-ladder (o workspace pieno).' });
                                    return;
                                }
                                saveSlots(next);
                                setStatusMsg({ tone: 'ok', text: `✓ Aggiunto al Multi-ladder (${next.length} ladder) — apri /multi-ladder.` });
                            }}
                            title="Aggiungi questo mercato al workspace Multi-ladder (N ladder affiancati, anche di eventi diversi)"
                            className="p-1 rounded-md border border-white/10 text-white/50 hover:text-white hover:border-white/40 transition-colors"
                        >
                            <Layers className="w-3 h-3" />
                        </button>
                    )}
                    {/* B19: stacca questo mercato in una finestra popout dedicata (multi-monitor) */}
                    {popout && (
                        <button
                            type="button"
                            onClick={() => {
                                const q = new URLSearchParams({
                                    sport: popout.sport,
                                    market: marketId,
                                    ...(popout.eventId ? { event: popout.eventId } : {}),
                                    ...(marketName ? { name: marketName } : {}),
                                    ...(popout.eventName ? { eventName: popout.eventName } : {}),
                                    ...(popout.p1 ? { p1: popout.p1 } : {}),
                                    ...(popout.p2 ? { p2: popout.p2 } : {}),
                                });
                                window.open(`/ladder-popout?${q.toString()}`, `ladder_${marketId}`,
                                    'popup=yes,width=560,height=860,resizable=yes,scrollbars=yes');
                            }}
                            title="Stacca questo ladder in una finestra dedicata (multi-monitor)"
                            className="p-1 rounded-md border border-white/10 text-white/50 hover:text-white hover:border-white/40 transition-colors"
                        >
                            <ExternalLink className="w-3 h-3" />
                        </button>
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
                                stakeMode={stakeMode}
                                status={status}
                                canTrade={canTrade}
                                busy={busy}
                                columns={gridColumns}
                                greenupSupported={!!orderApi.greenup}
                                enableDragMove={enableDragMove}
                                recenterSeq={recenterSeq}
                                nudge={nudge}
                                samples={samplesRef.current.get(s.selection_id)}
                                onPlace={onPlace}
                                onCancel={onCancel}
                                onGreenup={onGreenup}
                                onGreenupAt={onGreenupAt}
                                onCancelSide={onCancelSide}
                                onMoveOrder={onMoveOrder}
                                onHoverRow={onHoverRow}
                                onWindowShift={onWindowShift}
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
