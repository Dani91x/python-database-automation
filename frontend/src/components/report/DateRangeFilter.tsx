// ============================================================================
// DateRangeFilter — filtro data a CALENDARIO (range Dal→Al) self-contained.
// Zero dipendenze extra (solo date-fns, già nel progetto). Popover dark/glass
// con griglia mensile: 1° clic = Dal, 2° clic = Al. Emette stringhe 'yyyy-MM-dd'
// (compatibili con get_personal_report / get_personal_trades).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import {
    addMonths, subMonths, startOfMonth, endOfMonth, startOfWeek, endOfWeek,
    eachDayOfInterval, format, isSameDay, isSameMonth, isWithinInterval, parseISO,
} from 'date-fns';
import { it } from 'date-fns/locale';
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react';

interface Props {
    from: string | null;
    to: string | null;
    onChange: (from: string | null, to: string | null) => void;
}

const parse = (s: string | null): Date | null => {
    if (!s) return null;
    try { return parseISO(s); } catch { return null; }
};
const iso = (d: Date) => format(d, 'yyyy-MM-dd');
const label = (s: string | null) => (s ? format(parseISO(s), 'dd/MM/yy') : '—');

export function DateRangeFilter({ from, to, onChange }: Props) {
    const [open, setOpen] = useState(false);
    const [view, setView] = useState<Date>(() => parse(from) ?? parse(to) ?? new Date());
    const ref = useRef<HTMLDivElement>(null);

    const fromD = parse(from);
    const toD = parse(to);

    // chiudi al clic fuori
    useEffect(() => {
        if (!open) return;
        const onDown = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', onDown);
        return () => document.removeEventListener('mousedown', onDown);
    }, [open]);

    const days = useMemo(() => {
        const start = startOfWeek(startOfMonth(view), { weekStartsOn: 1 });
        const end = endOfWeek(endOfMonth(view), { weekStartsOn: 1 });
        return eachDayOfInterval({ start, end });
    }, [view]);

    const pick = (d: Date) => {
        // 1° clic o range già completo → nuovo Dal; 2° clic → Al (ordina)
        if (!fromD || (fromD && toD)) {
            onChange(iso(d), null);
        } else if (d < fromD) {
            onChange(iso(d), iso(fromD));
        } else {
            onChange(iso(fromD), iso(d));
        }
    };

    const inRange = (d: Date) => {
        if (fromD && toD) return isWithinInterval(d, { start: fromD, end: toD });
        return false;
    };
    const isEdge = (d: Date) => (fromD && isSameDay(d, fromD)) || (toD && isSameDay(d, toD));

    return (
        <div className="relative" ref={ref}>
            <button
                type="button"
                onClick={() => setOpen(o => !o)}
                className="w-full flex items-center gap-2 bg-black/60 border border-white/10 rounded-lg
                           px-3 py-2 text-sm text-white hover:border-primary/60 transition-colors"
            >
                <CalendarDays className="w-4 h-4 text-primary shrink-0" />
                <span className={from || to ? 'text-white' : 'text-muted-foreground'}>
                    {from || to ? `${label(from)} → ${label(to)}` : 'Seleziona periodo'}
                </span>
                {(from || to) && (
                    <X className="w-3.5 h-3.5 ml-auto text-muted-foreground hover:text-white"
                        onClick={(e) => { e.stopPropagation(); onChange(null, null); }} />
                )}
            </button>

            {open && (
                <div className="absolute z-50 mt-2 w-72 glass-card bg-black/95 border border-white/10
                                backdrop-blur-2xl rounded-xl p-3 shadow-2xl">
                    {/* header mese */}
                    <div className="flex items-center justify-between mb-2">
                        <button type="button" onClick={() => setView(v => subMonths(v, 1))}
                            className="p-1 rounded hover:bg-white/10 text-muted-foreground hover:text-white">
                            <ChevronLeft className="w-4 h-4" />
                        </button>
                        <span className="text-sm font-bold font-display capitalize">
                            {format(view, 'MMMM yyyy', { locale: it })}
                        </span>
                        <button type="button" onClick={() => setView(v => addMonths(v, 1))}
                            className="p-1 rounded hover:bg-white/10 text-muted-foreground hover:text-white">
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>

                    {/* giorni settimana */}
                    <div className="grid grid-cols-7 gap-0.5 mb-1">
                        {['L', 'M', 'M', 'G', 'V', 'S', 'D'].map((d, i) => (
                            <div key={i} className="text-center text-[9px] uppercase text-muted-foreground py-1">{d}</div>
                        ))}
                    </div>

                    {/* griglia giorni */}
                    <div className="grid grid-cols-7 gap-0.5">
                        {days.map((d, i) => {
                            const edge = isEdge(d);
                            const range = inRange(d) && !edge;
                            const dim = !isSameMonth(d, view);
                            return (
                                <button
                                    key={i} type="button" onClick={() => pick(d)}
                                    className={[
                                        'h-8 text-xs rounded-md tabular-nums transition-colors',
                                        edge ? 'bg-primary text-primary-foreground font-bold'
                                            : range ? 'bg-primary/20 text-white'
                                            : 'hover:bg-white/10 text-white/80',
                                        dim ? 'opacity-30' : '',
                                    ].join(' ')}
                                >
                                    {format(d, 'd')}
                                </button>
                            );
                        })}
                    </div>

                    {/* azioni rapide */}
                    <div className="flex items-center justify-between mt-3 pt-2 border-t border-white/5">
                        <button type="button" onClick={() => { onChange(null, null); }}
                            className="text-[11px] text-muted-foreground hover:text-white">Azzera</button>
                        <button type="button" onClick={() => setOpen(false)}
                            className="text-[11px] text-primary font-bold hover:underline">Chiudi</button>
                    </div>
                </div>
            )}
        </div>
    );
}
