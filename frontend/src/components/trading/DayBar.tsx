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
import { T, TIP, pnlClass } from '@/lib/tradeStatus';

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
    /**
     * 24/09 - di `realized`, la parte STIMATA (chiusa dal bot, Betfair non ha
     * ancora regolato): scritta accanto al realizzato, mai confusa col reale.
     * Assente = la pagina non la dichiara (comportamento di prima).
     */
    realizedEstimated?: number | null;
    /**
     * 24/09 - le posizioni VIVE, "se chiudo ora" (stimato): mostrato a parte e
     * sommato al realizzato SOLO per l'avanzamento della barra e il "resta".
     * "Obiettivo centrato" resta sul solo realizzato. Assente = come prima.
     */
    inProgress?: number | null;
    /**
     * Certificazione 12/09 — le parole dei contatori sono sovrascrivibili:
     * «operazioni» non significa la stessa cosa nei tre bot (cicli in Mike,
     * posizioni in Omega/Safe) e le pagine erano costrette a spiegarlo nella
     * `note`. I default restano quelli del glossario (`T.matches` /
     * `T.operations`): chi non passa nulla non cambia di una virgola.
     */
    labels?: { matches?: string; operations?: string };
    /** spiegazione dei contatori (tooltip): sostituisce quella generica */
    countsNote?: string;
    testId?: string;
    /** override dei data-testid interni (le pagine conservano i loro storici) */
    ids?: Partial<Record<'day' | 'line' | 'counts' | 'remaining' | 'goalHit', string>>;
}

