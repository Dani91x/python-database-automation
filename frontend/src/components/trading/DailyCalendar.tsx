// ============================================================================
// DailyCalendar.tsx — CALENDARIO MENSILE delle giornate operative.
//
// Ogni cella = P&L realizzato del giorno (verde/rosso con intensità relativa
// al mese), numero di trade piazzati e — per Omega — il marcatore obiettivo
// (● centrato / ○ mancato). Click o Invio/Spazio selezionano il giorno; le
// frecce muovono il focus (roving tabindex), Home/End vanno a inizio/fine
// settimana. Navigazione mese prec/succ + "Oggi". Su schermi stretti la
// griglia scorre in orizzontale dentro il proprio contenitore.
// ============================================================================
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    calendarGrid, monthLabel, dayLabel, shiftMonth, romeDay,
    type CalendarCell, type DailyRow,
} from '@/lib/dailyHistory';
import { fmtMoney } from '@/lib/format';

const WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];

function fmtSignedEur(v: number): string {
    return fmtMoney(v, { signed: true });
}

/**
 * H-10 — "centrato / mancato" si può dire SOLO se l'obiettivo di quel giorno è
 * STORICIZZATO (`goal_snapshot`). Con un obiettivo di ripiego (quello corrente
 * del control, magari cambiato la settimana dopo) il giudizio è falso: niente
 * ●/○, e la cella lo dichiara nel tooltip.
 */
export function goalMarkOf(row: DailyRow | null, showGoal: boolean): boolean | null {
    if (!showGoal || !row) return null;
    if (row.goal == null || !(row.goal > 0)) return null;
    if (!row.goal_snapshot) return null;
    return row.pnl_realized >= row.goal;
}

/** classe di intensità: 4 livelli per segno, in base al |pnl| massimo del mese */
export function intensityClass(pnl: number, maxAbs: number): string {
    if (pnl === 0 || maxAbs <= 0) return 'bg-white/5 border-white/10 text-slate-300';
    const ratio = Math.min(1, Math.abs(pnl) / maxAbs);
    const lvl = ratio > 0.75 ? 3 : ratio > 0.4 ? 2 : ratio > 0.15 ? 1 : 0;
    if (pnl > 0) {
        return ['bg-emerald-500/10 border-emerald-500/25 text-emerald-200',
            'bg-emerald-500/20 border-emerald-500/35 text-emerald-200',
            'bg-emerald-500/35 border-emerald-500/50 text-emerald-100',
            'bg-emerald-500/55 border-emerald-400/70 text-white'][lvl];
    }
    return ['bg-red-500/10 border-red-500/25 text-red-200',
        'bg-red-500/20 border-red-500/35 text-red-200',
        'bg-red-500/35 border-red-500/50 text-red-100',
        'bg-red-500/55 border-red-400/70 text-white'][lvl];
}

export interface DailyCalendarProps {
    rows: DailyRow[];
    year: number;
    /** 1-12 */
    month: number;
    selectedDay: string | null;
    onSelectDay: (day: string) => void;
    onMonthChange: (year: number, month: number) => void;
    /** Omega: mostra il marcatore obiettivo centrato/mancato */
    showGoal?: boolean;
    /** giornata operativa corrente (default: Europe/Rome adesso) */
    today?: string;
    loading?: boolean;
}

function cellAria(c: CalendarCell, showGoal: boolean): string {
    const base = dayLabel(c.day, { weekday: true });
    if (!c.row) return `${base}: nessuna operazione`;
    const r = c.row;
    let s = `${base}: ${fmtSignedEur(r.pnl_realized)}, ${r.trades_placed} trade`;
    const mark = goalMarkOf(r, showGoal);
    if (mark != null) s += mark ? ', obiettivo centrato' : ', obiettivo mancato';
    else if (showGoal && r.goal != null && r.goal > 0) s += ', obiettivo non storicizzato';
    return s;
}

