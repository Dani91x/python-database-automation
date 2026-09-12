// ============================================================================
// PerformancePanel.tsx — KPI di periodo sulle giornate operative + equity per
// giorno + breakdown (strategia/sport/origine per Safe, gamba per Omega).
// Tutte le cifre escono dalle funzioni pure di lib/dailyHistory (testate):
// qui solo presentazione. Il selettore di periodo è controllato dal padre.
// ============================================================================
import { useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { EquityCurve } from '@/components/trading/EquityCurve';
import { EQUITY_TITLE, EQUITY_AXIS_NOTE } from '@/components/trading/EquityCard';
import { StatTile, KpiRow } from '@/components/trading/StatTile';
import {
    equityByDay, summarizeRows, aggregateBreakdown, dayLabel, WIN_LOSS_TIP,
    PERIOD_LABEL, type DailyRow, type PeriodKind, type HistoryVariant, type DailyBreakdown,
} from '@/lib/dailyHistory';
import { fmtMoney, fmtPct as fmtPctFrac, fmtNum } from '@/lib/format';

function fmtEur(v: number | null | undefined): string {
    return fmtMoney(v);
}
function fmtSignedEur(v: number | null | undefined): string {
    return fmtMoney(v, { signed: true });
}
/**
 * §1 — UNA forma per le percentuali: virgola, spazio e UN decimale, come la
 * barra della giornata (`fmtPctPoints(pct, 1)`). Prima qui erano a zero
 * decimali: «94 %» accanto a «0,0 %» nella stessa pagina, e un win rate di
 * 93,6 % arrotondato a 94 % su 52 trade.
 */
function fmtPct(v: number | null | undefined): string {
    return fmtPctFrac(v, 1);
}

const PERIODS: PeriodKind[] = ['month', '30d', '90d', 'year'];

const OMEGA_PHASE_LABEL: Record<string, string> = {
    ht_cs: 'Gamba 1T (Half Time Score)', ft_cs: 'Gamba 2T (Correct Score)', scalp: 'Scalp', none: 'Senza fase (v1/manuale)',
};
const SAFE_STRATEGY_LABEL: Record<string, string> = {
    base: 'BASE', esatto: 'R. ESATTO', punta: 'PUNTA', tennis: 'TENNIS', model: 'MODELLO', manual: 'MANUALE',
};
const MIKE_ROLE_LABEL: Record<string, string> = {
    under_entry: 'Ingresso Under 3.5', under_green: 'Green-up Under 3.5', under_last: 'Ultimo ingresso (PERSIST)',
    over_cover: 'Copertura Over 4.5', under_close: 'Chiusura Under 3.5', over_close: 'Chiusura Over 4.5',
    reentry: 'Re-ingresso Under 4.5', reentry_green: 'Green re-ingresso', manual_close: 'Chiusura manuale',
};
const STRATEGY_LABELS: Record<HistoryVariant, Record<string, string>> = {
    omega: OMEGA_PHASE_LABEL, safe: SAFE_STRATEGY_LABEL, mike: MIKE_ROLE_LABEL,
};
const SPORT_LABEL: Record<string, string> = { calcio: '⚽ Calcio', tennis: '🎾 Tennis' };
const ORIGIN_LABEL: Record<string, string> = { auto: '⚙️ Automatico', manual: '✋ Manuale' };

/**
 * §19 — il pannello aveva una copia privata di StatTile (stesse classi, altra
 * `min-w`, niente tooltip): due tessere KPI diverse nella stessa pagina. Ora si
 * usa la tessera condivisa; `Tile` resta solo come alias tipizzato locale.
 */
const Tile = StatTile;

function BreakdownTable({ title, data, labels, testId }: {
    title: string; data: Record<string, DailyBreakdown>; labels: Record<string, string>; testId: string;
}) {
    const entries = Object.entries(data).sort((a, b) => b[1].pnl - a[1].pnl);
    if (entries.length === 0) return null;
    return (
        <div className="overflow-x-auto" data-testid={testId}>
            <table className="w-full text-sm">
                <thead className="text-[11px] uppercase text-slate-500 bg-black/30">
                    <tr>
                        <th className="text-left px-3 py-2">{title}</th>
                        <th className="text-right px-3 py-2" title="aperture piazzate nel periodo">Trade</th>
                        <th className="text-right px-3 py-2" title={WIN_LOSS_TIP}>Vinti</th>
                        <th className="text-right px-3 py-2" title={WIN_LOSS_TIP}>Persi</th>
                        <th className="text-right px-3 py-2">Win rate</th>
                        <th className="text-right px-3 py-2">P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {entries.map(([k, b]) => {
                        const wr = b.won + b.lost > 0 ? b.won / (b.won + b.lost) : null;
                        return (
                            <tr key={k} className="border-t border-white/5">
                                <td className="px-3 py-1.5 font-semibold text-slate-200">{labels[k] ?? k}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums">{b.n}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums text-emerald-300">{b.won}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums text-red-300">{b.lost}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums">{fmtPct(wr)}</td>
                                <td className={`px-3 py-1.5 text-right tabular-nums font-bold ${b.pnl > 0 ? 'text-emerald-400' : b.pnl < 0 ? 'text-red-400' : 'text-slate-300'}`}>
                                    {fmtSignedEur(b.pnl)}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

export interface PerformancePanelProps {
    /** righe GIÀ filtrate sul periodo scelto */
    rows: DailyRow[];
    period: PeriodKind;
    onPeriodChange: (p: PeriodKind) => void;
    variant: HistoryVariant;
    loading?: boolean;
    /** intervallo mostrato accanto al selettore */
    range?: { from: string; to: string } | null;
    /**
     * Il periodo NON è coperto dalla finestra caricata (limite dei 400 giorni
     * dello storico): meglio dirlo che mostrare zeri che sembrano dati.
     */
    unavailable?: string | null;
}

export function PerformancePanel({ rows, period, onPeriodChange, variant, loading = false, range, unavailable = null }: PerformancePanelProps) {
    const s = useMemo(() => summarizeRows(rows), [rows]);
    const equity = useMemo(() => equityByDay(rows), [rows]);
    const byStrategy = useMemo(() => aggregateBreakdown(rows, 'by_strategy'), [rows]);
    const bySport = useMemo(() => aggregateBreakdown(rows, 'by_sport'), [rows]);
    const byOrigin = useMemo(() => aggregateBreakdown(rows, 'by_origin'), [rows]);
    const streakLabel = s.streaks.current > 0
        ? `${s.streaks.current} giornate positive di fila`
        : s.streaks.current < 0 ? `${-s.streaks.current} giornate negative di fila` : 'nessuna serie in corso';

    return (
        <div className="space-y-4" data-testid="performance-panel" aria-busy={loading || undefined}>
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Periodo</span>
                {PERIODS.map((p) => (
                    <button
                        key={p}
                        type="button"
                        onClick={() => onPeriodChange(p)}
                        aria-pressed={period === p}
                        className={`px-2.5 py-0.5 rounded-full border text-xs ${period === p ? 'bg-secondary/20 text-secondary border-secondary/40' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                    >
                        {PERIOD_LABEL[p]}
                    </button>
                ))}
                {range && (
                    <span className="text-[11px] text-slate-500 tabular-nums" data-testid="period-range">
                        {dayLabel(range.from, { year: false })} → {dayLabel(range.to)}
                    </span>
                )}
            </div>

            {unavailable && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200" data-testid="period-unavailable">
                    {unavailable}
                </div>
            )}

            <KpiRow loading={loading && rows.length === 0} tiles={10}>
                <Tile label="P&L periodo" value={fmtSignedEur(s.pnl)} tone={s.pnl > 0 ? 'pos' : s.pnl < 0 ? 'neg' : 'plain'} testId="kpi-pnl"
                    hint="somma dei P&L realizzati delle giornate del periodo"
                    sub={s.commission != null
                        // il P&L è già NETTO: la commissione è quella scritta dal
                        // servizio dove c'è, altrimenti ricavata dal netto positivo
                        ? `commissioni ${fmtEur(s.commission)} già dedotte dal P&L`
                        : `${s.days} giornate operative`} />
                <Tile label="Giornate +/−" value={`${s.positiveDays} / ${s.negativeDays}`} tone={s.positiveDays >= s.negativeDays ? 'pos' : 'neg'} testId="kpi-days"
                    hint="giornate chiuse in utile / in perdita nel periodo"
                    sub={`${s.days} giornate con attività`} />
                <Tile label="Win rate" value={fmtPct(s.winRate)} tone="plain" testId="kpi-winrate"
                    hint={WIN_LOSS_TIP}
                    sub={`${s.won}V · ${s.lost}P · ${s.void} void · ${s.hedgedClosed} chiusi o in chiusura a mercato`} />
                <Tile label="Profit factor" value={s.profitFactor == null ? '—' : fmtNum(s.profitFactor, 2)} tone={s.profitFactor == null ? 'plain' : s.profitFactor >= 1 ? 'pos' : 'neg'} testId="kpi-pf"
                    hint="quanto si incassa per ogni euro perso: sotto 1 il bot perde"
                    sub="gross profit / gross loss" />
                <Tile label="Expectancy / trade" value={fmtSignedEur(s.expectancy)} tone={s.expectancy == null ? 'plain' : s.expectancy >= 0 ? 'pos' : 'neg'} testId="kpi-expectancy"
                    hint="P&L medio per apertura regolata nel periodo"
                    sub={`${s.settled} aperture regolate · ${s.tradesPlaced} piazzate`} />
                <Tile label="Max drawdown" value={fmtEur(s.drawdown.maxDrawdown)} tone={s.drawdown.maxDrawdown > 0 ? 'danger' : 'plain'} testId="kpi-dd"
                    hint="massima discesa dell’equity dal suo picco, dentro il periodo"
                    sub={s.drawdown.currentDrawdown > 0 ? `in corso ${fmtEur(s.drawdown.currentDrawdown)} dal picco` : 'sul picco'} />
                <Tile label="Miglior giornata" value={fmtSignedEur(s.bestDay?.pnl_realized ?? null)} tone="pos" testId="kpi-best"
                    sub={s.bestDay ? dayLabel(s.bestDay.day, { year: false }) : '—'} />
                <Tile label="Peggior giornata" value={fmtSignedEur(s.worstDay?.pnl_realized ?? null)} tone="neg" testId="kpi-worst"
                    sub={s.worstDay ? dayLabel(s.worstDay.day, { year: false }) : '—'} />
                <Tile label="Serie" value={`${s.streaks.bestWin}+ / ${s.streaks.bestLoss}−`} tone="plain" testId="kpi-streak"
                    hint="giornate positive e negative consecutive: record del periodo" sub={streakLabel} />
                {variant === 'omega' && (
                    <Tile label="Obiettivo centrato" value={s.goalHit.total > 0 ? `${s.goalHit.hit}/${s.goalHit.total}` : '—'}
                        tone={s.goalHit.rate == null ? 'plain' : s.goalHit.rate >= 0.5 ? 'gold' : 'neg'} testId="kpi-goal"
                        sub={s.goalHit.rate != null
                            ? `${fmtPct(s.goalHit.rate)} delle giornate${s.goalHit.notHistorized > 0 ? ` · ${s.goalHit.notHistorized} senza obiettivo storicizzato` : ''}`
                            : s.goalHit.notHistorized > 0
                                ? `${s.goalHit.notHistorized} giornate con obiettivo non storicizzato: non giudicabili`
                                : 'nessun obiettivo registrato'} />
                )}
                {s.maxLiability != null && (
                    <Tile label="Liability max" value={fmtEur(s.maxLiability)} tone="danger" testId="kpi-liab"
                        hint="massima liability registrata su una singola posizione nel periodo" sub="massima esposizione su un trade" />
                )}
            </KpiRow>

            <Card className="glass-card border-white/10 p-4">
                <div className="text-sm text-slate-300" title={EQUITY_AXIS_NOTE}>{EQUITY_TITLE} · per giornata</div>
                <div className="text-[10px] text-slate-500 mb-2">{EQUITY_AXIS_NOTE}</div>
                <EquityCurve
                    series={equity}
                    label="Equity per giornata"
                    emptyLabel="nessuna giornata regolata nel periodo — la curva compare al primo incasso"
                />
            </Card>

            {rows.length > 0 && (
                <Card className="glass-card border-white/10 p-0 overflow-hidden divide-y divide-white/5">
                    <BreakdownTable
                        title={variant === 'safe' ? 'Strategia' : 'Gamba'}
                        data={byStrategy}
                        labels={STRATEGY_LABELS[variant]}
                        testId="breakdown-strategy"
                    />
                    {variant === 'safe' && (
                        <BreakdownTable title="Sport" data={bySport} labels={SPORT_LABEL} testId="breakdown-sport" />
                    )}
                    <BreakdownTable title="Origine" data={byOrigin} labels={ORIGIN_LABEL} testId="breakdown-origin" />
                </Card>
            )}
        </div>
    );
}

export default PerformancePanel;