export function DayBar({
    dayLabel, realized, realizedTotal, goal, matches, operations, won, lost, live,
    openLiability, lockedPnl, note, labels, countsNote, testId = 'day-bar', ids,
    realizedEstimated, inProgress,
}: DayBarProps) {
    const matchesLabel = labels?.matches?.trim() || T.matches;
    const operationsLabel = labels?.operations?.trim() || T.operations;
    const matchesTip = countsNote?.trim() || TIP.matches;
    const operationsTip = countsNote?.trim() || TIP.operations;
    const tid = {
        day: ids?.day ?? 'day-bar-day',
        line: ids?.line ?? 'day-bar-line',
        counts: ids?.counts ?? 'day-bar-counts',
        remaining: ids?.remaining ?? 'day-bar-remaining',
        goalHit: ids?.goalHit ?? 'day-bar-goal-hit',
    };
    // CERT. 13/09 — un numero illeggibile NON e' zero e non e' un traguardo:
    // con `realized` NaN la barra scriveva «obiettivo CENTRATO» in verde, e
    // `pct` NaN finiva in `style width:"NaN%"` e in `aria-valuenow="NaN"`.
    const numero = (v: unknown): number | null => {
        if (v == null) return null;
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
    };
    const real = numero(realized);
    const stimato = numero(realizedEstimated);
    const inCorso = numero(inProgress);
    const g = numero(goal) ?? 0;
    const hasGoal = g > 0;
    // 24/09: l'avanzamento = realizzato + in corso (se passato); senza
    // `inProgress` e' identico a prima
    const avanz = real !== null ? real + (inCorso ?? 0) : null;
    const pct = hasGoal && avanz !== null ? Math.max(0, Math.min(100, (avanz / g) * 100)) : 0;
    const remaining = hasGoal && avanz !== null ? Math.max(0, g - avanz) : 0;
    const centrato = hasGoal && real !== null && real >= g;
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
                        <span className={pnlClass(real)}>{fmtMoney(real, { signed: true })}</span>
                        {hasGoal && <span className="text-slate-500 text-lg"> · {pctText}</span>}
                    </div>
                )}
            </div>

            <div
                className="text-sm text-slate-200 flex flex-wrap items-center gap-x-3 gap-y-1 tabular-nums"
                data-testid={tid.line}
            >
                {hasGoal && <span title={TIP.goalToday}>{T.goalToday} <b className="text-secondary">{fmtMoney(g)}</b></span>}
                {hasGoal && <span className="text-slate-600" aria-hidden>·</span>}
                {(matches != null || operations != null) && (
                    <>
                        <span data-testid={tid.counts}>
                            {matches != null && <span title={matchesTip}>{matchesLabel} <b className="text-slate-100">{matches}</b></span>}
                            {matches != null && operations != null && ' · '}
                            {operations != null && <span title={operationsTip}>{operationsLabel} <b className="text-slate-100">{operations}</b></span>}
                            {(won != null || lost != null) && (
                                <> · <span title={TIP.winLoss}><b className="text-emerald-400">{won ?? 0}V</b> <b className="text-red-400">{lost ?? 0}P</b></span></>
                            )}
                            {live != null && live > 0 && <> · <span title={TIP.liveCount}><b className="text-sky-300">{live}</b> {T.live}</span></>}
                        </span>
                        <span className="text-slate-600" aria-hidden>·</span>
                    </>
                )}
                {real !== null && (
                    <span title={TIP.realizedToday}>{T.realizedToday} <b className={pnlClass(real)}>{fmtMoney(real, { signed: true })}</b>
                        {stimato != null && (
                            <span className="text-amber-300/80 text-xs" data-testid="day-bar-stimato"
                                title="parte chiusa dai bot ma non ancora regolata da Betfair: e' il calcolo del bot, diventera' il netto di Betfair al regolamento">
                                {' '}(di cui stimato {fmtMoney(stimato, { signed: true })})
                            </span>
                        )}
                    </span>
                )}
                {inCorso != null && (
                    <>
                        <span className="text-slate-600" aria-hidden>&middot;</span>
                        <span data-testid="day-bar-in-corso"
                            title="posizioni ancora aperte con soldi veri: quanto varrebbe chiuderle adesso. Stimato, entra nell'avanzamento della barra, non nel realizzato">
                            in corso (stimato) <b className={pnlClass(inCorso)}>{fmtMoney(inCorso, { signed: true })}</b>
                        </span>
                    </>
                )}
                {hasGoal && real !== null && <span className="text-slate-600" aria-hidden>·</span>}
                {hasGoal && real !== null && (!centrato ? (
                    <span>{T.remaining} <b className="text-amber-300" data-testid={tid.remaining}>{fmtMoney(remaining)}</b></span>
                ) : (
                    <span>
                        obiettivo <b className="text-emerald-400" data-testid={tid.goalHit}>{T.goalHit}</b>
                        {real > g ? ` (${fmtMoney(real - g, { signed: true })} oltre)` : ''}
                    </span>
                ))}
                {/* §6: la liability si mostra SEMPRE se il bot la fornisce, anche
                    a zero — prima spariva sotto lo zero e «nessuna esposizione»
                    diventava indistinguibile da «dato non passato», mentre il
                    P&L bloccato a zero restava a schermo: due regole per due
                    grandezze gemelle. */}
                {openLiability != null && (
                    <>
                        <span className="text-slate-600" aria-hidden>·</span>
                        <span title={TIP.openLiability}>{T.openLiability} <b className="text-orange-400" data-testid="day-bar-liability">{fmtMoney(openLiability)}</b></span>
                    </>
                )}
                {lockedPnl != null && (
                    <>
                        <span className="text-slate-600" aria-hidden>·</span>
                        <span title={TIP.lockedPnl}>{T.lockedPnl} <b className={pnlClass(lockedPnl)} data-testid="day-bar-locked">{fmtMoney(lockedPnl, { signed: true })}</b></span>
                    </>
                )}
                {realizedTotal != null && (
                    <>
                        <span className="text-slate-600" aria-hidden>·</span>
                        {/* CERT. 13/09 — un totale storico NEGATIVO usciva in `text-slate-300`:
                            grigio, indistinguibile da un utile. Il segno del P&L e' la prima
                            informazione della pagina, anche quando e' una nota di contorno. */}
                        <span className="text-slate-500">totale storico <b className={pnlClass(realizedTotal)}>{fmtMoney(realizedTotal, { signed: true })}</b></span>
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
