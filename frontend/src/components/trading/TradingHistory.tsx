// ============================================================================
// TradingHistory.tsx — sezione "STORICO" (per giornata operativa) condivisa da
// Omega e Safe Strategy: calendario mensile + pannello performance di periodo
// + dettaglio del giorno selezionato.
//
// Dati: le RPC owner-only di migrations/daily_history.sql tramite i fetcher
// passati dal padre (così le pagine restano testabili con fetcher mockati).
// Una sola finestra di caricamento copre sia il mese del calendario sia il
// periodo del pannello; il dettaglio giorno si carica alla selezione.
// ============================================================================
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { DailyCalendar } from '@/components/trading/DailyCalendar';
import { PerformancePanel } from '@/components/trading/PerformancePanel';
import { DayDetail } from '@/components/trading/DayDetail';
import {
    periodRange, filterRange, romeDay, addDays, clampHistoryRange, attributionOf, MAX_HISTORY_DAYS,
    type DailyRow, type DayTrade, type PeriodKind, type HistoryVariant,
} from '@/lib/dailyHistory';

export interface TradingHistoryProps {
    variant: HistoryVariant;
    fetchDaily: (from: string, to: string) => Promise<DailyRow[]>;
    fetchDayTrades: (day: string) => Promise<DayTrade[]>;
    /** posizione ancora viva nel dettaglio → torna alla vista live */
    onGoLive?: (trade: DayTrade) => void;
    /** filtro (es. sport) mostrato sopra: cambia → ricarica */
    filterKey?: string;
    /** giornata operativa corrente (test) */
    today?: string;
    /** contatore esterno: incrementalo per forzare un ricaricamento (es. realtime) */
    refreshToken?: number;
}

function monthBounds(year: number, month: number): { from: string; to: string } {
    const mm = month < 10 ? `0${month}` : String(month);
    const from = `${year}-${mm}-01`;
    const nextFirst = month === 12 ? `${year + 1}-01-01` : `${year}-${month + 1 < 10 ? '0' : ''}${month + 1}-01`;
    return { from, to: addDays(nextFirst, -1) };
}

export function TradingHistory({
    variant, fetchDaily, fetchDayTrades, onGoLive, filterKey = '', today, refreshToken = 0,
}: TradingHistoryProps) {
    const todayDay = today ?? romeDay();
    const [period, setPeriod] = useState<PeriodKind>('month');
    const [ym, setYm] = useState(() => ({ year: Number(todayDay.slice(0, 4)), month: Number(todayDay.slice(5, 7)) }));
    const [selectedDay, setSelectedDay] = useState<string | null>(todayDay);
    const [rows, setRows] = useState<DailyRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [dayTrades, setDayTrades] = useState<DayTrade[] | null>(null);
    const [dayLoading, setDayLoading] = useState(false);
    const [dayError, setDayError] = useState<string | null>(null);
    const [manualRefresh, setManualRefresh] = useState(0);

    const pRange = useMemo(() => periodRange(period, todayDay), [period, todayDay]);
    const mRange = useMemo(() => monthBounds(ym.year, ym.month), [ym]);
    // finestra unica di caricamento = unione mese ∪ periodo, CLAMPATA a 400
    // giorni (M-17): oltre quella soglia la RPC solleva un'eccezione e prima
    // tutto lo storico sparira dietro un "Storico non disponibile".
    const loadRange = useMemo(() => clampHistoryRange(
        pRange.from < mRange.from ? pRange.from : mRange.from,
        pRange.to > mRange.to ? pRange.to : mRange.to,
    ), [pRange, mRange]);

    // guardia anti-risposte fuori ordine
    const seqRef = useRef(0);
    useEffect(() => {
        const seq = ++seqRef.current;
        setLoading(true);
        setError(null);
        fetchDaily(loadRange.from, loadRange.to)
            .then((r) => { if (seq === seqRef.current) { setRows(r); setLoading(false); } })
            .catch((e) => { if (seq === seqRef.current) { setError(String((e as Error)?.message ?? e)); setLoading(false); } });
    }, [fetchDaily, loadRange.from, loadRange.to, filterKey, refreshToken, manualRefresh]);

    const daySeqRef = useRef(0);
    useEffect(() => {
        if (!selectedDay) { setDayTrades(null); return; }
        const seq = ++daySeqRef.current;
        setDayLoading(true);
        setDayError(null);
        fetchDayTrades(selectedDay)
            .then((t) => { if (seq === daySeqRef.current) { setDayTrades(t); setDayLoading(false); } })
            .catch((e) => { if (seq === daySeqRef.current) { setDayError(String((e as Error)?.message ?? e)); setDayTrades([]); setDayLoading(false); } });
    }, [fetchDayTrades, selectedDay, filterKey, refreshToken, manualRefresh]);

    const periodRows = useMemo(() => filterRange(rows, pRange.from, pRange.to), [rows, pRange]);
    const onMonthChange = useCallback((year: number, month: number) => setYm({ year, month }), []);
    const onSelectDay = useCallback((day: string) => setSelectedDay(day), []);

    return (
        <div className="space-y-5" data-testid="trading-history">
            <div className="flex items-center gap-2 flex-wrap text-[11px] text-slate-500">
                {/* L-08: il testo dice l'ATTRIBUZIONE vera della variante, non
                    "regolati nel giorno" anche dove il giorno è il piazzamento */}
                <span>
                    Giornata operativa = fuso Europe/Rome · oggi <b className="text-slate-300 tabular-nums">{todayDay}</b> ·
                    {attributionOf(variant) === 'placed'
                        ? ' P&L realizzato = posizioni PIAZZATE nel giorno (chiusure incluse), anche se si regolano dopo'
                        : ' P&L realizzato = trade REGOLATI nel giorno (chiusure incluse)'}
                </span>
                <Button variant="ghost" size="sm" className="ml-auto h-7 text-xs" onClick={() => setManualRefresh((n) => n + 1)} disabled={loading}>
                    <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />Aggiorna
                </Button>
            </div>
            {loadRange.clamped && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200" data-testid="history-clamped">
                    finestra accorciata agli ultimi {MAX_HISTORY_DAYS} giorni (limite dello storico):
                    dal <b className="tabular-nums">{loadRange.from}</b> al <b className="tabular-nums">{loadRange.to}</b>
                </div>
            )}
            {error && (
                <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" data-testid="history-error">
                    Storico non disponibile: {error}
                </div>
            )}
            <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">
                <Card className="glass-card border-white/10 p-4 xl:col-span-2">
                    <DailyCalendar
                        rows={rows}
                        year={ym.year}
                        month={ym.month}
                        selectedDay={selectedDay}
                        onSelectDay={onSelectDay}
                        onMonthChange={onMonthChange}
                        showGoal={variant === 'omega'}
                        today={todayDay}
                        loading={loading}
                    />
                </Card>
                <div className="xl:col-span-3">
                    <PerformancePanel
                        rows={periodRows}
                        period={period}
                        onPeriodChange={setPeriod}
                        variant={variant}
                        loading={loading}
                        range={pRange}
                    />
                </div>
            </div>
            <DayDetail
                day={selectedDay}
                trades={dayTrades}
                loading={dayLoading}
                error={dayError}
                variant={variant}
                attribution={attributionOf(variant)}
                onGoLive={onGoLive}
            />
        </div>
    );
}

export default TradingHistory;
