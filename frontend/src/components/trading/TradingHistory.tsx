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
    periodRange, filterRange, romeDay, addDays, historyWindow, attributionOf, dayLabel,
    statoGiornoDb, testoCriterioGiornata,
    calendarGridBounds, PERIOD_LABEL, MAX_HISTORY_DAYS,
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
    /** 30/09: da dove viene il P&L mostrato (conto Betfair / simulato / stima),
     *  con le parole di `lib/fontePnl.ts`. Assente = nessuna riga in piu'. */
    fonteNota?: string;
    /**
     * 01/10 (A-05..A-07) - la MONETA dello storico mostrato, dichiarata in
     * testa prima dei numeri («SOLDI VERI» / «PROVA»). Assente = la pagina
     * non l'ha detta: si scrive che la moneta non e' dichiarata, mai muti.
     */
    modo?: 'live' | 'paper';
    /** 01/10 - presente = la pagina permette di passare all'altra moneta: il
     *  selettore («soldi veri» / «prova») e' l'UNICA traccia dell'altra moneta */
    onModo?: (m: 'live' | 'paper') => void;
}

function monthBounds(year: number, month: number): { from: string; to: string } {
    const mm = month < 10 ? `0${month}` : String(month);
    const from = `${year}-${mm}-01`;
    const nextFirst = month === 12 ? `${year + 1}-01-01` : `${year}-${month + 1 < 10 ? '0' : ''}${month + 1}-01`;
    return { from, to: addDays(nextFirst, -1) };
}