export function DailyCalendar({
    rows, year, month, selectedDay, onSelectDay, onMonthChange, showGoal = false, today, loading = false,
}: DailyCalendarProps) {
    const todayDay = today ?? romeDay();
    const weeks = useMemo(() => calendarGrid(year, month, rows), [year, month, rows]);
    const cells = useMemo(() => weeks.flat(), [weeks]);
    const monthRows = useMemo(() => cells.filter((c) => c.inMonth && c.row).map((c) => c.row as DailyRow), [cells]);
    const maxAbs = useMemo(() => monthRows.reduce((m, r) => Math.max(m, Math.abs(r.pnl_realized)), 0), [monthRows]);
    const monthPnl = useMemo(() => monthRows.reduce((s, r) => s + r.pnl_realized, 0), [monthRows]);

    // roving tabindex: una sola cella nel tab order
    const [focusDay, setFocusDay] = useState<string>(() => selectedDay ?? todayDay);
    const gridRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        // il giorno focalizzabile deve appartenere alla griglia visibile
        if (!cells.some((c) => c.day === focusDay)) {
            const pick = cells.find((c) => c.day === selectedDay)
                ?? cells.find((c) => c.day === todayDay)
                ?? cells.find((c) => c.inMonth);
            if (pick) setFocusDay(pick.day);
        }
    }, [cells, focusDay, selectedDay, todayDay]);

    function focusCell(day: string) {
        setFocusDay(day);
        const el = gridRef.current?.querySelector<HTMLButtonElement>(`[data-day="${day}"]`);
        el?.focus();
    }

    function onKey(e: KeyboardEvent<HTMLButtonElement>, c: CalendarCell) {
        const idx = cells.findIndex((x) => x.day === c.day);
        if (idx < 0) return;
        let next: number | null = null;
        switch (e.key) {
            case 'ArrowRight': next = idx + 1; break;
            case 'ArrowLeft': next = idx - 1; break;
            case 'ArrowDown': next = idx + 7; break;
            case 'ArrowUp': next = idx - 7; break;
            case 'Home': next = idx - c.dow; break;
            case 'End': next = idx + (6 - c.dow); break;
            case 'Enter':
            case ' ':
                e.preventDefault();
                onSelectDay(c.day);
                return;
            default: return;
        }
        e.preventDefault();
        if (next != null && next >= 0 && next < cells.length) focusCell(cells[next].day);
    }

    const prev = shiftMonth(year, month, -1);
    const next = shiftMonth(year, month, 1);
    const todayY = Number(todayDay.slice(0, 4)), todayM = Number(todayDay.slice(5, 7));

    return (
        <div className="space-y-3" data-testid="daily-calendar">
            <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1">
                    <Button variant="ghost" size="sm" aria-label="Mese precedente" onClick={() => onMonthChange(prev.year, prev.month)}>
                        <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <div className="font-display font-black text-lg capitalize min-w-[160px] text-center" data-testid="calendar-month">
                        {monthLabel(year, month)}
                    </div>
                    <Button variant="ghost" size="sm" aria-label="Mese successivo" onClick={() => onMonthChange(next.year, next.month)}>
                        <ChevronRight className="w-4 h-4" />
                    </Button>
                    <Button
                        variant="outline" size="sm" className="ml-1 border-white/10"
                        onClick={() => { onMonthChange(todayY, todayM); onSelectDay(todayDay); }}
                    >
                        Oggi
                    </Button>
                </div>
                <div className="text-sm tabular-nums" data-testid="calendar-month-total">
                    <span className="text-slate-400 mr-2">{monthRows.length} giornate</span>
                    <span className={`font-bold ${monthPnl > 0 ? 'text-emerald-400' : monthPnl < 0 ? 'text-red-400' : 'text-slate-300'}`}>
                        {fmtSignedEur(monthPnl)}
                    </span>
                </div>
            </div>

            <div className="overflow-x-auto">
                <div
                    ref={gridRef}
                    role="grid"
                    aria-label={`Calendario ${monthLabel(year, month)}`}
                    aria-busy={loading || undefined}
                    className="min-w-[560px] grid grid-cols-7 gap-1"
                >
                    {WEEKDAYS.map((w) => (
                        <div key={w} role="columnheader" className="text-[10px] uppercase tracking-wide text-slate-500 text-center py-1">
                            {w}
                        </div>
                    ))}
                    {cells.map((c) => {
                        const r = c.row;
                        const isSel = c.day === selectedDay;
                        const isToday = c.day === todayDay;
                        // H-10: solo con obiettivo STORICIZZATO si giudica la giornata
                        const goalHit = goalMarkOf(r, showGoal);
                        const goalStale = goalHit == null && showGoal && r != null && r.goal != null && r.goal > 0;
                        const tone = r ? intensityClass(r.pnl_realized, maxAbs) : 'bg-transparent border-white/5 text-slate-500';
                        return (
                            <button
                                key={c.day}
                                type="button"
                                role="gridcell"
                                data-day={c.day}
                                data-testid={c.inMonth ? 'calendar-day' : 'calendar-day-outside'}
                                data-in-month={c.inMonth ? '1' : '0'}
                                aria-selected={isSel}
                                aria-current={isToday ? 'date' : undefined}
                                aria-label={cellAria(c, showGoal)}
                                tabIndex={c.day === focusDay ? 0 : -1}
                                onClick={() => onSelectDay(c.day)}
                                onKeyDown={(e) => onKey(e, c)}
                                onFocus={() => setFocusDay(c.day)}
                                className={[
                                    'relative rounded-md border h-[62px] px-1.5 py-1 text-left transition',
                                    'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                                    c.inMonth ? '' : 'opacity-40',
                                    tone,
                                    isSel ? 'ring-2 ring-secondary' : '',
                                ].join(' ')}
                            >
                                <div className="flex items-center justify-between text-[11px] leading-none">
                                    <span className={`tabular-nums ${isToday ? 'font-black text-primary' : 'text-slate-400'}`}>{c.dom}</span>
                                    {goalHit != null && (
                                        <span
                                            data-testid={goalHit ? 'goal-hit' : 'goal-miss'}
                                            className={`text-[10px] ${goalHit ? 'text-secondary' : 'text-slate-500'}`}
                                            aria-hidden
                                        >
                                            {goalHit ? '●' : '○'}
                                        </span>
                                    )}
                                    {goalStale && (
                                        <span
                                            data-testid="goal-not-historized"
                                            className="text-[10px] text-slate-600"
                                            aria-hidden
                                            title="obiettivo non storicizzato: quello mostrato è quello corrente, non quello di quel giorno"
                                        >·</span>
                                    )}
                                </div>
                                {r ? (
                                    <>
                                        <div className="mt-1 font-bold tabular-nums text-[12px] leading-tight">{fmtSignedEur(r.pnl_realized)}</div>
                                        <div className="text-[10px] opacity-80 tabular-nums">{r.trades_placed} trade</div>
                                    </>
                                ) : (
                                    <div className="mt-1 text-[10px] text-slate-600">—</div>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {!loading && monthRows.length === 0 && (
                <div className="text-center text-sm text-muted-foreground py-3" data-testid="calendar-empty">
                    nessuna operazione in {monthLabel(year, month)}
                </div>
            )}
            <div className="text-[10px] text-slate-500 flex items-center gap-3 flex-wrap">
                <span>verde/rosso = P&L realizzato del giorno (intensità relativa al mese)</span>
                {showGoal && <span>● obiettivo centrato · ○ mancato · <span className="text-slate-600">·</span> obiettivo non storicizzato</span>}
                <span>frecce per muoversi, Invio per selezionare</span>
            </div>
        </div>
    );
}

export default DailyCalendar;
