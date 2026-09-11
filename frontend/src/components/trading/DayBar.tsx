// ============================================================================
// DayBar.tsx — barra "GIORNATA OPERATIVA" unica per i tre bot.
//
// Prima solo Omega aveva obiettivo + barra di avanzamento, e stavano sepolti
// dentro il tab "Automatico"; Safe e Mike dichiaravano la giornata operativa
// solo nel sottotitolo di un KPI. Qui la giornata e' la PRIMA cosa che si legge
// sotto il banner di modalita', identica in tutte e tre le sezioni.
//
// Tutte le props sono opzionali: un bot senza obiettivo (Safe, Mike) mostra
// solo i contatori; Omega mostra anche obiettivo, barra, "resta"/"CENTRATO".
// ============================================================================
import { Target } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { fmtMoney, fmtPctPoints } from '@/lib/format';
import { T } from '@/lib/tradeStatus';

export interface DayBarProps {
    /** etichetta della giornata (già formattata, es. "giovedì 10 settembre 2026") */
    dayLabel: string;
    /** P&L realizzato nella giornata operativa */
    realized?: number | null;
    /** cumulato storico, come nota */
    realizedTotal?: number | null;
    /** obiettivo della giornata (0/undefined = bot senza obiettivo) */
    goal?: number | null;
    /** contatori della giornata */
    matches?: number | null;
    operations?: number | null;
    won?: number | null;
    lost?: number | null;
    live?: number | null;
    /** esposizione e risultato bloccato */
    openLiability?: number | null;
    lockedPnl?: number | null;
    /** nota libera (es. "conta SOLO le partite piazzate oggi") */
    note?: string;
    testId?: string;
    /** override dei data-testid interni (le pagine conservano i loro storici) */
    ids?: Partial<Record<'day' | 'line' | 'counts' | 'remaining' | 'goalHit', string>>;
}

export function DayBar({
    dayLabel, realized, realizedTotal, goal, matches, operations, won, lost, live,
    openLiability, lockedPnl, note, testId = 'day-bar', ids,
}: DayBarProps) {
    const tid = {
        day: ids?.day ?? 'day-bar-day',
        line: ids?.line ?? 'day-bar-line',
        counts: ids?.counts ?? 'day-bar-counts',
        remaining: ids?.remaining ?? 'day-bar-remaining',
        goalHit: ids?.goalHit ?? 'day-bar-goal-hit',
    };
    const real = realized == null ? null : Number(realized);
    const g = Number(goal ?? 0);
    const hasGoal = g > 0;
    const pct = hasGoal && real !== null ? Math.max(0, Math.min(100, (real / g) * 100)) : 0;
    const remaining = hasGoal && real !== null ? Math.max(0, g - real) : 0;
    // §5: UNA sola forma per le percentuali (lib/format), mai un replace locale
    const pctText = fmtPctPoints(pct, 1);

    return (
        <Card className="glass-card border-white/10 p-4" data-testid={testId}>
            <div className="flex items-end justify-between mb-2 gap-3 flex-wrap">
                <div>
                    <div className="flex items-center gap-2 text-sm text-slate-300">
                        <Target className="w-4 h-4 text-secondary" aria-hidden /> {T.dayBarTitle}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                        {T.operatingDay}{' '}
                        <b className="text-slate-300 capitalize" data-testid={tid.day}>{dayLabel}</b>{' '}
                        (Europe/Rome){note ? ` — ${note}` : ''}
                    </div>
                </div>
                {real !== null && (
                    <div className="font-display font-black text-2xl tabular-nums">
                        <span className={real >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtMoney(real, { signed: true })}</span>
                        {hasGoal && <span className="text-slate-500 text-lg"> · {pctText}</span>}
                    </div>
                )}
            </div>

            <div
                className="text-sm text-slate-200 flex flex-wrap items-center gap-x-3 gap-y-1 tabular-nums"
                data-testid={tid.line}
            >
                {hasGoal && <span>{T.goalToday} <b className="text-secondary">{fmtMoney(g)}</b></span>}
                {hasGoal && <span className="text-slate-600" aria-hidden>·</span>}
                {(matches != null || operations != null) && (
                    <>
                        <span data-testid={tid.counts}>
                            {matches != null && <>{T.matches} <b className="text-slate-100">{matches}</b></>}
                            {matches != null && operations != null && ' · '}
                            {operations != null && <>{T.operations} <b className="text-slate-100">{operations}</b></>}
                            {(won != null || lost != null) && (
                                <> · <b className="text-emerald-400">{won ?? 0}V</b> <b className="text-red-400">{lost ?? 0}P</b></>
                            )}
                            {live != null && live > 0 && <> · <b className="text-sky-300">{live}</b> {T.live}</>}
                        </span>
                        <span className="text-slate-600" aria-hidden>·</span>
                    </>
                )}
                {real !== null && (
                    <span>{T.realizedToday} <b className={real >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fmtMoney(real, { signed: true })}</b></span>
                )}
                {hasGoal && real !== null && <span className="text-slate-600" aria-hidden>·</span>}
                {hasGoal && real !== null && (remaining > 0 ? (
                    <span>{T.remaining} <b className="text-amber-300" data-testid={tid.remaining}>{fmtMoney(remaining)}</b></span>
                ) : (
                    <span>
                        obiettivo <b className="text-emerald-400" data-testid={tid.goalHit}>{T.goalHit}</b>
                        {real > g ? ` (${fmtMoney(real - g, { signed: true })} oltre)` : ''}
                    </span>
                ))}
                {openLiability != null && openLiability > 0 && (
                    <>
                        <span className="text-slate-600" aria-hidden>·</span>
                        <span>{T.openLiability} <b className="text-orange-400" data-testid="day-bar-liability">{fmtMoney(openLiability)}</b></span>
                    </>
                )}
                {lockedPnl != null && (
                    <>
                        <span className="text-slate-600" aria-hidden>·</span>
                        <span>{T.lockedPnl} <b className={lockedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'} data-testid="day-bar-locked">{fmtMoney(lockedPnl, { signed: true })}</b></span>
                    </>
                )}
                {realizedTotal != null && (
                    <>
                        <span className="text-slate-600" aria-hidden>·</span>
                        <span className="text-slate-500">totale storico <b className="text-slate-300">{fmtMoney(realizedTotal, { signed: true })}</b></span>
                    </>
                )}
            </div>

            {hasGoal && (
                <div
                    className="relative h-5 mt-2 rounded-full bg-black/50 border border-white/10 overflow-hidden"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(pct)}
                    aria-label="Avanzamento obiettivo di oggi"
                >
                    <div
                        className="absolute inset-y-0 left-0 bg-gradient-to-r from-emerald-500 to-secondary transition-all duration-700"
                        style={{ width: `${pct}%` }}
                    />
                    <div className="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-white/90 tabular-nums">
                        {pctText}
                    </div>
                </div>
            )}
        </Card>
    );
}

export default DayBar;