export function TradingHistory({
    variant, fetchDaily, fetchDayTrades, onGoLive, filterKey = '', today, refreshToken = 0,
    fonteNota, modo, onModo,
}: TradingHistoryProps) {
    const todayDay = today ?? romeDay();
    const [period, setPeriod] = useState<PeriodKind>('month');
    const [ym, setYm] = useState(() => ({ year: Number(todayDay.slice(0, 4)), month: Number(todayDay.slice(5, 7)) }));
    const [selectedDay, setSelectedDay] = useState<string | null>(todayDay);
    const [rows, setRows] = useState<DailyRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    // le posizioni caricate INSIEME al giorno a cui appartengono: senza questa
    // coppia, cambiando giorno restavano a schermo i trade del giorno prima
    // sotto la data nuova (totali compresi) finché non arrivava la risposta.
    const [dayData, setDayData] = useState<{ day: string; trades: DayTrade[] } | null>(null);
    const [dayLoading, setDayLoading] = useState(false);
    const [dayError, setDayError] = useState<string | null>(null);
    const [manualRefresh, setManualRefresh] = useState(0);

    const pRange = useMemo(() => periodRange(period, todayDay), [period, todayDay]);
    const mRange = useMemo(() => monthBounds(ym.year, ym.month), [ym]);
    // la finestra deve coprire la GRIGLIA, non il solo mese: le celle di coda
    // del mese precedente e di testa del successivo sono disegnate e prima
    // dichiaravano «nessuna operazione» su giornate mai caricate.
    const gRange = useMemo(() => calendarGridBounds(ym.year, ym.month), [ym]);
    // finestra unica di caricamento = mese visualizzato (SEMPRE dentro) esteso
    // al periodo fin dove il limite dei 400 giorni lo consente (M-17). Prima la
    // finestra teneva gli ultimi 400 giorni a partire da OGGI: navigando il
    // calendario indietro di più di un anno il mese mostrato restava fuori e la
    // griglia dichiarava «nessuna operazione» su giornate che esistono.
    const loadRange = useMemo(() => historyWindow(gRange, pRange), [pRange, gRange]);

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
        if (!selectedDay) { setDayData(null); return; }
        const day = selectedDay;
        const seq = ++daySeqRef.current;
        setDayLoading(true);
        setDayError(null);
        fetchDayTrades(day)
            .then((t) => { if (seq === daySeqRef.current) { setDayData({ day, trades: t }); setDayLoading(false); } })
            .catch((e) => { if (seq === daySeqRef.current) { setDayError(String((e as Error)?.message ?? e)); setDayData({ day, trades: [] }); setDayLoading(false); } });
    }, [fetchDayTrades, selectedDay, filterKey, refreshToken, manualRefresh]);

    // i trade mostrati sono SOLO quelli del giorno selezionato: mai quelli di
    // un'altra giornata rimasti da una richiesta precedente
    const dayTrades = dayData && dayData.day === selectedDay ? dayData.trades : null;
    // R-01 (review 01/10): il «giorno della PARTITA» si dichiara solo se le
    // righe lette lo portano dal database (`in_day`); altrimenti il criterio vero
    const criterioTesto = testoCriterioGiornata(statoGiornoDb(dayTrades), [variant]);
    const periodRows = useMemo(() => filterRange(rows, pRange.from, pRange.to), [rows, pRange]);
    const onMonthChange = useCallback((year: number, month: number) => setYm({ year, month }), []);
    const onSelectDay = useCallback((day: string) => setSelectedDay(day), []);

    return (
        <div className="space-y-5" data-testid="trading-history">
            <div className="flex items-center gap-2 flex-wrap text-[11px] text-slate-500">
                {/* 01/10 (A-05..A-07): la MONETA si legge prima dei numeri, con
                    le stesse parole e gli stessi colori dello Storico dello sport */}
                <span
                    className={`text-[9.5px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                        modo === 'live' ? 'bg-red-500/20 text-red-300'
                            : modo === 'paper' ? 'bg-white/10 text-white/60' : 'bg-amber-500/15 text-amber-300'
                    }`}
                    data-testid="history-moneta" data-modo={modo ?? 'non-dichiarata'}
                >{modo === 'live' ? 'SOLDI VERI' : modo === 'paper' ? 'PROVA' : 'moneta non dichiarata'}</span>
                {onModo && (
                    <span className="flex items-center rounded-lg border border-white/10 overflow-hidden text-[10.5px] font-bold"
                        role="group" aria-label="Moneta dello storico">
                        {(['live', 'paper'] as const).map((m) => (
                            <button key={m} type="button" onClick={() => onModo(m)} aria-pressed={modo === m}
                                data-testid={`history-mode-${m}`}
                                className={`px-2 py-0.5 transition ${modo === m
                                    ? (m === 'live' ? 'bg-red-500/25 text-red-300' : 'bg-white/15 text-white/80')
                                    : 'text-slate-400 hover:text-white'}`}
                            >{m === 'live' ? 'soldi veri' : 'prova'}</button>
                        ))}
                    </span>
                )}
                {/* B-02 (01/10): UNA frase sola per i tre bot, il giorno della
                    PARTITA, ma SOLO se il database lo manda (R-01, review 01/10) */}
                <span data-testid="history-criterio">
                    {/* §1: le date si leggono nella stessa forma ovunque
                        («12 settembre 2026»), mai l'ISO grezzo accanto alle
                        etichette italiane del calendario e del dettaglio */}
                    Oggi <b className="text-slate-300">{dayLabel(todayDay)}</b> · {criterioTesto}
                    {fonteNota && <span data-testid="history-fonte-pnl"> · {fonteNota}</span>}
                </span>
                <Button variant="ghost" size="sm" className="ml-auto h-7 text-xs" onClick={() => setManualRefresh((n) => n + 1)} disabled={loading}>
                    <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />Aggiorna
                </Button>
            </div>
            {loadRange.clamped && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200" data-testid="history-clamped">
                    finestra limitata a {MAX_HISTORY_DAYS} giorni (limite dello storico): caricato
                    dal <b>{dayLabel(loadRange.from)}</b> al <b>{dayLabel(loadRange.to)}</b>
                    {loadRange.periodTruncated && <> — il mese mostrato c’è per intero, il periodo «{PERIOD_LABEL[period]}» no</>}
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
                        unavailable={loadRange.periodTruncated
                            ? `Periodo non calcolabile: con il mese di ${dayLabel(mRange.from, { year: true })} a schermo lo storico può caricare al massimo ${MAX_HISTORY_DAYS} giorni, e «${PERIOD_LABEL[period]}» resta fuori. Torna al mese corrente per rivedere questi KPI.`
                            : null} />
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
